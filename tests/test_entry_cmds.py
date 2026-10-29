"""papers edit, rm, tag, and their shortcuts on list"""
import io
import os
from contextlib import redirect_stdout
from unittest.mock import patch

from papers.bib import Biblio
from papers.encoding import parse_keywords
from papers.utils import PapersExit

from tests.common import FileTest, entry


def tagged(key, keywords, *files):
    return entry(key, *files).replace(' title', f' keywords = {{{keywords}}},\n title')


class EntryTest(FileTest):

    def keys(self):
        return sorted(e.key for e in Biblio.load(self.path('lib', 'papers.bib'), '').entries)

    def entry(self, key):
        return next(e for e in Biblio.load(self.path('lib', 'papers.bib'), '').entries if e.key == key)


class TestAddEmptyKey(EntryTest):
    "the key template gives an empty key (no author, year, doi): the key of the first title word"

    def test_add(self):
        new = self.write('new.json', content='[{"type": "article-journal", "title": "Only a title"}]')
        self.lib(f'add {new}')
        self.lib('add --title "Only a title" --year 2000')
        self.lib('add --title "Only another"')
        self.assertEqual(self.keys(), ['only', 'only2000', 'onlyb'])


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
        with patch('papers.cli.entry_cmds.stdin_is_terminal', return_value=terminal), \
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


class TestNestedTags(EntryTest):
    "a tag with / is under another tag (#128)"

    def setUp(self):
        super().setUp()
        self.bib(tagged('one2000', 'climate, climate/amoc'), tagged('two2000', 'climate/amoc/tipping, kiwi'),
                 tagged('three2000', 'climate-review, climatex'), tagged('four2000', 'ocean/amoc, Climate/Arctic'))

    def tags(self, key):
        return parse_keywords(self.entry(key))

    def listed(self, args):
        return sorted(self.out('list -K ' + args).split())

    def test_list_tag(self):
        self.assertEqual(self.listed('--tag climate'), ['four2000', 'one2000', 'two2000'])
        self.assertEqual(self.listed('--tag climate/amoc'), ['one2000', 'two2000'])
        self.assertEqual(self.listed('--tag climate/amoc/'), ['one2000', 'two2000'])
        self.assertEqual(self.listed('--tag CLIMATE/AMOC/tipping'), ['two2000'])
        self.assertEqual(self.listed('--tag climate/amoc/tip'), [])
        self.assertEqual(self.listed('--tag "climate/*"'), ['four2000', 'one2000', 'two2000'])
        self.assertEqual(self.listed('--tag "*/amoc"'), ['four2000', 'one2000', 'two2000'])
        self.assertEqual(self.listed('--tag "climate*"'), ['four2000', 'one2000', 'three2000', 'two2000'])
        self.assertEqual(self.listed('--tag climate kiwi'), ['two2000'])

    def test_rename(self):
        out = self.out('tag --rename climate ocean')
        self.assertIn('3 entries', out)
        self.assertEqual(self.tags('one2000'), ['ocean', 'ocean/amoc'])
        self.assertEqual(self.tags('two2000'), ['ocean/amoc/tipping', 'kiwi'])
        self.assertEqual(self.tags('three2000'), ['climate-review', 'climatex'])
        # whatever the case, as --tag climate finds it
        self.assertEqual(self.tags('four2000'), ['ocean/amoc', 'ocean/Arctic'])

    def test_rename_nested(self):
        self.lib('tag --rename climate/amoc ocean')
        self.assertEqual(self.tags('one2000'), ['climate', 'ocean'])
        self.assertEqual(self.tags('two2000'), ['ocean/tipping', 'kiwi'])

    def test_rename_merges(self):
        self.lib('tag --rename climate/amoc/tipping ocean/amoc')
        self.lib('tag two2000 --add ocean/amoc/x')
        self.lib('tag --rename ocean/amoc/x ocean/amoc')
        self.assertEqual(self.tags('two2000'), ['ocean/amoc', 'kiwi'])

    def test_list_tree(self):
        self.assertEqual(self.out('tag').splitlines(), [
            'climate (2)',
            '  amoc (2)',
            '    tipping (1)',
            'Climate (1)',
            '  Arctic (1)',
            'climate-review (1)',
            'climatex (1)',
            'kiwi (1)',
            'ocean (1)',
            '  amoc (1)',
        ])


