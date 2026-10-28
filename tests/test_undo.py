"""papers undo, redo and restore through the history of the machine (see
papers.backup, papers.history): moving along the states, branches after an
undo, changes made outside papers, the messages, and a bibtex without
library"""
import os
from pathlib import Path

import papers.backup
from papers.bib import Biblio
from papers.config import CONFIG_FILE_LOCAL

from tests.common import BaseTest, InitTest

bibtex2 = """@article{SomeOneElse2000,
 author = {Some One},
 doi = {10.5194/xxxx},
 title = {Interesting Stuff},
 year = {2000}
}"""


class HistoryTest(InitTest):

    def head(self):
        "the number of the current state"
        project, place = papers.backup.project_of(self.config, create=False)
        return project.head(place)['state']

    def keys(self):
        return sorted(e.key for e in Biblio.load(self._path(self.mybib), '').entries)

    def out(self, cmd):
        return self.papers(cmd, sp_cmd='check_output')


class TestTimeTravel(HistoryTest):

    def test_undo_redo(self):
        self.papers(f'add {self.anotherbib}')
        first = self.head()
        self.papers('list --add-tag change')
        second = self.head()
        self.assertNotEqual(first, second)
        with_tag = Path(self._path(self.mybib)).read_text()

        self.papers('undo')
        self.assertEqual(self.head(), first)
        self.assertNotIn('change', Path(self._path(self.mybib)).read_text())
        self.papers('undo')
        self.assertEqual(self.keys(), [])
        self.papers('redo')
        self.assertEqual(self.head(), first)
        self.papers('redo')
        self.assertEqual(self.head(), second)
        self.assertEqual(Path(self._path(self.mybib)).read_text(), with_tag)  # byte for byte

        # beyond the last state, nothing changes
        self.assertRaises(Exception, lambda: self.papers('redo'))
        self.assertEqual(self.head(), second)

        self.papers('undo -n 2')
        self.assertEqual(self.keys(), [])
        self.papers('redo -n 2')
        self.assertEqual(self.head(), second)

        # a state by its number
        self.papers(f'restore {first}')
        self.assertEqual(self.head(), first)
        self.papers(f'restore --ref {second}')
        self.assertEqual(self.head(), second)

    def test_nothing_to_undo(self):
        with self.assertRaisesRegex(Exception, 'nothing to undo'):
            self.papers('undo')
        self.papers(f'add {self.anotherbib}')
        with self.assertRaisesRegex(Exception, 'only 1 step'):
            self.papers('undo -n 5')

    def test_undo_then_change_branches(self):
        # a change made after an undo starts a branch: the undone states stay in the history
        self.papers(f'add {self.anotherbib}')
        self.papers('list --add-tag change')
        undone = self.head()
        future_bib = Path(self._path(self.mybib)).read_text()
        self.papers('undo')
        self.papers('list --add-tag another')
        self.assertNotEqual(self.head(), undone)
        self.assertRaises(Exception, lambda: self.papers('redo'))  # a new line: nothing to redo
        self.papers(f'restore {undone}')  # across the branches
        self.assertEqual(Path(self._path(self.mybib)).read_text(), future_bib)
        self.papers('undo')
        self.assertNotIn('change', Path(self._path(self.mybib)).read_text())

    def test_unknown_state(self):
        self.papers(f'add {self.anotherbib}')
        with self.assertRaisesRegex(Exception, 'no step 99'):
            self.papers('restore 99')

    def test_dry_run(self):
        self.papers(f'add {self.anotherbib}')
        before = Path(self._path(self.mybib)).read_text()
        out = self.out('undo --dry-run')
        self.assertIn('DRYRUN: undo:', out)
        self.assertEqual(Path(self._path(self.mybib)).read_text(), before)


