import unittest
import os, subprocess as sp
import tempfile, shutil
import difflib
from pathlib import Path

from papers.extract import extract_pdf_metadata
from papers.bib import Biblio, bibtexparser, parse_file, format_file
from download import downloadpdf

def run(cmd):
    print(cmd)
    return str(sp.check_output(cmd, shell=True).strip().decode())

def prepare_paper():
    pdf = downloadpdf('bg-8-515-2011.pdf')
    doi = '10.5194/bg-8-515-2011'
    key = 'Perrette_2011'
    newkey = 'perrette_yool2011'
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

    file_rename = "perrette_et_al_2011_near-ubiquity-of-ice-edge-blooms-in-the-arctic.pdf"

    return pdf, doi, key, newkey, year, bibtex, file_rename


def prepare_paper2():
    pdf = downloadpdf('esd-4-11-2013.pdf')
    si = downloadpdf('esd-4-11-2013-supplement.pdf')
    doi = '10.5194/esd-4-11-2013'
    key = 'Perrette_2013'
    newkey = 'perrette_landerer2013'
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
    file_rename = "perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf"

    return pdf, si, doi, key, newkey, year, bibtex, file_rename

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
        self.pdf, self.doi, self.key, self.newkey, self.year, self.bibtex, self.file_rename = prepare_paper()
        self.assertTrue(os.path.exists(self.pdf))

    def test_doi(self):
        self.assertEqual(run('papers doi '+self.pdf).strip(), self.doi)

    def test_fetch(self):
        bibtexs = run('papers fetch '+self.doi).strip()
        db1 = bibtexparser.loads(bibtexs)
        db2 = bibtexparser.loads(self.bibtex)
        self.assertEqual(db1.entries, db2.entries)

    def test_fetch_scholar(self):
        extract_pdf_metadata(self.pdf, scholar=True)

class TestInstall(unittest.TestCase):

    def setUp(self):
        self.mybib = tempfile.mktemp(prefix='papers.bib')
        self.filesdir = tempfile.mktemp(prefix='papers.files')

    def test_local_install(self):
        sp.check_call('papers install --local --bibtex {} --files {}'.format(self.mybib, self.filesdir),
            shell=True)
        self.assertTrue(os.path.exists(self.mybib))
        self.assertTrue(os.path.exists(self.filesdir))

    def tearDown(self):
        if os.path.exists(self.filesdir):
            shutil.rmtree(self.filesdir)
        if os.path.exists(self.mybib):
            os.remove(self.mybib)
        if os.path.exists('.papersconfig.json'):
            os.remove('.papersconfig.json')

