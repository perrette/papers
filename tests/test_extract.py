import unittest
import os

from papers.extract import extract_pdf_metadata
from papers.bib import bibtexparser
from tests.common import paperscmd, prepare_paper


class TestSimple(unittest.TestCase):

    def setUp(self):
        self.pdf, self.doi, self.key, self.newkey, self.year, self.bibtex, self.file_rename = prepare_paper()
        self.assertTrue(os.path.exists(self.pdf))

    def test_doi(self):
        self.assertEqual(paperscmd(f'doi {self.pdf}', sp_cmd='check_output').strip(), self.doi)

    def test_fetch(self):
        bibtexs = paperscmd(f'fetch {self.doi}', sp_cmd='check_output').strip()
        db1 = bibtexparser.loads(bibtexs)
        db2 = bibtexparser.loads(self.bibtex)
        self.assertEqual(db1.entries, db2.entries)

    def test_fetch_scholar(self):
        extract_pdf_metadata(self.pdf, scholar=True)