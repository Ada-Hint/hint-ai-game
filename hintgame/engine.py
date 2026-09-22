"""Pure game rules. Mutations run inside the repository's optimistic transaction."""
from collections import Counter
from copy import deepcopy
import hashlib
import math
import secrets
import time

from .content import initial_state, question

RANK_POINTS = 20
EXCLUDED_CATEGORY = '__excluded__'


class RuleError(ValueError):
    """A safe, user-facing validation message."""


def new_id():
    return secrets.token_hex(12)


def clean_options(rows, original=()):
    """Keep existing IDs; dynamic editor rows may contain None, NaN or duplicates."""
    known = {o['id'] for o in original if isinstance(o.get('id'), str) and o['id'].strip()}
    used, cleaned = set(), []
    for row in rows:
        oid = row.get('id')
        if not isinstance(oid, str) or oid not in known or oid in used:
            oid = new_id()
        used.add(oid)
        label = row.get('label')
        cleaned.append({'id': oid, 'label': label.strip() if isinstance(label, str) else '',
                        'exclusive': row.get('exclusive') is True, 'other': row.get('other') is True})
    return cleaned


def validate_options(options):
    ids = [o.get('id') for o in options]
    if any(not isinstance(oid, str) or not oid.strip() for oid in ids) or len(set(ids)) != len(ids):
        raise RuleError('Each choice needs a unique ID.')
    labels = [o.get('label', '').strip().casefold() for o in options]
    if len(options) < 2 or any(not label for label in labels) or len(set(labels)) != len(labels):
        raise RuleError('Add at least two choices with distinct, nonempty labels.')


def validate_ranking(order, options):
    ids = {o['id'] for o in options}
    if (not isinstance(order, list) or any(not isinstance(oid, str) for oid in order)
            or len(order) != len(ids) or set(order) != ids):
        raise RuleError('Rank every displayed answer exactly once.')
    return list(order)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def active_version(state):
    return next((v for v in state["survey"]["versions"] if v["id"] == state["survey"]["active_version"]), None)


def validate_questions(questions):
    if not questions:
        raise RuleError("Add at least one question before publishing.")
    ids = set()
    for q in questions:
        if not q.get("id") or q["id"] in ids:
            raise RuleError("Each question needs a unique ID.")
        ids.add(q["id"])
        if not q.get("title", "").strip():
            raise RuleError("Give every question a title.")
        if len(q["title"]) > 500:
            raise RuleError("Keep question titles under 500 characters.")
        if q.get("kind") not in {"choice", "rating", "text", "ranking"}:
            raise RuleError("Choose a supported question type.")
        if q.get('display', 'dropdown') not in {'dropdown', 'checkboxes'}:
            raise RuleError('Choose dropdown or tick boxes for the choice layout.')
        if q["kind"] in {"choice", "ranking"}:
            options = q.get("options", [])
            validate_options(options)
            if sum(bool(o.get("other")) for o in options) > 1:
                raise RuleError("Use only one Other choice per question.")
            if any(o.get("other") and o.get("exclusive") for o in options):
                raise RuleError("Other cannot also be an exclusive choice.")
            if q['kind'] == 'ranking' and any(o.get('other') or o.get('exclusive') for o in options):
                raise RuleError('Ranking answers cannot use Other or Exclusive.')
        if q["kind"] == "rating" and not (1 <= q.get("minimum", 1) < q.get("maximum", 5) <= 10):
            raise RuleError("Rating scales must run from 1–10 with the maximum above the minimum.")


def save_draft(state, questions):
    validate_questions(questions)
    state["survey"]["draft"] = deepcopy(questions)


def validate_import(data):
    if not isinstance(data, dict) or data.get("format") != "hint-survey-draft-v1" or not isinstance(data.get("questions"), list):
        raise RuleError("Import a question draft exported from this app.")
    required = {"id", "title", "kind", "required", "multiple", "help", "options", "minimum", "maximum", "low_label", "high_label"}
    for q in data["questions"]:
        if not isinstance(q, dict) or not required.issubset(q):
            raise RuleError("The question draft is missing required fields.")
        if not all(isinstance(q[k], str) for k in ["id", "title", "kind", "help", "low_label", "high_label"]) or not isinstance(q["options"], list):
            raise RuleError("The question draft contains invalid field types.")
        if type(q["required"]) is not bool or type(q["multiple"]) is not bool or type(q["minimum"]) is not int or type(q["maximum"]) is not int:
            raise RuleError("The question draft contains invalid settings.")
        for o in q["options"]:
            if not isinstance(o, dict) or not isinstance(o.get("id"), str) or not isinstance(o.get("label"), str) or type(o.get("exclusive")) is not bool or type(o.get("other")) is not bool:
                raise RuleError("The question draft contains an invalid answer choice.")
    validate_questions(data["questions"])


