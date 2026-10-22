import os
from pathlib import Path
import subprocess as sp
from papers.backup import run_git
from papers.config import CONFIG_FILE_LOCAL
from papers.bib import Biblio

from tests.common import prepare_paper, BaseTest, GitInitTest, GitLFSInitTest

bibtex2 = """@article{SomeOneElse2000,
 author = {Some One},
 doi = {10.5194/xxxx},
 title = {Interesting Stuff},
 year = {2000}
}"""

class TimeTravelBase:

    def get_commit(self):
        "commit representing the current library state (undo/redo append restore commits)"
        from papers.backup import cursor_commit
        return cursor_commit(self.config.gitdir)

    def test_undo(self):
        ## Make sure git undo / redo travels as expected

        print(self.config.status(verbose=True))
        self.assertTrue(self.config.git)

        commits = []
        commits.append(self.get_commit())

        self.papers(f'add {self.anotherbib}')
        self.assertTrue(self.config.git)
        commits.append(self.get_commit())
        print("bib add paper:", self._path(self.mybib))
        print(open(self._path(self.mybib)).read())
        print("backup after add paper:", self.config.backupfile)
        print(open(self.config.backupfile).read())

        self.papers('list --add-tag change')
        self.assertTrue(self.config.git)
        commits.append(self.get_commit())
        print("bib add-tag:", self._path(self.mybib))
        print(open(self._path(self.mybib)).read())
        print("backup after add-tag:", self.config.backupfile)
        print(open(self.config.backupfile).read())

        # make sure we have 3 distinct commits
        run_git(self.config.gitdir, 'log')
        print(commits)
        print(self.config.gitdir)
        sp.check_call(f'ls {self.config.gitdir}', shell=True)
        self.assertEqual(len(set(commits)), 3)

        self.papers('undo')
        current = self.get_commit()
        self.assertEqual(current, commits[-2])

        self.papers('undo')
        current = self.get_commit()
        self.assertEqual(current, commits[-3])

        self.papers('redo')
        current = self.get_commit()
        self.assertEqual(current, commits[-2])

        self.papers('redo')
        current = self.get_commit()
        self.assertEqual(current, commits[-1])

        # beyond last commit, nothing changes
        f = lambda: self.papers('redo')
        self.assertRaises(Exception, f)
        current = self.get_commit()
        self.assertEqual(current, commits[-1])

        # two steps back
        self.papers('undo -n 2')
        current = self.get_commit()
        self.assertEqual(current, commits[-3])

        # two steps forth
        self.papers('redo -n 2')
        current = self.get_commit()
        self.assertEqual(current, commits[-1])

        # Now go to specific commits
        self.papers(f'restore-backup --ref {commits[0]}')
        current = self.get_commit()
        self.assertEqual(current, commits[0])

        self.papers(f'restore-backup --ref {commits[-1]}')
        current = self.get_commit()
        self.assertEqual(current, commits[-1])

    def test_undo_then_change_keeps_history(self):
        ## A new change made while undone must not discard the redoable states

        commits = [self.get_commit()]

        self.papers(f'add {self.anotherbib}')
        commits.append(self.get_commit())

        self.papers('list --add-tag change')
        commits.append(self.get_commit())
        future_bib = open(self._path(self.mybib)).read()

        self.papers('undo')
        self.assertEqual(self.get_commit(), commits[1])

        # new line of history on top of the undone state
        self.papers('list --add-tag another')
        self.assertNotIn(self.get_commit(), commits)

        # the state that was still redoable remains reachable
        self.papers(f'restore-backup --ref {commits[2]}')
        self.assertEqual(self.get_commit(), commits[2])
        self.assertMultiLineEqual(open(self._path(self.mybib)).read(), future_bib)


class TestTimeTravelGitLocal(GitInitTest, TimeTravelBase):
    pass


