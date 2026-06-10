"""Unit tests for papers.config (pure logic, no install)"""
import json
import multiprocessing
import os
import tempfile
import time
import unittest
from pathlib import Path

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
        # the tracked backup copy is named after the bibtex itself
        self.assertEqual("x.bib", Path(cfg.backupfile).name)

    def test_backupfile_reserved_names(self):
        cfg = Config(local=True, bibtex="/tmp/backup_clean.bib", gitdir="/tmp/git")
        self.assertNotEqual(Path(cfg.backupfile).name, Path(cfg.backupfile_clean).name)


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


class TestCachedCorruptFile(unittest.TestCase):

    def test_corrupt_cache_file_is_ignored(self):
        # a corrupt cache file used to crash every cached query
        import papers.config as pconfig
        with tempfile.TemporaryDirectory() as d:
            old_cache_dir = pconfig.CACHE_DIR
            pconfig.CACHE_DIR = d
            try:
                open(os.path.join(d, "testcache.json"), "w").write("{corrupt json")

                @pconfig.cached("testcache.json")
                def fn(x):
                    return x.upper()

                self.assertEqual(fn("a"), "A")
            finally:
                pconfig.CACHE_DIR = old_cache_dir


def _concurrent_cache_worker(cache_dir, key):
    # runs in a child process: each process holds its own in-memory cache
    import papers.config as pconfig
    pconfig.CACHE_DIR = cache_dir

    @pconfig.cached("concurrent.json")
    def fn(x):
        # widen the window between cache load and cache write
        time.sleep(0.2)
        return "value-" + x

    fn(key)


class TestCachedConcurrency(unittest.TestCase):

    def test_concurrent_writers_keep_all_keys(self):
        # several processes writing in parallel must not clobber each other
        keys = ["doi%d" % i for i in range(4)]
        with tempfile.TemporaryDirectory() as d:
            procs = [multiprocessing.Process(target=_concurrent_cache_worker, args=(d, key))
                     for key in keys]
            for p in procs:
                p.start()
            for p in procs:
                p.join()
            cache = json.load(open(os.path.join(d, "concurrent.json")))
            for key in keys:
                self.assertEqual(cache.get(key), "value-" + key)

    def test_write_merges_with_file_content(self):
        # a write must merge with entries another process added meanwhile
        import papers.config as pconfig
        with tempfile.TemporaryDirectory() as d:
            old_cache_dir = pconfig.CACHE_DIR
            pconfig.CACHE_DIR = d
            try:
                file = os.path.join(d, "merge.json")

                @pconfig.cached("merge.json")
                def fn(x):
                    # while we compute, another process writes its own entry
                    json.dump({"other": "OTHER"}, open(file, "w"))
                    return x.upper()

                self.assertEqual(fn("a"), "A")
                cache = json.load(open(file))
                self.assertEqual(cache.get("a"), "A")
                self.assertEqual(cache.get("other"), "OTHER")
            finally:
                pconfig.CACHE_DIR = old_cache_dir

    def test_in_memory_values_win_on_merge(self):
        # for keys present both in memory and on disk, ours win
        import papers.config as pconfig
        with tempfile.TemporaryDirectory() as d:
            old_cache_dir = pconfig.CACHE_DIR
            pconfig.CACHE_DIR = d
            try:
                file = os.path.join(d, "winner.json")

                @pconfig.cached("winner.json")
                def fn(x):
                    json.dump({"a": "stale"}, open(file, "w"))
                    return x.upper()

                self.assertEqual(fn("a"), "A")
                cache = json.load(open(file))
                self.assertEqual(cache["a"], "A")
            finally:
                pconfig.CACHE_DIR = old_cache_dir

    def test_write_is_atomic_replace(self):
        # no partial state is ever visible at the cache path: writes go to a
        # temp file and are renamed over; the temp file does not linger
        import papers.config as pconfig
        with tempfile.TemporaryDirectory() as d:
            old_cache_dir = pconfig.CACHE_DIR
            pconfig.CACHE_DIR = d
            try:
                @pconfig.cached("atomic.json")
                def fn(x):
                    return x.upper()

                fn("a")
                files = os.listdir(d)
                self.assertIn("atomic.json", files)
                self.assertFalse([f for f in files if f.endswith(".tmp")])
            finally:
                pconfig.CACHE_DIR = old_cache_dir
