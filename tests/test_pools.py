"""Pools: resolution, origin copies, add from a pool, pull, push, export, the
pool command, light libraries, status"""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import papers.config
from papers.bib import Biblio
from papers.config import Config, MachineConfig
from papers.duplicate import Distinct
from papers.entries import entry_from_dict, parse_string
from papers.pools import Pools, PoolError, Origin, ORIGIN_FILE, POOL_FIELD
from papers.utils import PapersExit

from tests.common import ConfigTest


POOL_BIB = """@article{Smith_2020,
 author = {Smith, John and Doe, Jane},
 doi = {10.1000/abc123},
 file = {:files/smith.pdf:pdf},
 journal = {Nat.},
 title = {Climate sensitivity revisited},
 year = {2020}
}

@article{Brown_2021,
 author = {Brown, Bob},
 doi = {10.1000/brown},
 title = {Ocean heat},
 year = {2021}
}
"""

SMITH_BIB = """@article{smith2020climate,
 author = {Smith, John and Doe, Jane},
 doi = {10.1000/ABC123},
 title = {Climate sensitivity revisited},
 year = {2020}
}
"""

NEW_BIB = """@article{mine2022,
 author = {Mine, Me},
 file = {:mine.pdf:pdf},
 title = {My own paper},
 year = {2022}
}
"""


def no_fetch(*args, **kwargs):
    raise AssertionError('no network query expected')


class PoolTest(ConfigTest):
    """a pool in pool/ (two entries, one with a file), and a library in lib/
    that uses it"""

    def setUp(self):
        super().setUp()
        self.papers('init pool --no-git')
        Path(self.path('pool', 'files', 'smith.pdf')).write_text('pdf of smith')
        Path(self.path('pool', 'papers.bib')).write_text(POOL_BIB)
        self.papers('init lib --no-git --pool ../pool')
        self.pool_pdf = self.path('pool', 'files', 'smith.pdf')

    def lib(self, cmd, **kw):
        return self.papers(cmd, cwd=self.path('lib'), **kw)

    def out(self, cmd, cwd='lib'):
        return self.papers(cmd, cwd=self.path(cwd), sp_cmd='check_output')

    def bib(self, where='lib'):
        biblio = Biblio.load(self.path(where, 'papers.bib'), '')
        return biblio, {e.key: e for e in biblio.entries}

    def entry(self, key, where='lib'):
        return self.bib(where)[1][key]

    def files(self, key, where='lib'):
        biblio, entries = self.bib(where)
        return biblio.get_files(entries[key])

    def origin(self):
        return Origin.load(self.path('lib', ORIGIN_FILE))

    def edit_pool(self, old, new):
        text = Path(self.path('pool', 'papers.bib')).read_text()
        assert old in text, old
        Path(self.path('pool', 'papers.bib')).write_text(text.replace(old, new))

    def edit_lib(self, old, new):
        text = Path(self.path('lib', 'papers.bib')).read_text()
        assert old in text, old
        Path(self.path('lib', 'papers.bib')).write_text(text.replace(old, new))

    def take_smith(self, cmd='add ../smith.bib'):
        Path(self.path('smith.bib')).write_text(SMITH_BIB)
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            self.lib(cmd)


# RESOLUTION
# ==========

