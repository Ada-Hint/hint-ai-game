"""Branded Streamlit components. Escape all respondent and editor content."""
import base64
from html import escape
from io import BytesIO
from pathlib import Path
import string
import streamlit as st

from . import engine
from .content import DEMO, FOLLOWUP, PROMPTS, STARTER
from .ranking import ranking_input

ROOT = Path(__file__).resolve().parent.parent


def html(value):
    st.markdown(value, unsafe_allow_html=True)


def stylesheet():
    fonts = []
    for name, family, weight in [("walter-neue-regular", "Walter", 400), ("walter-neue-bold", "Walter", 700), ("monument-semi-mono", "Monument", 400)]:
        if (ROOT / f"static/fonts/{name}.woff2").exists():
            fonts.append(f"@font-face{{font-family:{family};src:url('/app/static/fonts/{name}.woff2') format('woff2');font-weight:{weight};font-display:swap}}")
    st.markdown(f'<style>{"".join(fonts)}{(ROOT / "static/style.css").read_text()}</style>', unsafe_allow_html=True)


def brandbar(label="MARKETING LUNCH & LEARN"):
    logo = ROOT / "static/hint-wordmark.png"
    if logo.exists():
        data = base64.b64encode(logo.read_bytes()).decode()
        image = f'<img class="brand-logo" src="data:image/png;base64,{data}" alt="Hint">'
    else:
        image = '<span style="font-size:36px;font-weight:700;letter-spacing:-3px">hint</span>'
    html(f'<div class="brandbar">{image}<div class="brandtag">A HINT OF AI<br>{escape(label)}</div></div>')


def hero(eyebrow, title, description, badges=()):
    tags = "".join(f'<span class="badge">{escape(b)}</span>' for b in badges)
    html(f'<section class="hero"><div class="eyebrow">{escape(eyebrow)}</div><h1>{escape(title)}</h1><p>{escape(description)}</p><div class="subline">{tags}</div><div class="orb"></div><div class="orb small"></div></section>')


def footer():
    html('<div class="footer-note"><span>A LITTLE CURIOSITY GOES A LONG WAY.</span><span>HINT · LUNCH & LEARN</span></div>')


def takeaway(title, description):
    html(f'<div class="takeaway"><div class="micro">TAKE A LITTLE HINT</div><h3>{escape(title)}</h3><p>{escape(description)}</p></div>')


def result_rows(rows, denominator, survey=False, reveal_count=None):
    for i, row in enumerate(rows):
        if reveal_count is not None and i >= reveal_count:
            html(f'<div class="result-row covered">{i + 1:02d} &nbsp; · &nbsp; WAIT FOR THE REVEAL</div>')
            continue
        pct = 100 * row["count"] / denominator if denominator else 0
        unit = "respondents" if survey else "votes"
        label = f'{row["count"]} of {denominator} {unit}'
        if survey:
            label += f' · {round(pct)}%'
        html(f'<div class="result-row"><div class="result-fill" style="width:{pct:.2f}%"></div><div class="result-content"><span class="result-label">{escape(row["label"])}</span><span class="result-count">{label}</span></div></div>')


def leaderboard(state, personal_id=None):
    rows = engine.leaderboard(state)
    if not rows:
        st.info("The leaderboard will appear when players join.")
        return
    for p in rows:
        label = p["nickname"] + (" · you" if p["player_id"] == personal_id else "")
        html(f'<div class="leader"><span class="leader-rank">{p["rank"]:02d}</span><span class="leader-name">{escape(label)}</span><span class="leader-score">{p["score"]} <small>PTS</small></span></div>')
    st.caption(f"Quiz: 100 points per correct answer. Ranking: {engine.RANK_POINTS} points per correct position. Ties share a rank. No speed bonuses.")


def ranking_results(result):
    for i, row in enumerate(result['rows'], 1):
        average = row['average_rank']
        detail = f"Average position {average:.2f} · {row['first_count']} ranked first" if average is not None else 'No rankings yet'
        html(f'<div class="result-row"><div class="result-content"><span class="result-label">{i}. {escape(row["label"])}</span><span class="result-count">{detail}</span></div></div>')
    st.caption('Lower average position ranks higher. Equal averages are tied; either order within the tied positions counts in the game.')


