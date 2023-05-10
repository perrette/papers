import os
from pathlib import Path
import json
import shutil
import tempfile
import unittest
import subprocess as sp
from papers.config import Config
from papers.config import CONFIG_FILE, CONFIG_FILE_LOCAL
from papers.bib import Biblio
# from pathlib import Path

from tests.common import paperscmd, prepare_paper, run, PAPERSCMD, BaseTest, LocalGitInstallTest, LocalGitLFSInstallTest, GlobalGitInstallTest, GlobalGitLFSInstallTest

bibtex2 = """@article{SomeOneElse2000,
 author = {Some One},
 doi = {10.5194/xxxx},
 title = {Interesting Stuff},
 year = {2000}
}"""

class TimeTravelBase:

    def get_commit(self):
        return sp.check_output(f"git rev-parse HEAD", shell=True, cwd=self.config.gitdir).strip().decode()

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
        print("backup after add paper:", self.config.backupfile_clean)
        print(open(self.config.backupfile_clean).read())

        self.papers(f'list --add-tag change')
        self.assertTrue(self.config.git)
        commits.append(self.get_commit())
        print("bib add-tag:", self._path(self.mybib))
        print(open(self._path(self.mybib)).read())
        print("backup after add-tag:", self.config.backupfile_clean)
        print(open(self.config.backupfile_clean).read())

        # make sure we have 3 distinct commits
        self.config.gitcmd('log')
        print(commits)
        print(self.config.gitdir)
        sp.check_call(f'ls {self.config.gitdir}', shell=True)
        self.assertEqual(len(set(commits)), 3)

        self.papers(f'undo')
        current = self.get_commit()
        self.assertEqual(current, commits[-2])

        self.papers(f'undo')
        current = self.get_commit()
        self.assertEqual(current, commits[-3])

        self.papers(f'redo')
        current = self.get_commit()
        self.assertEqual(current, commits[-2])

        self.papers(f'redo')
        current = self.get_commit()
        self.assertEqual(current, commits[-1])

        # beyond last commit, nothing changes
        f = lambda: self.papers(f'redo')
        self.assertRaises(Exception, f)
        current = self.get_commit()
        self.assertEqual(current, commits[-1])

        # two steps back
        self.papers(f'undo -n 2')
        current = self.get_commit()
        self.assertEqual(current, commits[-3])

        # two steps forth
        self.papers(f'redo -n 2')
        current = self.get_commit()
        self.assertEqual(current, commits[-1])

        # Now go to specific commits
        self.papers(f'restore-backup --ref {commits[0]}')
        current = self.get_commit()
        self.assertEqual(current, commits[0])

        self.papers(f'restore-backup --ref {commits[-1]}')
        current = self.get_commit()
        self.assertEqual(current, commits[-1])


class TestTimeTravelGitLocal(LocalGitInstallTest, TimeTravelBase):
    pass

class TestTimeTravelGitGlobal(GlobalGitInstallTest, TimeTravelBase):
    pass


class TestRestoreGitLocal(LocalGitInstallTest):

    def get_commit(self):
        return sp.check_output(f"git rev-parse HEAD", shell=True, cwd=self.config.gitdir).strip().decode()

    def test_undo(self):
        ## Make sure git undo / redo travels as expected

        self.papers(f'add {self.anotherbib}')
        biblio = Biblio.load(self._path(self.mybib), '')

        # Remove bibtex
        sp.check_call(f"rm -f {self._path(self.mybib)}", shell=True)

        self.papers(f'restore-backup')
        biblio2 = Biblio.load(self._path(self.mybib), '')

        self.assertMultiLineEqual(biblio.format(), biblio2.format())