def publish(state):
    if state["frozen"]:
        raise RuleError("The game uses saved results. Use Run game → Reset game / unlock editing before publishing a new survey.")
    s = state["survey"]
    validate_questions(s["draft"])
    current = active_version(state)
    if current and current["questions"] == s["draft"]:
        s["open"] = True
        return current["id"]
    version = {"id": new_id(), "number": len(s["versions"]) + 1,
               "questions": deepcopy(s["draft"]), "published_at": time.time()}
    s["versions"].append(version)
    s["active_version"] = version["id"]
    s["open"] = True
    return version["id"]


def set_survey_open(state, opened):
    if opened and (state["frozen"] or not active_version(state)):
        raise RuleError("Publish a survey before opening responses. If a game has started, use Run game → Reset game / unlock editing first.")
    state["survey"]["open"] = opened


def clean_answers(questions, answers):
    cleaned = {}
    for q in questions:
        raw = answers.get(q["id"], {})
        choices = list(dict.fromkeys(raw.get("choices", [])))
        ranking = []
        texts = []
        for item in raw.get("texts", []):
            value = str(item.get("value", "")).strip()
            if value:
                if len(value) > 1000:
                    raise RuleError("Please keep each written response under 1,000 characters.")
                texts.append({"id": str(item.get("id") or new_id()), "value": value})
        if len({t["id"] for t in texts}) != len(texts):
            raise RuleError("Each written response must have a distinct ID.")
        rating = raw.get("rating")
        if q["kind"] == "choice":
            allowed = {o["id"]: o for o in q["options"]}
            if any(c not in allowed for c in choices):
                raise RuleError("One of the choices changed. Refresh the survey and try again.")
            if not q["multiple"] and len(choices) > 1:
                raise RuleError(f'Choose one answer for “{q["title"]}”.')
            if len(choices) > 1 and any(allowed[c].get("exclusive") for c in choices):
                raise RuleError(f'For “{q["title"]}”, choose an exclusive answer on its own, or remove it to select other answers.')
            has_other = any(allowed[c].get("other") for c in choices)
            texts = texts if has_other else []
            rating = None
        elif q['kind'] == 'ranking':
            order = raw.get('ranking', [])
            if order != []:
                ranking = validate_ranking(order, q['options'])
            choices, texts, rating = [], [], None
        elif q["kind"] == "rating":
            if rating is not None and (type(rating) is not int or not q["minimum"] <= rating <= q["maximum"]):
                raise RuleError("Choose a rating within the displayed scale.")
            choices, texts = [], []
        else:
            choices, rating = [], None
            if not q["multiple"] and len(texts) > 1:
                raise RuleError(f'Enter one response for “{q["title"]}”.')
        if q["required"] and not (choices or texts or ranking or rating is not None):
            raise RuleError(f'Please answer “{q["title"]}”.')
        cleaned[q["id"]] = {"choices": choices, "texts": texts, "rating": rating}
        if q['kind'] == 'ranking':
            cleaned[q['id']]['ranking'] = ranking
    return cleaned


def submit_survey(state, version_id, answers, receipt):
    rid = digest(receipt)
    # Idempotent retry, including after the host closes the survey.
    if any(r["id"] == rid for r in state["survey"]["responses"]):
        return rid
    version = active_version(state)
    if not state["survey"]["open"] or state["frozen"]:
        raise RuleError("This survey is closed. Thank you for your interest—join us for the game!")
    if not version or version_id != version["id"]:
        raise RuleError("The host published a new survey version. Refresh to load it; your previous answers have not been submitted.")
    cleaned = clean_answers(version["questions"], answers)
    state["survey"]["responses"].append({"id": rid, "version_id": version_id, "answers": cleaned})
    return rid


