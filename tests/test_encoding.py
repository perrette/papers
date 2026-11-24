"""Unit tests for papers.encoding (78% -> higher coverage)"""
import unittest

from papers.encoding import standard_name
from papers.encoding import (
    family_names,
    parse_keywords,
    format_key,
)
from tests.common import BibTest


class TestStandardName(unittest.TestCase):

    def test_standard_name(self):
        self.assertEqual(standard_name("Smith, John"), "Smith, John")
        result = standard_name("Doe, Jane and Smith, John")
        self.assertIn("Doe", result)
        self.assertIn("Smith", result)


class TestFamilyNames(unittest.TestCase):

    def test_single_author(self):
        self.assertEqual(family_names("Smith, John"), ["Smith"])

    def test_multiple_authors(self):
        result = family_names("Perrette, M. and Yool, A.")
        self.assertEqual(result, ["Perrette", "Yool"])

    def test_standard_format(self):
        result = family_names("Doe, Jane and Smith, John")
        self.assertEqual(result, ["Doe", "Smith"])

    def test_braces_are_one_name(self):
        result = family_names("{Barnes and Noble} and {Smith, Jones}, J. and John Doe")
        self.assertEqual(result, ["{Barnes and Noble}", "{Smith, Jones}", "Doe"])


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