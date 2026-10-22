import os
import shutil
import subprocess as sp
import tempfile
import unittest
from pathlib import Path

from papers.entries import parse_bibtex_file, parse_string, get_entry_val, library_from_entries
from papers.encoding import latex_to_unicode_library

from papers.bib import Biblio
from papers.utils import PapersExit
from unittest.mock import patch

from tests.common import PAPERSCMD, paperscmd, prepare_paper, prepare_paper2, BibTest, FileTest, entry


def unicode_fields(entry):
    "the fields of an entry but its key, with LaTeX decoded to unicode (for comparison)"
    e = latex_to_unicode_library(library_from_entries([entry])).entries[0]
    return {k: get_entry_val(e, k, '') for k, _ in e.items() if k != 'ID'}


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
        db1 = parse_bibtex_file(self.mybib)
        self.assertTrue(len(db1.entries) > 0)
        entry1 = db1.entries[0]
        file = get_entry_val(entry1, 'file', '').strip()
        if 'file' in entry1:
            entry1.pop('file')
        db2 = parse_string(self.bibtex)
        if doi_only:
            self.assertEqual([e['doi'] for e in db1.entries], [e['doi'] for e in db2.entries])  # entry is as expected
        elif dismiss_key:
            f = unicode_fields
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
        db = parse_bibtex_file(self.mybib)
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
        # the library and the scanned folder in a temporary directory, not in the current directory
        self.tmp = tempfile.TemporaryDirectory()
        self.libdir = self.tmp.name
        self.somedir = os.path.join(self.libdir, 'somedir')
        self.subdir = os.path.join(self.somedir, 'subdir')
        os.makedirs(self.subdir)
        shutil.copy(self.pdf1, self.somedir)
        shutil.copy(self.pdf2, self.subdir)
        self.mybib = os.path.join(self.libdir, 'papers.bib')
        paperscmd(f'init --bibtex {self.mybib}', cwd=self.libdir)

    def test_adddir_pdf(self):
        self.my = Biblio.load(self.mybib, '')
        self.my.scan_dir(self.somedir)
        self.assertEqual(len(self.my.db.entries), 2)
        keys = [self.my.db.entries[0]['ID'], self.my.db.entries[1]['ID']]
        self.assertEqual(sorted(keys), sorted([self.newkey1, self.newkey2]))  # PDF: update key

    def test_adddir_pdf_cmd(self):
        paperscmd(f'add --recursive --bibtex {self.mybib} {self.somedir}', cwd=self.libdir)
        self.my = Biblio.load(self.mybib, '')
        self.assertEqual(len(self.my.db.entries), 2)
        keys = [self.my.db.entries[0]['ID'], self.my.db.entries[1]['ID']]
        self.assertEqual(sorted(keys), sorted([self.newkey1, self.newkey2])) # PDF: update key

    def tearDown(self):
        self.tmp.cleanup()



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


def no_fetch(*args, **kwargs):
    raise AssertionError('no network query expected')


