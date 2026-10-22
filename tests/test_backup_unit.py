"""Unit tests of papers.backup: run_git, the manifest and the backup
directories, backup_bib, restore (with git-lfs), undo and redo errors, and
the undone state of older versions"""
import os
import subprocess as sp
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import papers.backup
from papers.backup import (adopt_legacy_undone_state, backup_bib, check_gitdir_ownership, git_redo,
                           git_restore_state, git_undo, list_backup_dirs, read_manifest, resolve_gitdir,
                           legacy_gitdir, restore_from_backupdir, run_git, _exclude_from_git)
from papers.bib import Biblio
from papers.config import Config
from papers.utils import PapersExit


ENTRY = """@article{a2000,
 author = {Author, A.},
 file = {:files/a.pdf:pdf},
 title = {One},
 year = {2000}
}
"""


class TmpTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.realpath(self.tmp.name)
        self.patch = mock.patch.multiple(papers.backup, BACKUP_DIR=self.path('backups'),
                                         BACKUP_DIR_LEGACY=self.path('legacy-backups'))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def path(self, *p):
        return os.path.join(self.dir, *p)

    def library(self, gitlfs=False):
        os.makedirs(self.path('lib', 'files'), exist_ok=True)
        Path(self.path('lib', 'files', 'a.pdf')).write_text('pdf of a')
        Path(self.path('lib', 'papers.bib')).write_text(ENTRY)
        config = Config(bibtex=self.path('lib', 'papers.bib'), filesdir=self.path('lib', 'files'),
                        git=True, gitlfs=gitlfs, gitdir=self.path('backups', 'lib'))
        return config

    def snapshot(self, config, message):
        backup_bib(Biblio.load(config.bibtex, config.filesdir), config, message=message)


class TestGitHelpers(TmpTest):

    def test_run_git_failure(self):
        os.makedirs(self.path('repo'))
        with self.assertLogs('papers', level='ERROR'), self.assertRaises(sp.CalledProcessError):
            run_git(self.path('repo'), 'log')
        self.assertNotEqual(run_git(self.path('repo'), ['log'], check=False).returncode, 0)

    def test_unreadable_manifest(self):
        os.makedirs(self.path('repo'))
        Path(self.path('repo', 'manifest.json')).write_text('{broken')
        with self.assertLogs('papers', level='WARNING'):
            self.assertIsNone(read_manifest(self.path('repo')))

    def test_exclude_without_git(self):
        os.makedirs(self.path('repo'))
        _exclude_from_git(self.path('repo'), 'manifest.json')  # nothing to do without .git
        self.assertFalse(os.path.exists(self.path('repo', '.git')))

    def test_legacy_gitdir_is_used(self):
        bibtex = self.path('lib', 'papers.bib')
        os.makedirs(legacy_gitdir(bibtex))
        self.assertEqual(resolve_gitdir(bibtex), legacy_gitdir(bibtex))

    def test_list_backup_dirs(self):
        os.makedirs(self.path('legacy-backups', 'old'))
        config = self.library()
        config.gitdir = self.path('elsewhere')
        os.makedirs(config.gitdir)
        dirs = [info['gitdir'] for info in list_backup_dirs(config)]
        self.assertEqual(dirs, [self.path('legacy-backups', 'old'), self.path('elsewhere')])
        self.assertTrue(list_backup_dirs(config)[-1]['current'])


