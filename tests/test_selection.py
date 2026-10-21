"""Selecting entries by key or DOI, and `-` for the standard input"""
import io
import unittest
from unittest.mock import patch

from papers.bib import Biblio
from papers.entries import parse_string
from papers.utils import PapersExit
from papers.__main__ import read_selection, select_entries
from tests.common import LocalInstallTest

bibtex = """@article{Alpha2000,
 author = {A. Alpha},
 doi = {10.1000/alpha},
 title = {Alpha},
 year = {2000}
}

@article{Beta2001,
 author = {B. Beta},
 doi = {10.1000/BETA},
 title = {Beta},
 year = {2001}
}

@article{Gamma2002,
 author = {G. Gamma},
 title = {Gamma},
 year = {2002}
}
"""


def keys(entries):
    return [e.key for e in entries]


class SelectEntriesTest(unittest.TestCase):

    def setUp(self):
        self.biblio = Biblio(parse_string(bibtex))

    def test_keys(self):
        self.assertEqual(keys(select_entries(self.biblio, ['Gamma2002', 'alpha2000'])), ['Gamma2002', 'Alpha2000'])

    def test_dois(self):
        self.assertEqual(keys(select_entries(self.biblio, ['10.1000/beta', '10.1000/alpha'])), ['Beta2001', 'Alpha2000'])

    def test_no_repetition(self):
        self.assertEqual(keys(select_entries(self.biblio, ['Alpha2000', '10.1000/alpha'])), ['Alpha2000'])

    def test_stdin(self):
        stdin = io.StringIO('Beta2001\n\n  \n10.1000/alpha\n')
        self.assertEqual(keys(select_entries(self.biblio, ['-', 'Gamma2002'], stdin=stdin)),
                         ['Beta2001', 'Alpha2000', 'Gamma2002'])

    def test_empty_stdin_selects_nothing(self):
        self.assertEqual(select_entries(self.biblio, ['-'], stdin=io.StringIO('')), [])

    def test_unknown(self):
        with self.assertRaisesRegex(PapersExit, 'Nope.*10.1000/nope'):
            select_entries(self.biblio, ['Alpha2000', 'Nope', '10.1000/nope'])

    def test_read_selection(self):
        self.assertEqual(read_selection(['a', '-', 'b'], stdin=io.StringIO('x\ny\n')), ['a', 'x', 'y', 'b'])


class SelectionCommandsTest(LocalInstallTest):
    initial_content = bibtex
    anotherbib_content = None

    def test_list_key_only_short(self):
        out = self.papers('list -K', sp_cmd='check_output')
        self.assertEqual(out.split(), ['Alpha2000', 'Beta2001', 'Gamma2002'])

    def test_check_takes_keys_and_stdin(self):
        with patch('papers.bib.Biblio.fix_entry') as fix:
            with patch('sys.stdin', io.StringIO('10.1000/beta\n')):
                self.papers('check - Gamma2002 --force')
            self.assertEqual([c.args[0].key for c in fix.call_args_list], ['Beta2001', 'Gamma2002'])

    def test_check_unknown_key(self):
        with patch('papers.bib.Biblio.fix_entry') as fix:
            with self.assertRaises(PapersExit):
                self.papers('check Alpha2000 Nope --force')
            fix.assert_not_called()

    def test_open_stdin(self):
        with patch('papers.__main__.view_entry_files') as view, \
                patch('papers.bib.Biblio.get_files', return_value=['x.pdf']):
            with patch('sys.stdin', io.StringIO('Alpha2000\n10.1000/beta\n')):
                self.papers('open -')
            self.assertEqual([c.args[1].key for c in view.call_args_list], ['Alpha2000', 'Beta2001'])
