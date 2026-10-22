"""The deprecated features of v3 that still work, with a deprecation
warning: the file actions of list, papers filecheck, the -m/--mode option
of add, the list options replaced by --duplicates --by, and the options and
commands renamed in v3 (-a of add, -f of list, -f/--force of check and
backup, --no-prompt/--force of install, restore-backup, doi). To remove with
them in v4 (the tests of papers install are in test_install.py)."""
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from papers.bib import Biblio
from papers.entries import get_entry_val
from papers.merge import DuplicateError
from tests.common import FileTest, LibraryTest, BibTest, entry, paperscmd, prepare_paper
from tests.test_duplicates import LIB, NEW, LIST


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
        with patch('papers.cli.entry_cmds.view_entry_files') as view:
            self.warns('list --key one2000 -o', 'papers open -')
        view.assert_called_once()

    def test_fetch(self):
        with patch('papers.bib.Biblio.fix_entry') as fix:
            self.warns('list --key one2000 --fetch',
                       'papers check --fetch --fetch-all --fix-doi --fix-key --format-name -')
        fix.assert_called_once()
        self.assertEqual(fix.call_args.kwargs, dict(fix_doi=True, fix_key=True, fetch_all=True, interactive=True))
        # the same as check with these options (format_name is True by default in fix_entry)
        with patch('papers.bib.Biblio.fix_entry') as fix2:
            self.lib('check one2000 --fetch --fetch-all --fix-doi --fix-key --format-name')
        kw = fix2.call_args.kwargs
        self.assertTrue(kw['fix_doi'] and kw['fix_key'] and kw['fetch_all'] and kw['format_name'] and kw['interactive'])
        self.assertFalse(kw['auto_key'] or kw['key_ascii'] or kw['encoding'])


class TestFilecheckAlias(FileTest):

    def setUp(self):
        super().setUp()
        self.a = self.write('src', 'a.pdf')
        self.bib(entry('one2000', self.a, 'files/broken.pdf'))

    def test_rename(self):
        with self.assertLogs('papers', level='WARNING') as logs:
            self.lib('filecheck --rename --copy')
        self.assertIn('papers file rename --keep-source', '\n'.join(logs.output))
        self.assertTrue(os.path.exists(self.a))
        self.assertEqual(len(self.libfiles()), 1)

    def test_delete_broken(self):
        with self.assertLogs('papers', level='WARNING') as logs:
            self.lib('filecheck --delete-broken --force')
        self.assertIn('papers file detach --broken', '\n'.join(logs.output))
        self.assertEqual(self.files('one2000'), [self.a])


