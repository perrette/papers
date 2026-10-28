"""Pools: resolution, origin copies, add from a pool, pull, push, sync,
export, status, shallow libraries, and the conversions of `papers config
pool`"""
import json
import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

import papers.backup
import papers.config
from papers.bib import Biblio
from papers.config import Config, CONFIG_FILE_LOCAL
from papers.duplicate import Distinct
from papers.entries import entry_from_dict, parse_string
from papers.pools import Pools, PoolError, Origin, ORIGIN_DIR, LEGACY_ORIGIN_FILE, POOL_FIELD, origin_file_name
from papers.utils import PapersExit

from tests import TEST_DEFAULT_LIBRARY
from tests.common import ConfigTest, pool_id


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


# the commands that exchange with another library (--pool PATH)
EXCHANGES = ('add', 'pull', 'push', 'sync')


class PoolTest(ConfigTest):
    """a library in pool/ (two entries, one with a file), and a
    self-contained library in lib/ that exchanges entries with it: `lib`
    and `out` add `--pool ../pool` to add, pull, push and sync, unless the
    command has --pool or --no-pool, or the library has a pool (a shallow
    library: its pool is the default)"""

    def setUp(self):
        super().setUp()
        self.papers('init pool')
        Path(self.path('pool', 'files', 'smith.pdf')).write_text('pdf of smith')
        Path(self.path('pool', 'papers.bib')).write_text(POOL_BIB)
        self.papers('init lib')
        self.pool_pdf = self.path('pool', 'files', 'smith.pdf')

    def with_pool(self, cmd, cwd):
        words = cmd.split()
        if not words or words[0] not in EXCHANGES or '--pool' in words or '--no-pool' in words:
            return cmd
        if os.path.realpath(cwd) != os.path.realpath(self.path('lib')):
            return cmd
        if json.load(open(self.path('lib', CONFIG_FILE_LOCAL))).get('pool', 'none') != 'none':
            return cmd
        return cmd + ' --pool ../pool'

    def lib(self, cmd, **kw):
        return self.papers(self.with_pool(cmd, self.path('lib')), cwd=self.path('lib'), **kw)

    def out(self, cmd, cwd='lib'):
        return self.papers(self.with_pool(cmd, self.path(cwd)), cwd=self.path(cwd), sp_cmd='check_output')

    def state(self):
        "the state of the pool for the library, as `pull --check` gives it (the pool of `status`)"
        return self.out('pull --check').splitlines()[0]

    def bib(self, where='lib'):
        biblio = Biblio.load(self.path(where, 'papers.bib'), '')
        return biblio, {e.key: e for e in biblio.entries}

    def entry(self, key, where='lib'):
        return self.bib(where)[1][key]

    def files(self, key, where='lib'):
        biblio, entries = self.bib(where)
        return biblio.get_files(entries[key])

    def origin(self):
        return Origin.load(self.path('lib', ORIGIN_DIR))

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
        config = Config.load(self.path('lib', CONFIG_FILE_LOCAL))
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
        self.assertEqual(len(pool.biblio.entries), 2)
        self.assertIs(pools.target(), pool)
        self.assertIs(pools.get(self.path('pool')), pool)

    def test_errors(self):
        os.makedirs(self.path('notalib'))
        pools = Pools(self.config('none'))
        self.assertIsNone(pools.pool())
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
            self.assertIsNone(pools.pool())
        # writing to it is an error too: no pool is created
        with self.assertRaisesRegex(PoolError, r'does not exist: create it first with `papers init .*missing`'):
            pools.target()
        self.assertFalse(os.path.exists(self.path('missing')))
        with self.assertRaisesRegex(PoolError, r'does not exist \(disk not mounted\?\): create it first'):
            Pools(self.config('../no/such/pool')).target()

    def test_no_pool_setting(self):
        # a library that does not set its pool has none (self-contained), even with a default library
        os.makedirs(TEST_DEFAULT_LIBRARY)
        self.papers('init', cwd=TEST_DEFAULT_LIBRARY)
        Path(TEST_DEFAULT_LIBRARY, 'papers.bib').write_text(POOL_BIB)
        self.papers(f'config --global default {TEST_DEFAULT_LIBRARY}')
        self.lib('config --unset pool')
        self.assertNotIn('pool', self.json('lib'))
        config = Config.load(self.path('lib', CONFIG_FILE_LOCAL))
        self.assertIsNone(config.pool_path())
        self.assertEqual(self.out('config pool'), 'none')
        self.assertRegex(self.out('config'), r'\npool += none  \(default\)\n')
        out = self.out('status')
        self.assertIn('* files:  files (the files directory of the library', out)
        self.assertNotIn('* pool:', out)  # self-contained: no pool line
        self.assertNotIn('* pool:', self.out('status -v'))
        # no lookups in the default library: the entry is added as it is, not taken from there
        Path(self.path('smith.bib')).write_text(SMITH_BIB)
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            self.papers('add ../smith.bib', cwd=self.path('lib'))
        self.assertEqual(list(self.bib()[1]), ['smith2020climate'])
        self.assertNotIn('journal', self.entry('smith2020climate'))
        self.assertEqual(len(self.origin()), 0)
        for cmd in ['push --all', 'pull', 'sync', 'pull --check']:
            with self.assertRaisesRegex(PapersExit, r'^this library has no pool: give one with `--pool PATH`$'):
                self.papers(cmd, cwd=self.path('lib'))

    def test_v2_project_library(self):
        # a project library of papers 2: self-contained, as in papers 2, even with a default library
        os.makedirs(TEST_DEFAULT_LIBRARY)
        self.papers('init', cwd=TEST_DEFAULT_LIBRARY)
        Path(TEST_DEFAULT_LIBRARY, 'papers.bib').write_text(POOL_BIB)
        self.papers(f'config --global default {TEST_DEFAULT_LIBRARY}')
        json.dump({'bibtex': 'papers.bib', 'filesdir': 'files', 'local': True},
                  open(self.path('lib', CONFIG_FILE_LOCAL), 'w'))
        self.assertNotIn('* pool:', self.out('status'))
        self.assertNotIn('* pool:', self.out('status -v'))
        Path(self.path('smith.bib')).write_text(SMITH_BIB)
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            self.papers('add ../smith.bib', cwd=self.path('lib'))
        self.assertEqual(list(self.bib()[1]), ['smith2020climate'])
        self.assertNotIn('journal', self.entry('smith2020climate'))  # not taken from the default library
        self.assertEqual(len(Biblio.load(os.path.join(TEST_DEFAULT_LIBRARY, 'papers.bib'), '').entries), 2)

    def test_missing_library_is_never_created(self):
        # every command that takes a library as pool: an error, nothing created
        missing = r'\S+/no/such does not exist \(disk not mounted\?\): create it first with `papers init \S+/no/such/pool`'
        lib_json = self.json('lib')
        for cmd in ['config pool ../no/such/pool -y', 'add --pool ../no/such/pool --doi 10.1000/abc123',
                    'pull --pool ../no/such/pool', 'sync --all --pool ../no/such/pool']:
            with self.assertRaisesRegex(PapersExit, missing):
                self.lib(cmd)
        with self.assertRaisesRegex(PapersExit, missing):
            self.papers('init other --pool ../no/such/pool')
        self.assertFalse(os.path.exists(self.path('no')))
        self.assertFalse(os.path.exists(self.path('other')))
        self.assertEqual(self.json('lib'), lib_json)

    def test_push_to_missing_pool(self):
        # nothing is created: neither the pool nor its parent folder (a disk not mounted?)
        for cmd in ['push --pool ../no/such/pool', 'push --all --pool ../no/such/pool']:
            with self.assertRaisesRegex(PapersExit, r'no/such/pool: \S+/no/such does not exist \(disk not mounted\?\): '
                                                    r'create it first with `papers init .*no/such/pool`'):
                self.lib(cmd)
        self.assertFalse(os.path.exists(self.path('no')))
        # a missing pool whose parent folder exists is not created either
        with self.assertRaisesRegex(PapersExit, r'pool .*newpool does not exist: create it first with '
                                                r'`papers init .*newpool` \(nothing was changed\)'):
            self.lib('push --all --pool ../newpool')
        self.assertFalse(os.path.exists(self.path('newpool')))


# ORIGIN
# ======

