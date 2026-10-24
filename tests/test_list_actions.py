"""The actions of papers list (--rename, --open, --attach, --detach,
--fix-files, --push, --export...): the same result as the command each one
stands for, run on the listed entries."""
import os
import re
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from papers.bib import Biblio
from papers.utils import PapersExit
from tests.common import FileTest, entry
from tests.test_pools import NEW_BIB, PoolTest


class TestListActions(FileTest):

    def setUp(self):
        super().setUp()
        # a second library, the same as lib/: one runs list, the other the command
        shutil.copytree(self.path('lib'), self.path('lib2'))
        for lib in ('lib', 'lib2'):
            a = self.write(lib + '-src', 'a.pdf')
            b = self.write(lib + '-src', 'b.pdf')
            Path(self.path(lib, 'papers.bib')).write_text(
                entry('one2000', a, doi='10.1000/one') + entry('two2000', b) + entry('three2001'))

    def lib2(self, cmd):
        return self.papers(cmd, cwd=self.path('lib2'))

    def state(self, lib):
        "the bibtex and the files of a library, with the library's name left out"
        bib = Path(self.path(lib, 'papers.bib')).read_text().replace(self.path(lib), 'LIB').replace(f'../{lib}-src', '../LIB-src')
        files = sorted(os.path.relpath(os.path.join(root, f), self.path(lib))
                       for root, _, fs in os.walk(self.path(lib, 'files')) for f in fs)
        sources = sorted(os.listdir(self.path(lib + '-src')))
        return bib, files, sources

    def assertSame(self, list_cmd, cmd):
        self.lib(list_cmd)
        self.lib2(cmd)
        self.assertEqual(self.state('lib'), self.state('lib2'))

    def test_rename(self):
        self.assertSame('list --year 2000 --rename', 'file rename one2000 two2000')
        self.assertEqual(self.state('lib')[2], [])
        self.assertEqual(len(self.libfiles()), 2)

    def test_rename_keep_source(self):
        self.assertSame('list --key one2000 --rename --keep-source', 'file rename one2000 --keep-source')
        self.assertEqual(self.state('lib')[2], ['a.pdf', 'b.pdf'])
        self.assertEqual(len(self.libfiles()), 1)

    def test_keep_source_needs_rename(self):
        with self.assertRaises(SystemExit):
            self.lib('list --key one2000 --keep-source')

    def test_attach(self):
        for lib in ('lib', 'lib2'):
            self.write(lib + '-src', 'si.pdf')
        self.lib(f"list --key three2001 --attach {self.path('lib-src', 'si.pdf')}")
        self.lib2(f"file attach three2001 {self.path('lib2-src', 'si.pdf')}")
        self.assertEqual(self.state('lib'), self.state('lib2'))
        self.assertEqual(len(self.files('three2001')), 1)

    def test_attach_needs_one_entry(self):
        si = self.write('lib-src', 'si.pdf')
        before = self.state('lib')
        for search in ['--key nothing', '--year 2000']:
            with self.assertRaisesRegex(PapersExit, 'only one entry.*nothing was changed'):
                self.lib(f'list {search} --attach {si}')
            self.assertEqual(self.state('lib'), before)

    def test_open(self):
        with patch('papers.cli.common.open_with_system') as opened:
            self.lib('list --year 2000 --open')
        with patch('papers.cli.common.open_with_system') as opened2:
            self.lib('open one2000 two2000')
        self.assertEqual(opened.call_count, 2)
        self.assertEqual([c.args for c in opened.call_args_list], [c.args for c in opened2.call_args_list])

    def test_open_short_option(self):
        with patch('papers.cli.common.open_with_system') as opened:
            self.lib('list --key one2000 -o')
        opened.assert_called_once_with(self.path('lib-src', 'a.pdf'))

    def test_one_action_at_a_time(self):
        before = self.state('lib')
        with self.assertRaises(SystemExit):
            self.lib('list --key one2000 --rename --open')
        with self.assertRaises(SystemExit):
            self.lib('list --key one2000 --delete --add-tag x')
        self.assertEqual(self.state('lib'), before)

    def test_no_deprecation_warning(self):
        with patch('papers.cli.entry_cmds.logger.warning') as warning:
            self.lib('list --key one2000 --rename')
        warning.assert_not_called()

    def test_one_backup_commit(self):
        self.lib('config git true')
        count = lambda: int(self.out('git rev-list --count HEAD').strip())
        before = count()
        self.lib('list --year 2000 --rename')
        self.assertEqual(count(), before + 1)
        self.assertNotIn('lib-src', Path(self.path('lib', 'papers.bib')).read_text())
        # one undo step: the links before the rename
        self.lib('undo')
        self.assertIn('lib-src', Path(self.path('lib', 'papers.bib')).read_text())


def _snapshot(root):
    "the files under root and their content (with the mtimes and times of the origin records left out)"
    state = {}
    for folder, _, files in os.walk(root):
        for f in files:
            path = os.path.join(folder, f)
            state[os.path.relpath(path, root)] = re.sub(rb'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[^},\s]*', b'TIME', re.sub(rb'\d{16,}', b'MTIME', Path(path).read_bytes()))
    return state


