"""Unit tests for papers.cache"""
import json
import multiprocessing
import os
import tempfile
import time
import unittest

from papers.cache import cached, NOT_FOUND_TTL


class CacheTest(unittest.TestCase):
    """the cache writes one json file per key under papers.config.CACHE_DIR/<name>/"""

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

        @cached("doi")
        def fn(x):
            calls.append(x)
            return {"title": x}

        self.assertEqual(fn("10.1234/a/b:c"), {"title": "10.1234/a/b:c"})
        self.assertEqual(fn("10.1234/a/b:c"), {"title": "10.1234/a/b:c"})
        self.assertEqual(calls, ["10.1234/a/b:c"])
        self.assertTrue(os.path.isfile(os.path.join(self.tmp.name, "doi", "10.1234", "a%2Fb%3Ac.json")))

    def test_normalized_key(self):
        calls = []

        @cached("doi", normalize=str.lower)
        def fn(x):
            calls.append(x)
            return x

        self.assertEqual(fn("10.1234/ABC"), "10.1234/ABC")
        self.assertEqual(fn("10.1234/abc"), "10.1234/ABC")  # from the cache
        self.assertEqual(calls, ["10.1234/ABC"])  # called with the argument as given
        self.assertTrue(os.path.isfile(os.path.join(self.tmp.name, "doi", "10.1234", "abc.json")))

    def test_hashed_key_passes_the_argument(self):
        @cached("query", hashed_key=True)
        def fn(x):
            return x.upper()

        self.assertEqual(fn("some long text"), "SOME LONG TEXT")
        self.assertEqual(fn("some long text"), "SOME LONG TEXT")

    def test_corrupt_cache_file_is_ignored(self):
        file = os.path.join(self.tmp.name, "doi", "10.1234", "a.json")
        os.makedirs(os.path.dirname(file))
        open(file, "w").write("{corrupt json")

        @cached("doi")
        def fn(x):
            return x.upper()

        with self.assertLogs("papers", level="WARNING"):
            self.assertEqual(fn("10.1234/a"), "10.1234/A")
        self.assertEqual(json.load(open(file)), {"value": "10.1234/A"})

    def test_not_found_is_remembered_for_a_while(self):
        calls = []

        class NotFound(ValueError):
            pass

        @cached("doi", not_found=NotFound)
        def fn(x):
            calls.append(x)
            raise NotFound(x)

        for _ in range(2):
            with self.assertRaises(NotFound):
                fn("10.1234/a")
        self.assertEqual(len(calls), 1)

        # expired: asked again
        file = os.path.join(self.tmp.name, "doi", "10.1234", "a.json")
        json.dump({"not_found": time.time() - NOT_FOUND_TTL - 1}, open(file, "w"))
        with self.assertRaises(NotFound):
            fn("10.1234/a")
        self.assertEqual(len(calls), 2)

    def test_cached_not_found_shows_the_argument_as_given(self):
        # used to show the lower-cased cache key
        class NotFound(ValueError):
            pass

        @cached("doi", not_found=NotFound, normalize=str.lower)
        def fn(x):
            raise NotFound(x)

        with self.assertRaises(NotFound):
            fn("10.1234/ABC")
        with self.assertRaisesRegex(NotFound, r"^10\.1234/ABC: not found \(cached"):
            fn("10.1234/ABC")

    def test_other_errors_are_not_cached(self):
        calls = []

        @cached("doi", not_found=KeyError)
        def fn(x):
            calls.append(x)
            raise ValueError("network down")

        for _ in range(2):
            with self.assertRaises(ValueError):
                fn("10.1234/a")
        self.assertEqual(len(calls), 2)

    def test_trim(self):
        @cached("doi", trim=lambda r: {k: v for k, v in r.items() if k != "reference"})
        def fn(x):
            return {"title": "T", "reference": ["long", "list"]}

        self.assertEqual(fn("10.1234/a"), {"title": "T"})

    def test_legacy_cache_is_migrated(self):
        legacy = os.path.join(self.tmp.name, "crossref.json")
        json.dump({"10.1234/A": {"message": {"title": ["A"], "reference": [1]}},
                   "10.1234/b": {"message": {"title": ["B"]}},
                   "10.1234/drop": "garbage"}, open(legacy, "w"))
        migrate = lambda v: v["message"] if isinstance(v, dict) else None

        @cached("doi", legacy="crossref.json", migrate=migrate)
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

        @cached("concurrent")
        def fn(x):
            raise AssertionError("should be cached")

        for key in keys:
            self.assertEqual(fn(key), "value-" + key)


def _concurrent_cache_worker(cache_dir, key):
    import papers.config as pconfig
    pconfig.CACHE_DIR = cache_dir

    @cached("concurrent")
    def fn(x):
        time.sleep(0.2)
        return "value-" + x

    fn(key)
