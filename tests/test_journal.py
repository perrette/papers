"""undo, redo and restore bring the files back and forth with the bibtex
(papers.journal.restore): the safety rules (never overwrite, a file changed
since stays, an external file only unlinked is never deleted, the pool keeps
its files), and the places a file is found (the operations of the commands,
the checksums, the files kept by the history)"""
import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch

import papers.backup
from papers import journal
from papers.checksums import FILES_JSON
from papers.config import Config, CONFIG_FILE_LOCAL
from papers.utils import checksum
from papers.files import delete_files

from tests.common import FileTest, entry


class JournalTest(FileTest):
    """a library in lib/, with an entry that links to a file outside of
    it, src/a.pdf (e.g. a folder of the project)"""

    def setUp(self):
        super().setUp()
        self.a = self.write('src', 'a.pdf', content='pdf a')
        self.bib(entry('one2000', self.a))

    def moved(self):
        "the file of one2000 in lib/files"
        files = self.libfiles()
        self.assertEqual(len(files), 1, files)
        return self.path('lib', 'files', files[0])

    def config(self):
        return Config.load(self.path('lib', CONFIG_FILE_LOCAL))

    def project(self):
        "the history of the library, and its place"
        return papers.backup.project_of(self.config(), create=False)

    def head(self):
        "the current state of the library"
        project, place = self.project()
        return project.state(project.head(place)['state'])


class TestOneStep(JournalTest):

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
        self.assertIn('restored from the history', out)


class TestSeveralSteps(JournalTest):

    def test_one_step_at_a_time(self):
        # the case of the issue: a rename that moved the files of a project folder
        b = self.write('src', 'b.pdf', content='pdf b')
        self.bib(entry('one2000', self.a), entry('two2000', b))
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

    def test_restore_state(self):
        self.lib('file rename --move')  # state 1: the library before it
        self.lib('tag one2000 --add x')
        out = self.out('restore 1')
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
        self.assertIn('restored from the history', out)
        self.assertIn(' --> moved back to ', out)
        self.assertEqual(Path(b).read_text(), 'pdf b')
        self.assertEqual(self.libfiles(), [])
        project, place = self.project()
        states = len(project.states())
        out = self.out('redo -n 2')
        self.assertIn('deleted again (kept in the history)', out)
        self.assertFalse(os.path.exists(b))
        self.assertEqual(self.libfiles(), [])
        # the file deleted again by redo is not a step of its own: undo goes back before the rm
        project, place = self.project()
        self.assertEqual(len(project.states()), states)
        self.lib('undo')
        self.assertEqual(len(self.libfiles()), 1)  # restored from the history, where the add put it

    def test_add_copied_from_outside(self):
        b = self.write('downloads', 'b.pdf', content='pdf b')
        Path(self.path('downloads', 'b.bib')).write_text(entry('two2000', b))
        self.lib('add ../downloads/b.bib --copy')
        self.assertIn('removed (a copy of ', self.out('undo'))
        self.assertEqual(self.libfiles(), [])
        self.lib('redo')
        self.assertEqual(len(self.libfiles()), 1)
        self.assertEqual(Path(b).read_text(), 'pdf b')

    def test_operations_in_the_state(self):
        self.lib('file rename --move')
        ops = self.head()['ops']
        self.assertEqual([(op['op'], op['src'], op['dst']) for op in ops],
                         [('moved', self.a, os.path.join('files', self.libfiles()[0]))])  # in the library: relative
        self.lib('tag one2000 --add x')
        self.assertEqual(self.head()['ops'], [])  # that command moved nothing


class TestChecksums(JournalTest):
    "the checksums of the files, .papers/files.json"

    def hashes(self):
        path = self.path('lib', FILES_JSON)
        return json.load(open(path))['files'] if os.path.exists(path) else {}

    def test_written_by_the_commands(self):
        self.lib('file rename --move')
        moved = self.moved()
        self.assertEqual(self.hashes(), {os.path.relpath(moved, self.path('lib')): checksum(moved).hex()})
        self.assertIn(FILES_JSON, self.head()['files'])  # in the history
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
        project, place = self.project()
        n = project.head(place)['state']
        project.update(n, dict(project.state(n), ops=[]))
        out = self.out('undo')
        self.assertIn('moved back to', out)
        self.assertEqual(Path(self.a).read_text(), 'pdf a')
        self.assertFalse(os.path.exists(moved))


