"""entries that bibtexparser cannot read: a warning, and no writing to a pool that has one"""
from pathlib import Path

from papers.bib import Biblio, unreadable_blocks
from papers.entries import parse_string
from papers.utils import PapersExit

from tests.test_pools import PoolTest

TWICE = """@article{twice,
 title = {One},
 title = {Two},
 year = {2001}
}
"""

NEW_BIB = """@article{new2021,
 author = {New, A.},
 title = {A new paper},
 year = {2021},
 doi = {10.1000/new}
}
"""


class TestUnreadable(PoolTest):

    def test_blocks(self):
        found = unreadable_blocks(parse_string('@article{ok, title={A}}\n\n' + TWICE))
        self.assertEqual(len(found), 1)
        line, reason = found[0]
        self.assertEqual(line, 3)
        self.assertIn('a field given twice', reason)

    def test_text_kept(self):
        # the entry is not seen, but saving the library writes its text back
        Path(self.path('lib', 'papers.bib')).write_text(TWICE)
        Path(self.path('new.bib')).write_text(NEW_BIB)
        self.lib('add ../new.bib --no-pool')
        text = Path(self.path('lib', 'papers.bib')).read_text()
        self.assertIn('title = {Two}', text)
        self.assertIn('new2021', text)
        self.assertEqual(len(Biblio.load(self.path('lib', 'papers.bib'), '').unreadable), 1)

    def test_push_refused(self):
        Path(self.path('new.bib')).write_text(NEW_BIB)
        self.lib('add ../new.bib --no-pool')
        pool_bib = Path(self.path('pool', 'papers.bib'))
        pool_bib.write_text(pool_bib.read_text() + '\n' + TWICE)
        before = pool_bib.read_text()
        with self.assertRaisesRegex(PapersExit, r'could not be read .*Fix .* before writing to the pool'):
            self.lib('push --all')
        self.assertEqual(pool_bib.read_text(), before)

    def test_pull_allowed(self):
        # reading from a pool with an unreadable entry works (with a warning)
        pool_bib = Path(self.path('pool', 'papers.bib'))
        pool_bib.write_text(pool_bib.read_text() + '\n' + TWICE)
        self.lib('pull --all')
        self.assertIn('Smith_2020', Path(self.path('lib', 'papers.bib')).read_text())
