"""Unit tests for papers.config (pure logic, no install)"""
import os
import tempfile
import unittest

from papers.config import Config, CONFIG_FILE_LOCAL


class TestConfigRoot(unittest.TestCase):

    def test_root_non_local_returns_sep(self):
        """When local=False, root is Path('/')"""
        cfg = Config(local=False, bibtex="/tmp/x.bib")
        self.assertEqual(cfg.root, __import__('pathlib').Path(os.path.sep))

    def test_root_local_with_bibtex(self):
        """When local=True and bibtex set, root is parent of bibtex"""
        with tempfile.NamedTemporaryFile(suffix='.bib', delete=False) as f:
            path = f.name
        try:
            cfg = Config(local=True, bibtex=path)
            expected = __import__('pathlib').Path(path).parent.resolve()
            self.assertEqual(cfg.root, expected)
        finally:
            os.unlink(path)


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
        self.assertIn("backup_copy.bib", str(cfg.backupfile))


class TestConfigCollections(unittest.TestCase):

    def test_collections(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "lib.bib"), 'w').close()
            open(os.path.join(d, "other.bib"), 'w').close()
            open(os.path.join(d, "readme.txt"), 'w').close()
            cfg = Config(local=True, bibtex=os.path.join(d, "lib.bib"))
            colls = cfg.collections()
            self.assertIn("lib.bib", colls)
            self.assertIn("other.bib", colls)
            self.assertEqual(len(colls), 2)
