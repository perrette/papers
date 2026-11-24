"""Exchanges with another library than the pool: `add --pool PATH`, and
`pull --pool PATH` in a shallow library (the entries and files taken go
to its pool too); the library given must have no pool"""
import os
from pathlib import Path
from unittest.mock import patch

from papers.utils import PapersExit

from tests.test_pools import PoolTest, no_fetch

OTHER_BIB = """@article{Jones_2019,
 author = {Jones, Ann},
 doi = {10.1000/jones},
 file = {:files/jones.pdf:pdf},
 title = {Ice sheets},
 year = {2019}
}
"""


class OtherTest(PoolTest):
    """pool/ and lib/ (see PoolTest), and other/, a library with Jones_2019
    and its PDF"""

    def setUp(self):
        super().setUp()
        self.papers('init other')
        Path(self.path('other', 'papers.bib')).write_text(OTHER_BIB)
        self.other_pdf = self.path('other', 'files', 'jones.pdf')
        Path(self.other_pdf).write_text('pdf of jones')
        self.other_text = Path(self.path('other', 'papers.bib')).read_text()

    def add_jones(self, where='lib', options=''):
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            return self.papers(f'add --pool ../other --doi 10.1000/jones {options}', cwd=self.path(where),
                               sp_cmd='check_output')

    def assertOtherUnchanged(self):
        self.assertEqual(Path(self.path('other', 'papers.bib')).read_text(), self.other_text)
        self.assertEqual(os.listdir(self.path('other', 'files')), ['jones.pdf'])


class TestAddPool(OtherTest):

    def test_self_contained(self):
        self.lib('config files move')
        out = self.add_jones()
        self.assertRegex(out, r'Added -> jones2019: .* \[from pool ../other\]')  # the library's key template
        files = self.files('jones2019')
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith(self.path('lib', 'files')), files)  # copied, never moved
        self.assertTrue(os.path.exists(self.other_pdf))
        record = self.origin().get(self.entry('jones2019'), '../other')
        self.assertEqual(record.pool_key, 'Jones_2019')
        self.assertIsNone(record.files)  # the file links of a self-contained library are its own
        self.assertOtherUnchanged()  # nothing is sent to PATH
        self.assertEqual(len(self.bib('pool')[1]), 2)
        # the record serves the next exchange with ../other
        Path(self.path('other', 'papers.bib')).write_text(self.other_text.replace('year = {2019}',
                                                                                   'volume = {2},\n year = {2019}'))
        self.lib('pull --pool ../other')
        self.assertEqual(self.entry('jones2019')['volume'], '2')

    def test_new_entry_is_not_sent(self):
        Path(self.path('new.bib')).write_text('@article{mine2022,\n author = {Mine, Me},\n title = {Mine},\n'
                                              ' year = {2022}\n}\n')
        self.papers('add ../new.bib --pool ../other', cwd=self.path('lib'))
        self.assertIn('mine2022', self.bib()[1])
        self.assertOtherUnchanged()
        self.assertEqual(len(self.origin()), 0)

    def test_shallow(self):
        # a shallow library: the entry taken from ../other goes to its pool too, with a copy of the PDF
        self.papers('init shallow --pool pool')
        self.papers('config files copy', cwd=self.path('shallow'))
        out = self.add_jones('shallow')
        self.assertRegex(out, r'Added -> jones2019: .* \[from pool ../other; also added to pool ../pool\]')
        files = self.files('jones2019', 'shallow')
        self.assertTrue(files[0].startswith(self.path('pool', 'files')), files)
        pool_biblio, pool = self.bib('pool')
        pe, = [e for e in pool.values() if e['doi'] == '10.1000/jones']
        self.assertEqual(pool_biblio.get_files(pe), files)  # the links are the pool entry's
        self.assertFalse(os.path.exists(self.path('shallow', 'files')))
        self.assertOtherUnchanged()

    def test_errors(self):
        with self.assertRaisesRegex(PapersExit, '--pool PATH and --no-pool exclude each other'):
            self.add_jones(options='--no-pool')
        self.papers('init shallow --pool pool')
        with self.assertRaisesRegex(PapersExit, r'\S+/shallow has a pool itself \(../pool\): give a library '
                                                'without pool'):
            self.papers('add --pool ../shallow --doi 10.1000/jones', cwd=self.path('lib'))
        with self.assertRaisesRegex(PapersExit, 'does not exist'):
            self.papers('add --pool ../missing --doi 10.1000/jones', cwd=self.path('lib'))
        self.assertEqual(self.bib()[1], {})

    def test_help(self):
        out = self.papers('add --help', sp_cmd='check_output', reliable=True)
        self.assertIn('papers -C PATH add', ' '.join(out.split()))


class TestShallowWithOther(OtherTest):
    "a shallow library exchanges with another library than its pool"

    def setUp(self):
        super().setUp()
        self.papers('init shallow --pool pool')
        self.papers('config files copy', cwd=self.path('shallow'))

    def shallow(self, cmd):
        return self.papers(cmd, cwd=self.path('shallow'), sp_cmd='check_output')

    def test_pull(self):
        out = self.shallow('pull --pool ../other Jones_2019')
        self.assertIn('Added -> Jones_2019: Ice sheets (doi:10.1000/jones, file:1) [from pool ../other]', out)
        self.assertIn('Jones_2019: also added to pool ../pool', out)
        files = self.files('Jones_2019', 'shallow')
        self.assertTrue(files[0].startswith(self.path('pool', 'files')), files)
        pool_biblio, pool = self.bib('pool')
        self.pool_key, = [k for k, e in pool.items() if e['doi'] == '10.1000/jones']  # the pool's key template
        self.assertEqual(pool_biblio.get_files(pool[self.pool_key]), files)
        self.assertOtherUnchanged()
        origin = self.origin_of('shallow')
        self.assertIsNotNone(origin.get(self.entry('Jones_2019', 'shallow'), '../other'))
        self.assertIsNotNone(origin.get(self.entry('Jones_2019', 'shallow'), '../pool'))
        # later: the changes of ../other come with pull --pool ../other, and go to the pool with push
        Path(self.path('other', 'papers.bib')).write_text(self.other_text.replace('year = {2019}',
                                                                                   'volume = {2},\n year = {2019}'))
        self.shallow('pull --pool ../other')
        self.assertEqual(self.entry('Jones_2019', 'shallow')['volume'], '2')
        self.assertNotIn('volume', self.entry(self.pool_key, 'pool'))
        self.shallow('push')
        self.assertEqual(self.entry(self.pool_key, 'pool')['volume'], '2')

    def test_push(self):
        self.shallow('pull Smith_2020')
        self.shallow('push --pool ../other Smith_2020')
        biblio, entries = self.bib('other')
        pe, = [e for e in entries.values() if 'doi' in e.fields_dict and e['doi'].lower() == '10.1000/abc123']
        files = biblio.get_files(pe)
        self.assertTrue(files[0].startswith(self.path('other', 'files')), files)  # a copy
        self.assertEqual(self.files('Smith_2020', 'shallow'), [self.pool_pdf])  # unchanged

    def origin_of(self, where):
        from papers.pools import Origin, ORIGIN_DIR
        return Origin.load(self.path(where, ORIGIN_DIR))

    def test_other_must_have_no_pool(self):
        self.papers('init third --pool other')
        for cmd in ['pull --all', 'push --all', 'sync --all', 'pull --check']:
            with self.assertRaisesRegex(PapersExit, 'has a pool itself'):
                self.shallow(cmd + ' --pool ../third')
