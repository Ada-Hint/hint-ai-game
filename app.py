"""Run with: streamlit run app.py"""
from copy import deepcopy
from html import escape
import hmac
import json
import secrets
import time
from urllib.parse import urlencode

import streamlit as st

from hintgame import engine, ui
from hintgame.content import initial_state
from hintgame.settings import ROOT, load_settings
from hintgame.storage import SQLiteRepository, StorageError, SupabaseRepository
from hintgame.survey_ui import question_editor, render_questions
from hintgame.ranking import register_ranking_component

st.set_page_config(page_title="A Hint of AI", page_icon="💧", layout="centered", initial_sidebar_state="collapsed")
register_ranking_component()
ui.stylesheet()


@st.cache_resource
def get_repo(settings, rehearsal):
    event_id = settings.event_id + ("-rehearsal" if rehearsal else "")
    factory = engine.seed_rehearsal if rehearsal else initial_state
    if settings.backend == "supabase":
        return SupabaseRepository(settings.supabase_url, settings.supabase_key, event_id, factory)
    return SQLiteRepository(settings.sqlite_path, event_id, factory)


try:
    settings = load_settings()
    rehearsal = st.query_params.get("mode") == "rehearsal"
    repo = get_repo(settings, rehearsal)
except (StorageError, ValueError) as exc:
    ui.brandbar()
    st.error(str(exc))
    st.info("The host can check the setup steps in README.md. No responses have been submitted from this page.")
    st.stop()

view = st.query_params.get("view", "home")
event_code = settings.event_code + ("-DEMO" if rehearsal else "")
scope = "rehearsal" if rehearsal else "live"


def link(target, absolute=False, mode=None):
    params = {"view": target, "event": event_code}
    selected_mode = rehearsal if mode is None else mode
    if selected_mode:
        params["mode"] = "rehearsal"
    if mode is not None:
        params["event"] = settings.event_code + ("-DEMO" if mode else "")
    return (settings.public_url if absolute else "") + "/?" + urlencode(params)


def snapshot():
    try:
        return repo.snapshot()
    except StorageError as exc:
        st.error(str(exc))
        st.caption("No new votes can be accepted while the connection is unavailable. The host can continue in Teams chat.")
        if st.button("Try connection again"):
            st.rerun()
        st.stop()


def commit(action, message=None):
    try:
        result = repo.mutate(action)
    except (engine.RuleError, StorageError) as exc:
        st.error(str(exc))
        return None
    if message:
        st.session_state["notice"] = message
    st.rerun()
    return result


def is_host():
    return st.session_state.get("host_auth") == engine.digest(settings.host_password)


def host_commit(action, message=None):
    if not is_host():
        st.error("Sign in as the host first.")
        st.stop()
    return commit(action, message)


def require_event():
    supplied = st.query_params.get("event", "")
    if hmac.compare_digest(supplied, event_code) or st.session_state.get("event_access_" + scope) == event_code:
        return
    ui.hero("YOU’RE INVITED", "A little curiosity.\nA useful start.", "Enter the event code from your Teams invitation to join in.", ["18 MINUTES", "NO AI EXPERIENCE NEEDED"])
    with st.form("event_gate"):
        value = st.text_input("Event code", placeholder="From your host")
        if st.form_submit_button("Let me in", type="primary"):
            if hmac.compare_digest(value.strip(), event_code):
                st.session_state["event_access_" + scope] = event_code
                st.rerun()
            st.error("That code doesn’t match. Check the code in your invitation.")
    st.caption("Hosting this session?")
    st.link_button("Host sign-in", "/?view=manage")
    st.stop()


def host_login():
    if is_host():
        return
    ui.hero("THE HOST’S CORNER", "Let’s make this\na little more useful.", "Sign in to edit your survey, explore responses, and run the game.")
    with st.form("host_login"):
        password = st.text_input("Host password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")
    if submitted:
        valid = hmac.compare_digest(password, settings.host_password)
        def check(s):
            now = time.time()
            attempts = [t for t in s["login_attempts"].get("host", []) if t > now - 60]
            if len(attempts) >= 5:
                raise engine.RuleError("Too many attempts. Wait a minute before trying again.")
            s["login_attempts"]["host"] = [] if valid else attempts + [now]
            return valid
        try:
            if repo.mutate(check):
                st.session_state["host_auth"] = engine.digest(settings.host_password)
                st.rerun()
            st.error("That password doesn’t match.")
        except (engine.RuleError, StorageError) as exc:
            st.error(str(exc))
    if settings.backend == "sqlite":
        st.caption("Local preview: the generated host password is in .local/host-password.txt in the project folder.")
    st.stop()


