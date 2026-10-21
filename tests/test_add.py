import os
import shutil
import subprocess as sp
import tempfile
import unittest
from pathlib import Path

import bibtexparser
from papers.entries import parse_file as bp_parse_file, parse_string, get_entry_val
from papers.encoding import entry_to_unicode_dict

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
        db1 = bp_parse_file(self.mybib)
        self.assertTrue(len(db1.entries) > 0)
        entry1 = db1.entries[0]
        file = get_entry_val(entry1, 'file', '').strip()
        if 'file' in entry1:
            entry1.pop('file')
        db2 = parse_string(self.bibtex)
        if doi_only:
            self.assertEqual([e['doi'] for e in db1.entries], [e['doi'] for e in db2.entries])  # entry is as expected
        elif dismiss_key:
            f = entry_to_unicode_dict
            self.assertEqual([f(e) for e in db1.entries], [f(e) for e in db2.entries])  # entry is as expected
        else:
            self.assertEqual([dict(e.items()) for e in db1.entries], [dict(e.items()) for e in db2.entries])
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
        db = bp_parse_file(self.mybib)
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
        paperscmd(f'add -rc --bibtex {self.mybib} --filesdir {self.filesdir} {self.pdf} --attach {self.si}')

        file_ = self._checkbib(dismiss_key=True)
        self.assertTrue(';' in file_)
        main_, si_ = file_.split(';')
        main = self._checkfile(main_)
        si = self._checkfile(si_)
        # flat layout: the main file is named after the entry, the other
        # one next to it, with its original name as a label
        self.assertEqual(os.path.dirname(main), os.path.dirname(si))
        name = Path(self.file_rename).stem
        self.assertEqual(os.path.basename(main), name + '.pdf')
        self.assertEqual(os.path.basename(si), name + '--' + os.path.basename(self.si))
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

    def test_addbib_cmd_update_key(self):
        # --update-key regenerates the key of entries added from a bibtex file
        # according to the key template (issue #108)
        paperscmd(f'add {self.somebib} --bibtex {self.mybib} --update-key')
        bib = Biblio.load(self.mybib, '')
        self.assertEqual(len(bib.db.entries), 2)
        self.assertEqual(bib.db.entries[0]['ID'], self.key1)  # pre-existing entry untouched
        self.assertEqual(bib.db.entries[1]['ID'], self.newkey2)  # default template {author}{year}

    def test_addbib_cmd_update_key_custom_template(self):
        paperscmd(f'add {self.somebib} --bibtex {self.mybib} -u --key-template "{{year}}"')
        bib = Biblio.load(self.mybib, '')
        self.assertEqual(len(bib.db.entries), 2)
        self.assertEqual(bib.db.entries[0]['ID'], self.key1)
        self.assertEqual(bib.db.entries[1]['ID'], self.year)

    def test_attachment_fails_with_multiple_entries(self):
        func = lambda: paperscmd(f'add {self.pdf} {self.pdf} --bibtex {self.mybib} --filesdir {self.filesdir} --attachment {self.pdf}')
        self.assertRaises(Exception, func)

    def test_fails_with_no_file_and_no_doi(self):
        func = lambda: paperscmd(f'add --bibtex {self.mybib} --filesdir {self.filesdir} --attachment {self.pdf}')
        self.assertRaises(Exception, func)

    def test_fails_with_no_file_and_doi_but_no_query_doi(self):
        func = lambda: paperscmd(f'add --bibtex {self.mybib} --filesdir {self.filesdir} --attachment {self.pdf} --doi 123 --no-query-doi')
        self.assertRaises(Exception, func)

    def test_add_doi_only_no_pdf(self):
        """papers add --doi X --bibtex Y creates bibtex entry without PDF attachment"""
        open(self.mybib, 'w').write('')
        doi = '10.5194/bg-8-515-2011'  # use prepare_paper DOI (key1)
        paperscmd(f'add --bibtex {self.mybib} --doi {doi}')
        bib = Biblio.load(self.mybib, '')
        self.assertEqual(len(bib.db.entries), 1)
        self.assertEqual(bib.db.entries[0]['doi'], doi)
        self.assertNotIn('file', bib.db.entries[0])  # no file attachment

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


    # Field order after exact-duplicate merge: existing entry fields first, then merged 'file' appended
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

    # the auto-generated key from an unknown entry is the slugified doi (issue #105)
    bibtex_conflict_key_fixed = """@article{10-5194-bg-8-515-2011xxx,
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
        # an entry that differs by its key only is not asked about
        open(self.otherbib, 'w').write(self.bibtex_otherkey)
        sp.check_call(f'{PAPERSCMD} add {self.otherbib} --bibtex {self.mybib} < /dev/null', shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex) # entries did not change


    def test_add_same_but_key_update(self):
        open(self.otherbib, 'w').write(self.bibtex_otherkey)
        paperscmd(f'add {self.otherbib} --bibtex {self.mybib} -u')
        self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex) # entries did not change


    def test_add_same_but_key_error_mode(self):
        # nothing to decide: no error, even with --on-duplicate error
        open(self.otherbib, 'w').write(self.bibtex_otherkey)
        paperscmd(f'add {self.otherbib} --bibtex {self.mybib} --on-duplicate error')
        self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex)


    def test_add_same_but_file(self):
        open(self.otherbib, 'w').write(self.bibtex_hasfile)
        paperscmd(f'add {self.otherbib} --bibtex {self.mybib} -u --relative-path')
        self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex_hasfile) # entries did not change


    def test_add_conflict_key_check_raises(self):
        # key conflict: raises exception whatever mode is indicated
        open(self.otherbib, 'w').write(self.bibtex_conflict_key)
        func = lambda : paperscmd(f'add {self.otherbib} --bibtex {self.mybib} --on-duplicate skip --debug')
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
        paperscmd(f'add {self.otherbib} --no-check-duplicate --bibtex {self.mybib} --on-duplicate error')
        expected = self.bibtex+'\n\n'+self.bibtex_same_doi
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_same_doi_other_key(self):
        # same DOI, same content, other key: nothing to decide, the library is unchanged
        open(self.otherbib, 'w').write(self.bibtex_same_doi)
        paperscmd(f'add {self.otherbib} --bibtex {self.mybib} --on-duplicate error')
        self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex)

    def test_add_same_doi_conflict_fails(self):
        open(self.otherbib, 'w').write(self.bibtex_same_doi.replace('{feb}', '{mar}'))
        func = lambda : paperscmd(f'add {self.otherbib} --bibtex {self.mybib} --on-duplicate error')
        self.assertRaises(Exception, func)

    def test_add_same_doi_update_key(self):
        # test doi and update key and identical entry detected
        open(self.otherbib, 'w').write(self.bibtex_same_doi)
        paperscmd(f'add {self.otherbib} --update-key --bibtex {self.mybib} --on-duplicate error')
        expected = self.bibtex
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_miss_field_nothing_new(self):
        # the added entry has fewer fields: nothing to add, nothing to decide
        open(self.otherbib, 'w').write(self.bibtex_miss_field)
        paperscmd(f'add {self.otherbib} --bibtex {self.mybib} --on-duplicate error')
        self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex)

    def test_add_more_fields_fails(self):
        # the library entry has fewer fields: they would be added, which is a decision
        open(self.mybib, 'w').write(self.bibtex_miss_field)
        open(self.otherbib, 'w').write(self.bibtex)
        func = lambda : paperscmd(f'add {self.otherbib} --bibtex {self.mybib} --on-duplicate error')
        self.assertRaises(Exception, func)

    def test_add_miss_merge(self):
        # miss field but merges
        open(self.otherbib, 'w').write(self.bibtex_miss_field)
        paperscmd(f'add {self.otherbib} --on-duplicate keep --bibtex {self.mybib}')
        expected = self.bibtex
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_miss_doi_merge(self):
        # miss field but merges
        open(self.otherbib, 'w').write(self.bibtex_miss_doi_field)
        paperscmd(f'add {self.otherbib} --on-duplicate keep --bibtex {self.mybib}')
        expected = self.bibtex
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_miss_titauthor_merge(self):
        # miss field but merges
        open(self.otherbib, 'w').write(self.bibtex_miss_titauthor_field)
        paperscmd(f'add {self.otherbib} --on-duplicate keep --bibtex {self.mybib} --debug')
        expected = self.bibtex
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change


class TestScanCurrentDir(unittest.TestCase):

    def test_scan_root_not_skipped(self):
        # issue #100: `papers add . --recursive` silently skipped the scan root
        # because basename('.') looks like a hidden directory
        from papers.utils import set_directory
        bibtex = "@article{A2000,\n author = {A. Author},\n title = {One},\n year = {2000}\n}"
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'ref.bib'), 'w').write(bibtex)
            lib = os.path.join(d, 'lib.bib')
            open(lib, 'w').write('')
            my = Biblio.load(lib, '')
            with set_directory(d):
                my.scan_dir('.')
            self.assertEqual(len(my.db.entries), 1)


class TestAddBibRelocateFiles(BibTest):
    """`papers add source.bib` into another library: file links must be
    resolved relative to the source bibtex and stored so that they are valid
    from the destination bibtex"""

    bibtex = """@article{Author2000,
 author = {A. Author},
 file = {:pdfs/paper.pdf:pdf},
 title = {Some Title},
 year = {2000}
}"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, 'src')
        self.dest = os.path.join(self.tmp.name, 'dest')
        os.makedirs(os.path.join(self.src, 'pdfs'))
        os.makedirs(os.path.join(self.dest, 'files'))
        self.pdf = os.path.join(self.src, 'pdfs', 'paper.pdf')
        open(self.pdf, 'w').write('not really a pdf')
        open(os.path.join(self.src, 'papers.bib'), 'w').write(self.bibtex)
        self.mybib = os.path.join(self.dest, 'references.bib')
        open(self.mybib, 'w').write('')

    def tearDown(self):
        self.tmp.cleanup()

    def _file_field(self):
        bib = Biblio.load(self.mybib, '')
        self.assertEqual(len(bib.entries), 1)
        return get_entry_val(bib.entries[0], 'file', '')

    def test_relative_paths_point_to_source_file(self):
        # run from the source directory, with the bibtex given as a bare name
        paperscmd(f'add --no-query-doi --relative-paths --bibtex {self.mybib} --filesdir {self.dest}/files papers.bib', cwd=self.src)
        field = self._file_field()
        self.assertEqual(field, ':../src/pdfs/paper.pdf:pdf')
        # valid from the destination's point of view, file not moved
        self.assertTrue(os.path.exists(os.path.join(self.dest, '../src/pdfs/paper.pdf')))
        self.assertTrue(os.path.exists(self.pdf))

    def test_absolute_paths_point_to_source_file(self):
        paperscmd(f'add --no-query-doi --absolute-paths --bibtex {self.mybib} papers.bib', cwd=self.src)
        self.assertEqual(self._file_field(), f':{self.pdf}:pdf')

    def test_rename_copy_into_destination_filesdir(self):
        paperscmd(f'add --no-query-doi --relative-paths -rc --bibtex {self.mybib} --filesdir {self.dest}/files papers.bib', cwd=self.src)
        field = self._file_field()
        self.assertEqual(field, ':files/author_2000_some-title.pdf:pdf')
        self.assertTrue(os.path.exists(os.path.join(self.dest, 'files', 'author_2000_some-title.pdf')))
        self.assertTrue(os.path.exists(self.pdf))  # copied, not moved


