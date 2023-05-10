import os
import shutil
import subprocess as sp
import tempfile
import unittest
from pathlib import Path

import bibtexparser

from papers.bib import Biblio
from tests.common import PAPERSCMD, paperscmd, prepare_paper, prepare_paper2, BibTest


class TestFileCheck(BibTest):

    def setUp(self):
        self.pdf, self.doi, self.key, self.newkey, self.year, self.bibtex, self.file_rename = prepare_paper()
        self.assertTrue(os.path.exists(self.pdf))
        self.mybib = tempfile.mktemp(prefix='papers.bib')
        self.filesdir = tempfile.mktemp(prefix='papers.files')
        open(self.mybib, 'w').write(self.bibtex)
        # paperscmd(f'install --local --bibtex {self.mybib} --filesdir {self.filesdir}'
        self.assertTrue(os.path.exists(self.mybib))

    def test_filecheck_rename(self):
        paperscmd(f"""add --bibtex {self.mybib} --filesdir {self.filesdir} {self.pdf} --doi {self.doi} << EOF
u
EOF""")
        file_rename = os.path.join(self.filesdir, self.file_rename)
        self.assertFalse(os.path.exists(file_rename))
        self.assertTrue(os.path.exists(self.pdf))
        paperscmd(f'filecheck --bibtex {self.mybib} --filesdir {self.filesdir} --rename')
        self.assertTrue(os.path.exists(file_rename))
        self.assertFalse(os.path.exists(self.pdf))
        biblio = Biblio.load(self.mybib, '')
        e = biblio.entries[[e['ID'] for e in biblio.entries].index(self.key)]
        files = biblio.get_files(e)
        self.assertTrue(len(files) == 1)
        self.assertEqual(files[0], os.path.abspath(file_rename))


    def tearDown(self):
        if os.path.exists(self.filesdir):
            shutil.rmtree(self.filesdir)
        if os.path.exists(self.mybib):
            os.remove(self.mybib)
        if os.path.exists('.papersconfig.json'):
            os.remove('.papersconfig.json')