def show_home():
    ui.hero("A HINT OF AI", "Small prompts.\nUseful possibilities.", "A little friendly competition. A few practical shortcuts. A fresh way to start with AI.", ["18 MINUTES", "PLAY ON YOUR OWN", "LEARN TOGETHER"])
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.subheader("Before we play")
            st.write("Tell us what you’re curious about. Your answers will help shape the game.")
            st.link_button("Take the survey", link("survey"), type="primary", width="stretch")
    with right:
        with st.container(border=True):
            st.subheader("Ready for the game?")
            st.write("Pick a nickname, follow your host on Teams, and add your vote.")
            st.link_button("Join the game", link("play"), width="stretch")
    st.caption("No AI account needed to play. Everyone’s starting point is welcome.")
    st.link_button("Host workspace", link("manage"))


def show_survey():
    state = snapshot()
    receipt = st.query_params.get("receipt") or st.session_state.get("survey_receipt_" + scope)
    if receipt and any(r["id"] == engine.digest(receipt) for r in state["survey"]["responses"]):
        ui.hero("YOU’RE ALL SET", "A little input.\nA better lunch & learn.", "Your answers are saved. Thanks for helping shape what we’ll explore together.", ["ANONYMOUS", "SEE YOU ON TEAMS"])
        st.success("Survey submitted. You don’t need to submit again.")
        st.caption("Your survey answers are not connected to your game nickname.")
        st.link_button("Join the game when it’s time", link("play"), type="primary")
        return
    ui.hero("BEFORE WE PLAY", "Give us\na little hint.", "Help shape our lunch and learn. No AI expertise required. Where you see ‘choose all that apply,’ you don’t have to pick just one.", ["ABOUT 5 MINUTES", "ANONYMOUS", "MULTIPLE ANSWERS WELCOME"])
    version = engine.active_version(state)
    if not version or not state["survey"]["open"]:
        st.info("The survey isn’t open right now. Your host will let you know when it’s ready.")
        st.link_button("Join the game", link("play"))
        return
    st.caption("No names or emails. The host sees responses; only whole-group results and selected, reviewed excerpts may appear in the game.")
    answers = render_questions(version["questions"], f"survey_{scope}_{version['id']}")
    answered = sum(bool(a["choices"] or a.get("ranking") or a["rating"] is not None or any(t["value"].strip() for t in a["texts"])) for a in answers.values())
    st.progress(answered / len(version["questions"]), text=f"{answered} of {len(version['questions'])} questions answered · optional questions can be skipped")
    token_key = "survey_receipt_" + scope
    token = st.session_state.setdefault(token_key, secrets.token_urlsafe(24))
    if st.button("Send my hints →", type="primary", width="stretch"):
        try:
            repo.mutate(lambda s: engine.submit_survey(s, version["id"], answers, token))
            st.query_params["receipt"] = token
            st.rerun()
        except (engine.RuleError, StorageError) as exc:
            st.error(str(exc))


def show_play():
    token_key = "player_token_" + scope
    state = snapshot()
    token = st.session_state.get(token_key)
    if not token or engine.digest(token) not in state["players"]:
        ui.hero("YOUR SEAT AT THE TABLE", "Curiosity looks\ngood on you.", "Choose a nickname. Follow the host on Teams. Vote when the question opens.", ["100 POINTS PER QUIZ ANSWER", f"{engine.RANK_POINTS} POINTS PER CORRECT RANK", "NO SPEED BONUS"])
        with st.form("join_game"):
            nickname = st.text_input("Your game nickname", max_chars=24, placeholder="Something your colleagues will recognize")
            if st.form_submit_button("I’m in →", type="primary", width="stretch"):
                token = st.session_state.setdefault("pending_token_" + scope, secrets.token_hex(12).upper())
                try:
                    repo.mutate(lambda s: engine.join_player(s, nickname, token))
                    st.session_state[token_key] = token
                    st.rerun()
                except (engine.RuleError, StorageError) as exc:
                    st.error(str(exc))
        with st.expander("Already joined? Restore your score"):
            with st.form("rejoin_game"):
                code = st.text_input("Your private rejoin code", type="password")
                if st.form_submit_button("Rejoin"):
                    code = code.strip().upper()
                    if engine.digest(code) in snapshot()["players"]:
                        st.session_state[token_key] = code
                        st.rerun()
                    st.error("That rejoin code wasn’t found in this game.")
        st.caption("No connection to your anonymous survey answers. Nicknames and game scores appear on the board.")
        return
    with st.expander("Save your private rejoin code", expanded=not st.session_state.get("saved_code_" + scope)):
        st.code(token, language=None)
        st.caption("Copy this somewhere private. If you refresh, reconnect, or switch devices, use it to restore your nickname and score.")
        if st.button("I’ve saved my code", key="save_rejoin"):
            st.session_state["saved_code_" + scope] = True
            st.rerun()
    player_live(token)


