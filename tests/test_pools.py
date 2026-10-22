"""Pools: resolution, origin copies, add from a pool, pull, push, sync,
export, status, libraries that are not local, and the conversions of
`papers config local` and `papers config pool`"""
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import papers.config
from papers.bib import Biblio
from papers.config import Config
from papers.duplicate import Distinct
from papers.entries import entry_from_dict, parse_string
from papers.pools import Pools, PoolError, Origin, ORIGIN_FILE, POOL_FIELD
from papers.utils import PapersExit

from tests import TEST_GLOBAL_POOL
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
    """a pool in pool/ (two entries, one with a file), and a local library
    in lib/ that uses it"""

    def setUp(self):
        super().setUp()
        self.papers('init pool --no-git --pool none')
        Path(self.path('pool', 'files', 'smith.pdf')).write_text('pdf of smith')
        Path(self.path('pool', 'papers.bib')).write_text(POOL_BIB)
        self.papers('init lib --no-git --pool ../pool --local')
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

    def config(self, pool=None):
        config = Config.load(self.path('lib', '.papersconfig.json'))
        if pool is None:
            config.unset('pool')
        else:
            config.set('pool', pool)
        return config

    def test_path_and_cache(self):
        pools = Pools(self.config('../pool'))
        pool = pools.pool()
        self.assertEqual(pool.path, self.path('pool'))
        self.assertEqual(pool.id, '../pool')
        self.assertIs(pools.all()[0], pool)
        self.assertEqual(len(pool.biblio.entries), 2)
        self.assertIs(pools.target(), pool)
        self.assertIs(pools.get(self.path('pool')), pool)

    def test_errors(self):
        os.makedirs(self.path('notalib'))
        pools = Pools(self.config('none'))
        self.assertIsNone(pools.pool())
        self.assertEqual(pools.all(), [])
        with self.assertRaisesRegex(PoolError, 'no pool'):
            pools.target()
        with self.assertRaisesRegex(PoolError, 'does not exist'):
            pools.get(self.path('missing', 'pool'))
        with self.assertRaisesRegex(PoolError, 'is not a library'):
            pools.get(self.path('notalib'))
        with self.assertRaisesRegex(PoolError, 'the library itself'):
            pools.get(self.path('lib'))

    def test_never_itself(self):
        self.assertIsNone(Pools(self.config('.')).pool())

    def test_missing_pool_is_a_warning(self):
        pools = Pools(self.config('../missing'))
        with self.assertLogs(papers.logger, level='WARNING'):
            self.assertEqual(pools.all(), [])
        # a pool created when written to, if its parent directory exists
        self.assertEqual(pools.target().path, self.path('missing'))
        with self.assertRaisesRegex(PoolError, 'does not exist'):
            Pools(self.config('../no/such/pool')).target()

    def test_global_pool_not_created_yet(self):
        pools = Pools(self.config())
        with self.assertNoLogs(papers.logger, level='WARNING'):
            self.assertEqual(pools.all(), [])
        with self.assertNoLogs(papers.logger, level='WARNING'):
            self.lib('config --unset pool')
            self.lib('pull')
        self.assertIn('(global pool, not created yet)', self.out('status'))
        self.assertFalse(os.path.exists(TEST_GLOBAL_POOL))
        pool = pools.target()  # created, quietly
        self.assertEqual(pool.path, TEST_GLOBAL_POOL)
        self.assertEqual(pool.id, 'global')
        self.assertEqual(pool.label, f'pool {papers.config.short_home(TEST_GLOBAL_POOL)}')
        self.assertEqual(pool.config.pool, 'none')
        self.assertTrue(pool.config.local)

    def test_push_to_missing_pool(self):
        with self.assertRaisesRegex(PapersExit, 'does not exist'):
            self.lib('push --pool ../no/such/pool')


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

    def test_global_pool_of_earlier_builds(self):
        # earlier v3 builds named the global pool `default`
        path = self.path('lib', ORIGIN_FILE)
        origin = Origin(path)
        origin.set('smith2020climate', 'default', parse_string(POOL_BIB).entries[0])
        origin.set_pulled('default', 12345)
        origin.save()
        origin = Origin.load(path)
        self.assertEqual(origin.records()[0].pool, 'global')
        self.assertEqual(origin.pulled('global'), 12345)

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

    def test_doi_with_fields(self):
        # the fields given on the command line apply to the library entry
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            self.lib('add --doi 10.1000/brown --title "Ocean heat, revised" --key brown')
        e = self.entry('brown')
        self.assertEqual(e['title'], 'Ocean heat, revised')
        self.assertEqual(self.origin().get(e).pool_key, 'Brown_2021')
        self.assertIn('{Ocean heat}', Path(self.path('pool', 'papers.bib')).read_text())  # the pool is unchanged

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
        self.assertNotIn('mine2022', self.bib('pool')[1])  # auto-push false
        self.assertEqual(len(self.origin()), 0)

    def test_auto_push(self):
        self.lib('config auto-push true')
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
        os.utime(self.path('pool', 'papers.bib'), ns=(1, 1))
        self.assertIn('changed since last pull or push', self.out('status'))  # the skip is not a pull

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
        before = self.origin().pulled('../pool')  # the add from the pool (setUp)
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        self.lib('pull 10.1000/abc123')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature')
        self.assertEqual(self.origin().pulled('../pool'), before)  # only a full pull counts as a pull

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
        self.assertIn('up to date', self.out('status'))
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        os.utime(self.path('pool', 'papers.bib'), ns=(1, 1))
        self.assertIn('changed since last pull or push', self.out('status'))
        out = self.out('pull --check')
        self.assertIn('pool ../pool: changed since last pull or push', out)
        self.assertIn('smith2020climate: changed in pool ../pool: journal', out)
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nat.')  # nothing pulled
        self.lib('pull')
        self.assertIn('up to date', self.out('status'))


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

    def test_pool_only_fields_come_with_the_next_pull(self):
        # the same paper on both sides, without origin record: each has a field of its own
        self.edit_pool('journal = {Nat.},', 'abstract = {From the pool.},\n journal = {Nat.},')
        self.lib('pull')  # an exchange with the pool before
        self.assertIn('up to date', self.out('status'))
        Path(self.path('smith.bib')).write_text(SMITH_BIB.replace('year = {2020}', 'keywords = {mine},\n year = {2020}'))
        self.lib('add ../smith.bib --no-pool')
        self.lib('push smith2020climate')
        self.assertEqual(self.entry('Smith_2020', 'pool')['keywords'], 'mine')
        self.assertNotIn('abstract', self.entry('smith2020climate'))  # push does not change the library
        # the origin is the library's version, sent: what the pool has beyond it is to pull
        self.assertNotIn('abstract', self.origin().get(self.entry('smith2020climate')).entry)
        self.assertIn('changed since last pull or push', self.out('status'))
        out = self.out('pull --check')
        self.assertIn('smith2020climate: changed in pool ../pool: abstract, file, journal', out)
        self.lib('pull')
        e = self.entry('smith2020climate')
        self.assertEqual((e['abstract'], e['journal'], e['keywords']), ('From the pool.', 'Nat.', 'mine'))
        self.assertIn('up to date', self.out('status'))
        self.assertIn('pull: 1 unchanged', self.out('pull'))
        self.assertIn('push to pool ../pool: 1 unchanged', self.out('push smith2020climate'))
        self.assertIn('up to date', self.out('status'))

    def test_push_keeps_a_pool_change(self):
        # a field changed in the pool only, during a push: kept in the pool, and pulled after
        self.lib('push')
        key = self.origin().get(self.entry('mine2022')).pool_key
        self.edit_pool('title = {My own paper}', 'title = {My own paper (pool)}')
        self.edit_lib('year = {2022}', 'journal = {J. Mine},\n year = {2022}')
        self.lib('push')
        self.assertEqual(self.entry(key, 'pool')['title'], 'My own paper (pool)')
        self.lib('push')  # the pool's title is not taken back by a second push
        self.assertEqual(self.entry(key, 'pool')['title'], 'My own paper (pool)')
        self.lib('pull')
        self.assertEqual(self.entry('mine2022')['title'], 'My own paper (pool)')

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
        self.assertIn('up to date', self.out('status'))

    def test_global_pool_created(self):
        self.lib('config --unset pool')
        out = self.out('push')
        self.assertNotIn('create the library', out)  # quietly
        self.assertTrue(os.path.exists(os.path.join(TEST_GLOBAL_POOL, '.papersconfig.json')))
        biblio = Biblio.load(os.path.join(TEST_GLOBAL_POOL, 'papers.bib'), '')
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
        # a library of its own, to hand over
        self.assertEqual(self.json('out')['pool'], 'none')
        self.assertIs(self.json('out')['local'], True)
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

    def test_export_then_pool(self):
        # `export --pool` of earlier builds: export, then make it the pool
        with self.assertRaises(SystemExit):
            self.lib('export ../out --pool --no-git')
        self.lib('export ../out --no-git')
        self.lib('config pool ../out')
        self.assertEqual(self.json('lib')['pool'], '../out')
        text = Path(self.path('out', 'papers.bib')).read_text()
        Path(self.path('out', 'papers.bib')).write_text(text.replace('title = {My own paper}', 'title = {My own paper},\n volume = {3}'))
        self.lib('pull --on-duplicate update')  # no origin copies yet: differences are conflicts
        self.assertEqual(self.entry('mine2022')['volume'], '3')
        self.assertEqual(self.origin().get(self.entry('mine2022')).pool, '../out')


