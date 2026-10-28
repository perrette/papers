import os, json, re
import copy
from pathlib import Path
import platformdirs

from papers.entries import parse_string, get_entry_val, parse_file
from papers import logger
from papers.filename import NAMEFORMAT, KEYFORMAT
from papers import __version__
from papers.utils import bcolors, check_filesdir, PapersExit, write_atomic

DRYRUN = False

# platform-appropriate locations (on Linux these honor the XDG variables and
# match the paths previous versions derived by hand; they differ on
# macOS/Windows, where the legacy locations below are checked for migration)
# the global configuration of papers v2 (v2 compatibility, remove with migrate)
CONFIG_FILE = os.path.join(platformdirs.user_config_dir(), 'papersconfig.json')
# the configuration file of a library, relative to the library directory
CONFIG_FILE_LOCAL = os.path.join('.papers', 'config.json')
# its name in papers 2: read, and moved to CONFIG_FILE_LOCAL when the
# configuration is saved (see Config.save)
CONFIG_FILE_LOCAL_V2 = '.papersconfig.json'
LIBRARY_CONFIG_FILES = [CONFIG_FILE_LOCAL, CONFIG_FILE_LOCAL_V2]

DATA_DIR = platformdirs.user_data_dir('papers')
# the backups of papers 3.0.0b2 and earlier (no longer used, see papers.backup.stale_backups)
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
# the history of the libraries (see papers.history), unless the history-dir setting says otherwise
HISTORY_DIR = os.path.join(DATA_DIR, 'history')
CACHE_DIR = platformdirs.user_cache_dir('papers')

# locations used by previous versions (XDG conventions on every platform),
# kept for migration and for listing pre-existing backup directories
# v2 compatibility, remove with migrate (but BACKUP_DIR_LEGACY)
HOME = os.environ.get('HOME', os.path.expanduser('~'))
_CONFIG_HOME_LEGACY = os.environ.get('XDG_CONFIG_HOME', os.path.join(HOME, '.config'))
_DATA_HOME_LEGACY = os.environ.get('XDG_DATA_HOME', os.path.join(HOME, '.local', 'share'))
CONFIG_FILE_LEGACY = os.path.join(_DATA_HOME_LEGACY, 'config.json')
CONFIG_FILE_LEGACY_XDG = os.path.join(_CONFIG_HOME_LEGACY, 'papersconfig.json')
BACKUP_DIR_LEGACY = os.path.join(_DATA_HOME_LEGACY, 'papers', 'backups')


# version of the configuration files written by this papers; a file without
# version was written by papers v2
CONFIG_VERSION = 3
# settings of the v2 file format, only read from files without version
# v2 compatibility, remove with migrate
_V2_KEYS = ('absolute_paths', 'backup_files')


def file_version(js, file):
    "format version of a configuration file (2 without version); raise PapersExit if it is too new"
    version = js.get('version', 2)
    if not isinstance(version, int) or isinstance(version, bool):
        raise PapersExit(f"{file}: invalid configuration version {version!r}")
    if version > CONFIG_VERSION:
        raise PapersExit(f"{file} was written by a newer papers (configuration version {version}; "
                         f"papers {__version__} reads up to version {CONFIG_VERSION}): upgrade papers")
    if version >= 3:
        for key in _V2_KEYS:
            js.pop(key, None)
    return version


# global configuration: the default library and default settings for libraries
MACHINE_CONFIG_FILE = os.path.join(platformdirs.user_config_dir('papers'), 'config.json')
# the value of the pool setting for no pool
NO_POOL = 'none'


def _single_pool(js, file):
    """a pool setting written as a list (by papers builds that took several
    pools): one path is that path; several paths are an error"""
    value = js.get('pool')
    if not isinstance(value, list):
        return
    paths = [p for p in value if isinstance(p, str) and p]
    if len(paths) > 1:
        raise PapersExit(f"{file}: the pool setting lists several pools ({', '.join(paths)}); papers takes "
                         f"one pool: write one path, or {NO_POOL}, in this file")
    js['pool'] = paths[0] if paths else NO_POOL


