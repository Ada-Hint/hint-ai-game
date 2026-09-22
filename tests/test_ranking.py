from copy import deepcopy
import json
import unittest

from hintgame import engine as e
from hintgame.content import initial_state, question


def ranking_card(source='manual'):
    return {'id': 'rank', 'title': 'Rank these tasks', 'kind': 'ranking', 'section': 'RANK',
            'ranking_source': source, 'survey_question_id': 'rank_question', 'top_n': 2,
            'options': [{'id': 'a', 'label': 'Alpha'}, {'id': 'b', 'label': 'Beta'}, {'id': 'c', 'label': 'Gamma'}],
            'correct': ['c', 'b', 'a'], 'scored': True}


class RankingTests(unittest.TestCase):
    def test_editor_ids_handle_null_nan_duplicate_and_string_sentinels(self):
        original = [{'id': 'stable', 'label': 'Old wording'}]
        rows = [{'id': value, 'label': f'Answer {i}'} for i, value in enumerate(['stable', None, float('nan'), 'nan', 'None', 'stable', ''])]
        cleaned = e.clean_options(rows, original)
        self.assertEqual(cleaned[0]['id'], 'stable')
        self.assertEqual(len({o['id'] for o in cleaned}), len(rows))
        self.assertNotIn('nan', [o['id'] for o in cleaned])
        self.assertEqual(e.clean_options(cleaned, cleaned), cleaned)
        e.validate_options(json.loads(json.dumps(cleaned, allow_nan=False)))

    def survey(self, required=True):
        s = initial_state()
        q = question('rank_question', 'Most annoying tasks?', 'ranking', ['Alpha', 'Beta', 'Gamma'], required=required)
        s['survey']['draft'] = [q]
        s['cards'] = [ranking_card('survey')]
        e.publish(s)
        return s, q, [o['id'] for o in q['options']]

    def test_complete_rankings_required_and_optional_skips_preserved(self):
        s, q, ids = self.survey()
        for invalid in [[], ids[:2], [ids[0]] * 3, ids + ['unknown'], 'abc', None, [[], 'b', 'c']]:
            with self.subTest(invalid=invalid), self.assertRaises(e.RuleError):
                e.clean_answers([q], {q['id']: {'ranking': invalid}})
        cleaned = e.clean_answers([q], {q['id']: {'ranking': ids[::-1]}})
        self.assertEqual(cleaned[q['id']]['ranking'], ids[::-1])
        q['required'] = False
        self.assertEqual(e.clean_answers([q], {})[q['id']]['ranking'], [])
        e.validate_import({'format': 'hint-survey-draft-v1', 'questions': [q]})

    def test_average_rank_ties_and_top_cutoff_are_frozen(self):
        s, q, ids = self.survey(required=False)
        for i in range(6):
            order = ids if i % 2 else [ids[0], ids[2], ids[1]]
            e.submit_survey(s, s['survey']['active_version'], {q['id']: {'ranking': order}}, str(i))
        e.submit_survey(s, s['survey']['active_version'], {}, 'skip')
        result = e.aggregate(s, q['id'])
        self.assertEqual(result['denominator'], 6)
        self.assertEqual([r['average_rank'] for r in result['rows']], [1, 2.5, 2.5])
        e.freeze(s)
        c = s['game']['deck'][0]
        self.assertEqual(len(c['options']), 3)  # Includes both tied answers at top-2 cutoff.
        self.assertEqual(e.answer_points(c, ids), 60)
        self.assertEqual(e.answer_points(c, [ids[0], ids[2], ids[1]]), 60)
        self.assertEqual(e.answer_points(c, [ids[1], ids[0], ids[2]]), 20)
        snapshot = deepcopy(c['snapshot'])
        s['survey']['responses'].clear()
        self.assertEqual(c['snapshot'], snapshot)

    def test_ranking_vote_replacement_deadline_reveal_and_rejoin(self):
        s = initial_state()
        e.publish(s)
        e.save_cards(s, [ranking_card()])
        e.freeze(s)
        e.join_player(s, 'Player', 'token')
        e.game_action(s, 'start', now=100)
        e.game_action(s, 'open', now=100)
        for invalid in [['a', 'a', 'b'], ['a', 'b'], ['x', 'b', 'c'], 'a']:
            with self.assertRaises(e.RuleError):
                e.vote(s, 'token', 'rank', invalid, now=101)
        e.vote(s, 'token', 'rank', ['c', 'b', 'a'], now=101)
        e.vote(s, 'token', 'rank', ['a', 'b', 'c'], now=102)
        self.assertEqual(e.leaderboard(s)[0]['score'], 0)
        with self.assertRaises(e.RuleError):
            e.vote(s, 'token', 'rank', ['c', 'b', 'a'], now=130)
        e.game_action(s, 'close', now=131)
        e.game_action(s, 'reveal', now=132)
        self.assertEqual(e.leaderboard(s)[0]['score'], 20)
        e.join_player(s, 'Player', 'token')
        self.assertEqual(e.leaderboard(s)[0]['score'], 20)
        self.assertEqual(sum(r['count'] for r in e.vote_counts(s, s['game']['deck'][0])), 1)
        e.game_action(s, 'chat_fallback')
        self.assertEqual(e.leaderboard(s)[0]['score'], 20)

    def test_survey_ranking_low_response_and_invalid_mapping(self):
        s, q, ids = self.survey()
        for i in range(4):
            e.submit_survey(s, s['survey']['active_version'], {q['id']: {'ranking': ids}}, str(i))
        with self.assertRaisesRegex(e.RuleError, 'five'):
            e.freeze(s)
        self.assertFalse(s['frozen'])
        s['cards'][0]['survey_question_id'] = 'missing'
        with self.assertRaisesRegex(e.RuleError, 'Map ranking'):
            e.freeze(s)

    def test_choice_counts_can_feed_ranking(self):
        s = e.seed_rehearsal()
        c = ranking_card('survey')
        c.update(survey_question_id='tasks', top_n=3)
        s['cards'] = [c]
        e.freeze(s)
        c = s['game']['deck'][0]
        self.assertEqual(c['correct'][0], 'tasks_0')
        self.assertEqual(len(c['correct']), 5)  # Four equally popular runners-up.
        self.assertEqual(e.answer_points(c, c['correct']), 100)

    def test_manual_card_validation(self):
        s = initial_state()
        for bad in [['a', 'a', 'c'], ['a'], ['a', 'b', 'unknown']]:
            c = ranking_card()
            c['correct'] = bad
            with self.assertRaises(e.RuleError):
                e.save_cards(s, [c])


if __name__ == '__main__':
    unittest.main()