def responses_for(state, version_id=None):
    vid = version_id or state["survey"]["active_version"]
    return [r for r in state["survey"]["responses"] if r["version_id"] == vid]


def mapping_key(version_id, qid):
    return f"{version_id}:{qid}"


def text_key(response_id, qid, text_id):
    return f"{response_id}:{qid}:{text_id}"


def text_entries(state, qid, version_id=None):
    entries = []
    for r in responses_for(state, version_id):
        for t in r["answers"].get(qid, {}).get("texts", []):
            entries.append({"key": text_key(r["id"], qid, t["id"]), "value": t["value"]})
    return entries


def aggregate(state, qid, version_id=None):
    vid = version_id or state["survey"]["active_version"]
    version = next((v for v in state["survey"]["versions"] if v["id"] == vid), None)
    if not version:
        return {"denominator": 0, "rows": [], "multiple": False}
    q = next((q for q in version["questions"] if q["id"] == qid), None)
    if not q:
        return {"denominator": 0, "rows": [], "multiple": False}
    if q['kind'] == 'text':
        options = state['survey']['categories'].get(mapping_key(vid, qid), [])
        counts = Counter({o['id']: 0 for o in options})
        answered = denominator = ungrouped = excluded = grouped = 0
        for response in responses_for(state, vid):
            entries = response['answers'].get(qid, {}).get('texts', [])
            answered += bool(entries)
            selected = set()
            for entry in entries:
                mapped = state['survey']['mappings'].get(text_key(response['id'], qid, entry['id']))
                if mapped == EXCLUDED_CATEGORY:
                    excluded += 1
                elif mapped in counts:
                    selected.add(mapped)
                    grouped += 1
                else:
                    ungrouped += 1
            denominator += bool(selected)
            counts.update(selected)
        rows = [{'id': o['id'], 'label': o['label'], 'count': counts[o['id']],
                 'percent': round(100 * counts[o['id']] / denominator) if denominator else 0} for o in options]
        rows.sort(key=lambda row: -row['count'])
        return {'kind': 'text', 'rows': rows, 'denominator': denominator, 'answered': answered,
                'multiple': q.get('multiple', False), 'ungrouped': ungrouped, 'excluded': excluded, 'grouped': grouped}
    if q['kind'] == 'ranking':
        rankings = [r['answers'].get(qid, {}).get('ranking', []) for r in responses_for(state, vid)]
        rankings = [order for order in rankings if order]
        totals, firsts = Counter(), Counter()
        for order in rankings:
            for position, oid in enumerate(order, 1):
                totals[oid] += position
            firsts[order[0]] += 1
        rows = [{'id': o['id'], 'label': o['label'], 'rank_total': totals[o['id']],
                 'average_rank': totals[o['id']] / len(rankings) if rankings else None,
                 'first_count': firsts[o['id']]} for o in q['options']]
        rows.sort(key=lambda r: r['rank_total'])
        return {'denominator': len(rankings), 'rows': rows, 'multiple': False, 'kind': 'ranking'}
    options = deepcopy(q.get("options", [])) + state["survey"]["categories"].get(mapping_key(vid, qid), [])
    counts = Counter({o["id"]: 0 for o in options})
    denominator = 0
    other_ids = {o["id"] for o in options if o.get("other")}
    for r in responses_for(state, vid):
        a = r["answers"].get(qid, {})
        if not (a.get("choices") or a.get("texts") or a.get("rating") is not None):
            continue
        denominator += 1
        selected = set(a.get("choices", []))
        if a.get("texts") and selected & other_ids:
            selected -= other_ids
            for t in a["texts"]:
                mapped = state["survey"]["mappings"].get(text_key(r["id"], qid, t["id"]))
                if mapped in counts:
                    selected.add(mapped)
                else:
                    selected |= other_ids
        if q["kind"] == "rating":
            selected = {str(a["rating"])} if a.get("rating") is not None else set()
        counts.update(selected)
    if q["kind"] == "rating":
        options = [{"id": str(i), "label": str(i)} for i in range(q["minimum"], q["maximum"] + 1)]
    rows = [{"id": o["id"], "label": o["label"], "count": counts[o["id"]],
             "percent": round(100 * counts[o["id"]] / denominator) if denominator else 0} for o in options]
    rows.sort(key=lambda r: -r["count"])
    return {"denominator": denominator, "rows": rows, "multiple": q.get("multiple", False)}


