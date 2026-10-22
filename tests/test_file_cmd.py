"""papers file: rename, mv, attach, detach, check, clean"""
import io
import json
import os
import subprocess as sp
from pathlib import Path
from unittest.mock import patch

from papers.utils import PapersExit

from tests.common import PAPERSCMD, FileTest, entry


class TestRename(FileTest):

    def setUp(self):
        super().setUp()
        self.a = self.write('src', 'a.pdf')
        self.b = self.write('src', 'b.pdf')
        self.bib(entry('one2000', self.a), entry('two2000', self.b))

    def test_all(self):
        self.lib('file rename')
        self.assertFalse(os.path.exists(self.a))
        self.assertFalse(os.path.exists(self.b))
        self.assertEqual(len(self.libfiles()), 2)
        self.assertTrue(self.files('one2000')[0].startswith(self.path('lib', 'files')))

    def test_keys(self):
        self.lib('file rename two2000')
        self.assertTrue(os.path.exists(self.a))
        self.assertFalse(os.path.exists(self.b))

    def test_keep_source(self):
        self.lib('file rename --keep-source one2000')
        self.assertTrue(os.path.exists(self.a))
        new, = self.files('one2000')
        self.assertEqual(os.stat(new).st_ino, os.stat(self.a).st_ino)

    def test_stdin(self):
        with patch('sys.stdin', io.StringIO('one2000\n')):
            self.lib('file rename -')
        self.assertFalse(os.path.exists(self.a))
        self.assertTrue(os.path.exists(self.b))

    def test_empty_stdin_renames_nothing(self):
        with patch('sys.stdin', io.StringIO('')):
            self.lib('file rename -')
        self.assertTrue(os.path.exists(self.a))
        self.assertTrue(os.path.exists(self.b))

    def test_pipe(self):
        sp.check_call(f'{PAPERSCMD} list -K --title "of two" | {PAPERSCMD} file rename -',
                      shell=True, cwd=self.path('lib'))
        self.assertTrue(os.path.exists(self.a))
        self.assertFalse(os.path.exists(self.b))

    def test_unknown_key(self):
        with self.assertRaises(PapersExit):
            self.lib('file rename one2000 nope2000')
        self.assertTrue(os.path.exists(self.a))

    def test_other_library_is_copied(self):
        os.makedirs(self.path('other'))
        self.papers('init --no-git', cwd=self.path('other'))
        c = self.write('other', 'files', 'c.pdf')
        self.bib(entry('three2000', c))
        self.lib('file rename')
        self.assertTrue(os.path.exists(c))
        self.assertEqual(len(self.libfiles()), 1)