@st.fragment(run_every="2s")
def player_live(token):
    state = snapshot()
    pid = engine.digest(token)
    if pid not in state["players"]:
        st.warning("The host started a new game. Join again to play.")
        if st.button("Join the new game"):
            st.session_state.pop("player_token_" + scope, None)
            st.session_state.pop("pending_token_" + scope, None)
            st.rerun()
        return
    points = next((p["score"] for p in engine.leaderboard(state) if p["player_id"] == pid), 0)
    ui.html(f'<div class="score-strip"><strong>{escape(state["players"][pid]["nickname"])}</strong><span>{points} POINT{"S" if points != 1 else ""} · YOUR SCORE</span></div>')
    if engine.current_card(state) is None:
        ui.hero("YOU’RE IN", "A little patience.\nA lot of possibility.", "Keep this page open and follow the host on Teams. The first question will appear here automatically.", [f'{len(state["players"])} PLAYERS IN THE ROOM'])
        return
    def submit(card_id, option_id):
        commit(lambda s: engine.vote(s, token, card_id, option_id))
    ui.render_card(state, token, submit)


@st.fragment(run_every="2s")
def present_live():
    state = snapshot()
    if engine.current_card(state) is None:
        ui.hero("WELCOME TO A HINT OF AI", "A little friendly\ncompetition.", "Six questions. A few practical shortcuts. Everyone’s starting point is welcome.", ["18 MINUTES", "NO TEAMS", "NO SPEED BONUS"])
        a, b = st.columns([3, 1])
        with a:
            st.subheader("Grab a nickname. Join the room.")
            ui.html(f'<div class="join-code">{escape(event_code)}</div>')
            st.write("Open the link in Teams chat, or scan the code.")
            st.link_button("Open the player link", link("play", True))
            st.caption(f'{len(state["players"])} players ready · Quiz: 100 points per correct answer. Ranking: {engine.RANK_POINTS} points per correct position.')
        with b:
            ui.qr_code(link("play", True), 165)
    else:
        ui.render_card(state, presentation=True)


def setup_links(state):
    st.subheader("One link. Everyone in.")
    st.caption("Send the survey three business days before the session. Close it the afternoon before, review the responses, then use Run game → Start game when you’re ready to play.")
    if settings.backend == "sqlite":
        st.info("Local preview uses SQLite. Before inviting remote attendees, follow README.md to configure Supabase and deploy to Streamlit.")
    if settings.public_url.startswith("http://localhost"):
        st.caption("These links currently open on this computer. Set PUBLIC_BASE_URL to the deployed app URL before sharing remotely.")
    for title, target in [("Survey link", "survey"), ("Player link", "play"), ("Presentation link — screen-share this", "present")]:
        st.markdown(f"**{title}**")
        st.code(link(target, True), language=None)
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown("**Event code**")
        st.code(event_code, language=None)
        st.markdown("**Ready-to-copy invitation**")
        invite = f"A Hint of AI: a practical, playful lunch & learn for our marketing team.\n\nBefore we meet, take this anonymous survey. Choose multiple answers wherever you like:\n{link('survey', True)}\n\nWe’ll play individually over Teams—no AI account or experience needed. Bring your lunch and a little curiosity."
        st.code(invite, language=None)
    with c2:
        st.caption("PLAYER QR CODE")
        ui.qr_code(link("play", True), 170)
    st.divider()
    st.subheader("Rehearse without touching real responses.")
    st.write("Rehearsal is a separate event with eight clearly synthetic survey responses. Open its host, board, and player links in separate tabs.")
    if rehearsal:
        st.link_button("Return to the real event", link("manage", mode=False))
        if st.checkbox("Replace rehearsal data with fresh sample responses") and st.button("Reset rehearsal"):
            def reset(s):
                s.clear()
                s.update(engine.seed_rehearsal())
            host_commit(reset, "Rehearsal reset. Real event data was not changed.")
    else:
        st.link_button("Open rehearsal workspace", link("manage", mode=True), type="primary")
    st.divider()
    st.markdown("**Facilitator guide:** see HOST_GUIDE.md in the project folder for timing, teaching notes, and fallback instructions.")


