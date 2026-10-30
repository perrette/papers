"""Where `papers file fix` (also `papers file check`, and `papers file
fetch` before it downloads) looks for the file of a broken link beyond the
pool, by the checksum that the library's .papers/files.json has for the
link: in the library itself, and in the other libraries of the machine.

The other libraries are the places of the history store (papers.history:
the bibtex of each library, or bibtex without library, that recorded a step
on this machine), except the current library and the libraries searched
already (its pool, --pool PATH). Their checksums are those of the
.papers/files.json kept in the head state of their place in the history
store, read at each search (OtherLibraries): once per command, and only
when a broken link has a recorded checksum. Nothing is read or written in
the other libraries but the files found (their checksum is read).
"""
import os

import papers.checksums
from papers import backup, logger
from papers.config import short_home
from papers.files import is_inside, realpath
from papers.utils import checksum

# the name of .papers/files.json among the kept files of a state (history.md 3.3)
FILES_JSON = '.papers/files.json'


class Digests:
    "the sha256 of the files read in the command, each file read once"

    def __init__(self):
        self._digests = {}

    def __call__(self, path):
        if path not in self._digests:
            try:
                self._digests[path] = checksum(path).hex()
            except OSError:
                self._digests[path] = None
        return self._digests[path]


class Checksums:
    """the files of a .papers/files.json ({path: sha256}) by checksum: a
    file is found if it exists and still has that content"""

    def __init__(self, hashes, digests):
        self.paths = {}
        for path, digest in sorted(hashes.items()):
            self.paths.setdefault(digest, []).append(path)
        self.digests = digests

    def find(self, digest, exclude=()):
        "a file with this checksum, not one of `exclude` (real paths), or None"
        for path in self.paths.get(digest, []):
            if os.path.isfile(path) and realpath(path) not in exclude and self.digests(path) == digest:
                return path
        return None


class Source:
    """where a file found for a broken link comes from: 'own' (the library
    itself, by checksum), 'pool' (the pool, by checksum) or 'other' (another
    library of the machine, by checksum: place, the real path of its
    bibtex); key: the entry of the library that links to the file (None: a
    file that no entry links to)"""

    def __init__(self, kind, place=None, key=None):
        self.kind = kind
        self.place = place
        self.key = key

    def describe(self):
        if self.kind == 'own':
            return f'same content as the file of {self.key}' if self.key else 'same content, in the library'
        if self.kind == 'pool':
            return 'from the pool, same content'
        return f'found in {short_home(os.path.dirname(self.place))}'


def _linked_by(biblio):
    "{real path: key of the first entry that links to it} of a bibliography"
    owners = {}
    for e in biblio.entries:
        for f in biblio.get_files(e):
            owners.setdefault(realpath(f), e.key)
    return owners


class OwnLibrary:
    """the library itself: a broken link whose checksum .papers/files.json
    has, found in a file of files.json or an unlinked file of the files
    directory with that content"""

    def __init__(self, config, biblio, digests):
        self.config = config
        self.biblio = biblio
        self.digests = digests
        self._hashes = self._checksums = None
        self._owners = None
        self._unlinked = None

    @property
    def hashes(self):
        if self._hashes is None:
            self._hashes = papers.checksums.load(self.config) if self.config.file else {}
        return self._hashes

    @property
    def checksums(self):
        if self._checksums is None:
            self._checksums = Checksums(self.hashes, self.digests)
        return self._checksums

    @property
    def owners(self):
        if self._owners is None:
            self._owners = _linked_by(self.biblio)
        return self._owners

    def digest(self, link):
        "the checksum recorded for a link, or None"
        return self.hashes.get(os.path.normpath(link))

    def unlinked(self):
        "the files of the files directory that no entry links to and files.json does not have"
        if self._unlinked is None:
            self._unlinked = []
            filesdir = self.config.filesdir
            known = {realpath(p) for p in self.hashes}
            if filesdir and os.path.isdir(filesdir):
                for root, dirs, files in os.walk(filesdir):
                    dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
                    for name in sorted(files):
                        path = os.path.join(root, name)
                        if not name.startswith('.') and not name.endswith('.bib') \
                                and realpath(path) not in self.owners and realpath(path) not in known:
                            self._unlinked.append(path)
        return self._unlinked

    def find(self, link, exclude=()):
        "(file, Source) of the library with the content of the broken link `link`, or None"
        digest = self.digest(link)
        if digest is None:
            return None
        found = self.checksums.find(digest, exclude)
        if found is None:
            found = next((f for f in self.unlinked() if realpath(f) not in exclude and self.digests(f) == digest),
                         None)
        if found is None:
            return None
        return found, Source('own', key=self.owners.get(realpath(found)))


