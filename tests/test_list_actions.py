"""The actions of papers list (--rename, --open, --attach...): the same
result as the command each one stands for, run on the listed entries."""
import os
import shutil
from pathlib import Path
from unittest.mock import patch

from papers.utils import PapersExit
from tests.common import FileTest, entry


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
