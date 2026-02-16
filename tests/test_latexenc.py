"""Unit tests for papers.latexenc - LaTeX/Unicode conversion (37% coverage -> target ~90%)"""
import unittest

from papers.latexenc import (
    latex_to_unicode,
    string_to_latex,
    protect_uppercase,
)


class TestLatexToUnicode(unittest.TestCase):
    """Test latex_to_unicode conversions"""

    def test_simple_accents(self):
        self.assertEqual(latex_to_unicode("{\\'e}"), "é")
        self.assertEqual(latex_to_unicode("{\\'E}"), "É")
        self.assertEqual(latex_to_unicode("{\\\"u}"), "ü")
        self.assertEqual(latex_to_unicode("{\\c{c}}"), "ç")
        self.assertEqual(latex_to_unicode("{\\~n}"), "ñ")

    def test_crappy_format(self):
        self.assertEqual(latex_to_unicode("\\'{e}"), "é")
        self.assertEqual(latex_to_unicode("\\'{a}"), "á")

    def test_crappy2_combining_accents(self):
        """unicode_to_crappy_latex2: \\` {e} -> e with combining grave"""
        self.assertEqual(latex_to_unicode("\\`{e}"), "è")
        self.assertEqual(latex_to_unicode("\\'{e}"), "é")

    def test_trailing_combining_char_discarded(self):
        """Trailing combining diacritical (e.g. bare \\') is discarded"""
        # "\\'" alone maps to U+0301 (combining acute), trailing so discarded -> empty
        result = latex_to_unicode("\\'")
        self.assertEqual(result, "")

    def test_no_backslash_unchanged(self):
        self.assertEqual(latex_to_unicode("hello"), "hello")
        self.assertEqual(latex_to_unicode("Hello World"), "Hello World")

    def test_removes_braces(self):
        result = latex_to_unicode("{\\'e}")
        self.assertNotIn("{", result)
        self.assertNotIn("}", result)


class TestUnicodeToLatex(unittest.TestCase):
    """Test string_to_latex (unicode -> LaTeX conversion)"""

    def test_simple_accents(self):
        result = string_to_latex("é")
        self.assertIn("\\'", result)
        result = string_to_latex("á")
        self.assertIn("\\'", result)

    def test_roundtrip_via_latex_to_unicode(self):
        for s in ["é", "ñ", "ç", "ü", "ö", "François"]:
            result = string_to_latex(s)
            self.assertIsInstance(result, str)
            back = latex_to_unicode(result)
            self.assertEqual(back, s, f"Roundtrip failed for {s}: {result} -> {back}")


class TestStringToLatex(unittest.TestCase):
    """Test string_to_latex (maps each char via unicode_to_latex_map)"""

    def test_preserves_spaces_and_braces(self):
        result = string_to_latex(" { } ")
        self.assertEqual(result, " { } ")

    def test_converts_accents(self):
        result = string_to_latex("é")
        self.assertIn("\\'", result)


class TestProtectUppercase(unittest.TestCase):
    """Test protect_uppercase for bibtex"""

    def test_wraps_uppercase_in_braces(self):
        result = protect_uppercase("Hello")
        self.assertIn("{H}", result)
        self.assertIn("{W}", protect_uppercase("World"))

    def test_preserves_lowercase(self):
        result = protect_uppercase("hello")
        self.assertEqual(result, "hello")