class TestOrigin(PoolTest):

    def test_roundtrip(self):
        path = self.path('lib', ORIGIN_DIR)
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

    def test_file_names(self):
        self.assertRegex(origin_file_name('~/Documents/papers'), r'^papers-[0-9a-f]{6}\.bib$')
        name = origin_file_name('../shared-with-bob')
        self.assertRegex(name, r'^shared-with-bob-[0-9a-f]{6}\.bib$')
        self.assertNotEqual(name, origin_file_name('/data/shared-with-bob'))
        self.assertRegex(origin_file_name('/data/Lab Papers/'), r'^lab-papers-[0-9a-f]{6}\.bib$')

    def test_one_file_per_pool(self):
        path = self.path('lib', ORIGIN_DIR)
        origin = Origin(path)
        pe = parse_string(POOL_BIB).entries[0]
        origin.set('smith2020climate', '../pool', pe)
        origin.set('smith2020climate', '~/Documents/papers', pe)
        origin.set_pulled('~/Documents/papers', 12345)
        origin.save()
        name = origin_file_name('~/Documents/papers')
        self.assertEqual(sorted(os.listdir(path)), sorted([name, origin_file_name('../pool')]))
        text = Path(path, name).read_text()
        self.assertTrue(text.startswith('@comment{papers-pool ~/Documents/papers}\n'), text)
        self.assertIn('@comment{papers-pulled 12345}', text)
        self.assertNotIn(POOL_FIELD + ' =', text)
        origin = Origin.load(path)
        lib = entry_from_dict({'ID': 'smith2020climate', 'ENTRYTYPE': 'article'})
        self.assertEqual((origin.get(lib, '~/Documents/papers').pool, origin.get(lib, '../pool').pool),
                         ('~/Documents/papers', '../pool'))
        self.assertIsNone(origin.get(lib, '../other'))
        self.assertEqual((origin.pulled('~/Documents/papers'), origin.pulled('../pool')), (12345, None))
        self.assertEqual(len(origin), 2)

    def test_migration(self):
        # earlier v3 builds: one file, .papers/origin.bib, with a papers-pool
        # field and papers-pull comments
        legacy = self.path('lib', LEGACY_ORIGIN_FILE)
        os.makedirs(os.path.dirname(legacy), exist_ok=True)
        Path(legacy).write_text(
            '@comment{papers-pull 12345 ../other}\n\n@comment{papers-pull 678 ../pool}\n\n'
            '@article{a2020,\n papers-pool = {../other},\n papers-pool-key = {A_2020},\n title = {A}\n}\n\n'
            '@article{b2020,\n papers-pool = {../pool},\n papers-pool-key = {B_2020},\n title = {B}\n}\n')
        origin = Origin.load(self.path('lib', ORIGIN_DIR))
        self.assertFalse(os.path.exists(legacy))
        self.assertEqual(sorted(os.listdir(self.path('lib', ORIGIN_DIR))),
                         sorted([origin_file_name('../other'), origin_file_name('../pool')]))
        self.assertEqual([(r.key, r.pool, r.pool_key) for r in origin.records()],
                         [('a2020', '../other', 'A_2020'), ('b2020', '../pool', 'B_2020')])
        self.assertEqual((origin.pulled('../other'), origin.pulled('../pool')), (12345, 678))
        self.assertNotIn(POOL_FIELD, origin.records()[0].entry.fields_dict)
        again = Origin.load(self.path('lib', ORIGIN_DIR))
        self.assertEqual(len(again), 2)
        self.assertEqual(again.pulled('../pool'), 678)

    def test_history(self):
        self.take_smith('add ../smith.bib')
        config = Config.load(self.path('lib', CONFIG_FILE_LOCAL))
        name = os.path.join(ORIGIN_DIR, origin_file_name('../pool'))
        project, place = papers.backup.project_of(config, create=False)
        state = project.state(project.head(place)['state'])
        self.assertIn('smith2020climate', project.store.text(state['files'][name]))
        # a file removed from the library leaves the next state
        os.remove(self.path('lib', name))
        self.lib('tag smith2020climate --add x')
        project = papers.backup.project_of(config, create=False)[0]
        self.assertNotIn(name, project.state(project.head(place)['state'])['files'])


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

    def test_key(self):
        # --key alone: the pool entry of that key (ignoring case), as --doi does
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            out = self.out('add --key smith_2020')
        self.assertRegex(out, r'^Added -> Smith_2020: .* \[from pool ../pool\]$')
        e = self.entry('Smith_2020')
        self.assertEqual(e['journal'], 'Nat.')
        self.assertEqual(self.files('Smith_2020'), [self.pool_pdf])
        self.assertEqual(self.origin().get(e).pool_key, 'Smith_2020')
        # already in the library
        out = self.out('add --key Smith_2020')
        self.assertIn('already in library: Smith_2020', out)
        self.assertEqual(len(self.bib()[1]), 1)

    def test_key_not_found(self):
        before = Path(self.path('lib', 'papers.bib')).read_text()
        pool_before = Path(self.path('pool', 'papers.bib')).read_text()
        with self.assertRaisesRegex(PapersExit, r'nothing to add: no file, identifier or bibtex given, '
                                    r'and no entry nope2020 in pool ../pool'):
            self.lib('add --key nope2020')
        with self.assertRaisesRegex(PapersExit, r'no entry Smith_2020 in the library \(--no-pool\)'):
            self.lib('add --key Smith_2020 --no-pool')
        self.assertEqual(Path(self.path('lib', 'papers.bib')).read_text(), before)
        self.assertEqual(Path(self.path('pool', 'papers.bib')).read_text(), pool_before)

    def test_no_empty_entry(self):
        Path(self.path('a.pdf')).write_text('a')
        with self.assertRaisesRegex(PapersExit, 'nothing to add: the entry has no fields or no key'):
            self.lib('add --attach ../a.pdf')
        self.assertEqual(len(self.bib()[1]), 0)

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

    def test_pdf_same_content_move_mode(self):
        # the PDF given is stored already (the pool's file): with move, it is removed
        for mode, kept in [('copy', True), ('link', True), ('move', False)]:
            with self.subTest(mode=mode):
                Path(self.path('lib', 'papers.bib')).write_text('')
                Path(self.path('copy.pdf')).write_text('pdf of smith')
                with patch('papers.bib.fetch_bibtex_by_doi', no_fetch), \
                     patch('papers.bib.extract_pdf_metadata', no_fetch):
                    self.lib(f'add ../copy.pdf --{mode}')
                biblio, entries = self.bib()
                files = biblio.get_files(list(entries.values())[0])
                self.assertEqual(len(files), 1)
                self.assertTrue(os.path.samefile(files[0], self.pool_pdf))
                self.assertEqual(os.path.exists(self.path('copy.pdf')), kept)
                self.assertTrue(os.path.exists(self.pool_pdf))

    def test_attachment_different_content_move_mode(self):
        # a different version is attached as another file, and moved
        Path(self.path('other.pdf')).write_text('another version')
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            self.lib('add --doi 10.1000/abc123 --attach ../other.pdf --move')
        biblio, entries = self.bib()
        files = biblio.get_files(list(entries.values())[0])
        self.assertEqual(len(files), 2)
        self.assertFalse(os.path.exists(self.path('other.pdf')))
        self.assertEqual(Path(files[1]).read_text(), 'another version')

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

    def test_auto_push_ignored_without_pool(self):
        # a self-contained library pushes nothing on its own, and add --pool sends nothing to PATH
        self.lib('config auto-push true')
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        self.lib('add ../new.bib')
        self.assertIn('mine2022', self.bib()[1])
        self.assertNotIn('mine2022', self.bib('pool')[1])
        self.take_smith()
        self.lib('tag smith2020climate --add x')
        self.assertEqual(len(self.bib('pool')[1]), 2)
        self.assertNotIn('keywords', self.entry('Smith_2020', 'pool'))


# PULL
# ====

