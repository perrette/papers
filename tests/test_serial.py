# This file contains tests that are copied from other tests in tests/test_*.py
# that exhibited conflicts and failures when run in parallel with --dist loadfile
# and therefore have to be run in series.

# TODO A better way of doing this is something like --dist loadgroup possibly
# with explicit xdist_groups

import os
import shutil
import subprocess as sp
import tempfile
import unittest
from pathlib import Path

import bibtexparser

from papers.bib import Biblio
from tests.common import PAPERSCMD, paperscmd, prepare_paper, prepare_paper2, BibTest


# from tests/test_filesheck.py
class TestFileCheck(BibTest):

    def setUp(self):
        (
            self.pdf,
            self.doi,
            self.key,
            self.newkey,
            self.year,
            self.bibtex,
            self.file_rename,
        ) = prepare_paper()
        self.assertTrue(os.path.exists(self.pdf))
        self.mybib = tempfile.mktemp(prefix="papers.bib")
        self.filesdir = tempfile.mktemp(prefix="papers.files")
        open(self.mybib, "w").write(self.bibtex)
        # paperscmd(f'install --local --bibtex {self.mybib} --filesdir {self.filesdir}'
        self.assertTrue(os.path.exists(self.mybib))

    def test_filecheck_rename(self):
        paperscmd(
            f"""add --bibtex {self.mybib} --filesdir {self.filesdir} {self.pdf} --doi {self.doi} << EOF
u
EOF"""
        )
        file_rename = os.path.join(self.filesdir, self.file_rename)
        self.assertFalse(os.path.exists(file_rename))
        self.assertTrue(os.path.exists(self.pdf))
        paperscmd(
            f"filecheck --bibtex {self.mybib} --filesdir {self.filesdir} --rename"
        )
        self.assertTrue(os.path.exists(file_rename))
        self.assertFalse(os.path.exists(self.pdf))
        biblio = Biblio.load(self.mybib, "")
        e = biblio.entries[[e["ID"] for e in biblio.entries].index(self.key)]
        files = biblio.get_files(e)
        self.assertTrue(len(files) == 1)
        self.assertEqual(files[0], os.path.abspath(file_rename))

    def tearDown(self):
        if os.path.exists(self.filesdir):
            shutil.rmtree(self.filesdir)
        if os.path.exists(self.mybib):
            os.remove(self.mybib)
        if os.path.exists(".papersconfig.json"):
            os.remove(".papersconfig.json")


# from tests/test_add.py
class TestAdd(BibTest):

    def setUp(self):
        (
            self.pdf,
            self.doi,
            self.key,
            self.newkey,
            self.year,
            self.bibtex,
            self.file_rename,
        ) = prepare_paper()
        self.assertTrue(os.path.exists(self.pdf))
        self.mybib = tempfile.mktemp(prefix="papers.bib")
        self.filesdir = tempfile.mktemp(prefix="papers.files")
        open(self.mybib, "w").write("")
        # paperscmd(f'install --local --bibtex {self.mybib} --filesdir {self.filesdir}'
        self.assertTrue(os.path.exists(self.mybib))

    def _checkbib(self, doi_only=False, dismiss_key=False):
        db1 = bibtexparser.load(open(self.mybib))
        self.assertTrue(len(db1.entries) > 0)
        file = db1.entries[0].pop("file").strip()
        db2 = bibtexparser.loads(self.bibtex)
        if doi_only:
            self.assertEqual(
                [e["doi"] for e in db1.entries], [e["doi"] for e in db2.entries]
            )  # entry is as expected
            # self.assertEqual([e['title'].lower() for e in db1.entries], [e['title'].lower() for e in db2.entries]) # entry is as expected
        elif dismiss_key:
            f = lambda e: bibtexparser.customization.convert_to_unicode(
                {k: e[k] for k in e if k != "ID"}
            )
            self.assertEqual(
                [f(e) for e in db1.entries], [f(e) for e in db2.entries]
            )  # entry is as expected
        else:
            self.assertEqual(db1.entries, db2.entries)  # entry is as expected
        return file

    def _checkfile(self, file):
        _, file, type = file.split(":")
        self.assertEqual(type, "pdf")  # file type is PDF
        file = os.path.abspath(os.path.join(os.path.dirname(self.mybib), file))
        self.assertTrue(os.path.exists(file))  # file link is valid
        return file

    def test_fails_without_install(self):
        os.remove(self.mybib)
        func = lambda: paperscmd(
            f"add {self.pdf} --bibtex {self.mybib} --files {self.filesdir}"
        )
        self.assertRaises(Exception, func)

    def test_add(self):
        self.assertTrue(os.path.exists(self.mybib))
        paperscmd(f"add --bibtex {self.mybib} {self.pdf}")

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

        paperscmd(
            f"add -rc --bibtex {self.mybib} --filesdir {self.filesdir} {self.pdf}"
        )

        file_ = self._checkbib(dismiss_key=True)  # 'file:pdf'
        file = self._checkfile(file_)
        self.assertEqual(
            file, os.path.join(self.filesdir, self.file_rename)
        )  # update key since pdf
        self.assertTrue(os.path.exists(self.pdf))  # old pdf still exists

    def test_add_rename_copy_journal(self):
        """
        Tests that demanding a {journal} in the --name-template works.
        Lightly begged/borrowed/stolen from the above test.
        """
        paperscmd(
            f'add --rename --copy --name-template "{{journal}}/{{authorX}}_{{year}}_{{title}}" --name-title-sep - --name-author-sep _ --bibtex {self.mybib} --filesdir {self.filesdir} {self.pdf}'
        )  # need to escape the {} in f-strings by doubling those curly braces.

        file_ = self._checkbib(dismiss_key=True)
        the_file = self._checkfile(file_)
        self.assertTrue(os.path.exists(self.pdf))
        new_path = str(the_file).split(os.path.sep)
        old_path = str(os.path.join(self.filesdir, self.file_rename)).split(os.path.sep)
        self.assertEqual(old_path[-1], new_path[-1])
        self.assertEqual(old_path[0], new_path[0])
        db = bibtexparser.load(open(self.mybib))
        journal = db.entries[0]["journal"]
        self.assertEqual(journal, new_path[-2])  # TODO a little gross, hardcoded

    def test_add_rename(self):

        pdfcopy = tempfile.mktemp(prefix="myref_test", suffix=".pdf")
        shutil.copy(self.pdf, pdfcopy)

        paperscmd(
            f"add -r --bibtex {self.mybib} --filesdir {self.filesdir} {pdfcopy} --debug"
        )

        file_ = self._checkbib(dismiss_key=True)  # 'file:pdf'
        file = self._checkfile(file_)
        self.assertEqual(
            file, os.path.join(self.filesdir, self.file_rename)
        )  # update key since pdf
        self.assertFalse(os.path.exists(pdfcopy))

    def tearDown(self):
        if os.path.exists(self.filesdir):
            shutil.rmtree(self.filesdir)
        if os.path.exists(self.mybib):
            os.remove(self.mybib)
        if os.path.exists(".papersconfig.json"):
            os.remove(".papersconfig.json")


