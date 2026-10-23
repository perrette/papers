"""The order and the text of a saved bibtex: Biblio.sort and format_library"""
import os
import shutil
import tempfile
import unittest

from bibtexparser.middlewares import SortBlocksByTypeAndKeyMiddleware

from papers.bib import Biblio
from papers.entries import parse_string

HERE = os.path.dirname(__file__)
VARIED = os.path.join(HERE, 'sortformat', 'varied.bib')
# the output of the implementation based on bibtexparser's middlewares
# (SortBlocksByTypeAndKeyMiddleware, then write_string with the default unparse stack)
EXPECTED = os.path.join(HERE, 'sortformat', 'varied.expected.bib')


def read(path):
    with open(path) as f:
        return f.read()


class TestSortFormat(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='papers-sortformat-')

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_sort_format_unchanged(self):
        biblio = Biblio.load(VARIED, '')
        biblio.sort()
        self.assertEqual(biblio.format(), read(EXPECTED))

    def test_save_unchanged(self):
        bibtex = os.path.join(self.tmp, 'papers.bib')
        shutil.copy(VARIED, bibtex)
        Biblio.load(bibtex, '').save(bibtex)
        self.assertEqual(read(bibtex), read(EXPECTED))

    def test_same_order_as_bibtexparser(self):
        library = parse_string(read(VARIED))
        expected = SortBlocksByTypeAndKeyMiddleware().transform(library=library)
        biblio = Biblio(library)
        biblio.sort()
        describe = lambda blocks: [(type(b).__name__, getattr(b, 'key', None), b.raw) for b in blocks]
        self.assertEqual(describe(biblio.db.blocks), describe(expected.blocks))

    def test_format_leaves_values(self):
        "formatting does not enclose the values of the library itself"
        biblio = Biblio.load(VARIED, '')
        before = [(e.key, [(f.key, f.value) for f in e.fields]) for e in biblio.entries]
        biblio.format()
        after = [(e.key, sorted((f.key, f.value) for f in e.fields)) for e in biblio.entries]
        self.assertEqual(after, [(k, sorted(fields)) for k, fields in before])

    def test_entries_are_kept_by_save(self):
        "an entry held before a save is still the entry of the library after it"
        bibtex = os.path.join(self.tmp, 'papers.bib')
        shutil.copy(VARIED, bibtex)
        biblio = Biblio.load(bibtex, '')
        held = {e.key: e for e in biblio.entries}
        biblio.save(bibtex)
        self.assertEqual(len(biblio.entries), len(held))
        for e in biblio.entries:
            self.assertIs(e, held[e.key])
        # a change made after the save is in the library
        held['delta2004']['note'] = 'changed after save'
        biblio.save(bibtex)
        self.assertIn('changed after save', read(bibtex))


if __name__ == '__main__':
    unittest.main()
