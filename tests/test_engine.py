from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from hintgame import engine as e
from hintgame.content import initial_state
from hintgame.storage import SQLiteRepository


def answers(state):
    return {q["id"]: {"choices": [q["options"][0]["id"]] if q["options"] else [], "texts": [], "rating": 3 if q["kind"] == "rating" else None} for q in e.active_version(state)["questions"]}


class SurveyTests(unittest.TestCase):
    def setUp(self):
        self.s = initial_state()
        self.vid = e.publish(self.s)

    def submit(self, value, token="receipt-one"):
        return e.submit_survey(self.s, self.vid, value, token)

    def test_multiselect_counts_people_not_selections(self):
        a = answers(self.s)
        a["tasks"]["choices"] = ["tasks_0", "tasks_1", "tasks_0"]
        self.submit(a)
        self.submit(a, "second")
        rows = {r["id"]: r for r in e.aggregate(self.s, "tasks")["rows"]}
        self.assertEqual(rows["tasks_0"]["count"], 2)
        self.assertEqual(rows["tasks_1"]["percent"], 100)
        self.assertEqual(e.aggregate(self.s, "tasks")["denominator"], 2)

    def test_optional_question_denominator_excludes_skips(self):
        a = answers(self.s)
        a["area"]["choices"] = []
        self.submit(a)
        self.submit(answers(self.s), "second")
        self.assertEqual(e.aggregate(self.s, "area")["denominator"], 1)

    def test_exclusive_choices_are_validated_server_side(self):
        for values in [["tools_0", "tools_3"], ["tools_3", "tools_4"]]:
            a = answers(self.s)
            a["tools"]["choices"] = values
            with self.assertRaises(e.RuleError):
                self.submit(a)
        self.assertEqual(self.s["survey"]["responses"], [])

    def test_single_choice_and_rating_validation(self):
        a = answers(self.s)
        a["frequency"]["choices"] = ["frequency_0", "frequency_1"]
        with self.assertRaises(e.RuleError):
            self.submit(a)
        a = answers(self.s)
        for value in [0, 6, True, "3"]:
            a["confidence"]["rating"] = value
            with self.assertRaises(e.RuleError):
                self.submit(a)

    def test_repeatable_text_and_other_deduplication(self):
        a = answers(self.s)
        a["tasks"]["choices"] = ["tasks_0", "tasks_5"]
        a["tasks"]["texts"] = [{"id": "one", "value": "Email copy"}, {"id": "two", "value": "Product copy"}]
        a["ideas"]["texts"] = [{"id": "1", "value": "Summarize a report"}, {"id": "2", "value": "Explain a spreadsheet"}, {"id": "3", "value": " "}]
        self.submit(a)
        entries = e.text_entries(self.s, "tasks")
        e.categorize(self.s, "tasks", entries[0]["key"], "tasks_0")
        result = {r["id"]: r["count"] for r in e.aggregate(self.s, "tasks")["rows"]}
        self.assertEqual(result["tasks_0"], 1)
        self.assertEqual(result["tasks_5"], 1)
        e.categorize(self.s, "tasks", entries[1]["key"], "tasks_0")
        result = {r["id"]: r["count"] for r in e.aggregate(self.s, "tasks")["rows"]}
        self.assertEqual(result["tasks_0"], 1)
        self.assertEqual(result["tasks_5"], 0)
        self.assertEqual(len(e.text_entries(self.s, "ideas")), 2)

    def test_new_categories_are_reused_and_frozen(self):
        a = answers(self.s)
        a["tasks"] = {"choices": ["tasks_5"], "texts": [{"id": "1", "value": "Planning"}, {"id": "2", "value": "Planning projects"}]}
        self.submit(a)
        for item in e.text_entries(self.s, "tasks"):
            e.categorize(self.s, "tasks", item["key"], new_label="Planning")
        result = e.aggregate(self.s, "tasks")
        self.assertEqual([r["count"] for r in result["rows"] if r["label"] == "Planning"], [1])
        e.freeze(self.s)
        with self.assertRaises(e.RuleError):
            e.categorize(self.s, "tasks", e.text_entries(self.s, "tasks")[0]["key"], new_label="Something else")

    def test_idempotent_submit_and_anonymous_record(self):
        a = answers(self.s)
        self.submit(a)
        self.s["survey"]["open"] = False
        self.submit(a)
        self.assertEqual(len(self.s["survey"]["responses"]), 1)
        self.assertEqual(set(self.s["survey"]["responses"][0]), {"id", "version_id", "answers"})
        with self.assertRaises(e.RuleError):
            self.submit(a, "new receipt")

    def test_new_version_preserves_old_answers(self):
        self.submit(answers(self.s))
        self.s["survey"]["draft"][0]["title"] = "Edited question"
        second = e.publish(self.s)
        self.assertNotEqual(self.vid, second)
        self.assertEqual(len(e.responses_for(self.s, self.vid)), 1)
        self.assertEqual(len(e.responses_for(self.s, second)), 0)
        with self.assertRaises(e.RuleError):
            e.submit_survey(self.s, self.vid, answers(self.s), "stale")

    def test_freeze_requires_valid_mapping(self):
        self.s["cards"][1]["survey_question_id"] = "gone"
        with self.assertRaises(e.RuleError):
            e.freeze(self.s)
        self.assertFalse(self.s["frozen"])

    def test_approved_excerpts_only(self):
        a = answers(self.s)
        a["ideas"]["texts"] = [{"id": "1", "value": "Public example"}, {"id": "2", "value": "Private example"}]
        self.submit(a)
        entry = e.text_entries(self.s, "ideas")[0]
        e.approve_entry(self.s, "ideas", entry["key"], True)
        e.freeze(self.s)
        self.assertEqual(self.s["frozen_excerpts"], ["Public example"])

    def test_draft_import_roundtrip_and_bad_input(self):
        e.validate_import({"format": "hint-survey-draft-v1", "questions": self.s["survey"]["draft"]})
        for value in [[], {"questions": []}, {"format": "hint-survey-draft-v1", "questions": [None]}]:
            with self.assertRaises(e.RuleError):
                e.validate_import(value)


