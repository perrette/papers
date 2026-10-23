"""papers config, install, uninstall, migrate: the option errors and the
settings that change other settings"""
import os
from unittest.mock import patch

import papers.config
from papers.utils import PapersExit
from tests.common import ConfigTest, FileTest


class TestConfigCmd(FileTest):

    def test_unset_and_key(self):
        with self.assertRaises(SystemExit):
            self.lib('config --unset git git')

    def test_unset_git_turns_off_git_lfs(self):
        self.lib('config git-lfs true')
        self.assertEqual(self.out('config git').strip(), 'true')  # git-lfs implies git
        self.lib('config --unset git')
        self.assertEqual(self.out('config git-lfs').strip(), 'false')

    def test_git_false_turns_off_git_lfs(self):
        self.lib('config git-lfs true')
        self.lib('config git false')
        self.assertEqual(self.out('config git-lfs').strip(), 'false')

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
        out = self.papers('init lib --no-git', sp_cmd='check_output')
        self.assertEqual(out.splitlines(), [
            f'created the library {papers.config.short_home(self.path("lib"))}',
            '* bibtex:  papers.bib',
            '* files:   files (the files directory of the library)',
            '* pool:    none (a self-contained library: its own entries and files)',
            '* backup:  off',
            '`papers status -v` shows all settings'])
        self.assertEqual(self.json('lib')['pool'], 'none')
        self.assertNotIn('local', self.json('lib'))

    def test_shallow(self):
        self.papers('init pool --no-git')
        out = self.papers('init lib --git --pool ../pool', sp_cmd='check_output')
        self.assertIn('* files:   in the pool ../pool\n', out)
        self.assertIn('* pool:    ../pool (a shallow library: it takes its entries from the pool and links to its '
                      'files)\n', out)
        self.assertIn('* backup:  git', out)
        self.assertEqual(self.json('lib')['pool'], '../pool')
        self.assertNotIn('local', self.json('lib'))

    def test_pool_none(self):
        out = self.papers('init lib --no-git --pool none', sp_cmd='check_output')
        self.assertIn('* pool:    none (a self-contained library', out)


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
            self.papers('init --no-git --no-check-files')
        self.assertFalse(os.path.exists(self.path('.papersconfig.json')))

    def test_init_in_a_library(self):
        self.papers('init --no-git')
        os.makedirs(self.path('sub'))
        with self.assertLogs('papers', level='INFO') as logs:
            self.papers('init --no-git --info', cwd=self.path('sub'))
        self.assertIn('inside the library', '\n'.join(logs.output))