def categorize(state, qid, entry_key, category_id=None, new_label=None):
    if state["frozen"]:
        raise RuleError("Results are frozen for this game.")
    version = active_version(state)
    if not version:
        raise RuleError("Publish a survey first.")
    q = next((q for q in version["questions"] if q["id"] == qid), None)
    if not q or q["kind"] not in {"choice", "text"}:
        raise RuleError("Group written answers from text or choice questions into categories.")
    if entry_key not in {e["key"] for e in text_entries(state, qid)}:
        raise RuleError("This written entry no longer belongs to the active survey.")
    key = mapping_key(version["id"], qid)
    extra = state["survey"]["categories"].setdefault(key, [])
    choices = (q['options'] if q['kind'] == 'choice' else []) + extra
    if new_label:
        new_label = new_label.strip()
        if not new_label or len(new_label) > 120:
            raise RuleError("Use a category name of 1–120 characters.")
        existing = next((o for o in choices if o["label"].casefold() == new_label.casefold()), None)
        category_id = existing["id"] if existing else new_id()
        if not existing:
            extra.append({"id": category_id, "label": new_label})
    if category_id is None:
        state["survey"]["mappings"].pop(entry_key, None)
    elif category_id == EXCLUDED_CATEGORY and q['kind'] == 'text':
        state['survey']['mappings'][entry_key] = category_id
    elif category_id not in {o["id"] for o in (q['options'] if q['kind'] == 'choice' else []) + extra}:
        raise RuleError("Choose an existing category or create a new one.")
    else:
        state["survey"]["mappings"][entry_key] = category_id


def approve_entry(state, qid, entry_key, approved):
    if state["frozen"]:
        raise RuleError("Approved excerpts are frozen for this game.")
    if entry_key not in {e["key"] for e in text_entries(state, qid)}:
        raise RuleError("Choose an entry from the active survey.")
    approved_set = set(state["survey"]["approved"])
    if approved:
        approved_set.add(entry_key)
    else:
        approved_set.discard(entry_key)
    state["survey"]["approved"] = sorted(approved_set)


def save_cards(state, cards):
    if state["frozen"]:
        raise RuleError("Use Run game → Reset game / unlock editing before changing the game questions.")
    if not cards or len({c["id"] for c in cards}) != len(cards):
        raise RuleError("Cards need distinct IDs.")
    for c in cards:
        if not c.get("title", "").strip():
            raise RuleError("Each game card needs a title.")
        if c.get('kind') not in {'quiz', 'poll', 'survey', 'ranking', 'leaderboard', 'demo', 'finish'}:
            raise RuleError('Choose a supported game card type.')
        if c['kind'] == 'ranking':
            if c.get('ranking_source', 'manual') not in {'manual', 'survey'}:
                raise RuleError('Choose a ranking source.')
            if c.get('ranking_source') == 'survey':
                if not c.get('survey_question_id'):
                    raise RuleError('Choose a survey question for this ranking round.')
                if type(c.get('top_n', 5)) is not int or not 2 <= c.get('top_n', 5) <= 20:
                    raise RuleError('Choose between 2 and 20 top answers.')
            else:
                validate_options(c.get('options', []))
                validate_ranking(c.get('correct', []), c['options'])
        if c["kind"] in {"quiz", "poll"}:
            opts = c.get("options", [])
            validate_options(opts)
            if len(opts) < 2 or len({o["id"] for o in opts}) != len(opts) or any(not o["label"].strip() for o in opts):
                raise RuleError("Each vote needs at least two distinct, labeled choices.")
            if c["kind"] == "quiz" and (not c.get("correct") or any(a not in {o["id"] for o in opts} for a in c["correct"])):
                raise RuleError("Choose the correct answer for each quiz question.")
    state["cards"] = deepcopy(cards)