class TestResolution(PoolTest):

    def config(self, pools):
        config = Config.load(self.path('lib', '.papersconfig.json'))
        config.pools = pools
        return config

    def test_path_and_cache(self):
        pools = Pools(self.config(['../pool']))
        pool = pools.resolve('../pool')
        self.assertEqual(pool.path, self.path('pool'))
        self.assertEqual(pool.id, '../pool')
        self.assertIs(pools.all()[0], pool)
        self.assertEqual(len(pool.biblio.entries), 2)
        self.assertIs(pools.first(), pool)

    def test_name(self):
        self.papers(f'config --machine pools.shared {self.path("pool")}')
        pools = Pools(self.config(['shared']))
        self.assertEqual(pools.first().path, self.path('pool'))
        self.assertEqual(pools.first().id, 'shared')

    def test_errors(self):
        os.makedirs(self.path('notalib'))
        pools = Pools(self.config([]))
        with self.assertRaisesRegex(PoolError, 'unknown pool name: nope'):
            pools.resolve('nope')
        with self.assertRaisesRegex(PoolError, 'does not exist'):
            pools.resolve('../missing')
        with self.assertRaisesRegex(PoolError, 'is not a library'):
            pools.resolve('../notalib')
        with self.assertRaisesRegex(PoolError, 'is this library'):
            pools.resolve('.')
        with self.assertRaisesRegex(PoolError, 'no pools'):
            pools.first()

    def test_all_skips_self_and_missing(self):
        pools = Pools(self.config(['.', '../missing', '../pool']))
        self.assertEqual([p.id for p in pools.all()], ['../pool'])
        with self.assertRaisesRegex(PoolError, 'does not exist'):
            pools.first()  # push writes to the first pool: it must exist
        self.assertEqual(Pools(self.config(['.', '../pool'])).first().id, '../pool')  # never itself

    def test_unknown_name_is_a_warning(self):
        pools = Pools(self.config(['nope', '../pool']))
        with self.assertLogs(papers.logger, level='WARNING'):
            self.assertEqual([p.id for p in pools.all()], ['../pool'])

    def test_push_to_unknown_pool(self):
        with self.assertRaisesRegex(PapersExit, 'unknown pool name'):
            self.lib('push --pool nope')


# ORIGIN
# ======

class TestOrigin(PoolTest):

    def test_roundtrip(self):
        path = self.path('lib', ORIGIN_FILE)
        origin = Origin(path)
        pe = parse_string(POOL_BIB).entries[0]
        origin.set('smith2020climate', '../pool', pe)
        origin.set_pulled('../pool', 12345)
        origin.save()
        self.assertTrue(os.path.exists(path))
        origin = Origin.load(path)
        lib = entry_from_dict({'ID': 'smith2020climate', 'ENTRYTYPE': 'article'})
        record = origin.get(lib)
        self.assertEqual(record.pool, '../pool')
        self.assertEqual(record.pool_key, 'Smith_2020')
        self.assertTrue(record.time)
        self.assertEqual(record.entry.key, 'smith2020climate')
        self.assertEqual(record.entry['journal'], 'Nat.')
        self.assertNotIn('file', record.entry)
        self.assertNotIn(POOL_FIELD, record.entry)
        self.assertEqual(origin.pulled('../pool'), 12345)
        # by a former key
        renamed = entry_from_dict({'ID': 'newkey', 'ENTRYTYPE': 'article', 'ids': 'smith2020climate'})
        self.assertEqual(origin.get(renamed).pool_key, 'Smith_2020')
        # setting the same version again changes nothing
        origin.set('smith2020climate', '../pool', pe)
        self.assertFalse(origin.changed)

    def test_backup(self):
        self.lib('config git true')
        self.take_smith('add ../smith.bib')
        config = Config.load(self.path('lib', '.papersconfig.json'))
        backup = os.path.join(config.gitdir, ORIGIN_FILE)
        self.assertTrue(os.path.exists(backup))
        self.assertIn('smith2020climate', Path(backup).read_text())
        tracked = papers.backup.run_git(config.gitdir, ['ls-files'])
        self.assertIn(ORIGIN_FILE, str(tracked))


# ADD FROM A POOL
# ===============

