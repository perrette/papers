"""undo and redo move the files of the command back and forth (papers.journal)"""
import os
from pathlib import Path

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
        self.assertIn('deleted by the command, not restored', out)


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

    def test_several_steps_leave_the_files(self):
        self.lib('file rename --move')
        self.lib('tag one2000 --add x')
        out = self.out('undo -n 2')
        self.assertIn('stay as they are', out)
        self.assertFalse(os.path.exists(self.a))

    def test_journal_is_committed(self):
        self.lib('file rename --move')
        out = self.lib('git show --stat HEAD', sp_cmd='check_output')
        self.assertIn('files-journal.json', out)
        self.lib('tag one2000 --add x')
        out = self.lib('git show --stat HEAD', sp_cmd='check_output')
        self.assertIn('files-journal.json', out)  # removed: that command moved nothing


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
