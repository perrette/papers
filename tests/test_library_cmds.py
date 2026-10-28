"""papers config, install, uninstall, migrate: the option errors and the
settings that change other settings"""
import os
from unittest.mock import patch

import papers.config
from papers.utils import PapersExit
from tests.common import ConfigTest, FileTest
from papers.config import CONFIG_FILE_LOCAL


class TestConfigCmd(FileTest):

    def test_unset_and_key(self):
        with self.assertRaises(SystemExit):
            self.lib('config --unset git git')

    def test_removed_settings(self):
        for name in ('git', 'git-lfs', 'trash-days', 'trash-size'):
            with self.assertRaises(PapersExit) as cm:
                self.lib(f'config {name} true')
            self.assertIn('no longer used', str(cm.exception))

    def test_machine_settings(self):
        # a library cannot choose where the history goes, or whether it keeps the deleted files
        for name in ('history-dir', 'keep-deleted-files'):
            with self.assertRaises(PapersExit) as cm:
                self.lib(f'config {name} x')
            self.assertIn('setting of the machine', str(cm.exception))
        self.lib('config --global keep-deleted-files false')
        self.assertIn('keep-deleted-files = false', self.out('config --global'))
        # history-separate and history-size: a library may set them (its own store)
        self.lib('config history-separate true')
        self.lib('config history-size 10')
        self.assertEqual(self.out('config history-size').strip(), '10')

    def test_filesdir_that_does_not_exist(self):
        with self.assertLogs('papers', level='WARNING') as logs:
            self.lib('config filesdir other')
        self.assertIn('does not exist', logs.output[0])
        self.assertEqual(self.out('config filesdir').strip(), self.path('lib', 'other'))

    def test_dry_run(self):
        before = self.out('config files')
        out = self.out('config files copy --dry-run')
        papers.config.DRYRUN = False
        self.assertIn('not saved', out)
        self.assertEqual(self.out('config files'), before)

    def test_bad_value(self):
        with self.assertRaises(PapersExit):
            self.lib('config key.author-num many')

    def test_global_has_no_pool(self):
        with self.assertRaisesRegex(PapersExit, 'the global configuration has no pool'):
            self.lib('config --global pool a')

    def test_global_default_takes_one_path(self):
        with self.assertRaisesRegex(PapersExit, 'takes one value'):
            self.lib('config --global default a b')

    def test_default_is_global(self):
        with self.assertRaisesRegex(PapersExit, 'default is a setting of the global configuration'):
            self.lib('config default ../lib')

    def test_global_dry_run(self):
        out = self.out(f'config --global default {self.path("lib")} --dry-run')
        papers.config.DRYRUN = False
        self.assertIn('not saved', out)
        self.assertEqual(self.out('config --global default').strip(), '')

    def test_global_get(self):
        self.lib('config --global files copy')
        self.assertEqual(self.out('config --global files').strip(), 'copy')
        self.assertIn('files = copy', self.out('config --global'))


class TestInitSummary(ConfigTest):

    def test_self_contained(self):
        # by default, a self-contained library
        out = self.papers('init lib', sp_cmd='check_output')
        self.assertEqual(out.splitlines(), [
            f'created the library {papers.config.short_home(self.path("lib"))}',
            '* bibtex:  papers.bib',
            '* files:   files (the files directory of the library)',
            '* history: undo and redo (`papers history`)',
            '`papers config` lists and sets the settings'])
        self.assertEqual(self.json('lib')['pool'], 'none')
        self.assertNotIn('local', self.json('lib'))

    def test_shallow(self):
        self.papers('init pool')
        out = self.papers('init lib --pool ../pool', sp_cmd='check_output')
        self.assertIn('* files:   in the pool (shallow library)\n* pool:    ../pool\n', out)
        self.assertIn('* history: undo and redo', out)
        self.assertEqual(self.json('lib')['pool'], '../pool')
        self.assertNotIn('local', self.json('lib'))

    def test_pool_none(self):
        out = self.papers('init lib --pool none', sp_cmd='check_output')
        self.assertIn('* files:   files (the files directory of the library)\n', out)
        self.assertNotIn('* pool:', out)


class TestOtherCommands(ConfigTest):

    def test_install_edit_and_reset(self):
        with self.assertRaises(SystemExit):
            self.papers('install --edit --reset')

    def test_uninstall_without_library(self):
        with self.assertRaises(SystemExit), \
                patch('papers.cli.library_cmds.logger'):
            self.papers('uninstall')

    def test_migrate_light_is_gone(self):
        # replaced by `papers config pool PATH|none`
        with self.assertRaises(SystemExit):
            self.papers('migrate --light')

    def test_migrate_nothing(self):
        out = self.papers('migrate', sp_cmd='check_output')
        self.assertIn('nothing to migrate', out)

    def test_init_no_check_files_is_gone(self):
        # it did nothing on init; install keeps it (it skips the files count of the status)
        with self.assertRaises(SystemExit):
            self.papers('init --no-check-files')
        self.assertFalse(os.path.exists(self.path(CONFIG_FILE_LOCAL)))

    def test_init_dir_not_left_behind(self):
        # a check that fails after DIR is created removes it again
        with patch('papers.cli.library_cmds.resolve_install', side_effect=PapersExit('failed')), \
                self.assertRaises((PapersExit, SystemExit)):
            self.papers('init new/lib')
        self.assertFalse(os.path.exists(self.path('new')))

    def test_init_in_a_library(self):
        self.papers('init')
        os.makedirs(self.path('sub'))
        with self.assertLogs('papers', level='INFO') as logs:
            self.papers('init --info', cwd=self.path('sub'))
        self.assertIn('inside the library', '\n'.join(logs.output))
