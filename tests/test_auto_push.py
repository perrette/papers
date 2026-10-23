"""The rules of the exchanges with the pool: the fields that each side
keeps (key, ids, file), removals, and the auto-push setting"""
import os
from pathlib import Path
from unittest.mock import patch

from papers.pools import ORIGIN_DIR
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
        # files mode link: the PDF stays where it is, the library and the pool entry link it there
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        out = self.out('add ../new.bib')
        self.assertIn('also added to pool ../pool', out)
        biblio, entries = self.bib('pool')
        pe = next(e for e in entries.values() if e['title'] == 'My own paper')
        self.assertEqual(biblio.get_files(pe), [self.path('mine.pdf')])
        self.assertEqual(self.files('mine2022'), [self.path('mine.pdf')])

    def test_add_new_entry_copy_mode(self):
        self.lib('config files copy')
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        self.out('add ../new.bib')
        biblio, entries = self.bib('pool')
        pe = next(e for e in entries.values() if e['title'] == 'My own paper')
        files = biblio.get_files(pe)
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith(self.path('pool', 'files')))
        self.assertEqual(self.files('mine2022'), files)
        self.assertTrue(Path(self.path('mine.pdf')).exists())

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


LINKS_NOTE = 'file links also updated in pool ../pool'


class TestNonLocalFileLinks(ExchangeTest):
    """a non-local library, auto-push off: the commands that change the file
    links of an entry update the links of the pool entry right away"""

    def setUp(self):
        super().setUp()
        self.lib('config files copy')
        self.lib('config local false -y')
        Path(self.path('si.pdf')).write_text('supplement')

    def pool_files(self, key='Smith_2020'):
        return self.files(key, where='pool')

    def unlinked_in_pool(self):
        "what `papers file clean` in the pool would remove"
        out = self.out('file clean --yes --dry-run', cwd='pool')
        return [line for line in out.splitlines() if line.startswith('DRYRUN: remove ')]

    def attach(self):
        out = self.out(f'file attach smith2020climate {self.path("si.pdf")}')
        si, = [f for f in self.files('smith2020climate') if f != self.pool_pdf]
        self.assertTrue(si.startswith(self.path('pool', 'files')), si)
        return out, si

    def test_attach(self):
        out, si = self.attach()
        self.assertIn(f'[{LINKS_NOTE}]', out)
        self.assertEqual(self.pool_files(), [self.pool_pdf, si])
        self.assertEqual(self.unlinked_in_pool(), [])
        # only the links: the other fields still follow auto-push
        self.lib('tag smith2020climate --add foo')
        self.assertFalse(self.has(self.smith('pool'), 'keywords'))
        self.assertIn('../pool: up to date', self.out('pull --check'))
        Path(self.path('pool', 'files', 'stray.pdf')).write_text('stray')
        self.assertEqual(len(self.unlinked_in_pool()), 1)

    def test_rename(self):
        Path(self.path('lib', 'x.pdf')).write_text('external')
        self.edit_lib('file = {', 'file = {:x.pdf:pdf;')
        out = self.out('file rename smith2020climate')
        self.assertIn(LINKS_NOTE, out)
        new = [f for f in self.files('smith2020climate') if f != self.pool_pdf]
        self.assertEqual(len(new), 1)
        self.assertTrue(new[0].startswith(self.path('pool', 'files')), new)
        self.assertEqual(sorted(self.pool_files()), sorted([self.pool_pdf] + new))
        self.assertEqual(self.unlinked_in_pool(), [])

    def test_detach(self):
        _, si = self.attach()
        out = self.out(f'file detach {si}')
        self.assertIn(f'smith2020climate: {LINKS_NOTE}', out)
        self.assertEqual(self.pool_files(), [self.pool_pdf])
        self.assertTrue(Path(si).exists())  # detach never deletes

    def test_rm(self):
        _, si = self.attach()
        out = self.out(f'file rm {si}')
        self.assertIn(f'smith2020climate: {LINKS_NOTE}', out)
        self.assertIn(f'delete {si}', out)
        self.assertEqual(self.files('smith2020climate'), [self.pool_pdf])
        self.assertEqual(self.pool_files(), [self.pool_pdf])
        self.assertFalse(Path(si).exists())  # no entry of the pool links to it any more

    def test_mv(self):
        _, si = self.attach()
        dest = self.path('pool', 'files', 'moved.pdf')
        out = self.out(f'file mv {si} {dest}')
        self.assertIn(f'smith2020climate: {LINKS_NOTE}', out)
        self.assertEqual(self.pool_files(), [self.pool_pdf, dest])
        self.assertEqual(self.unlinked_in_pool(), [])

    def test_check_fix(self):
        Path(self.path('downloads')).mkdir()
        Path(self.path('downloads', 'gone.pdf')).write_text('found again')
        self.edit_lib('file = {', 'file = {:../somewhere/gone.pdf:pdf;')
        out = self.out('file check --fix --search ../downloads')
        self.assertIn(f'smith2020climate: {LINKS_NOTE}', out)
        new = [f for f in self.files('smith2020climate') if f != self.pool_pdf]
        self.assertTrue(new and new[0].startswith(self.path('pool', 'files')), new)
        self.assertEqual(sorted(self.pool_files()), sorted([self.pool_pdf] + new))
        self.assertEqual(self.unlinked_in_pool(), [])

    def test_entry_not_shared_in_the_pool(self):
        # an entry of the library without origin record, that the pool has: only its links
        brown = '@article{brown2021,\n author = {Brown, Bob},\n doi = {10.1000/brown},\n title = {Ocean heat}\n}\n'
        Path(self.path('lib', 'papers.bib')).write_text(Path(self.path('lib', 'papers.bib')).read_text() + brown)
        out = self.out(f'file attach brown2021 {self.path("si.pdf")}')
        self.assertIn(LINKS_NOTE, out)
        self.assertEqual(self.pool_files('Brown_2021'), self.files('brown2021'))
        self.assertIsNone(self.origin().get(self.entry('brown2021')))
        self.assertEqual(self.unlinked_in_pool(), [])

    def test_entry_not_in_the_pool(self):
        # an entry that the pool does not have: added to the pool, as add does
        Path(self.path('lib', 'papers.bib')).write_text(
            Path(self.path('lib', 'papers.bib')).read_text() + NEW_BIB.replace(' file = {:mine.pdf:pdf},\n', ''))
        out = self.out(f'file attach mine2022 {self.path("si.pdf")}')
        self.assertIn('also added to pool ../pool', out)
        record = self.origin().get(self.entry('mine2022'))
        self.assertIsNotNone(record)
        self.assertEqual(self.pool_files(record.pool_key), self.files('mine2022'))
        self.assertEqual(self.unlinked_in_pool(), [])

    def test_local_library_is_unaffected(self):
        self.lib('config local true -y')
        pool_text = Path(self.path('pool', 'papers.bib')).read_text()
        out = self.out(f'file attach smith2020climate {self.path("si.pdf")}')
        self.assertNotIn('pool', out)
        self.assertEqual(Path(self.path('pool', 'papers.bib')).read_text(), pool_text)