class TestAddExistingEntry(FileTest):
    """add FILE with the DOI of a library entry: the file is attached to it,
    without network query nor duplicate dialogue"""

    def setUp(self):
        super().setUp()
        self.a = self.write('lib', 'files', 'a.pdf')
        self.new = self.write('src', 'new.pdf')
        self.si = self.write('src', 'si.pdf')
        self.bib(entry('one2000', 'files/a.pdf', doi='10.1000/one'),
                 entry('two2000', doi='10.48550/arXiv.2101.01234'))
        self.lib('config files move')

    def add(self, cmd):
        with patch("papers.bib.fetch_bibtex_by_doi", no_fetch), \
                patch('papers.bib.extract_pdf_metadata', no_fetch), \
                patch('papers.extract.fetch_bibtex_by_doi', no_fetch), \
                patch('builtins.input', no_fetch):
            return self.out(cmd)

    def keys(self):
        return sorted(e.key for e in Biblio.load(self.path('lib', 'papers.bib'), '').entries)

    def test_doi_option(self):
        out = self.add(f'add {self.new} --doi 10.1000/ONE --title Other')
        self.assertIn('already in library: one2000 (+1 file)', out)
        self.assertEqual(self.keys(), ['one2000', 'two2000'])
        files = self.files('one2000')
        self.assertEqual(files[0], self.a)  # untouched
        self.assertEqual(len(files), 2)
        self.assertTrue(files[1].startswith(self.path('lib', 'files')))
        self.assertFalse(os.path.exists(self.new))  # files: move
        self.assertNotIn('Other', open(self.path('lib', 'papers.bib')).read())

    def test_doi_option_and_attach(self):
        self.add(f'add {self.new} --doi 10.1000/one --attach {self.si}')
        self.assertEqual(len(self.files('one2000')), 3)

    def test_doi_without_file(self):
        out = self.add(f'add --doi 10.1000/one --attach {self.si} --link')
        self.assertIn('already in library: one2000', out)
        self.assertEqual(self.files('one2000'), [self.a, self.si])

    def test_arxiv_doi(self):
        Path(self.path('lib', 'papers.bib')).write_text(
            '@article{arx2021,\n author = {Some One},\n archiveprefix = {arXiv},\n eprint = {2101.01234},\n'
            ' title = {Title of arx2021},\n year = {2021}\n}\n')
        self.add(f'add {self.new} --doi 10.48550/arXiv.2101.01234v2 --link')
        self.assertEqual(self.files('arx2021'), [self.new])

    def test_doi_of_pdf_metadata(self):
        with patch('papers.bib.parse_doi_from_pdf_metadata', return_value='10.1000/one'):
            out = self.add(f'add {self.new} --link')
        self.assertIn('already in library: one2000', out)
        self.assertEqual(self.files('one2000'), [self.a, self.new])

    def test_doi_of_pdf_text(self):
        with patch('papers.bib.parse_doi_from_pdf_metadata', return_value=None), \
                patch('papers.bib.pdfhead', return_value='Title of one2000\n doi:10.1000/one'), \
                patch('papers.bib.pdftail', return_value=''):
            self.add(f'add {self.new} --link')
        self.assertEqual(self.files('one2000'), [self.a, self.new])

    def test_several_pdfs_are_not_prefetched(self):
        with patch('papers.bib.parse_doi_from_pdf_metadata', return_value='10.1000/one'), \
                patch('papers.cli.entry_cmds.prefetch_pdf_metadata', no_fetch):
            self.add(f'add {self.new} {self.si} --link')
        self.assertEqual(self.files('one2000'), [self.a, self.new, self.si])

    def test_same_file_again(self):
        out = self.add(f'add {self.a} --doi 10.1000/one')
        self.assertIn('already in library: one2000\n', out)
        self.assertEqual(self.files('one2000'), [self.a])

    def test_identical_file_not_attached(self):
        copy = self.write('src', 'copy.pdf', content='a.pdf')  # the content of files/a.pdf
        out = self.add(f'add {copy} --doi 10.1000/one')
        self.assertIn('already in library: one2000\n', out)
        self.assertIn(f'{copy}: not attached, the entry has the same file: {self.a}', out)
        self.assertEqual(self.files('one2000'), [self.a])
        self.assertTrue(os.path.exists(copy))  # left where it is

    def test_recursive(self):
        # add -R: a PDF of the DOI of a library entry is attached to it; one with its content is not
        self.write('src', 'sub', 'copy.pdf', content='a.pdf')
        with patch('papers.bib.parse_doi_from_pdf_metadata', return_value='10.1000/one'):
            out = self.add(f'add -R {self.path("src")}')
        self.assertEqual(self.keys(), ['one2000', 'two2000'])
        self.assertEqual(out.count('already in library: one2000 (+1 file)\n'), 2)  # new.pdf, si.pdf
        self.assertIn('already in library: one2000\n', out)  # sub/copy.pdf
        files = self.files('one2000')
        self.assertEqual(len(files), 3)
        self.assertEqual(files[0], self.a)
        self.assertEqual(sorted(Path(f).read_text() for f in files), ['a.pdf', 'new.pdf', 'si.pdf'])
        self.assertTrue(all(f.startswith(self.path('lib', 'files')) for f in files))
        self.assertTrue(os.path.exists(self.path('src', 'sub', 'copy.pdf')))

    def test_no_check_duplicate_fetches(self):
        fetched = '@article{x,\n author = {Some One},\n doi = {10.1000/one},\n title = {Title of one2000},\n year = {2000}\n}\n'
        with patch('papers.bib.fetch_bibtex_by_doi', return_value=fetched) as fetch:
            self.lib(f'add {self.new} --doi 10.1000/one --no-check-duplicate --link')
        fetch.assert_called_once()
        self.assertEqual(len(self.keys()), 3)

    def test_doi_option_ignores_other_fields(self):
        # the entry is in the library: --title is not applied, with a warning
        with self.assertLogs('papers', level='WARNING') as logs:
            self.add(f'add {self.new} --doi 10.1000/one --title Other --key other --link')
        self.assertIn('ignored: key, title', '\n'.join(logs.output))
        self.assertEqual(self.keys(), ['one2000', 'two2000'])


