"""papers edit, rm, tag, and their shortcuts on list"""
import io
import os
from contextlib import redirect_stdout
from unittest.mock import patch

from papers.bib import Biblio
from papers.encoding import parse_keywords
from papers.utils import PapersExit

from tests.test_file_cmd import FileTest, entry


def tagged(key, keywords, *files):
    return entry(key, *files).replace(' title', f' keywords = {{{keywords}}},\n title')


class EntryTest(FileTest):

    def keys(self):
        return sorted(e.key for e in Biblio.load(self.path('lib', 'papers.bib'), '').entries)

    def entry(self, key):
        return next(e for e in Biblio.load(self.path('lib', 'papers.bib'), '').entries if e.key == key)


class TestRm(EntryTest):

    def setUp(self):
        super().setUp()
        self.own = self.write('lib', 'files', 'own.pdf')
        self.shared = self.write('lib', 'files', 'shared.pdf')
        self.outside = self.write('elsewhere', 'out.pdf')
        self.bib(entry('one2000', 'files/own.pdf', 'files/shared.pdf', self.outside),
                 entry('two2000', 'files/shared.pdf'),
                 entry('three2000'))

    def rm(self, cmd, terminal=False, answer='n'):
        out = io.StringIO()
        with patch('papers.cli.stdin_is_terminal', return_value=terminal), \
                patch('builtins.input', return_value=answer) as ask, redirect_stdout(out):
            self.lib(cmd)
        self.asked = ask.call_count
        self.prompt = ask.call_args.args[0] if ask.called else None
        return out.getvalue()

    def test_non_terminal_keeps_files(self):
        out = self.rm('rm one2000')
        self.assertEqual(self.keys(), ['three2000', 'two2000'])
        self.assertEqual(self.asked, 0)
        for f in [self.own, self.shared, self.outside]:
            self.assertTrue(os.path.exists(f))
        self.assertIn(self.own, out)
        self.assertIn('papers file clean', out)

    def test_terminal_asks_for_files_inside(self):
        out = self.rm('rm one2000', terminal=True, answer='y')
        self.assertEqual(self.asked, 1)
        self.assertEqual(self.prompt, 'also delete 1 file(s)? [y/N] ')
        self.assertIn(self.own, out)
        self.assertFalse(os.path.exists(self.own))
        self.assertTrue(os.path.exists(self.shared))  # two2000 links to it
        self.assertTrue(os.path.exists(self.outside))  # only with --delete-files

    def test_terminal_no(self):
        self.rm('rm one2000', terminal=True, answer='n')
        self.assertTrue(os.path.exists(self.own))

    def test_delete_files(self):
        self.rm('rm one2000 --delete-files', terminal=True)
        self.assertEqual(self.asked, 0)
        self.assertFalse(os.path.exists(self.own))
        self.assertFalse(os.path.exists(self.outside))
        self.assertTrue(os.path.exists(self.shared))

    def test_keep_files(self):
        self.rm('rm one2000 --keep-files', terminal=True)
        self.assertEqual(self.asked, 0)
        self.assertTrue(os.path.exists(self.own))

    def test_hard_link(self):
        pool = self.write('pool', 'files', 'pool.pdf')
        os.link(pool, self.path('lib', 'files', 'linked.pdf'))
        self.bib(entry('four2000', 'files/linked.pdf'))
        out = self.rm('rm four2000', terminal=True, answer='y')
        self.assertIn('hard link', out)
        self.assertFalse(os.path.exists(self.path('lib', 'files', 'linked.pdf')))
        self.assertTrue(os.path.exists(pool))

    def test_several_and_stdin(self):
        with patch('sys.stdin', io.StringIO('one2000\nthree2000\n')):
            self.rm('rm - --delete-files')
        self.assertEqual(self.keys(), ['two2000'])
        # removing the last entry that links to the shared file deletes it
        self.rm('rm two2000 --delete-files')
        self.assertFalse(os.path.exists(self.shared))

    def test_unknown_key_changes_nothing(self):
        with self.assertRaises(PapersExit):
            self.rm('rm one2000 nope2000 --delete-files')
        self.assertEqual(len(self.keys()), 3)
        self.assertTrue(os.path.exists(self.own))

    def test_list_delete(self):
        self.rm('list --key one2000 --delete', terminal=True, answer='y')
        self.assertEqual(self.keys(), ['three2000', 'two2000'])
        self.assertFalse(os.path.exists(self.own))

    def test_list_delete_keep_files(self):
        self.rm('list --key one2000 --delete --keep-files', terminal=True)
        self.assertEqual(self.asked, 0)
        self.assertTrue(os.path.exists(self.own))

    def test_list_delete_files(self):
        self.rm('list --key one2000 --delete --delete-files')
        self.assertFalse(os.path.exists(self.outside))


