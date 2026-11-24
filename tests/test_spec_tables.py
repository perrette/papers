"""The data tables of the specification (design/data/) are those the code uses."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'scripts'))

import spec_tables  # noqa: E402


class TestSpecTables(unittest.TestCase):

    def check(self, name):
        with open(os.path.join(spec_tables.DATA, name), encoding='utf-8') as f:
            self.assertEqual(f.read(), spec_tables.TABLES[name](),
                             f'design/data/{name} differs from the code: run python scripts/spec_tables.py')

    def test_latex_characters(self):
        "bibtex.md 4.1, 4.2: design/data/latex-characters.tsv"
        self.check('latex-characters.tsv')

    def test_ascii_transliteration(self):
        "bibtex.md 9.1: design/data/ascii-transliteration.tsv"
        self.check('ascii-transliteration.tsv')
