import os, json
import contextlib
import copy
import tempfile
from pathlib import Path
import hashlib
import time
from urllib.parse import quote
import platformdirs

from papers.entries import parse_string
from papers import logger
from papers.filename import Format, NAMEFORMAT, KEYFORMAT
from papers import __version__
from papers.utils import bcolors, check_filesdir, search_config

# GIT = False
DRYRUN = False

# platform-appropriate locations (on Linux these honor the XDG variables and
# match the paths previous versions derived by hand; they differ on
# macOS/Windows, where the legacy locations below are checked for migration)
CONFIG_FILE = os.path.join(platformdirs.user_config_dir(), 'papersconfig.json')
CONFIG_FILE_LOCAL = '.papersconfig.json'
# file names of a library configuration (.papers/config.json: older versions)
LIBRARY_CONFIG_FILES = [CONFIG_FILE_LOCAL, os.path.join('.papers', 'config.json')]

DATA_DIR = platformdirs.user_data_dir('papers')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
CACHE_DIR = platformdirs.user_cache_dir('papers')

# locations used by previous versions (XDG conventions on every platform),
# kept for migration and for listing pre-existing backup directories
HOME = os.environ.get('HOME', os.path.expanduser('~'))
_CONFIG_HOME_LEGACY = os.environ.get('XDG_CONFIG_HOME', os.path.join(HOME, '.config'))
_DATA_HOME_LEGACY = os.environ.get('XDG_DATA_HOME', os.path.join(HOME, '.local', 'share'))
CONFIG_FILE_LEGACY = os.path.join(_DATA_HOME_LEGACY, 'config.json')
CONFIG_FILE_LEGACY_XDG = os.path.join(_CONFIG_HOME_LEGACY, 'papersconfig.json')
BACKUP_DIR_LEGACY = os.path.join(_DATA_HOME_LEGACY, 'papers', 'backups')


# per-machine configuration: pool names and default settings for libraries
MACHINE_CONFIG_FILE = os.path.join(platformdirs.user_config_dir('papers'), 'config.json')
# pools known without per-machine configuration
DEFAULT_POOLS = {'default': os.path.join('~', 'Documents', 'papers')}


# Settings of `papers config`, by name. The name and key format fields map to
# the attributes of papers.filename.Format (name.author-num -> author_num).
_FORMAT_FIELDS = ['template', 'author-num', 'author-sep', 'title-word-num',
                  'title-word-size', 'title-sep', 'unknown-template', 'unknown-strict']
_NAME_FIELDS = _FORMAT_FIELDS[:5] + ['title-length'] + _FORMAT_FIELDS[5:]
_INT_FIELDS = ['author-num', 'title-word-num', 'title-word-size', 'title-length']

# type of each setting: 'path', 'list', 'bool', 'int', 'str', or a tuple of choices
SETTINGS = {
    'bibtex': 'path',
    'filesdir': 'path',
    'pools': 'list',
    'paths': ('relative', 'absolute'),
    'files': ('move', 'copy', 'link'),
    'git': 'bool',
    'git-lfs': 'bool',
    'editor': 'str',
}
for _field in _NAME_FIELDS:
    SETTINGS['name.' + _field] = 'int' if _field in _INT_FIELDS else ('bool' if _field == 'unknown-strict' else 'str')
for _field in _FORMAT_FIELDS:
    SETTINGS['key.' + _field] = 'int' if _field in _INT_FIELDS else ('bool' if _field == 'unknown-strict' else 'str')

# settings that only make sense for a library (the per-machine configuration
# names its pools with pools.NAME instead)
LIBRARY_ONLY = ('bibtex', 'filesdir', 'pools')
# settings a library inherits from the per-machine configuration when unset
INHERITED = [name for name in SETTINGS if name not in ('bibtex', 'filesdir')]


