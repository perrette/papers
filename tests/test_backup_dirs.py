import os
import json
import shutil
import tempfile
from pathlib import Path
import unittest

from papers.backup import default_gitdir, read_manifest, write_manifest
from papers.bib import Biblio
from papers.config import CONFIG_FILE_LOCAL, BACKUP_DIR, Config
from tests.common import BaseTest, LocalGitInstallTest, paperscmd


class TestDefaultGitdirNaming(unittest.TestCase):

    def test_same_basename_maps_to_different_dirs(self):
        a = default_gitdir("/somewhere/projecta/references.bib")
        b = default_gitdir("/somewhere/projectb/references.bib")
        self.assertNotEqual(a, b)
        # the parent folder tells same-named libraries apart at a glance
        self.assertTrue(os.path.basename(a).startswith("projecta-references-"))
        self.assertTrue(os.path.basename(b).startswith("projectb-references-"))

    def test_deterministic(self):
        self.assertEqual(default_gitdir("/x/lib.bib"), default_gitdir("/x/lib.bib"))


class TestManifest(LocalGitInstallTest):

    def test_install_writes_manifest(self):
        manifest = read_manifest(self.config.gitdir)
        self.assertIsNotNone(manifest)
        self.assertEqual(Path(manifest["bibtex"]), Path(self._path(self.mybib)).resolve())

    def test_manifest_untracked_and_survives_operations(self):
        self.papers(f'add {self.anotherbib}')
        self.papers('undo')
        self.papers('redo')
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


class TestBackupRemove(LocalGitInstallTest):

    def test_remove_by_name(self):
        gitdir = self.config.gitdir
        self.assertTrue(os.path.isdir(gitdir))
        self.papers(f'backup remove {os.path.basename(gitdir)} --force')
        self.assertFalse(os.path.exists(gitdir))

    def test_remove_requires_pattern(self):
        func = lambda: self.papers('backup remove --force')
        self.assertRaises(BaseException, func)
        self.assertTrue(os.path.isdir(self.config.gitdir))

    def test_remove_no_match(self):
        out = self.papers('backup remove no-such-dir-xyz --force', sp_cmd='check_output')
        self.assertIn('no matching backup directory', out)
        self.assertTrue(os.path.isdir(self.config.gitdir))

    def test_list_filter(self):
        name = os.path.basename(self.config.gitdir)
        out = self.papers(f'backup list {name}', sp_cmd='check_output')
        self.assertIn(name, out)
        out = self.papers('backup list no-such-dir-xyz', sp_cmd='check_output')
        self.assertNotIn(name, out)


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
        self.papers('add more.bib')

        # undo materializes the legacy-layout snapshot: restore must fall back
        # to backup_copy.bib
        self.papers('undo')
        self.assertMultiLineEqual(open(self._path(self.mybib)).read(), bib1)


bibtex_new = """@article{SomeOneElse2000,
 author = {Some One},
 doi = {10.5194/xxxx},
 title = {Interesting Stuff},
 year = {2000}
}"""


def _snapshots(gitdir):
    from papers.backup import backup_info
    return backup_info(gitdir)['snapshots'] or 0


class TestAddFromAnotherDirectory(LocalGitInstallTest):
    """`papers add --bibtex /path/to/library.bib` run from another directory:
    the configuration (and backup directory) of that library applies,
    whatever the current directory holds"""

    def setUp(self):
        super().setUp()
        self.other = tempfile.TemporaryDirectory()
        open(os.path.join(self.other.name, 'new.bib'), 'w').write(bibtex_new)

    def tearDown(self):
        self.other.cleanup()
        super().tearDown()

    def _add_from_other(self):
        paperscmd(f'add --bibtex {self._path(self.mybib)} --filesdir {self._path(self.filesdir)} new.bib', cwd=self.other.name)

    def test_backup_in_library_gitdir(self):
        gitdir = self.config.gitdir
        n = _snapshots(gitdir)
        self._add_from_other()
        self.assertEqual(len(Biblio.load(self._path(self.mybib), '').entries), 1)
        self.assertEqual(_snapshots(gitdir), n + 1)

    def test_cwd_local_config_with_broken_git_setup(self):
        # the current directory is another library whose backup directory does not exist
        paperscmd('install --force --local --bibtex other.bib --files otherfiles', cwd=self.other.name)
        otherconfig = os.path.join(self.other.name, CONFIG_FILE_LOCAL)
        js = json.load(open(otherconfig))
        js['git'] = True
        js['gitdir'] = os.path.join(self.other.name, 'no-such-backup')
        json.dump(js, open(otherconfig, 'w'))
        before = open(otherconfig).read()

        gitdir = self.config.gitdir
        n = _snapshots(gitdir)
        self._add_from_other()
        self.assertEqual(len(Biblio.load(self._path(self.mybib), '').entries), 1)
        self.assertEqual(_snapshots(gitdir), n + 1)
        # the other library is left alone
        self.assertEqual(open(otherconfig).read(), before)
        self.assertFalse(os.path.exists(js['gitdir']))

    def test_bibtex_without_config_gets_its_own_backup(self):
        # here the roles are reversed: the current directory holds the
        # git-enabled library, --bibtex points to a bare bibtex elsewhere
        from papers.backup import resolve_gitdir
        otherbib = os.path.join(self.other.name, 'lib.bib')
        open(otherbib, 'w').write('')
        config_before = open(self._path(CONFIG_FILE_LOCAL)).read()
        n = _snapshots(self.config.gitdir)

        self.papers(f'add --bibtex {otherbib} {self.anotherbib}')

        self.assertEqual(len(Biblio.load(otherbib, '').entries), 1)
        # backed up in a directory of its own, the current library untouched
        self.assertEqual(_snapshots(resolve_gitdir(otherbib)), 1)
        self.assertEqual(_snapshots(self.config.gitdir), n)
        self.assertEqual(open(self._path(CONFIG_FILE_LOCAL)).read(), config_before)

    def test_backup_failure_does_not_abort_the_command(self):
        from unittest import mock
        with mock.patch('papers.__main__.silent_backup_bib', side_effect=RuntimeError('git is broken')):
            with self.assertLogs('papers', level='ERROR'):
                self.papers(f'add {self.anotherbib}')
        self.assertEqual(len(Biblio.load(self._path(self.mybib), '').entries), 1)