class TestShallow(FileTest):
    """a file added to a shallow library goes to the pool: undo in the library
    moves it back (the pool undoes the add too); with --library-only, copies
    it back, and the pool keeps it"""

    def add(self):
        self.papers('init pool')
        self.papers('init shallow --pool ../pool')
        a = self.write('src', 'a.pdf', content='pdf a')
        Path(self.path('src', 'a.bib')).write_text(entry('one2000', a))
        self.papers('add ../src/a.bib --move', cwd=self.path('shallow'))
        pool_files = os.listdir(self.path('pool', 'files'))
        self.assertEqual(len(pool_files), 1)
        self.assertFalse(os.path.exists(a))
        return a, pool_files

    def test_moved_back(self):
        a, pool_files = self.add()
        self.papers('undo', cwd=self.path('shallow'))
        self.assertTrue(os.path.exists(a))
        self.assertEqual(os.listdir(self.path('pool', 'files')), [])
        self.papers('redo', cwd=self.path('shallow'))
        self.assertFalse(os.path.exists(a))
        self.assertEqual(os.listdir(self.path('pool', 'files')), pool_files)

    def test_copied_back(self):
        a, pool_files = self.add()
        self.papers('undo --library-only', cwd=self.path('shallow'))
        self.assertTrue(os.path.exists(a))
        self.assertEqual(os.listdir(self.path('pool', 'files')), pool_files)  # the pool entry still links it
        self.papers('redo', cwd=self.path('shallow'))
        self.assertFalse(os.path.exists(a))  # moved again: the pool has it
        self.assertEqual(os.listdir(self.path('pool', 'files')), pool_files)


class TestDeleted(JournalTest):
    "the files that the commands delete: kept in the history, unless keep-deleted-files is false"

    def store(self):
        return papers.backup.store(self.config())

    def kept(self):
        "the files kept by the history"
        root = self.store().file_objects
        return [f for _, _, files in os.walk(root) for f in files] if os.path.isdir(root) else []

    def test_rm_undo_restores_from_the_history(self):
        self.lib('rm one2000 --delete-files')
        self.assertFalse(os.path.exists(self.a))
        self.assertEqual(self.kept(), [self.head()['deleted'][0] + '.pdf'])
        out = self.out('undo')
        self.assertIn('restored from the history', out)
        self.assertEqual(Path(self.a).read_text(), 'pdf a')
        self.assertEqual(self.files('one2000'), [self.a])
        out = self.out('redo')
        self.assertIn('deleted again (kept in the history)', out)
        self.assertFalse(os.path.exists(self.a))
        # nothing of the history in the library
        self.assertFalse(os.path.exists(self.path('lib', '.papers', 'backup')))

    def test_operations_after_a_save_without_state(self):
        # a save that adds no state (nothing changed), then a file deleted: a state of its own,
        # not added to the state of the previous command
        from papers.library import finish_journal
        self.lib('tag one2000 --add x')  # a first state
        config = self.config()
        project, place = self.project()
        before = project.head(place)['state']
        previous_ops = list(project.state(before).get('ops') or [])
        journal.start(config.bibtex, papers.backup.Deleted(config))
        papers.backup.record(config)  # nothing changed: no state
        pdf = self.write('lib', 'files', 'stray.pdf', content='pdf a')  # a file no entry links to
        journal.remove(pdf)
        finish_journal(config)
        project, place = self.project()
        after = project.head(place)['state']
        self.assertNotEqual(after, before)
        self.assertEqual(project.state(before).get('ops') or [], previous_ops)
        self.assertEqual([op['op'] for op in project.state(after)['ops']], ['trashed'])
        self.lib('undo')
        self.assertEqual(Path(pdf).read_text(), 'pdf a')

    def test_keep_deleted_files_false(self):
        self.lib('config --global keep-deleted-files false')
        self.lib('rm one2000 --delete-files')
        self.assertFalse(os.path.exists(self.a))
        self.assertEqual(self.kept(), [])
        self.assertIn('deleted by the command, not restored', self.out('undo'))

    def test_history_emptied(self):
        self.lib('rm one2000 --delete-files')
        shutil.rmtree(self.store().file_objects)
        self.assertIn('no longer in the history', self.out('undo'))
        self.assertFalse(os.path.exists(self.a))

    def test_identical_copy_not_kept(self):
        # e.g. papers config pool: the library's copy is deleted, the pool has the same file
        copy = self.write('pool', 'a.pdf', content='pdf a')
        journal.start(self.path('lib', 'papers.bib'), papers.backup.Deleted(self.config()))
        delete_files([self.a], same={self.a: copy})
        self.assertFalse(os.path.exists(self.a))
        self.assertEqual(self.kept(), [])
        ops, _ = journal.leftover()
        self.assertEqual([(op['op'], op['dst']) for op in ops], [('removed', copy)])
        lines = journal.restore({copy}, {self.a}, ops, undo=True)
        self.assertIn('restored (a copy of', '\n'.join(lines))
        self.assertTrue(os.path.exists(copy))  # the pool keeps it
        self.assertEqual(Path(self.a).read_text(), 'pdf a')


