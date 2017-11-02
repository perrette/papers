from __future__ import print_function, absolute_import

import unittest
import os, subprocess as sp
import tempfile, shutil

from utils import myref
from myref.bib import MyRef, bibtexparser
from download import downloadpdf


def run(cmd):
    print(cmd)
    return sp.check_output(cmd, shell=True)

def prepare_paper():
    pdf = downloadpdf('bg-8-515-2011.pdf')
    doi = '10.5194/bg-8-515-2011'
    bibtex = """@article{Perrette_2011,
    doi = {10.5194/bg-8-515-2011},
    url = {https://doi.org/10.5194%2Fbg-8-515-2011},
    year = 2011,
    month = {feb},
    publisher = {Copernicus {GmbH}},
    volume = {8},
    number = {2},
    pages = {515--524},
    author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
    title = {Near-ubiquity of ice-edge blooms in the Arctic},
    journal = {Biogeosciences}
}"""
# .replace('\t','    ')
    return pdf, doi, bibtex

class TestSimple(unittest.TestCase):

    def setUp(self):
        self.pdf, self.doi, self.bibtex = prepare_paper()

    def test_doi(self):
        self.assertEqual(run('myref doi '+self.pdf).strip(), self.doi)

    def test_fetch(self):
        bibtexs = run('myref fetch '+self.doi).strip()
        db1 = bibtexparser.loads(bibtexs)
        db2 = bibtexparser.loads(self.bibtex)
        self.assertEqual(db1.entries, db2.entries)
	    

class TestAdd(unittest.TestCase):

    def setUp(self):
        self.pdf, self.doi, self.bibtex = prepare_paper()
        self.mybib = tempfile.mktemp(prefix='myref.bib')
        self.filesdir = tempfile.mktemp(prefix='myref.files')
        

    def _checkbib(self):
        db1 = bibtexparser.load(open(self.mybib))
        file = db1.entries[0].pop('file').strip()
        file, type = file.split(':')
        self.assertEqual(type, 'pdf') # file type is PDF
        self.assertTrue(os.path.exists(file))  # file link is valid

        db2 = bibtexparser.loads(self.bibtex)
        self.assertEqual(db1.entries, db2.entries) # entry is as expected
        return file


    def test_add(self):

        sp.check_call('myref add --bibtex {} {}'.format(
            self.mybib, self.pdf), shell=True)

        file = self._checkbib()
        self.assertEqual(file, self.pdf)
        self.assertTrue(os.path.exists(self.pdf)) # old pdf still exists


    def test_add_rename_copy(self):

        sp.check_call('myref add -rc --bibtex {} --filesdir {} {}'.format(
            self.mybib, self.filesdir, self.pdf), shell=True)

        file = self._checkbib()
        self.assertEqual(file, os.path.join(self.filesdir,'2011','Perrette_2011.pdf'))
        self.assertTrue(os.path.exists(self.pdf)) # old pdf still exists

    def test_add_rename(self):

        pdfcopy = tempfile.mktemp(prefix='myref_test', suffix='.pdf')
        shutil.copy(self.pdf, pdfcopy)

        sp.check_call('myref add -r --bibtex {} --filesdir {} {}'.format(
            self.mybib, self.filesdir, pdfcopy), shell=True)

        file = self._checkbib()
        self.assertEqual(file, os.path.join(self.filesdir,'2011','Perrette_2011.pdf'))
        self.assertFalse(os.path.exists(pdfcopy))

    def tearDown(self):
        if os.path.exists(self.filesdir):
            shutil.rmtree(self.filesdir)
        os.remove(self.mybib)


if __name__ == '__main__':
    unittest.main()
