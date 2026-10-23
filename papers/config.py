import os, json
import copy
from pathlib import Path
import platformdirs

from papers.entries import parse_string, get_entry_val, parse_file
from papers import logger
from papers.filename import NAMEFORMAT, KEYFORMAT
from papers import __version__
from papers.utils import bcolors, check_filesdir, PapersExit

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
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
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
    'files': ('move', 'copy', 'link'),
    'auto-push': 'bool',
    'git': 'bool',
    'git-lfs': 'bool',
    'editor': 'str',
}
for _kind in ('name', 'key'):
    for _field in _FORMAT_FIELDS:
        SETTINGS[_kind + '.' + _field] = 'int' if _field in _INT_FIELDS else (
            'bool' if _field == 'unknown-strict' else 'str')

# settings that only make sense for a library
LIBRARY_ONLY = ('bibtex', 'filesdir')
# settings of a library other than its paths: when the library does not set
# one, the global configuration applies, except for pool (see Config.inherited)
LIBRARY_SETTINGS = [name for name in SETTINGS if name not in LIBRARY_ONLY]


def default_value(name):
    "built-in default of a setting"
    if name.startswith('name.'):
        return getattr(NAMEFORMAT, _attr(name))
    if name.startswith('key.'):
        return getattr(KEYFORMAT, _attr(name))
    return {'paths': 'relative', 'files': 'move', 'auto-push': False,
            'git': False, 'git-lfs': False, 'editor': None}.get(name)


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
    if name == 'git-lfs':
        return js.get('gitlfs', js.get('backup_files'))
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
    if name == 'git-lfs':
        js.pop('backup_files', None)
        name = 'gitlfs'
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


def gitdir_to_json(gitdir):
    """how a library configuration stores its backup directory: by name if it
    is in the backup folder of the machine (BACKUP_DIR), else as absolute path"""
    if gitdir is None:
        return None
    gitdir = os.path.abspath(gitdir)
    if os.path.realpath(os.path.dirname(gitdir)) == os.path.realpath(BACKUP_DIR):
        return os.path.basename(gitdir)
    return gitdir


