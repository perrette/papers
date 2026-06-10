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

from tests.common import (paperscmd, prepare_paper, run, PAPERSCMD, BaseTest as TestBaseInstall,
                          LocalInstallTest, GlobalInstallTest, LocalGitLFSInstallTest)

bibtex2 = """@article{SomeOneElse2000,
 author = {Some One},
 doi = {10.5194/xxxx},
 title = {Interesting Stuff},
 year = {2000}
}"""

class TestLocalInstall(TestBaseInstall):

    def test_install(self):
        self.assertFalse(self._exists(self.mybib))
        self.assertFalse(self._exists(self.filesdir))
        self.papers(f'install --force --local --bibtex {self.mybib} --files {self.filesdir}')
        # Config file was created:
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        # Values of config file match input:
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.assertTrue(config.git)  # fresh install defaults to git
        # bibtex and files directory were created:
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))


    def test_install_defaults_no_preexisting_bibtex(self):
        self.assertFalse(self._exists(self.mybib))
        self.assertFalse(self._exists(self.filesdir))
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))
        # pre-existing bibtex?
        os.remove(self._path(self.anotherbib))
        self.assertFalse(self._exists(self.anotherbib))
        self.papers(f'install --force --local')
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        # self.assertEqual(config.bibtex, os.path.abspath(self._path("papers.bib")))
        self.assertEqual(config.bibtex, os.path.abspath(self._path("papers.bib")))
        self.assertEqual(config.filesdir, os.path.abspath(self._path("files")))
        self.assertTrue(config.git)


    def test_install_defaults_preexisting_bibtex(self):
        self.assertFalse(self._exists(self.mybib))
        self.assertFalse(self._exists(self.filesdir))
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))
        # pre-existing bibtex
        self.assertTrue(self._exists(self.anotherbib))
        self.assertFalse(self._exists("papers.bib"))
        self.papers(f'install --force --local')
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.anotherbib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path("files")))
        self.assertTrue(config.git)


    def test_install_defaults_preexisting_pdfs(self):
        self.assertFalse(self._exists(self.filesdir))
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))
        # pre-existing pdfs folder (pre-defined set of names)
        os.makedirs(self._path("pdfs"))
        self.papers(f'install --force --local')
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        # self.assertEqual(config.bibtex, os.path.abspath(self._path("papers.bib")))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.anotherbib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path("pdfs")))
        self.assertTrue(config.git)

    def test_install_raise(self):
        self.papers(f'install --force --local --bibtex {self.mybib} --files {self.filesdir}')
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))
        f = lambda : self.papers(f'install --local --bibtex {self.mybib} --files {self.filesdir}')
        self.assertRaises(Exception, f)

    def test_install_force(self):
        self.papers(f'install --force --local --bibtex {self.mybib} --files {self.filesdir}')
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.papers(f'install --local --force --bibtex {self.mybib}XX')
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib + "XX")))
        # Re-installing updates the existing configuration: the files folder is kept
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.assertTrue(config.git)

    def test_install_reset(self):
        self.papers(f'install --force --local --bibtex {self.mybib} --files {self.filesdir}')
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.papers(f'install --local --force --reset --bibtex {self.mybib}XX')
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib + "XX")))
        # --reset starts over: the files folder from the previous install is forgotten
        self.assertEqual(config.filesdir, os.path.abspath(self._path("files")))

    def test_install_edit(self):
        self.papers(f'install --force --local --bibtex {self.mybib} --files {self.filesdir}')
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.papers(f'install --local --edit --bibtex {self.mybib}XX')
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib + "XX")))
        # The files folder from previous install is remembered
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.assertTrue(config.git)

    def test_install_interactive(self):
        # fully interactive install
        sp.check_call(f"""{PAPERSCMD} install --local << EOF
{self.mybib}
{self.filesdir}
n
EOF""", shell=True, cwd=self.temp_dir.name)
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.assertFalse(config.git)

        # Now try simple carriage return (select defaults): everything is kept
        sp.check_call(f"""{PAPERSCMD} install --local << EOF



EOF""", shell=True, cwd=self.temp_dir.name)
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))

        # update existing install interactively (the default behavior)
        sp.check_call(f"""{PAPERSCMD} install --local --bibtex {self.mybib}XX << EOF
y
n
EOF""", shell=True, cwd=self.temp_dir.name)
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib + "XX")))
        # The files folder from previous install is remembered
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.assertFalse(config.git)

        # start over from defaults (--reset)
        sp.check_call(f"""{PAPERSCMD} install --local --reset --bibtex {self.mybib}XX << EOF
y
n
EOF""", shell=True, cwd=self.temp_dir.name)
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib + "XX")))
        # The files folder from previous install was forgotten
        self.assertEqual(config.filesdir, os.path.abspath(self._path("files")))
        self.assertFalse(config.git)

        # unset values from install with the reset words
        sp.check_call(f"""{PAPERSCMD} install --local << EOF
reset
reset
n
EOF""", shell=True, cwd=self.temp_dir.name)
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, None)
        # The files folder from previous install was forgotten
        self.assertEqual(config.filesdir, None)
        self.assertFalse(config.git)

        # install with git tracking
        sp.check_call(f"""{PAPERSCMD} install --local << EOF


y
y
EOF""", shell=True, cwd=self.temp_dir.name)
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        ## by default another bib is detected, because it starts with a (sorted)
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.anotherbib)))
        # The files folder from previous install was forgotten
        self.assertEqual(config.filesdir, os.path.abspath(self._path("files")))
        self.assertTrue(config.git)
        self.assertTrue(config.gitlfs)


