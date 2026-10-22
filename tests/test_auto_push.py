"""The rules of the exchanges with the pool: the fields that each side
keeps (key, ids, file), removals, and the auto-push setting"""
from pathlib import Path
from unittest.mock import patch

from tests.test_pools import PoolTest, NEW_BIB, SMITH_BIB, no_fetch

NOTE = '[not pushed: changed in the pool too; papers sync decides]'


class ExchangeTest(PoolTest):
    "the library shares smith2020climate with the pool (Smith_2020)"

    def setUp(self):
        super().setUp()
        self.take_smith()

    def smith(self, where='lib'):
        return self.entry('smith2020climate' if where == 'lib' else 'Smith_2020', where)

    def has(self, e, field):
        return field in e.fields_dict


class TestOwnFields(ExchangeTest):
    "key, ids and file belong to each side"

    def test_push_keeps_the_library_ids(self):
        self.edit_lib('journal = {Nat.}', 'journal = {Nature},\n ids = {oldkey}')
        self.assertIn('Modified', self.out('push'))
        pe = self.smith('pool')
        self.assertEqual(pe['journal'], 'Nature')
        self.assertFalse(self.has(pe, 'ids'))
        self.assertEqual(sorted(self.bib('pool')[1]), ['Brown_2021', 'Smith_2020'])  # the pool key

    def test_pull_keeps_the_pool_ids(self):
        self.edit_pool('journal = {Nat.}', 'journal = {Nature},\n ids = {poolold}')
        self.assertIn('Modified', self.out('pull'))
        e = self.smith()
        self.assertEqual(e['journal'], 'Nature')
        self.assertFalse(self.has(e, 'ids'))
        self.assertEqual(list(self.bib()[1]), ['smith2020climate'])  # the library key

    def test_pull_keeps_the_library_ids(self):
        self.edit_lib('journal = {Nat.}', 'journal = {Nat.},\n ids = {oldkey}')
        self.edit_pool('journal = {Nat.}', 'journal = {Nature},\n ids = {poolold}')
        self.lib('pull')
        self.assertEqual(self.smith()['ids'], 'oldkey')
        self.lib('push')
        self.assertEqual(self.smith('pool')['ids'], 'poolold')

    def test_first_exchange_does_not_merge_ids(self):
        # no origin record: a one-time exchange with another library
        self.papers('init other --no-git --pool none')
        Path(self.path('other', 'papers.bib')).write_text(
            POOL_SMITH.replace('journal = {Nat.}', 'journal = {Nat.},\n ids = {otherold}'))
        self.edit_lib('journal = {Nat.}', 'journal = {Nat.},\n ids = {oldkey}')
        self.lib('push --pool ../other smith2020climate --on-duplicate update')
        other = self.entry('Smith_2020', 'other')
        self.assertEqual(other['ids'], 'otherold')
        self.lib('pull --pool ../other smith2020climate --on-duplicate update')
        self.assertEqual(self.smith()['ids'], 'oldkey')

    def test_add_from_the_pool_without_its_ids(self):
        self.edit_pool('doi = {10.1000/brown}', 'doi = {10.1000/brown},\n ids = {poolold}')
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            self.lib('add --doi 10.1000/brown')
        e, = [e for e in self.bib()[1].values() if e['title'] == 'Ocean heat']
        self.assertFalse(self.has(e, 'ids'))


POOL_SMITH = """@article{Smith_2020,
 author = {Smith, John and Doe, Jane},
 doi = {10.1000/abc123},
 journal = {Nat.},
 title = {Climate sensitivity revisited},
 year = {2020}
}
"""


class TestRemovals(ExchangeTest):

    def test_removed_in_the_pool(self):
        self.edit_pool(' journal = {Nat.},\n', '')
        self.assertIn('Modified', self.out('pull'))
        self.assertFalse(self.has(self.smith(), 'journal'))
        self.assertNotIn('Modified', self.out('push'))
        self.assertFalse(self.has(self.smith('pool'), 'journal'))

    def test_removed_in_the_library(self):
        self.edit_lib(' journal = {Nat.},\n', '')
        self.assertIn('Modified', self.out('push'))
        self.assertFalse(self.has(self.smith('pool'), 'journal'))
        self.assertNotIn('Modified', self.out('pull'))
        self.assertFalse(self.has(self.smith(), 'journal'))

    def test_removed_on_both_sides(self):
        self.edit_lib(' journal = {Nat.},\n', '')
        self.edit_pool(' journal = {Nat.},\n', '')
        self.assertIn('nothing to sync', self.out('sync'))

    def test_removed_on_one_side_changed_on_the_other(self):
        self.edit_lib('journal = {Nat.}', 'journal = {Nature}')
        self.edit_pool(' journal = {Nat.},\n', '')
        out = self.out('pull --on-duplicate skip')
        self.assertIn('Conflict', out)
        self.assertEqual(self.smith()['journal'], 'Nature')
        self.lib('pull --on-duplicate update')  # the pool's removal
        self.assertFalse(self.has(self.smith(), 'journal'))

    def test_pull_check_lists_a_removal(self):
        self.edit_pool(' journal = {Nat.},\n', '')
        self.assertIn('smith2020climate: changed in pool ../pool: journal', self.out('pull --check'))


