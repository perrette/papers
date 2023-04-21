import os, json
from pathlib import Path
import subprocess as sp, sys, shutil
import hashlib
import bibtexparser
from papers import logger
from papers.filename import Format, NAMEFORMAT, KEYFORMAT

# GIT = False
DRYRUN = False

# config directory location
HOME = os.environ.get('HOME',os.path.expanduser('~'))
CONFIG_HOME = os.environ.get('XDG_CONFIG_HOME', os.path.join(HOME, '.config'))
CACHE_HOME = os.environ.get('XDG_CACHE_HOME', os.path.join(HOME, '.cache'))
DATA_HOME = os.environ.get('XDG_DATA_HOME', os.path.join(HOME, '.local','share'))

CONFIG_FILE = os.path.join(CONFIG_HOME, 'papersconfig.json')
DATA_DIR = os.path.join(DATA_HOME, 'papers')
CACHE_DIR = os.path.join(CACHE_HOME, 'papers')

def search_config(filenames, start_dir, default):
    """Thanks Chat GPT !"""
    current_dir = os.path.abspath(start_dir)
    root_dir = os.path.abspath(os.sep)
    while True:
        for filename in filenames:
            file_path = os.path.join(current_dir, filename)
            if os.path.exists(file_path):
                return file_path

        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:
            return default

        # root
        if parent_dir == root_dir:
            return default
        current_dir = parent_dir

    return default


# utils
# -----

class bcolors:
    # https://stackoverflow.com/a/287944/2192272
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def check_filesdir(folder):
    folder_size = 0
    file_count = 0
    for (path, dirs, files) in os.walk(folder):
      for file in files:
        filename = os.path.join(path, file)
        if filename.endswith('.pdf'):
            folder_size += os.path.getsize(filename)
            file_count += 1
    return file_count, folder_size

