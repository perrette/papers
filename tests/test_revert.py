"""papers history --revert N: step N taken back alone, as a new step (see
papers.revert)"""
import json
import os
import unittest
from pathlib import Path

import papers.backup
from papers.bib import Biblio
from papers.config import Config, CONFIG_FILE_LOCAL
from papers.utils import PapersExit

from tests.common import FileTest, entry


class RevertTest(FileTest):

    def setUp(self):
        super().setUp()
        Path(self.path('a.bib')).write_text(entry('one2000') + entry('two2001'))
        self.lib('add ../a.bib')

    def entries(self):
        return {e.key: e for e in Biblio.load(self.path('lib', 'papers.bib'), '').entries}

    def field(self, key, name):
        e = self.entries()[key]
        return e[name] if name in e.fields_dict else None

    def project(self):
        return papers.backup.project_of(Config.load(self.path('lib', CONFIG_FILE_LOCAL)), create=False)

    def step(self):
        "the current step of the library"
        project, place = self.project()
        return project.head(place)['state']

    def state(self, n):
        project, _ = self.project()
        return project.state(n)


class TestRevertEntries(RevertTest):

    def test_tags_one_by_one(self):
        self.lib('tag one2000 --add climate')
        n = self.step()
        self.lib('tag one2000 --add later')
        self.lib('tag two2001 --add ice')
        out = self.out(f'history --revert {n}')
        self.assertIn('Modified -> one2000', out)
        self.assertEqual(self.field('one2000', 'keywords'), 'later')
        self.assertEqual(self.field('two2001', 'keywords'), 'ice')
        # a new step, which says what it reverts; undo takes it back
        self.assertEqual(self.state(self.step())['reverts'], [n])
        self.lib('undo')
        self.assertEqual(self.field('one2000', 'keywords'), 'climate, later')

    def test_tag_removed_comes_back(self):
        self.lib('tag one2000 --add a b')
        self.lib('tag one2000 --rm a')
        n = self.step()
        self.lib('tag one2000 --add c')
        self.lib(f'history --revert {n}')
        self.assertEqual(self.field('one2000', 'keywords'), 'b, c, a')

    def test_field(self):
        self.lib('edit one2000 --set journal=Nature')
        n = self.step()
        self.lib('edit two2001 --set journal=Science')
        self.lib(f'history --revert {n}')
        self.assertIsNone(self.field('one2000', 'journal'))
        self.assertEqual(self.field('two2001', 'journal'), 'Science')

    def test_conflict(self):
        self.lib('edit one2000 --set journal=Nature')
        n = self.step()
        self.lib('edit one2000 --set journal=Science')
        steps = len(self.project()[0].states())
        with self.assertRaises(PapersExit):  # no terminal: an error, nothing saved
            self.lib(f'history --revert {n}')
        self.assertEqual(len(self.project()[0].states()), steps)
        self.lib(f'history --revert {n} --on-duplicate keep')
        self.assertEqual(self.field('one2000', 'journal'), 'Science')
        self.lib(f'history --revert {n} --on-duplicate update')
        self.assertIsNone(self.field('one2000', 'journal'))

    def test_skip(self):
        self.lib('edit one2000 --set journal=Nature')
        n = self.step()
        self.lib('edit one2000 --set journal=Science')
        out = self.out(f'history --revert {n} --on-duplicate skip')
        self.assertIn('one2000: changed since step', out)
        self.assertEqual(self.field('one2000', 'journal'), 'Science')

    def test_added_entry(self):
        Path(self.path('b.bib')).write_text(entry('three2002'))
        self.lib('add ../b.bib')
        n = self.step()
        self.lib('tag one2000 --add later')
        out = self.out(f'history --revert {n}')
        self.assertIn('Removed -> three2002', out)
        self.assertNotIn('three2002', self.entries())
        self.assertEqual(self.field('one2000', 'keywords'), 'later')

    def test_added_entry_changed_since(self):
        Path(self.path('b.bib')).write_text(entry('three2002'))
        self.lib('add ../b.bib')
        n = self.step()
        self.lib('tag three2002 --add later')
        out = self.out(f'history --revert {n}')
        self.assertIn('three2002: added by step', out)
        self.assertIn('three2002', self.entries())

    def test_removed_entry(self):
        self.lib('rm two2001')
        n = self.step()
        self.lib('tag one2000 --add later')
        out = self.out(f'history --revert {n}')
        self.assertIn('Added -> two2001', out)
        self.assertIn('two2001', self.entries())
        self.assertEqual(self.field('one2000', 'keywords'), 'later')

    def test_key(self):
        self.lib('edit one2000 --key first2000 --keep-old-key')
        n = self.step()
        self.lib('tag first2000 --add later')
        self.lib(f'history --revert {n}')
        self.assertIn('one2000', self.entries())
        self.assertNotIn('first2000', self.entries())
        self.assertIsNone(self.field('one2000', 'ids'))
        self.assertEqual(self.field('one2000', 'keywords'), 'later')

    def test_distinct(self):
        distinct = self.path('lib', '.papers', 'distinct.json')
        pair = [{'authortitle': 'one'}, {'authortitle': 'two'}]
        Path(distinct).write_text(json.dumps({'distinct': [pair]}))
        self.lib('tag one2000 --add a')  # the step has the pair
        n = self.step()
        self.lib('tag two2001 --add b')
        self.lib(f'history --revert {n}')
        self.assertEqual(json.load(open(distinct))['distinct'], [])

    def test_errors(self):
        with self.assertRaises(PapersExit):
            self.lib('history --revert 1')  # the first step
        with self.assertRaises(PapersExit):
            self.lib('history --revert 99')
        self.lib('tag one2000 --add a')
        n = self.step()
        self.lib('undo')
        self.lib('tag one2000 --add b')  # step n is no longer in the current history
        with self.assertRaises(PapersExit):
            self.lib(f'history --revert {n}')

    def test_dry_run(self):
        self.lib('tag one2000 --add a')
        n = self.step()
        self.lib(f'history --revert {n} --dry-run')
        self.assertEqual(self.field('one2000', 'keywords'), 'a')
        self.assertEqual(self.step(), n)


