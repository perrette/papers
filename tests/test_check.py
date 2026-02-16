"""Tests for papers check --format-name --encoding --fix-doi --fix-key
Documented in README: fix entries (papers check --format-name --encoding unicode --fix-doi --fix-key ...)
"""
import os

from tests.common import LocalInstallTest
from papers.bib import Biblio
from papers.config import CONFIG_FILE_LOCAL


# Entry with author in "First Last" format (will be formatted to "Last, First")
bibtex_format_name = """@article{TestKey2020,
 author = {John Smith and Jane Doe},
 doi = {10.5194/bg-8-515-2011},
 title = {Test Article},
 year = {2020}
}"""

# Entry with DOI that has "DOI:" prefix (fix-doi will normalize)
bibtex_fix_doi = """@article{Perrette2011,
 author = {M. Perrette and A. Yool},
 doi = {DOI:10.5194/bg-8-515-2011},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
 year = {2011}
}"""

# Entry with key starting with digit (fix-key will generate new key)
bibtex_fix_key = """@article{10.5194/bg-8-515-2011,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 doi = {10.5194/bg-8-515-2011},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
 year = {2011}
}"""

# Entry with LaTeX encoding ({\'e} etc) for encoding unicode test
bibtex_latex_encoding = """@article{EncodingTest2020,
 author = {Fran{\\c{c}}ois M{\\'e}nard},
 doi = {10.5194/test-2020},
 title = {Test with {\\'e} and {\\\"u}},
 year = {2020}
}"""


class TestCheckFormatName(LocalInstallTest):

    initial_content = bibtex_format_name

    def test_check_format_name(self):
        """papers check --format-name formats author names (family, given)"""
        self.papers('check --format-name --force')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)
        author = biblio.entries[0]['author']
        self.assertIn('Smith, John', author)
        self.assertIn('Doe, Jane', author)


class TestCheckFixDoi(LocalInstallTest):

    initial_content = bibtex_fix_doi

    def test_check_fix_doi(self):
        """papers check --fix-doi normalizes DOI (e.g. strips DOI: prefix)"""
        self.papers('check --fix-doi --force')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)
        doi = biblio.entries[0]['doi']
        self.assertEqual(doi, '10.5194/bg-8-515-2011')
        self.assertNotIn('DOI:', doi)


class TestCheckFixKey(LocalInstallTest):

    initial_content = bibtex_fix_key

    def test_check_fix_key(self):
        """papers check --fix-key generates key from author/year when key starts with digit"""
        self.papers('check --fix-key --force')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)
        key = biblio.entries[0]['ID']
        self.assertFalse(key[0].isdigit(), f'key should not start with digit: {key}')
        self.assertIn('perrette', key.lower())
        self.assertIn('2011', key)


class TestCheckEncoding(LocalInstallTest):

    initial_content = bibtex_latex_encoding

    def test_check_encoding_unicode(self):
        """papers check --encoding unicode converts LaTeX to unicode"""
        self.papers('check --encoding unicode --force')
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)
        author = biblio.entries[0]['author']
        title = biblio.entries[0]['title']
        # LaTeX {\'e} -> é, {\"u} -> ü, {\c{c}} -> ç
        self.assertIn('é', author or '')
        self.assertIn('é', title or '')
        # Should not contain raw LaTeX
        self.assertNotIn("{\\'e}", author or '')
        self.assertNotIn("{\\'e}", title or '')
