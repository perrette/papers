"""Three-way merge (pull, push): the model and the dialogue"""
import unittest
from unittest.mock import patch

from papers.duplicate import Verdict, SAME
from papers.entries import entry_from_dict
from papers.merge import (
    Merge, Dialogue, Resolver, DuplicateError, ask, CONFLICT, ADDED, SAME as UNCHANGED,
    CHANGED_TARGET, CHANGED_OTHER, CHANGED_BOTH,
)


def entry(key='key', type='article', **fields):
    return entry_from_dict(dict(fields, ID=key, ENTRYTYPE=type))


BASE = dict(author='Smith, John', title='Climate sensitivity revisited', year='2020',
            journal='Nat.', keywords='climate')


def three(lib=None, pool=None, base=None):
    "a pull: library entry, pool entry, origin copy (each a change of BASE)"
    return Merge([entry('smith2020climate', **{**BASE, **(lib or {})}),
                  entry('Smith_2020', **{**BASE, **(pool or {})})],
                 base=entry('smith2020climate', **{**BASE, **(base or {})}))


class TestThreeWay(unittest.TestCase):

    def status(self, m):
        return {f.name: (f.status, f.changed) for f in m.fields}

    def test_unchanged(self):
        m = three()
        self.assertTrue(m.is_exact())

    def test_changed_in_pool_only_is_offered(self):
        m = three(pool={'journal': 'Nature', 'volume': '10'})
        s = self.status(m)
        self.assertEqual(s['journal'], (ADDED, CHANGED_OTHER))
        self.assertEqual(s['volume'], (ADDED, CHANGED_OTHER))
        self.assertEqual(m.conflicts, [])
        r = m.result()
        self.assertEqual(r['journal'], 'Nature')
        self.assertEqual(r['volume'], '10')
        self.assertEqual(r.key, 'smith2020climate')

    def test_changed_in_library_only_is_kept(self):
        m = three(lib={'keywords': 'climate, mine'})
        self.assertEqual(self.status(m)['keywords'], (UNCHANGED, CHANGED_TARGET))
        self.assertTrue(m.is_exact())
        self.assertEqual(m.result()['keywords'], 'climate, mine')

    def test_changed_on_both_sides(self):
        m = three(lib={'journal': 'Nature'}, pool={'journal': 'Nature Climate Change'})
        self.assertEqual(self.status(m)['journal'], (CONFLICT, CHANGED_BOTH))
        self.assertEqual(m.result()['journal'], 'Nature')
        m.choose_all(1)
        self.assertEqual(m.result()['journal'], 'Nature Climate Change')

    def test_same_change_on_both_sides(self):
        m = three(lib={'journal': 'Nature'}, pool={'journal': 'nature'})
        self.assertTrue(m.is_exact())

    def test_removed_in_pool_is_kept(self):
        m = Merge([entry('a', **BASE), entry('b', **{k: v for k, v in BASE.items() if k != 'keywords'})],
                  base=entry('a', **BASE))
        self.assertTrue(m.is_exact())
        self.assertEqual(m.result()['keywords'], 'climate')

    def test_removed_in_library_stays_removed(self):
        m = Merge([entry('a', **{k: v for k, v in BASE.items() if k != 'keywords'}), entry('b', **BASE)],
                  base=entry('a', **BASE))
        self.assertTrue(m.is_exact())
        self.assertNotIn('keywords', m.result())

    def test_added_differently_on_both_sides(self):
        m = three(lib={'volume': '9'}, pool={'volume': '10'})
        self.assertEqual(self.status(m)['volume'], (CONFLICT, CHANGED_BOTH))

    def test_decline_addition(self):
        m = three(pool={'journal': 'Nature', 'volume': '10'})
        for f in m.additions:
            f.decline()
        r = m.result()
        self.assertEqual(r['journal'], 'Nat.')
        self.assertNotIn('volume', r)

    def test_ids_of_the_target_only(self):
        m = Merge([entry('a', ids='old', **BASE), entry('b', ids='poolold', **BASE)], base=entry('a', **BASE))
        self.assertEqual(m.result()['ids'], 'old')


class TestThreeWayDialogue(unittest.TestCase):

    def merge(self):
        return three(lib={'keywords': 'climate, mine', 'journal': 'Nature'},
                     pool={'journal': 'Nature Climate Change', 'volume': '10'})

    def test_screen(self):
        text = Dialogue(self.merge(), 'pull', 'pool default').screen()
        self.assertIn('smith2020climate  <-  pool default (Smith_2020)', text)
        self.assertIn('origin = the pool version at the last pull or push', text)
        self.assertIn('changed in library, kept', text)
        self.assertIn('added in pool', text)
        self.assertIn('changed on both sides', text)
        self.assertIn('origin: {Nat.}', text)
        self.assertIn('1 conflict, 1 change from the pool', text)
        self.assertIn('1 keep library values', text)
        self.assertIn('2 take pool values', text)
        self.assertIn('s skip (pull again later)', text)
        self.assertNotIn('not the same paper', text)

    def test_push_labels(self):
        m = Merge([entry('Smith_2020', **BASE, journal_='x'), entry('smith2020climate', **{**BASE, 'volume': '10'})],
                  base=entry('Smith_2020', **BASE))
        text = Dialogue(m, 'push', 'pool default').screen()
        self.assertIn('smith2020climate  ->  pool default (Smith_2020)', text)
        self.assertIn('added in library', text)

    def test_no_distinct_answer(self):
        d = Dialogue(self.merge(), 'pull')
        self.assertEqual(d.parse('n').kind, 'invalid')
        self.assertEqual(d.parse('f').kind, 'fields')
        # without conflict, f goes through the changes from the pool
        self.assertEqual(Dialogue(three(pool={'volume': '10'}), 'pull').parse('f').kind, 'fields')

    def test_field_by_field_includes_additions(self):
        answers = iter(['f', '1', '1'])  # journal: library; volume: decline
        output = []
        decision = ask(self.merge(), 'pull', input=lambda prompt: next(answers), output=output.append, color=False)
        self.assertEqual(decision.kind, 'merge')
        self.assertEqual(decision.entry['journal'], 'Nature')
        self.assertNotIn('volume', decision.entry)
        self.assertEqual(decision.entry['keywords'], 'climate, mine')

    def test_resolver(self):
        verdict = Verdict(SAME, 'pool default')
        with self.assertRaises(DuplicateError) as cm:
            Resolver('error').decide(self.merge(), 'pull', verdict)
        self.assertIn('smith2020climate: changed in the library and in pool default', str(cm.exception))
        self.assertIn('update', str(cm.exception))
        self.assertEqual(Resolver('keep').decide(self.merge(), 'pull', verdict).entry['journal'], 'Nature')
        self.assertEqual(Resolver('update').decide(self.merge(), 'pull', verdict).entry['journal'],
                         'Nature Climate Change')
        self.assertEqual(Resolver('skip').decide(self.merge(), 'pull', verdict).kind, 'skip')


if __name__ == '__main__':
    unittest.main()