# STATUS
# ======

class TestStatus(PoolTest):

    def test_status(self):
        out = self.out('status')
        self.assertIn('* pool:               ../pool (not pulled from yet)', out)
        self.assertIn('* local:              true', out)
        self.assertIn('* auto-push:          false', out)
        self.assertIn('* files mode:         link', out)  # the global configuration of the tests
        self.lib('config files copy')
        self.assertIn('* files mode:         copy', self.out('status'))
        self.lib('config auto-push true')
        self.assertIn('* auto-push:          true', self.out('status'))
        self.lib('config pool none')
        out = self.out('status')
        self.assertIn('* pool:               none', out)
        self.assertNotIn('auto-push', out)

    def test_after_add_from_pool(self):
        # the first exchange with the pool counts as a pull
        self.take_smith()
        self.assertIn('* pool:               ../pool (up to date)', self.out('status'))
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        os.utime(self.path('pool', 'papers.bib'), ns=(1, 1))
        self.assertIn('(changed since last pull or push)', self.out('status'))
        # a later push does not hide the change of the pool
        self.lib('push')
        self.assertIn('(changed since last pull or push)', self.out('status'))
        self.lib('pull')
        self.assertIn('(up to date)', self.out('status'))

    def test_partial_pull_is_not_an_exchange(self):
        self.take_smith()
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        os.utime(self.path('pool', 'papers.bib'), ns=(1, 1))
        self.lib('pull smith2020climate')
        self.assertIn('(changed since last pull or push)', self.out('status'))

    def test_after_add_to_the_global_pool(self):
        # a library that is not local: add places the entry in the global pool, created
        self.papers('config --global local false')
        self.papers('init other --no-git')
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        self.papers('add ../new.bib', cwd=self.path('other'))
        out = self.papers('status', cwd=self.path('other'), sp_cmd='check_output')
        self.assertIn(f'* pool:               {papers.config.short_home(TEST_GLOBAL_POOL)} (global pool, up to date)',
                      out)

    def test_missing_pool(self):
        self.lib('config pool ../missing')
        self.assertIn('../missing (', self.out('status'))
        self.assertIn('missing', self.out('status').split('../missing')[1])

    def test_pool_command_is_gone(self):
        with self.assertRaises(SystemExit):
            self.papers('pool list')


