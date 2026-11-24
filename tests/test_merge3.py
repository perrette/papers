"""Three-way merge (pull, push): the model and the dialogue"""
import unittest

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

    def test_equivalent_change_in_pool_only_is_offered(self):
        # a case or brace fix of one side is sent: the target is the base exactly
        m = three(pool={'title': 'Climate sensitivity revisited: {CO2}'},
                  lib={'title': 'Climate sensitivity revisited: CO2'}, base={'title': 'Climate sensitivity revisited: CO2'})
        self.assertEqual(self.status(m)['title'], (ADDED, CHANGED_OTHER))
        self.assertEqual(m.conflicts, [])
        self.assertEqual(m.result()['title'], 'Climate sensitivity revisited: {CO2}')
        m = three(pool={'journal': 'nat.'})
        self.assertEqual(m.result()['journal'], 'nat.')

    def test_equivalent_values_without_change_of_target(self):
        # the target changed (not the base exactly): equivalent values keep the target's
        m = three(lib={'journal': 'NAT.'}, pool={'journal': 'nat.'})
        self.assertTrue(m.is_exact())
        self.assertEqual(m.result()['journal'], 'NAT.')
        m = three(lib={'journal': 'nat.'})  # changed in the target only
        self.assertTrue(m.is_exact())
        self.assertEqual(m.result()['journal'], 'nat.')

    def test_two_way_equivalent_values_unchanged(self):
        # a merge without base (add): equivalent values are the same, the target's kept
        m = Merge([entry('a', **BASE), entry('b', **{**BASE, 'journal': 'nat.', 'title': '{Climate} sensitivity revisited'})])
        self.assertTrue(m.is_exact())
        self.assertEqual((m.result()['journal'], m.result()['title']), ('Nat.', 'Climate sensitivity revisited'))

    def test_removed_in_pool_is_offered(self):
        m = Merge([entry('a', **BASE), entry('b', **{k: v for k, v in BASE.items() if k != 'keywords'})],
                  base=entry('a', **BASE))
        self.assertEqual(self.status(m)['keywords'], (ADDED, CHANGED_OTHER))
        self.assertTrue(m.additions[0].removal)
        self.assertEqual(m.conflicts, [])
        self.assertNotIn('keywords', m.result())
        m.additions[0].decline()
        self.assertEqual(m.result()['keywords'], 'climate')

    def test_removed_in_pool_changed_in_library_is_a_conflict(self):
        m = Merge([entry('a', **{**BASE, 'keywords': 'climate, mine'}),
                   entry('b', **{k: v for k, v in BASE.items() if k != 'keywords'})],
                  base=entry('a', **BASE))
        self.assertEqual(self.status(m)['keywords'], (CONFLICT, CHANGED_BOTH))
        self.assertEqual(m.result()['keywords'], 'climate, mine')
        m.choose_all(1)
        self.assertNotIn('keywords', m.result())

    def test_removed_in_library_changed_in_pool_is_a_conflict(self):
        m = Merge([entry('a', **{k: v for k, v in BASE.items() if k != 'keywords'}),
                   entry('b', **{**BASE, 'keywords': 'climate, pool'})],
                  base=entry('a', **BASE))
        self.assertEqual(self.status(m)['keywords'], (CONFLICT, CHANGED_BOTH))
        self.assertNotIn('keywords', m.result())  # the library's removal, until decided
        m.choose_all(1)
        self.assertEqual(m.result()['keywords'], 'climate, pool')

    def test_removed_on_both_sides(self):
        no_keywords = {k: v for k, v in BASE.items() if k != 'keywords'}
        m = Merge([entry('a', **no_keywords), entry('b', **no_keywords)], base=entry('a', **BASE))
        self.assertTrue(m.is_exact())
        self.assertNotIn('keywords', m.result())

    def test_no_base_one_side_only_is_an_addition(self):
        # first exchange, one-time --pool: no removal information
        no_keywords = {k: v for k, v in BASE.items() if k != 'keywords'}
        m = Merge([entry('a', **no_keywords), entry('b', **BASE)], exchange=True)
        self.assertEqual([f.name for f in m.additions], ['keywords'])
        self.assertEqual(m.result()['keywords'], 'climate')
        m = Merge([entry('a', **BASE), entry('b', **no_keywords)], exchange=True)
        self.assertTrue(m.is_exact())
        self.assertEqual(m.result()['keywords'], 'climate')

    def test_duplicate_merge_without_base_unaffected(self):
        # add, check: a field missing in one entry is taken from the other
        no_keywords = {k: v for k, v in BASE.items() if k != 'keywords'}
        m = Merge([entry('a', **BASE), entry('b', **no_keywords)])
        self.assertTrue(m.is_exact())
        self.assertEqual(m.result()['keywords'], 'climate')
        m = Merge([entry('a', ids='x', **no_keywords), entry('b', ids='y', **BASE)], keys_to_ids=True)
        self.assertEqual(m.result()['keywords'], 'climate')
        self.assertEqual(m.result()['ids'], 'x, y, b')

    def test_exchange_ids_of_the_target_only_without_base(self):
        m = Merge([entry('a', ids='old', **BASE), entry('b', ids='poolold', **BASE)], exchange=True)
        self.assertEqual(m.result()['ids'], 'old')
        self.assertEqual(m.result().key, 'a')

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
        self.assertIn('origin = the entry as last exchanged (add, pull or push)', text)
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

    def removal(self):
        "keywords changed in the library, removed in the pool; year removed in the pool"
        pool = {k: v for k, v in BASE.items() if k not in ('keywords', 'year')}
        return Merge([entry('smith2020climate', **{**BASE, 'keywords': 'climate, mine'}), entry('Smith_2020', **pool)],
                     base=entry('smith2020climate', **BASE))

    def test_screen_shows_removals(self):
        text = Dialogue(self.removal(), 'pull', 'pool default').screen()
        lines = text.splitlines()
        year = next(line for line in lines if 'year' in line)
        self.assertRegex(year, r'^\+  year +   = \(removed\) +removed in pool$')
        keywords = [line for line in lines if 'keywords' in line or line.startswith('!  ' + ' ' * 8)]
        self.assertIn('removed in pool, changed in library', keywords[0])
        self.assertIn('{climate, mine}', keywords[0])
        self.assertTrue(any('2: (removed)' in line for line in lines))
        self.assertTrue(any('origin: {climate}' in line for line in lines))

    def test_field_question_removal(self):
        d = Dialogue(self.removal(), 'pull')
        keywords = next(f for f in d.merge.conflicts if f.name == 'keywords')
        question = d.field_question(keywords)
        self.assertIn('2  (removed)', question)
        self.assertEqual(d.parse_field(keywords, '2').kind, 'take')
        answers = iter(['f', '2', '2'])  # keywords: the pool's removal; year: removed
        decision = ask(self.removal(), 'pull', input=lambda prompt: next(answers), output=lambda text: None,
                       color=False)
        self.assertNotIn('keywords', decision.entry)
        self.assertNotIn('year', decision.entry)

    def test_edit_text_removal(self):
        self.assertIn('% keywords = (removed)   (2)', self.removal().edit_text())

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