def gitdir_from_json(value, root):
    """backup directory of a library configuration: a name is a directory of
    the machine's backup folder, a path is relative to the library (root)"""
    if value is None:
        return None
    if is_backup_name(value):
        return os.path.join(BACKUP_DIR, value)
    return str(Path(root).resolve() / value)


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
        # pool names of earlier v3 builds (`pools.NAME PATH`): only read, so
        # that their libraries keep finding their pool
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
                data = json.load(open(file))
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
        "absolute path of the default library, or None"
        if self.default is None:
            return None
        return os.path.abspath(os.path.expanduser(self.default))

    def save(self):
        os.makedirs(os.path.dirname(self.file), exist_ok=True)
        json.dump({**self.data, 'version': CONFIG_VERSION}, open(self.file, 'w'),
                  sort_keys=True, indent=2, separators=(',', ': '))


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

    A library without pool is self-contained: its own entries and files. A
    library with a pool is shallow (see `shallow`): it links to the files
    of the pool entries, and adds its new entries to the pool.
    """
    def __init__(self, file=None,
        bibtex=None, filesdir=None,
        keyformat=None,
        nameformat=None,
        editor=None,
        gitdir=None, git=None, gitlfs=None, is_library=None, absolute_paths=None,
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
        self.gitdir = gitdir
        self.keyformat = copy.deepcopy(keyformat) if keyformat is not None else self._inherited_format('key')
        self.nameformat = copy.deepcopy(nameformat) if nameformat is not None else self._inherited_format('name')
        self.editor = editor if editor is not None else self.inherited('editor')
        if absolute_paths is None:
            absolute_paths = self.inherited('paths') == 'absolute'
        self.absolute_paths = absolute_paths
        self.git = git if git is not None else self.inherited('git')
        self.gitlfs = gitlfs if gitlfs is not None else self.inherited('git-lfs')
        # the pool: a path (relative to the library), or none
        self.pool = pool if pool is not None else NO_POOL
        # what `add` does with a file: move or copy it into the files
        # directory, or link it where it is (see papers.files.FilesPolicy)
        self.files = files if files is not None else self.inherited('files')
        # auto-push: the commands that change entries push them to the pool
        # (those shared with it, and new ones; see papers.cli.common.save_entries),
        # in a shallow library only
        self.auto_push = auto_push if auto_push is not None else self.inherited('auto-push')


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
        if name == 'git-lfs':
            return bool(self.gitlfs)
        if name == 'git':
            return bool(self.git)
        return getattr(self, name.replace('-', '_'))

    def set(self, name, value):
        "set a setting of the library (saved by `save`)"
        if name.startswith('name.'):
            setattr(self.nameformat, _attr(name), value)
        elif name.startswith('key.'):
            setattr(self.keyformat, _attr(name), value)
        elif name == 'paths':
            self.absolute_paths = value == 'absolute'
        elif name == 'git-lfs':
            self.gitlfs = value
        else:
            setattr(self, name.replace('-', '_'), value)
        self.explicit.add(name)

    def unset(self, name):
        "remove a setting from the library: the global or default value applies (pool: none)"
        self.explicit.discard(name)
        self.set(name, None if name in ('bibtex', 'filesdir') else self.inherited(name))
        self.explicit.discard(name)

    def is_set(self, name):
        "the library sets this setting (in its file, or changed since loaded)"
        if name in ('bibtex', 'filesdir'):
            return getattr(self, name) is not None
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
    def backupfile_clean(self):
        "copy of the bibtex with file paths relative to the backup directory (--git-lfs mode)"
        return Path(self.gitdir)/'backup_clean.bib'

    @property
    def backupfile(self):
        "tracked verbatim copy of the bibtex, named after it"
        name = Path(self.bibtex).name if self.bibtex else 'library.bib'
        if name in ('backup_clean.bib', 'manifest.json'):
            # avoid clashing with the backup directory's own files
            name = 'backup_' + name
        return Path(self.gitdir)/name


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
        p2 = str((Path(root).resolve() if root is not None else self.configdir) / p)
        return p2


    def tojson(self):
        """content of the configuration file: the paths, and the settings that
        the library sets (the others come from the global configuration when loaded)"""
        js = {
            "filesdir": self._relpath(self.filesdir),
            "bibtex": self._relpath(self.bibtex),
            # by name under the backup folder of each machine
            "gitdir": gitdir_to_json(self._abspath(self.gitdir)) if self.is_library else self._abspath(self.gitdir),
        }
        for name in LIBRARY_SETTINGS:
            if self.is_set(name):
                json_set(js, name, self.get(name))
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
            logger.info(f'DRYRUN: {self.file} not saved')
            return
        if self.is_library and is_v2_config_name(self.file):
            self.file = move_v2_config(self.file)
        if os.path.dirname(self.file):
            os.makedirs(os.path.dirname(self.file), exist_ok=True)
        with open(self.file, 'w') as f:
            json.dump(self.tojson(), f, sort_keys=True, indent=2, separators=(',', ': '))


    @classmethod
    def load(cls, the_file, machine=None, is_library=None):
        """is_library=False for a global configuration of v2 (the default
        tells them apart by the file content or name)"""
        js = json.load(open(the_file))
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
        gitdir = js.get('gitdir')
        if gitdir is not None and is_library:
            if version < 3:
                # a path in v2 (".papers" in v2.2 to v2.4), never a name
                gitdir = str(config_root(the_file).resolve() / gitdir)
            else:
                gitdir = gitdir_from_json(gitdir, config_root(the_file))
        cfg = cls(file=the_file, is_library=is_library, machine=machine,
                  bibtex=js.get('bibtex'), filesdir=js.get('filesdir'), gitdir=gitdir)
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
        for field in ['bibtex', 'filesdir', 'gitdir']:
            setattr(self, field, self._abspath(getattr(self, field), root))


    def settings_lines(self, names=None):
        """lines `name = value (source)` of `papers config` and `papers status -v`
        (bibtex and filesdir as absolute paths, as `papers config KEY` prints them)"""
        names = names or list(SETTINGS)
        width = max(len(name) for name in names)
        lines = []
        for name in names:
            value = self.get(name)
            lines.append(f'{name.ljust(width)} = {format_value(value)}  ({self.source(name)})')
        return lines


    def status(self, check_files=False, verbose=False):

        def _fmt_path(p):
            if self.is_library:
                return os.path.relpath(p, ".")
            else:  # v2 compatibility, remove with migrate
                return p

        lines = []
        if self.file and os.path.exists(self.file):
            status = (str(self.configdir) if self.is_library else self.file) + ' ' + {'default': '(default library)',
                      'v2-global': '(global configuration of papers v2: run `papers migrate`)'}.get(self.origin, '')
        else:
            status = bcolors.WARNING+"(no library found: create one with `papers init`)"+bcolors.ENDC
        lines.append(bcolors.BOLD+f'papers library: {status}'.rstrip()+bcolors.ENDC)
        lines.append(bcolors.BOLD+f'version {__version__}'+bcolors.ENDC)
        if verbose:
            lines.append('* configuration file: '+(_fmt_path(self.file) if self.file and os.path.exists(self.file) else bcolors.WARNING+'none'+bcolors.ENDC))
            lines.append('* global config:      '+self.machine.file+('' if self.machine.exists() else ' (none)'))
            lines.append('* cache directory:    '+CACHE_DIR)
            lines.append('* backup (git):       '+str(self.git))
            if self.git:
                lines.append('* backup files (git-lfs): '+str(self.gitlfs))
                lines.append('* backup directory:   '+str(self.gitdir))

        if self.file is None and self.bibtex is None:
            return '\n'.join(lines)  # no library

        in_pool = self.shallow
        if in_pool:
            # the files of a shallow library are in its pool (see papers.pools.use_pool_files)
            lines.append('* files:              in the pool (shallow library)')
        elif self.filesdir is None:
            lines.append('* files:              linked where they are (no files directory)')
        else:
            notes = ['the files directory of the library']
            if not os.path.exists(self.filesdir):
                notes.append(bcolors.WARNING+'missing'+bcolors.ENDC)
            elif not os.listdir(self.filesdir):
                notes.append(bcolors.WARNING+'empty'+bcolors.ENDC)
            elif check_files:
                file_count, folder_size = check_filesdir(self.filesdir)
                notes.append(bcolors.OKBLUE+"{} files, {:.1f} MB".format(file_count, folder_size/(1024*1024.0))+bcolors.ENDC)
            lines.append(f'* files:              {_fmt_path(self.filesdir)} ({", ".join(notes)})')
        if in_pool:
            note = ' (the files added are moved into the pool)' if (self.files or 'move') == 'move' else \
                ' (the files added are copied into the pool)' if self.files == 'copy' else \
                ' (the files added stay where they are, the pool entry links to them there)'
        else:
            note = ' (no files directory: the files are linked where they are)' if self.filesdir is None else ''
        lines.append(f'* files mode:         {self.files or "move"}' + note)

        if self.bibtex is None:
            status = bcolors.WARNING+' (unset)'+bcolors.ENDC
        elif not os.path.exists(self.bibtex):
            status = bcolors.WARNING+' (missing)'+bcolors.ENDC
        elif check_files:
            try:
                bibtexstring = open(self.bibtex).read()
                db = parse_string(bibtexstring)
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
        lines.append(f'* bibtex:             {_fmt_path(self.bibtex) if self.bibtex else self.bibtex}'+status)

        if self.file:
            from papers.pools import status_line  # papers.pools imports this module
            if self.shallow or verbose:
                lines.append('* pool:               ' + status_line(self))
            if self.shallow:
                if self.auto_push:
                    text = 'true (the commands push the entries they change to the pool)'
                else:
                    text = 'false (add adds the new entries to the pool; push or sync sends the changes)'
                lines.append('* auto-push:          ' + text)

        if verbose:
            lines.append('* settings:')
            lines.extend('    '+line for line in self.settings_lines())

        return '\n'.join(lines)
