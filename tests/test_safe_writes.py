"""Safe writes (#119): the bibtex is replaced in one step, and not written
when another program wrote it since papers read it"""
import os
import stat
import tempfile
import unittest
from pathlib import Path

from papers.bib import Biblio, BibtexChanged
from papers.utils import write_atomic

BIB = "@article{a,\n title = {A}\n}\n"
OTHER = "@article{b,\n title = {B}\n}\n"


class TestWriteAtomic(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_write(self):
        path = os.path.join(self.dir, 'a.bib')
        write_atomic(path, 'one')
        Path(path).chmod(0o640)
        write_atomic(path, 'two')
        self.assertEqual(Path(path).read_text(), 'two')
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o640)
        self.assertEqual(os.listdir(self.dir), ['a.bib'])  # no temporary file left

    def test_symlink(self):
        target = os.path.join(self.dir, 'target.bib')
        link = os.path.join(self.dir, 'link.bib')
        Path(target).write_text('one')
        os.symlink(target, link)
        write_atomic(link, 'two')
        self.assertTrue(os.path.islink(link))
        self.assertEqual(Path(target).read_text(), 'two')


class TestChangedSinceRead(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.bibtex = os.path.join(self.temp_dir.name, 'papers.bib')
        Path(self.bibtex).write_text(BIB)
        self.biblio = Biblio.load(self.bibtex, None)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_refused(self):
        Path(self.bibtex).write_text(OTHER)
        self.biblio.add_bibtex("@article{c,\n title = {C}\n}\n")
        self.assertRaises(BibtexChanged, self.biblio.save, self.bibtex)
        self.assertEqual(Path(self.bibtex).read_text(), OTHER)

    def test_same_content(self):
        # rewritten with the same content (e.g. by a sync client): saved
        Path(self.bibtex).write_text(BIB)
        os.utime(self.bibtex, ns=(1, 1))
        self.biblio.add_bibtex("@article{c,\n title = {C}\n}\n")
        self.biblio.save(self.bibtex)
        self.assertIn('@article{c,', Path(self.bibtex).read_text())

    def test_saved_twice(self):
        # the second save of a command compares with the first
        self.biblio.add_bibtex("@article{c,\n title = {C}\n}\n")
        self.biblio.save(self.bibtex)
        self.biblio.add_bibtex("@article{d,\n title = {D}\n}\n")
        self.biblio.save(self.bibtex)
        self.assertIn('@article{d,', Path(self.bibtex).read_text())