class TestEdit(EntryTest):

    def setUp(self):
        super().setUp()
        self.bib(entry('one2000'), entry('two2000'))

    def test_edit(self):
        def edit(entries):
            self.assertEqual([e.key for e in entries], ['two2000'])
            entries[0]['title'] = 'Edited'
            return entries
        with patch('papers.cli.common.edit_in_editor', side_effect=edit):
            self.lib('edit two2000')
        self.assertEqual(self.entry('two2000')['title'], 'Edited')
        self.assertEqual(self.keys(), ['one2000', 'two2000'])

    def test_edit_rejected_exits(self):
        # an edit that does not parse is an error, exit 1 (#117)
        with patch('papers.cli.common.edit_text', return_value='@article{two2000,\n title = {unclosed\n'), \
                self.assertRaises(PapersExit):
            self.lib('edit two2000')
        self.assertEqual(self.entry('two2000')['title'], 'Title of two2000')

    def test_edit_key_taken(self):
        with patch('papers.cli.common.edit_text', return_value=entry('one2000')), \
                self.assertRaisesRegex(PapersExit, 'another entry'):
            self.lib('edit two2000')
        self.assertEqual(self.keys(), ['one2000', 'two2000'])


    def editor_script(self):
        script = self.write('bin', 'editor.sh', content="#!/bin/sh\nsed -i 's/Original/Edited/' \"$1\"\n")
        os.chmod(script, 0o755)
        return script

    def test_add_edit_without_file(self):
        self.lib(f'config editor {self.editor_script()}')
        with patch.dict(os.environ, {'VISUAL': 'false', 'EDITOR': 'false'}):
            self.lib('add -e --title Original --author "Smith, John" --year 2001 --key three2001')
        self.assertEqual(self.entry('three2001')['title'], 'Edited')

    def test_add_file_edit(self):
        # used to fail: the edited entries were set as dicts on a read-only property
        bib = self.write('src', 'three.bib', content=entry('three2000'))
        def edit(entries):
            self.assertEqual([e.key for e in entries], ['three2000'])
            entries[0]['title'] = 'Edited'
            entries[0]['note'] = ''  # emptied in the editor: removed
            return entries
        with patch('papers.cli.entry_cmds.edit_entries', side_effect=edit):
            self.lib(f'add {bib} -e')
        self.assertEqual(self.keys(), ['one2000', 'three2000', 'two2000'])
        self.assertEqual(self.entry('three2000')['title'], 'Edited')
        self.assertNotIn('note', self.entry('three2000'))

    def test_add_file_edit_error(self):
        # used to return before saving: the added entry was lost
        bib = self.write('src', 'three.bib', content=entry('three2000'))
        with patch('papers.cli.entry_cmds.edit_entries', side_effect=OSError('no editor')), \
                self.assertLogs('papers', level='ERROR') as logs:
            self.lib(f'add {bib} -e')
        self.assertEqual(self.keys(), ['one2000', 'three2000', 'two2000'])  # added, unedited
        self.assertEqual(self.entry('three2000')['title'], 'Title of three2000')
        self.assertIn('no editor', '\n'.join(logs.output))

    def test_add_edit_without_file_several_entries(self):
        with patch('papers.cli.entry_cmds.edit_entries', side_effect=lambda entries: entries * 2):
            with self.assertRaisesRegex(PapersExit, 'one entry at a time'):
                self.lib('add -e --title T --key three2001')

    def test_editor_setting_wins_over_visual(self):
        self.lib(f'config editor {self.editor_script()}')
        self.bib(entry('one2000').replace('Title of one2000', 'Original'))
        with patch.dict(os.environ, {'VISUAL': 'false', 'EDITOR': 'false'}):
            self.lib('edit one2000')
        self.assertEqual(self.entry('one2000')['title'], 'Edited')

    def test_visual_without_editor_setting(self):
        self.bib(entry('one2000').replace('Title of one2000', 'Original'))
        with patch.dict(os.environ, {'VISUAL': self.editor_script(), 'EDITOR': 'false'}):
            self.lib('edit one2000')
        self.assertEqual(self.entry('one2000')['title'], 'Edited')

    def test_unknown_key(self):
        with patch('papers.cli.common.edit_in_editor') as edit:
            with self.assertRaises(PapersExit):
                self.lib('edit nope2000')
            edit.assert_not_called()

    def test_list_edit(self):
        def edit(entries):
            entries[0]['title'] = 'Edited'
            return entries
        with patch('papers.cli.common.edit_in_editor', side_effect=edit):
            self.lib('list --key one2000 -e')
        self.assertEqual(self.entry('one2000')['title'], 'Edited')