class TestMv(FileTest):

    def setUp(self):
        super().setUp()
        self.a = self.write('lib', 'files', 'a.pdf')
        self.b = self.write('lib', 'files', 'sub', 'b.pdf')
        self.unlinked = self.write('lib', 'files', 'sub', 'notes.txt')
        self.bib(entry('one2000', 'files/a.pdf'), entry('two2000', 'files/sub/b.pdf'))

    def test_file(self):
        self.lib('file mv files/a.pdf files/c.pdf')
        self.assertFalse(os.path.exists(self.a))
        self.assertEqual(self.files('one2000'), [self.path('lib', 'files', 'c.pdf')])
        self.assertEqual(Path(self.path('lib', 'files', 'c.pdf')).read_text(), 'a.pdf')

    def test_into_folder(self):
        self.lib('file mv files/a.pdf files/sub')
        self.assertEqual(self.files('one2000'), [self.path('lib', 'files', 'sub', 'a.pdf')])

    def test_creates_parent_folder(self):
        self.lib('file mv files/a.pdf files/new/c.pdf')
        self.assertEqual(self.files('one2000'), [self.path('lib', 'files', 'new', 'c.pdf')])

    def test_rule1_unlinked_file(self):
        os.makedirs(self.path('lib', 'files', 'other'))
        with self.assertRaisesRegex(PapersExit, 'no entry links to this file'):
            self.lib('file mv files/a.pdf files/sub/notes.txt files/other')
        self.assertTrue(os.path.exists(self.a))
        self.assertTrue(os.path.exists(self.unlinked))

    def test_rule2_folder(self):
        self.lib('file mv files/sub files/moved')
        self.assertFalse(os.path.exists(self.path('lib', 'files', 'sub')))
        self.assertTrue(os.path.exists(self.path('lib', 'files', 'moved', 'notes.txt')))
        self.assertEqual(self.files('two2000'), [self.path('lib', 'files', 'moved', 'b.pdf')])
        self.assertEqual(self.files('one2000'), [self.a])

    def test_rule2_folder_without_linked_file(self):
        self.write('lib', 'files', 'empty', 'x.txt')
        with self.assertRaisesRegex(PapersExit, 'no entry links to a file in this folder'):
            self.lib('file mv files/empty files/moved')
        self.assertTrue(os.path.exists(self.path('lib', 'files', 'empty', 'x.txt')))

    def test_rule3_several_sources(self):
        with self.assertRaisesRegex(PapersExit, 'existing folder'):
            self.lib('file mv files/a.pdf files/sub/b.pdf files/new')
        self.assertTrue(os.path.exists(self.a))
        os.makedirs(self.path('lib', 'files', 'new'))
        self.lib('file mv files/a.pdf files/sub/b.pdf files/new')
        self.assertEqual(self.files('one2000'), [self.path('lib', 'files', 'new', 'a.pdf')])
        self.assertEqual(self.files('two2000'), [self.path('lib', 'files', 'new', 'b.pdf')])

    def test_rule4_existing_file(self):
        with self.assertRaisesRegex(PapersExit, 'destination exists'):
            self.lib('file mv files/a.pdf files/sub/notes.txt')
        self.assertTrue(os.path.exists(self.a))
        self.lib('file mv -f files/a.pdf files/sub/notes.txt')
        self.assertFalse(os.path.exists(self.a))
        self.assertEqual(Path(self.unlinked).read_text(), 'a.pdf')
        self.assertEqual(self.files('one2000'), [self.unlinked])

    def test_rule4_force_linked_destination_warns(self):
        with self.assertLogs('papers', level='WARNING') as logs:
            self.lib('file mv -f files/a.pdf files/sub/b.pdf')
        self.assertIn('-f replaces ' + self.b + ', which two2000 links to', '\n'.join(logs.output))
        self.assertEqual(Path(self.b).read_text(), 'a.pdf')

    def test_rule4_force_unlinked_destination_does_not_warn(self):
        with patch('papers.cli.file_cmds.logger.warning') as warning:
            self.lib('file mv -f files/a.pdf files/sub/notes.txt')
        warning.assert_not_called()

    def test_rule4_folder_onto_file(self):
        with self.assertRaisesRegex(PapersExit, 'exists as a file'):
            self.lib('file mv -f files/sub files/a.pdf')

    def test_rule5_dry_run(self):
        out = self.out('file mv -n files/sub files/moved')
        self.assertIn('mv ' + self.path('lib', 'files', 'sub'), out)
        self.assertIn('two2000: ' + self.b + ' -> ' + self.path('lib', 'files', 'moved', 'b.pdf'), out)
        self.assertTrue(os.path.exists(self.b))
        self.assertEqual(self.files('two2000'), [self.b])

    def test_rule6_files_directory(self):
        self.lib('file mv files library-files')
        self.assertEqual(json.load(open(self.path('lib', '.papersconfig.json')))['filesdir'], 'library-files')
        self.assertEqual(self.files('two2000'), [self.path('lib', 'library-files', 'sub', 'b.pdf')])
        self.assertEqual(self.lib('config filesdir', sp_cmd='check_output'), self.path('lib', 'library-files'))

    def test_bibtex_is_not_moved(self):
        with self.assertRaisesRegex(PapersExit, 'cannot be moved'):
            self.papers(f'-C lib file mv {self.path("lib")} {self.path("lib2")}')

    def test_into_itself(self):
        with self.assertRaisesRegex(PapersExit, 'inside itself'):
            self.lib('file mv files/sub files/sub/deeper')

    def test_failure_midway(self):
        import shutil
        real_move = shutil.move
        calls = []

        def move(src, dst):
            calls.append(src)
            if len(calls) == 2:
                raise OSError('disk full')
            return real_move(src, dst)
        os.makedirs(self.path('lib', 'files', 'new'))
        with patch('papers.files.shutil.move', side_effect=move):
            with self.assertRaisesRegex(PapersExit, 'disk full'):
                self.lib('file mv files/a.pdf files/sub/b.pdf files/new')
        self.assertEqual(self.files('one2000'), [self.path('lib', 'files', 'new', 'a.pdf')])
        self.assertEqual(self.files('two2000'), [self.b])

    def test_links_compared_by_real_path(self):
        os.symlink(self.path('lib', 'files'), self.path('lib', 'alias'))
        self.bib(entry('one2000', 'alias/a.pdf'), entry('two2000', 'files/sub/b.pdf'))
        self.lib('file mv files/a.pdf files/c.pdf')
        self.assertEqual(self.files('one2000'), [self.path('lib', 'files', 'c.pdf')])


