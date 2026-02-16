"""Unit tests for papers.encoding (78% -> higher coverage)"""
import os
import tempfile
import unittest

from papers.encoding import update_file_path, standard_name, strip_outmost_brackets
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

    def test_parse_file_invalid_format_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_file('a:b:c:d')
        self.assertIn('unknown', str(ctx.exception))


    def test_format_file(self):
        field = format_file(['/path/to/file.pdf'])
        self.assertEqual(field, ':/path/to/file.pdf:pdf')


    def test_format_files(self):
        field = format_file(['/path/to/file1.pdf','/path/to/file2.pdf'])
        self.assertEqual(field, ':/path/to/file1.pdf:pdf;:/path/to/file2.pdf:pdf')

    def test_format_file_relative_to_root(self):
        """format_file with relative_to=os.sep uses abspath"""
        paths = [os.path.abspath('/tmp/file.pdf')]
        result = format_file(paths, relative_to=os.path.sep)
        self.assertIn('file.pdf', result)


class TestUpdateFilePath(unittest.TestCase):

    def test_update_file_path_changes_path(self):
        with tempfile.TemporaryDirectory() as base:
            sub1 = os.path.join(base, "dir1")
            sub2 = os.path.join(base, "dir2")
            os.makedirs(sub1)
            os.makedirs(sub2)
            pdf_path = os.path.join(sub1, "file.pdf")
            open(pdf_path, "wb").close()
            entry = {"ID": "test", "file": f":{pdf_path}:pdf"}
            result = update_file_path(entry, from_relative_to=sub1, to_relative_to=sub2)
            self.assertIsNotNone(result)
            old_file, new_file = result
            self.assertIn("file.pdf", new_file)

    def test_update_file_path_check_exists(self):
        with tempfile.TemporaryDirectory() as base:
            sub = os.path.join(base, "dir")
            os.makedirs(sub)
            pdf_path = os.path.join(sub, "file.pdf")
            open(pdf_path, "wb").close()
            entry = {"ID": "test", "file": f":{pdf_path}:pdf"}
            update_file_path(entry, from_relative_to=base, to_relative_to=base, check=True)
            self.assertIn("file", entry)


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


class TestStandardName(unittest.TestCase):

    def test_standard_name(self):
        self.assertEqual(standard_name("Smith, John"), "Smith, John")
        result = standard_name("Doe, Jane and Smith, John")
        self.assertIn("Doe", result)
        self.assertIn("Smith", result)


class TestStripOutmostBrackets(unittest.TestCase):

    def test_strips_single_bracket_group(self):
        self.assertEqual(strip_outmost_brackets("{Smith}"), "Smith")


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