class TestPull(PoolTest):

    def setUp(self):
        super().setUp()
        self.take_smith()
        self.edit_lib('year = {2020}', 'keywords = {mine},\n year = {2020}')

    def test_nothing_changed(self):
        out = self.out('pull')
        self.assertIn('nothing to pull from pool ../pool', out)

    def test_key_changed(self):
        # the record of the exchange follows the key (papers edit --key)
        self.lib('edit smith2020climate --key smith2020')
        e = self.entry('smith2020')
        self.assertEqual(self.origin().get(e).key, 'smith2020')
        self.assertIn('nothing to pull from pool ../pool', self.out('pull'))
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        self.lib('pull')
        self.assertEqual(self.entry('smith2020')['journal'], 'Nature')
        self.assertEqual(list(self.bib()[1]), ['smith2020'])

    def test_nothing_to_pull_is_not_saved(self):
        self.lib('pull')
        with patch('papers.bib.Biblio.save') as save:
            self.lib('pull')
        save.assert_not_called()

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
        self.assertIn('nothing to pull from pool ../pool', self.out('pull'))

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
        self.assertIn('changed since last pull or push', self.state())  # the skip is not a pull
        # a shallow library: status says it too
        self.lib('config pool ../pool -y')
        out = self.out('status')
        self.assertIn('../pool (both changed)', out)  # the conflict: changed on both sides
        self.assertIn('`papers sync --dry-run` shows the changes', out)

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

    def test_entry_without_origin_is_shared(self):
        # without KEY or --all, pull updates the entries whose paper the pool has, with an origin record or not
        shutil.rmtree(self.path('lib', ORIGIN_DIR))
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        # without origin record, no base for the merge: the change is a conflict
        with self.assertRaisesRegex(PapersExit, '1 conflict'):
            self.out('pull')
        self.out('pull --on-duplicate update')
        self.assertIsNotNone(self.origin().get(self.entry('smith2020climate')))
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature')

    def test_recorded_pool_entry_among_same_papers(self):
        "the pool has the paper twice: the pool entry of the origin record is the one pulled"
        self.edit_pool('@article{Smith_2020,', SMITH_BIB.replace('smith2020climate', 'Aaa_2020')
                       .replace('year', 'journal = {Other},\n year') + '\n@article{Smith_2020,')
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        self.lib('pull')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature')
        self.assertEqual(self.origin().get(self.entry('smith2020climate')).pool_key, 'Smith_2020')

    def test_pool_key_of_another_paper(self):
        "the pool key of the record now names another paper: the pool entry is found by its identity"
        self.edit_pool('@article{Smith_2020,', '@article{Smith_2020x,')
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        self.edit_pool('@article{Brown_2021,', '@article{Smith_2020,\n doi = {10.1000/other},\n title = {Other},\n'
                       ' year = {2020}\n}\n\n@article{Brown_2021,')
        self.lib('pull')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature')
        self.assertEqual(self.origin().get(self.entry('smith2020climate')).pool_key, 'Smith_2020x')

    def test_entry_without_origin_is_linked(self):
        for cmd in ['pull smith2020climate', 'pull --all']:
            with self.subTest(cmd=cmd):
                shutil.rmtree(self.path('lib', ORIGIN_DIR), ignore_errors=True)
                self.out(cmd)
                self.assertIsNotNone(self.origin().get(self.entry('smith2020climate')))

    def test_select(self):
        before = self.origin().pulled('../pool')  # the add from the pool (setUp)
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        self.lib('pull 10.1000/abc123')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature')
        self.assertEqual(self.origin().pulled('../pool'), before)  # only a full pull counts as a pull

    def test_missing_pool(self):
        self.lib('config pool ../pool -y')  # a shallow library
        os.rename(self.path('pool'), self.path('elsewhere'))
        for cmd in ['pull', 'pull --check', 'sync']:
            with self.assertRaisesRegex(PapersExit, r'^pool \S+/pool does not exist: create it first with '
                                                    r'`papers init \S+/pool` \(nothing was changed\)$'):
                self.lib(cmd)
        os.makedirs(self.path('pool'))
        with self.assertRaisesRegex(PapersExit, r'pool \S+/pool is not a library'):
            self.lib('pull')
        # with --pool PATH too, the pool of a shallow library, where its files go, is not created
        with self.assertRaisesRegex(PapersExit, r'pool \S+/pool is not a library .*`papers init \S+/pool`'):
            self.lib('pull --pool ../elsewhere')
        self.assertEqual(os.listdir(self.path('pool')), [])
        os.rmdir(self.path('pool'))
        os.rename(self.path('elsewhere'), self.path('pool'))
        # --pool PATH
        for cmd in ['pull', 'pull --check', 'sync']:
            with self.assertRaisesRegex(PapersExit, r'pool \S+/missing does not exist'):
                self.lib(cmd + ' --pool ../missing')

    def test_entry_not_in_the_pool(self):
        self.edit_pool('@article{Smith_2020,', '@article{Other_2020,')
        self.edit_pool('doi = {10.1000/abc123}', 'doi = {10.1000/other}')
        self.edit_pool('title = {Climate sensitivity revisited}', 'title = {Other}')
        # removed from the pool: noted once (the origin record is dropped), not pulled
        self.assertEqual(self.out('pull'), 'smith2020climate: removed from pool ../pool '
                         '(`papers push --pool ../pool smith2020climate` adds it back)\nnothing to pull from pool ../pool')
        self.assertIsNone(self.origin().get(self.entry('smith2020climate')))
        self.assertEqual(self.out('pull'), 'nothing to pull from pool ../pool')
        out = self.out('pull smith2020climate')
        self.assertRegex(out, r'^Not found -> smith2020climate: .* \[not in pool ../pool\]$')

    def test_distinct_merged(self):
        pool_distinct = Distinct.for_library(self.path('pool'))
        pool_distinct.pairs.append([{'doi': '10.1/a'}, {'doi': '10.1/b'}])
        pool_distinct.changed = True
        pool_distinct.save()
        self.lib('pull')
        self.assertIn([{'doi': '10.1/a'}, {'doi': '10.1/b'}],
                      Distinct.for_library(self.path('lib')).pairs)

    def test_check_and_status(self):
        self.lib('pull')
        self.assertIn('up to date', self.state())
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        os.utime(self.path('pool', 'papers.bib'), ns=(1, 1))
        self.assertIn('changed since last pull or push', self.state())
        out = self.out('pull --check')
        self.assertIn('pool ../pool: changed since last pull or push', out)
        self.assertIn('smith2020climate: changed in pool ../pool: journal', out)
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nat.')  # nothing pulled
        self.lib('pull')
        self.assertIn('up to date', self.state())


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
        self.lib('push --all')
        pool_biblio, pool = self.bib('pool')
        self.assertIn('mine-2022', pool)
        files = pool_biblio.get_files(pool['mine-2022'])
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith(self.path('pool', 'files')))
        self.assertTrue(os.path.exists(self.path('mine.pdf')))  # copied
        self.assertIn('mine2022', self.bib()[1])  # library key kept
        self.assertEqual(self.origin().get(self.entry('mine2022')).pool_key, 'mine-2022')
        self.assertIn('nothing to push to pool ../pool', self.out('push'))  # shared: nothing new

    def test_shared_entries_only(self):
        # without KEY or --all, only the entries shared with the pool
        out = self.out('push')
        self.assertEqual(out, 'push to pool ../pool: no entries shared with it '
                              '(`papers push --pool ../pool KEY` or `papers push --pool ../pool --all` '
                              'adds entries to it)')
        self.assertEqual(len(self.bib('pool')[1]), 2)
        self.lib('push mine2022')
        self.assertEqual(len(self.bib('pool')[1]), 3)
        self.assertIn('nothing to push to pool ../pool', self.out('push'))

    def test_pool_name_template(self):
        self.papers('config name.template {title}', cwd=self.path('pool'))
        self.lib('push --all')
        self.assertTrue(os.path.exists(self.path('pool', 'files', 'my-own-paper.pdf')))

    def test_changes(self):
        self.lib('push --all')
        key = self.origin().get(self.entry('mine2022')).pool_key
        self.edit_lib('year = {2022}', 'journal = {J. Mine},\n year = {2022}')
        self.edit_pool('title = {My own paper},', 'note = {pool note},\n title = {My own paper},')
        self.lib('push --all')
        e = self.entry(key, 'pool')
        self.assertEqual(e['journal'], 'J. Mine')
        self.assertEqual(e['note'], 'pool note')  # changed in the pool only: kept
        self.assertNotIn('note', self.entry('mine2022'))  # push does not change the library

    def conflict(self):
        self.lib('push --all')
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
            self.lib('push --all')

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
        self.assertIn('up to date', self.state())
        Path(self.path('smith.bib')).write_text(SMITH_BIB.replace('year = {2020}', 'keywords = {mine},\n year = {2020}'))
        self.lib('add ../smith.bib --no-pool')
        self.lib('push smith2020climate')
        self.assertEqual(self.entry('Smith_2020', 'pool')['keywords'], 'mine')
        self.assertNotIn('abstract', self.entry('smith2020climate'))  # push does not change the library
        # the origin is the library's version, sent: what the pool has beyond it is to pull
        self.assertNotIn('abstract', self.origin().get(self.entry('smith2020climate')).entry)
        self.assertIn('changed since last pull or push', self.state())
        out = self.out('pull --check')
        self.assertIn('smith2020climate: changed in pool ../pool: abstract, file, journal', out)
        self.lib('pull')
        e = self.entry('smith2020climate')
        self.assertEqual((e['abstract'], e['journal'], e['keywords']), ('From the pool.', 'Nat.', 'mine'))
        self.assertIn('up to date', self.state())
        self.assertIn('nothing to pull from pool ../pool', self.out('pull'))
        self.assertIn('nothing to push to pool ../pool', self.out('push smith2020climate'))
        self.assertIn('up to date', self.state())

    def test_push_keeps_a_pool_change(self):
        # a field changed in the pool only, during a push: kept in the pool, and pulled after
        self.lib('push --all')
        key = self.origin().get(self.entry('mine2022')).pool_key
        self.edit_pool('title = {My own paper}', 'title = {My own paper (pool)}')
        self.edit_lib('year = {2022}', 'journal = {J. Mine},\n year = {2022}')
        self.lib('push --all')
        self.assertEqual(self.entry(key, 'pool')['title'], 'My own paper (pool)')
        self.lib('push --all')  # the pool's title is not taken back by a second push
        self.assertEqual(self.entry(key, 'pool')['title'], 'My own paper (pool)')
        self.lib('pull')
        self.assertEqual(self.entry('mine2022')['title'], 'My own paper (pool)')

    def test_distinct_merged(self):
        lib = Distinct.for_library(self.path('lib'))
        lib.pairs.append([{'doi': '10.1/a'}, {'doi': '10.1/b'}])
        lib.changed = True
        lib.save()
        self.lib('push --all')
        self.assertIn([{'doi': '10.1/a'}, {'doi': '10.1/b'}],
                      Distinct.for_library(self.path('pool')).pairs)

    def test_status_after_push(self):
        self.lib('pull')
        self.lib('push --all')
        self.assertIn('up to date', self.state())

    def test_pool_not_created(self):
        # a pool that does not exist is an error: `papers init PATH` creates it
        with self.assertRaisesRegex(PapersExit, r'pool \S+/new does not exist: create it first with '
                                                r'`papers init \S+/new` \(nothing was changed\)'):
            self.lib('push --all --pool ../new')
        self.assertFalse(os.path.exists(self.path('new')))
        self.papers('init new')
        self.lib('push --all --pool ../new')
        self.assertEqual(json.load(open(self.path('new', CONFIG_FILE_LOCAL)))['pool'], 'none')
        self.assertEqual(len(self.bib('new')[1]), 1)


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
        self.lib('export ../out')
        biblio, entries = self.bib('out')
        self.assertEqual(sorted(entries), ['mine2022', 'smith2020climate'])
        files = biblio.get_files(entries['mine2022'])
        self.assertTrue(files[0].startswith(self.path('out', 'files')))
        self.assertTrue(os.path.samefile(files[0], self.lib_pdf))
        text = Path(self.path('out', 'papers.bib')).read_text()
        self.assertIn('file = {:files/', text)  # relative links
        # a new library: no backup of a previous bibtex
        self.assertFalse(os.path.exists(self.path('out', '.papers.bib.backup')))
        # a library of its own, to hand over
        self.assertEqual(self.json('out')['pool'], 'none')
        self.assertNotIn('local', self.json('out'))
        # add of the folder restores it
        self.papers('init back')
        self.papers('add ../out --recursive --no-pool', cwd=self.path('back'))
        self.assertEqual(sorted(self.bib('back')[1]), ['mine2022', 'smith2020climate'])

    def test_selection_and_link(self):
        self.lib('export ../out mine2022 --files link')
        biblio, entries = self.bib('out')
        self.assertEqual(list(entries), ['mine2022'])
        self.assertEqual(biblio.get_files(entries['mine2022']), [self.lib_pdf])
        self.assertIn('file = {:../lib/files/', Path(self.path('out', 'papers.bib')).read_text())

    def test_none(self):
        self.lib('export ../out --files none')
        self.assertNotIn('file', self.entry('mine2022', 'out'))
        self.assertEqual(os.listdir(self.path('out', 'files')), [])

    def test_not_empty(self):
        os.makedirs(self.path('out'))
        Path(self.path('out', 'x')).write_text('x')
        with self.assertRaisesRegex(PapersExit, 'not an empty directory'):
            self.lib('export ../out')

    def test_export_then_pool(self):
        # `export --pool` of earlier builds: export, then make it the pool
        with self.assertRaises(SystemExit):
            self.lib('export ../out --pool')
        self.lib('export ../out')
        self.lib('config pool ../out -y')  # links to the copies of the PDFs that export made
        self.assertEqual(self.json('lib')['pool'], '../out')
        self.assertTrue(self.files('mine2022')[0].startswith(self.path('out', 'files')))
        text = Path(self.path('out', 'papers.bib')).read_text()
        Path(self.path('out', 'papers.bib')).write_text(text.replace('title = {My own paper}', 'title = {My own paper},\n volume = {3}'))
        self.lib('pull --all --on-duplicate update')  # nothing shared yet: --all; differences are conflicts
        self.assertEqual(self.entry('mine2022')['volume'], '3')
        out = pool_id(self.path('out'), '../out')
        self.assertEqual(self.origin().get(self.entry('mine2022'), out).pool, out)