class TestTag(EntryTest):

    def setUp(self):
        super().setUp()
        self.bib(tagged('one2000', 'kiwi, ocean'), tagged('two2000', 'ocean'), entry('three2000'))

    def tags(self, key):
        return parse_keywords(self.entry(key))

    def test_list(self):
        out = self.out('tag')
        self.assertEqual(out.splitlines(), ['ocean (2)', 'kiwi (1)'])
        self.assertEqual(self.out('tag two2000').splitlines(), ['ocean (1)'])

    def test_add(self):
        self.lib('tag one2000 three2000 --add ocean sea')
        self.assertEqual(self.tags('one2000'), ['kiwi', 'ocean', 'sea'])
        self.assertEqual(self.tags('three2000'), ['ocean', 'sea'])
        self.assertEqual(self.entry('one2000')['keywords'], 'kiwi, ocean, sea')

    def test_rm(self):
        self.lib('tag one2000 two2000 --rm ocean')
        self.assertEqual(self.tags('one2000'), ['kiwi'])
        self.assertNotIn('keywords', self.entry('two2000').fields_dict)

    def test_stdin(self):
        with patch('sys.stdin', io.StringIO('two2000\n')):
            self.lib('tag - --add new')
        self.assertEqual(self.tags('two2000'), ['ocean', 'new'])
        self.assertEqual(self.tags('one2000'), ['kiwi', 'ocean'])

    def test_rename(self):
        out = self.out('tag --rename ocean sea')
        self.assertIn('2 entries', out)
        self.assertEqual(self.tags('one2000'), ['kiwi', 'sea'])
        self.assertEqual(self.tags('two2000'), ['sea'])

    def test_rename_merges(self):
        self.lib('tag --rename ocean kiwi')
        self.assertEqual(self.tags('one2000'), ['kiwi'])

    def test_add_needs_entries(self):
        with self.assertRaises(SystemExit):
            self.lib('tag --add x')

    def test_list_add_tag(self):
        self.lib('list --key three2000 --add-tag kiwi')
        self.assertEqual(self.tags('three2000'), ['kiwi'])


class TestEdit(EntryTest):

    def setUp(self):
        super().setUp()
        self.bib(entry('one2000'), entry('two2000'))

    def test_edit(self):
        def edit(entries):
            self.assertEqual([e.key for e in entries], ['two2000'])
            entries[0]['title'] = 'Edited'
            return entries
        with patch('papers.cli.edit_entries', side_effect=edit):
            self.lib('edit two2000')
        self.assertEqual(self.entry('two2000')['title'], 'Edited')
        self.assertEqual(self.keys(), ['one2000', 'two2000'])

    def test_unknown_key(self):
        with patch('papers.cli.edit_entries') as edit:
            with self.assertRaises(PapersExit):
                self.lib('edit nope2000')
            edit.assert_not_called()

    def test_list_edit(self):
        def edit(entries):
            entries[0]['title'] = 'Edited'
            return entries
        with patch('papers.cli.edit_entries', side_effect=edit):
            self.lib('list --key one2000 -e')
        self.assertEqual(self.entry('one2000')['title'], 'Edited')
