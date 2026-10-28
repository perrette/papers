"""Tests of the rules of design/exchange.md that no other test checks: one
class per section, each test naming the section it checks"""
import hashlib
import json
import os
import re
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

import papers
import papers.backup
from papers.config import Config, CONFIG_FILE_LOCAL
from papers.pools import ORIGIN_DIR, LEGACY_ORIGIN_FILE, _library_id
from papers.utils import PapersExit

from tests.test_pools import PoolTest, NEW_BIB, POOL_BIB, SMITH_BIB, no_fetch


IDENT = '7e5754a0ccd246968e910bcd2a16dcf2'


def set_id(where, id):
    "write the library identifier `id` into the configuration of the library in `where`"
    file = os.path.join(where, CONFIG_FILE_LOCAL)
    js = json.load(open(file))
    js['id'] = id
    Path(file).write_text(json.dumps(js))


class SpecTest(PoolTest):
    "PoolTest (pool/ with Smith_2020 and Brown_2021, lib/ self-contained), with helpers"

    def origin_files(self, where='lib'):
        folder = self.path(where, ORIGIN_DIR)
        return {n: Path(folder, n).read_text() for n in sorted(os.listdir(folder))} if os.path.isdir(folder) else {}

    def origin_text(self, where='lib'):
        files = self.origin_files(where)
        self.assertEqual(len(files), 1, list(files))
        return list(files.values())[0]

    def lib_text(self):
        return Path(self.path('lib', 'papers.bib')).read_text()

    def pool_text(self):
        return Path(self.path('pool', 'papers.bib')).read_text()

    def write_origin(self, name, text):
        os.makedirs(self.path('lib', ORIGIN_DIR), exist_ok=True)
        Path(self.path('lib', ORIGIN_DIR, name)).write_text(text)

    def mtime(self, where='pool'):
        return os.stat(self.path(where, 'papers.bib')).st_mtime_ns


# 2.3 THE POOL ID
# ===============

class TestPoolId(SpecTest):

    def test_identifier_format(self):
        "exchange.md 2.3: a library identifier is 32 lower-case hexadecimal digits; else a path id"
        set_id(self.path('pool'), IDENT.upper())
        self.lib('pull Smith_2020')
        self.assertEqual(list(self.origin().entries), ['../pool'])
        shutil.rmtree(self.path('lib', ORIGIN_DIR))
        set_id(self.path('pool'), IDENT)
        self.lib('pull Smith_2020')
        self.assertEqual(list(self.origin().entries), [IDENT])

    def test_other_library_relative_id(self):
        "exchange.md 2.3 (4): an other library is named by its path relative to the library, ./ prepended"
        self.lib(f'pull --pool {self.path("pool")} Smith_2020')
        self.assertEqual(list(self.origin().entries), ['../pool'])
        with patch.dict(os.environ, {'HOME': self.dir}):
            self.lib('pull --pool ~/pool Brown_2021')
        self.assertEqual(list(self.origin().entries), ['../pool'])
        self.papers('init sub', cwd=self.path('lib'))
        Path(self.path('lib', 'sub', 'papers.bib')).write_text(NEW_BIB.replace(' file = {:mine.pdf:pdf},\n', ''))
        self.lib('pull --pool sub mine2022')
        self.assertEqual(sorted(self.origin().entries), ['../pool', './sub'])

    def test_path_ids_in_sorted_order(self):
        "exchange.md 2.3 (2): without identifier, the first designating path id in sorted order"
        self.write_origin('a.bib', '@comment{papers-pool ../pool/}\n\n'
                                   '@article{brown2021,\n papers-pool-key = {Brown_2021},\n title = {Ocean heat}\n}\n')
        self.write_origin('b.bib', '@comment{papers-pool ../pool}\n\n'
                                   '@article{other,\n papers-pool-key = {Other},\n title = {Other}\n}\n')
        before = self.origin_files()['a.bib']
        self.lib('pull Smith_2020')
        origin = self.origin()
        self.assertIn('smith_2020', origin.entries['../pool'])  # under '../pool', before '../pool/'
        self.assertNotIn('smith_2020', origin.entries['../pool/'])
        self.assertEqual(self.origin_files()['a.bib'], before)

    def test_identifier_after_first_step(self):
        "exchange.md 2.3: a pool gets an identifier at its first step; the next exchange moves the records"
        self.assertIsNone(_library_id(self.path('pool')))
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        self.lib('add ../new.bib')
        self.lib('push --all')
        self.assertEqual(list(self.origin().entries), ['../pool'])
        own = _library_id(self.path('pool'))
        self.assertIsNotNone(own)
        self.lib('pull')
        self.assertEqual(list(self.origin().entries), [own])
        name = f'pool-{hashlib.sha1(own.encode()).hexdigest()[:6]}.bib'
        self.assertEqual(list(self.origin_files()), [name])


# 2.2 RULES ON A POOL
# ===================

class TestPoolRules(SpecTest):

    def test_configured_pool_with_a_pool_auto_push_warns(self):
        "exchange.md 2.2, 12.1: a configured pool that took a pool: the automatic push warns, the library is saved"
        self.papers('init other --pool pool')
        self.papers('config auto-push true', cwd=self.path('other'))
        self.papers('pull Smith_2020', cwd=self.path('other'))
        self.papers('init top')
        pool_json = self.json('pool')
        pool_json['pool'] = '../top'
        Path(self.path('pool', CONFIG_FILE_LOCAL)).write_text(json.dumps(pool_json))
        pool_before = self.pool_text()
        with self.assertLogs(papers.logger, level='WARNING') as cm:
            self.papers('tag Smith_2020 --add x', cwd=self.path('other'))
        self.assertTrue(any('not pushed to the pool' in m and 'has a pool itself' in m for m in cm.output), cm.output)
        self.assertIn('keywords = {x}', Path(self.path('other', 'papers.bib')).read_text())
        self.assertEqual(self.pool_text(), pool_before)
        # a command that adds entries to the pool stops
        Path(self.path('new.bib')).write_text(NEW_BIB.replace(' file = {:mine.pdf:pdf},\n', ''))
        with self.assertRaisesRegex(PapersExit, 'has a pool itself'):
            self.papers('add ../new.bib', cwd=self.path('other'))

    def test_unreadable_pool_stops_the_automatic_push(self):
        "exchange.md 2.2, 12.1: a pool with entries that could not be parsed stops the automatic push, nothing saved"
        self.lib('config pool ../pool -y')
        self.lib('config auto-push true')
        self.take_smith()
        Path(self.path('pool', 'papers.bib')).write_text(POOL_BIB + '\n@article{Brown_2021,\n title = {Twice}\n}\n')
        pool_before, lib_before = self.pool_text(), self.lib_text()
        with self.assertRaisesRegex(PapersExit, r'Fix \S+papers.bib before writing to the pool \(nothing was changed\)'):
            self.lib('tag smith2020climate --add x')
        self.assertEqual((self.pool_text(), self.lib_text()), (pool_before, lib_before))


# 3.1 ORIGIN FILES
# ================

