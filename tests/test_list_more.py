"""More tests of papers list, tag and edit: the filters, the review check,
and the errors of the options"""
import io
from contextlib import redirect_stdout
from unittest.mock import patch

from papers.utils import PapersExit
from tests.common import FileTest, entry


class TestListFilters(FileTest):

    def setUp(self):
        super().setUp()
        self.a = self.write('src', 'a.pdf')
        self.bib(entry('one2000', self.a, doi='10.1000/one'),
                 entry('two2000', self.path('src', 'missing.pdf')),
                 entry('three2000').replace(' author = {Some One},\n', ''),
                 entry('four2000', doi='not a doi').replace('title', 'abstract = {About ice sheets},\n title'))

    def keys(self, cmd):
        return self.out(f'list {cmd} -K').split()

    def test_review_required(self):
        self.assertEqual(self.keys('--review-required'), ['three2000', 'four2000'])
        self.assertEqual(self.keys('--review-required --invert'), ['one2000', 'two2000'])

    def test_files(self):
        self.assertEqual(self.keys('--has-file'), ['one2000', 'two2000'])
        self.assertEqual(self.keys('--no-file'), ['three2000', 'four2000'])
        self.assertEqual(self.keys('--broken-file'), ['two2000'])

    def test_abstract_and_doi(self):
        self.assertEqual(self.keys('--abstract ice'), ['four2000'])
        self.assertEqual(self.keys('--doi 10.1000'), ['one2000'])

    def test_first_author(self):
        self.assertEqual(self.keys('--first-author one'), ['one2000', 'two2000', 'four2000'])

    def test_fuzzy_title(self):
        self.assertEqual(self.keys('--title "Titel of one2000"'), [])
        self.assertIn('one2000', self.keys('--title "Titel of one2000" --fuzzy'))

    def test_field(self):
        self.assertEqual(self.out('list --key one2000 --field doi year --no-key').split(), ['10.1000/one', '2000'])

    def test_by_and_fuzzy(self):
        with self.assertRaises(SystemExit):
            self.lib('list --duplicates --by key --fuzzy')

    def test_add_files_needs_one_entry(self):
        with self.assertRaisesRegex(PapersExit, 'only one entry'), self.assertLogs('papers', level='WARNING'):
            self.lib(f'list --add-files {self.a}')

    def test_fetch(self):
        with patch('papers.bib.Biblio.fix_entry') as fix, self.assertLogs('papers', level='WARNING') as logs:
            self.lib('list --key one2000 --fetch')
        self.assertTrue(fix.call_args.kwargs['fetch_all'])
        self.assertIn('papers check --fetch', '\n'.join(logs.output))

    def test_edit_failure_saves_nothing(self):
        with patch('papers.cli.common.edit_entries', side_effect=OSError('no editor')), \
                self.assertLogs('papers', level='ERROR'):
            self.lib('list --key one2000 -e')


class TestTagErrors(FileTest):

    def setUp(self):
        super().setUp()
        self.bib(entry('one2000'))

    def test_rename_with_entries(self):
        with self.assertRaises(SystemExit):
            self.lib('tag one2000 --rename a b')

    def test_add_without_entries(self):
        with self.assertRaises(SystemExit):
            self.lib('tag --add a')


class TestEditPipe(FileTest):

    def test_keys_from_a_pipe(self):
        # the editor reads the terminal: /dev/tty, when there is one
        self.bib(entry('one2000'))
        with patch('sys.stdin', io.StringIO('one2000\n')), \
                patch('papers.cli.entry_cmds.os.open', side_effect=OSError('no terminal')) as tty, \
                patch('papers.cli.common.edit_entries', side_effect=lambda entries: entries):
            self.lib('edit -')
        tty.assert_called_once()
