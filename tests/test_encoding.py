import unittest
from papers.bib import parse_file, format_file
from tests.common import BibTest


class TestBibtexFileEntry(unittest.TestCase):

    def test_parse_file(self):
        the_file = parse_file('file.pdf:/path/to/file.pdf:pdf')
        self.assertEqual(the_file, ['/path/to/file.pdf'])
        the_file = parse_file(':/path/to/file.pdf:pdf')
        self.assertEqual(the_file, ['/path/to/file.pdf'])
        the_file = parse_file('/path/to/file.pdf:pdf')
        self.assertEqual(the_file, ['/path/to/file.pdf'])
        the_file = parse_file('/path/to/file.pdf')
        self.assertEqual(the_file, ['/path/to/file.pdf'])
        the_file = parse_file(':/path/to/file.pdf:')
        self.assertEqual(the_file, ['/path/to/file.pdf'])
        del the_file


    def test_parse_files(self):
        files = parse_file(':/path/to/file1.pdf:pdf;:/path/to/file2.pdf:pdf')
        self.assertEqual(files, ['/path/to/file1.pdf','/path/to/file2.pdf'])
        del files


    def test_format_file(self):
        field = format_file(['/path/to/file.pdf'])
        self.assertEqual(field, ':/path/to/file.pdf:pdf')
        del field


    def test_format_files(self):
        field = format_file(['/path/to/file1.pdf','/path/to/file2.pdf'])
        self.assertEqual(field, ':/path/to/file1.pdf:pdf;:/path/to/file2.pdf:pdf')
        del field


class TestUnicode(BibTest):
    pass


class TestUnicodeVsLatexEncoding(BibTest):
    pass