class TestFileCheck(BibTest):

    def setUp(self):
        self.pdf, self.doi, self.key, self.newkey, self.year, self.bibtex, self.file_rename = prepare_paper()
        self.assertTrue(os.path.exists(self.pdf))
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workdir = self.temp_dir.name
        self.mybib = os.path.join(self.workdir, 'papers.bib')
        self.filesdir = os.path.join(self.workdir, 'files')
        open(self.mybib, 'w').write(self.bibtex)
        self.assertTrue(os.path.exists(self.mybib))

    def papers(self, cmd):
        return paperscmd(cmd, cwd=self.workdir)

    def test_filecheck_rename(self):
        paperscmd(f"""add --bibtex {self.mybib} --filesdir {self.filesdir} {self.pdf} --doi {self.doi} << EOF
u
EOF""", cwd=self.workdir)
        file_rename = os.path.join(self.filesdir, self.file_rename)
        self.assertFalse(os.path.exists(file_rename))
        self.assertTrue(os.path.exists(self.pdf))
        paperscmd(f'filecheck --bibtex {self.mybib} --filesdir {self.filesdir} --rename', cwd=self.workdir)
        self.assertTrue(os.path.exists(file_rename))
        self.assertFalse(os.path.exists(self.pdf))
        biblio = Biblio.load(self.mybib, '')
        e = next(ent for ent in biblio.entries if get_entry_val(ent, 'ID', '').lower() == self.key.lower())
        files = biblio.get_files(e)
        self.assertTrue(len(files) == 1)
        self.assertEqual(files[0], os.path.abspath(file_rename))

    def test_filecheck_delete_broken(self):
        """papers filecheck --delete-broken --force removes broken file links from entries"""
        os.makedirs(self.filesdir, exist_ok=True)
        self.papers(f'init --bibtex {self.mybib} --filesdir {self.filesdir}')
        # Add entry with valid file first
        self.papers(f'add {self.pdf} --doi {self.doi}')
        # Manually add a broken file link to the entry
        biblio = Biblio.load(self.mybib, self.filesdir)
        e = biblio.entries[0]
        real_file = biblio.get_files(e)[0]
        broken_path = os.path.join(os.path.dirname(real_file), 'nonexistent_file.pdf')
        biblio.set_files(e, [real_file, broken_path])
        biblio.save(self.mybib)
        self.assertEqual(len(biblio.get_files(e)), 2)
        self.papers('filecheck --delete-broken --force')
        biblio = Biblio.load(self.mybib, self.filesdir)
        e = biblio.entries[0]
        self.assertEqual(len(biblio.get_files(e)), 1)
        self.papers('uninstall')

    def test_filecheck_hash_check(self):
        """papers filecheck --hash-check removes duplicate files (same content) from entry"""
        os.makedirs(self.filesdir, exist_ok=True)
        pdf_copy = os.path.join(self.filesdir, 'duplicate.pdf')
        shutil.copy(self.pdf, pdf_copy)
        self.papers(f'init --bibtex {self.mybib} --filesdir {self.filesdir}')
        self.papers(f'add {self.pdf} --doi {self.doi}')
        biblio = Biblio.load(self.mybib, self.filesdir)
        e = biblio.entries[0]
        files = biblio.get_files(e)
        biblio.set_files(e, files + [pdf_copy])  # add same-content file again
        biblio.save(self.mybib)
        self.assertEqual(len(biblio.get_files(e)), 2)
        self.papers('filecheck --hash-check --force')
        biblio = Biblio.load(self.mybib, self.filesdir)
        e = biblio.entries[0]
        self.assertEqual(len(biblio.get_files(e)), 1)
        self.papers('uninstall')

    def test_filecheck_clean_filesdir(self):
        """papers filecheck --clean-filesdir --force removes unlinked files from filesdir"""
        os.makedirs(self.filesdir, exist_ok=True)
        self.papers(f'init --bibtex {self.mybib} --filesdir {self.filesdir}')
        self.papers(f'add {self.pdf} --doi {self.doi}')
        orphan = os.path.join(self.filesdir, 'orphan_unlinked.pdf')
        shutil.copy(self.pdf, orphan)
        self.assertTrue(os.path.exists(orphan))
        self.papers('filecheck --clean-filesdir --force')
        self.assertFalse(os.path.exists(orphan))
        self.papers('uninstall')

    def tearDown(self):
        self.temp_dir.cleanup()


class TestAddDeprecated(LibraryTest):

    lib = LIB

    def setUp(self):
        super().setUp()
        self.new = self.write('new.bib', NEW)

    def warns(self, cmd, text):
        with self.assertLogs('papers', level='WARNING') as logs:
            self.papers(cmd)
        self.assertIn(text, '\n'.join(logs.output))

    def test_mode_u(self):
        self.warns(f'add {self.new} -m u', '-m/--mode u is deprecated: use --on-duplicate keep')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature')

    def test_mode_U(self):
        self.warns(f'add {self.new} -m U', 'use --on-duplicate update')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature Climate Change')

    def test_mode_o(self):
        self.warns(f'add {self.new} -m o', 'use --on-duplicate update (the key and the fields only in the library')
        self.assertEqual(self.entry('smith2020climate')['keywords'], 'climate, mine')

    def test_mode_s(self):
        self.warns(f'add {self.new} -m s', 'use --on-duplicate skip')
        self.assertEqual(Path(self.bibtex).read_text(), LIB)

    def test_mode_r(self):
        with self.assertRaises(DuplicateError):
            self.papers(f'add {self.new} -m r')

    def test_mode_a(self):
        self.warns(f'add {self.new} -m a', 'use --no-check-duplicate')
        self.assertEqual(sorted(self.entries()), ['Smith_2020', 'smith2020climate'])

    def test_option_wins(self):
        self.warns(f'add {self.new} -m u --on-duplicate update', 'deprecated')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature Climate Change')

    def test_no_merge_files(self):
        self.warns(f'add {self.new} --no-merge-files --on-duplicate keep', '--no-merge-files is deprecated')
        self.assertIn('other/smith-preprint.pdf', self.entry('smith2020climate')['file'])


