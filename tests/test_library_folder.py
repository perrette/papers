"""The files of .papers/ (distinct.json, origin/) are in the library folder,
the folder of .papers/config.json, also when the bibtex is in another folder;
those that earlier v3 builds wrote next to the bibtex are moved there."""
import json
import os
from pathlib import Path
from unittest.mock import patch

from papers.config import Config
from papers.duplicate import DISTINCT_FILE
from papers.pools import ORIGIN_DIR

from tests.common import ConfigTest


NEW_BIB = """@article{mine2022,
 author = {Mine, Me},
 doi = {10.1000/mine},
 title = {My own paper},
 year = {2022}
}
"""

# the same DOI, another title: a duplicate to answer "not the same paper"
DUP_BIB = """@article{other2022,
 author = {Other, An},
 doi = {10.1000/mine},
 title = {Another paper},
 year = {2022}
}
"""

DISTINCT = '{"distinct": []}\n'


class LibraryFolderTest(ConfigTest):
    "a library in lib/ whose bibtex is lib/bib/papers.bib"

    def setUp(self):
        super().setUp()
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('dup.bib')).write_text(DUP_BIB)

    def lib(self, cmd, answers=()):
        with patch('builtins.input', side_effect=list(answers)):
            return self.papers(cmd, cwd=self.path('lib'))

    def test_origin_in_library_folder(self):
        self.papers('init pool')
        self.papers('init lib --pool ../pool --bibtex bib/papers.bib')
        self.lib('add ../new.bib')
        self.assertTrue(os.listdir(self.path('lib', ORIGIN_DIR)))
        self.assertFalse(os.path.exists(self.path('lib', 'bib', '.papers')))

    def test_distinct_in_library_folder(self):
        self.papers('init lib --bibtex bib/papers.bib')
        self.lib('add ../new.bib')
        self.lib('add ../dup.bib --on-duplicate ask', answers=['n'])
        self.assertTrue(os.path.isfile(self.path('lib', DISTINCT_FILE)))
        self.assertFalse(os.path.exists(self.path('lib', 'bib', '.papers')))
        # the history keeps distinct.json of the library folder
        self.lib('undo')
        self.assertFalse(os.path.exists(self.path('lib', DISTINCT_FILE)))
        self.lib('redo')
        self.assertTrue(os.path.isfile(self.path('lib', DISTINCT_FILE)))

    def test_move_from_bibtex_folder(self):
        self.papers('init lib --bibtex bib/papers.bib')
        old = self.path('lib', 'bib', '.papers')
        os.makedirs(os.path.join(old, 'origin'))
        Path(old, 'distinct.json').write_text(DISTINCT)
        Path(old, 'origin', 'pool.bib').write_text('')
        with self.assertLogs('papers', 'INFO') as logs:
            self.lib('list')
        self.assertEqual(len([line for line in logs.output if 'moved' in line]), 1)
        self.assertEqual(Path(self.path('lib', DISTINCT_FILE)).read_text(), DISTINCT)
        self.assertTrue(os.path.isfile(self.path('lib', ORIGIN_DIR, 'pool.bib')))
        self.assertFalse(os.path.exists(os.path.join(old, 'distinct.json')))
        self.assertFalse(os.path.exists(os.path.join(old, 'origin')))

    def test_no_move_over_existing_file(self):
        self.papers('init lib --bibtex bib/papers.bib')
        os.makedirs(self.path('lib', 'bib', '.papers'))
        Path(self.path('lib', 'bib', DISTINCT_FILE)).write_text('{"distinct": [[{}, {}]]}\n')
        Path(self.path('lib', DISTINCT_FILE)).write_text(DISTINCT)
        self.lib('list')
        self.assertEqual(Path(self.path('lib', DISTINCT_FILE)).read_text(), DISTINCT)
        self.assertTrue(os.path.exists(self.path('lib', 'bib', DISTINCT_FILE)))

    def test_undo_across_the_move(self):
        self.papers('init lib --bibtex bib/papers.bib')
        self.lib('add ../new.bib')
        # a step recorded by an earlier build: distinct.json next to the bibtex
        bibdir = self.path('lib', 'bib')
        with patch.object(Config, 'libdir', property(lambda self: bibdir)):
            self.lib('add ../dup.bib --on-duplicate ask', answers=['n'])
        self.assertTrue(os.path.isfile(os.path.join(bibdir, DISTINCT_FILE)))
        self.lib('list')  # moved to the library folder
        self.assertFalse(os.path.exists(os.path.join(bibdir, DISTINCT_FILE)))
        moved = Path(self.path('lib', DISTINCT_FILE)).read_text()
        self.lib('undo')
        self.assertFalse(os.path.exists(self.path('lib', DISTINCT_FILE)))
        self.lib('redo')
        self.assertEqual(Path(self.path('lib', DISTINCT_FILE)).read_text(), moved)
        self.assertFalse(os.path.exists(os.path.join(bibdir, DISTINCT_FILE)))

    def test_other_library_left_alone(self):
        # lib/ uses the bibtex of the library other/, which has its own distinct.json
        self.papers('init other')
        Path(self.path('other', DISTINCT_FILE)).write_text(DISTINCT)
        os.makedirs(self.path('lib', '.papers'))
        Path(self.path('lib', '.papers', 'config.json')).write_text(
            json.dumps({'bibtex': '../other/papers.bib', 'filesdir': 'files', 'version': 3}))
        self.lib('list')
        self.assertEqual(Path(self.path('other', DISTINCT_FILE)).read_text(), DISTINCT)
        self.assertFalse(os.path.exists(self.path('lib', DISTINCT_FILE)))
