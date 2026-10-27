"""papers backup, restore and git: the cases without backup, and the
backup folders of papers 3.0.0b2 and earlier"""
import os
from unittest.mock import patch

from papers.utils import PapersExit
from tests.common import ConfigTest, FileTest


class TestBackupCmds(FileTest):

    def test_restore_without_git(self):
        with self.assertRaisesRegex(PapersExit, 'papers config git true'):
            self.lib('restore')

    def old(self, name):
        "a backup folder of papers 3.0.0b2 or earlier"
        from papers.config import BACKUP_DIR
        os.makedirs(os.path.join(BACKUP_DIR, name, '.git'), exist_ok=True)
        return os.path.join(BACKUP_DIR, name)

    def test_remove_answer_no(self):
        old = self.old('backup-x')
        with patch('builtins.input', return_value='n'):
            out = self.out('backup remove backup-x')
        self.assertIn('* backup-x', out)
        self.assertTrue(os.path.isdir(old))

    def test_remove_nothing_matches(self):
        self.old('backup-x')
        self.assertNotIn('backup-x', self.out('backup remove other'))

    def test_remove_needs_names(self):
        with self.assertRaises(SystemExit):
            self.lib('backup remove')

    def test_list(self):
        self.assertIn('(git off: previous bibtex only)', self.out('backup'))
        self.assertNotIn('papers 3.0.0b2', self.out('backup'))
        self.old('backup-x')
        self.assertIn('* backup-x', self.out('backup list'))

    def test_undo_without_git_nor_previous_version(self):
        with self.assertRaisesRegex(PapersExit, 'nothing to undo'):
            self.lib('undo')
        self.assertTrue(os.path.exists(self.path('lib', 'papers.bib')))

    def test_enable_git_without_git_installed(self):
        with patch('papers.backup.shutil.which', return_value=None), \
                self.assertRaisesRegex(PapersExit, 'needs git'):
            self.lib('config git true')
        self.assertEqual(self.out('config git').strip(), 'false')

    def test_git_lfs_first_snapshot(self):
        "the files are tracked with git-lfs, and no state of the history lacks the bibtex"
        self.lib('config git-lfs true')
        gitdir = os.path.expanduser(self.out('status -v').split('backup folder:')[1].split()[0])
        with open(os.path.join(gitdir, '.gitattributes')) as f:
            self.assertIn('files/** filter=lfs', f.read())
        self.assertEqual(self.out('git rev-list --count HEAD').strip(), '1')
        with self.assertRaisesRegex(PapersExit, 'nothing to undo'):
            self.lib('undo')
        self.assertTrue(os.path.exists(self.path('lib', 'papers.bib')))

    def test_git_not_found(self):
        self.lib('config git true')
        with patch('papers.cli.backup_cmds.sp.run', side_effect=OSError('no git')):
            with self.assertRaisesRegex(PapersExit, 'failed to run git'):
                self.lib('git status')


class TestGitWithoutLibrary(ConfigTest):

    def test_no_library(self):
        with patch('papers.cli.backup_cmds.logger'), self.assertRaises(PapersExit):
            self.papers('git status', cwd=self.dir)
