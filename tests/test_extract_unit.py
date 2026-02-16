"""Unit tests for papers.extract (42% -> higher coverage)"""
import unittest

from papers.extract import (
    parse_doi,
    isvaliddoi,
    DOIParsingError,
    _parse_doi_from_metadata_string,
    format_authors,
    map_crossref_to_bibtex_type,
    crossref_to_bibtex,
)


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


class TestParseDoiFromMetadataString(unittest.TestCase):

    def test_prism_doi(self):
        meta = '<prism:doi>10.5194/bg-8-515-2011</prism:doi>'
        self.assertEqual(_parse_doi_from_metadata_string(meta), '10.5194/bg-8-515-2011')

    def test_dc_identifier_doi(self):
        meta = '<dc:identifier>doi:10.1029/2020GL090987</dc:identifier>'
        self.assertEqual(_parse_doi_from_metadata_string(meta), '10.1029/2020GL090987')

    def test_pdfx_doi(self):
        meta = '<pdfx:doi>10.1000/xyz123</pdfx:doi>'
        self.assertEqual(_parse_doi_from_metadata_string(meta), '10.1000/xyz123')

    def test_crossmark_doi(self):
        meta = '<crossmark:DOI>10.1234/example</crossmark:DOI>'
        self.assertEqual(_parse_doi_from_metadata_string(meta), '10.1234/example')

    def test_no_match_returns_none(self):
        self.assertIsNone(_parse_doi_from_metadata_string('no doi here'))
        self.assertIsNone(_parse_doi_from_metadata_string(''))


class TestFormatAuthors(unittest.TestCase):

    def test_single_author(self):
        authors = [{"given": "John", "family": "Doe"}]
        self.assertEqual(format_authors(authors), "Doe, John")

    def test_multiple_authors(self):
        authors = [
            {"given": "Alice", "family": "Smith"},
            {"given": "Bob", "family": "Jones"},
        ]
        self.assertEqual(format_authors(authors), "Smith, Alice and Jones, Bob")

    def test_missing_given(self):
        authors = [{"family": "Einstein"}]
        self.assertEqual(format_authors(authors), "Einstein, ")

    def test_empty_list(self):
        self.assertEqual(format_authors([]), "")


class TestMapCrossrefToBibtexType(unittest.TestCase):

    def test_journal_article(self):
        self.assertEqual(map_crossref_to_bibtex_type("journal-article"), "article")

    def test_book(self):
        self.assertEqual(map_crossref_to_bibtex_type("book"), "book")

    def test_proceedings_article(self):
        self.assertEqual(map_crossref_to_bibtex_type("proceedings-article"), "inproceedings")

    def test_conference_paper(self):
        self.assertEqual(map_crossref_to_bibtex_type("conference-paper"), "inproceedings")

    def test_unknown_maps_to_misc(self):
        self.assertEqual(map_crossref_to_bibtex_type("unknown-type"), "misc")


class TestCrossrefToBibtex(unittest.TestCase):
    """Unit tests for crossref_to_bibtex with mock message dicts (no network)."""

    def test_minimal_message(self):
        msg = {
            "type": "journal-article",
            "title": ["Test Title"],
            "author": [{"given": "A.", "family": "Author"}],
            "DOI": "10.1234/test",
        }
        bib = crossref_to_bibtex(msg)
        self.assertIn("@article{", bib)
        self.assertIn("Test Title", bib)
        self.assertIn("Author, A.", bib)
        self.assertIn("10.1234/test", bib)

    def test_book_type(self):
        msg = {
            "type": "book",
            "title": ["A Book"],
            "author": [{"given": "B.", "family": "Writer"}],
            "DOI": "10.5678/book",
        }
        bib = crossref_to_bibtex(msg)
        self.assertIn("@book{", bib)