# LIBRARIES THAT ARE NOT LOCAL
# ============================

class NonLocalTest(PoolTest):
    """the library has files of its own (lib/files): mine2022 (not in the
    pool), and smith2020climate (a copy of the pool's file)"""

    def setUp(self):
        super().setUp()
        self.lib('config files copy')
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        self.lib('add ../new.bib')
        self.take_smith()
        self.lib_smith = self.files('smith2020climate')[0]
        self.lib_mine = self.files('mine2022')[0]


class TestConfigLocal(NonLocalTest):

    def test_local_false(self):
        out = self.out('config local false -y')
        self.assertIs(self.json('lib')['local'], False)
        self.assertIn('smith2020climate: link to the same file of the pool', out)
        self.assertIn('mine2022: added to the pool', out)
        # in the pool: relinked, the library's copy deleted
        self.assertEqual(self.files('smith2020climate'), [self.pool_pdf])
        self.assertFalse(os.path.exists(self.lib_smith))
        self.assertTrue(os.path.exists(self.pool_pdf))
        # not in the pool: moved there, with the pool's name template, and the entry added
        self.assertFalse(os.path.exists(self.lib_mine))
        mine = self.files('mine2022')
        self.assertTrue(mine[0].startswith(self.path('pool', 'files')), mine)
        key = self.origin().get(self.entry('mine2022')).pool_key
        pool_biblio, pool = self.bib('pool')
        self.assertEqual(pool_biblio.get_files(pool[key]), mine)
        self.assertEqual(os.listdir(self.path('lib', 'files')), [])
        self.assertIn('local:              false', self.out('status'))

    def test_same_paper_different_content(self):
        # moved to the pool, and attached to the pool entry
        Path(self.lib_smith).unlink()
        Path(self.lib_smith).write_text('another version')
        self.lib('config local false -y')
        files = self.files('smith2020climate')
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith(self.path('pool', 'files')))
        self.assertEqual(Path(files[0]).read_text(), 'another version')
        self.assertEqual(Path(self.pool_pdf).read_text(), 'pdf of smith')
        pool_biblio, pool = self.bib('pool')
        self.assertEqual(pool_biblio.get_files(pool['Smith_2020']), [self.pool_pdf, files[0]])

    def test_dry_run(self):
        out = self.out('config local false --dry-run')
        self.assertIn('nothing was changed', out)
        self.assertIs(self.json('lib')['local'], True)
        self.assertTrue(os.path.exists(self.lib_smith))
        self.assertTrue(os.path.exists(self.lib_mine))

    def test_no_terminal(self):
        with self.assertRaisesRegex(PapersExit, 'pass -y'):
            self.lib('config local false')
        self.assertIs(self.json('lib')['local'], True)
        self.assertTrue(os.path.exists(self.lib_smith))

    def test_prompt(self):
        with patch('papers.cli.library_cmds.stdin_is_terminal', lambda: True), \
                patch('builtins.input', lambda prompt: 'n'):
            self.lib('config local false')
        self.assertIs(self.json('lib')['local'], True)
        self.assertTrue(os.path.exists(self.lib_smith))
        with patch('papers.cli.library_cmds.stdin_is_terminal', lambda: True), \
                patch('builtins.input', lambda prompt: 'y'):
            self.lib('config local false')
        self.assertIs(self.json('lib')['local'], False)
        self.assertFalse(os.path.exists(self.lib_smith))

    def test_local_true(self):
        self.lib('config local false -y')
        out = self.out('config local true -y')
        self.assertIn('copy 2 files of the pool', out)
        self.assertIs(self.json('lib')['local'], True)
        for key in ('smith2020climate', 'mine2022'):
            files = self.files(key)
            self.assertTrue(files[0].startswith(self.path('lib', 'files')), files)
        self.assertTrue(os.path.samefile(self.files('smith2020climate')[0], self.pool_pdf))  # hard link
        self.assertTrue(os.path.exists(self.pool_pdf))

    def test_local_false_needs_a_pool(self):
        self.lib('config pool none')
        with self.assertRaisesRegex(PapersExit, 'needs a pool'):
            self.lib('config local false -y')

    def test_unset_local(self):
        with self.assertRaisesRegex(PapersExit, 'set in each library'):
            self.lib('config --unset local')

    def test_init_not_local(self):
        self.papers('config --global local false')
        self.papers('init other --no-git --pool ../pool')
        self.assertIs(self.json('other')['local'], False)
        self.papers('init third --no-git --pool ../pool --local')
        self.assertIs(self.json('third')['local'], True)
        out = self.papers('init fourth --no-git --pool none', sp_cmd='check_output')
        self.assertIn('the library is local', out)
        self.assertIs(self.json('fourth')['local'], True)
        self.papers('config --global pool none')
        self.papers('init fifth --no-git')
        self.assertEqual(self.json('fifth')['pool'], 'none')
        self.assertIs(self.json('fifth')['local'], True)

    def test_init_not_local_has_no_files_directory(self):
        # the files go to the pool: the files directory is created when needed
        self.papers('config --global local false')
        self.papers('init other --no-git --pool ../pool')
        self.assertFalse(os.path.exists(self.path('other', 'files')))
        self.assertIn('* files directory:    files (not created yet)',
                      self.papers('status', cwd=self.path('other'), sp_cmd='check_output'))
        self.papers('init third --no-git --pool ../pool --local')
        self.assertTrue(os.path.isdir(self.path('third', 'files')))
        self.papers('init fourth --no-git --pool none')
        self.assertTrue(os.path.isdir(self.path('fourth', 'files')))
        # the files of the pool are copied into it when the library becomes local
        Path(self.path('smith.bib')).write_text(SMITH_BIB)
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            self.papers('add ../smith.bib', cwd=self.path('other'))
        self.papers('config local true -y', cwd=self.path('other'))
        self.assertEqual(len(os.listdir(self.path('other', 'files'))), 1)

    def test_inconsistent_file(self):
        # local false without pool (written by hand): read as local, with a warning
        js = self.json('lib')
        js.update(pool='none', local=False)
        json.dump(js, open(self.path('lib', '.papersconfig.json'), 'w'))
        with self.assertLogs(papers.logger, level='WARNING'):
            config = Config.load(self.path('lib', '.papersconfig.json'))
        self.assertTrue(config.local)


