"""Tests of the rules of design/library.md that no other test checks: one
class per section of the specification, each test naming its section."""
import json
import os
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import papers.config
import papers.lock
from papers.bib import Biblio
from papers.config import CONFIG_FILE_LOCAL, Config, MachineConfig, SETTINGS
from papers.filename import Format, make_template_fields, slugify
from papers.lock import LockError
from papers.utils import PapersExit

from tests.common import ConfigTest, FileTest, entry


def config_text(path):
    "the text of a configuration file, as bytes"
    return Path(path).read_bytes()


class TestLayout(ConfigTest):
    "library.md, Layout"

    def test_papers_folder_of_the_library_directory(self):
        """library.md Layout: config.json, lock, files.json, distinct.json and
        origin/ are in the .papers folder of the library directory, also when
        the bibtex is in another folder"""
        self.papers('init lib --bibtex lib/bib/papers.bib')
        Path(self.path('a.pdf')).write_text('pdf')
        Path(self.path('a.bib')).write_text(entry('one2000', self.path('a.pdf')))
        self.papers('add ../a.bib', cwd=self.path('lib'))
        config = Config.load(self.path('lib', CONFIG_FILE_LOCAL))
        self.assertEqual(papers.lock.lock_path(config), self.path('lib', '.papers', 'lock'))
        self.assertTrue(os.path.isfile(self.path('lib', '.papers', 'files.json')))
        self.assertFalse(os.path.exists(self.path('lib', 'bib', '.papers')))

    def test_no_move_with_dry_run(self):
        """library.md Layout: the files of the .papers/ next to the bibtex are
        not moved by a dry run"""
        # bug: the command line loads the configuration (and moves the files,
        # papers.config.move_papers_files) before it sets papers.config.DRYRUN
        self.papers('init lib --bibtex lib/bib/papers.bib')
        os.makedirs(self.path('lib', 'bib', '.papers'))
        Path(self.path('lib', 'bib', '.papers', 'distinct.json')).write_text('{"distinct": []}\n')
        self.papers('list --dry-run', cwd=self.path('lib'))
        papers.config.DRYRUN = False
        self.assertTrue(os.path.exists(self.path('lib', 'bib', '.papers', 'distinct.json')))
        self.assertFalse(os.path.exists(self.path('lib', '.papers', 'distinct.json')))


class TestConfigurationFormat(ConfigTest):
    "library.md, The library configuration: Format"

    def test_written_format(self):
        """library.md Format: keys sorted, indent of two spaces, separators
        `,` and `: `, LF, no final newline, ASCII with \\uXXXX escapes"""
        self.papers('init lib')
        self.papers('config editor "édit -w"', cwd=self.path('lib'))
        data = config_text(self.path('lib', CONFIG_FILE_LOCAL))
        js = json.loads(data)
        self.assertEqual(data.decode('ascii'),
                         json.dumps(js, sort_keys=True, indent=2, separators=(',', ': ')))
        self.assertIn(b'"editor": "\\u00e9dit -w"', data)
        self.assertNotIn(b'\r', data)
        self.assertFalse(data.endswith(b'\n'))
        self.assertTrue(data.startswith(b'{\n  "'))

    def test_read_as_utf8(self):
        """library.md Format: readers accept any JSON formatting and UTF-8
        text (a byte order mark is ignored)"""
        os.makedirs(self.path('lib', '.papers'))
        Path(self.path('lib', CONFIG_FILE_LOCAL)).write_bytes(
            '﻿{"version":3,"bibtex":"réf.bib","editor":"é","filesdir":null}'.encode('utf-8'))
        config = Config.load(self.path('lib', CONFIG_FILE_LOCAL))
        self.assertEqual(config.editor, 'é')
        self.assertEqual(config.bibtex, self.path('lib', 'réf.bib'))