class TestAdd2(TestAdd):

    def setUp(self):
        (
            self.pdf,
            self.si,
            self.doi,
            self.key,
            self.newkey,
            self.year,
            self.bibtex,
            self.file_rename,
        ) = prepare_paper2()
        self.assertTrue(os.path.exists(self.pdf))
        self.mybib = tempfile.mktemp(prefix="papers.bib")
        self.filesdir = tempfile.mktemp(prefix="papers.files")
        # paperscmd(f'install --local --bibtex {self.mybib} --filesdir {self.filesdir}'
        open(self.mybib, "w").write("")

    def test_add_attachment(self):
        paperscmd(
            f"add -rc --bibtex {self.mybib} --filesdir {self.filesdir} {self.pdf} -a {self.si}"
        )

        file_ = self._checkbib(dismiss_key=True)
        self.assertTrue(";" in file_)
        main_, si_ = file_.split(";")
        main = self._checkfile(main_)
        si = self._checkfile(si_)
        # files have been moved in an appropriately named directory
        dirmain = os.path.dirname(main)
        dirsi = os.path.dirname(si)
        self.assertEqual(dirmain, dirsi)
        self.assertEqual(Path(dirmain).name, Path(self.file_rename).stem)
        # individual files have not been renamed
        self.assertEqual(os.path.basename(main), os.path.basename(self.pdf))
        self.assertEqual(os.path.basename(si), os.path.basename(self.si))
        # old pdfs still exists
        self.assertTrue(os.path.exists(self.pdf))
        self.assertTrue(os.path.exists(self.si))


class TestAddBib(BibTest):

    def setUp(self):
        self.mybib = tempfile.mktemp(prefix="papers.bib")
        self.somebib = tempfile.mktemp(prefix="papers.somebib.bib")
        (
            self.pdf1,
            self.doi,
            self.key1,
            self.newkey1,
            self.year,
            self.bibtex1,
            self.file_rename1,
        ) = prepare_paper()
        (
            self.pdf2,
            self.si,
            self.doi,
            self.key2,
            self.newkey2,
            self.year,
            self.bibtex2,
            self.file_rename2,
        ) = prepare_paper2()
        open(self.mybib, "w").write(self.bibtex1)
        open(self.somebib, "w").write(self.bibtex2)
        self.my = Biblio.load(self.mybib, "")

    def test_addbib_method(self):
        self.assertTrue(self.key1 in [e["ID"] for e in self.my.db.entries])
        self.assertTrue(self.key2 not in [e["ID"] for e in self.my.db.entries])
        self.my.add_bibtex_file(self.somebib)
        self.assertEqual(len(self.my.db.entries), 2)
        self.assertEqual(self.my.db.entries[0]["ID"], self.key1)
        self.assertEqual(self.my.db.entries[1]["ID"], self.key2)

    def test_addbib_cmd(self):
        bib = Biblio.load(self.mybib, "")
        self.assertEqual(len(bib.db.entries), 1)
        self.assertEqual(bib.db.entries[0]["ID"], self.key1)
        paperscmd(f"add {self.somebib} --bibtex {self.mybib}")
        bib = Biblio.load(self.mybib, "")
        self.assertEqual(len(bib.db.entries), 2)
        self.assertEqual(bib.db.entries[0]["ID"], self.key1)
        self.assertEqual(bib.db.entries[1]["ID"], self.key2)

    def test_addbib_cmd_dryrun(self):
        bib = Biblio.load(self.mybib, "")
        self.assertEqual(len(bib.db.entries), 1)
        self.assertEqual(bib.db.entries[0]["ID"], self.key1)
        paperscmd(f"add {self.somebib} --bibtex {self.mybib} --dry-run")
        bib = Biblio.load(self.mybib, "")
        self.assertEqual(len(bib.db.entries), 1)
        self.assertEqual(bib.db.entries[0]["ID"], self.key1)
        self.assertTrue(self.key2 not in [e["ID"] for e in self.my.db.entries])

    def test_attachment_fails_with_multiple_entries(self):
        func = lambda: paperscmd(
            f"add {self.pdf} {self.pdf} --bibtex {self.mybib} --filesdir {self.filesdir} --attachment {self.pdf}"
        )
        self.assertRaises(Exception, func)

    def test_fails_with_no_file_and_no_doi(self):
        func = lambda: paperscmd(
            f"add --bibtex {self.mybib} --filesdir {self.filesdir} --attachment {self.pdf}"
        )
        self.assertRaises(Exception, func)

    def test_fails_with_no_file_and_doi_but_no_query_doi(self):
        func = lambda: paperscmd(
            f"add --bibtex {self.mybib} --filesdir {self.filesdir} --attachment {self.pdf} --doi 123 --no-query-doi"
        )
        self.assertRaises(Exception, func)

    def tearDown(self):
        os.remove(self.mybib)
        os.remove(self.somebib)
        if os.path.exists(".papersconfig.json"):
            os.remove(".papersconfig.json")


