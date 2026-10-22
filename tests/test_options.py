"""The options harmonized in v3: -y/--yes, -R/--recursive, extract
--doi-only, restore (the deprecated forms are in test_deprecated.py)"""
from unittest.mock import patch

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