# Settings of `papers config`, by name. The name and key format fields map to
# the attributes of papers.filename.Format (name.author-num -> author_num).
_FORMAT_FIELDS = ['template', 'author-num', 'author-sep', 'title-word-num', 'title-word-size', 'title-length',
                  'title-sep', 'unknown-template', 'unknown-strict']
_INT_FIELDS = ['author-num', 'title-word-num', 'title-word-size', 'title-length']

# type of each setting: 'path', 'pool', 'bool', 'int', 'str', or a tuple of choices
SETTINGS = {
    'bibtex': 'path',
    'filesdir': 'path',
    'pool': 'pool',
    'paths': ('relative', 'absolute'),
    'files': ('ask', 'move', 'copy', 'link'),
    'auto-push': 'bool',
    'editor': 'str',
    'checksums': 'bool',
    'history-dir': 'str',
    'history-size': 'int',
    'history-separate': 'bool',
    'keep-deleted-files': 'bool',
}
for _kind in ('name', 'key'):
    for _field in _FORMAT_FIELDS:
        SETTINGS[_kind + '.' + _field] = 'int' if _field in _INT_FIELDS else (
            'bool' if _field == 'unknown-strict' else 'str')

# settings that only make sense for a library
LIBRARY_ONLY = ('bibtex', 'filesdir')
# settings of the machine only: a library does not set them (a library
# received from someone cannot choose where the history goes, or what it keeps;
# history-separate and history-size may be set by a library: its own store,
# in the folder of the machine, see papers.backup.store)
MACHINE_ONLY = ('history-dir', 'keep-deleted-files')
# settings of a library other than its paths: when the library does not set
# one, the global configuration applies, except for pool (see Config.inherited)
LIBRARY_SETTINGS = [name for name in SETTINGS if name not in LIBRARY_ONLY + MACHINE_ONLY]
# settings of papers before the history (see design/history.md): ignored
REMOVED_SETTINGS = {
    'git': 'papers keeps the history of the libraries without git (see `papers history`)',
    'git-lfs': 'papers keeps the files that its commands delete in its history, without git-lfs '
               '(see `papers history`)',
    'trash-days': 'the history-size setting (global) limits the history, with the files it keeps',
    'trash-size': 'the history-size setting (global) limits the history, with the files it keeps',
}


def default_value(name):
    "built-in default of a setting"
    if name.startswith('name.'):
        return getattr(NAMEFORMAT, _attr(name))
    if name.startswith('key.'):
        return getattr(KEYFORMAT, _attr(name))
    return {'paths': 'relative', 'files': 'move', 'auto-push': False, 'history-size': 500,
            'history-separate': False, 'keep-deleted-files': True, 'checksums': True, 'editor': None, 'history-dir': None}.get(name)


def _attr(name):
    "Format attribute of a name.* or key.* setting"
    return name.split('.', 1)[1].replace('-', '_')


def _group(name):
    return 'nameformat' if name.startswith('name.') else 'keyformat'


def json_get(js, name):
    """value of a setting in the json of a configuration file, or None
    (None also means unset)"""
    if name.startswith(('name.', 'key.')):
        return (js.get(_group(name)) or {}).get(_attr(name))
    if name == 'paths':
        if js.get('paths') is not None:
            return js['paths']
        if js.get('absolute_paths') is not None:  # files of v2 (v2 compatibility, remove with migrate)
            return 'absolute' if js['absolute_paths'] else 'relative'
        return None
    return js.get(name)


def json_set(js, name, value):
    "set (or with value None, remove) a setting in the json of a configuration file"
    if name.startswith(('name.', 'key.')):
        group = js.setdefault(_group(name), {})
        if value is None:
            group.pop(_attr(name), None)
        else:
            group[_attr(name)] = value
        if not group:
            del js[_group(name)]
        return
    if name == 'paths':
        js.pop('absolute_paths', None)
    if value is None:
        js.pop(name, None)
    else:
        js[name] = value