FETCHED = ('@article{fetched2000,\n author = {Fetched, Author},\n doi = {10.1000/fetched},\n'
           ' journal = {Fetched Journal},\n title = {Fetched title},\n year = {2000}\n}\n')


class TestAddMetadataOptions(FileTest):
    """the fields given on the command line (--title, --year, --key...)
    replace those of the fetched or extracted entry"""

    def setUp(self):
        super().setUp()
        self.pdf = self.write('src', 'paper.pdf')
        self.si = self.write('src', 'si.pdf')

    def add(self, cmd):
        with patch('papers.bib.fetch_bibtex_by_doi', return_value=FETCHED), \
                patch('papers.bib.extract_pdf_metadata', return_value=FETCHED), \
                patch('papers.cli.entry_cmds.prefetch_pdf_metadata', no_fetch), \
                patch('builtins.input', no_fetch):
            self.lib(cmd)
        biblio = Biblio.load(self.path('lib', 'papers.bib'), '')
        self.assertEqual(len(biblio.entries), 1)
        return biblio, biblio.entries[0]

    def test_title(self):
        _, e = self.add(f'add {self.pdf} --title "My Title" --link')
        self.assertEqual(e['title'], 'My Title')
        self.assertEqual(e['journal'], 'Fetched Journal')  # the other fields are fetched

    def test_year_and_generated_key(self):
        _, e = self.add(f'add {self.pdf} --year 1999 --link')
        self.assertEqual(e['year'], '1999')
        self.assertEqual(e.key, 'fetched1999')  # the key template sees the year given

    def test_key(self):
        _, e = self.add(f'add {self.pdf} --key mykey --year 1999 --link')
        self.assertEqual(e.key, 'mykey')

    def test_author(self):
        _, e = self.add(f'add {self.pdf} --author "Given, Name" --link')
        self.assertEqual(e['author'], 'Given, Name')
        self.assertEqual(e.key, 'given2000')

    def test_journal(self):
        _, e = self.add(f'add {self.pdf} --journal "Other Journal" --link')
        self.assertEqual(e['journal'], 'Other Journal')

    def test_type(self):
        _, e = self.add(f'add {self.pdf} --type book --link')
        self.assertEqual(e.entry_type, 'book')

    def test_metadata(self):
        _, e = self.add(f'add {self.pdf} --metadata volume=12 title=Other --link')
        self.assertEqual((e['volume'], e['title']), ('12', 'Other'))

    def test_files_are_merged(self):
        biblio, e = self.add(f'add {self.pdf} --attach {self.si} --title T --link')
        self.assertEqual(biblio.get_files(e), [self.pdf, self.si])

    def test_doi_without_file(self):
        _, e = self.add('add --doi 10.1000/fetched --title "My Title" --key mykey')
        self.assertEqual((e.key, e['title'], e['journal']), ('mykey', 'My Title', 'Fetched Journal'))

    def test_bibtex_file(self):
        bib = self.write('src', 'one.bib', content=FETCHED)
        _, e = self.add(f'add {bib} --title "My Title" --key mykey')
        self.assertEqual((e.key, e['title']), ('mykey', 'My Title'))

    def test_bibtex_file_with_several_entries(self):
        bib = self.write('src', 'two.bib', content=FETCHED + '\n' + entry('other2000'))
        with self.assertRaises(PapersExit) as cm:
            self.lib(f'add {bib} --title "My Title"')
        self.assertIn('2 entries', str(cm.exception))
        self.assertEqual(Biblio.load(self.path('lib', 'papers.bib'), '').entries, [])

    def test_directory(self):
        with self.assertRaises(PapersExit):
            self.lib(f'add -R {self.path("src")} --title "My Title"')

    def test_duplicate_with_other_title(self):
        # the title given conflicts with the library entry: --on-duplicate decides
        self.bib(FETCHED)
        with patch('papers.bib.extract_pdf_metadata', return_value=FETCHED), \
                patch('papers.bib.parse_doi_from_pdf_metadata', return_value=None):
            self.lib(f'add {self.pdf} --title "My Title" --on-duplicate update --link --no-query-doi')
        e = Biblio.load(self.path('lib', 'papers.bib'), '').entries[0]
        self.assertEqual((e.key, e['title']), ('fetched2000', 'My Title'))