class TestAdd(PoolTest):

    def test_bibtex(self):
        self.take_smith()
        e = self.entry('smith2020climate')
        self.assertEqual(e['journal'], 'Nat.')  # from the pool
        self.assertEqual(e['doi'], '10.1000/abc123')
        self.assertEqual(self.files('smith2020climate'), [self.pool_pdf])  # files: link (tests)
        record = self.origin().get(e)
        self.assertEqual((record.pool, record.pool_key), ('../pool', 'Smith_2020'))

    def test_doi(self):
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            self.lib('add --doi 10.1000/brown')
        biblio, entries = self.bib()
        self.assertEqual(len(entries), 1)
        e = list(entries.values())[0]
        self.assertEqual(e['title'], 'Ocean heat')
        self.assertEqual(self.origin().get(e).pool_key, 'Brown_2021')

    def test_pdf_same_content(self):
        Path(self.path('copy.pdf')).write_text('pdf of smith')
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch), \
             patch('papers.bib.extract_pdf_metadata', no_fetch):
            self.lib('add ../copy.pdf')
        biblio, entries = self.bib()
        e = list(entries.values())[0]
        self.assertEqual(e['journal'], 'Nat.')
        self.assertEqual(biblio.get_files(e), [self.pool_pdf])  # the pool's copy, once
        self.assertTrue(os.path.exists(self.path('copy.pdf')))

    def test_pdf_doi_in_text(self):
        Path(self.path('other.pdf')).write_text('another pdf')
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch), \
             patch('papers.bib.extract_pdf_metadata', no_fetch), \
             patch('papers.pools.parse_doi_from_pdf_metadata', lambda pdf: None), \
             patch('papers.pools.pdfhead', lambda pdf: 'Climate sensitivity revisited\ndoi:10.1000/abc123'), \
             patch('papers.pools.pdftail', lambda pdf: ''):
            self.lib('add ../other.pdf')
        biblio, entries = self.bib()
        e = list(entries.values())[0]
        self.assertEqual(e['journal'], 'Nat.')
        self.assertEqual(sorted(biblio.get_files(e)), sorted([self.pool_pdf, self.path('other.pdf')]))

    def test_copy_mode(self):
        self.lib('config files copy')
        self.take_smith()
        files = self.files('smith2020climate')
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith(self.path('lib', 'files')))
        self.assertTrue(os.path.samefile(files[0], self.pool_pdf))  # hard link
        self.assertTrue(os.path.exists(self.pool_pdf))

    def test_move_mode_never_moves_pool_files(self):
        self.lib('config files move')
        self.take_smith()
        files = self.files('smith2020climate')
        self.assertTrue(files[0].startswith(self.path('lib', 'files')))
        self.assertTrue(os.path.exists(self.pool_pdf))

    def test_library_name_template(self):
        self.lib('config files copy')
        self.lib('config name.template {title}')
        self.take_smith()
        self.assertEqual(os.path.basename(self.files('smith2020climate')[0]), 'climate-sensitivity-revisited.pdf')

    def test_no_pool(self):
        Path(self.path('smith.bib')).write_text(SMITH_BIB)
        self.lib('add ../smith.bib --no-pool')
        e = self.entry('smith2020climate')
        self.assertNotIn('journal', e)
        self.assertIsNone(self.origin().get(e))

    def test_new_entry_not_in_pool(self):
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        self.lib('add ../new.bib')
        self.assertIn('mine2022', self.bib()[1])
        self.assertNotIn('mine2022', self.bib('pool')[1])  # sync none
        self.assertEqual(len(self.origin()), 0)

    def test_sync_push(self):
        self.lib('config sync push')
        self.papers('config key.template {author}{year}', cwd=self.path('pool'))
        self.papers('config name.template {author}-{year}', cwd=self.path('pool'))
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        self.lib('add ../new.bib')
        self.assertIn('mine2022', self.bib()[1])
        pool = self.bib('pool')[1]
        self.assertIn('mine2022', pool)  # {author}{year} of the pool's template
        pool_files = self.bib('pool')[0].get_files(pool['mine2022'])
        self.assertEqual(pool_files, [self.path('pool', 'files', 'mine-2022.pdf')])
        self.assertEqual(self.origin().get(self.entry('mine2022')).pool_key, 'mine2022')
        # an entry taken from the pool is not added again
        self.take_smith()
        self.assertEqual(len(self.bib('pool')[1]), 3)


