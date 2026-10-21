"""File moves and configuration paths (no network: dummy files, bibtex input)"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from papers.bib import Biblio
from papers.config import Config, CONFIG_FILE_LOCAL
from papers.utils import move
from tests.common import paperscmd, BibTest


ENTRY = """@article{smith2020,
 author = {Smith, John},
 title = {A test},
 year = {2020},
 file = {:a.pdf:pdf}
}
"""


class TestMoveSameFile(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir = self.temp_dir.name
        self.file = os.path.join(self.dir, 'a.pdf')
        Path(self.file).write_text('a')

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_relative_vs_absolute(self):
        cwd = os.getcwd()
        os.chdir(self.dir)
        try:
            move(self.file, 'a.pdf', interactive=False)
        finally:
            os.chdir(cwd)
        self.assertTrue(os.path.exists(self.file))

    def test_symlinked_directory(self):
        link = os.path.join(self.dir, 'link')
        os.symlink(self.dir, link)
        move(self.file, os.path.join(link, 'a.pdf'), interactive=False)
        self.assertTrue(os.path.exists(self.file))

    def test_hardlink_is_moved(self):
        other = os.path.join(self.dir, 'b.pdf')
        os.link(self.file, other)
        move(self.file, other, interactive=False)
        self.assertFalse(os.path.exists(self.file))
        self.assertEqual(Path(other).read_text(), 'a')


class TestRenameInPlace(BibTest):
    """rename files already at their place, with a relative --filesdir"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir = self.temp_dir.name
        Path(self.dir, 'a.pdf').write_text('a')
        Path(self.dir, 'b.pdf').write_text('b')
        Path(self.dir, 'in.bib').write_text(ENTRY)
        Path(self.dir, 'lib.bib').write_text('')
        self.opts = '--bibtex lib.bib --filesdir files --relative-paths --no-git'

    def tearDown(self):
        self.temp_dir.cleanup()

    def papers(self, cmd):
        return paperscmd(f'{cmd} {self.opts}', cwd=self.dir)

    def files(self):
        biblio = Biblio.load(os.path.join(self.dir, 'lib.bib'), None)
        return biblio.get_files(biblio.entries[0])

    def assertFilesExist(self, n):
        files = self.files()
        self.assertEqual(len(files), n)
        for f in files:
            self.assertTrue(os.path.exists(f), f)

    def test_single_file(self):
        self.papers('add in.bib --rename')
        self.assertFilesExist(1)
        self.papers('filecheck --rename')
        self.assertFilesExist(1)
        self.papers('list --rename')
        self.assertFilesExist(1)

    def test_several_files(self):
        self.papers('add in.bib --rename')
        self.papers('list --add-files b.pdf --rename')
        self.assertFilesExist(2)
        self.papers('filecheck --rename')
        self.assertFilesExist(2)
        self.papers('list --rename')
        self.assertFilesExist(2)


class TestLocalConfigSubfolder(BibTest):
    """local configuration whose bibtex lives in a subfolder"""

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

    def test_save_from_another_directory(self):
        configfile = os.path.join(self.dir, CONFIG_FILE_LOCAL)
        config = Config(file=configfile, local=True,
                        bibtex=os.path.join(self.dir, 'refs', 'papers.bib'),
                        filesdir=os.path.join(self.dir, 'files'))
        config.save()
        js = json.load(open(configfile))
        self.assertEqual(js['bibtex'], os.path.join('refs', 'papers.bib'))
        self.assertEqual(js['filesdir'], 'files')
