"""Unit tests for papers.filename"""
import unittest

from papers.filename import Format, UNKNOWN_AUTHOR, UNKNOWN_YEAR, UNKNOWN_TITLE


class TestFormatIsUnknown(unittest.TestCase):

    def test_unknown_strict_all_must_be_unknown(self):
        fmt = Format(template="{author}", unknown_strict=True)
        self.assertTrue(fmt.is_unknown({"author": UNKNOWN_AUTHOR, "year": UNKNOWN_YEAR, "title": UNKNOWN_TITLE}))
        self.assertFalse(fmt.is_unknown({"author": "Smith", "year": UNKNOWN_YEAR, "title": UNKNOWN_TITLE}))

    def test_unknown_non_strict_any_is_unknown(self):
        fmt = Format(template="{author}", unknown_strict=False)
        self.assertTrue(fmt.is_unknown({"author": "Smith", "year": "2020", "title": UNKNOWN_TITLE}))
        self.assertFalse(fmt.is_unknown({"author": "Smith", "year": "2020", "title": "A Paper"}))
