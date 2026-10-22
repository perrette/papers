"""Undo and redo in a library that has a pool, with the git backup: each
library has its own history (the pool too), and the origin records of the
library (.papers/origin/) are restored with its bibtex"""
import os
import unittest
from pathlib import Path

from papers.backup import run_git, cursor_commit
from papers.bib import Biblio
from papers.config import Config
from papers.pools import ORIGIN_DIR, Origin

from tests.common import ConfigTest


NEW_BIB = """@article{mine2022,
 author = {Mine, Me},
 keywords = {a},
 title = {My own paper},
 year = {2022}
}
"""

OTHER_BIB = """@article{other2023,
 author = {Other, An},
 title = {Another paper},
 year = {2023}
}
"""


class UndoPoolTest(ConfigTest):
    """a pool in pool/ and a library in lib/ that uses it, both with the
    git backup; local: whether the library is local (then with auto-push,
    so that `add` writes the pool too)"""

    local = False

    def setUp(self):
        super().setUp()
        self.papers('config --global local ' + ('true' if self.local else 'false'))
        self.papers('init pool --git --pool none')
        self.papers('init lib --git --pool ../pool' + (' --local' if self.local else ''))
        if self.local:
            self.lib('config auto-push true')
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('other.bib')).write_text(OTHER_BIB)

    def lib(self, cmd):
        return self.papers(cmd, cwd=self.path('lib'))

    def out(self, cmd):
        return self.papers(cmd, cwd=self.path('lib'), sp_cmd='check_output')

    def gitdir(self, where):
        return Config.load(self.path(where, '.papersconfig.json')).gitdir

    def commits(self, where):
        return int(run_git(self.gitdir(where), ['rev-list', '--count', 'HEAD']).stdout)

    def cursor(self, where='lib'):
        return cursor_commit(self.gitdir(where))

    def entries(self, where='lib'):
        return {e.key: e for e in Biblio.load(self.path(where, 'papers.bib'), '').entries}

    def keywords(self, key, where='lib'):
        e = self.entries(where)[key]
        return e['keywords'] if 'keywords' in e.fields_dict else None

    def record(self, key):
        "the origin record of a library entry, or None"
        return next((r for r in Origin.load(self.path('lib', ORIGIN_DIR)).records() if r.key == key), None)

    def origin_files(self):
        "{name: content} of the origin files of the library"
        d = self.path('lib', ORIGIN_DIR)
        return {f: Path(d, f).read_text() for f in sorted(os.listdir(d))} if os.path.isdir(d) else {}

    def tag(self, key, tag, where='lib'):
        "tag an entry of the library and push it, or tag an entry of the pool"
        if where == 'pool':
            self.lib(f'-C ../pool list -k {key} --add-tag {tag}')
        else:
            self.lib(f'list -k {key} --add-tag {tag}')
            self.lib(f'push {key}')

    def undo_to(self, commit):
        "undo in the library, one step at a time, back to the state of `commit`"
        for _ in range(10):
            if self.cursor() == commit:
                return
            self.lib('undo')
        self.fail(f'undo does not reach {commit}')


class UndoInLibrary:
    """checks for a library that is local and one that is not"""

    def test_add_then_undo_redo(self):
        lib, pool = self.commits('lib'), self.commits('pool')
        self.lib('add ../new.bib')
        # both the library and the pool get a commit
        self.assertEqual(self.commits('lib'), lib + 1)
        self.assertEqual(self.commits('pool'), pool + 1)
        self.assertIn('mine2022', self.entries('pool'))
        self.assertIsNotNone(self.record('mine2022'))

        pool = self.commits('pool')
        self.lib('undo')
        # the library only: the pool keeps the entry and its history
        self.assertNotIn('mine2022', self.entries())
        self.assertIn('mine2022', self.entries('pool'))
        self.assertEqual(self.commits('pool'), pool)
        # the origin file did not exist before the add: removed
        self.assertEqual(self.origin_files(), {})

        self.lib('redo')
        self.assertIn('mine2022', self.entries())
        self.assertIsNotNone(self.record('mine2022'))
        self.assertEqual(self.commits('pool'), pool)

    def test_undo_after_push(self):
        self.lib('add ../new.bib')
        before, origin = self.cursor(), self.origin_files()
        self.tag('mine2022', 'foo')
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a, foo')
        self.assertEqual(self.record('mine2022').entry['keywords'], 'a, foo')

        self.undo_to(before)
        # the bibtex and the origin records are those of the state restored
        self.assertEqual(self.keywords('mine2022'), 'a')
        self.assertEqual(self.origin_files(), origin)
        self.assertEqual(self.record('mine2022').entry['keywords'], 'a')
        # the pool still has the tag: it changed since the restored state
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a, foo')
        self.assertIn('(changed since last pull or push)', self.out('status'))
        self.assertIn('mine2022: changed in pool ../pool: keywords\n', self.out('pull --check') + '\n')

        # the push does not send the undone state back to the pool
        self.assertNotIn('Modified', self.out('push'))
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a, foo')
        # the pull takes the pool's version, without conflict
        out = self.out('pull')
        self.assertIn('Modified -> mine2022', out)
        self.assertEqual(self.keywords('mine2022'), 'a, foo')
        self.assertIn('(up to date)', self.out('status'))

    def test_undo_after_pull(self):
        self.lib('add ../new.bib')
        self.tag('mine2022', 'b', where='pool')
        before, origin = self.cursor(), self.origin_files()
        self.lib('pull')
        self.assertEqual(self.keywords('mine2022'), 'a, b')
        self.assertEqual(self.record('mine2022').entry['keywords'], 'a, b')

        self.lib('undo')
        self.assertEqual(self.cursor(), before)
        self.assertEqual(self.keywords('mine2022'), 'a')
        self.assertEqual(self.origin_files(), origin)
        self.assertEqual(self.record('mine2022').entry['keywords'], 'a')
        self.assertIn('(changed since last pull or push)', self.out('status'))

        # the push does not revert the pool's change
        self.assertNotIn('Modified', self.out('push'))
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a, b')
        # the pull takes it again
        self.assertIn('Modified -> mine2022', self.out('pull'))
        self.assertEqual(self.keywords('mine2022'), 'a, b')

        # redo brings the state after the pull back, origin records included
        self.lib('undo')
        self.lib('redo')
        self.assertEqual(self.keywords('mine2022'), 'a, b')
        self.assertEqual(self.record('mine2022').entry['keywords'], 'a, b')

    def test_restore_ref_restores_origin(self):
        self.lib('add ../new.bib')
        before, origin = self.cursor(), self.origin_files()
        self.tag('mine2022', 'foo')
        self.lib(f'restore --ref {before}')
        self.assertEqual(self.origin_files(), origin)
        self.assertEqual(self.keywords('mine2022'), 'a')