def default_value(name):
    "built-in default of a setting"
    if name.startswith('name.'):
        return getattr(NAMEFORMAT, _attr(name))
    if name.startswith('key.'):
        return getattr(KEYFORMAT, _attr(name))
    return copy.deepcopy({'pools': ['default'], 'paths': 'relative', 'files': 'move', 'git': False,
                          'git-lfs': False, 'editor': None}.get(name))


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
        if js.get('absolute_paths') is not None:  # files of v2
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
    if kind == 'list':
        return list(values)
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
    if isinstance(value, list):
        return ' '.join(value)
    return str(value)


def short_home(path):
    "a path under the home directory as ~/..., as written in the per-machine configuration"
    home = os.path.expanduser('~')
    path = os.path.abspath(path)
    if path == home or path.startswith(home + os.path.sep):
        return '~' + path[len(home):]
    return path


def is_pool_path(pool):
    """a pool entry of a library is a path if it contains a path separator or
    starts with '.' or '~', otherwise a name of the per-machine configuration"""
    return (os.path.sep in pool or (os.path.altsep and os.path.altsep in pool)
            or pool.startswith(('.', '~')))


class MachineConfig:
    """per-machine configuration: pool names and the defaults of library settings

    The file has the layout of a library configuration, except that `pools`
    maps names to paths (~ allowed):
        {"pools": {"default": "~/Documents/papers"}, "editor": "vim",
         "nameformat": {"template": "{author}_{year}"}}
    """
    def __init__(self, file=None, data=None):
        self.file = file
        self.data = data if data is not None else {}

    @classmethod
    def load(cls, file=None):
        file = file or MACHINE_CONFIG_FILE
        data = {}
        if os.path.exists(file):
            try:
                data = json.load(open(file))
            except (json.JSONDecodeError, OSError) as error:
                logger.warning(f"unreadable per-machine configuration {file}: {error} -- ignored")
        return cls(file, data)

    def exists(self):
        return self.file is not None and os.path.exists(self.file)

    def get(self, name):
        if name == 'pools':
            return None  # a library's list; see self.pools for the names
        return json_get(self.data, name)

    def set(self, name, value):
        json_set(self.data, name, value)

    @property
    def pools(self):
        "pool names and their paths, as written (with ~)"
        return {**DEFAULT_POOLS, **self.data.get('pools', {})}

    def pool_path(self, name):
        path = self.pools.get(name)
        return os.path.abspath(os.path.expanduser(path)) if path else None

    def set_pool(self, name, path):
        pools = self.data.setdefault('pools', {})
        if path is None:
            pools.pop(name, None)
            if not pools:
                del self.data['pools']
        else:
            pools[name] = path

    def save(self):
        os.makedirs(os.path.dirname(self.file), exist_ok=True)
        json.dump(self.data, open(self.file, 'w'), sort_keys=True, indent=2, separators=(',', ': '))


