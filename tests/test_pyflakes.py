"""pyflakes finds no unused import or name in papers/ and tests/"""
import io
import os
import unittest

import papers

try:
    from pyflakes import api, reporter
except ImportError:  # not a dependency of papers (see the tox deps)
    api = None


@unittest.skipIf(api is None, 'pyflakes is not installed')
class TestPyflakes(unittest.TestCase):

    def check(self, path):
        out = io.StringIO()
        n = api.checkRecursive([path], reporter.Reporter(out, out))
        self.assertEqual(n, 0, out.getvalue())

    def test_papers(self):
        self.check(os.path.dirname(papers.__file__))

    def test_tests(self):
        self.check(os.path.dirname(os.path.abspath(__file__)))