class TestConfigurationKeys(ConfigTest):
    "library.md, The library configuration: Keys"

    FORMAT_KEYS = [('template', 'template', '{year}', '{year}'), ('author-num', 'author_num', '3', 3),
                   ('author-sep', 'author_sep', '+', '+'), ('title-word-num', 'title_word_num', '4', 4),
                   ('title-word-size', 'title_word_size', '2', 2), ('title-length', 'title_length', '30', 30),
                   ('title-sep', 'title_sep', '+', '+'), ('unknown-template', 'unknown_template', 'x{year}', 'x{year}'),
                   ('unknown-strict', 'unknown_strict', 'true', True)]

    def test_format_keys(self):
        """library.md Keys: each name.* and key.* setting is a member of
        nameformat or keyformat, with underscores, of the type of the table"""
        self.papers('init lib')
        for kind, group in (('name', 'nameformat'), ('key', 'keyformat')):
            for setting, key, value, written in self.FORMAT_KEYS:
                with self.subTest(setting=f'{kind}.{setting}'):
                    self.papers(f'config {kind}.{setting} "{value}"', cwd=self.path('lib'))
                    self.assertIs(type(self.json('lib')[group][key]), type(written))
                    self.assertEqual(self.json('lib')[group][key], written)
        self.assertEqual(len(self.json('lib')['nameformat']), 9)

    def test_other_keys(self):
        """library.md Keys: the other JSON keys are the setting names, with
        hyphens, and the values of the types of the table"""
        self.papers('init lib')
        for name, value, written in [('paths', 'absolute', 'absolute'), ('files', 'copy', 'copy'),
                                     ('auto-push', 'yes', True), ('editor', 'vim', 'vim'),
                                     ('checksums', 'off', False), ('history-size', '12', 12),
                                     ('history-separate', 'true', True)]:
            with self.subTest(name=name):
                self.papers(f'config {name} {value}', cwd=self.path('lib'))
                self.assertIs(type(self.json('lib')[name]), type(written))
                self.assertEqual(self.json('lib')[name], written)


class TestWrittenKeys(ConfigTest):
    "library.md, The library configuration: Which keys papers writes"

    def test_paths_written_as_null(self):
        """library.md Which keys papers writes: bibtex and filesdir are always
        written, as null when unset; version is always 3"""
        self.papers('init lib')
        self.papers('config --unset filesdir', cwd=self.path('lib'))
        js = self.json('lib')
        self.assertIn('filesdir', js)
        self.assertIsNone(js['filesdir'])
        self.assertEqual(js['version'], 3)

    def test_init_writes_pool_and_paths(self):
        """library.md Which keys papers writes: papers init writes pool (none)
        and paths, and no other setting it was not given"""
        self.papers('init lib --editor vim')
        js = self.json('lib')
        self.assertEqual(set(js), {'bibtex', 'filesdir', 'pool', 'paths', 'editor', 'version'})
        self.assertEqual((js['pool'], js['paths'], js['editor']), ('none', 'relative', 'vim'))

    def test_prune_removes_the_settings_of_papers_2(self):
        """library.md Which keys papers writes: `papers config --prune` removes
        the keys of the settings of papers 2 (git, gitlfs, backup_files,
        gitdir, trash-days, trash-size)"""
        # bug: --prune says it removed gitlfs and gitdir, but the file keeps
        # them, since the save keeps the keys papers does not know (5bf7022)
        self.papers('init lib')
        js = self.json('lib')
        js.update(git=True, gitlfs=False, gitdir='.papers', backup_files=False)
        Path(self.path('lib', CONFIG_FILE_LOCAL)).write_text(json.dumps(js))
        out = self.papers('config --prune', cwd=self.path('lib'), sp_cmd='check_output')
        for key in ('git', 'gitlfs', 'gitdir', 'backup_files'):
            self.assertIn(key, out)
        js = self.json('lib')
        for key in ('git', 'gitlfs', 'gitdir', 'backup_files'):
            self.assertNotIn(key, js)