class TestAddDir(BibTest):

    def setUp(self):
        (
            self.pdf1,
            self.doi,
            self.key1,
            self.newkey1,
            self.year,
            self.bibtex1,
            self.file_rename1,
        ) = prepare_paper()
        (
            self.pdf2,
            self.si,
            self.doi,
            self.key2,
            self.newkey2,
            self.year,
            self.bibtex2,
            self.file_rename2,
        ) = prepare_paper2()
        self.somedir = tempfile.mktemp(prefix="papers.somedir")
        self.subdir = os.path.join(self.somedir, "subdir")
        os.makedirs(self.somedir)
        os.makedirs(self.subdir)
        shutil.copy(self.pdf1, self.somedir)
        shutil.copy(self.pdf2, self.subdir)
        self.mybib = tempfile.mktemp(prefix="papers.bib")
        paperscmd(f"install --local --no-prompt --bibtex {self.mybib}")

    def test_adddir_pdf(self):
        self.my = Biblio.load(self.mybib, "")
        self.my.scan_dir(self.somedir)
        self.assertEqual(len(self.my.db.entries), 2)
        keys = [self.my.db.entries[0]["ID"], self.my.db.entries[1]["ID"]]
        self.assertEqual(
            sorted(keys), sorted([self.newkey1, self.newkey2])
        )  # PDF: update key

    def test_adddir_pdf_cmd(self):
        paperscmd(f"add --recursive --bibtex {self.mybib} {self.somedir}")
        self.my = Biblio.load(self.mybib, "")
        self.assertEqual(len(self.my.db.entries), 2)
        keys = [self.my.db.entries[0]["ID"], self.my.db.entries[1]["ID"]]
        self.assertEqual(
            sorted(keys), sorted([self.newkey1, self.newkey2])
        )  # PDF: update key

    def tearDown(self):
        os.remove(self.mybib)
        shutil.rmtree(self.somedir)
        paperscmd(f"uninstall")


# The test below were written first. There are not systematic but they have the advantage to exist.
# Short after they have been written, they were considered deprecated.
# Now as I write these lines I cannot immediately grasp what is wrong with them.
# Probably best to keep them for now, and to review them at some point in the future to remove any redundancy with other tests.
class TestAddConflict(BibTest):
    # TODO: tear down in several smaller tests

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
        self.mybib = tempfile.mktemp(prefix="papers.bib")
        self.filesdir = tempfile.mktemp(prefix="papers.files")
        self.otherbib = tempfile.mktemp(prefix="papers.otherbib")
        # self.my = Biblio.newbib(self.mybib, self.filesdir)
        # paperscmd(f'install --local --bibtex {} --files {}'.format(self.mybib, self.filesdir))
        open(self.mybib, "w").write(self.bibtex)
        # open(self.otherbib, 'w').write('')
        # paperscmd(f'add {self.otherbib} --bibtex {self.mybib}')
        # self.assertMultiLineEqual(open(self.mybib).read().strip(), self.bibtex)

    def tearDown(self):
        os.remove(self.mybib)
        if os.path.exists(self.filesdir):
            shutil.rmtree(self.filesdir)
        if os.path.exists(self.otherbib):
            os.remove(self.otherbib)
        if os.path.exists(".papersconfig.json"):
            os.remove(".papersconfig.json")

    def test_add_same(self):
        open(self.otherbib, "w").write(self.bibtex)
        paperscmd(f"add {self.otherbib} --bibtex {self.mybib}")
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), self.bibtex
        )  # entries did not change

    def test_add_same_but_key_interactive(self):
        # fails in raise mode
        open(self.otherbib, "w").write(self.bibtex_otherkey)
        sp.check_call(
            f"echo u | {PAPERSCMD} add {self.otherbib} --bibtex {self.mybib}",
            shell=True,
        )
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), self.bibtex
        )  # entries did not change

    def test_add_same_but_key_update(self):
        open(self.otherbib, "w").write(self.bibtex_otherkey)
        paperscmd(f"add {self.otherbib} --bibtex {self.mybib} -u")
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), self.bibtex
        )  # entries did not change

    def test_add_same_but_key_fails(self):
        # fails in raise mode
        open(self.otherbib, "w").write(self.bibtex_otherkey)
        func = lambda x: paperscmd(
            f"add {self.otherbib} --bibtex {self.mybib} --mode r"
        )
        self.assertRaises(Exception, func)

    def test_add_same_but_file(self):
        open(self.otherbib, "w").write(self.bibtex_hasfile)
        paperscmd(f"add {self.otherbib} --bibtex {self.mybib} -u --relative-path")
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), self.bibtex_hasfile
        )  # entries did not change

    def test_add_conflict_key_check_raises(self):
        # key conflict: raises exception whatever mode is indicated
        open(self.otherbib, "w").write(self.bibtex_conflict_key)
        func = lambda: paperscmd(
            f"add {self.otherbib} --bibtex {self.mybib} --mode s --debug"
        )
        self.assertRaises(Exception, func)

    def test_add_conflict_key_nocheck_raises(self):
        # also when no check duplicate is indicated
        func = lambda: paperscmd(
            f"add {self.otherbib} --bibtex {self.mybib} --no-check-duplicate"
        )
        self.assertRaises(Exception, func)

    # def test_add_conflict_key_appends(self):
    #     # key conflict : ra
    #     open(self.otherbib, 'w').write(self.bibtex_conflict_key)
    #     paperscmd(f'add {} --no-check-duplicate --bibtex {} --mode r'.format(self.otherbib, self.mybib))
    #     expected = self.bibtex_conflict_key+'\n\n'+self.bibtex
    #     self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_add_conflict_key_update(self):
        # key conflict and update entry
        open(self.otherbib, "w").write(self.bibtex_conflict_key)
        paperscmd(f"add {self.otherbib} --bibtex {self.mybib} -u")
        expected = self.bibtex_conflict_key_fixed + "\n\n" + self.bibtex
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), expected
        )  # entries did not change

    def test_add_same_doi_unchecked(self):
        # does not normally test doi
        open(self.otherbib, "w").write(self.bibtex_same_doi)
        paperscmd(
            f"add {self.otherbib} --no-check-duplicate --bibtex {self.mybib} --mode r"
        )
        expected = self.bibtex + "\n\n" + self.bibtex_same_doi
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), expected
        )  # entries did not change

    def test_add_same_doi_fails(self):
        # test doi and triggers conflict
        open(self.otherbib, "w").write(self.bibtex_same_doi)
        func = lambda: paperscmd(f"add {self.otherbib} --bibtex {self.mybib} --mode r")
        self.assertRaises(Exception, func)

    def test_add_same_doi_update_key(self):
        # test doi and update key and identical entry detected
        open(self.otherbib, "w").write(self.bibtex_same_doi)
        paperscmd(f"add {self.otherbib} --update-key --bibtex {self.mybib} --mode r")
        expected = self.bibtex
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), expected
        )  # entries did not change

    def test_add_miss_field_fails(self):
        # miss field and triggers conflict
        open(self.otherbib, "w").write(self.bibtex_miss_field)
        func = lambda: paperscmd(f"add {self.otherbib} --bibtex {self.mybib} --mode r")
        self.assertRaises(Exception, func)

    def test_add_miss_merge(self):
        # miss field but merges
        open(self.otherbib, "w").write(self.bibtex_miss_field)
        paperscmd(f"add {self.otherbib} --mode u --bibtex {self.mybib}")
        expected = self.bibtex
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), expected
        )  # entries did not change

    def test_add_miss_doi_merge(self):
        # miss field but merges
        open(self.otherbib, "w").write(self.bibtex_miss_doi_field)
        paperscmd(f"add {self.otherbib} --mode u --bibtex {self.mybib}")
        expected = self.bibtex
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), expected
        )  # entries did not change

    def test_add_miss_titauthor_merge(self):
        # miss field but merges
        open(self.otherbib, "w").write(self.bibtex_miss_titauthor_field)
        paperscmd(f"add {self.otherbib} --mode u --bibtex {self.mybib} --debug")
        expected = self.bibtex
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), expected
        )  # entries did not change


