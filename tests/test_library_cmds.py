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

    def test_global_pool_takes_one_path(self):
        with self.assertRaisesRegex(PapersExit, 'takes one path'):
            self.lib('config --global pools.x a b')

    def test_global_dry_run(self):
        out = self.out('config --global pools.x /a/b --dry-run')
        papers.config.DRYRUN = False
        self.assertIn('not saved', out)
        self.assertEqual(self.out('config --global pools.x'), '')

    def test_global_get(self):
        self.lib('config --global files copy')
        self.assertEqual(self.out('config --global files').strip(), 'copy')
        self.assertIn('files = copy', self.out('config --global'))


class TestOtherCommands(ConfigTest):

    def test_install_edit_and_reset(self):
        with self.assertRaises(SystemExit):
            self.papers('install --edit --reset')

    def test_uninstall_without_library(self):
        with self.assertRaises(SystemExit), \
                patch('papers.cli.library_cmds.logger'):
            self.papers('uninstall')

    def test_migrate_light_and_full(self):
        with self.assertRaises(SystemExit):
            self.papers('migrate --light --full')

    def test_migrate_nothing(self):
        out = self.papers('migrate', sp_cmd='check_output')
        self.assertIn('nothing to migrate', out)

    def test_init_in_a_library(self):
        self.papers('init --no-git')
        os.makedirs(self.path('sub'))
        with self.assertLogs('papers', level='INFO') as logs:
            self.papers('init --no-git --info', cwd=self.path('sub'))
        self.assertIn('inside the library', '\n'.join(logs.output))