class TestGuard(JournalTest):
    """before deleting more than the history keeps (history-size), or enough
    to drop a large part of it, papers asks"""

    def setUp(self):
        super().setUp()
        Path(self.a).write_bytes(b'%PDF' + b'x' * (2 * journal.MB))  # 2 MB
        self.lib('config --global history-size 1')

    def test_more_than_the_history_keeps_without_terminal(self):
        with patch('papers.backup.stdin_is_terminal', return_value=False), \
                self.assertLogs('papers', level='WARNING') as logs:
            out = self.out('rm one2000 --delete-files')
        self.assertIn('more than the history keeps (history-size: 1 MB)', out)
        self.assertIn('cannot be undone', out)
        self.assertIn('no terminal to confirm', '\n'.join(logs.output))
        self.assertTrue(os.path.exists(self.a))  # kept
        self.assertIn('kept ', out)

    def test_more_than_the_history_keeps_confirmed(self):
        with patch('papers.backup.stdin_is_terminal', return_value=True), \
                patch('builtins.input', return_value='y'):
            self.lib('rm one2000 --delete-files')
        self.assertFalse(os.path.exists(self.a))
        self.assertFalse(os.path.isdir(papers.backup.store(self.config()).file_objects))  # to the system trash
        self.assertIn('deleted by the command, not restored', self.out('undo'))  # to the system trash

    def test_answer_no(self):
        with patch('papers.backup.stdin_is_terminal', return_value=True), \
                patch('builtins.input', return_value='n'):
            self.lib('rm one2000 --delete-files')
        self.assertTrue(os.path.exists(self.a))

    def test_yes(self):
        with patch('builtins.input', side_effect=AssertionError('no question expected')):
            self.lib('rm one2000 --delete-files --yes')
        self.assertFalse(os.path.exists(self.a))

    def test_lesser_case_recent_states(self):
        # 0.6 MB, within the limit, but the history must drop states of the last day to keep it
        self.lib('config --global history-size 3')
        b = self.write('src', 'b.pdf', content='')
        Path(b).write_bytes(b'%PDF' + b'y' * (2 * journal.MB))
        self.bib(entry('one2000', self.a), entry('two2000', b))
        self.lib('rm one2000 --delete-files --yes')
        with patch('papers.backup.stdin_is_terminal', return_value=True), \
                patch('builtins.input', return_value='n') as answer:
            out = self.out('rm two2000 --delete-files')
        answer.assert_called_once()
        self.assertIn('of them from the last day', out)
        self.assertTrue(os.path.exists(b))

    def test_no_limit(self):
        self.lib('config --global history-size 0')
        with patch('builtins.input', side_effect=AssertionError('no question expected')):
            self.lib('rm one2000 --delete-files')
        self.assertIn('restored from the history', self.out('undo'))


class TestRefusedSave(JournalTest):
    """another program wrote the bibtex while the command ran: papers does
    not write it (#119), and puts back the files that the command moved"""

    def other_program(self, *args, **kwargs):
        Path(self.path('lib', 'papers.bib')).write_text(entry('other2001'))

    def test_files_put_back(self):
        with patch('papers.checksums.update', side_effect=self.other_program), \
                self.assertRaisesRegex(Exception, 'put back the files'):
            self.out('file rename --move')
        self.assertEqual(Path(self.a).read_text(), 'pdf a')
        self.assertEqual(self.libfiles(), [])
        self.assertIn('other2001', Path(self.path('lib', 'papers.bib')).read_text())  # not overwritten

    def test_deleted_files_put_back(self):
        with patch('papers.checksums.update', side_effect=self.other_program), \
                self.assertRaises(Exception):
            self.out('rm one2000 --delete-files')
        # rm deletes the files after the save: nothing was deleted
        self.assertEqual(Path(self.a).read_text(), 'pdf a')

    def test_rollback(self):
        b = self.write('src', 'b.pdf', content='pdf b')
        moved = self.path('lib', 'files', 'b.pdf')
        journal.start(self.path('lib', 'papers.bib'))
        os.makedirs(os.path.dirname(moved), exist_ok=True)
        shutil.move(b, moved)
        journal.record('moved', b, moved)
        copy = self.path('lib', 'files', 'a.pdf')
        shutil.copy(self.a, copy)
        journal.record('copied', self.a, copy)
        lines = journal.rollback(self.path('lib', 'papers.bib'))
        self.assertEqual(Path(b).read_text(), 'pdf b')
        self.assertFalse(os.path.exists(copy))
        self.assertTrue(os.path.exists(self.a))
        self.assertEqual(len(lines), 2)
        self.assertEqual(journal.pending(self.path('lib', 'papers.bib')), [])