class TestReading(ConfigTest):
    "library.md, The library configuration: Reading"

    def write(self, js):
        os.makedirs(self.path('lib', '.papers'), exist_ok=True)
        Path(self.path('lib', CONFIG_FILE_LOCAL)).write_text(json.dumps(js))
        return self.path('lib', CONFIG_FILE_LOCAL)

    def test_unknown_pool_name(self):
        """library.md Reading 4: a pools item that is an unknown pool name is
        a warning, and the library has no pool"""
        file = self.write({'bibtex': 'papers.bib', 'version': 3, 'pools': ['nowhere']})
        with self.assertLogs(papers.logger, level='WARNING') as logs:
            config = Config.load(file, machine=MachineConfig(self.path('machine.json')))
        self.assertIn('unknown pool name nowhere', logs.output[0])
        self.assertFalse(config.has_pool())

    def test_pools_item_that_is_a_path(self):
        """library.md Reading 4: a pools item with a path separator, or
        starting with `.` or `~`, is the pool path; none is no pool"""
        machine = MachineConfig(self.path('machine.json'))
        for item, pool in [('../a', '../a'), ('~/a', '~/a'), ('.hidden', '.hidden'), ('x/y', 'x/y'),
                           ('none', 'none')]:
            with self.subTest(item=item):
                config = Config.load(self.write({'bibtex': 'papers.bib', 'version': 3, 'pools': [item, 'other']}),
                                     machine=machine)
                self.assertEqual(config.pool, pool)

    def test_null_is_unset(self):
        """library.md Reading 6: a setting present with the value null is not
        set (the inherited value applies)"""
        machine = MachineConfig(self.path('machine.json'), {'editor': 'vim'})
        config = Config.load(self.write({'bibtex': 'papers.bib', 'version': 3, 'editor': None}), machine=machine)
        self.assertEqual(config.editor, 'vim')
        self.assertEqual(config.source('editor'), 'global')


class TestIdField(FileTest):
    "library.md, The library configuration: The id field"

    def test_no_id_with_dry_run(self):
        """library.md The id field: with --dry-run, no id is created"""
        Path(self.path('a.bib')).write_text(entry('one2000'))
        self.lib('add ../a.bib --dry-run')
        papers.config.DRYRUN = False
        self.assertNotIn('id', self.json('lib'))

    def test_id_is_a_uuid4(self):
        """library.md The id field: 32 lowercase hexadecimal characters, a
        random UUID version 4 without dashes"""
        import uuid
        Path(self.path('a.bib')).write_text(entry('one2000'))
        self.lib('add ../a.bib')
        id = self.json('lib')['id']
        self.assertRegex(id, '^[0-9a-f]{32}$')
        self.assertEqual(uuid.UUID(hex=id).version, 4)


class TestRelativePaths(ConfigTest):
    "library.md, The library configuration: Relative paths"

    def test_symbolic_links(self):
        """library.md Relative paths: a relative bibtex is joined to the
        library directory with its symbolic links resolved, then normalised
        lexically (a symbolic link inside the path is kept)"""
        self.papers('init real')
        os.symlink(self.path('real'), self.path('link'))
        os.makedirs(self.path('real', 'sub'))
        os.symlink(self.path('real', 'sub'), self.path('real', 'sublink'))
        js = self.json('real')
        js['bibtex'] = 'sublink/../sublink/refs.bib'
        Path(self.path('real', CONFIG_FILE_LOCAL)).write_text(json.dumps(js))
        config = Config.load(self.path('link', CONFIG_FILE_LOCAL))
        self.assertEqual(config.bibtex, self.path('real', 'sublink', 'refs.bib'))

    def test_absolute_stays_absolute(self):
        """library.md Relative paths: an absolute bibtex or filesdir stays
        absolute when read"""
        self.papers('init lib')
        js = self.json('lib')
        js['filesdir'] = self.path('elsewhere')
        Path(self.path('lib', CONFIG_FILE_LOCAL)).write_text(json.dumps(js))
        self.assertEqual(Config.load(self.path('lib', CONFIG_FILE_LOCAL)).filesdir, self.path('elsewhere'))

    def test_pool_resolved_against_the_library(self):
        """library.md Relative paths: a relative pool is joined to the library
        directory; a leading ~ is the home directory"""
        self.papers('init lib')
        for pool, path in [('../pool', self.path('pool')), ('~/pool', os.path.join(os.path.expanduser('~'), 'pool'))]:
            js = self.json('lib')
            js['pool'] = pool
            Path(self.path('lib', CONFIG_FILE_LOCAL)).write_text(json.dumps(js))
            self.assertEqual(Config.load(self.path('lib', CONFIG_FILE_LOCAL)).pool_path(), path)


