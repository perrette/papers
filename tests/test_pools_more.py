"""More tests of papers.pools: pull --check, push conflicts, conversions
without files directory, link repairs, the Pool lookups, pull of pool
entries and sync"""
import os
from pathlib import Path
from unittest.mock import patch

from papers.bib import Biblio
from papers.config import Config, CONFIG_FILE_LOCAL
from papers.pools import Exchange, Pools, PoolError, load_biblio, mtime, use_pool_files
from papers.utils import PapersExit

from tests.common import ConfigTest
from tests.test_pools import PoolTest, SMITH_BIB, NEW_BIB


class TestPullCheck(PoolTest):

    def test_not_found_in_pool(self):
        self.take_smith()
        self.edit_pool('doi = {10.1000/abc123}', 'doi = {10.1000/other}')
        self.edit_pool('@article{Smith_2020,', '@article{Other_2020,')
        note = ('smith2020climate: removed from pool ../pool '
                '(`papers push --pool ../pool smith2020climate` adds it back)')
        self.assertIn(note, self.out('pull --check'))
        self.assertIn(note, self.out('pull --check'))  # nothing written

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

    def exchange(self, pool=None):
        "the Exchange of lib, with a pool setting"
        config = Config.load(self.path('lib', CONFIG_FILE_LOCAL))
        if pool:
            config.set('pool', pool)
        return Exchange(config, Biblio.load(config.bibtex, config.filesdir))

    def test_to_local_without_filesdir(self):
        exchange = self.exchange()
        exchange.biblio.filesdir = None
        with self.assertRaisesRegex(PapersExit, 'no files directory'):
            exchange.own_files([], [])

    def test_pool_without_filesdir(self):
        exchange = self.exchange('../pool')  # a shallow library
        exchange.pools.pool().config.filesdir = None
        with self.assertRaisesRegex(PoolError, 'has no files directory'):
            use_pool_files(exchange.config, exchange.pools)

    def test_repair_links_without_pool_entry_or_file(self):
        self.take_smith()
        exchange = self.exchange('../pool')
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
        return Pools(Config.load(self.path('lib', CONFIG_FILE_LOCAL))).get(self.path('pool'))

    def test_repr_and_label(self):
        pool = self.pool()
        self.assertEqual(repr(pool), f"Pool('../pool', {self.path('pool')!r})")
        # the records name it relative to the library; the messages as given
        self.assertEqual(pool.label, f'pool {self.path("pool")}')
        with patch.dict(os.environ, {'HOME': self.path()}):
            self.assertEqual(self.pool().label, 'pool ~/pool')

    def test_label_of_the_pool_option(self):
        # every message names the pool as --pool gives it, though the records name it ../pool
        Path(self.path('new.bib')).write_text(NEW_BIB)
        self.lib('add ../new.bib --no-pool')
        out = self.out('push --all --pool ./../pool')
        self.assertIn('[to pool ./../pool]', out)
        self.assertNotIn('pool ../pool', out)
        self.assertEqual(self.origin().get(self.entry('mine2022')).pool, '../pool')

    def test_label_of_the_pool_setting(self):
        # the pool of the library: as its pool setting writes it, though the records name it ../pool
        self.lib('pull Smith_2020')
        self.lib(f'config pool {self.path("pool")} -y')
        self.edit_pool('{Nat.}', '{Nature}')
        out = self.out('sync')
        self.assertIn(f'[from pool {self.path("pool")}]', out)
        self.assertNotIn('pool ../pool', out)
        self.assertEqual(self.origin().get(self.entry('Smith_2020')).pool, '../pool')

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
        pools = Pools(Config.load(self.path('lib', CONFIG_FILE_LOCAL)))
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

    def test_shallow_links(self):
        self.lib('config pool ../pool -y')
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
        self.papers('init other')
        Path(self.path('other', 'papers.bib')).write_text(NEW_BIB.replace(' file = {:mine.pdf:pdf},\n', ''))
        self.lib('pull --pool ../other mine2022')
        record = self.origin().get(self.entry('mine2022'), '../other')  # recorded for ../other
        self.assertEqual(record.pool_key, 'mine2022')
        self.assertIsNone(self.origin().get(self.entry('mine2022'), '../pool'))
        # a later pull without KEY: the entries exchanged with ../other, merged three-way
        Path(self.path('other', 'papers.bib')).write_text(
            NEW_BIB.replace(' file = {:mine.pdf:pdf},\n', ' volume = {3},\n'))
        self.edit_lib('year = {2022}', 'journal = {J. Mine},\n year = {2022}')
        self.lib('pull --pool ../other')
        e = self.entry('mine2022')
        self.assertEqual((e['volume'], e['journal']), ('3', 'J. Mine'))  # no conflict
        self.lib('pull --pool ../other --all')
        self.assertEqual(list(self.bib()[1]), ['mine2022'])

    def test_no_pool(self):
        for cmd in ['pull Smith_2020', 'pull', 'push --all', 'sync']:
            with self.assertRaisesRegex(PapersExit, 'this library has no pool: give one with `--pool PATH`'):
                self.papers(cmd, cwd=self.path('lib'))
        self.assertEqual(self.bib()[1], {})


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
        self.assertEqual(len(lines), 1)  # the push changed nothing: no line
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature')
        self.assertEqual(len(self.bib('pool')[1]), 2)  # mine2022 is not shared: not pushed
        self.assertEqual(self.out('sync'), 'nothing to sync with pool ../pool')
        # --all: each side gets what it does not have
        lines = self.out('sync --all').splitlines()
        self.assertRegex(lines[0], r'^Added -> Brown_2021: .* \[from pool ../pool\]$')
        self.assertRegex(lines[1], r'^Added -> mine2022: .* \[to pool ../pool\]$')
        self.assertEqual(len(lines), 2)  # one entry each: no count line
        self.assertEqual(len(self.bib('pool')[1]), 3)
        self.assertEqual(self.out('sync'), 'nothing to sync with pool ../pool')

    def test_nothing_shared(self):
        self.papers('init other')
        out = self.out('sync --pool ../other')
        self.assertEqual(out, 'nothing to sync with pool ../other: no entries shared with it '
                              '(`papers sync --pool ../other --all` adds the entries missing on each side)')
        self.assertEqual(self.bib('other')[1], {})
        self.assertEqual('push to pool ../other: no entries shared with it (`papers push --pool ../other KEY` '
                         'or `papers push --pool ../other --all` adds entries to it)', self.out('push --pool ../other'))
        self.assertEqual('nothing to pull from pool ../other', self.out('pull --pool ../other'))
        self.assertEqual(self.bib('other')[1], {})
        # once exchanged, the entries are shared with it
        self.lib('push --pool ../other mine2022')
        self.assertEqual(self.out('sync --pool ../other'), 'nothing to sync with pool ../other')

    def test_not_found_only_for_keys_given(self):
        self.edit_pool('@article{Smith_2020,', '@article{Other_2020,')
        self.edit_pool('doi = {10.1000/abc123}', 'doi = {10.1000/other}')
        self.edit_pool('title = {Climate sensitivity revisited}', 'title = {Other}')
        self.assertNotIn('Not found', self.out('pull'))
        self.assertRegex(self.out('pull smith2020climate'), r'Not found -> smith2020climate: .* \[not in pool ../pool\]')
        out = self.out('sync')  # removed from the pool: not pushed back
        self.assertNotIn('Not found', out)
        self.assertNotIn('Added', out)
        self.assertRegex(self.out('push smith2020climate'), r'^Added -> smith2020climate: .* \[to pool ../pool\]$')

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