# PULL
# ====

class TestPull(PoolTest):

    def setUp(self):
        super().setUp()
        self.take_smith()
        self.edit_lib('year = {2020}', 'keywords = {mine},\n year = {2020}')

    def test_nothing_changed(self):
        out = self.out('pull')
        self.assertIn('pull: 1 unchanged', out)

    def test_pool_change_taken_library_change_kept(self):
        self.edit_pool('journal = {Nat.}', 'journal = {Nature},\n volume = {10}')
        self.lib('pull')  # no conflict: no question, even without terminal
        e = self.entry('smith2020climate')
        self.assertEqual(e['journal'], 'Nature')
        self.assertEqual(e['volume'], '10')
        self.assertEqual(e['keywords'], 'mine')
        self.assertEqual(self.origin().get(e).entry['journal'], 'Nature')

    def conflict(self):
        self.edit_pool('journal = {Nat.}', 'journal = {Nature Climate Change},\n volume = {10}')
        self.edit_lib('journal = {Nat.}', 'journal = {Nature}')

    def test_conflict_error(self):
        self.conflict()
        with self.assertRaisesRegex(PapersExit, 'changed in the library and in pool ../pool'):
            self.lib('pull')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature')
        self.assertNotIn('volume', self.entry('smith2020climate'))

    def test_conflict_keep(self):
        self.conflict()
        self.lib('pull --on-duplicate keep')
        e = self.entry('smith2020climate')
        self.assertEqual((e['journal'], e['volume']), ('Nature', '10'))
        self.assertEqual(self.origin().get(e).entry['journal'], 'Nature Climate Change')
        # next time: no conflict (the origin is the pool version)
        self.assertIn('pull: 1 unchanged', self.out('pull'))

    def test_conflict_update(self):
        self.conflict()
        self.lib('pull --on-duplicate update')
        e = self.entry('smith2020climate')
        self.assertEqual(e['journal'], 'Nature Climate Change')
        self.assertEqual(e['keywords'], 'mine')
        self.assertEqual(e.key, 'smith2020climate')

    def test_conflict_skip(self):
        self.conflict()
        self.lib('pull --on-duplicate skip')
        e = self.entry('smith2020climate')
        self.assertEqual(e['journal'], 'Nature')
        self.assertNotIn('volume', e)
        self.assertEqual(self.origin().get(e).entry['journal'], 'Nat.')  # not updated

    def test_conflict_ask(self):
        self.conflict()
        with patch('builtins.input', lambda prompt: '2'):
            self.lib('pull --on-duplicate ask')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature Climate Change')

    def test_key_never_changes(self):
        self.edit_pool('@article{Smith_2020,', '@article{Renamed_2020,')
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        self.lib('pull')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature')

    def test_new_pool_file(self):
        self.lib('config files copy')
        Path(self.path('pool', 'files', 'smith-si.pdf')).write_text('supplement')
        self.edit_pool('file = {:files/smith.pdf:pdf}', 'file = {:files/smith.pdf:pdf;:files/smith-si.pdf:pdf}')
        self.lib('pull')
        files = self.files('smith2020climate')
        self.assertEqual(len(files), 2)
        self.assertTrue(files[1].startswith(self.path('lib', 'files')))
        self.assertTrue(os.path.samefile(files[1], self.path('pool', 'files', 'smith-si.pdf')))

    def test_entry_without_origin_is_linked(self):
        Path(self.path('lib', ORIGIN_FILE)).unlink()
        out = self.out('pull')
        self.assertIn('linked: smith2020climate', out)
        self.assertIsNotNone(self.origin().get(self.entry('smith2020climate')))

    def test_select(self):
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        self.lib('pull 10.1000/abc123')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature')
        self.assertIsNone(self.origin().pulled('../pool'))  # only a full pull counts as a pull

    def test_distinct_merged(self):
        pool_distinct = Distinct.for_bibtex(self.path('pool', 'papers.bib'))
        pool_distinct.pairs.append([{'doi': '10.1/a'}, {'doi': '10.1/b'}])
        pool_distinct.changed = True
        pool_distinct.save()
        self.lib('pull')
        self.assertIn([{'doi': '10.1/a'}, {'doi': '10.1/b'}],
                      Distinct.for_bibtex(self.path('lib', 'papers.bib')).pairs)

    def test_check_and_status(self):
        self.lib('pull')
        self.assertIn('unchanged since last pull', self.out('status'))
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        os.utime(self.path('pool', 'papers.bib'), ns=(1, 1))
        self.assertIn('changed since last pull', self.out('status'))
        out = self.out('pull --check')
        self.assertIn('pool ../pool: changed since last pull', out)
        self.assertIn('smith2020climate: changed in pool ../pool: journal', out)
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nat.')  # nothing pulled
        self.lib('pull')
        self.assertIn('unchanged since last pull', self.out('status'))


