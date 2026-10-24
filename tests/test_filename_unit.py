"""Unit tests for papers.filename"""
import unittest

from papers.filename import Format, TemplateError, UNKNOWN_AUTHOR, UNKNOWN_YEAR, UNKNOWN_TITLE, listtag, make_template_fields


class TestFormatIsUnknown(unittest.TestCase):

    def test_unknown_strict_all_must_be_unknown(self):
        fmt = Format(template="{author}", unknown_strict=True)
        self.assertTrue(fmt.is_unknown({"author": UNKNOWN_AUTHOR, "year": UNKNOWN_YEAR, "title": UNKNOWN_TITLE}))
        self.assertFalse(fmt.is_unknown({"author": "Smith", "year": UNKNOWN_YEAR, "title": UNKNOWN_TITLE}))

    def test_unknown_non_strict_any_is_unknown(self):
        fmt = Format(template="{author}", unknown_strict=False)
        self.assertTrue(fmt.is_unknown({"author": "Smith", "year": "2020", "title": UNKNOWN_TITLE}))
        self.assertFalse(fmt.is_unknown({"author": "Smith", "year": "2020", "title": "A Paper"}))


class TestUnknownKeySanitized(unittest.TestCase):

    def test_unknown_key_from_doi_is_sanitized(self):
        # issue #105: the raw doi (slashes, dots...) used to become the key
        from papers.filename import KEYFORMAT
        key = KEYFORMAT({"doi": "10.5194/bg-8(515)-2011"})
        self.assertTrue(key)
        for c in '/().':
            self.assertNotIn(c, key)


class TestTitleLength(unittest.TestCase):
    """title-length is a hard limit: the last words are dropped, and a first
    word longer than the limit is cut"""

    def test_drops_last_words(self):
        self.assertEqual(listtag(['climate', 'sensitivity', 'revisited'], maxlength=20, minwordlen=1),
                         'climate-sensitivity')

    def test_one_word_left(self):
        # used to keep two words whatever the length
        self.assertEqual(listtag(['climate', 'sensitivity', 'revisited'], maxlength=10, minwordlen=1), 'climate')

    def test_long_first_word_is_cut(self):
        self.assertEqual(listtag(['sensitivity', 'revisited'], maxlength=5, minwordlen=1), 'sensi')

    def test_word_num(self):
        self.assertEqual(listtag(['a', 'b', 'c'], maxlength=100, minwordlen=1, n=2), 'a-b')

    def test_word_size(self):
        self.assertEqual(listtag(['a', 'bb', 'ccc'], maxlength=100, minwordlen=2), 'bb-ccc')

    def test_separator_counts(self):
        # the length is that of the title in the name, with its separator
        fields = make_template_fields({'title': 'Climate sensitivity revisited'}, title_length=20,
                                      title_sep='--')
        self.assertEqual(fields['title'], 'climate--sensitivity')
        fields = make_template_fields({'title': 'Climate sensitivity revisited'}, title_length=19,
                                      title_sep='--')
        self.assertEqual(fields['title'], 'climate')

    def test_template(self):
        fmt = Format(template='{title}', title_length=12)
        self.assertEqual(fmt({'title': 'Climate sensitivity revisited'}), 'climate')
        self.assertEqual(Format(template='{Title}', title_length=4)({'title': 'Climate'}), 'Clim')


ENTRY = {"ID": "smith2020", "author": "Smith, John", "year": "2020", "title": "Climate"}


class TestPlaceholders(unittest.TestCase):

    def test_key(self):
        self.assertEqual(Format(template="{key}")(ENTRY), "smith2020")
        self.assertEqual(Format(template="{ID}")(ENTRY), "smith2020")

    def test_unknown_placeholder(self):
        with self.assertRaises(TemplateError) as cm:
            Format(template="{year}_{xxx}")(ENTRY)
        message = str(cm.exception)
        self.assertIn("unknown placeholder {xxx} in the name template '{year}_{xxx}'", message)
        self.assertIn("available: {author}", message)
        self.assertIn("{key}", message)
        with self.assertRaisesRegex(TemplateError, r'unknown placeholder \{foo\} in the key template'):
            Format(template="{foo}", kind='key')(ENTRY)
        with self.assertRaisesRegex(TemplateError, r'unknown placeholder \{\} in the name template'):
            Format(template="{}")(ENTRY)
        with self.assertRaisesRegex(TemplateError, 'invalid name template'):
            Format(template="{year")(ENTRY)
