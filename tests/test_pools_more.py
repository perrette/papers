"""More tests of papers.pools: pull --check, push conflicts, conversions
without files directory, link repairs, the Pool lookups, pull of pool
entries and sync"""
import os
from pathlib import Path

from papers.bib import Biblio
from papers.config import Config
from papers.pools import Exchange, Pools, PoolError, load_biblio, mtime, use_pool_files
from papers.utils import PapersExit

from tests.test_pools import PoolTest, SMITH_BIB, NEW_BIB


class TestPullCheck(PoolTest):

    def test_not_found_in_pool(self):
        self.take_smith()
        self.edit_pool('doi = {10.1000/abc123}', 'doi = {10.1000/other}')
        self.edit_pool('@article{Smith_2020,', '@article{Other_2020,')
        self.assertIn('smith2020climate: not found in pool ../pool', self.out('pull --check'))

    def test_not_pulled_yet(self):
        Path(self.path('lib', 'papers.bib')).write_text(SMITH_BIB)
        self.assertIn('smith2020climate: in pool ../pool as Smith_2020, not pulled yet', self.out('pull --check smith2020climate'))

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

    def test_to_local_without_filesdir(self):
        exchange = self.exchange()
        exchange.biblio.filesdir = None
        with self.assertRaisesRegex(PapersExit, 'no files directory'):
            exchange.to_local([], [])

    def test_pool_without_filesdir(self):
        exchange = self.exchange()
        exchange.pools.pool().config.filesdir = None
        exchange.config.local = False
        with self.assertRaisesRegex(PoolError, 'has no files directory'):
            use_pool_files(exchange.config, exchange.pools)

    def test_repair_links_without_pool_entry_or_file(self):
        self.take_smith()
        exchange = self.exchange()
        e = exchange.biblio.entries[0]
        # a broken link into the pool, and the pool entry has no file the entry does not link to
        exchange.biblio.set_files(e, [self.pool_pdf, self.path('pool', 'files', 'renamed.pdf')])
        self.assertEqual(exchange.repair_links(), [])
        exchange.pools.pool().biblio.entries[0]['doi'] = '10.1000/other'
        exchange.pools.pool().biblio.entries[0]['title'] = 'Other'
        exchange.pools.pool()._index = None
        exchange.origin.entries.clear()
        self.assertEqual(exchange.repair_links(), [])  # no pool entry


class TestPoolLookups(PoolTest):

    def pool(self):
        return Pools(Config.load(self.path('lib', '.papersconfig.json'))).pool()

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
        # a path given on the command line is named as the pool setting writes it
        pools = Pools(Config.load(self.path('lib', '.papersconfig.json')))
        self.assertEqual(pools.get(self.path('pool')).id, '../pool')

    def test_load_biblio_without_bibtex(self):
        config = Config(bibtex=self.path('none', 'papers.bib'), filesdir=self.path('none', 'files'))
        biblio = load_biblio(config)
        self.assertEqual(biblio.entries, [])
        self.assertFalse(os.path.exists(self.path('none')))

    def test_mtime_missing(self):
        self.assertIsNone(mtime(self.path('missing')))


class TestPullEntries(PoolTest):
    """papers pull KEY of entries that are only in the pool, and --all, --pool"""

    def test_pull_pool_key(self):
        out = self.out('pull Smith_2020')
        self.assertRegex(out, r'^Added -> Smith_2020: .* \[from pool ../pool\]$')
        e = self.entry('Smith_2020')
        self.assertEqual(e['journal'], 'Nat.')
        record = self.origin().get(e)
        self.assertEqual((record.pool, record.pool_key), ('../pool', 'Smith_2020'))
        self.assertEqual(self.files('Smith_2020'), [self.pool_pdf])  # files: link (tests)
        # pulled again: an update, not a new entry
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        self.lib('pull Smith_2020')
        self.assertEqual(len(self.bib()[1]), 1)
        self.assertEqual(self.entry('Smith_2020')['journal'], 'Nature')

    def test_pull_by_doi(self):
        self.lib('pull 10.1000/brown')
        self.assertEqual(list(self.bib()[1]), ['Brown_2021'])

    def test_copy_mode(self):
        self.lib('config files copy')
        self.lib('pull Smith_2020')
        files = self.files('Smith_2020')
        self.assertTrue(files[0].startswith(self.path('lib', 'files')))
        self.assertTrue(os.path.samefile(files[0], self.pool_pdf))  # a hard link

    def test_non_local_links(self):
        self.lib('config local false -y')
        self.lib('config files copy')
        self.lib('pull Smith_2020')
        self.assertEqual(self.files('Smith_2020'), [self.pool_pdf])

    def test_key_taken(self):
        Path(self.path('lib', 'papers.bib')).write_text(NEW_BIB.replace('mine2022', 'Smith_2020'))
        self.lib('pull 10.1000/abc123')
        entries = self.bib()[1]
        self.assertEqual(sorted(entries), ['Smith_2020', 'Smith_2020b'])
        self.assertEqual(entries['Smith_2020b']['doi'], '10.1000/abc123')

    def test_same_paper_in_library(self):
        # the pool entry is the same paper as a library entry: that entry is updated
        Path(self.path('lib', 'papers.bib')).write_text(SMITH_BIB)
        self.lib('pull Smith_2020 --on-duplicate update')
        entries = self.bib()[1]
        self.assertEqual(list(entries), ['smith2020climate'])
        self.assertEqual(entries['smith2020climate']['journal'], 'Nat.')

    def test_unknown(self):
        with self.assertRaisesRegex(PapersExit, 'nope: no entry found'):
            self.lib('pull Smith_2020 nope')
        self.assertEqual(self.bib()[1], {})  # nothing changed

    def test_all(self):
        Path(self.path('lib', 'papers.bib')).write_text(SMITH_BIB)
        out = self.out('pull --all --on-duplicate keep')
        self.assertRegex(out, r'Added -> Brown_2021: .* \[from pool ../pool\]\n')
        self.assertIn('pull from pool ../pool: 1 modified, 1 added', out)
        self.assertEqual(sorted(self.bib()[1]), ['Brown_2021', 'smith2020climate'])

    def test_other_pool(self):
        self.papers('init other --no-git --pool none')
        Path(self.path('other', 'papers.bib')).write_text(NEW_BIB.replace(' file = {:mine.pdf:pdf},\n', ''))
        self.lib('pull --pool ../other mine2022')
        self.assertIsNone(self.origin().get(self.entry('mine2022')))  # one-time: shared with no pool
        self.lib('pull --pool ../other --all')
        self.assertEqual(list(self.bib()[1]), ['mine2022'])

    def test_no_pool(self):
        self.lib('config pool none')
        with self.assertRaisesRegex(PapersExit, 'no pool'):
            self.lib('pull Smith_2020')
        self.assertIn('pull: nothing to do', self.out('pull'))