# PUSH
# ====

class TestPush(PoolTest):

    def setUp(self):
        super().setUp()
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        self.lib('add ../new.bib')

    def test_new_entry(self):
        self.papers('config key.template {author}-{year}', cwd=self.path('pool'))
        self.lib('push')
        pool_biblio, pool = self.bib('pool')
        self.assertIn('mine-2022', pool)
        files = pool_biblio.get_files(pool['mine-2022'])
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith(self.path('pool', 'files')))
        self.assertTrue(os.path.exists(self.path('mine.pdf')))  # copied
        self.assertIn('mine2022', self.bib()[1])  # library key kept
        self.assertEqual(self.origin().get(self.entry('mine2022')).pool_key, 'mine-2022')
        self.assertIn('push to pool ../pool: 1 unchanged', self.out('push'))  # nothing new

    def test_pool_name_template(self):
        self.papers('config name.template {title}', cwd=self.path('pool'))
        self.lib('push')
        self.assertTrue(os.path.exists(self.path('pool', 'files', 'my-own-paper.pdf')))

    def test_changes(self):
        self.lib('push')
        key = self.origin().get(self.entry('mine2022')).pool_key
        self.edit_lib('year = {2022}', 'journal = {J. Mine},\n year = {2022}')
        self.edit_pool('title = {My own paper},', 'note = {pool note},\n title = {My own paper},')
        self.lib('push')
        e = self.entry(key, 'pool')
        self.assertEqual(e['journal'], 'J. Mine')
        self.assertEqual(e['note'], 'pool note')  # changed in the pool only: kept
        self.assertNotIn('note', self.entry('mine2022'))  # push does not change the library

    def conflict(self):
        self.lib('push')
        key = self.origin().get(self.entry('mine2022')).pool_key
        self.edit_lib('title = {My own paper}', 'title = {My own paper (library)}')
        self.edit_pool('title = {My own paper}', 'title = {My own paper (pool)}')
        return key

    def test_conflict_keep(self):
        key = self.conflict()
        self.lib('push --on-duplicate keep')
        self.assertEqual(self.entry(key, 'pool')['title'], 'My own paper (pool)')

    def test_conflict_update(self):
        key = self.conflict()
        self.lib('push --on-duplicate update')
        self.assertEqual(self.entry(key, 'pool')['title'], 'My own paper (library)')
        self.assertEqual(self.entry(key, 'pool').key, key)

    def test_conflict_error(self):
        self.conflict()
        with self.assertRaises(PapersExit):
            self.lib('push')

    def test_existing_pool_entry(self):
        # the same paper is in the pool, without origin record: merged, not added
        Path(self.path('smith.bib')).write_text(SMITH_BIB.replace('year = {2020}', 'volume = {10},\n year = {2020}'))
        self.lib('add ../smith.bib --no-pool')
        self.lib('push --on-duplicate keep smith2020climate')
        pool = self.bib('pool')[1]
        self.assertEqual(len(pool), 2)
        self.assertEqual(pool['Smith_2020']['volume'], '10')
        self.assertEqual(pool['Smith_2020']['doi'], '10.1000/abc123')

    def test_distinct_merged(self):
        lib = Distinct.for_bibtex(self.path('lib', 'papers.bib'))
        lib.pairs.append([{'doi': '10.1/a'}, {'doi': '10.1/b'}])
        lib.changed = True
        lib.save()
        self.lib('push')
        self.assertIn([{'doi': '10.1/a'}, {'doi': '10.1/b'}],
                      Distinct.for_bibtex(self.path('pool', 'papers.bib')).pairs)

    def test_status_after_push(self):
        self.lib('pull')
        self.lib('push')
        self.assertIn('unchanged since last pull', self.out('status'))

    def test_default_pool_created(self):
        self.lib('config pools default')
        self.lib('push')
        from tests import TEST_DEFAULT_POOL
        self.assertTrue(os.path.exists(os.path.join(TEST_DEFAULT_POOL, '.papersconfig.json')))
        biblio = Biblio.load(os.path.join(TEST_DEFAULT_POOL, 'papers.bib'), '')
        self.assertEqual(len(biblio.entries), 1)