class TestGitdirByName(unittest.TestCase):
    """the library configuration names its backup directory, resolved under
    the backup folder of the machine (BACKUP_DIR)"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir = os.path.realpath(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def path(self, *p):
        return os.path.join(self.dir, *p)

    def json(self, *p):
        return json.load(open(self.path(*p, CONFIG_FILE_LOCAL)))

    def config(self, gitdir):
        config = Config(file=self.path(CONFIG_FILE_LOCAL), local=True,
                        bibtex=self.path('lib.bib'), gitdir=gitdir)
        config.save()
        return Config.load(config.file)

    def test_by_name(self):
        gitdir = os.path.join(BACKUP_DIR, 'lib-0123abcd')
        config = self.config(gitdir)
        self.assertEqual(self.json()['gitdir'], 'lib-0123abcd')
        self.assertEqual(config.gitdir, gitdir)

    def test_custom_location(self):
        gitdir = self.path('elsewhere', 'backup')
        config = self.config(gitdir)
        self.assertEqual(self.json()['gitdir'], gitdir)
        self.assertEqual(config.gitdir, gitdir)

    def test_absolute_path_of_previous_versions(self):
        gitdir = os.path.join(BACKUP_DIR, 'lib-0123abcd')
        json.dump({'bibtex': 'lib.bib', 'gitdir': gitdir, 'version': 3},
                  open(self.path(CONFIG_FILE_LOCAL), 'w'))
        config = Config.load(self.path(CONFIG_FILE_LOCAL))
        self.assertEqual(config.gitdir, gitdir)
        config.save()
        self.assertEqual(self.json()['gitdir'], 'lib-0123abcd')

    def test_init_and_copied_library(self):
        os.makedirs(self.path('a'))
        paperscmd('init --git', cwd=self.path('a'))
        name = self.json('a')['gitdir']
        self.assertEqual(os.path.basename(name), name)
        gitdir = os.path.join(BACKUP_DIR, name)
        self.assertTrue(os.path.isdir(os.path.join(gitdir, '.git')))
        self.assertEqual(Config.load(self.path('a', CONFIG_FILE_LOCAL)).gitdir, gitdir)
        out = paperscmd('backup list', cwd=self.path('a'), sp_cmd='check_output')
        self.assertIn(f'* {name}: {self.path("a", "papers.bib")}', out)
        self.assertIn('[current]', out)

        # a copy of the library names the same backup directory: it moves
        # to a fresh one instead of sharing it
        shutil.copytree(self.path('a'), self.path('b'))
        open(self.path('new.bib'), 'w').write(bibtex_new)
        paperscmd('add ../new.bib', cwd=self.path('b'))
        nameb = self.json('b')['gitdir']
        self.assertNotEqual(nameb, name)
        self.assertEqual(os.path.basename(nameb), nameb)
        self.assertEqual(Path(read_manifest(os.path.join(BACKUP_DIR, nameb))['bibtex']),
                         Path(self.path('b', 'papers.bib')))
        self.assertEqual(Path(read_manifest(gitdir)['bibtex']), Path(self.path('a', 'papers.bib')))
        self.assertEqual(_snapshots(gitdir), 1)
        self.assertEqual(self.json('a')['gitdir'], name)