class TestOriginFiles(SpecTest):

    def test_file_name_examples(self):
        "exchange.md 3.1: <name>-<first 6 hex digits of sha1(pool id)>.bib, the examples of the section"
        from papers.pools import origin_file_name
        home = os.path.expanduser('~')
        examples = [
            ((IDENT, os.path.join(home, 'papers', 'shared-with-bob')), 'shared-with-bob-569371.bib'),
            ((IDENT, None), 'pool-569371.bib'),
            (('../pool', None), 'pool-615fe0.bib'),
            (('../shared-with-bob', None), 'shared-with-bob-d15650.bib'),
            (('~/Documents/papers', None), 'papers-e311da.bib'),
            (('../My Papers', None), 'my-papers-94036c.bib'),
            (('../pool/', None), 'pool-b6adbc.bib'),
            (('../x/../pool', None), 'pool-' + hashlib.sha1(b'../x/../pool').hexdigest()[:6] + '.bib'),
            (('../...', None), 'pool-' + hashlib.sha1(b'../...').hexdigest()[:6] + '.bib'),  # empty slug
        ]
        for (id, path), name in examples:
            with self.subTest(id=id, path=path):
                self.assertEqual(origin_file_name(id, path), name)
                self.assertEqual(name[-10:-4], hashlib.sha1(id.encode('utf-8')).hexdigest()[:6])

    def test_identifier_file_named_after_the_folder(self):
        "exchange.md 3.1: the first exchange with a pool that has an identifier names the file after its folder"
        os.rename(self.path('pool'), self.path('My Pool'))
        set_id(self.path('My Pool'), IDENT)
        self.lib('pull --pool "../My Pool" Smith_2020')
        self.assertEqual(list(self.origin_files()), ['my-pool-569371.bib'])


# 3.2 FORMAT
# ==========

ORIGIN_EXPECTED = """@comment{{papers-pool {id}}}

@comment{{papers-pulled {mtime}}}

@comment{{papers-pool-path {path}}}

@article{{brown2021,
 author = {{Brown, Bob}},
 doi = {{10.1000/brown}},
 file = {{}},
 papers-pool-key = {{Brown_2021}},
 papers-time = {{{time2}}},
 title = {{Ocean heat}},
 year = {{2021}}
}}

@article{{Smith_2020,
 author = {{Smith, John and Doe, Jane}},
 doi = {{10.1000/abc123}},
 file = {{:../pool/files/smith.pdf:pdf}},
 journal = {{Nat.}},
 papers-pool-key = {{Smith_2020}},
 papers-time = {{{time}}},
 title = {{Climate sensitivity revisited}},
 year = {{2020}}
}}
"""


class TestOriginFormat(SpecTest):

    def test_exact_text(self):
        "exchange.md 3.2, 3.3: the comments, then the records sorted by lower-case key, fields sorted, LF"
        set_id(self.path('pool'), IDENT)
        self.lib('config pool ../pool -y')
        Path(self.path('lib', 'papers.bib')).write_text(
            '@article{brown2021,\n author = {Brown, Bob},\n doi = {10.1000/brown},\n title = {Ocean heat},\n'
            ' year = {2021}\n}\n')
        self.lib('pull --all')
        text = self.origin_text()
        times = re.findall(r'papers-time = \{([^}]*)\}', text)
        self.assertEqual(len(times), 2)
        with patch.dict(os.environ, {'HOME': os.path.expanduser('~')}):
            path = papers.config.short_home(self.path('pool'))
        expected = ORIGIN_EXPECTED.format(id=IDENT, mtime=self.mtime(), path=path, time=times[1], time2=times[0])
        self.assertEqual(text, expected)
        self.assertNotIn('\r', Path(self.path('lib', ORIGIN_DIR, list(self.origin_files())[0])).read_bytes().decode())

    def test_pool_path_follows_the_pool(self):
        "exchange.md 3.2 (3): papers-pool-path is where the pool was at the last exchange; the file follows"
        set_id(self.path('pool'), IDENT)
        self.lib('pull Smith_2020')
        self.assertEqual(list(self.origin_files()), ['pool-569371.bib'])
        os.rename(self.path('pool'), self.path('sealevel'))
        self.lib('pull --pool ../sealevel')
        files = self.origin_files()
        self.assertEqual(list(files), ['sealevel-569371.bib'])
        self.assertIn('@comment{papers-pool-path ' + papers.config.short_home(self.path('sealevel')) + '}',
                      files['sealevel-569371.bib'])
        self.assertIsNotNone(self.origin().get(self.entry('Smith_2020'), IDENT))


# 3.3 WHAT A RECORD HOLDS
# =======================