class TestConfigPool(NonLocalTest):

    def setUp(self):
        super().setUp()
        self.lib('config local false -y')
        self.mine = self.files('mine2022')[0]
        self.papers('init other --no-git --pool none')

    def test_pool_none(self):
        out = self.out('config pool none -y')
        self.assertIn('so it becomes local', out)
        self.assertEqual(self.json('lib')['pool'], 'none')
        self.assertIs(self.json('lib')['local'], True)
        for key in ('smith2020climate', 'mine2022'):
            self.assertTrue(self.files(key)[0].startswith(self.path('lib', 'files')))
        self.assertTrue(os.path.exists(self.pool_pdf))  # the pool keeps its files

    def test_pool_none_no_terminal(self):
        with self.assertRaisesRegex(PapersExit, 'pass -y'):
            self.lib('config pool none')
        self.assertEqual(self.json('lib')['pool'], '../pool')

    def test_other_pool(self):
        # the other pool has smith already, with the same file
        Path(self.path('other', 'files', 'smith-copy.pdf')).write_text('pdf of smith')
        Path(self.path('other', 'papers.bib')).write_text(
            POOL_BIB.split('@article{Brown')[0].replace('files/smith.pdf', 'files/smith-copy.pdf'))
        out = self.out('config pool ../other -y')
        self.assertIn('smith2020climate: link to the same file of the pool', out)
        self.assertIn('mine2022: added to the pool', out)
        self.assertEqual(self.json('lib')['pool'], '../other')
        self.assertIs(self.json('lib')['local'], False)
        self.assertEqual(self.files('smith2020climate'), [self.path('other', 'files', 'smith-copy.pdf')])
        mine = self.files('mine2022')
        self.assertTrue(mine[0].startswith(self.path('other', 'files')), mine)
        # the old pool keeps its files
        self.assertTrue(os.path.exists(self.pool_pdf))
        self.assertTrue(os.path.exists(self.mine))
        self.assertTrue(os.path.samefile(mine[0], self.mine))  # a hard link
        self.assertEqual(self.origin().get(self.entry('mine2022')).pool, '../other')

    def test_new_pool_created(self):
        self.lib('config pool ../new -y')
        self.assertTrue(os.path.exists(self.path('new', '.papersconfig.json')))
        self.assertEqual(len(self.bib('new')[1]), 2)
        self.assertTrue(self.files('mine2022')[0].startswith(self.path('new', 'files')))

    def test_unset_pool(self):
        self.lib('config --unset pool -y')
        self.assertNotIn('pool', self.json('lib'))
        self.assertTrue(self.files('mine2022')[0].startswith(os.path.join(TEST_GLOBAL_POOL, 'files')))

    def test_local_library_just_sets(self):
        self.lib('config local true -y')
        files = self.files('mine2022')
        self.lib('config pool ../other')
        self.assertEqual(self.json('lib')['pool'], '../other')
        self.assertEqual(self.files('mine2022'), files)

    def test_pool_path_written_relative(self):
        self.lib('config local true -y')
        self.lib(f'config pool {self.path("other")}')
        self.assertEqual(self.json('lib')['pool'], self.path('other'))  # absolute
        self.lib('config pool ../other')
        self.assertEqual(self.json('lib')['pool'], '../other')  # written relative: relative
        self.lib(f'config pool {self.path("lib", "sub")}')
        self.assertEqual(self.json('lib')['pool'], './sub')  # under the library
        self.lib('config pool /elsewhere/pool')
        self.assertEqual(self.json('lib')['pool'], '/elsewhere/pool')


