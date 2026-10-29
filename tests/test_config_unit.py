"""Unit tests for papers.config (pure logic, no install)"""
import json
import os
import tempfile
import unittest
from unittest import mock

from papers.config import Config, CONFIG_FILE_LOCAL, CONFIG_FILE_LOCAL_V2, MachineConfig


class TestConfigRelpath(unittest.TestCase):

    def test_relpath_local(self):
        with tempfile.TemporaryDirectory() as d:
            bib = os.path.join(d, "lib.bib")
            open(bib, 'w').close()
            cfg = Config(file=os.path.join(d, CONFIG_FILE_LOCAL), bibtex=bib, is_library=True)
            # Path under root -> relative
            sub = os.path.join(d, "sub", "file.pdf")
            os.makedirs(os.path.dirname(sub))
            result = cfg._relpath(sub)
            self.assertIn("sub", result)

    def test_relpath_none_returns_none(self):
        cfg = Config(is_library=True, bibtex="/tmp/x.bib")
        self.assertIsNone(cfg._relpath(None))

    def test_relpath_non_local_returns_abspath(self):
        cfg = Config(is_library=False, bibtex="/tmp/x.bib")
        result = cfg._relpath("/some/path/file.pdf")
        self.assertEqual(result, "/some/path/file.pdf")


class TestConfigEditor(unittest.TestCase):

    def test_editor_setter(self):
        # the editor setting is handed to utils.edit_text, the environment is left alone
        with mock.patch.dict(os.environ, {"EDITOR": "nano"}):
            cfg = Config(is_library=True, bibtex="/tmp/x.bib")
            cfg.editor = "vim"
            self.assertEqual(cfg.editor, "vim")
            self.assertEqual(os.environ.get("EDITOR"), "nano")


class TestLibraryId(unittest.TestCase):
    "the identifier of a library names its history (see papers.backup)"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.tmp.name, CONFIG_FILE_LOCAL)
        os.makedirs(os.path.dirname(self.file))
        self.machine = MachineConfig(os.path.join(self.tmp.name, 'machine.json'))

    def tearDown(self):
        self.tmp.cleanup()

    def test_created_once_and_kept(self):
        json.dump({'bibtex': 'lib.bib', 'version': 3}, open(self.file, 'w'))
        config = Config.load(self.file, machine=self.machine)
        self.assertIsNone(config.library_id(create=False))
        id = config.library_id()
        self.assertRegex(id, r'^[0-9a-f]{32}$')
        self.assertEqual(json.load(open(self.file))['id'], id)
        self.assertEqual(Config.load(self.file, machine=self.machine).library_id(), id)

    def test_invalid_id_ignored(self):
        for bad in ('../../somewhere', 'a/b', '', 12):
            json.dump({'bibtex': 'lib.bib', 'version': 3, 'id': bad}, open(self.file, 'w'))
            config = Config.load(self.file, machine=self.machine)
            self.assertIsNone(config.library_id(create=False))
            self.assertRegex(config.library_id(), r'^[0-9a-f]{32}$')  # a new one, written over it

    def test_only_the_id_is_written(self):
        # the settings in memory may be those of the command (e.g. the files directory of a pool)
        json.dump({'bibtex': 'lib.bib', 'version': 3}, open(self.file, 'w'))
        config = Config.load(self.file, machine=self.machine)
        config.filesdir = '/somewhere/else'
        config.library_id()
        self.assertEqual(set(json.load(open(self.file))), {'bibtex', 'version', 'id'})

    def test_written_to_papers_config_json(self):
        # a library configuration of papers 2 is moved first, as by any save
        v2 = os.path.join(self.tmp.name, CONFIG_FILE_LOCAL_V2)
        os.rmdir(os.path.dirname(self.file))
        json.dump({'bibtex': 'lib.bib', 'version': 3}, open(v2, 'w'))
        config = Config.load(v2, machine=self.machine)
        id = config.library_id()
        self.assertFalse(os.path.exists(v2))
        self.assertEqual(config.file, self.file)
        self.assertEqual(json.load(open(self.file)), {'bibtex': 'lib.bib', 'version': 3, 'id': id})

    def test_machine_settings_not_read_from_a_library(self):
        json.dump({'bibtex': 'lib.bib', 'version': 3, 'history-dir': '/tmp/evil', 'keep-deleted-files': False,
                   'history-separate': True, 'history-size': 7}, open(self.file, 'w'))
        config = Config.load(self.file, machine=self.machine)
        self.assertIsNone(config.history_dir)
        self.assertTrue(config.keep_deleted_files)
        # a library may keep a history of its own, of its own size
        self.assertTrue(config.history_separate)
        self.assertEqual(config.history_size, 7)
        js = config.tojson()
        self.assertNotIn('history-dir', js)
        self.assertNotIn('keep-deleted-files', js)

    def test_unknown_keys_kept(self):
        # e.g. the settings of a newer papers: kept as they are when papers saves the file
        json.dump({'bibtex': 'lib.bib', 'version': 3, 'editor': 'vim', 'pools': ['old'], 'future': {'a': [1]},
                   'nameformat': {'template': '{author}', 'future-field': 2}}, open(self.file, 'w'))
        config = Config.load(self.file, machine=self.machine)
        config.unset('editor')
        config.set('name.template', '{year}')
        config.save()
        js = json.load(open(self.file))
        self.assertEqual(js['future'], {'a': [1]})
        self.assertEqual(js['nameformat'], {'template': '{year}', 'future-field': 2})
        # the known settings are those of papers: unset, or read and no longer written
        self.assertNotIn('editor', js)
        self.assertNotIn('pools', js)


