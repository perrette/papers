import unittest
import os
import tempfile
import shutil

from papers.extract import extract_pdf_metadata
from papers.entries import parse_string

from papers.bib import Biblio
from tests.common import paperscmd, prepare_paper, prepare_paper2, BibTest


class TestSimple(unittest.TestCase):

    def setUp(self):
        (
            self.pdf,
            self.doi,
            self.key,
            self.newkey,
            self.year,
            self.bibtex,
            self.file_rename,
        ) = prepare_paper()
        self.assertTrue(os.path.exists(self.pdf))

    def test_doi(self):
        self.assertEqual(
            paperscmd(f"doi {self.pdf}", sp_cmd="check_output").strip(), self.doi
        )

    def test_fetch(self):
        bibtexs = paperscmd(f"fetch {self.doi}", sp_cmd="check_output").strip()
        db1 = parse_string(bibtexs)
        db2 = parse_string(self.bibtex)
        self.assertEqual(
            [dict(e.items()) for e in db1.entries],
            [dict(e.items()) for e in db2.entries],
        )

    def test_fetch_scholar(self):
        extract_pdf_metadata(self.pdf, scholar=True)


class TestAddDir(BibTest):
    # TODO delete this later
    def setUp(self):
        (
            self.pdf1,
            self.doi,
            self.key1,
            self.newkey1,
            self.year,
            self.bibtex1,
            self.file_rename1,
        ) = prepare_paper()
        (
            self.pdf2,
            self.si,
            self.doi,
            self.key2,
            self.newkey2,
            self.year,
            self.bibtex2,
            self.file_rename2,
        ) = prepare_paper2()
        self.somedir = tempfile.mktemp(prefix="papers.somedir")
        self.subdir = os.path.join(self.somedir, "subdir")
        os.makedirs(self.somedir)
        os.makedirs(self.subdir)
        shutil.copy(self.pdf1, self.somedir)
        shutil.copy(self.pdf2, self.subdir)
        self.mybib = tempfile.mktemp(prefix="papers.bib")
        paperscmd(f"install --local --no-prompt --bibtex {self.mybib}")

    def test_adddir_pdf(self):
        self.my = Biblio.load(self.mybib, "")
        self.my.scan_dir(self.somedir)
        self.assertEqual(len(self.my.db.entries), 2)
        keys = [self.my.db.entries[0]["ID"], self.my.db.entries[1]["ID"]]
        self.assertEqual(
            sorted(keys), sorted([self.newkey1, self.newkey2])
        )  # PDF: update key

    def test_adddir_pdf_cmd(self):
        paperscmd(f"add --recursive --bibtex {self.mybib} {self.somedir}")
        self.my = Biblio.load(self.mybib, "")
        self.assertEqual(len(self.my.db.entries), 2)
        keys = [self.my.db.entries[0]["ID"], self.my.db.entries[1]["ID"]]
        self.assertEqual(
            sorted(keys), sorted([self.newkey1, self.newkey2])
        )  # PDF: update key

    def tearDown(self):
        os.remove(self.mybib)
        shutil.rmtree(self.somedir)
        paperscmd(f"uninstall")


class TestRecursiveExtract(unittest.TestCase):

    def setUp(self):
        (
            self.pdf1,
            self.doi1,
            self.key1,
            self.newkey1,
            self.year1,
            self.bibtex1,
            self.file_rename1,
        ) = prepare_paper()
        (
            self.pdf2,
            self.si2,
            self.doi2,
            self.key2,
            self.newkey2,
            self.year2,
            self.bibtex2,
            self.file_rename2,
        ) = prepare_paper2()
        self.somedir = tempfile.mktemp(prefix="papers.somedir")
        self.subdir = os.path.join(self.somedir, "subdir")
        os.makedirs(self.somedir)
        os.makedirs(self.subdir)
        shutil.copy(self.pdf1, self.somedir)
        shutil.copy(self.pdf2, self.subdir)
        self.mybib = tempfile.mktemp(prefix="papers.bib")
        paperscmd(f"install --local --no-prompt --bibtex {self.mybib}")
        self.assertTrue(os.path.exists(self.pdf1))
        self.assertTrue(os.path.exists(self.pdf2))

    def test_doi(self):
        self.assertEqual(
            paperscmd(f"doi {self.pdf1}", sp_cmd="check_output").strip(), self.doi1
        )

    def test_fetch(self):
        bibtexs = paperscmd(f"extract {self.pdf1}", sp_cmd="check_output").strip()
        db1 = parse_string(bibtexs)
        db2 = parse_string(self.bibtex1)
        self.assertEqual(
            [dict(e.items()) for e in db1.entries],
            [dict(e.items()) for e in db2.entries],
        )

    def tearDown(self):
        os.remove(self.mybib)
        shutil.rmtree(self.somedir)
        paperscmd(f"uninstall")
