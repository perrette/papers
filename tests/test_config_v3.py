"""v3 configuration: library and per-machine configuration, init, config,
migrate, -C and the default pool"""
import json
import os
import tempfile
import unittest
from pathlib import Path

import papers.config
from papers.config import Config, MachineConfig, CONFIG_FILE, CONFIG_FILE_LOCAL
from papers.bib import Biblio
from papers.utils import PapersExit

from tests import TEST_DEFAULT_POOL
from tests.common import paperscmd, ConfigTest

ENTRY = """@article{someone2000,
 author = {Some One},
 title = {Interesting Stuff},
 year = {2000}
}
"""


class TestResolution(unittest.TestCase):
    """library configuration, then per-machine configuration, then default"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.temp_dir.name, CONFIG_FILE_LOCAL)
        json.dump({'bibtex': 'lib.bib', 'keyformat': {'template': '{author}'}, 'paths': 'absolute'},
                  open(self.file, 'w'))
        self.machine = MachineConfig(os.path.join(self.temp_dir.name, 'machine.json'),
                                     {'editor': 'vim', 'keyformat': {'template': '{year}'},
                                      'nameformat': {'template': '{title}'}, 'paths': 'relative'})

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_order(self):
        config = Config.load(self.file, machine=self.machine)
        self.assertEqual(config.keyformat.template, '{author}')
        self.assertEqual(config.source('key.template'), 'library')
        self.assertTrue(config.absolute_paths)
        self.assertEqual(config.source('paths'), 'library')
        self.assertEqual(config.nameformat.template, '{title}')
        self.assertEqual(config.source('name.template'), 'machine')
        self.assertEqual(config.editor, 'vim')
        self.assertEqual(config.source('editor'), 'machine')
        self.assertEqual(config.nameformat.author_num, papers.filename.NAMEFORMAT.author_num)
        self.assertEqual(config.source('name.author-num'), 'default')
        self.assertEqual(config.pools, ['default'])
        self.assertEqual(config.source('pools'), 'default')

    def test_save_keeps_inherited_settings_out(self):
        config = Config.load(self.file, machine=self.machine)
        config.save()
        js = json.load(open(self.file))
        self.assertEqual(js['keyformat'], {'template': '{author}'})
        self.assertNotIn('nameformat', js)
        self.assertNotIn('editor', js)
        # a changed setting is saved
        config.nameformat.author_num = 1
        config.save()
        self.assertEqual(json.load(open(self.file))['nameformat'], {'author_num': 1})

    def test_unset(self):
        config = Config.load(self.file, machine=self.machine)
        config.unset('key.template')
        self.assertEqual(config.keyformat.template, '{year}')
        self.assertEqual(config.source('key.template'), 'machine')
        config.save()
        self.assertNotIn('keyformat', json.load(open(self.file)))

    def test_v2_local_config(self):
        # files of v2 store absolute_paths, backup_files and full formats
        json.dump({'bibtex': 'lib.bib', 'local': True, 'absolute_paths': True, 'backup_files': True,
                   'git': True, 'nameformat': {'template': '{author}', 'author_num': 3}},
                  open(self.file, 'w'))
        config = Config.load(self.file, machine=self.machine)
        self.assertEqual(config.get('paths'), 'absolute')
        self.assertTrue(config.gitlfs)
        self.assertEqual(config.nameformat.author_num, 3)
        config.save()
        js = json.load(open(self.file))
        self.assertEqual(js['paths'], 'absolute')
        self.assertNotIn('absolute_paths', js)
        self.assertTrue(js['gitlfs'])
        self.assertEqual(js['version'], 3)


class TestFormatVersion(unittest.TestCase):
    """configuration files written by v3 carry "version": 3"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.temp_dir.name, CONFIG_FILE_LOCAL)
        self.machine = MachineConfig(os.path.join(self.temp_dir.name, 'machine.json'))

    def tearDown(self):
        self.temp_dir.cleanup()

    def write(self, js, file=None):
        json.dump(js, open(file or self.file, 'w'))

    def test_written(self):
        self.write({'bibtex': 'lib.bib'})
        Config.load(self.file, machine=self.machine).save()
        self.assertEqual(json.load(open(self.file))['version'], 3)
        self.machine.set('editor', 'vim')
        self.machine.save()
        self.assertEqual(json.load(open(self.machine.file)), {'editor': 'vim', 'version': 3})
        # not a setting
        self.assertNotIn('version', MachineConfig.load(self.machine.file).data)

    def test_v3_ignores_v2_settings(self):
        # absolute_paths, backup_files and local are only read from files of v2
        self.write({'bibtex': 'lib.bib', 'version': 3, 'absolute_paths': True,
                    'backup_files': True, 'local': False})
        config = Config.load(self.file, machine=self.machine)
        self.assertTrue(config.local)
        self.assertEqual(config.get('paths'), 'relative')
        self.assertFalse(config.gitlfs)
        self.write({'bibtex': 'lib.bib', 'absolute_paths': True, 'backup_files': True})
        config = Config.load(self.file, machine=self.machine)
        self.assertEqual(config.get('paths'), 'absolute')
        self.assertTrue(config.gitlfs)

    def test_newer_version(self):
        self.write({'bibtex': 'lib.bib', 'version': 4})
        with self.assertRaisesRegex(PapersExit, 'newer papers'):
            Config.load(self.file, machine=self.machine)
        self.write({'version': 4}, self.machine.file)
        with self.assertRaisesRegex(PapersExit, 'newer papers'):
            MachineConfig.load(self.machine.file)

    def test_newer_version_command(self):
        self.write({'bibtex': 'lib.bib', 'version': 4})
        with self.assertRaises(PapersExit):
            paperscmd('status', cwd=self.temp_dir.name)


