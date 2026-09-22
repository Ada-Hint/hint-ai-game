"""Editable starting content. IDs remain stable across wording edits."""
from copy import deepcopy


def option(key, label, exclusive=False, other=False):
    return {"id": key, "label": label, "exclusive": exclusive, "other": other}


def question(key, title, kind, labels=(), required=True, multiple=False):
    return {"id": key, "title": title, "kind": kind, "required": required,
            "multiple": multiple, "help": "", "options": [option(f"{key}_{i}", label) for i, label in enumerate(labels)],
            "minimum": 1, "maximum": 5, "low_label": "Where do I start?",
            "high_label": "Comfortable experimenting"}


def survey_questions():
    qs = [
        question("area", "Which areas describe your work?", "choice", ["Creative", "Brand, Social & Partnerships", "DTC & Lifecycle", "Analytics & Growth", "Other"], False, True),
        question("frequency", "How often do you currently use AI for work?", "choice", ["Never", "Tried it a few times", "Monthly", "Weekly", "Most days"]),
        question("tools", "Which AI tools have you tried?", "choice", ["ChatGPT", "Microsoft Copilot", "Other", "None", "Not sure"], multiple=True),
        question("confidence", "How confident are you giving AI a useful task?", "rating"),
        question("tasks", "Which tasks would you love AI to help take off your plate?", "choice", ["Copy and content", "Creative briefs and ideas", "Reports and insights", "Meeting recaps and project updates", "Research summaries", "Other"], multiple=True),
        question("hesitations", "What makes you hesitate to use AI at work?", "choice", ["Getting started", "Accuracy", "Generic or off-brand output", "What information I can share", "Finding time", "Other", "No major hesitation"], multiple=True),
        question("ideas", "What real tasks or questions would you like us to cover?", "text", required=False, multiple=True),
    ]
    for q in qs:
        for o in q["options"]:
            o["other"] = o["label"] == "Other"
            o["exclusive"] = o["label"] in {"None", "Not sure", "No major hesitation"}
    qs[-1]["help"] = "General examples are perfect. Please leave out confidential information. Add as many ideas as you like."
    return qs


def open_ended_survey_questions():
    """Workshop draft: collect the room's own wording before building game rounds."""
    qs = [
        question('area', 'Which areas describe your work?', 'choice', ['Creative', 'Brand, Social & Partnerships', 'DTC & Lifecycle', 'Analytics & Growth', 'Other'], False, True),
        question('ai_comfort', 'From 1–10, how comfortable are you with using AI?', 'rating'),
        question('tools', 'What AI tools do you use?', 'choice', ['ChatGPT', 'Microsoft Copilot', 'Claude', 'Gemini', 'Grok', 'Meta AI', 'Other', 'None', 'Not sure'], multiple=True),
        question('ai_usage', 'How are you using AI today?', 'choice', ['In a browser', 'In chat', 'For coding', 'In work apps (e.g. Word, Excel, or Teams)', 'To generate text', 'To analyze data', 'Other', 'Not using AI yet'], multiple=True),
        question('first_task', 'What’s the first thing you’d ask AI to help you with at work?', 'text', required=False),
        question('never_again', 'What task would you be happiest to never do again?', 'text', required=False),
        question('reporting', 'Name the #1 bit of data or reporting you’re constantly asked for.', 'text', required=False),
        question('ai_association', 'When someone says AI, what’s the first thing that comes to mind?', 'text', required=False),
        question('ai_bad', 'Name the one thing AI is terrible at.', 'text', required=False),
        question('ai_good', 'Name the one thing AI is surprisingly good at.', 'text', required=False),
        question('work_document', 'Name a work document nobody enjoys creating.', 'text', required=False),
        question('improve_at', 'If AI could instantly make you better at one thing, what would you choose?', 'text', required=False),
        question('learning_topics', 'What topics do you most want to learn about?', 'choice', ['Practical uses for Copilot', 'Prompting', 'Data analysis', 'AI terminology and the basics', 'How organizations are using AI', 'Other'], multiple=True),
    ]
    for q in qs:
        if q['kind'] == 'choice':
            q['display'] = 'checkboxes'
            q['help'] = 'Select all that apply.'
            for o in q['options']:
                o['other'] = o['label'] == 'Other'
                o['exclusive'] = o['label'] in {'None', 'Not sure', 'Not using AI yet'}
        elif q['kind'] == 'text':
            q['help'] = 'One answer is plenty. You can skip this if nothing comes to mind. Please leave out confidential information.'
    qs[1].update(minimum=1, maximum=10, low_label='Not comfortable yet', high_label='Very comfortable')
    qs[3]['help'] = 'Choose both where you use AI and what you use it for. Select all that apply.'
    return qs


