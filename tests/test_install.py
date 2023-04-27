import os
import json
import shutil
import tempfile
import unittest
import subprocess as sp
from papers.config import Config, search_config
from papers.config import CONFIG_FILE
from papers.bib import Biblio
# from pathlib import Path

from tests.common import paperscmd, prepare_paper, run, PAPERSCMD

bibtex = """@article{Perrette_2011,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 doi = {10.5194/bg-8-515-2011},
 journal = {Biogeosciences},
 link = {https://doi.org/10.5194%2Fbg-8-515-2011},
 month = {feb},
 number = {2},
 pages = {515--524},
 publisher = {Copernicus {GmbH}},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
 volume = {8},
 year = {2011}
}"""

bibtex2 = """@article{SomeOneElse2000,
 author = {Some One},
 doi = {10.5194/xxxx},
 title = {Interesting Stuff},
 year = {2000}
}"""

class TestBaseInstall(unittest.TestCase):

    def setUp(self):
        if os.path.exists(CONFIG_FILE):
            self.backup = tempfile.mktemp(prefix='papers.bib.backup')
            shutil.move(CONFIG_FILE, self.backup)
        else:
            self.backup = None

        self.temp_dir = tempfile.TemporaryDirectory()
        self.mybib = "papersxyz.bib"
        self.filesdir = "filesxyz"
        self.anotherbib = 'another.bib'
        open(self._path(self.anotherbib), 'w').write(bibtex)

    # def tearDown(self):
    #     if os.path.exists(CONFIG_FILE):
    #         os.remove(CONFIG_FILE)
    #     if self.backup:
    #         shutil.move(self.backup, CONFIG_FILE)
    #     self.temp_dir.cleanup()


    def _path(self, p):
        return os.path.join(self.temp_dir.name, p)

    def _exists(self, p):
        return os.path.exists(os.path.join(self.temp_dir.name, p))

    def papers(self, cmd, **kw):
        return paperscmd(f'{cmd}', cwd=self.temp_dir.name, **kw)



