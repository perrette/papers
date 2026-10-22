"""pyflakes finds no unused import or name in papers/"""
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

    def test_papers(self):
        out = io.StringIO()
        n = api.checkRecursive([os.path.dirname(papers.__file__)], reporter.Reporter(out, out))
        self.assertEqual(n, 0, out.getvalue())
