import os
import subprocess as sp
import sys
import unittest
from unittest.mock import patch
from urllib.parse import quote
import papers
from tests.common import InitTest, BaseTest, BibTest, tempfile, paperscmd
from papers.cli import VIEWER_PASSTHROUGH_ENV
from papers.utils import PapersExit, find_masked_viewer, file_uri_to_path
from papers.utils import strip_all

bibtex = """@article{Perrette_2011,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 doi = {10.5194/bg-8-515-2011},
 file = {article.pdf:pdf; supplement.mov:mov},
 journal = {Biogeosciences},
 keywords = {kiwi, ocean},
 link = {https://doi.org/10.5194%2Fbg-8-515-2011},
 month = {feb},
 number = {2},
 pages = {515--524},
 publisher = {Copernicus {GmbH}},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
 volume = {8},
 year = {2011}
}"""


class ListTest(InitTest):
    initial_content = bibtex
    anotherbib_content = None


class FormattingTest(ListTest):

    def test_format(self):
        out = self.papers('list -l', sp_cmd='check_output')
        self.assertEqual(strip_all(out), "Perrette_2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, files:2, kiwi | ocean)")

        out = self.papers('list --key-only', sp_cmd='check_output')
        self.assertEqual(out, "Perrette_2011")

        out = self.papers('list --field month doi', sp_cmd='check_output')
        self.assertEqual(strip_all(out), "Perrette_2011: feb 10.5194/bg-8-515-2011")

    def test_color(self):
        line = "Perrette_2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, files:2, kiwi | ocean)"
        # the standard output of the tests is not a terminal: no colours, no hyperlinks
        self.assertEqual(self.papers('list -l', sp_cmd='check_output'), line)
        self.assertEqual(self.papers('list -l --color never', sp_cmd='check_output'), line)
        out = self.papers('list -l --color always', sp_cmd='check_output')
        self.assertIn('\033[', out)
        self.assertIn('\033]8;;https://doi.org/10.5194/bg-8-515-2011', out)
        self.assertEqual(strip_all(out), line)
        self.assertNotIn('\033', self.papers('status', sp_cmd='check_output'))

    @unittest.skipUnless(hasattr(os, 'openpty'), 'needs a pseudo-terminal')
    def test_color_in_terminal(self):
        def run(**env):
            master, slave = os.openpty()
            environ = {k: v for k, v in os.environ.items() if k != 'NO_COLOR'}
            environ['PYTHONPATH'] = os.path.dirname(os.path.dirname(papers.__file__))
            sp.run([sys.executable, '-m', 'papers', 'list', '-l'], cwd=self.temp_dir.name, stdout=slave,
                   env={**environ, **env}, check=True)
            os.close(slave)
            out = os.read(master, 100000).decode()
            os.close(master)
            return out
        self.assertIn('\033[', run())
        self.assertNotIn('\033', run(NO_COLOR='1'))
        self.assertIn('\033', run(NO_COLOR=''))

    def test_format_option(self):
        line = self.papers('list -l', sp_cmd='check_output')
        self.assertEqual(self.papers('list', sp_cmd='check_output'), line)
        self.assertEqual(self.papers('list --format line', sp_cmd='check_output'), line)
        self.assertEqual(self.papers('list --format key', sp_cmd='check_output'), 'Perrette_2011')
        self.assertMultiLineEqual(self.papers('list --format bibtex', sp_cmd='check_output'),
                                  self.papers('list --plain', sp_cmd='check_output'))
        self.assertIn('@article{Perrette_2011', self.papers('list --format bibtex', sp_cmd='check_output'))

    def test_format_exclusive(self):
        with self.assertRaises(SystemExit):
            self.papers('list --format key --plain', sp_cmd='check_output')