def survey_results(state):
    st.subheader("Survey results & game categories")
    versions = state["survey"]["versions"]
    if not versions:
        st.info("Publish your survey to begin collecting responses.")
        return
    selected = st.selectbox("Survey version", [v["id"] for v in reversed(versions)], format_func=lambda vid: next(f'Version {v["number"]}{" · active" if vid == state["survey"]["active_version"] else " · archived"}' for v in versions if v["id"] == vid))
    version = next(v for v in versions if v["id"] == selected)
    responses = engine.responses_for(state, selected)
    st.metric("Anonymous responses", len(responses))
    st.caption("Review responses, group written answers, then create linked game rounds. Each person counts once per category. Original written answers stay private unless you approve an excerpt.")
    for q in version["questions"]:
        with st.expander(q["title"], expanded=q["id"] in {"frequency", "confidence"}):
            if q["kind"] in {"choice", "rating", "ranking", "text"}:
                result = engine.aggregate(state, q["id"], selected)
                if q["kind"] == "ranking":
                    ui.ranking_results(result)
                else:
                    ui.result_rows(result["rows"], result["denominator"], survey=True)
                if q['kind'] == 'text':
                    st.caption(f"{result['denominator']} respondents with grouped answers · {result['answered']} respondents wrote an answer · {result['ungrouped']} ungrouped entries · {result['excluded']} excluded entries")
                    st.caption('Each person counts once per category. Percentages use respondents with at least one grouped answer; skipped and fully excluded answers are not counted.')
                    if result['ungrouped']:
                        st.warning('Review every written response: assign a category or explicitly exclude it before using this question in a game.')
                    elif not result['rows']:
                        st.info('Categories will appear here as you group written responses below.')
                else:
                    st.caption(f'{result["denominator"]} respondents answered this question.')
            entries = engine.text_entries(state, q["id"], selected)
            if entries:
                st.markdown("**Written responses · original wording stays private unless approved as an excerpt**")
                st.caption("Group similar answers under the same category. Only category labels and counts appear on game boards.")
            active = selected == state["survey"]["active_version"]
            for i, entry in enumerate(entries):
                st.write(entry["value"])
                if q["kind"] in {"choice", "text"} and active:
                    choices = (q["options"] if q["kind"] == "choice" else []) + state["survey"]["categories"].get(engine.mapping_key(selected, q["id"]), [])
                    choices = [o for o in choices if not o.get("other")]
                    labels = {"": "Not grouped yet" if q["kind"] == "text" else "Keep under Other", **{o["id"]: o["label"] for o in choices}, "__new__": "＋ Create a category"}
                    if q["kind"] == "text":
                        labels[engine.EXCLUDED_CATEGORY] = "Exclude from game counts"
                    mapped = state["survey"]["mappings"].get(entry["key"], "")
                    keys = list(labels)
                    chosen = st.selectbox("Count this response under", keys, format_func=labels.get, index=keys.index(mapped) if mapped in keys else 0, key="map_" + entry["key"] + "_" + (mapped or "unassigned"), disabled=state["frozen"])
                    new_label = st.text_input("New category name", key="new_" + entry["key"] + "_" + (mapped or "unassigned")) if chosen == "__new__" else None
                    if st.button("Save category", key="save_" + entry["key"], disabled=state["frozen"]):
                        if chosen == "__new__" and not (new_label or "").strip():
                            st.error("Enter a name for the new category.")
                        else:
                            host_commit(lambda s, qid=q["id"], key=entry["key"], choice=chosen, label=new_label: engine.categorize(s, qid, key, choice or None if choice != "__new__" else None, label))
                if active:
                    approved = entry["key"] in state["survey"]["approved"]
                    if st.button("Remove from approved excerpts" if approved else "Approve excerpt for the walkthrough", key="approve_" + entry["key"], disabled=state["frozen"]):
                        host_commit(lambda s, qid=q["id"], key=entry["key"], value=not approved: engine.approve_entry(s, qid, key, value))
                st.divider()
            if active and q['kind'] in {'choice', 'text', 'ranking'}:
                st.markdown('**Make a game round from these results**')
                st.caption('This creates a linked card. You can adjust its wording and place it in the deck under Game content. Text categories must be reviewed before starting; ranking rounds need at least five counted respondents.')
                game_title = st.text_input('Game question', value='Which answer came up most often? ' + q['title'], key='new_round_title_' + q['id'], disabled=state['frozen'])
                left, right = st.columns(2)
                if q['kind'] != 'ranking' and left.button('＋ Guess the room', key='add_guess_' + q['id'], disabled=state['frozen']):
                    host_commit(lambda s, qid=q['id'], title=game_title: engine.add_survey_card(s, qid, 'survey', title), 'Linked Guess the room card added. Find it in Game content to adjust wording and order.')
                if right.button('＋ Rank the room', key='add_rank_' + q['id'], disabled=state['frozen']):
                    host_commit(lambda s, qid=q['id'], title=game_title: engine.add_survey_card(s, qid, 'ranking', title), 'Linked ranking card added. Find it in Game content to adjust wording, top answers, and order.')
    export = {"version": version, "responses": responses, "counts": {q["id"]: engine.aggregate(state, q["id"], selected) for q in version["questions"]}, "grouping": {q["id"]: {"categories": state["survey"]["categories"].get(engine.mapping_key(selected, q["id"]), []), "assignments": {e["key"]: state["survey"]["mappings"].get(e["key"]) for e in engine.text_entries(state, q["id"], selected)}} for q in version["questions"]}}
    st.download_button("Download anonymous survey results", json.dumps(export, indent=2), file_name=f'hint-survey-v{version["number"]}.json', mime="application/json")


