"""Unit tests for papers.encoding (78% -> higher coverage)"""
import unittest

from papers.bib import parse_file, format_file
from papers.encoding import (
    _outermost_bracket_groups,
    family_names,
    parse_keywords,
    format_key,
)
from tests.common import BibTest


class TestBibtexFileEntry(unittest.TestCase):

    def test_parse_file(self):
        file = parse_file('file.pdf:/path/to/file.pdf:pdf')
        self.assertEqual(file, ['/path/to/file.pdf'])
        file = parse_file(':/path/to/file.pdf:pdf')
        self.assertEqual(file, ['/path/to/file.pdf'])
        file = parse_file('/path/to/file.pdf:pdf')
        self.assertEqual(file, ['/path/to/file.pdf'])
        file = parse_file('/path/to/file.pdf')
        self.assertEqual(file, ['/path/to/file.pdf'])
        file = parse_file(':/path/to/file.pdf:')
        self.assertEqual(file, ['/path/to/file.pdf'])


    def test_parse_files(self):
        files = parse_file(':/path/to/file1.pdf:pdf;:/path/to/file2.pdf:pdf')
        self.assertEqual(files, ['/path/to/file1.pdf','/path/to/file2.pdf'])


    def test_format_file(self):
        field = format_file(['/path/to/file.pdf'])
        self.assertEqual(field, ':/path/to/file.pdf:pdf')


    def test_format_files(self):
        field = format_file(['/path/to/file1.pdf','/path/to/file2.pdf'])
        self.assertEqual(field, ':/path/to/file1.pdf:pdf;:/path/to/file2.pdf:pdf')


class TestOutermostBracketGroups(unittest.TestCase):
    """Test _outermost_bracket_groups (used for name parsing)"""

    def test_single_group(self):
        self.assertEqual(_outermost_bracket_groups('{my name}'), ['my name'])

    def test_multiple_groups(self):
        self.assertEqual(_outermost_bracket_groups('{my} {name}'), ['my', 'name'])

    def test_nested_braces(self):
        # The function extracts content between outermost braces; inner {} are included
        result = _outermost_bracket_groups("{my nam\\'{e}}")
        self.assertEqual(len(result), 1)
        self.assertIn("my nam", result[0])


class TestFamilyNames(unittest.TestCase):

    def test_single_author(self):
        self.assertEqual(family_names("Smith, John"), ["Smith"])

    def test_multiple_authors(self):
        result = family_names("Perrette, M. and Yool, A.")
        self.assertEqual(result, ["Perrette", "Yool"])

    def test_standard_format(self):
        result = family_names("Doe, Jane and Smith, John")
        self.assertEqual(result, ["Doe", "Smith"])


class TestParseKeywords(unittest.TestCase):

    def test_single_keyword(self):
        e = {"keywords": "ocean"}
        self.assertEqual(parse_keywords(e), ["ocean"])

    def test_multiple_keywords(self):
        e = {"keywords": "kiwi, ocean, climate"}
        self.assertEqual(parse_keywords(e), ["kiwi", "ocean", "climate"])

    def test_with_spaces(self):
        e = {"keywords": " sea-level ,  projections "}
        self.assertEqual(parse_keywords(e), ["sea-level", "projections"])

    def test_empty(self):
        e = {"keywords": ""}
        self.assertEqual(parse_keywords(e), [])


class TestFormatKey(unittest.TestCase):

    def test_format_key_with_file(self):
        e = {"ID": "Test2020", "file": ":/path/to/file.pdf:pdf"}
        result = format_key(e, no_key=False)
        self.assertIn("Test2020", result)

    def test_format_key_no_key(self):
        e = {"ID": "Test2020"}
        self.assertEqual(format_key(e, no_key=True), "")


class TestUnicode(BibTest):
    pass


class TestUnicodeVsLatexEncoding(BibTest):
    pass