# EXPORT
# ======

class TestExport(PoolTest):

    def setUp(self):
        super().setUp()
        self.lib('config files copy')
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        self.lib('add ../new.bib')
        self.take_smith()
        self.lib_pdf = self.files('mine2022')[0]

    def test_copy(self):
        self.lib('export ../out --no-git')
        biblio, entries = self.bib('out')
        self.assertEqual(sorted(entries), ['mine2022', 'smith2020climate'])
        files = biblio.get_files(entries['mine2022'])
        self.assertTrue(files[0].startswith(self.path('out', 'files')))
        self.assertTrue(os.path.samefile(files[0], self.lib_pdf))
        text = Path(self.path('out', 'papers.bib')).read_text()
        self.assertIn('file = {:files/', text)  # relative links
        self.assertTrue(os.path.exists(self.path('out', '.papersconfig.json')))
        # add of the folder restores it
        self.papers('init back --no-git')
        self.papers('add ../out --recursive --no-pool', cwd=self.path('back'))
        self.assertEqual(sorted(self.bib('back')[1]), ['mine2022', 'smith2020climate'])

    def test_selection_and_link(self):
        self.lib('export ../out mine2022 --files link --no-git')
        biblio, entries = self.bib('out')
        self.assertEqual(list(entries), ['mine2022'])
        self.assertEqual(biblio.get_files(entries['mine2022']), [self.lib_pdf])
        self.assertIn('file = {:../lib/files/', Path(self.path('out', 'papers.bib')).read_text())

    def test_none(self):
        self.lib('export ../out --files none --no-git')
        self.assertNotIn('file', self.entry('mine2022', 'out'))
        self.assertEqual(os.listdir(self.path('out', 'files')), [])

    def test_not_empty(self):
        os.makedirs(self.path('out'))
        Path(self.path('out', 'x')).write_text('x')
        with self.assertRaisesRegex(PapersExit, 'not an empty directory'):
            self.lib('export ../out --no-git')

    def test_pool(self):
        self.lib('export ../out --pool --no-git')
        self.assertEqual(self.json('lib')['pools'], ['../pool', '../out'])
        record = self.origin().get(self.entry('mine2022'))
        self.assertEqual(record.pool, '../out')
        # the new pool is used by pull
        text = Path(self.path('out', 'papers.bib')).read_text()
        Path(self.path('out', 'papers.bib')).write_text(text.replace('title = {My own paper}', 'title = {My own paper},\n volume = {3}'))
        self.lib('pull')
        self.assertEqual(self.entry('mine2022')['volume'], '3')