def content_editor(state):
    st.subheader("Your questions. Your teaching moments.")
    st.caption("Create linked Guess the room or ranking rounds from Survey results after grouping written answers. Edit each card’s wording and place it in the game here.")
    if state["frozen"]:
        st.info("Game content is saved for the current game. Use Run game → Reset game / unlock editing to make changes; survey responses will be preserved.")
        return
    cards = state["cards"]
    labels = {c["id"]: f'{i + 1}. {c["title"]}' for i, c in enumerate(cards)}
    if "pending_edit_card" in st.session_state:
        st.session_state["edit_card_id"] = st.session_state.pop("pending_edit_card")
    cid = st.selectbox("Game card", list(labels), format_func=labels.get, key="edit_card_id")
    c = next(c for c in cards if c["id"] == cid)
    kinds = {"quiz": "Quiz", "poll": "Live poll", "survey": "Guess the room", "ranking": "Ranking (drag to order)"}
    kind = st.selectbox("Game response type", list(kinds), format_func=kinds.get, index=list(kinds).index(c["kind"]), key="card_kind_" + cid) if c["kind"] in kinds else c["kind"]
    source = c.get("ranking_source", "manual")
    if kind == "ranking":
        source = st.radio("Correct order comes from", ["manual", "survey"], format_func=lambda x: "Host-set order" if x == "manual" else "Survey results", index=["manual", "survey"].index(source), key="rank_source_" + cid)
    revision = engine.digest(str(c))[:10]
    with st.form(f"card_editor_{cid}_{kind}_{source}_{revision}"):
        title = st.text_area("Question or title", value=c["title"], height=100)
        section = st.text_input("Round label", value=c.get("section", ""))
        lesson = st.text_input("Takeaway headline", value=c.get("lesson", ""))
        explanation = st.text_area("Host explanation", value=c.get("explanation", ""))
        options = deepcopy(c.get("options", []))
        correct = list(c.get("correct", []))
        survey_qid = c.get("survey_question_id")
        poll_title = c.get("poll_title", "")
        top_n = c.get("top_n", 5)
        editable = kind in {"quiz", "poll"} or (kind == "ranking" and source == "manual")
        if editable:
            initial = options or [{"id": f"{cid}_{i}", "label": f"Answer {i + 1}"} for i in range(2)]
            initial = [{**o, "correct": o["id"] in correct, "rank": correct.index(o["id"]) + 1 if o["id"] in correct else i + 1} for i, o in enumerate(initial)]
            st.caption("Add or delete answer rows. For ranking, enter each correct position from 1 to the number of answers." if kind == "ranking" else "Add or delete answer rows. For quizzes, mark the correct answer(s).")
            rows = st.data_editor(initial, key=f"card_options_{cid}_{kind}_{revision}", num_rows="dynamic", hide_index=True, width="stretch", column_config={
                "id": None, "exclusive": None, "other": None,
                "label": st.column_config.TextColumn("Answer", required=True),
                "correct": st.column_config.CheckboxColumn("Correct", default=False) if kind == "quiz" else None,
                "rank": st.column_config.NumberColumn("Correct position", min_value=1, step=1, required=True) if kind == "ranking" else None,
            })
        if kind == "survey" or (kind == "ranking" and source == "survey"):
            version = engine.active_version(state)
            allowed = {"choice", "text", "ranking"} if kind == "ranking" else {"choice", "text"}
            survey_qs = [q for q in (version["questions"] if version else state["survey"]["draft"]) if q["kind"] in allowed]
            if survey_qs:
                qlabels = {q["id"]: q["title"] for q in survey_qs}
                ids = list(qlabels)
                survey_qid = st.selectbox("Survey question feeding this board", ids, format_func=qlabels.get, index=ids.index(survey_qid) if survey_qid in ids else 0)
            else:
                survey_qid = None
                st.info("Add and publish a choice, text, or ranking survey question first.")
            if kind == "ranking":
                top_n = st.number_input("Number of top answers to rank", min_value=2, max_value=20, value=top_n)
                st.caption("Choice and grouped-text results rank by response count; ranking results use average position. Tied answers accept either order within their tied positions. Ties at the cutoff are included. At least five survey responses are required.")
            else:
                poll_title = st.text_input("Live-poll wording if fewer than five people answer", value=poll_title)
        if st.form_submit_button("Save game card", type="primary"):
            try:
                if editable:
                    options = engine.clean_options(rows, c.get("options", []))
                    if kind == "ranking":
                        positions = [r.get("rank") for r in rows]
                        if any(not isinstance(n, (int, float)) or isinstance(n, bool) for n in positions) or sorted(positions) != list(range(1, len(rows) + 1)):
                            raise engine.RuleError("Use each correct position once, from 1 to the number of answers.")
                        correct = [o["id"] for _, o in sorted(zip(positions, options), key=lambda item: item[0])]
                    else:
                        correct = [o["id"] for o, row in zip(options, rows) if row.get("correct") is True] if kind == "quiz" else []
                updated = {**c, "kind": kind, "title": title.strip(), "section": section.strip(), "lesson": lesson.strip(), "explanation": explanation.strip(), "options": options, "correct": correct, "scored": kind in {"quiz", "ranking"}}
                if kind in {"survey", "ranking"}:
                    updated.update(survey_question_id=survey_qid, poll_title=poll_title, ranking_source=source, top_n=int(top_n))
                host_commit(lambda s: engine.save_cards(s, [updated if card["id"] == cid else card for card in s["cards"]]), "Game card saved.")
            except engine.RuleError as exc:
                st.error(str(exc))
    cols = st.columns(3)
    def move_card(s, offset):
        updated = list(s["cards"])
        index = next(i for i, card in enumerate(updated) if card["id"] == cid)
        target = index + offset
        if 0 <= target < len(updated):
            updated[index], updated[target] = updated[target], updated[index]
            engine.save_cards(s, updated)
    if cols[0].button("↑ Move card up", disabled=cards[0]["id"] == cid):
        host_commit(lambda s: move_card(s, -1))
    if cols[1].button("↓ Move card down", disabled=cards[-1]["id"] == cid):
        host_commit(lambda s: move_card(s, 1))
    if cols[2].button("Remove game card", disabled=len(cards) == 1):
        host_commit(lambda s: engine.save_cards(s, [card for card in s["cards"] if card["id"] != cid]))
    if st.button("＋ Add a ranking round"):
        new_card = {"id": engine.new_id(), "kind": "ranking", "title": "Rank the most annoying marketing tasks", "section": "RANK THE ROOM", "ranking_source": "manual", "options": [{"id": "A", "label": "Reporting"}, {"id": "B", "label": "Meeting notes"}, {"id": "C", "label": "Content revisions"}], "correct": ["A", "B", "C"], "scored": True}
        def add(s):
            updated = list(s["cards"])
            index = next((i for i, card in enumerate(updated) if card["kind"] == "finish"), len(updated))
            updated.insert(index, new_card)
            engine.save_cards(s, updated)
        st.session_state["pending_edit_card"] = new_card["id"]
        host_commit(add, "Ranking round added. Set its correct order or connect survey results.")