class TestRevertFiles(RevertTest):

    def test_added_with_file(self):
        pdf = self.write('downloads', 'three.pdf', content='pdf three')
        Path(self.path('b.bib')).write_text(entry('three2002', pdf))
        self.lib('add ../b.bib --move')
        n = self.step()
        self.assertFalse(os.path.exists(pdf))
        self.lib('tag one2000 --add later')
        out = self.out(f'history --revert {n}')
        self.assertIn('moved back to', out)
        self.assertEqual(Path(pdf).read_text(), 'pdf three')
        self.assertEqual(self.libfiles(), [])
        # undo of the revert: the file goes where the add had put it
        self.lib('undo')
        self.assertFalse(os.path.exists(pdf))
        self.assertEqual(len(self.libfiles()), 1)

    def test_removed_with_file(self):
        pdf = self.write('downloads', 'three.pdf', content='pdf three')
        Path(self.path('b.bib')).write_text(entry('three2002', pdf))
        self.lib('add ../b.bib --move')
        kept, = self.libfiles()
        self.lib('rm three2002 --delete-files')
        n = self.step()
        self.assertEqual(self.libfiles(), [])
        self.lib('tag one2000 --add later')
        self.lib(f'history --revert {n}')
        self.assertEqual(self.libfiles(), [kept])  # from the history
        self.assertEqual(len(self.files('three2002')), 1)


class TestRevertShallow(FileTest):
    "a step that also wrote the pool: the revert acts on the library, and says how to revert the pool's step"

    def test_pool_line(self):
        self.papers('init pool')
        self.lib('config pool ../pool')
        Path(self.path('a.bib')).write_text(entry('one2000'))
        self.lib('add ../a.bib')
        project, place = papers.backup.project_of(Config.load(self.path('lib', CONFIG_FILE_LOCAL)), create=False)
        n = project.head(place)['state']
        pool_step = project.state(n)['pools']
        self.lib('tag one2000 --add later')
        out = self.out(f'history --revert {n}')
        step = next(iter(pool_step.values()))['state']
        self.assertIn(f'`papers -C ../pool history --revert {step}`', out)


if __name__ == '__main__':
    unittest.main()