class TestAdd(unittest.TestCase):

    def setUp(self):
        self.pdf, self.doi, self.key, self.newkey, self.year, self.bibtex, self.file_rename = prepare_paper()
        self.assertTrue(os.path.exists(self.pdf))
        self.mybib = tempfile.mktemp(prefix='papers.bib')
        self.filesdir = tempfile.mktemp(prefix='papers.files')
        open(self.mybib, 'w').write('')
        # sp.check_call('papers install --local --bibtex {} --filesdir {}'.format(self.mybib, self.filesdir), shell=True)
        self.assertTrue(os.path.exists(self.mybib))

    def _checkbib(self, doi_only=False, dismiss_key=False):
        db1 = bibtexparser.load(open(self.mybib))
        self.assertTrue(len(db1.entries) > 0)
        file = db1.entries[0].pop('file').strip()
        db2 = bibtexparser.loads(self.bibtex)
        if doi_only:
            self.assertEqual([e['doi'] for e in db1.entries], [e['doi'] for e in db2.entries]) # entry is as expected
            # self.assertEqual([e['title'].lower() for e in db1.entries], [e['title'].lower() for e in db2.entries]) # entry is as expected
        elif dismiss_key:
            f = lambda e: bibtexparser.customization.convert_to_unicode({k:e[k] for k in e if k!='ID'})
            self.assertEqual([f(e) for e in db1.entries], [f(e) for e in db2.entries]) # entry is as expected
        else:
            self.assertEqual(db1.entries, db2.entries) # entry is as expected
        return file

    def _checkfile(self, file):
        _, file, type = file.split(':')
        self.assertEqual(type, 'pdf') # file type is PDF
        file = os.path.abspath(os.path.join(os.path.dirname(self.mybib), file))
        self.assertTrue(os.path.exists(file))  # file link is valid
        return file


    def test_fails_without_install(self):
        os.remove(self.mybib)
        func = lambda: sp.check_call('papers add {} --bibtex {} --files {}'.format(self.pdf, self.mybib,
            self.filesdir))
        self.assertRaises(Exception, func)


    def test_add(self):
        self.assertTrue(os.path.exists(self.mybib))
        print("bibtex", self.mybib, 'exists?', os.path.exists(self.mybib))
        sp.check_call('papers add --bibtex {} {}'.format(
            self.mybib, self.pdf), shell=True)

        file_ = self._checkbib(dismiss_key=True)
        file = self._checkfile(file_)
        self.assertEqual(file, self.pdf)
        # self.assertTrue(os.path.exists(self.pdf)) # old pdf still exists


    # def test_add_fulltext(self):
    #     # self.assertTrue(os.path.exists(self.mybib))
    #     sp.check_call('papers add --no-query-doi --bibtex {} {}'.format(
    #         self.mybib, self.pdf), shell=True)

    #     file_ = self._checkbib(doi_only=True)
    #     file = self._checkfile(file_)
    #     self.assertEqual(file, self.pdf)
    #     self.assertTrue(os.path.exists(self.pdf)) # old pdf still exists


    def test_add_rename_copy(self):

        sp.check_call('papers add -rc --bibtex {} --filesdir {} {}'.format(
            self.mybib, self.filesdir, self.pdf), shell=True)

        file_ = self._checkbib(dismiss_key=True)  # 'file:pdf'
        file = self._checkfile(file_)
        self.assertEqual(file, os.path.join(self.filesdir, self.file_rename)) # update key since pdf
        self.assertTrue(os.path.exists(self.pdf)) # old pdf still exists


    def test_add_rename(self):

        pdfcopy = tempfile.mktemp(prefix='myref_test', suffix='.pdf')
        shutil.copy(self.pdf, pdfcopy)

        sp.check_call('papers add -r --bibtex {} --filesdir {} {} --debug'.format(
            self.mybib, self.filesdir, pdfcopy), shell=True)

        file_ = self._checkbib(dismiss_key=True)  # 'file:pdf'
        file = self._checkfile(file_)
        self.assertEqual(file, os.path.join(self.filesdir,self.file_rename)) # update key since pdf
        self.assertFalse(os.path.exists(pdfcopy))


    def tearDown(self):
        if os.path.exists(self.filesdir):
            shutil.rmtree(self.filesdir)
        if os.path.exists(self.mybib):
            os.remove(self.mybib)
        if os.path.exists('.papersconfig.json'):
            os.remove('.papersconfig.json')


class TestAdd2(TestAdd):

    def setUp(self):
        self.pdf, self.si, self.doi, self.key, self.newkey, self.year, self.bibtex, self.file_rename = prepare_paper2()
        self.assertTrue(os.path.exists(self.pdf))
        self.mybib = tempfile.mktemp(prefix='papers.bib')
        self.filesdir = tempfile.mktemp(prefix='papers.files')
        # sp.check_call('papers install --local --bibtex {} --filesdir {}'.format(self.mybib, self.filesdir), shell=True)
        open(self.mybib, 'w').write('')

    def test_add_attachment(self):
        sp.check_call('papers add -rc --bibtex {} --filesdir {} {} -a {}'.format(
            self.mybib, self.filesdir, self.pdf, self.si), shell=True)

        file_ = self._checkbib(dismiss_key=True)
        self.assertTrue(';' in file_)
        main_, si_ = file_.split(';')
        main = self._checkfile(main_)
        si = self._checkfile(si_)
        # files have been moved in an appropriately named directory
        dirmain = os.path.dirname(main)
        dirsi = os.path.dirname(si)
        self.assertEqual(dirmain, dirsi)
        dirmains = dirmain.split(os.path.sep)
        self.assertEqual(Path(dirmain).name, Path(self.file_rename).stem)
        # individual files have not been renamed
        self.assertEqual(os.path.basename(main), os.path.basename(self.pdf))
        self.assertEqual(os.path.basename(si), os.path.basename(self.si))
        # old pdfs still exists
        self.assertTrue(os.path.exists(self.pdf))
        self.assertTrue(os.path.exists(self.si))


