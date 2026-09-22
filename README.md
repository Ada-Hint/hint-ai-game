# A Hint of AI

A Hint-branded, 18-minute marketing lunch-and-learn game. Includes an editable anonymous survey, live individual voting, a Teams presentation board, a nickname leaderboard, and prepared Copilot/ChatGPT teaching examples. No AI API key is needed.

## Preview locally

Python 3.11 or newer is recommended. From this folder:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

Open **http://localhost:8501/?view=home&event=HINTAI**.

- Host workspace: **http://localhost:8501/?view=manage**.
- The first launch generates a host password in **`.local/host-password.txt`**. Open that file, copy its contents, and sign in. This file is ignored by Git.
- In **Edit survey**, customize questions and click **Publish survey**. The real event starts with no responses and an unpublished draft.
- In **Setup & links**, open the separate **rehearsal workspace**. It contains eight synthetic survey responses and has its own player/board links.
- Local SQLite data is saved in `.local/hint.db`, so closing and reopening the app does not erase responses or scores.

Localhost links work only on your own computer. Use the hosting steps below for a remote workforce. Do not use Streamlit Cloud’s local filesystem for event data; it may be replaced when the app restarts or redeploys.

## Host on Streamlit with Supabase

### 1. Create the shared database

1. Sign in to [Supabase](https://supabase.com/dashboard) and create a project.
2. Open its **SQL Editor**, paste the contents of [`supabase/schema.sql`](supabase/schema.sql), and run it. This creates the event table, revision-checked save functions, and server-only access permissions. It can be run again safely.
3. Find the project URL and a **secret API key** (`sb_secret_…`) in the project’s API settings. A legacy `service_role` key is also supported using `SUPABASE_SERVICE_ROLE_KEY`. The key is a server credential: put it only in Streamlit secrets, never in a public link or the repository. The app deliberately does not use an anonymous/publishable browser key.

### 2. Deploy the app

1. Put the application in a GitHub repository you control. Include `streamlit_app.py`, `app.py`, `hintgame/`, `static/`, `requirements.txt`, `.streamlit/config.toml`, and `supabase/`. Do not commit `.local/`, `.venv/`, `.streamlit/secrets.toml`, or personal responses. The large reference PDF/HTML are not needed by the app.
2. In [Streamlit Community Cloud](https://share.streamlit.io/), create an app from that repository with **`streamlit_app.py`** as the entry point. Choose Python 3.11 or newer.
3. In the app’s **Secrets** settings, paste and fill in the template below before inviting attendees:

```toml
STORAGE_BACKEND = "supabase"
SUPABASE_URL = "https://YOUR-PROJECT.supabase.co"
SUPABASE_SECRET_KEY = "sb_secret_YOUR-SERVER-ONLY-KEY"
HOST_PASSWORD = "choose-a-long-unique-host-password"
EVENT_CODE = "choose-an-event-code"
EVENT_ID = "hint-lunch-and-learn"
PUBLIC_BASE_URL = "https://YOUR-APP.streamlit.app"
```

The cloud entry point refuses to collect responses until persistent storage and an HTTPS public URL are configured. Local preview continues to use `streamlit run app.py`.

4. Restart the app. Sign in through `?view=manage`, publish the survey, and copy the hosted links from **Setup & links**. The QR code now points to the hosted player page.
5. Test the link on a phone or a second browser before sharing it in Teams. If the Streamlit app is private, attendees also need access at the hosting layer. Otherwise, the app uses its event code for entry and a separate host password for management.

The app initializes an empty live event automatically. The rehearsal event is stored separately using the event ID plus `-rehearsal`. Keep `EVENT_ID` unchanged to return to the same responses and scores. To run a completely separate lunch-and-learn with a new survey population, use a new event ID and event code.

### 3. Move a local draft to the hosted app, if needed

Use **Edit survey → Download question draft** locally, then **Edit survey → Import question draft** on the hosted app. This transfers question wording and choices only, without participant information. Publish the imported draft. Before starting a game, update or remove older linked cards in **Game content** if their source questions were replaced; build new rounds from the grouped responses. Local rehearsal data is not copied to Supabase.

## The four views

| View | Use |
|---|---|
| Survey | Anonymous pre-event questions; multiple choices and repeatable written responses. |
| Play | Nickname, private rejoin code, current question, vote confirmation, and personal score. |
| Present | Screen-share this tab in Teams. Host controls and raw survey responses never appear here. |
| Manage | Password-protected question editor, results/categorization, live controls, links, and rehearsal. |

### Editing and publishing

- Draft questions can be added, removed, duplicated, reordered, and edited. Choice and text questions have **Allow multiple responses**; ratings are single answers. **Ranking (drag to order)** lets respondents rank every listed answer, then confirm their order. New answer rows receive unique IDs automatically.
- Mark an answer as **Exclusive** when it must be chosen alone; mark **Other** to show repeatable write-in fields.
- Save edits, preview as a respondent, then publish. Publishing changed content creates a new version with a fresh active response set; older responses are retained under **Survey results → Survey version**. It does not reinterpret old answers or silently combine incompatible versions.
- Survey predictions map to the active version’s choice questions. Update mappings in **Game content** if you replace the default task/hesitation questions.
- A submitted response receives a private receipt URL. Reloading that URL shows confirmation without submitting again. Respondents are not asked for names or emails, and survey records are not linked to game players. With no identity verification, a person using a fresh browser can submit again; the survey is designed for a trusted internal group.

### Start and run the game

Open **Manage → Run game**. The Game control room puts the current status and primary action at the top:

1. **Start game** closes the survey, saves its results for this session, and shows the first card. The timer stays off until you open voting. If setup is incomplete, the page explains what to fix and links to the survey and game editors.
2. **Open voting · 30 seconds** lets players answer. Watch the live countdown and answer count; **＋ 15 seconds** adds time.
3. **Close voting** locks answers, or let the timer expire. **Reopen · 15 seconds** gives players another chance before the reveal.
4. **Reveal results** shows the answers and awards points. For Guess the room, use **Reveal next answer** or **Reveal all answers** to uncover the rest of the board.
5. **Next card →** advances everyone together. Use **Next walkthrough step →** during the demo and **Finish game** on the final card.

The status reads **GAME NOT STARTED**, **GAME RUNNING**, or **GAME FINISHED**. The current card, next card, and audience preview help you follow the session without switching tabs. The presentation and player links are below the controls; opening either link does not start the game. Share only the presentation tab in Teams and keep the host control room open. **Reset game / unlock editing** is separate and requires confirmation before clearing players and scores.

### Build the game from open-ended survey answers

The **Open-ended workshop survey template** in **Edit survey** contains the 13-question workshop draft: work-area tick boxes, 1–10 AI comfort, tools, current usage, eight optional single-answer text questions, and learning topics with an Other text field. You can also import `hint-open-ended-survey-draft.json`. Review and publish before sharing; replacing a draft never changes published responses. Publishing a changed draft starts a new response version.

After collecting responses:

1. Open **Survey results** and expand a text question. Read the original answers privately.
2. Under each answer, select **＋ Create a category**, enter a label such as “Reporting,” and **Save category**. Reuse that category for similar wording. A response can be reassigned later. Select **Exclude from game counts** for an answer you deliberately do not want to use.
3. The category table updates automatically. Counts represent people, not repeated entries; a person counts at most once in each category. For text questions, percentages use people with at least one grouped answer. The page shows ungrouped and excluded entries separately. Blank optional answers are not counted.
4. Enter the game question wording and choose **＋ Guess the room** or **＋ Rank the room**. The app creates a card linked to that survey question. In **Game content**, adjust wording, top-answer count (ranking), and position in the deck. Update or remove older survey-linked cards if their source questions are no longer in the published survey.
5. Before starting, group or explicitly exclude **every** written entry for each text question used by a game card. At least two categories must have responses. Guess the room uses an unscored poll with fewer than five grouped respondents; survey-based ranking requires at least five. **Start game** freezes the reviewed categories and counts.

Only category labels and counts appear in these game rounds. Original responses appear publicly only if separately approved as walkthrough excerpts. The anonymous-results JSON download includes original responses, category definitions, per-entry assignments, exclusions, and counts so grouping can be reviewed outside the app. Grouping is a host decision; the app does not infer categories or silently classify responses.

### Ranking questions and rounds

1. In **Edit survey**, add a question and choose **Ranking (drag to order)**. Add the items, save, preview, and publish. Respondents drag the handles (mouse or touch), use the up/down buttons, or use arrow keys on a handle, then select **Confirm ranking** before sending the survey. Optional rankings can be left unconfirmed to skip.
2. In **Game content**, select **＋ Add a ranking round**, or change an existing voting card’s response type to Ranking. Set its title and choose **Survey results** or **Host-set order**.
3. For survey results, select a published choice, grouped-text, or ranking question and the number of top answers. Choice and grouped-text results use response counts; ranking results use average position (lower is better). Survey-derived rankings require at least five answers to that question and at least two items with results. Ties at the cutoff are included, so a round can contain more than the requested number of items.
4. For a host-set order, add answers and enter each correct position once (1 through the number of answers). Save the card and use Move card up/down to place it in the game.
5. Select **Start game** in **Run game** to save the results and show the first card, then open voting, close, and reveal. Players see the items alphabetically, drag into their predicted order, and select **Save ranking**. They can change and save again until the deadline. Reveal shows the full correct order and their matches; each correct position earns **20 points**. Items tied in survey results accept either order within their tied positions. Existing quizzes continue to award 100 points.

The game uses a frozen snapshot; later draft edits cannot change the answer key. Ranking orders and aggregate results are included in the existing survey JSON export. No new package or database migration is required; the ranking input uses [Streamlit’s built-in custom components](https://docs.streamlit.io/develop/concepts/custom-components/components-v2).

### Counts, write-ins, and scoring

- A respondent selecting three categories contributes one count to each. The denominator is the number who answered that question, not the number of selections. Percentages can exceed 100% when summed.
- In **Survey results**, map write-ins to an existing category or a new category. Several entries from the same person mapped to one category count once. Unmapped entries remain under Other; Other disappears for that person only after every write-in has been mapped elsewhere.
- Short-text responses stay private unless you explicitly approve an excerpt for the walkthrough. No automatic AI analysis or categorization is performed.
- **Start game** closes the survey, saves a frozen snapshot, and shows the first card. It fixes the game’s answer boards, correct answers, and approved excerpts. With fewer than five answers to a mapped question, that opening becomes an unscored live poll.
- Correct quiz and Guess the room answers earn 100 points only after the reveal. Ranking rounds earn **20 points per answer in the correct position**, also only after reveal. All survey answers tied for first count as correct. No speed bonuses, penalties, or bonus tie-break rounds.
- Voting uses the server’s deadline. Players can change their answer while voting is open. Scores are derived from saved votes and revealed questions, so retries/reloads do not award duplicate points.
- Players should copy their private rejoin code. After a refresh or on another device, they can restore their nickname and score with it. Do not share rejoin codes with the room.

## Brand assets

`static/hint-wordmark.png` is the exact logo supplied for this project. The interface uses the brand book’s printed digital hex colors: dark blue `#000072`, light blue `#CCECF4`, and electric blue `#0037FF`.

Licensed fonts were not supplied. Arial and a system monospace are the defaults. To use the brand fonts, add licensed webfont files at:

```text
static/fonts/walter-neue-regular.woff2
static/fonts/walter-neue-bold.woff2
static/fonts/monument-semi-mono.woff2
```

The app loads these only when present. No external font or AI service calls are required.

## Verification and maintenance

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Tests cover survey validation, multi-answer counts, text grouping, version preservation, scoring, deadlines, ties, concurrent votes, persistent storage, host gating, and the main Streamlit flows. Supabase HTTP-contract tests use a simulated endpoint; a live Supabase deployment still requires the project and credentials above.

Both storage backends use revision checks and retry on conflicts. This keeps concurrent voting from silently overwriting another player’s answer. The small event document design is intended for this 15–25-person workshop, not a public large-scale quiz service. Secrets and database details are never sent to player views.

Use **HOST_GUIDE.md** for the event run sheet. If live voting becomes unreliable, switch to Teams chat, retain points already earned, and continue without further scoring. A complete hosting outage requires using the guide directly until the app returns.

Technical references: [Streamlit fragments](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment), [Streamlit Supabase setup](https://docs.streamlit.io/develop/tutorials/databases/supabase), [Supabase access controls](https://supabase.com/docs/guides/database/postgres/row-level-security).