class Config:
    """configuration of a library

    Each setting comes from the library's configuration file, else from the
    per-machine configuration, else from its built-in default. The attributes
    hold the resulting values; `explicit` names the settings set in the file.
    """
    def __init__(self, file=None,
        bibtex=None, filesdir=None,
        keyformat=None,
        nameformat=None,
        editor=None,
        gitdir=None, git=None, gitlfs=None, local=None, absolute_paths=None, backup_files=None,
        pools=None, files=None, machine=None):
        self.file = file
        self.local = local
        self.machine = machine if machine is not None else MachineConfig.load()
        # how the configuration was found (see papers.__main__.find_config)
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
        if gitlfs is None:
            gitlfs = backup_files if backup_files is not None else self.inherited('git-lfs')
        self.gitlfs = gitlfs
        self.pools = list(pools) if pools is not None else self.inherited('pools')
        # what `add` does with a file: move or copy it into the files
        # directory, or link it where it is (see papers.files.FilesPolicy)
        self.files = files if files is not None else self.inherited('files')


    @property
    def editor(self):
        return self._editor

    @editor.setter
    def editor(self, value):
        if value is not None:
            os.environ['EDITOR'] = value
        self._editor = value

    @property
    def backup_files(self):
        "the files are backed up with git-lfs"
        return self.gitlfs

    @backup_files.setter
    def backup_files(self, value):
        self.gitlfs = value

    # settings by name (see SETTINGS)
    # -------------------------------
    def inherited(self, name):
        "value of a setting when the library does not set it"
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
        return getattr(self, name)

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
            setattr(self, name, value)
        self.explicit.add(name)

    def unset(self, name):
        "remove a setting from the library: it is inherited again"
        self.explicit.discard(name)
        self.set(name, None if name in ('bibtex', 'filesdir') else self.inherited(name))
        self.explicit.discard(name)

    def is_set(self, name):
        "the library sets this setting (in its file, or changed since loaded)"
        if name in ('bibtex', 'filesdir'):
            return getattr(self, name) is not None
        return name in self.explicit or self.get(name) != self.inherited(name)

    def source(self, name):
        "where the value of a setting comes from: library, machine or default"
        if self.file and self.is_set(name):
            return 'library'
        if name not in ('bibtex', 'filesdir') and self.machine.get(name) is not None:
            return 'machine'
        return 'default'

    # pools
    # -----
    def pool_path(self, pool):
        """path of a pool entry: a name of the per-machine configuration, or
        a path relative to the library; None for an unknown name"""
        if not is_pool_path(pool):
            return self.machine.pool_path(pool)
        return os.path.abspath(os.path.join(self.configdir, os.path.expanduser(pool)))

    def collections(self):
        files = []
        for root, dirs, files in os.walk(os.path.dirname(self.bibtex)):
            break
        # return sorted(f[:-4] for f in files if f.endswith('.bib'))
        return sorted(f for f in files if f.endswith('.bib'))

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
    def root(self):
        if self.local and self.bibtex:
            return Path(self.bibtex).parent.resolve()
        else:
            return Path(os.path.sep)

    def gitcmd(self, cmd, check=True):
        from papers.backup import run_git
        return run_git(self.gitdir, cmd, check=check)


    @property
    def configdir(self):
        "directory that relative paths of a local configuration file refer to"
        return Path(self.file).parent.resolve() if self.file else Path.cwd()

    def _relpath(self, p):
        if p is None: return p
        if not self.local:
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
        if not self.local:
            return str(Path(p).resolve())  # abspath
        p2 = str((Path(root).resolve() if root is not None else self.configdir) / p)
        return p2


    def tojson(self):
        """content of the configuration file: the paths, and the settings that
        the library sets (the others are inherited when loaded)"""
        js = {
            "filesdir": self._relpath(self.filesdir),
            "bibtex": self._relpath(self.bibtex),
            "gitdir": self._abspath(self.gitdir), # central gitdir
        }
        for name in INHERITED:
            if self.is_set(name):
                json_set(js, name, self.get(name))
        if not self.local:
            js["local"] = False  # global configuration of v2
        return js

    def save(self):
        json.dump(self.tojson(), open(self.file, 'w'), sort_keys=True, indent=2, separators=(',', ': '))


    @classmethod
    def load(cls, the_file, machine=None, local=None):
        """local=False for a global configuration of v2 (the default tells
        them apart by the file content or name)"""
        js = json.load(open(the_file))
        if local is None:
            local = js.get('local')
        if local is None:
            # v2 global configurations (papersconfig.json, not hidden) are not local
            local = os.path.basename(the_file) != os.path.basename(CONFIG_FILE)
        cfg = cls(file=the_file, local=local, machine=machine,
                  bibtex=js.get('bibtex'), filesdir=js.get('filesdir'), gitdir=js.get('gitdir'))
        if not local and json_get(js, 'paths') is None:
            js['paths'] = 'absolute'  # default of v2 for a global configuration
        for name in INHERITED:
            value = json_get(js, name)
            if value is not None:
                cfg.set(name, value)
        cfg._update_paths_to_absolute()
        return cfg


    def _update_paths_to_absolute(self):
        if self.file is None:
            logger.warning("_update_paths_to_absolute: only works if Config.file is defined")
            return
        root = Path(self.file).parent
        for field in ['bibtex', 'filesdir', 'gitdir']:
            setattr(self, field, self._abspath(getattr(self, field), root))


    def settings_lines(self, names=None):
        "lines `name = value (source)` of `papers config` and `papers status -v`"
        names = names or list(SETTINGS)
        width = max(len(name) for name in names)
        lines = []
        for name in names:
            value = self.get(name)
            if name in ('bibtex', 'filesdir') and value is not None and self.file:
                value = self._relpath(value)
            lines.append(f'{name.ljust(width)} = {format_value(value)}  ({self.source(name)})')
        return lines


    def status(self, check_files=False, verbose=False):

        def _fmt_path(p):
            if self.local:
                return os.path.relpath(p, ".")
            else:
                return p

        lines = []
        if self.file and os.path.exists(self.file):
            status = (str(self.configdir) if self.local else self.file) + ' ' + {'default-pool': '(default pool)',
                      'v2-global': '(global configuration of papers v2: run `papers migrate`)'}.get(self.origin, '')
        else:
            status = bcolors.WARNING+"(no library found: create one with `papers init`)"+bcolors.ENDC
        lines.append(bcolors.BOLD+f'papers library: {status}'.rstrip()+bcolors.ENDC)
        lines.append(bcolors.BOLD+f'version {__version__}'+bcolors.ENDC)
        if verbose:
            lines.append('* configuration file: '+(_fmt_path(self.file) if self.file and os.path.exists(self.file) else bcolors.WARNING+'none'+bcolors.ENDC))
            lines.append('* per-machine config: '+self.machine.file+('' if self.machine.exists() else ' (none)'))
            lines.append('* cache directory:    '+CACHE_DIR)
            lines.append('* backup (git):       '+str(self.git))
            if self.git:
                lines.append('* backup files (git-lfs): '+str(self.gitlfs))
                lines.append('* backup directory:   '+str(self.gitdir))

        if self.file is None and self.bibtex is None:
            return '\n'.join(lines)  # no library

        if self.filesdir is None:
            status = bcolors.WARNING+' (unset)'+bcolors.ENDC
        elif not os.path.exists(self.filesdir):
            status = bcolors.WARNING+' (missing)'+bcolors.ENDC
        elif not os.listdir(self.filesdir):
            status = bcolors.WARNING+' (empty)'+bcolors.ENDC
        elif check_files:
            file_count, folder_size = check_filesdir(self.filesdir)
            status = bcolors.OKBLUE+" ({} files, {:.1f} MB)".format(file_count, folder_size/(1024*1024.0))+bcolors.ENDC
        else:
            status = ''

        lines.append(f'* files directory:    {_fmt_path(self.filesdir) if self.filesdir else self.filesdir}'+status)

        if self.bibtex is None:
            status = bcolors.WARNING+' (unset)'+bcolors.ENDC
        elif not os.path.exists(self.bibtex):
            status = bcolors.WARNING+' (missing)'+bcolors.ENDC
        elif check_files:
            try:
                bibtexstring = open(self.bibtex).read()
                db = parse_string(bibtexstring)
                if len(db.entries):
                    from papers.encoding import parse_file
                    from papers.entries import get_entry_val
                    nfiles = sum(len(parse_file(get_entry_val(e, 'file', ''))) for e in db.entries)
                    status = bcolors.OKBLUE+' ({} entries, {} file links)'.format(len(db.entries), nfiles)+bcolors.ENDC
                else:
                    status = bcolors.WARNING+' (empty)'+bcolors.ENDC
            except:
                status = bcolors.FAIL+' (corrupted)'+bcolors.ENDC
        elif os.path.getsize(self.bibtex) == 0:
            status = bcolors.WARNING+' (empty)'+bcolors.ENDC
        else:
            status = ''
        lines.append(f'* bibtex:             {_fmt_path(self.bibtex) if self.bibtex else self.bibtex}'+status)

        if self.file:
            lines.append('* pools:'+('' if self.pools else ' none'))
            for pool in self.pools:
                path = self.pool_path(pool)
                if path is None:
                    status = bcolors.WARNING+' (unknown pool name)'+bcolors.ENDC
                elif not os.path.exists(path):
                    status = bcolors.WARNING+' (missing)'+bcolors.ENDC
                elif not os.path.exists(os.path.join(path, CONFIG_FILE_LOCAL)):
                    status = bcolors.WARNING+' (not a library)'+bcolors.ENDC
                else:
                    status = ''
                label = pool if not is_pool_path(pool) else ''
                lines.append(f'    {label+": " if label else ""}{path or pool}'+status)

        if verbose:
            lines.append('* settings:')
            lines.extend('    '+line for line in self.settings_lines())

        return '\n'.join(lines)