class TestMachineConfiguration(ConfigTest):
    "library.md, The machine configuration"

    @unittest.skipUnless(sys.platform.startswith('linux'), 'the locations of Linux')
    def test_location(self):
        """library.md The machine configuration, Location: $XDG_CONFIG_HOME/papers/config.json
        on Linux; data $XDG_DATA_HOME/papers, cache $XDG_CACHE_HOME/papers"""
        self.assertEqual(papers.config.MACHINE_CONFIG_FILE,
                         os.path.join(os.environ['XDG_CONFIG_HOME'], 'papers', 'config.json'))
        self.assertEqual(papers.config.DATA_DIR, os.path.join(os.environ['XDG_DATA_HOME'], 'papers'))
        self.assertEqual(papers.config.HISTORY_DIR, os.path.join(os.environ['XDG_DATA_HOME'], 'papers', 'history'))
        self.assertEqual(papers.config.CACHE_DIR, os.path.join(os.environ['XDG_CACHE_HOME'], 'papers'))

    def test_written_format(self):
        """library.md The machine configuration, Format: written whole, with
        version 3, in the format of the library configuration; keys papers
        does not know are kept"""
        file = self.path('machine.json')
        Path(file).write_text(json.dumps({'future': {'a': 1}, 'editor': 'vi'}))
        machine = MachineConfig.load(file)
        machine.set('editor', 'é')
        machine.save()
        data = config_text(file)
        self.assertEqual(data.decode('ascii'), json.dumps({'editor': 'é', 'future': {'a': 1}, 'version': 3},
                                                          sort_keys=True, indent=2, separators=(',', ': ')))

    def test_default_written_with_home(self):
        """library.md The machine configuration, default: written with ~ for
        the home directory when under it"""
        home = os.path.expanduser('~')
        os.makedirs(os.path.join(home, 'lib'))
        try:
            self.papers('init', cwd=os.path.join(home, 'lib'))
            self.papers(f'config --global default {os.path.join(home, "lib")}')
            self.assertEqual(json.load(open(papers.config.MACHINE_CONFIG_FILE))['default'], '~/lib')
        finally:
            import shutil
            shutil.rmtree(os.path.join(home, 'lib'))

    def test_history_dir_written_absolute(self):
        """library.md The machine configuration: `config --global history-dir`
        writes the folder absolute (with ~), from a path relative to the
        current directory"""
        self.papers('config --global history-dir hist')
        self.assertEqual(json.load(open(papers.config.MACHINE_CONFIG_FILE))['history-dir'],
                         papers.config.short_home(self.path('hist')))


# the settings table of library.md: name -> built-in default
DEFAULTS = {
    'bibtex': None, 'filesdir': None, 'pool': 'none', 'paths': 'relative', 'files': 'move', 'auto-push': False,
    'editor': None, 'checksums': True, 'history-dir': None, 'history-size': 500, 'history-separate': False,
    'keep-deleted-files': True,
    'name.template': '{authorX}_{year}_{title}', 'name.author-num': 2, 'name.author-sep': '_',
    'name.title-word-num': 100, 'name.title-word-size': 1, 'name.title-length': 100, 'name.title-sep': '-',
    'name.unknown-template': 'unknown_{doi_or_id}', 'name.unknown-strict': False,
    'key.template': '{author}{year}', 'key.author-num': 2, 'key.author-sep': '_',
    'key.title-word-num': 100, 'key.title-word-size': 1, 'key.title-length': 100, 'key.title-sep': '-',
    'key.unknown-template': '{doi_}', 'key.unknown-strict': False,
}
# the type of each setting in the table: path, pool, bool, int, str, or the choices
TYPES = {'bibtex': 'path', 'filesdir': 'path', 'pool': 'pool', 'paths': ('relative', 'absolute'),
         'files': ('ask', 'move', 'copy', 'link'), 'auto-push': 'bool', 'editor': 'str', 'checksums': 'bool',
         'history-dir': 'str', 'history-size': 'int', 'history-separate': 'bool', 'keep-deleted-files': 'bool',
         **{f'{kind}.{field}': 'int' for kind in ('name', 'key')
            for field in ('author-num', 'title-word-num', 'title-word-size', 'title-length')},
         **{f'{kind}.{field}': 'str' for kind in ('name', 'key')
            for field in ('template', 'author-sep', 'title-sep', 'unknown-template')},
         **{f'{kind}.unknown-strict': 'bool' for kind in ('name', 'key')}}