class TestInit(ConfigTest):

    def test_init(self):
        self.papers('init --no-git')
        js = self.json()
        self.assertEqual(js['bibtex'], 'papers.bib')
        self.assertEqual(js['filesdir'], 'files')
        self.assertEqual(js['pools'], ['default'])
        self.assertEqual(js['paths'], 'relative')
        self.assertFalse(js['git'])
        self.assertNotIn('nameformat', js)  # inherited
        self.assertTrue(os.path.isfile(self.path('papers.bib')))
        self.assertTrue(os.path.isdir(self.path('files')))

    def test_init_options(self):
        self.papers('init --no-git --bibtex refs.bib --filesdir pdfs --pool default ../shared '
                    '--paths absolute --name-template "{author}_{year}" --key-author-num 1')
        js = self.json()
        self.assertEqual(js['bibtex'], 'refs.bib')
        self.assertEqual(js['filesdir'], 'pdfs')
        self.assertEqual(js['pools'], ['default', '../shared'])
        self.assertEqual(js['paths'], 'absolute')
        self.assertEqual(js['nameformat'], {'template': '{author}_{year}'})
        self.assertEqual(js['keyformat'], {'author_num': 1})

    def test_init_git(self):
        self.papers('init --git')
        config = Config.load(self.path(CONFIG_FILE_LOCAL))
        self.assertTrue(config.git)
        self.assertTrue(os.path.isdir(os.path.join(config.gitdir, '.git')))

    def test_init_machine_defaults(self):
        self.papers('config --machine git false')
        self.papers('config --machine paths absolute')
        self.papers('init')
        js = self.json()
        self.assertFalse(js['git'])
        self.assertEqual(js['paths'], 'absolute')

    def test_init_existing(self):
        self.papers('init --no-git')
        with self.assertRaises(PapersExit):
            self.papers('init --no-git')

    def test_init_dir(self):
        cwd = os.getcwd()
        self.papers('init --no-git lib/sub')
        self.assertEqual(os.getcwd(), cwd)
        self.assertEqual(self.json('lib', 'sub')['bibtex'], 'papers.bib')
        self.assertTrue(os.path.isfile(self.path('lib', 'sub', 'papers.bib')))
        self.assertTrue(os.path.isdir(self.path('lib', 'sub', 'files')))
        self.assertFalse(os.path.exists(self.path(CONFIG_FILE_LOCAL)))
        with self.assertRaises(PapersExit):
            self.papers('init --no-git lib/sub')
        # an existing directory; --bibtex and --filesdir are relative to it
        self.papers('init --no-git lib --bibtex refs.bib --filesdir pdfs')
        js = self.json('lib')
        self.assertEqual((js['bibtex'], js['filesdir']), ('refs.bib', 'pdfs'))
        self.assertTrue(os.path.isfile(self.path('lib', 'refs.bib')))

    def test_relative_paths_by_default(self):
        self.papers('init --no-git')
        Path(self.path('a.pdf')).write_text('pdf')
        Path(self.path('a.bib')).write_text(ENTRY.replace('year', f'file = {{:{self.path("a.pdf")}:pdf}},\n year'))
        self.papers('add a.bib')
        biblio = Biblio.load(self.path('papers.bib'), '')
        self.assertEqual(biblio.entries[0]['file'], ':a.pdf:pdf')