# from tests/test_install.py
from papers.config import Config
from papers.config import CONFIG_FILE, CONFIG_FILE_LOCAL

from tests.common import (
    BaseTest as TestBaseInstall,
    LocalInstallTest,
    GlobalInstallTest,
)

bibtex2 = """@article{SomeOneElse2000,
 author = {Some One},
 doi = {10.5194/xxxx},
 title = {Interesting Stuff},
 year = {2000}
}"""


class TestLocalInstall(TestBaseInstall):

    def test_install(self):
        self.assertFalse(self._exists(self.mybib))
        self.assertFalse(self._exists(self.filesdir))
        self.papers(
            f"install --force --local --bibtex {self.mybib} --files {self.filesdir}"
        )
        # Config file was created:
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        # Values of config file match input:
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.assertFalse(config.git)
        # bibtex and files directory were created:
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))

    def test_install_defaults_no_preexisting_bibtex(self):
        self.assertFalse(self._exists(self.mybib))
        self.assertFalse(self._exists(self.filesdir))
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))
        # pre-existing bibtex?
        os.remove(self._path(self.anotherbib))
        self.assertFalse(self._exists(self.anotherbib))
        self.papers(f"install --force --local")
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        # self.assertEqual(config.bibtex, os.path.abspath(self._path("papers.bib")))
        self.assertEqual(config.bibtex, os.path.abspath(self._path("papers.bib")))
        self.assertEqual(config.filesdir, os.path.abspath(self._path("files")))
        self.assertFalse(config.git)

    def test_install_defaults_preexisting_bibtex(self):
        self.assertFalse(self._exists(self.mybib))
        self.assertFalse(self._exists(self.filesdir))
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))
        # pre-existing bibtex
        self.assertTrue(self._exists(self.anotherbib))
        self.assertFalse(self._exists("papers.bib"))
        self.papers(f"install --force --local")
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.anotherbib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path("files")))
        self.assertFalse(config.git)

    def test_install_defaults_preexisting_pdfs(self):
        self.assertFalse(self._exists(self.filesdir))
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))
        # pre-existing pdfs folder (pre-defined set of names)
        os.makedirs(self._path("pdfs"))
        self.papers(f"install --force --local")
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        # self.assertEqual(config.bibtex, os.path.abspath(self._path("papers.bib")))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.anotherbib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path("pdfs")))
        self.assertFalse(config.git)

    def test_install_raise(self):
        self.papers(
            f"install --force --local --bibtex {self.mybib} --files {self.filesdir}"
        )
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))
        f = lambda: self.papers(
            f"install --local --bibtex {self.mybib} --files {self.filesdir}"
        )
        self.assertRaises(Exception, f)

    def test_install_force(self):
        self.papers(
            f"install --force --local --bibtex {self.mybib} --files {self.filesdir}"
        )
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.papers(f"install --local --force --bibtex {self.mybib}XX")
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib + "XX")))
        # The files folder from previous install was forgotten
        self.assertEqual(config.filesdir, os.path.abspath(self._path("files")))
        self.assertFalse(config.git)

    def test_install_edit(self):
        self.papers(
            f"install --force --local --bibtex {self.mybib} --files {self.filesdir}"
        )
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.papers(f"install --local --edit --bibtex {self.mybib}XX")
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib + "XX")))
        # The files folder from previous install is remembered
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.assertFalse(config.git)

    def test_install_interactive(self):
        # fully interactive install
        sp.check_call(
            f"""{PAPERSCMD} install --local << EOF
{self.mybib}
{self.filesdir}
n
EOF""",
            shell=True,
            cwd=self.temp_dir.name,
        )
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.assertFalse(config.git)

        # Now try simple carriage return (select default)
        sp.check_call(
            f"""{PAPERSCMD} install --local << EOF

e



EOF""",
            shell=True,
            cwd=self.temp_dir.name,
        )
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))

        # edit existing install (--edit)
        sp.check_call(
            f"""{PAPERSCMD} install --local --bibtex {self.mybib}XX << EOF
e
y
n
EOF""",
            shell=True,
            cwd=self.temp_dir.name,
        )
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib + "XX")))
        # The files folder from previous install is remembered
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))
        self.assertFalse(config.git)

        # overwrite existing install (--force)
        sp.check_call(
            f"""{PAPERSCMD} install --local --bibtex {self.mybib}XX << EOF
o
y
n
EOF""",
            shell=True,
            cwd=self.temp_dir.name,
        )
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib + "XX")))
        # The files folder from previous install was forgotten
        self.assertEqual(config.filesdir, os.path.abspath(self._path("files")))
        self.assertFalse(config.git)

        # reset default values from install
        sp.check_call(
            f"""{PAPERSCMD} install --local << EOF
e
reset
reset
n
EOF""",
            shell=True,
            cwd=self.temp_dir.name,
        )
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, None)
        # The files folder from previous install was forgotten
        self.assertEqual(config.filesdir, None)
        self.assertFalse(config.git)

        # install with git tracking
        sp.check_call(
            f"""{PAPERSCMD} install --local << EOF
e


y
y
EOF""",
            shell=True,
            cwd=self.temp_dir.name,
        )
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        # by default another bib is detected, because it starts with a (sorted)
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.anotherbib)))
        # The files folder from previous install was forgotten
        self.assertEqual(config.filesdir, os.path.abspath(self._path("files")))
        self.assertTrue(config.git)
        self.assertTrue(config.gitlfs)


class TestInstallNewBibTex(TestBaseInstall):

    # no bibtex file is present at start
    initial_content = None
    anotherbib_content = None

    def test_install(self):
        self.assertFalse(self._exists(self.mybib))
        self.assertFalse(self._exists(self.anotherbib))
        self.papers(
            f"""install --local --filesdir files << EOF
e
my.bib
EOF"""
        )


