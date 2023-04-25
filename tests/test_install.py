import os
import shutil
import tempfile
import unittest
# from pathlib import Path

from tests.common import paperscmd

class TestInstall(unittest.TestCase):

    def setUp(self):
        self.mybib = tempfile.mktemp(prefix='papers.bib')
        self.filesdir = tempfile.mktemp(prefix='papers.files')

    def test_local_install(self):
        paperscmd(f'install --local --bibtex {self.mybib} --files {self.filesdir}')
        self.assertTrue(os.path.exists(self.mybib))
        self.assertTrue(os.path.exists(self.filesdir))

    def tearDown(self):
        if os.path.exists(self.filesdir):
            shutil.rmtree(self.filesdir)
        if os.path.exists(self.mybib):
            os.remove(self.mybib)
        if os.path.exists('.papersconfig.json'):
            os.remove('.papersconfig.json')