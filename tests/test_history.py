"""The history of the machine (papers.history) and of a library in it
(papers.backup): the store of pieces and files, the tree of states and the
places, the retention, and the libraries that move, are copied or exported"""
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

import papers.backup
import papers.config
from papers import history
from papers.config import Config, CONFIG_FILE_LOCAL

from tests.common import ConfigTest, entry


BIB = """% a comment before the first entry
@string{jgr = {Journal of Geophysical Research}}

@article{a2000,
 title = {A, with an @ inside},
 journal = jgr
}

@article{b2001,
 title = {B été}
}
"""


class StoreTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = history.Store(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def objects(self):
        return sorted(f for _, _, files in os.walk(self.store.objects) for f in files)

    def state(self, text='', parent=None, t=None, deleted=()):
        return {'parent': parent, 'time': time.time() if t is None else t,
                'bibtex': {'pieces': self.store.put_text(text), 'sha': history.sha256(text.encode())},
                'files': {}, 'ops': [], 'deleted': list(deleted)}


class TestPieces(StoreTest):

    def test_byte_for_byte(self):
        for text in (BIB, BIB.replace('\n', '\r\n'), '', '@article{x,\n}', 'no entry at all\n'):
            self.assertEqual(self.store.text(self.store.put_text(text)), text)

    def test_pieces_of_entries(self):
        big = ''.join(f'@article{{k{i},\n title = {{T{i}}}\n}}\n\n' for i in range(2000))
        pieces = self.store.put_text(big)
        self.assertTrue(20 < len(pieces) < 200, len(pieces))  # about 32 entries a piece
        # an entry added in the middle changes the piece it is in only
        lines = big.split('@article{k1000,')
        changed = self.store.put_text(lines[0] + '@article{new,\n}\n\n@article{k1000,' + lines[1])
        self.assertLessEqual(len(set(changed) - set(pieces)), 2)

    def test_shared_pieces(self):
        self.store.put_text(BIB)
        before = self.objects()
        self.store.put_text(BIB.replace('{B été}', '{B changed}'))
        self.assertEqual(len(self.objects()), len(before) + 1)  # one entry changed: one piece

    def test_missing_piece(self):
        pieces = self.store.put_text(BIB)
        shutil.rmtree(self.store.objects)
        self.assertRaises(KeyError, self.store.text, pieces)

    def test_files(self):
        path = os.path.join(self.tmp.name, 'a.pdf')
        Path(path).write_text('pdf')
        digest = history.sha256(b'pdf')
        kept = self.store.put_file(path, digest)
        self.assertFalse(os.path.exists(path))
        self.assertEqual(self.store.file_object(digest), kept)
        self.assertTrue(kept.endswith(digest + '.pdf'))
        Path(path).write_text('pdf')
        self.assertEqual(self.store.put_file(path, digest), kept)  # stored once
        self.assertIsNone(self.store.file_object('0' * 64))


class TestStates(StoreTest):

    def test_identifier(self):
        for bad in ('', '../x', 'a/b', None):
            self.assertRaises(ValueError, self.store.project, bad)

    def test_tree(self):
        p = self.store.project('p')
        one = p.add(self.state('1'))
        two = p.add(self.state('2', parent=one))
        three = p.add(self.state('3', parent=two))
        branch = p.add(self.state('b', parent=one))
        self.assertEqual((one, two, three, branch), (1, 2, 3, 4))
        self.assertEqual(p.line(three), [3, 2, 1])
        self.assertEqual(p.path(three, branch), ([3, 2], [4]))
        self.assertEqual(p.path(three, one), ([3, 2], []))
        self.assertEqual(p.path(one, three), ([], [2, 3]))
        # read again from disk
        self.assertEqual(sorted(self.store.project('p').states()), [1, 2, 3, 4])

    def test_places(self):
        p = self.store.project('p')
        one = p.add(self.state('1', t=1))
        two = p.add(self.state('2', parent=one, t=2))
        p.add(self.state('1', parent=two, t=3))  # the same bibtex, later
        place = os.path.join(self.tmp.name, 'lib.bib')
        Path(place).write_text('')
        p.set_head(place, two, redo=[3])
        self.assertEqual(p.head(place), dict(p.head(place), state=2, redo=[3]))
        # a new place starts from the latest state with its bibtex, or else the latest
        self.assertEqual(p.start_state(history.sha256(b'1')), 3)
        self.assertEqual(p.start_state(history.sha256(b'unknown')), 3)
        p.set_head('/nowhere/lib.bib', one)
        self.assertEqual(p.forget_missing_places(), ['/nowhere/lib.bib'])
        self.assertEqual(list(p.heads()), [place])
        self.assertEqual(p.remove_head(place), 0)


class TestPrune(StoreTest):

    def test_oldest_states_first(self):
        p = self.store.project('p')
        now = time.time()
        old = p.add(self.state('@article{old,\n}\n', t=now - 100))
        new = p.add(self.state('@article{new,\n}\n', parent=old, t=now))
        p.set_head('/lib.bib', new)
        later = now + history.GRACE + 1
        self.assertEqual(self.store.prune(0, now=later), [])  # no limit
        dropped = self.store.prune(1, now=later, dry=True)
        self.assertEqual([n for _, n, _ in dropped], [old])
        self.assertIn(old, p.states())  # dry: nothing changed
        self.store.prune(1, now=later)
        self.assertEqual(sorted(self.store.project('p').states()), [new])  # the current state is kept
        self.assertEqual(len(self.objects()), 1)

    def test_recent_objects_kept(self):
        # a command writes its pieces before its state
        self.store.put_text('@article{orphan,\n}\n')
        self.store.prune(1)
        self.assertEqual(len(self.objects()), 1)
        self.store.prune(1, now=time.time() + history.GRACE + 1)
        self.assertEqual(self.objects(), [])

    def test_files_to_the_discard(self):
        p = self.store.project('p')
        path = os.path.join(self.tmp.name, 'a.pdf')
        Path(path).write_bytes(b'x' * 1000)
        digest = history.sha256(b'x' * 1000)
        self.store.put_file(path, digest)
        old = p.add(self.state('', t=1, deleted=[digest]))
        p.set_head('/lib.bib', p.add(self.state('@a{b,\n}', parent=old)))
        discarded = []
        self.store.prune(10, discard=discarded.append, now=time.time() + history.GRACE + 1)
        self.assertEqual(len(discarded), 1)
        self.assertTrue(discarded[0].endswith('.pdf'))

    def test_extra(self):
        p = self.store.project('p')
        old = p.add(self.state('@a{a,\n}', t=1))
        p.set_head('/lib.bib', p.add(self.state('@a{b,\n}', parent=old)))
        size = self.store.size()
        self.assertEqual(self.store.prune(size, dry=True), [])
        self.assertEqual(len(self.store.prune(size, extra=1000, dry=True)), 1)


class LibraryTest(ConfigTest):

    def setUp(self):
        super().setUp()
        self.papers('init lib')

    def lib(self, cmd, where='lib'):
        return self.papers(cmd, cwd=self.path(where))

    def out(self, cmd, where='lib'):
        return self.papers(cmd, cwd=self.path(where), sp_cmd='check_output')

    def config(self, where='lib'):
        return Config.load(self.path(where, CONFIG_FILE_LOCAL))

    def project(self, where='lib'):
        return papers.backup.project_of(self.config(where), create=False)

    def keys(self, where='lib'):
        text = Path(self.path(where, 'papers.bib')).read_text()
        return sorted(k for k in ('one2000', 'two2000', 'three2000') if '{' + k + ',' in text)

    def add(self, key, where='lib'):
        Path(self.path(f'{key}.bib')).write_text(entry(key))
        self.lib(f'add ../{key}.bib', where)


class TestDownloads(LibraryTest):
    "papers add --move takes a PDF out of ~/Downloads: undo puts it back there"

    def test_add_move_undo(self):
        os.makedirs(self.path('Downloads'))
        pdf = self.path('Downloads', 'paper.pdf')
        Path(pdf).write_text('%PDF the paper')
        Path(self.path('one.bib')).write_text(entry('one2000'))
        self.lib(f'add ../one.bib --attach {pdf} --move')
        self.assertFalse(os.path.exists(pdf))
        moved = [os.path.join(d, f) for d, _, files in os.walk(self.path('lib', 'files')) for f in files]
        self.assertEqual(len(moved), 1)
        out = self.out('undo')
        self.assertIn(f'--> moved back to {pdf}', out)
        self.assertEqual(Path(pdf).read_text(), '%PDF the paper')
        self.assertFalse(os.path.exists(moved[0]))
        self.assertEqual(self.keys(), [])
        self.lib('redo')
        self.assertFalse(os.path.exists(pdf))
        self.assertEqual(Path(moved[0]).read_text(), '%PDF the paper')
        # outside the library: an absolute path in the state; inside: relative to the library
        project, place = self.project()
        op, = project.state(project.head(place)['state'])['ops']
        self.assertEqual((op['op'], op['src']), ('moved', pdf))
        self.assertFalse(os.path.isabs(op['dst']))


class TestPlaces(LibraryTest):
    "the history is found by the identifier of the library, wherever the library is"

    def test_no_trace_before_a_change(self):
        self.lib('list')
        self.assertNotIn('id', json.load(open(self.path('lib', CONFIG_FILE_LOCAL))))
        self.assertIn('no history yet', self.out('history'))
        self.add('one2000')
        self.assertRegex(json.load(open(self.path('lib', CONFIG_FILE_LOCAL)))['id'], '^[0-9a-f]{32}$')
        self.assertFalse(os.path.exists(self.path('lib', '.papers', 'backup')))
        # the folder of papers' internals is not tracked by git
        self.assertEqual(Path(self.path('lib', '.papers', '.gitignore')).read_text(), '*\n')

    def test_gitignore(self):
        ignore = self.path('lib', '.papers', '.gitignore')
        Path(ignore).write_text('backup/\n')  # written by earlier versions: replaced
        self.lib('config files copy')
        self.assertEqual(Path(ignore).read_text(), '*\n')
        Path(ignore).write_text('files.json\n')  # the user's: kept
        self.lib('config files move')
        self.assertEqual(Path(ignore).read_text(), 'files.json\n')

    def test_moved_library_continues(self):
        self.add('one2000')
        self.add('two2000')
        shutil.move(self.path('lib'), self.path('moved'))
        self.lib('undo', where='moved')
        self.assertEqual(self.keys('moved'), ['one2000'])
        project, place = self.project('moved')
        self.assertEqual(list(project.heads()), [place])  # the old place is forgotten

    def test_copied_library_branches(self):
        self.add('one2000')
        shutil.copytree(self.path('lib'), self.path('copy'))
        self.add('two2000')                 # in the library
        self.add('three2000', where='copy')  # in the copy
        self.lib('undo', where='copy')
        self.assertEqual(self.keys('copy'), ['one2000'])
        self.assertEqual(self.keys(), ['one2000', 'two2000'])  # the library is left alone
        self.lib('undo', where='copy')       # the history before the copy is shared
        self.assertEqual(self.keys('copy'), [])
        self.lib('undo')
        self.assertEqual(self.keys(), ['one2000'])
        project, _ = self.project()
        self.assertEqual(len(project.heads()), 2)

    def test_export_has_its_own_history(self):
        self.add('one2000')
        self.lib('export ../out')
        self.assertNotEqual(self.config('out').library_id(create=False), self.config().library_id(create=False))


class TestHistoryCommand(LibraryTest):

    def test_list(self):
        self.add('one2000')
        self.add('two2000')
        self.lib('undo')
        out = self.out('history')
        lines = [line.strip() for line in out.splitlines()]
        self.assertRegex(lines[0], r'^3 papers add ../two2000.bib .*\(undone: `papers redo`\)$')
        self.assertRegex(lines[1], r'^> 2 papers add ../one2000.bib')
        self.assertRegex(lines[2], r'^1 the library before its first recorded command')
        self.assertIn('up to 500 MB', out)

    def test_stale_backups(self):
        os.makedirs(self.path('lib', '.papers', 'backup', '.git'))
        Path(self.path('lib', '.papers', 'backup', 'papers.bib')).write_text('x' * 2000)
        out = self.out('history')
        self.assertIn('stale: ', out)
        self.assertIn('no longer used', out)
        self.assertIn('rm -rf ', out)
        self.assertTrue(os.path.isdir(self.path('lib', '.papers', 'backup')))  # papers does not delete it

    def test_all_and_remove(self):
        self.add('one2000')
        self.papers('init other')
        self.add('two2000', where='other')
        out = self.out('history --all')
        ids = [self.config(w).library_id(create=False) for w in ('lib', 'other')]
        for id in ids:
            self.assertIn(f'* {id}: 2 steps', out)
        self.lib(f'history --remove {ids[1]} --yes')
        self.assertNotIn(ids[1], self.out('history --all'))
        self.lib('history --remove --yes')
        self.assertNotIn(ids[0], self.out('history --all'))
        self.assertIn('no history yet', self.out('history'))

    def test_remove_keeps_the_history_of_a_copy(self):
        self.add('one2000')
        shutil.copytree(self.path('lib'), self.path('copy'))
        self.lib('list', where='copy')
        self.add('two2000', where='copy')
        out = self.out('history --remove')
        self.assertIn('stays for the other folder', out)
        self.lib('undo', where='copy')
        self.assertEqual(self.keys('copy'), ['one2000'])

    def test_remove_without_terminal(self):
        self.add('one2000')
        with self.assertRaisesRegex(Exception, 'no terminal to confirm'):
            self.lib('history --remove')


class TestSeparate(LibraryTest):
    "history-separate: a library keeps its history in a store of its own"

    def test_own_store(self):
        self.lib('config history-separate true')
        self.add('one2000')
        id = self.config().library_id(create=False)
        root = self.config().history_dir
        self.assertTrue(os.path.isdir(os.path.join(root, 'separate', id, 'projects', id)))
        self.assertFalse(os.path.isdir(os.path.join(root, 'projects', id)))
        self.assertIn(f'separate/{id}', self.out('history --all').replace(os.sep, '/'))
        self.lib('undo')
        self.assertEqual(self.keys(), [])

    def test_size_of_its_own(self):
        self.lib('config history-separate true')
        self.lib('config history-size 7')
        self.add('one2000')
        self.assertIn('up to 7 MB', self.out('history'))
        # without history-separate, the size of the library does not apply
        self.lib('config history-separate false')
        self.assertIn('up to 500 MB', self.out('history'))

    def test_dry_run_writes_nothing(self):
        Path(self.path('one.bib')).write_text(entry('one2000'))
        self.lib('add ../one.bib --dry-run')
        self.assertFalse(os.path.exists(self.config().history_dir + '/projects'))


if __name__ == '__main__':
    unittest.main()
