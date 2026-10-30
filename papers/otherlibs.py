"""Where `papers file fix` (also `papers file check`, and `papers file
fetch` before it downloads) looks for the file of a broken link beyond the
pool: the library itself by checksum, and the other libraries of the
machine.

The other libraries are the places of the history store (papers.history:
the bibtex of each library, or bibtex without library, that recorded a step
on this machine), except the current library and the libraries searched
already (its pool, --pool PATH). A place that no longer exists (a library
moved or deleted) is skipped. Each library is read once per command,
without side effects: its configuration, its bibtex (through the parse
cache) and its .papers/files.json; nothing is written in it, it is not
locked, migrated or recorded.
"""
import os

import papers.checksums
from papers import backup, logger
from papers.bib import Biblio
from papers.config import Config, find_library_config, short_home
from papers.duplicate import SAME, IdentityIndex, find_duplicates
from papers.files import is_inside, realpath
from papers.utils import checksum


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
    library of the machine); key: the entry that links to the file (None:
    a file that no entry links to)"""

    def __init__(self, kind, library=None, key=None):
        self.kind = kind
        self.library = library
        self.key = key

    def describe(self):
        if self.kind == 'own':
            return f'same content as the file of {self.key}' if self.key else 'same content, in the library'
        if self.kind == 'pool':
            return 'from the pool, same content'
        return f'found in {self.library.shown}' + (f' (entry {self.key})' if self.key else '')


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
        self.hashes = papers.checksums.load(config) if config.file else {}
        self.checksums = Checksums(self.hashes, digests)
        self.digests = digests
        self._owners = None
        self._unlinked = None

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


class OtherLibrary:
    """a library of the machine (or a bibtex without library: config None),
    read when first used"""

    def __init__(self, bibtex, config, digests):
        self.bibtex = bibtex
        self.config = config
        self.path = config.libdir if config is not None else os.path.dirname(bibtex)
        self.shown = short_home(self.path)
        self.digests = digests
        self._biblio = self._index = self._checksums = self._owners = None
        self.readable = True

    def __repr__(self):
        return f'OtherLibrary({self.bibtex!r})'

    @property
    def biblio(self):
        if self._biblio is None and self.readable:
            try:
                self._biblio = Biblio.load(self.bibtex, self.config.filesdir if self.config else None)
            except Exception as error:
                logger.debug(f'{self.bibtex}: not read: {error}')
                self.readable = False
        return self._biblio

    @property
    def index(self):
        if self._index is None:
            # the entries with file links only: an entry without file has nothing to give
            self._index = IdentityIndex([e for e in self.biblio.entries if 'file' in e] if self.biblio else [])
        return self._index

    @property
    def owners(self):
        if self._owners is None:
            self._owners = _linked_by(self.biblio) if self.biblio else {}
        return self._owners

    @property
    def checksums(self):
        if self._checksums is None:
            hashes = {}
            if self.config is not None:
                try:
                    hashes = papers.checksums.load(self.config)
                except Exception as error:
                    logger.debug(f'{self.path}: checksums not read: {error}')
            self._checksums = Checksums(hashes, self.digests)
        return self._checksums

    @property
    def filesdir(self):
        return self.config.filesdir if self.config is not None else None

    def by_checksum(self, digest, exclude=()):
        "(file, Source) of a file with this checksum, or None"
        found = self.checksums.find(digest, exclude)
        if found is None:
            return None
        return found, Source('other', self, self.owners.get(realpath(found)))

    def same_paper(self, e, distinct=None):
        "the entries that are the same paper as `e` (SAME verdict), with at least one file that exists"
        if self.biblio is None:
            return []
        return [x for x, verdict in find_duplicates(e, None, distinct, index=self.index)
                if verdict.kind == SAME and any(os.path.exists(f) for f in self.biblio.get_files(x))]


def other_libraries(config, exclude=(), digests=None):
    """the other libraries of the machine (see the module): the places of the
    history stores, in sorted order, except the bibtex files `exclude`, and
    those that no longer exist"""
    excluded = {realpath(b) for b in exclude if b}
    places = set()
    try:
        for store in backup.all_stores(config):
            for id in store.project_ids():
                places.update(store.project(id).heads())
    except Exception as error:
        logger.debug(f'the places of the history not read: {error}')
    digests = digests or Digests()
    libraries = []
    for place in sorted(places):
        if not os.path.isfile(place) or realpath(place) in excluded:
            continue
        excluded.add(realpath(place))
        other = None
        try:
            configfile = find_library_config(os.path.dirname(place))
            if configfile is not None:
                other = Config.load(configfile, machine=config.machine)
                if not other.bibtex or realpath(other.bibtex) != realpath(place):
                    other = None  # a bibtex inside a library folder, not its bibtex
        except Exception as error:
            logger.debug(f'{place}: configuration not read: {error}')
            continue
        libraries.append(OtherLibrary(place, other, digests))
    return libraries


def is_own_unlinked(source, file, filesdir):
    "a file of the library's files directory that no entry links to, found by checksum"
    return source.kind == 'own' and source.key is None and bool(filesdir) and is_inside(file, filesdir)


class Lookup:
    """the sources of `papers file fix` beyond the names of the pool (see
    papers.cli.file_cmds.plan_relinks): the library by checksum, the pool
    by checksum, and the other libraries of the machine (read when first
    needed). exclude: the bibtex files of the libraries searched already
    (the pool, --pool PATH)."""

    def __init__(self, config, biblio, pool=None, exclude=()):
        self.config = config
        self.biblio = biblio
        self.digests = Digests()
        self.own = OwnLibrary(config, biblio, self.digests)
        self.pool = pool
        self._pool_checksums = None
        self.exclude = [config.bibtex] + [b for b in exclude if b]
        self._others = None

    def others(self):
        if self._others is None:
            self._others = other_libraries(self.config, self.exclude, self.digests)
        return self._others

    def in_pool(self, link, exclude=()):
        "(file, Source) of the pool with the checksum of the broken link, or None"
        digest = self.own.digest(link)
        if digest is None or self.pool is None or not self.pool.config.file:
            return None
        if self._pool_checksums is None:
            self._pool_checksums = Checksums(papers.checksums.load(self.pool.config), self.digests)
        found = self._pool_checksums.find(digest, exclude)
        return (found, Source('pool')) if found else None

    def in_others(self, e, broken, exclude=()):
        """the files of the other libraries for the broken links of an entry:
        ({link: [files]}, {link: Source}); by checksum first, then among the
        files of an entry of the same paper (see papers.pools.match_entry_files)"""
        from papers.pools import match_entry_files  # papers.pools imports papers.files
        found, sources = {}, {}
        exclude = set(exclude)
        for link in broken:
            digest = self.own.digest(link)
            if digest is None:
                continue
            for library in self.others():
                hit = library.by_checksum(digest, exclude)
                if hit:
                    found[link], sources[link] = [hit[0]], hit[1]
                    exclude.add(realpath(hit[0]))
                    break
        for library in self.others():
            rest = [link for link in broken if link not in found]
            if not rest:
                break
            for x in library.same_paper(e, self.biblio.distinct):
                left = [f for f in library.biblio.get_files(x) if os.path.exists(f) and realpath(f) not in exclude]
                more = match_entry_files(rest, left, library.filesdir)
                found.update(more)
                sources.update(dict.fromkeys(more, Source('other', library, x.key)))
                exclude.update(realpath(f) for fs in more.values() for f in fs)
                rest = [link for link in rest if link not in more]
                if not rest:
                    break
        return found, sources

    def pdf_of_same_paper(self, e):
        "(file, Source) of the first PDF that exists of an entry of the same paper in the other libraries, or None"
        for library in self.others():
            for x in library.same_paper(e, self.biblio.distinct):
                pdf = next((f for f in library.biblio.get_files(x) if f.lower().endswith('.pdf') and os.path.isfile(f)),
                           None)
                if pdf:
                    return pdf, Source('other', library, x.key)
        return None
