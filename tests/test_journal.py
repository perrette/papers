"""undo, redo and restore bring the files back and forth with the bibtex
(papers.journal.restore): the safety rules (never overwrite, a file changed
since stays, an external file only unlinked is never deleted, the pool keeps
its files), and the places a file is found (the journal, the checksums, the
trash, the git-lfs store)"""
import json
import os
import shutil
import time
from pathlib import Path
from unittest.mock import patch

from papers import journal
from papers.checksums import FILES_JSON
from papers.config import Config, CONFIG_FILE_LOCAL
from papers.utils import checksum
from papers.files import delete_files

from tests.common import FileTest, entry


class JournalTest(FileTest):
    """a library in lib/ (git off), with an entry that links to a file
    outside of it, src/a.pdf (e.g. a folder of the project)"""

    def setUp(self):
        super().setUp()
        self.a = self.write('src', 'a.pdf', content='pdf a')
        self.bib(entry('one2000', self.a))

    def moved(self):
        "the file of one2000 in lib/files"
        files = self.libfiles()
        self.assertEqual(len(files), 1, files)
        return self.path('lib', 'files', files[0])


class TestWithoutGit(JournalTest):

    def test_rename_undo_redo(self):
        self.lib('file rename --move')
        moved = self.moved()
        self.assertFalse(os.path.exists(self.a))
        out = self.out('undo')
        self.assertIn(' --> moved back to ', out)
        self.assertEqual(Path(self.a).read_text(), 'pdf a')
        self.assertFalse(os.path.exists(moved))
        self.assertEqual(self.files('one2000'), [self.a])
        out = self.out('redo')
        self.assertIn(' --> moved to ', out)
        self.assertFalse(os.path.exists(self.a))
        self.assertEqual(self.files('one2000'), [moved])
        # and back again: the swap of the bibtex goes with the files
        self.lib('undo')
        self.assertTrue(os.path.exists(self.a))

    def test_copy_removed_by_undo(self):
        self.lib('file rename --copy')
        copy = self.moved()
        out = self.out('undo')
        self.assertIn('removed (a copy of ', out)
        self.assertFalse(os.path.exists(copy))
        self.assertTrue(os.path.exists(self.a))
        self.lib('redo')
        self.assertEqual(Path(copy).read_text(), 'pdf a')
        self.assertTrue(os.path.exists(self.a))

    def test_file_changed_since(self):
        self.lib('file rename --move')
        moved = self.moved()
        Path(moved).write_text('annotated')
        out = self.out('undo')
        self.assertIn('not where the command left it (or changed since): left as it is', out)
        self.assertEqual(Path(moved).read_text(), 'annotated')
        self.assertFalse(os.path.exists(self.a))  # the link of the restored bibtex is broken

    def test_place_taken(self):
        self.lib('file rename --move')
        moved = self.moved()
        self.write('src', 'a.pdf', content='another a')
        out = self.out('undo')
        self.assertIn('not moved back', out)
        self.assertTrue(os.path.exists(moved))
        self.assertEqual(Path(self.a).read_text(), 'another a')

    def test_only_the_last_command(self):
        # a later command that changes the bibtex without moving files: undo does not move the earlier ones
        self.lib('file rename --move')
        moved = self.moved()
        self.lib('tag one2000 --add x')
        out = self.out('undo')
        self.assertNotIn('-->', out)
        self.assertTrue(os.path.exists(moved))

    def test_file_mv(self):
        self.lib('file mv ../src/a.pdf ../src/b.pdf')
        b = self.path('src', 'b.pdf')
        self.assertEqual(self.files('one2000'), [b])
        self.lib('undo')
        self.assertTrue(os.path.exists(self.a))
        self.assertFalse(os.path.exists(b))
        self.assertEqual(self.files('one2000'), [self.a])

    def test_deleted_file_reported(self):
        self.lib('rm one2000 --delete-files')
        out = self.out('undo')
        self.assertIn('restored from the trash', out)