class TestAttach(FileTest):

    def setUp(self):
        super().setUp()
        self.a = self.write('lib', 'files', 'own-name.pdf')
        self.si = self.write('src', 'si.pdf')
        self.bib(entry('one2000', 'files/own-name.pdf', doi='10.1000/one'))

    def test_move(self):
        self.lib('config files move')
        self.lib(f'file attach one2000 {self.si}')
        files = self.files('one2000')
        self.assertEqual(files[0], self.a)  # left as it was
        self.assertEqual(len(files), 2)
        self.assertTrue(files[1].startswith(self.path('lib', 'files')))
        self.assertFalse(os.path.exists(self.si))

    def test_link_and_doi(self):
        self.lib(f'file attach 10.1000/one {self.si}')  # files: link (tests)
        self.assertEqual(self.files('one2000'), [self.a, self.si])

    def test_copy_option(self):
        self.lib(f'file attach one2000 {self.si} --copy')
        self.assertTrue(os.path.exists(self.si))
        self.assertEqual(len(self.libfiles()), 2)

    def test_missing_file(self):
        with self.assertRaises(PapersExit):
            self.lib('file attach one2000 nothing.pdf')

    def test_unknown_key(self):
        with self.assertRaises(PapersExit):
            self.lib(f'file attach nope2000 {self.si}')


class TestDetach(FileTest):

    def setUp(self):
        super().setUp()
        self.a = self.write('lib', 'files', 'a.pdf')
        self.b = self.write('lib', 'files', 'b.pdf')
        self.shared = self.write('lib', 'files', 'shared.pdf')
        self.bib(entry('one2000', 'files/a.pdf', 'files/b.pdf', 'files/shared.pdf', 'files/broken.pdf'),
                 entry('two2000', 'files/shared.pdf', 'files/broken2.pdf', doi='10.1000/two'),
                 entry('three2000', 'files/shared.pdf'))

    def test_file(self):
        out = self.out('file detach files/b.pdf')
        self.assertNotIn(self.b, self.files('one2000'))
        self.assertIn(self.a, self.files('one2000'))
        self.assertTrue(os.path.exists(self.b))
        self.assertIn('one2000: removed the link to', out)

    def test_shared_file_every_entry(self):
        out = self.out('file detach files/shared.pdf')
        for key in ('one2000', 'two2000', 'three2000'):
            self.assertNotIn(self.shared, self.files(key))
            self.assertIn(f'{key}: removed the link', out)
        self.assertTrue(os.path.exists(self.shared))

    def test_file_key(self):
        self.lib('file detach files/shared.pdf --key 10.1000/two')
        self.assertIn(self.shared, self.files('one2000'))
        self.assertNotIn(self.shared, self.files('two2000'))

    def test_several_keys(self):
        self.lib('file detach files/shared.pdf --key one2000 two2000')
        self.assertNotIn(self.shared, self.files('one2000'))
        self.assertNotIn(self.shared, self.files('two2000'))
        self.assertIn(self.shared, self.files('three2000'))

    def test_repeated_key(self):
        self.lib('file detach files/shared.pdf -k one2000 --key three2000')
        self.assertNotIn(self.shared, self.files('one2000'))
        self.assertIn(self.shared, self.files('two2000'))
        self.assertNotIn(self.shared, self.files('three2000'))

    def test_key_stdin(self):
        with patch('sys.stdin', io.StringIO('two2000\nthree2000\n')):
            self.lib('file detach files/shared.pdf --key -')
        self.assertIn(self.shared, self.files('one2000'))
        self.assertNotIn(self.shared, self.files('two2000'))
        self.assertNotIn(self.shared, self.files('three2000'))

    def test_swallowed_file(self):
        before = open(self.path('lib', 'papers.bib')).read()
        with self.assertRaisesRegex(PapersExit, 'files/b.pdf is not an entry: put the files before --key'):
            self.lib('file detach --key one2000 files/b.pdf')
        self.assertEqual(open(self.path('lib', 'papers.bib')).read(), before)

    def test_key_all_links(self):
        self.lib('file detach --key one2000')
        self.assertEqual(self.files('one2000'), [])
        self.assertTrue(os.path.exists(self.a))

    def test_not_linked(self):
        self.write('lib', 'files', 'other.pdf')
        with self.assertRaisesRegex(PapersExit, 'no entry links to this file'):
            self.lib('file detach files/b.pdf files/other.pdf')
        self.assertIn(self.b, self.files('one2000'))

    def test_not_linked_from_key(self):
        with self.assertRaisesRegex(PapersExit, 'none of the entries of --key'):
            self.lib('file detach files/b.pdf --key two2000')
        self.assertIn(self.b, self.files('one2000'))

    def test_folder(self):
        with self.assertRaisesRegex(PapersExit, 'is a folder'):
            self.lib('file detach files')
        self.lib('file detach -r files --key one2000')
        self.assertEqual(self.files('one2000'), [])  # broken.pdf too: its path is in files/
        self.assertTrue(os.path.exists(self.a))

    def test_broken(self):
        self.lib('file detach --broken')
        self.assertEqual(len(self.files('one2000')), 3)
        self.assertEqual(self.files('two2000'), [self.shared])

    def test_broken_key(self):
        self.lib('file detach --broken --key two2000')
        self.assertEqual(len(self.files('one2000')), 4)
        self.assertEqual(len(self.files('two2000')), 1)

    def test_no_argument(self):
        with self.assertRaises(SystemExit):
            self.lib('file detach')


