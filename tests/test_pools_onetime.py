"""The pool setting written as a list by earlier builds, exchanges with
another library than the pool (--pool PATH), the origin file of each
pool when the pool changes, and small output fixes"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import papers.config
import papers.extract
from papers.config import Config, MachineConfig, CONFIG_FILE_LOCAL
from papers.pools import origin_file_name
from papers.utils import PapersExit

from tests.common import paperscmd, pool_id
from tests.test_pools import PoolTest

OTHER_BIB = """@article{Brown_2021,
 author = {Brown, Bob},
 doi = {10.1000/brown},
 journal = {Ocean Sci.},
 title = {Ocean heat},
 year = {2021}
}

@article{Jones_2019,
 author = {Jones, Ann},
 doi = {10.1000/jones},
 title = {Ice sheets},
 year = {2019}
}
"""


class TestPoolSettingAsList(unittest.TestCase):
    "a pool setting written as a list: one path is that path, several are an error"

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.temp_dir.name, CONFIG_FILE_LOCAL)
        os.makedirs(os.path.dirname(self.file))
        self.machine = MachineConfig(os.path.join(self.temp_dir.name, 'machine.json'), {})

    def tearDown(self):
        self.temp_dir.cleanup()

    def load(self, value):
        json.dump({'bibtex': 'lib.bib', 'version': 3, 'pool': value}, open(self.file, 'w'))
        return Config.load(self.file, machine=self.machine)

    def test_one_path(self):
        config = self.load(['../shared'])
        self.assertEqual(config.pool, '../shared')
        config.save()
        self.assertEqual(json.load(open(self.file))['pool'], '../shared')

    def test_several_paths(self):
        with self.assertRaisesRegex(PapersExit, f'{self.file}: the pool setting lists several pools '
                                                r'\(../a, /b\); papers takes one pool'):
            self.load(['../a', '/b'])

    def test_global(self):
        # the global configuration has no pool: the setting of earlier builds is ignored
        file = self.machine.file
        for value in ['~/g', ['~/g'], ['~/g', '/other']]:
            json.dump({'pool': value}, open(file, 'w'))
            with self.assertLogs(papers.logger, level='WARNING') as cm:
                machine = MachineConfig.load(file)
            self.assertIn('the global pool setting is no longer used', cm.output[0])
            self.assertIsNone(machine.default)
            self.assertIsNone(machine.get('pool'))


class OneTimeTest(PoolTest):
    """pool/ (Smith_2020 with a file, Brown_2021), which lib/ exchanges
    with, and other/ (Brown_2021 with a journal, Jones_2019), another
    library"""

    def setUp(self):
        super().setUp()
        self.papers('init other --pool none')
        Path(self.path('other', 'papers.bib')).write_text(OTHER_BIB)

    def keys(self, where):
        return sorted(self.bib(where)[1])


class TestSetting(OneTimeTest):

    def test_config_takes_one_path(self):
        self.lib('config pool ../other')
        self.assertEqual(self.json('lib')['pool'], '../other')
        self.assertEqual(self.out('config pool'), '../other')
        self.lib('config pool none')
        self.assertEqual(self.json('lib')['pool'], 'none')
        with self.assertRaisesRegex(PapersExit, 'pool takes one value, got 2'):
            self.lib('config pool ../pool ../other')

    def test_init(self):
        out = self.papers('init third --pool ../pool', sp_cmd='check_output')
        self.assertIn('* files:   in the pool (shallow library)\n* pool:    ../pool\n', out)
        self.assertEqual(self.json('third')['pool'], '../pool')

    def test_status(self):
        self.papers('init third --pool ../pool')
        self.assertIn('* pool:   ../pool (not pulled from yet)\n', self.out('status', cwd='third'))


class TestOneTime(OneTimeTest):
    "exchanges with several libraries: each has its origin records"

    def test_records_for_each_library(self):
        self.lib('pull Smith_2020')
        record = self.origin().get(self.entry('Smith_2020'), '../pool')
        out = self.out('sync --pool ../other Jones_2019')
        self.assertIn('Added -> Jones_2019: Ice sheets (doi:10.1000/jones) [from pool ../other]', out)
        self.assertEqual(self.origin().get(self.entry('Jones_2019'), '../other').pool_key, 'Jones_2019')
        self.assertIsNone(self.origin().get(self.entry('Jones_2019'), '../pool'))
        self.lib('push --pool ../other Smith_2020')
        self.assertEqual(len(self.keys('other')), 3)
        origin = self.origin()
        self.assertEqual(len(origin), 3)  # Smith_2020 for ../pool and ../other, Jones_2019 for ../other
        self.assertEqual(origin.get(self.entry('Smith_2020'), '../pool').time, record.time)  # untouched
        self.assertEqual(sorted(os.listdir(self.path('lib', '.papers', 'origin'))),
                         sorted([origin_file_name('../pool'), origin_file_name('../other')]))
        # without a stored base, a field that differs is a conflict
        text = Path(self.path('other', 'papers.bib')).read_text()
        Path(self.path('other', 'papers.bib')).write_text(text.replace('{Ocean heat}', '{Ocean heat content}'))
        self.lib('pull Brown_2021')  # from the pool, without journal
        with self.assertRaisesRegex(PapersExit, 'conflict'):
            self.lib('pull --pool ../other Brown_2021 --on-duplicate error')
        self.lib('pull --pool ../other Brown_2021 --on-duplicate update')
        self.assertEqual(self.entry('Brown_2021')['title'], 'Ocean heat content')
        self.assertEqual(self.origin().get(self.entry('Brown_2021'), '../pool').entry['title'], 'Ocean heat')
        self.assertEqual(self.origin().get(self.entry('Brown_2021'), pool_id(self.path('other'), '../other')).entry['title'],
                         'Ocean heat content')
        # with a stored base: three-way merge, a field changed on one side only needs no decision
        text = Path(self.path('other', 'papers.bib')).read_text()
        Path(self.path('other', 'papers.bib')).write_text(text.replace('journal = {Ocean Sci.}',
                                                                       'journal = {Ocean Science}'))
        self.edit_lib('title = {Ocean heat content}', 'title = {Ocean heat content},\n volume = {7}')
        out = self.out('sync --pool ../other --on-duplicate error')  # the entries shared with ../other
        e = self.entry('Brown_2021')
        self.assertEqual((e['journal'], e['volume']), ('Ocean Science', '7'))
        self.assertEqual(self.entry('Brown_2021', 'other')['volume'], '7')
        self.assertRegex(out, r'Modified -> Brown_2021: .* \[in pool ../other\]')
        self.assertNotIn('unchanged', out)

    def test_without_key(self):
        self.lib('pull Smith_2020')
        self.assertIn('nothing to sync with pool ../other: no entries shared with it', self.out('sync --pool ../other'))
        self.assertEqual(self.keys('lib'), ['Smith_2020'])

    def test_pool_option_with_the_pool_of_the_library(self):
        self.lib('pull --pool ../pool Smith_2020')
        self.assertEqual(self.origin().get(self.entry('Smith_2020')).pool, '../pool')

    def test_config_pool_finds_the_records(self):
        # the records of the exchanges with --pool PATH serve when PATH becomes the pool, however it is written
        self.lib('pull --pool ../other Brown_2021')
        self.lib(f'config pool {self.path("other")}')  # absolute; the library has no PDF
        self.assertEqual(self.json('lib')['pool'], self.path('other'))
        text = Path(self.path('other', 'papers.bib')).read_text()
        Path(self.path('other', 'papers.bib')).write_text(text.replace('{Ocean Sci.}', '{Ocean Science}'))
        # the messages name the pool as its setting writes it; the records keep ../other
        self.assertIn(f'[from pool {self.path("other")}]', self.out('sync'))
        self.assertEqual(self.entry('Brown_2021')['journal'], 'Ocean Science')
        self.assertEqual(os.listdir(self.path('lib', '.papers', 'origin')), [origin_file_name('../other')])
        # and back: the library without pool exchanges with ../other as before
        self.lib('config pool none')
        self.assertIn('nothing to sync with pool ../other', self.out('sync --pool ../other'))

    def test_missing_pool(self):
        self.lib('pull Smith_2020')
        os.rename(self.path('pool'), self.path('elsewhere'))
        for cmd in ['sync', 'push', 'pull']:
            with self.assertRaisesRegex(PapersExit, r'pool \S+/pool does not exist'):
                self.lib(cmd)


class TestConfigPoolFiles(OneTimeTest):
    """config pool of a shallow library: the new pool must have its PDFs;
    `push --pool NEW` copies them there"""

    def setUp(self):
        super().setUp()
        self.lib('config pool ../pool -y')
        self.lib('pull Smith_2020')
        self.assertEqual(self.files('Smith_2020'), [self.pool_pdf])

    def test_pool_changes(self):
        with self.assertRaisesRegex(PapersExit, r'\(nothing was changed\): Smith_2020\n'
                                                r'Copy them to the pool first: `papers push --pool ../other Smith_2020`'):
            self.lib('config pool ../other -y')
        self.assertEqual(self.json('lib')['pool'], '../pool')
        self.lib('push --pool ../other Smith_2020')
        # the PDF is copied into the new pool, and the origin record is written for it
        other_files = os.listdir(self.path('other', 'files'))
        self.assertEqual(len(other_files), 1)
        self.assertEqual(sorted(os.listdir(self.path('lib', '.papers', 'origin'))),
                         sorted([origin_file_name('../pool'), origin_file_name('../other')]))
        self.assertEqual(self.files('Smith_2020'), [self.pool_pdf])  # the library is not changed
        out = self.out('config pool ../other -y')
        self.assertIn('pool = ../other (in ' + self.path('lib', CONFIG_FILE_LOCAL) + ')', out)
        self.assertEqual(self.files('Smith_2020'), [self.path('other', 'files', other_files[0])])
        self.assertEqual(len(self.bib('other')[1]), 3)
        self.assertTrue(os.path.exists(self.pool_pdf))  # the former pool keeps its file

    def test_push_all(self):
        self.lib('push --pool ../other --all')
        self.assertEqual(len(os.listdir(self.path('other', 'files'))), 1)
        self.lib('config pool ../other -y')
        self.assertTrue(self.files('Smith_2020')[0].startswith(self.path('other', 'files')))

    def test_no_pdf(self):
        # entries without PDF: the pool changes, nothing is copied or added
        self.lib('rm Smith_2020 --keep-files')
        Path(self.path('lib', 'papers.bib')).write_text(OTHER_BIB.split('@article{Jones')[0])
        self.lib('config pool ../other -y')
        self.assertEqual(self.json('lib')['pool'], '../other')
        self.assertEqual(len(self.bib('other')[1]), 2)

    def test_pool_none(self):
        self.lib('config pool none -y')
        self.assertTrue(self.files('Smith_2020')[0].startswith(self.path('lib', 'files')))


class TestSmallFixes(PoolTest):

    def test_config_pool_path_with_home(self):
        home_lib = os.path.join(os.environ['HOME'], 'homelib')
        try:
            paperscmd('init homelib', cwd=os.environ['HOME'])
            out = paperscmd('config pool none', cwd=home_lib, sp_cmd='check_output')
            self.assertEqual(out, 'pool = none (in ~/homelib/.papers/config.json)')
        finally:
            shutil.rmtree(home_lib, ignore_errors=True)

    def test_extract_errors(self):
        with self.assertRaisesRegex(PapersExit, r'^missing.pdf: no such file$'):
            self.papers('extract --doi-only missing.pdf')
        Path(self.path('nodoi.pdf')).write_text('not a pdf')
        with patch('papers.cli.fetch_cmds.extract_pdf_doi',
                   side_effect=papers.extract.DOIParsingError('no DOI found whose title appears in the text')):
            with self.assertRaisesRegex(PapersExit, r'nodoi.pdf: no DOI found whose title appears in the text'):
                self.papers('extract --doi-only nodoi.pdf')
        with self.assertRaisesRegex(PapersExit, '1 of 2 files failed'):
            with patch('papers.cli.fetch_cmds.extract_pdf_doi', return_value='10.1/x'):
                self.papers(f'extract --doi-only nodoi.pdf {self.path("missing.pdf")}')

