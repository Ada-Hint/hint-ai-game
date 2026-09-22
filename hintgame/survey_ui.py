"""Survey inputs and the host's question editor."""
from copy import deepcopy
from html import escape
import json
import streamlit as st

from . import engine, ui
from .content import question, open_ended_survey_questions
from .ranking import ranking_input


def exclusive_changed(widget_key, exclusive_ids):
    current = st.session_state.get(widget_key, [])
    previous = st.session_state.get(widget_key + "_previous", [])
    added = [v for v in current if v not in previous]
    added_exclusive = [v for v in added if v in exclusive_ids]
    if added_exclusive:
        current = [added_exclusive[-1]]
    elif any(v not in exclusive_ids for v in added):
        current = [v for v in current if v not in exclusive_ids]
    st.session_state[widget_key] = current
    st.session_state[widget_key + "_previous"] = current


def checkbox_choice_changed(key, oid, option_ids, exclusive_ids):
    if not st.session_state.get(f'{key}_choice_{oid}'):
        return
    clear = set(option_ids) - {oid} if oid in exclusive_ids else exclusive_ids
    for other in clear:
        st.session_state[f'{key}_choice_{other}'] = False


def repeatable_text(key, multiple, label="Your response"):
    count_key = key + "_count"
    count = st.session_state.setdefault(count_key, 1)
    if not multiple:
        count = 1
    values = []
    for i in range(count):
        value = st.text_input(f"{label} {i + 1}" if multiple else label, key=f"{key}_{i}", max_chars=1000, placeholder="A few words are plenty…")
        values.append({"id": str(i), "value": value})
    if multiple:
        c1, c2 = st.columns(2)
        if c1.button("＋ Add another response", key=key + "_add"):
            st.session_state[count_key] = count + 1
            st.rerun()
        if count > 1 and c2.button("Remove last entry", key=key + "_remove"):
            st.session_state.pop(f"{key}_{count - 1}", None)
            st.session_state[count_key] = count - 1
            st.rerun()
    return values


def render_questions(questions, prefix):
    answers = {}
    for i, q in enumerate(questions):
        key = f"{prefix}_{q['id']}"
        with st.container(border=True):
            hint = "CHOOSE ALL THAT APPLY" if q["kind"] == "choice" and q["multiple"] else {"choice": "CHOOSE ONE", "rating": "YOUR CONFIDENCE", "text": "IN YOUR OWN WORDS", "ranking": "RANK FROM FIRST TO LAST"}[q["kind"]]
            if not q["required"]:
                hint += " · OPTIONAL"
            ui.html(f'<div class="q-number">{i + 1:02d} / {len(questions):02d} &nbsp; · &nbsp; {hint}</div><div class="question-title">{escape(q["title"])}</div>')
            if q.get("help"):
                st.caption(q["help"])
            choices, texts, rating = [], [], None
            ranking = []
            if q["kind"] == "choice":
                labels = {o["id"]: o["label"] for o in q["options"]}
                if q["multiple"]:
                    exclusive_ids = {o['id'] for o in q['options'] if o.get('exclusive')}
                    if q.get('display') == 'checkboxes':
                        for oid, label in labels.items():
                            if st.checkbox(label, key=f'{key}_choice_{oid}', on_change=checkbox_choice_changed, args=(key, oid, list(labels), exclusive_ids)):
                                choices.append(oid)
                    else:
                        choices = st.multiselect(q["title"], list(labels), format_func=labels.get, key=key, placeholder="Select all that apply", label_visibility="collapsed", on_change=exclusive_changed, args=(key, exclusive_ids))
                else:
                    selected = st.radio(q["title"], list(labels), format_func=labels.get, index=None, key=key, label_visibility="collapsed")
                    choices = [selected] if selected is not None else []
                if any(o.get("other") and o["id"] in choices for o in q["options"]):
                    texts = repeatable_text(key + "_other", True, "Something else")
            elif q['kind'] == 'ranking':
                ranking = ranking_input(q['options'], key + '_ranking')
            elif q["kind"] == "rating":
                rating = st.radio(q["title"], list(range(q["minimum"], q["maximum"] + 1)), index=None, horizontal=True, key=key, label_visibility="collapsed")
                st.caption(f'{q["minimum"]} — {q.get("low_label", "")} · {q["maximum"]} — {q.get("high_label", "")}')
            else:
                texts = repeatable_text(key, q["multiple"])
            answers[q["id"]] = {"choices": choices, "texts": texts, "rating": rating}
            if q['kind'] == 'ranking':
                answers[q['id']]['ranking'] = ranking
    return answers