class SameResult:
    """assertSame(list_cmd, cmd): the list action and the command, each run
    from the same state of the temporary directory, leave the same files"""

    def assertSame(self, list_cmd, cmd, run=None):
        run = run or self.lib
        saved = tempfile.mkdtemp()
        try:
            shutil.copytree(self.dir, os.path.join(saved, 'dir'), symlinks=True)
            run(list_cmd)
            after_list = _snapshot(self.dir)
            shutil.rmtree(self.dir)
            shutil.copytree(os.path.join(saved, 'dir'), self.dir, symlinks=True)
            run(cmd)
            self.assertEqual(after_list, _snapshot(self.dir))
        finally:
            shutil.rmtree(saved)
        return after_list


class TestListFileActions(SameResult, FileTest):

    def setUp(self):
        super().setUp()
        self.a = self.write('src', 'a.pdf')
        self.b = self.write('src', 'b.pdf')
        self.bib(entry('one2000', self.a, self.b, doi='10.1000/one'), entry('two2000', self.path('gone.pdf')),
                 entry('three2000', self.path('src', 'three.pdf')))
        Path(self.path('lib', 'papers.bib')).write_text(
            Path(self.path('lib', 'papers.bib')).read_text().replace('Some One}', 'Some One},\n keywords = {x, y}', 1))

    def test_rm_tag(self):
        self.assertSame('list --key one2000 --rm-tag x', 'tag one2000 --rm x')
        self.assertEqual(self.entries_keywords(), 'y')

    def entries_keywords(self):
        biblio = Biblio.load(self.path('lib', 'papers.bib'), '')
        return next(e for e in biblio.entries if e.key == 'one2000')['keywords']

    def test_detach_all(self):
        self.assertSame('list --key one2000 --detach', 'file detach --key one2000')
        self.assertEqual(self.files('one2000'), [])

    def test_detach_files(self):
        self.assertSame(f'list --key one2000 --detach {self.a}', f'file detach {self.a} --key one2000')
        self.assertEqual(self.files('one2000'), [self.b])

    def test_detach_broken(self):
        self.assertSame('list --year 2000 --detach-broken', 'file detach --broken --key one2000 two2000 three2000')
        self.assertEqual(self.files('two2000'), [])
        self.assertEqual(len(self.files('one2000')), 2)

    def test_broken_is_broken_file(self):
        "--broken is short for the search option --broken-file, as before (--detach-broken detaches)"
        self.assertEqual(self.out('list --broken -K').split(), ['two2000', 'three2000'])

    def test_fix_files(self):
        self.write('found', 'gone.pdf')
        out = self.assertSame(f"list --broken-file --fix-files {self.path('found')}",
                              f"file fix two2000 three2000 --search {self.path('found')}")
        self.assertIn(os.path.join('found', 'gone.pdf'), out)  # copied, not moved
        self.assertEqual(len(self.files('two2000')), 1)

    def test_fix_files_move(self):
        self.write('found', 'gone.pdf')
        out = self.assertSame(f"list --key two2000 --fix-files {self.path('found')} --move",
                              f"file fix two2000 --search {self.path('found')} --move")
        self.assertNotIn(os.path.join('found', 'gone.pdf'), out)
        self.assertEqual(len(self.files('two2000')), 1)

    def test_export(self):
        out = self.assertSame(f"list --key one2000 --export {self.path('out')} --export-format bib,csl-json",
                              f"export {self.path('out')} one2000 --format bib,csl-json")
        self.assertIn(os.path.join('out', 'papers.json'), out)
        self.assertIn(os.path.join('out', 'papers.bib'), out)

    def test_export_files(self):
        out = self.assertSame(f"list --key one2000 --export {self.path('out')} --export-files none",
                              f"export {self.path('out')} one2000 --files none")
        self.assertNotIn(b'file', out[os.path.join('out', 'papers.bib')])

    def test_options_need_their_action(self):
        before = _snapshot(self.dir)
        for cmd in ['--move', '--pool ../x', '--on-duplicate keep', '--export-format ris',
                    '--detach a.pdf --detach-broken', '--detach --fix-files', '--push --pool a --pool b']:
            with self.subTest(cmd), self.assertRaises(SystemExit):
                self.lib(f'list --key one2000 {cmd}')
        self.assertEqual(_snapshot(self.dir), before)


class TestListExchangeActions(SameResult, PoolTest):

    def setUp(self):
        super().setUp()
        self.take_smith()
        Path(self.path('lib', 'papers.bib')).write_text(
            Path(self.path('lib', 'papers.bib')).read_text() + NEW_BIB.replace('file = {:mine.pdf:pdf},\n', ''))

    def test_push(self):
        self.assertSame('list --key mine2022 --push --pool ../pool', 'push mine2022 --pool ../pool')
        self.assertIn('mine2022', self.bib('pool')[1])

    def test_pull(self):
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        self.assertSame('list --key smith2020climate --pull --pool ../pool', 'pull smith2020climate --pool ../pool')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature')

    def test_sync(self):
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        self.assertSame('list --sync --pool ../pool', 'sync smith2020climate mine2022 --pool ../pool')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature')
        self.assertIn('mine2022', self.bib('pool')[1])

    def test_on_duplicate(self):
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        self.edit_lib('journal = {Nat.}', 'journal = {N.}')
        self.assertSame('list --key smith2020climate --pull --pool ../pool --on-duplicate keep',
                        'pull smith2020climate --pool ../pool --on-duplicate keep')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'N.')