class TestWithGit(JournalTest):

    def setUp(self):
        super().setUp()
        self.lib('config git true')

    def test_one_step_at_a_time(self):
        # the case of the issue: a rename that moved the files of a project folder
        b = self.write('src', 'b.pdf', content='pdf b')
        self.bib(entry('one2000', self.a), entry('two2000', b))
        self.lib('config git true')
        self.lib('file rename one2000 --move')
        self.lib('file rename two2000 --move')
        self.assertFalse(os.path.exists(self.a) or os.path.exists(b))
        self.lib('undo')
        self.assertTrue(os.path.exists(b))
        self.assertFalse(os.path.exists(self.a))
        self.lib('undo')
        self.assertTrue(os.path.exists(self.a))
        self.assertEqual(self.libfiles(), [])
        self.lib('redo')
        self.assertFalse(os.path.exists(self.a))
        self.assertTrue(os.path.exists(b))

    def test_several_steps(self):
        self.lib('file rename --move')
        self.lib('tag one2000 --add x')
        out = self.out('undo -n 2')
        self.assertIn(' --> moved back to ', out)
        self.assertEqual(Path(self.a).read_text(), 'pdf a')
        self.assertEqual(self.libfiles(), [])
        self.lib('redo -n 2')
        self.assertFalse(os.path.exists(self.a))
        self.assertEqual(len(self.libfiles()), 1)

    def test_chain_of_moves(self):
        # rename, then move by papers file mv: undo of both finds the file at its last place
        self.lib('file rename --move')
        moved = self.moved()
        self.lib(f'file mv {moved} files/renamed.pdf')
        self.lib('undo -n 2')
        self.assertEqual(Path(self.a).read_text(), 'pdf a')
        self.assertEqual(self.libfiles(), [])
        self.lib('redo -n 2')
        self.assertEqual(self.libfiles(), ['renamed.pdf'])
        self.assertFalse(os.path.exists(self.a))

    def test_restore_ref(self):
        first = self.lib('git rev-list --max-parents=0 HEAD', sp_cmd='check_output').strip()
        self.lib('file rename --move')
        self.lib('tag one2000 --add x')
        out = self.out(f'restore --ref {first}')
        self.assertIn(' --> moved back to ', out)
        self.assertEqual(Path(self.a).read_text(), 'pdf a')
        self.assertEqual(self.files('one2000'), [self.a])

    def test_external_file_only_unlinked(self):
        # detach keeps the file: neither redo nor undo deletes it
        self.lib(f'file detach {self.a}')
        self.lib('undo')
        self.assertEqual(self.files('one2000'), [self.a])
        self.lib('redo')
        self.assertEqual(self.files('one2000'), [])
        self.assertEqual(Path(self.a).read_text(), 'pdf a')
        self.lib('undo')
        self.assertTrue(os.path.exists(self.a))

    def test_add_moved_from_outside(self):
        b = self.write('downloads', 'b.pdf', content='pdf b')
        Path(self.path('downloads', 'b.bib')).write_text(entry('two2000', b))
        self.lib('add ../downloads/b.bib --move')
        self.assertFalse(os.path.exists(b))
        out = self.out('undo')
        self.assertIn(' --> moved back to ', out)
        self.assertEqual(Path(b).read_text(), 'pdf b')
        self.assertEqual(self.libfiles(), [])
        self.lib('redo')
        self.assertFalse(os.path.exists(b))
        self.assertEqual(len(self.libfiles()), 1)

    def test_add_then_delete_several_steps(self):
        # the file went from downloads/ to the files directory, then to the
        # trash: undo of both puts it back in downloads/, redo in the trash
        b = self.write('downloads', 'b.pdf', content='pdf b')
        Path(self.path('downloads', 'b.bib')).write_text(entry('two2000', b))
        self.lib('add ../downloads/b.bib --move')
        self.lib('rm two2000 --delete-files')
        out = self.out('undo -n 2')
        self.assertIn('restored from the trash', out)
        self.assertIn(' --> moved back to ', out)
        self.assertEqual(Path(b).read_text(), 'pdf b')
        self.assertEqual(self.libfiles(), [])
        out = self.out('redo -n 2')
        self.assertIn('deleted again (to the trash)', out)
        self.assertFalse(os.path.exists(b))
        self.assertEqual(self.libfiles(), [])

    def test_add_copied_from_outside(self):
        b = self.write('downloads', 'b.pdf', content='pdf b')
        Path(self.path('downloads', 'b.bib')).write_text(entry('two2000', b))
        self.lib('add ../downloads/b.bib --copy')
        self.assertIn('removed (a copy of ', self.out('undo'))
        self.assertEqual(self.libfiles(), [])
        self.lib('redo')
        self.assertEqual(len(self.libfiles()), 1)
        self.assertEqual(Path(b).read_text(), 'pdf b')

    def test_journal_is_committed(self):
        self.lib('file rename --move')
        out = self.lib('git show --stat HEAD', sp_cmd='check_output')
        self.assertIn('files-journal.json', out)
        self.lib('tag one2000 --add x')
        out = self.lib('git show --stat HEAD', sp_cmd='check_output')
        self.assertIn('files-journal.json', out)  # removed: that command moved nothing


