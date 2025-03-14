import os
import shutil
import subprocess as sp
import tempfile
import unittest
from pathlib import Path

import bibtexparser

from papers.bib import Biblio
from tests.common import PAPERSCMD, paperscmd, prepare_paper, prepare_paper2, BibTest


class TestAdd(BibTest):

    def setUp(self):
        self.pdf, self.doi, self.key, self.newkey, self.year, self.bibtex, self.file_rename = prepare_paper()
        self.assertTrue(os.path.exists(self.pdf))
        self.mybib = tempfile.mktemp(prefix='papers.bib')
        self.filesdir = tempfile.mktemp(prefix='papers.files')
        open(self.mybib, 'w').write('')
        # paperscmd(f'install --local --bibtex {self.mybib} --filesdir {self.filesdir}'
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
        func = lambda: paperscmd(f'add {self.pdf} --bibtex {self.mybib} --files {self.filesdir}')
        self.assertRaises(Exception, func)


    def test_add(self):
        self.assertTrue(os.path.exists(self.mybib))
        paperscmd(f'add --bibtex {self.mybib} {self.pdf}')

        file_ = self._checkbib(dismiss_key=True)
        the_file = self._checkfile(file_)
        self.assertEqual(the_file, self.pdf)
        # self.assertTrue(os.path.exists(self.pdf)) # old pdf still exists


    # def test_add_fulltext(self):
    #     # self.assertTrue(os.path.exists(self.mybib))
    #     paperscmd(f'add --no-query-doi --bibtex {self.mybib} {self.pdf}')

    #     file_ = self._checkbib(doi_only=True)
    #     file = self._checkfile(file_)
    #     self.assertEqual(file, self.pdf)
    #     self.assertTrue(os.path.exists(self.pdf)) # old pdf still exists


    def test_add_rename_copy(self):

        paperscmd(f'add -rc --bibtex {self.mybib} --filesdir {self.filesdir} {self.pdf}')

        file_ = self._checkbib(dismiss_key=True)  # 'file:pdf'
        file = self._checkfile(file_)
        self.assertEqual(file, os.path.join(self.filesdir, self.file_rename)) # update key since pdf
        self.assertTrue(os.path.exists(self.pdf)) # old pdf still exists

    def test_add_rename_copy_journal(self):
        '''
        Tests that demanding a {journal} in the --name-template works.
        Lightly begged/borrowed/stolen from the above test.
        '''
        paperscmd(f'add --rename --copy --name-template "{{journal}}/{{authorX}}_{{year}}_{{title}}" --name-title-sep - --name-author-sep _ --bibtex {self.mybib} --filesdir {self.filesdir} {self.pdf}') # need to escape the {} in f-strings by doubling those curly braces.

        file_ = self._checkbib(dismiss_key=True)
        the_file = self._checkfile(file_)
        self.assertTrue(os.path.exists(self.pdf))
        new_path = str(the_file).split(os.path.sep)
        old_path = str(os.path.join(self.filesdir, self.file_rename)).split(os.path.sep)
        self.assertEqual(old_path[-1], new_path[-1])
        self.assertEqual(old_path[0], new_path[0])
        db = bibtexparser.load(open(self.mybib))
        journal = db.entries[0]['journal']
        self.assertEqual(journal, new_path[-2]) #TODO a little gross, hardcoded

    def test_add_rename(self):

        pdfcopy = tempfile.mktemp(prefix='myref_test', suffix='.pdf')
        shutil.copy(self.pdf, pdfcopy)

        paperscmd(f'add -r --bibtex {self.mybib} --filesdir {self.filesdir} {pdfcopy} --debug')

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
        # paperscmd(f'install --local --bibtex {self.mybib} --filesdir {self.filesdir}'
        open(self.mybib, 'w').write('')

    def test_add_attachment(self):
        paperscmd(f'add -rc --bibtex {self.mybib} --filesdir {self.filesdir} {self.pdf} -a {self.si}')

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