def _cache_path(folder, key):
    """one json file per key: <folder>/<prefix>/<rest>.json, split at the first
    slash so that DOIs are grouped by registrant (10.1126/science.1166510 ->
    10.1126/science.1166510.json); characters unsafe in file names are quoted"""
    head, sep, tail = key.partition('/')
    if not sep:
        head, tail = key[:2], key
    name = quote(tail, safe='')
    if len(name) > 200:  # file name length limit
        name = hashlib.sha256(tail.encode('utf-8')).hexdigest()
    return os.path.join(folder, quote(head, safe=''), name + '.json')


def _read_cache_file(file):
    if os.path.exists(file):
        try:
            return json.load(open(file))
        except (json.JSONDecodeError, OSError) as error:
            # a corrupt cache file must not break every query
            logger.warning(f"unreadable cache file {file}: {error} -- ignored")
    return None


def _write_cache_file(data, file):
    """atomic replace, so an interrupted write cannot truncate the file"""
    os.makedirs(os.path.dirname(file), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(file),
                               prefix=os.path.basename(file) + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f)
        os.replace(tmp, file)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def _migrate_legacy_cache(legacy, folder, migrate):
    """split a cache of previous versions (one json file for all keys) into
    the per-key files; the legacy file is kept as <legacy>.bak"""
    data = _read_cache_file(legacy)
    if data:
        logger.info(f'migrate cache {legacy} to {folder}')
        for key, value in data.items():
            if migrate:
                value = migrate(value)
            if value is not None:
                # lower-case: DOIs are case-insensitive, and looked up in lower case
                _write_cache_file({'value': value}, _cache_path(folder, key.lower()))
    with contextlib.suppress(OSError):  # another process may have migrated it
        os.replace(legacy, legacy + '.bak')