class TestChecksums(JournalTest):
    "the checksums of the files, .papers/files.json"

    def setUp(self):
        super().setUp()
        self.lib('config git true')

    def hashes(self):
        path = self.path('lib', FILES_JSON)
        return json.load(open(path))['files'] if os.path.exists(path) else {}

    def test_written_by_the_commands(self):
        self.lib('file rename --move')
        moved = self.moved()
        self.assertEqual(self.hashes(), {os.path.relpath(moved, self.path('lib')): checksum(moved).hex()})
        self.assertIn(FILES_JSON, self.lib('git ls-files', sp_cmd='check_output'))  # backed up
        self.lib('rm one2000')
        self.assertEqual(self.hashes(), {})  # no entry links the file

    def test_setting_off(self):
        self.lib('config checksums false')
        self.lib('file rename --move')
        self.assertEqual(self.hashes(), {})
        self.lib('undo')  # with the journal only
        self.assertEqual(Path(self.a).read_text(), 'pdf a')

    def test_command(self):
        self.assertIn('1 checksum written', self.out('file checksum'))
        self.assertEqual(self.hashes(), {os.path.relpath(self.a, self.path('lib')): checksum(self.a).hex()})
        Path(self.a).write_text('annotated')
        out = self.out('file checksum --check')
        self.assertIn('changed since its checksum', out)
        self.assertNotEqual(self.hashes()[os.path.relpath(self.a, self.path('lib'))], checksum(self.a).hex())
        self.assertIn('1 checksum written (1 changed)', self.out('file checksum'))
        self.assertEqual(self.hashes()[os.path.relpath(self.a, self.path('lib'))], checksum(self.a).hex())
        self.lib('undo')  # the checksums before
        self.assertNotEqual(self.hashes()[os.path.relpath(self.a, self.path('lib'))], checksum(self.a).hex())

    def test_found_by_checksum(self):
        # the journal of the command is gone (e.g. a command of an earlier
        # version): the checksum of the restored state finds the file
        self.lib('file checksum')
        self.lib('file rename --move')
        moved = self.moved()
        commit = self.lib('git rev-parse HEAD', sp_cmd='check_output').strip()
        self.lib('git rm -q files-journal.json')
        self.lib('git commit -q --amend --no-edit')
        self.assertNotEqual(self.lib('git rev-parse HEAD', sp_cmd='check_output').strip(), commit)
        out = self.out('undo')
        self.assertIn('moved back to', out)
        self.assertEqual(Path(self.a).read_text(), 'pdf a')
        self.assertFalse(os.path.exists(moved))


class TestShallow(FileTest):
    "a file added to a shallow library goes to the pool: undo in the library copies it back, the pool keeps it"

    def test_copied_back(self):
        self.papers('init pool --no-git')
        self.papers('init shallow --no-git --pool ../pool')
        a = self.write('src', 'a.pdf', content='pdf a')
        Path(self.path('src', 'a.bib')).write_text(entry('one2000', a))
        self.papers('add ../src/a.bib --move', cwd=self.path('shallow'))
        pool_files = os.listdir(self.path('pool', 'files'))
        self.assertEqual(len(pool_files), 1)
        self.assertFalse(os.path.exists(a))
        self.papers('undo', cwd=self.path('shallow'))
        self.assertTrue(os.path.exists(a))
        self.assertEqual(os.listdir(self.path('pool', 'files')), pool_files)  # the pool entry still links it
        self.papers('redo', cwd=self.path('shallow'))
        self.assertFalse(os.path.exists(a))  # moved again: the pool has it
        self.assertEqual(os.listdir(self.path('pool', 'files')), pool_files)