class TestDirectoryOption(ConfigTest):

    def test_C(self):
        os.makedirs(self.path('lib'))
        cwd = os.getcwd()
        self.papers(f'-C {self.path("lib")} init --no-git', cwd=cwd)
        self.assertEqual(os.getcwd(), cwd)
        self.assertTrue(os.path.exists(self.path('lib', CONFIG_FILE_LOCAL)))
        out = self.papers('-C lib config bibtex', sp_cmd='check_output')
        self.assertEqual(out, self.path('lib', 'papers.bib'))
        # several -C combine
        os.makedirs(self.path('lib', 'sub'))
        out = self.papers('-C lib -C sub status', sp_cmd='check_output')
        self.assertIn(self.path('lib'), out)

    def test_C_missing(self):
        with self.assertRaises(PapersExit):
            self.papers('-C missing status')


class TestDefaultPool(ConfigTest):

    def test_outside_library(self):
        os.makedirs(TEST_DEFAULT_POOL)
        self.papers('init --no-git', cwd=TEST_DEFAULT_POOL)
        Path(self.path('a.bib')).write_text(ENTRY)
        self.papers('add a.bib')
        self.assertFalse(os.path.exists(self.path('papers.bib')))
        biblio = Biblio.load(os.path.join(TEST_DEFAULT_POOL, 'papers.bib'), '')
        self.assertEqual([e['ID'] for e in biblio.entries], ['someone2000'])
        out = self.papers('status', sp_cmd='check_output')
        self.assertIn('(default pool)', out)
        # never uninstalled from outside
        with self.assertRaises(PapersExit):
            self.papers('uninstall')

    def test_no_library(self):
        Path(self.path('a.bib')).write_text(ENTRY)
        with self.assertRaises(PapersExit):
            self.papers('add a.bib')
        with self.assertRaises(PapersExit):
            self.papers('config bibtex')
        out = self.papers('status', sp_cmd='check_output')
        self.assertIn('papers init', out)
        self.assertIn(f'`papers init {papers.config.short_home(TEST_DEFAULT_POOL)}`', out)
        # the hint works
        self.papers(f'init --no-git {TEST_DEFAULT_POOL}')
        self.assertIn('(default pool)', self.papers('status', sp_cmd='check_output'))

    def test_builtin_default(self):
        # without per-machine configuration
        machine = MachineConfig.load(os.path.join(self.dir, 'none.json'))
        self.assertEqual(machine.pool_path('default'), TEST_DEFAULT_POOL)
        self.assertEqual(Config(machine=machine).pools, ['default'])

    def test_library_takes_precedence(self):
        os.makedirs(TEST_DEFAULT_POOL)
        self.papers('init --no-git', cwd=TEST_DEFAULT_POOL)
        self.papers('init --no-git --bibtex here.bib')
        Path(self.path('a.bib')).write_text(ENTRY)
        self.papers('add a.bib')
        self.assertEqual(len(Biblio.load(self.path('here.bib'), '').entries), 1)
        self.assertEqual(len(Biblio.load(os.path.join(TEST_DEFAULT_POOL, 'papers.bib'), '').entries), 0)


