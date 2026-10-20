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


class CacheTest(unittest.TestCase):
    """the cache writes one json file per key under CACHE_DIR/<name>/"""

    def setUp(self):
        import papers.config as pconfig
        self.pconfig = pconfig
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cache_dir = pconfig.CACHE_DIR
        pconfig.CACHE_DIR = self.tmp.name

    def tearDown(self):
        self.pconfig.CACHE_DIR = self.old_cache_dir
        self.tmp.cleanup()

    def test_one_file_per_doi(self):
        calls = []

        @self.pconfig.cached("doi")
        def fn(x):
            calls.append(x)
            return {"title": x}

        self.assertEqual(fn("10.1234/a/b:c"), {"title": "10.1234/a/b:c"})
        self.assertEqual(fn("10.1234/a/b:c"), {"title": "10.1234/a/b:c"})
        self.assertEqual(calls, ["10.1234/a/b:c"])
        self.assertTrue(os.path.isfile(os.path.join(self.tmp.name, "doi", "10.1234", "a%2Fb%3Ac.json")))

    def test_hashed_key_passes_the_argument(self):
        @self.pconfig.cached("query", hashed_key=True)
        def fn(x):
            return x.upper()

        self.assertEqual(fn("some long text"), "SOME LONG TEXT")
        self.assertEqual(fn("some long text"), "SOME LONG TEXT")

    def test_corrupt_cache_file_is_ignored(self):
        file = os.path.join(self.tmp.name, "doi", "10.1234", "a.json")
        os.makedirs(os.path.dirname(file))
        open(file, "w").write("{corrupt json")

        @self.pconfig.cached("doi")
        def fn(x):
            return x.upper()

        with self.assertLogs("papers", level="WARNING"):
            self.assertEqual(fn("10.1234/a"), "10.1234/A")
        self.assertEqual(json.load(open(file)), {"value": "10.1234/A"})

    def test_not_found_is_remembered_for_a_while(self):
        calls = []

        class NotFound(ValueError):
            pass

        @self.pconfig.cached("doi", not_found=NotFound)
        def fn(x):
            calls.append(x)
            raise NotFound(x)

        for _ in range(2):
            with self.assertRaises(NotFound):
                fn("10.1234/a")
        self.assertEqual(len(calls), 1)

        # expired: asked again
        file = os.path.join(self.tmp.name, "doi", "10.1234", "a.json")
        json.dump({"not_found": time.time() - self.pconfig.NOT_FOUND_TTL - 1}, open(file, "w"))
        with self.assertRaises(NotFound):
            fn("10.1234/a")
        self.assertEqual(len(calls), 2)

    def test_other_errors_are_not_cached(self):
        calls = []

        @self.pconfig.cached("doi", not_found=KeyError)
        def fn(x):
            calls.append(x)
            raise ValueError("network down")

        for _ in range(2):
            with self.assertRaises(ValueError):
                fn("10.1234/a")
        self.assertEqual(len(calls), 2)

    def test_trim(self):
        @self.pconfig.cached("doi", trim=lambda r: {k: v for k, v in r.items() if k != "reference"})
        def fn(x):
            return {"title": "T", "reference": ["long", "list"]}

        self.assertEqual(fn("10.1234/a"), {"title": "T"})

    def test_legacy_cache_is_migrated(self):
        legacy = os.path.join(self.tmp.name, "crossref.json")
        json.dump({"10.1234/A": {"message": {"title": ["A"], "reference": [1]}},
                   "10.1234/b": {"message": {"title": ["B"]}},
                   "10.1234/drop": "garbage"}, open(legacy, "w"))
        migrate = lambda v: v["message"] if isinstance(v, dict) else None

        @self.pconfig.cached("doi", legacy="crossref.json", migrate=migrate)
        def fn(x):
            raise AssertionError("should come from the migrated cache")

        self.assertEqual(fn("10.1234/a"), {"title": ["A"], "reference": [1]})  # keys lower-cased
        self.assertEqual(fn("10.1234/b"), {"title": ["B"]})
        self.assertFalse(os.path.exists(legacy))
        self.assertTrue(os.path.exists(legacy + ".bak"))
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "doi", "10.1234", "drop.json")))

    def test_concurrent_writers_keep_all_keys(self):
        # several processes writing in parallel must not clobber each other
        keys = ["10.1234/doi%d" % i for i in range(4)]
        procs = [multiprocessing.Process(target=_concurrent_cache_worker, args=(self.tmp.name, key))
                 for key in keys]
        for p in procs:
            p.start()
        for p in procs:
            p.join()

        @self.pconfig.cached("concurrent")
        def fn(x):
            raise AssertionError("should be cached")

        for key in keys:
            self.assertEqual(fn(key), "value-" + key)


def _concurrent_cache_worker(cache_dir, key):
    import papers.config as pconfig
    pconfig.CACHE_DIR = cache_dir

    @pconfig.cached("concurrent")
    def fn(x):
        time.sleep(0.2)
        return "value-" + x

    fn(key)
