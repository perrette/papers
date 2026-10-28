"""Unit tests of papers.cli (main, -C, main_clean_exit) and of the helpers
of papers.cli.common"""
import argparse
import io
import logging
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from papers import logger
from unittest import mock

import papers.cli
from papers.bib import Biblio
from papers.cli import main, main_clean_exit
from papers.cli.parser import get_parser
from papers.cli.common import (_delete_files_option, _key_option_entries, _one_entry, check_install,
                               edit_entries, edit_selected, files_mode, print_kept_files, stdin_is_terminal,
                               view_entry_files)
from papers.config import Config
from papers.utils import PapersExit

from tests.common import ConfigTest, FileTest, entry


def biblio_of(*entries):
    biblio = Biblio()
    biblio.add_bibtex(''.join(entries))
    return biblio


class TestMain(FileTest):

    def out(self, args):
        out = io.StringIO()
        with redirect_stdout(out):
            main(args)
        return out.getvalue()

    def test_version(self):
        self.assertEqual(self.out(['--version']).strip(), papers.__version__)

    def test_no_command_prints_help(self):
        with self.assertRaises(PapersExit), redirect_stdout(io.StringIO()) as out:
            main([])
        self.assertIn('usage: papers', out.getvalue())

    def test_file_without_subcommand(self):
        with self.assertRaises(PapersExit), redirect_stdout(io.StringIO()) as out:
            main(['-C', self.path('lib'), 'file'])
        self.assertIn('usage: papers file', out.getvalue())

    def test_C_attached_form(self):
        self.bib(entry('one2000'))
        self.assertIn('one2000', self.out([f'-C{self.path("lib")}', 'list']))

    def test_C_combined(self):
        self.bib(entry('one2000'))
        self.assertIn('one2000', self.out(['-C', self.dir, '-C', 'lib', 'list']))

    def test_C_without_directory(self):
        with self.assertRaisesRegex(PapersExit, 'requires a directory'):
            main(['-C'])

    def test_C_not_a_directory(self):
        with self.assertRaisesRegex(PapersExit, 'not a directory'):
            main(['-C', self.path('none'), 'list'])


class TestMainCleanExit(unittest.TestCase):

    def run_main(self, error):
        with mock.patch('papers.cli.main', side_effect=error), \
                mock.patch.object(papers.cli.logger, 'getEffectiveLevel', return_value=logging.WARNING), \
                self.assertLogs('papers', level='ERROR') as logs, \
                self.assertRaises(SystemExit) as cm:
            main_clean_exit([])
        self.assertEqual(cm.exception.code, 1)
        return '\n'.join(logs.output)

    def test_papers_exit(self):
        self.assertIn('something wrong', self.run_main(PapersExit('something wrong')))

    def test_eof(self):
        self.assertIn('no input to answer it', self.run_main(EOFError()))

    def test_debug_raises(self):
        with mock.patch('papers.cli.main', side_effect=PapersExit('x')), \
                mock.patch.object(papers.cli.logger, 'getEffectiveLevel', return_value=logging.DEBUG):
            with self.assertRaises(PapersExit):
                main_clean_exit([])
        with mock.patch('papers.cli.main', side_effect=EOFError()), \
                mock.patch.object(papers.cli.logger, 'getEffectiveLevel', return_value=logging.DEBUG):
            with self.assertRaises(EOFError):
                main_clean_exit([])



