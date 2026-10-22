"""Several pools: the pool setting as a list (configuration files, init,
config), lookup in order, writes to the first pool, pull and sync with
several pools, missing pools, and the files moved by `config pool`"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import papers.config
import papers.extract
from papers.config import Config, MachineConfig, CONFIG_FILE_LOCAL, pool_list, pool_to_json
from papers.pools import Pools, GLOBAL_POOL_ID
from papers.utils import PapersExit

from tests.common import paperscmd
from tests.test_pools import PoolTest, no_fetch

POOL2_BIB = """@article{Brown_2021,
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


class TestPoolSetting(unittest.TestCase):
    "the pool setting in the configuration files"

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.temp_dir.name, CONFIG_FILE_LOCAL)
        self.machine = MachineConfig(os.path.join(self.temp_dir.name, 'machine.json'), {})

    def tearDown(self):
        self.temp_dir.cleanup()

    def roundtrip(self, value):
        js = {'bibtex': 'lib.bib', 'version': 3, 'local': True}
        if value is not None:
            js['pool'] = value
        json.dump(js, open(self.file, 'w'))
        config = Config.load(self.file, machine=self.machine)
        config.save()
        return config, json.load(open(self.file)).get('pool')

    def test_values(self):
        self.assertEqual((pool_list('none'), pool_list('../a'), pool_list(['../a', '/b']), pool_list(None)),
                         ([], ['../a'], ['../a', '/b'], None))
        self.assertEqual((pool_to_json([]), pool_to_json(['../a']), pool_to_json(['../a', '/b'])),
                         ('none', '../a', ['../a', '/b']))

    def test_single_path_stays_a_string(self):
        config, stored = self.roundtrip('../shared')
        self.assertEqual(config.pool, ['../shared'])
        self.assertEqual(stored, '../shared')

    def test_list_stays_a_list(self):
        config, stored = self.roundtrip(['../a', '/b'])
        self.assertEqual(config.pool, ['../a', '/b'])
        self.assertEqual(config.pool_paths(), [os.path.abspath(os.path.join(self.temp_dir.name, '../a')), '/b'])
        self.assertEqual(config.pool_labels(), ['../a', '/b'])
        self.assertEqual(stored, ['../a', '/b'])

    def test_none(self):
        config, stored = self.roundtrip('none')
        self.assertEqual(config.pool, [])
        self.assertFalse(config.has_pool())
        self.assertEqual(stored, 'none')
        config, stored = self.roundtrip([])
        self.assertEqual(stored, 'none')

    def test_inherited_global_pool_is_not_stored(self):
        self.machine.set('pool', ['~/g', '/other'])
        self.assertEqual(self.machine.data['pool'], ['~/g', '/other'])
        config, stored = self.roundtrip(None)
        self.assertIsNone(stored)
        self.assertTrue(config.uses_global_pool)
        self.assertEqual(config.pool, ['~/g', '/other'])
        self.assertEqual(config.pool_labels(), [papers.config.short_home(os.path.expanduser('~/g')), '/other'])
        self.assertEqual(self.machine.pool_path(), os.path.expanduser('~/g'))
        self.machine.set('pool', ['/one'])
        self.assertEqual(self.machine.data['pool'], '/one')
        self.machine.set('pool', [])
        self.assertEqual(self.machine.data['pool'], 'none')
        self.assertIsNone(self.machine.pool_path())

    def test_global_pool_id_in_a_list(self):
        os.makedirs(os.path.join(self.temp_dir.name, 'g'))
        self.machine.set('pool', os.path.join(self.temp_dir.name, 'g'))
        config, _ = self.roundtrip(['./other', os.path.join(self.temp_dir.name, 'g')])
        pools = Pools(config)
        self.assertEqual([pools._id(p) for p in config.pool_paths()], ['./other', GLOBAL_POOL_ID])

    def test_library_in_its_own_list(self):
        config, _ = self.roundtrip(['.', '../a'])
        self.assertEqual(config.pool_labels(), ['../a'])
        self.assertTrue(config.is_pool_library())
        self.assertTrue(config.has_pool())


class MultiPoolTest(PoolTest):
    """pool/ (Smith_2020 with a file, Brown_2021), pool2/ (Brown_2021 with
    a journal, Jones_2019), and lib/ that uses both, in this order"""

    def setUp(self):
        super().setUp()
        self.papers('init pool2 --no-git --pool none')
        Path(self.path('pool2', 'papers.bib')).write_text(POOL2_BIB)
        self.lib('config pool ../pool ../pool2')

    def keys(self, where):
        return sorted(self.bib(where)[1])


