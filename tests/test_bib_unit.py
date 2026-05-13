"""Unit tests for papers.bib helpers (66% -> higher coverage)"""
import os
import unittest
from unittest import mock

from papers.bib import (
    append_abc,
    isvalidkey,
    compare_entries,
    are_duplicates,
    hidden_bibtex,
    backupfile as backupfile_fn,
    download_url,
    _basename_from_url,
    EXACT_DUPLICATES,
    GOOD_DUPLICATES,
    FAIR_DUPLICATES,
    PARTIAL_DUPLICATES,
)
from papers.duplicate import author_id, title_id, entry_id


def _fake_response(content=b"", status=200, content_type=""):
    r = mock.Mock()
    r.status_code = status
    r.content = content
    r.headers = {"content-type": content_type}
    return r


class TestHiddenBibtex(unittest.TestCase):

    def test_hidden_bibtex(self):
        self.assertEqual(
            hidden_bibtex("/path/to/mypaper"),
            "/path/to/mypaper/.mypaper.bib"
        )


class TestBackupfile(unittest.TestCase):

    def test_backupfile(self):
        result = backupfile_fn("/path/to/library.bib")
        self.assertIn("backup", result)
        self.assertTrue(result.endswith(".backup"))


class TestAppendAbc(unittest.TestCase):

    def test_append_b_to_new_key(self):
        self.assertEqual(append_abc('Author2000'), 'Author2000b')

    def test_append_c_after_b(self):
        self.assertEqual(append_abc('Author2000b'), 'Author2000c')

    def test_with_existing_keys(self):
        result = append_abc('Author2000', ['Author2000', 'Author2000b'])
        self.assertEqual(result, 'Author2000c')


class TestIsvalidkey(unittest.TestCase):

    def test_valid_key(self):
        self.assertTrue(isvalidkey('Author2020'))
        self.assertTrue(isvalidkey('Smith'))

    def test_invalid_starts_with_digit(self):
        self.assertFalse(isvalidkey('2020Author'))
        self.assertFalse(isvalidkey('10.5194/bg-8-515-2011'))

    def test_empty_key(self):
        self.assertFalse(isvalidkey(''))
        self.assertFalse(isvalidkey(None))


class TestCompareEntries(unittest.TestCase):

    def test_exact_duplicates(self):
        e = {"author": "Smith", "title": "Test", "year": "2020", "doi": "10.1234/test"}
        self.assertEqual(compare_entries(e, e), EXACT_DUPLICATES)

    def test_good_duplicates_same_author_title_doi(self):
        e1 = {"author": "Smith, John", "title": "A paper", "year": "2020", "doi": "10.1234/test"}
        e2 = {"author": "Smith, John", "title": "A paper", "year": "2021", "doi": "10.1234/test"}
        self.assertEqual(compare_entries(e1, e2), GOOD_DUPLICATES)

    def test_partial_duplicates_same_author_title_diff_doi(self):
        e1 = {"author": "Smith, John", "title": "A paper", "year": "2020", "doi": "10.1234/a"}
        e2 = {"author": "Smith, John", "title": "A paper", "year": "2020", "doi": "10.1234/b"}
        self.assertEqual(compare_entries(e1, e2), PARTIAL_DUPLICATES)

    def test_fair_duplicates_same_doi(self):
        e1 = {"author": "Smith", "title": "Paper A", "year": "2020", "doi": "10.5194/bg-8-515-2011"}
        e2 = {"author": "Jones", "title": "Paper B", "year": "2021", "doi": "10.5194/bg-8-515-2011"}
        self.assertEqual(compare_entries(e1, e2), FAIR_DUPLICATES)

    def test_no_match_returns_zero(self):
        e1 = {"author": "Smith", "title": "Paper A", "doi": "10.1234/a"}
        e2 = {"author": "Jones", "title": "Paper B", "doi": "10.1234/b"}
        self.assertEqual(compare_entries(e1, e2, fuzzy=False), 0)

    def test_fuzzy_similarity(self):
        e1 = {"author": "Smith, John", "title": "Climate change impacts", "doi": ""}
        e2 = {"author": "Smith, J.", "title": "Climate change impact on oceans", "doi": ""}
        score = compare_entries(e1, e2, fuzzy=True)
        self.assertGreater(score, 0)
        self.assertLessEqual(score, 100)


class TestEntryId(unittest.TestCase):

    def test_author_id(self):
        e = {"author": "Smith, John"}
        self.assertEqual(author_id(e), "smith")

    def test_title_id(self):
        e = {"title": "A Test Paper"}
        self.assertEqual(title_id(e), "a test paper")

    def test_entry_id(self):
        e = {"author": "Smith, J.", "title": "Paper", "doi": "10.1234/test"}
        doi, authortitle = entry_id(e)
        self.assertEqual(doi, "10.1234/test")
        self.assertIn("smith", authortitle)
        self.assertIn("paper", authortitle)

    def test_author_id_replaces_unicode(self):
        """_remove_unicode replaces chars with ord > 128"""
        e = {"author": "Müller, Hans"}
        self.assertEqual(author_id(e), "m_ller")