class TestConfigCommand(ConfigTest):

    def setUp(self):
        super().setUp()
        self.papers('init --no-git')

    def get(self, cmd):
        return self.papers('config ' + cmd, sp_cmd='check_output')

    def test_get_set_unset(self):
        self.assertEqual(self.get('name.template'), papers.filename.NAMEFORMAT.template)
        self.papers('config name.template "{author}_{year}"')
        self.assertEqual(self.json()['nameformat'], {'template': '{author}_{year}'})
        self.assertEqual(self.get('name.template'), '{author}_{year}')
        self.papers('config --unset name.template')
        self.assertNotIn('nameformat', self.json())
        self.assertEqual(self.get('name.template'), papers.filename.NAMEFORMAT.template)

    def test_types(self):
        self.papers('config name.author-num 3')
        self.assertEqual(self.json()['nameformat'], {'author_num': 3})
        self.papers('config paths absolute')
        self.assertEqual(self.json()['paths'], 'absolute')
        self.papers('config pools default ../shared')
        self.assertEqual(self.json()['pools'], ['default', '../shared'])
        self.assertEqual(self.get('pools'), 'default ../shared')
        self.papers('config editor "subl -w"')
        self.assertEqual(self.json()['editor'], 'subl -w')
        self.papers('config filesdir pdfs')
        self.assertEqual(self.json()['filesdir'], 'pdfs')

    def test_paths_are_absolute(self):
        # stored relative to the library, printed absolute (from anywhere)
        os.makedirs(self.path('sub'))
        self.papers('config bibtex refs.bib', cwd=self.path('sub'))
        self.assertEqual(self.json()['bibtex'], 'sub/refs.bib')
        self.assertEqual(self.get('bibtex'), self.path('sub', 'refs.bib'))
        out = self.papers('config filesdir', cwd=self.path('sub'), sp_cmd='check_output')
        self.assertEqual(out, self.path('files'))
        lines = {line.split('=')[0].strip(): line for line in self.get('').splitlines()[1:]}
        self.assertEqual(lines['bibtex'].split('=', 1)[1].strip(), self.path('sub', 'refs.bib') + '  (library)')
        self.assertEqual(lines['filesdir'].split('=', 1)[1].strip(), self.path('files') + '  (library)')

    def test_paths_converts_links(self):
        Path(self.path('a.pdf')).write_text('pdf')
        Path(self.path('papers.bib')).write_text(
            ENTRY.replace('year', f'file = {{:{self.path("a.pdf")}:pdf}},\n year'))
        self.papers('config paths relative')
        self.assertEqual(Biblio.load(self.path('papers.bib'), '').entries[0]['file'], ':a.pdf:pdf')
        self.papers('config paths absolute')
        self.assertEqual(Biblio.load(self.path('papers.bib'), '').entries[0]['file'], f':{self.path("a.pdf")}:pdf')

    def test_list(self):
        self.papers('config --machine editor vim')
        out = self.get('')
        self.assertIn('bibtex', out)
        lines = {line.split('=')[0].strip(): line for line in out.splitlines()[1:]}
        self.assertTrue(lines['bibtex'].endswith('(library)'))
        self.assertTrue(lines['editor'].endswith('(machine)'))
        self.assertTrue(lines['name.template'].endswith('(default)'))

    def test_machine(self):
        self.papers('config --machine name.template "{year}"')
        self.assertEqual(self.get('name.template'), '{year}')
        self.assertEqual(self.get('--machine name.template'), '{year}')
        self.papers('config --global pools.teaching /mnt/teaching')
        machine = MachineConfig.load()
        self.assertEqual(machine.pool_path('teaching'), '/mnt/teaching')
        self.assertIn('pools.teaching = /mnt/teaching', self.get('--machine'))
        self.papers('config --machine --unset pools.teaching')
        self.assertNotIn('teaching', MachineConfig.load().pools)
        # the library does not change
        self.assertNotIn('nameformat', self.json())

    def test_errors(self):
        for cmd in ['light true', 'foo bar', 'git maybe', 'name.author-num x',
                    'paths sometimes', 'git true false',
                    '--machine bibtex x.bib', '--machine pools default']:
            with self.assertRaises(PapersExit, msg=cmd):
                self.papers('config ' + cmd)

    def test_git(self):
        self.papers('config git true')
        config = Config.load(self.path(CONFIG_FILE_LOCAL))
        self.assertTrue(config.git)
        self.assertTrue(os.path.isdir(os.path.join(config.gitdir, '.git')))
        count = self.papers('git rev-list --all --count', sp_cmd='check_output')
        self.assertEqual(count, '1')
        self.papers('config git false')
        self.assertFalse(self.json()['git'])