class TestInstallNewBibTex(TestBaseInstall):

    # no bibtex file is present at start
    initial_content = None
    anotherbib_content = None

    def test_install(self):
        self.assertFalse(self._exists(self.mybib))
        self.assertFalse(self._exists(self.anotherbib))
        self.papers(f"""install --local --filesdir files << EOF
my.bib
n
EOF""")
        self.assertTrue(self._exists("my.bib"))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path("my.bib")))


class TestInstallEditor(TestBaseInstall):

    # no bibtex file is present at start
    initial_content = None
    anotherbib_content = None

    def test_install(self):
        self.papers(f'install --force --local --editor "subl -w"')
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.editor, "subl -w")


class TestDefaultLocal(LocalInstallTest):
    def test_install(self):
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self.config.local)
        self.papers(f'install --edit')
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertTrue(config.local)

class TestDefaultLocal2(GlobalInstallTest):
    def test_install(self):
        self.assertTrue(self._exists(CONFIG_FILE))
        self.assertFalse(self.config.local)
        self.papers(f'install --edit')
        self.assertTrue(self._exists(CONFIG_FILE))
        config = Config.load(CONFIG_FILE)
        self.assertFalse(config.local)


class TestGlobalInstall(TestBaseInstall):

    def test_install(self):
        self.assertFalse(self._exists(self.mybib))
        self.assertFalse(self._exists(self.filesdir))
        self.assertFalse(os.path.exists(CONFIG_FILE))
        self.papers(f'install --no-prompt --bibtex {self.mybib} --files {self.filesdir}')
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))
        self.assertTrue(os.path.exists(CONFIG_FILE))
        config = Config.load(self._path(CONFIG_FILE))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))


class TestGitInstall(TestBaseInstall):

    def test_install_gitlfs(self):
        self.papers(f'install --local --no-prompt --git-lfs')
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertTrue(config.git)
        # self.assertTrue(self._exists(".git"))

    def test_install(self):
        self.papers(f'install --local --no-prompt --bibtex {self.mybib} --files {self.filesdir} --git')
        self.assertTrue(self._exists(self.mybib))
        # self.assertTrue(self._exists(".git"))
        # count = sp.check_output(f'cd {self.temp_dir.name} && git rev-list --all --count', shell=True).strip().decode()
        # self.assertEqual(count, '0')
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        count = self.papers('git rev-list --all --count', sp_cmd='check_output')
        count_ = sp.check_output("git rev-list --all --count", shell=True, cwd=config.gitdir).decode().strip()
        self.assertEqual(count, count_)
        count2 = self.papers('git rev-list --all --count', sp_cmd='check_output')
        count2_ = sp.check_output("git rev-list --all --count", shell=True, cwd=config.gitdir).decode().strip()
        self.assertEqual(count2, count2_)
        self.papers(f'add {self.anotherbib}')
        # self.papers(f'add --doi 10.5194/bg-8-515-2011')
        count2 = self.papers('git rev-list --all --count', sp_cmd='check_output')

        print(count, count2)
        self.assertEqual(int(count2), int(count)+1)

    def test_install_interactive(self):
        self.papers(f"""install --local --filesdir files --bibtex bibbib.bib << EOF
y
y
EOF""")
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertTrue(config.git)
        self.assertTrue(config.gitlfs)

    def test_install_interactive2(self):
        self.papers(f"""install --local --filesdir files --bibtex bibbib.bib << EOF
y
n
EOF""")
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertTrue(config.git)
        self.assertFalse(config.gitlfs)

    def test_install_interactive3(self):
        self.papers(f"""install --local --filesdir files --bibtex bibbib.bib << EOF
n
EOF""")
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertFalse(config.git)
        self.assertFalse(config.gitlfs)

    def test_install_interactive4(self):
        # plain Enter selects the defaults: git on (fresh install), git-lfs off
        self.papers(f"""install --local --filesdir files --bibtex bibbib.bib << EOF


EOF""")
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertTrue(config.git)
        self.assertFalse(config.gitlfs)

    def test_install_no_git(self):
        self.papers(f'install --force --local --no-git --bibtex bibbib.bib --filesdir files')
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertFalse(config.git)
        self.assertFalse(config.gitlfs)

    def test_install_interactive5(self):
        self.papers(f"""install --local --filesdir files --bibtex bibbib.bib << EOF
y

EOF""")
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertTrue(config.git)
        self.assertFalse(config.gitlfs)


