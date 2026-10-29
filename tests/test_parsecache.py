"""The cache of the parsed bibtex (papers.parsecache): the library is the
same as bibtexparser makes of the whole text, the second time from the
cache, and after a change only the pieces that changed are split"""
import glob
import os
import tempfile
import unittest
from unittest.mock import patch

import bibtexparser

from papers import parsecache
from papers.entries import format_library, lowercase_fields, parse_string

HERE = os.path.dirname(__file__)


def entries(n, start=0):
    return ''.join(f'@article{{k{i},\n author = {{Author {i}}},\n title = {{Title {i}}},\n year = {{{2000 + i % 20}}}\n}}\n\n'
                   for i in range(start, start + n))


CASES = {
    'many': entries(500),
    'strings across pieces': '@string{jgr = {J. Geophys. Res.}}\n\n' + entries(200)
                             + '@article{s1,\n journal = jgr # {, Oceans},\n title = {S}\n}\n',
    'duplicates across pieces': entries(200) + entries(3, start=5),
    'at sign at a line start in a value': entries(100) + '@article{x1,\n abstract = {first line\n@second line}\n}\n\n'
                                          + entries(100, start=100),
    'comments': '% a comment\n\n@comment{papers-pool ../pool}\n\n' + entries(100) + 'some trailing text\n',
    'crlf': entries(100).replace('\n', '\r\n'),
    'broken entry': entries(50) + '@article{broken,\n title = {no closing brace\n\n' + entries(50, start=50),
    'preamble': '@preamble{"\\newcommand{\\x}{y}"}\n\n' + entries(80),
    'unicode': entries(40) + '@article{u,\n title = {été — ü}\n}\n',
    'empty fields and odd keys': '@article{a:b-c/d,\n title = {},\n year = 2000\n}\n\n' + entries(40),
}


def describe(library):
    "what papers sees of a library: its blocks (type, key, line, fields) and the text written back"
    blocks = [(type(b).__name__, getattr(b, 'key', None), b.start_line,
               [(f.key, f.value, f.start_line) for f in getattr(b, 'fields', [])]) for b in library.blocks]
    return blocks, format_library(library)


class TestParseCache(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = parsecache.Cache(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def assertSameParse(self, text, name=''):
        expected = describe(lowercase_fields(bibtexparser.parse_string(text)))
        self.assertEqual(describe(parse_string(text, cache=self.cache)), expected, f'{name}: first time')
        self.assertEqual(describe(parse_string(text, cache=self.cache)), expected, f'{name}: from the cache')

    def test_cases(self):
        for name, text in CASES.items():
            with self.subTest(name):
                self.assertSameParse(text, name)

    def test_files_of_the_tests(self):
        for path in glob.glob(os.path.join(HERE, '**', '*.bib'), recursive=True):
            with self.subTest(os.path.relpath(path, HERE)):
                self.assertSameParse(open(path, encoding='utf-8', errors='replace').read(), path)

    def test_only_changed_pieces_are_split(self):
        text = entries(1000)
        parse_string(text, cache=self.cache)
        changed = text.replace('title = {Title 500}', 'title = {Another title}')
        calls = []
        real = parsecache.Splitter

        def splitter(bibstr):
            calls.append(bibstr)
            return real(bibstr=bibstr)
        with patch('papers.parsecache.Splitter', side_effect=splitter):
            library = parse_string(changed, cache=self.cache)
        self.assertEqual(len(calls), 1)  # the piece with k500
        self.assertIn('Another title', calls[0])
        self.assertEqual(describe(library), describe(lowercase_fields(bibtexparser.parse_string(changed))))

    def test_not_cached_when_a_block_fails(self):
        parse_string(CASES['broken entry'], cache=self.cache)
        cached = [f for _, _, files in os.walk(self.tmp.name) for f in files]
        # the pieces before the broken one are cached; the broken one is not
        self.assertTrue(cached)
        self.assertLess(len(cached), len(list(parsecache._ordered(CASES['broken entry']))))

    def test_warning_once(self):
        # the splitter's warning of the broken block: once, not again for its piece
        with self.assertLogs('bibtexparser.splitter', 'WARNING') as logs:
            parse_string(CASES['broken entry'], cache=self.cache)
        self.assertEqual(len(logs.output), 1, logs.output)

    def test_prune(self):
        parse_string(entries(1000), cache=self.cache)
        self.cache.prune(size=1000)
        size = sum(os.path.getsize(os.path.join(d, f)) for d, _, files in os.walk(self.tmp.name) for f in files)
        self.assertLessEqual(size, 1000)
        # a cache emptied is filled again
        self.assertSameParse(entries(1000))

    def test_damaged_cache(self):
        text = entries(100)
        parse_string(text, cache=self.cache)
        for d, _, files in os.walk(self.tmp.name):
            for f in files:
                open(os.path.join(d, f), 'w').write('not json')
        self.assertSameParse(text)


if __name__ == '__main__':
    unittest.main()