class TestInstallEditor(TestBaseInstall):

    # no bibtex file is present at start
    initial_content = None
    anotherbib_content = None

    def test_install(self):
        self.papers(f'install --force --local --editor "subl -w"')
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.editor, "subl -w")


class TestGlobalInstall(TestBaseInstall):

    def test_install(self):
        self.assertFalse(self._exists(self.mybib))
        self.assertFalse(self._exists(self.filesdir))
        self.assertFalse(os.path.exists(CONFIG_FILE))
        self.papers(
            f"install --no-prompt --bibtex {self.mybib} --files {self.filesdir}"
        )
        self.assertTrue(self._exists(self.mybib))
        self.assertTrue(self._exists(self.filesdir))
        self.assertTrue(os.path.exists(CONFIG_FILE))
        config = Config.load(self._path(CONFIG_FILE))
        self.assertEqual(config.bibtex, os.path.abspath(self._path(self.mybib)))
        self.assertEqual(config.filesdir, os.path.abspath(self._path(self.filesdir)))


class TestGitInstall(TestBaseInstall):

    def test_install_gitlfs(self):
        self.papers(f"install --local --no-prompt --git-lfs")
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertTrue(config.git)
        # self.assertTrue(self._exists(".git"))

    def test_install(self):
        self.papers(
            f"install --local --no-prompt --bibtex {self.mybib} --files {self.filesdir} --git"
        )
        self.assertTrue(self._exists(self.mybib))
        # self.assertTrue(self._exists(".git"))
        # count = sp.check_output(f'cd {self.temp_dir.name} && git rev-list --all --count', shell=True).strip().decode()
        # self.assertEqual(count, '0')
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        count = self.papers("git rev-list --all --count", sp_cmd="check_output")
        count_ = (
            sp.check_output("git rev-list --all --count", shell=True, cwd=config.gitdir)
            .decode()
            .strip()
        )
        self.assertEqual(count, count_)
        count2 = self.papers("git rev-list --all --count", sp_cmd="check_output")
        count2_ = (
            sp.check_output("git rev-list --all --count", shell=True, cwd=config.gitdir)
            .decode()
            .strip()
        )
        self.assertEqual(count2, count2_)
        self.papers(f"add {self.anotherbib}")
        # self.papers(f'add --doi 10.5194/bg-8-515-2011')
        count2 = self.papers("git rev-list --all --count", sp_cmd="check_output")

        print(count, count2)
        self.assertEqual(int(count2), int(count) + 1)

    def test_install_interactive(self):
        self.papers(
            f"""install --local --filesdir files --bibtex bibbib.bib << EOF
y
y
EOF"""
        )
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertTrue(config.git)
        self.assertTrue(config.gitlfs)

    def test_install_interactive2(self):
        self.papers(
            f"""install --local --filesdir files --bibtex bibbib.bib << EOF
y
n
EOF"""
        )
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertTrue(config.git)
        self.assertFalse(config.gitlfs)

    def test_install_interactive3(self):
        self.papers(
            f"""install --local --filesdir files --bibtex bibbib.bib << EOF
n
EOF"""
        )
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertFalse(config.git)
        self.assertFalse(config.gitlfs)

    def test_install_interactive4(self):
        self.papers(
            f"""install --local --filesdir files --bibtex bibbib.bib << EOF

EOF"""
        )
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertFalse(config.git)
        self.assertFalse(config.gitlfs)

    def test_install_interactive5(self):
        self.papers(
            f"""install --local --filesdir files --bibtex bibbib.bib << EOF
y

EOF"""
        )
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertTrue(config.git)
        self.assertFalse(config.gitlfs)

class TestDefaultLocal(LocalInstallTest):
    def test_install(self):
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self.config.local)
        self.papers(f"install --edit")
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        config = Config.load(self._path(CONFIG_FILE_LOCAL))
        self.assertTrue(config.local)


class TestUninstall(LocalInstallTest):
    def test_uninstall_localinstall(self):
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.papers(f"uninstall")
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))

class TestDefaultLocal2(GlobalInstallTest):
    def test_install(self):
        self.assertTrue(self._exists(CONFIG_FILE))
        self.assertFalse(self.config.local)
        self.papers(f"install --edit")
        self.assertTrue(self._exists(CONFIG_FILE))
        config = Config.load(CONFIG_FILE)
        self.assertFalse(config.local)


class TestUninstall2(GlobalInstallTest):
    def test_uninstall_globalinstall(self):
        self.assertTrue(self._exists(CONFIG_FILE))
        self.papers(f"install --force --local")
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(CONFIG_FILE))
        self.papers(f"uninstall")
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(CONFIG_FILE))

    def test_uninstall_globalinstall_two(self):
        self.papers(f"install --force --local")
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(CONFIG_FILE))
        self.papers(f"uninstall --recursive")
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))
        self.assertFalse(self._exists(CONFIG_FILE))


# from tests/test_duplicates.py
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
        """test Biblio's eq method for duplicates"""
        db = bibtexparser.loads(a + "\n" + b)
        e1, e2 = db.entries
        refs = Biblio(similarity=self.similarity)
        return refs.eq(e1, e2)


class TestDuplicatesExact(SimilarityBase):

    similarity = "EXACT"

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

    similarity = "GOOD"

    def test_anotherkey(self):
        self.assertTrue(self.isduplicate(self.reference, self.anotherkey))

    def test_missingfield(self):
        self.assertTrue(self.isduplicate(self.reference, self.missingfield))

    def test_conflictyear(self):
        self.assertTrue(self.isduplicate(self.reference, self.conflictyear))


class TestDuplicatesFair(TestDuplicatesGood):

    similarity = "FAIR"

    def test_missingtitauthor(self):
        self.assertTrue(self.isduplicate(self.reference, self.missingtitauthor))

    def test_conflictauthor(self):
        self.assertTrue(self.isduplicate(self.reference, self.conflictauthor))


class TestDuplicatesPartial(TestDuplicatesFair):

    similarity = "PARTIAL"

    def test_missingdoi(self):
        self.assertTrue(self.isduplicate(self.reference, self.missingdoi))

    def test_conflictdoi(self):
        self.assertTrue(self.isduplicate(self.reference, self.conflictdoi))


class TestDuplicates(TestDuplicatesPartial):

    @staticmethod
    def isduplicate(a, b):
        """test Biblio's eq method for duplicates"""
        db = bibtexparser.loads(a + "\n" + b)
        e1, e2 = db.entries
        refs = Biblio()
        return refs.eq(e1, e2)


