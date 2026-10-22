"""The options harmonized in v3: -y/--yes, -R/--recursive, extract
--doi-only, restore (the deprecated forms are in test_deprecated.py); the
case of DOIs in fetch, and the exit code of papers git"""
from unittest.mock import patch

from papers.utils import PapersExit
from tests.common import FileTest, entry


def no_question(*args):
    raise AssertionError('no question expected')


class TestOptions(FileTest):

    def setUp(self):
        super().setUp()
        self.a = self.write('src', 'a.pdf')
        self.bib(entry('one2000', doi='10.1000/one'))

    def test_check_yes(self):
        with patch('papers.bib.Biblio.fix_entry') as fix:
            self.lib('check one2000 -y')
        self.assertFalse(fix.call_args.kwargs['interactive'])
        with patch('papers.bib.Biblio.fix_entry') as fix:
            self.lib('check one2000')
        self.assertTrue(fix.call_args.kwargs['interactive'])

    def test_backup_remove_yes(self):
        info = {'gitdir': self.path('backup-x'), 'bibtex': None, 'current': False, 'snapshots': None,
                'last': None, 'size': 0}
        with patch('papers.cli.backup_cmds.list_backup_dirs', return_value=[info]), \
                patch('papers.cli.backup_cmds.shutil.rmtree') as rmtree, patch('builtins.input', no_question):
            self.lib('backup remove backup-x --yes')
        rmtree.assert_called_once_with(self.path('backup-x'))

    def test_extract_doi_only(self):
        with patch('papers.cli.fetch_cmds.extract_pdf_doi', return_value='10.1000/x') as doi, \
                patch('papers.cli.fetch_cmds.extract_pdf_metadata', no_question):
            out = self.out(f'extract --doi-only {self.a}')
        self.assertEqual(out.strip(), '10.1000/x')
        doi.assert_called_once()

    def test_extract_R(self):
        with patch('papers.cli.fetch_cmds.extract_pdf_doi', return_value='10.1000/x') as doi:
            self.out(f'extract --doi-only -R {self.path("src")}')
        self.assertEqual(doi.call_args.args[0], self.a)

    def test_add_R(self):
        with patch('papers.bib.Biblio.scan_dir', return_value=[]) as scan:
            self.lib(f'add -R {self.path("src")} --no-query-doi --no-query-fulltext')
        scan.assert_called_once()

    def test_restore(self):
        self.lib('config git true')
        with patch('papers.cli.backup_cmds.restore_from_backupdir') as restore, \
                patch('papers.cli.backup_cmds.logger.warning') as warning:
            self.lib('restore')
        restore.assert_called_once()
        warning.assert_not_called()


class TestAddAuthor(FileTest):
    """-a is --author in add (the v2 -a FILE fallback is in test_deprecated.py)"""

    def setUp(self):
        super().setUp()
        self.a = self.write('src', 'a.pdf')

    def entry(self, key):
        from papers.bib import Biblio
        return next(e for e in Biblio.load(self.path('lib', 'papers.bib'), '').entries if e.key == key)

    def test_a_is_author(self):
        with self.assertNoLogs('papers', level='WARNING'):
            self.lib('add --title Three --year 2001 -a "Smith, John"')
        self.assertEqual(self.entry('smith2001')['author'], 'Smith, John')

    def test_a_then_file(self):
        # -a NAME FILE: the values after the name are files to add
        bib = self.write('src', 'one.bib', content=entry('one2000'))
        self.lib(f'add -a "Doe, Jane" {bib}')
        self.assertEqual(self.entry('one2000')['author'], 'Doe, Jane')

    def test_file_then_other_values(self):
        # the first value is a file but the others are not: neither attach nor author
        with self.assertRaisesRegex(PapersExit, '--attach FILE'):
            self.lib(f'add --title Three -a {self.a} Smith')

    def test_a_and_author(self):
        with self.assertRaises(PapersExit):
            self.lib('add --title Three -a Smith --author Doe')


class TestFetchKeepsCase(FileTest):

    def test_arxiv_doi_case(self):
        with patch('papers.cli.fetch_cmds.fetch_bibtex_by_doi', return_value='@misc{x}') as fetch:
            self.lib('fetch https://doi.org/10.48550/arXiv.math.AG/0601001')
        fetch.assert_called_once_with('10.48550/arXiv.math.AG/0601001')
        with patch('papers.fetch.fetch_bibtex_by_arxiv', return_value='@misc{x}') as arxiv:
            self.lib('fetch 10.48550/arXiv.math.AG/0601001')
        arxiv.assert_called_once_with('math.AG/0601001')


class TestGitCommand(FileTest):

    def test_git_error_exit_code(self):
        self.lib('config git true')
        with self.assertRaises(SystemExit) as cm:
            self.lib('git log no-such-ref')
        self.assertEqual(cm.exception.code, 128)  # git's own exit code

    def test_git_output(self):
        self.lib('config git true')
        self.assertEqual(self.out('git rev-list --all --count').strip(), '1')

    def test_no_backup(self):
        with self.assertRaisesRegex(PapersExit, 'papers config git true'):
            self.lib('git status')