# POOL COMMAND
# ============

class TestPoolCommand(PoolTest):

    def test_add_list_remove(self):
        self.papers(f'pool add shared {self.path("pool")}')
        self.assertEqual(MachineConfig.load().pool_path('shared'), self.path('pool'))
        self.assertEqual(self.papers('config --machine pools.shared', sp_cmd='check_output'), self.path('pool'))
        out = self.out('pool list')
        self.assertIn(f'shared: {self.path("pool")}', out)
        self.assertIn('default:', out)
        self.assertIn('pools of the library', out)
        self.assertIn(self.path('pool') + ' (not pulled from yet)', out)
        self.papers('pool remove shared')
        self.assertNotIn('shared', MachineConfig.load().pools)
        with self.assertRaises(PapersExit):
            self.papers('pool remove shared')

    def test_add_not_a_library(self):
        with self.assertLogs(papers.logger, level='WARNING'):
            self.papers(f'pool add x {self.path("nothing")}')

    def test_status(self):
        out = self.out('status')
        self.assertIn('* pools:', out)
        self.assertIn(self.path('pool'), out)
        self.assertIn('* light:              no', out)
        self.assertIn('* sync:               none', out)
        self.lib('config sync push')
        self.assertIn('* sync:               push', self.out('status'))


# LIGHT LIBRARIES
# ===============

class LightTest(PoolTest):

    def setUp(self):
        super().setUp()
        self.lib('config files copy')
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        self.lib('add ../new.bib')
        self.take_smith()
        self.lib_smith = self.files('smith2020climate')[0]
        self.lib_mine = self.files('mine2022')[0]


class TestMigrateLight(LightTest):

    def test_light(self):
        out = self.out('migrate --light')
        self.assertTrue(self.json('lib')['light'])
        # in the pool: relinked, the library's copy deleted
        self.assertEqual(self.files('smith2020climate'), [self.pool_pdf])
        self.assertFalse(os.path.exists(self.lib_smith))
        self.assertTrue(os.path.exists(self.pool_pdf))
        # not in the pool: kept and listed
        self.assertEqual(self.files('mine2022'), [self.lib_mine])
        self.assertTrue(os.path.exists(self.lib_mine))
        self.assertIn('mine2022: some of its files are not in the pool', out)
        self.assertIn('papers push', out)
        self.assertIn('light:              yes', self.out('status'))

    def test_push_then_light(self):
        self.lib('push')
        self.lib('migrate --light')
        self.assertTrue(self.files('mine2022')[0].startswith(self.path('pool', 'files')))
        self.assertFalse(os.path.exists(self.lib_mine))
        self.assertEqual(os.listdir(self.path('lib', 'files')), [])

    def test_same_paper_different_content_is_kept(self):
        Path(self.lib_smith).unlink()
        Path(self.lib_smith).write_text('another version')
        self.lib('migrate --light')
        self.assertEqual(self.files('smith2020climate'), [self.lib_smith])
        self.assertTrue(os.path.exists(self.lib_smith))

    def test_dry_run(self):
        self.lib('migrate --light --dry-run')
        self.assertNotIn('light', self.json('lib'))
        self.assertTrue(os.path.exists(self.lib_smith))

    def test_full(self):
        self.lib('push')
        self.lib('migrate --light')
        self.lib('migrate --full')
        self.assertNotIn('light', self.json('lib'))
        for key in ('smith2020climate', 'mine2022'):
            files = self.files(key)
            self.assertTrue(files[0].startswith(self.path('lib', 'files')), files)
        self.assertTrue(os.path.samefile(self.files('smith2020climate')[0], self.pool_pdf))
        self.assertTrue(os.path.exists(self.pool_pdf))

    def test_config_refuses_light(self):
        with self.assertRaisesRegex(PapersExit, 'migrate --light'):
            self.lib('config light true')

    def test_init_light(self):
        self.papers('init other --no-git --light --pool ../pool')
        self.assertTrue(self.json('other')['light'])


