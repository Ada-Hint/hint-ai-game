"""Saved authoring content must be the source of each live/rehearsal run."""
from copy import deepcopy
import unittest

from hintgame import engine as e
from hintgame.content import initial_state, open_ended_survey_questions


class SavedContentTests(unittest.TestCase):
    def saved_live(self):
        state = e.seed_rehearsal()
        cards = deepcopy(state['cards'])
        quiz = next(c for c in cards if c['id'] == 'brief')
        quiz.update(title='My saved question', lesson='My saved takeaway', explanation='My saved explanation')
        quiz['options'][0]['label'] = 'My edited answer'
        quiz['correct'] = [quiz['options'][0]['id']]
        poll = next(c for c in cards if c['id'] == 'practice')
        poll['title'] = 'My saved opening poll'
        rank = {'id': 'custom-ranking', 'kind': 'ranking', 'title': 'My saved ranking', 'section': 'ORDER IT',
                'ranking_source': 'manual', 'options': [{'id': 'one', 'label': 'First step'}, {'id': 'two', 'label': 'Next step'}],
                'correct': ['one', 'two'], 'scored': True}
        e.save_cards(state, [poll, quiz, rank])
        return state

    def test_live_start_uses_complete_saved_content_after_restart(self):
        state = self.saved_live()
        saved = deepcopy(state['cards'])
        e.start_game(state)
        self.assertEqual(state['game']['deck'][:2], saved[:2])
        self.assertEqual([c['id'] for c in state['game']['deck']], [c['id'] for c in saved])
        self.assertEqual(state['game']['deck'][2]['correct'], ['one', 'two'])
        e.reset_game(state)
        state['cards'][0]['title'] = 'Saved again after reset'
        e.start_game(state)
        self.assertEqual(e.current_card(state)['title'], 'Saved again after reset')

    def test_prepared_lobby_cannot_reuse_outdated_deck(self):
        state = e.seed_rehearsal()
        e.freeze(state)
        # Reproduce a persisted, previously prepared deck differing from saved cards.
        state['cards'] = deepcopy(self.saved_live()['cards'])
        preview = e.start_readiness(state)
        self.assertEqual(preview['cards'][0]['title'], 'My saved opening poll')
        self.assertEqual(state['game']['index'], -1)
        e.start_game(state)
        self.assertEqual(e.current_card(state)['title'], 'My saved opening poll')
        self.assertEqual(len(state['game']['deck']), 3)

    def test_rehearsal_uses_saved_content_without_real_people_or_responses(self):
        source = self.saved_live()
        source['players'] = {'private-player': {'nickname': 'Private real player'}}
        source['survey']['responses'][0]['answers']['ideas']['texts'] = [{'id': 'secret', 'value': 'Private real response'}]
        before = deepcopy(source)
        demo = e.seed_rehearsal(source)
        self.assertEqual(demo['cards'], source['cards'])
        self.assertEqual(demo['players'], {})
        self.assertEqual(len(e.responses_for(demo)), 8)
        self.assertNotIn('Private real', str(demo))
        e.start_game(demo)
        self.assertEqual(e.current_card(demo)['title'], source['cards'][0]['title'])
        self.assertEqual(source, before)

    def test_idle_sync_refreshes_content_but_active_session_keeps_snapshot(self):
        source = self.saved_live()
        demo = e.seed_rehearsal()
        e.join_player(demo, 'Demo player', 'demo-token')
        self.assertTrue(e.sync_rehearsal(demo, source))
        self.assertEqual(len(demo['players']), 1)
        unchanged = deepcopy(demo)
        self.assertFalse(e.sync_rehearsal(demo, source))
        self.assertEqual(demo, unchanged)
        e.start_game(demo)
        source['cards'][0]['title'] = 'Latest saved opening'
        self.assertFalse(e.sync_rehearsal(demo, source))
        self.assertEqual(e.current_card(demo)['title'], 'My saved opening poll')
        e.reset_game(demo)
        self.assertTrue(e.sync_rehearsal(demo, source))
        e.start_game(demo)
        self.assertEqual(e.current_card(demo)['title'], 'Latest saved opening')

    def test_sample_responses_support_custom_survey_schemas_and_linked_cards(self):
        source = initial_state()
        questions = open_ended_survey_questions()
        # Exercise required text, rating, choice and ranking instead of hardcoded IDs.
        questions = [questions[1], questions[4], questions[0]]
        questions[1]['required'] = True
        ranking = deepcopy(questions[2])
        ranking.update(id='custom-rank-survey', kind='ranking', multiple=False)
        for option in ranking['options']:
            option.update(other=False, exclusive=False)
        questions.append(ranking)
        e.save_draft(source, questions)
        e.publish(source)
        source['cards'] = [source['cards'][0]]
        e.add_survey_card(source, questions[1]['id'], 'survey', 'Guess the sample categories')
        e.add_survey_card(source, ranking['id'], 'ranking', 'Rank the saved survey answers')
        demo = e.seed_rehearsal(source)
        self.assertEqual(e.active_version(demo)['questions'], questions)
        self.assertEqual(e.aggregate(demo, questions[1]['id'])['ungrouped'], 0)
        e.start_game(demo)
        self.assertEqual([c['title'] for c in demo['game']['deck']], [c['title'] for c in source['cards']])
        self.assertTrue(demo['game']['deck'][1]['scored'])
        self.assertTrue(demo['game']['deck'][2]['scored'])

    def test_failed_start_does_not_damage_prepared_state(self):
        state = self.saved_live()
        e.freeze(state)
        state['cards'][0]['title'] = ''
        before = deepcopy(state)
        with self.assertRaises(e.RuleError):
            e.start_game(state)
        self.assertEqual(state, before)


if __name__ == '__main__':
    unittest.main()
