"""The library configuration is .papers/config.json; the .papersconfig.json
of papers 2 is read, and moved to .papers/config.json when papers saves the
configuration or by `papers migrate`."""
import io
import json
import os
import shutil
from contextlib import redirect_stdout
from pathlib import Path

import papers.config
from papers.backup import run_git
from papers.config import CONFIG_FILE_LOCAL, CONFIG_FILE_LOCAL_V2, Config, find_library_config, library_config_file
from papers.utils import PapersExit
from tests import TEST_DEFAULT_LIBRARY
from tests.common import ConfigTest, FileTest, entry


def to_v2_name(libdir):
    "rename the configuration of the library in libdir to .papersconfig.json (papers 2)"
    os.replace(os.path.join(libdir, CONFIG_FILE_LOCAL), os.path.join(libdir, CONFIG_FILE_LOCAL_V2))


class TestFindLibraryConfig(ConfigTest):

    def test_none(self):
        self.assertIsNone(find_library_config(self.dir))
        self.assertIsNone(library_config_file(self.dir))

    def test_both_names_from_a_subdirectory(self):
        os.makedirs(self.path('a', 'sub', 'deep'))
        os.makedirs(self.path('b', 'sub'))
        os.makedirs(self.path('a', '.papers'))
        Path(self.path('a', CONFIG_FILE_LOCAL)).write_text('{}')
        Path(self.path('b', CONFIG_FILE_LOCAL_V2)).write_text('{}')
        self.assertEqual(find_library_config(self.path('a', 'sub', 'deep')), self.path('a', CONFIG_FILE_LOCAL))
        self.assertEqual(find_library_config(self.path('b', 'sub')), self.path('b', CONFIG_FILE_LOCAL_V2))

    def test_both_files_are_an_error(self):
        os.makedirs(self.path('.papers'))
        Path(self.path(CONFIG_FILE_LOCAL)).write_text('{}')
        Path(self.path(CONFIG_FILE_LOCAL_V2)).write_text('{}')
        with self.assertRaisesRegex(PapersExit, 'two library configurations'):
            library_config_file(self.dir)


