"""Undo and redo in a library that has a pool: each library has its own
history (the pool too), and the origin records of the library
(.papers/origin/) are restored with its bibtex. A step that also wrote the
pool is undone and redone in the pool too, unless the pool changed since
(or with --library-only)."""
import os
import unittest
from pathlib import Path

import papers.backup
from papers.bib import Biblio
from papers.config import Config, CONFIG_FILE_LOCAL
from papers.pools import ORIGIN_DIR, Origin
from papers.utils import PapersExit

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
    """a pool in pool/ and a shallow library in lib/ that uses it;
    auto_push: the auto-push setting of the library"""

    auto_push = False

    def setUp(self):
        super().setUp()
        self.papers('init pool')
        self.papers('init lib --pool ../pool')
        if self.auto_push:
            self.lib('config auto-push true')
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('other.bib')).write_text(OTHER_BIB)

    def lib(self, cmd):
        return self.papers(cmd, cwd=self.path('lib'))

    def out(self, cmd):
        return self.papers(cmd, cwd=self.path('lib'), sp_cmd='check_output')

    def project(self, where):
        return papers.backup.project_of(Config.load(self.path(where, CONFIG_FILE_LOCAL)), create=False)

    def commits(self, where):
        "the number of states of the history of a library"
        project, _ = self.project(where)
        return len(project.states()) if project else 0

    def cursor(self, where='lib'):
        "the current state of a library"
        project, place = self.project(where)
        return project.head(place)['state']

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

    def undo_to(self, commit, options=''):
        "undo in the library, one step at a time, back to the state of `commit`"
        for _ in range(10):
            if self.cursor() == commit:
                return
            self.lib(f'undo {options}')
        self.fail(f'undo does not reach {commit}')