class SearchTest(ListTest):

    def test_list_title(self):
        out = self.papers('list --plain --title "ice-edge blooms"', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

    def test_list_title_fuzzy(self):
        out = self.papers('list --plain --title "ice edge bloom arctc"', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers('list --plain --title "ice edge bloom arctc" --fuzzy', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

    def test_list_title_multiple(self):
        out = self.papers('list --plain --title ice edge', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        out = self.papers('list --plain --title ice edge antarctic', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers('list --plain --title ice edge antarctic --any', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

    def test_list_author(self):
        out = self.papers('list --plain --author perrette', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        out = self.papers('list --plain --author perrette balafon', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers('list --plain --author perrette balafon --any', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

    def test_list_first_author(self):
        out = self.papers('list --plain --first-author perrette', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        # Yool is an author, but not the first author
        out = self.papers('list --plain --first-author yool', sp_cmd='check_output')
        self.assertEqual(out, "")

    def test_list_key(self):
        out = self.papers('list --plain --key perrette', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        out = self.papers('list --plain --key perrette --strict', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers('list --plain --key perrette_2011 --strict', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

    def test_list_year(self):
        out = self.papers('list --plain --year 201', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        out = self.papers('list --plain --year 201 --strict', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers('list --plain --year 2011 --strict', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

    def test_list_tag(self):
        out = self.papers('list --plain --tag kiwi', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        out = self.papers('list --plain --tag kiwi ocean', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        out = self.papers('list --plain --tag kiwi bonobo', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers('list --plain --tag kiwi bonobo --any', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

    def test_list_tag_whole(self):
        # a whole tag, not part of the keywords field (#121)
        self.assertEqual(self.papers('list --plain --tag kiw', sp_cmd='check_output'), "")
        self.assertEqual(self.papers('list --plain --tag "kiwi, ocean"', sp_cmd='check_output'), "")
        out = self.papers('list --plain --tag "kiw*"', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)
        out = self.papers('list --plain --tag KIWI', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)


    def test_list_combined(self):
        out = self.papers('list --plain --year 2011 --author perrette', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        # Here we'd need the full name (never useful in practice)
        out = self.papers('list --plain --year 2011 --author perrette --strict', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers('list --plain --year 2021 --author perrette', sp_cmd='check_output')
        self.assertEqual(out, "")

        # --any has no effect on multiple strings
        out = self.papers('list --plain --year 2021 --author perrette --any', sp_cmd='check_output')
        self.assertEqual(out, "")


    def test_list_fullsearch(self):
        out = self.papers('list --plain 2011 perrette', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        # --strict is deactivated
        out = self.papers('list --plain 2011 perrette --strict', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        out = self.papers('list --plain 2021 perrette', sp_cmd='check_output')
        self.assertEqual(out, "")

        # any works well on full search strings
        out = self.papers('list --plain 2021 perrette --any', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)


class ListBrokenFileTest(InitTest):
    """papers list --broken-file lists entries with broken file links"""
    # Entry with file pointing to non-existent path
    initial_content = """@article{BrokenFile2020,
 author = {John Doe},
 doi = {10.5194/test-2020},
 file = {:nonexistent/path/to/file.pdf:pdf},
 title = {Test},
 year = {2020}
}"""
    anotherbib_content = None

    def test_list_broken_file(self):
        out = self.papers('list --plain --broken-file', sp_cmd='check_output')
        self.assertIn('BrokenFile2020', out)
        self.assertIn('Test', out)

class ListDuplicatesTest(InitTest):
    """papers list --duplicates lists entries with duplicate DOIs/keys"""
    initial_content = """@article{Entry1,
 author = {Author A},
 doi = {10.5194/same-doi},
 title = {First Paper},
 year = {2020}
}
@article{Entry2,
 author = {Author B},
 doi = {10.5194/same-doi},
 title = {Second Paper},
 year = {2021}
}"""
    anotherbib_content = None

    def test_list_duplicates(self):
        out = self.papers('list --plain --duplicates', sp_cmd='check_output')
        self.assertIn('Entry1', out)
        self.assertIn('Entry2', out)


class ListReviewRequiredTest(InitTest):
    """papers list --review-required lists suspicious entries (invalid doi, missing fields, etc.)"""
    # Entry with key starting with digit (invalid)
    initial_content = """@article{2020InvalidKey,
 author = {John Doe},
 doi = {10.5194/test-2020},
 title = {Test Article},
 year = {2020}
}"""
    anotherbib_content = None

    def test_list_review_required_invalid_key(self):
        out = self.papers('list --plain --review-required', sp_cmd='check_output')
        self.assertIn('2020InvalidKey', out)


class EditTest(ListTest):
    def test_delete(self):
        out = self.papers('list --author perrette --delete', sp_cmd='check_output')
        self.assertIn("Removed", strip_all(out))
        self.assertIn("Perrette_2011", strip_all(out))

        out = self.papers('list', sp_cmd='check_output')
        self.assertEqual(out, "")


    def test_add_tag(self):

        out = self.papers('list --tag newtag', sp_cmd='check_output')
        self.assertEqual(out, "")

        self.papers('list --author perrette --add-tag newtag -1')
        # self.assertEqual(strip_all(out), "Perrette_2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, files:2, kiwi | ocean | newtag)")

        out = self.papers('list --tag newtag -1', sp_cmd='check_output')
        self.assertEqual(strip_all(out), "Perrette_2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, files:2, kiwi | ocean | newtag)")

    def test_add_files(self):

        with tempfile.NamedTemporaryFile() as temp, tempfile.NamedTemporaryFile() as temp2:
            out = self.papers('list 2011 perrette -1', sp_cmd='check_output')
            self.assertEqual(strip_all(out), "Perrette_2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, files:2, kiwi | ocean)")

            out = self.papers(f'list 2011 perrette --add-files {temp.name}  {temp2.name} --rename --copy', sp_cmd='check_output')

            out = self.papers('list 2011 perrette -1', sp_cmd='check_output')
            self.assertEqual(strip_all(out), "Perrette_2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, files:4, kiwi | ocean)")

    def test_add_files_file_uri(self):
        with tempfile.NamedTemporaryFile(suffix=' a.pdf') as temp:
            uri = 'file://' + temp.name.replace(' ', '%20')
            self.papers(f'list 2011 perrette --add-files {uri}')
            out = self.papers('list 2011 perrette -1', sp_cmd='check_output')
            self.assertIn('files:3', strip_all(out))

class OpenCmdTest(InitTest):
    initial_content = """@article{NoFile2020,
 author = {No File},
 title = {Nothing attached},
 year = {2020}
}"""
    anotherbib_content = None

    def test_open_no_file_warns(self):
        # completes without launching a viewer (no file attached)
        self.papers('open NoFile2020')
        self.papers('open nofile2020')  # case-insensitive

    def test_open_unknown_key(self):
        self.papers('open NoSuchKey')  # logs an error, does not crash

    def test_open_file_path(self):
        # `papers open` also accepts existing file paths directly
        from unittest.mock import patch
        f = self._path('direct.pdf')
        open(f, 'w').write('x')
        with patch('papers.cli.entry_cmds.open_with_system') as viewer:
            self.papers(f'open {f}')
            viewer.assert_called_once_with(f)

    def test_bare_file_argument_opens_viewer(self):
        # `papers somefile.pdf` behaves like the (possibly masked) document
        # viewer: without another `papers` in $PATH, the file is opened with
        # the system viewer (issue #107)
        f = self._path('direct.pdf')
        open(f, 'w').write('x')
        with patch.dict(os.environ), \
                patch('papers.cli.find_masked_viewer', return_value=None), \
                patch('papers.cli.open_with_system') as viewer:
            os.environ.pop(VIEWER_PASSTHROUGH_ENV, None)
            self.papers(f'{f}')
            viewer.assert_called_once_with(f)

    def test_subcommand_wins_over_file(self):
        # a file named like a subcommand does not hijack the CLI
        open(self._path('status'), 'w').write('x')
        with patch('papers.cli.find_masked_viewer') as finder, \
                patch('papers.cli.open_with_system') as viewer:
            self.papers('status')
            finder.assert_not_called()
            viewer.assert_not_called()


class ViewerPassthroughNoInstallTest(BaseTest):
    anotherbib_content = None

    def setUp(self):
        super().setUp()
        self.pdf = self._path('doc.pdf')
        open(self.pdf, 'w').write('x')
        env = patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(VIEWER_PASSTHROUGH_ENV, None)

    def test_bare_file_argument_without_install(self):
        # the viewer passthrough must work without any papers install
        with patch('papers.cli.find_masked_viewer', return_value=None), \
                patch('papers.cli.open_with_system') as viewer:
            self.papers(f'{self.pdf}')
            viewer.assert_called_once_with(self.pdf)

    def test_file_uri_argument(self):
        # desktop entries launch the viewer as `papers %U`, i.e. with file:// URIs
        uri = 'file://' + quote(self.pdf)
        with patch('papers.cli.find_masked_viewer', return_value=None), \
                patch('papers.cli.open_with_system') as viewer:
            self.papers(f"'{uri}'")
            viewer.assert_called_once_with(self.pdf)

    def test_masked_viewer_receives_arguments_unchanged(self):
        # the masked viewer is exec'd with the original arguments, instead of
        # xdg-open, which may resolve back to this command
        uri = 'file://' + quote(self.pdf)
        with patch('papers.cli.find_masked_viewer', return_value='/usr/bin/papers'), \
                patch('papers.cli.os.execv') as execv, \
                patch('papers.cli.open_with_system') as viewer:
            self.papers(f"'{uri}' {self.pdf}")
            execv.assert_called_once_with('/usr/bin/papers', ['/usr/bin/papers', uri, self.pdf])
            viewer.assert_not_called()

    def test_loop_guard(self):
        # handed to the system viewer once already: stop instead of looping
        os.environ[VIEWER_PASSTHROUGH_ENV] = '1'
        with patch('papers.cli.find_masked_viewer', return_value=None), \
                patch('papers.cli.open_with_system') as viewer:
            with self.assertRaises(PapersExit):
                self.papers(f'{self.pdf}')
            viewer.assert_not_called()


class FindMaskedViewerTest(unittest.TestCase):

    def _executable(self, path, content):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, 'w').write(content)
        os.chmod(path, 0o755)

    def test_skips_papers_cli_scripts(self):
        with tempfile.TemporaryDirectory() as d:
            script = '#!/usr/bin/python3\nfrom papers.__main__ import main_clean_exit\n'
            self._executable(os.path.join(d, 'venv', 'papers'), script)
            self._executable(os.path.join(d, 'pipx', 'papers'), script)
            self._executable(os.path.join(d, 'usr', 'papers'), '#!/bin/sh\n')
            path = os.pathsep.join(os.path.join(d, x) for x in ['venv', 'empty', 'pipx', 'usr'])
            with patch.dict(os.environ, {'PATH': path}):
                self.assertEqual(find_masked_viewer(), os.path.join(d, 'usr', 'papers'))

    def test_none_without_other_viewer(self):
        with tempfile.TemporaryDirectory() as d:
            self._executable(os.path.join(d, 'papers'), 'from papers.__main__ import main\n')
            with patch.dict(os.environ, {'PATH': d}):
                self.assertIsNone(find_masked_viewer())

    def test_file_uri_to_path(self):
        self.assertEqual(file_uri_to_path('file:///tmp/a%20b,%203.pdf'), '/tmp/a b, 3.pdf')
        self.assertEqual(file_uri_to_path('/tmp/a b.pdf'), '/tmp/a b.pdf')


class TestReviewRequiredKeepsDoi(BibTest):

    def test_doi_unchanged(self):
        # the invalid DOI used to be wrapped in color codes, and saved by an action
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            bib = os.path.join(d, 'lib.bib')
            open(bib, 'w').write("""@article{a2000,
 author = {Author, A.},
 title = {One},
 year = {2000},
 doi = {not a doi}
}
""")
            paperscmd(f'list --review-required --add-keywords checked --bibtex {bib}')
            text = open(bib).read()
        self.assertIn('doi = {not a doi}', text)
        self.assertIn('checked', text)