def ranking_reveal(state, c, pid):
    labels = {o['id']: o['label'] for o in c['options']}
    saved = state['votes'].get(c['id'], {}).get(pid)
    matches = engine.ranking_matches(c, saved)
    groups = c.get('rank_groups', [[oid] for oid in c['correct']])
    st.markdown('**The correct order**')
    for i, group in enumerate(groups):
        label = ' / '.join(labels[oid] for oid in group)
        suffix = ' (tied)' if len(group) > 1 else ''
        detail = ''
        if isinstance(saved, list) and i < len(saved):
            detail = f'{"✓" if matches[i] else "✗"} Your answer: {labels.get(saved[i], "—")}'
        html(f'<div class="result-row"><div class="result-content"><span class="result-label">{i + 1}. {escape(label + suffix)}</span><span class="result-count ranking-answer">{escape(detail)}</span></div></div>')
    if c.get('snapshot'):
        with st.expander('Survey results behind this order'):
            result = c['snapshot']
            if result.get('kind') == 'ranking':
                ranking_results(result)
            else:
                result_rows(result['rows'], result['denominator'], survey=True)
            st.caption(f'{result["denominator"]} counted survey respondents. Tied items accept either order within their tied positions.')
            if result.get('kind') == 'text':
                st.caption('Counts come from reviewed text categories. Skipped and fully excluded answers are not counted; original wording stays private.')
    with st.expander('What players ranked first'):
        result_rows(engine.vote_counts(state, c), len(state['votes'].get(c['id'], {})))


def qr_code(url, width=150):
    try:
        import qrcode
    except ImportError:
        st.caption("Open the link above to join.")
        return
    qr = qrcode.QRCode(border=2, box_size=6)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#000072", back_color="#F4FBFE")
    data = BytesIO()
    image.save(data, format="PNG")
    st.image(data.getvalue(), width=width)


def prompt_library(key="prompts"):
    st.subheader("Take a useful shortcut with you.")
    kind = st.selectbox("Pick a starter", ["Anything", *PROMPTS], key=key)
    st.code(STARTER if kind == "Anything" else PROMPTS[kind], language=None)
    st.caption("Use the copy button in the prompt box. Replace the brackets with your own approved information.")
    with st.expander("A useful follow-up"):
        st.code(FOLLOWUP, language=None)
    st.caption("Work in your organization’s approved account and use information you are authorized to share.")


def walkthrough(state):
    step = state["game"]["demo_step"]
    labels = ["OPEN A CHAT", "GIVE IT A BRIEF", "REVIEW THE DRAFT", "MAKE IT MORE USEFUL"]
    st.caption("PREPARED EXAMPLE · FICTIONAL INTERNAL CAMPAIGN · NO LIVE AI CONNECTION")
    st.subheader(f"{step + 1}. {labels[step]}")
    if step == 0:
        st.write("Open Copilot or ChatGPT with your appropriate work account. Start a new chat. You don’t need a connected file or a special feature for this example.")
        with st.container(border=True):
            st.markdown("**The task**")
            st.write(DEMO["brief"])
        st.caption("A small, fictional task is a comfortable place to start.")
        if state.get("frozen_excerpts"):
            with st.expander("A few ideas from our room"):
                for excerpt in state["frozen_excerpts"]:
                    st.write(excerpt)
    elif step == 1:
        st.code(DEMO["prompt"].replace("[Paste the fictional brief here]", DEMO["brief"]), language=None)
        takeaway("Task + context + source + format", "Tell it what you want, who it’s for, what information to use, and what a useful answer looks like.")
    elif step == 2:
        with st.container(border=True):
            st.markdown("**Prepared first draft**")
            st.write(DEMO["draft"])
        takeaway("Read it like an editor.", "Does it follow the brief? Are the facts supported? What is missing? Here, the meeting link and time zone still need a human answer.")
    else:
        st.code(DEMO["followup"], language=None)
        with st.container(border=True):
            st.markdown("**Prepared revision**")
            st.write(DEMO["revision"])
        st.caption("Keep what works. Be specific about what should change. Check the next draft, too.")