class UndoInLibrary:
    """checks for a library that is local and one that is not"""

    def test_add_then_undo_redo(self):
        lib, pool = self.commits('lib'), self.commits('pool')
        self.lib('add ../new.bib')
        # both the library and the pool get a state (and the first one, the state before it)
        self.assertEqual(self.commits('lib'), lib + (2 if lib == 0 else 1))
        self.assertEqual(self.commits('pool'), pool + (2 if pool == 0 else 1))
        self.assertIn('mine2022', self.entries('pool'))
        self.assertIsNotNone(self.record('mine2022'))

        pool = self.commits('pool')
        out = self.out('undo')
        # the pool takes back its step of the add too
        self.assertIn('pool ../pool: also undone', out)
        self.assertNotIn('mine2022', self.entries())
        self.assertNotIn('mine2022', self.entries('pool'))
        self.assertEqual(self.commits('pool'), pool)
        # the origin file did not exist before the add: removed
        self.assertEqual(self.origin_files(), {})

        self.assertIn('pool ../pool: also redone', self.out('redo'))
        self.assertIn('mine2022', self.entries())
        self.assertIn('mine2022', self.entries('pool'))
        self.assertIsNotNone(self.record('mine2022'))
        self.assertEqual(self.commits('pool'), pool)

    def test_add_then_undo_library_only(self):
        self.lib('add ../new.bib')
        pool = self.commits('pool')
        self.lib('undo --library-only')
        # the library only: the pool keeps the entry and its history
        self.assertNotIn('mine2022', self.entries())
        self.assertIn('mine2022', self.entries('pool'))
        self.assertEqual(self.commits('pool'), pool)
        self.assertEqual(self.origin_files(), {})
        # the pool is still where the add left it: redo has nothing to do there
        self.assertNotIn('pool ../pool', self.out('redo'))
        self.assertIn('mine2022', self.entries())
        self.assertIsNotNone(self.record('mine2022'))

    def test_pool_changed_since(self):
        self.lib('add ../new.bib')
        self.tag('mine2022', 'b', where='pool')
        out = self.out('undo')
        # the pool has a step on top of that of the add, which changed the entry: the revert keeps it
        self.assertIn('pool ../pool: changed since; nothing changed there for revert of step', out)
        self.assertIn('mine2022: added by step', out)
        self.assertNotIn('mine2022', self.entries())
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a, b')

    def test_pool_changed_since_elsewhere(self):
        # another entry changed in the pool since the add: the add is reverted there
        self.lib('add ../other.bib')
        self.lib('add ../new.bib')
        self.tag('other2023', 'b', where='pool')
        pool = self.commits('pool')
        out = self.out('undo')
        self.assertIn('pool ../pool: changed since, so step', out)
        self.assertNotIn('mine2022', self.entries('pool'))
        self.assertEqual(self.keywords('other2023', 'pool'), 'b')
        self.assertEqual(self.commits('pool'), pool + 1)  # a new step: the revert
        # redo takes the revert back in the pool
        self.assertIn('pool ../pool: changed since, so step', self.out('redo'))
        self.assertIn('mine2022', self.entries('pool'))
        self.assertIn('mine2022', self.entries())
        self.assertEqual(self.keywords('other2023', 'pool'), 'b')

    def test_redo_after_the_pool_moved_on(self):
        # undo takes the pool's step back; the pool changes; redo does the step again there (a new step)
        self.lib('add ../other.bib')
        self.lib('add ../new.bib')
        self.lib('undo')
        self.assertNotIn('mine2022', self.entries('pool'))
        self.tag('other2023', 'b', where='pool')
        pool = self.commits('pool')
        out = self.out('redo')
        self.assertIn('done again there', out)
        self.assertIn('mine2022', self.entries('pool'))
        self.assertIn('mine2022', self.entries())
        self.assertEqual(self.keywords('other2023', 'pool'), 'b')
        self.assertEqual(self.commits('pool'), pool + 1)
        # undo again: the step is reverted there (it is no longer in the pool's history line)
        self.lib('undo')
        self.assertNotIn('mine2022', self.entries('pool'))
        self.assertEqual(self.keywords('other2023', 'pool'), 'b')

    def test_pool_changed_outside_papers(self):
        self.lib('add ../new.bib')
        bib = Path(self.path('pool', 'papers.bib'))
        bib.write_text(bib.read_text() + OTHER_BIB)
        self.assertIn('pool ../pool: changed outside papers', self.out('undo'))
        self.assertNotIn('mine2022', self.entries())
        self.assertIn('mine2022', self.entries('pool'))
        self.assertIn('other2023', self.entries('pool'))

    def test_pool_undone_first(self):
        # the pool undid the add itself: undo in the library has nothing to do there
        self.lib('add ../new.bib')
        self.lib('-C ../pool undo')
        self.assertNotIn('pool ../pool', self.out('undo'))
        self.assertNotIn('mine2022', self.entries())
        self.assertNotIn('mine2022', self.entries('pool'))

    def test_undo_after_push(self):
        self.lib('add ../new.bib')
        before, origin = self.cursor(), self.origin_files()
        self.tag('mine2022', 'foo')
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a, foo')

        self.undo_to(before)
        # the push is undone in the pool too: in sync
        self.assertEqual(self.keywords('mine2022'), 'a')
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a')
        self.assertEqual(self.origin_files(), origin)
        self.assertIn('../pool (in sync)', self.out('status'))

        # several steps at once: the pool follows
        project, place = self.project('lib')
        steps = len(project.head(place)['redo'])
        self.lib(f'redo -n {steps}')
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a, foo')
        self.lib(f'undo -n {steps}')
        self.assertEqual(self.cursor(), before)
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a')

    def test_undo_after_push_library_only(self):
        self.lib('add ../new.bib')
        before, origin = self.cursor(), self.origin_files()
        self.tag('mine2022', 'foo')
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a, foo')
        self.assertEqual(self.record('mine2022').entry['keywords'], 'a, foo')

        self.undo_to(before, '--library-only')
        # the bibtex and the origin records are those of the state restored
        self.assertEqual(self.keywords('mine2022'), 'a')
        self.assertEqual(self.origin_files(), origin)
        self.assertEqual(self.record('mine2022').entry['keywords'], 'a')
        # the pool still has the tag: it changed since the restored state
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a, foo')
        self.assertIn('../pool (pool changed)', self.out('status'))
        self.assertIn('mine2022: changed in pool ../pool: keywords\n', self.out('pull --check') + '\n')

        # the push does not send the undone state back to the pool
        self.assertNotIn('Modified', self.out('push'))
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a, foo')
        # the pull takes the pool's version, without conflict
        out = self.out('pull')
        self.assertIn('Modified -> mine2022', out)
        self.assertEqual(self.keywords('mine2022'), 'a, foo')
        self.assertIn('../pool (in sync)', self.out('status'))

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
        self.assertIn('../pool (pool changed)', self.out('status'))

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
    "a shallow library: add adds the new entries to the pool too"

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
        self.assertIn('../pool (pool changed)', self.out('status'))
        # the library did not change the entry since: the pull takes the older value
        self.assertIn('Modified -> mine2022', self.out('pull'))
        self.assertEqual(self.keywords('mine2022'), 'a')
        self.assertIn('../pool (in sync)', self.out('status'))
        self.assertNotIn('Modified', self.out('push'))
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a')

    def test_pull_after_pool_undo_of_a_new_field(self):
        # a field that the pool undo removes is a removal for the
        # three-way merge (papers.merge): the pull removes it from the
        # library too, and the push does not bring it back
        self.lib('add ../other.bib')
        self.tag('other2023', 'foo')
        self.lib('-C ../pool undo')
        self.assertIsNone(self.keywords('other2023', 'pool'))
        self.lib('pull')
        self.assertIsNone(self.keywords('other2023'))
        self.assertNotIn('Modified', self.out('push'))
        self.assertIsNone(self.keywords('other2023', 'pool'))


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