class TestEditFrom(EntryTest):
    "papers edit KEY --from FILE (#117)"

    def setUp(self):
        super().setUp()
        self.bib(tagged('one2000', 'kiwi', 'files/one.pdf'), entry('two2000'))

    def test_from_file(self):
        new = self.write('new.bib', content='@article{fetched_2000,\n author = {New One},\n'
                                             ' title = {New title},\n doi = {10.1/x}\n}\n')
        self.lib(f'edit one2000 --from {new}')
        e = self.entry('one2000')  # the key stays
        self.assertEqual(e['title'], 'New title')
        self.assertEqual(e['doi'], '10.1/x')
        self.assertNotIn('year', e)  # the other fields are those of FILE
        self.assertEqual(parse_keywords(e), ['kiwi'])  # kept: FILE has none
        self.assertIn('one.pdf', e['file'])
        self.assertEqual(self.keys(), ['one2000', 'two2000'])

    def test_from_file_with_file_and_keywords(self):
        new = self.write('new.bib', content='@article{x,\n title = {T},\n keywords = {ocean},\n'
                                             ' file = {:files/other.pdf:pdf}\n}\n')
        self.lib(f'edit one2000 --from {new}')
        e = self.entry('one2000')
        self.assertEqual(parse_keywords(e), ['ocean'])
        self.assertIn('other.pdf', e['file'])

    def test_from_file_links_relative_to_file(self):
        # as with papers add FILE: a relative link is relative to the directory of FILE
        new = self.write('down', 'new.bib', content='@article{x,\n title = {T},\n file = {:paper.pdf:pdf}\n}\n')
        self.lib(f'edit one2000 --from {new}')
        biblio = Biblio.load(self.path('lib', 'papers.bib'), '')
        self.assertEqual(biblio.get_files(self.entry('one2000')), [self.path('down', 'paper.pdf')])

    def test_from_stdin_pipe(self):
        with patch('sys.stdin', io.StringIO('@article{x,\n title = {Piped}\n}\n')), \
                patch('papers.utils.stdin_is_terminal', return_value=False):
            self.lib('edit one2000 --from -')
        self.assertEqual(self.entry('one2000')['title'], 'Piped')

    def test_from_stdin_paste(self):
        # in a terminal, the closing brace ends the input: the next lines are not read
        stdin = io.StringIO('@article{x,\n title = {Pasted {Title}}\n}\nnot read\n')
        with patch('sys.stdin', stdin), patch('papers.utils.stdin_is_terminal', return_value=True), \
                redirect_stdout(io.StringIO()):
            self.lib('edit one2000 --from -')
        self.assertEqual(self.entry('one2000')['title'], 'Pasted {Title}')
        self.assertEqual(stdin.read(), 'not read\n')

    def test_from_ris(self):
        import importlib.util
        if importlib.util.find_spec('rispy') is None:
            self.skipTest('rispy is not installed')
        new = self.write('new.ris', content='TY  - JOUR\nTI  - From RIS\nPY  - 2001\nER  - \n')
        self.lib(f'edit one2000 --from {new}')
        self.assertEqual(self.entry('one2000')['title'], 'From RIS')

    def test_two_entries(self):
        new = self.write('new.bib', content=entry('a') + entry('b'))
        with self.assertRaisesRegex(PapersExit, '2 entries'):
            self.lib(f'edit one2000 --from {new}')

    def test_one_key(self):
        new = self.write('new.bib', content=entry('a'))
        with self.assertRaisesRegex(PapersExit, 'one entry'):
            self.lib(f'edit one2000 two2000 --from {new}')

    def test_errors(self):
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()):
            self.lib('edit - --from -')
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()):
            self.lib('edit one2000 --format ris')
        with self.assertRaisesRegex(PapersExit, 'missing.bib'):
            self.lib('edit one2000 --from missing.bib')


