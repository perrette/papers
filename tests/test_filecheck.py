"""Tests for papers filecheck.
Documented in README: filecheck --rename, --delete-missing (--delete-broken),
--hash-check, --fix-mendeley, --clean-filesdir, --force
"""
import os
import shutil
import subprocess as sp
import tempfile
import unittest
from pathlib import Path

import bibtexparser

from papers.bib import Biblio
from papers.entries import get_entry_val
from tests.common import PAPERSCMD, paperscmd, prepare_paper, prepare_paper2, BibTest


class TestFileCheck(BibTest):

    def setUp(self):
        self.pdf, self.doi, self.key, self.newkey, self.year, self.bibtex, self.file_rename = prepare_paper()
        self.assertTrue(os.path.exists(self.pdf))
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workdir = self.temp_dir.name
        self.mybib = os.path.join(self.workdir, 'papers.bib')
        self.filesdir = os.path.join(self.workdir, 'files')
        open(self.mybib, 'w').write(self.bibtex)
        self.assertTrue(os.path.exists(self.mybib))

    def papers(self, cmd):
        return paperscmd(cmd, cwd=self.workdir)

    def test_filecheck_rename(self):
        paperscmd(f"""add --bibtex {self.mybib} --filesdir {self.filesdir} {self.pdf} --doi {self.doi} << EOF
u
EOF""", cwd=self.workdir)
        file_rename = os.path.join(self.filesdir, self.file_rename)
        self.assertFalse(os.path.exists(file_rename))
        self.assertTrue(os.path.exists(self.pdf))
        paperscmd(f'filecheck --bibtex {self.mybib} --filesdir {self.filesdir} --rename', cwd=self.workdir)
        self.assertTrue(os.path.exists(file_rename))
        self.assertFalse(os.path.exists(self.pdf))
        biblio = Biblio.load(self.mybib, '')
        e = next(ent for ent in biblio.entries if get_entry_val(ent, 'ID', '').lower() == self.key.lower())
        files = biblio.get_files(e)
        self.assertTrue(len(files) == 1)
        self.assertEqual(files[0], os.path.abspath(file_rename))

    def test_filecheck_delete_broken(self):
        """papers filecheck --delete-broken --force removes broken file links from entries"""
        os.makedirs(self.filesdir, exist_ok=True)
        self.papers(f'install --local --no-prompt --bibtex {self.mybib} --filesdir {self.filesdir}')
        # Add entry with valid file first
        self.papers(f'add {self.pdf} --doi {self.doi}')
        # Manually add a broken file link to the entry
        biblio = Biblio.load(self.mybib, self.filesdir)
        e = biblio.entries[0]
        real_file = biblio.get_files(e)[0]
        broken_path = os.path.join(os.path.dirname(real_file), 'nonexistent_file.pdf')
        biblio.set_files(e, [real_file, broken_path])
        biblio.save(self.mybib)
        self.assertEqual(len(biblio.get_files(e)), 2)
        self.papers('filecheck --delete-broken --force')
        biblio = Biblio.load(self.mybib, self.filesdir)
        e = biblio.entries[0]
        self.assertEqual(len(biblio.get_files(e)), 1)
        self.papers('uninstall')

    def test_filecheck_hash_check(self):
        """papers filecheck --hash-check removes duplicate files (same content) from entry"""
        os.makedirs(self.filesdir, exist_ok=True)
        pdf_copy = os.path.join(self.filesdir, 'duplicate.pdf')
        shutil.copy(self.pdf, pdf_copy)
        self.papers(f'install --local --no-prompt --bibtex {self.mybib} --filesdir {self.filesdir}')
        self.papers(f'add {self.pdf} --doi {self.doi}')
        biblio = Biblio.load(self.mybib, self.filesdir)
        e = biblio.entries[0]
        files = biblio.get_files(e)
        biblio.set_files(e, files + [pdf_copy])  # add same-content file again
        biblio.save(self.mybib)
        self.assertEqual(len(biblio.get_files(e)), 2)
        self.papers('filecheck --hash-check --force')
        biblio = Biblio.load(self.mybib, self.filesdir)
        e = biblio.entries[0]
        self.assertEqual(len(biblio.get_files(e)), 1)
        self.papers('uninstall')

    def test_filecheck_clean_filesdir(self):
        """papers filecheck --clean-filesdir --force removes unlinked files from filesdir"""
        os.makedirs(self.filesdir, exist_ok=True)
        self.papers(f'install --local --no-prompt --bibtex {self.mybib} --filesdir {self.filesdir}')
        self.papers(f'add {self.pdf} --doi {self.doi}')
        orphan = os.path.join(self.filesdir, 'orphan_unlinked.pdf')
        shutil.copy(self.pdf, orphan)
        self.assertTrue(os.path.exists(orphan))
        self.papers('filecheck --clean-filesdir --force')
        self.assertFalse(os.path.exists(orphan))
        self.papers('uninstall')

    def tearDown(self):
        self.temp_dir.cleanup()