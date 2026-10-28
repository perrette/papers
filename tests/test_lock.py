"""The locks of the libraries (papers.lock): a command that writes a library
holds .papers/lock, refreshed while it runs; a stale lock is taken over"""
import json
import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import papers.lock
from papers.bib import Biblio
from papers.config import Config, CONFIG_FILE_LOCAL
from papers.lock import LockError
from papers.utils import PapersExit

from tests.common import ConfigTest

BIB = """@article{mine2022,
 author = {Mine, Me},
 title = {My own paper},
 year = {2022}
}
"""


class LockTest(ConfigTest):
    def setUp(self):
        super().setUp()
        self.papers('init lib')
        self.config = Config.load(self.path('lib', CONFIG_FILE_LOCAL))
        self.lockfile = self.path('lib', '.papers', 'lock')
        Path(self.path('new.bib')).write_text(BIB)
        # a process of this computer that is alive while the test runs
        self.sleeper = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])

    def tearDown(self):
        papers.lock.release_all()
        self.sleeper.kill()
        self.sleeper.wait()
        super().tearDown()

    def other_lock(self, pid=None, host=None):
        "a lock of another command"
        Path(self.lockfile).write_text(json.dumps({
            'token': 'other', 'pid': self.sleeper.pid if pid is None else pid,
            'host': host or socket.gethostname(), 'command': 'papers add x.pdf'}))

    def entries(self):
        return [e.key for e in Biblio.load(self.path('lib', 'papers.bib'), '').entries]


class TestLock(LockTest):

    def test_acquire_release(self):
        papers.lock.acquire(self.config)
        content = json.loads(Path(self.lockfile).read_text())
        self.assertEqual(content['pid'], os.getpid())
        self.assertEqual(content['host'], socket.gethostname())
        papers.lock.acquire(self.config)  # held already: nothing to do
        papers.lock.check(self.config)
        papers.lock.release_all()
        self.assertFalse(os.path.exists(self.lockfile))

    def test_wait_then_error(self):
        self.other_lock()
        with patch('papers.lock.WAIT', 0.3), self.assertRaises(LockError) as error:
            papers.lock.acquire(self.config)
        self.assertIn('papers add x.pdf', str(error.exception))
        self.assertIn(f'pid {self.sleeper.pid}', str(error.exception))
        self.assertEqual(json.loads(Path(self.lockfile).read_text())['token'], 'other')

    def test_released_while_waiting(self):
        self.other_lock()
        start = time.monotonic()
        with patch('papers.lock.time.sleep', side_effect=lambda s: os.remove(self.lockfile)):
            papers.lock.acquire(self.config)
        self.assertLess(time.monotonic() - start, 5)
        self.assertEqual(json.loads(Path(self.lockfile).read_text())['pid'], os.getpid())

    def test_stale_process_gone(self):
        self.sleeper.kill()
        self.sleeper.wait()
        self.other_lock()
        papers.lock.acquire(self.config)  # at once: the process no longer exists
        self.assertEqual(json.loads(Path(self.lockfile).read_text())['pid'], os.getpid())

    def test_stale_not_refreshed(self):
        # another computer: stale once the file did not change for LIFETIME seconds
        self.other_lock(host='elsewhere', pid=1)
        with patch('papers.lock.LIFETIME', 0.3):
            papers.lock.acquire(self.config)
        self.assertEqual(json.loads(Path(self.lockfile).read_text())['pid'], os.getpid())

    def test_refreshed_lock_is_not_stale(self):
        self.other_lock(host='elsewhere', pid=1)
        sleep = time.sleep

        def refresh(seconds):
            self.other_lock(host='elsewhere', pid=1)  # rewritten by its holder: a new file
            sleep(0.05)
        with patch('papers.lock.LIFETIME', 0.3), patch('papers.lock.WAIT', 1), \
                patch('papers.lock.time.sleep', side_effect=refresh), self.assertRaises(LockError):
            papers.lock.acquire(self.config)

    def test_refresh(self):
        with patch('papers.lock.REFRESH', 0.05):
            papers.lock.acquire(self.config)
            ino, before = os.stat(self.lockfile).st_ino, os.stat(self.lockfile).st_mtime_ns
            time.sleep(0.5)
            after = os.stat(self.lockfile).st_mtime_ns
        self.assertNotEqual(before, after)  # touched
        self.assertEqual(os.stat(self.lockfile).st_ino, ino)  # not rewritten
        papers.lock.check(self.config)

    def test_take_over_only_the_stale_file(self):
        # another waiting command took the stale lock over first: its fresh lock stays
        self.other_lock(host='elsewhere', pid=1)
        stale = papers.lock._signature(self.lockfile)
        os.remove(self.lockfile)
        self.other_lock(host='faster', pid=2)
        papers.lock._take_over(self.lockfile, stale)
        self.assertEqual(json.loads(Path(self.lockfile).read_text())['host'], 'faster')
        self.assertEqual([f for f in os.listdir(os.path.dirname(self.lockfile)) if 'stale' in f], [])

    def test_take_over(self):
        self.other_lock(host='elsewhere', pid=1)
        papers.lock._take_over(self.lockfile, papers.lock._signature(self.lockfile))
        self.assertFalse(os.path.exists(self.lockfile))

    def test_refresh_does_not_rewrite(self):
        with patch('papers.lock.REFRESH', 0.05):
            papers.lock.acquire(self.config)
            self.other_lock()  # taken over: the refresh of this process leaves it alone
            time.sleep(0.3)
        self.assertEqual(json.loads(Path(self.lockfile).read_text())['token'], 'other')

    def test_lost(self):
        papers.lock.acquire(self.config)
        self.other_lock()  # taken over while this command could not refresh it
        with self.assertRaises(LockError):
            papers.lock.check(self.config)
        papers.lock.release_all()
        self.assertTrue(os.path.exists(self.lockfile))  # not ours: left as it is