def host_tab_jump(tab):
    st.session_state["host_tab"] = tab


@st.fragment(run_every="2s")
def host_live():
    if not is_host():
        st.stop()
    state = snapshot()
    g = state["game"]
    ph = engine.phase(state)
    c = engine.current_card(state)
    running = c is not None and ph != "finished"
    deck = g["deck"] if state["frozen"] else state["cards"]
    readiness = engine.start_readiness(state) if c is None else None
    status = "GAME FINISHED" if ph == "finished" else "GAME RUNNING" if running else "GAME NOT STARTED"
    status_class = "finished" if ph == "finished" else "running" if running else "waiting"
    stage = {"ready": "Voting not open", "open": "Voting open", "closed": "Voting closed", "revealed": "Results revealed"}.get(ph, "Waiting to start")
    if c and not c.get("options"):
        stage = {"demo": "Walkthrough", "leaderboard": "Leaderboard", "finish": "Final leaderboard"}.get(c["kind"], "Presenting")
    if ph == "finished":
        stage = "Final scores are saved"
    with st.container(border=True, key="host_controls"):
        ui.html(f'<div class="host-status"><span class="host-status-pill {status_class}">{status}</span><span>{escape(stage)}</span></div>')
        if c is None:
            st.subheader("Ready to start your game")
            st.write("Start the game to show the first card on players’ screens. You’ll open voting when everyone is ready.")
            if st.button("Start game", type="primary", width="stretch", disabled=bool(readiness['error']), key="host_start_game"):
                host_commit(engine.start_game, "Game started. Open voting when everyone is ready.")
            st.caption("Starting closes the survey and saves its results for this game." if not state['frozen'] else "Survey results are already saved for this game. You’re ready to start.")
            if readiness['error']:
                st.error("Before you can start: " + readiness['error'])
                left, right = st.columns(2)
                left.button("Go to Edit survey", on_click=host_tab_jump, args=("Edit survey",), width="stretch")
                right.button("Go to Game content", on_click=host_tab_jump, args=("Game content",), width="stretch")
            elif readiness['polls']:
                st.info(f'{len(readiness["polls"])} survey round(s) have fewer than five responses and will run as unscored live polls. You can still start.')
            if not state['players']:
                st.caption("No players have joined yet. Share the player link below; you can also start now for a solo rehearsal.")
        elif ph == "finished":
            st.subheader("Game complete")
            st.write("The session is complete. Players can still see their scores and takeaways. To run it again, use Reset game below.")
        else:
            st.caption(f'CARD {g["index"] + 1} OF {len(deck)} · {c.get("section", "")}')
            st.subheader(c["title"])
            if c.get("options"):
                if ph == "ready":
                    st.write("Players can see the question. Read it aloud, then open voting to start the 30-second timer.")
                    if st.button("Open voting · 30 seconds", type="primary", width="stretch"):
                        host_commit(lambda s: engine.game_action(s, "open"))
                elif ph in {"open", "closed"}:
                    votes = len(state['votes'].get(c['id'], {}))
                    players = len(state['players'])
                    if ph == "open":
                        ui.html(f'<div class="host-vote-stats"><strong>{engine.seconds_left(state)}<small> seconds left</small></strong><span>{votes} / {players} players answered</span></div>')
                        st.write("Players are answering now. Close voting when you’re ready, or give them more time.")
                    else:
                        st.write(f"Answers are locked · {votes} of {players} players answered. Reveal the results to show the answers" + (" and award points." if c.get("scored") else ". This round is unscored."))
                    primary, secondary = st.columns([2, 1])
                    if ph == "open":
                        if primary.button("Close voting", type="primary", width="stretch"):
                            host_commit(lambda s: engine.game_action(s, "close"))
                    elif primary.button("Reveal results", type="primary", width="stretch"):
                        host_commit(lambda s: engine.game_action(s, "reveal"))
                    if secondary.button("＋ 15 seconds" if ph == "open" else "Reopen · 15 seconds", width="stretch"):
                        host_commit(lambda s: engine.game_action(s, "extend"))
                elif ph == "revealed":
                    st.write("Results are on screen. Points have been added to the leaderboard." if c.get("scored") else "Results are on screen. This round is unscored.")
                    if c["kind"] == "survey":
                        total = len(c['snapshot']['rows'])
                        remaining = total - g['reveal_count']
                        st.caption(f"{g['reveal_count']} of {total} survey answers revealed.")
                        if remaining > 0:
                            left, right = st.columns(2)
                            if left.button("Reveal next answer", type="primary", width="stretch"):
                                host_commit(lambda s: engine.game_action(s, "reveal_next"))
                            if right.button("Reveal all answers", width="stretch"):
                                host_commit(lambda s: engine.game_action(s, "reveal_all"))
                    else:
                        remaining = 0
                    last = g['index'] == len(deck) - 1
                    if st.button("Finish game" if last else "Next card →", type="secondary" if remaining else "primary", width="stretch"):
                        host_commit(lambda s: engine.game_action(s, "next"))
            else:
                if c['kind'] == 'demo':
                    st.write(f'Walkthrough step {g["demo_step"] + 1} of 4. Talk through the example shown below, then continue.')
                    if g['demo_step'] < 3 and st.button("Next walkthrough step →", type="primary", width="stretch"):
                        host_commit(lambda s: engine.game_action(s, "demo_next"))
                else:
                    st.write("The leaderboard is on screen. Give the room a moment, then continue.")
                if c['kind'] != 'demo' or g['demo_step'] == 3:
                    last = g['index'] == len(deck) - 1
                    if st.button("Finish game" if last else "Next card →", type="primary", width="stretch"):
                        host_commit(lambda s: engine.game_action(s, "next"))
            if g['index'] + 1 < len(deck):
                st.caption("Up next: " + deck[g['index'] + 1]['title'])
        if g['chat_fallback']:
            st.info("Teams chat mode is on. Continue using these controls; further questions are unscored.")
        ui.html(f'<div class="host-room-meta"><span><strong>{len(state["players"])}</strong> players joined</span><span><strong>{len(engine.responses_for(state))}</strong> survey responses</span><span><strong>{len(deck)}</strong> game cards</span></div>')

    if running:
        st.progress((g['index'] + 1) / len(deck), text=f'Game in progress · Card {g["index"] + 1} of {len(deck)} · Updates automatically')
    st.markdown("**Share with your players**")
    left, right = st.columns(2)
    left.link_button("Open presentation board ↗", link("present"), width="stretch")
    right.link_button("Open player join page ↗", link("play"), width="stretch")
    st.caption("Share the presentation tab in Teams. Keep this host dashboard open to run the game. Opening the board does not start the game.")
    with st.expander("Copy player link and event code"):
        st.code(link("play", True), language=None)
        st.write("Event code: " + event_code)
    if c:
        with st.expander("Audience view · current card", expanded=True):
            ui.render_card(state, presentation=True)
        if c.get('explanation') and not c.get('lesson'):
            with st.expander("Host notes"):
                st.write(c['explanation'])
    else:
        st.caption("How to run a round: Start game → Open voting → Close voting → Reveal results → Next card.")
    if running and not g["chat_fallback"]:
        with st.expander("Connection trouble? Switch to Teams chat"):
            st.write("Ask everyone to type their answer (or ranked order) in Teams chat. Continue revealing and advancing here. Scores earned so far stay; further questions are unscored.")
            if st.button("Continue in Teams chat · stop further scoring"):
                host_commit(lambda s: engine.game_action(s, "chat_fallback"))
    with st.expander("Reset game / unlock editing"):
        st.caption("This clears game players, votes, and scores. Survey versions and responses are preserved.")
        confirmed = st.checkbox("I want to clear this game and start a new one", key="confirm_game_reset")
        if st.button("Reset game", disabled=not confirmed):
            host_commit(engine.reset_game, "Game reset. You can edit or start again; survey responses were preserved.")


