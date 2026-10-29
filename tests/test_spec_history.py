"""The rules of design/history.md that no other test checks: one class per
section of the specification, each test naming its section. The other
tests of a section are listed in the specification ("Tests:" lines)."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

import papers.backup
import papers.config
from papers import history
from papers.config import Config, CONFIG_FILE_LOCAL
from papers.utils import PapersExit

from tests.common import ConfigTest, entry

HEX64 = r'^[0-9a-f]{64}$'


def sha(data):
    return history.sha256(data if isinstance(data, bytes) else data.encode('utf-8'))


class SpecTest(ConfigTest):
    "a library in lib/ (papers init lib), its history in a store of its own (self.root())"

    def setUp(self):
        super().setUp()
        self.papers('init lib')

    def lib(self, cmd, where='lib'):
        return self.papers(cmd, cwd=self.path(where))

    def out(self, cmd, where='lib'):
        return self.papers(cmd, cwd=self.path(where), sp_cmd='check_output')

    def root(self):
        return self.history_dir.name

    def config(self, where='lib'):
        return Config.load(self.path(where, CONFIG_FILE_LOCAL))

    def project(self, where='lib'):
        return papers.backup.project_of(self.config(where), create=False)

    def head(self, where='lib'):
        "the identifier of the current state"
        project, place = self.project(where)
        return project.head(place)['state']

    def state(self, n=None, where='lib'):
        project, _ = self.project(where)
        return project.state(n or self.head(where))

    def state_file(self, n=None, where='lib'):
        project, _ = self.project(where)
        return Path(project._path(n or self.head(where)))

    def count(self, where='lib'):
        project, _ = self.project(where)
        return len(project.states()) if project else 0

    def add(self, key, *files, where='lib'):
        Path(self.path(f'{key}.bib')).write_text(entry(key, *files))
        self.lib(f'add ../{key}.bib', where)

    def write(self, *p, content='x'):
        path = self.path(*p)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Path(path).write_text(content)
        return path

    def machine(self, **settings):
        "change the machine configuration (None: unset)"
        file = papers.config.MACHINE_CONFIG_FILE
        data = json.loads(Path(file).read_text())
        for name, value in settings.items():
            name = name.replace('_', '-')
            if value is None:
                data.pop(name, None)
            else:
                data[name] = value
        Path(file).write_text(json.dumps(data))


class StoreTest(unittest.TestCase):
    "a store in a temporary folder"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = history.Store(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def state(self, text='', parent=None, t=None, deleted=()):
        return {'parent': parent, 'time': time.time() if t is None else t,
                'bibtex': {'pieces': self.store.put_text(text), 'sha': sha(text)},
                'files': {}, 'ops': [], 'deleted': list(deleted)}

    def objects(self):
        return sorted(f for _, _, files in os.walk(self.store.objects) for f in files)


# 2. The store on disk
# ====================

class TestLocation(SpecTest):
    "history.md 2.1"

    @unittest.skipUnless(sys.platform.startswith('linux'), 'the data folder of Linux')
    def test_default_location(self):
        "history.md 2.1: without history-dir, the store is $XDG_DATA_HOME/papers/history"
        root = os.path.join(os.environ['XDG_DATA_HOME'], 'papers', 'history')
        self.assertEqual(papers.config.HISTORY_DIR, root)
        self.machine(history_dir=None)
        try:
            self.add('one2000')
            id = self.config().library_id(create=False)
            self.assertTrue(os.path.isdir(os.path.join(root, 'projects', id, 'states')))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_relative_history_dir(self):
        "history.md 2.1: a relative history-dir is relative to the folder of the machine configuration"
        root = os.path.join(os.path.dirname(papers.config.MACHINE_CONFIG_FILE), 'spec-history')
        self.machine(history_dir='spec-history')
        try:
            self.add('one2000')
            id = self.config().library_id(create=False)
            self.assertTrue(os.path.isdir(os.path.join(root, 'projects', id)))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_home(self):
        "history.md 2.1: a leading ~ of history-dir is the home directory"
        root = os.path.join(os.path.expanduser('~'), 'spec-history')
        self.machine(history_dir='~/spec-history')
        try:
            self.add('one2000')
            self.assertTrue(os.path.isdir(os.path.join(root, 'projects')))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_nothing_created_without_a_change(self):
        "history.md 2.1: a command that changes nothing creates no folder of the store"
        self.lib('list')
        Path(self.path('one.bib')).write_text(entry('one2000'))
        self.lib('add ../one.bib --dry-run')
        self.assertEqual(os.listdir(self.root()), [])


class TestLayout(SpecTest):
    "history.md 2.2"

    def test_layout(self):
        "history.md 2.2: objects/ab/<sha256>, file-objects/ab/<sha256>.pdf, projects/<id>/heads.json and states/"
        a = self.write('lib', 'files', 'a.pdf', content='pdf a')
        self.add('one2000', a)
        self.lib('rm one2000 --delete-files')
        id = self.config().library_id(create=False)
        self.assertEqual(sorted(os.listdir(self.root())), ['file-objects', 'objects', 'projects'])
        for folder in os.listdir(os.path.join(self.root(), 'objects')):
            for name in os.listdir(os.path.join(self.root(), 'objects', folder)):
                self.assertRegex(name, HEX64)
                self.assertEqual(folder, name[:2])
        digest = sha(b'pdf a')
        self.assertEqual(os.listdir(os.path.join(self.root(), 'file-objects')), [digest[:2]])
        self.assertEqual(os.listdir(os.path.join(self.root(), 'file-objects', digest[:2])), [digest + '.pdf'])
        self.assertEqual(os.listdir(os.path.join(self.root(), 'projects')), [id])
        self.assertEqual(sorted(os.listdir(os.path.join(self.root(), 'projects', id))), ['heads.json', 'states'])
        for name in os.listdir(os.path.join(self.root(), 'projects', id, 'states')):
            self.assertRegex(name, r'^[0-9a-f]{64}\.json$')

    def test_project_id(self):
        "history.md 2.2: <id> matches [0-9A-Za-z_-]+, other values are refused"
        store = history.Store(self.root())
        for good in ('abc', 'A_b-9'):
            self.assertEqual(store.project(good).id, good)
        for bad in ('a.b', 'a b', '', '../x', 'é'):
            self.assertRaises(ValueError, store.project, bad)


class TestObjects(StoreTest):
    "history.md 2.3"

    def test_example(self):
        "history.md 2.3: the example of the specification: 41 segments, a cut after k30"
        text = '% comment\n' + ''.join(f'@article{{k{n},\n title = {{T}},\n}}\n\n' for n in range(40))
        k30 = '@article{k30,\n title = {T},\n}\n\n'
        self.assertEqual(zlib.crc32(k30.encode()), 977124256)
        pieces = history.pieces(text)
        self.assertEqual(len(pieces), 2)
        first, second = pieces.values()
        self.assertTrue(first.startswith('% comment\n@article{k0,'))
        self.assertTrue(first.endswith(k30))
        self.assertTrue(second.startswith('@article{k31,'))
        self.assertEqual(first + second, text)
        self.assertEqual(self.store.put_text(text), list(pieces))

    def test_piece_max(self):
        "history.md 2.3: a piece has at most 256 segments"
        segments = [s for s in (f'@a{{k{n},\n}}\n' for n in range(2000))
                    if zlib.crc32(s.encode()) % history.PIECE_ENTRIES][:300]
        pieces = list(history.pieces(''.join(segments)).values())
        self.assertEqual(len(pieces), 2)
        self.assertEqual(pieces[0], ''.join(segments[:256]))

    def test_segments(self):
        "history.md 2.3: a cut before a line that starts with @, only after \\n; the empty text has no pieces"
        self.assertEqual(self.store.put_text(''), [])
        for text in ('a lone\r@cr does not cut\n', 'an @ inside a line\n', '\r\n@crlf{a,\n}\r\n@x{b,\n}'):
            # one piece here, whatever the cut (fewer than 32 segments, see test_example): the text is kept
            self.assertEqual(''.join(history.pieces(text).values()), text)
        # crc32 of each segment decides the cut: a text whose segments all end a piece gives one piece per segment
        ends = [s for s in (f'@a{{k{n},\n}}\n' for n in range(2000))
                if zlib.crc32(s.encode()) % history.PIECE_ENTRIES == 0][:3]
        self.assertEqual(list(history.pieces(''.join(ends)).values()), ends)
        lone = ends[0].replace('\n', '\r')
        self.assertEqual(len(history.pieces(lone + lone)), 1)  # a lone \r ends no line: one segment

    def test_object_file(self):
        "history.md 2.3: an object is named by the sha256 of its bytes, zlib-compressed, in the folder of its first two characters"
        text = '@article{a,\n title = {été}\n}\n'
        digest, = self.store.put_text(text)
        self.assertEqual(digest, sha(text))
        path = os.path.join(self.store.objects, digest[:2], digest)
        self.assertEqual(zlib.decompress(Path(path).read_bytes()), text.encode('utf-8'))

    def test_any_zlib_stream(self):
        "history.md 2.3: a reader accepts any compression level"
        text = '@article{a,\n}\n'
        digest = sha(text)
        os.makedirs(os.path.join(self.store.objects, digest[:2]))
        Path(self.store.objects, digest[:2], digest).write_bytes(zlib.compress(text.encode(), 0))
        self.assertEqual(self.store.text([digest]), text)

    def test_existing_object_refreshed(self):
        "history.md 2.3: an object stored again is not rewritten, its modification time is set to now"
        digest, = self.store.put_text('@a{b,\n}\n')
        path = os.path.join(self.store.objects, digest[:2], digest)
        os.utime(path, (1000, 1000))
        self.store.put_text('@a{b,\n}\n')
        self.assertGreater(os.path.getmtime(path), time.time() - 60)

    def test_tmp_files_are_not_objects(self):
        "history.md 2.3: files ending with .tmp are not objects (not counted, not read)"
        digest, = self.store.put_text('@a{b,\n}\n')
        size = self.store.size()
        Path(self.store.objects, digest[:2], digest + '.123.tmp').write_bytes(b'x' * 5000)
        self.assertEqual(self.store.size(), size)


class TestObjectsOfALibrary(SpecTest):
    "history.md 2.3, in a library"

    def test_bytes_of_the_file(self):
        "history.md 2.3 and 6.3: the stored text is the bytes of the file (BOM and \\r\\n included), restored as such"
        self.add('one2000')
        bib = Path(self.path('lib', 'papers.bib'))
        outside = ('﻿' + bib.read_text() + entry('two2000')).replace('\n', '\r\n').encode('utf-8')
        bib.write_bytes(outside)
        self.lib('tag one2000 --add x')
        project, _ = self.project()
        state = self.state(self.state()['parent'])
        self.assertEqual(state['kind'], 'outside')
        self.assertEqual(project.store.text(state['bibtex']['pieces']).encode('utf-8'), outside)
        self.assertEqual(state['bibtex']['sha'], sha(outside))
        self.lib('undo')
        self.assertEqual(bib.read_bytes(), outside)

    def test_missing_piece(self):
        "history.md 2.3: a missing piece: the history of the library is damaged"
        self.add('one2000')
        self.add('two2000')
        shutil.rmtree(os.path.join(self.root(), 'objects'))
        # the text is free: the command stops, naming the piece
        with self.assertRaisesRegex(PapersExit, r'damaged.*piece [0-9a-f]{64} is missing'):
            self.lib('undo')


class TestFileObjects(SpecTest):
    "history.md 2.4"

    def test_extension_as_written(self):
        "history.md 2.4: file-objects/<ab>/<sha256><extension>, the extension as written"
        a = self.write('lib', 'files', 'a.PDF', content='pdf A')
        self.add('one2000', a)
        self.lib('rm one2000 --delete-files')
        digest = sha(b'pdf A')
        self.assertTrue(os.path.isfile(os.path.join(self.root(), 'file-objects', digest[:2], digest + '.PDF')))

    def test_lookup_by_checksum(self):
        "history.md 2.4: any file of the folder whose name, up to its first dot, is the sha256"
        store = history.Store(self.root())
        digest = sha(b'z')
        folder = os.path.join(store.file_objects, digest[:2])
        os.makedirs(folder)
        Path(folder, digest + '.tar.gz').write_bytes(b'z')
        self.assertEqual(store.file_object(digest), os.path.join(folder, digest + '.tar.gz'))
        os.remove(os.path.join(folder, digest + '.tar.gz'))
        Path(folder, digest).write_bytes(b'z')  # no extension
        self.assertEqual(store.file_object(digest), os.path.join(folder, digest))

    def test_stored_again(self):
        "history.md 2.4: a file whose checksum is stored already is deleted, the stored one refreshed"
        store = history.Store(self.root())
        a, b = self.write('a.pdf', content='same'), self.write('b.txt', content='same')
        kept = store.put_file(a, sha(b'same'))
        os.utime(kept, (1000, 1000))
        self.assertEqual(store.put_file(b, sha(b'same')), kept)
        self.assertFalse(os.path.exists(b))
        self.assertGreater(os.path.getmtime(kept), time.time() - 60)
        self.assertTrue(kept.endswith('.pdf'))

    def test_shared_by_the_projects(self):
        "history.md 2.4: a file deleted by two libraries is stored once, and undo finds it in the whole store"
        self.papers('init other')
        for where in ('lib', 'other'):
            a = self.write(where, 'files', 'a.pdf', content='the same pdf')
            self.add('one2000', a, where=where)
            self.lib('rm one2000 --delete-files', where)
        folder = os.path.join(self.root(), 'file-objects', sha(b'the same pdf')[:2])
        self.assertEqual(len(os.listdir(folder)), 1)
        self.lib('undo', 'other')
        self.assertEqual(Path(self.path('other', 'files', 'a.pdf')).read_text(), 'the same pdf')


class TestStates(SpecTest):
    "history.md 2.5"

    def test_written_once(self):
        "history.md 2.5: a state is created exclusively; the same state (same identifier) is not written again"
        store = history.Store(self.root())
        p = store.project('p')
        state = {'parent': None, 'time': 1.0, 'bibtex': {'pieces': [], 'sha': sha('')}, 'files': {},
                 'ops': [], 'deleted': [], 'message': 'first'}
        n = p.add(dict(state))
        self.assertEqual(p.add(dict(state, message='second')), n)
        self.assertEqual(json.loads(Path(p._path(n)).read_text())['message'], 'first')

    def test_other_files_ignored(self):
        "history.md 2.5: a reader takes the files named <64 hex>.json holding a JSON object, and nothing else"
        self.add('one2000')
        project, _ = self.project()
        folder = project.states_dir
        states = sorted(project.states())
        Path(folder, 'notes.json').write_text('{}')
        Path(folder, 'a' * 64 + '.json').write_text('[1, 2]')
        Path(folder, 'b' * 64 + '.json.tmp').write_text('{}')
        Path(folder, 'C' * 64 + '.json').write_text('{}')
        self.assertEqual(sorted(self.project()[0].states()), states)

    def test_naming(self):
        "history.md 2.5: a step named by a start of 4 characters or more, without case, spaces dropped"
        self.add('one2000')
        self.add('two2000')
        first = self.state()['parent']
        self.lib(f'restore {first[:4].upper()}')
        self.assertEqual(self.head(), first)
        project, place = self.project()
        two = project.head(place)['redo'][-1]
        self.lib(f'restore " {two[:6]} "')
        self.assertEqual(self.head(), two)
        for value in (two[:3], 'zzzzzz', two[:4] + 'x'):
            with self.assertRaisesRegex(PapersExit, rf'^no step {value} in the history of the library '
                                                    r'\(see `papers history`\)$'):
                self.lib(f'restore {value}')

    def test_several(self):
        "history.md 2.5: a start that several states have is refused"
        self.add('one2000')
        project, _ = self.project()
        for name in ('abcd1' + '0' * 59, 'abcd2' + '0' * 59):
            Path(project.states_dir, name + '.json').write_text(json.dumps(
                {'parent': None, 'time': 1, 'bibtex': {'pieces': [], 'sha': sha('')}, 'files': {}}))
        with self.assertRaisesRegex(PapersExit, r'^abcd names several steps: abcd1000, abcd2000$'):
            self.lib('restore ABCD')

    def test_json(self):
        "history.md 2.5: a state is a JSON object in UTF-8 with \\n line endings"
        self.add('one2000')
        data = self.state_file().read_bytes()
        self.assertNotIn(b'\r', data)
        self.assertIsInstance(json.loads(data.decode('utf-8')), dict)
        self.assertEqual(self.head(), history.state_id(self.state()))

    def test_numbers_json(self):
        "history.md 2.5: the upgrade keeps numbers.json at the root of the store: {project id: {number: identifier}}"
        store = history.Store(self.root())
        folder = os.path.join(store.projects, 'p', 'states')
        os.makedirs(folder)
        Path(folder, '000001.json').write_text(json.dumps(dict(parent=None, time=1, bibtex={'pieces': [], 'sha': 'a'})))
        Path(folder, '000002.json').write_text(json.dumps(dict(parent=1, time=2, bibtex={'pieces': [], 'sha': 'b'})))
        states = store.project('p').states()
        one = next(n for n, s in states.items() if s['parent'] is None)
        two = next(n for n, s in states.items() if s['parent'] == one)
        self.assertEqual(json.loads(Path(self.root(), 'numbers.json').read_text()), {'p': {'1': one, '2': two}})
        self.assertEqual(sorted(os.listdir(folder)), sorted([one + '.json', two + '.json']))


class TestSeparateStores(SpecTest):
    "history.md 2.6"

    def test_machine_setting(self):
        "history.md 2.6: history-separate of the machine configuration applies; the library's value wins"
        self.machine(history_separate=True)
        self.add('one2000')
        id = self.config().library_id(create=False)
        self.assertTrue(os.path.isdir(os.path.join(self.root(), 'separate', id, 'projects', id)))
        self.papers('init other')
        self.lib('config history-separate false', 'other')
        self.add('two2000', where='other')
        other = self.config('other').library_id(create=False)
        self.assertTrue(os.path.isdir(os.path.join(self.root(), 'projects', other)))

    def test_bibtex_without_library(self):
        "history.md 2.6 and 5.1: a bibtex without library: its id is the sha256 of its place, cut to 32; history-separate of the machine applies"
        Path(self.path('refs.bib')).write_text(entry('one2000'))
        self.papers('tag one2000 --add x --bibtex refs.bib')
        id = sha(os.path.realpath(self.path('refs.bib')))[:32]
        self.assertEqual(os.listdir(os.path.join(self.root(), 'projects')), [id])
        self.machine(history_separate=True)
        self.papers('tag one2000 --add y --bibtex refs.bib')
        self.assertTrue(os.path.isdir(os.path.join(self.root(), 'separate', id, 'projects', id)))
        self.assertFalse(os.path.exists(self.path('.papers')))

    def test_change_of_the_setting(self):
        "history.md 2.6: changing the setting does not move the history"
        self.add('one2000')
        self.lib('config history-separate true')
        with self.assertRaisesRegex(PapersExit, 'nothing to undo'):
            self.lib('undo')


class TestHeads(SpecTest):
    "history.md 2.7"

    def test_format(self):
        "history.md 2.7: {real path of the bibtex: {state, redo, time}}"
        self.add('one2000')
        self.add('two2000')
        self.lib('undo')
        id = self.config().library_id(create=False)
        heads = json.loads(Path(self.root(), 'projects', id, 'heads.json').read_text())
        place = os.path.realpath(self.path('lib', 'papers.bib'))
        self.assertEqual(list(heads), [place])
        self.assertEqual(sorted(heads[place]), ['redo', 'state', 'time'])
        project, _ = self.project()
        two = project.state(heads[place]['redo'][0])
        self.assertEqual(two['parent'], heads[place]['state'])
        self.assertIsInstance(heads[place]['time'], float)
        self.assertLess(abs(heads[place]['time'] - time.time()), 60)

    def test_missing_states(self):
        "history.md 2.7: a head whose state no longer exists is absent; missing redo states are skipped"
        store = history.Store(self.root())
        p = store.project('p')
        one = p.add({'parent': None, 'time': 1, 'bibtex': {'pieces': [], 'sha': 'a'}, 'files': {}})
        p.set_head('/x.bib', one, redo=['f' * 64, one])
        self.assertEqual(p.head('/x.bib')['redo'], [one])
        p.set_head('/y.bib', 'e' * 64)
        self.assertIsNone(p.head('/y.bib'))

    def test_unreadable(self):
        "history.md 2.7: a missing or unreadable heads.json means no heads"
        store = history.Store(self.root())
        p = store.project('p')
        self.assertEqual(p.heads(), {})
        os.makedirs(p.dir)
        Path(p.dir, 'heads.json').write_text('not json')
        self.assertEqual(p.heads(), {})


class TestWritingOrder(SpecTest):
    "history.md 2.8"

    def test_order(self):
        "history.md 2.8: the objects and file objects, then the state, then the head"
        a = self.write('lib', 'files', 'a.pdf', content='pdf a')
        self.add('one2000', a)
        calls = []

        def spy(name, f):
            def wrapper(*args, **kw):
                calls.append(name)
                return f(*args, **kw)
            return wrapper
        with patch.object(history.Store, 'put_text', spy('object', history.Store.put_text)), \
                patch.object(history.Store, 'put_file', spy('file', history.Store.put_file)), \
                patch.object(history.Project, 'add', spy('state', history.Project.add)), \
                patch.object(history.Project, 'update', spy('state', history.Project.update)), \
                patch.object(history.Project, 'set_head', spy('head', history.Project.set_head)):
            self.lib('rm one2000 --delete-files')
        # rm: the save (objects, state, head), then the file deleted, and the state rewritten with it
        self.assertIn('file', calls)
        self.assertEqual(calls[-2:], ['file', 'state'])
        first_state = calls.index('state')
        self.assertIn('object', calls[:first_state])
        self.assertNotIn('object', calls[first_state:])
        self.assertEqual(calls[first_state + 1], 'head')


# 3. A state
# ==========

class TestKeys(SpecTest):
    "history.md 3.1"

    def test_keys(self):
        "history.md 3.1: the keys of a state, and the sha of the bibtex"
        self.add('one2000')
        state = json.loads(self.state_file().read_text())
        self.assertEqual(sorted(state), ['bibtex', 'deleted', 'files', 'kind', 'message', 'ops', 'parent', 'time'])
        self.assertRegex(state['parent'], HEX64)
        self.assertIsInstance(state['time'], float)
        self.assertEqual(sorted(state['bibtex']), ['pieces', 'sha'])
        self.assertEqual(state['bibtex']['sha'], sha(Path(self.path('lib', 'papers.bib')).read_bytes()))
        start = self.state(state['parent'])
        self.assertIsNone(start['parent'])
        self.assertEqual(start['bibtex'], {'pieces': [], 'sha': sha(b'')})  # no bibtex yet: the empty text

    def test_without_kind(self):
        "history.md 3.1: a reader accepts a state without kind"
        self.add('one2000')
        self.add('two2000')
        project, _ = self.project()
        for n in project.states():
            path = Path(project._path(n))
            path.write_text(json.dumps({k: v for k, v in json.loads(path.read_text()).items() if k != 'kind'}))
        self.lib('undo')
        self.lib('redo')
        self.assertIn('papers add ../two2000.bib', self.out('history'))

    def test_unknown_keys_kept(self):
        "history.md 3.1: an implementation that rewrites a state keeps the keys it does not know (here --drop-files)"
        a = self.write('lib', 'files', 'a.pdf', content='pdf a')
        self.add('one2000', a)
        self.lib('rm one2000 --delete-files')
        project, _ = self.project()
        n = self.head()
        project.update(n, dict(project.state(n), future={'a': 1}))
        self.lib(f'history --drop-files {n} --yes')
        state = json.loads(self.state_file(n).read_text())
        self.assertEqual(state['deleted'], [])
        self.assertEqual(state['future'], {'a': 1})


class TestKinds(SpecTest):
    "history.md 3.2"

    def test_kinds(self):
        "history.md 3.2: start, command and outside, with their messages"
        self.add('one2000')
        bib = Path(self.path('lib', 'papers.bib'))
        bib.write_text(bib.read_text() + entry('two2000'))
        self.lib('tag one2000 --add x')
        project, _ = self.project()
        line = [project.state(n) for n in project.line(self.head())]
        self.assertEqual([(s['kind'], s['message']) for s in line], [
            ('command', 'papers tag one2000 --add x'),
            ('outside', 'changed outside papers'),
            ('command', 'papers add ../one2000.bib'),
            ('start', 'the library before its first recorded command')])


class TestKeptFiles(SpecTest):
    "history.md 3.3"

    def test_names(self):
        "history.md 3.3: distinct.json, files.json, origin.bib and origin/*.bib, named with /; nothing else"
        self.add('one2000')
        for name in ('distinct.json', 'files.json', 'origin.bib', 'origin/a.bib', 'origin/b.txt', 'other.json'):
            self.write('lib', '.papers', *name.split('/'), content='{}\n')
        self.lib('tag one2000 --add x')
        self.assertTrue(os.path.exists(self.path('lib', '.papers', 'config.json')))
        self.assertEqual(sorted(self.state()['files']), ['.papers/distinct.json', '.papers/files.json',
                                                        '.papers/origin.bib', '.papers/origin/a.bib'])

    def test_library_directory(self):
        "history.md 3.3: the names are relative to the library directory, also when the bibtex is in a subfolder"
        shutil.rmtree(self.path('lib'))
        os.makedirs(self.path('lib', 'sub'))
        self.papers('init lib --bibtex lib/sub/refs.bib')
        a = self.write('lib', 'files', 'a.pdf', content='pdf a')
        Path(self.path('one.bib')).write_text(entry('one2000', a))
        self.lib('add ../one.bib')
        self.lib('file checksum')
        files_json = self.path('lib', '.papers', 'files.json')
        self.assertTrue(os.path.isfile(files_json))
        self.assertIn('.papers/files.json', self.state()['files'])
        self.lib('undo')  # before the checksums: files.json removed
        self.assertFalse(os.path.exists(files_json))
        self.lib('redo')
        self.assertTrue(os.path.isfile(files_json))
        self.assertFalse(os.path.exists(self.path('lib', 'sub', '.papers')))


class TestDeleted(SpecTest):
    "history.md 3.4"

    def test_sorted_without_repeats(self):
        "history.md 3.4: the sorted checksums of the trashed operations, each once"
        for name, content in (('a.pdf', 'one'), ('b.pdf', 'two'), ('c.pdf', 'one'), ('d.pdf', 'three')):
            self.write('lib', 'files', name, content=content)
        self.add('one2000')
        self.lib('file clean --yes')
        state = self.state()
        self.assertEqual([op['op'] for op in state['ops']], ['trashed'] * 4)
        self.assertEqual(state['deleted'], sorted({sha(b'one'), sha(b'two'), sha(b'three')}))


# 4. File operations
# ==================

class TestFileOperations(SpecTest):
    "history.md 4"

    def test_trashed(self):
        "history.md 4: a trashed operation: src relative to the bibtex folder, dst null, the checksum of the file"
        a = self.write('lib', 'files', 'a.pdf', content='pdf a')
        self.add('one2000', a)
        self.lib('rm one2000 --delete-files')
        self.assertEqual(self.state()['ops'], [{'op': 'trashed', 'src': 'files/a.pdf', 'dst': None,
                                                'checksum': sha(b'pdf a')}])

    def test_moved(self):
        "history.md 4: moved: the checksum at dst; a path outside the bibtex folder is absolute, never with .."
        a = self.write('src', 'a.pdf', content='pdf a')
        self.add('one2000', a)
        self.lib('file rename --move')
        op, = self.state()['ops']
        self.assertEqual(sorted(op), ['checksum', 'dst', 'op', 'src'])
        self.assertEqual(op['op'], 'moved')
        self.assertEqual(op['src'], a)
        self.assertFalse(os.path.isabs(op['dst']))
        self.assertTrue(op['dst'].startswith('files/'))
        self.assertEqual(op['checksum'], sha(b'pdf a'))

    def test_paths_absolute(self):
        "history.md 4: with paths absolute, all paths are absolute"
        self.lib('config paths absolute')
        a = self.write('lib', 'files', 'a.pdf', content='pdf a')
        self.add('one2000', a)
        self.lib('rm one2000 --delete-files')
        op, = self.state()['ops']
        self.assertEqual(op['src'], a)

    def test_copied(self):
        "history.md 4: copied: src, dst, the checksum at dst"
        a = self.write('src', 'a.pdf', content='pdf a')
        self.add('one2000', a)
        self.lib('file rename --copy')
        op, = self.state()['ops']
        self.assertEqual((op['op'], op['src'], op['checksum']), ('copied', a, sha(b'pdf a')))
        self.assertTrue(os.path.isfile(self.path('lib', op['dst'])))

    def test_relative_to_the_copy(self):
        "history.md 4: a relative path is read against the folder of the bibtex: undo in a copy acts on its own files"
        a = self.write('lib', 'files', 'a.pdf', content='pdf a')
        self.add('one2000', a)
        self.lib('rm one2000 --delete-files')
        shutil.copytree(self.path('lib'), self.path('copy'))
        self.lib('undo', 'copy')
        self.assertTrue(os.path.isfile(self.path('copy', 'files', 'a.pdf')))
        self.assertFalse(os.path.exists(a))


# 5. Recording
# ============

class TestRecording(SpecTest):
    "history.md 5.1 to 5.5"

    def test_id_created_at_the_first_state(self):
        "history.md 5.1: the id is written into the configuration when a state is first recorded"
        self.assertNotIn('id', self.json('lib'))
        self.add('one2000')
        id = self.json('lib')['id']
        self.assertEqual(os.listdir(os.path.join(self.root(), 'projects')), [id])

    def test_outside_state_files_from_disk(self):
        "history.md 5.2: the outside state has the .papers/ files as they are on disk at the start of the command"
        self.add('one2000')
        distinct = self.write('lib', '.papers', 'distinct.json', content='{"distinct": []}\n')
        bib = Path(self.path('lib', 'papers.bib'))
        bib.write_text(bib.read_text() + entry('two2000'))
        self.lib('tag one2000 --add x')
        outside = self.state(self.state()['parent'])
        self.assertEqual(outside['kind'], 'outside')
        self.assertIn('.papers/distinct.json', outside['files'])
        self.assertTrue(os.path.exists(distinct))

    def test_library_before_the_command(self):
        "history.md 5.3: the first state is the library before the command, also when the command wrote .papers/ before its save"
        from papers import journal
        from papers.bib import Biblio
        from papers.library import savebib
        Path(self.path('lib', 'papers.bib')).write_text(entry('one2000'))
        config = self.config()
        journal.start(config.bibtex)
        papers.backup.start(config, 'tag')
        self.write('lib', '.papers', 'distinct.json', content='{"distinct": []}\n')  # before the save
        biblio = Biblio.load(config.bibtex, '')
        biblio.entries[0]['note'] = 'changed'
        savebib(biblio, config)
        state = self.state()
        start = self.state(state['parent'])
        self.assertEqual(start['kind'], 'start')
        self.assertEqual(start['files'], {})
        self.assertIn('.papers/distinct.json', state['files'])
        self.assertEqual(self.project()[0].store.text(start['bibtex']['pieces']), entry('one2000'))

    def test_operations_after_the_head_moved(self):
        "history.md 5.5: operations done after the save are not recorded when the head moved on"
        self.add('one2000')
        n = self.head()
        self.add('two2000')
        config = self.config()
        with self.assertLogs('papers', level='WARNING') as logs:
            papers.backup.add_operations(config, n, [{'op': 'removed', 'src': self.path('x.pdf'), 'dst': None,
                                                      'checksum': None}])
        self.assertIn('1 file operation(s) not recorded for undo: the library changed since', '\n'.join(logs.output))
        self.assertEqual(self.state(n)['ops'], [])

    def test_no_state_for_an_identical_save(self):
        "history.md 5.4 rule 6: no state when nothing changed and there is no operation"
        self.add('one2000')
        self.lib('tag one2000 --add x')
        n, count = self.head(), self.count()
        self.lib('tag one2000 --add x')
        self.lib('check --duplicates')
        self.assertEqual((self.head(), self.count()), (n, count))

    def test_command_after_undo_starts_a_branch(self):
        "history.md 5.4 rule 7: a command after an undo empties the redo list; the undone state stays"
        self.add('one2000')
        self.add('two2000')
        undone = self.head()
        self.lib('undo')
        self.lib('tag one2000 --add x')
        project, place = self.project()
        self.assertEqual(project.head(place)['redo'], [])
        self.assertIn(undone, project.states())
        self.assertNotIn(undone, project.line(self.head()))


# 6. Undo, redo, restore
# ======================

class TestCommands(SpecTest):
    "history.md 6.2"

    def test_no_state_added(self):
        "history.md 6.2: undo, redo and restore add no state, they move the head"
        self.add('one2000')
        self.add('two2000')
        count = self.count()
        self.lib('undo')
        self.lib('redo')
        first = self.project()[0].line(self.head())[-1]
        self.lib(f'restore {first}')
        self.assertEqual(self.count(), count)

    def test_redo_list_of_undo(self):
        "history.md 6.2: undo -n 2: the redo list is the steps undone, the nearest to the target first"
        self.add('one2000')
        one = self.head()
        self.add('two2000')
        two = self.head()
        self.lib('undo -n 2')
        project, place = self.project()
        self.assertEqual(project.head(place)['redo'], [one, two])

    def test_redo_after_an_outside_change(self):
        "history.md 6.2: redo after a change made outside papers stops, and the redo list is empty"
        self.add('one2000')
        self.lib('undo')
        Path(self.path('lib', 'papers.bib')).write_text(entry('other2001'))
        with self.assertRaisesRegex(PapersExit, r'^nothing to redo: the library changed outside papers since the '
                                                r'undo \(recorded: `papers undo` goes back before that change\)$'):
            self.lib('redo')
        project, place = self.project()
        self.assertEqual(project.head(place)['redo'], [])
        self.assertEqual(self.state()['kind'], 'outside')

    def test_restore_redo_list(self):
        "history.md 6.2: restore to an ancestor: redo goes back to where the library was; to another branch: no redo"
        self.add('one2000')
        one = self.head()
        self.add('two2000')
        two = self.head()
        first = self.state(one)['parent']
        self.lib(f'restore {first}')
        project, place = self.project()
        self.assertEqual(project.head(place)['redo'], [one, two])
        self.lib(f'restore {one}')
        self.lib('tag one2000 --add x')  # a branch
        self.lib(f'restore {two}')
        project, place = self.project()
        self.assertEqual(project.head(place)['redo'], [])

    def test_steps_out_of_range(self):
        "history.md 6.2: -n of undo and redo is 1 or more, else a usage error (exit 2); more than there are: an error"
        self.add('one2000')
        self.add('two2000')
        self.lib('undo -n 2')
        project, place = self.project()
        head = project.head(place)
        for cmd in ('undo -n 0', 'undo -n -1', 'redo -n 0', 'redo -n -9'):
            with self.assertRaises(SystemExit) as cm:
                self.lib(cmd)
            self.assertEqual(cm.exception.code, 2)
        with self.assertRaisesRegex(PapersExit, r'^only 2 step\(s\) to redo$'):
            self.lib('redo -n 3')
        self.assertEqual(project.head(place), head)

    def test_nothing_to_restore(self):
        "history.md 6.2: restore to the current state"
        self.add('one2000')
        with self.assertRaisesRegex(PapersExit, rf'^nothing to restore: papers.bib is step {self.head()[:8]}$'):
            self.lib('restore')


class TestGoingToAState(SpecTest):
    "history.md 6.3"

    def test_kept_files_written_and_removed(self):
        "history.md 6.3: the kept files of the target are written, those of the current state it has not removed, others left alone"
        self.add('one2000')
        self.write('lib', '.papers', 'distinct.json', content='{"distinct": []}\n')
        self.lib('tag one2000 --add x')
        other = self.write('lib', '.papers', 'other.json', content='{}')
        self.lib('undo -n 2')
        self.assertFalse(os.path.exists(self.path('lib', '.papers', 'distinct.json')))
        self.assertTrue(os.path.exists(other))
        self.lib('redo -n 2')
        self.assertEqual(Path(self.path('lib', '.papers', 'distinct.json')).read_text(), '{"distinct": []}\n')


# 7. Undo and redo with a pool
# ============================

class TestPoolLink(SpecTest):
    "history.md 7.1"

    def setUp(self):
        super().setUp()
        self.papers('init pool')
        self.lib('config pool ../pool -y')

    def test_link(self):
        "history.md 7.1 and 5.4: pools {pool id: {state, base, config}}; the pool's state has no ops and has from"
        self.add('one2000')
        state = self.state()
        pool_id = self.config('pool').library_id(create=False)
        self.assertEqual(list(state['pools']), [pool_id])
        link = state['pools'][pool_id]
        self.assertEqual(sorted(link), ['base', 'config', 'state'])
        self.assertEqual(link['config'], self.path('pool', '.papers', 'config.json'))
        pool_state = self.state(link['state'], where='pool')
        self.assertEqual(link['state'], self.head('pool'))
        self.assertEqual(link['base'], pool_state['parent'])
        self.assertEqual(pool_state['ops'], [])
        self.assertEqual(pool_state['from'], os.path.realpath(self.path('lib')))
        self.assertEqual(pool_state['message'], state['message'])
        self.assertNotIn('from', state)
        self.assertNotIn('pools', pool_state)

    def test_pool_not_found(self):
        "history.md 7.2: a pool whose configuration is gone: the library only"
        self.add('one2000')
        shutil.move(self.path('pool'), self.path('gone'))
        out = self.out('undo')
        self.assertRegex(out, r'the pool of step [0-9a-f]{8} is not found \(at .*\): the library only')
        self.assertNotIn('one2000', Path(self.path('lib', 'papers.bib')).read_text())


# 8. Revert
# =========

class TestRevert(SpecTest):
    "history.md 8"

    def test_errors(self):
        "history.md 8: the errors of --revert"
        self.add('one2000')
        first = self.state()['parent']
        with self.assertRaisesRegex(PapersExit, rf'^step {first[:8]} is the first step of the history: nothing '
                                                r'before it to go back to$'):
            self.lib(f'history --revert {first}')
        self.add('two2000')
        two = self.head()
        self.lib('undo')
        self.lib('tag one2000 --add x')
        with self.assertRaisesRegex(PapersExit, rf'^step {two[:8]} is not in the current history of the library: '
                                                rf'`papers restore {two[:8]}` goes there$'):
            self.lib(f'history --revert {two}')

    def test_state(self):
        "history.md 8.4: the new state has reverts [N] and the message of the command"
        self.add('one2000')
        self.lib('tag one2000 --add x')
        n = self.head()
        self.lib('tag one2000 --add y')
        self.lib(f'history --revert {n[:8]}')
        state = self.state()
        self.assertEqual(state['reverts'], [n])
        self.assertEqual(state['message'], f'papers history --revert {n[:8]}')
        self.assertEqual(state['kind'], 'command')

    def test_origin_records_unchanged(self):
        "history.md 8.3: the content of the origin records is not changed by a revert"
        self.papers('init pool')
        self.lib('config pool ../pool -y')
        self.add('one2000')
        self.lib('tag one2000 --add x')
        n = self.head()
        origin = {f: Path(self.path('lib', '.papers', 'origin', f)).read_text()
                  for f in os.listdir(self.path('lib', '.papers', 'origin'))}
        self.lib(f'history --revert {n}')
        self.assertEqual({f: Path(self.path('lib', '.papers', 'origin', f)).read_text()
                          for f in os.listdir(self.path('lib', '.papers', 'origin'))}, origin)


# 9. Retention
# ============

class TestSize(StoreTest):
    "history.md 9.1"

    def test_what_counts(self):
        "history.md 9.1: objects and file objects count, .tmp files, states and heads.json do not"
        p = self.store.project('p')
        n = p.add(self.state('@a{b,\n}\n'))
        p.set_head('/x.bib', n)
        path = os.path.join(self.tmp.name, 'a.pdf')
        Path(path).write_bytes(b'y' * 3000)
        self.store.put_file(path, sha(b'y' * 3000))
        expected = sum(os.path.getsize(os.path.join(root, f))
                       for folder in (self.store.objects, self.store.file_objects)
                       for root, _, files in os.walk(folder) for f in files)
        Path(self.store.file_objects, 'ab').mkdir(exist_ok=True)
        Path(self.store.file_objects, 'ab', 'x.1.tmp').write_bytes(b'z' * 9999)
        self.assertEqual(self.store.size(), expected)


class TestSizeOfALibrary(SpecTest):
    "history.md 9.1, the setting"

    def test_machine_value_for_the_shared_store(self):
        "history.md 9.1: the shared store takes the machine's history-size, not the library's"
        self.lib('config --global history-size 9')
        self.lib('config history-size 7')
        self.add('one2000')
        self.assertIn('up to 9 MB', self.out('history'))

    def test_separate_store_falls_back_to_the_machine(self):
        "history.md 9.1: a separate store without a library value takes the machine's"
        self.lib('config --global history-size 9')
        self.lib('config history-separate true')
        self.add('one2000')
        self.assertIn('up to 9 MB', self.out('history'))


class TestPruning(StoreTest):
    "history.md 9.2"

    def test_no_limit_frees_unreferenced_objects(self):
        "history.md 9.2: with no limit, no state is dropped, and the removable objects are removed"
        p = self.store.project('p')
        old = p.add(self.state('@a{old,\n}\n', t=1))
        p.set_head('/x.bib', p.add(self.state('@a{new,\n}\n', parent=old)))
        self.store.put_text('@a{orphan,\n}\n')
        self.assertEqual(self.store.prune(0, now=time.time() + history.GRACE + 1), [])
        self.assertIn(old, self.store.project('p').states())
        self.assertEqual(len(self.objects()), 2)

    def test_order_by_time_then_identifier(self):
        "history.md 9.2: the states are dropped by time, then identifier, oldest first, all projects together"
        later = time.time() + history.GRACE + 1
        dropped = []
        for id in ('p', 'q'):
            p = self.store.project(id)
            a = p.add(self.state(f'@a{{{id}a,\n}}\n' + 'x' * 2000, t=5))
            b = p.add(self.state(f'@a{{{id}b,\n}}\n' + 'x' * 2000, parent=a, t=5 if id == 'q' else 9))
            p.set_head('/x.bib', p.add(self.state(f'@a{{{id}c,\n}}\n', parent=b, t=10)))
            dropped += [(5, id, a), (5 if id == 'q' else 9, id, b)]
        order = [(id, n) for _, id, n in sorted(dropped, key=lambda s: (s[0], s[2]))]
        self.assertEqual([(id, n) for id, n, _ in self.store.prune(1, dry=True, now=later)], order)
        self.assertEqual([(id, n) for id, n, _ in self.store.prune(self.store.size() - 1, dry=True, now=later)],
                         order[:1])

    def test_heads_of_all_projects_protected(self):
        "history.md 9.2: the current state of each place of each project is never dropped"
        for id in ('p', 'q'):
            p = self.store.project(id)
            p.set_head('/x.bib', p.add(self.state('@a{%s,\n}\n' % id + 'x' * 5000, t=1)))
        self.assertEqual(self.store.prune(1, now=time.time() + history.GRACE + 1), [])


class TestRemove(SpecTest):
    "history.md 9.3"

    def age(self):
        "the objects of the store, more than an hour old"
        for root, _, files in os.walk(self.root()):
            for f in files:
                if '/objects/' in os.path.join(root, f) or '/file-objects/' in os.path.join(root, f):
                    os.utime(os.path.join(root, f), (1000, 1000))

    def objects(self):
        return [f for root, _, files in os.walk(os.path.join(self.root(), 'objects')) for f in files]

    def test_last_place_prunes(self):
        "history.md 9.3: removing the history of the last place deletes the project and prunes the store"
        self.add('one2000')
        self.age()
        out = self.out('history --remove --yes')
        self.assertIn('removed the history of the library (2 steps)', out)
        self.assertEqual(os.listdir(os.path.join(self.root(), 'projects')), [])
        self.assertEqual(self.objects(), [])

    def test_by_id(self):
        "history.md 9.3: --remove ID removes that project and prunes its store"
        self.papers('init other')
        self.add('one2000', where='other')
        id = self.config('other').library_id(create=False)
        self.age()
        self.lib(f'history --remove {id} --yes')
        self.assertEqual(os.listdir(os.path.join(self.root(), 'projects')), [])
        self.assertEqual(self.objects(), [])
        with self.assertRaisesRegex(PapersExit, rf'^no history of a library {id} \(see `papers history --all`\)$'):
            self.lib(f'history --remove {id} --yes')

    def test_no_project(self):
        "history.md 9.3: no project"
        self.assertIn('the library has no history', self.out('history --remove --yes'))

    def test_dry_run(self):
        "history.md 9.3: with --dry-run nothing is removed"
        self.add('one2000')
        out = self.out('history --remove --yes --dry-run')
        self.assertIn('DRYRUN: the history of the library (2 steps) not removed', out)
        self.assertEqual(self.count(), 2)

    def test_place_without_history(self):
        "history.md 9.3: a copy that was never used has no history: nothing is removed"
        self.add('one2000')
        shutil.copytree(self.path('lib'), self.path('copy'))
        out = self.out('history --remove --yes', where='copy')
        self.assertIn('nothing to remove', out)
        project, place = self.project()
        self.assertEqual(list(project.heads()), [place])
        self.assertEqual(self.count(), 2)


class TestDropFiles(SpecTest):
    "history.md 9.4"

    def test_file_kept_by_another_project(self):
        "history.md 9.4: a file object that another project lists in deleted stays"
        self.papers('init other')
        for where in ('lib', 'other'):
            a = self.write(where, 'files', 'a.pdf', content='the same pdf')
            self.add('one2000', a, where=where)
            self.lib('rm one2000 --delete-files', where)
        self.lib(f'history --drop-files {self.head()} --yes')
        self.assertEqual(self.state()['deleted'], [])
        self.assertEqual(len(self.state(where='other')['deleted']), 1)
        folder = os.path.join(self.root(), 'file-objects', sha(b'the same pdf')[:2])
        self.assertEqual(len(os.listdir(folder)), 1)
        self.lib('undo')  # found by checksum in the store
        self.assertTrue(os.path.isfile(self.path('lib', 'files', 'a.pdf')))

    def test_dry_run(self):
        "history.md 9.4: with --dry-run the files are listed and stay"
        a = self.write('lib', 'files', 'a.pdf', content='a pdf')
        self.add('one2000', a)
        self.lib('rm one2000 --delete-files')
        out = self.out(f'history --drop-files {self.head()} --yes --dry-run')
        self.assertIn('DRYRUN: 1 file (0 KB) not dropped from the history', out)
        self.assertEqual(len(self.state()['deleted']), 1)


# 10. .papers/files.json
# ======================

class TestFilesJson(SpecTest):
    "history.md 10"

    def test_format(self):
        "history.md 10: {\"files\": {path: sha256}}, one-space indentation, sorted keys, a final newline"
        a = self.write('lib', 'files', 'a.pdf', content='pdf a')
        b = self.write('out', 'b.pdf', content='pdf b')
        self.add('one2000', a, b)
        self.lib('file checksum')
        text = Path(self.path('lib', '.papers', 'files.json')).read_text()
        self.assertEqual(text, '{\n "files": {\n  "../out/b.pdf": "%s",\n  "files/a.pdf": "%s"\n }\n}\n'
                         % (sha(b'pdf b'), sha(b'pdf a')))

    def test_absolute(self):
        "history.md 10: with paths absolute, the keys are absolute"
        self.lib('config paths absolute')
        a = self.write('lib', 'files', 'a.pdf', content='pdf a')
        self.add('one2000', a)
        self.lib('file checksum')
        self.assertEqual(json.loads(Path(self.path('lib', '.papers', 'files.json')).read_text()),
                         {'files': {a: sha(b'pdf a')}})

    def test_deleted_without_checksums(self):
        "history.md 10: the file is deleted when no checksum is left"
        a = self.write('lib', 'files', 'a.pdf', content='pdf a')
        self.add('one2000', a)
        self.lib('file checksum')
        self.lib('rm one2000')
        self.assertFalse(os.path.exists(self.path('lib', '.papers', 'files.json')))

    def test_relative_to_the_bibtex(self):
        "history.md 10: in .papers/ of the library directory, the keys relative to the directory of the bibtex"
        shutil.rmtree(self.path('lib'))
        os.makedirs(self.path('lib', 'sub'))
        self.papers('init lib --bibtex lib/sub/refs.bib')
        a = self.write('lib', 'files', 'a.pdf', content='pdf a')
        Path(self.path('one.bib')).write_text(entry('one2000', a))
        self.lib('add ../one.bib')
        self.lib('file checksum')
        self.assertEqual(json.loads(Path(self.path('lib', '.papers', 'files.json')).read_text()),
                         {'files': {'../files/a.pdf': sha(b'pdf a')}})


if __name__ == '__main__':
    unittest.main()


class TestFilesJsonKeys(unittest.TestCase):
    "history.md: the keys of .papers/files.json use / on every system"

    def test_written_and_read_with_slash(self):
        from types import SimpleNamespace
        from papers import checksums
        with tempfile.TemporaryDirectory() as d:
            config = SimpleNamespace(file=os.path.join(d, '.papers', 'config.json'), is_library=True, libdir=d,
                                     bibtex=os.path.join(d, 'papers.bib'), absolute_paths=False)
            path = os.path.join(d, 'files', 'a.pdf')
            with patch('os.sep', '\\'), patch('os.path.relpath', return_value='files\\a.pdf'):
                checksums.save(config, {path: 'abc'})
            stored = json.load(open(os.path.join(d, '.papers', 'files.json')))
            self.assertEqual(stored, {'files': {'files/a.pdf': 'abc'}})
            # a key written with \ by papers on Windows before 3.0.0b6 is read too
            self.assertEqual(checksums.parse('{"files": {"files\\\\a.pdf": "abc"}}', config), {path: 'abc'})