class TestBackup(TmpTest):

    def test_backup_needs_git(self):
        config = self.library()
        config.git = False
        with self.assertRaises(PapersExit):
            backup_bib(None, config)

    def test_backup_allocates_gitdir(self):
        config = self.library()
        config.gitdir = None
        self.snapshot(config, 'first')
        self.assertTrue(config.gitdir.startswith(self.path('backups')))
        self.assertEqual(read_manifest(config.gitdir)['bibtex'], config.bibtex)

    def test_pre_manifest_directory_is_adopted(self):
        config = self.library()
        os.makedirs(config.gitdir)
        run_git(config.gitdir, 'init')
        check_gitdir_ownership(config)
        self.assertEqual(read_manifest(config.gitdir)['bibtex'], config.bibtex)

    def test_undo_redo_without_history(self):
        config = self.library()
        os.makedirs(config.gitdir)
        run_git(config.gitdir, 'init')
        for action in (git_undo, git_redo):
            with self.assertRaisesRegex(PapersExit, 'no backup history'):
                action(config)

    def test_nothing_to_undo_or_redo(self):
        config = self.library()
        self.snapshot(config, 'first')
        with self.assertRaisesRegex(PapersExit, 'nothing to undo'):
            git_undo(config, steps=5)
        with self.assertRaisesRegex(PapersExit, 'nothing to redo'):
            git_redo(config)

    def test_restore_unknown_ref(self):
        config = self.library()
        self.snapshot(config, 'first')
        with self.assertRaisesRegex(PapersExit, 'unknown git reference'):
            git_restore_state(config, 'nope')

    def test_restore_failure_tells_how_to_recover(self):
        config = self.library()
        self.snapshot(config, 'first')
        with mock.patch('papers.backup._restore_from_backupdir', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(PapersExit, 'try to recover manually with `cp'):
                restore_from_backupdir(config)

    def test_legacy_undone_state(self):
        # versions before the append-only history: HEAD on a 'history' branch behind 'main'
        config = self.library()
        self.snapshot(config, 'first')
        Path(config.bibtex).write_text(ENTRY.replace('One', 'Two'))
        self.snapshot(config, 'second')
        run_git(config.gitdir, ['checkout', '-b', 'history', 'HEAD~1'])
        adopt_legacy_undone_state(config.gitdir)
        branch = run_git(config.gitdir, ['rev-parse', '--abbrev-ref', 'HEAD']).stdout.strip()
        self.assertEqual(branch, 'main')
        log = run_git(config.gitdir, ['log', '--pretty=%s']).stdout.split('\n')
        self.assertEqual(log[0], 'papers: adopt undone state ' + log[0].split('state ')[1])
        self.assertIn('One', Path(config.backupfile).read_text())  # the undone state is the tip

    def test_legacy_undone_state_at_main(self):
        config = self.library()
        self.snapshot(config, 'first')
        run_git(config.gitdir, ['checkout', '-b', 'history'])
        adopt_legacy_undone_state(config.gitdir)
        branches = run_git(config.gitdir, ['branch', '--format=%(refname:short)']).stdout.split()
        self.assertEqual(branches, ['main'])


class TestRestoreLFS(TmpTest):
    """restore with git-lfs: the links of the restored bibtex point to the
    files where they are, or to their copy in the backup"""

    def setUp(self):
        super().setUp()
        self.config = self.library(gitlfs=True)
        os.makedirs(self.config.gitdir)
        run_git(self.config.gitdir, 'init')
        self.snapshot(self.config, 'first')
        self.pdf = self.path('lib', 'files', 'a.pdf')
        self.backup_pdf = Biblio.load(str(self.config.backupfile_clean), '').get_files(
            Biblio.load(str(self.config.backupfile_clean), '').entries[0])[0]

    def files(self):
        biblio = Biblio.load(self.config.bibtex, '')
        return biblio.get_files(biblio.entries[0])

    def test_same_file(self):
        restore_from_backupdir(self.config)
        self.assertEqual(self.files(), [self.pdf])

    def test_changed_file_points_to_backup(self):
        os.remove(self.pdf)  # the backup copy is a hard link: replace the file
        Path(self.pdf).write_text('other content')
        with self.assertLogs('papers', level='WARNING'):
            restore_from_backupdir(self.config)
        self.assertEqual(self.files(), [self.backup_pdf])

    def test_missing_file_restored(self):
        os.remove(self.pdf)
        restore_from_backupdir(self.config, restore_files=True)
        self.assertEqual(self.files(), [self.pdf])
        self.assertEqual(Path(self.pdf).read_text(), 'pdf of a')

    def test_missing_file_restore_failure(self):
        os.remove(self.pdf)
        with mock.patch('papers.backup.move', side_effect=OSError('read-only')), \
                self.assertLogs('papers', level='ERROR'):
            restore_from_backupdir(self.config, restore_files=True)
        self.assertEqual(self.files(), [self.backup_pdf])

    def test_broken_backup_link(self):
        # a file that the snapshot does not have
        run_git(self.config.gitdir, ['rm', '--quiet', os.path.relpath(self.backup_pdf, self.config.gitdir)])
        run_git(self.config.gitdir, ['commit', '--quiet', '-m', 'remove the file'])
        with self.assertLogs('papers', level='WARNING'):
            restore_from_backupdir(self.config)
        self.assertEqual(self.files(), [self.pdf])

    def test_file_removed_from_work_tree_is_restored(self):
        os.remove(self.backup_pdf)
        restore_from_backupdir(self.config)
        self.assertEqual(Path(self.backup_pdf).read_text(), 'pdf of a')
        self.assertEqual(self.files(), [self.pdf])

    # the backup copy is a hard link of the library file: a file edited in
    # place is edited in the work tree of the backup too, and restores used
    # to read that, not the snapshot

    def test_edited_in_place_points_to_snapshot(self):
        Path(self.pdf).write_text('edited')  # same inode
        with self.assertLogs('papers', level='WARNING'):
            restore_from_backupdir(self.config)
        self.assertEqual(self.files(), [self.backup_pdf])
        self.assertEqual(Path(self.backup_pdf).read_text(), 'pdf of a')
        self.assertEqual(Path(self.pdf).read_text(), 'edited')  # the library file is left as it is

    def test_edited_in_place_then_removed_is_restored_from_snapshot(self):
        Path(self.pdf).write_text('edited')
        os.remove(self.pdf)
        restore_from_backupdir(self.config, restore_files=True)
        self.assertEqual(self.files(), [self.pdf])
        self.assertEqual(Path(self.pdf).read_text(), 'pdf of a')

    def test_undo_after_edit_in_place(self):
        Path(self.config.bibtex).write_text(ENTRY.replace('One', 'Two'))
        self.snapshot(self.config, 'second')
        Path(self.pdf).write_text('edited')
        os.remove(self.pdf)
        git_undo(self.config, restore_files=True)
        self.assertIn('One', Path(self.config.bibtex).read_text())
        self.assertEqual(Path(self.pdf).read_text(), 'pdf of a')