class TestCommands(LockTest):

    def test_writing_command_waits(self):
        self.other_lock()
        with patch('papers.lock.WAIT', 0.3), self.assertRaises(PapersExit):
            self.papers('add ../new.bib', cwd=self.path('lib'))
        self.assertEqual(self.entries(), [])

    def test_reading_command_does_not_wait(self):
        self.papers('add ../new.bib', cwd=self.path('lib'))
        self.assertFalse(os.path.exists(self.lockfile))  # released at the end
        self.other_lock()
        with patch('papers.lock.WAIT', 0.3):
            out = self.papers('list', cwd=self.path('lib'), sp_cmd='check_output')
            self.papers(f'export {self.path("out")}', cwd=self.path('lib'))
        self.assertIn('mine2022', out)
        with patch('papers.lock.WAIT', 0.3), self.assertRaises(PapersExit):
            self.papers('list --add-tag a', cwd=self.path('lib'))

    def test_pool_locked_too(self):
        self.papers('init pool')
        self.papers('config pool ../pool', cwd=self.path('lib'))
        Path(self.path('pool', '.papers', 'lock')).write_text(json.dumps({
            'token': 'other', 'pid': self.sleeper.pid, 'host': socket.gethostname(), 'command': 'papers edit'}))
        with patch('papers.lock.WAIT', 0.3), self.assertRaises(PapersExit):
            self.papers('push', cwd=self.path('lib'))
        # the library was locked first, and released
        self.assertFalse(os.path.exists(self.lockfile))


class TestUndoLocksPool(LockTest):
    "undo in a shallow library locks the pool before it looks where the pool is"

    def test_undo_waits_for_the_pool(self):
        self.papers('init pool')
        self.papers('init shallow --pool pool')
        self.papers('add ../new.bib', cwd=self.path('shallow'))
        Path(self.path('pool', '.papers', 'lock')).write_text(json.dumps({
            'token': 'other', 'pid': self.sleeper.pid, 'host': socket.gethostname(), 'command': 'papers edit'}))
        with patch('papers.lock.WAIT', 0.3), self.assertRaises(PapersExit):
            self.papers('undo', cwd=self.path('shallow'))
        # nothing written: the library and the pool still have the entry
        shallow = [e.key for e in Biblio.load(self.path('shallow', 'papers.bib'), '').entries]
        pool = [e.key for e in Biblio.load(self.path('pool', 'papers.bib'), '').entries]
        self.assertEqual((shallow, pool), (['mine2022'], ['mine2022']))
        os.remove(self.path('pool', '.papers', 'lock'))
        self.papers('undo', cwd=self.path('shallow'))
        self.assertEqual(Biblio.load(self.path('pool', 'papers.bib'), '').entries, [])


class TestPoolStepFrom(ConfigTest):
    "a step of the pool made from a library says which one"

    def test_history_of_the_pool(self):
        self.papers('init pool')
        self.papers('init lib --pool pool')
        Path(self.path('new.bib')).write_text(BIB)
        self.papers('add ../new.bib', cwd=self.path('lib'))
        out = self.papers('history', cwd=self.path('pool'), sp_cmd='check_output')
        self.assertIn('papers add ../new.bib (', out)
        self.assertIn(', from ', out)
        self.assertIn('lib)', out)
        own = self.papers('history', cwd=self.path('lib'), sp_cmd='check_output')
        self.assertNotIn(', from ', own)


if __name__ == '__main__':
    unittest.main()