class TestUndoPoolAutoPush(UndoPoolTest, UndoInLibrary):
    "a shallow library, with auto-push"
    auto_push = True

    def test_undo_pushes_what_a_step_did_not(self):
        # a step made with auto-push off left a change unpushed: the undo to it pushes it
        self.lib('add ../new.bib')
        self.lib('config auto-push false')
        self.lib('list -k mine2022 --add-tag b')
        self.lib('list -k mine2022 --add-tag c')
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a')
        self.lib('config auto-push true')
        out = self.out('undo')
        self.assertEqual(self.keywords('mine2022'), 'a, b')
        self.assertIn('mine2022: also modified in pool ../pool', out)
        self.assertEqual(self.keywords('mine2022', 'pool'), 'a, b')
        # the push is a new step: nothing to redo, as after any command; restore reaches the step undone
        self.assertIn('the push is a new step: nothing to redo now', out)
        with self.assertRaises(PapersExit):
            self.lib('redo')

    def test_undo_without_anything_to_push(self):
        self.lib('add ../new.bib')
        self.tag('mine2022', 'foo')
        lib = self.commits('lib')
        self.lib('undo')
        self.assertEqual(self.commits('lib'), lib)  # no step of a push


class TestUndoFileRmShallow(UndoPoolTest):
    """`file rm` in a shallow library deletes the pool file (kept in the history) and
    removes the link from the pool entry: undo in the library restores the
    file and the links of both; with --library-only, the pool keeps the change"""

    def test_undo_file_rm(self):
        self.lib('add ../new.bib')
        self.lib('config files move')
        Path(self.path('si.pdf')).write_text('supplement')
        self.lib(f'file attach mine2022 {self.path("si.pdf")}')
        biblio = Biblio.load(self.path('lib', 'papers.bib'), '')
        si, = biblio.get_files(self.entries()['mine2022'])
        self.assertTrue(si.startswith(self.path('pool', 'files')), si)
        self.lib(f'file rm {si}')
        self.assertFalse(os.path.exists(si))
        self.assertNotIn('file', self.entries('pool')['mine2022'].fields_dict)

        self.lib('undo')
        self.assertEqual(biblio.get_files(self.entries()['mine2022']), [si])
        self.assertEqual(Path(si).read_text(), 'supplement')  # from the history
        self.assertIn('file', self.entries('pool')['mine2022'].fields_dict)
        self.assertIn('../pool (in sync)', self.out('status'))

        self.lib('redo')
        self.assertFalse(os.path.exists(si))
        self.lib('undo --library-only')
        self.assertEqual(biblio.get_files(self.entries()['mine2022']), [si])
        self.assertEqual(Path(si).read_text(), 'supplement')
        self.assertNotIn('file', self.entries('pool')['mine2022'].fields_dict)
        # the pool entry no longer has the link it had at the restored state: the pull removes it
        self.lib('pull')
        self.assertNotIn('file', self.entries()['mine2022'].fields_dict)