class TestRecordContent(SpecTest):

    def test_time_format(self):
        "exchange.md 3.3: papers-time is local time, ISO 8601 with the UTC offset, to the second"
        self.lib('pull Smith_2020')
        time, = re.findall(r'papers-time = \{([^}]*)\}', self.origin_text())
        self.assertRegex(time, r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$')

    def test_push_of_a_new_entry(self):
        "exchange.md 3.3: the base of a push of a new entry has the fields of the library entry as sent"
        Path(self.path('new.bib')).write_text(NEW_BIB.replace('year = {2022}', 'ids = {old2022},\n year = {2022}'))
        Path(self.path('mine.pdf')).write_text('mine')
        self.lib('add ../new.bib')
        self.papers('config key.template {author}-{year}', cwd=self.path('pool'))
        self.lib('push mine2022')
        record = self.origin().get(self.entry('mine2022'))
        self.assertEqual(record.pool_key, 'mine-2022')
        self.assertEqual(record.key, 'mine2022')
        lib = self.entry('mine2022')
        expected = {k: v for k, v in lib.fields_dict.items() if k not in ('file', 'ids')}
        self.assertEqual({k: f.value for k, f in record.entry.fields_dict.items()},
                         {k: f.value for k, f in expected.items()})
        self.assertNotIn('old2022', self.origin_text())

    def test_record_ids_ignored_as_base(self):
        "exchange.md 3.3: ids of a record (written by another build) are no part of the base"
        self.take_smith()
        name = list(self.origin_files())[0]
        text = self.origin_files()[name].replace(' journal = ', ' ids = {x},\n journal = ')
        self.write_origin(name, text)
        self.assertNotIn('ids', self.origin().get(self.entry('smith2020climate')).entry.fields_dict)
        self.assertIn('nothing to pull from pool ../pool', self.out('pull'))


# 3.4 READING
# ===========

class TestOriginReading(SpecTest):

    def test_comments(self):
        "exchange.md 3.4: comments split into a first word and the rest; papers-pulled digits only"
        self.write_origin('x.bib', '@comment{  papers-pool   ../pool  }\n\n@comment{papers-pulled 12x}\n\n'
                                   '@comment{papers-pool-path   ~/some where }\n\n'
                                   '@article{a,\n papers-pool-key = {A},\n title = {A}\n}\n')
        origin = self.origin()
        self.assertEqual(list(origin.entries), ['../pool'])
        self.assertIsNone(origin.pulled('../pool'))
        self.assertEqual(origin.paths['../pool'], '~/some where')
        self.write_origin('x.bib', '@comment{papers-pool ../pool}\n\n@comment{papers-pulled 12}\n')
        self.assertEqual(self.origin().pulled('../pool'), 12)

    def test_files_ignored(self):
        "exchange.md 3.4: only .bib files; a file without papers-pool comment is ignored with a warning"
        self.write_origin('notes.txt', '@comment{papers-pool ../pool}\n\n@article{a,\n title = {A}\n}\n')
        self.write_origin('none.bib', '@article{b,\n title = {B}\n}\n')
        with self.assertLogs(papers.logger, level='WARNING') as cm:
            origin = self.origin()
        self.assertEqual(origin.entries, {})
        self.assertTrue(any('none.bib' in m and 'papers-pool' in m for m in cm.output), cm.output)

    def test_keys_without_case(self):
        "exchange.md 3.4: records by lower-case key; the last file read (name order) wins; former keys"
        self.write_origin('a.bib', '@comment{papers-pool ../pool}\n\n@article{Key,\n papers-pool-key = {A},\n'
                                   ' title = {A}\n}\n')
        self.write_origin('b.bib', '@comment{papers-pool ../pool}\n\n@article{KEY,\n papers-pool-key = {B},\n'
                                   ' title = {B}\n}\n')
        from papers.entries import entry_from_dict
        origin = self.origin()
        self.assertEqual(origin.get(entry_from_dict({'ID': 'key', 'ENTRYTYPE': 'article'})).pool_key, 'B')
        renamed = entry_from_dict({'ID': 'new', 'ENTRYTYPE': 'article', 'ids': 'other, kEy'})
        self.assertEqual(origin.get(renamed).pool_key, 'B')

    def test_utf8_with_bom(self):
        "exchange.md 3.4: origin files are read as UTF-8, a byte order mark dropped"
        os.makedirs(self.path('lib', ORIGIN_DIR))
        Path(self.path('lib', ORIGIN_DIR, 'x.bib')).write_bytes(
            '\ufeff@comment{papers-pool ../pool}\n\n@article{a,\n papers-pool-key = {A},\n title = {Été}\n}\n'
            .encode('utf-8'))
        with patch('locale.getpreferredencoding', lambda *a: 'latin-1'):
            origin = self.origin()
        self.assertEqual(list(origin.entries), ['../pool'])
        self.assertEqual(origin.entries['../pool']['a']['title'], 'Été')


# 3.5 WRITING
# ===========

class TestOriginWriting(SpecTest):

    def test_same_record_keeps_its_time(self):
        "exchange.md 3.5: setting the same record again leaves its papers-time"
        self.take_smith()
        before = self.origin_text()
        self.edit_pool('@article{Brown_2021,', '@article{Brown_2021,\n note = {x},')  # the pool changed elsewhere
        self.lib('pull smith2020climate')
        self.assertEqual(self.origin_text(), before)

    def test_unchanged_file_not_written(self):
        "exchange.md 3.5: a file whose content would not change is not written"
        self.take_smith()
        file = self.path('lib', ORIGIN_DIR, list(self.origin_files())[0])
        os.utime(file, ns=(1, 1))
        self.lib('pull')
        self.assertEqual(os.stat(file).st_mtime_ns, 1)

    def test_dry_run_writes_nothing(self):
        "exchange.md 3.5: with --dry-run no origin file is written"
        self.lib('pull --all --dry-run')
        self.assertEqual(self.origin_files(), {})

    def test_add_keeps_an_existing_record(self):
        "exchange.md 3.5: add from the pool records the pool entry only if the entry has no record for the pool"
        self.take_smith()
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        before = self.origin_text()
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            self.lib('add --doi 10.1000/abc123')  # the library has it: the files attached, if any
        self.assertEqual(self.origin_text(), before)


# 3.6 THE EXCHANGE TIME
# =====================

class TestExchangeTime(SpecTest):

    def pulled(self):
        "the exchange time of the one pool (its records may still be under its path id)"
        pulls = self.origin().pulls
        self.assertLessEqual(len(pulls), 1, pulls)
        return next(iter(pulls.values()), None)

    def test_value_is_the_pool_mtime(self):
        "exchange.md 3.6: papers-pulled is the modification time of the pool's bibtex, in nanoseconds"
        os.utime(self.path('pool', 'papers.bib'), ns=(1234567891234567891, 1234567891234567891))
        self.lib('pull --all')
        self.assertEqual(self.pulled(), 1234567891234567891)
        self.assertIn('@comment{papers-pulled 1234567891234567891}', self.origin_text())

    def test_push_after_a_pool_change(self):
        "exchange.md 3.6: a push after the pool changed since the last exchange does not set the time"
        self.take_smith()
        recorded = self.pulled()
        self.edit_pool('@article{Brown_2021,', '@article{Brown_2021,\n note = {x},')
        os.utime(self.path('pool', 'papers.bib'), ns=(5, 5))
        self.edit_lib('journal = {Nat.}', 'journal = {Nature}')
        self.lib('push')
        self.assertIn('journal = {Nature}', self.pool_text())
        self.assertEqual(self.pulled(), recorded)
        # a push to an unchanged pool sets it
        self.lib('pull')
        self.edit_lib('journal = {Nature}', 'journal = {Nature Geo}')
        self.lib('push')
        self.assertEqual(self.pulled(), self.mtime())

    def test_link_update(self):
        "exchange.md 3.6: a link update sets the time only when the pool had not changed since the last exchange"
        self.lib('config pool ../pool -y')
        self.lib('config files link')
        self.take_smith()
        Path(self.path('si.pdf')).write_text('supplement')
        self.lib(f'file attach smith2020climate {self.path("si.pdf")}')
        self.assertIn('si.pdf', self.pool_text())
        self.assertEqual(self.pulled(), self.mtime())
        # the pool changed: a link update does not hide it
        self.edit_pool('@article{Brown_2021,', '@article{Brown_2021,\n note = {x},')
        os.utime(self.path('pool', 'papers.bib'), ns=(5, 5))
        recorded = self.pulled()
        self.lib(f'file detach {self.path("si.pdf")}')
        self.assertNotIn('si.pdf', self.pool_text())
        self.assertEqual(self.pulled(), recorded)

    def test_later_add_keeps_the_time(self):
        "exchange.md 3.6: only the first exchange by add records the time"
        self.take_smith()
        recorded = self.pulled()
        self.assertEqual(recorded, self.mtime())
        self.edit_pool('@article{Brown_2021,', '@article{Brown_2021,\n note = {x},')
        os.utime(self.path('pool', 'papers.bib'), ns=(5, 5))
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            self.lib('add --doi 10.1000/brown')
        self.assertEqual(self.pulled(), recorded)

    def test_quit_does_not_set_it(self):
        "exchange.md 3.6, 5.7: a pull whose dialogue was quit does not set the time"
        self.take_smith()
        recorded = self.pulled()
        self.edit_pool('journal = {Nat.}', 'journal = {Nature Climate Change}')
        self.edit_lib('journal = {Nat.}', 'journal = {Nature}')
        os.utime(self.path('pool', 'papers.bib'), ns=(5, 5))
        with patch('builtins.input', lambda prompt: 'q'):
            self.lib('pull --on-duplicate ask')
        self.assertEqual(self.pulled(), recorded)
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature')


# 3.7 RENAMED KEYS
# ================

class TestRenamedKeys(SpecTest):

    def test_replaced_in_every_pool(self):
        "exchange.md 3.7: a rename moves the records in every pool file, the pool key unchanged"
        self.papers('init other')
        Path(self.path('other', 'papers.bib')).write_text(SMITH_BIB.replace('smith2020climate', 'S2020'))
        self.take_smith()
        self.lib('pull --pool ../other smith2020climate')
        self.lib('edit smith2020climate --key smith2020')
        origin = self.origin()
        for pool, pool_key in [('../pool', 'Smith_2020'), ('../other', 'S2020')]:
            with self.subTest(pool=pool):
                self.assertEqual(list(origin.entries[pool]), ['smith2020'])
                record = origin.get(self.entry('smith2020'), pool)
                self.assertEqual((record.key, record.pool_key), ('smith2020', pool_key))

    @unittest.expectedFailure
    def test_shallow_library(self):
        "exchange.md 3.7: in a shallow library too, the record follows the renamed key"
        # bug: save_entries (papers/cli/common.py) rekeys the records and saves them, then savebib
        # (follow_renamed_keys, papers/library.py) rekeys them again on disk: the old key has no
        # record any more, so Origin.rekey drops the record under the new key as a leftover
        self.lib('config pool ../pool -y')
        self.take_smith()
        self.lib('edit smith2020climate --key smith2020')
        record = self.origin().get(self.entry('smith2020'))
        self.assertIsNotNone(record)
        self.assertEqual(record.pool_key, 'Smith_2020')


# 3.8 LEGACY FILE
# ===============

class TestLegacyOrigin(SpecTest):

    def legacy(self):
        legacy = self.path('lib', LEGACY_ORIGIN_FILE)
        os.makedirs(os.path.dirname(legacy), exist_ok=True)
        Path(legacy).write_text(
            '@comment{papers-pull 12345 ../pool}\n\n'
            '@article{a2020,\n papers-pool = {../pool},\n papers-pool-key = {Legacy},\n title = {A}\n}\n\n'
            '@article{b2020,\n papers-pool-key = {B_2020},\n title = {B}\n}\n')
        return legacy

    def test_origin_dir_wins(self):
        "exchange.md 3.8: the legacy file is read after origin/, where origin/ has none; missing papers-pool: ''"
        self.write_origin('x.bib', '@comment{papers-pool ../pool}\n\n@comment{papers-pulled 99}\n\n'
                                   '@article{a2020,\n papers-pool-key = {New},\n title = {A}\n}\n')
        legacy = self.legacy()
        origin = self.origin()
        self.assertEqual(origin.entries['../pool']['a2020']['papers-pool-key'], 'New')
        self.assertEqual(origin.pulled('../pool'), 99)
        self.assertEqual(list(origin.entries['']), ['b2020'])
        self.assertFalse(os.path.exists(legacy))
        self.assertNotIn('papers-pool =', ''.join(self.origin_files().values()))

    def test_dry_run_keeps_it(self):
        "exchange.md 3.8: with --dry-run the legacy file stays"
        legacy = self.legacy()
        self.lib('pull --dry-run')
        self.assertTrue(os.path.exists(legacy))


# 3.9 RECORDS UNDER A PATH ID
# ===========================

class TestPathIdRecords(SpecTest):

    def setUp(self):
        super().setUp()
        self.take_smith()  # records under ../pool
        set_id(self.path('pool'), IDENT)
        self.before = self.origin_files()

    def test_move(self):
        "exchange.md 3.9: records and time move to the identifier, papers-pool-path set, old file removed"
        pulled = self.origin().pulled('../pool')
        self.lib('pull')
        files = self.origin_files()
        self.assertEqual(list(files), ['pool-569371.bib'])
        text = files['pool-569371.bib']
        self.assertTrue(text.startswith(f'@comment{{papers-pool {IDENT}}}\n\n@comment{{papers-pulled '))
        self.assertIn('@comment{papers-pool-path ' + papers.config.short_home(self.path('pool')) + '}', text)
        origin = self.origin()
        self.assertEqual(origin.pulled(IDENT), pulled)
        self.assertEqual(origin.get(self.entry('smith2020climate'), IDENT).pool_key, 'Smith_2020')

    def test_status_writes_nothing(self):
        "exchange.md 2.3, 3.9: papers status does not write the move"
        self.lib('config pool ../pool -y')
        self.before = self.origin_files()
        self.out('status')
        self.assertEqual(self.origin_files(), self.before)

    def test_other_path_id_stays(self):
        "exchange.md 3.9: a path id that does not designate the pool of the command stays"
        self.papers('init other')
        Path(self.path('other', 'papers.bib')).write_text(NEW_BIB.replace(' file = {:mine.pdf:pdf},\n', ''))
        self.lib('pull --pool ../other mine2022')
        other = [n for n in self.origin_files() if n.startswith('other-')]
        self.lib('pull')
        self.assertEqual(sorted(self.origin_files()), sorted(other + ['pool-569371.bib']))
        self.assertIn('../other', self.origin().entries)


# 4.1 THE POOL ENTRY OF A LIBRARY ENTRY
# =====================================

class TestPoolEntry(SpecTest):

    def test_record_key_by_identity_of_the_entry(self):
        "exchange.md 4.1 (1.1): the pool entry of the record's key, if the same paper as the library entry"
        self.take_smith()
        # the base changed its DOI (not the same paper as the pool entry), the entry is still the same paper
        name = list(self.origin_files())[0]
        self.write_origin(name, self.origin_files()[name].replace('10.1000/abc123', '10.1000/zzz')
                          .replace('Climate sensitivity revisited', 'Something else'))
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        self.lib('pull --on-duplicate update')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature')

    def no_doi(self):
        "smith2020climate taken from the pool, without DOI on both sides"
        self.edit_pool(' doi = {10.1000/abc123},\n', '')
        Path(self.path('smith.bib')).write_text(SMITH_BIB.replace(' doi = {10.1000/ABC123},\n', ''))
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            self.lib('add ../smith.bib')
        self.assertIsNotNone(self.origin().get(self.entry('smith2020climate')))

    def test_titles_changed_on_both_sides(self):
        "exchange.md 4.1 (1.4): found under the record's pool key, same authors and year"
        self.no_doi()
        self.edit_pool('Climate sensitivity revisited', 'Climate sensitivity, again')
        self.edit_lib('Climate sensitivity revisited', 'Climate sensitivity reconsidered')
        out = self.out('pull --check')
        self.assertIn('smith2020climate: changed in pool ../pool: title (1 conflict)', out)

    def test_reused_pool_key(self):
        "exchange.md 4.1 (1.4): another paper under the record's pool key (other authors) is not taken"
        self.no_doi()
        self.edit_pool('Climate sensitivity revisited', 'Another paper')
        self.edit_pool('Smith, John and Doe, Jane', 'Other, Ann')
        self.edit_lib('Climate sensitivity revisited', 'Climate sensitivity reconsidered')
        out = self.out('pull')
        self.assertIn('smith2020climate: removed from pool ../pool', out)

    def test_distinct_pairs_of_both_sides(self):
        "exchange.md 4.1: the not-same-paper pairs of the pool's distinct.json are used"
        Path(self.path('lib', 'papers.bib')).write_text(SMITH_BIB)
        from papers.duplicate import Distinct
        d = Distinct.for_library(self.path('pool'))
        d.pairs.append([{'doi': '10.1000/abc123'}, {'doi': '10.1000/abc123'}])
        d.changed = True
        d.save()
        # the pair says that entries of this DOI are not the same paper: nothing shared
        self.assertEqual(self.out('pull'), 'nothing to pull from pool ../pool')
        self.assertEqual(self.origin().records(), [])

    def test_ask_verdict_is_no_match(self):
        "exchange.md 4.1: an ask verdict (title guard) is no match"
        Path(self.path('lib', 'papers.bib')).write_text(
            '@incollection{chapter,\n author = {Brown, Bob},\n doi = {10.1000/brown},\n'
            ' title = {A chapter on ocean heat},\n year = {2021}\n}\n')
        self.lib('pull --all')
        self.assertEqual(sorted(self.bib()[1]), ['Brown_2021', 'Smith_2020', 'chapter'])
        self.assertIsNone(self.origin().get(self.entry('chapter')))


# 4.2 THE LIBRARY ENTRY OF A POOL ENTRY
# =====================================

class TestLibraryEntry(SpecTest):

    def test_record_of_the_pool_key_first(self):
        "exchange.md 4.2 (1): the library entry with a record of this pool key, before the same paper"
        self.take_smith()
        # a second library entry of the same paper, before it in the library
        self.edit_lib('@article{smith2020climate,', SMITH_BIB.replace('smith2020climate', 'aaa2020') +
                      '\n@article{smith2020climate,')
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        self.lib('pull Smith_2020 --on-duplicate update')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature')
        self.assertNotIn('journal', self.entry('aaa2020'))


# 5.1 SIDES
# =========

class TestSides(SpecTest):

    def test_links_written_for_the_target(self):
        "exchange.md 5.1: the incoming file links are written for the target library"
        self.lib('config paths absolute')
        self.lib('pull Smith_2020')
        self.assertIn(f'file = {{:{self.pool_pdf}:pdf}}', self.lib_text())
        self.lib('config paths relative')
        Path(self.path('lib', 'papers.bib')).write_text('')
        shutil.rmtree(self.path('lib', ORIGIN_DIR))
        self.lib('pull Smith_2020')
        self.assertIn('file = {:../pool/files/smith.pdf:pdf}', self.lib_text())


# 5.3 THE THREE-WAY RULE
# ======================

class TestThreeWayRule(SpecTest):
    "the rows of the table of 5.3, through pull (target: the library, incoming: the pool)"

    BASE = 'Base value'

    def check(self, t, o, b, expected, conflict=False):
        """a field `note` with the target value t, the incoming value o and the
        base value b (None: absent); the result after pull --on-duplicate keep"""
        def entry(key, value):
            note = f' note = {{{value}}},\n' if value is not None else ''
            return (f'@article{{{key},\n author = {{Brown, Bob}},\n doi = {{10.1000/brown}},\n{note}'
                    f' title = {{Ocean heat}},\n year = {{2021}}\n}}\n')
        Path(self.path('pool', 'papers.bib')).write_text(entry('Brown_2021', o))
        Path(self.path('lib', 'papers.bib')).write_text(entry('brown2021', t))
        shutil.rmtree(self.path('lib', ORIGIN_DIR), ignore_errors=True)
        self.write_origin('o.bib', '@comment{papers-pool ../pool}\n\n' +
                          entry('brown2021', b).replace(' title', ' papers-pool-key = {Brown_2021},\n title'))
        out = self.out('pull --check')
        self.assertEqual('(1 conflict)' in out, conflict, out)
        self.lib('pull --on-duplicate keep')
        e = self.entry('brown2021')
        self.assertEqual(e['note'] if 'note' in e.fields_dict else None, expected)

    def test_table(self):
        "exchange.md 5.3: each row of the three-way table"
        rows = [
            # t, o, b, result, conflict
            ('CO2', '{CO2}', 'CO2', '{CO2}', False),  # target identical to base, equivalent change: taken
            ('{CO2}', 'CO2', 'co2', '{CO2}', False),  # both equivalent, target not the base: target's spelling
            ('x', 'x', None, 'x', False),  # same
            ('x', None, None, 'x', False),  # added in the target
            (None, 'x', None, 'x', False),  # addition
            ('x', 'b', 'b', 'x', False),  # changed in the target
            (None, 'b', 'b', None, False),  # removed in the target
            ('b', 'y', 'b', 'y', False),  # changed in the incoming entry
            ('b', None, 'b', None, False),  # removed in the incoming entry
            ('x', 'y', 'b', 'x', True),  # changed on both sides
            (None, 'y', 'b', None, True),  # removed on one side, changed on the other
            ('x', 'y', None, 'x', True),  # added on both sides, differently
            (None, None, 'b', None, False),  # removed on both sides
            ('  ', 'x', None, 'x', False),  # whitespace-only counts as absent
        ]
        for t, o, b, expected, conflict in rows:
            with self.subTest(t=t, o=o, b=b):
                self.check(t, o, b, expected, conflict)

    def test_entry_type(self):
        "exchange.md 5.2, 5.3: the entry type is merged as a field, compared in lower case"
        self.take_smith()
        self.edit_pool('@article{Smith_2020', '@Article{Smith_2020')
        self.assertIn('nothing to pull', self.out('pull'))
        self.edit_pool('@Article{Smith_2020', '@book{Smith_2020')
        self.lib('pull')
        self.assertEqual(self.entry('smith2020climate').entry_type.lower(), 'book')


# 5.4 WITHOUT BASE
# ================

class TestWithoutBase(SpecTest):

    def test_table(self):
        "exchange.md 5.4: the rows of the two-way table, through pull of an entry without record"
        rows = [
            # library value, pool value, result, conflict
            ('Nat.', 'Nat.', 'Nat.', False),
            ('nat.', 'Nat.', 'nat.', False),  # equivalent: the target's spelling
            ('Nat.', None, 'Nat.', False),
            (None, 'Nat.', 'Nat.', False),
            ('Nat.', 'Nature', 'Nat.', True),
        ]
        for t, o, expected, conflict in rows:
            with self.subTest(t=t, o=o):
                journal = lambda v: f' journal = {{{v}}},\n' if v is not None else ''
                Path(self.path('pool', 'papers.bib')).write_text(POOL_BIB.replace(' journal = {Nat.},\n', journal(o)))
                Path(self.path('lib', 'papers.bib')).write_text(SMITH_BIB.replace(' title', journal(t) + ' title'))
                shutil.rmtree(self.path('lib', ORIGIN_DIR), ignore_errors=True)
                if conflict:
                    with self.assertRaisesRegex(PapersExit, '1 conflict'):
                        self.out('pull')
                self.lib('pull --on-duplicate keep')
                e = self.entry('smith2020climate')
                self.assertEqual(e['journal'] if 'journal' in e.fields_dict else None, expected)
                self.assertIsNotNone(self.origin().get(e))


# 5.5 OUTCOME
# ===========

class TestOutcome(SpecTest):

    def test_linked_writes_a_record_only(self):
        "exchange.md 5.5: nothing to merge and no record: linked, the library entry unchanged, the record set"
        self.lib('pull Smith_2020')
        shutil.rmtree(self.path('lib', ORIGIN_DIR))
        before = self.lib_text()
        out = self.out('pull')
        self.assertIn('1 linked', out)
        self.assertEqual(self.lib_text(), before)
        self.assertIsNotNone(self.origin().get(self.entry('Smith_2020')))

    def test_skip_comes_again(self):
        "exchange.md 5.5: a skipped conflict sets no record, so the entry comes again"
        self.take_smith()
        self.edit_pool('journal = {Nat.}', 'journal = {Nature Climate Change}')
        self.edit_lib('journal = {Nat.}', 'journal = {Nature}')
        before = self.origin_text()
        self.assertIn('skipped', self.out('pull --on-duplicate skip'))
        self.assertEqual(self.origin_text(), before)
        self.assertIn('skipped', self.out('pull --on-duplicate skip'))


# 5.6 --on-duplicate
# ==================

class TestOnDuplicate(SpecTest):

    def conflict(self):
        self.take_smith()
        self.edit_pool('journal = {Nat.}', 'journal = {Pool J.}')
        self.edit_lib('journal = {Nat.}', 'journal = {Lib J.}')

    def test_sync_keep_and_update(self):
        "exchange.md 5.6: sync keep ends with the library's values on both sides, update with the pool's"
        for mode, value in [('keep', 'Lib J.'), ('update', 'Pool J.')]:
            with self.subTest(mode=mode):
                Path(self.path('lib', 'papers.bib')).write_text('')
                shutil.rmtree(self.path('lib', ORIGIN_DIR), ignore_errors=True)
                Path(self.path('pool', 'papers.bib')).write_text(POOL_BIB)
                self.conflict()
                self.lib(f'sync --on-duplicate {mode}')
                self.assertEqual(self.entry('smith2020climate')['journal'], value)
                self.assertEqual(self.entry('Smith_2020', 'pool')['journal'], value)

    def test_update_takes_a_removal(self):
        "exchange.md 5.6: update takes a removal as a removal"
        self.take_smith()
        self.edit_pool(' journal = {Nat.},\n', '')
        self.edit_lib('journal = {Nat.}', 'journal = {Lib J.}')
        self.lib('pull --on-duplicate update')
        self.assertNotIn('journal', self.entry('smith2020climate').fields_dict)

    def test_additions_in_every_mode(self):
        "exchange.md 5.6: additions are taken in every mode, skip too, when the entry has no conflict"
        self.take_smith()
        self.edit_pool('journal = {Nat.}', 'journal = {Nat.},\n volume = {3}')
        for mode in ('skip', 'error'):
            with self.subTest(mode=mode):
                self.lib(f'pull --on-duplicate {mode}')
                self.assertEqual(self.entry('smith2020climate')['volume'], '3')


# 6.1 PULL SELECTION
# ==================

class TestPullSelection(SpecTest):

    def test_list_pull(self):
        "exchange.md 6.1 (4): list --pull pulls the listed entries, no new entries"
        self.take_smith()
        Path(self.path('new.bib')).write_text(NEW_BIB.replace(' file = {:mine.pdf:pdf},\n', ''))
        self.lib('add ../new.bib --no-pool')
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        self.lib('list smith --pull --pool ../pool')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature')
        self.assertEqual(sorted(self.bib()[1]), ['mine2022', 'smith2020climate'])


# 6.2 PULL STEPS
# ==============

class TestPullSteps(SpecTest):

    def test_repair_before_the_merge(self):
        "exchange.md 6.2 (2), 15.3: a pull repairs the broken links to pool files of a shared entry"
        self.lib('config pool ../pool -y')
        self.take_smith()
        new = self.path('pool', 'files', 'renamed.pdf')
        os.rename(self.pool_pdf, new)
        self.edit_pool('files/smith.pdf', 'files/renamed.pdf')
        self.lib('pull')
        self.assertEqual(self.files('smith2020climate'), [new])


# 6.3 NEW ENTRIES OF A PULL
# =========================

class TestPullNew(SpecTest):

    def test_fields_without_ids(self):
        "exchange.md 6.3: a new entry has the fields of the pool entry, without ids"
        self.edit_pool('journal = {Nat.}', 'ids = {old_smith},\n journal = {Nat.}')
        self.lib('pull Smith_2020')
        e = self.entry('Smith_2020')
        self.assertNotIn('ids', e.fields_dict)
        self.assertEqual(e['journal'], 'Nat.')

    def test_suffix_without_case(self):
        "exchange.md 6.3: the pool key taken without case gets the letter suffix"
        Path(self.path('lib', 'papers.bib')).write_text(NEW_BIB.replace('mine2022', 'smith_2020')
                                                        .replace(' file = {:mine.pdf:pdf},\n', ''))
        self.lib('pull --all')
        self.assertEqual(sorted(self.bib()[1]), ['Brown_2021', 'Smith_2020b', 'smith_2020'])


# 6.4 FILES OF A PULL
# ===================

class TestPullFiles(SpecTest):

    def test_files_kept_where_they_are(self):
        "exchange.md 6.4: the files the entry had before stay where they are"
        self.lib('config files copy')
        self.take_smith()
        own = self.files('smith2020climate')
        Path(self.path('pool', 'files', 'si.pdf')).write_text('supplement')
        self.edit_pool('file = {:files/smith.pdf:pdf}', 'file = {:files/smith.pdf:pdf;:files/si.pdf:pdf}')
        self.lib('pull')
        files = self.files('smith2020climate')
        self.assertEqual(files[:len(own)], own)
        self.assertTrue(files[-1].startswith(self.path('lib', 'files')))

    def test_move_mode_copies(self):
        "exchange.md 6.4: a file of a pool is copied, never moved, in move mode too"
        self.lib('config files move')
        self.lib('pull Smith_2020')
        self.assertTrue(self.files('Smith_2020')[0].startswith(self.path('lib', 'files')))
        self.assertTrue(os.path.exists(self.pool_pdf))

    def test_without_files_directory(self):
        "exchange.md 6.4: without files directory, the files are linked"
        self.lib('config files copy')
        js = self.json('lib')
        js['filesdir'] = None
        Path(self.path('lib', CONFIG_FILE_LOCAL)).write_text(json.dumps(js))
        self.lib('pull Smith_2020')
        self.assertEqual(self.files('Smith_2020'), [self.pool_pdf])


# 7.1 PUSH SELECTION
# ==================

class TestPushSelection(SpecTest):

    def removed(self):
        self.take_smith()
        self.edit_pool('@article{Smith_2020,', '@article{Other_2020,')
        self.edit_pool('doi = {10.1000/abc123}', 'doi = {10.1000/other}')
        self.edit_pool('title = {Climate sensitivity revisited}', 'title = {Other}')

    def test_all_adds_back_removed(self):
        "exchange.md 7.1: push --all includes the entries removed from the pool"
        self.removed()
        out = self.out('push --all')
        self.assertRegex(out, r'Added -> smith2020climate: .* \[to pool ../pool\]')

    def test_list_push(self):
        "exchange.md 7.1: list --push pushes the listed entries"
        Path(self.path('new.bib')).write_text(NEW_BIB.replace(' file = {:mine.pdf:pdf},\n', ''))
        self.lib('add ../new.bib')
        self.lib('list mine --push --pool ../pool')
        self.assertEqual(len(self.bib('pool')[1]), 3)


# 7.2 PUSH STEPS
# ==============

class TestPushSteps(SpecTest):

    def test_new_file_copied_into_the_pool(self):
        "exchange.md 7.2: a new file of a pushed entry is copied into the pool's files directory; the pool's stay"
        self.take_smith()
        Path(self.path('si.pdf')).write_text('supplement')
        self.lib(f'file attach smith2020climate {self.path("si.pdf")} --copy')
        self.lib('push')
        files = self.files('Smith_2020', 'pool')
        self.assertEqual(files[0], self.pool_pdf)
        self.assertEqual(len(files), 2)
        self.assertTrue(files[1].startswith(self.path('pool', 'files')), files)
        self.assertEqual(Path(files[1]).read_text(), 'supplement')


# 7.3 ENTRIES NEW TO THE POOL
# ===========================

class TestPushNew(SpecTest):

    def add(self, bib):
        Path(self.path('lib', 'papers.bib')).write_text(bib)

    def test_empty_entry(self):
        "exchange.md 7.3: an entry with no field other than file and ids is not pushed (empty)"
        self.add('@misc{empty,\n ids = {x}\n}\n')
        out = self.out('push --all')
        self.assertIn('Not pushed -> empty', out)
        self.assertEqual(len(self.bib('pool')[1]), 2)

    def test_key_suffix_in_the_pool(self):
        "exchange.md 7.3: the key of the pool's template gets the suffix rule against the pool's keys"
        self.papers('config key.template {author}_{year}', cwd=self.path('pool'))
        self.add('@article{x,\n author = {Brown, Ann},\n title = {Another},\n year = {2021}\n}\n')
        self.lib('push --all')
        self.assertEqual(sorted(self.bib('pool')[1]), ['Brown_2021', 'Smith_2020', 'brown_2021b'])
        self.assertEqual(self.origin().get(self.entry('x')).pool_key, 'brown_2021b')

    def test_no_key_template_key(self):
        "exchange.md 7.3: when the pool's template gives no key, the library key, with a suffix if needed"
        self.papers('config key.template {journal}', cwd=self.path('pool'))
        self.add('@article{Brown_2021,\n author = {Ann, Other},\n title = {Another},\n year = {1999}\n}\n')
        self.lib('push --all')
        self.assertIn('Brown_2021b', self.bib('pool')[1])

    def test_fields_without_ids(self):
        "exchange.md 7.3: the fields of the library entry, without ids"
        self.add('@article{x,\n author = {Ann, Other},\n ids = {old},\n title = {Another},\n year = {1999}\n}\n')
        self.papers('config key.template {author}{year}', cwd=self.path('pool'))
        self.lib('push --all')
        pool = self.bib('pool')[1]
        new, = [e for k, e in pool.items() if k not in ('Smith_2020', 'Brown_2021')]
        self.assertNotIn('ids', new.fields_dict)
        self.assertEqual(new['title'], 'Another')


# 8. SYNC
# =======

class TestSync(SpecTest):

    def test_conflict_exit_status(self):
        "exchange.md 8 (2): a pull that left a conflict: the pull saved, nothing pushed, an error"
        self.take_smith()
        Path(self.path('new.bib')).write_text(NEW_BIB.replace(' file = {:mine.pdf:pdf},\n', ''))
        self.lib('add ../new.bib --no-pool')
        self.edit_pool('journal = {Nat.}', 'journal = {Pool J.},\n volume = {3}')
        self.edit_lib('journal = {Nat.}', 'journal = {Lib J.}')
        self.edit_pool('@article{Brown_2021,', '@article{Brown_2021,\n note = {x},')
        Path(self.path('lib', 'papers.bib')).write_text(self.lib_text() + '\n' + POOL_BIB.split('\n\n')[1]
                                                         .replace('Brown_2021', 'brown2021'))
        with self.assertRaisesRegex(PapersExit, r'not pushed: the pull left conflicts undecided \(smith2020climate\)'):
            self.lib('sync --on-duplicate skip')
        self.assertEqual(self.entry('brown2021')['note'], 'x')  # the pull is saved
        self.assertNotIn('Lib J.', self.pool_text())


# 9. PULL --CHECK
# ===============

class TestPullCheck(SpecTest):

    def test_nothing_written(self):
        "exchange.md 9: pull --check merges and writes nothing, and drops no record"
        self.take_smith()
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        lib, origin = self.lib_text(), self.origin_files()
        self.out('pull --check')
        self.assertEqual((self.lib_text(), self.origin_files()), (lib, origin))

    def test_fields_sorted_and_conflicts(self):
        "exchange.md 9: the fields sorted, with the count of conflicts"
        self.take_smith()
        self.edit_pool('journal = {Nat.}', 'journal = {Pool J.},\n volume = {3}')
        self.edit_pool('year = {2020}', 'year = {2021}')
        self.edit_lib('journal = {Nat.}', 'journal = {Lib J.}')
        self.edit_lib('year = {2020}', 'year = {2019}')
        self.assertIn('smith2020climate: changed in pool ../pool: journal, volume, year (2 conflicts)',
                      self.out('pull --check'))

    def test_nothing_to_pull(self):
        "exchange.md 9: no line about an entry: nothing to pull"
        self.take_smith()
        self.assertEqual(self.out('pull --check smith2020climate'), 'nothing to pull')

    def test_not_pulled_from_yet(self):
        "exchange.md 14.2: no papers-pulled and no record: not pulled from yet"
        self.assertEqual(self.state(), 'pool ../pool: not pulled from yet')


# 12.1 AUTOMATIC PUSHES
# =====================

class TestAutoPush(SpecTest):

    def test_pool_unusable_warns(self):
        "exchange.md 12.1: when the pool cannot be used (missing), a warning, and the library is saved"
        self.lib('config pool ../pool -y')
        self.lib('config auto-push true')
        self.take_smith()
        os.rename(self.path('pool'), self.path('elsewhere'))
        with self.assertLogs(papers.logger, level='WARNING') as cm:
            self.lib('tag smith2020climate --add x')
        self.assertTrue(any('not pushed to the pool' in m and 'does not exist' in m for m in cm.output), cm.output)
        self.assertIn('keywords = {x}', self.lib_text())

    def test_renamed_entry_is_not_new(self):
        "exchange.md 12.1 (2): an entry renamed in the command is not new: pushed onto its pool entry"
        self.lib('config pool ../pool -y')
        self.lib('config auto-push true')
        self.take_smith()

        def edit(entries):
            entries[0].key = 'smith2020'
            entries[0]['journal'] = 'Nature'
            return entries
        with patch('papers.cli.common.edit_in_editor', side_effect=edit):
            self.lib('edit smith2020climate')
        self.assertEqual(sorted(self.bib()[1]), ['smith2020'])
        pool = self.bib('pool')[1]
        self.assertEqual(sorted(pool), ['Brown_2021', 'Smith_2020'])
        self.assertEqual(pool['Smith_2020']['journal'], 'Nature')


# 12.3 LINK UPDATES
# =================

class TestLinkUpdates(SpecTest):

    def test_record_file_field(self):
        "exchange.md 12.3: the record's file field is set to the new links of the pool entry"
        self.lib('config pool ../pool -y')
        self.lib('config files link')
        self.take_smith()
        Path(self.path('si.pdf')).write_text('supplement')
        self.lib(f'file attach smith2020climate {self.path("si.pdf")}')
        record = self.origin().get(self.entry('smith2020climate'))
        self.assertEqual(record.files, ':../pool/files/smith.pdf:pdf;:../si.pdf:pdf')


# 13.1 ADD: LOOKUP
# ================

class TestAddLookup(SpecTest):

    def test_bibtex_entry_keeps_its_key_and_fields(self):
        "exchange.md 13.1: an added bibtex entry keeps its key; its fields the pool entry lacks are added; pool wins"
        Path(self.path('smith.bib')).write_text(SMITH_BIB.replace('year = {2020}', 'journal = {Other},\n'
                                                                  ' note = {mine},\n year = {2020}'))
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch):
            self.lib('add ../smith.bib')
        e = self.entry('smith2020climate')
        self.assertEqual((e['journal'], e['note']), ('Nat.', 'mine'))
        self.assertEqual(self.origin().get(e).pool_key, 'Smith_2020')

    def test_pdf_metadata_doi(self):
        "exchange.md 13.1: a PDF: the DOI of its metadata, then the pool entry of that DOI"
        Path(self.path('other.pdf')).write_text('another pdf')
        with patch('papers.bib.fetch_bibtex_by_doi', no_fetch), \
             patch('papers.bib.extract_pdf_metadata', no_fetch), \
             patch('papers.pools.parse_doi_from_pdf_metadata', lambda pdf: '10.1000/brown'):
            self.lib('add ../other.pdf')
        e, = self.bib()[1].values()
        self.assertEqual(e['title'], 'Ocean heat')
        self.assertEqual(self.origin().get(e).pool_key, 'Brown_2021')