class TestSettings(ConfigTest):
    "library.md, Settings"

    def test_table(self):
        """library.md Settings, Table: the settings, their types and their
        built-in defaults"""
        self.assertEqual(SETTINGS, TYPES)
        config = Config(machine=MachineConfig(self.path('none.json')))
        for name, value in DEFAULTS.items():
            with self.subTest(name=name):
                self.assertEqual(config.get(name), value)

    def test_where(self):
        """library.md Settings, Table: bibtex, filesdir and pool only in the
        library configuration; history-dir and keep-deleted-files only in the
        machine configuration"""
        self.papers('init lib')
        for name in ('bibtex', 'filesdir', 'pool'):
            with self.subTest(name=name), self.assertRaises(papers.utils.PapersExit):
                self.papers(f'config --global {name} x')
        for name, value in (('history-dir', 'x'), ('keep-deleted-files', 'false')):
            with self.subTest(name=name), self.assertRaises(papers.utils.PapersExit):
                self.papers(f'config {name} {value}', cwd=self.path('lib'))

    def test_command_line_first(self):
        """library.md Settings, Precedence: a command-line option wins over the
        library configuration, which wins over the machine configuration"""
        self.papers('config --global key.template "{year}"')
        self.papers('init lib --key-template "{author}"')
        Path(self.path('a.bib')).write_text(entry('one2000'))
        self.papers('add ../a.bib --update-key --key-template "k{year}"', cwd=self.path('lib'))
        self.papers('add --title "Another paper" --author "Two, Some" --year 2001', cwd=self.path('lib'))
        keys = [e.key for e in Biblio.load(self.path('lib', 'papers.bib'), '').entries]
        self.assertEqual(sorted(keys), ['k2000', 'two'])


class TestFindingTheLibrary(ConfigTest):
    "library.md, Finding the library of a command"

    def test_first_library_upwards(self):
        """library.md Finding the library 2: the first directory upwards that
        has a library configuration is the library (a library inside another)"""
        self.papers('init outer')
        self.papers('init outer/inner')
        os.makedirs(self.path('outer', 'inner', 'deep'))
        os.makedirs(self.path('outer', 'other'))
        out = self.papers('config bibtex', cwd=self.path('outer', 'inner', 'deep'), sp_cmd='check_output')
        self.assertEqual(out, self.path('outer', 'inner', 'papers.bib'))
        out = self.papers('config bibtex', cwd=self.path('outer', 'other'), sp_cmd='check_output')
        self.assertEqual(out, self.path('outer', 'papers.bib'))

    def test_root_never_searched(self):
        """library.md Finding the library 2: the filesystem root itself is
        never searched"""
        from papers.config import find_library_config
        with patch('papers.config.library_config_file', side_effect=lambda path: path) as found:
            self.assertEqual(find_library_config('/'), None)
        found.assert_not_called()

    def test_bibtex_of_the_library_from_elsewhere(self):
        """library.md Finding the library, --bibtex FILE: when the search from
        the directory of FILE finds a library whose bibtex is FILE, that
        library is used"""
        self.papers('init lib')
        Path(self.path('a.bib')).write_text(entry('one2000'))
        os.makedirs(self.path('elsewhere'))
        self.papers(f'add --bibtex {self.path("lib", "papers.bib")} ../a.bib', cwd=self.path('elsewhere'))
        self.assertRegex(self.json('lib')['id'], '^[0-9a-f]{32}$')  # the library's history
        self.assertEqual([e.key for e in Biblio.load(self.path('lib', 'papers.bib'), '').entries], ['one2000'])

    def test_bibtex_without_library(self):
        """library.md Finding the library, --bibtex FILE: another bibtex is a
        bibtex without library: the settings of the library found, no
        configuration written, no id, no lock, no files.json"""
        self.papers('init lib --key-template "k{year}"')
        js = self.json('lib')
        os.makedirs(self.path('loose'))
        Path(self.path('loose', 'refs.bib')).write_text('')
        Path(self.path('a.pdf')).write_text('pdf')
        Path(self.path('a.bib')).write_text(entry('one2000', self.path('a.pdf')))
        with patch('papers.lock.acquire') as acquire:
            self.papers('add --bibtex ../loose/refs.bib ../a.bib --update-key', cwd=self.path('lib'))
        for call in acquire.call_args_list:
            self.assertIsNone(papers.lock.lock_path(call.args[0]))
        self.assertEqual(self.json('lib'), js)
        self.assertEqual([e.key for e in Biblio.load(self.path('loose', 'refs.bib'), '').entries], ['k2000'])
        self.assertEqual(os.listdir(self.path('loose')), ['refs.bib'])
        self.assertFalse(os.path.exists(self.path('lib', '.papers', 'files.json')))

    def test_status_bibtex(self):
        "library.md Finding the library, --bibtex FILE: papers status too"
        self.papers('init lib')
        self.papers('init other --bibtex other/refs.bib')
        Path(self.path('other', 'refs.bib')).write_text(entry('one2000'))
        out = self.papers('status --bibtex ../other/refs.bib', cwd=self.path('lib'), sp_cmd='check_output')
        self.assertIn('refs.bib (1 entr', out)
        self.assertIn(self.path('other'), out)
        with self.assertRaises(PapersExit):
            self.papers(f'status --bibtex {self.path("missing.bib")}', cwd=self.path('lib'))