class TestAutoPush(ExchangeTest):

    def setUp(self):
        super().setUp()
        self.lib('config auto-push true')

    def test_tag(self):
        out = self.out('tag smith2020climate --add foo')
        self.assertIn('[also modified in pool ../pool]', out)
        self.assertEqual(self.smith('pool')['keywords'], 'foo')
        self.lib('tag --rename foo bar')
        self.assertEqual(self.smith('pool')['keywords'], 'bar')

    def test_list_add_tag(self):
        self.lib('list -k smith2020climate --add-tag foo')
        self.assertEqual(self.smith('pool')['keywords'], 'foo')

    def test_edit(self):
        def edit(entries):
            entries[0]['note'] = 'edited'
            return entries
        with patch('papers.cli.common.edit_entries', side_effect=edit):
            self.lib('edit smith2020climate')
        self.assertEqual(self.smith('pool')['note'], 'edited')

    def test_check_duplicates(self):
        Path(self.path('lib', 'papers.bib')).write_text(Path(self.path('lib', 'papers.bib')).read_text()
            + '\n@article{zdup,\n doi = {10.1000/abc123},\n note = {from the duplicate}\n}\n')
        self.lib('check --duplicates --on-duplicate keep')
        self.assertEqual(list(self.bib()[1]), ['smith2020climate'])
        self.assertEqual(self.smith('pool')['note'], 'from the duplicate')

    def test_add_new_entry(self):
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        out = self.out('add ../new.bib')
        self.assertIn('also added to pool ../pool', out)
        self.assertEqual(len(self.bib('pool')[1]), 3)

    def test_file_attach_and_detach(self):
        Path(self.path('si.pdf')).write_text('supplement')
        self.lib(f'file attach smith2020climate {self.path("si.pdf")}')
        biblio, entries = self.bib('pool')
        self.assertEqual(len(biblio.get_files(entries['Smith_2020'])), 2)
        # detach: the pool keeps its links (file is not merged)
        self.lib('file detach --key smith2020climate')
        self.assertEqual(self.files('smith2020climate'), [])
        biblio, entries = self.bib('pool')
        self.assertEqual(len(biblio.get_files(entries['Smith_2020'])), 2)

    def test_only_the_entries_changed(self):
        self.edit_pool('title = {Ocean heat}', 'title = {Ocean heat},\n note = {pool}')
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            self.lib('add --doi 10.1000/brown')
        pool_text = Path(self.path('pool', 'papers.bib')).read_text()
        self.lib('tag smith2020climate --add foo')
        self.assertEqual(self.entry('Brown_2021', 'pool')['note'], 'pool')
        self.assertEqual(Path(self.path('pool', 'papers.bib')).read_text(),
                         pool_text.replace('journal = {Nat.},', 'journal = {Nat.},\n keywords = {foo},'))

    def test_entry_not_shared_is_not_pushed(self):
        Path(self.path('lib', 'papers.bib')).write_text(
            Path(self.path('lib', 'papers.bib')).read_text() + '\n' + NEW_BIB)
        self.lib('tag mine2022 --add foo')
        self.assertNotIn('mine2022', self.bib('pool')[1])

    def test_rm_is_not_pushed(self):
        self.lib('rm smith2020climate --keep-files')
        self.assertIn('Smith_2020', self.bib('pool')[1])

    def test_conflict_does_not_stop_the_command(self):
        self.edit_pool('journal = {Nat.}', 'journal = {Nat.},\n keywords = {pool}')
        out = self.out('tag smith2020climate --add foo')
        self.assertIn('Modified', out)
        self.assertIn(NOTE, out)
        self.assertEqual(self.smith()['keywords'], 'foo')  # saved
        self.assertEqual(self.smith('pool')['keywords'], 'pool')  # not pushed
        out = self.out('tag --rename foo bar')
        self.assertIn(f'smith2020climate: {NOTE[1:-1]}', out)


class TestAutoPushOff(ExchangeTest):

    def test_nothing_pushed(self):
        pool_text = Path(self.path('pool', 'papers.bib')).read_text()
        self.lib('tag smith2020climate --add foo')
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        self.lib('add ../new.bib')
        Path(self.path('si.pdf')).write_text('supplement')
        self.lib(f'file attach smith2020climate {self.path("si.pdf")}')
        self.assertEqual(Path(self.path('pool', 'papers.bib')).read_text(), pool_text)
        self.assertIn('Modified', self.out('push'))
        self.assertEqual(self.smith('pool')['keywords'], 'foo')


class TestNonLocalAutoPush(ExchangeTest):
    "a non-local library: add puts the new entries in the pool, the changes follow auto-push"

    def setUp(self):
        super().setUp()
        self.lib('config local false -y')

    def test_status(self):
        self.assertIn('* auto-push:          false (add adds the new entries to the pool; push or sync sends '
                      'the changes)', self.out('status'))

    def test_add_new_entry_goes_to_the_pool(self):
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        out = self.out('add ../new.bib')
        self.assertIn('also added to pool ../pool', out)
        biblio, entries = self.bib('pool')
        pe = next(e for e in entries.values() if e['title'] == 'My own paper')
        self.assertTrue(biblio.get_files(pe)[0].startswith(self.path('pool', 'files')))

    def test_changes_not_pushed(self):
        self.lib('tag smith2020climate --add foo')
        self.assertFalse(self.has(self.smith('pool'), 'keywords'))
        # add of an entry that the library has: a change
        Path(self.path('smith.bib')).write_text(SMITH_BIB.replace('year = {2020}', 'year = {2020},\n note = {x}'))
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            self.lib('add ../smith.bib --on-duplicate update')
        self.assertEqual(self.smith()['note'], 'x')
        self.assertFalse(self.has(self.smith('pool'), 'note'))

    def test_changes_pushed_with_auto_push(self):
        self.lib('config auto-push true')
        self.lib('tag smith2020climate --add foo')
        self.assertEqual(self.smith('pool')['keywords'], 'foo')
