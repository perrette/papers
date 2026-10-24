"""papers fetch and extract, with the network functions mocked"""
import io
import os
from contextlib import redirect_stdout
from unittest.mock import patch

from papers.utils import PapersExit
from tests.common import FileTest


class TestFetch(FileTest):

    def test_dois(self):
        with patch('papers.cli.fetch_cmds.fetch_bibtex_by_doi', side_effect=lambda doi: f'@misc{{{doi}}}') as fetch:
            out = self.out('fetch 10.1000/a doi:10.1000/b')
        self.assertEqual(out.split(), ['@misc{10.1000/a}', '@misc{10.1000/b}'])
        self.assertEqual(fetch.call_count, 2)

    def test_doi_and_scholar(self):
        with self.assertRaises(SystemExit):
            self.lib('fetch 10.1000/a --scholar')

    def test_fulltext(self):
        with patch('papers.cli.fetch_cmds.fetch_bibtex_by_fulltext_crossref', return_value='@misc{x}') as search:
            self.assertEqual(self.out('fetch Climate sensitivity revisited').strip(), '@misc{x}')
        search.assert_called_once_with('Climate sensitivity revisited')

    def test_fulltext_scholar(self):
        with patch('papers.cli.fetch_cmds.fetch_bibtex_by_fulltext_scholar', return_value='@misc{x}') as search:
            self.out('fetch Climate sensitivity --scholar')
        search.assert_called_once_with('Climate sensitivity')


class TestExtract(FileTest):

    def setUp(self):
        super().setUp()
        self.a = self.write('src', 'a.pdf')
        self.b = self.write('src', 'sub', 'b.PDF')

    def test_directory_needs_R(self):
        with self.assertRaises(SystemExit):
            self.lib(f'extract {self.path("src")}')

    def test_no_pdf(self):
        os.makedirs(self.path('empty'))
        with self.assertLogs('papers', level='WARNING'):
            self.assertEqual(self.out(f'extract -R {self.path("empty")}'), '')

    def test_several_files_and_errors(self):
        def metadata(file, **kw):
            if file == self.b:
                raise ValueError('no metadata')
            return '@misc{a}'
        out = io.StringIO()
        with patch('papers.cli.fetch_cmds.extract_pdf_metadata', side_effect=metadata) as extract, \
                self.assertLogs('papers', level='ERROR') as logs, redirect_stdout(out), \
                self.assertRaisesRegex(PapersExit, '^1 of 2 files failed$'):
            self.lib(f'extract -R {self.path("src")} --fulltext')
        self.assertEqual(out.getvalue().splitlines(), [f'% {self.a}', '@misc{a}', f'% {self.b}'])
        self.assertIn('no metadata', logs.output[0])
        self.assertFalse(extract.call_args.kwargs['search_doi'])

    def test_one_file_error_is_raised(self):
        with patch('papers.cli.fetch_cmds.extract_pdf_metadata', side_effect=ValueError('no metadata')):
            with self.assertRaisesRegex(PapersExit, f'^{self.a}: no metadata$'):
                self.lib(f'extract {self.a}')