class Config:
    """configuration class to specify system-wide collections and files-dir
    """
    def __init__(self, file=CONFIG_FILE, data=DATA_DIR, cache=CACHE_DIR,
        bibtex=None, filesdir=None,
        keyformat=KEYFORMAT,
        nameformat=NAMEFORMAT,
        gitdir=None, git=False, gitlfs=False, local=None, absolute_paths=None):
        self.file = file
        self.local = local
        self.data = data
        self.cache = cache
        self.filesdir = filesdir
        self.bibtex = bibtex
        self.keyformat = keyformat
        self.nameformat = nameformat
        if absolute_paths is None:
            absolute_paths = False if local else True
        self.absolute_paths = absolute_paths
        self.gitdir = gitdir  or data
        self.git = git
        self.gitlfs = gitlfs

    def collections(self):
        files = []
        for root, dirs, files in os.walk(os.path.dirname(self.bibtex)):
            break
        # return sorted(f[:-4] for f in files if f.endswith('.bib'))
        return sorted(f for f in files if f.endswith('.bib'))

    @property
    def root(self):
        if self.local:
            return Path(self.bibtex).parent.resolve()
        else:
            return Path(os.path.sep)

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
            "keyformat": self.keyformat.todict(),
            "nameformat": self.nameformat.todict(),
            "local": self.local,
            "absolute_paths": self.absolute_paths,
            "git": self.git,
            }, open(self.file, 'w'), sort_keys=True, indent=2, separators=(',', ': '))


    def load(self):
        js = json.load(open(self.file))
        root = Path(self.file).parent.parent
        self.local = js.get('local', self.local)
        self.bibtex = self._abspath(js.get('bibtex', self.bibtex), root)
        self.filesdir = self._abspath(js.get('filesdir', self.filesdir), root)
        self.gitdir = self._abspath(js.get('gitdir', self.gitdir), root)
        self.nameformat = Format(**js["nameformat"]) if "nameformat" in js else self.nameformat
        self.keyformat = Format(**js["keyformat"]) if "keyformat" in js else self.keyformat
        self.absolute_paths = js.get('absolute_paths', self.absolute_paths)
        self.git = js.get('git', self.git)
        self.gitlfs = js.get('gitlfs', self.gitlfs)


    def reset(self):
        cfg = type(self)()
        self.bibtex = cfg.bibtex
        self.filesdir = cfg.filesdir


    def check_install(self):
        if not os.path.exists(self.cache):
            logger.info('make cache directory for DOI requests: '+self.cache)
            os.makedirs(self.cache)


    # make a git commit?
    @property
    def _gitdir(self):
        return os.path.join(self.gitdir, '.git')

    def gitinit(self, branch=None):
        if not os.path.exists(self._gitdir):
            # with open(os.devnull, 'w') as shutup:
            sp.check_call(['git','init'], cwd=self.gitdir)
            if self.gitlfs:
                try:
                    sp.check_call('git lfs track "files/**"', cwd=self.gitdir, shell=True) # this does not seem to work
                    sp.check_call('git lfs track "pdf/*"', cwd=self.gitdir, shell=True) # pdf tracked via git-lfs
                except Exception as error:
                    logger.warning("Install git-lfs : https://git-lfs.github.com to track PDF files")
                    self.gitlfs = False

        else:
            raise ValueError('git is already initialized in '+self.gitdir)

    def gitcommit(self, branch=None, message=None):
        if os.path.exists(self._gitdir):
            target = os.path.join(self.gitdir, os.path.basename(self.bibtex))
            target_files = os.path.join(self.gitdir, "files")
            if not os.path.samefile(self.bibtex, target):
                shutil.copy(self.bibtex, target)
            message = message or 'save '+self.bibtex+' after command:\n\n    papers ' +' '.join(sys.argv[1:])
            with open(os.devnull, 'w') as shutup:
                if branch is not None:
                    sp.check_call(['git','checkout',branch], stdout=shutup, stderr=shutup, cwd=self.gitdir)
                sp.check_call(['git','add',target], stdout=shutup, stderr=shutup, cwd=self.gitdir)
                if self.gitlfs:
                    sp.check_call(['git','add',target_files], stdout=shutup, stderr=shutup, cwd=self.gitdir)
                res = sp.call(['git','commit','-m', message], stdout=shutup, stderr=shutup, cwd=self.gitdir)
                if res == 0:
                    logger.info('git commit')
        else:
            raise ValueError('git is not initialized in '+self.gitdir)

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
        if verbose:
            lines.append('* configuration file: '+(_fmt_path(self.file) if self.file and os.path.exists(self.file) else bcolors.WARNING+'none'+bcolors.ENDC))
            lines.append('* cache directory:    '+self.cache)
            lines.append('* absolute paths:     '+str(self.absolute_paths))
            # lines.append('* app data directory: '+self.data)
            lines.append('* git-tracked:        '+str(self.git))
            lines.append('* git-lfs tracked:    '+str(self.gitlfs))
            if self.git:
                lines.append('* git directory :     '+self.gitdir)

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




config = Config()
config.check_install()



def cached(file, hashed_key=False):

    file = os.path.join(config.cache, file)

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




def hash_bytestr_iter(bytesiter, hasher, ashexstr=False):
    for block in bytesiter:
        hasher.update(block)
    return (hasher.hexdigest() if ashexstr else hasher.digest())

def file_as_blockiter(afile, blocksize=65536):
    with afile:
        block = afile.read(blocksize)
        while len(block) > 0:
            yield block
            block = afile.read(blocksize)

def checksum(fname):
    """memory-efficient check sum (sha256)

    source: https://stackoverflow.com/a/3431835/2192272
    """
    return hash_bytestr_iter(file_as_blockiter(open(fname, 'rb')), hashlib.sha256())



# move / copy
def move(f1, f2, copy=False, interactive=True):
    dirname = os.path.dirname(f2)
    if dirname and not os.path.exists(dirname):
        logger.info('create directory: '+dirname)
        os.makedirs(dirname)
    if f1 == f2:
        logger.info('dest is identical to src: '+f1)
        return

    if os.path.exists(f2):
        # if identical file, pretend nothing happened, skip copying
        if checksum(f2) == checksum(f1):
            if not copy:
                os.remove(f1)
            return

        elif interactive:
            ans = input('dest file already exists: '+f2+'. Replace? (y/n) ')
            if ans.lower() != 'y':
                return
        else:
            os.remove(f2)

    if copy:
        cmd = 'cp {} {}'.format(f1, f2)
        logger.info(cmd)
        if not DRYRUN:
            shutil.copy(f1, f2)
    else:
        cmd = 'mv {} {}'.format(f1, f2)
        logger.info(cmd)
        if not DRYRUN:
            shutil.move(f1, f2)
