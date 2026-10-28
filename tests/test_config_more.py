"""Unit tests of the remaining branches of papers.config"""
import json
import os
import tempfile
import unittest
from unittest import mock

from papers.config import (CONFIG_FILE_LOCAL, Config, MachineConfig, file_version, json_get, json_set,
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

    def test_short_home(self):
        home = os.path.expanduser('~')
        self.assertEqual(short_home(os.path.join(home, 'papers')), os.path.join('~', 'papers'))
        self.assertEqual(short_home(home), '~')
        self.assertEqual(short_home('/elsewhere'), '/elsewhere')


class TestMachineConfig(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.tmp.name, 'config.json')

    def tearDown(self):
        self.tmp.cleanup()

    def test_unreadable(self):
        # an error, as for a library configuration: saving the global
        # configuration would otherwise replace the file
        with open(self.file, 'w') as f:
            f.write('{not json')
        with self.assertRaisesRegex(PapersExit, 'config.json'):
            MachineConfig.load(self.file)

    def test_wrong_type(self):
        for js, name in [({'auto-push': 'no'}, 'auto-push'), ({'default': 3}, 'default'),
                         ({'history-size': True}, 'history-size'), ({'files': 'keep'}, 'files'),
                         ({'nameformat': {'title_length': '10'}}, 'name.title-length')]:
            with open(self.file, 'w') as f:
                json.dump(js, f)
            with self.assertRaisesRegex(PapersExit, f'config.json: invalid value .* for the setting {name} '):
                MachineConfig.load(self.file)

    def test_right_types(self):
        with open(self.file, 'w') as f:
            json.dump({'auto-push': False, 'default': '~/lib', 'history-size': 10, 'files': 'copy',
                       'editor': None, 'nameformat': {'title_length': 10, 'unknown_strict': True}}, f)
        self.assertEqual(MachineConfig.load(self.file).get('history-size'), 10)

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

    def test_wrong_type(self):
        file = os.path.join(self.dir, CONFIG_FILE_LOCAL)
        os.makedirs(os.path.dirname(file))
        machine = MachineConfig(os.path.join(self.dir, 'machine.json'))
        for js, name in [({'auto-push': 'no'}, 'auto-push'), ({'pool': 3}, 'pool'),
                         ({'bibtex': ['a.bib']}, 'bibtex'), ({'paths': 'relativ'}, 'paths'),
                         ({'keyformat': {'author_num': 2.5}}, 'key.author-num')]:
            with open(file, 'w') as f:
                json.dump({'version': 3, **js}, f)
            with self.assertRaisesRegex(PapersExit, f'config.json: invalid value .* for the setting {name} '):
                Config.load(file, machine=machine)
        for text in ('{not json', '[]'):
            with open(file, 'w') as f:
                f.write(text)
            with self.assertRaisesRegex(PapersExit, 'config.json'):
                Config.load(file, machine=machine)

    def test_update_paths_without_file(self):
        with self.assertLogs('papers', level='WARNING'):
            Config()._update_paths_to_absolute()

    def test_status_unset_and_missing(self):
        config = Config(file=os.path.join(self.dir, CONFIG_FILE_LOCAL),
                        bibtex=os.path.join(self.dir, 'missing.bib'))
        status = config.status(check_files=True)
        self.assertIn('no files directory', status)
        self.assertIn('(missing)', status)
        config.bibtex = None
        self.assertIn('(unset)', config.status())