class TestUndoGitLocal(LocalGitLFSInstallTest):

    def test_undo(self):

        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 0)

        self.papers(f'add {self.anotherbib}')
        biblio = biblio1 = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)

        open(self._path('yetanother'), 'w').write(bibtex2)
        self.papers(f'add yetanother')
        biblio = biblio2 = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 2)

        self.papers(f'undo')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)
        self.assertMultiLineEqual(biblio.format(), biblio1.format())

        self.papers(f'undo')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 0)

        self.papers(f'redo')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)
        self.assertMultiLineEqual(biblio.format(), biblio1.format())

        self.papers(f'redo')
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

        self.papers(f'filecheck --rename')

        biblio = biblio_future = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)
        file_path = os.path.join(self.config.filesdir, file_rename)
        self.assertEqual(biblio.get_files(biblio.entries[0]), [ file_path ])
        self.assertFalse(os.path.exists(pdf))
        self.assertTrue(os.path.exists(file_path))

        backup = Biblio.load(self.config.backupfile_clean, self._path('.papers/files'))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(backup_file_path)

        self.papers(f'undo')

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

        self.papers(f'redo')

        backup = Biblio.load(self.config.backupfile_clean, self._path('.papers/files'))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(backup_file_path)

        biblio = Biblio.load(self._path(self.mybib), '')
        # we're back on track
        self.assertMultiLineEqual(biblio.format(), biblio_future.format())

        # ...that's because the future file does exist
        self.assertTrue(os.path.exists(biblio_future.get_files(biblio_future.entries[0])[0]))
        self.assertTrue(os.path.exists(biblio.get_files(biblio.entries[0])[0]))


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

        self.papers(f'filecheck --rename')

        biblio = biblio_future = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)
        file_path = os.path.join(self.config.filesdir, file_rename)
        self.assertEqual(biblio.get_files(biblio.entries[0]), [ file_path ])
        self.assertFalse(os.path.exists(pdf))
        self.assertTrue(os.path.exists(file_path))

        backup = Biblio.load(self.config.backupfile_clean, self._path('.papers/files'))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(backup_file_path)

        self.papers(f'undo --restore')

        backup = Biblio.load(self.config.backupfile_clean, self._path('.papers/files'))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(backup_file_path)

        # The biblio has its file pointer to the backup directory:
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertMultiLineEqual(biblio.format(), biblio_original.format())
        self.assertEqual(len(biblio.entries), 1)

        # ...that's because the original file does exist
        self.assertTrue(os.path.exists(biblio_original.get_files(biblio_original.entries[0])[0]))

        self.papers(f'redo')

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

        self.papers(f'filecheck --rename --copy')

        biblio = biblio_future = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)
        file_path = os.path.join(self.config.filesdir, file_rename)
        self.assertEqual(biblio.get_files(biblio.entries[0]), [ file_path ])
        self.assertTrue(os.path.exists(pdf))
        self.assertTrue(os.path.exists(file_path))

        backup = Biblio.load(self.config.backupfile_clean, self._path('.papers/files'))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(Path(backup_file_path).exists())

        self.papers(f'undo')

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

        self.papers(f'redo')

        backup = Biblio.load(self.config.backupfile_clean, self._path('.papers/files'))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(Path(backup_file_path).exists())

        biblio = Biblio.load(self._path(self.mybib), '')
        # here again, we're back on track
        self.assertMultiLineEqual(biblio.format(), biblio_future.format())

        # ...that's because the future file does exist as well
        self.assertTrue(os.path.exists(biblio_future.get_files(biblio_future.entries[0])[0]))
        self.assertTrue(os.path.exists(biblio.get_files(biblio.entries[0])[0]))





class TestUndoGitOnlyLocal(LocalGitInstallTest):
    def _install(self):
        self.papers(f'install --local --no-prompt --bibtex {self.mybib} --files {self.filesdir} --git')
        self.config = Config.load(self._path(CONFIG_FILE_LOCAL))


class TestUndoGitGlobal(GlobalGitLFSInstallTest):

    def _install(self):
        self.papers(f'install --no-prompt --bibtex {self.mybib} --files {self.filesdir} --git --git-lfs')
        self.config = Config.load(CONFIG_FILE)

    def _format_file(self, name):
        return os.path.abs(name)


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



class TestUninstall(LocalGitLFSInstallTest):
    def test_uninstall(self):
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.papers(f'uninstall')
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))


class TestUninstall2(GlobalGitLFSInstallTest):
    def test_uninstall(self):
        self.assertTrue(self._exists(CONFIG_FILE))
        self.papers(f'install --force --local')
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(CONFIG_FILE))
        self.papers(f'uninstall')
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(CONFIG_FILE))

    def test_uninstall(self):
        self.papers(f'install --force --local')
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(CONFIG_FILE))
        self.papers(f'uninstall --recursive')
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))
        self.assertFalse(self._exists(CONFIG_FILE))