# STATUS
# ======

class TestStatus(PoolTest):

    def test_status(self):
        out = self.out('status')
        self.assertIn('* files:  files (the files directory of the library', out)
        self.assertNotIn('* pool:', out)
        self.assertNotIn('* library:', out)
        self.assertNotIn('* pool:', self.out('status -v'))
        self.assertNotIn('auto-push', out)
        self.assertNotIn('local', out)
        self.lib('config pool ../pool -y')
        out = self.out('status')
        self.assertNotIn('* library:', out)
        self.assertIn('* pool:   ../pool (not pulled from yet)', out)
        self.assertIn(f'* files:  in the pool, {self.path("pool", "files")}\n', out)
        self.assertNotIn('files mode', out)  # a setting: `papers config`
        self.assertTrue(out.endswith('`papers pull` takes the entries shared with the pool'))
        self.lib('config auto-push true')
        self.assertNotIn('auto-push', self.out('status'))  # a setting: `papers config`
        self.lib('config pool none')
        out = self.out('status')
        self.assertNotIn('* pool:', out)
        self.assertNotIn('auto-push', out)
        # the bibtex first, then the files; -v adds the locations, no settings
        lines = self.out('status -v').splitlines()
        self.assertEqual([line.split(':')[0] for line in lines[1:-1]],
                         ['* bibtex', '* files', '* history', '* configuration file', '* cache directory',
                          '* version'])
        self.assertEqual(lines[-1], '`papers config` lists and sets the settings')

    def shallow_with_smith(self):
        "a shallow library that took smith2020climate from its pool, auto-push off"
        self.lib('config pool ../pool -y')
        self.take_smith()
        self.assertIn('../pool (in sync)', self.out('status'))

    def pool_line(self):
        out = self.out('status')
        return next(line for line in out.splitlines() if line.startswith('* pool:')), out.splitlines()[-1]

    def test_pool_changed(self):
        self.shallow_with_smith()
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        line, hint = self.pool_line()
        self.assertTrue(line.endswith('../pool (pool changed)'), line)
        self.assertEqual(hint, '`papers pull --dry-run` shows the changes, `papers pull` takes them')
        self.lib('pull')
        self.assertTrue(self.pool_line()[0].endswith('(in sync)'))

    def test_library_changed(self):
        self.shallow_with_smith()
        self.edit_lib('journal = {Nat.}', 'journal = {Nature}')  # e.g. in an editor
        line, hint = self.pool_line()
        self.assertTrue(line.endswith('../pool (library changed)'), line)
        self.assertEqual(hint, '`papers push --dry-run` shows the changes, `papers push` sends them')
        self.lib('push')
        self.assertTrue(self.pool_line()[0].endswith('(in sync)'))

    def test_both_changed(self):
        self.shallow_with_smith()
        self.edit_lib('journal = {Nat.}', 'journal = {Nature}')
        self.edit_pool('title = {Climate sensitivity revisited}', 'title = {Climate sensitivity, revisited}')
        line, hint = self.pool_line()
        self.assertTrue(line.endswith('../pool (both changed)'), line)
        self.assertEqual(hint, '`papers sync --dry-run` shows the changes, `papers sync` exchanges them')

    def test_same_change_on_both_sides(self):
        # the pool file changed, but the entry is the same on both sides: in sync (nothing of the library written)
        self.shallow_with_smith()
        self.edit_lib('journal = {Nat.}', 'journal = {Nature}')
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        line, hint = self.pool_line()
        self.assertTrue(line.endswith('../pool (in sync)'), line)
        self.assertEqual(hint, '`papers config` lists and sets the settings')
        self.assertIn('changed since last pull or push', self.state())  # status writes no origin file

    def test_fast_path(self):
        # once status found them in sync, it compares only the entries of the pieces that changed since
        self.shallow_with_smith()
        self.out('status')
        config = Config.load(self.path('lib', CONFIG_FILE_LOCAL))
        project, _ = papers.backup.project_of(config, create=False)
        self.assertTrue(os.path.exists(os.path.join(project.dir, 'exchanges.json')))  # on the machine
        self.assertFalse(os.path.exists(self.path('lib', '.papers', 'exchanges.json')))
        from papers.pools import exchange_state, Pools
        with patch('papers.pools.Biblio.load', side_effect=AssertionError('nothing to read')):
            self.assertEqual(exchange_state(config, Pools(config), self.path('pool')), ('in sync', None))
        # a change on either side is found
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        self.assertTrue(self.pool_line()[0].endswith('(pool changed)'))
        self.edit_lib('title = {Climate sensitivity revisited}', 'title = {Climate sensitivity, revisited}')
        self.assertTrue(self.pool_line()[0].endswith('(both changed)'))
        self.lib('sync --on-duplicate skip')
        self.assertTrue(self.pool_line()[0].endswith('(in sync)'))

    def test_fast_path_after_a_touch(self):
        # the pool file rewritten as it was: in sync, from the pieces, and nothing of the library written
        self.shallow_with_smith()
        self.out('status')
        origin = {f: Path(self.path('lib', '.papers', 'origin', f)).read_text()
                  for f in os.listdir(self.path('lib', '.papers', 'origin'))}
        os.utime(self.path('pool', 'papers.bib'), ns=(1, 1))
        self.assertTrue(self.pool_line()[0].endswith('(in sync)'))
        self.assertEqual({f: Path(self.path('lib', '.papers', 'origin', f)).read_text()
                          for f in os.listdir(self.path('lib', '.papers', 'origin'))}, origin)

    def test_entry_type_changed(self):
        # @article -> @book in the library: push would send it, status says so
        self.shallow_with_smith()
        self.out('status')
        self.edit_lib('@article{smith2020climate', '@book{smith2020climate')
        self.assertTrue(self.pool_line()[0].endswith('(library changed)'), self.pool_line())

    def test_entry_removed_from_the_pool(self):
        # once in sync, an entry removed from the pool shows (the fast comparison does not skip it)
        self.shallow_with_smith()
        self.out('status')
        text = Path(self.path('pool', 'papers.bib')).read_text()
        start = text.index('@article{Smith_2020')
        end = text.find('\n@', start + 1)
        Path(self.path('pool', 'papers.bib')).write_text(text[:start] + (text[end + 1:] if end > 0 else ''))
        self.assertFalse(self.pool_line()[0].endswith('(in sync)'), self.pool_line())

    def test_other_entries_of_the_pool(self):
        # a change of the pool that does not concern the library
        self.shallow_with_smith()
        self.edit_pool('@article{', '@article{other2024,\n title = {Another}\n}\n\n@article{', )
        self.assertTrue(self.pool_line()[0].endswith('(in sync)'))

    def test_after_add_from_pool(self):
        # the first exchange with the pool counts as a pull
        self.take_smith()
        self.assertEqual('pool ../pool: up to date', self.state())
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        os.utime(self.path('pool', 'papers.bib'), ns=(1, 1))
        self.assertIn('changed since last pull or push', self.state())
        # a later push does not hide the change of the pool
        self.lib('push')
        self.assertIn('changed since last pull or push', self.state())
        self.lib('pull')
        self.assertIn('up to date', self.state())

    def check_no_flip(self, config=None):
        """two libraries on the same pool (lib and b), with the same entry:
        an exchange that changes nothing does not write the pool, and the
        other library stays up to date. config: a command run in both
        libraries first"""
        shallow = config == 'shallow'
        if shallow:
            self.lib('config pool ../pool -y')
        elif config:
            self.lib(config)
        self.take_smith()
        self.papers('init b' + (' --pool ../pool' if shallow else ''))
        option = '' if shallow else ' --pool ../pool'
        b = lambda cmd: self.papers(cmd + (option if cmd.split()[0] in EXCHANGES else ''), cwd=self.path('b'))
        if config and not shallow:
            b(config)
        b_status = lambda: self.papers('pull --check' + option, cwd=self.path('b'), sp_cmd='check_output')
        pool_bib = self.path('pool', 'papers.bib')
        content = Path(pool_bib).read_text()
        backup = self.path('pool', '.papers.bib.backup')
        os.utime(pool_bib, ns=(10**18, 10**18))  # a past write of the pool, recorded by both libraries
        self.lib('pull')
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            b('add ../smith.bib')  # taken from the pool
        self.assertIn('up to date', b_status())
        self.assertEqual(os.stat(pool_bib).st_mtime_ns, 10**18)
        self.assertIn('up to date', self.state())
        backup_mtime = os.stat(backup).st_mtime_ns if os.path.exists(backup) else None
        self.lib('sync')
        self.assertIn('up to date', self.state())
        self.assertIn('up to date', b_status())
        b('sync')
        self.lib('push')
        self.assertIn('up to date', self.state())
        self.assertIn('up to date', b_status())
        self.assertEqual(os.stat(pool_bib).st_mtime_ns, 10**18)
        self.assertEqual(Path(pool_bib).read_text(), content)
        self.assertEqual(os.stat(backup).st_mtime_ns if os.path.exists(backup) else None, backup_mtime)

    def test_no_change_no_flip(self):
        self.check_no_flip()

    def test_no_change_no_flip_auto_push(self):
        self.check_no_flip('config auto-push true')

    def test_no_change_no_flip_shallow(self):
        self.check_no_flip('shallow')

    def test_partial_pull_is_not_an_exchange(self):
        self.take_smith()
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        os.utime(self.path('pool', 'papers.bib'), ns=(1, 1))
        self.lib('pull smith2020climate')
        self.assertIn('changed since last pull or push', self.state())

    def test_after_add_to_the_pool(self):
        # a shallow library: add places the entry in the pool
        self.papers('init other --pool ../pool')
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        self.papers('add ../new.bib', cwd=self.path('other'))
        out = self.papers('status', cwd=self.path('other'), sp_cmd='check_output')
        self.assertIn('* pool:   ../pool (in sync)', out)

    def test_missing_pool(self):
        self.lib('config pool ../pool -y')
        os.rename(self.path('pool'), self.path('elsewhere'))
        self.assertIn('../pool (', self.out('status'))
        self.assertIn('missing', self.out('status').split('* pool:')[1])

    def test_pool_command_is_gone(self):
        with self.assertRaises(SystemExit):
            self.papers('pool list')