def show_manage():
    host_login()
    ui.html('<div class="host-heading"><h1>Game control room</h1><p>Start the game here. Guide the room one card at a time.</p></div>')
    tab = st.radio("Host workspace", ["Run game", "Edit survey", "Survey results", "Game content", "Setup & links"], horizontal=True, label_visibility="collapsed", key="host_tab")
    if tab == "Run game":
        host_live()
    elif tab == "Edit survey":
        question_editor(snapshot(), host_commit)
    elif tab == "Survey results":
        survey_results(snapshot())
    elif tab == "Game content":
        content_editor(snapshot())
    else:
        setup_links(snapshot())
    st.divider()
    if st.button("Sign out"):
        st.session_state.pop("host_auth", None)
        st.rerun()


ui.brandbar("REHEARSAL · SAMPLE DATA" if rehearsal else "MARKETING LUNCH & LEARN")
if rehearsal:
    ui.html('<div class="rehearsal">REHEARSAL · Synthetic survey responses · Separate from the real event</div>')
if "notice" in st.session_state:
    st.success(st.session_state.pop("notice"))
if view == "manage":
    show_manage()
else:
    require_event()
    if view == "survey":
        show_survey()
    elif view == "play":
        show_play()
    elif view == "present":
        present_live()
    else:
        show_home()
ui.footer()