def card(key, title, options, answer=None, lesson="", explanation="", section="", kind="quiz"):
    return {"id": key, "title": title, "kind": kind, "section": section,
            "options": [option(chr(65 + i), label) for i, label in enumerate(options)],
            "correct": [answer] if answer else [], "lesson": lesson,
            "explanation": explanation, "scored": answer is not None}


def game_cards():
    return [
        card("practice", "What’s your lunch-and-learn energy?", ["Curious. Show me something useful.", "Here for a shortcut (and lunch).", "Already experimenting. Let’s play."], section="THE WARM-UP", kind="poll"),
        {**card("room_tasks", "Which task was selected by the most colleagues?", [], section="GUESS THE ROOM", kind="survey"), "survey_question_id": "tasks", "poll_title": "Which of these tasks would you most like AI to help with?", "lesson": "Start with one useful first draft.", "explanation": "AI can help you get something onto the page. Choose a small, repeatable task and stay involved in the review."},
        {**card("room_hesitations", "Which hesitation was selected most often?", [], section="GUESS THE ROOM", kind="survey"), "survey_question_id": "hesitations", "poll_title": "Which of these is your biggest hesitation about AI?", "lesson": "You don’t need to have it all figured out.", "explanation": "Different starting points are welcome. Begin with fictional or approved information, a clear task, and a quick check of the result."},
        card("brief", "Which prompt gives AI the clearest brief?", ["Write something fun for Hint.", "You’re a world-class marketer. Make this amazing.", "Using this sample brief, write three Instagram captions for this audience, under 25 words each, in an encouraging, playful tone. Use only the supplied product facts."], "C", "Give it a better brief.", "Name the task, audience, source material, tone, and output format. Specific instructions make it easier to judge whether the answer is useful.", "CREATIVE + BRAND"),
        card("revise", "The email draft feels generic. What next?", ["Start a new chat with the same prompt.", "Explain what missed, supply a tone example, and request a shorter revision with one clear CTA.", "Ask it to try harder."], "B", "The first answer is a first draft.", "Tell it what to keep and what to change. One example of the tone you want is more useful than ‘make it better.’", "DTC + LIFECYCLE"),
        {"id": "midpoint", "kind": "leaderboard", "section": "HALFWAY CHECK-IN", "title": "A little friendly competition.", "explanation": "Still anyone’s game. Next up: knowing what to do with the answer."},
        card("analytics", "The AI says a campaign caused sales to rise. Your table only shows that both rose. What next?", ["Put the conclusion into the recap.", "Ask for more confident wording.", "Check the calculations and ask it to separate observations from possible explanations."], "C", "Confidence isn’t evidence.", "Check the numbers against your source. An increase alongside a campaign does not, by itself, establish that the campaign caused it.", "ANALYTICS + GROWTH"),
        card("claims", "An AI-written creator brief adds a product benefit that isn’t in your approved facts. What next?", ["Remove the unsupported benefit and verify the remaining claims against the brief.", "Keep it because it sounds plausible.", "Ask another AI whether it sounds right."], "A", "Your source gets the final say.", "Check claims against approved facts. A second AI agreeing is not a substitute for evidence or your team’s review.", "SOCIAL + PARTNERSHIPS"),
        {"id": "walkthrough", "kind": "demo", "section": "FROM BLANK CHAT TO USEFUL DRAFT", "title": "Small task. Better brief. Useful start."},
        card("followup", "What would you ask for next?", ["Make the CTA more specific.", "Give me two options in a warmer tone.", "Flag anything that needs a fact check."], lesson="Keep the conversation going.", explanation="All three can be useful. Choose a follow-up that addresses what your draft actually needs.", section="YOUR NEXT PROMPT", kind="poll"),
        card("commitment", "Which small win will you try this week?", ["A clearer creative brief", "A few social caption options", "A lifecycle email first draft", "A performance recap to review"], lesson="One useful task is a great start.", explanation="Use the starter prompt below. Give it context, review the result, and tell it what to change.", section="YOUR NEXT SMALL WIN", kind="poll"),
        {"id": "finish", "kind": "finish", "section": "NICELY DONE", "title": "A little more AI confidence.", "explanation": "Take one useful shortcut with you. The human judgment stays yours."},
    ]