class TestDuplicatesAdd(TestDuplicates):

    def setUp(self):
        self.mybib = tempfile.mktemp(prefix="papers.bib")
        self.otherbib = tempfile.mktemp(prefix="papers.otherbib")

    def tearDown(self):
        os.remove(self.mybib)
        os.remove(self.otherbib)

    def isduplicate(self, a, b):
        """test Biblio's eq method in 'add' mode"""
        open(self.mybib, "w").write(a)
        open(self.otherbib, "w").write(b)
        res = paperscmd(
            f"add {self.otherbib} --bibtex {self.mybib} --update-key --mode r --debug",
            sp_cmd="call",
        )
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
        self.mybib = tempfile.mktemp(prefix="papers.bib")
        self.otherbib = tempfile.mktemp(prefix="papers.otherbib")
        open(self.mybib, "w").write(self.original)

    def tearDown(self):
        os.remove(self.mybib)
        os.remove(self.otherbib)

    def command(self, mode):
        return f"echo {mode} | {PAPERSCMD} add {self.otherbib} --bibtex {self.mybib} --debug"

    def test_overwrite(self):

        expected = self.conflict

        open(self.otherbib, "w").write(self.conflict)
        sp.check_call(self.command("o"), shell=True)
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), expected
        )  # entries did not change

    def test_skip(self):

        expected = self.original

        open(self.otherbib, "w").write(self.conflict)
        sp.check_call(self.command("s"), shell=True)
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), expected
        )  # entries did not change

    def test_append(self):
        open(self.otherbib, "w").write(self.conflict)
        sp.check_call(self.command("a"), shell=True)
        # paperscmd(f'add {} --bibtex {} --debug'.format(self.otherbib, self.mybib))
        expected = self.conflict + "\n\n" + self.original
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), expected
        )  # entries did not change

    def test_raises(self):
        # update key to new entry, but does not merge...
        open(self.otherbib, "w").write(self.conflict)
        func = lambda: sp.check_call(self.command("r"), shell=True)
        self.assertRaises(Exception, func)

    def test_original_updated_from_conflict(self):

        expected = """@article{Perrette_2011,
 author = {New Author Field},
 doi = {10.5194/bg-8-515-2011},
 journal = {Biogeosciences},
 year = {RareYear}
}"""

        open(self.otherbib, "w").write(self.conflict)
        sp.check_call(self.command("u"), shell=True)
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), expected
        )  # entries did not change

    def test_conflict_updated_from_original(self):

        expected = """@article{AnotherKey,
 author = {New Author Field},
 doi = {10.5194/bg-8-515-2011},
 journal = {ConflictJournal},
 year = {RareYear}
}"""

        open(self.otherbib, "w").write(self.conflict)
        sp.check_call(self.command("U"), shell=True)
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), expected
        )  # entries did not change

    def test_conflict_updated_from_original_but_originalkey(self):

        expected = """@article{10.5194/bg-8-515-2011,
 author = {New Author Field},
 doi = {10.5194/bg-8-515-2011},
 journal = {ConflictJournal},
 year = {RareYear}
}"""
        open(self.otherbib, "w").write(self.conflict)
        sp.check_call(self.command("U") + " --update-key", shell=True)
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), expected
        )  # entries did not change


class TestAddResolveDuplicateCommand(TestAddResolveDuplicate):

    def command(self, mode):
        return f"{PAPERSCMD} add {self.otherbib} --bibtex {self.mybib} --mode {mode} --debug"


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
        self.mybib = tempfile.mktemp(prefix="papers.bib")
        open(self.mybib, "w").write(self.original + "\n\n" + self.conflict)

    def tearDown(self):
        os.remove(self.mybib)

    def command(self, mode):
        return f"echo {mode} | {PAPERSCMD} check --duplicates --bibtex {self.mybib} --debug"

    def test_pick_conflict_1(self):

        expected = self.conflict

        sp.check_call(self.command("1"), shell=True)
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), expected
        )  # entries did not change

    def test_pick_reference_2(self):

        expected = self.original

        sp.check_call(self.command("2"), shell=True)
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), expected
        )  # entries did not change

    def test_skip_check(self):

        expected = self.conflict + "\n\n" + self.original

        sp.check_call(self.command("s"), shell=True)
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), expected
        )  # entries did not change

    def test_not_a_duplicate(self):

        expected = self.conflict + "\n\n" + self.original

        sp.check_call(self.command("n"), shell=True)
        self.assertMultiLineEqual(
            open(self.mybib).read().strip(), expected
        )  # entries did not change

    def test_raises(self):
        # update key to new entry, but does not merge...
        func = lambda: sp.check_call(self.command("r"), shell=True)
        self.assertRaises(Exception, func)

    def test_merge(self):
        # update key to new entry, but does not merge...
        expected = """@article{AnotherKey,
         author = {New Author Field},
         doi = {10.5194/bg-8-515-2011},
         journal = {ConflictJournal},
         year = {RareYear}
        }"""
        func = lambda: sp.check_call(self.command("m\n3"), shell=True)
        del expected # TODO flake8 flags the above definition for expected as unised
        self.assertRaises(Exception, func)


# from tests/test_undo.py

from tests.common import (
    BaseTest,
    LocalGitInstallTest,
    LocalGitLFSInstallTest,
    GlobalGitInstallTest,
    GlobalGitLFSInstallTest,
)