class TestLight(LightTest):

    def setUp(self):
        super().setUp()
        self.lib('push')
        self.lib('migrate --light')

    def test_rm_never_deletes_pool_files(self):
        out = self.out('rm smith2020climate --delete-files')
        self.assertTrue(os.path.exists(self.pool_pdf))
        self.assertIn('it is a file of a pool', out)
        self.assertNotIn('smith2020climate', self.bib()[1])

    def test_add_places_files_in_pool(self):
        self.papers('config name.template {title}', cwd=self.path('pool'))
        Path(self.path('other.bib')).write_text(NEW_BIB.replace('mine2022', 'other2023').replace(
            'My own paper', 'Another paper').replace('mine.pdf', 'other.pdf').replace('2022', '2023'))
        Path(self.path('other.pdf')).write_text('other')
        self.lib('add ../other.bib')
        files = self.files('other2023')
        self.assertEqual(files, [self.path('pool', 'files', 'another-paper.pdf')])
        self.assertTrue(os.path.exists(self.path('other.pdf')))  # files: copy
        pool = self.bib('pool')[1]
        key = self.origin().get(self.entry('other2023')).pool_key
        self.assertEqual(self.bib('pool')[0].get_files(pool[key]), files)

    def test_add_from_pool_links_to_pool_file(self):
        self.lib('rm smith2020climate --keep-files')
        self.take_smith()
        self.assertEqual(self.files('smith2020climate'), [self.pool_pdf])
        self.assertEqual(os.listdir(self.path('pool', 'files')).count('smith.pdf'), 1)
        self.assertEqual(len(self.bib('pool')[1]), 3)  # not added again

    def test_pull_links_to_pool_files(self):
        Path(self.path('pool', 'files', 'smith-si.pdf')).write_text('supplement')
        text = Path(self.path('pool', 'papers.bib')).read_text()
        Path(self.path('pool', 'papers.bib')).write_text(
            text.replace('file = {:files/smith.pdf:pdf}', 'file = {:files/smith.pdf:pdf;:files/smith-si.pdf:pdf}'))
        self.lib('pull')
        self.assertEqual(self.files('smith2020climate'), [self.pool_pdf, self.path('pool', 'files', 'smith-si.pdf')])

    def rename_in_pool(self):
        new = self.path('pool', 'files', 'renamed.pdf')
        os.rename(self.pool_pdf, new)
        text = Path(self.path('pool', 'papers.bib')).read_text()
        Path(self.path('pool', 'papers.bib')).write_text(text.replace('files/smith.pdf', 'files/renamed.pdf'))
        return new

    def test_broken_link_repaired_on_load(self):
        new = self.rename_in_pool()
        self.lib('tag smith2020climate --add x')  # any command that writes
        self.assertEqual(self.files('smith2020climate'), [new])

    def test_file_check_fix(self):
        new = self.rename_in_pool()
        out = self.out('file check')
        self.assertIn('broken link to a pool file', out)
        self.assertIn('fix with --fix', out)
        self.assertNotEqual(self.files('smith2020climate'), [new])
        self.lib('file check --fix')
        self.assertEqual(self.files('smith2020climate'), [new])


class TestFullLibraryRepair(PoolTest):

    def test_file_check_fix(self):
        self.take_smith()  # files: link, the entry links to the pool file
        new = self.path('pool', 'files', 'renamed.pdf')
        os.rename(self.pool_pdf, new)
        text = Path(self.path('pool', 'papers.bib')).read_text()
        Path(self.path('pool', 'papers.bib')).write_text(text.replace('files/smith.pdf', 'files/renamed.pdf'))
        self.lib('file check --fix')
        self.assertEqual(self.files('smith2020climate'), [new])


if __name__ == '__main__':
    unittest.main()
