"""papers config, install, uninstall, migrate: the option errors and the
settings that change other settings"""
import os
from unittest.mock import patch

import papers.config
from papers.utils import PapersExit
from tests import TEST_GLOBAL_POOL
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

    def test_global_pool_several_paths(self):
        self.lib('config --global pool /a ~/b')
        self.assertEqual(papers.config.MachineConfig.load().data['pool'], ['/a', '~/b'])
        self.assertEqual(self.lib('config --global pool', sp_cmd='check_output'), '/a ~/b')
        self.lib('config --global pool /a')
        self.assertEqual(papers.config.MachineConfig.load().data['pool'], '/a')
        with self.assertRaisesRegex(PapersExit, 'none cannot be given with paths'):
            self.lib('config --global pool none /a')

    def test_global_dry_run(self):
        out = self.out('config --global pool /a/b --dry-run')
        papers.config.DRYRUN = False
        self.assertIn('not saved', out)
        self.assertNotEqual(self.out('config --global pool').strip(), '/a/b')

    def test_global_get(self):
        self.lib('config --global files copy')
        self.assertEqual(self.out('config --global files').strip(), 'copy')
        self.assertIn('files = copy', self.out('config --global'))


class TestInitSummary(ConfigTest):

    def test_local(self):
        out = self.papers('init lib --local --no-git', sp_cmd='check_output')
        self.assertEqual(out.splitlines(), [
            f'created the library {papers.config.short_home(self.path("lib"))}',
            '* bibtex:  papers.bib',
            '* files:   files (the files directory of the library)',
            f'* pool:    {papers.config.short_home(TEST_GLOBAL_POOL)} (shared entries; the PDFs stay in this library)',
            '* backup:  off',
            '`papers status -v` shows all settings'])

    def test_local_pool_path(self):
        self.papers('init pool --no-git --pool none')
        out = self.papers('init lib --local --no-git --pool ../pool', sp_cmd='check_output')
        self.assertIn('* pool:    ../pool (shared entries; the PDFs stay in this library)\n', out)

    def test_local_no_pool(self):
        out = self.papers('init lib --local --no-git --pool none', sp_cmd='check_output')
        self.assertNotIn('* pool:', out)

    def test_not_local(self):
        self.papers('config --global local false')
        out = self.papers('init lib --git', sp_cmd='check_output')
        self.assertIn(f'* files:   in the pool {papers.config.short_home(TEST_GLOBAL_POOL)}', out)
        self.assertIn('* backup:  git', out)
        self.assertNotIn('* pool:', out)  # the files line names the pool
        self.assertNotIn('settings:', out)


class TestOtherCommands(ConfigTest):

    def test_install_edit_and_reset(self):
        with self.assertRaises(SystemExit):
            self.papers('install --edit --reset')

    def test_uninstall_without_library(self):
        with self.assertRaises(SystemExit), \
                patch('papers.cli.library_cmds.logger'):
            self.papers('uninstall')

    def test_migrate_light_is_gone(self):
        # replaced by `papers config local false|true`
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