class OtherLibraries:
    """the files of the other libraries of the machine by checksum: for each
    place of the history store (but `skip`, real paths of bibtex), the
    .papers/files.json kept in its head state (history.md 3.3; a state
    without it: a library without checksums), read once, when first needed
    (see the module)"""

    def __init__(self, config, digests, skip=()):
        self.config = config
        self.digests = digests
        self.skip = skip
        self._places = None

    @staticmethod
    def heads(config):
        "{place: (project, head state)} of the history stores of the machine"
        heads = {}
        for store in backup.all_stores(config):
            for id in store.project_ids():
                project = store.project(id)
                for place, n in project.head_states().items():
                    heads.setdefault(place, (project, n))
        return heads

    @staticmethod
    def checksums(project, n, place):
        "{absolute path: sha256} of the files.json of the state n of a place ({}: none, or not read)"
        state = project.read_state(n) if n else None
        pieces = ((state or {}).get('files') or {}).get(FILES_JSON)
        if not pieces:
            return {}
        try:
            text = project.store.text(pieces)
        except KeyError as error:  # history.Damaged
            logger.debug(f'{place}: files.json of state {n} not read: {error}')
            return {}
        return papers.checksums.parse_text(text, os.path.dirname(place))

    def places(self):
        "[(place, Checksums)] of the other libraries that exist, in the order of their place"
        if self._places is None:
            self._places = []
            try:
                heads = self.heads(self.config)
            except Exception as error:
                logger.debug(f'the places of the history not read: {error}')
                heads = {}
            for place in sorted(heads):
                if realpath(place) in self.skip or not os.path.isfile(place):
                    continue  # searched already, or moved or deleted
                hashes = self.checksums(*heads[place], place)
                if hashes:
                    self._places.append((place, Checksums(hashes, self.digests)))
        return self._places

    def find(self, digest, exclude=()):
        """(file, place) of a file with this checksum that exists and has that
        content, not one of `exclude` (real paths), in the order of the places
        and paths; or None"""
        for place, checksums in self.places():
            found = checksums.find(digest, exclude)
            if found:
                return found, place
        return None


def is_own_unlinked(source, file, filesdir):
    "a file of the library's files directory that no entry links to, found by checksum"
    return source.kind == 'own' and source.key is None and bool(filesdir) and is_inside(file, filesdir)


class Lookup:
    """the sources of `papers file fix` beyond the names of the pool (see
    papers.cli.file_cmds.plan_relinks), by checksum: the library, the pool,
    and the other libraries of the machine (read when first needed). exclude: the bibtex files of the libraries searched
    already (the pool, --pool PATH)."""

    def __init__(self, config, biblio, pool=None, exclude=()):
        self.config = config
        self.biblio = biblio
        self.digests = Digests()
        self.own = OwnLibrary(config, biblio, self.digests)
        self.pool = pool
        self._pool_checksums = None
        self.exclude = {realpath(b) for b in [config.bibtex] + list(exclude) if b}
        self.others = OtherLibraries(config, self.digests, self.exclude)

    def in_pool(self, link, exclude=()):
        "(file, Source) of the pool with the checksum of the broken link, or None"
        digest = self.own.digest(link)
        if digest is None or self.pool is None or not self.pool.config.file:
            return None
        if self._pool_checksums is None:
            self._pool_checksums = Checksums(papers.checksums.load(self.pool.config), self.digests)
        found = self._pool_checksums.find(digest, exclude)
        return (found, Source('pool')) if found else None

    def in_others(self, link, exclude=()):
        "(file, Source) of another library of the machine with the checksum of the broken link, or None"
        digest = self.own.digest(link)
        if digest is None:
            return None
        found = self.others.find(digest, exclude)
        return (found[0], Source('other', found[1])) if found else None