class TestCommands(MultiPoolTest):

    def test_config(self):
        self.assertEqual(self.json('lib')['pool'], ['../pool', '../pool2'])
        self.assertEqual(self.out('config pool'), '../pool ../pool2')
        self.lib('config pool ../pool2')
        self.assertEqual(self.json('lib')['pool'], '../pool2')
        self.lib('config pool none')
        self.assertEqual(self.json('lib')['pool'], 'none')
        with self.assertRaisesRegex(PapersExit, 'none cannot be given with paths'):
            self.lib('config pool none ../pool')

    def test_init(self):
        out = self.papers('init other --no-git --local --pool ../pool --pool ../pool2', sp_cmd='check_output')
        self.assertEqual(self.json('other')['pool'], ['../pool', '../pool2'])
        self.assertIn('* pools:   ../pool, ../pool2 (looked up in this order; new entries go to the first; '
                      'the PDFs stay in this library)', out)
        self.papers('config --global local false')
        out = self.papers('init third --no-git --pool ../pool --pool ../pool2', sp_cmd='check_output')
        self.assertIn('* files:   in the pool ../pool\n', out)
        self.assertIn('* pools:   ../pool, ../pool2 (looked up in this order; new entries go to the first)', out)
        self.papers('init fourth --no-git --pool none')
        self.assertEqual(self.json('fourth')['pool'], 'none')

    def test_status(self):
        out = self.out('status')
        self.assertIn('* pools:              ../pool (new entries go here, not pulled from yet)\n'
                      '                      ../pool2 (not pulled from yet)', out)


class TestLookup(MultiPoolTest):

    def add(self, cmd):
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            return self.out(cmd)

    def test_first_match_wins(self):
        out = self.add('add --doi 10.1000/brown')
        self.assertIn('[from pool ../pool]', out)
        self.assertNotIn('journal', self.entry('brown2021'))
        self.assertEqual(self.origin().get(self.entry('brown2021')).pool, '../pool')

    def test_found_in_a_later_pool(self):
        out = self.add('add --doi 10.1000/jones')
        self.assertIn('[from pool ../pool2]', out)
        self.assertEqual(self.origin().get(self.entry('jones2019')).pool, '../pool2')

    def test_key(self):
        self.add('add --key Jones_2019')
        self.assertEqual(self.keys('lib'), ['Jones_2019'])

    def test_pull_key(self):
        self.lib('pull Jones_2019 Smith_2020')
        self.assertEqual(self.keys('lib'), ['Jones_2019', 'Smith_2020'])
        self.assertEqual(self.origin().get(self.entry('Jones_2019')).pool, '../pool2')
        with self.assertRaisesRegex(PapersExit, 'nope: no entry found'):
            self.lib('pull nope')

    def test_auto_push_writes_to_the_first_pool(self):
        self.lib('config auto-push true')
        self.add('add --doi 10.1000/jones')
        self.assertEqual(self.keys('pool'), ['Brown_2021', 'Smith_2020', 'jones2019'])  # the pool's key template
        self.assertEqual(self.keys('pool2'), ['Brown_2021', 'Jones_2019'])


