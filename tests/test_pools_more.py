"""More tests of papers.pools: pull --check, push conflicts, light and full
conversions without files directory, link repairs, and the Pool lookups"""
import os
from pathlib import Path
from unittest.mock import patch

from papers.bib import Biblio
from papers.config import Config
from papers.pools import Exchange, Pool, Pools, PoolError, ORIGIN_FILE, load_biblio, mtime
from papers.merge import Resolver
from papers.utils import PapersExit

from tests.test_pools import PoolTest, SMITH_BIB, NEW_BIB, no_fetch


class TestPullCheck(PoolTest):

    def test_not_found_in_pool(self):
        self.take_smith()
        self.edit_pool('doi = {10.1000/abc123}', 'doi = {10.1000/other}')
        self.edit_pool('@article{Smith_2020,', '@article{Other_2020,')
        self.assertIn('smith2020climate: not found in pool ../pool', self.out('pull --check'))

    def test_not_pulled_yet(self):
        Path(self.path('lib', 'papers.bib')).write_text(SMITH_BIB)
        self.assertIn('smith2020climate: in pool ../pool as Smith_2020, not pulled yet', self.out('pull --check'))

    def test_new_pool_file(self):
        self.take_smith()
        Path(self.path('pool', 'files', 'smith-si.pdf')).write_text('supplement')
        self.edit_pool('file = {:files/smith.pdf:pdf}', 'file = {:files/smith.pdf:pdf;:files/smith-si.pdf:pdf}')
        self.assertIn('smith2020climate: changed in pool ../pool: file', self.out('pull --check'))

    def test_conflict_count(self):
        self.take_smith()
        self.edit_pool('journal = {Nat.}', 'journal = {Nature Climate Change}')
        self.edit_lib('journal = {Nat.}', 'journal = {Nature}')
        self.assertIn('journal (1 conflict)', self.out('pull --check'))


class TestPushConflict(PoolTest):

    def setUp(self):
        super().setUp()
        self.take_smith()
        self.edit_pool('journal = {Nat.}', 'journal = {Nature Climate Change}')
        self.edit_lib('journal = {Nat.}', 'journal = {Nature}')

    def test_skip(self):
        out = self.out('push --on-duplicate skip')
        self.assertIn('skipped', out)
        self.assertIn('Nature Climate Change', Path(self.path('pool', 'papers.bib')).read_text())

    def test_update(self):
        self.lib('push --on-duplicate update')
        text = Path(self.path('pool', 'papers.bib')).read_text()
        self.assertIn('journal = {Nature}', text)


class TestExchange(PoolTest):

    def exchange(self):
        config = Config.load(self.path('lib', '.papersconfig.json'))
        return Exchange(config, Biblio.load(config.bibtex, config.filesdir))

    def test_to_light_pool_without_filesdir(self):
        self.take_smith()
        exchange = self.exchange()
        pool = exchange.pools.first()
        pool.config.filesdir = None
        with self.assertRaisesRegex(PoolError, 'has no files directory'):
            exchange.to_light()

    def test_to_full_without_filesdir(self):
        exchange = self.exchange()
        exchange.biblio.filesdir = None
        with self.assertRaisesRegex(PapersExit, 'no files directory'):
            exchange.to_full()

    def test_repair_links_without_pool_entry_or_file(self):
        self.take_smith()
        exchange = self.exchange()
        e = exchange.biblio.entries[0]
        # a broken link into the pool, and the pool entry has no file the entry does not link to
        exchange.biblio.set_files(e, [self.pool_pdf, self.path('pool', 'files', 'renamed.pdf')])
        self.assertEqual(exchange.repair_links(), [])
        exchange.pools.first().biblio.entries[0]['doi'] = '10.1000/other'
        exchange.pools.first().biblio.entries[0]['title'] = 'Other'
        exchange.pools.first()._index = None
        exchange.origin.entries.clear()
        self.assertEqual(exchange.repair_links(), [])  # no pool entry

    def test_push_added_without_light_or_sync(self):
        self.assertEqual(self.exchange().push_added([], [], Resolver('error')), [])


class TestPoolLookups(PoolTest):

    def pool(self):
        return Pools(Config.load(self.path('lib', '.papersconfig.json'))).first()

    def test_repr_and_label(self):
        pool = self.pool()
        self.assertEqual(repr(pool), f"Pool('../pool', {self.path('pool')!r})")
        self.assertEqual(pool.label, 'pool ../pool')

    def test_find_file(self):
        pool = self.pool()
        self.assertEqual(pool.find_file(self.pool_pdf)[1], self.pool_pdf)  # the same file
        self.assertEqual(pool.find_file(self.path('missing.pdf')), (None, None))
        Path(self.path('other.pdf')).write_text('pdf of smiht')  # same size, other content
        self.assertEqual(pool.find_file(self.path('other.pdf')), (None, None))

    def test_by_key(self):
        pool = self.pool()
        smith = pool.biblio.entries[0] if pool.biblio.entries[0].key == 'Smith_2020' else pool.biblio.entries[1]
        self.assertIsNone(pool.by_key('', smith))
        self.assertIsNone(pool.by_key('nope', smith))
        other = Biblio()
        other.add_bibtex(SMITH_BIB.replace('10.1000/ABC123', '10.1000/different'))
        self.assertIsNone(pool.by_key('smith_2020', other.entries[0]))  # contradicting DOI
        self.assertIs(pool.by_key('smith_2020', smith), smith)

    def test_pool_path_given_as_in_setting(self):
        # a path given on the command line is named as the pools setting writes it
        pools = Pools(Config.load(self.path('lib', '.papersconfig.json')))
        self.assertEqual(pools.get(self.path('pool')).id, '../pool')

    def test_load_biblio_without_bibtex(self):
        config = Config(bibtex=self.path('none', 'papers.bib'), filesdir=self.path('none', 'files'))
        biblio = load_biblio(config)
        self.assertEqual(biblio.entries, [])
        self.assertFalse(os.path.exists(self.path('none')))

    def test_mtime_missing(self):
        self.assertIsNone(mtime(self.path('missing')))