# SHALLOW LIBRARIES
# =================

class OwnFilesTest(PoolTest):
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


class TestConfigPoolSelfContained(OwnFilesTest):
    "`papers config pool PATH` in a self-contained library: it becomes shallow"

    def test_refused(self):
        # mine2022 links to a PDF that the pool does not have: nothing changes
        pool_text = Path(self.path('pool', 'papers.bib')).read_text()
        lib_text = Path(self.path('lib', 'papers.bib')).read_text()
        with self.assertRaises(PapersExit) as cm:
            self.lib('config pool ../pool -y')
        message = str(cm.exception)
        self.assertIn('pool ../pool: 1 entry links to PDFs that the pool ../pool does not have (nothing was '
                      'changed): mine2022', message)
        self.assertIn('Copy them to the pool first: `papers push --pool ../pool mine2022`', message)
        self.assertIn('Then run `papers config pool ../pool` again.', message)
        self.assertNotIn('smith2020climate', message)  # the pool has its PDF
        self.assertNotIn('--dry-run', message)
        self.assertEqual(self.json('lib').get('pool', 'none'), 'none')
        self.assertEqual(Path(self.path('pool', 'papers.bib')).read_text(), pool_text)
        self.assertEqual(Path(self.path('lib', 'papers.bib')).read_text(), lib_text)
        self.assertTrue(os.path.exists(self.lib_smith))
        self.assertTrue(os.path.exists(self.lib_mine))
        self.assertEqual(sorted(os.listdir(self.path('pool', 'files'))), ['smith.pdf'])

    def test_becomes_shallow(self):
        self.lib('push mine2022')
        pool_text = Path(self.path('pool', 'papers.bib')).read_text()
        pool_mine = self.files(self.origin().get(self.entry('mine2022')).pool_key, 'pool')
        out = self.out('config pool ../pool --dry-run')  # the details: each file
        self.assertIn('smith2020climate: files/', out)
        self.assertIn(f'-> {self.pool_pdf} (deleted)', out)
        self.assertEqual(self.json('lib').get('pool', 'none'), 'none')
        out = self.out('config pool ../pool -y')
        self.assertEqual(self.json('lib')['pool'], '../pool')
        self.assertIn('link to the copies in the pool ../pool for 2 files (same content); '
                      'the library\'s copies in files (2 files) are deleted', out)
        # relinked, the library's copies deleted; the pool is not changed
        self.assertEqual(self.files('smith2020climate'), [self.pool_pdf])
        self.assertEqual(self.files('mine2022'), pool_mine)
        self.assertFalse(os.path.exists(self.lib_smith))
        self.assertFalse(os.path.exists(self.lib_mine))
        self.assertTrue(os.path.exists(self.pool_pdf))
        self.assertTrue(os.path.exists(pool_mine[0]))
        self.assertEqual(os.listdir(self.path('lib', 'files')), [])
        self.assertEqual(Path(self.path('pool', 'papers.bib')).read_text(), pool_text)
        self.assertIn('the library is now shallow', out)
        self.assertIn(f'* files:  in the pool, {self.path("pool", "files")}\n', self.out('status'))
        # the origin records of the exchanges with --pool ../pool are those of the pool
        self.assertIn('nothing to push to pool ../pool', self.out('push'))

    def test_entries_without_pdf_do_not_block(self):
        self.lib('rm mine2022 --delete-files')
        Path(self.path('nopdf.bib')).write_text(NEW_BIB.replace('mine2022', 'nopdf2023').replace(
            ' file = {:mine.pdf:pdf},\n', '').replace('My own paper', 'No PDF'))
        self.lib('add ../nopdf.bib')
        self.lib('config pool ../pool -y')
        self.assertEqual(self.json('lib')['pool'], '../pool')
        self.assertEqual(self.files('smith2020climate'), [self.pool_pdf])
        self.assertIn('nopdf2023', self.bib()[1])
        self.assertEqual(len(self.bib('pool')[1]), 2)  # not pushed

    def test_broken_links_do_not_block(self):
        self.lib('push mine2022')
        os.remove(self.lib_mine)
        out = self.out('config pool ../pool -y')
        self.assertEqual(self.json('lib')['pool'], '../pool')
        self.assertIn('1 link was already broken', out)
        self.assertEqual(self.files('mine2022'), [self.lib_mine])  # unchanged

    def test_same_paper_different_content(self):
        # the pool entry has another version of the PDF: refused
        Path(self.lib_smith).unlink()
        Path(self.lib_smith).write_text('another version')
        self.lib('push mine2022')
        with self.assertRaisesRegex(PapersExit, r'\(nothing was changed\): smith2020climate\n'):
            self.lib('config pool ../pool -y')
        self.assertTrue(os.path.exists(self.lib_smith))
        self.assertEqual(self.json('lib').get('pool', 'none'), 'none')

    def test_many_entries(self):
        text = Path(self.path('lib', 'papers.bib')).read_text()
        for i in range(12):
            Path(self.path('lib', 'files', f'p{i}.pdf')).write_text(f'paper {i}')
            text += (f'\n@article{{paper{i:02d},\n author = {{Author{i}, A.}},\n file = {{:files/p{i}.pdf:pdf}},\n'
                     f' title = {{Paper number {i}}},\n year = {{2000}}\n}}\n')
        Path(self.path('lib', 'papers.bib')).write_text(text)
        with self.assertRaises(PapersExit) as cm:
            self.lib('config pool ../pool -y')
        message = str(cm.exception)
        self.assertIn('13 entries link to PDFs', message)
        self.assertIn('mine2022, paper00, paper01, paper02, paper03, paper04, paper05, paper06, paper07, paper08 '
                      'and 3 more', message)
        self.assertIn('Copy them to the pool first: `papers push --pool ../pool --all`', message)

    def test_dry_run(self):
        self.lib('push --all')
        out = self.out('config pool ../pool --dry-run')
        self.assertIn('nothing was changed', out)
        self.assertEqual(self.json('lib').get('pool', 'none'), 'none')
        self.assertTrue(os.path.exists(self.lib_smith))
        self.assertTrue(os.path.exists(self.lib_mine))

    def test_no_terminal(self):
        self.lib('push --all')
        with self.assertRaisesRegex(PapersExit, 'pass -y'):
            self.lib('config pool ../pool')
        self.assertEqual(self.json('lib').get('pool', 'none'), 'none')
        self.assertTrue(os.path.exists(self.lib_smith))

    def test_prompt(self):
        self.lib('push --all')
        with patch('papers.cli.library_cmds.stdin_is_terminal', lambda: True), \
                patch('builtins.input', lambda prompt: 'n'):
            self.lib('config pool ../pool')
        self.assertEqual(self.json('lib').get('pool', 'none'), 'none')
        self.assertTrue(os.path.exists(self.lib_smith))
        with patch('papers.cli.library_cmds.stdin_is_terminal', lambda: True), \
                patch('builtins.input', lambda prompt: 'y'):
            self.lib('config pool ../pool')
        self.assertEqual(self.json('lib')['pool'], '../pool')
        self.assertFalse(os.path.exists(self.lib_smith))

    def test_pool_none(self):
        self.lib('push --all')
        self.lib('config pool ../pool -y')
        out = self.out('config pool none -y')
        self.assertIn('copy 2 files of the pool', out)
        self.assertIn('the library is now self-contained', out)
        self.assertEqual(self.json('lib').get('pool', 'none'), 'none')
        for key in ('smith2020climate', 'mine2022'):
            files = self.files(key)
            self.assertTrue(files[0].startswith(self.path('lib', 'files')), files)
        self.assertTrue(os.path.samefile(self.files('smith2020climate')[0], self.pool_pdf))  # hard link
        self.assertTrue(os.path.exists(self.pool_pdf))

    def test_pool_must_be_a_library_without_pool(self):
        lib_json = self.json('lib')
        with self.assertRaisesRegex(PapersExit, r'pool ../missing: \S+/missing does not exist: create it first '
                                                r'with `papers init \S+/missing` \(nothing was changed\)'):
            self.lib('config pool ../missing -y')
        os.makedirs(self.path('notalib'))
        with self.assertRaisesRegex(PapersExit, 'is not a library'):
            self.lib('config pool ../notalib -y')
        self.papers('init shallow --pool ../pool')
        with self.assertRaisesRegex(PapersExit, r'pool ../shallow: \S+/shallow has a pool itself \(../pool\): '
                                                r'give a library without pool \(nothing was changed\)'):
            self.lib('config pool ../shallow -y')
        self.assertEqual(self.json('lib'), lib_json)

    def test_local_is_gone(self):
        with self.assertRaisesRegex(PapersExit, 'unknown setting: local'):
            self.lib('config local true')
        with self.assertRaises(SystemExit):
            self.papers('init other --local')

    def test_init_shallow(self):
        out = self.papers('init other --pool ../pool', sp_cmd='check_output')
        self.assertIn('* files:   in the pool (shallow library)\n* pool:    ../pool\n', out)
        self.assertEqual(self.json('other')['pool'], '../pool')
        self.assertNotIn('local', self.json('other'))
        out = self.papers('init fourth', sp_cmd='check_output')
        self.assertIn('* files:   files (the files directory of the library)\n', out)
        self.assertNotIn('* pool:', out)
        self.assertEqual(self.json('fourth')['pool'], 'none')

    def test_init_pool_must_be_a_library_without_pool(self):
        for pool, error in [('../missing', 'does not exist'), ('../lib/files', 'is not a library'),
                            ('.', 'this is the library itself')]:
            with self.subTest(pool=pool):
                with self.assertRaisesRegex(PapersExit, error):
                    self.papers(f'init other --pool {pool}')
                self.assertFalse(os.path.exists(self.path('other')))  # nothing created
        self.papers('init shallow --pool ../pool')
        with self.assertRaisesRegex(PapersExit, 'has a pool itself'):
            self.papers('init other --pool ../shallow')
        self.assertFalse(os.path.exists(self.path('other')))

    def test_init_shallow_has_no_files_directory(self):
        # the files go to the pool: the files directory is created when needed
        self.papers('init other --pool ../pool')
        self.assertFalse(os.path.exists(self.path('other', 'files')))
        out = self.papers('status', cwd=self.path('other'), sp_cmd='check_output')
        self.assertIn(f'* files:  in the pool, {self.path("pool", "files")}\n', out)
        self.assertNotIn('files directory', out)
        self.papers('init fourth')
        self.assertTrue(os.path.isdir(self.path('fourth', 'files')))
        self.assertIn('* files:  files (the files directory of the library, empty)',
                      self.papers('status', cwd=self.path('fourth'), sp_cmd='check_output'))
        # the files of the pool are copied into it when the library becomes self-contained
        Path(self.path('smith.bib')).write_text(SMITH_BIB)
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            self.papers('add ../smith.bib', cwd=self.path('other'))
        self.papers('config pool none -y', cwd=self.path('other'))
        self.assertEqual(len(os.listdir(self.path('other', 'files'))), 1)

    def test_earlier_local_setting_ignored(self):
        # `local` of earlier v3 builds: the pool alone says whether the library is shallow
        js = self.json('lib')
        js.update(pool='../pool', local=True)
        json.dump(js, open(self.path('lib', CONFIG_FILE_LOCAL), 'w'))
        config = Config.load(self.path('lib', CONFIG_FILE_LOCAL))
        self.assertTrue(config.shallow)
        self.assertFalse(hasattr(config, 'local'))
        config.save()
        self.assertNotIn('local', self.json('lib'))