class TestNonLocal(NonLocalTest):

    def setUp(self):
        super().setUp()
        self.lib('push')
        self.lib('config local false -y')

    def test_rm_never_deletes_pool_files(self):
        out = self.out('rm smith2020climate --delete-files')
        self.assertTrue(os.path.exists(self.pool_pdf))
        self.assertIn('it is a file of a pool', out)
        self.assertNotIn('smith2020climate', self.bib()[1])

    def test_file_rm_never_deletes_pool_files(self):
        out = self.out(f'file rm {self.pool_pdf}')
        self.assertTrue(os.path.exists(self.pool_pdf))
        self.assertIn('it is a file of a pool', out)
        self.assertEqual(self.files('smith2020climate'), [])

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

    def test_file_attach_places_files_in_pool(self):
        Path(self.path('si.pdf')).write_text('supplement')
        self.lib(f'file attach smith2020climate {self.path("si.pdf")}')
        files = self.files('smith2020climate')
        self.assertEqual(files[0], self.pool_pdf)
        self.assertEqual(len(files), 2)
        self.assertTrue(files[1].startswith(self.path('pool', 'files')), files)
        self.assertEqual(os.listdir(self.path('lib', 'files')), [])
        pool = self.bib('pool')
        key = self.origin().get(self.entry('smith2020climate')).pool_key
        self.assertEqual(pool[0].get_files(pool[1][key]), files)  # the pool entry has the file too

    def test_file_rename_places_files_in_pool(self):
        Path(self.path('loose.pdf')).write_text('loose')
        biblio, entries = self.bib()
        biblio.set_files(entries['mine2022'], biblio.get_files(entries['mine2022']) + [self.path('loose.pdf')])
        biblio.save(self.path('lib', 'papers.bib'))
        self.lib('file rename mine2022')
        files = self.files('mine2022')
        self.assertTrue(all(f.startswith(self.path('pool', 'files')) for f in files), files)
        self.assertEqual(os.listdir(self.path('lib', 'files')), [])

    def test_add_to_global_pool(self):
        # the global pool is created quietly by the first add
        self.lib('config local true -y')
        self.lib('config --unset pool')
        self.lib('config local false -y')
        Path(self.path('other.bib')).write_text(NEW_BIB.replace('mine2022', 'other2023').replace(
            'My own paper', 'Another paper').replace('mine.pdf', 'other.pdf').replace('2022', '2023'))
        Path(self.path('other.pdf')).write_text('other')
        self.lib('add ../other.bib')
        files = self.files('other2023')
        self.assertTrue(files[0].startswith(os.path.join(TEST_GLOBAL_POOL, 'files')), files)

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


class TestLocalLibraryRepair(PoolTest):

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