def parse_value(name, values):
    """check and convert the command-line value(s) of a setting; raise ValueError"""
    kind = SETTINGS[name]
    if len(values) != 1:
        raise ValueError(f'{name} takes one value, got {len(values)}')
    value = values[0]
    if kind == 'bool':
        low = value.lower()
        if low in ('true', 'yes', 'on', '1'):
            return True
        if low in ('false', 'no', 'off', '0'):
            return False
        raise ValueError(f'{name}: expected true or false, got {value!r}')
    if kind == 'int':
        try:
            return int(value)
        except ValueError:
            raise ValueError(f'{name}: expected an integer, got {value!r}')
    if isinstance(kind, tuple) and value not in kind:
        raise ValueError(f'{name}: expected one of {", ".join(kind)}, got {value!r}')
    return value


def format_value(value):
    "a setting's value as printed by `papers config`"
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def short_home(path):
    "a path under the home directory as ~/..., as written in the global configuration"
    home = os.path.expanduser('~')
    path = os.path.abspath(path)
    if path == home or path.startswith(home + os.path.sep):
        return '~' + path[len(home):]
    return path


# the backup of a library, in its .papers folder (see papers.backup)
BACKUP_DIR_LOCAL = os.path.join('.papers', 'backup')


# .papers/.gitignore: the folder holds the internals of papers, which a
# library under git does not track (they may change between versions)
GITIGNORE = '*\n'
# the .gitignore that papers wrote before (the git backup in the library)
_LEGACY_GITIGNORES = ('backup/\n',)


def ignore_papers_folder(folder):
    """write .papers/.gitignore (everything ignored), unless the user wrote
    one; the one that earlier versions wrote is replaced"""
    if os.path.basename(os.path.normpath(folder)) != '.papers':
        return
    path = os.path.join(folder, '.gitignore')
    try:
        current = open(path, encoding='utf-8').read() if os.path.exists(path) else None
        if current is None or current in _LEGACY_GITIGNORES:
            write_atomic(path, GITIGNORE)
    except OSError as error:
        logger.debug(f'{path}: not written ({error})')


def config_root(file):
    """the directory that the relative paths of a library configuration file
    refer to, the library directory: the parent of .papers for
    .papers/config.json (as papers v2.2 to v2.4 also read and wrote it), the
    directory of the file for the .papersconfig.json of papers 2"""
    p = Path(file)
    if p.name == 'config.json' and p.parent.name == '.papers':
        return p.parent.parent
    return p.parent


def library_config_file(path):
    """the configuration file of the library in directory `path`, or None.
    A directory with both names (.papers/config.json and .papersconfig.json
    of papers 2) is an error: the user keeps one."""
    found = [os.path.join(path, name) for name in LIBRARY_CONFIG_FILES
             if os.path.isfile(os.path.join(path, name))]
    if len(found) > 1:
        raise PapersExit(f"{short_home(os.path.abspath(path))} has two library configurations, "
                         f"{CONFIG_FILE_LOCAL} and {CONFIG_FILE_LOCAL_V2} (of papers 2): keep one of them "
                         "and remove the other (nothing was changed)")
    return found[0] if found else None


def find_library_config(start_dir='.'):
    """the configuration file of the library of start_dir: in start_dir or a
    directory above it (the root directory excluded), else None"""
    current = os.path.abspath(start_dir)
    while True:
        parent = os.path.dirname(current)
        if parent == current:  # the root directory
            return None
        file = library_config_file(current)
        if file is not None:
            return file
        current = parent


def move_v2_config(file, dryrun=False):
    """move the library configuration of papers 2 `file` (.papersconfig.json)
    to .papers/config.json in the same directory, and return the new path
    (with dryrun: only say so). Error if both files exist."""
    libdir = os.path.dirname(os.path.abspath(file))
    new = os.path.join(libdir, CONFIG_FILE_LOCAL)
    if os.path.exists(new):
        library_config_file(libdir)  # the error of two configurations
    if dryrun:
        print(f"DRYRUN: {short_home(file)} not moved to {short_home(new)}")
        return file
    os.makedirs(os.path.dirname(new), exist_ok=True)
    os.replace(file, new)
    print(f"moved {short_home(file)} to {short_home(new)}")
    return new


def is_v2_config_name(file):
    "a library configuration file with the name of papers 2 (.papersconfig.json)"
    return file is not None and os.path.basename(file) == CONFIG_FILE_LOCAL_V2