class TestLoggingOptions(unittest.TestCase):
    "-v/--verbose and --debug, and the former --info, --warn and --error (hidden, still accepted)"

    def setUp(self):
        self.addCleanup(papers.cli.logger.setLevel, papers.cli.logger.level)
        papers.cli.logger.setLevel(logging.WARNING)
        self.parser, self.subparsers = get_parser()

    def level(self, *args):
        papers.cli.handle_logging(self.parser.parse_args(['status', *args]))
        return papers.cli.logger.level

    def test_levels(self):
        for args, level in [((), logging.WARNING), (('-v',), logging.INFO), (('--verbose',), logging.INFO),
                            (('--debug',), logging.DEBUG), (('-v', '--debug'), logging.DEBUG),
                            (('--warn',), logging.WARNING), (('--error',), logging.ERROR)]:
            with self.subTest(args=args):
                papers.cli.logger.setLevel(logging.WARNING)
                self.assertEqual(self.level(*args), level)

    def test_info(self):
        with self.assertLogs('papers', level='WARNING') as logs:
            self.assertEqual(self.level('--info'), logging.INFO)
        self.assertIn('--info is deprecated: use -v', '\n'.join(logs.output))

    def test_help(self):
        text = self.subparsers.choices['add'].format_help()
        self.assertIn('-v, --verbose', text)
        self.assertIn('--debug', text)
        for option in ['--info', '--warn', '--error']:
            self.assertNotIn(option, text)


class TestCheckInstall(ConfigTest):

    def options(self, **kw):
        return argparse.Namespace(**{'bibtex': None, 'filesdir': None, 'absolute_paths': None, 'git': None, **kw})

    def test_no_library(self):
        with self.assertRaisesRegex(PapersExit, 'papers init'):
            check_install(None, self.options(), Config())

    def test_bibtex_must_exist(self):
        config = Config(bibtex=self.path('papers.bib'))
        with self.assertRaisesRegex(PapersExit, 'no bibtex file found'):
            check_install(None, self.options(), config)
        self.assertIs(check_install(None, self.options(), config, bibtex_must_exist=False), config)

    def test_options(self):
        Path(self.path('papers.bib')).write_text('')
        config = Config(bibtex=self.path('papers.bib'))
        with self.assertLogs('papers', level='WARNING'):
            config = check_install(None, self.options(filesdir='files', absolute_paths=True), config)
        self.assertEqual((config.filesdir, config.absolute_paths), ('files', True))


class TestFilesMode(unittest.TestCase):

    def test_link_excludes_copy(self):
        o = argparse.Namespace(link=True, copy=True)
        with self.assertRaises(PapersExit):
            files_mode(o, Config(filesdir='files'))

    def test_no_filesdir(self):
        self.assertEqual(files_mode(argparse.Namespace(), Config()), 'link')
        with self.assertRaisesRegex(PapersExit, 'no files directory'):
            files_mode(argparse.Namespace(copy=True), Config())


class TestHelpers(unittest.TestCase):

    def test_stdin_closed(self):
        with mock.patch.object(sys, 'stdin', None):
            self.assertFalse(stdin_is_terminal())

    def test_delete_files_option(self):
        parser = argparse.ArgumentParser()
        config = argparse.Namespace(shallow=False)
        with mock.patch.object(parser, 'error', side_effect=SystemExit(2)):
            with self.assertRaises(SystemExit):
                _delete_files_option(parser, argparse.Namespace(delete_files=True, keep_files=True), config)
        self.assertIsNone(_delete_files_option(parser, argparse.Namespace(delete_files=False, keep_files=False),
                                               config))
        self.assertFalse(_delete_files_option(parser, argparse.Namespace(delete_files=False, keep_files=True),
                                              config))
        self.assertTrue(_delete_files_option(parser, argparse.Namespace(delete_files=True, keep_files=False),
                                             config))
        shallow = argparse.Namespace(shallow=True)
        with self.assertRaisesRegex(PapersExit, 'shallow library'):
            _delete_files_option(parser, argparse.Namespace(delete_files=True, keep_files=False), shallow)
        self.assertIsNone(_delete_files_option(parser, argparse.Namespace(delete_files=False, keep_files=False),
                                               shallow))

    def test_print_kept_files(self):
        with redirect_stdout(io.StringIO()) as out:
            print_kept_files(['a.pdf'], ['b.pdf'])
        self.assertEqual(out.getvalue(), 'kept a.pdf: another entry links to it\nkept b.pdf: it is a file of a pool\n')

    def test_key_option_swallows_a_file(self):
        biblio = biblio_of(entry('one2000'))
        self.assertIsNone(_key_option_entries(biblio, None))
        with self.assertRaisesRegex(PapersExit, 'put the files before --key'):
            _key_option_entries(biblio, ['one2000', 'paper.pdf'])

    def test_one_entry(self):
        biblio = biblio_of(entry('one2000'), entry('two2000'))
        self.assertEqual(_one_entry(biblio, 'one2000').key, 'one2000')

    def test_view_entry_files(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, '.x.bib').write_text('')  # a folder of the pre-2.19 layout
            biblio = biblio_of(entry('one2000', os.path.join(d, 'a.pdf'), os.path.join(d, 'b.pdf')),
                               entry('two2000', os.path.join(d, 'c.pdf')))
            with mock.patch('papers.cli.common.hidden_bibtex', return_value=os.path.join(d, '.x.bib')), \
                    mock.patch('papers.cli.common.open_with_system') as view:
                view_entry_files(biblio, biblio.entries[0])
            view.assert_called_once_with(d)
            with mock.patch('papers.cli.common.open_with_system') as view:
                view_entry_files(biblio, biblio.entries[1])
            view.assert_called_once_with(os.path.join(d, 'c.pdf'))