class TestPoolIdentifier(ConfigTest):
    """the origin records name the pool by its library identifier: a library
    moved away from its pool keeps them"""

    def test_library_moved(self):
        import shutil
        self.papers('init pool')
        self.papers('init lib --pool ../pool')
        Path(self.path('new.bib')).write_text('@article{mine2022,\n author = {Mine, Me},\n title = {Mine},\n'
                                              ' year = {2022}\n}\n')
        self.papers('add ../new.bib', cwd=self.path('lib'))
        self.papers('pull', cwd=self.path('lib'))  # an exchange once the pool has its identifier
        names = os.listdir(self.path('lib', '.papers', 'origin'))
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].startswith('pool-'), names)  # named after the pool folder
        text = Path(self.path('lib', '.papers', 'origin', names[0])).read_text()
        self.assertRegex(text, r'@comment\{papers-pool [0-9a-f]{32}\}')
        self.assertIn('@comment{papers-pool-path', text)
        # the library moves; its pool setting is set again
        os.makedirs(self.path('elsewhere'))
        shutil.move(self.path('lib'), self.path('elsewhere', 'lib'))
        lib = self.path('elsewhere', 'lib')
        self.papers('config pool ../../pool -y', cwd=lib)
        # a correction in the pool (before: under the former id, the records were lost: nothing to pull)
        self.papers('edit mine2022 --set title=Corrected', cwd=self.path('pool'))
        out = self.papers('pull', cwd=lib, sp_cmd='check_output')
        self.assertIn('Modified -> mine2022: Corrected', out)
        self.assertIn('(in sync)', self.papers('status', cwd=lib, sp_cmd='check_output'))

    def test_file_named_after_the_pool_folder(self):
        self.papers('init sealevel')
        self.papers('init lib --pool ../sealevel')
        Path(self.path('new.bib')).write_text('@article{mine2022,\n title = {Mine},\n year = {2022}\n}\n')
        self.papers('add ../new.bib', cwd=self.path('lib'))
        self.papers('pull', cwd=self.path('lib'))
        names = os.listdir(self.path('lib', '.papers', 'origin'))
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].startswith('sealevel-'), names)
        self.assertIn('@comment{papers-pool-path', Path(self.path('lib', '.papers', 'origin', names[0])).read_text())
