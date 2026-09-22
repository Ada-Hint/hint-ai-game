from copy import deepcopy
import json
import unittest

from hintgame import engine as e
from hintgame.content import initial_state, open_ended_survey_questions, question


class TextCategoryTests(unittest.TestCase):
    def setUp(self):
        self.s = initial_state()
        self.q = question('free', 'What task would you never do again?', 'text', required=False, multiple=True)
        # A type conversion can leave old options behind; they must never become text categories.
        self.q['options'] = [{'id': 'stale', 'label': 'Old choice', 'exclusive': False, 'other': False}]
        self.s['survey']['draft'] = [self.q]
        self.s['cards'] = []
        self.vid = e.publish(self.s)

    def submit(self, token, values):
        e.submit_survey(self.s, self.vid, {'free': {'texts': [{'id': str(i), 'value': value} for i, value in enumerate(values)]}}, token)

    def populate(self):
        for i in range(6):
            self.submit(str(i), ['Sales report' if i < 4 else 'Meeting minutes'])
        for entry in e.text_entries(self.s, 'free'):
            e.categorize(self.s, 'free', entry['key'], new_label='Reporting' if entry['value'] == 'Sales report' else 'Meeting notes')

    def test_workshop_draft_has_requested_order_types_and_scale(self):
        qs = open_ended_survey_questions()
        self.assertEqual(len(qs), 13)
        self.assertEqual([q['kind'] for q in qs], ['choice', 'rating', 'choice', 'choice'] + ['text'] * 8 + ['choice'])
        self.assertEqual(qs[0]['display'], 'checkboxes')
        self.assertTrue(qs[0]['multiple'])
        self.assertEqual((qs[1]['minimum'], qs[1]['maximum']), (1, 10))
        self.assertEqual(qs[-1]['options'][-1]['label'], 'Other')
        self.assertTrue(qs[-1]['options'][-1]['other'])
        self.assertTrue(qs[-1]['multiple'])
        e.validate_import(json.loads(json.dumps({'format': 'hint-survey-draft-v1', 'questions': qs})))

    def test_grouping_counts_each_person_once_and_exposes_unreviewed_entries(self):
        self.submit('one', ['Sales report', 'Weekly sales numbers', 'No idea'])
        self.submit('two', ['Meeting minutes'])
        self.submit('skip', [])
        entries = e.text_entries(self.s, 'free')
        e.categorize(self.s, 'free', entries[0]['key'], new_label='Reporting')
        e.categorize(self.s, 'free', entries[1]['key'], new_label='reporting')
        e.categorize(self.s, 'free', entries[2]['key'], e.EXCLUDED_CATEGORY)
        result = e.aggregate(self.s, 'free')
        self.assertEqual(result['denominator'], 1)
        self.assertEqual((result['answered'], result['ungrouped'], result['excluded']), (2, 1, 1))
        self.assertEqual([(r['label'], r['count'], r['percent']) for r in result['rows']], [('Reporting', 1, 100)])
        e.categorize(self.s, 'free', entries[3]['key'], new_label='Meeting notes')
        result = e.aggregate(self.s, 'free')
        self.assertEqual((result['denominator'], result['ungrouped']), (2, 0))
        self.assertEqual([r['percent'] for r in result['rows']], [50, 50])
        e.categorize(self.s, 'free', entries[0]['key'], None)
        self.assertEqual(e.aggregate(self.s, 'free')['ungrouped'], 1)

    def test_linked_guess_and_ranking_use_categories_not_original_text(self):
        self.populate()
        guess_id = e.add_survey_card(self.s, 'free', 'survey', 'What would most people stop doing?')
        rank_id = e.add_survey_card(self.s, 'free', 'ranking', 'Rank the tasks people want to stop doing')
        e.start_game(self.s)
        guess, ranking = self.s['game']['deck']
        self.assertEqual((guess['id'], ranking['id']), (guess_id, rank_id))
        self.assertEqual([r['count'] for r in guess['snapshot']['rows']], [4, 2])
        self.assertEqual({o['label'] for o in guess['options']}, {'Reporting', 'Meeting notes'})
        self.assertNotIn('Sales report', json.dumps(self.s['game']['deck']))
        self.assertNotIn('Old choice', json.dumps(self.s['game']['deck']))
        self.assertEqual(e.answer_points(ranking, ranking['correct']), 40)
        self.assertEqual(e.answer_points(guess, guess['correct'][0]), 100)
        with self.assertRaises(e.RuleError):
            e.categorize(self.s, 'free', e.text_entries(self.s, 'free')[0]['key'], None)

    def test_unreviewed_or_insufficient_categories_block_start(self):
        self.populate()
        self.submit('late', ['Confidential example'])
        e.add_survey_card(self.s, 'free')
        self.assertIn('Group or exclude', e.start_readiness(self.s)['error'])
        last = e.text_entries(self.s, 'free')[-1]
        e.categorize(self.s, 'free', last['key'], e.EXCLUDED_CATEGORY)
        self.assertIsNone(e.start_readiness(self.s)['error'])
        for entry in e.text_entries(self.s, 'free'):
            e.categorize(self.s, 'free', entry['key'], e.EXCLUDED_CATEGORY)
        self.assertIn('at least two categories', e.start_readiness(self.s)['error'])

    def test_new_survey_version_does_not_reuse_old_groups(self):
        self.populate()
        before = deepcopy(e.aggregate(self.s, 'free', self.vid))
        self.s['survey']['draft'][0]['title'] = 'Changed question'
        e.publish(self.s)
        self.assertEqual(e.aggregate(self.s, 'free', self.vid), before)
        self.assertEqual(e.aggregate(self.s, 'free')['rows'], [])
        with self.assertRaises(e.RuleError):
            e.categorize(self.s, 'free', e.text_entries(self.s, 'free', self.vid)[0]['key'], new_label='Old response')

    def test_low_count_guess_becomes_poll_but_rank_needs_five(self):
        self.submit('one', ['Reporting'])
        self.submit('two', ['Meeting notes'])
        for entry in e.text_entries(self.s, 'free'):
            e.categorize(self.s, 'free', entry['key'], new_label=entry['value'])
        e.add_survey_card(self.s, 'free')
        copy = deepcopy(self.s)
        e.start_game(copy)
        self.assertEqual(copy['game']['deck'][0]['kind'], 'poll')
        e.add_survey_card(self.s, 'free', 'ranking')
        self.assertIn('five', e.start_readiness(self.s)['error'])


if __name__ == '__main__':
    unittest.main()