class TestAddBib(BibTest):

    def setUp(self):
        self.mybib = tempfile.mktemp(prefix='papers.bib')
        self.somebib = tempfile.mktemp(prefix='papers.somebib.bib')
        self.pdf1, self.doi, self.key1, self.newkey1, self.year, self.bibtex1, self.file_rename1 = prepare_paper()
        self.pdf2, self.si, self.doi, self.key2, self.newkey2, self.year, self.bibtex2, self.file_rename2 = prepare_paper2()
        bib = '\n'.join([self.bibtex1, self.bibtex2])
        open(self.mybib,'w').write(self.bibtex1)
        open(self.somebib,'w').write(self.bibtex2)
        self.my = Biblio.load(self.mybib, '')

    def test_addbib_method(self):
        self.assertTrue(self.key1 in [e['ID'] for e in self.my.db.entries])
        self.assertTrue(self.key2 not in [e['ID'] for e in self.my.db.entries])
        self.my.add_bibtex_file(self.somebib)
        self.assertEqual(len(self.my.db.entries), 2)
        self.assertEqual(self.my.db.entries[0]['ID'], self.key1)
        self.assertEqual(self.my.db.entries[1]['ID'], self.key2)

    def test_addbib_cmd(self):
        bib = Biblio.load(self.mybib, '')
        self.assertEqual(len(bib.db.entries), 1)
        self.assertEqual(bib.db.entries[0]['ID'], self.key1)
        paperscmd(f'add {self.somebib} --bibtex {self.mybib}')
        bib = Biblio.load(self.mybib, '')
        self.assertEqual(len(bib.db.entries), 2)
        self.assertEqual(bib.db.entries[0]['ID'], self.key1)
        self.assertEqual(bib.db.entries[1]['ID'], self.key2)

    def test_addbib_cmd_dryrun(self):
        bib = Biblio.load(self.mybib, '')
        self.assertEqual(len(bib.db.entries), 1)
        self.assertEqual(bib.db.entries[0]['ID'], self.key1)
        paperscmd(f'add {self.somebib} --bibtex {self.mybib} --dry-run')
        bib = Biblio.load(self.mybib, '')
        self.assertEqual(len(bib.db.entries), 1)
        self.assertEqual(bib.db.entries[0]['ID'], self.key1)
        self.assertTrue(self.key2 not in [e['ID'] for e in self.my.db.entries])

    def test_attachment_fails_with_multiple_entries(self):
        func = lambda: paperscmd(f'add {self.pdf} {self.pdf} --bibtex {self.mybib} --filesdir {self.filesdir} --attachment {self.pdf}')
        self.assertRaises(Exception, func)

    def test_fails_with_no_file_and_no_doi(self):
        func = lambda: paperscmd(f'add --bibtex {self.mybib} --filesdir {self.filesdir} --attachment {self.pdf}')
        self.assertRaises(Exception, func)

    def test_fails_with_no_file_and_doi_but_no_query_doi(self):
        func = lambda: paperscmd(f'add --bibtex {self.mybib} --filesdir {self.filesdir} --attachment {self.pdf} --doi 123 --no-query-doi')
        self.assertRaises(Exception, func)



    def tearDown(self):
        os.remove(self.mybib)
        os.remove(self.somebib)
        if os.path.exists('.papersconfig.json'):
            os.remove('.papersconfig.json')


class TestAddDir(BibTest):

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
        paperscmd(f'install --local --no-prompt --bibtex {self.mybib}')

    def test_adddir_pdf(self):
        self.my = Biblio.load(self.mybib, '')
        self.my.scan_dir(self.somedir)
        self.assertEqual(len(self.my.db.entries), 2)
        keys = [self.my.db.entries[0]['ID'], self.my.db.entries[1]['ID']]
        self.assertEqual(sorted(keys), sorted([self.newkey1, self.newkey2]))  # PDF: update key

    def test_adddir_pdf_cmd(self):
        paperscmd(f'add --recursive --bibtex {self.mybib} {self.somedir}')
        self.my = Biblio.load(self.mybib, '')
        self.assertEqual(len(self.my.db.entries), 2)
        keys = [self.my.db.entries[0]['ID'], self.my.db.entries[1]['ID']]
        self.assertEqual(sorted(keys), sorted([self.newkey1, self.newkey2])) # PDF: update key

    def tearDown(self):
        os.remove(self.mybib)
        shutil.rmtree(self.somedir)
        paperscmd(f'uninstall')



