"""Unit tests for papers.config (pure logic, no install)"""
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from papers.config import Config, CONFIG_FILE_LOCAL


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


class TestConfigBackupFiles(unittest.TestCase):

    def test_backupfile_properties(self):
        cfg = Config(is_library=True, bibtex="/tmp/x.bib", gitdir="/tmp/git")
        self.assertIn("backup_clean.bib", str(cfg.backupfile_clean))
        # the tracked backup copy is named after the bibtex itself
        self.assertEqual("x.bib", Path(cfg.backupfile).name)

    def test_backupfile_reserved_names(self):
        cfg = Config(is_library=True, bibtex="/tmp/backup_clean.bib", gitdir="/tmp/git")
        self.assertNotEqual(Path(cfg.backupfile).name, Path(cfg.backupfile_clean).name)
