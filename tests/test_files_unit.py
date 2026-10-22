"""Unit tests of papers.files: downloads, files policy, entry folders,
moves, file checks and the cleaning of the files directory"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

import papers.config
from papers.bib import Biblio
from papers.entries import get_entry_val
from papers.files import (FilesPolicy, OtherLibraries, attach_files, check_entry_files, clean_filesdir,
                          download_url, entry_filecheck_metadata, execute_moves, fix_mendeley_path, is_inside,
                          plan_moves, read_entry_dir, rename_files, scan_dir_items)
from papers.utils import PapersExit


def entry(key, *files, doi=None):
    file = ';'.join(f':{f}:pdf' for f in files)
    return (f"@article{{{key},\n author = {{Some One}},\n" + (f" doi = {{{doi}}},\n" if doi else "")
            + (f" file = {{{file}}},\n" if files else "") + f" title = {{Title of {key}}},\n year = {{2000}}\n}}\n\n")


class TmpTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.realpath(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, *p, content=None):
        path = os.path.join(self.dir, *p)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Path(path).write_text(content or os.path.basename(path))
        return path

    def biblio(self, *entries, filesdir=None):
        biblio = Biblio(filesdir=filesdir)
        biblio.add_bibtex(''.join(entries))
        return biblio


class TestDownload(unittest.TestCase):

    def test_connection_error(self):
        with mock.patch('papers.files.requests.get', side_effect=requests.exceptions.ConnectionError('down')):
            with self.assertRaisesRegex(ValueError, 'ConnectionError'):
                download_url('https://example.org/a.pdf')

    def test_waf_challenge_hint(self):
        response = mock.Mock(status_code=202, headers={'content-type': 'text/html'}, content=b'')
        with mock.patch('papers.files.requests.get', return_value=response):
            with self.assertRaisesRegex(ValueError, 'CAPTCHA'):
                download_url('https://example.org/a.pdf', expect_pdf=True)


class TestPolicy(TmpTest):

    def test_is_inside(self):
        self.assertFalse(is_inside(self.dir, None))
        self.assertTrue(is_inside(os.path.join(self.dir, 'a'), self.dir))
        self.assertFalse(is_inside(self.dir + 'x', self.dir))

    def test_bad_mode(self):
        with self.assertRaises(ValueError):
            FilesPolicy('delete')

    def test_link_mode(self):
        self.assertEqual(FilesPolicy('link')(self.write('a.pdf')), 'link')

    def test_download_is_moved(self):
        d = tempfile.mkdtemp(prefix='papers_dl_')
        try:
            self.assertEqual(FilesPolicy('link')(os.path.join(d, 'a.pdf')), 'move')
        finally:
            os.rmdir(d)

    def test_unreadable_library_config(self):
        # a broken configuration of another library: the file is not its file
        self.write('other', '.papersconfig.json', content='{not json')
        pdf = self.write('other', 'files', 'a.pdf')
        self.assertIsNone(OtherLibraries().owner(pdf))
        self.assertEqual(FilesPolicy('move')(pdf), 'move')

    def test_configuration_in_dot_papers(self):
        self.write('other', '.papers', 'config.json', content='{"filesdir": "files", "bibtex": "papers.bib"}')
        pdf = self.write('other', 'files', 'a.pdf')
        owner = OtherLibraries().owner(pdf)
        self.assertIsNotNone(owner)


class TestEntryDir(TmpTest):

    def test_not_an_entry_dir(self):
        os.makedirs(os.path.join(self.dir, 'x'))
        with self.assertRaises(TypeError):
            read_entry_dir(os.path.join(self.dir, 'x'))

    def test_files_of_the_folder(self):
        self.write('x', '.x.bib', content=entry('x2000'))
        pdf = self.write('x', 'x.pdf')
        e = read_entry_dir(os.path.join(self.dir, 'x'), relative_to=os.path.sep)
        self.assertEqual(get_entry_val(e, 'file'), f':{pdf}:pdf')

    def test_without_update_files(self):
        # used to fail on an undefined variable
        self.write('x', '.x.bib', content=entry('x2000', 'old.pdf'))
        self.write('x', 'x.pdf')
        e = read_entry_dir(os.path.join(self.dir, 'x'), update_files=False)
        self.assertEqual(get_entry_val(e, 'file'), ':old.pdf:pdf')

    def test_scan_skips_files_linked_from_a_bibtex(self):
        pdf = self.write('a.pdf')
        self.write('lib.bib', content=entry('a2000', 'a.pdf'))
        other = self.write('b.pdf')
        with self.assertLogs('papers', level='INFO') as logs:
            items = scan_dir_items(self.dir)
        self.assertEqual([path for _, path, _ in items], [os.path.join(self.dir, 'lib.bib'), other])
        self.assertIn(f'{pdf}: linked from a scanned bibtex file', '\n'.join(logs.output))


class TestRenameAttach(TmpTest):

    def config(self, filesdir):
        config = papers.config.Config(filesdir=filesdir)
        return config

    def test_rename_without_filesdir(self):
        with self.assertRaisesRegex(PapersExit, 'no files directory'):
            rename_files(self.biblio(entry('a2000')), [], self.config(None))

    def test_rename_error_is_logged(self):
        biblio = self.biblio(entry('a2000', self.write('a.pdf')), filesdir=os.path.join(self.dir, 'files'))
        with mock.patch.object(biblio, 'rename_entry_files', side_effect=OSError('disk full')), \
                self.assertLogs('papers', level='ERROR') as logs:
            rename_files(biblio, biblio.entries, self.config(os.path.join(self.dir, 'files')))
        self.assertIn('a2000: disk full', '\n'.join(logs.output))

    def test_attach_missing_file(self):
        biblio = self.biblio(entry('a2000'))
        with self.assertRaisesRegex(PapersExit, 'does not exist'):
            attach_files(biblio, biblio.entries[0], [os.path.join(self.dir, 'missing.pdf')], self.config(None), 'link')

    def test_attach_url_is_downloaded_and_moved(self):
        filesdir = os.path.join(self.dir, 'files')
        biblio = self.biblio(entry('a2000'), filesdir=filesdir)
        d = tempfile.mkdtemp(prefix='papers_dl_')
        Path(d, 'si.pdf').write_text('si')
        with mock.patch('papers.files.download_url', return_value=os.path.join(d, 'si.pdf')):
            attach_files(biblio, biblio.entries[0], ['https://example.org/si.pdf'], self.config(filesdir), 'link')
        files = biblio.get_files(biblio.entries[0])
        self.assertEqual(len(files), 1)
        self.assertTrue(is_inside(files[0], filesdir))
        self.assertFalse(os.path.exists(os.path.join(d, 'si.pdf')))
        os.rmdir(d)


class TestPlanMoves(TmpTest):

    def setUp(self):
        super().setUp()
        self.a = self.write('a', 'a.pdf')
        self.b = self.write('b', 'b.pdf')
        self.biblio_ = self.biblio(entry('a2000', self.a), entry('b2000', self.b))

    def errors(self, sources, dest, **kw):
        with self.assertRaises(PapersExit) as cm:
            plan_moves(self.biblio_, sources, dest, **kw)
        return str(cm.exception)

    def test_missing_source(self):
        self.assertIn('does not exist', self.errors([os.path.join(self.dir, 'none.pdf')], self.dir))

    def test_folder_inside_itself(self):
        self.assertIn('inside itself', self.errors([os.path.join(self.dir, 'a')], os.path.join(self.dir, 'a', 'sub')))

    def test_folder_onto_folder(self):
        os.makedirs(os.path.join(self.dir, 'c', 'a'))
        self.assertIn('destination exists', self.errors([os.path.join(self.dir, 'a')], os.path.join(self.dir, 'c')))

    def test_same_source_and_destination(self):
        self.assertIn('the same', self.errors([self.a], self.a))

    def test_given_twice(self):
        os.makedirs(os.path.join(self.dir, 'c'))
        self.assertIn('given twice', self.errors([self.a, self.a], os.path.join(self.dir, 'c')))

    def test_inside_another_source(self):
        os.makedirs(os.path.join(self.dir, 'c'))
        self.assertIn('inside another source', self.errors([os.path.join(self.dir, 'a'), self.a],
                                                           os.path.join(self.dir, 'c')))

    def test_protected(self):
        bib = self.write('a', 'papers.bib')
        self.assertIn('cannot be moved', self.errors([os.path.join(self.dir, 'a')], os.path.join(self.dir, 'c'),
                                                     protected=[bib]))

    def test_execute_force_replaces_and_stops_on_error(self):
        target = self.write('c', 'b.pdf', content='old')
        moves = plan_moves(self.biblio_, [self.b], target, force=True)
        done, error = execute_moves(moves, force=True)
        self.assertIsNone(error)
        self.assertEqual(Path(target).read_text(), 'b.pdf')
        moves = plan_moves(self.biblio_, [self.a], os.path.join(self.dir, 'd.pdf'))
        with mock.patch('papers.files.shutil.move', side_effect=OSError('read-only')):
            done, error = execute_moves(moves)
        self.assertEqual(done, [])
        self.assertIsInstance(error, OSError)


class TestCheckFiles(TmpTest):

    def test_metadata_doi(self):
        biblio = self.biblio(entry('a2000', doi='10.1000/a'))
        e = biblio.entries[0]
        with mock.patch('papers.files.extract_pdf_doi', return_value='10.1000/A'):
            entry_filecheck_metadata(e, 'a.pdf')  # same DOI, other case
        with mock.patch('papers.files.extract_pdf_doi', return_value='10.1000/b'):
            with self.assertRaisesRegex(ValueError, 'entry <=> pdf'):
                entry_filecheck_metadata(e, 'a.pdf')
        with mock.patch('papers.files.extract_pdf_doi', return_value='not a doi'):
            with self.assertRaisesRegex(ValueError, 'invalid parsed doi'):
                entry_filecheck_metadata(e, 'a.pdf')
        with mock.patch('papers.files.extract_pdf_doi', side_effect=OSError):
            with self.assertRaisesRegex(ValueError, 'failed to parse doi'):
                entry_filecheck_metadata(e, 'a.pdf')

    def test_metadata_without_doi(self):
        e = self.biblio(entry('a2000')).entries[0]
        with self.assertRaisesRegex(ValueError, 'no doi'):
            entry_filecheck_metadata(e, 'a.pdf')

    def test_fix_mendeley_path(self):
        pdf = self.write('home', 'a_b.pdf')
        broken = pdf[1:].replace('a_b', 'a{\\_}b')  # no leading /, latex underscore
        self.assertEqual(fix_mendeley_path(broken), pdf)
        self.assertEqual(fix_mendeley_path('a.pdf'), 'a.pdf')  # no directory: unchanged

    def test_fix_mendeley_path_bad_latex(self):
        with mock.patch('papers.files.latex_to_unicode', side_effect=KeyError('x')), \
                self.assertLogs('papers', level='WARNING'):
            self.assertEqual(fix_mendeley_path('/a/b.pdf'), '/a/b.pdf')

    def test_repair_and_identical_files(self):
        # a link saved by Mendeley without its leading /: relative to the bibtex directory, it is broken
        pdf = self.write('home', 'a.pdf', content='same')
        copy = self.write('copy.pdf', content='same')
        bibtex = self.write('lib', 'papers.bib', content=entry('a2000', pdf[1:], copy))
        biblio = Biblio.load(bibtex, '')
        e = biblio.entries[0]
        self.assertFalse(os.path.exists(biblio.get_files(e)[0]))
        issues = check_entry_files(biblio, e, fix=True)
        self.assertEqual(len(issues), 2, issues)
        self.assertIn('path can be repaired', issues[0])
        self.assertIn('identical files', issues[1])
        self.assertEqual(biblio.get_files(e), [pdf])

    def test_metadata_issue_is_reported(self):
        pdf = self.write('a.pdf')
        biblio = self.biblio(entry('a2000', pdf, doi='10.1000/a'))
        with mock.patch('papers.files.extract_pdf_doi', return_value='10.1000/b'):
            issues = check_entry_files(biblio, biblio.entries[0], metadata=True)
        self.assertIn('entry <=> pdf', issues[0])


class TestClean(TmpTest):

    def setUp(self):
        super().setUp()
        self.filesdir = os.path.join(self.dir, 'files')
        self.linked = self.write('files', 'linked.pdf')
        self.biblio_ = self.biblio(entry('a2000', self.linked), filesdir=self.filesdir)

    def test_no_filesdir(self):
        with self.assertRaises(ValueError):
            clean_filesdir(self.biblio(entry('a2000')))

    def test_not_interactive(self):
        unlinked = self.write('files', 'sub', 'unlinked.pdf')
        self.write('files', 'old', '.old.bib', content=entry('old2000'))
        old = self.write('files', 'old', 'old.pdf')
        removed = clean_filesdir(self.biblio_, interactive=False)
        self.assertEqual(sorted(removed), [old, unlinked])  # the files of the folder, without .old.bib
        self.assertFalse(os.path.exists(os.path.join(self.filesdir, 'old')))  # old-layout folder
        self.assertTrue(os.path.exists(self.linked))

    def test_yes_to_all_in_folder(self):
        a = self.write('files', 'a.pdf')
        b = self.write('files', 'b.pdf')
        with mock.patch('builtins.input', return_value='Y') as ask:
            removed = clean_filesdir(self.biblio_)
        self.assertEqual(removed, [a, b])
        self.assertEqual(ask.call_count, 1)

    def test_ignored(self):
        self.write('files', 'keep', 'x.pdf')
        y = self.write('files', 'y.pdf')
        removed = clean_filesdir(self.biblio_, interactive=False, ignore_files=[y], ignore_folders=['keep'])
        self.assertEqual(removed, [])

    def test_ignored_folder_by_path(self):
        self.write('files', 'keep', 'x.pdf')
        removed = clean_filesdir(self.biblio_, interactive=False,
                                 ignore_folders=[os.path.join(self.filesdir, 'keep')])
        self.assertEqual(removed, [])

    def test_old_folder_asks(self):
        self.write('files', 'old', '.old.bib', content=entry('old2000'))
        with mock.patch('builtins.input', return_value='n'):
            clean_filesdir(self.biblio_)
        self.assertTrue(os.path.exists(os.path.join(self.filesdir, 'old')))
        with mock.patch('builtins.input', return_value='y'):
            clean_filesdir(self.biblio_)
        self.assertFalse(os.path.exists(os.path.join(self.filesdir, 'old')))

    def test_dry_run(self):
        a = self.write('files', 'a.pdf')
        papers.config.DRYRUN = True
        try:
            with mock.patch('builtins.print'):
                clean_filesdir(self.biblio_, interactive=False)
        finally:
            papers.config.DRYRUN = False
        self.assertTrue(os.path.exists(a))
