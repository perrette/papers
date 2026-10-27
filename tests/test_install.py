"""papers install, deprecated in v3 (an alias of init, or an update of the
library configuration; install --global is an error): to remove with the
command in v4"""
import os
from pathlib import Path
import json
import tempfile
import subprocess as sp
from papers.config import Config
from papers.config import CONFIG_FILE, CONFIG_FILE_LOCAL

import papers.config
from papers.utils import PapersExit
from tests.common import (paperscmd, PAPERSCMD, BaseTest as TestBaseInstall, BibTest, ConfigTest,
                          InitTest, GitLFSInitTest)


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
        self.papers('install --force --local')
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
        self.papers('install --force --local')
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
        self.papers('install --force --local')
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
        self.papers("""install --local --filesdir files << EOF
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
        self.papers('install --force --local --editor "subl -w"')
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.editor, "subl -w")


class TestDefaultLocal(InitTest):
    def test_install(self):
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertFalse(self.config.shallow)
        self.papers('install --edit')
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertFalse(config.shallow)

class TestDefaultScopeIsLocal(TestBaseInstall):
    def test_fresh_install_is_local(self):
        # a fresh install without scope option is local; an existing install
        # keeps its scope (covered by TestDefaultLocal2)
        self.papers(f'install --no-prompt --bibtex {self.mybib} --files {self.filesdir}')
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertFalse(os.path.exists(CONFIG_FILE))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertFalse(config.shallow)


class TestGlobalInstall(TestBaseInstall):

    def test_install_global_is_an_error(self):
        machine = open(papers.config.MACHINE_CONFIG_FILE).read()
        with self.assertRaises(PapersExit) as cm:
            self.papers(f'install --no-prompt --global --bibtex {self.mybib} --files {self.filesdir}')
        self.assertIn('`papers init PATH --global`', str(cm.exception))
        self.assertIn('papers init ~/Documents/papers/default --global', str(cm.exception))
        self.assertIn('`papers config --global default PATH`', str(cm.exception))
        # nothing was changed
        self.assertFalse(self._exists(self.mybib))
        self.assertFalse(self._exists(self.filesdir))
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))
        self.assertFalse(os.path.exists(CONFIG_FILE))
        self.assertEqual(open(papers.config.MACHINE_CONFIG_FILE).read(), machine)


class TestGitInstall(TestBaseInstall):

    def test_install_gitlfs(self):
        self.papers('install --local --no-prompt --git-lfs')
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
        self.papers("""install --local --filesdir files --bibtex bibbib.bib << EOF
y
y
EOF""")
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertTrue(config.git)
        self.assertTrue(config.gitlfs)

    def test_install_interactive2(self):
        self.papers("""install --local --filesdir files --bibtex bibbib.bib << EOF
y
n
EOF""")
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertTrue(config.git)
        self.assertFalse(config.gitlfs)

    def test_install_interactive3(self):
        self.papers("""install --local --filesdir files --bibtex bibbib.bib << EOF
n
EOF""")
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertFalse(config.git)
        self.assertFalse(config.gitlfs)

    def test_install_interactive4(self):
        # plain Enter selects the defaults: git on (fresh install), git-lfs off
        self.papers("""install --local --filesdir files --bibtex bibbib.bib << EOF


EOF""")
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertTrue(config.git)
        self.assertFalse(config.gitlfs)

    def test_install_no_git(self):
        self.papers('install --force --local --no-git --bibtex bibbib.bib --filesdir files')
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertFalse(config.git)
        self.assertFalse(config.gitlfs)

    def test_install_interactive5(self):
        self.papers("""install --local --filesdir files --bibtex bibbib.bib << EOF
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

    def write_gitdir(self, value):
        "the backup folder that the configuration of papers 3.0.0b2 named"
        js = json.load(open(self._path(CONFIG_FILE_LOCAL)))
        js['gitdir'] = value
        json.dump(js, open(self._path(CONFIG_FILE_LOCAL), 'w'))

    def test_edit_with_a_missing_central_gitdir(self):
        self.papers(f'install --force --local --no-git --bibtex {self.mybib} --files {self.filesdir}')
        self.write_gitdir('references-never-created')
        self.papers('install --local --edit --git')
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.gitdir, os.path.join(self._path('.papers'), 'backup'))
        self.assertTrue(os.path.isdir(os.path.join(config.gitdir, '.git')))
        self.assertNotIn('gitdir', json.load(open(self._path(CONFIG_FILE_LOCAL))))

    def test_edit_adopts_the_central_gitdir(self):
        from papers.backup import git_init
        from papers.config import BACKUP_DIR
        self.papers(f'install --force --local --no-git --bibtex {self.mybib} --files {self.filesdir}')
        legacy = os.path.join(BACKUP_DIR, 'references')
        os.makedirs(legacy)
        git_init(legacy)
        self.write_gitdir('references')
        self.papers('install --local --edit --git')
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.gitdir, os.path.join(self._path('.papers'), 'backup'))
        self.assertTrue(os.path.isdir(os.path.join(config.gitdir, '.git')))
        self.assertFalse(os.path.exists(legacy))

    def test_edit_no_duplicate_bibtex_candidates(self):
        # the configured (absolute) bibtex and the same file found by the
        # directory scan must not be reported as several files
        from papers import logger
        self.papers(f'install --force --local --no-git --bibtex {self.anotherbib} --files {self.filesdir}')
        with self.assertLogs(logger, level='WARNING') as cm:
            logger.warning('sentinel')  # assertLogs requires at least one record
            self.papers('install --local --edit --no-git')
        self.assertFalse(any('Several bibtex files' in line for line in cm.output), cm.output)