class TestPoolSetting(ConfigTest):
    "library.md, Pools and shallow libraries: The pool setting"

    def test_written_with_home(self):
        """library.md The pool setting: a path given absolute, outside the
        library, is written absolute with ~ for the home directory"""
        home = os.path.expanduser('~')
        try:
            self.papers(f'init {os.path.join(home, "pool")}')
            self.papers(f'init lib --pool {os.path.join(home, "pool")}')
            self.assertEqual(self.json('lib')['pool'], '~/pool')
        finally:
            import shutil
            shutil.rmtree(os.path.join(home, 'pool'))

    def test_inside_the_library(self):
        """library.md The pool setting: a path inside the library is written
        relative, starting with ./"""
        self.papers('init lib')
        self.papers('init lib/sub')
        self.papers(f'config pool {self.path("lib", "sub")}', cwd=self.path('lib'))
        self.assertEqual(self.json('lib')['pool'], './sub')
        self.papers('config pool sub', cwd=self.path('lib'))
        self.assertEqual(self.json('lib')['pool'], './sub')


class TestRulesOnThePool(ConfigTest):
    "library.md, Pools and shallow libraries: States, rules on the pool"

    def test_auto_push_warns(self):
        """library.md Rules on the pool: a configured pool that took a pool of
        its own since: the automatic push prints a warning, the command goes on"""
        self.papers('init top')
        self.papers('init pool')
        self.papers('init lib --pool pool')
        Path(self.path('a.bib')).write_text(entry('one2000'))
        self.papers('add ../a.bib', cwd=self.path('lib'))
        self.papers('config auto-push true', cwd=self.path('lib'))
        js = self.json('pool')
        js['pool'] = '../top'
        Path(self.path('pool', CONFIG_FILE_LOCAL)).write_text(json.dumps(js))
        with self.assertLogs(papers.logger, level='WARNING') as logs:
            self.papers('list --add-tag x', cwd=self.path('lib'))
        self.assertTrue(any('not pushed to the pool' in line and 'has a pool itself' in line
                            for line in logs.output), logs.output)
        biblio = Biblio.load(self.path('lib', 'papers.bib'), '')
        self.assertEqual(biblio.entries[0]['keywords'], 'x')


class TestTemplateSyntax(unittest.TestCase):
    "library.md, Name and key templates: Syntax"

    def test_literal_braces(self):
        """library.md Syntax: {{ and }} are literal braces"""
        self.assertEqual(Format('{{x}}_{year}', kind='key')({'year': '2020'}), '{x}_2020')


