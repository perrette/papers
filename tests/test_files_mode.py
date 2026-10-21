"""What `add` does with a file: the `files` setting (move, copy, link) and
its command-line overrides"""
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path

import papers.config
from papers.config import Config, MachineConfig
from papers.bib import Biblio
from papers.utils import PapersExit

from tests.common import ConfigTest


def bib_with_file(key, file):
    return f"""@article{{{key},
 author = {{Some One}},
 file = {{:{file}:pdf}},
 title = {{Title of {key}}},
 year = {{2000}}
}}
"""


class FilesModeTest(ConfigTest):
    """a library in lib/, and files to add in src/"""

    def setUp(self):
        super().setUp()
        os.makedirs(self.path('lib'))
        os.makedirs(self.path('src'))
        self.lib('init --no-git')
        self.pdf = self.path('src', 'a.pdf')
        Path(self.pdf).write_text('pdf a')
        Path(self.path('src', 'a.bib')).write_text(bib_with_file('one2000', self.pdf))

    def lib(self, cmd, **kw):
        return self.papers(cmd, cwd=self.path('lib'), **kw)

    def unset_machine_files(self):
        "the per-machine configuration of the tests sets files to link: remove it"
        machine = MachineConfig.load()
        machine.set('files', None)
        machine.save()

    def files(self, key='one2000'):
        biblio = Biblio.load(self.path('lib', 'papers.bib'), '')
        e = next(e for e in biblio.entries if e.key == key)
        return biblio.get_files(e)

    def moved_name(self):
        files = os.listdir(self.path('lib', 'files'))
        self.assertEqual(len(files), 1, files)
        return self.path('lib', 'files', files[0])


class TestSetting(FilesModeTest):

    def test_default_is_move(self):
        self.assertEqual(papers.config.default_value('files'), 'move')
        self.unset_machine_files()
        self.assertEqual(self.lib('config files', sp_cmd='check_output'), 'move')
        self.lib('add ../src/a.bib')
        self.assertFalse(os.path.exists(self.pdf))
        self.assertEqual(self.files(), [self.moved_name()])

    def test_machine_then_library(self):
        self.assertEqual(self.lib('config files', sp_cmd='check_output'), 'link')  # tests/__init__.py
        self.lib('config files copy')
        self.assertEqual(json.load(open(self.path('lib', '.papersconfig.json')))['files'], 'copy')
        config = Config.load(self.path('lib', '.papersconfig.json'))
        self.assertEqual(config.source('files'), 'library')
        self.lib('config --unset files')
        self.assertEqual(self.lib('config files', sp_cmd='check_output'), 'link')

    def test_invalid(self):
        with self.assertRaises(PapersExit):
            self.lib('config files delete')


class TestModes(FilesModeTest):

    def test_move(self):
        self.lib('config files move')
        self.lib('add ../src/a.bib')
        self.assertFalse(os.path.exists(self.pdf))
        new = self.moved_name()
        self.assertEqual(Path(new).read_text(), 'pdf a')
        self.assertEqual(self.files(), [new])

    def test_copy_is_hard_link(self):
        self.lib('config files copy')
        self.lib('add ../src/a.bib')
        self.assertTrue(os.path.exists(self.pdf))
        new = self.moved_name()
        self.assertEqual(self.files(), [new])
        self.assertEqual(os.stat(new).st_ino, os.stat(self.pdf).st_ino)

    def test_copy_without_hard_link(self):
        # e.g. the files directory is on another file system
        from unittest import mock
        self.lib('config files copy')
        with mock.patch('os.link', side_effect=OSError('Invalid cross-device link')):
            self.lib('add ../src/a.bib')
        self.assertTrue(os.path.exists(self.pdf))
        new = self.moved_name()
        self.assertEqual(self.files(), [new])
        self.assertNotEqual(os.stat(new).st_ino, os.stat(self.pdf).st_ino)
        self.assertEqual(Path(new).read_text(), 'pdf a')

    def test_link(self):
        self.lib('config files link')
        self.lib('add ../src/a.bib')
        self.assertEqual(os.listdir(self.path('lib', 'files')), [])
        self.assertEqual(self.files(), [self.pdf])

    def test_options_override_setting(self):
        self.lib('config files move')
        self.lib('add --link ../src/a.bib')
        self.assertEqual(self.files(), [self.pdf])

    def test_copy_option(self):
        self.lib('config files link')
        self.lib('add --copy ../src/a.bib')
        self.assertTrue(os.path.exists(self.pdf))
        self.assertEqual(self.files(), [self.moved_name()])
        self.lib('add -c ../src/a.bib')  # same entry again: nothing changes
        self.assertEqual(self.files(), [self.moved_name()])

    def test_rename_is_move(self):
        self.lib('config files link')
        self.lib('add -r ../src/a.bib')
        self.assertFalse(os.path.exists(self.pdf))
        self.assertEqual(self.files(), [self.moved_name()])

    def test_move_option(self):
        self.lib('config files copy')
        self.lib('add --move ../src/a.bib')
        self.assertFalse(os.path.exists(self.pdf))

    def test_link_excludes_move(self):
        with self.assertRaises(PapersExit):
            self.lib('add --link -r ../src/a.bib')

    def test_directory(self):
        self.lib('config files move')
        self.lib('add --recursive ../src')
        self.assertFalse(os.path.exists(self.pdf))
        self.assertEqual(self.files(), [self.moved_name()])


