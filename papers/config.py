import os, json
from pathlib import Path
import subprocess as sp, sys
import hashlib
import bibtexparser
from papers import logger
from papers.filename import Format, NAMEFORMAT, KEYFORMAT
from papers import __version__
from papers.utils import bcolors, check_filesdir, search_config

# GIT = False
DRYRUN = False

# config directory location
HOME = os.environ.get('HOME',os.path.expanduser('~'))
CONFIG_HOME = os.environ.get('XDG_CONFIG_HOME', os.path.join(HOME, '.config'))
CACHE_HOME = os.environ.get('XDG_CACHE_HOME', os.path.join(HOME, '.cache'))
DATA_HOME = os.environ.get('XDG_DATA_HOME', os.path.join(HOME, '.local','share'))

CONFIG_FILE_LEGACY = os.path.join(CONFIG_HOME, 'papersconfig.json')
CONFIG_FILE = os.path.join(DATA_HOME, 'config.json')
CONFIG_FILE_LOCAL = '.papers/config.json'
DATA_DIR = os.path.join(DATA_HOME, 'papers')
CACHE_DIR = os.path.join(CACHE_HOME, 'papers')


class Config:
    """configuration class to specify system-wide collections and files-dir
    """
    def __init__(self, file=None, data=DATA_DIR,
        bibtex=None, filesdir=None,
        keyformat=KEYFORMAT,
        nameformat=NAMEFORMAT,
        editor=None,
        gitdir=None, git=False, gitlfs=False, local=None, absolute_paths=None, backup_files=False):
        self.file = file
        self.local = local
        self.data = data
        self.filesdir = filesdir
        self.editor = editor
        self.bibtex = bibtex
        self.keyformat = keyformat
        self.nameformat = nameformat
        if absolute_paths is None:
            absolute_paths = False if local else True
        self.absolute_paths = absolute_paths
        self.gitdir = gitdir  or data
        self.git = git
        self.gitlfs = gitlfs
        self.backup_files = backup_files


    @property
    def editor(self):
        return self._editor

    @editor.setter
    def editor(self, value):
        if value is not None:
            os.environ['EDITOR'] = value
        self._editor = value

    def collections(self):
        files = []
        for root, dirs, files in os.walk(os.path.dirname(self.bibtex)):
            break
        # return sorted(f[:-4] for f in files if f.endswith('.bib'))
        return sorted(f for f in files if f.endswith('.bib'))

    @property
    def root(self):
        if self.local and self.bibtex:
            return Path(self.bibtex).parent.resolve()
        else:
            return Path(os.path.sep)

    def gitcmd(self, cmd, check=True, **kw):
        return (sp.check_call if check else sp.call)(f"git {cmd}", shell=True, cwd=self.gitdir, **kw)


    def _relpath(self, p):
        if p is None: return p
        if not self.local:
            return str(Path(p).resolve())  # abspath

        # otherwise express path relative to bibtex (parent of config file)
        try:
            # logger.info(f"rel path: (p)", p)
            return str((self.root / p).relative_to(self.root))
        except Exception as error:
            print(error)
            logger.warn(f"config :: can't save {p} as relative path to {self.root}")
            return p

    def _abspath(self, p, root=None):
        if p is None: return p
        if not self.local:
            return str(Path(p).resolve())  # abspath
        p2 = str((Path(root).resolve() if root is not None else self.root) / p)
        return p2


    def save(self):
        json.dump({
            "filesdir": self._relpath(self.filesdir),
            "bibtex": self._relpath(self.bibtex),
            "gitdir": self._relpath(self.gitdir),
            "editor": self.editor,
            "keyformat": self.keyformat.todict(),
            "nameformat": self.nameformat.todict(),
            "local": self.local,
            "absolute_paths": self.absolute_paths,
            "git": self.git,
            "gitlfs": self.gitlfs,
            "backup_files": self.backup_files,
            }, open(self.file, 'w'), sort_keys=True, indent=2, separators=(',', ': '))


    @classmethod
    def load(cls, file):
        js = json.load(open(file))
        if 'nameformat' in js:
            js['nameformat'] = Format(**js.get('nameformat'))
        if 'keyformat' in js:
            js['keyformat'] = Format(**js.get('keyformat'))
        cfg = cls(file=file, **js)
        cfg._update_paths_to_absolute()
        return cfg


    def _update_paths_to_absolute(self):
        if self.file is None:
            logger.warn("_update_paths_to_absolute: only works if Config.file is defined")
            return
        root = Path(self.file).parent.parent
        for field in ['bibtex', 'filesdir', 'gitdir']:
            setattr(self, field, self._abspath(getattr(self, field), root))


    def status(self, check_files=False, verbose=False):

        def _fmt_path(p):
            if self.local:
                return os.path.relpath(p, ".")
            else:
                return p

        lines = []
        if self.file and os.path.exists(self.file):
            status = "(local)" if self.local else "(global)"
        else:
            status = bcolors.WARNING+"(default, not installed)"+bcolors.ENDC
        lines.append(bcolors.BOLD+f'papers configuration {status}'+bcolors.ENDC)
        lines.append(bcolors.BOLD+f'version {__version__}'+bcolors.ENDC)
        if verbose:
            lines.append('* configuration file: '+(_fmt_path(self.file) if self.file and os.path.exists(self.file) else bcolors.WARNING+'none'+bcolors.ENDC))
            lines.append('* cache directory:    '+CACHE_DIR)
            lines.append('* absolute paths:     '+str(self.absolute_paths))
            # lines.append('* app data directory: '+self.data)
            lines.append('* git-tracked:        '+str(self.git))
            if self.git:
                lines.append('* git-lfs tracked:    '+str(self.gitlfs))
                lines.append('* git directory :     '+self.gitdir)
            lines.append('* editor:             '+str(self.editor))

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
                db = bibtexparser.loads(bibtexstring)
                if len(db.entries):
                    status = bcolors.OKBLUE+' ({} entries)'.format(len(db.entries))+bcolors.ENDC
                else:
                    status = bcolors.WARNING+' (empty)'+bcolors.ENDC
            except:
                status = bcolors.FAIL+' (corrupted)'+bcolors.ENDC
        elif os.path.getsize(self.bibtex) == 0:
            status = bcolors.WARNING+' (empty)'+bcolors.ENDC
        else:
            status = ''
        lines.append(f'* bibtex:             {_fmt_path(self.bibtex) if self.bibtex else self.bibtex}'+status)

        # if verbose:
        #     collections = self.collections()
        #     status = bcolors.WARNING+' none'+bcolors.ENDC if not collections else ''
        #     lines.append('* other collections:'+status)
        #     for i, nm in enumerate(collections):
        #         if i > 10:
        #             lines.append('    '+'({} more collections...)'.format(len(collections)-10))
        #             break
        #         status = ' (*)' if nm == self.collection else ''
        #         lines.append('    '+nm+status)



        return '\n'.join(lines)


def _init_cache():
    if not os.path.exists(CACHE_DIR):
        logger.info('make cache directory for DOI requests: '+CACHE_DIR)
        os.makedirs(CACHE_DIR)

_init_cache()

def cached(file, hashed_key=False):

    file = os.path.join(CACHE_DIR, file)

    def decorator(fun):
        if os.path.exists(file):
            cache = json.load(open(file))
        else:
            cache = {}
        def decorated(doi):
            if hashed_key: # use hashed parameter as key (for full text query)
                key = hashlib.sha256(doi.encode('utf-8')).hexdigest()[:6]
            else:
                key = doi
            if key in cache:
                logger.debug('load from cache: '+repr((file, key)))
                return cache[key]
            else:
                res = cache[key] = fun(doi)
                if not DRYRUN:
                    json.dump(cache, open(file,'w'))
            return res
        return decorated
    return decorator