class TestPlaceholders(unittest.TestCase):
    "library.md, Name and key templates: Placeholders"

    def test_authors(self):
        """library.md Placeholders, Author names: the table of the author
        placeholders, with author-sep `_` and author-num 2"""
        cases = [
            ('Doe, John', dict(author='doe', Author='Doe', AUTHOR='DOE', AuthorX='Doe', authorX='doe')),
            ('Doe, John and Smith, Ann', dict(author='doe_smith', Author='Doe_Smith', AUTHOR='DOE_SMITH',
                                              AuthorX='Doe_and_Smith', authorX='doe_and_smith')),
            ('Doe, J. and Smith, A. and Lee, B.', dict(author='doe_smith', AuthorX='Doe_et_al', authorX='doe_et_al')),
            ('John {van der Berg}', dict(author='van-der-berg')),
            ('{Ocean and Ice Group} and Doe, J.', dict(author='ocean-and-ice-group_doe')),
            ('Müller, Hans', dict(author='muller', Author='Muller')),
        ]
        for author, expected in cases:
            fields = make_template_fields({'author': author})
            for name, value in expected.items():
                with self.subTest(author=author, placeholder=name):
                    self.assertEqual(fields[name], value)

    def test_missing_fields(self):
        """library.md Placeholders: a missing author is unknown, a missing year
        0000, a missing title, journal or doi empty"""
        fields = make_template_fields({'ID': 'Smith_2020'})
        self.assertEqual((fields['author'], fields['year'], fields['title'], fields['journal'], fields['doi']),
                         ('unknown', '0000', '', '', ''))

    def test_doi_placeholders(self):
        """library.md Placeholders, Other fields: doi path-safe, doi_
        slugified, doi_or_id the slugified doi or key"""
        fields = make_template_fields({'ID': 'Smith_2020', 'doi': '10.1000/ABC.d(1)'})
        self.assertEqual((fields['doi'], fields['doi_'], fields['doi_or_id']),
                         ('10.1000-ABC.d(1)', '10-1000-abc-d-1', '10-1000-abc-d-1'))
        self.assertEqual(make_template_fields({'ID': 'Smith_2020'})['doi_or_id'], 'smith-2020')

    def test_title_placeholders(self):
        """library.md Placeholders, Title: title and Title, the words of the
        slug joined with title-sep"""
        fields = make_template_fields({'title': 'The Ocean’s {CO2} uptake'}, title_sep='_')
        self.assertEqual((fields['title'], fields['Title']), ('the_oceans_co2_uptake', 'The_Oceans_Co2_Uptake'))
        self.assertEqual(make_template_fields({'title': 'A title'}, title_word_num=0)['title'], '')

    def test_slugify(self):
        """library.md Placeholders, Slugify: the examples, HTML entities, and
        the ASCII transliteration"""
        for text, slug in [('Müller', 'muller'), ("l'eau", 'l-eau'), ('10.1000/xyz(1)', '10-1000-xyz-1'),
                           ('1,000', '1000'), ('a,b', 'a-b'), ('ß', 'ss'), ('Œuvre', 'oeuvre'),
                           ('R&amp;D', 'r-d'), ('R&#38;D', 'r-d'), ('R&#x26;D', 'r-d'), ('--a--b--', 'a-b'),
                           ('Хрущёв', 'khrushchev'), ("it''s", 'it-s'), ('x_y', 'x-y')]:
            with self.subTest(text=text):
                self.assertEqual(slugify(text), slug)

    def test_ascii_table(self):
        """library.md Placeholders, Slugify: the table of bibtex.md 9.1, all scripts"""
        for text, slug in [('北京', 'beijing'), ('Αθήνα', 'athina'), ('한국어', 'hangugeo'), ('×', '')]:
            with self.subTest(text=text):
                self.assertEqual(slugify(text), slug)


class TestTemplateKeys(unittest.TestCase):
    "library.md, Name and key templates: Keys"

    def test_key_not_transformed(self):
        """library.md Keys: the key template decides the characters of the
        key; no path safety or file-name rule applies to keys"""
        fmt = Format('{journal}/{year}.', kind='key')
        self.assertEqual(fmt({'journal': 'a:b', 'year': '2000'}), 'a:b/2000.')