def is_backup_name(value):
    "a name, not a path, of a backup directory"
    return (value not in ('.', '..') and os.path.sep not in value
            and not (os.path.altsep and os.path.altsep in value) and not value.startswith('~'))


def pool_setting(path, libdir, base=None):
    """how the pool setting of a library in `libdir` writes a pool path given
    on the command line (`base`: the directory a relative path is relative
    to, by default libdir): relative to the library when it is written
    relative or is under the library (./ or ../ first), else absolute (~
    for the home directory). `none` stays none."""
    if path == NO_POOL:
        return path
    expanded = os.path.expanduser(path)
    full = os.path.abspath(os.path.join(base or libdir, expanded))
    libdir = os.path.abspath(libdir)
    if not os.path.isabs(expanded) or full == libdir or full.startswith(libdir.rstrip(os.path.sep) + os.path.sep):
        rel = os.path.relpath(full, libdir)
        return rel if rel.startswith('.') else os.path.join('.', rel)
    return short_home(full)


# the setting of the global configuration that names the default library
DEFAULT_LIBRARY = 'default'


class MachineConfig:
    """global configuration: the default library and the defaults of library settings

    The file has the layout of a library configuration:
        {"default": "~/Documents/papers", "editor": "vim",
         "nameformat": {"template": "{author}_{year}"}}
    `default` (optional) is the default library: a library without pool,
    used outside of any library, and the pool of `papers init --shallow`.
    """
    def __init__(self, file=None, data=None):
        self.file = file
        self.data = data if data is not None else {}
        # pool names of earlier v3 builds (`pools.NAME PATH`): not a setting,
        # but written back by save, so that their libraries keep finding their pool
        self.pool_names = {}
        names = self.data.pop('pools', None)
        if isinstance(names, dict):
            self.pool_names = names

    @classmethod
    def load(cls, file=None):
        file = file or MACHINE_CONFIG_FILE
        data = {}
        if os.path.exists(file):
            try:
                data = json.load(open(file, encoding='utf-8-sig'))
            except (json.JSONDecodeError, OSError) as error:
                logger.warning(f"unreadable global configuration {file}: {error} -- ignored")
        file_version(data, file)
        data.pop('version', None)
        if data.pop('pool', None) not in (None, NO_POOL):
            logger.warning(f"{file}: the global pool setting is no longer used (ignored); "
                           "`papers config --global default PATH` sets a default library")
        return cls(file, data)

    def exists(self):
        return self.file is not None and os.path.exists(self.file)

    def get(self, name):
        return json_get(self.data, name)

    def set(self, name, value):
        json_set(self.data, name, value)

    @property
    def default(self):
        "the default library as written (with ~), or None"
        return self.data.get(DEFAULT_LIBRARY) or None

    def default_path(self):
        "absolute path of the default library, or None (a relative path is relative to the folder of this file)"
        if self.default is None:
            return None
        return self.absolute(self.default)

    def absolute(self, path):
        "a path of this configuration: ~ expanded, relative to the folder of the file"
        path = os.path.expanduser(path)
        base = os.path.dirname(os.path.abspath(self.file)) if self.file else os.getcwd()
        return os.path.normpath(os.path.join(base, path))

    def save(self):
        os.makedirs(os.path.dirname(self.file), exist_ok=True)
        # through a temporary file (see write_atomic): a crash never leaves half a configuration
        data = {**self.data, 'version': CONFIG_VERSION}
        if self.pool_names:
            data['pools'] = self.pool_names
        write_atomic(self.file, json.dumps(data, sort_keys=True, indent=2, separators=(',', ': ')))


def _read_earlier_v3(js, machine, file):
    """the settings of the files written by earlier v3 builds, read as the
    current ones: `pools` (a list of names and paths) is the pool (its first
    entry; the name `default` is the default library). The settings `light`
    and `local` are gone: a library with a pool is shallow."""
    pools = js.pop('pools', None)
    for name in ('light', 'local', 'sync'):
        js.pop(name, None)
    _single_pool(js, file)
    if isinstance(pools, list) and 'pool' not in js:
        first = pools[0] if pools else NO_POOL
        if first == 'default':
            js['pool'] = machine.default or NO_POOL
        elif first == NO_POOL or os.path.sep in first or (os.path.altsep and os.path.altsep in first) \
                or first.startswith(('.', '~')):
            js['pool'] = first
        elif first in machine.pool_names:
            js['pool'] = machine.pool_names[first]
        else:
            logger.warning(f"{file}: unknown pool name {first}: the library has no pool")