class TestAttach(FilesModeTest):

    def test_attach(self):
        self.lib('config files move')
        self.lib(f'add --key two2000 --title Two --author "Two, T." --year 2000 --attach {self.pdf}')
        self.assertFalse(os.path.exists(self.pdf))
        self.assertEqual(self.files('two2000'), [self.moved_name()])

    def test_attachment_deprecated(self):
        self.lib('config files link')
        self.lib(f'add --key two2000 --title Two --attachment {self.pdf}')
        self.assertEqual(self.files('two2000'), [self.pdf])

    def test_a_is_free(self):
        with self.assertRaises(SystemExit):
            self.lib(f'add --key two2000 --title Two -a {self.pdf}')


class TestOtherLibrary(FilesModeTest):
    """a file inside the files directory of another library is never moved"""

    def setUp(self):
        super().setUp()
        os.makedirs(self.path('other'))
        self.papers('init --no-git', cwd=self.path('other'))
        os.makedirs(self.path('other', 'files'), exist_ok=True)
        self.other_pdf = self.path('other', 'files', 'b.pdf')
        Path(self.other_pdf).write_text('pdf b')
        Path(self.path('other', 'papers.bib')).write_text(bib_with_file('two2000', 'files/b.pdf'))

    def test_move_falls_back_to_copy(self):
        self.lib('config files move')
        out = io.StringIO()
        with redirect_stdout(out):
            self.lib('add ../other/papers.bib')
        self.assertIn('copied, not moved', out.getvalue())
        self.assertTrue(os.path.exists(self.other_pdf))
        new = self.moved_name()
        self.assertEqual(self.files('two2000'), [new])
        self.assertEqual(Path(new).read_text(), 'pdf b')

    def test_rename_option_too(self):
        self.lib('config files link')
        self.lib('add -r ../other/papers.bib')
        self.assertTrue(os.path.exists(self.other_pdf))
        self.assertEqual(len(os.listdir(self.path('lib', 'files'))), 1)

    def test_outside_files_directory_is_moved(self):
        # a file of the other library's folder, but outside its files directory
        Path(self.path('other', 'c.pdf')).write_text('pdf c')
        Path(self.path('src', 'c.bib')).write_text(bib_with_file('three2000', self.path('other', 'c.pdf')))
        self.lib('config files move')
        self.lib('add ../src/c.bib')
        self.assertFalse(os.path.exists(self.path('other', 'c.pdf')))

    def test_own_files_directory_is_not_other(self):
        # the current library's own files are renamed, also in copy mode
        Path(self.path('lib', 'files', 'x.pdf')).write_text('pdf x')
        Path(self.path('src', 'x.bib')).write_text(bib_with_file('four2000', self.path('lib', 'files', 'x.pdf')))
        self.lib('config files copy')
        self.lib('add ../src/x.bib')
        self.assertFalse(os.path.exists(self.path('lib', 'files', 'x.pdf')))
        self.assertEqual(self.files('four2000'), [self.moved_name()])
