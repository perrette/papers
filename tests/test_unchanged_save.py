"""A command that changes nothing does not write the bibtex nor add a state
to the history (papers.library.savebib, Biblio.unchanged)"""
import os
from pathlib import Path
from unittest.mock import patch

import papers.backup
from papers.bib import Biblio
from papers.config import Config, library_config_file

from tests.common import FileTest, entry


class TestUnchangedSave(FileTest):

    def setUp(self):
        super().setUp()
        self.bib(entry('one2000', doi='10.1000/one'), entry('two2000'))
        self.lib('tag one2000 --add first')  # the bibtex as papers writes it
        self.config = Config.load(library_config_file(self.path('lib')))
        os.utime(self.bibtex(), ns=(1, 1))

    def bibtex(self):
        return self.path('lib', 'papers.bib')

    def commits(self):
        "the number of states of the history of the library"
        project, _ = papers.backup.project_of(Config.load(library_config_file(self.path('lib'))), create=False)
        return len(project.states())

    def assertNotSaved(self, cmd):
        commits = self.commits()
        self.lib(cmd)
        self.assertEqual(os.stat(self.bibtex()).st_mtime_ns, 1)
        self.assertEqual(self.commits(), commits)

    def assertSaved(self, cmd):
        commits = self.commits()
        self.lib(cmd)
        self.assertNotEqual(os.stat(self.bibtex()).st_mtime_ns, 1)
        self.assertEqual(self.commits(), commits + 1)

    def test_check_without_duplicates(self):
        self.assertNotSaved('check --duplicates --on-duplicate skip')

    def test_add_skipped_duplicate(self):
        dup = self.write('dup.bib', content=entry('other2000', doi='10.1000/one'))
        with patch('papers.bib.fetch_bibtex_by_doi', side_effect=AssertionError('no network query')):
            self.assertNotSaved(f'add {dup} --on-duplicate skip')
        self.assertEqual(sorted(e.key for e in Biblio.load(self.bibtex(), '').entries), ['one2000', 'two2000'])

    def test_tag_already_there(self):
        self.assertNotSaved('tag one2000 --add first')

    def test_change_is_saved(self):
        self.assertSaved('tag two2000 --add second')

    def test_key_case_is_a_change(self):
        editor = self.write('bin', 'editor.sh', content="#!/bin/sh\nsed -i 's/{two2000,/{Two2000,/' \"$1\"\n")
        os.chmod(editor, 0o755)
        with patch.dict(os.environ, {'VISUAL': editor, 'EDITOR': editor}):
            self.assertSaved('edit two2000')

    def test_converted_links_are_saved(self):
        "the file links converted at load (`paths` setting) are written, although the command changes nothing"
        self.write('lib', 'files', 'one.pdf')
        text = Path(self.bibtex()).read_text().replace('@article{two2000,', '@article{two2000,\n file = {:files/one.pdf:pdf},')
        Path(self.bibtex()).write_text(text)
        os.utime(self.bibtex(), ns=(1, 1))
        self.lib('config paths absolute')
        self.assertIn(self.path('lib', 'files', 'one.pdf'), Path(self.bibtex()).read_text())