class TestMergeFiles(unittest.TestCase):
    "the union of the file links: a checksum only between files of the same size"

    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir)

    def write(self, name, content):
        import os
        path = os.path.join(self.dir, name)
        with open(path, 'w') as f:
            f.write(content)
        return path

    def merge(self, *links):
        from unittest import mock
        import papers.merge
        entries = [entry(f'k{i}', **BASE, file=';'.join(f':{f}:pdf' for f in fs)) for i, fs in enumerate(links)]
        with mock.patch.object(papers.merge, 'checksum', wraps=papers.merge.checksum) as checksum:
            m = Merge(entries)
        return m.files, checksum.call_count

    def test_same_files_not_read(self):
        a, b = self.write('a.pdf', 'aaa'), self.write('b.pdf', 'bbbb')
        self.assertEqual(self.merge([a, b], [a, b]), ([a, b], 0))

    def test_sizes_differ_not_read(self):
        a, b = self.write('a.pdf', 'aaa'), self.write('b.pdf', 'bbbb')
        self.assertEqual(self.merge([a], [b]), ([a, b], 0))

    def test_same_content_once(self):
        a, copy, other = self.write('a.pdf', 'aaa'), self.write('copy.pdf', 'aaa'), self.write('c.pdf', 'ccc')
        files, calls = self.merge([a], [copy, other])
        self.assertEqual(files, [a, other])
        self.assertLessEqual(calls, 3)  # each file read once at most

if __name__ == '__main__':
    unittest.main()


class TestEqualValues(unittest.TestCase):
    "values equal as strings are equivalent without being normalized (long abstracts)"

    def test_not_normalized(self):
        from unittest.mock import patch
        import papers.merge
        abstract = 'A long abstract with {LaTeX} and $x^2$, ' * 20
        calls = []
        normalize = papers.merge.normalize_text
        with patch('papers.merge.normalize_text', lambda v: calls.append(v) or normalize(v)):
            m = three(lib={'abstract': abstract}, pool={'abstract': abstract}, base={'abstract': abstract})
            self.assertTrue(m.is_exact())
            self.assertTrue(papers.merge.equivalent('author', 'Smith, J.', 'Smith, J.'))
        self.assertNotIn(abstract, calls)
        self.assertNotIn('Smith, J.', calls)
