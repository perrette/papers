"""Where `papers file fix` (also `papers file check`, and `papers file
fetch` before it downloads) looks for the file of a broken link beyond the
pool, by the checksum that the library's .papers/files.json has for the
link: in the library itself, and in the other libraries of the machine.

The other libraries are the places of the history store (papers.history:
the bibtex of each library, or bibtex without library, that recorded a step
on this machine), except the current library and the libraries searched
already (its pool, --pool PATH). They are found through the file index
(FileIndex), in the cache folder of the machine: for each checksum, the
files of the other libraries with that content, as the .papers/files.json
of the head state of their place has them. Nothing is read or written in
the other libraries but the files found (their checksum is read).
"""
import json
import os
import re

import papers.checksums
import papers.config
from papers import backup, logger
from papers.config import short_home
from papers.files import is_inside, realpath
from papers.utils import checksum

# of the files of the file index: a file of another format is not read
INDEX_FORMAT = 1
# the name of .papers/files.json among the kept files of a state (history.md 3.3)
FILES_JSON = '.papers/files.json'
_DIGEST = re.compile(r'[0-9a-f]{64}')


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


def index_dir():
    "the folder of the file index (see FileIndex)"
    return os.path.join(papers.config.CACHE_DIR, 'file-index')


def _read_json(path):
    "the content of a file of the index (a dict of format INDEX_FORMAT), or None"
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get('format') == INDEX_FORMAT else None


def _write_json(path, data):
    "write a file of the index through a temporary file and a rename (a cache: not synced to disk)"
    tmp = f'{path}.{os.getpid()}.tmp'
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(dict(data, format=INDEX_FORMAT), f, indent=0, sort_keys=True)
        os.replace(tmp, path)
    except OSError as error:
        logger.debug(f'{path}: not written ({error})')
        try:
            os.remove(tmp)
        except OSError:
            pass


class FileIndex:
    """the files of the libraries of the machine by checksum, in
    <cache dir>/file-index/ (a cache of papers, see the module):

    - <sha256>.json: {"format": 1, "copies": [{"path": ..., "place": ...,
      "state": ...}]}, the files with that content: the absolute path of
      the file, the place (real path of the bibtex) whose .papers/files.json
      has it, and the identifier of the head state of the place in which it
      was indexed;
    - seen.json: {"format": 1, "places": {place: state}}, the head state of
      each place when it was last indexed.

    `update` indexes the places whose head state changed since: the
    difference between the files.json of the two states (all of it, the
    first time), as the states keep it (history.md 3.3; a state without it:
    a library without checksums). A state never changes, so a place whose
    head is the same is not read again. A copy that is gone, or whose
    content changed, is dropped when `find` meets it.

    Several commands may update the index at once: each file is written
    through a temporary file and a rename, the last one wins (a copy lost
    that way comes back when its place changes again; the index is a cache)."""

    def __init__(self, root=None):
        self.root = root or index_dir()
        self.indexed = 0  # the places indexed by update (for the tests)

    def _path(self, digest):
        return os.path.join(self.root, digest + '.json')

    def copies(self, digest):
        data = _read_json(self._path(digest)) if _DIGEST.fullmatch(digest or '') else None
        copies = data.get('copies') if data else None
        return [c for c in copies if isinstance(c, dict)] if isinstance(copies, list) else []

    def _set_copies(self, digest, copies):
        if copies:
            _write_json(self._path(digest), {'copies': copies})
        else:
            try:
                os.remove(self._path(digest))
            except OSError:
                pass

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

    def update(self, config):
        "index the places of the history whose head state changed (see the class)"
        try:
            heads = self.heads(config)
        except Exception as error:
            logger.debug(f'the places of the history not read: {error}')
            return
        seen = (_read_json(os.path.join(self.root, 'seen.json')) or {}).get('places')
        seen = seen if isinstance(seen, dict) else {}
        added, removed = {}, {}  # digest: [copy], digest: {(path, place)}
        places = {}
        for place in sorted(heads):
            if not os.path.isfile(place):
                continue  # moved or deleted: forgotten (its copies are dropped when met)
            project, n = heads[place]
            places[place] = n
            old = seen.get(place)
            if old == n:
                continue
            self.indexed += 1
            before = self.checksums(project, old, place)
            after = self.checksums(project, n, place)
            for path, digest in after.items():
                if before.get(path) != digest:
                    added.setdefault(digest, []).append({'path': path, 'place': place, 'state': n})
            for path, digest in before.items():
                if after.get(path) != digest:
                    removed.setdefault(digest, set()).add((path, place))
        for digest in sorted(set(added) | set(removed)):
            new = added.get(digest, [])
            drop = removed.get(digest, set()) | {(c['path'], c['place']) for c in new}
            copies = [c for c in self.copies(digest) if (c.get('path'), c.get('place')) not in drop] + new
            self._set_copies(digest, copies)
        if places != seen:
            _write_json(os.path.join(self.root, 'seen.json'), {'places': places})

    def find(self, digest, exclude=(), places=(), digests=None):
        """(file, place) of a file with this checksum that exists and has that
        content, not one of `exclude` (real paths) nor of the places
        `places` (real paths of their bibtex), in the order of the places
        and paths; or None. The copies met that are gone (or of a place
        gone), or whose content changed, are dropped from the index."""
        digests = digests or Digests()
        copies = self.copies(digest)
        gone = []
        found = None
        for c in sorted(copies, key=lambda c: (str(c.get('place')), str(c.get('path')))):
            path, place = c.get('path'), c.get('place')
            if not isinstance(path, str) or not isinstance(place, str):
                gone.append(c)
            elif realpath(place) in places or realpath(path) in exclude:
                continue
            elif not os.path.isfile(place) or not os.path.isfile(path) or digests(path) != digest:
                gone.append(c)
            else:
                found = path, place
                break
        if gone:
            self._set_copies(digest, [c for c in copies if not any(c is g for g in gone)])
        return found


def is_own_unlinked(source, file, filesdir):
    "a file of the library's files directory that no entry links to, found by checksum"
    return source.kind == 'own' and source.key is None and bool(filesdir) and is_inside(file, filesdir)


class Lookup:
    """the sources of `papers file fix` beyond the names of the pool (see
    papers.cli.file_cmds.plan_relinks), by checksum: the library, the pool,
    and the other libraries of the machine (the file index, updated when
    first needed). exclude: the bibtex files of the libraries searched
    already (the pool, --pool PATH)."""

    def __init__(self, config, biblio, pool=None, exclude=()):
        self.config = config
        self.biblio = biblio
        self.digests = Digests()
        self.own = OwnLibrary(config, biblio, self.digests)
        self.pool = pool
        self._pool_checksums = None
        self.exclude = {realpath(b) for b in [config.bibtex] + list(exclude) if b}
        self._index = None

    def index(self):
        "the FileIndex, updated once per command"
        if self._index is None:
            self._index = FileIndex()
            self._index.update(self.config)
        return self._index

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
        found = self.index().find(digest, exclude, self.exclude, self.digests)
        return (found[0], Source('other', found[1])) if found else None
