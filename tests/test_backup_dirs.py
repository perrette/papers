import os
from pathlib import Path
import unittest

from papers.backup import default_gitdir, read_manifest, write_manifest
from papers.bib import Biblio
from tests.common import BaseTest, LocalGitInstallTest


class TestDefaultGitdirNaming(unittest.TestCase):

    def test_same_basename_maps_to_different_dirs(self):
        a = default_gitdir("/somewhere/a/papers.bib")
        b = default_gitdir("/somewhere/b/papers.bib")
        self.assertNotEqual(a, b)
        self.assertTrue(os.path.basename(a).startswith("papers-"))
        self.assertTrue(os.path.basename(b).startswith("papers-"))

    def test_deterministic(self):
        self.assertEqual(default_gitdir("/x/lib.bib"), default_gitdir("/x/lib.bib"))


class TestManifest(LocalGitInstallTest):

    def test_install_writes_manifest(self):
        manifest = read_manifest(self.config.gitdir)
        self.assertIsNotNone(manifest)
        self.assertEqual(Path(manifest["bibtex"]), Path(self._path(self.mybib)).resolve())

    def test_manifest_untracked_and_survives_operations(self):
        self.papers(f'add {self.anotherbib}')
        self.papers(f'undo')
        self.papers(f'redo')
        manifest = read_manifest(self.config.gitdir)
        self.assertIsNotNone(manifest)
        self.assertEqual(Path(manifest["bibtex"]), Path(self._path(self.mybib)).resolve())

    def test_collision_healing(self):
        gitdir0 = self.config.gitdir

        # another library claims the same backup directory
        otherbib = self._path("other.bib")
        open(otherbib, "w").write("")
        write_manifest(gitdir0, otherbib)

        # the next snapshot detects the foreign manifest and moves to a fresh directory
        self.papers(f'add {self.anotherbib}')
        config = self.config
        self.assertNotEqual(str(config.gitdir), str(gitdir0))
        manifest = read_manifest(config.gitdir)
        self.assertEqual(Path(manifest["bibtex"]), Path(self._path(self.mybib)).resolve())

        # the foreign directory was left untouched
        manifest0 = read_manifest(gitdir0)
        self.assertEqual(Path(manifest0["bibtex"]), Path(otherbib).resolve())

        # and the library itself was saved as usual
        biblio = Biblio.load(self._path(self.mybib), '')
        self.assertEqual(len(biblio.entries), 1)

    def test_backup_list(self):
        out = self.papers('backup list', sp_cmd='check_output')
        self.assertIn(os.path.basename(self.config.gitdir), out)
        self.assertIn(str(Path(self._path(self.mybib)).resolve()), out)