class TestMigrationPath(PoolTest):
    "a self-contained library moves its PDFs to a pool: push --pool PATH --all, config pool PATH"

    def test_sequence(self):
        self.papers('init mylib')
        self.assertEqual(self.json('mylib')['pool'], 'none')
        run = lambda cmd: self.papers(cmd, cwd=self.path('mylib'))
        run('config files copy')
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        run('add ../new.bib')
        Path(self.path('smith.bib')).write_text(SMITH_BIB.replace('}\n}', '},\n file = {:smith.pdf:pdf}\n}'))
        Path(self.path('smith.pdf')).write_text('pdf of smith')
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            run('add ../smith.bib')
        self.assertEqual(len(os.listdir(self.path('mylib', 'files'))), 2)
        run('push --pool ../pool --all')  # copies mine.pdf into the pool; the pool has smith's PDF already
        pool_biblio, pool = self.bib('pool')
        self.assertEqual(len(pool), 3)
        run('config pool ../pool -y')
        self.assertEqual(self.json('mylib')['pool'], '../pool')
        self.assertEqual(os.listdir(self.path('mylib', 'files')), [])
        biblio = Biblio.load(self.path('mylib', 'papers.bib'), '')
        for e in biblio.entries:
            files = biblio.get_files(e)
            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].startswith(self.path('pool', 'files')), files)
            self.assertTrue(os.path.exists(files[0]))
        self.assertEqual(len(os.listdir(self.path('pool', 'files'))), 2)


