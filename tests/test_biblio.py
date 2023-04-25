import os
import unittest
import tempfile
from papers.bib import Biblio
from tests.common import prepare_paper

class TestBiblio(unittest.TestCase):

    def setUp(self):
        self.mybib = tempfile.mktemp(prefix='papers.bib')
        # self.somebib = tempfile.mktemp(prefix='papers.somebib.bib')
        self.pdf, self.doi, self.key, self.newkey, self.year, self.bibtex, self.file_rename = prepare_paper()
        open(self.mybib,'w').write(self.bibtex)
        self.biblio = Biblio.load(self.mybib, '')

    def test_bib_equal(self):
        self.assertTrue(self.biblio == self.biblio)

    def tearDown(self):
        os.remove(self.mybib)
        # os.remove(self.somebib)