"""the file actions of list still work in v3, with a deprecation warning"""
import os
from unittest.mock import patch

from tests.test_file_cmd import FileTest, entry


class TestListDeprecated(FileTest):

    def setUp(self):
        super().setUp()
        self.a = self.write('src', 'a.pdf')
        self.si = self.write('src', 'si.pdf')
        self.bib(entry('one2000', self.a, doi='10.1000/one'), entry('two2000'))

    def warns(self, cmd, new):
        with self.assertLogs('papers', level='WARNING') as logs:
            self.lib(cmd)
        self.assertIn(new, '\n'.join(logs.output))

    def test_rename(self):
        self.warns('list --key one2000 --rename', 'papers file rename -')
        self.assertFalse(os.path.exists(self.a))
        self.assertEqual(len(self.libfiles()), 1)

    def test_rename_copy(self):
        self.warns('list --key one2000 --rename --copy', 'papers file rename --keep-source -')
        self.assertTrue(os.path.exists(self.a))
        self.assertEqual(len(self.libfiles()), 1)

    def test_copy(self):
        self.warns('list --key one2000 --copy', 'papers file rename --keep-source -')

    def test_add_files(self):
        self.warns(f'list --key two2000 --add-files {self.si}', 'papers file attach')
        self.assertEqual(self.files('two2000'), [self.si])

    def test_add_files_rename(self):
        self.warns(f'list --key two2000 --add-files {self.si} --rename', 'papers file attach')
        self.assertFalse(os.path.exists(self.si))
        self.assertEqual(len(self.libfiles()), 1)

    def test_open(self):
        with patch('papers.cli.view_entry_files') as view:
            self.warns('list --key one2000 -o', 'papers open -')
        view.assert_called_once()

    def test_fetch(self):
        with patch('papers.bib.Biblio.fix_entry') as fix:
            self.warns('list --key one2000 --fetch', 'papers check --fetch -')
        fix.assert_called_once()
