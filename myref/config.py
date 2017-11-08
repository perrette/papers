import os, json, logging
import subprocess as sp, sys, shutil

GIT = False

# config directory location
HOME = os.environ.get('HOME',os.path.expanduser('~'))
CONFIG_HOME = os.environ.get('XDG_CONFIG_HOME', os.path.join(HOME, '.config'))
CACHE_HOME = os.environ.get('XDG_CACHE_HOME', os.path.join(HOME, '.cache'))
DATA_HOME = os.environ.get('XDG_DATA_HOME', os.path.join(HOME, '.local','share'))


CONFIG_FILE = os.path.join(CONFIG_HOME, 'myrefconfig.json')
DATA_DIR = os.path.join(DATA_HOME, 'myref')
CACHE_DIR = os.path.join(CACHE_HOME, 'myref')


class Config(object):
    """configuration class to specify system-wide collections and files-dir
    """
    def __init__(self, file=CONFIG_FILE, data=DATA_DIR, cache=CACHE_DIR, 
        bibtex=None, filesdir=None, gitdir=None, git=False):
        self.file = file
        self.data = data
        self.cache = cache
        self.filesdir = filesdir or os.path.join(data, 'files')
        self.bibtex = bibtex  or os.path.join(data, 'myref.bib')
        self.gitdir = gitdir  or data
        self.git = git

    def collections(self):
        files = []
        for root, dirs, files in os.walk(os.path.dirname(self.bibtex)):
            break
        # return sorted(f[:-4] for f in files if f.endswith('.bib'))
        return sorted(f for f in files if f.endswith('.bib'))

    def save(self):
        json.dump({
            "filesdir":self.filesdir,
            "bibtex":self.bibtex,
            "git":self.git,
            "gitdir":self.gitdir,
            }, open(self.file, 'w'), sort_keys=True, indent=2, separators=(',', ': '))


    def load(self):
        js = json.load(open(self.file))
        self.bibtex = js.get('bibtex', self.bibtex)
        self.filesdir = js.get('filesdir', self.filesdir)
        self.git = js.get('git', self.git)
        self.gitdir = js.get('gitdir', self.gitdir)


    def reset(self):
        cfg = type(self)()
        self.bibtex = cfg.bibtex
        self.filesdir = cfg.filesdir


    def check_install(self):
        if not os.path.exists(self.cache):
            logging.info('make cache directory for DOI requests: '+self.cache)
            os.makedirs(self.cache)


    # make a git commit?
    @property
    def _gitdir(self):
        return os.path.join(self.gitdir, '.git')

    def gitinit(self, branch=None):
        if not os.path.exists(self._gitdir):
            # with open(os.devnull, 'w') as shutup:
            sp.check_call(['git','init'], cwd=self.gitdir)
        else:
            raise ValueError('git is already initialized in '+self.gitdir)

    def gitcommit(self, branch=None, message=None):
        if os.path.exists(self._gitdir):
            target = os.path.join(self.gitdir, os.path.basename(self.bibtex))
            if not os.path.samefile(self.bibtex, target):
                shutil.copy(self.bibtex, target)
            message = message or 'save '+self.bibtex+' after command:\n\n    myref ' +' '.join(sys.argv[1:])
            with open(os.devnull, 'w') as shutup:
                if branch is not None:
                    sp.check_call(['git','checkout',branch], stdout=shutup, stderr=shutup, cwd=self.gitdir)
                sp.check_call(['git','add',target], stdout=shutup, stderr=shutup, cwd=self.gitdir)
                sp.check_call(['git','commit','-m', message], stdout=shutup, stderr=shutup, cwd=self.gitdir)
        else:
            raise ValueError('git is not initialized in '+self.gitdir)



    def status(self, check_files=False, verbose=False):

        import bibtexparser
        from myref.tools import check_filesdir, bcolors

        lines = []
        lines.append(bcolors.BOLD+'myref configuration'+bcolors.ENDC)
        if verbose:
            lines.append('* configuration file: '+self.file) 
            lines.append('* cache directory:    '+self.cache) 
            # lines.append('* app data directory: '+self.data) 
            lines.append('* git-tracked:        '+str(self.git)) 
            if self.git:
                lines.append('* git directory :     '+self.gitdir) 

        if not os.path.exists(self.filesdir):
            status = bcolors.WARNING+' (missing)'+bcolors.ENDC
        elif not os.listdir(self.filesdir):
            status = bcolors.WARNING+' (empty)'+bcolors.ENDC
        elif check_files:
            file_count, folder_size = check_filesdir(self.filesdir)
            status = bcolors.OKBLUE+" ({} files, {:.1f} MB)".format(file_count, folder_size/(1024*1024.0))+bcolors.ENDC
        else:
            status = ''

        files = self.filesdir
        lines.append('* files directory:    '+files+status) 

        if not os.path.exists(self.bibtex):
            status = bcolors.WARNING+' (missing)'+bcolors.ENDC 
        elif check_files:
            try:
                db = bibtexparser.load(open(self.bibtex))
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
        lines.append('* bibtex:            '+self.bibtex+status)

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