# 14.1 STATUS LINE
# ================

class TestStatusLine(SpecTest):

    def test_not_a_library(self):
        "exchange.md 14.1: a pool directory without library configuration: not a library"
        self.lib('config pool ../pool -y')
        os.remove(self.path('pool', CONFIG_FILE_LOCAL))
        self.assertIn('* pool:   ../pool (', self.out('status'))
        self.assertIn('not a library', self.out('status').split('* pool:')[1].splitlines()[0])


# 14.3 STATUS COMPARISON
# ======================

class TestStatusComparison(SpecTest):

    def setUp(self):
        super().setUp()
        self.lib('config pool ../pool -y')

    def pool_line(self):
        return next(line for line in self.out('status').splitlines() if line.startswith('* pool:'))

    def test_entry_without_record_not_compared(self):
        "exchange.md 14.3 (1): an entry without record is not considered"
        self.take_smith()
        self.lib('pull')
        Path(self.path('lib', 'papers.bib')).write_text(
            self.lib_text() + '\n' + POOL_BIB.split('\n\n')[1].replace('Brown_2021', 'brown2021')
            .replace('Ocean heat', 'Ocean heat (library)'))
        self.assertTrue(self.pool_line().endswith('(in sync)'), self.pool_line())

    def test_link_removed_by_the_pool(self):
        "exchange.md 14.3 (4), 15.2: a link removed by the pool makes pool changed, not both changed"
        self.lib('config files link')
        self.take_smith()
        Path(self.path('si.pdf')).write_text('supplement')
        self.lib(f'file attach smith2020climate {self.path("si.pdf")}')
        self.papers(f'file detach {self.path("si.pdf")}', cwd=self.path('pool'))
        self.assertTrue(self.pool_line().endswith('(pool changed)'), self.pool_line())

    def test_writes_nothing_in_the_library(self):
        "exchange.md 14.3: status writes nothing in the library, also when the pool changed without difference"
        self.take_smith()
        self.edit_pool('@article{Brown_2021,', '@article{Brown_2021,\n note = {x},')
        files = {f: Path(f).read_bytes() for f in [self.path('lib', 'papers.bib'), self.path('lib', CONFIG_FILE_LOCAL)]}
        origin = self.origin_files()
        config = Config.load(self.path('lib', CONFIG_FILE_LOCAL))
        project, place = papers.backup.project_of(config, create=False)
        head = project.head(place)
        self.assertTrue(self.pool_line().endswith('(in sync)'))
        self.assertEqual({f: Path(f).read_bytes() for f in files}, files)
        self.assertEqual(self.origin_files(), origin)
        self.assertEqual(papers.backup.project_of(config, create=False)[0].head(place), head)


