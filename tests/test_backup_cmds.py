"""papers backup, restore and git: the cases without backup, and the
questions of backup remove"""
from unittest.mock import patch

from papers.utils import PapersExit
from tests.common import ConfigTest, FileTest


class TestBackupCmds(FileTest):

    def info(self, current=False):
        return {'gitdir': self.path('backup-x'), 'bibtex': self.path('gone.bib'), 'current': current,
                'snapshots': 3, 'last': '2026-01-01', 'size': 2048}

    def test_restore_without_git(self):
        with self.assertRaisesRegex(PapersExit, 'papers config git true'):
            self.lib('restore')

    def test_remove_answer_no(self):
        with patch('papers.cli.backup_cmds.list_backup_dirs', return_value=[self.info(current=True)]), \
                patch('papers.cli.backup_cmds.shutil.rmtree') as rmtree, \
                patch('builtins.input', return_value='n'), \
                self.assertLogs('papers', level='WARNING') as logs:
            out = self.out('backup remove backup-x')
        rmtree.assert_not_called()
        self.assertIn("current library's backup directory", logs.output[0])
        self.assertIn('(bibtex missing)', out)
        self.assertIn('3 snapshots, last 2026-01-01', out)

    def test_remove_nothing_matches(self):
        with patch('papers.cli.backup_cmds.list_backup_dirs', return_value=[self.info()]):
            self.assertIn('no matching backup directory', self.out('backup remove other'))

    def test_remove_needs_names(self):
        with self.assertRaises(SystemExit):
            self.lib('backup remove')

    def test_list_without_snapshot(self):
        self.lib('config git true')
        with patch('papers.cli.backup_cmds.list_backup_dirs', return_value=[]):
            out = self.out('backup')
        self.assertIn('no backup directory found', out)
        self.assertIn('no snapshot recorded yet', out)

    def test_list_git_off(self):
        with patch('papers.cli.backup_cmds.list_backup_dirs', return_value=[]):
            self.assertIn('git-tracking is off', self.out('backup list'))

    def test_git_not_found(self):
        self.lib('config git true')
        with patch('papers.cli.backup_cmds.sp.run', side_effect=OSError('no git')):
            with self.assertRaisesRegex(PapersExit, 'failed to run git'):
                self.lib('git status')


class TestGitWithoutLibrary(ConfigTest):

    def test_no_library(self):
        with patch('papers.cli.backup_cmds.logger'), self.assertRaises(PapersExit):
            self.papers('git status', cwd=self.dir)