class TestAddDuplicateKeepsExistingKey(BibTest):
    """a duplicate of an existing entry is merged under the existing entry's
    key, whatever the mode, with or without -u/--update-key"""

    existing = """@article{Perrette2013ESD,
 author = {Perrette, M. and Landerer, F. and Riva, R. and Frieler, K. and Meinshausen, M.},
 doi = {10.5194/esd-4-11-2013},
 journal = {Earth System Dynamics},
 title = {A scaling approach to project regional sea level rise and its uncertainties},
 year = {2013}
}"""

    # same DOI, other author formatting, one more field
    new = """@article{perrette_landerer2013,
 author = {M. Perrette and F. Landerer and R. Riva and K. Frieler and M. Meinshausen},
 doi = {10.5194/esd-4-11-2013},
 journal = {Earth System Dynamics},
 pages = {11-29},
 title = {A scaling approach to project regional sea level rise and its uncertainties},
 year = {2013}
}"""

    def setUp(self):
        self.mybib = tempfile.mktemp(prefix='papers.bib')
        self.otherbib = tempfile.mktemp(prefix='papers.otherbib')
        open(self.mybib, 'w').write(self.existing)
        open(self.otherbib, 'w').write(self.new)

    def tearDown(self):
        os.remove(self.mybib)
        os.remove(self.otherbib)

    def _entry(self):
        bib = Biblio.load(self.mybib, '')
        self.assertEqual(len(bib.entries), 1)
        return bib.entries[0]

    def test_update_missing_keeps_existing_key(self):
        paperscmd(f'add {self.otherbib} --bibtex {self.mybib} -u --on-duplicate keep')
        e = self._entry()
        self.assertEqual(e['ID'], 'Perrette2013ESD')
        self.assertEqual(e['pages'], '11-29')  # missing field merged in
        self.assertEqual(e['author'], 'Perrette, M. and Landerer, F. and Riva, R. and Frieler, K. and Meinshausen, M.')  # existing wins

    def test_update_with_new_keeps_existing_key(self):
        open(self.otherbib, 'w').write(self.new.replace('Earth System Dynamics', 'Earth Syst. Dynam.'))
        for options in ('-u --on-duplicate update', '--on-duplicate update'):
            open(self.mybib, 'w').write(self.existing)
            paperscmd(f'add {self.otherbib} --bibtex {self.mybib} {options}')
            e = self._entry()
            self.assertEqual(e['ID'], 'Perrette2013ESD')
            self.assertEqual(e['journal'], 'Earth Syst. Dynam.')  # new wins
            # the same names in another order are not a conflict: the library spelling stays
            self.assertEqual(e['author'], 'Perrette, M. and Landerer, F. and Riva, R. and Frieler, K. and Meinshausen, M.')

    def test_overwrite_keeps_existing_key(self):
        # deprecated -m o: --on-duplicate update
        paperscmd(f'add {self.otherbib} --bibtex {self.mybib} -m o')
        self.assertEqual(self._entry()['ID'], 'Perrette2013ESD')

    def test_append_keeps_existing_key_and_generates_new(self):
        # deprecated -m a: --no-check-duplicate
        paperscmd(f'add {self.otherbib} --bibtex {self.mybib} -u -m a')
        bib = Biblio.load(self.mybib, '')
        self.assertEqual(sorted(e['ID'] for e in bib.entries), ['Perrette2013ESD', 'perrette_landerer2013'])