class TestTrash(JournalTest):

    def setUp(self):
        super().setUp()
        self.lib('config git true')

    def trash(self):
        config = Config.load(self.path('lib', CONFIG_FILE_LOCAL))
        return config.trash()[0]

    def test_rm_undo_restores_from_the_trash(self):
        self.lib('rm one2000 --delete-files')
        self.assertFalse(os.path.exists(self.a))
        self.assertEqual(len(os.listdir(self.trash())), 1)
        out = self.out('undo')
        self.assertIn('restored from the trash', out)
        self.assertEqual(Path(self.a).read_text(), 'pdf a')
        self.assertEqual(self.files('one2000'), [self.a])
        out = self.out('redo')
        self.assertIn('deleted again (to the trash)', out)
        self.assertFalse(os.path.exists(self.a))
        # the trash is not backed up
        self.assertNotIn('trash', self.lib('git status --short', sp_cmd='check_output'))

    def test_larger_than_the_trash_is_kept_without_terminal(self):
        self.lib('config trash-size 0')
        with patch('papers.files.stdin_is_terminal', return_value=False), \
                self.assertLogs('papers', level='WARNING') as logs:
            self.lib('rm one2000 --delete-files')
        self.assertIn('more than the trash holds (0 MB, the trash-size setting)', '\n'.join(logs.output))
        self.assertTrue(os.path.exists(self.a))  # kept

    def test_larger_than_the_trash_confirmed(self):
        self.lib('config trash-size 0')
        with patch('papers.files.stdin_is_terminal', return_value=True), \
                patch('builtins.input', return_value='y'):
            self.lib('rm one2000 --delete-files')
        self.assertFalse(os.path.exists(self.a))
        self.assertFalse(os.path.isdir(self.trash()) and os.listdir(self.trash()))
        self.assertIn('deleted by the command, not restored', self.out('undo'))

    def test_trash_emptied(self):
        self.lib('rm one2000 --delete-files')
        shutil.rmtree(self.trash())
        self.assertIn('no longer in the trash', self.out('undo'))
        self.assertFalse(os.path.exists(self.a))

    def test_git_lfs_store(self):
        # the git-lfs copies of the backups of earlier versions: undo finds a file there by its checksum
        digest = checksum(self.a).hex()
        self.lib('rm one2000 --delete-files')
        shutil.rmtree(self.trash())
        gitdir = os.path.dirname(self.trash())
        lfs = os.path.join(gitdir, '.git', 'lfs', 'objects', digest[:2], digest[2:4])
        os.makedirs(lfs)
        Path(lfs, digest).write_text('pdf a')
        self.assertIn('restored from the git-lfs copy', self.out('undo'))
        self.assertEqual(Path(self.a).read_text(), 'pdf a')

    def test_old_files_leave_the_trash(self):
        trash = self.trash()
        os.makedirs(trash)
        old = self.write(trash, 'old.pdf')
        os.utime(old, (0, 0))
        recent = self.write(trash, 'recent.pdf')
        with patch('send2trash.send2trash') as system_trash:
            journal.empty_trash(trash, days=30, megabytes=100)
        system_trash.assert_called_once_with(old)  # to the trash of the system
        os.remove(old)
        old = self.write(trash, 'old.pdf')
        self.assertEqual(sorted(os.listdir(trash)), ['old.pdf', 'recent.pdf'])
        # beyond the size: the oldest go first
        Path(old).write_bytes(b'x' * journal.MB)
        os.utime(old, (time.time() - 10, time.time() - 10))
        journal.empty_trash(trash, days=30, megabytes=1)
        self.assertEqual(sorted(os.listdir(trash)), ['recent.pdf'])
        self.assertTrue(os.path.exists(recent))

    def test_identical_copy_not_trashed(self):
        # e.g. papers config pool: the library's copy is deleted, the pool has the same file
        copy = self.write('pool', 'a.pdf', content='pdf a')
        journal.start(self.path('lib', 'papers.bib'), (self.trash(), 30, 100))
        delete_files([self.a], same={self.a: copy})
        self.assertFalse(os.path.exists(self.a))
        self.assertFalse(os.path.isdir(self.trash()))
        ops, _ = journal.leftover()
        self.assertEqual([(op['op'], op['dst']) for op in ops], [('removed', copy)])
        lines = journal.restore({copy}, {self.a}, ops, undo=True)
        self.assertIn('restored (a copy of', '\n'.join(lines))
        self.assertTrue(os.path.exists(copy))  # the pool keeps it
        self.assertEqual(Path(self.a).read_text(), 'pdf a')