class TestFileRm(FileTest):

    def setUp(self):
        super().setUp()
        self.a = self.write('lib', 'files', 'a.pdf')
        self.b = self.write('lib', 'files', 'sub', 'b.pdf')
        self.notes = self.write('lib', 'files', 'sub', 'notes.txt')
        self.c = self.write('lib', 'files', 'sub2', 'deep', 'c.pdf')
        self.shared = self.write('lib', 'files', 'shared.pdf')
        self.outside = self.write('elsewhere', 'out.pdf')
        self.bib(entry('one2000', 'files/a.pdf', 'files/sub/b.pdf', 'files/shared.pdf', '../elsewhere/out.pdf'),
                 entry('two2000', 'files/shared.pdf', 'files/sub2/deep/c.pdf'))

    def test_file(self):
        out = self.out('file rm files/a.pdf ../elsewhere/out.pdf')
        self.assertFalse(os.path.exists(self.a))
        self.assertFalse(os.path.exists(self.outside))
        self.assertEqual(self.files('one2000'), [self.b, self.shared])
        self.assertIn('one2000: removed the link to', out)
        self.assertIn('delete', out)

    def test_shared_file(self):
        self.lib('file rm files/shared.pdf')
        self.assertFalse(os.path.exists(self.shared))
        self.assertNotIn(self.shared, self.files('one2000'))
        self.assertNotIn(self.shared, self.files('two2000'))

    def test_key_keeps_file_linked_elsewhere(self):
        out = self.out('file rm files/shared.pdf --key one2000')
        self.assertTrue(os.path.exists(self.shared))
        self.assertNotIn(self.shared, self.files('one2000'))
        self.assertIn(self.shared, self.files('two2000'))
        self.assertIn('another entry links to it', out)

    def test_several_keys(self):
        self.lib('file rm files/shared.pdf --key one2000 two2000')
        self.assertFalse(os.path.exists(self.shared))

    def test_swallowed_file(self):
        with self.assertRaisesRegex(PapersExit, 'is not an entry: put the files before --key'):
            self.lib('file rm --key one2000 files/a.pdf')
        self.assertTrue(os.path.exists(self.a))

    def test_unlinked_is_error(self):
        before = open(self.path('lib', 'papers.bib')).read()
        with self.assertRaisesRegex(PapersExit, 'no entry links to this file'):
            self.lib('file rm files/a.pdf files/sub/notes.txt')
        self.assertTrue(os.path.exists(self.a))
        self.assertEqual(open(self.path('lib', 'papers.bib')).read(), before)

    def test_folder_needs_r(self):
        with self.assertRaisesRegex(PapersExit, 'is a folder'):
            self.lib('file rm files/sub')
        self.assertTrue(os.path.exists(self.b))

    def test_recursive(self):
        self.lib('file rm -r files/sub files/sub2')
        self.assertFalse(os.path.exists(self.b))
        self.assertTrue(os.path.exists(self.notes))  # not linked: kept, as git rm -r
        self.assertTrue(os.path.isdir(self.path('lib', 'files', 'sub')))
        self.assertFalse(os.path.exists(self.path('lib', 'files', 'sub2')))  # left empty: removed
        self.assertEqual(self.files('two2000'), [self.shared])

    def test_recursive_keeps_filesdir(self):
        self.lib('file rm -r files')
        self.assertTrue(os.path.isdir(self.path('lib', 'files')))
        self.assertEqual(self.libfiles(), ['sub/notes.txt'])

    def test_dry_run(self):
        before = open(self.path('lib', 'papers.bib')).read()
        out = self.out('file rm -r files/sub2 --dry-run')
        self.assertTrue(os.path.exists(self.c))
        self.assertEqual(open(self.path('lib', 'papers.bib')).read(), before)
        self.assertIn('DRYRUN: delete', out)
        self.assertIn('DRYRUN: remove folder', out)

    def test_broken_link(self):
        self.bib(entry('one2000', 'files/a.pdf', 'files/gone.pdf'))
        self.lib('file rm files/gone.pdf')
        self.assertEqual(self.files('one2000'), [self.a])