class TestRestoreGitLocal(GitInitTest):

    def get_commit(self):
        return sp.check_output("git rev-parse HEAD", shell=True, cwd=self.config.gitdir).strip().decode()

    def test_undo(self):
        ## Make sure git undo / redo travels as expected

        self.papers(f'add {self.anotherbib}')
        biblio = Biblio.load(self._path(self.mybib), '')

        # Remove bibtex
        sp.check_call(f"rm -f {self._path(self.mybib)}", shell=True)

        self.papers('restore-backup')
        biblio2 = Biblio.load(self._path(self.mybib), '')

        self.assertMultiLineEqual(biblio.format(), biblio2.format())


class TestUndoGitLocal(GitLFSInitTest):

    def test_undo(self):

        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 0)

        self.papers(f'add {self.anotherbib}')
        biblio = biblio1 = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)

        open(self._path('yetanother'), 'w').write(bibtex2)
        self.papers('add yetanother')
        biblio = biblio2 = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 2)

        self.papers('undo')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)
        self.assertMultiLineEqual(biblio.format(), biblio1.format())

        self.papers('undo')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 0)

        self.papers('redo')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)
        self.assertMultiLineEqual(biblio.format(), biblio1.format())

        self.papers('redo')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 2)
        self.assertMultiLineEqual(biblio.format(), biblio2.format())


    def _format_file(self, name):
        return name

    def test_undo_files_rename(self):
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 0)

        pdf, doi, key, newkey, year, bibtex, file_rename = prepare_paper()

        self.papers(f'add {pdf} --doi {doi}')

        biblio = biblio_original = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)
        self.assertEqual(biblio.get_files(biblio.entries[0]), [ pdf ])
        self.assertTrue(os.path.exists(pdf))

        backup = backup0 = Biblio.load(self.config.backupfile_clean, self._path('.papers/files'))
        self.assertEqual(len(backup.entries), 1)
        backup_file_path = str((Path(self._path(self.config.gitdir))/"files"/file_rename).resolve())
        self.assertEqual(backup.get_files(backup.entries[0]), [ backup_file_path ])
        self.assertTrue(Path(backup_file_path).exists())

        self.papers('filecheck --rename')

        biblio = biblio_future = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)
        file_path = os.path.join(self.config.filesdir, file_rename)
        self.assertEqual(biblio.get_files(biblio.entries[0]), [ file_path ])
        self.assertFalse(os.path.exists(pdf))
        self.assertTrue(os.path.exists(file_path))

        backup = Biblio.load(self.config.backupfile_clean, self._path('.papers/files'))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(backup_file_path)

        self.papers('undo')

        backup = Biblio.load(self.config.backupfile_clean, self._path('.papers/files'))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(backup_file_path)

        # The biblio has its file pointer to the backup directory:
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertFalse(biblio.format() == biblio_original.format())
        self.assertEqual(len(biblio.entries), 1)

        self.assertNotEqual(biblio.get_files(biblio.entries[0]), biblio_original.get_files(biblio_original.entries[0]))
        self.assertEqual(biblio.get_files(biblio.entries[0]), backup.get_files(backup.entries[0]))

        # ...that's because the original file does not exist
        self.assertTrue(os.path.exists(biblio.get_files(biblio.entries[0])[0]))
        self.assertFalse(os.path.exists(biblio_original.get_files(biblio_original.entries[0])[0]))

        self.papers('redo')

        backup = Biblio.load(self.config.backupfile_clean, self._path('.papers/files'))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(backup_file_path)

        biblio = Biblio.load(self._path(self.mybib), '')
        # we're back on track
        self.assertMultiLineEqual(biblio.format(), biblio_future.format())

        # ...that's because the future file does exist
        self.assertTrue(os.path.exists(biblio_future.get_files(biblio_future.entries[0])[0]))
        self.assertTrue(os.path.exists(biblio.get_files(biblio.entries[0])[0]))


    def test_restore_file_edited_in_place(self):
        # the backup copy is a hard link of the library file, so it is
        # edited too: restore used to bring back the edited version
        pdf, doi, key, newkey, year, bibtex, file_rename = prepare_paper()
        self.papers(f'add {pdf} --doi {doi} --copy')
        biblio = Biblio.load(self._path(self.mybib), '')
        file_path = biblio.get_files(biblio.entries[0])[0]
        self.assertNotEqual(os.path.realpath(file_path), os.path.realpath(pdf))
        original = Path(file_path).read_bytes()
        with open(file_path, 'ab') as f:  # same inode
            f.write(b'edited')
        os.remove(file_path)

        self.papers('restore --restore-files')
        self.assertEqual(Path(file_path).read_bytes(), original)

    def test_undo_files_rename_restore(self):
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 0)

        pdf, doi, key, newkey, year, bibtex, file_rename = prepare_paper()

        self.papers(f'add {pdf} --doi {doi}')

        biblio = biblio_original = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)
        self.assertEqual(biblio.get_files(biblio.entries[0]), [ pdf ])
        self.assertTrue(os.path.exists(pdf))

        backup = backup0 = Biblio.load(self.config.backupfile_clean, self._path('.papers/files'))
        self.assertEqual(len(backup.entries), 1)
        backup_file_path = str((Path(self._path(self.config.gitdir))/"files"/file_rename).resolve())
        self.assertEqual(backup.get_files(backup.entries[0]), [ backup_file_path ])
        self.assertTrue(Path(backup_file_path).exists())

        self.papers('filecheck --rename')

        biblio = biblio_future = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)
        file_path = os.path.join(self.config.filesdir, file_rename)
        self.assertEqual(biblio.get_files(biblio.entries[0]), [ file_path ])
        self.assertFalse(os.path.exists(pdf))
        self.assertTrue(os.path.exists(file_path))

        backup = Biblio.load(self.config.backupfile_clean, self._path('.papers/files'))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(backup_file_path)

        self.papers('undo --restore')

        backup = Biblio.load(self.config.backupfile_clean, self._path('.papers/files'))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(backup_file_path)

        # The biblio has its file pointer to the backup directory:
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertMultiLineEqual(biblio.format(), biblio_original.format())
        self.assertEqual(len(biblio.entries), 1)

        # ...that's because the original file does exist
        self.assertTrue(os.path.exists(biblio_original.get_files(biblio_original.entries[0])[0]))

        self.papers('redo')

        backup = Biblio.load(self.config.backupfile_clean, self._path('.papers/files'))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(backup_file_path)

        biblio = Biblio.load(self._path(self.mybib), '')
        # we're back on track
        self.assertMultiLineEqual(biblio.format(), biblio_future.format())

        # ...that's because the future file does exist
        self.assertTrue(os.path.exists(biblio_future.get_files(biblio_future.entries[0])[0]))
        self.assertTrue(os.path.exists(biblio.get_files(biblio.entries[0])[0]))


    def test_undo_files_rename_copy(self):
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 0)

        pdf, doi, key, newkey, year, bibtex, file_rename = prepare_paper()

        self.papers(f'add {pdf} --doi {doi}')

        biblio = biblio_original = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)
        self.assertEqual(biblio.get_files(biblio.entries[0]), [ pdf ])
        self.assertTrue(os.path.exists(pdf))

        backup = backup0 = Biblio.load(self.config.backupfile_clean, self._path('.papers/files'))
        self.assertEqual(len(backup.entries), 1)
        backup_file_path = str((Path(self._path(self.config.gitdir))/"files"/file_rename).resolve())
        self.assertEqual(backup.get_files(backup.entries[0]), [ backup_file_path ])
        self.assertTrue(Path(backup_file_path).exists())

        self.papers('filecheck --rename --copy')

        biblio = biblio_future = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)
        file_path = os.path.join(self.config.filesdir, file_rename)
        self.assertEqual(biblio.get_files(biblio.entries[0]), [ file_path ])
        self.assertTrue(os.path.exists(pdf))
        self.assertTrue(os.path.exists(file_path))

        backup = Biblio.load(self.config.backupfile_clean, self._path('.papers/files'))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(Path(backup_file_path).exists())

        self.papers('undo')

        backup = Biblio.load(self.config.backupfile_clean, self._path('.papers/files'))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(Path(backup_file_path).exists())

        # The biblio has its file pointer as it should, cause the original file can be found
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertMultiLineEqual(biblio.format(), biblio_original.format())
        # print(biblio.format())
        # print(biblio_original.format())
        # self.assertTrue(biblio == biblio_original)

        # ...that's because the original file does not exist
        self.assertTrue(os.path.exists(biblio_original.get_files(biblio_original.entries[0])[0]))
        self.assertTrue(os.path.exists(biblio.get_files(biblio.entries[0])[0]))

        self.papers('redo')

        backup = Biblio.load(self.config.backupfile_clean, self._path('.papers/files'))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(Path(backup_file_path).exists())

        biblio = Biblio.load(self._path(self.mybib), '')
        # here again, we're back on track
        self.assertMultiLineEqual(biblio.format(), biblio_future.format())

        # ...that's because the future file does exist as well
        self.assertTrue(os.path.exists(biblio_future.get_files(biblio_future.entries[0])[0]))
        self.assertTrue(os.path.exists(biblio.get_files(biblio.entries[0])[0]))