class TestEditEntries(unittest.TestCase):

    def setUp(self):
        self.entries = biblio_of(entry('one2000')).entries

    def edit(self, text):
        with mock.patch('papers.cli.common.edit_text', return_value=text):
            with self.assertLogs('papers', level='ERROR'):
                return edit_entries(self.entries)

    def test_editor_failed(self):
        self.assertIs(self.edit(None), self.entries)

    def test_no_entry(self):
        self.assertIs(self.edit('just text'), self.entries)

    def test_unparsable_block(self):
        self.assertIs(self.edit(entry('one2000') + '@article{two,\n title = {unclosed\n'), self.entries)

    def test_bad_field_name(self):
        self.assertIs(self.edit('@article{one2000,\n bad.name = {x}\n}\n'), self.entries)

    def test_edit_selected_error(self):
        biblio = biblio_of(entry('one2000'))
        with mock.patch('papers.cli.common.edit_in_editor', side_effect=OSError('no editor')):
            self.assertRaisesRegex(PapersExit, 'no editor', edit_selected, biblio, biblio.entries)
        self.assertEqual([e.key for e in biblio.entries], ['one2000'])


class TestImports(unittest.TestCase):

    def test_network_modules_not_imported(self):
        "requests and bs4 are imported when a network query is made, not when papers starts"
        import subprocess
        code = "import sys, papers.cli; print(sorted(m for m in ('requests', 'bs4') if m in sys.modules))"
        out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True,
                             env=dict(os.environ, PYTHONPATH=str(Path(papers.cli.__file__).parents[2])))
        self.assertEqual(out.stdout.strip(), '[]')


class TestBrokenPipe(unittest.TestCase):

    def test_no_traceback(self):
        # papers list | head (#121): a subprocess, since the handler replaces the standard output
        code = ("import papers.cli as c\n"
                "def main(args=None): raise BrokenPipeError\n"
                "c.main = main\n"
                "c.main_clean_exit()\n")
        res = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                             env={**os.environ, 'PYTHONPATH': os.getcwd()})
        self.assertEqual(res.returncode, 1)
        self.assertNotIn('Traceback', res.stderr)


class TestInterrupt(unittest.TestCase):

    def test_ctrl_c(self):
        import io
        from contextlib import redirect_stderr
        from papers.cli import main_clean_exit
        err = io.StringIO()
        with patch('papers.cli.main', side_effect=KeyboardInterrupt), redirect_stderr(err), \
                patch.object(logger, 'getEffectiveLevel', return_value=30), self.assertRaises(SystemExit) as cm:
            main_clean_exit([])
        self.assertEqual(cm.exception.code, 130)
        self.assertNotIn('Traceback', err.getvalue())