# 14.4 exchanges.json
# ===================

class TestExchangesJson(SpecTest):

    def setUp(self):
        super().setUp()
        self.lib('config pool ../pool -y')
        self.take_smith()
        config = Config.load(self.path('lib', CONFIG_FILE_LOCAL))
        project, _ = papers.backup.project_of(config, create=False)
        self.file = os.path.join(project.dir, 'exchanges.json')

    def test_exact_content(self):
        "exchange.md 14.4: {pool id: {library, pool, origin: sorted SHA-256 of the pieces}}, compact form"
        from papers import history
        self.out('status')
        text = Path(self.file).read_text()
        pieces = lambda t: sorted(hashlib.sha256(p.encode('utf-8')).hexdigest() for p in history.pieces(t).values())
        origin = self.origin_text()
        expected = {'../pool': {'library': pieces(self.lib_text()), 'pool': pieces(self.pool_text()),
                                'origin': pieces(origin)}}
        self.assertEqual(json.loads(text), expected)
        self.assertEqual(text, json.dumps(expected, separators=(', ', ': '), ensure_ascii=True))
        self.assertFalse(text.endswith('\n'))
        self.assertEqual(sorted(history.pieces(self.lib_text())), expected['../pool']['library'])

    def test_unreadable_file_means_not_known(self):
        "exchange.md 14.4: a file that cannot be read means not known: every entry is compared"
        self.out('status')
        Path(self.file).write_text('not json')
        self.edit_pool('journal = {Nat.}', 'journal = {Nature}')
        self.assertIn('(pool changed)', self.out('status'))


