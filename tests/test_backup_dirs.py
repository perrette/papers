"""the backup folder of a library: .papers/backup, and the backup folders
of papers 3.0.0b2 and earlier (in a folder of the machine) that it adopts"""
import os
import json
import shutil
import tempfile
from pathlib import Path

from papers.backup import git_init, run_git
from papers.bib import Biblio
from papers.config import CONFIG_FILE_LOCAL, BACKUP_DIR, Config
from tests.common import ConfigTest, GitInitTest, paperscmd


class TestLocalBackup(ConfigTest):

    def setUp(self):
        super().setUp()
        os.makedirs(self.path('a'))
        self.papers('init --git', cwd=self.path('a'))
        Path(self.path('new.bib')).write_text(bibtex_new)

    def test_in_the_library(self):
        config = Config.load(self.path('a', CONFIG_FILE_LOCAL))
        self.assertEqual(config.gitdir, self.path('a', '.papers', 'backup'))
        self.assertTrue(os.path.isdir(self.path('a', '.papers', 'backup', '.git')))
        self.assertNotIn('gitdir', json.load(open(config.file)))
        # a library in a folder under git (e.g. a project) does not track its backup
        self.assertIn('backup/', Path(self.path('a', '.papers', '.gitignore')).read_text().splitlines())

    def test_moved_library_keeps_its_history(self):
        self.papers('add ../new.bib', cwd=self.path('a'))
        shutil.move(self.path('a'), self.path('b'))
        self.papers('undo', cwd=self.path('b'))
        self.assertEqual(Biblio.load(self.path('b', 'papers.bib'), '').entries, [])
        self.papers('redo', cwd=self.path('b'))
        self.assertEqual(len(Biblio.load(self.path('b', 'papers.bib'), '').entries), 1)

    def test_copied_library_has_its_own_history(self):
        shutil.copytree(self.path('a'), self.path('b'))
        self.papers('add ../new.bib', cwd=self.path('b'))
        self.assertEqual(_snapshots(self.path('b', '.papers', 'backup')),
                         _snapshots(self.path('a', '.papers', 'backup')) + 1)

    def test_previous_bibtex_without_git(self):
        self.papers('config git false', cwd=self.path('a'))
        self.papers('add ../new.bib', cwd=self.path('a'))
        self.assertTrue(os.path.exists(self.path('a', '.papers', 'backup', 'previous.bib')))
        self.assertFalse(os.path.exists(self.path('a', '.papers.bib.backup')))
        self.papers('undo', cwd=self.path('a'))
        self.assertEqual(Biblio.load(self.path('a', 'papers.bib'), '').entries, [])


