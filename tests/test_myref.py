from __future__ import print_function, absolute_import

import unittest
import os, subprocess as sp
import tempfile, shutil

from myref.bib import MyRef, bibtexparser, parse_file, format_file
from download import downloadpdf


def run(cmd):
    print(cmd)
    return str(sp.check_output(cmd, shell=True).strip().decode())

def prepare_paper():
    pdf = downloadpdf('bg-8-515-2011.pdf')
    doi = '10.5194/bg-8-515-2011'
    key = 'Perrette_2011'
    year = '2011'
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
    return pdf, doi, key, year, bibtex

def prepare_paper2():
    pdf = downloadpdf('esd-4-11-2013.pdf')
    si = downloadpdf('esd-4-11-2013-supplement.pdf')
    doi = '10.5194/esd-4-11-2013'
    key = 'Perrette_2013'
    year = '2013'
    bibtex = """@article{Perrette_2013,
    doi = {10.5194/esd-4-11-2013},
    url = {https://doi.org/10.5194%2Fesd-4-11-2013},
    year = 2013,
    month = {jan},
    publisher = {Copernicus {GmbH}},
    volume = {4},
    number = {1},
    pages = {11--29},
    author = {M. Perrette and F. Landerer and R. Riva and K. Frieler and M. Meinshausen},
    title = {A scaling approach to project regional sea level rise and its uncertainties},
    journal = {Earth System Dynamics}
}"""
    return pdf, si, doi, key, year, bibtex

class TestBibtexFileEntry(unittest.TestCase):

    def test_parse_file(self):
        file = parse_file('file.pdf:/path/to/file.pdf:pdf')
        self.assertEqual(file, ['/path/to/file.pdf'])
        file = parse_file(':/path/to/file.pdf:pdf')
        self.assertEqual(file, ['/path/to/file.pdf'])
        file = parse_file('/path/to/file.pdf:pdf')
        self.assertEqual(file, ['/path/to/file.pdf'])
        file = parse_file('/path/to/file.pdf')
        self.assertEqual(file, ['/path/to/file.pdf'])
        file = parse_file(':/path/to/file.pdf:')
        self.assertEqual(file, ['/path/to/file.pdf'])


    def test_parse_files(self):
        files = parse_file(':/path/to/file1.pdf:pdf;:/path/to/file2.pdf:pdf')
        self.assertEqual(files, ['/path/to/file1.pdf','/path/to/file2.pdf'])


    def test_format_file(self):
        field = format_file(['/path/to/file.pdf'])
        self.assertEqual(field, ':/path/to/file.pdf:pdf')


    def test_format_files(self):
        field = format_file(['/path/to/file1.pdf','/path/to/file2.pdf'])
        self.assertEqual(field, ':/path/to/file1.pdf:pdf;:/path/to/file2.pdf:pdf')



class TestSimple(unittest.TestCase):

    def setUp(self):
        self.pdf, self.doi, self.key, self.year, self.bibtex = prepare_paper()

    def test_doi(self):
        self.assertEqual(run('myref doi '+self.pdf).strip(), self.doi)

    def test_fetch(self):
        bibtexs = run('myref fetch '+self.doi).strip()
        db1 = bibtexparser.loads(bibtexs)
        db2 = bibtexparser.loads(self.bibtex)
        self.assertEqual(db1.entries, db2.entries)
	    

class TestAdd(unittest.TestCase):

    def setUp(self):
        self.pdf, self.doi, self.key, self.year, self.bibtex = prepare_paper()
        self.mybib = tempfile.mktemp(prefix='myref.bib')
        self.filesdir = tempfile.mktemp(prefix='myref.files')


    def _checkbib(self):
        db1 = bibtexparser.load(open(self.mybib))
        file = db1.entries[0].pop('file').strip()
        db2 = bibtexparser.loads(self.bibtex)
        self.assertEqual(db1.entries, db2.entries) # entry is as expected
        return file

    def _checkfile(self, file):
        _, file, type = file.split(':')
        self.assertEqual(type, 'pdf') # file type is PDF
        self.assertTrue(os.path.exists(file))  # file link is valid
        return file


    def test_add(self):

        sp.check_call('myref add --bibtex {} {}'.format(
            self.mybib, self.pdf), shell=True)

        file_ = self._checkbib()
        file = self._checkfile(file_)
        self.assertEqual(file, self.pdf)
        # self.assertTrue(os.path.exists(self.pdf)) # old pdf still exists


    def test_add_rename_copy(self):

        sp.check_call('myref add -rc --bibtex {} --filesdir {} {}'.format(
            self.mybib, self.filesdir, self.pdf), shell=True)

        file_ = self._checkbib()  # 'file:pdf'
        file = self._checkfile(file_)
        self.assertEqual(file, os.path.join(self.filesdir, self.year, self.key+'.pdf'))
        self.assertTrue(os.path.exists(self.pdf)) # old pdf still exists


    def test_add_rename(self):

        pdfcopy = tempfile.mktemp(prefix='myref_test', suffix='.pdf')
        shutil.copy(self.pdf, pdfcopy)

        sp.check_call('myref add -r --bibtex {} --filesdir {} {}'.format(
            self.mybib, self.filesdir, pdfcopy), shell=True)

        file_ = self._checkbib()  # 'file:pdf'
        file = self._checkfile(file_)
        self.assertEqual(file, os.path.join(self.filesdir,self.year,self.key+'.pdf'))
        self.assertFalse(os.path.exists(pdfcopy))


    def tearDown(self):
        if os.path.exists(self.filesdir):
            shutil.rmtree(self.filesdir)
        os.remove(self.mybib)


class TestAdd2(TestAdd):

    def setUp(self):
        self.pdf, self.si, self.doi, self.key, self.year, self.bibtex = prepare_paper2()
        self.mybib = tempfile.mktemp(prefix='myref.bib')
        self.filesdir = tempfile.mktemp(prefix='myref.files')

    def test_add_attachment(self):
        sp.check_call('myref add -rc --bibtex {} --filesdir {} {} -a {}'.format(
            self.mybib, self.filesdir, self.pdf, self.si), shell=True)

        file_ = self._checkbib()
        print('file field in bibtex:', file_)
        self.assertTrue(';' in file_)
        main_, si_ = file_.split(';')
        main = self._checkfile(main_)
        si = self._checkfile(si_)
        # files have been moved in an appropriately named directory
        dirmain = os.path.dirname(main)
        dirsi = os.path.dirname(si)
        self.assertEqual(dirmain, dirsi)
        dirmains = dirmain.split(os.path.sep)
        self.assertEqual(dirmains[-1], self.key)
        self.assertEqual(dirmains[-2], self.year)
        self.assertEqual(os.path.sep.join(dirmains[:-2]), self.filesdir)
        # individual files have not been renamed
        self.assertEqual(os.path.basename(main), os.path.basename(self.pdf))
        self.assertEqual(os.path.basename(si), os.path.basename(self.si))
        # old pdfs still exists
        self.assertTrue(os.path.exists(self.pdf)) 
        self.assertTrue(os.path.exists(self.si))


if __name__ == '__main__':
    unittest.main()
