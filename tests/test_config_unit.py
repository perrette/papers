"""Unit tests for papers.config (pure logic, no install)"""
import json
import os
import tempfile
import unittest
from unittest import mock

from papers.config import Config, CONFIG_FILE_LOCAL, MachineConfig


class TestConfigRelpath(unittest.TestCase):

    def test_relpath_local(self):
        with tempfile.TemporaryDirectory() as d:
            bib = os.path.join(d, "lib.bib")
            open(bib, 'w').close()
            cfg = Config(file=os.path.join(d, CONFIG_FILE_LOCAL), bibtex=bib, is_library=True)
            # Path under root -> relative
            sub = os.path.join(d, "sub", "file.pdf")
            os.makedirs(os.path.dirname(sub))
            result = cfg._relpath(sub)
            self.assertIn("sub", result)

    def test_relpath_none_returns_none(self):
        cfg = Config(is_library=True, bibtex="/tmp/x.bib")
        self.assertIsNone(cfg._relpath(None))

    def test_relpath_non_local_returns_abspath(self):
        cfg = Config(is_library=False, bibtex="/tmp/x.bib")
        result = cfg._relpath("/some/path/file.pdf")
        self.assertEqual(result, "/some/path/file.pdf")


class TestConfigEditor(unittest.TestCase):

    def test_editor_setter(self):
        # the editor setting is handed to utils.edit_text, the environment is left alone
        with mock.patch.dict(os.environ, {"EDITOR": "nano"}):
            cfg = Config(is_library=True, bibtex="/tmp/x.bib")
            cfg.editor = "vim"
            self.assertEqual(cfg.editor, "vim")
            self.assertEqual(os.environ.get("EDITOR"), "nano")


class TestLibraryId(unittest.TestCase):
    "the identifier of a library names its history (see papers.backup)"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.tmp.name, CONFIG_FILE_LOCAL)
        os.makedirs(os.path.dirname(self.file))
        self.machine = MachineConfig(os.path.join(self.tmp.name, 'machine.json'))

    def tearDown(self):
        self.tmp.cleanup()

    def test_created_once_and_kept(self):
        json.dump({'bibtex': 'lib.bib', 'version': 3}, open(self.file, 'w'))
        config = Config.load(self.file, machine=self.machine)
        self.assertIsNone(config.library_id(create=False))
        id = config.library_id()
        self.assertRegex(id, r'^[0-9a-f]{32}$')
        self.assertEqual(json.load(open(self.file))['id'], id)
        self.assertEqual(Config.load(self.file, machine=self.machine).library_id(), id)

    def test_invalid_id_ignored(self):
        for bad in ('../../somewhere', 'a/b', '', 12):
            json.dump({'bibtex': 'lib.bib', 'version': 3, 'id': bad}, open(self.file, 'w'))
            config = Config.load(self.file, machine=self.machine)
            self.assertIsNone(config.library_id(create=False))
            self.assertRegex(config.library_id(), r'^[0-9a-f]{32}$')  # a new one, written over it

    def test_only_the_id_is_written(self):
        # the settings in memory may be those of the command (e.g. the files directory of a pool)
        json.dump({'bibtex': 'lib.bib', 'version': 3}, open(self.file, 'w'))
        config = Config.load(self.file, machine=self.machine)
        config.filesdir = '/somewhere/else'
        config.library_id()
        self.assertEqual(set(json.load(open(self.file))), {'bibtex', 'version', 'id'})

    def test_machine_settings_not_read_from_a_library(self):
        json.dump({'bibtex': 'lib.bib', 'version': 3, 'history-dir': '/tmp/evil', 'keep-deleted-files': False,
                   'history-separate': True, 'history-size': 7}, open(self.file, 'w'))
        config = Config.load(self.file, machine=self.machine)
        self.assertIsNone(config.history_dir)
        self.assertTrue(config.keep_deleted_files)
        # a library may keep a history of its own, of its own size
        self.assertTrue(config.history_separate)
        self.assertEqual(config.history_size, 7)
        js = config.tojson()
        self.assertNotIn('history-dir', js)
        self.assertNotIn('keep-deleted-files', js)