class TestAdoptCentralBackup(ConfigTest):
    """the backup of papers 3.0.0b2 and earlier, in a folder of the machine
    (BACKUP_DIR), moves to the library"""

    def setUp(self):
        super().setUp()
        os.makedirs(self.path('lib', '.papers'))
        Path(self.path('lib', 'papers.bib')).write_text('')
        Path(self.path('new.bib')).write_text(bibtex_new)

    def central(self, name, bibtex=None):
        "a backup folder of papers 3.0.0b2, with one snapshot, a trash and a manifest"
        gitdir = os.path.join(BACKUP_DIR, name)
        os.makedirs(gitdir)
        git_init(gitdir)
        Path(gitdir, 'papers.bib').write_text('')
        run_git(gitdir, ['add', 'papers.bib'])
        run_git(gitdir, ['commit', '-m', 'old snapshot'])
        os.makedirs(os.path.join(gitdir, 'trash'))
        Path(gitdir, 'trash', 'x.pdf').write_text('x')
        json.dump({'bibtex': bibtex or self.path('lib', 'papers.bib')}, open(os.path.join(gitdir, 'manifest.json'), 'w'))
        return gitdir

    def configure(self, **js):
        json.dump({'bibtex': 'papers.bib', 'filesdir': 'files', 'git': True, 'version': 3, **js},
                  open(self.path('lib', CONFIG_FILE_LOCAL), 'w'))

    def check_adopted(self, old):
        local = self.path('lib', '.papers', 'backup')
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.isdir(os.path.join(local, '.git')))
        self.assertTrue(os.path.exists(os.path.join(local, 'trash', 'x.pdf')))
        self.assertFalse(os.path.exists(os.path.join(local, 'manifest.json')))
        self.assertNotIn('gitdir', json.load(open(self.path('lib', CONFIG_FILE_LOCAL))))
        log = paperscmd('git log --format=%s', cwd=self.path('lib'), sp_cmd='check_output')
        self.assertEqual(log.splitlines()[-1], 'old snapshot')  # the history moved too

    def test_named_by_the_configuration(self):
        old = self.central('lib-0123abcd')
        self.configure(gitdir='lib-0123abcd')
        with self.assertLogs('papers', level='WARNING') as logs:
            self.papers('add ../new.bib', cwd=self.path('lib'))
        self.assertTrue(any('the backup of the library moved from' in line for line in logs.output))
        self.check_adopted(old)
        self.papers('undo', cwd=self.path('lib'))  # to the old snapshot
        self.assertEqual(Biblio.load(self.path('lib', 'papers.bib'), '').entries, [])

    def test_named_after_the_bibtex(self):
        # the configuration of papers 3.0.0b1 did not always name it
        from papers.backup import _central_gitdirs
        self.configure()
        config = Config.load(self.path('lib', CONFIG_FILE_LOCAL))
        old = self.central(os.path.basename(_central_gitdirs(config)[0]))
        self.papers('status', cwd=self.path('lib'))
        self.check_adopted(old)

    def test_of_another_library(self):
        from papers.backup import _central_gitdirs
        self.configure()
        config = Config.load(self.path('lib', CONFIG_FILE_LOCAL))
        old = self.central(os.path.basename(_central_gitdirs(config)[0]), bibtex=self.path('other.bib'))
        self.papers('status', cwd=self.path('lib'))
        self.assertTrue(os.path.isdir(os.path.join(old, '.git')))
        self.assertFalse(os.path.exists(self.path('lib', '.papers', 'backup', '.git')))

    def test_previous_bibtex_without_git(self):
        self.configure(git=False)
        Path(self.path('lib', '.papers.bib.backup')).write_text(bibtex_new)
        self.papers('status', cwd=self.path('lib'))
        self.assertFalse(os.path.exists(self.path('lib', '.papers.bib.backup')))
        self.papers('undo', cwd=self.path('lib'))
        self.assertEqual(len(Biblio.load(self.path('lib', 'papers.bib'), '').entries), 1)

    def test_backup_list_and_remove(self):
        self.central('gone-0123abcd', bibtex=self.path('gone.bib'))
        self.configure()
        out = self.papers('backup list', cwd=self.path('lib'), sp_cmd='check_output')
        self.assertIn('backup of papers.bib: ', out.replace(self.path('lib') + os.sep, ''))
        self.assertIn('* gone-0123abcd', out)
        self.papers('backup remove gone-* --yes', cwd=self.path('lib'))
        self.assertFalse(os.path.exists(os.path.join(BACKUP_DIR, 'gone-0123abcd')))