class TestPathsOfSettings(unittest.TestCase):
    "~ is the home directory in every path setting; a relative path of the global configuration is relative to its folder"

    def test_home_in_bibtex_and_filesdir(self):
        from papers.config import Config, MachineConfig
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, '.papers'))
            file = os.path.join(d, '.papers', 'config.json')
            with open(file, 'w') as f:
                json.dump({'bibtex': '~/refs.bib', 'filesdir': '~/pdfs', 'version': 3}, f)
            config = Config.load(file, machine=MachineConfig(os.path.join(d, 'machine.json')))
            self.assertEqual(config.bibtex, os.path.join(os.path.expanduser('~'), 'refs.bib'))
            self.assertEqual(config.filesdir, os.path.join(os.path.expanduser('~'), 'pdfs'))

    def test_relative_to_the_global_configuration(self):
        from papers.config import MachineConfig
        machine = MachineConfig('/etc/papers/config.json', {'default': 'library', 'history-dir': '../history'})
        self.assertEqual(machine.default_path(), '/etc/papers/library')
        self.assertEqual(machine.absolute('../history'), '/etc/history')
        self.assertEqual(machine.absolute('~/h'), os.path.join(os.path.expanduser('~'), 'h'))


class TestPoolPathsOnce(unittest.TestCase):
    """the folder of the library and the path of its pool resolve symbolic
    links: once per configuration file and pool setting (the exchanges ask
    for them for every entry), again when either changes"""

    def setUp(self):
        from papers.config import Config, MachineConfig
        self.dir = tempfile.TemporaryDirectory()
        d = os.path.realpath(self.dir.name)
        for name in ('lib', 'pool'):
            os.makedirs(os.path.join(d, name, '.papers'))
        os.symlink(os.path.join(d, 'lib'), os.path.join(d, 'link'))
        self.d = d
        self.config = Config(file=os.path.join(d, 'lib', '.papers', 'config.json'), is_library=True,
                             bibtex=os.path.join(d, 'lib', 'papers.bib'), pool='../pool',
                             machine=MachineConfig(os.path.join(d, 'machine.json')))

    def tearDown(self):
        self.dir.cleanup()

    def test_resolved_once(self):
        calls = []
        realpath = os.path.realpath
        with mock.patch('os.path.realpath', lambda p, **kw: calls.append(p) or realpath(p, **kw)):
            for _ in range(100):
                self.assertTrue(self.config.shallow)
                self.assertTrue(self.config.has_pool())
                self.assertEqual(self.config.pool_path(), os.path.join(self.d, 'pool'))
                self.assertEqual(str(self.config.configdir), os.path.join(self.d, 'lib'))
        self.assertLessEqual(len(calls), 3)  # 1 200 before

    def test_changed_pool_setting(self):
        self.assertTrue(self.config.shallow)
        self.config.set('pool', '.')
        self.assertTrue(self.config.is_pool_library())
        self.assertFalse(self.config.shallow)
        self.config.set('pool', '../link')  # the library itself, through a symbolic link
        self.assertTrue(self.config.is_pool_library())
        self.config.pool = '../pool'
        self.assertTrue(self.config.shallow)
        self.config.set('pool', 'none')
        self.assertIsNone(self.config.pool_path())
        self.assertFalse(self.config.shallow)

    def test_changed_file(self):
        self.assertEqual(str(self.config.configdir), os.path.join(self.d, 'lib'))
        self.config.file = os.path.join(self.d, 'pool', '.papers', 'config.json')
        self.assertEqual(str(self.config.configdir), os.path.join(self.d, 'pool'))
        self.assertTrue(self.config.is_pool_library())  # ../pool from pool/

    def test_relative_file(self):
        # a relative configuration file is relative to the current directory
        from papers.utils import set_directory
        self.config.file = os.path.join('.papers', 'config.json')
        with set_directory(os.path.join(self.d, 'lib')):
            self.assertEqual(str(self.config.configdir), os.path.join(self.d, 'lib'))
        with set_directory(os.path.join(self.d, 'pool')):
            self.assertEqual(str(self.config.configdir), os.path.join(self.d, 'pool'))