if __name__ == '__main__':
    unittest.main()


class TestSeveralSavesOfThePool(UndoPoolTest):
    "a command that saved the pool twice: undo takes the pool back to before the first save"

    def test_undo(self):
        from papers import journal
        from papers.library import savebib
        self.lib('add ../new.bib')
        pool_before = self.entries('pool')
        lib_config = Config.load(self.path('lib', CONFIG_FILE_LOCAL))
        pool_config = Config.load(self.path('pool', CONFIG_FILE_LOCAL))
        journal.start(lib_config.bibtex)
        papers.backup.start(lib_config, 'tag')
        for tag in ('x', 'y'):  # two saves of the pool in one command
            biblio = Biblio.load(pool_config.bibtex, '')
            biblio.entries[0]['keywords'] = tag
            savebib(biblio, pool_config)
        lib = Biblio.load(lib_config.bibtex, '')
        lib.entries[0]['note'] = 'changed'
        savebib(lib, lib_config)
        self.assertEqual(self.keywords('mine2022', 'pool'), 'y')
        self.lib('undo')
        self.assertEqual(self.keywords('mine2022', 'pool'), pool_before['mine2022']['keywords'])
        self.lib('redo')
        self.assertEqual(self.keywords('mine2022', 'pool'), 'y')


class TestNumberedStatesOfTwoStores(UndoPoolTest):
    """history-separate: the library and its pool in two stores, with the
    numbered states of papers up to 3.0.0b5. The link of a library step to
    its pool's step keeps a number; the pool's store maps it once upgraded."""

    def as_numbered(self):
        "write the states of both histories as an earlier version did (000001.json, ...)"
        import json
        projects = [self.project(where)[0] for where in ('lib', 'pool')]
        numbers = {}
        for project in projects:
            order = sorted(project.states(), key=lambda n: project.state(n)['time'])
            numbers[project.id] = {n: i + 1 for i, n in enumerate(order)}
        for project in projects:
            ids = numbers[project.id]
            for n, state in project.states().items():
                state = dict(state, parent=ids.get(state.get('parent')))
                if state.get('pools'):
                    state['pools'] = {p: dict(link, state=numbers[p][link['state']])
                                      for p, link in state['pools'].items()}
                Path(project.states_dir, f'{ids[n]:06d}.json').write_text(json.dumps(state))
                os.remove(project._path(n))
            heads = json.loads(Path(project.dir, 'heads.json').read_text())
            for head in heads.values():
                head['state'] = ids[head['state']]
                head['redo'] = [ids[r] for r in head.get('redo') or []]
            Path(project.dir, 'heads.json').write_text(json.dumps(heads))

    def check_undo_redo(self, first):
        self.lib('config history-separate true')
        self.lib('add ../new.bib')
        lib, pool = (self.project(where)[0] for where in ('lib', 'pool'))
        self.assertNotEqual(lib.store.root, pool.store.root)
        self.as_numbered()
        self.project(first)[0].states()  # this store is upgraded first
        self.assertIn('pool ../pool: also undone', self.out('undo'))
        self.assertNotIn('mine2022', self.entries('pool'))
        self.assertIn('pool ../pool: also redone', self.out('redo'))
        self.assertIn('mine2022', self.entries('pool'))

    def test_library_upgraded_first(self):
        self.check_undo_redo('lib')

    def test_pool_upgraded_first(self):
        self.check_undo_redo('pool')