NOT_FOUND_TTL = 24 * 3600  # seconds


def cached(name, hashed_key=False, legacy=None, migrate=None, trim=None, not_found=None):
    """cache the results of fun(key) as json files under CACHE_DIR/name/

    legacy: cache file of previous versions, migrated on first use (with
        migrate(value) -> value, or None to drop it)
    trim: applied to results before they are stored
    not_found: exception class raised by fun when the key does not exist:
        it is remembered (and raised again) for NOT_FOUND_TTL seconds
    """
    def decorator(fun):
        def decorated(arg):
            key = arg
            folder = os.path.join(CACHE_DIR, name)
            if legacy and not DRYRUN and os.path.exists(os.path.join(CACHE_DIR, legacy)):
                _migrate_legacy_cache(os.path.join(CACHE_DIR, legacy), folder, migrate)
            if hashed_key: # use hashed parameter as key (for full text query)
                key = hashlib.sha256(arg.encode('utf-8')).hexdigest()[:16]
            file = _cache_path(folder, key)
            data = _read_cache_file(file)
            if data and 'value' in data:
                logger.debug('load from cache: '+repr((name, key)))
                return data['value']
            if data and not_found and time.time() - data.get('not_found', 0) < NOT_FOUND_TTL:
                raise not_found(f'{key}: not found (cached until {time.ctime(data["not_found"] + NOT_FOUND_TTL)})')
            try:
                res = fun(arg)
            except Exception as error:
                if not_found and isinstance(error, not_found) and not DRYRUN:
                    _write_cache_file({'not_found': time.time()}, file)
                raise
            if trim:
                res = trim(res)
            if not DRYRUN:
                _write_cache_file({'value': res}, file)
            return res
        return decorated
    return decorator
