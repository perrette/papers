"""More tests of add, check, open and the file subcommands: their option
errors and less common paths (no network: fetching is mocked)"""
import os
from pathlib import Path
from unittest.mock import patch

import papers.config
from papers.bib import Biblio
from papers.utils import PapersExit
from tests.common import FileTest, entry


def no_fetch(*args, **kwargs):
    raise AssertionError('no network query expected')


class TestAddMore(FileTest):

    def keys(self):
        return sorted(e.key for e in Biblio.load(self.path('lib', 'papers.bib'), '').entries)

    def test_nothing_to_add(self):
        with self.assertRaisesRegex(PapersExit, 'No entry added'):
            self.lib('add')

    def test_directory_needs_R(self):
        os.makedirs(self.path('src'))
        with self.assertRaisesRegex(PapersExit, 'requires -R/--recursive'):
            self.lib(f'add {self.path("src")}')

    def test_several_files_error_and_ignore_errors(self):
        good = self.write('src', 'good.bib', content=entry('good2000'))
        bad = self.write('src', 'bad.pdf')
        with patch('papers.bib.extract_pdf_metadata', side_effect=ValueError('no metadata')), \
                patch('papers.cli.entry_cmds.prefetch_pdf_metadata'):
            with self.assertRaisesRegex(PapersExit, 'use --ignore-errors'):
                self.lib(f'add {bad} {good}')
            with self.assertLogs('papers', level='ERROR'):
                self.lib(f'add {bad} {good} --ignore-errors')
        self.assertEqual(self.keys(), ['good2000'])

    def test_url_attachment_is_downloaded(self):
        import tempfile
        d = tempfile.mkdtemp(prefix='papers_dl_')
        si = os.path.join(d, 'si.pdf')
        Path(si).write_text('si')
        with patch('papers.cli.entry_cmds.download_url', return_value=si) as download:
            self.lib('add --title T --key t2000 --attach https://example.org/si.pdf --link')
        download.assert_called_once()
        files = Biblio.load(self.path('lib', 'papers.bib'), '').get_files(
            Biblio.load(self.path('lib', 'papers.bib'), '').entries[0])
        self.assertTrue(files[0].startswith(self.path('lib', 'files')))  # moved whatever the mode
        os.rmdir(d)

    def test_open_added_entries(self):
        one = self.write('src', 'one.bib', content=entry('one2000', self.write('src', 'one.pdf'))
                         + entry('two2000', self.write('src', 'two.pdf')))
        with patch('papers.cli.entry_cmds.view_entry_files') as view:
            self.lib(f'add {one} -o --link')
        self.assertEqual(view.call_count, 2)


class TestCheckMore(FileTest):

    def test_on_duplicate_without_duplicates(self):
        self.bib(entry('one2000'))
        with self.assertLogs('papers', level='WARNING') as logs:
            self.lib('check --on-duplicate keep -y')
        self.assertIn('only apply with --duplicates', logs.output[0])


class TestOpenMore(FileTest):

    def test_unknown_key_without_library(self):
        os.makedirs(self.path('nolib'))
        with patch('papers.cli.entry_cmds.get_biblio', side_effect=ValueError('no bibtex')):
            with self.assertRaisesRegex(PapersExit, 'no bibliography is configured'):
                self.lib('open nope2000')


class TestFileMore(FileTest):

    def setUp(self):
        super().setUp()
        self.a = self.write('lib', 'files', 'a.pdf')
        self.bib(entry('one2000', 'files/a.pdf'))

    def test_mv_needs_two_paths(self):
        with self.assertRaises(SystemExit):
            self.lib(f'file mv {self.a}')

    def test_mv_dry_run_of_the_files_directory(self):
        out = self.out('file mv files other --dry-run')
        papers.config.DRYRUN = False
        self.assertIn('DRYRUN: filesdir = ', out)
        self.assertIn(f'DRYRUN: one2000: {self.a} -> {self.path("lib", "other", "a.pdf")}', out)
        self.assertTrue(os.path.exists(self.a))

    def test_detach_errors(self):
        with self.assertRaises(SystemExit):
            self.lib(f'file detach --broken {self.a}')
        with self.assertRaises(SystemExit):
            self.lib('file detach')

    def test_detach_nothing(self):
        self.assertIn('no link removed', self.out('file detach --broken'))

    def test_rm_needs_files(self):
        with self.assertRaises(SystemExit):
            self.lib('file rm')

    def test_check_without_issue(self):
        self.assertIn('no issue found in the files of 1 entries', self.out('file check'))

    def test_clean_without_filesdir(self):
        self.lib('config --unset filesdir')
        with self.assertRaisesRegex(PapersExit, 'no files directory'):
            self.lib('file clean -y')