class TestUndoPool(UndoPoolTest, UndoInLibrary):
    "a library that is not local: changes of its entries go to the pool too"

    def test_pool_undo_redo(self):
        self.lib('add ../new.bib')
        lib = self.commits('lib')
        self.lib('-C ../pool undo')
        # the pool only
        self.assertNotIn('mine2022', self.entries('pool'))
        self.assertIn('mine2022', self.entries())
        self.assertEqual(self.commits('lib'), lib)
        self.lib('-C ../pool redo')
        self.assertIn('mine2022', self.entries('pool'))
        self.assertEqual(self.commits('lib'), lib)

    def test_pull_after_pool_undo(self):
        self.lib('add ../new.bib')
        self.tag('mine2022', 'foo')
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a, foo')
        self.lib('-C ../pool undo')
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a')
        # the record has the newer version: the pool changed relative to it
        self.assertEqual(self.record('mine2022').entry['keywords'], 'a, foo')
        self.assertIn('(changed since last pull or push)', self.out('status'))
        # the library did not change the entry since: the pull takes the older value
        self.assertIn('Modified -> mine2022', self.out('pull'))
        self.assertEqual(self.keywords('mine2022'), 'a')
        self.assertIn('(up to date)', self.out('status'))
        self.assertNotIn('Modified', self.out('push'))
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a')

    def test_pull_after_pool_undo_of_a_new_field(self):
        # a field that the pool undo removes is a removal for the
        # three-way merge, and a field removed on one side is kept from
        # the other (papers.merge): the library keeps it, and the push
        # sends it back to the pool (and says so)
        self.lib('add ../other.bib')
        self.tag('other2023', 'foo')
        self.lib('-C ../pool undo')
        self.assertIsNone(self.keywords('other2023', 'pool'))
        self.lib('pull')
        self.assertEqual(self.keywords('other2023'), 'foo')
        self.assertIn('Modified -> other2023', self.out('push'))
        self.assertEqual(self.keywords('other2023', 'pool'), 'foo')


    def test_undo_restores_distinct(self):
        self.lib('add ../new.bib')
        distinct = self.path('lib', '.papers', 'distinct.json')
        Path(distinct).write_text('{"distinct": []}\n')
        self.tag('mine2022', 'foo')  # the backup has distinct.json from now on
        self.lib('undo')
        self.assertTrue(os.path.exists(distinct))  # the state after the tag, before the push
        self.lib('undo')
        self.assertFalse(os.path.exists(distinct))
        self.lib('redo')
        self.assertEqual(Path(distinct).read_text(), '{"distinct": []}\n')


class TestUndoPoolLocal(UndoPoolTest, UndoInLibrary):
    "a local library, with auto-push"
    local = True


class TestUndoPoolNoGit(UndoPoolTest):
    """a local library without the git backup: undo swaps the bibtex with
    its previous version, and leaves the origin records as they are"""
    local = True

    def setUp(self):
        super().setUp()
        self.lib('config git false')

    def test_undo_after_pull(self):
        self.lib('add ../new.bib')
        self.tag('mine2022', 'b', where='pool')
        self.lib('pull')
        origin = self.origin_files()
        self.lib('undo')
        self.assertEqual(self.keywords('mine2022'), 'a')
        # the origin records are those after the pull
        self.assertEqual(self.origin_files(), origin)
        self.assertEqual(self.record('mine2022').entry['keywords'], 'a, b')
        # the undone pull is a change of the library: the push sends it, and says so
        self.assertIn('Modified -> mine2022', self.out('push'))
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a')


if __name__ == '__main__':
    unittest.main()