class TestFileNames(FileTest):
    "library.md, The files directory: File names"

    def test_extension(self):
        """library.md File names: <ext> is the part of the current name from
        the last dot of the base name, case kept; empty if none"""
        self.lib('config files move')
        self.lib('config name.template "{author}_{year}"')
        for key, name, new in [('a2000', 'paper.v2.PDF', 'one_2000.PDF'), ('b2001', 'notes', 'one_2001')]:
            src = self.write('src', name)
            Path(self.path('src', key + '.bib')).write_text(
                entry(key, src).replace('Some One', 'One, Some').replace('2000', key[1:]))
            self.lib(f'add ../src/{key}.bib')
            self.assertEqual(self.files(key), [self.path('lib', 'files', new)])


class TestLockFile(FileTest):
    "library.md, The lock: File"

    def tearDown(self):
        papers.lock.release_all()
        super().tearDown()

    def config(self):
        return Config.load(self.path('lib', CONFIG_FILE_LOCAL))

    def test_content(self):
        """library.md The lock, File: a JSON object with token (32 hexadecimal
        characters), pid, host and command"""
        papers.lock.acquire(self.config(), command='papers add x.pdf')
        content = json.loads(Path(self.path('lib', '.papers', 'lock')).read_text())
        self.assertEqual(set(content), {'token', 'pid', 'host', 'command'})
        self.assertRegex(content['token'], '^[0-9a-f]{32}$')
        self.assertEqual((content['pid'], content['host'], content['command']),
                         (os.getpid(), socket.gethostname(), 'papers add x.pdf'))

    def test_no_lock(self):
        """library.md The lock, File: a bibtex without library has no lock;
        nothing is locked with --dry-run"""
        config = self.config()
        config.file = None
        self.assertIsNone(papers.lock.lock_path(config))
        papers.config.DRYRUN = True
        try:
            papers.lock.acquire(self.config())
        finally:
            papers.config.DRYRUN = False
        self.assertFalse(os.path.exists(self.path('lib', '.papers', 'lock')))

    def test_dot_papers_created(self):
        """library.md The lock, File: .papers/ is created if missing"""
        Path(self.path('lib', '.papersconfig.json')).write_text(
            Path(self.path('lib', CONFIG_FILE_LOCAL)).read_text())
        import shutil
        shutil.rmtree(self.path('lib', '.papers'))
        papers.lock.acquire(Config.load(self.path('lib', '.papersconfig.json')))
        self.assertTrue(os.path.isfile(self.path('lib', '.papers', 'lock')))


class TestLockProtocol(FileTest):
    "library.md, The lock: Protocol"

    def tearDown(self):
        papers.lock.release_all()
        super().tearDown()

    def config(self):
        return Config.load(self.path('lib', CONFIG_FILE_LOCAL))

    def test_unreadable_lock_is_being_written(self):
        """library.md The lock, Acquire 2: a file that cannot be parsed counts
        as being written: not stale before LIFETIME"""
        lock = self.path('lib', '.papers', 'lock')
        Path(lock).write_text('{"tok')
        with patch('papers.lock.LIFETIME', 10), patch('papers.lock.WAIT', 0.3), self.assertRaises(LockError):
            papers.lock.acquire(self.config())
        self.assertEqual(Path(lock).read_text(), '{"tok')

    def test_check_recreates_a_removed_lock(self):
        """library.md The lock, Check before writing: no file (removed by a
        command that found it stale): the holder creates it again"""
        papers.lock.acquire(self.config())
        lock = self.path('lib', '.papers', 'lock')
        token = json.loads(Path(lock).read_text())['token']
        os.remove(lock)
        papers.lock.check(self.config())
        self.assertEqual(json.loads(Path(lock).read_text())['token'], token)

    def test_check_unreadable_goes_on(self):
        """library.md The lock, Check before writing: unreadable content: go
        on"""
        papers.lock.acquire(self.config())
        Path(self.path('lib', '.papers', 'lock')).write_text('')
        papers.lock.check(self.config())

    def test_values(self):
        """library.md The lock, Values: LIFETIME 10 s, REFRESH 2 s"""
        self.assertEqual((papers.lock.LIFETIME, papers.lock.REFRESH), (10, 2))


if __name__ == '__main__':
    unittest.main()