def game_survey_result(state, q):
    result = aggregate(state, q['id'])
    if q['kind'] == 'text':
        if result['ungrouped']:
            raise RuleError(f'Group or exclude all written responses to “{q["title"]}” in Survey results before starting the game.')
        result['rows'] = [r for r in result['rows'] if r['count'] > 0]
        if len(result['rows']) < 2:
            raise RuleError(f'“{q["title"]}” needs at least two categories with responses. Group the answers in Survey results or choose another game question.')
    return result


def add_survey_card(state, qid, kind='survey', title=None):
    """Create a linked round without copying private written answers to the deck."""
    version = active_version(state)
    q = next((q for q in version['questions'] if q['id'] == qid), None) if version else None
    if not q or q['kind'] not in {'choice', 'text', 'ranking'} or kind not in {'survey', 'ranking'}:
        raise RuleError('Choose a published choice, text, or ranking question.')
    if kind == 'survey' and q['kind'] == 'ranking':
        raise RuleError('Use a ranking round for a ranking survey question.')
    cid = new_id()
    new_card = {'id': cid, 'kind': kind, 'title': (title or ('Rank the room’s most common answers' if kind == 'ranking' else 'Which answer came up most often?')).strip(),
                'section': 'RANK THE ROOM' if kind == 'ranking' else 'GUESS THE ROOM',
                'survey_question_id': qid, 'ranking_source': 'survey', 'top_n': 5,
                'options': [], 'correct': [], 'scored': True, 'lesson': '', 'explanation': '',
                'poll_title': 'Which of these answers would you choose?'}
    cards = deepcopy(state['cards'])
    index = next((i for i, c in enumerate(cards) if c['kind'] == 'finish'), len(cards))
    cards.insert(index, new_card)
    save_cards(state, cards)
    return cid


def freeze(state):
    if state["frozen"]:
        raise RuleError("Results are already frozen.")
    version = active_version(state)
    if not version:
        raise RuleError("Publish the survey first. With fewer than five responses, the opening becomes an unscored live poll.")
    cards = deepcopy(state["cards"])
    save_cards(state, cards)
    for c in cards:
        if c['kind'] == 'ranking':
            c['scored'] = True
            if c.get('ranking_source') == 'survey':
                q = next((q for q in version['questions'] if q['id'] == c.get('survey_question_id')), None)
                if not q or q['kind'] not in {'choice', 'text', 'ranking'}:
                    raise RuleError('Map ranking rounds to a choice, grouped text, or ranking question in the published survey.')
                result = game_survey_result(state, q)
                if result['denominator'] < 5:
                    raise RuleError(f'Ranking round “{c["title"]}” needs at least five survey responses. Collect more responses or use a host-set order.')
                rows = result['rows']
                metric = 'rank_total' if q['kind'] == 'ranking' else 'count'
                if q['kind'] in {'choice', 'text'}:
                    rows = [r for r in rows if r['count'] > 0]
                if len(rows) < 2:
                    raise RuleError('A survey ranking round needs at least two answers with results.')
                # Include the whole tie group at the cutoff, never arbitrarily exclude a tied item.
                cutoff = rows[min(c.get('top_n', 5), len(rows)) - 1][metric]
                rows = [r for r in rows if r[metric] <= cutoff] if metric == 'rank_total' else [r for r in rows if r[metric] >= cutoff]
                c['snapshot'] = {**result, 'rows': rows}
                c['options'] = [{'id': r['id'], 'label': r['label']} for r in rows]
                c['correct'] = [r['id'] for r in rows]
                c['rank_groups'] = []
                for row in rows:
                    c['rank_groups'].append([r['id'] for r in rows if r[metric] == row[metric]])
            else:
                c['rank_groups'] = [[oid] for oid in c['correct']]
            # Present a neutral alphabetical order, independent of the answer key.
            c['options'].sort(key=lambda o: (o['label'].casefold(), o['id']))
            continue
        if c["kind"] != "survey":
            continue
        q = next((q for q in version["questions"] if q["id"] == c.get("survey_question_id")), None)
        if not q or q["kind"] not in {"choice", "text"}:
            raise RuleError(f'Map “{c["title"]}” to a choice or grouped text question in the published survey using Game content.')
        result = game_survey_result(state, q)
        c["options"] = [{"id": o["id"], "label": o["label"]} for o in q["options"]] if q['kind'] == 'choice' else []
        for row in result["rows"]:
            if row["id"] not in {o["id"] for o in c["options"]}:
                c["options"].append({"id": row["id"], "label": row["label"]})
        c["snapshot"] = result
        c["scored"] = result["denominator"] >= 5
        if c["scored"]:
            top = max((r["count"] for r in result["rows"]), default=0)
            c["correct"] = [r["id"] for r in result["rows"] if r["count"] == top and top > 0]
        else:
            c["kind"] = "poll"
            c["title"] = c.get("poll_title") or q["title"]
            c["correct"] = []
            c["low_response_poll"] = True
    approved = set(state["survey"]["approved"])
    excerpts = [e["value"] for q in version["questions"] for e in text_entries(state, q["id"]) if e["key"] in approved]
    state["frozen_excerpts"] = excerpts
    state["frozen"] = True
    state["frozen_version"] = version["id"]
    state["survey"]["open"] = False
    state["game"]["deck"] = cards