STARTER = """Help me create [deliverable] for [audience].
Use the sample information below.
Keep the tone [tone] and return [format/length].
Use only the supplied facts and flag missing information.

Sample information: [paste here]"""
FOLLOWUP = "Keep [what worked], change [what didn’t], and give me two alternatives."
PROMPTS = {
    "Creative brief": "Using these approved notes, create a one-page creative brief. Include audience, objective, key message, deliverables, and open questions. Flag gaps instead of filling them in.\n\nNotes: [paste here]",
    "Social captions": "Using the approved facts below, write three social captions for [audience], under 25 words each. Keep the tone playful and encouraging. Do not add product benefits or offers.\n\nFacts: [paste here]",
    "Lifecycle email": "Draft a short email for [audience] about [occasion]. Use one clear CTA: [action]. Give me three subject lines and a body under 100 words. Use only these approved facts:\n[paste here]",
    "Performance recap": "Summarize this sample performance table in five bullets. Separate observations from possible explanations. Show calculations and flag missing context. Do not infer causation from a trend.\n\nSample table: [paste here]",
}
DEMO = {
    "brief": "Fictional internal campaign: invite the marketing team to a 15-minute creative brainstorm on Thursday at noon. Audience: busy colleagues. Goal: ask each person to bring one idea. Tone: playful and encouraging. No product claims or offers.",
    "prompt": "Using the fictional brief below, write an internal invitation under 50 words with one clear call to action. Keep it playful and encouraging. Use only the supplied facts; flag missing information.\n\n[Paste the fictional brief here]",
    "draft": "A little idea time? Join the marketing team for a 15-minute creative brainstorm on Thursday at noon. Bring one idea—rough edges welcome. Let’s see what we can make together.\n\nMissing information: meeting link and time zone.",
    "followup": "Keep the welcoming tone. Make the invitation under 35 words, and make ‘bring one idea’ the clear call to action. Give me two alternatives. Keep the missing-information note separate.",
    "revision": "Option 1: One idea. Fifteen minutes. Bring one idea to our marketing brainstorm Thursday at noon. Rough drafts and lunchtime inspiration welcome.\n\nOption 2: Got the start of something? Bring one idea to Thursday’s marketing brainstorm at noon. We’ll spend 15 minutes building on it together.\n\nStill needed: meeting link and time zone.",
}


def initial_state():
    return {"schema_version": 1,
            "survey": {"draft": survey_questions(), "versions": [], "active_version": None,
                       "open": False, "responses": [], "mappings": {}, "categories": {}, "approved": []},
            "cards": deepcopy(game_cards()), "frozen": False, "frozen_version": None,
            "players": {}, "votes": {}, "login_attempts": {},
            "game": {"deck": [], "index": -1, "phase": "lobby", "deadline": None,
                     "revealed": [], "reveal_count": 0, "chat_fallback": False, "demo_step": 0}}
