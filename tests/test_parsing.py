"""Reading and writing bibtex: field names in capitals, unreadable entries"""
import unittest

from papers.entries import format_library, get_entry_val, parse_string


class TestFieldNames(unittest.TestCase):

    def test_capitals(self):
        # older JabRef files (#121)
        lib = parse_string('@Article{k,\n Title = {Ice},\n Keywords = {ice},\n}\n')
        e = lib.entries[0]
        self.assertEqual(get_entry_val(e, 'title'), 'Ice')
        self.assertEqual(get_entry_val(e, 'keywords'), 'ice')
        self.assertIn('title = {Ice}', format_library(lib))


class TestUnreadable(unittest.TestCase):

    def test_one_warning(self):
        # the warning above an entry that does not parse is not repeated at every save (#121)
        text = "@article{a,\n title={T},\n}\n\n% my note\n@article{b,\n title={x},\n title={y},\n}\n"
        for i in range(3):
            text = format_library(parse_string(text))
        self.assertEqual(text.count('% WARNING Parsing failed'), 1)
        self.assertIn('% my note', text)
        self.assertIn(' title={x},\n title={y},', text)