class TestAddBib(unittest.TestCase):

    def setUp(self):
        self.mybib = tempfile.mktemp(prefix='papers.bib')
        self.somebib = tempfile.mktemp(prefix='papers.somebib.bib')
        self.pdf1, self.doi, self.key1, self.newkey1, self.year, self.bibtex1, self.file_rename1 = prepare_paper()
        self.pdf2, self.si, self.doi, self.key2, self.newkey2, self.year, self.bibtex2, self.file_rename2 = prepare_paper2()
        bib = '\n'.join([self.bibtex1, self.bibtex2])
        open(self.somebib,'w').write(bib)
        self.my = Biblio.newbib(self.mybib, '')

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
        if os.path.exists('.papersconfig.json'):
            os.remove('.papersconfig.json')


class TestAddDir(unittest.TestCase):

    def setUp(self):
        self.pdf1, self.doi, self.key1, self.newkey1, self.year, self.bibtex1, self.file_rename1 = prepare_paper()
        self.pdf2, self.si, self.doi, self.key2, self.newkey2, self.year, self.bibtex2, self.file_rename2 = prepare_paper2()
        self.somedir = tempfile.mktemp(prefix='papers.somedir')
        self.subdir = os.path.join(self.somedir, 'subdir')
        os.makedirs(self.somedir)
        os.makedirs(self.subdir)
        shutil.copy(self.pdf1, self.somedir)
        shutil.copy(self.pdf2, self.subdir)
        self.mybib = tempfile.mktemp(prefix='papers.bib')
        sp.check_call('papers install --local --no-prompt --bibtex {}'.format(self.mybib), shell=True)

    def test_adddir_pdf(self):
        self.my = Biblio.load(self.mybib, '')
        self.my.scan_dir(self.somedir)
        self.assertEqual(len(self.my.db.entries), 2)
        keys = [self.my.db.entries[0]['ID'], self.my.db.entries[1]['ID']]
        self.assertEqual(sorted(keys), sorted([self.newkey1, self.newkey2]))  # PDF: update key

    def test_adddir_pdf_cmd(self):
        sp.check_call('papers add --recursive --bibtex {} {}'.format(self.mybib, self.somedir), shell=True)
        self.my = Biblio.load(self.mybib, '')
        self.assertEqual(len(self.my.db.entries), 2)
        keys = [self.my.db.entries[0]['ID'], self.my.db.entries[1]['ID']]
        self.assertEqual(sorted(keys), sorted([self.newkey1, self.newkey2])) # PDF: update key

    def tearDown(self):
        os.remove(self.mybib)
        shutil.rmtree(self.somedir)
        if os.path.exists('.papersconfig.json'):
            os.remove('.papersconfig.json')


class BibTest(unittest.TestCase):
    """base class for bib tests: create a new bibliography
    """

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