def current_card(state):
    game = state["game"]
    i = game["index"]
    return game["deck"][i] if 0 <= i < len(game["deck"]) else None


def start_game(state, now=None):
    """Prepare and start together inside one repository transaction."""
    if state['game']['index'] != -1 or state['game']['phase'] != 'lobby':
        raise RuleError('This game has already started. Use the current game controls to continue.')
    if not state['frozen']:
        freeze(state)
    if not state['game']['deck']:
        raise RuleError('Add a game card in Game content before starting.')
    game_action(state, 'start', now)


def start_readiness(state):
    """Check the same start rules without changing survey or game data."""
    candidate = deepcopy(state)
    try:
        start_game(candidate)
    except RuleError as exc:
        return {'error': str(exc), 'polls': []}
    return {'error': None, 'polls': [c['title'] for c in candidate['game']['deck'] if c.get('low_response_poll')]}


def phase(state, now=None):
    g = state["game"]
    if g["phase"] == "open" and g["deadline"] is not None and (time.time() if now is None else now) >= g["deadline"]:
        return "closed"
    return g["phase"]


def seconds_left(state, now=None):
    deadline = state["game"]["deadline"]
    return max(0, math.ceil(deadline - (time.time() if now is None else now))) if deadline else 0


def join_player(state, nickname, token):
    if state["game"]["phase"] == "finished":
        raise RuleError("This game has finished. You can still view the board and takeaways.")
    pid = digest(token)
    if pid in state["players"]:
        return pid
    nickname = " ".join(nickname.split())
    if not 1 <= len(nickname) <= 24:
        raise RuleError("Choose a nickname of 1–24 characters.")
    if any(p["nickname"].casefold() == nickname.casefold() for p in state["players"].values()):
        raise RuleError("That nickname is taken. Add an initial or choose another.")
    state["players"][pid] = {"nickname": nickname}
    return pid


def vote(state, token, card_id, option_id, now=None):
    pid = digest(token)
    if pid not in state["players"]:
        raise RuleError("Rejoin with your private code before voting.")
    c = current_card(state)
    if not c or c["id"] != card_id or phase(state, now) != "open":
        raise RuleError("Voting has closed for that question. Your earlier vote, if any, is saved.")
    if c['kind'] == 'ranking':
        option_id = validate_ranking(option_id, c['options'])
    elif not isinstance(option_id, str) or option_id not in {o["id"] for o in c.get("options", [])}:
        raise RuleError("Choose one of the displayed answers.")
    state["votes"].setdefault(card_id, {})[pid] = option_id


