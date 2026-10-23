"""The Added/Modified/Removed/Existing lines that the commands print
(papers.cli.common._print_biblio_diff), from the entries as loaded"""
import os
import re
from unittest.mock import patch

from tests.common import FileTest, entry

ANSI = re.compile(r'\x1b\[[0-9;]*m|\x1b\]8;;[^\x1b]*\x1b\\')


class TestDiffReport(FileTest):

    def setUp(self):
        super().setUp()
        self.write('lib', 'files', 'one.pdf')
        self.bib(entry('one2000', 'files/one.pdf'), entry('two2000'), entry('three2000'))

    def report(self, cmd):
        "the lines of the changes (prefix and key)"
        out = ANSI.sub('', self.out(cmd))
        return [m.group(1) + ' ' + m.group(2) for m in re.finditer(r'(\w+) -> (\S+?):', out)]

    def test_tag(self):
        self.assertEqual(self.report('tag one2000 two2000 --add foo'), ['Modified one2000', 'Modified two2000'])
        self.assertEqual(self.report('tag one2000 two2000 --add foo'), [])  # nothing changed

    def test_rm(self):
        self.assertEqual(self.report('rm two2000 --keep-files'), ['Removed two2000'])

    def test_rm_shows_files_as_loaded(self):
        out = ANSI.sub('', self.out('rm one2000 --keep-files'))
        self.assertIn('Removed -> one2000: Title of one2000 (file:1)', out)

    def test_add(self):
        new = self.write('new.bib', content=entry('four2000') + entry('one2000'))
        self.assertEqual(self.report(f'add {new}'), ['Added four2000', 'Existing one2000'])

    def test_add_modifies(self):
        new = self.write('new.bib', content=entry('one2000').replace('year', 'note = {More},\n year'))
        self.assertEqual(self.report(f'add {new} --on-duplicate keep'), ['Modified one2000'])

    def test_edit_key(self):
        editor = self.write('bin', 'editor.sh', content="#!/bin/sh\nsed -i 's/{two2000,/{deux2000,/' \"$1\"\n")
        os.chmod(editor, 0o755)
        with patch.dict(os.environ, {'VISUAL': editor, 'EDITOR': editor}):
            self.assertEqual(self.report('edit two2000'), ['Removed two2000', 'Added deux2000'])

    def test_list_add_keywords(self):
        self.assertEqual(self.report('list --key three2000 --add-keywords bar'), ['Modified three2000'])

    def test_list_without_action(self):
        out = ANSI.sub('', self.out('list'))
        self.assertEqual(len(out.strip().splitlines()), 3)
        self.assertNotIn(' -> ', out)

    def test_file_attach(self):
        pdf = self.write('other.pdf')
        self.assertEqual(self.report(f'file attach three2000 {pdf} --link'), ['Modified three2000'])

    def test_file_rename(self):
        self.assertEqual(self.report('file rename one2000'), ['Modified one2000'])