class TestConfigPool(OwnFilesTest):
    "`papers config pool` in a shallow library"

    def setUp(self):
        super().setUp()
        self.lib('push --all')
        self.lib('config pool ../pool -y')
        self.mine = self.files('mine2022')[0]
        self.papers('init other --pool none')

    def test_pool_none(self):
        out = self.out('config pool none -y')
        self.assertIn('pool none: the library becomes self-contained, with its own files', out)
        self.assertEqual(self.json('lib')['pool'], 'none')
        for key in ('smith2020climate', 'mine2022'):
            self.assertTrue(self.files(key)[0].startswith(self.path('lib', 'files')))
        self.assertTrue(os.path.exists(self.pool_pdf))  # the pool keeps its files

    def test_pool_none_no_terminal(self):
        with self.assertRaisesRegex(PapersExit, 'pass -y'):
            self.lib('config pool none')
        self.assertEqual(self.json('lib')['pool'], '../pool')

    def other_has_smith(self):
        "the other pool has smith already, with the same file"
        Path(self.path('other', 'files', 'smith-copy.pdf')).write_text('pdf of smith')
        Path(self.path('other', 'papers.bib')).write_text(
            POOL_BIB.split('@article{Brown')[0].replace('files/smith.pdf', 'files/smith-copy.pdf'))

    def test_other_pool_refused(self):
        self.other_has_smith()
        other_text = Path(self.path('other', 'papers.bib')).read_text()
        lib_text = Path(self.path('lib', 'papers.bib')).read_text()
        with self.assertRaises(PapersExit) as cm:
            self.lib('config pool ../other -y')
        message = str(cm.exception)
        self.assertIn('pool ../other: 1 entry links to PDFs that the pool ../other does not have '
                      '(nothing was changed): mine2022', message)
        self.assertIn('`papers push --pool ../other mine2022`', message)
        self.assertNotIn('pull', message)
        self.assertEqual(self.json('lib')['pool'], '../pool')
        self.assertEqual(Path(self.path('other', 'papers.bib')).read_text(), other_text)
        self.assertEqual(Path(self.path('lib', 'papers.bib')).read_text(), lib_text)
        self.assertEqual(os.listdir(self.path('other', 'files')), ['smith-copy.pdf'])

    def test_other_pool(self):
        self.other_has_smith()
        self.lib('push --pool ../other mine2022')  # copies the PDF into the other library
        other_mine = [f for f in os.listdir(self.path('other', 'files')) if f != 'smith-copy.pdf']
        self.assertEqual(len(other_mine), 1)
        out = self.out('config pool ../other --dry-run')
        self.assertIn(f'smith2020climate: {self.pool_pdf} -> {self.path("other", "files", "smith-copy.pdf")}', out)
        out = self.out('config pool ../other -y')
        self.assertIn('link to the copies in the pool ../other for 2 files (same content)', out)
        self.assertNotIn('deleted', out)  # the files of the former pool stay
        self.assertEqual(self.json('lib')['pool'], '../other')
        self.assertNotIn('the library is now', out)  # it was shallow already
        self.assertEqual(self.files('smith2020climate'), [self.path('other', 'files', 'smith-copy.pdf')])
        self.assertEqual(self.files('mine2022'), [self.path('other', 'files', other_mine[0])])
        # the old pool keeps its files, nothing else was copied
        self.assertTrue(os.path.exists(self.pool_pdf))
        self.assertTrue(os.path.exists(self.mine))
        self.assertEqual(len(os.listdir(self.path('other', 'files'))), 2)
        self.assertEqual(len(self.bib('other')[1]), 2)
        # the origin records: mine2022 was pushed to the new pool, smith2020climate is not shared with it
        # (under the path of the pool, until the next exchange moves them to its identifier, see Pools._id)
        record = lambda key: (self.origin().get(self.entry(key), pool_id(self.path('other'), '../other'))
                              or self.origin().get(self.entry(key), '../other'))
        self.assertIsNotNone(record('mine2022'))
        self.assertIsNone(record('smith2020climate'))
        # the new pool has the paper of smith2020climate: shared with it, the push records it
        self.assertIn('push to pool ../other: 1 linked', self.out('push'))
        self.assertIsNotNone(self.origin().get(self.entry('smith2020climate'), pool_id(self.path('other'), '../other')))
        self.assertIsNotNone(self.origin().get(self.entry('mine2022'), pool_id(self.path('other'), '../other')))
        self.assertIn('nothing to push to pool ../other', self.out('push'))

    def test_new_pool_missing(self):
        with self.assertRaisesRegex(PapersExit, 'pool ../new: .* does not exist'):
            self.lib('config pool ../new -y')
        self.assertFalse(os.path.exists(self.path('new')))
        self.papers('init new')
        self.lib('push --pool ../new --all')
        self.lib('config pool ../new -y')
        self.assertEqual(len(self.bib('new')[1]), 2)
        self.assertTrue(self.files('mine2022')[0].startswith(self.path('new', 'files')))

    def test_unset_pool(self):
        # pool none, as `config pool none`: the library becomes self-contained
        out = self.out('config --unset pool -y')
        self.assertIn('becomes self-contained', out)
        self.assertNotIn('pool', self.json('lib'))
        for key in ('smith2020climate', 'mine2022'):
            self.assertTrue(self.files(key)[0].startswith(self.path('lib', 'files')))
        self.assertEqual(self.out('config pool'), 'none')

    def test_without_pdf_just_sets(self):
        # a self-contained library without PDFs: nothing to relink
        self.lib('config pool none -y')
        self.lib('file detach --key mine2022 smith2020climate')
        self.lib('config pool ../other')
        self.assertEqual(self.json('lib')['pool'], '../other')
        self.assertEqual(self.files('mine2022'), [])

    def test_pool_path_written_relative(self):
        self.lib('config pool none -y')
        self.lib('file detach --key mine2022 smith2020climate')
        self.lib(f'config pool {self.path("other")}')
        self.assertEqual(self.json('lib')['pool'], self.path('other'))  # absolute
        self.lib('config pool ../other')
        self.assertEqual(self.json('lib')['pool'], '../other')  # written relative: relative
        self.lib('init sub')
        self.lib(f'config pool {self.path("lib", "sub")}')
        self.assertEqual(self.json('lib')['pool'], './sub')  # under the library


