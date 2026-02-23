import unittest
import os
import tempfile
import shutil
import re
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

    def test_fetch(self):
        bibtexs = paperscmd(
            f"extract --recursive {self.somedir}", sp_cmd="check_output"
        ).strip()
        the_right_answer = """@article{10.5194/bg-8-515-2011,
        author = {Perrette, M. and Yool, A. and Quartly, G. D. and Popova, E. E.},
        doi = {10.5194/bg-8-515-2011},
        journal = {Biogeosciences},
        number = {2},
        pages = {515-524},
        title = {Near-ubiquity of ice-edge blooms in the Arctic},
        url = {https://doi.org/10.5194/bg-8-515-2011},
        volume = {8},
        year = {2011}
        }
        
        @article{10.5194/esd-4-11-2013,
        author = {Perrette, M. and Landerer, F. and Riva, R. and Frieler, K. and Meinshausen, M.},
        doi = {10.5194/esd-4-11-2013},
        journal = {Earth System Dynamics},
        number = {1},
        pages = {11-29},
        title = {A scaling approach to project regional sea level rise and its uncertainties},
        url = {https://doi.org/10.5194/esd-4-11-2013},
        volume = {4},
        year = {2013}
        }
        """
        processed_bibtexs = re.sub(r"\s+", "", bibtexs)
        processed_the_right_answer = re.sub(r"\s+", "", the_right_answer)
        self.assertEqual(processed_bibtexs, processed_the_right_answer)

    def tearDown(self):
        os.remove(self.mybib)
        shutil.rmtree(self.somedir)
        paperscmd(f"uninstall")
