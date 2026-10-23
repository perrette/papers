"""Unit tests of the remaining branches of papers.config"""
import json
import os
import tempfile
import unittest
from unittest import mock

from papers.config import (CONFIG_FILE_LOCAL, Config, MachineConfig, file_version, gitdir_from_json, json_get, json_set,
                           short_home)
from papers.utils import PapersExit


class TestJson(unittest.TestCase):

    def test_invalid_version(self):
        for version in ('3', True, 1.5):
            with self.assertRaises(PapersExit):
                file_version({'version': version}, 'x.json')

    def test_unset_format_setting(self):
        js = {'keyformat': {'template': '{author}', 'author_num': 1}}
        json_set(js, 'key.author-num', None)
        self.assertEqual(js, {'keyformat': {'template': '{author}'}})
        json_set(js, 'key.template', None)
        self.assertEqual(js, {})  # the empty group is removed

    def test_paths_of_v2(self):
        self.assertEqual(json_get({'absolute_paths': False}, 'paths'), 'relative')
        self.assertEqual(json_get({'backup_files': True}, 'git-lfs'), True)

    def test_short_home(self):
        home = os.path.expanduser('~')
        self.assertEqual(short_home(os.path.join(home, 'papers')), os.path.join('~', 'papers'))
        self.assertEqual(short_home(home), '~')
        self.assertEqual(short_home('/elsewhere'), '/elsewhere')

    def test_gitdir_none(self):
        self.assertIsNone(gitdir_from_json(None, '/lib'))


class TestMachineConfig(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.tmp.name, 'config.json')

    def tearDown(self):
        self.tmp.cleanup()

    def test_unreadable(self):
        with open(self.file, 'w') as f:
            f.write('{not json')
        with self.assertLogs('papers', level='WARNING'):
            self.assertEqual(MachineConfig.load(self.file).data, {})

    def test_pool_names_of_earlier_v3(self):
        # the pool names of earlier v3 builds: read for the libraries that name their pool
        machine = MachineConfig(self.file, {'pools': {'default': '/a', 'x': '/b'}})
        self.assertEqual(machine.pool_names['x'], '/b')
        self.assertNotIn('pools', machine.data)
        self.assertIsNone(machine.default)  # not the default library

    def test_default_library(self):
        machine = MachineConfig(self.file, {'default': '~/lib'})
        self.assertEqual(machine.default, '~/lib')
        self.assertEqual(machine.default_path(), os.path.expanduser('~/lib'))
        self.assertIsNone(MachineConfig(self.file, {}).default_path())


class TestConfig(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.realpath(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_relpath_failure_keeps_the_path(self):
        config = Config(file=os.path.join(self.dir, CONFIG_FILE_LOCAL), is_library=True)
        with mock.patch('papers.config.os.path.relpath', side_effect=ValueError('other drive')), \
                self.assertLogs('papers', level='WARNING'):
            self.assertEqual(config._relpath('/x/papers.bib'), '/x/papers.bib')

    def test_v2_global_configuration(self):
        # is_library=False: the file format of v2, with absolute paths by default
        file = os.path.join(self.dir, 'papersconfig.json')
        with open(file, 'w') as f:
            json.dump({'bibtex': os.path.join(self.dir, 'papers.bib')}, f)
        config = Config.load(file, is_library=False)
        self.assertTrue(config.absolute_paths)
        self.assertIs(config.tojson()['local'], False)

    def test_update_paths_without_file(self):
        with self.assertLogs('papers', level='WARNING'):
            Config()._update_paths_to_absolute()

    def test_status_unset_and_missing(self):
        config = Config(file=os.path.join(self.dir, CONFIG_FILE_LOCAL),
                        bibtex=os.path.join(self.dir, 'missing.bib'))
        status = config.status(check_files=True)
        self.assertIn('(unset)', status)  # files directory
        self.assertIn('(missing)', status)
        config.bibtex = None
        self.assertIn('(unset)', config.status())