class Config:
    """configuration of a library

    Each setting comes from the library's configuration file, else from the
    global configuration, else from its built-in default; the pool comes
    only from the library's file (none if it does not set it). The attributes
    hold the resulting values; `explicit` names the settings set in the file.
    The file keeps the pool once set, and the other settings when they differ
    from the global or default value (see `is_set`).

    A library without pool is self-contained: its own entries and files. A
    library with a pool is shallow (see `shallow`): it links to the files
    of the pool entries, and adds its new entries to the pool.
    """
    def __init__(self, file=None,
        bibtex=None, filesdir=None,
        keyformat=None,
        nameformat=None,
        editor=None,
        is_library=None, absolute_paths=None,
        pool=None, files=None, auto_push=None, machine=None):
        self.file = file
        # False for the global configuration of v2 (v2 compatibility, remove with migrate)
        self.is_library = is_library
        self.machine = machine if machine is not None else MachineConfig.load()
        # how the configuration was found (see papers.library.find_config)
        self.origin = None
        self.explicit = set()
        self.filesdir = filesdir
        self.bibtex = bibtex
        # the identifier of the library: its history (see library_id)
        self.id = None
        self.keyformat = copy.deepcopy(keyformat) if keyformat is not None else self._inherited_format('key')
        self.nameformat = copy.deepcopy(nameformat) if nameformat is not None else self._inherited_format('name')
        self.editor = editor if editor is not None else self.inherited('editor')
        if absolute_paths is None:
            absolute_paths = self.inherited('paths') == 'absolute'
        self.absolute_paths = absolute_paths
        # the pool: a path (relative to the library), or none
        self.pool = pool if pool is not None else NO_POOL
        # what `add` does with a file: move or copy it into the files
        # directory, or link it where it is (see papers.files.FilesPolicy)
        self.files = files if files is not None else self.inherited('files')
        # auto-push: the commands that change entries push them to the pool
        # (those shared with it, and new ones; see papers.cli.common.save_entries),
        # in a shallow library only
        self.auto_push = auto_push if auto_push is not None else self.inherited('auto-push')
        # the history of the machine (see papers.backup): where, how large, and
        # whether it keeps the files that the commands delete
        self.history_dir = self.inherited('history-dir')
        self.history_size = self.inherited('history-size')
        self.history_separate = self.inherited('history-separate')
        self.keep_deleted_files = self.inherited('keep-deleted-files')
        # the checksums of the files that the commands touch (see papers.checksums)
        self.checksums = self.inherited('checksums')

    def library_id(self, create=True):
        """the identifier of the library, which names its history (see
        papers.backup); a library without one gets one (saved), unless
        create is False"""
        if self.id is None and create and self.file and self.is_library:
            from papers.history import new_id  # papers.history is self-contained
            self.id = new_id()
            if os.path.exists(self.file) and not DRYRUN:
                # the identifier only: the settings in memory may be those of the command
                # (e.g. the files directory of the pool, see papers.pools.use_pool_files)
                js = json.load(open(self.file, encoding='utf-8-sig'))
                js['id'] = self.id
                write_atomic(self.file, json.dumps(js, sort_keys=True, indent=2, separators=(',', ': ')))
        return self.id


    # settings by name (see SETTINGS)
    # -------------------------------
    def inherited(self, name):
        """value of a setting when the library does not set it: the global
        configuration, else the built-in default. The pool is none: the
        global configuration has no pool."""
        if name == 'pool':
            return NO_POOL
        value = self.machine.get(name)
        return copy.deepcopy(value) if value is not None else default_value(name)

    def _inherited_format(self, kind):
        fmt = copy.deepcopy(NAMEFORMAT if kind == 'name' else KEYFORMAT)
        for name in SETTINGS:
            if name.startswith(kind + '.'):
                setattr(fmt, _attr(name), self.inherited(name))
        return fmt

    def get(self, name):
        "current value of a setting"
        if name.startswith('name.'):
            return getattr(self.nameformat, _attr(name))
        if name.startswith('key.'):
            return getattr(self.keyformat, _attr(name))
        if name == 'paths':
            return 'absolute' if self.absolute_paths else 'relative'
        return getattr(self, name.replace('-', '_'))

    def set(self, name, value):
        "set a setting of the library (saved by `save`)"
        if name.startswith('name.'):
            setattr(self.nameformat, _attr(name), value)
        elif name.startswith('key.'):
            setattr(self.keyformat, _attr(name), value)
        elif name == 'paths':
            self.absolute_paths = value == 'absolute'
        else:
            setattr(self, name.replace('-', '_'), value)
        self.explicit.add(name)

    def unset(self, name):
        "remove a setting from the library: the global or default value applies (pool: none)"
        self.explicit.discard(name)
        self.set(name, None if name in ('bibtex', 'filesdir') else self.inherited(name))
        self.explicit.discard(name)

    def is_set(self, name):
        """the library sets this setting: a setting given explicitly (in its
        configuration file, by `papers init` or `papers config NAME VALUE`),
        even with the global or default value, and a setting whose value
        differs from it; the others are inherited (not saved)"""
        if name in ('bibtex', 'filesdir'):
            return getattr(self, name) is not None
        if name in MACHINE_ONLY:
            return False
        return name in self.explicit or self.get(name) != self.inherited(name)

    def source(self, name):
        "where the value of a setting comes from: library, global or default"
        if self.file and self.is_set(name):
            return 'library'
        if name not in ('bibtex', 'filesdir', 'pool') and self.machine.get(name) is not None:
            return 'global'
        return 'default'

    # pool
    # ----
    def pool_path(self):
        """absolute path of the pool of the library (the pool setting, relative
        to the library), or None (pool none, or no library)"""
        if not self.file or self.pool == NO_POOL:
            return None
        return os.path.abspath(os.path.join(self.configdir, os.path.expanduser(self.pool)))

    def pool_label(self):
        "the pool as the pool setting writes it (relative to the library, or with ~), or None"
        return self.pool if self.pool_path() is not None else None

    def is_pool_library(self):
        "the library is its own pool (e.g. pool .), so it has none"
        path = self.pool_path()
        return bool(self.file) and path is not None and os.path.realpath(path) == os.path.realpath(self.configdir)

    def has_pool(self):
        return self.pool_path() is not None and not self.is_pool_library()

    @property
    def shallow(self):
        """a library with a pool: its entries link to the files of the pool
        entries, and its new entries go to the pool (see papers.pools)"""
        return bool(self.file) and self.has_pool()

    @property
    def configdir(self):
        "directory that relative paths of a local configuration file refer to"
        return config_root(self.file).resolve() if self.file else Path.cwd()

    def _relpath(self, p):
        if p is None: return p
        if not self.is_library:  # v2 compatibility, remove with migrate
            return str(Path(p).resolve())  # abspath

        # otherwise express path relative to the directory of the config file
        # (as `load` reads it), with '..' components if needed (e.g. files
        # directory outside it); a relative p is relative to the current directory
        try:
            return os.path.relpath(Path(p).resolve(), self.configdir)
        except ValueError:
            # e.g. different drive on Windows
            logger.warning(f"config :: can't save {p} as relative path to {self.configdir}")
            return p

    def _abspath(self, p, root=None):
        if p is None: return p
        if not self.is_library:  # v2 compatibility, remove with migrate
            return str(Path(p).resolve())  # abspath
        # normpath, not resolve: '..' is removed, the symbolic links are kept; ~ is the home directory
        return os.path.normpath((Path(root).resolve() if root is not None else self.configdir) / os.path.expanduser(p))


    def tojson(self):
        """content of the configuration file: the paths, and the settings that
        the library sets (the others come from the global configuration when loaded)"""
        js = {
            "filesdir": self._relpath(self.filesdir),
            "bibtex": self._relpath(self.bibtex),
        }
        for name in LIBRARY_SETTINGS:
            if self.is_set(name):
                json_set(js, name, self.get(name))
        if self.is_library and self.id:
            js["id"] = self.id
        if self.is_library:
            js["version"] = CONFIG_VERSION
        else:  # v2 compatibility, remove with migrate
            js["local"] = False  # global configuration of v2 (file format of v2)
        return js

    def save(self):
        """write the configuration file; a library configuration of papers 2
        (.papersconfig.json) is moved to .papers/config.json first. With
        --dry-run, nothing is written."""
        if DRYRUN:
            print(f'DRYRUN: {self.file} not saved')
            return
        if self.is_library and is_v2_config_name(self.file):
            self.file = move_v2_config(self.file)
        if os.path.dirname(self.file):
            os.makedirs(os.path.dirname(self.file), exist_ok=True)
        write_atomic(self.file, json.dumps(self.tojson(), sort_keys=True, indent=2, separators=(',', ': ')))
        if self.is_library:
            ignore_papers_folder(os.path.dirname(self.file))


    @classmethod
    def load(cls, the_file, machine=None, is_library=None):
        """is_library=False for a global configuration of v2 (the default
        tells them apart by the file content or name)"""
        js = json.load(open(the_file, encoding='utf-8-sig'))
        version = file_version(js, the_file)
        if is_library is None and version >= 3:
            is_library = True  # v3 has no global configuration
        # v2 compatibility, remove with migrate
        if version < 3:
            v2_local = js.pop('local', None)  # in v2: a library, not the global configuration
            if is_library is None:
                is_library = v2_local
        if is_library is None:
            # v2 global configurations (papersconfig.json, not hidden) are not local
            is_library = os.path.basename(the_file) != os.path.basename(CONFIG_FILE)
        machine = machine if machine is not None else MachineConfig.load()
        _read_earlier_v3(js, machine, the_file)
        cfg = cls(file=the_file, is_library=is_library, machine=machine,
                  bibtex=js.get('bibtex'), filesdir=js.get('filesdir'))
        # an identifier that papers did not write (e.g. a path, in a library received from someone) is ignored
        if is_library and isinstance(js.get('id'), str) and re.fullmatch(r'[0-9a-f]{32}', js['id']):
            cfg.id = js['id']
        if not is_library and json_get(js, 'paths') is None:  # v2 compatibility, remove with migrate
            js['paths'] = 'absolute'  # default of v2 for a global configuration
        for name in LIBRARY_SETTINGS:
            value = json_get(js, name)
            if value is not None:
                cfg.set(name, value)
        cfg._update_paths_to_absolute()
        return cfg


    def _update_paths_to_absolute(self):
        if self.file is None:
            logger.warning("_update_paths_to_absolute: only works if Config.file is defined")
            return
        root = config_root(self.file)
        for field in ['bibtex', 'filesdir']:
            setattr(self, field, self._abspath(getattr(self, field), root))


    def unused_while_shallow(self, name):
        """the settings that a shallow library does not use: its files are in
        the pool, named with the pool's template (filesdir is where
        `papers config pool none` copies them)"""
        return self.shallow and (name == 'filesdir' or name.startswith('name.'))

    def settings_lines(self, names=None):
        """lines `name = value (source)` of `papers config` and `papers status -v`
        (bibtex and filesdir as absolute paths, as `papers config KEY` prints them)"""
        names = names or list(SETTINGS)
        width = max(len(name) for name in names)
        lines = []
        for name in names:
            value = self.get(name)
            note = ', not used: shallow library' if self.unused_while_shallow(name) else ''
            lines.append(f'{name.ljust(width)} = {format_value(value)}  ({self.source(name)}{note})')
        return lines


    def status(self, check_files=False, verbose=False):
        """`papers status`: where the library, its bibtex and its files are,
        and how it stands with its pool, with a hint of what to do about it
        on the last line (-v: also its history, the configuration file, the
        cache and the version). `papers config` lists the settings."""

        def _fmt_path(p):
            if self.is_library:
                return os.path.relpath(p, ".")
            else:  # v2 compatibility, remove with migrate
                return p

        if self.file and os.path.exists(self.file):
            if self.origin == 'default':
                note = f'(default library, set in {short_home(self.machine.file)})'
            else:
                note = {'v2-global': '(global configuration of papers v2: run `papers migrate`)'}.get(self.origin, '')
            status = (str(self.configdir) if self.is_library else self.file) + ' ' + note
        else:
            status = bcolors.WARNING+"(no library found: create one with `papers init`)"+bcolors.ENDC
        header = [bcolors.BOLD+f'papers library: {status}'.rstrip()+bcolors.ENDC]
        items = []  # (label, value), aligned
        hint = None
        if self.file is not None or self.bibtex is not None:
            items.append(('bibtex', self._bibtex_status(check_files, _fmt_path)))
            items.append(('files', self._files_status(check_files, _fmt_path)))
            if self.file and self.shallow:
                from papers.pools import status_line  # papers.pools imports this module
                pool, hint = status_line(self)
                items.append(('pool', pool))
            if verbose:
                items.append(('history', self.history_summary()))
        if verbose:
            items.append(('configuration file', _fmt_path(self.file) if self.file and os.path.exists(self.file)
                          else bcolors.WARNING+'none'+bcolors.ENDC))
            items.append(('cache directory', short_home(CACHE_DIR)))
            items.append(('version', __version__))

        width = max(len(label) for label, _ in items) + 1 if items else 0
        lines = header + [f'* {(label + ":").ljust(width)} {value}' for label, value in items]
        if hint:
            lines.append(hint)
        elif self.file:
            lines.append('`papers config` lists and sets the settings')
        return '\n'.join(lines)

    def history_summary(self):
        "the history of the library (see papers.backup), for papers status -v: `papers history` tells more"
        from papers.backup import project_of  # papers.backup imports this module
        project, place = project_of(self, create=False)
        steps = len(project.states()) if project is not None else 0
        return f'{steps} step{"" if steps == 1 else "s"} (`papers history`)'

    def _files_status(self, check_files, _fmt_path):
        "where the files of the library are"
        if self.shallow:
            # the files of a shallow library are in its pool (see papers.pools.use_pool_files)
            from papers.pools import pool_files_dir  # papers.pools imports this module
            pool_dir = pool_files_dir(self)
            return f'in the pool, {short_home(pool_dir)}' if pool_dir else 'in the pool'
        if self.filesdir is None:
            return 'linked where they are (no files directory)'
        notes = ['the files directory of the library']
        if not os.path.exists(self.filesdir):
            notes.append(bcolors.WARNING+'missing'+bcolors.ENDC)
        elif not os.listdir(self.filesdir):
            notes.append(bcolors.WARNING+'empty'+bcolors.ENDC)
        elif check_files:
            file_count, folder_size = check_filesdir(self.filesdir)
            notes.append(bcolors.OKBLUE+"{} files, {:.1f} MB".format(file_count, folder_size/(1024*1024.0))+bcolors.ENDC)
        return f'{_fmt_path(self.filesdir)} ({", ".join(notes)})'

    def _bibtex_status(self, check_files, _fmt_path):
        "the bibtex of the library, and its state"
        if self.bibtex is None:
            status = bcolors.WARNING+' (unset)'+bcolors.ENDC
        elif not os.path.exists(self.bibtex):
            status = bcolors.WARNING+' (missing)'+bcolors.ENDC
        elif check_files:
            try:
                bibtexstring = open(self.bibtex).read()
                from papers.bib import parse_cache  # papers.bib imports this module
                db = parse_string(bibtexstring, cache=parse_cache())
                if len(db.entries):
                    nfiles = sum(len(parse_file(get_entry_val(e, 'file', ''))) for e in db.entries)
                    status = bcolors.OKBLUE+' ({} entries, {} file links)'.format(len(db.entries), nfiles)+bcolors.ENDC
                else:
                    status = bcolors.WARNING+' (empty)'+bcolors.ENDC
            except (OSError, ValueError):  # unreadable, or not text
                status = bcolors.FAIL+' (corrupted)'+bcolors.ENDC
        elif os.path.getsize(self.bibtex) == 0:
            status = bcolors.WARNING+' (empty)'+bcolors.ENDC
        else:
            status = ''
        return f'{_fmt_path(self.bibtex) if self.bibtex else self.bibtex}'+status