class TestMigrateV2Global(ConfigTest):

    def setUp(self):
        super().setUp()
        os.makedirs(self.path('lib'))
        Path(self.path('lib', 'a.pdf')).write_text('pdf')
        Path(self.path('lib', 'lib.bib')).write_text(
            ENTRY.replace('year', f'file = {{:{self.path("lib", "a.pdf")}:pdf}},\n year'))
        json.dump({'bibtex': self.path('lib', 'lib.bib'), 'filesdir': self.path('lib', 'pdfs'),
                   'local': False, 'absolute_paths': True, 'git': False, 'gitlfs': False,
                   'editor': 'nano', 'nameformat': {'template': '{author}-{year}'}},
                  open(CONFIG_FILE, 'w'))
        os.makedirs(self.path('elsewhere'))
        # no per-machine configuration yet
        os.remove(papers.config.MACHINE_CONFIG_FILE)

    def tearDown(self):
        for f in [CONFIG_FILE, CONFIG_FILE + '.v2.bak']:
            if os.path.exists(f):
                os.remove(f)
        super().tearDown()

    def test_still_used_before_migration(self):
        with self.assertLogs(papers.logger, level='WARNING') as cm:
            out = self.papers('list --key-only', cwd=self.path('elsewhere'), sp_cmd='check_output')
        self.assertEqual(out, 'someone2000')
        self.assertTrue(any('papers migrate' in line for line in cm.output))

    def test_migrate(self):
        out = self.papers('migrate', sp_cmd='check_output')
        self.assertIn('create the library configuration', out)
        self.assertFalse(os.path.exists(CONFIG_FILE))
        self.assertTrue(os.path.exists(CONFIG_FILE + '.v2.bak'))
        js = self.json('lib')
        self.assertEqual(js['bibtex'], 'lib.bib')
        self.assertEqual(js['filesdir'], 'pdfs')
        self.assertEqual(js['paths'], 'absolute')
        self.assertEqual(js['editor'], 'nano')
        self.assertEqual(js['nameformat'], {'template': '{author}-{year}'})
        self.assertEqual(js['pools'], ['default'])
        self.assertNotIn('local', js)
        self.assertEqual(MachineConfig.load().pool_path('default'), self.path('lib'))
        # the library is now the default pool
        out = self.papers('status', cwd=self.path('elsewhere'), sp_cmd='check_output')
        self.assertIn('(default pool)', out)
        # idempotent
        out = self.papers('migrate', sp_cmd='check_output')
        self.assertIn('nothing to migrate', out)
        self.assertEqual(self.json('lib'), js)

    def test_migrate_relative(self):
        self.papers('migrate --relative')
        self.assertEqual(self.json('lib')['paths'], 'relative')
        biblio = Biblio.load(self.path('lib', 'lib.bib'), '')
        self.assertEqual(biblio.entries[0]['file'], ':a.pdf:pdf')

    def test_existing_library_config_is_kept(self):
        self.papers('init --no-git --bibtex lib.bib', cwd=self.path('lib'))
        js = self.json('lib')
        out = self.papers('migrate', sp_cmd='check_output')
        self.assertIn('already exists', out)
        self.assertEqual(self.json('lib'), js)
        self.assertFalse(os.path.exists(CONFIG_FILE))

    def test_other_default_pool_is_kept(self):
        self.papers('config --machine pools.default /some/where')
        out = self.papers('migrate', sp_cmd='check_output')
        self.assertIn('not changed', out)
        self.assertEqual(MachineConfig.load().pool_path('default'), '/some/where')

    def test_install_global_migrates(self):
        # install --global performs the migration of the v2 global configuration
        self.papers('install --global --no-prompt --no-git', cwd=self.path('elsewhere'))
        self.assertFalse(os.path.exists(CONFIG_FILE))
        self.assertTrue(os.path.exists(CONFIG_FILE + '.v2.bak'))
        js = self.json('lib')
        self.assertEqual(js['bibtex'], 'lib.bib')
        self.assertEqual(js['editor'], 'nano')
        self.assertEqual(js['nameformat'], {'template': '{author}-{year}'})
        self.assertEqual(MachineConfig.load().pool_path('default'), self.path('lib'))
        # no more warning about the v2 configuration
        with self.assertNoLogs(papers.logger, level='WARNING'):
            out = self.papers('status', cwd=self.path('elsewhere'), sp_cmd='check_output')
        self.assertIn('(default pool)', out)


class TestMigrateFolders(ConfigTest):

    def test_folders(self):
        self.papers('init --no-git')
        biblio = Biblio(filesdir=self.path('files'))
        name = biblio.nameformat(Biblio.load(self._entry_bib(), '').entries[0])
        folder = self.path('files', name)
        os.makedirs(folder)
        for f in [f'{name}.pdf', 'si.pdf']:
            Path(folder, f).write_text(f)
        Path(folder, f'.{name}.bib').write_text(ENTRY)
        entry = ENTRY.replace('year', f'file = {{:files/{name}/{name}.pdf:pdf;:files/{name}/si.pdf:pdf}},\n year')
        flat = ENTRY.replace('someone2000', 'flat2000').replace('Some One', 'Other One')
        Path(self.path('flat.pdf')).write_text('flat')
        flat = flat.replace('year', 'file = {:flat.pdf:pdf},\n year')
        Path(self.path('papers.bib')).write_text(entry + '\n' + flat)

        out = self.papers('migrate --folders', sp_cmd='check_output')
        self.assertIn('1 entries moved', out)
        biblio = Biblio.load(self.path('papers.bib'), '')
        files = {e['ID']: e['file'] for e in biblio.entries}
        self.assertEqual(files['someone2000'], f':files/{name}.pdf:pdf;:files/{name}--si.pdf:pdf')
        self.assertEqual(files['flat2000'], ':flat.pdf:pdf')  # not in a folder: untouched
        self.assertFalse(os.path.exists(folder))

    def _entry_bib(self):
        Path(self.path('entry.bib')).write_text(ENTRY)
        return self.path('entry.bib')