class TestEditSet(EntryTest):
    "papers edit KEY... --set FIELD=VALUE --unset FIELD, --key NEW"

    def setUp(self):
        super().setUp()
        self.bib(tagged('one2000', 'kiwi', 'files/one.pdf'), entry('two2000'),
                 '@incollection{chap2000,\n crossref = {one2000},\n title = {A chapter}\n}\n')

    def porcelain(self, cmd):
        out = io.StringIO()
        with redirect_stdout(out), patch('sys.stderr', io.StringIO()):
            self.lib(cmd + ' --porcelain')
        return out.getvalue().splitlines()

    def test_set_unset(self):
        self.lib('edit one2000 two2000 --set journal="Earth System Dynamics" Year=2013')
        for key in ('one2000', 'two2000'):
            e = self.entry(key)
            self.assertEqual((e['journal'], e['year']), ('Earth System Dynamics', '2013'))
        self.lib('edit one2000 --unset journal keywords')
        e = self.entry('one2000')
        self.assertNotIn('journal', e)
        self.assertNotIn('keywords', e)
        self.assertIn('one.pdf', e['file'])

    def test_set_refused(self):
        for value in ('file=x.pdf', 'ID=x', 'id=x', 'key=x', 'KEY=x', 'bad.name=x'):
            with self.assertRaises(PapersExit):
                self.lib(f'edit one2000 --set {value}')
        with self.assertRaises(PapersExit):
            self.lib('edit one2000 --unset file')
        with self.assertRaises(SystemExit), patch('sys.stderr', io.StringIO()):
            self.lib('edit one2000 --set novalue')
        with self.assertRaises(SystemExit), patch('sys.stderr', io.StringIO()):
            self.lib('edit one2000 --set a=b --key x')
        self.assertIn('one.pdf', self.entry('one2000')['file'])

    def test_key(self):
        self.assertEqual(self.porcelain('edit one2000 --key perrette2013'),
                         ['renamed one2000 perrette2013', 'modified chap2000'])
        self.assertEqual(self.keys(), ['chap2000', 'perrette2013', 'two2000'])
        self.assertEqual(self.entry('chap2000')['crossref'], 'perrette2013')  # follows
        self.assertNotIn('ids', self.entry('perrette2013'))

    def test_key_case_only(self):
        # formats.md 7.2, bibtex.md 7.3: a change of case is a rename, crossref follows
        self.assertEqual(self.porcelain('edit one2000 --key One2000'), ['renamed one2000 One2000', 'modified chap2000'])
        self.assertEqual(self.keys(), ['One2000', 'chap2000', 'two2000'])
        self.assertEqual(self.entry('chap2000')['crossref'], 'One2000')

    def test_fix_key(self):
        # any change of key of an entry is a rename, papers check --fix-key too
        self.bib('@article{2000bad,\n author = {Smith, John},\n title = {Climate},\n year = {2000}\n}\n',
                 '@incollection{chap,\n crossref = {2000bad},\n title = {A chapter}\n}\n')
        self.assertEqual(self.porcelain('check --fix-key -y'), ['renamed 2000bad smith2000', 'modified chap'])
        self.assertEqual(self.entry('chap')['crossref'], 'smith2000')

    def test_keep_old_key(self):
        self.lib('edit one2000 --key perrette2013 --keep-old-key')
        self.assertEqual(self.entry('perrette2013')['ids'], 'one2000')
        self.lib('edit one2000 --set note=found')  # the old key still selects it
        self.assertEqual(self.entry('perrette2013')['note'], 'found')

    def test_keep_old_key_once(self):
        # back and forth: each former key once in ids, never the key itself
        self.lib('edit one2000 --key perrette2013 --keep-old-key')
        self.lib('edit perrette2013 --key one2000 --keep-old-key')
        self.assertEqual(self.entry('one2000')['ids'], 'perrette2013')
        self.lib('edit one2000 --key perrette2013 --keep-old-key')
        self.assertEqual(self.entry('perrette2013')['ids'], 'one2000')
        self.lib('edit perrette2013 --key one2000')  # without --keep-old-key
        self.assertNotIn('ids', self.entry('one2000'))
        self.lib('edit one2000 --key One2000 --keep-old-key')  # the same key, by case
        self.assertNotIn('ids', self.entry('One2000'))

    def test_key_refused(self):
        with self.assertRaisesRegex(PapersExit, 'another entry'):
            self.lib('edit one2000 --key two2000')
        with self.assertRaisesRegex(PapersExit, 'not a valid key'):
            self.lib('edit one2000 --key "a b"')
        with self.assertRaisesRegex(PapersExit, 'one entry'):
            self.lib('edit one2000 two2000 --key x')
        with self.assertRaises(SystemExit), patch('sys.stderr', io.StringIO()):
            self.lib('edit one2000 --keep-old-key')
        self.assertEqual(self.keys(), ['chap2000', 'one2000', 'two2000'])

    def test_empty_key_refused(self):
        # bibtex.md 7.2: --key '' is refused, it does not open the editor
        with patch.dict(os.environ, EDITOR='false'), self.assertRaisesRegex(PapersExit, 'not a valid key'):
            self.lib("edit one2000 --key ''")
        self.assertEqual(self.keys(), ['chap2000', 'one2000', 'two2000'])