class SimilarityBase(unittest.TestCase):

    similarity = None

    reference = """@article{Perrette_2011,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 doi = {10.5194/bg-8-515-2011},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
 year = {2011}
}"""

    anotherkey = """@article{OtherKey,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 doi = {10.5194/bg-8-515-2011},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
 year = {2011}
}"""

    missingfield = """@article{Perrette_2011,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 doi = {10.5194/bg-8-515-2011},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
}"""

    missingdoi = """@article{Perrette_2011,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
}"""

    missingtitauthor = """@article{Perrette_2011,
 doi = {10.5194/bg-8-515-2011},
}"""

    conflictauthor = """@article{Perrette_2011,
 author = {SomeOneElse},
 doi = {10.5194/bg-8-515-2011},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
}"""

    conflictdoi = """@article{Perrette_2011,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 doi = {10.5194/XXX},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
}"""

    conflictyear = """@article{Perrette_2011,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 doi = {10.5194/bg-8-515-2011},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
 year = {2012}
}"""


    def isduplicate(self, a, b):
        """test Biblio's eq method for duplicates
        """
        db = bibtexparser.loads(a+'\n'+b)
        e1, e2 = db.entries
        refs = Biblio(similarity=self.similarity)
        return refs.eq(e1, e2)


class TestDuplicatesExact(SimilarityBase):

    similarity = 'EXACT'

    def test_exactsame(self):
        self.assertTrue(self.isduplicate(self.reference, self.reference))

    def test_anotherkey(self):
        self.assertFalse(self.isduplicate(self.reference, self.anotherkey))

    def test_missingfield(self):
        self.assertFalse(self.isduplicate(self.reference, self.missingfield))

    def test_missingdoi(self):
        self.assertFalse(self.isduplicate(self.reference, self.missingdoi))

    def test_missingtitauthor(self):
        self.assertFalse(self.isduplicate(self.reference, self.missingtitauthor))

    def test_conflictauthor(self):
        self.assertFalse(self.isduplicate(self.reference, self.conflictauthor))

    def test_conflictdoi(self):
        self.assertFalse(self.isduplicate(self.reference, self.conflictdoi))

    def test_conflictyear(self):
        self.assertFalse(self.isduplicate(self.reference, self.conflictyear))


class TestDuplicatesGood(TestDuplicatesExact):

    similarity = 'GOOD'

    def test_anotherkey(self):
        self.assertTrue(self.isduplicate(self.reference, self.anotherkey))

    def test_missingfield(self):
        self.assertTrue(self.isduplicate(self.reference, self.missingfield))

    def test_conflictyear(self):
        self.assertTrue(self.isduplicate(self.reference, self.conflictyear))


class TestDuplicatesFair(TestDuplicatesGood):

    similarity = 'FAIR'

    def test_missingtitauthor(self):
        self.assertTrue(self.isduplicate(self.reference, self.missingtitauthor))

    def test_conflictauthor(self):
        self.assertTrue(self.isduplicate(self.reference, self.conflictauthor))


class TestDuplicatesPartial(TestDuplicatesFair):

    similarity = 'PARTIAL'

    def test_missingdoi(self):
        self.assertTrue(self.isduplicate(self.reference, self.missingdoi))

    def test_conflictdoi(self):
        self.assertTrue(self.isduplicate(self.reference, self.conflictdoi))


class TestDuplicates(TestDuplicatesPartial):

    @staticmethod
    def isduplicate(a, b):
        """test Biblio's eq method for duplicates
        """
        db = bibtexparser.loads(a+'\n'+b)
        e1, e2 = db.entries
        refs = Biblio()
        return refs.eq(e1, e2)


class TestDuplicatesAdd(TestDuplicates):

    def setUp(self):
        self.mybib = tempfile.mktemp(prefix='papers.bib')
        self.otherbib = tempfile.mktemp(prefix='papers.otherbib')

    def tearDown(self):
        os.remove(self.mybib)
        os.remove(self.otherbib)

    def isduplicate(self, a, b):
        """test Biblio's eq method in 'add' mode
        """
        open(self.mybib, 'w').write(a)
        open(self.otherbib, 'w').write(b)
        res = sp.call('papers add {} --bibtex {} --update-key --mode r --debug'.format(self.otherbib, self.mybib), shell=True)
        return res != 0

    @unittest.skip("skip cause does not make sense with add")
    def test_exactsame(self):
        pass

    @unittest.skip("skip cause does not make sense with add")
    def test_anotherkey(self):
        pass