class TestDotPapersGitdir(ConfigTest):
    """the libraries of papers v2.2 to v2.4 back up into <library>/.papers,
    where papers 3 keeps config.json, distinct.json and origin/"""

    def setUp(self):
        super().setUp()
        dot = self.path('lib', '.papers')
        os.makedirs(dot)
        Path(self.path('lib', 'papers.bib')).write_text('')
        Path(dot, 'config.json').write_text(
            '{"bibtex": "papers.bib", "filesdir": "files", "git": true, "gitdir": ".papers", "local": true}')
        git_init(dot)
        Path(dot, 'papers.bib').write_text('')
        run_git(dot, ['add', 'papers.bib'])
        run_git(dot, ['commit', '-m', 'v2 snapshot'])
        Path(dot, 'distinct.json').write_text('[]')
        Path(self.path('a.bib')).write_text(
            '@article{a2000,\n author = {One, Some},\n title = {A title},\n year = {2000}\n}\n')

    def test_moved_to_the_backup_folder(self):
        with self.assertLogs('papers', level='WARNING') as logs:
            self.papers('add ../a.bib', cwd=self.path('lib'))
        self.assertTrue(any('the backup of the library moved from' in line for line in logs.output))
        # the files of the library stay, the repository moved
        self.assertTrue(os.path.exists(self.path('lib', '.papers', 'distinct.json')))
        self.assertFalse(os.path.exists(self.path('lib', '.papers', '.git')))
        config = Config.load(self.path('lib', CONFIG_FILE_LOCAL))
        self.assertEqual(config.gitdir, self.path('lib', '.papers', 'backup'))
        log = paperscmd('git log --format=%s', cwd=self.path('lib'), sp_cmd='check_output')
        self.assertEqual(log.splitlines()[-1], 'v2 snapshot')  # the history moved too
        self.assertIn('a2000', Path(config.gitdir, 'papers.bib').read_text())

    def test_tracked_configuration_stays(self):
        # .papers/config.json is the library configuration of papers 3: a
        # repository that tracked it leaves it in the library
        dot = self.path('lib', '.papers')
        run_git(dot, ['add', 'config.json'])
        run_git(dot, ['commit', '-m', 'config'])
        with self.assertLogs('papers', level='WARNING'):
            self.papers('add ../a.bib', cwd=self.path('lib'))
        self.assertTrue(os.path.exists(self.path('lib', CONFIG_FILE_LOCAL)))
        config = Config.load(self.path('lib', CONFIG_FILE_LOCAL))
        self.assertEqual(config.gitdir, self.path('lib', '.papers', 'backup'))


class TestLegacyLayout(GitInitTest):
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
    res = run_git(gitdir, ['rev-list', '--count', 'HEAD'], check=False)
    return int(res.stdout) if res.returncode == 0 else 0


class TestAddFromAnotherDirectory(GitInitTest):
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
        paperscmd('init --bibtex other.bib --filesdir otherfiles', cwd=self.other.name)
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
        otherbib = os.path.join(self.other.name, 'lib.bib')
        open(otherbib, 'w').write('')
        config_before = open(self._path(CONFIG_FILE_LOCAL)).read()
        n = _snapshots(self.config.gitdir)

        self.papers(f'add --bibtex {otherbib} {self.anotherbib}')

        self.assertEqual(len(Biblio.load(otherbib, '').entries), 1)
        # backed up in a directory of its own, the current library untouched
        self.assertEqual(_snapshots(os.path.join(self.other.name, '.papers', 'backup-lib.bib')), 1)
        self.assertEqual(_snapshots(self.config.gitdir), n)
        self.assertEqual(open(self._path(CONFIG_FILE_LOCAL)).read(), config_before)

    def test_backup_failure_does_not_abort_the_command(self):
        from unittest import mock
        with mock.patch('papers.library.silent_backup_bib', side_effect=RuntimeError('git is broken')):
            with self.assertLogs('papers', level='ERROR'):
                self.papers(f'add {self.anotherbib}')
        self.assertEqual(len(Biblio.load(self._path(self.mybib), '').entries), 1)


class TestCommitFailure(GitInitTest):

    def test_warning(self):
        hook = Path(self.config.gitdir, '.git', 'hooks', 'pre-commit')
        hook.write_text('#!/bin/sh\necho refused >&2\nexit 1\n')
        hook.chmod(0o755)
        with self.assertLogs('papers', level='WARNING') as logs:
            self.papers(f'add {self.anotherbib}')
        self.assertTrue(any('could not commit' in line and 'refused' in line for line in logs.output))
