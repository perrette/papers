"""Unit tests for papers.bib helpers, and the download helpers of papers.files"""
import os
import unittest
from unittest import mock

from papers.bib import (
    append_abc,
    isvalidkey,
)
from papers.files import hidden_bibtex, download_url, _basename_from_url
from papers.duplicate import author_id, title_id, authortitle_id


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


class TestAppendAbc(unittest.TestCase):

    def test_append_b_to_new_key(self):
        self.assertEqual(append_abc('Author2000'), 'Author2000b')

    def test_append_c_after_b(self):
        self.assertEqual(append_abc('Author2000b'), 'Author2000c')

    def test_with_existing_keys(self):
        result = append_abc('Author2000', ['Author2000', 'Author2000b'])
        self.assertEqual(result, 'Author2000c')

    def test_ignores_case(self):
        self.assertEqual(append_abc('Author2000', ['author2000', 'author2000b']), 'Author2000c')

    def test_key_ending_with_a_letter(self):
        # the last letter is a suffix only after a digit: 'perrette' used to become 'perrettf'
        self.assertEqual(append_abc('perrette', ['perrette']), 'perretteb')
        self.assertEqual(append_abc('10-1000-abc', ['10-1000-abc']), '10-1000-abcb')

    def test_no_letter_left(self):
        with self.assertRaises(ValueError):
            append_abc('Author2000z', ['Author2000z'])


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


class TestEntryId(unittest.TestCase):

    def test_author_id(self):
        e = {"author": "Smith, John"}
        self.assertEqual(author_id(e), "smith")

    def test_title_id(self):
        e = {"title": "A Test Paper"}
        self.assertEqual(title_id(e), "a test paper")

    def test_authortitle_id(self):
        e = {"author": "Smith, J.", "title": "Paper", "doi": "10.1234/test"}
        self.assertEqual(authortitle_id(e), "smith|paper")

    def test_authortitle_id_needs_both(self):
        self.assertEqual(authortitle_id({"title": "Editorial"}), "")
        self.assertEqual(authortitle_id({"author": "Smith, J."}), "")

    def test_author_id_accents(self):
        e = {"author": "M{\\\"u}ller, Hans and Müller, Jens"}
        self.assertEqual(author_id(e), "muller muller")

    def test_title_id_braces_and_spaces(self):
        self.assertEqual(title_id({"title": "The {CO2}   Problem"}), "the co2 problem")


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
        with mock.patch("requests.get", return_value=resp):
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
        with mock.patch("requests.get", return_value=resp):
            local = download_url(url, expect_pdf=False)
        try:
            self.assertEqual(os.path.basename(local), "supp.zip")
        finally:
            os.remove(local)

    def test_rejects_html_for_attachment(self):
        url = "https://example.org/login.html"
        resp = _fake_response(content=b"<html><body>login</body></html>", content_type="text/html")
        with mock.patch("requests.get", return_value=resp):
            with self.assertRaises(ValueError) as cm:
                download_url(url, expect_pdf=False)
        self.assertIn("HTML page", str(cm.exception))

    def test_rejects_html_for_attachment_when_content_type_missing(self):
        url = "https://example.org/supp.zip"
        resp = _fake_response(content=b"<!DOCTYPE html><html>", content_type="")
        with mock.patch("requests.get", return_value=resp):
            with self.assertRaises(ValueError):
                download_url(url, expect_pdf=False)

    def test_rejects_non_pdf_when_expect_pdf(self):
        url = "https://example.org/paper"
        resp = _fake_response(content=b"<html>landing</html>", content_type="text/html")
        with mock.patch("requests.get", return_value=resp):
            with self.assertRaises(ValueError) as cm:
                download_url(url, expect_pdf=True)
        self.assertIn("did not return a PDF", str(cm.exception))

    def test_appends_pdf_extension_when_missing(self):
        url = "https://example.org/article/12345"
        resp = _fake_response(content=b"%PDF-1.7", content_type="application/pdf")
        with mock.patch("requests.get", return_value=resp):
            local = download_url(url, expect_pdf=True)
        try:
            self.assertTrue(local.endswith(".pdf"))
        finally:
            os.remove(local)

    def test_attachment_appends_extension_from_content_type(self):
        url = "https://doi.pangaea.de/10.1594/PANGAEA.760904?format=zip"
        resp = _fake_response(content=b"PK\x03\x04zip", content_type="application/zip")
        with mock.patch("requests.get", return_value=resp):
            local = download_url(url, expect_pdf=False)
        try:
            self.assertTrue(local.endswith(".zip"))
        finally:
            os.remove(local)

    def test_attachment_does_not_double_extension(self):
        url = "https://example.org/supp.zip"
        resp = _fake_response(content=b"PK\x03\x04zip", content_type="application/zip")
        with mock.patch("requests.get", return_value=resp):
            local = download_url(url, expect_pdf=False)
        try:
            self.assertEqual(os.path.basename(local), "supp.zip")
        finally:
            os.remove(local)

    def test_http_error_includes_url(self):
        url = "https://example.org/missing.pdf"
        resp = _fake_response(content=b"", content_type="text/plain", status=404)
        with mock.patch("requests.get", return_value=resp):
            with self.assertRaises(ValueError) as cm:
                download_url(url, expect_pdf=True)
        self.assertIn("404", str(cm.exception))
        self.assertIn(url, str(cm.exception))