class TestShallow(OwnFilesTest):

    def setUp(self):
        super().setUp()
        self.lib('push --all')
        self.lib('config pool ../pool -y')

    def test_add_key(self):
        # a shallow library: the pool entry is taken, and nothing empty is pushed
        self.lib('rm smith2020climate --keep-files')
        pool_entries = len(self.bib('pool')[1])
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            out = self.out('add --key SMITH_2020')
        self.assertIn('[from pool ../pool]', out)
        self.assertEqual(self.files('Smith_2020'), [self.pool_pdf])
        with self.assertRaisesRegex(PapersExit, 'no entry yool2011 in pool ../pool'):
            self.lib('add --key yool2011')
        self.assertNotIn('yool2011', self.bib()[1])
        self.assertEqual(len(self.bib('pool')[1]), pool_entries)

    def test_push_never_writes_empty_entry(self):
        # the push guard: an entry without fields, or without key, stays out of the pool
        pool_entries = len(self.bib('pool')[1])
        for bib in ['@article{empty2020,\n}\n', '@article{,\n title = {No key}\n}\n']:
            with self.subTest(bib=bib):
                Path(self.path('lib', 'papers.bib')).write_text(bib)
                out = self.out('push --all')
                self.assertIn('not pushed to pool ../pool', out)
                self.assertEqual(len(self.bib('pool')[1]), pool_entries)

    def test_rm_never_deletes_pool_files(self):
        # in a terminal, papers does not ask about the files of the pool
        with patch('papers.cli.entry_cmds.stdin_is_terminal', lambda: True), \
                patch('builtins.input', side_effect=AssertionError('asked')):
            out = self.out('rm smith2020climate')
        self.assertTrue(os.path.exists(self.pool_pdf))
        self.assertIn('it is a file of a pool', out)
        self.assertNotIn('smith2020climate', self.bib()[1])
        self.assertIn('Smith_2020', self.bib('pool')[1])  # the pool entry stays

    def test_rm_delete_files_is_an_error(self):
        before = Path(self.path('lib', 'papers.bib')).read_text()
        for cmd in ('rm smith2020climate --delete-files', 'list smith --delete --delete-files'):
            with self.subTest(cmd=cmd):
                with self.assertRaisesRegex(PapersExit, "--delete-files: the files of a shallow library are "
                                                        "the pool's: remove them with `papers file rm FILE`"):
                    self.lib(cmd)
                self.assertEqual(Path(self.path('lib', 'papers.bib')).read_text(), before)
                self.assertTrue(os.path.exists(self.pool_pdf))

    def test_file_rm_deletes_the_pool_file(self):
        # the link goes in the pool entry too: no entry links to the file any more
        out = self.out(f'file rm {self.pool_pdf}')
        self.assertFalse(os.path.exists(self.pool_pdf))
        self.assertIn(f'delete {self.pool_pdf}', out)
        self.assertEqual(self.files('smith2020climate'), [])
        self.assertEqual(self.files('Smith_2020', 'pool'), [])

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
        out = self.out(f'file attach smith2020climate {self.path("si.pdf")}')
        files = self.files('smith2020climate')
        self.assertEqual(files[0], self.pool_pdf)
        self.assertEqual(len(files), 2)
        self.assertTrue(files[1].startswith(self.path('pool', 'files')), files)
        self.assertEqual(os.listdir(self.path('lib', 'files')), [])
        # auto-push false: the pool entry links to the file right away
        self.assertIn('[file links also updated in pool ../pool]', out)
        key = self.origin().get(self.entry('smith2020climate')).pool_key
        pool = self.bib('pool')
        self.assertEqual(pool[0].get_files(pool[1][key]), files)

    def test_file_attach_auto_push(self):
        self.lib('config auto-push true')
        Path(self.path('si.pdf')).write_text('supplement')
        out = self.out(f'file attach smith2020climate {self.path("si.pdf")}')
        self.assertIn('[also modified in pool ../pool]', out)
        files = self.files('smith2020climate')
        key = self.origin().get(self.entry('smith2020climate')).pool_key
        pool = self.bib('pool')
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


    def test_add_same_pdf_move_mode(self):
        self.lib('rm smith2020climate --keep-files')
        Path(self.path('copy.pdf')).write_text('pdf of smith')
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch), \
             patch('papers.bib.extract_pdf_metadata', no_fetch):
            self.lib('add ../copy.pdf --move')
        self.assertFalse(os.path.exists(self.path('copy.pdf')))  # stored in the pool already
        biblio, entries = self.bib()
        linked = [f for e in entries.values() for f in biblio.get_files(e)]
        self.assertIn(self.pool_pdf, linked)
        self.assertTrue(os.path.exists(self.pool_pdf))

    def test_add_output(self):
        # one line per entry, with where else it went or where it came from
        Path(self.path('other.bib')).write_text(NEW_BIB.replace('mine2022', 'other2023').replace(
            'My own paper', 'Another paper').replace('mine.pdf', 'other.pdf').replace('2022', '2023'))
        Path(self.path('other.pdf')).write_text('other')
        out = self.out('add ../other.bib')
        self.assertRegex(out, r'^Added -> other2023: Another paper \(file:1\) \[also added to pool ../pool\]\n    \S+/other.pdf --> copied to \S+/pool/files/mine_2023_another-paper.pdf$')
        self.lib('rm smith2020climate --keep-files')
        Path(self.path('smith.bib')).write_text(SMITH_BIB)
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            out = self.out('add ../smith.bib')
        self.assertRegex(out, r'^Added -> smith2020climate: .* \[from pool ../pool\]$')

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
        self.assertIn(f'smith2020climate: broken link: {self.pool_pdf} -> {new} (from the pool)', out)
        self.assertIn('1 link can be relinked, 0 without a file found', out)
        self.assertNotEqual(self.files('smith2020climate'), [new])
        out = self.out('file fix')
        self.assertIn(f'smith2020climate: relinked to {new} (from the pool)', out)
        self.assertIn('1 link relinked, 0 still broken', out)
        self.assertEqual(self.files('smith2020climate'), [new])



if __name__ == '__main__':
    unittest.main()