class TestListDuplicatesDeprecated(LibraryTest):

    lib = LIST

    def keys(self, cmd):
        return self.papers(cmd + ' -K').split()

    def test_deprecated(self):
        for option, by in (('--duplicates-doi', 'doi'), ('--duplicates-tit', 'title'), ('--duplicates-key', 'key')):
            with self.assertLogs('papers', level='WARNING') as logs:
                keys = self.keys(f'list {option}')
            self.assertIn(f'{option} is deprecated: use --duplicates --by {by}', '\n'.join(logs.output))
            self.assertEqual(keys, self.keys(f'list --duplicates --by {by}'))
        with self.assertLogs('papers', level='WARNING') as logs:
            self.assertEqual(len(self.keys('list --duplicates --similarity FAIR')), 4)
        self.assertIn('--similarity is deprecated and ignored', '\n'.join(logs.output))


class TestRenamedOptions(FileTest):
    """options and commands of v2 renamed in v3 (removed in v4): they warn
    with the new form and do the same"""

    def setUp(self):
        super().setUp()
        self.a = self.write('src', 'a.pdf')
        self.bib(entry('one2000', doi='10.1000/one'), entry('two2000'))

    def warns(self, cmd, new, **kw):
        with self.assertLogs('papers', level='WARNING') as logs:
            out = self.out(cmd, **kw)
        self.assertIn(new, '\n'.join(logs.output))
        return out

    def out(self, cmd, answers=()):
        with patch('builtins.input', side_effect=list(answers)):
            return super().out(cmd)

    def test_add_a(self):
        # -a is --attach in v3 (v2 meaning), --author in v4
        self.warns(f'add --key three2000 --title Three -a {self.a}', '-a is deprecated: use --attach')
        self.assertEqual(self.files('three2000'), [self.a])

    def test_list_f(self):
        out = self.warns('list --key one2000 -f doi --no-key', '-f is deprecated: use --field')
        self.assertEqual(out.split(), ['10.1000/one'])

    def test_check_force(self):
        for option in ('-f', '--force'):
            with patch('papers.bib.Biblio.fix_entry') as fix:
                self.warns(f'check one2000 {option}', f'{option} is deprecated: use -y/--yes')
            self.assertFalse(fix.call_args.kwargs['interactive'])

    def test_backup_force(self):
        with patch('papers.cli.backup_cmds.list_backup_dirs', return_value=[]):
            self.warns('backup remove x -f', '-f is deprecated: use -y/--yes')

    def test_install_no_prompt(self):
        for option in ('--no-prompt', '--force'):
            with patch('papers.cli.library_cmds.InputAsker', side_effect=AssertionError('no question expected')):
                self.warns(f'install {option} --no-git', f'{option} is deprecated: use -y/--yes')

    def test_restore_backup(self):
        with patch('papers.cli.backup_cmds.restore_from_backupdir') as restore:
            self.lib('config git true')
            self.warns('restore-backup', '`papers restore-backup` is deprecated: use `papers restore`')
        restore.assert_called_once()

    def test_doi(self):
        with patch('papers.cli.fetch_cmds.extract_pdf_doi', return_value='10.1000/x'):
            out = self.warns(f'doi {self.a}', '`papers doi` is deprecated: use `papers extract --doi-only`')
        self.assertEqual(out.strip(), '10.1000/x')

    def test_install_backup_files(self):
        os.makedirs(self.path('other'))
        with self.assertLogs('papers', level='WARNING') as logs:
            self.papers('install --backup-files -y', cwd=self.path('other'))
        self.assertIn('--backup-files is deprecated: use --git-lfs', '\n'.join(logs.output))
        self.assertTrue(self.json('other')['gitlfs'])

    def test_paths_options(self):
        self.warns('list --relative-paths', '--relative-paths is deprecated')
        self.warns('list --absolute-paths', '`papers config paths absolute`')
