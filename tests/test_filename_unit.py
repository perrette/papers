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
        # attributes and indexes of the values (library.md, Syntax)
        for template in ('{year.real}', '{year[x]}', '{author.x.y}'):
            with self.assertRaisesRegex(TemplateError, 'invalid name template', msg=template):
                Format(template=template)(ENTRY)


class TestSafeFileNames(unittest.TestCase):

    def test_windows_characters(self):
        fmt = Format(template='{journal}/{author}_{year}')
        name = fmt({'author': 'Doe, J.', 'year': '2000', 'journal': 'Nature: "A|B" <x>?*\x01. '})
        self.assertEqual(name, 'Nature- -A-B- -x----/doe_2000')

    def test_reserved_names(self):
        fmt = Format(template='{journal}/{author}')
        self.assertEqual(fmt({'author': 'Nul', 'journal': 'con.x'}), 'con-.x/nul-')

    def test_no_journal(self):
        # no 'None' folder: an empty folder of the template is left out
        fmt = Format(template='{journal}/{author}_{year}')
        self.assertEqual(fmt({'author': 'Doe, J.', 'year': '2000'}), 'doe_2000')
        self.assertEqual(Format(template='{author}{journal}', kind='key')({'author': 'Doe, J.'}), 'doe')

    def test_keys_unchanged(self):
        fmt = Format(template='{journal}', kind='key')
        self.assertEqual(fmt({'journal': 'a:b'}), 'a:b')

    def test_length(self):
        from papers.filename import MAX_NAME_BYTES, fit_name
        fmt = Format(template='{journal}/{author}', author_num=200)
        name = fmt({'author': ' and '.join(['Müller'] * 200), 'journal': 'é' * 300})
        folder, base = name.split('/')
        self.assertLessEqual(len(folder.encode()), MAX_NAME_BYTES)
        self.assertEqual(fit_name(name + '.pdf')[-4:], '.pdf')
        self.assertEqual(len(fit_name(name + '.pdf').split('/')[1].encode()), MAX_NAME_BYTES)

    def test_attachments_fit(self):
        from papers.files import attachment_names
        from papers.filename import MAX_NAME_BYTES
        target = 'files/' + 'a' * 240
        names = attachment_names(['x.pdf', 'a/supplement.pdf', 'b/supplement.pdf'], target)
        self.assertEqual(names[0], target + '.pdf')
        for name in names:
            self.assertLessEqual(len(name.split('/')[1].encode()), MAX_NAME_BYTES + 2)
        self.assertEqual(len(set(names)), 3)


class TestSlugTable(unittest.TestCase):

    def test_own_table_whatever_the_slugify_backend(self):
        # python-slugify transliterates with text-unidecode or Unidecode; papers
        # transliterates first with its own table, so the backend does not matter
        import sys
        from unittest import mock
        from papers.filename import make_template_fields, slugify
        with mock.patch.dict(sys.modules, {'unidecode': None}):
            self.assertEqual(make_template_fields({'title': 'x˯x', 'author': 'D˯e'})['title'], 'xvx')
            self.assertEqual(make_template_fields({'title': 'x˯x', 'author': 'D˯e'})['author'], 'dve')
        # apostrophes included
        self.assertEqual(slugify("l'objet Объект Хрущёв µm"), 'l-objet-obekt-khrushchev-mm')
