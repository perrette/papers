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

    def test_case(self):
        # BibTeX ignores the case of field names and keys: Title and title,
        # or Smith2000 and smith2000, are given twice
        text = ('@article{Smith2000, title={A}}\n\n@article{smith2000, title={B}}\n\n'
                '@article{other, Title={C}, title={D}}\n')
        db = parse_string(text)
        self.assertEqual([e.key for e in db.entries], ['Smith2000'])
        self.assertEqual([reason for line, reason in unreadable_blocks(db)],
                         ["a key given twice (keys ignore case): 'smith2000'", "a field given twice: 'title'"])
        Path(self.path('lib', 'papers.bib')).write_text(text)
        Path(self.path('new.bib')).write_text(NEW_BIB)
        self.lib('add ../new.bib --no-pool')
        saved = Path(self.path('lib', 'papers.bib')).read_text()
        for part in ('@article{smith2000, title={B}}', 'Title={C}, title={D}', 'new2021'):
            self.assertIn(part, saved)

    def test_added_bibtex_warns(self):
        biblio = Biblio()
        with self.assertLogs('papers', level='WARNING') as logs:
            biblio.add_bibtex('@article{a2000, title={A}, year={2000}}\n\n@article{b2000, Title={B}, title={C}}\n')
        self.assertIn("line 3: a field given twice: 'title'): they are not added", '\n'.join(logs.output))
        self.assertEqual([e.key for e in biblio.entries], ['a2000'])

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