class TestUninstall(InitTest):
    def test_uninstall(self):
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.papers('uninstall')
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))

    def test_uninstall_reports_leftovers(self):
        out = self.papers('uninstall', sp_cmd='check_output')
        self.assertIn('the bibliography remains', out)
        # the bibtex and files are not touched
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))


class TestUninstallRemoveBackup(GitLFSInitTest):
    def test_uninstall_remove_backup(self):
        gitdir = self.config.gitdir
        self.assertTrue(os.path.isdir(gitdir))
        out = self.papers('uninstall --remove-backup', sp_cmd='check_output')
        self.assertIn('removed backup directory', out)
        self.assertFalse(os.path.exists(gitdir))
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))


class TestStatus(InitTest):
    """papers status -v shows configuration (documented in README)"""
    def test_status_verbose(self):
        out = self.papers('status -v', sp_cmd='check_output')
        self.assertIn('configuration', out.lower())
        self.assertIn(self.mybib, out)
        self.assertIn(self.filesdir, out)

    def test_status_counts_file_links(self):
        self.papers(f'add {self.anotherbib}')
        out = self.papers('status -v', sp_cmd='check_output')
        # one entry, no attachment
        self.assertIn('1 entries, 0 file links', out)


class TestUninstall2(InitTest):
    """uninstall --recursive (deprecated) is ignored: only the configuration
    of the library is removed, not those found upwards nor the v2 global one"""
    def test_uninstall(self):
        import papers.config
        os.makedirs(self._path('sub'))
        paperscmd('init --no-git', cwd=self._path('sub'))
        self.assertTrue(self._exists(os.path.join('sub', CONFIG_FILE_LOCAL)))
        json.dump({'bibtex': self._path(self.mybib), 'local': False}, open(CONFIG_FILE, 'w'))
        machine = open(papers.config.MACHINE_CONFIG_FILE).read()

        paperscmd('uninstall', cwd=self._path('sub'))
        self.assertFalse(self._exists(os.path.join('sub', CONFIG_FILE_LOCAL)))
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(os.path.exists(CONFIG_FILE))

        paperscmd('init --no-git', cwd=self._path('sub'))
        with self.assertLogs("papers", level="WARNING") as logs:
            paperscmd("uninstall --recursive", cwd=self._path("sub"))
        self.assertIn("deprecated and ignored", "\n".join(logs.output))
        self.assertFalse(self._exists(os.path.join('sub', CONFIG_FILE_LOCAL)))
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(os.path.exists(CONFIG_FILE))
        self.assertEqual(open(papers.config.MACHINE_CONFIG_FILE).read(), machine)


class TestInstallIsInit(ConfigTest):

    def test_install_is_init(self):
        self.papers('install --no-prompt --no-git')
        self.assertEqual(self.json()['pool'], 'none')  # self-contained, as with init
        self.assertNotIn('local', self.json())


class TestReinstallSubfolder(BibTest):
    """local configuration whose bibtex lives in a subfolder, updated with install"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir = self.temp_dir.name
        os.makedirs(os.path.join(self.dir, 'refs'))
        Path(self.dir, 'refs', 'papers.bib').write_text('')

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_reinstall_keeps_paths(self):
        paperscmd('install --local --no-prompt --no-git --bibtex refs/papers.bib --filesdir files', cwd=self.dir)
        configfile = os.path.join(self.dir, CONFIG_FILE_LOCAL)
        for _ in range(2):
            js = json.load(open(configfile))
            self.assertEqual(js['bibtex'], os.path.join('refs', 'papers.bib'))
            self.assertEqual(js['filesdir'], 'files')
            config = Config.load(configfile)
            self.assertEqual(Path(config.bibtex), Path(self.dir, 'refs', 'papers.bib').resolve())
            self.assertEqual(Path(config.filesdir), Path(self.dir, 'files').resolve())
            # update the install
            paperscmd('install --no-prompt --editor vim', cwd=self.dir)
