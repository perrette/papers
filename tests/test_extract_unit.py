"""Unit tests for papers.extract (42% -> higher coverage)"""
import unittest

from papers.extract import parse_doi, isvaliddoi, DOIParsingError


class TestParseDoi(unittest.TestCase):

    def test_standard_doi(self):
        self.assertEqual(parse_doi('doi:10.5194/bg-8-515-2011'), '10.5194/bg-8-515-2011')

    def test_strips_doi_prefix(self):
        self.assertEqual(parse_doi('DOI:10.5194/test-2020'), '10.5194/test-2020')

    def test_normalizes_case(self):
        result = parse_doi('doi:10.5194/ESD-4-11-2013')
        self.assertEqual(result, '10.5194/esd-4-11-2013')

    def test_invalid_raises(self):
        with self.assertRaises(DOIParsingError):
            parse_doi('not a doi')

    def test_arxiv_conversion(self):
        result = parse_doi('arxiv:1234.5678')
        self.assertIn('10.48550', result)
        self.assertIn('1234.5678', result)


class TestIsvaliddoi(unittest.TestCase):

    def test_valid_doi(self):
        self.assertTrue(isvaliddoi('10.5194/bg-8-515-2011'))

    def test_invalid_returns_false(self):
        self.assertFalse(isvaliddoi('invalid'))
        self.assertFalse(isvaliddoi(''))
