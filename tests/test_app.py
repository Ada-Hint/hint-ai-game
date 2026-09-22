import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from hintgame import engine
from hintgame.content import open_ended_survey_questions
from hintgame.storage import SQLiteRepository

APP = Path(__file__).resolve().parents[1] / "app.py"


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "test.db")
        self.env = patch.dict(os.environ, {"STORAGE_BACKEND": "sqlite", "SQLITE_PATH": self.db, "HOST_PASSWORD": "test-host-password-only", "EVENT_CODE": "TEST", "EVENT_ID": "test-event", "PUBLIC_BASE_URL": "http://localhost:8501"})
        self.env.start()
        self.repo = SQLiteRepository(self.db, "test-event", engine.seed_rehearsal)

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def app(self, view, authorized=True):
        at = AppTest.from_file(str(APP), default_timeout=15)
        at.query_params["view"] = view
        if authorized:
            at.query_params["event"] = "TEST"
        at.run()
        self.assertFalse(at.exception, [x.message for x in at.exception])
        return at

    def host(self):
        at = self.app("manage")
        at.text_input[0].set_value("test-host-password-only")
        next(b for b in at.button if b.label == "Sign in").click().run()
        self.assertFalse(at.exception, [x.message for x in at.exception])
        return at

    def test_event_and_host_are_gated(self):
        at = self.app("survey", authorized=False)
        self.assertEqual([v.label for v in at.text_input], ["Event code"])
        self.assertFalse(at.multiselect)
        admin = self.app("manage")
        self.assertNotIn("Start game", [b.label for b in admin.button])
        admin.text_input[0].set_value("wrong")
        next(b for b in admin.button if b.label == "Sign in").click().run()
        self.assertTrue(admin.error)

    def test_host_editor_can_save_publish_and_preserve_archive(self):
        at = self.host()
        at.radio(key="host_tab").set_value("Edit survey").run()
        self.assertFalse(at.exception, [x.message for x in at.exception])
        title = next(t for t in at.text_input if t.label == "Question")
        title.set_value("Which parts of marketing do you work on?")
        next(b for b in at.button if b.label == "Save question").click().run()
        self.assertFalse(at.exception, [x.message for x in at.exception])
        next(b for b in at.button if b.label == "Publish survey").click().run()
        self.assertFalse(at.exception, [x.message for x in at.exception])
        state = self.repo.snapshot()
        self.assertEqual(len(state["survey"]["versions"]), 2)
        self.assertEqual(len(state["survey"]["responses"]), 8)
        self.assertEqual(engine.active_version(state)["questions"][0]["title"], "Which parts of marketing do you work on?")

    def test_survey_multiple_other_text_and_submission_receipt(self):
        at = self.app("survey")
        vid = self.repo.snapshot()["survey"]["active_version"]
        prefix = f"survey_live_{vid}_"
        at.multiselect(key=prefix + "tools").set_value(["tools_0", "tools_1"]).run()
        at.radio(key=prefix + "frequency").set_value("frequency_2").run()
        at.radio(key=prefix + "confidence").set_value(3).run()
        at.multiselect(key=prefix + "tasks").set_value(["tasks_0", "tasks_5"]).run()
        at.text_input(key=prefix + "tasks_other_0").set_value("Planning")
        at.button(key=prefix + "tasks_other_add").click().run()
        at.text_input(key=prefix + "tasks_other_1").set_value("Presentations")
        at.multiselect(key=prefix + "hesitations").set_value(["hesitations_0", "hesitations_1"]).run()
        next(b for b in at.button if b.label == "Send my hints →").click().run()
        self.assertFalse(at.exception, [x.message for x in at.exception])
        self.assertIn("Survey submitted", at.success[0].value)
        records = self.repo.snapshot()["survey"]["responses"]
        self.assertEqual(len(records), 9)
        self.assertEqual(len(records[-1]["answers"]["tasks"]["texts"]), 2)
        self.assertNotIn("player_id", records[-1])
        reloaded = AppTest.from_file(str(APP), default_timeout=15)
        reloaded.query_params.update({"view": "survey", "event": "TEST", "receipt": at.query_params["receipt"]})
        reloaded.run()
        self.assertFalse(reloaded.exception)
        self.assertIn("Survey submitted", reloaded.success[0].value)
        self.assertEqual(len(self.repo.snapshot()["survey"]["responses"]), 9)

    def test_exclusive_selection_replaces_existing_selections(self):
        at = self.app("survey")
        vid = self.repo.snapshot()["survey"]["active_version"]
        key = f"survey_live_{vid}_tools"
        at.multiselect(key=key).set_value(["tools_0", "tools_1"]).run()
        at.multiselect(key=key).set_value(["tools_0", "tools_1", "tools_3"]).run()
        self.assertEqual(at.multiselect(key=key).value, ["tools_3"])
        at.multiselect(key=key).set_value(["tools_3", "tools_0"]).run()
        self.assertEqual(at.multiselect(key=key).value, ["tools_0"])

    def test_player_host_and_presentation_share_game(self):
        host = self.host()
        player = self.app("play")
        player.text_input[0].set_value("Test Player")
        next(b for b in player.button if b.label == "I’m in →").click().run()
        self.assertFalse(player.exception, [x.message for x in player.exception])
        host.button(key="host_start_game").click().run()
        self.assertIn("GAME RUNNING", " ".join(m.value for m in host.markdown))
        self.assertEqual(self.repo.snapshot()["game"]["phase"], "ready")
        next(b for b in host.button if b.label == "Open voting · 30 seconds").click().run()
        player.run()
        player.button(key="vote_practice_A").click().run()
        self.assertEqual(len(self.repo.snapshot()["votes"]["practice"]), 1)
        board = self.app("present")
        self.assertNotIn("Close voting", [b.label for b in board.button])
        self.assertFalse(board.exception)
        next(b for b in host.button if b.label == "Close voting").click().run()
        next(b for b in host.button if b.label == "Reveal results").click().run()
        player.run()
        self.assertFalse(player.exception, [x.message for x in player.exception])
        self.assertFalse(any(b.key == "vote_practice_A" for b in player.button))

    def test_remaining_host_views_render(self):
        at = self.host()
        for tab in ["Survey results", "Game content", "Setup & links"]:
            at.radio(key="host_tab").set_value(tab).run()
            self.assertFalse(at.exception, [x.message for x in at.exception])

    def test_host_start_blocker_and_navigation(self):
        self.repo.mutate(lambda s: s['survey'].update(active_version=None))
        at = self.host()
        self.assertTrue(at.button(key='host_start_game').disabled)
        self.assertTrue(any('Publish' in error.value for error in at.error))
        next(b for b in at.button if b.label == 'Go to Edit survey').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.radio(key='host_tab').value, 'Edit survey')

    def test_host_can_run_entire_deck_and_finish(self):
        at = self.host()
        self.assertIn('GAME NOT STARTED', ' '.join(m.value for m in at.markdown))
        at.button(key='host_start_game').click().run()
        def click(label):
            next(b for b in at.button if b.label == label).click().run()
            self.assertFalse(at.exception, [x.message for x in at.exception])
            self.assertFalse(at.error)
        for index, card in enumerate(self.repo.snapshot()['game']['deck']):
            self.assertEqual(self.repo.snapshot()['game']['index'], index)
            self.assertIn('GAME RUNNING', ' '.join(m.value for m in at.markdown))
            if card.get('options'):
                click('Open voting · 30 seconds')
                click('Close voting')
                click('Reveal results')
                if card['kind'] == 'survey':
                    click('Reveal next answer')
                    click('Reveal all answers')
            if card['kind'] == 'demo':
                for _ in range(3):
                    click('Next walkthrough step →')
            last = index == len(self.repo.snapshot()['game']['deck']) - 1
            click('Finish game' if last else 'Next card →')
        self.assertEqual(self.repo.snapshot()['game']['phase'], 'finished')
        at.run()  # Settle the fragment refresh after the final button-triggered rerun.
        self.assertIn('GAME FINISHED', ' '.join(m.value for m in at.markdown))
        self.assertFalse(any(b.label in {'Start game', 'Next card →', 'Finish game'} for b in at.button))

    def test_expired_vote_offers_reveal_or_reopen(self):
        self.repo.mutate(engine.start_game)
        self.repo.mutate(lambda s: engine.game_action(s, 'open', now=1))
        at = self.host()
        self.assertIn('Voting closed', ' '.join(m.value for m in at.markdown))
        self.assertIn('Reveal results', [b.label for b in at.button])
        next(b for b in at.button if b.label == 'Reopen · 15 seconds').click().run()
        self.assertEqual(engine.phase(self.repo.snapshot()), 'open')
        self.assertIn('Close voting', [b.label for b in at.button])

    def test_all_presentation_cards_and_walkthrough_steps_render(self):
        self.repo.mutate(engine.freeze)
        for index, card in enumerate(self.repo.snapshot()["game"]["deck"]):
            def show(s, i=index):
                s["game"].update(index=i, phase="revealed", reveal_count=100, demo_step=0)
            self.repo.mutate(show)
            self.app("present")
            if card["kind"] == "demo":
                for step in range(1, 4):
                    self.repo.mutate(lambda s, n=step: s["game"].update(demo_step=n))
                    self.app("present")

    def test_rejoin_restores_existing_player(self):
        self.repo.mutate(lambda s: engine.join_player(s, "Returning player", "PRIVATECODE"))
        at = self.app("play")
        next(t for t in at.text_input if t.label == "Your private rejoin code").set_value("privatecode")
        next(b for b in at.button if b.label == "Rejoin").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(self.repo.snapshot()["players"]), 1)
        self.assertEqual(at.session_state["player_token_live"], "PRIVATECODE")

    def test_added_editor_rows_get_stable_unique_ids(self):
        at = self.host()
        at.radio(key='host_tab').set_value('Edit survey').run()
        at.selectbox(key='edit_qid').set_value('tools').run()
        q = next(q for q in self.repo.snapshot()['survey']['draft'] if q['id'] == 'tools')
        key = f'question_options_tools_choice_{engine.digest(str(q))[:10]}'
        at.session_state[key] = {'edited_rows': {}, 'deleted_rows': [], 'added_rows': [{'label': name} for name in ['Claude', 'Grok', 'Meta AI']]}
        next(b for b in at.button if b.label == 'Save question').click().run()
        self.assertFalse(at.exception)
        self.assertFalse(at.error)
        saved = next(q for q in self.repo.snapshot()['survey']['draft'] if q['id'] == 'tools')
        self.assertEqual(len(saved['options']), 8)
        self.assertEqual(len({o['id'] for o in saved['options']}), 8)
        self.assertEqual(saved['options'][:5], q['options'])
        next(b for b in at.button if b.label == 'Save question').click().run()
        self.assertEqual(next(q for q in self.repo.snapshot()['survey']['draft'] if q['id'] == 'tools'), saved)

    def test_ranking_survey_and_game_editors_and_views(self):
        at = self.host()
        at.radio(key='host_tab').set_value('Edit survey').run()
        at.selectbox(key='q_kind_area').set_value('ranking').run()
        next(b for b in at.button if b.label == 'Save question').click().run()
        self.assertFalse(at.exception, [x.message for x in at.exception])
        self.assertFalse(at.error)
        q = self.repo.snapshot()['survey']['draft'][0]
        self.assertEqual(q['kind'], 'ranking')
        self.assertFalse(any(o['other'] or o['exclusive'] for o in q['options']))
        next(b for b in at.button if b.label == 'Publish survey').click().run()
        self.app('survey')
        at.radio(key='host_tab').set_value('Survey results').run()
        self.assertFalse(at.exception, [x.message for x in at.exception])
        at.radio(key='host_tab').set_value('Game content').run()
        next(b for b in at.button if b.label == '＋ Add a ranking round').click().run()
        c = next(c for c in self.repo.snapshot()['cards'] if c['kind'] == 'ranking')
        self.assertEqual(at.selectbox(key='edit_card_id').value, c['id'])
        next(b for b in at.button if b.label == 'Save game card').click().run()
        self.assertFalse(at.exception, [x.message for x in at.exception])
        self.assertFalse(at.error)
        self.repo.mutate(engine.freeze)
        def open_card(s):
            index = next(i for i, card in enumerate(s['game']['deck']) if card['id'] == c['id'])
            s['game'].update(index=index, phase='open', deadline=9999999999)
            engine.join_player(s, 'Ranker', 'ranktoken')
        self.repo.mutate(open_card)
        player = AppTest.from_file(str(APP), default_timeout=15)
        player.query_params.update({'view': 'play', 'event': 'TEST'})
        player.session_state['player_token_live'] = 'ranktoken'
        player.run()
        self.assertFalse(player.exception, [x.message for x in player.exception])
        self.repo.mutate(lambda s: engine.vote(s, 'ranktoken', c['id'], ['A', 'C', 'B']))
        self.repo.mutate(lambda s: engine.game_action(s, 'close'))
        self.repo.mutate(lambda s: engine.game_action(s, 'reveal'))
        player.run()
        self.assertFalse(player.exception, [x.message for x in player.exception])
        self.assertTrue(any('1 of 3 positions correct · +20 points.' in x.value for x in player.success))
        self.app('present')

    def test_new_game_answer_can_be_correct_and_keeps_id_on_resave(self):
        at = self.host()
        at.radio(key='host_tab').set_value('Game content').run()
        at.selectbox(key='edit_card_id').set_value('brief').run()
        c = next(c for c in self.repo.snapshot()['cards'] if c['id'] == 'brief')
        key = f'card_options_brief_quiz_{engine.digest(str(c))[:10]}'
        at.session_state[key] = {'edited_rows': {2: {'correct': False}}, 'deleted_rows': [], 'added_rows': [{'label': 'A new correct answer', 'correct': True}, {'label': 'Another response'}]}
        next(b for b in at.button if b.label == 'Save game card').click().run()
        self.assertFalse(at.exception)
        self.assertFalse(at.error)
        saved = next(c for c in self.repo.snapshot()['cards'] if c['id'] == 'brief')
        self.assertEqual(len(saved['options']), 5)
        self.assertEqual(len({o['id'] for o in saved['options']}), 5)
        self.assertEqual(saved['correct'], [saved['options'][3]['id']])
        next(b for b in at.button if b.label == 'Save game card').click().run()
        self.assertEqual(next(c for c in self.repo.snapshot()['cards'] if c['id'] == 'brief'), saved)

    def test_workshop_checkboxes_scale_other_and_submission(self):
        self.repo.mutate(lambda s: engine.save_draft(s, open_ended_survey_questions()))
        self.repo.mutate(engine.publish)
        at = self.app('survey')
        vid = self.repo.snapshot()['survey']['active_version']
        prefix = f'survey_live_{vid}_'
        at.checkbox(key=prefix + 'area_choice_area_0').check().run()
        at.checkbox(key=prefix + 'area_choice_area_2').check().run()
        at.radio(key=prefix + 'ai_comfort').set_value(10).run()
        at.checkbox(key=prefix + 'tools_choice_tools_0').check().run()
        at.checkbox(key=prefix + 'tools_choice_tools_7').check().run()
        self.assertFalse(at.checkbox(key=prefix + 'tools_choice_tools_0').value)
        at.checkbox(key=prefix + 'tools_choice_tools_1').check().run()
        self.assertFalse(at.checkbox(key=prefix + 'tools_choice_tools_7').value)
        at.checkbox(key=prefix + 'ai_usage_choice_ai_usage_0').check().run()
        at.checkbox(key=prefix + 'learning_topics_choice_learning_topics_5').check().run()
        at.text_input(key=prefix + 'learning_topics_other_0').set_value('AI for presentations')
        at.text_input(key=prefix + 'never_again_0').set_value('Weekly reporting')
        next(b for b in at.button if b.label == 'Send my hints →').click().run()
        self.assertFalse(at.exception)
        self.assertFalse(at.error)
        record = self.repo.snapshot()['survey']['responses'][-1]['answers']
        self.assertEqual(record['area']['choices'], ['area_0', 'area_2'])
        self.assertEqual(record['ai_comfort']['rating'], 10)
        self.assertEqual(record['tools']['choices'], ['tools_1'])
        self.assertEqual(record['never_again']['texts'][0]['value'], 'Weekly reporting')
        self.assertEqual(record['learning_topics']['texts'][0]['value'], 'AI for presentations')

    def test_host_groups_text_and_creates_linked_game_round(self):
        def add_text(s):
            s['survey']['responses'][0]['answers']['ideas']['texts'] = [{'id': 'one', 'value': 'Pulling the weekly sales report'}]
        self.repo.mutate(add_text)
        entry = engine.text_entries(self.repo.snapshot(), 'ideas')[0]
        at = self.host()
        at.radio(key='host_tab').set_value('Survey results').run()
        at.selectbox(key='map_' + entry['key'] + '_unassigned').set_value('__new__').run()
        at.text_input(key='new_' + entry['key'] + '_unassigned').set_value('Reporting')
        at.button(key='save_' + entry['key']).click().run()
        self.assertFalse(at.exception)
        self.assertFalse(at.error)
        result = engine.aggregate(self.repo.snapshot(), 'ideas')
        self.assertEqual([(r['label'], r['count']) for r in result['rows']], [('Reporting', 1)])
        at.text_input(key='new_round_title_ideas').set_value('Which task came up most often?')
        at.button(key='add_guess_ideas').click().run()
        state = self.repo.snapshot()
        c = next(c for c in state['cards'] if c.get('survey_question_id') == 'ideas')
        self.assertEqual(c['title'], 'Which task came up most often?')
        self.assertEqual(c['kind'], 'survey')
        self.assertFalse(at.exception)
        at.radio(key='host_tab').set_value('Game content').run()
        at.selectbox(key='edit_card_id').set_value(c['id']).run()
        self.assertFalse(at.exception)
        source = next(v for v in at.selectbox if v.label == 'Survey question feeding this board')
        self.assertEqual(source.value, 'ideas')


if __name__ == "__main__":
    unittest.main()
