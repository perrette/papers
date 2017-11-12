from __future__ import print_function, absolute_import

import unittest
import os, subprocess as sp
import tempfile, shutil
import difflib

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
    author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
    doi = {10.5194/bg-8-515-2011},
    journal = {Biogeosciences},
    month = {feb},
    number = {2},
    pages = {515--524},
    publisher = {Copernicus {GmbH}},
    title = {Near-ubiquity of ice-edge blooms in the Arctic},
    url = {https://doi.org/10.5194%2Fbg-8-515-2011},
    volume = {8},
    year = 2011,
}"""

    return pdf, doi, key, year, bibtex

def prepare_paper2():
    pdf = downloadpdf('esd-4-11-2013.pdf')
    si = downloadpdf('esd-4-11-2013-supplement.pdf')
    doi = '10.5194/esd-4-11-2013'
    key = 'Perrette_2013'
    year = '2013'
    bibtex = """@article{Perrette_2013,
    author = {M. Perrette and F. Landerer and R. Riva and K. Frieler and M. Meinshausen},
    doi = {10.5194/esd-4-11-2013},
    journal = {Earth System Dynamics},
    month = {jan},
    number = {1},
    pages = {11--29},
    publisher = {Copernicus {GmbH}},
    title = {A scaling approach to project regional sea level rise and its uncertainties},
    url = {https://doi.org/10.5194%2Fesd-4-11-2013},
    volume = {4},
    year = 2013,
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
	    
class TestInstall(unittest.TestCase):

    def setUp(self):
        self.mybib = tempfile.mktemp(prefix='myref.bib')
        self.filesdir = tempfile.mktemp(prefix='myref.files')

    def test_install(self):
        sp.check_call('myref install --local --bibtex {} --files {}'.format(self.mybib, self.filesdir), 
            shell=True)
        self.assertTrue(os.path.exists(self.mybib))
        self.assertTrue(os.path.exists(self.filesdir))

    def tearDown(self):
        if os.path.exists(self.filesdir):
            shutil.rmtree(self.filesdir)
        if os.path.exists(self.mybib):
            os.remove(self.mybib)
        if os.path.exists('.myrefconfig.json'):
            os.remove('.myrefconfig.json')

class TestAdd(unittest.TestCase):

    def setUp(self):
        self.pdf, self.doi, self.key, self.year, self.bibtex = prepare_paper()
        self.mybib = tempfile.mktemp(prefix='myref.bib')
        self.filesdir = tempfile.mktemp(prefix='myref.files')
        open(self.mybib, 'w').write('')
        # sp.check_call('myref install --local --bibtex {} --filesdir {}'.format(self.mybib, self.filesdir), shell=True)
        self.assertTrue(os.path.exists(self.mybib))

    def _checkbib(self, doi_only=False):
        db1 = bibtexparser.load(open(self.mybib))
        self.assertTrue(len(db1.entries) > 0)
        file = db1.entries[0].pop('file').strip()
        db2 = bibtexparser.loads(self.bibtex)
        if doi_only:
            self.assertEqual([e['doi'] for e in db1.entries], [e['doi'] for e in db2.entries]) # entry is as expected
            # self.assertEqual([e['title'].lower() for e in db1.entries], [e['title'].lower() for e in db2.entries]) # entry is as expected
        else:
            self.assertEqual(db1.entries, db2.entries) # entry is as expected
        return file

    def _checkfile(self, file):
        _, file, type = file.split(':')
        self.assertEqual(type, 'pdf') # file type is PDF
        self.assertTrue(os.path.exists(file))  # file link is valid
        return file


    def test_fails_without_install(self):
        os.remove(self.mybib)
        func = lambda: sp.check_call('myref add {} --bibtex {} --files {}'.format(self.pdf, self.mybib, 
            self.filesdir))
        self.assertRaises(Exception, func)


    def test_add(self):
        # self.assertTrue(os.path.exists(self.mybib))
        sp.check_call('myref add --force --bibtex {} {}'.format(
            self.mybib, self.pdf), shell=True)

        file_ = self._checkbib()
        file = self._checkfile(file_)
        self.assertEqual(file, self.pdf)
        # self.assertTrue(os.path.exists(self.pdf)) # old pdf still exists


    def test_add_fulltext(self):
        # self.assertTrue(os.path.exists(self.mybib))
        sp.check_call('myref add --no-query-doi --bibtex {} {}'.format(
            self.mybib, self.pdf), shell=True)

        file_ = self._checkbib(doi_only=True)
        file = self._checkfile(file_)
        self.assertEqual(file, self.pdf)
        self.assertTrue(os.path.exists(self.pdf)) # old pdf still exists


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
        if os.path.exists(self.mybib):
            os.remove(self.mybib)
        if os.path.exists('.myrefconfig.json'):
            os.remove('.myrefconfig.json')


class TestAdd2(TestAdd):

    def setUp(self):
        self.pdf, self.si, self.doi, self.key, self.year, self.bibtex = prepare_paper2()
        self.mybib = tempfile.mktemp(prefix='myref.bib')
        self.filesdir = tempfile.mktemp(prefix='myref.files')
        # sp.check_call('myref install --local --bibtex {} --filesdir {}'.format(self.mybib, self.filesdir), shell=True)
        open(self.mybib, 'w').write('')

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


class TestAddBib(unittest.TestCase):

    def setUp(self):
        self.mybib = tempfile.mktemp(prefix='myref.bib')
        self.somebib = tempfile.mktemp(prefix='myref.somebib.bib')
        self.pdf1, self.doi, self.key1, self.year, self.bibtex1 = prepare_paper()
        self.pdf2, self.si, self.doi, self.key2, self.year, self.bibtex2 = prepare_paper2()
        bib = '\n'.join([self.bibtex1, self.bibtex2])
        open(self.somebib,'w').write(bib)
        self.my = MyRef.newbib(self.mybib, '')

    def test_addbib(self):
        self.assertTrue(self.key1 not in [e['ID'] for e in self.my.db.entries])
        self.assertTrue(self.key2 not in [e['ID'] for e in self.my.db.entries])
        self.my.add_bibtex_file(self.somebib)
        self.assertEqual(len(self.my.db.entries), 2)
        self.assertEqual(self.my.db.entries[0]['ID'], self.key1)
        self.assertEqual(self.my.db.entries[1]['ID'], self.key2)

    def tearDown(self):
        os.remove(self.mybib)
        os.remove(self.somebib)
        if os.path.exists('.myrefconfig.json'):
            os.remove('.myrefconfig.json')


class TestAddDir(unittest.TestCase):

    def setUp(self):
        self.pdf1, self.doi, self.key1, self.year, self.bibtex1 = prepare_paper()
        self.pdf2, self.si, self.doi, self.key2, self.year, self.bibtex2 = prepare_paper2()
        self.somedir = tempfile.mktemp(prefix='myref.somedir')
        self.subdir = os.path.join(self.somedir, 'subdir')
        os.makedirs(self.somedir)
        os.makedirs(self.subdir)
        shutil.copy(self.pdf1, self.somedir)
        shutil.copy(self.pdf2, self.subdir)
        self.mybib = tempfile.mktemp(prefix='myref.bib')
        sp.check_call('myref install --local --bibtex {}'.format(self.mybib), shell=True)

    def test_adddir_pdf(self):
        self.my = MyRef.load(self.mybib, '')
        self.my.scan_dir(self.somedir)
        self.assertEqual(len(self.my.db.entries), 2)
        keys = [self.my.db.entries[0]['ID'], self.my.db.entries[1]['ID']]
        self.assertEqual(sorted(keys), sorted([self.key1, self.key2]))

    def test_adddir_pdf_cmd(self):
        sp.check_call('myref add --recursive --bibtex {} {}'.format(self.mybib, self.somedir), shell=True)
        self.my = MyRef.load(self.mybib, '')
        self.assertEqual(len(self.my.db.entries), 2)
        keys = [self.my.db.entries[0]['ID'], self.my.db.entries[1]['ID']]
        self.assertEqual(sorted(keys), sorted([self.key1, self.key2]))

    def tearDown(self):
        os.remove(self.mybib)
        shutil.rmtree(self.somedir)
        if os.path.exists('.myrefconfig.json'):
            os.remove('.myrefconfig.json')


class BibTest(unittest.TestCase):
    """base class for bib tests: create a new bibliography
    """
    def setUp(self):
        self.mybib = tempfile.mktemp(prefix='myref.bib')
        self.filesdir = tempfile.mktemp(prefix='myref.files')
        self.otherbib = tempfile.mktemp(prefix='myref.otherbib')
        # self.my = MyRef.newbib(self.mybib, self.filesdir)
        # sp.check_call('myref install --local --bibtex {} --files {}'.format(self.mybib, self.filesdir), shell=True)
        open(self.mybib, 'w').write('')

    def tearDown(self):
        os.remove(self.mybib)
        if os.path.exists(self.filesdir):
            shutil.rmtree(self.filesdir)
        if os.path.exists(self.otherbib):
            os.remove(self.otherbib)
        if os.path.exists('.myrefconfig.json'):
            os.remove('.myrefconfig.json')


    def assertMultiLineEqual(self, first, second, msg=None):
        """Assert that two multi-line strings are equal.

        If they aren't, show a nice diff.
        source: https://stackoverflow.com/a/3943697/2192272
        """
        self.assertTrue(isinstance(first, str),
                'First argument is not a string')
        self.assertTrue(isinstance(second, str),
                'Second argument is not a string')

        if first != second:
            message = ''.join(difflib.ndiff(first.splitlines(True),
                                                second.splitlines(True)))
            if msg:
                message += " : " + msg
            self.fail("Multi-line strings are unequal:\n" + message)


class TestAddConflict(BibTest):
    
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

    bibtex_file = """@article{Perrette_2011,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 doi = {10.5194/bg-8-515-2011},
 file = {:mypdf.pdf:pdf},
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

    bibtex_conflict_key = """@article{Perrette_2011,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 doi = {10.5194/bg-8-515-2011XXX},
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

    bibtex_same_doi = """@article{SomeOtherKey,
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

    bibtex_miss_field = """@article{Perrette_2011,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 doi = {10.5194/bg-8-515-2011},
}"""

    def setUp(self):
        super(TestAddConflict, self).setUp()
        open(self.otherbib, 'w').write(self.bibtex)
        sp.check_call('myref add {} --bibtex {}'.format(self.otherbib, self.mybib), shell=True)        
        self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex)


    def test_add_same(self):
        open(self.otherbib, 'w').write(self.bibtex)
        sp.check_call('myref add {} --bibtex {}'.format(self.otherbib, self.mybib), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex) # entries did not change


    def test_add_same_but_file(self):
        open(self.otherbib, 'w').write(self.bibtex_file)
        sp.check_call('myref add {} --bibtex {} -f'.format(self.otherbib, self.mybib), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex_file) # entries did not change


    def test_add_conflict_key_raises(self):
        # key conflict: raises exception
        open(self.otherbib, 'w').write(self.bibtex_conflict_key)
        func = lambda : sp.check_call('myref add {} --bibtex {} -f'.format(self.otherbib, self.mybib), shell=True)
        self.assertRaises(Exception, func)

    def test_add_conflict_key_appends(self):
        # key conflict but append anyway
        open(self.otherbib, 'w').write(self.bibtex_conflict_key)
        sp.check_call('myref add {} --mode a --bibtex {} -f'.format(self.otherbib, self.mybib), shell=True)
        expected = self.bibtex_conflict_key+'\n\n'+self.bibtex
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_conflict_key_skip(self):
        # key conflict and skip entry
        open(self.otherbib, 'w').write(self.bibtex_conflict_key)
        sp.check_call('myref add {} --mode s --bibtex {} -f'.format(self.otherbib, self.mybib), shell=True)
        expected = self.bibtex
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_same_doi_unchecked(self):
        # does not normally test doi
        open(self.otherbib, 'w').write(self.bibtex_same_doi)
        sp.check_call('myref add {} --mode s --no-check-doi --bibtex {} -f'.format(self.otherbib, self.mybib), shell=True)
        expected = self.bibtex+'\n\n'+self.bibtex_same_doi
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_same_doi_fails(self):
        # test doi and triggers conflict
        open(self.otherbib, 'w').write(self.bibtex_same_doi)
        func = lambda : sp.check_call('myref add {} --bibtex {} -f'.format(self.otherbib, self.mybib), shell=True)
        self.assertRaises(Exception, func)

    def test_add_same_doi_update_key(self):
        # test doi and update key and identical entry detected
        open(self.otherbib, 'w').write(self.bibtex_same_doi)
        sp.check_call('myref add {} --update-key --bibtex {} -f'.format(self.otherbib, self.mybib), shell=True)
        expected = self.bibtex
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_miss_field_fails(self):
        # miss field and triggers conflict
        open(self.otherbib, 'w').write(self.bibtex_miss_field)
        func = lambda : sp.check_call('myref add {} --bibtex {} -f'.format(self.otherbib, self.mybib), shell=True)
        self.assertRaises(Exception, func)

    def test_add_miss_merge(self):
        # miss field but merges
        open(self.otherbib, 'w').write(self.bibtex_miss_field)
        sp.check_call('myref add {} --mode m --bibtex {} -f'.format(self.otherbib, self.mybib), shell=True)
        expected = self.bibtex
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change


    def tearDown(self):
        pass





if __name__ == '__main__':
    unittest.main()