def render_card(state, player_token=None, submit_vote=None, presentation=False):
    c = engine.current_card(state)
    if c is None:
        return
    g = state["game"]
    ph = engine.phase(state)
    pid = engine.digest(player_token) if player_token else None
    if c["kind"] in {"leaderboard", "finish"}:
        hero(c["section"], c["title"], c.get("explanation", ""))
        leaderboard(state, pid)
        if c["kind"] == "finish":
            prompt_library("final_prompts")
        return
    if c["kind"] == "demo":
        html(f'<div class="eyebrow">{escape(c["section"])}</div>')
        walkthrough(state)
        return
    badge = "100 POINTS" if c.get("scored") else "JUST FOR FUN"
    if c['kind'] == 'ranking' and c.get('scored'):
        badge = f'{engine.RANK_POINTS} POINTS PER CORRECT POSITION · {engine.RANK_POINTS * len(c["options"])} MAX'
    timing = f'<div class="timer"><strong>{engine.seconds_left(state):02d}</strong><span>seconds</span></div>' if ph == "open" else f'<span class="badge">{ {"ready":"GET READY", "closed":"VOTING CLOSED", "revealed":"THE REVEAL"}.get(ph, "") }</span>'
    html(f'<div class="room-top"><span class="badge blue">{escape(c.get("section", "LIVE VOTE"))}</span><span class="micro">{badge}</span>{timing}</div>')
    title_class = "room-title compact" if player_token else "room-title"
    html(f'<div class="{title_class}">{escape(c["title"])}</div>')
    if g["chat_fallback"]:
        st.info("We’re playing along in Teams chat. Further questions are unscored.")
    if c.get("low_response_poll"):
        st.caption("A live room check-in · unscored")
    if ph == "revealed":
        if c['kind'] == 'ranking':
            ranking_reveal(state, c, pid)
        elif c["kind"] == "survey":
            st.markdown("**You told us…**")
            result_rows(c["snapshot"]["rows"], c["snapshot"]["denominator"], True, g["reveal_count"])
            result = c['snapshot']
            if result.get('kind') == 'text':
                st.caption(f"Grouped written answers from {result['denominator']} respondents. Each person counts once per category. Skipped and fully excluded answers are not counted; original wording stays private.")
            elif result.get('multiple'):
                st.caption("Each person counts once per category. Multiple selections were allowed, so percentages may total more than 100%.")
            else:
                st.caption('Each person counts once. Percentages use the number who answered this question.')
            with st.expander("How the room guessed"):
                result_rows(engine.vote_counts(state, c), len(state["votes"].get(c["id"], {})))
        else:
            counts = engine.vote_counts(state, c)
            denominator = len(state["votes"].get(c["id"], {}))
            for row in counts:
                if row["id"] in c.get("correct", []):
                    row["label"] = "✓ " + row["label"]
            result_rows(counts, denominator)
        if c.get("correct") and c["kind"] not in {"survey", "ranking"}:
            labels = [o["label"] for o in c["options"] if o["id"] in c["correct"]]
            st.success("Best answer: " + " / ".join(labels))
        if pid and c.get("scored"):
            saved = state["votes"].get(c["id"], {}).get(pid)
            if c['kind'] == 'ranking' and saved:
                points = engine.answer_points(c, saved)
                matches = sum(engine.ranking_matches(c, saved))
                st.success(f'{matches} of {len(c["options"])} positions correct · +{points} points.')
            elif saved in c.get("correct", []):
                st.success("That’s 100 points. Nicely done!")
            elif saved:
                st.caption("No points this time. Take the useful bit into the next round.")
        if c.get("lesson"):
            takeaway(c["lesson"], c.get("explanation", ""))
    else:
        selected = state["votes"].get(c["id"], {}).get(pid)
        if c['kind'] == 'ranking' and pid and submit_vote and ph == 'open' and not g['chat_fallback']:
            ranking_input(c['options'], f'rank_vote_{state["frozen_version"]}_{c["id"]}_{pid}', initial=selected, submit=lambda order: submit_vote(c['id'], order))
            if selected:
                st.success('A ranking is saved. Save again to submit any changes before voting closes.')
            else:
                st.caption('Arrange the answers and select Save ranking before voting closes.')
        elif pid and submit_vote and ph == "open" and not g["chat_fallback"]:
            with st.container(key="player_answers"):
                for i, opt in enumerate(c["options"]):
                    letter = string.ascii_uppercase[i] if i < 26 else str(i + 1)
                    if st.button(f'{letter}  ·  {opt["label"]}', type="primary" if selected == opt["id"] else "secondary", width="stretch", key=f'vote_{c["id"]}_{opt["id"]}'):
                        submit_vote(c["id"], opt["id"])
            if selected:
                st.success("Vote saved. You can change it until voting closes.")
            else:
                st.caption("Tap one answer. Everyone has the same time; there’s no speed bonus.")
        else:
            options = c['options']
            if c['kind'] == 'ranking' and isinstance(selected, list):
                by_id = {o['id']: o for o in options}
                options = [by_id[oid] for oid in selected]
                st.caption('Your saved ranking')
            elif c['kind'] == 'ranking':
                st.caption('Answers are shown alphabetically. Players rank them from first to last.')
            for i, opt in enumerate(options):
                letter = string.ascii_uppercase[i] if i < 26 else str(i + 1)
                if c['kind'] == 'ranking':
                    letter = str(i + 1)
                cls = "option-card correct" if pid and selected == opt["id"] else "option-card"
                html(f'<div class="{cls}"><span class="option-letter">{letter}</span><span>{escape(opt["label"])}</span></div>')
            if ph == "ready":
                st.caption("The host will open voting shortly.")
            elif ph == "closed":
                st.caption("Answers are locked. The host will reveal the results.")
        st.caption(f'{len(state["votes"].get(c["id"], {}))} of {len(state["players"])} players have voted')
    dots = "".join(f'<i class="{"done" if i <= g["index"] else ""}"></i>' for i in range(len(g["deck"])))
    html(f'<div class="progress-dots">{dots}</div>')
    if c["id"] == "commitment" and ph == "revealed":
        prompt_library("commitment_prompts")