class TestCheck(FileTest):

    def setUp(self):
        super().setUp()
        self.a = self.write('lib', 'files', 'a.pdf', content='same')
        self.b = self.write('lib', 'files', 'b.pdf', content='same')
        self.bib(entry('one2000', 'files/a.pdf', 'files/b.pdf', 'files/broken.pdf', doi='10.1000/one'),
                 entry('two2000', 'files/a.pdf', 'files/a.pdf'))

    def test_report(self):
        before = open(self.path('lib', 'papers.bib')).read()
        out = self.out('file check')
        self.assertIn('one2000: broken link', out)
        self.assertIn('one2000: identical files', out)
        self.assertIn('two2000: the same file is linked twice', out)
        self.assertEqual(open(self.path('lib', 'papers.bib')).read(), before)

    def test_keys(self):
        out = self.out('file check two2000')
        self.assertNotIn('one2000', out)

    def test_fix(self):
        self.lib('file check --fix')
        self.assertEqual(self.files('one2000'), [self.a, self.path('lib', 'files', 'broken.pdf')])
        self.assertEqual(self.files('two2000'), [self.a])
        self.assertTrue(os.path.exists(self.b))  # the file itself is kept

    def test_metadata(self):
        with patch('papers.files.extract_pdf_doi', return_value='10.1000/other') as extract:
            out = self.out('file check one2000 --metadata')
        self.assertTrue(extract.called)
        self.assertIn('10.1000/one <=> 10.1000/other', out)
        with patch('papers.files.extract_pdf_doi') as extract:
            self.out('file check one2000')
            extract.assert_not_called()


class TestClean(FileTest):

    def setUp(self):
        super().setUp()
        self.a = self.write('lib', 'files', 'a.pdf')
        self.linked = self.write('lib', 'files', '2000', 'linked.pdf')
        self.unlinked = self.write('lib', 'files', '2000', 'unlinked.pdf')
        self.hidden = self.write('lib', 'files', '.hidden', 'x.pdf')
        self.git = self.write('lib', 'files', '.git', 'objects')
        self.top = self.write('lib', 'files', 'top.pdf')
        self.bib(entry('one2000', 'files/a.pdf', 'files/2000/linked.pdf'))

    def test_subfolders(self):
        self.lib('file clean -y')
        self.assertFalse(os.path.exists(self.unlinked))
        self.assertFalse(os.path.exists(self.top))
        for f in [self.a, self.linked, self.hidden, self.git]:
            self.assertTrue(os.path.exists(f), f)

    def test_asks(self):
        with patch('builtins.input', return_value='n') as ask:
            self.lib('file clean')
        self.assertEqual(ask.call_count, 2)
        self.assertTrue(os.path.exists(self.unlinked))

    def test_dry_run(self):
        self.lib('file clean -y --dry-run')
        self.assertTrue(os.path.exists(self.unlinked))

    def test_old_layout_folder_is_counted(self):
        # used to print 2: the files of the removed folder were not counted
        folder = self.path('lib', 'files', 'old2000')
        self.write('lib', 'files', 'old2000', '.old2000.bib', content=entry('old2000'))
        self.write('lib', 'files', 'old2000', 'x.pdf')
        self.write('lib', 'files', 'old2000', 'y.pdf')
        out = self.out('file clean -y')
        self.assertFalse(os.path.exists(folder))
        self.assertIn('removed 4 unlinked file(s)', out)
