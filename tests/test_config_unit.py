"""Unit tests for papers.config (pure logic, no install)"""
import os
import tempfile
import unittest
from pathlib import Path

from papers.config import Config


class TestConfigRelpath(unittest.TestCase):

    def test_relpath_local(self):
        with tempfile.TemporaryDirectory() as d:
            bib = os.path.join(d, "lib.bib")
            open(bib, 'w').close()
            cfg = Config(file=os.path.join(d, ".papersconfig.json"), bibtex=bib, local=True)
            # Path under root -> relative
            sub = os.path.join(d, "sub", "file.pdf")
            os.makedirs(os.path.dirname(sub))
            result = cfg._relpath(sub)
            self.assertIn("sub", result)

    def test_relpath_none_returns_none(self):
        cfg = Config(local=True, bibtex="/tmp/x.bib")
        self.assertIsNone(cfg._relpath(None))

    def test_relpath_non_local_returns_abspath(self):
        cfg = Config(local=False, bibtex="/tmp/x.bib")
        result = cfg._relpath("/some/path/file.pdf")
        self.assertEqual(result, "/some/path/file.pdf")


class TestConfigEditor(unittest.TestCase):

    def test_editor_setter(self):
        old_editor = os.environ.get("EDITOR")
        try:
            cfg = Config(local=True, bibtex="/tmp/x.bib")
            cfg.editor = "vim"
            self.assertEqual(cfg.editor, "vim")
            self.assertEqual(os.environ.get("EDITOR"), "vim")
        finally:
            if old_editor is not None:
                os.environ["EDITOR"] = old_editor
            elif "EDITOR" in os.environ:
                del os.environ["EDITOR"]


class TestConfigBackupFiles(unittest.TestCase):

    def test_backupfile_properties(self):
        cfg = Config(local=True, bibtex="/tmp/x.bib", gitdir="/tmp/git")
        self.assertIn("backup_clean.bib", str(cfg.backupfile_clean))
        # the tracked backup copy is named after the bibtex itself
        self.assertEqual("x.bib", Path(cfg.backupfile).name)

    def test_backupfile_reserved_names(self):
        cfg = Config(local=True, bibtex="/tmp/backup_clean.bib", gitdir="/tmp/git")
        self.assertNotEqual(Path(cfg.backupfile).name, Path(cfg.backupfile_clean).name)
