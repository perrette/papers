"""--dry-run writes nothing: not the library, not its pool (not even the
global pool that does not exist yet), not the backup"""
import os
from pathlib import Path

from papers.config import DATA_DIR

from tests import TEST_DEFAULT_LIBRARY
from tests.common import ConfigTest
from tests.test_pools import NEW_BIB


def snapshot(*dirs):
    "path -> (modification time, size) of the files and directories under dirs"
    state = {}
    for d in dirs:
        if not os.path.exists(d):
            continue
        state[d] = None  # a directory that exists
        for root, dirnames, filenames in os.walk(d):
            for name in dirnames + filenames:
                p = os.path.join(root, name)
                st = os.lstat(p)
                state[p] = (st.st_mtime_ns, st.st_size)
    return state


class DryRunTest(ConfigTest):

    def lib(self, cmd, **kw):
        return self.papers(cmd, cwd=self.path('lib'), **kw)

    def assertNoWrites(self, cmd):
        dirs = [self.dir, TEST_DEFAULT_LIBRARY, DATA_DIR]
        before = snapshot(*dirs)
        self.lib(cmd)
        after = snapshot(*dirs)
        changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
        self.assertEqual(changed, [], f'{cmd} wrote these files')


class TestShallowDryRun(DryRunTest):
    "a shallow library, and its pool"

    def setUp(self):
        super().setUp()
        self.papers('init pool')
        self.papers('init lib --pool pool')
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')

    def test_add(self):
        self.assertNoWrites('add ../new.bib --dry-run')

    def test_file_attach_and_rename(self):
        # an entry of the library, and a file to attach or rename
        Path(self.path('lib', 'papers.bib')).write_text(NEW_BIB.replace(':mine.pdf:', ':../mine.pdf:'))
        self.assertNoWrites(f'file attach mine2022 {self.path("mine.pdf")} --dry-run')
        self.assertNoWrites('file rename --dry-run')
        self.assertNoWrites('push --dry-run')

    def test_add_then_dry_runs(self):
        self.lib('add ../new.bib')
        self.assertIn('mine2022', Path(self.path('pool', 'papers.bib')).read_text())
        Path(self.path('mine.pdf')).write_text('mine')
        self.papers('init other')
        for cmd in ['add ../new.bib --on-duplicate update', 'tag mine2022 --add x', 'rm mine2022 --keep-files',
                    'check -y', 'pull', 'push', 'sync', 'undo', 'restore', 'push --pool ../other --all',
                    'pull --pool ../pool --all', 'config pool none', 'install --edit']:
            self.assertNoWrites(cmd + ' --dry-run')

    def test_undo_redo(self):
        self.lib('add ../new.bib')
        self.lib('tag mine2022 --add x')
        self.lib('undo')
        out = self.lib('redo --dry-run', sp_cmd='check_output')
        self.assertIn('DRYRUN: redo:', out)
        self.assertNoWrites('redo --dry-run')
        self.assertNoWrites('undo --dry-run')


class TestSelfContainedDryRun(DryRunTest):

    def test_undo_without_git(self):
        self.papers('init lib')
        Path(self.path('new.bib')).write_text(NEW_BIB)
        Path(self.path('mine.pdf')).write_text('mine')
        self.lib('add ../new.bib')
        self.lib('tag mine2022 --add x')
        self.assertNoWrites('undo --dry-run')