class TestUndoNoInstall(BaseTest):

    def test_undo(self):

        open(self._path(self.mybib), 'w').write('')

        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 0)
        self.papers(f'add {self.anotherbib}  --bibtex {self.mybib} --files {self.filesdir}')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)

        open(self._path('yetanother'), 'w').write(bibtex2)
        self.papers(f'add yetanother --bibtex {self.mybib} --files {self.filesdir}')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 2)

        self.papers(f'undo --bibtex {self.mybib} --files {self.filesdir}')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)

        self.papers(f'undo --bibtex {self.mybib} --files {self.filesdir}')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 2)

        self.papers(f'redo --bibtex {self.mybib} --files {self.filesdir}')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)

        self.papers(f'redo --bibtex {self.mybib} --files {self.filesdir}')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 2)

        self.papers(f'redo --bibtex {self.mybib} --files {self.filesdir}')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)



class TestUninstall(GitLFSInitTest):
    def test_uninstall(self):
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.papers('uninstall')
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))


class TestUndoMessages(GitInitTest):

    def out(self, cmd):
        return self.papers(cmd, sp_cmd='check_output')

    def test_undo_and_redo_say_what_they_restore(self):
        self.papers(f'add {self.anotherbib}')
        Path(self._path('si.pdf')).write_text('supplement')
        self.papers('file attach --move 10.5194/bg-8-515-2011 si.pdf')
        biblio = Biblio.load(self._path(self.mybib), '')
        files = biblio.get_files(biblio.entries[0])
        self.assertEqual(len(files), 1)
        attached = files[0]
        self.assertTrue(attached.startswith(self._path(self.filesdir)))

        out = self.out('undo')
        self.assertRegex(out.splitlines()[0], rf'^undo: {self.mybib} restored to [0-9a-f]+ papers add '
                                              rf'{self.anotherbib} \(\d{{4}}-\d\d-\d\d \d\d:\d\d\)$')
        self.assertIn('1 file(s) of the files directory are linked by no entry now '
                      '(`papers file clean` removes them)', out)
        self.assertIn(attached, out)
        self.assertTrue(os.path.exists(attached))  # left in place

        out = self.out('redo')
        self.assertRegex(out, rf'^redo: {self.mybib} restored to [0-9a-f]+ papers file attach')
        self.assertNotIn('linked by no entry', out)