def game_action(state, action, now=None):
    now = time.time() if now is None else now
    g = state["game"]
    c = current_card(state)
    current_phase = phase(state, now)
    if action == "start":
        if not state["frozen"] or g["index"] != -1:
            raise RuleError("Freeze the results before starting a new game.")
        g.update(index=0, phase="ready", deadline=None)
    elif action == "open":
        if not c or not c.get("options") or current_phase != "ready":
            raise RuleError("This question is not ready to open.")
        g.update(phase="open", deadline=now + 30)
    elif action == "extend":
        if not c or current_phase not in {"open", "closed"}:
            raise RuleError("Open a vote before extending it.")
        g.update(phase="open", deadline=max(g.get("deadline") or now, now) + 15)
    elif action == "close":
        if current_phase not in {"open", "closed"}:
            raise RuleError("There is no open vote to close.")
        g.update(phase="closed", deadline=now)
    elif action == "reveal":
        if not c or current_phase != "closed":
            raise RuleError("Close voting before revealing results.")
        g.update(phase="revealed", reveal_count=1)
        if c["id"] not in g["revealed"]:
            g["revealed"].append(c["id"])
    elif action in {"reveal_next", "reveal_all"}:
        if not c or c["kind"] != "survey" or current_phase != "revealed":
            raise RuleError("Reveal a survey board first.")
        total = len(c["snapshot"]["rows"])
        g["reveal_count"] = total if action == "reveal_all" else min(total, g["reveal_count"] + 1)
    elif action == "next":
        if not c or (c.get("options") and current_phase != "revealed"):
            raise RuleError("Reveal the current vote before moving on.")
        if g["index"] >= len(g["deck"]) - 1:
            g["phase"] = "finished"
        else:
            g.update(index=g["index"] + 1, phase="ready", deadline=None, reveal_count=0, demo_step=0)
    elif action == "demo_next":
        if not c or c["kind"] != "demo":
            raise RuleError("Open the walkthrough first.")
        g["demo_step"] = min(3, g["demo_step"] + 1)
    elif action == "chat_fallback":
        g["chat_fallback"] = True
        # Already-revealed questions keep their points; subsequent ones are unscored.
        for item in g["deck"]:
            if item["id"] not in g["revealed"]:
                item["scored"] = False
    else:
        raise RuleError("Unknown host action.")


def leaderboard(state):
    scores = {pid: 0 for pid in state["players"]}
    for c in state["game"]["deck"]:
        if c["id"] not in state["game"]["revealed"] or not c.get("scored"):
            continue
        for pid, answer in state["votes"].get(c["id"], {}).items():
            if pid in scores:
                scores[pid] += answer_points(c, answer)
    rows = [{"player_id": pid, "nickname": state["players"][pid]["nickname"], "score": score} for pid, score in scores.items()]
    rows.sort(key=lambda p: (-p["score"], p["nickname"].casefold()))
    last_score, rank = None, 0
    for i, row in enumerate(rows):
        if row["score"] != last_score:
            rank = i + 1
        row["rank"], last_score = rank, row["score"]
    return rows


def ranking_matches(c, answer):
    groups = c.get('rank_groups', [[oid] for oid in c.get('correct', [])])
    return [isinstance(answer, list) and i < len(answer) and answer[i] in group for i, group in enumerate(groups)]


def answer_points(c, answer):
    if not c.get('scored'):
        return 0
    if c['kind'] == 'ranking':
        return RANK_POINTS * sum(ranking_matches(c, answer))
    return 100 if answer in c.get('correct', []) else 0


def vote_counts(state, c):
    if c['kind'] == 'ranking':
        votes = state['votes'].get(c['id'], {}).values()
        return [{'id': o['id'], 'label': o['label'], 'count': sum(isinstance(a, list) and bool(a) and a[0] == o['id'] for a in votes)} for o in c['options']]
    counts = Counter(state["votes"].get(c["id"], {}).values())
    return [{"id": o["id"], "label": o["label"], "count": counts[o["id"]]} for o in c.get("options", [])]


def reset_game(state):
    """Explicit host reset. Survey versions/responses are preserved."""
    fresh = initial_state()
    state.update(game=fresh["game"], players={}, votes={}, frozen=False, frozen_version=None, frozen_excerpts=[])


def seed_rehearsal():
    state = initial_state()
    vid = publish(state)
    for i in range(8):
        answers = {q["id"]: {"choices": [q["options"][0]["id"]] if q["options"] else [], "texts": [], "rating": 2 + i % 4 if q["kind"] == "rating" else None} for q in state["survey"]["draft"]}
        answers["frequency"]["choices"] = [f"frequency_{i % 5}"]
        answers["tools"]["choices"] = ["tools_0", "tools_1"] if i % 2 else ["tools_0"]
        answers["tasks"]["choices"] = ["tasks_0", f"tasks_{1 + i % 4}"]
        answers["hesitations"]["choices"] = ["hesitations_1", f"hesitations_{2 + i % 3}"]
        submit_survey(state, vid, answers, f"synthetic-rehearsal-{i}")
    return state
