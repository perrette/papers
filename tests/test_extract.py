import unittest
import os

from papers.extract import extract_pdf_metadata
from papers.bibtexparser_compat import parse_string
from tests.common import paperscmd, prepare_paper


class TestSimple(unittest.TestCase):

    def setUp(self):
        self.pdf, self.doi, self.key, self.newkey, self.year, self.bibtex, self.file_rename = prepare_paper()
        self.assertTrue(os.path.exists(self.pdf))

    def test_doi(self):
        self.assertEqual(paperscmd(f'doi {self.pdf}', sp_cmd='check_output').strip(), self.doi)

    def test_fetch(self):
        bibtexs = paperscmd(f'fetch {self.doi}', sp_cmd='check_output').strip()
        db1 = parse_string(bibtexs)
        db2 = parse_string(self.bibtex)
        self.assertEqual([dict(e.items()) for e in db1.entries], [dict(e.items()) for e in db2.entries])

    def test_fetch_scholar(self):
        extract_pdf_metadata(self.pdf, scholar=True)