def question_editor(state, commit):
    draft = state["survey"]["draft"]
    st.subheader("Make the survey yours.")
    st.caption("Draft edits stay private until you publish. Existing published responses are always preserved.")
    if not draft:
        st.info("Add your first question below.")
    else:
        labels = {q["id"]: f'{i + 1}. {q["title"]}' for i, q in enumerate(draft)}
        qid = st.selectbox("Question to edit", list(labels), format_func=labels.get, key="edit_qid")
        q = next(q for q in draft if q["id"] == qid)
        types = {"choice": "Choices", "rating": "Rating scale", "text": "Short text", "ranking": "Ranking (drag to order)"}
        kind = st.selectbox("Response type", list(types), format_func=types.get, index=list(types).index(q["kind"]), key=f"q_kind_{qid}")
        with st.form(f"edit_question_{qid}_{kind}"):
            title = st.text_input("Question", value=q["title"], max_chars=500)
            helper = st.text_input("Helpful note", value=q.get("help", ""))
            required = st.checkbox("Required", value=q["required"])
            multiple = st.checkbox("Allow multiple responses", value=q["multiple"] if kind in {'choice', 'text'} else False, disabled=kind in {'rating', 'ranking'}, help="Choice questions accept multiple selections; text questions get an Add another response button.")
            options = q["options"]
            display = q.get('display', 'dropdown')
            if kind == 'choice':
                display = st.selectbox('Multiple-choice layout', ['dropdown', 'checkboxes'], index=['dropdown', 'checkboxes'].index(display), format_func=lambda value: 'Tick boxes' if value == 'checkboxes' else 'Dropdown', help='Used when multiple responses are allowed. Single-choice questions use radio buttons.')
            minimum, maximum = q["minimum"], q["maximum"]
            low_label, high_label = q.get("low_label", ""), q.get("high_label", "")
            if kind in {"choice", "ranking"}:
                st.caption("Add or delete rows to change choices. ‘Exclusive’ means that answer must be selected alone. ‘Other’ opens repeatable text fields." if kind == 'choice' else "Add the answers people will rank. First means highest priority. Results show average position; lower is higher-ranked.")
                initial = options or [{"id": f'{qid}_{i}', "label": f"Option {i + 1}", "exclusive": False, "other": False} for i in range(2)]
                options = st.data_editor(initial, key=f'question_options_{qid}_{kind}_{engine.digest(str(q))[:10]}', num_rows="dynamic", hide_index=True, width="stretch", column_config={"id": None, "label": st.column_config.TextColumn("Answer", required=True), "exclusive": st.column_config.CheckboxColumn("Exclusive", default=False) if kind == 'choice' else None, "other": st.column_config.CheckboxColumn("Other", default=False) if kind == 'choice' else None})
            if kind == "rating":
                c1, c2 = st.columns(2)
                minimum = c1.number_input("Minimum", min_value=1, max_value=9, value=q["minimum"])
                maximum = c2.number_input("Maximum", min_value=2, max_value=10, value=q["maximum"])
                low_label = st.text_input("Low-end label", value=low_label)
                high_label = st.text_input("High-end label", value=high_label)
            if st.form_submit_button("Save question", type="primary"):
                cleaned_options = engine.clean_options(options, q['options'])
                if kind == 'ranking':
                    for o in cleaned_options:
                        o.update(exclusive=False, other=False)
                updated = {**q, "kind": kind, "title": title.strip(), "help": helper.strip(), "required": required, "multiple": multiple if kind in {'choice', 'text'} else False, "options": cleaned_options, "minimum": int(minimum), "maximum": int(maximum), "low_label": low_label, "high_label": high_label}
                if kind == 'choice':
                    updated['display'] = display
                def save(s):
                    questions = [updated if item["id"] == qid else item for item in s["survey"]["draft"]]
                    engine.save_draft(s, questions)
                commit(save, "Question saved.")
        cols = st.columns(4)
        def move(s, offset):
            qs = s["survey"]["draft"]
            index = next(i for i, item in enumerate(qs) if item["id"] == qid)
            target = index + offset
            if 0 <= target < len(qs):
                qs[index], qs[target] = qs[target], qs[index]
        if cols[0].button("↑ Move up", disabled=draft[0]["id"] == qid, width="stretch"):
            commit(lambda s: move(s, -1))
        if cols[1].button("↓ Move down", disabled=draft[-1]["id"] == qid, width="stretch"):
            commit(lambda s: move(s, 1))
        if cols[2].button("Duplicate", width="stretch"):
            def duplicate(s):
                source = next(item for item in s["survey"]["draft"] if item["id"] == qid)
                copy = deepcopy(source)
                copy.update(id=engine.new_id(), title=copy["title"] + " (copy)")
                for o in copy["options"]:
                    o["id"] = engine.new_id()
                s["survey"]["draft"].append(copy)
            commit(duplicate, "Question duplicated.")
        if cols[3].button("Remove", width="stretch"):
            def remove(s):
                s["survey"]["draft"] = [item for item in s["survey"]["draft"] if item["id"] != qid]
            commit(remove, "Question removed from the draft.")
    if st.button("＋ Add a question"):
        commit(lambda s: s["survey"]["draft"].append(question(engine.new_id(), "Your new question", "choice", ["Option 1", "Option 2"], multiple=True)))
    st.divider()
    version = engine.active_version(state)
    if version:
        response_count = len(engine.responses_for(state))
        st.caption(f'Published version {version["number"]} · {response_count} responses · {"Open" if state["survey"]["open"] else "Closed"}')
        if response_count and version["questions"] != draft:
            st.info("Publishing these changes creates a new version with a fresh response set. Earlier responses remain available in Survey results; the game uses the new active version.")
    if st.button("Publish survey", type="primary", disabled=state["frozen"]):
        commit(engine.publish, "Survey published. Your sharing link is ready in Setup & links.")
    if version and not state["frozen"]:
        opened = state["survey"]["open"]
        if st.button("Close responses" if opened else "Reopen responses"):
            commit(lambda s: engine.set_survey_open(s, not opened))
    with st.expander("Preview as a respondent"):
        st.caption("PREVIEW ONLY · Answers here are never submitted.")
        render_questions(draft, "preview_" + engine.digest(str(draft))[:10])
    with st.expander("Download or import a question draft"):
        st.caption("Move your question wording and choices between local preview and the hosted app. Responses and player data are never included.")
        st.download_button("Download question draft", json.dumps({"format": "hint-survey-draft-v1", "questions": draft}, indent=2), file_name="hint-question-draft.json", mime="application/json")
        uploaded = st.file_uploader("Import question draft", type=["json"])
        if uploaded is not None and st.button("Replace draft with imported questions", disabled=state["frozen"]):
            try:
                if uploaded.size > 2_000_000:
                    raise engine.RuleError("The draft is too large. Upload a question draft under 2 MB.")
                imported = json.loads(uploaded.getvalue())
                engine.validate_import(imported)
                commit(lambda s: engine.save_draft(s, imported["questions"]), "Draft imported. Preview and publish it when ready.")
            except (ValueError, TypeError, KeyError) as exc:
                st.error(str(exc) if isinstance(exc, engine.RuleError) else "This isn’t a valid Hint question draft. Export one from this app and try again.")
    with st.expander('Open-ended workshop survey template'):
        st.caption('13 questions: work areas, AI comfort, tools and usage, eight open-text prompts, and learning topics. Download your current draft above before replacing it. Published surveys and responses are preserved.')
        if st.button('Replace draft with open-ended workshop questions'):
            commit(lambda s: engine.save_draft(s, open_ended_survey_questions()), 'Open-ended workshop draft loaded. Review and publish when ready.')
