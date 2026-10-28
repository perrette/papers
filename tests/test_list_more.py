"""More tests of papers list, tag and edit: the filters, the review check,
and the errors of the options"""
import io
import os
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

    def test_invert_is_the_complement(self):
        # used to invert each word, then require all of them: "no word
        # matches" instead of "not listed by the same search"
        self.bib(self.read_bib() + entry('five2001').replace('Title of five2001', 'Ice and ocean')
                 + entry('six2001').replace('Title of six2001', 'Ocean heat').replace('Some One', 'Other, Person'))
        every = self.keys('')
        for search in ['--title ice ocean', '--title ice ocean --any', '--title "of" --year 2001',
                       '--author one --year 2000', '--author other --title ocean --any',
                       '--title "Titel of one2000" --fuzzy', 'ice sheets', 'ice sheets --any', '--key "*2000"',
                       '--strict --title ice', '--has-file', '--review-required --author one',
                       '--duplicates --by title', '--first-author one --year 2001']:
            with self.subTest(search):
                listed = self.keys(search)
                inverted = self.keys(search + ' --invert')
                self.assertEqual(sorted(listed + inverted), sorted(every))
                self.assertFalse(set(listed) & set(inverted))

    def read_bib(self):
        with open(self.path('lib', 'papers.bib')) as f:
            return f.read()

    def test_fuzzy_title(self):
        self.assertEqual(self.keys('--title "Titel of one2000"'), [])
        self.assertIn('one2000', self.keys('--title "Titel of one2000" --fuzzy'))

    def test_fuzzy_ratio_is_a_minimum(self):
        # the same words in another order score 100: a match with --fuzzy-ratio 100
        self.assertEqual(self.keys('--title "one2000 of Title" --fuzzy --fuzzy-ratio 100'), ['one2000'])

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
        before = open(self.path('lib', 'papers.bib')).read()
        # exits 1 (#117)
        with patch('papers.cli.common.edit_in_editor', side_effect=OSError('no editor')), \
                self.assertRaisesRegex(PapersExit, 'no editor'):
            self.lib('list --key one2000 -e')
        self.assertEqual(open(self.path('lib', 'papers.bib')).read(), before)


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
        real_open = os.open
        ttys = []

        def no_terminal(path, *args, **kwargs):  # the other files (e.g. the lock of the library) open
            if path == '/dev/tty':
                ttys.append(path)
                raise OSError('no terminal')
            return real_open(path, *args, **kwargs)
        with patch('sys.stdin', io.StringIO('one2000\n')), \
                patch('papers.cli.entry_cmds.os.open', side_effect=no_terminal), \
                patch('papers.cli.common.edit_in_editor', side_effect=lambda entries: entries):
            self.lib('edit -')
        self.assertEqual(ttys, ['/dev/tty'])