class GameTests(unittest.TestCase):
    def setUp(self):
        self.s = e.seed_rehearsal()
        e.freeze(self.s)
        e.join_player(self.s, "Watermelon", "player1")
        e.game_action(self.s, "start", now=100)

    def next_card(self):
        e.game_action(self.s, "open", now=100)
        e.game_action(self.s, "close", now=110)
        e.game_action(self.s, "reveal", now=110)
        e.game_action(self.s, "next", now=111)

    def test_vote_can_change_and_deadline_is_enforced(self):
        c = e.current_card(self.s)
        e.game_action(self.s, "open", now=100)
        e.vote(self.s, "player1", c["id"], "A", now=101)
        e.vote(self.s, "player1", c["id"], "B", now=129)
        self.assertEqual(len(self.s["votes"][c["id"]]), 1)
        with self.assertRaises(e.RuleError):
            e.vote(self.s, "player1", c["id"], "C", now=130)
        self.assertEqual(self.s["votes"][c["id"]][e.digest("player1")], "B")
        self.assertEqual(e.phase(self.s, now=130), "closed")

    def test_no_reveal_before_close_and_no_stale_votes(self):
        with self.assertRaises(e.RuleError):
            e.game_action(self.s, "reveal", now=100)
        self.next_card()
        e.game_action(self.s, "open", now=100)
        with self.assertRaises(e.RuleError):
            e.vote(self.s, "player1", "practice", "A", now=105)

    def test_scores_only_on_reveal_and_never_double_award(self):
        self.next_card()
        c = e.current_card(self.s)
        e.game_action(self.s, "open", now=100)
        e.vote(self.s, "player1", c["id"], c["correct"][0], now=105)
        self.assertEqual(e.leaderboard(self.s)[0]["score"], 0)
        e.game_action(self.s, "close", now=110)
        e.game_action(self.s, "reveal", now=110)
        self.assertEqual(e.leaderboard(self.s)[0]["score"], 100)
        for _ in range(5):
            e.game_action(self.s, "reveal_next", now=110)
        self.assertEqual(e.leaderboard(self.s)[0]["score"], 100)

    def test_tied_survey_answers_both_score(self):
        s = initial_state()
        vid = e.publish(s)
        for i in range(6):
            a = answers(s)
            a["tasks"]["choices"] = ["tasks_0", "tasks_1"]
            e.submit_survey(s, vid, a, str(i))
        e.freeze(s)
        c = s["game"]["deck"][1]
        self.assertEqual(set(c["correct"]), {"tasks_0", "tasks_1"})
        s["game"].update(index=1, phase="open", deadline=130)
        for token, answer in [("p1", "tasks_0"), ("p2", "tasks_1")]:
            e.join_player(s, token, token)
            e.vote(s, token, c["id"], answer, now=100)
        e.game_action(s, "close", now=110)
        e.game_action(s, "reveal", now=110)
        self.assertEqual([(p["score"], p["rank"]) for p in e.leaderboard(s)], [(100, 1), (100, 1)])

    def test_low_response_fallback_and_frozen_snapshot(self):
        s = initial_state()
        vid = e.publish(s)
        e.submit_survey(s, vid, answers(s), "one")
        e.freeze(s)
        self.assertEqual(s["game"]["deck"][1]["kind"], "poll")
        self.assertFalse(s["game"]["deck"][1]["scored"])
        with self.assertRaises(e.RuleError):
            e.submit_survey(s, vid, answers(s), "late")
        old_title = s["game"]["deck"][3]["title"]
        s["cards"][3]["title"] = "Local edit cannot alter frozen deck"
        self.assertEqual(s["game"]["deck"][3]["title"], old_title)

    def test_rejoin_identity_and_nickname_collision(self):
        self.assertEqual(e.join_player(self.s, "Changed", "player1"), e.digest("player1"))
        self.assertEqual(len(self.s["players"]), 1)
        with self.assertRaises(e.RuleError):
            e.join_player(self.s, "watermelon", "player2")

    def test_chat_fallback_keeps_earned_points(self):
        self.next_card()
        c = e.current_card(self.s)
        e.game_action(self.s, "open", now=100)
        e.vote(self.s, "player1", c["id"], c["correct"][0], now=101)
        e.game_action(self.s, "close", now=102)
        e.game_action(self.s, "reveal", now=102)
        e.game_action(self.s, "chat_fallback")
        self.assertEqual(e.leaderboard(self.s)[0]["score"], 100)
        self.assertFalse(self.s["game"]["deck"][3]["scored"])

    def test_reset_preserves_surveys_only(self):
        before = deepcopy(self.s["survey"])
        e.reset_game(self.s)
        self.assertEqual(self.s["survey"], before)
        self.assertFalse(self.s["frozen"])
        self.assertEqual(self.s["players"], {})

    def test_start_prepares_snapshot_without_starting_timer(self):
        s = e.seed_rehearsal()
        before = deepcopy(s)
        self.assertIsNone(e.start_readiness(s)['error'])
        self.assertEqual(s, before)
        e.start_game(s, now=100)
        self.assertTrue(s['frozen'])
        self.assertFalse(s['survey']['open'])
        self.assertEqual(s['game']['index'], 0)
        self.assertEqual(s['game']['phase'], 'ready')
        self.assertIsNone(s['game']['deadline'])
        with self.assertRaises(e.RuleError):
            e.start_game(s, now=101)
        self.assertEqual(s['game']['index'], 0)

    def test_start_accepts_previously_frozen_game(self):
        s = e.seed_rehearsal()
        e.freeze(s)
        deck = deepcopy(s['game']['deck'])
        e.start_game(s)
        self.assertEqual(s['game']['deck'], deck)
        self.assertEqual(s['game']['phase'], 'ready')

    def test_start_readiness_explains_blockers_and_poll_fallbacks(self):
        s = initial_state()
        self.assertIn('Publish', e.start_readiness(s)['error'])
        e.publish(s)
        ready = e.start_readiness(s)
        self.assertIsNone(ready['error'])
        self.assertEqual(len(ready['polls']), 2)
        s['cards'][1]['survey_question_id'] = 'missing'
        before = deepcopy(s)
        self.assertIsNotNone(e.start_readiness(s)['error'])
        self.assertEqual(s, before)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "state.db"
        self.repo = SQLiteRepository(self.path, factory=e.seed_rehearsal)

    def tearDown(self):
        self.directory.cleanup()

    def test_25_concurrent_players_and_votes_persist_on_restart(self):
        self.repo.mutate(e.freeze)
        self.repo.mutate(lambda s: e.game_action(s, "start", now=100))
        self.repo.mutate(lambda s: e.game_action(s, "open", now=100))
        def participate(i):
            self.repo.mutate(lambda s: e.join_player(s, f"Player {i}", f"token-{i}"))
            self.repo.mutate(lambda s: e.vote(s, f"token-{i}", "practice", "A", now=101))
            self.repo.mutate(lambda s: e.vote(s, f"token-{i}", "practice", "B", now=102))
        with ThreadPoolExecutor(max_workers=25) as pool:
            list(pool.map(participate, range(25)))
        restarted = SQLiteRepository(self.path).snapshot()
        self.assertEqual(len(restarted["players"]), 25)
        self.assertEqual(len(restarted["votes"]["practice"]), 25)
        self.assertEqual(set(restarted["votes"]["practice"].values()), {"B"})

    def test_rehearsal_isolation(self):
        demo = SQLiteRepository(self.path, "rehearsal", e.seed_rehearsal)
        self.repo.mutate(lambda s: e.join_player(s, "Real player", "real-token"))
        demo.mutate(e.freeze)
        self.assertFalse(self.repo.snapshot()["frozen"])
        self.assertEqual(demo.snapshot()["players"], {})

    def test_rejected_transaction_does_not_write_partial_state(self):
        before = self.repo.snapshot()
        def bad_change(s):
            s["players"]["bad"] = {"nickname": "Not saved"}
            raise e.RuleError("Stop")
        with self.assertRaises(e.RuleError):
            self.repo.mutate(bad_change)
        self.assertEqual(self.repo.snapshot(), before)

    def test_stale_revision_cannot_overwrite_new_data(self):
        revision, document = self.repo.read()
        self.repo.mutate(lambda s: e.join_player(s, "Fresh", "fresh-token"))
        self.assertFalse(self.repo.compare_swap(revision, document))
        self.assertEqual(len(self.repo.snapshot()["players"]), 1)


if __name__ == "__main__":
    unittest.main()
