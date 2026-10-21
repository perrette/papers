"""The files of a library: what `add` does with a file (the `files` setting),
and the file operations of `papers file`, `papers rm`.

Links of the bibtex are compared by real path (symbolic links resolved).
"""
import os
import tempfile

from papers import logger
from papers.bib import DOWNLOAD_PREFIX
from papers.config import Config, LIBRARY_CONFIG_FILES
from papers.utils import search_config


FILES_MODES = ('move', 'copy', 'link')


def realpath(path):
    return os.path.normcase(os.path.realpath(path))


def is_inside(path, folder):
    "path is folder or inside it (real paths)"
    if folder is None:
        return False
    path, folder = realpath(path), realpath(folder)
    return path == folder or path.startswith(folder.rstrip(os.path.sep) + os.path.sep)


def is_download(file):
    "a file downloaded by papers into a temporary directory (see bib.download_url)"
    parent = os.path.dirname(os.path.abspath(file))
    return (os.path.basename(parent).startswith(DOWNLOAD_PREFIX)
            and is_inside(parent, tempfile.gettempdir()))


class OtherLibraries:
    """finds the library a file belongs to: a library whose configuration is
    found in the file's directory or above, and whose files directory
    contains the file (only the files directory is checked, not the links
    of the library's bibtex)"""

    def __init__(self, current=None, machine=None):
        "current: configuration file of the current library (not an other library)"
        self.current = realpath(current) if current else None
        self.machine = machine
        self._cache = {}

    def _config(self, configfile):
        if configfile not in self._cache:
            try:
                self._cache[configfile] = Config.load(configfile, machine=self.machine)
            except Exception as error:
                logger.debug(f'{configfile}: {error}')
                self._cache[configfile] = None
        return self._cache[configfile]

    def owner(self, file):
        "configuration of the other library whose files directory holds `file`, or None"
        start = os.path.dirname(os.path.abspath(file))
        while True:
            configfile = search_config(LIBRARY_CONFIG_FILES, start_dir=start, default=None)
            if configfile is None:
                return None
            # the configuration file is in <library>/ or <library>/.papers/
            libdir = os.path.dirname(configfile)
            if os.path.basename(libdir) == '.papers':
                libdir = os.path.dirname(libdir)
            if self.current is None or realpath(configfile) != self.current:
                config = self._config(configfile)
                if config is not None and config.filesdir and is_inside(file, config.filesdir):
                    return config
            parent = os.path.dirname(libdir)
            if parent == libdir:
                return None
            start = parent


class FilesPolicy:
    """what to do with each file placed in the files directory (the `copy`
    argument of Biblio.rename_entry_files): 'move', 'copy' (a hard link when
    possible) or 'link' (leave it where it is).

    - mode is the `files` setting (or its command-line override);
    - a file that belongs to another library (see OtherLibraries) is never
      moved: `move` falls back to `copy` for it, so that the other library
      keeps its link;
    - a file already in the library's files directory is moved (renamed)
      in copy mode too, since a copy would leave an unlinked file there;
    - a file downloaded by papers into a temporary directory is always moved;
    - `keep` lists files to leave where they are, whatever the mode (e.g. the
      files an entry already had before `file attach`).

    TODO (light libraries): in a light library, files are placed in the
    files directory of the first pool instead.
    """

    def __init__(self, mode, filesdir=None, current_config=None, machine=None, keep=()):
        if mode not in FILES_MODES:
            raise ValueError(f'files mode must be one of {", ".join(FILES_MODES)}, got {mode!r}')
        self.mode = mode
        self.filesdir = filesdir
        self.others = OtherLibraries(current_config, machine=machine)
        self.keep = {realpath(f) for f in keep}
        self._said = set()

    def __call__(self, file):
        if is_download(file):
            return 'move'
        if realpath(file) in self.keep:
            return 'link'
        if self.mode == 'link':
            return 'link'
        if is_inside(file, self.filesdir):
            return 'move'
        if self.mode == 'move':
            owner = self.others.owner(file)
            if owner is not None:
                if file not in self._said:
                    print(f'{file} belongs to the library in {owner.configdir}: copied, not moved')
                    self._said.add(file)
                return 'copy'
        return self.mode