class TestPullSync(MultiPoolTest):

    def test_pull_all(self):
        out = self.out('pull --all')
        self.assertIn('pull from pool ../pool and pool ../pool2: 3 added', out)
        self.assertEqual(self.keys('lib'), ['Brown_2021', 'Jones_2019', 'Smith_2020'])
        # Brown_2021 is in both: taken from the first pool, once
        self.assertNotIn('journal', self.entry('Brown_2021'))
        origin = self.origin()
        self.assertEqual([origin.get(self.entry(k)).pool for k in ['Brown_2021', 'Jones_2019', 'Smith_2020']],
                         ['../pool', '../pool2', '../pool'])
        self.assertIn('pull from pool ../pool and pool ../pool2: 3 unchanged', self.out('pull'))

    def test_each_entry_from_its_pool(self):
        self.lib('pull Jones_2019 Smith_2020')
        self.edit_pool('year = {2020}', 'volume = {1},\n year = {2020}')
        text = Path(self.path('pool2', 'papers.bib')).read_text()
        Path(self.path('pool2', 'papers.bib')).write_text(text.replace('year = {2019}', 'volume = {2},\n year = {2019}'))
        self.lib('pull')
        self.assertEqual((self.entry('Smith_2020')['volume'], self.entry('Jones_2019')['volume']), ('1', '2'))

    def test_sync_pushes_to_the_first(self):
        self.lib('pull Jones_2019')
        text = Path(self.path('lib', 'papers.bib')).read_text()
        Path(self.path('lib', 'papers.bib')).write_text(text.replace('year = {2019}', 'note = {mine},\n year = {2019}'))
        out = self.out('sync')
        # shared with pool2 only: pulled from it, and nothing to push to pool
        self.assertIn('nothing to sync with pool ../pool and pool ../pool2 (1 entry unchanged)', out)
        self.assertEqual(self.keys('pool'), ['Brown_2021', 'Smith_2020'])
        self.assertNotIn('note', self.entry('Jones_2019', 'pool2'))
        self.lib('push Jones_2019')
        self.assertIn('jones2019', self.keys('pool'))
        self.assertNotIn('note', self.entry('Jones_2019', 'pool2'))  # never written to

    def test_sync_all(self):
        Path(self.path('lib', 'papers.bib')).write_text(
            '@article{mine2022,\n author = {Mine, Me},\n title = {My own paper},\n year = {2022}\n}\n')
        self.lib('sync --all')
        self.assertEqual(self.keys('lib'), ['Brown_2021', 'Jones_2019', 'Smith_2020', 'mine2022'])
        self.assertEqual(len(self.bib('pool')[1]), 4)  # Jones_2019 and mine2022 pushed to the first
        self.assertEqual(self.keys('pool2'), ['Brown_2021', 'Jones_2019'])

    def test_one_pool_on_the_command_line(self):
        out = self.out('pull --all --pool ../pool2')
        self.assertIn('pull from pool ../pool2: 2 added', out)
        self.assertIn('journal', self.entry('Brown_2021'))

    def test_missing_pool_is_a_warning(self):
        os.rename(self.path('pool2'), self.path('elsewhere'))
        with self.assertLogs(papers.logger, level='WARNING') as logs:
            out = self.out('pull --all')
        self.assertIn('pool2 does not exist', '\n'.join(logs.output))
        self.assertIn('pull from pool ../pool: 2 added', out)
        self.assertIn('../pool2 (', self.out('status'))
        self.assertIn('missing', self.out('status').split('../pool2')[1])
        self.lib('sync')  # the first pool is there

    def test_missing_first_pool(self):
        self.lib('pull Jones_2019')
        os.rename(self.path('pool'), self.path('elsewhere'))
        with self.assertRaisesRegex(PapersExit, r'pool \S+/pool does not exist \(nothing was changed\)'):
            self.lib('sync')
        with self.assertRaisesRegex(PapersExit, r'pool \S+/pool does not exist'):
            self.lib('push')
        self.assertIn('pull from pool ../pool2: 1 unchanged', self.out('pull'))

    def test_entry_of_a_missing_pool_is_not_looked_up_elsewhere(self):
        self.lib('pull Brown_2021')  # from the first pool, without journal
        os.rename(self.path('pool'), self.path('elsewhere'))
        self.lib('pull --on-duplicate error')  # no conflict with the Brown_2021 of pool2
        self.assertNotIn('journal', self.entry('Brown_2021'))


class TestConfigPoolFiles(PoolTest):
    "the files move only when the first pool changes"

    def setUp(self):
        super().setUp()
        self.papers('init pool2 --no-git --pool none')
        self.lib('config local false -y')
        self.lib('pull Smith_2020')
        self.assertEqual(self.files('Smith_2020'), [self.pool_pdf])

    def test_pools_further_down(self):
        out = self.out('config pool ../pool ../pool2')
        self.assertEqual(out, 'pool = ../pool ../pool2 (in ' + self.path('lib', CONFIG_FILE_LOCAL) + ')')
        self.lib('config pool ../pool')
        self.assertEqual(self.files('Smith_2020'), [self.pool_pdf])
        self.assertEqual(sorted(self.bib('pool2')[1]), [])

    def test_first_pool_changes(self):
        self.lib('config pool ../pool2 -y')
        files = self.files('Smith_2020')
        self.assertTrue(files[0].startswith(self.path('pool2', 'files')))
        self.assertEqual(len(self.bib('pool2')[1]), 1)  # the entry added to the new first pool

    def test_list_becomes_empty(self):
        self.lib('config pool ../pool ../pool2')
        self.lib('config pool none -y')
        self.assertTrue(self.files('Smith_2020')[0].startswith(self.path('lib', 'files')))


class TestSmallFixes(PoolTest):

    def test_config_local_path_with_home(self):
        home_lib = os.path.join(os.environ['HOME'], 'homelib')
        try:
            paperscmd('init homelib --no-git --pool none', cwd=os.environ['HOME'])
            out = paperscmd('config local true', cwd=home_lib, sp_cmd='check_output')
            self.assertEqual(out, 'local = true (in ~/homelib/.papersconfig.json)')
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

