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

    def test_strips_unbalanced_trailing_paren(self):
        # DOI wrapped in parens — closing ')' must not be slurped
        self.assertEqual(parse_doi('(doi:10.1007/s00382-010-0904-1)'), '10.1007/s00382-010-0904-1')
        # URL ending in ')'
        self.assertEqual(parse_doi('http://dx.doi.org/10.1007/s00382-010-0904-1)'),
                         '10.1007/s00382-010-0904-1')

    def test_preserves_balanced_parens(self):
        # DOIs may legitimately contain balanced parens — must survive intact
        doi = '10.1234/foo(bar)baz'
        self.assertEqual(parse_doi('doi:'+doi), doi)
        # Trailing ')' that is part of a balanced pair must be kept
        doi = '10.1234/foo(bar)'
        self.assertEqual(parse_doi('doi:'+doi), doi)


class TestIsvaliddoi(unittest.TestCase):

    def test_valid_doi(self):
        self.assertTrue(isvaliddoi('10.5194/bg-8-515-2011'))

    def test_invalid_returns_false(self):
        self.assertFalse(isvaliddoi('invalid'))
        self.assertFalse(isvaliddoi(''))

    def test_trailing_paren_invalid(self):
        # The DOI without the trailing paren is valid; with it, should be rejected
        self.assertTrue(isvaliddoi('10.1007/s00382-010-0904-1'))
        self.assertFalse(isvaliddoi('10.1007/s00382-010-0904-1)'))


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


class TestQueryText(unittest.TestCase):

    def test_too_short_raises_valueerror(self):
        # used to be an AssertionError, which callers do not handle
        from papers.extract import query_text
        with self.assertRaises(ValueError):
            query_text("one two")

    def test_enough_words(self):
        from papers.extract import query_text
        self.assertEqual(query_text("one two three"), "one two three")


class TestCollectPdfFiles(unittest.TestCase):

    def test_collect(self):
        import os, tempfile
        from pathlib import Path
        from papers.__main__ import _collect_pdf_files
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "a.pdf"), "w").write("x")
            open(os.path.join(d, "b.PDF"), "w").write("x")   # case-insensitive
            open(os.path.join(d, "notes.txt"), "w").write("x")
            sub = os.path.join(d, "sub")
            os.makedirs(sub)
            open(os.path.join(sub, "c.pdf"), "w").write("x")

            # plain files pass through, several at once
            self.assertEqual(_collect_pdf_files(["x.pdf", "y.pdf"]), ["x.pdf", "y.pdf"])

            # directories require recursive
            with self.assertRaises(ValueError):
                _collect_pdf_files([d])

            found = _collect_pdf_files([d], recursive=True)
            names = sorted(Path(f).name for f in found)
            self.assertEqual(names, ["a.pdf", "b.PDF", "c.pdf"])
