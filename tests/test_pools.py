"""Pools: resolution, origin copies, add from a pool, pull, push, export, the
pool command, light libraries, status"""
import io
import json
import os
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import papers.config
from papers.bib import Biblio
from papers.config import Config, MachineConfig
from papers.duplicate import Distinct
from papers.entries import entry_from_dict, parse_string
from papers.pools import Pools, PoolError, Origin, ORIGIN_FILE, POOL_FIELD
from papers.utils import PapersExit

from tests.test_config_v3 import ConfigTest


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
             patch('papers.extract.parse_doi_from_pdf_metadata', lambda pdf: None), \
             patch('papers.extract.pdfhead', lambda pdf: 'Climate sensitivity revisited\ndoi:10.1000/abc123'), \
             patch('papers.extract.pdftail', lambda pdf: ''):
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


if __name__ == '__main__':
    unittest.main()
