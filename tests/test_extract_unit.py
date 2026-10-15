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


# first page of a Copernicus preprint as extracted by pymupdf: the stamped
# header (with the article DOI) comes after the manuscript text, which cites a
# data DOI in the abstract
ESSD_TEXT = """A gridded dataset of something important
Author One, Author Two
Abstract. We present a dataset of something important. The data are available
at https://doi.org/10.5281/zenodo.15385035 (One and Two, 2025).
1 Introduction
Something important has been measured for a long time.
https://doi.org/10.5194/essd-2025-300
Preprint. Discussion started: 10 July 2025
"""


class TestParseDoiCandidates(unittest.TestCase):

    def test_prefers_article_doi_over_data_repository(self):
        self.assertEqual(parse_doi(ESSD_TEXT), '10.5194/essd-2025-300')

    def test_candidates_ordered(self):
        from papers.extract import parse_dois
        self.assertEqual(parse_dois(ESSD_TEXT), ['10.5194/essd-2025-300', '10.5281/zenodo.15385035'])

    def test_data_repository_doi_alone_is_kept(self):
        txt = 'Data: https://doi.org/10.5281/zenodo.15385035 and nothing else'
        self.assertEqual(parse_doi(txt), '10.5281/zenodo.15385035')

    def test_url_context_preference_ignores_data_repository(self):
        # the article DOI is not in a URL, the data DOI is
        txt = 'doi:10.5194/essd-2025-300\nData: https://doi.org/10.5281/zenodo.15385035'
        self.assertEqual(parse_doi(txt), '10.5194/essd-2025-300')


class TestExtractTxtMetadataCandidates(unittest.TestCase):
    """metadata lookup over several DOI candidates (crossref is mocked)"""

    def _bibtex(self, doi, title, author='One, Author and Two, Author'):
        return f"@article{{{doi},\n author = {{{author}}},\n doi = {{{doi}}},\n title = {{{title}}},\n year = {{2025}}\n}}"

    def test_article_doi_fetched_first(self):
        from unittest import mock
        from papers.extract import extract_txt_metadata
        fetch = mock.Mock(return_value=self._bibtex('10.5194/essd-2025-300', 'A gridded dataset of something important'))
        with mock.patch('papers.extract.fetch_bibtex_by_doi', fetch):
            bibtex = extract_txt_metadata(ESSD_TEXT, search_doi=True, search_fulltext=False)
        self.assertIn('A gridded dataset of something important', bibtex)
        fetch.assert_called_once_with('10.5194/essd-2025-300')

    def test_next_candidate_on_request_error(self):
        from unittest import mock
        from papers.extract import extract_txt_metadata, DOIRequestError
        txt = 'see https://doi.org/10.1234/not-registered and https://doi.org/10.5678/registered-paper\nThe registered paper'
        def fetch(doi):
            if doi == '10.1234/not-registered':
                raise DOIRequestError(doi)
            return self._bibtex(doi, 'The registered paper')
        with mock.patch('papers.extract.fetch_bibtex_by_doi', side_effect=fetch):
            with self.assertLogs('papers', level='WARNING'):
                bibtex = extract_txt_metadata(txt, search_doi=True, search_fulltext=False)
        self.assertIn('10.5678/registered-paper', bibtex)

    def test_prefers_candidate_whose_title_is_in_text(self):
        from unittest import mock
        from papers.extract import extract_txt_metadata
        txt = 'Building on earlier work (doi:10.1000/earlier-work), we present\nThe Actual Paper Title\nhttps://doi.org/10.1000/actual-paper'
        titles = {'10.1000/earlier-work': 'Some Earlier Work', '10.1000/actual-paper': 'The Actual Paper Title'}
        with mock.patch('papers.extract.fetch_bibtex_by_doi', side_effect=lambda doi: self._bibtex(doi, titles[doi])):
            bibtex = extract_txt_metadata(txt, search_doi=True, search_fulltext=False)
        self.assertIn('10.1000/actual-paper', bibtex)
        self.assertNotIn('earlier-work', bibtex)

    def test_metadata_without_title_or_author_is_skipped(self):
        from unittest import mock
        from papers.extract import extract_txt_metadata
        txt = 'https://doi.org/10.1000/empty-record then https://doi.org/10.1000/complete-record\nComplete Record Title'
        def fetch(doi):
            if doi == '10.1000/empty-record':
                return f"@misc{{{doi},\n doi = {{{doi}}}\n}}"
            return self._bibtex(doi, 'Complete Record Title')
        with mock.patch('papers.extract.fetch_bibtex_by_doi', side_effect=fetch):
            with self.assertLogs('papers', level='WARNING'):
                bibtex = extract_txt_metadata(txt, search_doi=True, search_fulltext=False)
        self.assertIn('10.1000/complete-record', bibtex)

    def test_stub_only_as_last_resort_with_warning(self):
        from unittest import mock
        from papers.extract import extract_txt_metadata, DOIRequestError
        with mock.patch('papers.extract.fetch_bibtex_by_doi', side_effect=DOIRequestError('nope')):
            with self.assertLogs('papers', level='WARNING'):
                bibtex = extract_txt_metadata(ESSD_TEXT, search_doi=True, search_fulltext=False)
        # the stub carries the article DOI, not the data DOI
        self.assertIn('10.5194/essd-2025-300', bibtex)
        self.assertNotIn('zenodo', bibtex)

    def test_fulltext_search_before_stub(self):
        from unittest import mock
        from papers.extract import extract_txt_metadata, DOIRequestError
        fulltext = mock.Mock(return_value=self._bibtex('10.5194/essd-2025-300', 'A gridded dataset of something important'))
        with mock.patch('papers.extract.fetch_bibtex_by_doi', side_effect=DOIRequestError('nope')), \
                mock.patch('papers.extract.fetch_bibtex_by_fulltext_crossref', fulltext):
            bibtex = extract_txt_metadata(ESSD_TEXT, search_doi=True, search_fulltext=True)
        fulltext.assert_called_once()
        self.assertIn('Author', bibtex)