## The test below were written first. There are not systematic but they have the advantage to exist.
## Short after they have been written, they were considered deprecated.
## Now as I write these lines I cannot immediately grasp what is wrong with them.
## Probably best to keep them for now, and to review them at some point in the future to remove any redundancy with other tests.
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

    bibtex_conflict_key_fixed = """@article{10.5194/bg-8-515-2011XXX,
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
        # paperscmd(f'install --local --bibtex {} --files {}'.format(self.mybib, self.filesdir))
        open(self.mybib, 'w').write(self.bibtex)
        # open(self.otherbib, 'w').write('')
        # paperscmd(f'add {self.otherbib} --bibtex {self.mybib}')
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
        paperscmd(f'add {self.otherbib} --bibtex {self.mybib}')
        self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex) # entries did not change


    def test_add_same_but_key_interactive(self):
        # fails in raise mode
        open(self.otherbib, 'w').write(self.bibtex_otherkey)
        sp.check_call(f'echo u | {PAPERSCMD} add {self.otherbib} --bibtex {self.mybib}', shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex) # entries did not change


    def test_add_same_but_key_update(self):
        open(self.otherbib, 'w').write(self.bibtex_otherkey)
        paperscmd(f'add {self.otherbib} --bibtex {self.mybib} -u')
        self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex) # entries did not change


    def test_add_same_but_key_fails(self):
        # fails in raise mode
        open(self.otherbib, 'w').write(self.bibtex_otherkey)
        func = lambda x: paperscmd(f'add {self.otherbib} --bibtex {self.mybib} --mode r')
        self.assertRaises(Exception, func)


    def test_add_same_but_file(self):
        open(self.otherbib, 'w').write(self.bibtex_hasfile)
        paperscmd(f'add {self.otherbib} --bibtex {self.mybib} -u --relative-path')
        self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex_hasfile) # entries did not change


    def test_add_conflict_key_check_raises(self):
        # key conflict: raises exception whatever mode is indicated
        open(self.otherbib, 'w').write(self.bibtex_conflict_key)
        func = lambda : paperscmd(f'add {self.otherbib} --bibtex {self.mybib} --mode s --debug')
        self.assertRaises(Exception, func)

    def test_add_conflict_key_nocheck_raises(self):
        # also when no check duplicate is indicated
        func = lambda : paperscmd(f'add {self.otherbib} --bibtex {self.mybib} --no-check-duplicate')
        self.assertRaises(Exception, func)

    # def test_add_conflict_key_appends(self):
    #     # key conflict : ra
    #     open(self.otherbib, 'w').write(self.bibtex_conflict_key)
    #     paperscmd(f'add {} --no-check-duplicate --bibtex {} --mode r'.format(self.otherbib, self.mybib))
    #     expected = self.bibtex_conflict_key+'\n\n'+self.bibtex
    #     self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_conflict_key_update(self):
        # key conflict and update entry
        open(self.otherbib, 'w').write(self.bibtex_conflict_key)
        paperscmd(f'add {self.otherbib} --bibtex {self.mybib} -u')
        expected = self.bibtex_conflict_key_fixed+'\n\n'+self.bibtex
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_same_doi_unchecked(self):
        # does not normally test doi
        open(self.otherbib, 'w').write(self.bibtex_same_doi)
        paperscmd(f'add {self.otherbib} --no-check-duplicate --bibtex {self.mybib} --mode r')
        expected = self.bibtex+'\n\n'+self.bibtex_same_doi
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_same_doi_fails(self):
        # test doi and triggers conflict
        open(self.otherbib, 'w').write(self.bibtex_same_doi)
        func = lambda : paperscmd(f'add {self.otherbib} --bibtex {self.mybib} --mode r')
        self.assertRaises(Exception, func)

    def test_add_same_doi_update_key(self):
        # test doi and update key and identical entry detected
        open(self.otherbib, 'w').write(self.bibtex_same_doi)
        paperscmd(f'add {self.otherbib} --update-key --bibtex {self.mybib} --mode r')
        expected = self.bibtex
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_miss_field_fails(self):
        # miss field and triggers conflict
        open(self.otherbib, 'w').write(self.bibtex_miss_field)
        func = lambda : paperscmd(f'add {self.otherbib} --bibtex {self.mybib} --mode r')
        self.assertRaises(Exception, func)

    def test_add_miss_merge(self):
        # miss field but merges
        open(self.otherbib, 'w').write(self.bibtex_miss_field)
        paperscmd(f'add {self.otherbib} --mode u --bibtex {self.mybib}')
        expected = self.bibtex
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_miss_doi_merge(self):
        # miss field but merges
        open(self.otherbib, 'w').write(self.bibtex_miss_doi_field)
        paperscmd(f'add {self.otherbib} --mode u --bibtex {self.mybib}')
        expected = self.bibtex
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_miss_titauthor_merge(self):
        # miss field but merges
        open(self.otherbib, 'w').write(self.bibtex_miss_titauthor_field)
        paperscmd(f'add {self.otherbib} --mode u --bibtex {self.mybib} --debug')
        expected = self.bibtex
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change