class TimeTravelBase:

    def get_commit(self):
        return (
            sp.check_output(f"git rev-parse HEAD", shell=True, cwd=self.config.gitdir)
            .strip()
            .decode()
        )

    def test_undo_timetravel_base(self):
        # Make sure git undo / redo travels as expected

        print(self.config.status(verbose=True))
        self.assertTrue(self.config.git)

        commits = []
        commits.append(self.get_commit())

        self.papers(f"add {self.anotherbib}")
        self.assertTrue(self.config.git)
        commits.append(self.get_commit())
        print("bib add paper:", self._path(self.mybib))
        print(open(self._path(self.mybib)).read())
        print("backup after add paper:", self.config.backupfile_clean)
        print(open(self.config.backupfile_clean).read())

        self.papers(f"list --add-tag change")
        self.assertTrue(self.config.git)
        commits.append(self.get_commit())
        print("bib add-tag:", self._path(self.mybib))
        print(open(self._path(self.mybib)).read())
        print("backup after add-tag:", self.config.backupfile_clean)
        print(open(self.config.backupfile_clean).read())

        # make sure we have 3 distinct commits
        self.config.gitcmd("log")
        print(commits)
        print(self.config.gitdir)
        sp.check_call(f"ls {self.config.gitdir}", shell=True)
        self.assertEqual(len(set(commits)), 3)

        self.papers(f"undo")
        current = self.get_commit()
        self.assertEqual(current, commits[-2])

        self.papers(f"undo")
        current = self.get_commit()
        self.assertEqual(current, commits[-3])

        self.papers(f"redo")
        current = self.get_commit()
        self.assertEqual(current, commits[-2])

        self.papers(f"redo")
        current = self.get_commit()
        self.assertEqual(current, commits[-1])

        # beyond last commit, nothing changes
        f = lambda: self.papers(f"redo")
        self.assertRaises(Exception, f)
        current = self.get_commit()
        self.assertEqual(current, commits[-1])

        # two steps back
        self.papers(f"undo -n 2")
        current = self.get_commit()
        self.assertEqual(current, commits[-3])

        # two steps forth
        self.papers(f"redo -n 2")
        current = self.get_commit()
        self.assertEqual(current, commits[-1])

        # Now go to specific commits
        self.papers(f"restore-backup --ref {commits[0]}")
        current = self.get_commit()
        self.assertEqual(current, commits[0])

        self.papers(f"restore-backup --ref {commits[-1]}")
        current = self.get_commit()
        self.assertEqual(current, commits[-1])


class TestTimeTravelGitLocal(LocalGitInstallTest, TimeTravelBase):
    pass


class TestTimeTravelGitGlobal(GlobalGitInstallTest, TimeTravelBase):
    pass


class TestRestoreGitLocal(LocalGitInstallTest):

    def get_commit(self):
        return (
            sp.check_output(f"git rev-parse HEAD", shell=True, cwd=self.config.gitdir)
            .strip()
            .decode()
        )

    def test_undo_restore_local(self):
        # Make sure git undo / redo travels as expected

        self.papers(f"add {self.anotherbib}")
        biblio = Biblio.load(self._path(self.mybib), "")

        # Remove bibtex
        sp.check_call(f"rm -f {self._path(self.mybib)}", shell=True)

        self.papers(f"restore-backup")
        biblio2 = Biblio.load(self._path(self.mybib), "")

        self.assertMultiLineEqual(biblio.format(), biblio2.format())


class TestUndoGitLocal(LocalGitLFSInstallTest):

    def test_undo_undo_local(self):

        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 0)

        self.papers(f"add {self.anotherbib}")
        biblio = biblio1 = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 1)

        open(self._path("yetanother"), "w").write(bibtex2)
        self.papers(f"add yetanother")
        biblio = biblio2 = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 2)

        self.papers(f"undo")
        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 1)
        self.assertMultiLineEqual(biblio.format(), biblio1.format())

        self.papers(f"undo")
        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 0)

        self.papers(f"redo")
        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 1)
        self.assertMultiLineEqual(biblio.format(), biblio1.format())

        self.papers(f"redo")
        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 2)
        self.assertMultiLineEqual(biblio.format(), biblio2.format())

    def _format_file(self, name):
        return name

    def test_undo_files_rename(self):
        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 0)

        pdf, doi, key, newkey, year, bibtex, file_rename = prepare_paper()

        self.papers(f"add {pdf} --doi {doi}")

        biblio = biblio_original = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 1)
        self.assertEqual(biblio.get_files(biblio.entries[0]), [pdf])
        self.assertTrue(os.path.exists(pdf))

        backup = backup0 = Biblio.load(
            self.config.backupfile_clean, self._path(".papers/files")
        )
        self.assertEqual(len(backup.entries), 1)
        backup_file_path = str(
            (Path(self._path(self.config.gitdir)) / "files" / file_rename).resolve()
        )
        self.assertEqual(backup.get_files(backup.entries[0]), [backup_file_path])
        self.assertTrue(Path(backup_file_path).exists())

        self.papers(f"filecheck --rename")

        biblio = biblio_future = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 1)
        file_path = os.path.join(self.config.filesdir, file_rename)
        self.assertEqual(biblio.get_files(biblio.entries[0]), [file_path])
        self.assertFalse(os.path.exists(pdf))
        self.assertTrue(os.path.exists(file_path))

        backup = Biblio.load(self.config.backupfile_clean, self._path(".papers/files"))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(backup_file_path)

        self.papers(f"undo")

        backup = Biblio.load(self.config.backupfile_clean, self._path(".papers/files"))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(backup_file_path)

        # The biblio has its file pointer to the backup directory:
        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertFalse(biblio.format() == biblio_original.format())
        self.assertEqual(len(biblio.entries), 1)

        self.assertNotEqual(
            biblio.get_files(biblio.entries[0]),
            biblio_original.get_files(biblio_original.entries[0]),
        )
        self.assertEqual(
            biblio.get_files(biblio.entries[0]), backup.get_files(backup.entries[0])
        )

        # ...that's because the original file does not exist
        self.assertTrue(os.path.exists(biblio.get_files(biblio.entries[0])[0]))
        self.assertFalse(
            os.path.exists(biblio_original.get_files(biblio_original.entries[0])[0])
        )

        self.papers(f"redo")

        backup = Biblio.load(self.config.backupfile_clean, self._path(".papers/files"))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(backup_file_path)

        biblio = Biblio.load(self._path(self.mybib), "")
        # we're back on track
        self.assertMultiLineEqual(biblio.format(), biblio_future.format())

        # ...that's because the future file does exist
        self.assertTrue(
            os.path.exists(biblio_future.get_files(biblio_future.entries[0])[0])
        )
        self.assertTrue(os.path.exists(biblio.get_files(biblio.entries[0])[0]))

    def test_undo_files_rename_restore(self):
        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 0)

        pdf, doi, key, newkey, year, bibtex, file_rename = prepare_paper()

        self.papers(f"add {pdf} --doi {doi}")

        biblio = biblio_original = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 1)
        self.assertEqual(biblio.get_files(biblio.entries[0]), [pdf])
        self.assertTrue(os.path.exists(pdf))

        backup = backup0 = Biblio.load(
            self.config.backupfile_clean, self._path(".papers/files")
        )
        self.assertEqual(len(backup.entries), 1)
        backup_file_path = str(
            (Path(self._path(self.config.gitdir)) / "files" / file_rename).resolve()
        )
        self.assertEqual(backup.get_files(backup.entries[0]), [backup_file_path])
        self.assertTrue(Path(backup_file_path).exists())

        self.papers(f"filecheck --rename")

        biblio = biblio_future = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 1)
        file_path = os.path.join(self.config.filesdir, file_rename)
        self.assertEqual(biblio.get_files(biblio.entries[0]), [file_path])
        self.assertFalse(os.path.exists(pdf))
        self.assertTrue(os.path.exists(file_path))

        backup = Biblio.load(self.config.backupfile_clean, self._path(".papers/files"))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(backup_file_path)

        self.papers(f"undo --restore")

        backup = Biblio.load(self.config.backupfile_clean, self._path(".papers/files"))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(backup_file_path)

        # The biblio has its file pointer to the backup directory:
        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertMultiLineEqual(biblio.format(), biblio_original.format())
        self.assertEqual(len(biblio.entries), 1)

        # ...that's because the original file does exist
        self.assertTrue(
            os.path.exists(biblio_original.get_files(biblio_original.entries[0])[0])
        )

        self.papers(f"redo")

        backup = Biblio.load(self.config.backupfile_clean, self._path(".papers/files"))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(backup_file_path)

        biblio = Biblio.load(self._path(self.mybib), "")
        # we're back on track
        self.assertMultiLineEqual(biblio.format(), biblio_future.format())

        # ...that's because the future file does exist
        self.assertTrue(
            os.path.exists(biblio_future.get_files(biblio_future.entries[0])[0])
        )
        self.assertTrue(os.path.exists(biblio.get_files(biblio.entries[0])[0]))

    def test_undo_files_rename_copy(self):
        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 0)

        pdf, doi, key, newkey, year, bibtex, file_rename = prepare_paper()

        self.papers(f"add {pdf} --doi {doi}")

        biblio = biblio_original = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 1)
        self.assertEqual(biblio.get_files(biblio.entries[0]), [pdf])
        self.assertTrue(os.path.exists(pdf))

        backup = backup0 = Biblio.load(
            self.config.backupfile_clean, self._path(".papers/files")
        )
        self.assertEqual(len(backup.entries), 1)
        backup_file_path = str(
            (Path(self._path(self.config.gitdir)) / "files" / file_rename).resolve()
        )
        self.assertEqual(backup.get_files(backup.entries[0]), [backup_file_path])
        self.assertTrue(Path(backup_file_path).exists())

        self.papers(f"filecheck --rename --copy")

        biblio = biblio_future = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 1)
        file_path = os.path.join(self.config.filesdir, file_rename)
        self.assertEqual(biblio.get_files(biblio.entries[0]), [file_path])
        self.assertTrue(os.path.exists(pdf))
        self.assertTrue(os.path.exists(file_path))

        backup = Biblio.load(self.config.backupfile_clean, self._path(".papers/files"))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(Path(backup_file_path).exists())

        self.papers(f"undo")

        backup = Biblio.load(self.config.backupfile_clean, self._path(".papers/files"))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(Path(backup_file_path).exists())

        # The biblio has its file pointer as it should, cause the original file can be found
        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertMultiLineEqual(biblio.format(), biblio_original.format())
        # print(biblio.format())
        # print(biblio_original.format())
        # self.assertTrue(biblio == biblio_original)

        # ...that's because the original file does not exist
        self.assertTrue(
            os.path.exists(biblio_original.get_files(biblio_original.entries[0])[0])
        )
        self.assertTrue(os.path.exists(biblio.get_files(biblio.entries[0])[0]))

        self.papers(f"redo")

        backup = Biblio.load(self.config.backupfile_clean, self._path(".papers/files"))
        self.assertMultiLineEqual(backup.format(), backup0.format())
        self.assertTrue(Path(backup_file_path).exists())

        biblio = Biblio.load(self._path(self.mybib), "")
        # here again, we're back on track
        self.assertMultiLineEqual(biblio.format(), biblio_future.format())

        # ...that's because the future file does exist as well
        self.assertTrue(
            os.path.exists(biblio_future.get_files(biblio_future.entries[0])[0])
        )
        self.assertTrue(os.path.exists(biblio.get_files(biblio.entries[0])[0]))