class TestAreDuplicates(unittest.TestCase):

    def test_exact_are_duplicates(self):
        e = {"author": "Smith", "title": "Test", "year": "2020"}
        self.assertTrue(are_duplicates(e, e, similarity="EXACT"))

    def test_partial_same_doi(self):
        e1 = {"author": "A", "title": "X", "doi": "10.1234/x"}
        e2 = {"author": "B", "title": "Y", "doi": "10.1234/x"}
        self.assertTrue(are_duplicates(e1, e2, similarity="PARTIAL"))

    def test_invalid_similarity_raises(self):
        e = {"author": "A", "title": "X"}
        with self.assertRaises(ValueError):
            are_duplicates(e, e, similarity="INVALID")


class TestBasenameFromUrl(unittest.TestCase):

    def test_basic(self):
        self.assertEqual(
            _basename_from_url("https://example.org/path/foo.pdf"),
            "foo.pdf",
        )

    def test_strips_query(self):
        self.assertEqual(
            _basename_from_url("https://example.org/a/b/file.zip?token=xyz"),
            "file.zip",
        )

    def test_url_encoded(self):
        self.assertEqual(
            _basename_from_url("https://example.org/foo%20bar.zip"),
            "foo bar.zip",
        )

    def test_empty_path_falls_back(self):
        self.assertEqual(_basename_from_url("https://example.org/"), "download")


class TestDownloadUrl(unittest.TestCase):

    def test_pdf_saved_with_url_basename(self):
        url = "https://example.org/paper.pdf"
        resp = _fake_response(content=b"%PDF-1.4\n...", content_type="application/pdf")
        with mock.patch("papers.bib.requests.get", return_value=resp):
            local = download_url(url, expect_pdf=True)
        try:
            self.assertEqual(os.path.basename(local), "paper.pdf")
            with open(local, "rb") as f:
                self.assertTrue(f.read().startswith(b"%PDF"))
        finally:
            os.remove(local)

    def test_attachment_saved_with_url_basename(self):
        url = "https://example.org/supp.zip"
        resp = _fake_response(content=b"PK\x03\x04zipdata", content_type="application/zip")
        with mock.patch("papers.bib.requests.get", return_value=resp):
            local = download_url(url, expect_pdf=False)
        try:
            self.assertEqual(os.path.basename(local), "supp.zip")
        finally:
            os.remove(local)

    def test_rejects_html_for_attachment(self):
        url = "https://example.org/login.html"
        resp = _fake_response(content=b"<html><body>login</body></html>", content_type="text/html")
        with mock.patch("papers.bib.requests.get", return_value=resp):
            with self.assertRaises(ValueError) as cm:
                download_url(url, expect_pdf=False)
        self.assertIn("HTML page", str(cm.exception))

    def test_rejects_html_for_attachment_when_content_type_missing(self):
        url = "https://example.org/supp.zip"
        resp = _fake_response(content=b"<!DOCTYPE html><html>", content_type="")
        with mock.patch("papers.bib.requests.get", return_value=resp):
            with self.assertRaises(ValueError):
                download_url(url, expect_pdf=False)

    def test_rejects_non_pdf_when_expect_pdf(self):
        url = "https://example.org/paper"
        resp = _fake_response(content=b"<html>landing</html>", content_type="text/html")
        with mock.patch("papers.bib.requests.get", return_value=resp):
            with self.assertRaises(ValueError) as cm:
                download_url(url, expect_pdf=True)
        self.assertIn("did not return a PDF", str(cm.exception))

    def test_appends_pdf_extension_when_missing(self):
        url = "https://example.org/article/12345"
        resp = _fake_response(content=b"%PDF-1.7", content_type="application/pdf")
        with mock.patch("papers.bib.requests.get", return_value=resp):
            local = download_url(url, expect_pdf=True)
        try:
            self.assertTrue(local.endswith(".pdf"))
        finally:
            os.remove(local)

    def test_attachment_appends_extension_from_content_type(self):
        url = "https://doi.pangaea.de/10.1594/PANGAEA.760904?format=zip"
        resp = _fake_response(content=b"PK\x03\x04zip", content_type="application/zip")
        with mock.patch("papers.bib.requests.get", return_value=resp):
            local = download_url(url, expect_pdf=False)
        try:
            self.assertTrue(local.endswith(".zip"))
        finally:
            os.remove(local)

    def test_attachment_does_not_double_extension(self):
        url = "https://example.org/supp.zip"
        resp = _fake_response(content=b"PK\x03\x04zip", content_type="application/zip")
        with mock.patch("papers.bib.requests.get", return_value=resp):
            local = download_url(url, expect_pdf=False)
        try:
            self.assertEqual(os.path.basename(local), "supp.zip")
        finally:
            os.remove(local)

    def test_http_error_includes_url(self):
        url = "https://example.org/missing.pdf"
        resp = _fake_response(content=b"", content_type="text/plain", status=404)
        with mock.patch("papers.bib.requests.get", return_value=resp):
            with self.assertRaises(ValueError) as cm:
                download_url(url, expect_pdf=True)
        self.assertIn("404", str(cm.exception))
        self.assertIn(url, str(cm.exception))