class TestInit(ConfigTest):

    def test_init(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.papers('init --no-git')
        self.assertTrue(os.path.isfile(self.path(CONFIG_FILE_LOCAL)))
        self.assertFalse(os.path.exists(self.path(CONFIG_FILE_LOCAL_V2)))
        self.assertEqual(Config.load(self.path(CONFIG_FILE_LOCAL)).bibtex, self.path('papers.bib'))

    def test_init_global(self):
        self.papers(f'init {TEST_DEFAULT_LIBRARY} --global --no-git')
        self.assertTrue(os.path.isfile(os.path.join(TEST_DEFAULT_LIBRARY, CONFIG_FILE_LOCAL)))
        self.assertFalse(os.path.exists(os.path.join(TEST_DEFAULT_LIBRARY, CONFIG_FILE_LOCAL_V2)))

    def test_init_in_a_v2_library(self):
        self.papers('init --no-git')
        to_v2_name(self.dir)
        with self.assertRaisesRegex(PapersExit, 'a library already exists here'):
            self.papers('init --no-git')

    def test_pool_that_is_not_a_library(self):
        os.makedirs(self.path('pool'))
        with self.assertRaisesRegex(PapersExit, r'not a library \(no \.papers/config\.json\)'):
            self.papers('init lib --pool ../pool --no-git')


class V2LibraryTest(FileTest):
    """a library in lib/ whose configuration has the name of papers 2"""

    def setUp(self):
        super().setUp()
        to_v2_name(self.path('lib'))

    def old(self):
        return self.path('lib', CONFIG_FILE_LOCAL_V2)

    def new(self):
        return self.path('lib', CONFIG_FILE_LOCAL)


class TestV2Library(V2LibraryTest):

    def test_found(self):
        os.makedirs(self.path('lib', 'sub'))
        out = io.StringIO()
        with redirect_stdout(out):
            self.papers('status -v', cwd=self.path('lib', 'sub'))
        self.assertIn('papers library: ' + self.path('lib'), out.getvalue())
        self.assertIn(CONFIG_FILE_LOCAL_V2, out.getvalue())
        # reading does not move it
        self.assertTrue(os.path.exists(self.old()))
        self.assertFalse(os.path.exists(self.new()))

    def test_found_with_directory_option(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.papers(f'-C {self.path("lib")} config bibtex')
        self.assertEqual(out.getvalue().strip(), self.path('lib', 'papers.bib'))

    def test_pool(self):
        os.makedirs(self.path('shallow'))
        self.papers('init --pool ../lib --no-git', cwd=self.path('shallow'))
        self.assertEqual(self.json('shallow')['pool'], '../lib')
        self.assertTrue(os.path.exists(self.old()))  # the pool is not saved

    def test_default_library(self):
        shutil.move(self.path('lib'), TEST_DEFAULT_LIBRARY)
        self.papers(f'config --global default {TEST_DEFAULT_LIBRARY}')
        out = io.StringIO()
        with redirect_stdout(out):
            self.papers('status')
        self.assertIn('(default library, set in ', out.getvalue())

    def test_moved_on_save(self):
        before = json.load(open(self.old()))
        out = self.out('config files copy')
        self.assertIn(f'moved {self.old()} to {self.new()}', out)
        self.assertFalse(os.path.exists(self.old()))
        after = json.load(open(self.new()))
        self.assertEqual(after['files'], 'copy')
        self.assertEqual({k: after[k] for k in ('bibtex', 'filesdir')}, {k: before[k] for k in ('bibtex', 'filesdir')})
        config = Config.load(self.new())
        self.assertEqual(config.bibtex, self.path('lib', 'papers.bib'))
        self.assertEqual(config.filesdir, self.path('lib', 'files'))
        # once only
        self.assertNotIn('moved', self.out('config files link'))

    def test_dry_run_moves_nothing(self):
        out = self.out('config files copy --dry-run')
        papers.config.DRYRUN = False
        self.assertIn('not saved', out)
        self.assertTrue(os.path.exists(self.old()))
        self.assertFalse(os.path.exists(self.new()))

    def test_both_files(self):
        shutil.copy(self.old(), self.new())
        before = os.listdir(self.path('lib'))
        for cmd in ['status', 'config files copy', 'migrate']:
            with self.assertRaisesRegex(PapersExit, 'two library configurations.*nothing was changed'):
                self.lib(cmd)
        self.assertEqual(os.listdir(self.path('lib')), before)
        self.assertNotIn('"files":', open(self.old()).read() + open(self.new()).read())

    def test_migrate(self):
        out = self.out('migrate --dry-run')
        papers.config.DRYRUN = False
        self.assertIn(f'DRYRUN: {self.old()} not moved to {self.new()}', out)
        self.assertTrue(os.path.exists(self.old()))
        self.assertFalse(os.path.exists(self.new()))

        out = self.out('migrate')
        self.assertIn(f'moved {self.old()} to {self.new()}', out)
        self.assertFalse(os.path.exists(self.old()))
        self.assertEqual(Config.load(self.new()).bibtex, self.path('lib', 'papers.bib'))

        self.assertIn('nothing to migrate', self.out('migrate'))


class TestUndoAfterMove(V2LibraryTest):
    """the backup does not track the library configuration: undo and redo
    bring back the bibtex, before and after the move, and leave the
    configuration where it is"""

    def bibtex(self):
        return open(self.path('lib', 'papers.bib')).read()

    def test_undo(self):
        self.lib('config git true')  # saves the configuration: moved
        self.assertTrue(os.path.exists(self.new()))
        gitdir = Config.load(self.new()).gitdir
        self.write('a.bib', content=entry('a2000'))
        self.write('b.bib', content=entry('b2000'))
        self.lib(f'add {self.path("a.bib")}')
        state_a = self.bibtex()
        self.lib(f'add {self.path("b.bib")}')
        self.assertIn('b2000', self.bibtex())
        tracked = run_git(gitdir, ['ls-files']).stdout.split()
        self.assertNotIn('config.json', ' '.join(tracked))
        self.assertNotIn(CONFIG_FILE_LOCAL_V2, tracked)

        self.lib('undo')
        self.assertEqual(self.bibtex(), state_a)
        self.lib('undo')
        self.assertNotIn('a2000', self.bibtex())
        self.lib('redo')
        self.assertEqual(self.bibtex(), state_a)
        self.assertTrue(os.path.exists(self.new()))
        self.assertFalse(os.path.exists(self.old()))
        self.assertTrue(Config.load(self.new()).git)

    def test_undo_of_a_backup_made_before_the_move(self):
        # backups made by the library under its papers 2 name
        os.replace(self.old(), self.new())
        self.lib('config git true')
        os.replace(self.new(), self.old())
        os.rmdir(os.path.dirname(self.new()))
        self.write('a.bib', content=entry('a2000'))
        self.lib(f'add {self.path("a.bib")}')
        self.assertTrue(os.path.exists(self.old()))  # the add does not save the configuration
        self.lib('config files copy')  # moved
        self.assertFalse(os.path.exists(self.old()))
        self.lib('undo')
        self.assertNotIn('a2000', self.bibtex())
        self.assertTrue(os.path.exists(self.new()))
        self.assertFalse(os.path.exists(self.old()))
        self.assertEqual(Config.load(self.new()).files, 'copy')


class TestExport(FileTest):

    def test_export(self):
        self.bib(entry('a2000'))
        self.lib('export ../out --no-git')
        self.assertTrue(os.path.isfile(self.path('out', CONFIG_FILE_LOCAL)))
        self.assertFalse(os.path.exists(self.path('out', CONFIG_FILE_LOCAL_V2)))