class TestUndoGitOnlyLocal(LocalGitInstallTest):
    def _install(self):
        self.papers(
            f"install --local --no-prompt --bibtex {self.mybib} --files {self.filesdir} --git"
        )
        self.config = Config.load(self._path(CONFIG_FILE_LOCAL))


class TestUndoGitGlobal(GlobalGitLFSInstallTest):

    def _install(self):
        self.papers(
            f"install --no-prompt --bibtex {self.mybib} --files {self.filesdir} --git --git-lfs"
        )
        self.config = Config.load(CONFIG_FILE)

    def _format_file(self, name):
        return os.path.abs(name)


class TestUndoNoInstall(BaseTest):

    def test_undo_noinstall(self):

        open(self._path(self.mybib), "w").write("")

        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 0)
        self.papers(
            f"add {self.anotherbib}  --bibtex {self.mybib} --files {self.filesdir}"
        )
        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 1)

        open(self._path("yetanother"), "w").write(bibtex2)
        self.papers(f"add yetanother --bibtex {self.mybib} --files {self.filesdir}")
        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 2)

        self.papers(f"undo --bibtex {self.mybib} --files {self.filesdir}")
        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 1)

        self.papers(f"undo --bibtex {self.mybib} --files {self.filesdir}")
        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 2)

        self.papers(f"redo --bibtex {self.mybib} --files {self.filesdir}")
        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 1)

        self.papers(f"redo --bibtex {self.mybib} --files {self.filesdir}")
        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 2)

        self.papers(f"redo --bibtex {self.mybib} --files {self.filesdir}")
        biblio = Biblio.load(self._path(self.mybib), "")
        self.assertEqual(len(biblio.entries), 1)


class TestUninstallUndo(LocalGitLFSInstallTest):
    def test_uninstall_localgit(self):
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.papers(f"uninstall")
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))


class TestUninstallUndo2(GlobalGitLFSInstallTest):
    def test_uninstall_global_git(self):
        self.assertTrue(self._exists(CONFIG_FILE))
        self.papers(f"install --force --local")
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(CONFIG_FILE))
        self.papers(f"uninstall")
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(CONFIG_FILE))

    def test_uninstall_global_git_two(self):
        self.papers(f"install --force --local")
        self.assertTrue(self._exists(CONFIG_FILE_LOCAL))
        self.assertTrue(self._exists(CONFIG_FILE))
        self.papers(f"uninstall --recursive")
        self.assertFalse(self._exists(CONFIG_FILE_LOCAL))
        self.assertFalse(self._exists(CONFIG_FILE))
