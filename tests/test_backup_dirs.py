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

    def test_backup_defaults_to_list(self):
        out = self.papers('backup', sp_cmd='check_output')
        self.assertIn(os.path.basename(self.config.gitdir), out)


class TestBackupListWithoutGit(BaseTest):

    def test_backup_list_reports_git_off(self):
        self.papers(f'install --force --local --no-git --bibtex {self.mybib} --files {self.filesdir}')
        out = self.papers('backup list', sp_cmd='check_output')
        self.assertIn('git-tracking is off', out)


class TestLegacyLayout(LocalGitInstallTest):
    """Backup directories written by older versions tracked backup_copy.bib /
    backup_clean.bib; the new layout tracks the bibtex under its own name."""

    def _make_legacy(self):
        from papers.backup import run_git
        gitdir = self.config.gitdir
        name = Path(self.config.backupfile).name
        run_git(gitdir, ["mv", name, "backup_copy.bib"])
        run_git(gitdir, ["commit", "-m", "simulate pre-layout-2 backup"])

    def test_snapshot_converges_to_new_layout(self):
        self._make_legacy()
        self.papers(f'add {self.anotherbib}')
        gitdir = Path(self.config.gitdir)
        self.assertTrue(self.config.backupfile.exists())
        self.assertFalse((gitdir / "backup_copy.bib").exists())

    def test_undo_across_layouts(self):
        self.papers(f'add {self.anotherbib}')
        bib1 = open(self._path(self.mybib)).read()
        self._make_legacy()

        # a new snapshot on top of the legacy layout
        open(self._path("more.bib"), "w").write(
            "@article{More2024,\n author = {Mo Re},\n title = {More},\n year = {2024}\n}")
        self.papers(f'add more.bib')

        # undo materializes the legacy-layout snapshot: restore must fall back
        # to backup_copy.bib
        self.papers(f'undo')
        self.assertMultiLineEqual(open(self._path(self.mybib)).read(), bib1)