class TestAddWithoutDoi(unittest.TestCase):
    """an entry described on the command line (e.g. an old paper without DOI),
    with its PDF attached"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mybib = os.path.join(self.tmp.name, 'papers.bib')
        self.filesdir = os.path.join(self.tmp.name, 'files')
        self.pdf = os.path.join(self.tmp.name, 'old paper.pdf')
        open(self.mybib, 'w').write('')
        open(self.pdf, 'w').write('not really a pdf')

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_metadata_and_attachment(self):
        paperscmd(f'add --bibtex {self.mybib} --filesdir {self.filesdir} --rename '
                  f'--title "Self-consistent equilibrium ocean tides" --author "Agnew, Duncan C. and Farrell, W. E." '
                  f'--year 1978 --attachment "{self.pdf}"')
        bib = Biblio.load(self.mybib, self.filesdir)
        self.assertEqual(len(bib.entries), 1)
        e = bib.entries[0]
        self.assertEqual(e['title'], 'Self-consistent equilibrium ocean tides')
        self.assertEqual(e['year'], '1978')
        files = bib.get_files(e)
        self.assertEqual(len(files), 1)
        self.assertTrue(os.path.abspath(files[0]).startswith(self.filesdir))  # --rename moved it
        self.assertFalse(os.path.exists(self.pdf))
