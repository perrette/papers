import os, json, logging

GIT = False

# config directory location
HOME = os.environ.get('HOME',os.path.expanduser('~'))
CONFIG_HOME = os.environ.get('XDG_CONFIG_HOME', os.path.join(HOME, '.config'))
CACHE_HOME = os.environ.get('XDG_CACHE_HOME', os.path.join(HOME, '.cache'))
DATA_HOME = os.environ.get('XDG_DATA_HOME', os.path.join(HOME, '.local','share'))


CONFIG_FILE = os.path.join(CONFIG_HOME, 'myref.json')
DATA_DIR = os.path.join(DATA_HOME, 'myref')
CACHE_DIR = os.path.join(CACHE_HOME, 'myref')


class Config(object):
    """configuration class to specify system-wide collections and files-dir
    """
    def __init__(self, file=CONFIG_FILE, data=DATA_DIR, cache=CACHE_DIR, 
        bibtex=None, filesdir=None):
        self.file = file
        self.data = data
        self.cache = cache
        self.filesdir = filesdir or os.path.join(data, 'files')
        self.bibtex = bibtex  or os.path.join(data, 'myref.bib')

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
            }, open(self.file, 'w'), sort_keys=True, indent=2, separators=(',', ': '))


    def load(self):
        js = json.load(open(self.file))
        self.bibtex = js.get('bibtex', self.bibtex)
        self.filesdir = js.get('filesdir', self.filesdir)


    def reset(self):
        cfg = type(self)()
        self.bibtex = cfg.bibtex
        self.filesdir = cfg.filesdir


    def check_install(self):
        if not os.path.exists(self.cache):
            logging.info('make cache directory for DOI requests: '+self.cache)
            os.makedirs(self.cache)


config = Config()
config.check_install()