class TestCommandsThatDoNotSave(JournalTest):
    """a command that changes files but not the bibtex (papers file clean),
    or that stops early (an error, Ctrl-C): what it did to the files is a
    step of the history, and undo brings the files back"""

    def stray(self, name, content='stray'):
        return self.write('lib', 'files', name, content=content)

    def test_file_clean_undo(self):
        a, b = self.stray('a.pdf', 'a'), self.stray('b.pdf', 'b')
        self.lib('file clean --yes')
        self.assertFalse(os.path.exists(a) or os.path.exists(b))
        self.assertIn('restored from the history', self.out('undo'))
        self.assertEqual(Path(a).read_text(), 'a')
        self.assertEqual(Path(b).read_text(), 'b')
        self.assertIn('deleted again', self.out('redo'))
        self.assertFalse(os.path.exists(a) or os.path.exists(b))

    def test_interrupted(self):
        a, b = self.stray('a.pdf', 'a'), self.stray('b.pdf', 'b')
        with patch('builtins.input', side_effect=['y', KeyboardInterrupt]), self.assertRaises(KeyboardInterrupt):
            self.lib('file clean')
        self.assertFalse(os.path.exists(a))  # removed before Ctrl-C
        self.assertTrue(os.path.exists(b))
        self.lib('undo')
        self.assertEqual(Path(a).read_text(), 'a')

    def test_question(self):
        self.stray('a.pdf')
        with patch('builtins.input', return_value='n') as ask:
            self.lib('file clean')
        self.assertIn('[y: yes, n: no, Y: all, N: none]', ask.call_args[0][0])


class TestShallowClean(FileTest):
    "the filesdir setting of a shallow library is not used: file clean does not clean it"

    def test_refused(self):
        self.papers('init pool')
        os.makedirs(self.path('other'))
        other = self.write('other', 'not-mine.pdf', content='a file of another library')
        self.lib('config filesdir ../other')
        self.lib('config pool ../pool -y')
        with self.assertRaisesRegex(Exception, r'in its pool: clean them there.*papers -C \.\./pool file clean'):
            self.lib('file clean --yes')
        self.assertTrue(os.path.exists(other))


class TestDropFiles(JournalTest):
    "papers history --drop-files N|PATH: the files kept by the history leave it by hand"

    def setUp(self):
        super().setUp()
        Path(self.a).write_text('x' * 3000)
        self.lib('rm one2000 --delete-files')
        project, place = self.project()
        self.step = project.head(place)['state']

    def kept(self):
        root = papers.backup.store(self.config()).file_objects
        return [f for _, _, files in os.walk(root) for f in files] if os.path.isdir(root) else []

    def test_size_in_the_list(self):
        self.assertRegex(self.out('history'), rf'> {self.step} papers rm one2000 --delete-files .*\[3 KB of deleted files\]')

    def test_drop_by_step(self):
        out = self.out(f'history --drop-files {self.step} --yes')
        self.assertIn('dropped 1 file (3 KB) from the history', out)
        self.assertEqual(self.kept(), [])
        self.assertNotIn('deleted files]', self.out('history'))
        self.assertIn('no longer in the history', self.out('undo'))
        self.assertFalse(os.path.exists(self.a))

    def test_drop_by_path(self):
        self.lib(f'history --drop-files {self.a} --yes')
        self.assertEqual(self.kept(), [])
        self.assertIn('keeps no file deleted from', self.out(f'history --drop-files {self.a} --yes'))

    def test_confirmation(self):
        with self.assertRaisesRegex(Exception, 'no terminal to confirm'):
            self.lib(f'history --drop-files {self.step}')
        with patch('papers.cli.backup_cmds.stdin_is_terminal', return_value=True), \
                patch('builtins.input', return_value='n'):
            self.lib(f'history --drop-files {self.step}')
        self.assertEqual(len(self.kept()), 1)

    def test_unknown_step(self):
        with self.assertRaisesRegex(Exception, 'no step 99'):
            self.lib('history --drop-files 99 --yes')