BROWN_BIB = """@article{brown2021,
 author = {Brown, Bob},
 doi = {10.1000/brown},
 file = {:brown.pdf:pdf},
 title = {Ocean heat},
 year = {2021}
}
"""


class TestNonLocalSharedLinks(ExchangeTest):
    """a non-local library: the file links of a library entry are those of
    its pool entry, both ways; files mode link: a PDF added stays where it
    is, and the library and the pool entry link to it there"""

    def setUp(self):
        super().setUp()
        self.lib('config local false -y')
        self.lib('config files link')
        Path(self.path('si.pdf')).write_text('supplement')
        self.si = self.path('si.pdf')

    def pool_files(self, key='Smith_2020'):
        return self.files(key, where='pool')

    def pool_folder(self):
        return sorted(os.listdir(self.path('pool', 'files')))

    def test_status(self):
        self.assertIn('* files mode:         link (the files added stay where they are, the pool entry links '
                      'to them there)', self.out('status'))

    def test_add_link_mode_entry_new_to_the_pool(self):
        self.lib('config files copy')
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        self.out('add ../new.bib --link')
        record = self.origin().get(self.entry('mine2022'))
        self.assertEqual(self.files('mine2022'), [self.path('mine.pdf')])
        self.assertEqual(self.pool_files(record.pool_key), [self.path('mine.pdf')])
        self.assertEqual(self.pool_folder(), ['smith.pdf'])  # no copy

    def test_add_link_mode_entry_in_the_pool(self):
        # the pool has the paper (Brown_2021), without file: the pool entry links the PDF where it is
        Path(self.path('brown.bib')).write_text(BROWN_BIB)
        Path(self.path('brown.pdf')).write_text('brown')
        out = self.out('add ../brown.bib')
        self.assertIn('from pool ../pool', out)
        self.assertEqual(self.files('brown2021'), [self.path('brown.pdf')])
        self.assertEqual(self.pool_files('Brown_2021'), [self.path('brown.pdf')])
        self.assertEqual(self.pool_folder(), ['smith.pdf'])

    def test_attach_link_mode(self):
        out = self.out(f'file attach smith2020climate {self.si}')
        self.assertIn(LINKS_NOTE, out)
        self.assertEqual(self.files('smith2020climate'), [self.pool_pdf, self.si])
        self.assertEqual(self.pool_files(), [self.pool_pdf, self.si])
        self.assertEqual(self.pool_folder(), ['smith.pdf'])

    def test_attach_move_mode(self):
        self.lib('config files move')
        self.out(f'file attach smith2020climate {self.si}')
        new = [f for f in self.files('smith2020climate') if f != self.pool_pdf]
        self.assertEqual(len(new), 1)
        self.assertTrue(new[0].startswith(self.path('pool', 'files')), new)
        self.assertEqual(self.pool_files(), self.files('smith2020climate'))
        self.assertFalse(os.path.exists(self.si))

    def test_loaded_link_not_sent(self):
        # a link that the library had when loaded and the pool never had (from when it was local) stays
        # in the library only; the links added by a command are sent
        Path(self.path('lib', 'files')).mkdir(exist_ok=True)
        Path(self.path('lib', 'files', 'old.pdf')).write_text('old')
        self.edit_lib('file = {', 'file = {:files/old.pdf:pdf;')
        self.out(f'file attach smith2020climate {self.si}')
        self.assertEqual(self.pool_files(), [self.pool_pdf, self.si])
        self.assertIn(self.path('lib', 'files', 'old.pdf'), self.files('smith2020climate'))

    def test_pull_removes_the_links_the_pool_removed(self):
        Path(self.path('lib', 'files')).mkdir(exist_ok=True)
        Path(self.path('lib', 'files', 'old.pdf')).write_text('old')
        self.edit_lib('file = {', 'file = {:files/old.pdf:pdf;')
        self.out(f'file attach smith2020climate {self.si}')
        # the pool entry loses the link (e.g. `file detach` in another library of the pool)
        self.papers(f'file detach {self.si}', cwd=self.path('pool'))
        self.assertEqual(self.pool_files(), [self.pool_pdf])
        self.assertIn('smith2020climate: changed in pool ../pool: file', self.out('pull --check'))
        self.out('pull')
        # the link the pool entry never had stays
        self.assertEqual(sorted(self.files('smith2020climate')),
                         sorted([self.path('lib', 'files', 'old.pdf'), self.pool_pdf]))
        self.assertTrue(os.path.exists(self.si))
        self.assertNotIn('smith2020climate', self.out('pull --check'))

    def test_pull_adds_the_links_the_pool_added(self):
        self.lib('pull')  # records the links of the pool entry
        self.papers(f'file attach Smith_2020 {self.si} --link', cwd=self.path('pool'))
        self.out('pull')
        self.assertEqual(self.files('smith2020climate'), [self.pool_pdf, self.si])

    def test_sync_removes_the_links_the_pool_removed(self):
        self.out(f'file attach smith2020climate {self.si}')
        self.papers(f'file detach {self.si}', cwd=self.path('pool'))
        self.out('sync')
        self.assertEqual(self.files('smith2020climate'), [self.pool_pdf])
        self.assertEqual(self.pool_files(), [self.pool_pdf])

    def origin_file(self):
        origin, = [Path(self.path('lib', ORIGIN_DIR, name)) for name in os.listdir(self.path('lib', ORIGIN_DIR))]
        return origin

    def test_record_keeps_the_file_field(self):
        # the record of a non-local library keeps the pool entry's links in its file field
        self.out(f'file attach smith2020climate {self.si}')
        record = self.origin().get(self.entry('smith2020climate'))
        self.assertIsNotNone(record.files)
        self.assertNotIn('file', record.entry)  # not part of the base of the merge
        self.assertIn(' file = {', self.origin_file().read_text())
        self.assertNotIn('papers-files', self.origin_file().read_text())

    def test_pull_without_recorded_links_removes_nothing(self):
        # records written before the links were recorded (or by a local library): nothing is removed
        self.out(f'file attach smith2020climate {self.si}')
        origin = self.origin_file()
        text = origin.read_text()
        origin.write_text(''.join(line for line in text.splitlines(True) if not line.startswith(' file = ')))
        self.papers(f'file detach {self.si}', cwd=self.path('pool'))
        self.out('pull')
        self.assertIn(self.si, self.files('smith2020climate'))

    def test_record_of_development_builds(self):
        # papers-files (development builds of v3) is ignored: nothing is removed, and the next record drops it
        self.out(f'file attach smith2020climate {self.si}')
        origin = self.origin_file()
        text = origin.read_text()
        self.assertIn(' file = ', text)
        origin.write_text(text.replace(' file = ', ' papers-files = '))
        self.papers(f'file detach {self.si}', cwd=self.path('pool'))
        self.out('pull')
        self.assertIn(self.si, self.files('smith2020climate'))
        self.assertNotIn('papers-files', origin.read_text())
        self.assertIn(' file = ', origin.read_text())

    def test_local_pull_unchanged(self):
        self.out(f'file attach smith2020climate {self.si}')
        self.lib('config local true -y')
        self.lib('config files link')
        self.papers(f'file detach {self.si}', cwd=self.path('pool'))
        self.out('pull')
        self.assertIn(self.si, self.files('smith2020climate'))
        self.assertIsNone(self.origin().get(self.entry('smith2020climate')).files)  # a local library: no file field

    def test_file_rm_deletes_a_pool_file(self):
        self.lib('config files move')
        self.out(f'file attach smith2020climate {self.si}')
        si, = [f for f in self.files('smith2020climate') if f != self.pool_pdf]
        out = self.out(f'file rm {si} --dry-run')
        self.assertIn(f'DRYRUN: delete {si}', out)
        self.assertTrue(os.path.exists(si))
        self.assertEqual(self.pool_files(), [self.pool_pdf, si])
        out = self.out(f'file rm {si}')
        self.assertIn(f'delete {si}', out)
        self.assertFalse(os.path.exists(si))
        self.assertEqual(self.pool_files(), [self.pool_pdf])

    def test_file_rm_deletes_a_file_linked_in_place(self):
        self.out(f'file attach smith2020climate {self.si}')
        self.out(f'file rm {self.si}')
        self.assertFalse(os.path.exists(self.si))
        self.assertEqual(self.pool_files(), [self.pool_pdf])

    def test_file_rm_keeps_a_file_of_another_pool_entry(self):
        self.out(f'file attach smith2020climate {self.si}')
        self.papers(f'file attach Brown_2021 {self.si} --link', cwd=self.path('pool'))
        out = self.out(f'file rm {self.si}')
        self.assertIn(f'kept {self.si}: an entry of the pool links to it', out)
        self.assertTrue(os.path.exists(self.si))
        self.assertEqual(self.pool_files(), [self.pool_pdf])
        self.assertEqual(self.pool_files('Brown_2021'), [self.si])

    def test_rm_key_deletes_no_file_of_the_pool(self):
        self.out(f'file attach smith2020climate {self.si}')
        pool_text = Path(self.path('pool', 'papers.bib')).read_text()
        out = self.out('rm smith2020climate --delete-files')
        self.assertIn('it is a file of a pool', out)
        self.assertTrue(os.path.exists(self.si))
        self.assertTrue(os.path.exists(self.pool_pdf))
        self.assertEqual(Path(self.path('pool', 'papers.bib')).read_text(), pool_text)