class TestSync(PoolTest):

    def setUp(self):
        super().setUp()
        self.take_smith()
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        self.lib('add ../new.bib')

    def test_pull_then_push(self):
        # without --all: the shared entries only (smith2020climate, taken from the pool)
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        lines = self.out('sync').splitlines()
        self.assertRegex(lines[0], r'^Modified -> smith2020climate: .* \[from pool ../pool\]$')
        self.assertEqual(lines[1], 'push to pool ../pool: 1 unchanged')
        self.assertEqual(len(lines), 2)
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature')
        self.assertEqual(len(self.bib('pool')[1]), 2)  # mine2022 is not shared: not pushed
        self.assertEqual(self.out('sync'), 'nothing to sync with pool ../pool (1 entry unchanged)')
        # --all: each side gets what it does not have
        lines = self.out('sync --all').splitlines()
        self.assertRegex(lines[0], r'^Added -> Brown_2021: .* \[from pool ../pool\]$')
        self.assertEqual(lines[1], 'pull from pool ../pool: 1 unchanged, 1 added')
        self.assertRegex(lines[2], r'^Added -> mine2022: .* \[to pool ../pool\]$')
        self.assertEqual(lines[3], 'push to pool ../pool: 2 unchanged, 1 added')
        self.assertEqual(len(lines), 4)
        self.assertEqual(len(self.bib('pool')[1]), 3)
        self.assertEqual(self.out('sync'), 'nothing to sync with pool ../pool (3 entries unchanged)')

    def test_nothing_shared(self):
        self.papers('init other --no-git --pool none')
        out = self.out('sync --pool ../other')
        self.assertEqual(out, 'nothing to sync with pool ../other: not the pool of the library, so no entries are shared '
                              'with it (`papers sync --pool PATH KEY...` or `--all` exchanges entries with it once)')
        self.assertEqual(self.bib('other')[1], {})
        self.assertIn('push to pool ../other: not the pool of the library, so no entries are shared with it',
                      self.out('push --pool ../other'))
        self.assertIn('pull from pool ../other: not the pool of the library', self.out('pull --pool ../other'))
        self.assertEqual(self.bib('other')[1], {})

    def test_not_found_only_for_keys_given(self):
        self.edit_pool('@article{Smith_2020,', '@article{Other_2020,')
        self.edit_pool('doi = {10.1000/abc123}', 'doi = {10.1000/other}')
        self.edit_pool('title = {Climate sensitivity revisited}', 'title = {Other}')
        self.assertNotIn('Not found', self.out('pull'))
        self.assertRegex(self.out('pull smith2020climate'), r'Not found -> smith2020climate: .* \[not in pool ../pool\]')
        out = self.out('sync')  # not found in the pool: pushed to it
        self.assertNotIn('Not found', out)
        self.assertRegex(out, r'^Added -> smith2020climate: .* \[to pool ../pool\]$')

    def test_conflict_stops_before_push(self):
        self.edit_pool('journal = {Nat.}', 'journal = {Nature Climate Change}')
        self.edit_lib('journal = {Nat.}', 'journal = {Nature}')
        with self.assertRaisesRegex(PapersExit, 'not pushed'):
            self.lib('sync --all --on-duplicate skip')
        self.assertEqual(len(self.bib('pool')[1]), 2)  # nothing pushed
        self.lib('sync --all --on-duplicate keep')
        self.assertEqual(len(self.bib('pool')[1]), 3)
        self.assertIn('journal = {Nature}', Path(self.path('pool', 'papers.bib')).read_text())

    def test_selection(self):
        self.lib('sync mine2022 Brown_2021')
        self.assertIn('Brown_2021', self.bib()[1])
        self.assertEqual(len(self.bib('pool')[1]), 3)