class TestOutsideChanges(HistoryTest):
    "a change made outside papers is recorded as a state of its own (#120)"

    def test_not_dropped_by_undo(self):
        self.papers(f'add {self.anotherbib}')
        text = Path(self._path(self.mybib)).read_text()
        Path(self._path(self.mybib)).write_text(text + '\n' + bibtex2)  # e.g. an editor
        Path(self._path('third.bib')).write_text(bibtex2.replace('SomeOneElse2000', 'third2001')
                                                 .replace('10.5194/xxxx', '10.5194/yyyy'))
        self.papers('add third.bib')
        self.assertIn('changed outside papers', self.out('history'))
        # undo of the add: what was on disk before it, with the outside change
        self.papers('undo')
        self.assertIn('SomeOneElse2000', self.keys())
        self.assertNotIn('third2001', self.keys())
        # once more: the change made outside papers
        self.papers('undo')
        self.assertNotIn('SomeOneElse2000', self.keys())
        self.papers('redo -n 2')
        self.assertIn('third2001', self.keys())

    def test_undo_right_after_an_outside_change(self):
        self.papers(f'add {self.anotherbib}')
        Path(self._path(self.mybib)).write_text(Path(self._path(self.mybib)).read_text() + '\n' + bibtex2)
        self.papers('undo')  # undoes the change made outside papers
        self.assertNotIn('SomeOneElse2000', self.keys())
        self.papers('redo')
        self.assertIn('SomeOneElse2000', self.keys())

    def test_restore_drops_the_outside_change(self):
        self.papers(f'add {self.anotherbib}')
        Path(self._path(self.mybib)).write_text('broken by hand')
        self.papers('restore')
        self.assertNotIn('broken', Path(self._path(self.mybib)).read_text())
        self.papers('redo')  # recorded: it can come back
        self.assertEqual(Path(self._path(self.mybib)).read_text(), 'broken by hand')
        self.papers('undo')
        with self.assertRaisesRegex(Exception, 'nothing to restore'):
            self.papers('restore')


class TestUndoMessages(HistoryTest):

    def test_undo_and_redo_say_what_they_restore(self):
        self.papers(f'add {self.anotherbib}')
        Path(self._path('si.pdf')).write_text('supplement')
        self.papers('file attach --move 10.5194/bg-8-515-2011 si.pdf')
        biblio = Biblio.load(self._path(self.mybib), '')
        attached = biblio.get_files(biblio.entries[0])[0]
        self.assertTrue(attached.startswith(self._path(self.filesdir)))

        out = self.out('undo')
        self.assertRegex(out.splitlines()[0], rf'^undo: {self.mybib} restored to \d+ papers add '
                                              rf'{self.anotherbib} \(\d{{4}}-\d\d-\d\d \d\d:\d\d\)$')
        # the file is moved back where it was (papers.journal)
        self.assertIn(' --> moved back to si.pdf', out)
        self.assertNotIn('linked by no entry', out)
        self.assertFalse(os.path.exists(attached))
        self.assertEqual(Path(self._path('si.pdf')).read_text(), 'supplement')

        out = self.out('redo')
        self.assertRegex(out, rf'^redo: {self.mybib} restored to \d+ papers file attach')
        self.assertIn('si.pdf --> moved to ', out)
        self.assertTrue(os.path.exists(attached))
        self.assertFalse(os.path.exists(self._path('si.pdf')))

        out = self.out('undo -n 2')
        self.assertIn(' --> moved back to si.pdf', out)
        self.assertFalse(os.path.exists(attached))
        self.assertEqual(Path(self._path('si.pdf')).read_text(), 'supplement')


class TestUndoNoInstall(BaseTest):
    "a bibtex without library: its history is named by its path"

    def test_undo(self):
        open(self._path(self.mybib), 'w').write('')
        opts = f'--bibtex {self.mybib} --files {self.filesdir}'

        def count():
            return len(Biblio.load(self._path(self.mybib), '').entries)
        self.papers(f'add {self.anotherbib} {opts}')
        self.assertEqual(count(), 1)
        open(self._path('yetanother'), 'w').write(bibtex2)
        self.papers(f'add yetanother {opts}')
        self.assertEqual(count(), 2)
        self.papers(f'undo {opts}')
        self.assertEqual(count(), 1)
        self.papers(f'undo {opts}')
        self.assertEqual(count(), 0)
        self.papers(f'redo {opts}')
        self.assertEqual(count(), 1)
        self.papers(f'redo {opts}')
        self.assertEqual(count(), 2)
        self.assertRaises(Exception, lambda: self.papers(f'redo {opts}'))
        self.assertFalse(os.path.exists(self._path(CONFIG_FILE_LOCAL)))
        self.assertFalse(os.path.exists(self._path('.papers')))  # nothing written next to the bibtex
