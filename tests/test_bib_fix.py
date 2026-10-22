"""Unit tests of papers.bib.Biblio: fix_entry (papers check), check_duplicates,
save, file paths and renaming (no network: the fetch functions are mocked)"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from papers.bib import Biblio, DuplicateKeyError, entry_diff
from papers.duplicate import Distinct
from papers.entries import parse_string
from papers.merge import DuplicateError


ENTRY = """@article{a2000,
 author = {Author, A.},
 doi = {10.1000/a},
 title = {One},
 year = {2000}
}"""

FETCHED = """@article{x,
 author = {Author, Anne},
 doi = {10.1000/a},
 journal = {Journal},
 title = {One},
 year = {2000}
}"""


def biblio_of(bibtex, **kw):
    biblio = Biblio(**kw)
    biblio.add_bibtex(bibtex)
    return biblio


class TestFixEntry(unittest.TestCase):

    def test_encoding_latex(self):
        # used to fail: iteration over an Entry, and unicode_to_latex is a table
        biblio = biblio_of('@article{k, author = {Müller, Jörg}, title = {Über}, year = {2000},\n'
                           ' doi = {10.1000/a_b}, file = {:files/m_x.pdf:pdf}}')
        e = biblio.entries[0]
        biblio.fix_entry(e, encoding='latex', format_name=False)
        self.assertEqual(e['author'], 'M{\\"u}ller, J{\\"o}rg')
        self.assertEqual(e['title'], '{\\"U}ber')
        self.assertEqual(e['doi'], '10.1000/a_b')  # identifiers and paths are not escaped
        self.assertNotIn('\\_', e['file'])

    def test_unknown_encoding(self):
        biblio = biblio_of(ENTRY)
        with self.assertRaises(AssertionError):
            biblio.fix_entry(biblio.entries[0], encoding='ascii')

    def test_fix_doi(self):
        biblio = biblio_of(ENTRY.replace('10.1000/a', 'https://doi.org/10.1000/a'))
        e = biblio.entries[0]
        biblio.fix_entry(e, fix_doi=True)
        self.assertEqual(e['doi'], '10.1000/a')

    def test_fetch_updates_and_adds_fields(self):
        biblio = biblio_of(ENTRY.replace('year', 'note = {mine},\n year'))
        e = biblio.entries[0]
        with mock.patch('papers.bib.fetch_bibtex_by_doi', return_value=FETCHED) as fetch:
            biblio.fix_entry(e, fetch=True)
        fetch.assert_called_once_with('10.1000/a')
        self.assertEqual((e['journal'], e['author'], e['note']), ('Journal', 'Author, Anne', 'mine'))
        self.assertEqual(e.key, 'a2000')

    def test_fetch_failure_keeps_entry(self):
        biblio = biblio_of(ENTRY)
        e = biblio.entries[0]
        with mock.patch('papers.bib.fetch_bibtex_by_doi', side_effect=ValueError('offline')):
            with self.assertLogs('papers', level='WARNING'):
                biblio.fix_entry(e, fetch=True)
        self.assertNotIn('journal', e)

    def test_fetch_up_to_date(self):
        biblio = biblio_of(FETCHED)
        e = biblio.entries[0]
        with mock.patch('papers.bib.fetch_bibtex_by_doi', return_value=FETCHED):
            biblio.fix_entry(e, fetch=True)
        self.assertEqual(e['journal'], 'Journal')

    def test_fetch_without_doi_does_nothing(self):
        biblio = biblio_of(ENTRY.replace(' doi = {10.1000/a},\n', ''))
        with mock.patch('papers.bib.fetch_bibtex_by_fulltext_crossref') as search:
            biblio.fix_entry(biblio.entries[0], fetch=True)
        search.assert_not_called()

    def test_fetch_all_searches_title_and_authors(self):
        biblio = biblio_of(ENTRY.replace(' doi = {10.1000/a},\n', ''))
        e = biblio.entries[0]
        with mock.patch('papers.bib.fetch_bibtex_by_fulltext_crossref', return_value=FETCHED) as search:
            biblio.fix_entry(e, fetch_all=True)
        search.assert_called_once_with('', title='One', author='Author')
        self.assertEqual(e['doi'], '10.1000/a')

    def test_fetch_all_failure(self):
        biblio = biblio_of(ENTRY.replace(' doi = {10.1000/a},\n', ''))
        with mock.patch('papers.bib.fetch_bibtex_by_fulltext_crossref', side_effect=ValueError('no results')):
            with self.assertLogs('papers', level='WARNING'):
                biblio.fix_entry(biblio.entries[0], fetch_all=True)

    def test_fix_key(self):
        biblio = biblio_of(ENTRY.replace('a2000', '10.1000/a'))
        e = biblio.entries[0]
        biblio.fix_entry(e, fix_key=True)
        self.assertEqual(e.key, 'author2000')

    def test_fix_key_keeps_valid_key(self):
        biblio = biblio_of(ENTRY)
        e = biblio.entries[0]
        biblio.fix_entry(e, fix_key=True)
        self.assertEqual(e.key, 'a2000')
        biblio.fix_entry(e, auto_key=True)
        self.assertEqual(e.key, 'author2000')

    def test_key_ascii(self):
        biblio = biblio_of(ENTRY.replace('a2000', 'müller2000'))
        e = biblio.entries[0]
        biblio.fix_entry(e, key_ascii=True)
        self.assertEqual(e.key, 'muller2000')

    def test_interactive_accept(self):
        biblio = biblio_of(ENTRY)
        e = biblio.entries[0]
        with mock.patch('builtins.input', return_value='y'), mock.patch('builtins.print'):
            biblio.fix_entry(e, auto_key=True, interactive=True)
        self.assertEqual(e.key, 'author2000')

    def test_interactive_decline_restores_entry(self):
        biblio = biblio_of(ENTRY)
        e = biblio.entries[0]
        with mock.patch('builtins.input', return_value='n'), mock.patch('builtins.print'), \
                mock.patch('papers.bib.fetch_bibtex_by_doi', return_value=FETCHED):
            biblio.fix_entry(e, fetch=True, auto_key=True, interactive=True)
        self.assertEqual(e.key, 'a2000')
        self.assertEqual(e['author'], 'Author, A.')
        self.assertNotIn('journal', e)  # added fields are removed again

    def test_entry_diff(self):
        old = parse_string(ENTRY).entries[0]
        new = parse_string(ENTRY.replace('One', 'Two')).entries[0]
        diff = entry_diff(old, new, color=False)
        self.assertIn('- ', diff)
        self.assertIn('Two', diff)
        self.assertIn('\033[', entry_diff(old, new))


class TestCheckDuplicates(unittest.TestCase):

    BIB = ENTRY + '\n\n' + ENTRY.replace('a2000', 'b2000').replace('year', 'journal = {J},\n year')

    def test_error(self):
        biblio = biblio_of(self.BIB)
        with self.assertRaises(DuplicateError) as cm:
            biblio.check_duplicates('error')
        self.assertIn('a2000', str(cm.exception))
        self.assertEqual(len(biblio.entries), 2)

    def test_skip(self):
        biblio = biblio_of(self.BIB)
        biblio.check_duplicates('skip')
        self.assertEqual(len(biblio.entries), 2)

    def test_update_is_not_available(self):
        with self.assertRaises(ValueError):
            biblio_of(self.BIB).check_duplicates('update')

    def test_exact_duplicates_are_merged(self):
        # b2000 has all the fields of a2000: no conflict, no question
        biblio = biblio_of(self.BIB)
        with mock.patch('builtins.print'):
            biblio.check_duplicates('keep')
        self.assertEqual([e.key for e in biblio.entries], ['b2000'])
        self.assertEqual(biblio.entries[0]['ids'], 'a2000')

    def test_no_error_without_duplicates(self):
        biblio = biblio_of(ENTRY)
        biblio.check_duplicates('error')
        self.assertEqual(len(biblio.entries), 1)


class TestBiblio(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_db_type(self):
        with self.assertRaises(TypeError):
            Biblio(db=[])

    def test_newbib_creates_directory(self):
        bibtex = os.path.join(self.dir, 'sub', 'papers.bib')
        biblio = Biblio.newbib(bibtex, '')
        self.assertTrue(os.path.exists(bibtex))
        self.assertEqual(biblio.entries, [])

    def test_entries_setter(self):
        biblio = biblio_of(ENTRY + '\n' + ENTRY.replace('a2000', 'b2000'))
        biblio.entries = [biblio.entries[1]]
        self.assertEqual([e.key for e in biblio.entries], ['b2000'])

    def test_save_keeps_a_backup_and_the_distinct_pairs(self):
        bibtex = os.path.join(self.dir, 'papers.bib')
        Path(bibtex).write_text(ENTRY)
        biblio = Biblio.load(bibtex, '')
        biblio.distinct = Distinct()  # not attached to a file yet
        a = biblio.entries[0]
        biblio.distinct.add(a, parse_string(ENTRY.replace('10.1000/a', '10.1000/b')).entries[0])
        biblio.save(bibtex)
        self.assertTrue(os.path.exists(os.path.join(self.dir, '.papers.bib.backup')))
        self.assertTrue(Distinct.for_bibtex(bibtex).pairs)

    def test_save_with_other_relative_root_warns(self):
        bibtex = os.path.join(self.dir, 'papers.bib')
        biblio = biblio_of(ENTRY, relative_to=os.path.join(self.dir, 'elsewhere'))
        with self.assertLogs('papers', level='WARNING'):
            biblio.save(bibtex)

    def test_update_file_path(self):
        biblio = biblio_of(ENTRY.replace('year', 'file = {:a/x.pdf:pdf},\n year'), relative_to='/root')
        biblio.update_file_path('/root/a')
        self.assertEqual(biblio.entries[0]['file'], ':x.pdf:pdf')
        self.assertEqual(biblio.relative_to, '/root/a')

    def test_rename_without_filesdir(self):
        biblio = biblio_of(ENTRY)
        with self.assertRaises(ValueError):
            biblio.rename_entry_files(biblio.entries[0])

    def test_rename_entries_files_logs_errors(self):
        biblio = biblio_of(ENTRY)
        with self.assertLogs('papers', level='ERROR'):
            biblio.rename_entries_files(relative_to='/x')
        self.assertEqual(biblio.relative_to, '/x')

    def test_rename_broken_link(self):
        biblio = biblio_of(ENTRY.replace('year', f'file = {{:{self.dir}/missing.pdf:pdf}},\n year'),
                           filesdir=os.path.join(self.dir, 'files'))
        with self.assertLogs('papers', level='WARNING'):
            biblio.rename_entry_files(biblio.entries[0])
        self.assertEqual(biblio.get_files(biblio.entries[0]), [os.path.join(self.dir, 'missing.pdf')])

    def test_same_key_other_paper(self):
        biblio = biblio_of(ENTRY)
        with self.assertRaises(DuplicateKeyError):
            biblio.add_bibtex(ENTRY.replace('One', 'Two').replace('10.1000/a', '10.1000/b'))
        biblio.add_bibtex(ENTRY.replace('One', 'Two').replace('10.1000/a', '10.1000/b'), update_key=True)
        self.assertEqual(sorted(e.key for e in biblio.entries), ['a2000', 'author2000'])

    def test_same_key_same_title_merges_files(self):
        biblio = biblio_of(ENTRY)
        biblio.add_bibtex(ENTRY.replace('year', 'file = {:/x.pdf:pdf},\n year'))
        self.assertEqual(len(biblio.entries), 1)
        self.assertEqual(biblio.get_files(biblio.entries[0]), ['/x.pdf'])


class TestScanDir(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_errors_are_logged_and_skipped(self):
        Path(self.dir, 'bad.pdf').write_text('not a pdf')
        Path(self.dir, 'one.bib').write_text(ENTRY)
        biblio = Biblio()
        with mock.patch('papers.bib.extract_pdf_metadata', side_effect=ValueError('no metadata')), \
                self.assertLogs('papers', level='WARNING') as logs:
            entries = biblio.scan_dir(self.dir)
        self.assertEqual([e.key for e in entries], ['a2000'])
        self.assertIn('no metadata', '\n'.join(logs.output))

    def test_duplicate_error_stops(self):
        Path(self.dir, 'one.bib').write_text(ENTRY.replace('One', 'One, revised'))
        biblio = biblio_of(ENTRY)
        with self.assertRaises(DuplicateError):
            biblio.scan_dir(self.dir, check_duplicate=True, on_duplicate='error')

    def test_hidden_bibtex_folder(self):
        folder = os.path.join(self.dir, 'old')
        os.makedirs(folder)
        Path(folder, '.old.bib').write_text(ENTRY)
        biblio = Biblio()
        entries = biblio.scan_dir(self.dir)
        self.assertEqual([e.key for e in entries], ['a2000'])

    def test_unreadable_hidden_bibtex(self):
        folder = os.path.join(self.dir, 'old')
        os.makedirs(folder)
        Path(folder, '.old.bib').write_text('')
        biblio = Biblio()
        with self.assertLogs('papers', level='WARNING'):
            self.assertEqual(biblio.scan_dir(self.dir), [])


class TestAddMore(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_pdf_url_is_downloaded_and_renamed(self):
        pdf = os.path.join(self.dir, 'dl.pdf')
        Path(pdf).write_text('pdf')
        biblio = Biblio(filesdir=os.path.join(self.dir, 'files'))
        with mock.patch('papers.bib.download_url', return_value=pdf) as download, \
                mock.patch('papers.bib.extract_pdf_metadata', return_value=FETCHED):
            entries = biblio.add_pdf('https://example.org/paper.pdf')
        download.assert_called_once_with('https://example.org/paper.pdf', expect_pdf=True)
        self.assertTrue(biblio.get_files(entries[0])[0].startswith(os.path.join(self.dir, 'files')))
        self.assertFalse(os.path.exists(pdf))

    def test_convert_to_unicode(self):
        biblio = Biblio()
        biblio.add_bibtex(ENTRY.replace('One', '{\\"U}ber'), convert_to_unicode=True)
        self.assertEqual(biblio.entries[0]['title'], 'Über')

    def test_attachments_of_a_bibtex(self):
        biblio = Biblio()
        biblio.add_bibtex(ENTRY, attachments=['si.pdf'])
        self.assertEqual(biblio.get_files(biblio.entries[0]), [os.path.abspath('si.pdf')])

    def test_attach_to_existing_copies(self):
        filesdir = os.path.join(self.dir, 'files')
        biblio = biblio_of(ENTRY, filesdir=filesdir)
        new = os.path.join(self.dir, 'new.pdf')
        Path(new).write_text('new')
        biblio.attach_to_existing(biblio.entries[0], [new], rename=True, copy=True)
        files = biblio.get_files(biblio.entries[0])
        self.assertTrue(files[0].startswith(filesdir))
        self.assertTrue(os.path.exists(new))  # copied