# 15.3 REPAIR OF BROKEN LINKS
# ===========================

class TestRepair(SpecTest):

    def setUp(self):
        super().setUp()
        self.lib('config pool ../pool -y')
        self.take_smith()

    def test_first_link_takes_the_rest(self):
        "exchange.md 15.3 (4): links left: the first gets all the remaining candidates, the others are removed"
        for name in ('a.pdf', 'b.pdf'):
            Path(self.path('pool', 'files', name)).write_text(name)
        os.remove(self.pool_pdf)
        self.edit_pool('file = {:files/smith.pdf:pdf}', 'file = {:files/a.pdf:pdf;:files/b.pdf:pdf}')
        gone = [self.path('pool', 'files', 'x.pdf'), self.path('pool', 'files', 'y.pdf')]
        self.edit_lib('file = {:../pool/files/smith.pdf:pdf}', 'file = {:../pool/files/x.pdf:pdf;:../pool/files/y.pdf:pdf}')
        self.lib('tag smith2020climate --add t')
        self.assertEqual(self.files('smith2020climate'),
                         [self.path('pool', 'files', 'a.pdf'), self.path('pool', 'files', 'b.pdf')])
        self.assertFalse(any(os.path.exists(f) for f in gone))

    def test_saved_at_the_next_save(self):
        "exchange.md 15.3: links repaired at load are written at the next save, even if nothing else changed"
        new = self.path('pool', 'files', 'renamed.pdf')
        os.rename(self.pool_pdf, new)
        self.edit_pool('files/smith.pdf', 'files/renamed.pdf')
        self.lib('pull --check')
        self.assertIn('files/smith.pdf', self.lib_text())  # commands that do not save
        self.lib('pull')  # nothing to pull: saved all the same
        self.assertIn('../pool/files/renamed.pdf', self.lib_text())
