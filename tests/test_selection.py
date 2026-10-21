"""Selecting entries by key or DOI, and `-` for the standard input"""
import io
import unittest
from unittest.mock import patch

from papers.bib import Biblio
from papers.entries import parse_string
from papers.utils import PapersExit
from papers.identifiers import read_selection, select_entries
from papers.identifiers import normalize_doi, normalize_arxiv, normalize_isbn, parse_identifier
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
        with self.assertRaisesRegex(PapersExit, '(?s)Nope: no entry found.*10.1000/nope: no entry found'):
            select_entries(self.biblio, ['Alpha2000', 'Nope', '10.1000/nope'])

    def test_read_selection(self):
        self.assertEqual(read_selection(['a', '-', 'b'], stdin=io.StringIO('x\ny\n')), ['a', 'x', 'y', 'b'])


ids_bibtex = """@article{New2021,
 author = {N. New},
 ids = {Old2020, older2019},
 doi = {10.48550/arXiv.2101.01234},
 title = {New},
 year = {2021}
}

@article{Eprint1999,
 archiveprefix = {arXiv},
 author = {E. Eprint},
 eprint = {hep-th/9901001v3},
 title = {Eprint},
 year = {1999}
}

@article{Other2010,
 archiveprefix = {HAL},
 author = {O. Other},
 eprint = {2101.99999},
 title = {Other},
 year = {2010}
}

@incollection{ChapterA,
 author = {C. A},
 isbn = {978-0-306-40615-7},
 title = {Chapter A},
 year = {2000}
}

@incollection{ChapterB,
 author = {C. B},
 isbn = {0-306-40615-2},
 title = {Chapter B},
 year = {2000}
}

@book{Book2000,
 author = {B. Book},
 isbn = {0 8044 2957 X},
 title = {Book},
 year = {2000}
}
"""


class IdentifierTest(unittest.TestCase):

    def test_doi(self):
        for s in ['10.1000/ABC', 'doi:10.1000/abc', 'https://doi.org/10.1000/abc', 'http://dx.doi.org/10.1000/abc']:
            self.assertEqual(parse_identifier(s), ('doi', '10.1000/abc'), s)
        self.assertIsNone(normalize_doi('Smith2000'))

    def test_arxiv(self):
        for s in ['2101.01234', '2101.01234v2', 'arXiv:2101.01234', 'https://arxiv.org/abs/2101.01234v1']:
            self.assertEqual(parse_identifier(s), ('arxiv', '2101.01234'), s)
        self.assertEqual(parse_identifier('hep-th/9901001'), ('arxiv', 'hep-th/9901001'))
        self.assertEqual(parse_identifier('math.GT/0309136v1'), ('arxiv', 'math.gt/0309136'))
        self.assertIsNone(normalize_arxiv('smith/2000'))

    def test_isbn(self):
        self.assertEqual(normalize_isbn('978-0-306-40615-7'), '9780306406157')
        self.assertEqual(normalize_isbn('0-306-40615-2'), '9780306406157')  # same book
        self.assertEqual(normalize_isbn('0 8044 2957 X'), '9780804429573')
        self.assertIsNone(normalize_isbn('978-0-306-40615-8'))  # wrong check digit
        self.assertIsNone(normalize_isbn('0-306-40615-3'))
        self.assertEqual(parse_identifier('080442957X')[0], 'isbn')

    def test_key(self):
        self.assertEqual(parse_identifier('Smith2000'), ('key', 'smith2000'))
        with self.assertRaisesRegex(ValueError, 'cannot start with a digit'):
            parse_identifier('2000smith')


class SelectIdentifiersTest(unittest.TestCase):

    def setUp(self):
        self.biblio = Biblio(parse_string(ids_bibtex))

    def select(self, *args):
        return keys(select_entries(self.biblio, list(args)))

    def test_ids_aliases(self):
        self.assertEqual(self.select('old2020'), ['New2021'])
        self.assertEqual(self.select('Older2019', 'new2021'), ['New2021'])

    def test_arxiv_doi(self):
        self.assertEqual(self.select('arXiv:2101.01234v3'), ['New2021'])
        self.assertEqual(self.select('10.48550/ARXIV.2101.01234'), ['New2021'])

    def test_eprint(self):
        self.assertEqual(self.select('hep-th/9901001'), ['Eprint1999'])
        with self.assertRaisesRegex(PapersExit, 'no entry found'):
            self.select('2101.99999')  # eprint of another archive

    def test_isbn(self):
        self.assertEqual(self.select('080442957x'), ['Book2000'])
        self.assertEqual(self.select('978-0-8044-2957-3'), ['Book2000'])

    def test_ambiguous(self):
        with self.assertRaisesRegex(PapersExit, 'several entries match: ChapterA, ChapterB'):
            self.select('9780306406157')

    def test_ambiguous_from_stdin(self):
        with self.assertRaisesRegex(PapersExit, 'several entries match'):
            select_entries(self.biblio, ['-'], stdin=io.StringIO('Book2000\n0306406152\n'))

    def test_not_a_key(self):
        with self.assertRaisesRegex(PapersExit, 'cannot start with a digit'):
            self.select('2000book')


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
        with patch('papers.cli.entry_cmds.view_entry_files') as view, \
                patch('papers.bib.Biblio.get_files', return_value=['x.pdf']):
            with patch('sys.stdin', io.StringIO('Alpha2000\n10.1000/beta\n')):
                self.papers('open -')
            self.assertEqual([c.args[1].key for c in view.call_args_list], ['Alpha2000', 'Beta2001'])