class TestInstallEdit(TestBaseInstall):

    def test_filesdir_outside_library_dir(self):
        # the files directory may live outside the library folder: the local
        # config then stores a '..'-style relative path, not an absolute one
        with tempfile.TemporaryDirectory() as outside:
            self.papers(f'install --force --local --no-git --bibtex {self.mybib} --files {outside}')
            js = json.load(open(self._path(CONFIG_FILE_LOCAL)))
            self.assertTrue(js['filesdir'].startswith('..'), js['filesdir'])
            config = Config.load(self._path(CONFIG_FILE_LOCAL))
            self.assertEqual(os.path.realpath(config.filesdir), os.path.realpath(outside))

    def test_edit_reallocates_missing_gitdir(self):
        # older configs carried a never-created legacy gitdir; enabling git via
        # --edit should allocate the current (hashed) naming scheme instead
        from papers.config import BACKUP_DIR
        self.papers(f'install --force --local --no-git --bibtex {self.mybib} --files {self.filesdir}')
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        legacy = os.path.join(BACKUP_DIR, 'references-never-created')
        config.gitdir = legacy
        config.save()

        self.papers(f'install --local --edit --git')
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertNotEqual(config.gitdir, legacy)
        self.assertTrue(os.path.isdir(config.gitdir))
        self.assertFalse(os.path.exists(legacy))

    def test_edit_keeps_existing_gitdir(self):
        from papers.config import BACKUP_DIR
        self.papers(f'install --force --local --no-git --bibtex {self.mybib} --files {self.filesdir}')
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        legacy = os.path.join(BACKUP_DIR, 'references')
        os.makedirs(legacy)
        config.gitdir = legacy
        config.save()

        self.papers(f'install --local --edit --git')
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.gitdir, legacy)
        self.assertTrue((Path(legacy)/'.git').is_dir())

    def test_edit_no_duplicate_bibtex_candidates(self):
        # the configured (absolute) bibtex and the same file found by the
        # directory scan must not be reported as several files
        from papers import logger
        self.papers(f'install --force --local --no-git --bibtex {self.anotherbib} --files {self.filesdir}')
        with self.assertLogs(logger, level='WARNING') as cm:
            logger.warning('sentinel')  # assertLogs requires at least one record
            self.papers(f'install --local --edit --no-git')
        self.assertFalse(any('Several bibtex files' in line for line in cm.output), cm.output)



class TestUninstall(LocalInstallTest):
    def test_uninstall(self):
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.papers(f'uninstall')
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))

    def test_uninstall_reports_leftovers(self):
        out = self.papers('uninstall', sp_cmd='check_output')
        self.assertIn('the bibliography remains', out)
        # the bibtex and files are not touched
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))


class TestUninstallRemoveBackup(LocalGitLFSInstallTest):
    def test_uninstall_remove_backup(self):
        gitdir = self.config.gitdir
        self.assertTrue(os.path.isdir(gitdir))
        out = self.papers('uninstall --remove-backup', sp_cmd='check_output')
        self.assertIn('removed backup directory', out)
        self.assertFalse(os.path.exists(gitdir))
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))


class TestStatus(LocalInstallTest):
    """papers status -v shows configuration (documented in README)"""
    def test_status_verbose(self):
        out = self.papers('status -v', sp_cmd='check_output')
        self.assertIn('configuration', out.lower())
        self.assertIn(self.mybib, out)
        self.assertIn(self.filesdir, out)


class TestUninstall2(GlobalInstallTest):
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