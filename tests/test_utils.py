"""Unit tests for papers.utils (80% -> higher coverage)"""
import os
import tempfile
import unittest

from papers.utils import (
    strip_colors,
    strip_ansi_link,
    strip_all,
    check_filesdir,
    checksum,
    hash_bytestr_iter,
    ansi_link,
    bcolors,
    color_enabled,
    use_color,
)
import papers.utils


class ColorTest(unittest.TestCase):
    "the colours of the output on (the tests run without terminal: off)"

    def setUp(self):
        self._color = papers.utils.COLOR
        use_color(True)

    def tearDown(self):
        use_color(self._color)


class TestAnsiLink(ColorTest):

    def test_ansi_link_with_label(self):
        result = ansi_link("https://example.com", "click here")
        self.assertIn("click here", result)
        self.assertIn("example.com", result)

    def test_ansi_link_without_label_uses_uri(self):
        result = ansi_link("https://example.com")
        self.assertIn("example.com", result)


    def test_no_link_without_colors(self):
        use_color(False)
        self.assertEqual(ansi_link("https://example.com", "click here"), "click here")


class TestStripColors(ColorTest):

    def test_strip_okgreen(self):
        s = f"{bcolors.OKGREEN}green{bcolors.ENDC}"
        self.assertEqual(strip_colors(s), "green")

    def test_strip_bold(self):
        s = f"{bcolors.BOLD}bold{bcolors.ENDC}"
        self.assertEqual(strip_colors(s), "bold")


class TestStripAnsiLink(unittest.TestCase):

    def test_strip_link_keeps_label(self):
        # OSC 8 ; params ; URI ST label OSC 8 ;; ST
        s = "\033]8;;https://example.com\033\\click\033]8;;\033\\"
        result = strip_ansi_link(s)
        self.assertIn("click", result)
        self.assertNotIn("example.com", result)


class TestStripAll(ColorTest):

    def test_strips_both_colors_and_links(self):
        s = f"{bcolors.OKBLUE}\033]8;;url\033\\link\033]8;;\033\\{bcolors.ENDC}"
        result = strip_all(s)
        self.assertEqual(result, "link")


class FakeTerminal:
    def isatty(self):
        return True


class TestColorEnabled(unittest.TestCase):

    def setUp(self):
        self._no_color = os.environ.pop('NO_COLOR', None)

    def tearDown(self):
        os.environ.pop('NO_COLOR', None)
        if self._no_color is not None:
            os.environ['NO_COLOR'] = self._no_color

    def test_auto(self):
        self.assertTrue(color_enabled('auto', FakeTerminal()))
        self.assertFalse(color_enabled('auto', open(os.devnull, 'w')))
        os.environ['NO_COLOR'] = '1'
        self.assertFalse(color_enabled('auto', FakeTerminal()))
        os.environ['NO_COLOR'] = ''  # empty: not set (https://no-color.org)
        self.assertTrue(color_enabled('auto', FakeTerminal()))

    def test_always_never(self):
        os.environ['NO_COLOR'] = '1'
        self.assertTrue(color_enabled('always', open(os.devnull, 'w')))
        self.assertFalse(color_enabled('never', FakeTerminal()))

    def test_use_color(self):
        color = papers.utils.COLOR
        try:
            use_color(False)
            self.assertEqual(bcolors.OKGREEN + 'x' + bcolors.ENDC, 'x')
            use_color(True)
            self.assertEqual(bcolors.OKGREEN, '\033[92m')
        finally:
            use_color(color)


class TestChecksum(unittest.TestCase):

    def test_checksum_deterministic(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as f:
            f.write(b'hello world')
            path = f.name
        try:
            c1 = checksum(path)
            c2 = checksum(path)
            self.assertEqual(c1, c2)
            self.assertEqual(len(c1), 32)  # sha256 digest (bytes)
        finally:
            os.unlink(path)


class TestHashBytestrIter(unittest.TestCase):

    def test_ashexstr_returns_hex_string(self):
        result = hash_bytestr_iter(iter([b'hello']), __import__('hashlib').sha256(), ashexstr=True)
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 64)
        self.assertTrue(all(c in '0123456789abcdef' for c in result))


class TestCheckFilesdir(unittest.TestCase):

    def test_counts_pdfs(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "a.pdf"), 'wb').write(b"x" * 1000)
            open(os.path.join(d, "b.pdf"), 'wb').write(b"y" * 500)
            open(os.path.join(d, "readme.txt"), 'wb').write(b"text")
            count, size = check_filesdir(d)
            self.assertEqual(count, 2)
            self.assertEqual(size, 1500)


class TestCheckFilesdirCase(unittest.TestCase):

    def test_uppercase_pdf_counted(self):
        # issue #94: .PDF files were silently ignored
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "a.PDF"), "w").write("dummy")
            open(os.path.join(d, "b.pdf"), "w").write("dummy")
            count, size = check_filesdir(d)
            self.assertEqual(count, 2)


class TestSpecificExceptions(unittest.TestCase):
    "the exceptions that used to be caught by bare except clauses"

    def test_hardlink_falls_back_to_copy(self):
        from unittest.mock import patch
        from papers.utils import move
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, 'a.pdf'), os.path.join(d, 'b.pdf')
            open(src, 'w').write('a')
            with patch('os.link', side_effect=OSError('cross-device link')):
                move(src, dst, copy=True, hardlink=True)
            self.assertEqual(open(dst).read(), 'a')
            self.assertNotEqual(os.stat(src).st_ino, os.stat(dst).st_ino)

    def test_isvaliddoi(self):
        from papers.extract import isvaliddoi
        self.assertTrue(isvaliddoi('10.1000/abc123'))
        self.assertFalse(isvaliddoi('not a doi'))

    def test_status_corrupted_bibtex(self):
        from papers.config import Config
        with tempfile.TemporaryDirectory() as d:
            bibtex = os.path.join(d, 'papers.bib')
            open(bibtex, 'wb').write(b'\xff\xfe\x00not utf-8')
            config = Config(bibtex=bibtex, filesdir=d)
            self.assertIn('(corrupted)', config.status(check_files=True))