class TestAddResolveDuplicate(BibTest):

    original = """@article{Perrette_2011,
 doi = {10.5194/bg-8-515-2011},
 journal = {Biogeosciences},
 year = {RareYear}
}"""


    conflict = """@article{AnotherKey,
 author = {New Author Field},
 doi = {10.5194/bg-8-515-2011},
 journal = {ConflictJournal}
}"""


    def setUp(self):
        self.mybib = tempfile.mktemp(prefix='papers.bib')
        self.otherbib = tempfile.mktemp(prefix='papers.otherbib')
        open(self.mybib, 'w').write(self.original)

    def tearDown(self):
        os.remove(self.mybib)
        os.remove(self.otherbib)

    def command(self, mode):
        return 'echo {} | papers add {} --bibtex {} --debug'.format(mode, self.otherbib, self.mybib)

    def test_overwrite(self):

        expected = self.conflict

        open(self.otherbib, 'w').write(self.conflict)
        sp.check_call(self.command('o'), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change


    def test_skip(self):

        expected = self.original

        open(self.otherbib, 'w').write(self.conflict)
        sp.check_call(self.command('s'), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_append(self):
        open(self.otherbib, 'w').write(self.conflict)
        sp.check_call(self.command('a'), shell=True)
        # sp.check_call('papers add {} --bibtex {} --debug'.format(self.otherbib, self.mybib), shell=True)
        expected = self.conflict + '\n\n' + self.original
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change


    def test_raises(self):
        # update key to new entry, but does not merge...
        open(self.otherbib, 'w').write(self.conflict)
        func = lambda: sp.check_call(self.command('r'), shell=True)
        self.assertRaises(Exception, func)


    def test_original_updated_from_conflict(self):

        expected = """@article{Perrette_2011,
 author = {New Author Field},
 doi = {10.5194/bg-8-515-2011},
 journal = {Biogeosciences},
 year = {RareYear}
}"""

        open(self.otherbib, 'w').write(self.conflict)
        sp.check_call(self.command('u'), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change


    def test_conflict_updated_from_original(self):

        expected = """@article{AnotherKey,
 author = {New Author Field},
 doi = {10.5194/bg-8-515-2011},
 journal = {ConflictJournal},
 year = {RareYear}
}"""

        open(self.otherbib, 'w').write(self.conflict)
        sp.check_call(self.command('U'), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change


    def test_conflict_updated_from_original_but_originalkey(self):

        expected = """@article{Perrette_2011,
 author = {New Author Field},
 doi = {10.5194/bg-8-515-2011},
 journal = {ConflictJournal},
 year = {RareYear}
}"""
        open(self.otherbib, 'w').write(self.conflict)
        sp.check_call(self.command('U') + ' --update-key', shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change



class TestAddResolveDuplicateCommand(TestAddResolveDuplicate):

    def command(self, mode):
        return 'papers add {} --bibtex {} --mode {} --debug'.format(self.otherbib, self.mybib, mode)



class TestCheckResolveDuplicate(BibTest):

    original = """@article{Perrette_2011,
 doi = {10.5194/bg-8-515-2011},
 journal = {Biogeosciences},
 year = {RareYear}
}"""


    conflict = """@article{AnotherKey,
 author = {New Author Field},
 doi = {10.5194/bg-8-515-2011},
 journal = {ConflictJournal}
}"""


    def setUp(self):
        self.mybib = tempfile.mktemp(prefix='papers.bib')
        open(self.mybib, 'w').write(self.original + '\n\n' + self.conflict)

    def tearDown(self):
        os.remove(self.mybib)

    def command(self, mode):
        return 'echo {} | papers check --duplicates --bibtex {} --debug'.format(mode, self.mybib)

    def test_pick_conflict_1(self):

        expected = self.conflict

        sp.check_call(self.command('1'), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_pick_reference_2(self):

        expected = self.original

        sp.check_call(self.command('2'), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change


    def test_skip_check(self):

        expected = self.conflict + '\n\n' + self.original

        sp.check_call(self.command('s'), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change


    def test_not_a_duplicate(self):

        expected = self.conflict + '\n\n' + self.original

        sp.check_call(self.command('n'), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change


    def test_raises(self):
        # update key to new entry, but does not merge...
        func = lambda: sp.check_call(self.command('r'), shell=True)
        self.assertRaises(Exception, func)


    def test_merge(self):
        # update key to new entry, but does not merge...
        expected = """@article{AnotherKey,
         author = {New Author Field},
         doi = {10.5194/bg-8-515-2011},
         journal = {ConflictJournal},
         year = {RareYear}
        }"""
        func = lambda: sp.check_call(self.command('m\n3'), shell=True)
        self.assertRaises(Exception, func)



class TestUnicode(BibTest):
    pass


class TestUnicodeVsLatexEncoding(BibTest):
    pass


## KEEP FOR NOW BUT TRASH ASAP:

class TestAddConflict(BibTest):
    ## TODO: tear down in several smaller tests

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

    bibtex_otherkey = """@article{otherkey,
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


    bibtex_hasfile = """@article{Perrette_2011,
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
 author = {M. Perrette and Another author},
 doi = {10.5194/bg-8-515-2011XXX},
 title = {Something else entirely}
}"""

    bibtex_conflict_key_fixed = """@article{Perrette_2011b,
 author = {M. Perrette and Another author},
 doi = {10.5194/bg-8-515-2011XXX},
 title = {Something else entirely}
}"""

    bibtex_same_doi = """@article{same_doi,
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

    bibtex_miss_field = """@article{miss_field,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 doi = {10.5194/bg-8-515-2011},
 title = {Near-ubiquity of ice-edge blooms in the Arctic}
}"""

    bibtex_miss_doi_field = """@article{miss_doi_field,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 title = {Near-ubiquity of ice-edge blooms in the Arctic}
}"""

    bibtex_miss_titauthor_field = """@article{miss_titauthor_field,
 doi = {10.5194/bg-8-515-2011},
}"""


    def setUp(self):
        self.mybib = tempfile.mktemp(prefix='papers.bib')
        self.filesdir = tempfile.mktemp(prefix='papers.files')
        self.otherbib = tempfile.mktemp(prefix='papers.otherbib')
        # self.my = Biblio.newbib(self.mybib, self.filesdir)
        # sp.check_call('papers install --local --bibtex {} --files {}'.format(self.mybib, self.filesdir), shell=True)
        open(self.mybib, 'w').write(self.bibtex)
        # open(self.otherbib, 'w').write('')
        # sp.check_call('papers add {} --bibtex {}'.format(self.otherbib, self.mybib), shell=True)
        # self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex)

    def tearDown(self):
        os.remove(self.mybib)
        if os.path.exists(self.filesdir):
            shutil.rmtree(self.filesdir)
        if os.path.exists(self.otherbib):
            os.remove(self.otherbib)
        if os.path.exists('.papersconfig.json'):
            os.remove('.papersconfig.json')


    def test_add_same(self):
        open(self.otherbib, 'w').write(self.bibtex)
        sp.check_call('papers add {} --bibtex {}'.format(self.otherbib, self.mybib), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex) # entries did not change


    def test_add_same_but_key_interactive(self):
        # fails in raise mode
        open(self.otherbib, 'w').write(self.bibtex_otherkey)
        sp.check_call('echo u | papers add {} --bibtex {}'.format(self.otherbib, self.mybib), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex) # entries did not change


    def test_add_same_but_key_update(self):
        open(self.otherbib, 'w').write(self.bibtex_otherkey)
        sp.check_call('papers add {} --bibtex {} -u'.format(self.otherbib, self.mybib), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex) # entries did not change


    def test_add_same_but_key_fails(self):
        # fails in raise mode
        open(self.otherbib, 'w').write(self.bibtex_otherkey)
        func = lambda x: sp.check_call('papers add {} --bibtex {} --mode r'.format(self.otherbib, self.mybib), shell=True)
        self.assertRaises(Exception, func)


    def test_add_same_but_file(self):
        open(self.otherbib, 'w').write(self.bibtex_hasfile)
        sp.check_call('papers add {} --bibtex {} -u'.format(self.otherbib, self.mybib), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex_hasfile) # entries did not change


    def test_add_conflict_key_check_raises(self):
        # key conflict: raises exception whatever mode is indicated
        open(self.otherbib, 'w').write(self.bibtex_conflict_key)
        func = lambda : sp.check_call('papers add {} --bibtex {} --mode s --debug'.format(self.otherbib, self.mybib), shell=True)
        self.assertRaises(Exception, func)

    def test_add_conflict_key_nocheck_raises(self):
        # also when no check duplicate is indicated
        func = lambda : sp.check_call('papers add {} --bibtex {} --no-check-duplicate'.format(self.otherbib, self.mybib), shell=True)
        self.assertRaises(Exception, func)

    # def test_add_conflict_key_appends(self):
    #     # key conflict : ra
    #     open(self.otherbib, 'w').write(self.bibtex_conflict_key)
    #     sp.check_call('papers add {} --no-check-duplicate --bibtex {} --mode r'.format(self.otherbib, self.mybib), shell=True)
    #     expected = self.bibtex_conflict_key+'\n\n'+self.bibtex
    #     self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_conflict_key_update(self):
        # key conflict and update entry
        open(self.otherbib, 'w').write(self.bibtex_conflict_key)
        sp.check_call('papers add {} --bibtex {} -u'.format(self.otherbib, self.mybib), shell=True)
        expected = self.bibtex+'\n\n'+self.bibtex_conflict_key_fixed
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_same_doi_unchecked(self):
        # does not normally test doi
        open(self.otherbib, 'w').write(self.bibtex_same_doi)
        sp.check_call('papers add {} --no-check-duplicate --bibtex {} --mode r'.format(self.otherbib, self.mybib), shell=True)
        expected = self.bibtex+'\n\n'+self.bibtex_same_doi
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_same_doi_fails(self):
        # test doi and triggers conflict
        open(self.otherbib, 'w').write(self.bibtex_same_doi)
        func = lambda : sp.check_call('papers add {} --bibtex {} --mode r'.format(self.otherbib, self.mybib), shell=True)
        self.assertRaises(Exception, func)

    def test_add_same_doi_update_key(self):
        # test doi and update key and identical entry detected
        open(self.otherbib, 'w').write(self.bibtex_same_doi)
        sp.check_call('papers add {} --update-key --bibtex {} --mode r'.format(self.otherbib, self.mybib), shell=True)
        expected = self.bibtex
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_miss_field_fails(self):
        # miss field and triggers conflict
        open(self.otherbib, 'w').write(self.bibtex_miss_field)
        func = lambda : sp.check_call('papers add {} --bibtex {} --mode r'.format(self.otherbib, self.mybib), shell=True)
        self.assertRaises(Exception, func)

    def test_add_miss_merge(self):
        # miss field but merges
        open(self.otherbib, 'w').write(self.bibtex_miss_field)
        sp.check_call('papers add {} --mode u --bibtex {}'.format(self.otherbib, self.mybib), shell=True)
        expected = self.bibtex
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_miss_doi_merge(self):
        # miss field but merges
        open(self.otherbib, 'w').write(self.bibtex_miss_doi_field)
        sp.check_call('papers add {} --mode u --bibtex {}'.format(self.otherbib, self.mybib), shell=True)
        expected = self.bibtex
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_miss_titauthor_merge(self):
        # miss field but merges
        open(self.otherbib, 'w').write(self.bibtex_miss_titauthor_field)
        sp.check_call('papers add {} --mode u --bibtex {} --debug'.format(self.otherbib, self.mybib), shell=True)
        expected = self.bibtex
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change



if __name__ == '__main__':
    unittest.main()