class TestLocalInstall(TestBaseInstall):

    def test_install(self):
        self.assertFalse(self._exists(self.mybib))
        self.assertFalse(self._exists(self.filesdir))
        self.papers(f'install --force --local --bibtex {self.mybib} --files {self.filesdir}')
        # Config file was created:
        self.assertTrue(self._exists(".papers/config.json"))
        # Values of config file match input:
        config = Config.load(self._path(".papers/config.json"))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.assertFalse(config.git)
        # bibtex and files directory were created:
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))


    def test_install_defaults_no_preexisting_bibtex(self):
        self.assertFalse(self._exists(self.mybib))
        self.assertFalse(self._exists(self.filesdir))
        self.assertFalse(self._exists(".papers/config.json"))
        # pre-existing bibtex?
        os.remove(self._path(self.anotherbib))
        self.assertFalse(self._exists(self.anotherbib))
        self.papers(f'install --force --local')
        self.assertTrue(self._exists(".papers/config.json"))
        config = Config.load(self._path(".papers/config.json"))
        # self.assertEqual(config.bibtex, os.path.abspath(self._path("papers.bib")))
        self.assertEqual(config.bibtex, os.path.abspath(self._path("papers.bib")))
        self.assertEqual(config.filesdir, os.path.abspath(self._path("files")))
        self.assertFalse(config.git)


    def test_install_defaults_preexisting_bibtex(self):
        self.assertFalse(self._exists(self.mybib))
        self.assertFalse(self._exists(self.filesdir))
        self.assertFalse(self._exists(".papers/config.json"))
        # pre-existing bibtex
        self.assertTrue(self._exists(self.anotherbib))
        self.assertFalse(self._exists("papers.bib"))
        self.papers(f'install --force --local')
        self.assertTrue(self._exists(".papers/config.json"))
        config = Config.load(self._path(".papers/config.json"))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.anotherbib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path("files")))
        self.assertFalse(config.git)


    def test_install_defaults_preexisting_pdfs(self):
        self.assertFalse(self._exists(self.filesdir))
        self.assertFalse(self._exists(".papers/config.json"))
        # pre-existing pdfs folder (pre-defined set of names)
        os.makedirs(self._path("pdfs"))
        self.papers(f'install --force --local')
        self.assertTrue(self._exists(".papers/config.json"))
        config = Config.load(self._path(".papers/config.json"))
        # self.assertEqual(config.bibtex, os.path.abspath(self._path("papers.bib")))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.anotherbib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path("pdfs")))
        self.assertFalse(config.git)

    def test_install_raise(self):
        self.papers(f'install --force --local --bibtex {self.mybib} --files {self.filesdir}')
        self.assertTrue(self._exists(".papers/config.json"))
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))
        f = lambda : self.papers(f'install --local --bibtex {self.mybib} --files {self.filesdir}')
        self.assertRaises(Exception, f)

    def test_install_force(self):
        self.papers(f'install --force --local --bibtex {self.mybib} --files {self.filesdir}')
        self.assertTrue(self._exists(".papers/config.json"))
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))
        config = Config.load(self._path(".papers/config.json"))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.papers(f'install --local --force --bibtex {self.mybib}XX')
        config = Config.load(self._path(".papers/config.json"))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib + "XX")))
        # The files folder from previous install was forgotten
        self.assertEqual(config.filesdir, os.path.abspath(self._path("files")))
        self.assertFalse(config.git)

    def test_install_edit(self):
        self.papers(f'install --force --local --bibtex {self.mybib} --files {self.filesdir}')
        self.assertTrue(self._exists(".papers/config.json"))
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))
        config = Config.load(self._path(".papers/config.json"))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.papers(f'install --local --edit --bibtex {self.mybib}XX')
        config = Config.load(self._path(".papers/config.json"))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib + "XX")))
        # The files folder from previous install is remembered
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.assertFalse(config.git)

    def test_install_interactive(self):
        # fully interactive install
        sp.check_call(f"""{PAPERSCMD} install --local << EOF
{self.mybib}
{self.filesdir}
n
EOF""", shell=True, cwd=self.temp_dir.name)
        self.assertTrue(self._exists(".papers/config.json"))
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))
        config = Config.load(self._path(".papers/config.json"))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.assertFalse(config.git)

        # Now try simple carriage return (select default)
        sp.check_call(f"""{PAPERSCMD} install --local << EOF
e



EOF""", shell=True, cwd=self.temp_dir.name)
        self.assertTrue(self._exists(".papers/config.json"))
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))
        config = Config.load(self._path(".papers/config.json"))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))

        # edit existing install (--edit)
        sp.check_call(f"""{PAPERSCMD} install --local --bibtex {self.mybib}XX << EOF
e
y
n
EOF""", shell=True, cwd=self.temp_dir.name)
        config = Config.load(self._path(".papers/config.json"))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib + "XX")))
        # The files folder from previous install is remembered
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.assertFalse(config.git)

        # overwrite existing install (--force)
        sp.check_call(f"""{PAPERSCMD} install --local --bibtex {self.mybib}XX << EOF
o
y
n
EOF""", shell=True, cwd=self.temp_dir.name)
        config = Config.load(self._path(".papers/config.json"))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib + "XX")))
        # The files folder from previous install was forgotten
        self.assertEqual(config.filesdir, os.path.abspath(self._path("files")))
        self.assertFalse(config.git)

        # reset default values from install
        sp.check_call(f"""{PAPERSCMD} install --local << EOF
e
reset
reset
n
EOF""", shell=True, cwd=self.temp_dir.name)
        config = Config.load(self._path(".papers/config.json"))
        self.assertEqual(config.bibtex, None)
        # The files folder from previous install was forgotten
        self.assertEqual(config.filesdir, None)
        self.assertFalse(config.git)

        # install with git tracking
        sp.check_call(f"""{PAPERSCMD} install --local << EOF
e
reset
reset
y
y
EOF""", shell=True, cwd=self.temp_dir.name)
        config = Config.load(self._path(".papers/config.json"))
        self.assertEqual(config.bibtex, None)
        # The files folder from previous install was forgotten
        self.assertEqual(config.filesdir, None)
        self.assertTrue(config.git)
        self.assertTrue(config.gitlfs)


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

    def test_install(self):
        self.papers(f'install --local --no-prompt --bibtex {self.mybib} --files {self.filesdir} --git')
        self.assertTrue(self._exists(self.mybib))
        # self.assertTrue(self._exists(".git"))
        # count = sp.check_output(f'cd {self.temp_dir.name} && git rev-list --all --count', shell=True).strip().decode()
        # self.assertEqual(count, '0')
        count = self.papers('git rev-list --all --count')
        self.papers(f'add {self.anotherbib}')
        # self.papers(f'add --doi 10.5194/bg-8-515-2011')
        count2 = self.papers('git rev-list --all --count')
        # The part below fails on github CI, I cannot explain why
        self.assertEqual(int(count2), int(count)+1)
        # self.papers(f'git log', sp_cmd='check_call')


    def test_undo(self):
        self.papers(f'install --local --no-prompt --bibtex {self.mybib} --files {self.filesdir} --git --git-lfs')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 0)
        self.papers(f'add {self.anotherbib}')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)

        open(self._path('yetanother'), 'w').write(bibtex2)
        self.papers(f'add yetanother')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 2)

        self.papers(f'undo')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)

        self.papers(f'undo')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 0)

        self.papers(f'redo')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)

        self.papers(f'redo')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 2)

        self.papers(f'redo')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 2)