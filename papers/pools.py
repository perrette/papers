"""Pools: the libraries that a library exchanges entries with.

A library is in one of two states, given by its `pool` setting:

- no pool (`pool: none`, or no setting): the library is self-contained,
  with its own entries and its own files (its files directory);
- a pool (the path of a library, relative to the library or with ~): the
  library is shallow. Its entries link to the files of the pool entries,
  and its new entries (and their files) go to the pool.

The pool of a library has no pool itself (an exchange goes one level).
Any library can also exchange entries with another library given on the
command line (`--pool PATH`), as it does with its pool, except that the
files are copied rather than linked.

- `Pools` resolves the pool of a library, and the libraries given on the
  command line (`push --pool PATH`), to libraries, loaded when first used
  and kept for the run. A library never uses itself as a pool.
- `Origin` is `.papers/origin/` of a library, one file per pool (the pool
  of the library, and each library given with `--pool PATH`): for each
  entry exchanged with the pool, the base of the next three-way merge,
  under the library's key, with the pool's key (`papers-pool-key`) and the
  time (`papers-time`). In a shallow library the record for its pool
  keeps its `file` field: the file links of the pool entry after the
  exchange (the library entry has the same links); otherwise it has no
  `file` field. The file links are not part of the base of the merge
  (papers.merge.EXCHANGE_OWN). The base is the version
  of the side that sent the entry, as sent: the pool entry for `add` and
  `pull`, the library entry for `push`. The receiving side has taken all of it into account (taken,
  kept or declined), so that what it has beyond it shows as its own change
  in the next exchange the other way. The files of earlier pools are kept:
  setting the pool back to one of them, or exchanging with it again,
  finds its records again. Each file also holds the
  modification time of the pool's bibtex at the last exchange with it (a
  pull of all entries that skipped none; a push or an add when the pool had
  not changed since the previous exchange, or that were the first, and a
  push only if it left the pool with nothing that the library does not
  have), so that `status` and `pull --check` can tell that a pool changed
  since.
- `Exchange` does what involves a library and a pool: `add` looking in
  the pool first (`PoolLookup`), `pull`, `push`, the conversions of the
  files of `papers config pool`, and the repair of broken links to pool
  files.
- `export` writes a selection of a library as a new library.

The key of an entry belongs to each library: `pull` and `push` never change
the key of the library they write to. An entry of the library is matched to
its pool entry by the pool key of its origin copy when that pool entry is
the same paper (papers.duplicate.same_paper), else by the identity rule
applied to its origin copy, then to the entry itself (Exchange.pool_entry). An entry is shared with a pool
when the pool has its paper this way (Exchange.sharing), with an origin
record or not: the record is only the base of the merge.
"""
import datetime
import hashlib
import json
import os
import re
from types import SimpleNamespace

from bibtexparser import Library
from bibtexparser.model import Entry, ExplicitComment, Field
from slugify import slugify

import papers.config
from papers import history, journal, lock, logger
from papers.config import Config, CONFIG_FILE_LOCAL, NO_POOL, library_config_file, short_home
from papers.duplicate import (Distinct, IdentityIndex, contradicts, distinct_union, find_duplicates, same_paper,
                              SAME, Verdict)
from papers.entries import (get_entry_val, set_entry_key, entry_copy, parse_string, format_library, format_file,
                            parse_file)
from papers.bib import Biblio, append_abc, read_text
from papers.extract import parse_doi_from_pdf_metadata, parse_dois, pdfhead, pdftail, title_in_text
from papers.files import ATTACHMENT_SEP, FilesPolicy, realpath, is_inside
from papers.install import resolve_install, apply_install, DefaultAsker
from papers.library import get_biblio
from papers.merge import Merge, apply_entry
from papers.utils import PapersExit, checksum, bcolors, write_atomic


class PoolError(PapersExit):
    "a pool that cannot be used (missing, not a library, has a pool)"


# the error of the exchanges without pool
NO_POOL_MESSAGE = 'this library has no pool: give one with `--pool PATH`'


# LIBRARIES
# =========

def create_library(path, machine, bibtex='papers.bib'):
    """create a self-contained library (no pool, its own files) in
    directory `path` (as `papers init` does), and return its
    configuration. With --dry-run, nothing is written: the configuration
    is that of the library to be created."""
    o = SimpleNamespace(bibtex=os.path.join(path, bibtex), filesdir=os.path.join(path, 'files'),
                        reset=False, paths=None, absolute_paths=None, pool=NO_POOL, editor=None)
    plan = resolve_install(Config(machine=machine), o, asker=DefaultAsker(),
                           target=os.path.join(path, CONFIG_FILE_LOCAL))
    if papers.config.DRYRUN:
        print(f'DRYRUN: create the library {path}')
        return plan.config
    os.makedirs(path, exist_ok=True)
    print(f'create the library {path}')
    return Config.load(apply_install(plan).file, machine=machine)


def load_biblio(config):
    "the bibliography of a library, without creating its bibtex if it does not exist yet"
    if config.bibtex and os.path.exists(config.bibtex):
        return get_biblio(config)
    relative_to = os.path.sep if config.absolute_paths else os.path.dirname(config.bibtex)
    return Biblio(filesdir=config.filesdir, nameformat=config.nameformat, keyformat=config.keyformat,
                  relative_to=relative_to, distinct=Distinct.for_library(config.libdir))


def entry_for(entry, source, target, key=None):
    """a copy of `entry` of the bibliography `source`, for the bibliography
    `target`: its file links written for `target`, under `key`"""
    e = entry_copy(entry)
    if key is not None:
        set_entry_key(e, key)
    files = source.get_files(entry)
    if 'file' in e.fields_dict:
        del e['file']
    if files:
        target.set_files(e, files)
    return e


def exchange_copy(entry, source, target, key=None):
    """the copy of an entry that an exchange sends to the other side (see
    entry_for), without the fields that each side keeps for itself
    (papers.merge.EXCHANGE_OWN): its key is given by the receiving side,
    its former keys (ids) are dropped, its file links are written for
    `target` (the receiving side handles the files)"""
    e = entry_for(entry, source, target, key=key)
    if 'ids' in e.fields_dict:
        del e['ids']
    return e


def mtime(file):
    "modification time of a file in nanoseconds, or None"
    try:
        return os.stat(file).st_mtime_ns
    except OSError:
        return None


# POOLS
# =====

def check_readable(pool):
    """a pool with entries that could not be read is not written to: papers
    does not see them, and would add the same papers again"""
    unreadable = getattr(pool.biblio, 'unreadable', ())
    if unreadable:
        from papers.bib import unreadable_message
        raise PapersExit(unreadable_message(short_home(pool.config.bibtex), unreadable)
                         + f'. Fix {short_home(pool.config.bibtex)} before writing to the pool (nothing was changed)')


def not_a_library(what, path):
    """the error for a pool, or a library given on the command line, that is
    not a library: `papers init PATH` creates it (a command given a pool
    never creates it). A missing parent directory may be a disk not mounted."""
    shown = short_home(path)
    parent = os.path.dirname(os.path.abspath(path))
    if os.path.exists(path):
        reason = f'{shown} is not a library (no {CONFIG_FILE_LOCAL})'
    elif not os.path.isdir(parent):
        reason = f'{shown}: {short_home(parent)} does not exist (disk not mounted?)'
    else:
        reason = f'{shown} does not exist'
    return f'{what} {reason}: create it first with `papers init {shown}`'


def library_without_pool(path, machine, what):
    """the configuration of the library in directory `path`, which must
    exist and have no pool: the pool of a shallow library, or the default
    library (`what` names it in the errors)"""
    configfile = library_config_file(path)
    if configfile is None:
        raise PoolError(not_a_library(what, path) + ' (nothing was changed)')
    config = Config.load(configfile, machine=machine)
    if config.has_pool():
        raise PoolError(f'{what} {short_home(path)} has a pool itself ({config.pool_label()}): '
                        'give a library without pool (nothing was changed)')
    return config


def check_poolless(pool):
    """the pool of a library, or a library given with --pool PATH, has no
    pool itself: an exchange goes one level"""
    if pool.config.has_pool():
        raise PoolError(f'{pool.shown} has a pool itself ({pool.config.pool_label()}): '
                        'give a library without pool')


class Pool:
    """a library used as a pool. `id` is how the library names it in its
    origin records (see Pools._id); `shown` is how the messages name it
    (see Pools.resolve)."""

    def __init__(self, id, path, config, shown=None):
        self.id = id
        self.path = path
        self.config = config
        self.shown = shown or short_home(path)
        self._biblio = None
        self._index = None
        self._keys = None  # lower-case key -> pool entry (see entry_of_key)
        self._sizes = None

    def __repr__(self):
        return f'Pool({self.id!r}, {self.path!r})'

    @property
    def label(self):
        return f'pool {self.shown}'

    @property
    def filesdir(self):
        return self.config.filesdir

    @property
    def biblio(self):
        if self._biblio is None:
            self._biblio = load_biblio(self.config)
        return self._biblio

    @property
    def index(self):
        if self._index is None:
            self._index = IdentityIndex(self.biblio.entries)
        return self._index

    def bibtex_mtime(self):
        return mtime(self.config.bibtex)

    def distinct(self, distinct=None):
        "the pairs that are not the same paper of the pool and of `distinct` (see distinct_union)"
        return distinct_union(self.biblio.distinct, distinct)

    def find(self, entry, distinct=None):
        "the pool entry that is the same paper as `entry` (SAME verdict only), or None"
        found = find_duplicates(entry, None, self.distinct(distinct), index=self.index)
        return next((e for e, verdict in found if verdict.kind == SAME), None)

    def entry_of_key(self, key):
        "the pool entry of key `key` (ignoring case), or None"
        if self._keys is None:
            self._keys = {}
            for x in self.biblio.entries:
                self._keys.setdefault(x.key.lower(), x)
        return self._keys.get((key or '').lower()) if key else None

    def by_key(self, key, origin):
        """the pool entry of key `key` (the pool key of an origin record) if
        its identifiers do not contradict the origin copy: found this way
        when the title (the only identifier of entries without DOI) changed
        on both sides"""
        pe = self.entry_of_key(key)
        if pe is None or contradicts(pe, origin):
            return None
        return pe

    def find_doi(self, doi):
        return self.find(Entry('misc', 'doi', [Field('doi', doi)]))

    def find_file(self, file):
        """(pool entry, pool file) of a pool file with the content of `file`
        (compared by size, then checksum), or (None, None)"""
        if self._sizes is None:
            self._sizes = {}
            for e in self.biblio.entries:
                for f in self.biblio.get_files(e):
                    if os.path.isfile(f):
                        self._sizes.setdefault(os.path.getsize(f), []).append((e, f))
        try:
            size = os.path.getsize(file)
        except OSError:
            return None, None
        hash_ = None
        for e, f in self._sizes.get(size, []):
            if realpath(f) == realpath(file):
                return e, f
            hash_ = hash_ or checksum(file)
            if checksum(f) == hash_:
                return e, f
        return None, None

    def add_entry(self, e):
        "keep the lookups up to date after an entry was added to the pool"
        if self._index is not None:
            self._index.add(e)
        if self._keys is not None:
            self._keys.setdefault(e.key.lower(), e)
        self._sizes = None

    def update_entry(self, e, new):
        "replace the content of a pool entry (keeping the lookups up to date)"
        if self._index is not None:
            self._index.remove(e)
        key = e.key
        apply_entry(e, new)
        if e.key != key:
            self._keys = None
        self.add_entry(e)


class Pools:
    """the pool of a library (its `pool` setting) and the pools named on the
    command line, resolved when first used and kept for the run"""

    def __init__(self, config):
        self.config = config
        self._cache = {}
        # the pool ids of the origin records of the library (see _id)
        self.known_ids = []
        # called with (former id, new id, path) when the records of a pool move to its library id (see _id)
        self.renamed = None
        # called with (id, path) for a pool named by its library id: where it is, for its origin file
        self.located = None

    @property
    def libdir(self):
        "the directory of the library (a relative pool setting is relative to it)"
        return str(self.config.configdir) if self.config.file else os.getcwd()

    def _is_self(self, path):
        return self.config.file is not None and realpath(path) == realpath(self.libdir)

    def set_known_ids(self, ids):
        """the pool ids of the origin records of the library: a pool keeps
        the id that its records use, however it is given"""
        self.known_ids = sorted(ids)
        for pool_ in self._cache.values():
            pool_.id = self._id(pool_.path)

    def _id(self, path):
        """how the origin records name the pool in `path`: the identifier of
        the pool library (its `id`, which stays when a library moves); the
        records under a former id, the pool's path as the library wrote it,
        move to it (see `renamed`). A pool without identifier (a library of an
        earlier version that never recorded a step): the id of its records if
        it has some, else for the pool of the library its pool setting, else
        its path relative to the library."""
        own_id = _library_id(path)
        former = next((id for id in self.known_ids if id != own_id and _is_path_id(id) and
                       realpath(os.path.join(self.libdir, os.path.expanduser(id))) == realpath(path)), None)
        if former is not None and self.renamed is None:
            return former  # the records move at the next exchange (not with `papers status`)
        if own_id:
            if former is not None:
                self.renamed(former, own_id, path)
            if self.located is not None:
                self.located(own_id, path)
            return own_id
        if former is not None:
            return former
        own = self.path()
        if own is not None and realpath(own) == realpath(path):
            return self.config.pool_label()  # as the pool setting writes it
        rel = os.path.relpath(path, self.libdir)
        return rel if rel.startswith('.') else os.path.join('.', rel)

    def _shown(self, path):
        """how the messages name the pool in `path` when the command line
        does not give it: the pool of the library as its pool setting
        writes it, else with ~ for the home directory"""
        own = self.path()
        if own is not None and realpath(own) == realpath(path):
            return self.config.pool_label()
        return short_home(path)

    def resolve(self, path, shown=None):
        """the Pool of the library in directory `path`, which must be a
        library (see not_a_library). The messages name it `shown` (the
        path as given on the command line), by default as _shown says."""
        path = os.path.abspath(path)
        key = realpath(path)
        if key in self._cache:
            pool_ = self._cache[key]
            if shown:
                pool_.shown = shown
            return pool_
        shown = shown or self._shown(path)
        if self._is_self(path):
            raise PoolError(f'pool {shown}: this is the library itself')
        configfile = library_config_file(path)
        if configfile is None:
            if os.path.exists(path) and not os.path.isdir(path):
                raise PoolError(f'pool {shown}: not a directory')
            raise PoolError(not_a_library('pool', path))
        config = Config.load(configfile, machine=self.config.machine)
        if lock.held():  # a command that writes its library: the pool too, before it reads it
            lock.acquire(config)
        pool_ = Pool(self._id(path), path, config, shown)
        self._cache[key] = pool_
        return pool_

    def path(self):
        "the path of the pool of the library, or None (pool none, or the library is its own pool)"
        path = self.config.pool_path()
        return None if path is None or self._is_self(path) else path

    def pool(self, quiet=False):
        """the pool of the library, or None (pool none, or the library is its
        own pool). A pool that cannot be read is a warning (none with
        quiet), and None."""
        path = self.path()
        if path is None:
            return None
        try:
            return self.resolve(path)
        except PoolError as error:
            if not quiet:
                logger.warning(str(error))
            return None

    def target(self):
        """the pool that pull, push and the shallow libraries exchange with:
        an error if it is not a library, or if it has a pool itself (as
        --pool PATH)"""
        path = self.path()
        if path is None:
            raise PoolError(NO_POOL_MESSAGE)
        pool_ = self.resolve(path)
        check_poolless(pool_)  # it may have taken a pool since the pool setting was made
        return pool_

    def get(self, path):
        """a library given on the command line (--pool PATH): a path relative
        to the current directory, of a library without pool"""
        pool_ = self.get_library(path)
        check_poolless(pool_)
        return pool_

    def get_library(self, path):
        """a library given on the command line (--pool PATH), which may have
        a pool itself (`papers file fix --pool PATH` only takes its files)"""
        # named as given; an absolute path with ~ (the shell expands ~/...)
        shown = path if not os.path.isabs(os.path.expanduser(path)) else short_home(os.path.expanduser(path))
        return self.resolve(os.path.abspath(os.path.expanduser(path)), shown=shown)

    def loaded(self):
        "the pools resolved so far"
        return list(self._cache.values())

    def files_dirs(self):
        "the files directory of the pool, if it exists, as a list"
        pool = self.pool(quiet=True)
        return [pool.filesdir] if pool is not None and pool.filesdir else []


# ORIGIN COPIES
# =============

ORIGIN_DIR = os.path.join('.papers', 'origin')
LEGACY_ORIGIN_FILE = os.path.join('.papers', 'origin.bib')  # one file for all pools, in earlier v3 builds
POOL_FIELD = 'papers-pool'  # in the legacy file only
POOL_KEY_FIELD = 'papers-pool-key'
TIME_FIELD = 'papers-time'
# the file links of a record (a shallow library: those of the pool entry
# after the last exchange, as the library writes its links, see
# Exchange.pool_removed); `papers-files` held them in development builds
# of v3, and is ignored
FILE_FIELD = 'file'
_DEV_FILES_FIELD = 'papers-files'
_ORIGIN_FIELDS = (POOL_FIELD, POOL_KEY_FIELD, TIME_FIELD, _DEV_FILES_FIELD)
_RECORD_EXTRA = _ORIGIN_FIELDS + (FILE_FIELD,)  # not part of the base entry
# the first comments of a file: @comment{papers-pool <pool id>} and
# @comment{papers-pulled <pool bibtex mtime in ns>}
_POOL_COMMENT = 'papers-pool'
_PULLED_COMMENT = 'papers-pulled'
_PATH_COMMENT = 'papers-pool-path'  # where the pool was at the last exchange (for the reader, and the file name)
_LEGACY_PULL_COMMENT = 'papers-pull'  # <mtime> <pool id>, in the legacy file


def _library_id(path):
    "the identifier of the library in directory `path` (the `id` of its configuration), or None"
    try:
        file = library_config_file(path)
        id = json.load(open(file, encoding='utf-8-sig')).get('id') if file else None
    except (OSError, ValueError, AttributeError, PapersExit):
        return None
    return id if isinstance(id, str) and re.fullmatch(r'[0-9a-f]{32}', id) else None


def _is_path_id(id):
    "a pool id of an earlier version: the pool's path, not a library identifier"
    return not re.fullmatch(r'[0-9a-f]{32}', id)


def origin_file_name(pool, path=None):
    """the origin file of a pool: the name of the pool folder (path: where
    the pool is, for a pool id that is a library identifier) and the start
    of the sha1 of the pool id (two pools in folders of the same name get
    different files)"""
    folder = path if path is not None else (pool if _is_path_id(pool) else '')
    name = slugify(os.path.basename(os.path.normpath(folder))) if folder else ''
    return f'{name or "pool"}-{hashlib.sha1(pool.encode()).hexdigest()[:6]}.bib'


class Record:
    """the origin record of a library entry for a pool: `entry` is the base
    version (see the module documentation; under the library key, without
    the papers-* fields and file links). `files`: the `file` field of the
    record, in a shallow library the file links of the pool entry after
    the last exchange (as written in the library's bibtex), or None if not
    recorded."""

    def __init__(self, key, pool, pool_key, time, entry, files=None):
        self.key = key
        self.pool = pool
        self.pool_key = pool_key
        self.time = time
        self.entry = entry
        self.files = files

    def __repr__(self):
        return f'Record({self.key!r}, {self.pool!r}, {self.pool_key!r})'


def _now():
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec='seconds')


def _strip(e, names):
    e = entry_copy(e)
    for name in names:
        if name in e.fields_dict:
            del e[name]
    return e


class Origin:
    """`.papers/origin/` of a library: one file per pool (see
    origin_file_name), with the pool id and the time of the last exchange
    in its first comments, and the records of the entries exchanged with
    the pool (see the module documentation). An entry can have records in
    several files, from earlier pools of the library."""

    def __init__(self, dir=None):
        self.dir = dir
        self.entries = {}  # pool id -> {lower-case library key -> entry with the papers-* fields}
        self.pulls = {}    # pool id -> mtime (ns) of the pool bibtex at the last exchange
        self.changed = set()  # the pools whose file is to be written
        self.known = set()  # the pools that have records when loaded
        self.paths = {}  # pool id -> where the pool was (see _PATH_COMMENT)
        self.read_from = {}  # pool id -> the file its records were read from
        self.stale = set()  # files to remove at the save (the records of a pool that moved to another id)

    @classmethod
    def for_library(cls, libdir):
        "the records of the library in the folder `libdir` (see papers.config.library_dir)"
        return cls.load(os.path.join(libdir, ORIGIN_DIR))

    @classmethod
    def load(cls, dir):
        origin = cls(dir)
        names = sorted(os.listdir(dir)) if os.path.isdir(dir) else []
        for name in names:
            if name.endswith('.bib'):
                origin._read(os.path.join(dir, name))
        legacy = os.path.join(os.path.dirname(dir), os.path.basename(LEGACY_ORIGIN_FILE))
        if os.path.exists(legacy):
            origin._migrate(legacy)
        origin.known = {pool for pool, records in origin.entries.items() if records}
        return origin

    @staticmethod
    def _parse(path):
        try:
            return parse_string(open(path, encoding='utf-8-sig').read())
        except Exception as error:
            logger.warning(f'{path}: could not be read ({error}); ignored')
            return None

    def _read(self, path):
        lib = self._parse(path)
        if lib is None:
            return
        words = [block.comment.strip().split(None, 1) for block in lib.comments]
        pool = next((w[1].strip() for w in words if len(w) == 2 and w[0] == _POOL_COMMENT), None)
        if pool is None:
            logger.warning(f'{path}: no `{_POOL_COMMENT}` comment naming the pool; ignored')
            return
        pulled = next((w[1].strip() for w in words if len(w) == 2 and w[0] == _PULLED_COMMENT), '')
        if pulled.isdigit():
            self.pulls[pool] = int(pulled)
        where = next((w[1].strip() for w in words if len(w) == 2 and w[0] == _PATH_COMMENT), None)
        if where:
            self.paths[pool] = where
        self.read_from[pool] = path
        records = self.entries.setdefault(pool, {})
        for e in lib.entries:
            records[e.key.lower()] = e

    def _migrate(self, legacy):
        """split the single origin file of earlier v3 builds into one file
        per pool, and remove it"""
        lib = self._parse(legacy)
        if lib is None:
            return
        for block in lib.comments:
            words = block.comment.strip().split(None, 2)
            if len(words) == 3 and words[0] == _LEGACY_PULL_COMMENT and words[1].isdigit():
                self.pulls.setdefault(words[2], int(words[1]))
        for e in lib.entries:
            pool = get_entry_val(e, POOL_FIELD, '')
            self.entries.setdefault(pool, {}).setdefault(e.key.lower(), _strip(e, (POOL_FIELD,)))
        self.changed.update(self.entries, self.pulls)
        if papers.config.DRYRUN:
            return
        self.save()
        os.remove(legacy)
        logger.info(f'{legacy}: split into one file per pool in {self.dir}')

    def __len__(self):
        return sum(len(records) for records in self.entries.values())

    def _record(self, pool, e):
        return Record(e.key, pool, get_entry_val(e, POOL_KEY_FIELD, ''), get_entry_val(e, TIME_FIELD, ''),
                      _strip(e, _RECORD_EXTRA), files=get_entry_val(e, FILE_FIELD, None))

    def get(self, entry, pool=None):
        """the record of a library entry (by key, or by a former key of its
        ids field) for `pool` (default: any pool), or None"""
        keys = [get_entry_val(entry, 'ID', '')] + [k.strip() for k in get_entry_val(entry, 'ids', '').split(',')]
        for id, records in self.entries.items():
            if pool is not None and id != pool:
                continue
            for key in keys:
                if key and key.lower() in records:
                    return self._record(id, records[key.lower()])
        return None

    def records(self, pool=None):
        return [self._record(id, e) for id, records in self.entries.items() if pool is None or id == pool
                for e in records.values()]

    def set(self, key, pool, pool_entry, files=None):
        """record the base version of an entry for a pool, with the key of
        the pool entry (the record does not change if it is the same as
        before, its time included), and `files`, the file links of the pool
        entry, in the `file` field of the record (see Record; None: no
        `file` field)"""
        new = _strip(pool_entry, _RECORD_EXTRA)
        records = self.entries.setdefault(pool, {})
        old = records.get(key.lower())
        if old is not None and get_entry_val(old, POOL_KEY_FIELD, '') == pool_entry.key \
                and _same_fields(_strip(old, _RECORD_EXTRA), new):
            self.set_files(key, pool, files)
            return
        set_entry_key(new, key)
        if files is not None:
            new.fields.append(Field(FILE_FIELD, files))
        new.fields += [Field(POOL_KEY_FIELD, pool_entry.key), Field(TIME_FIELD, _now())]
        records[key.lower()] = new
        self.changed.add(pool)

    def set_files(self, key, pool, files):
        """set the file links of the pool entry in the record of an entry,
        if it has one (files None: remove them)"""
        old = self.entries.get(pool, {}).get(key.lower())
        if old is None or (get_entry_val(old, FILE_FIELD, None) == files
                           and _DEV_FILES_FIELD not in old.fields_dict):
            return
        for name in (FILE_FIELD, _DEV_FILES_FIELD):
            if name in old.fields_dict:
                del old[name]
        if files is not None:
            old.fields.append(Field(FILE_FIELD, files))
        self.changed.add(pool)

    def remove(self, key, pool):
        if self.entries.get(pool, {}).pop(key.lower(), None) is not None:
            self.changed.add(pool)

    def rekey(self, old, new):
        "the records of a library entry whose key changed from `old` to `new`, in every pool"
        for pool, records in self.entries.items():
            record = records.pop(old.lower(), None)
            if record is not None:
                set_entry_key(record, new)
                records[new.lower()] = record
                self.changed.add(pool)

    def file_of(self, pool):
        "the origin file of the pool id `pool` (see origin_file_name), or None without origin folder"
        if self.dir is None:
            return None
        if pool in self.read_from:
            return self.read_from[pool]
        where = self.paths.get(pool)
        return os.path.join(self.dir, origin_file_name(pool, os.path.expanduser(where) if where else None))

    def locate(self, pool, path):
        """where the pool `pool` (a library identifier) is: its origin file
        is named after that folder, and says it (see _PATH_COMMENT)"""
        where = short_home(path)
        if self.paths.get(pool) != where:
            self.paths[pool] = where
            if pool in self.entries or pool in self.pulls:
                self.changed.add(pool)  # written again, under the name of the folder

    def rename_pool(self, old, new, path=None):
        """the records of the pool `old` move to the id `new` (the pool's
        library identifier, see Pools._id); path: where the pool is"""
        if old not in self.entries and old not in self.pulls:
            return
        records = self.entries.pop(old, {})
        self.entries.setdefault(new, {}).update({k: e for k, e in records.items() if k not in self.entries[new]})
        if old in self.pulls:
            self.pulls.setdefault(new, self.pulls.pop(old))
        if old in self.known:
            self.known.add(new)
        if path is not None:
            self.paths[new] = short_home(path)
        if old in self.read_from:
            self.stale.add(self.read_from.pop(old))
        self.changed.discard(old)
        self.changed.add(new)
        logger.info(f'origin records of {old}: now under the identifier of the pool library, {new}')

    def pulled(self, pool):
        "mtime (ns) of the pool's bibtex at the last exchange (see set_pulled), or None"
        return self.pulls.get(pool)

    def first_exchange(self, pool):
        "no exchange with the pool before this command: no exchange time, and no record when loaded"
        return self.pulled(pool) is None and pool not in self.known

    def set_pulled(self, pool, mtime_ns):
        if mtime_ns is not None and self.pulls.get(pool) != mtime_ns:
            self.pulls[pool] = mtime_ns
            self.changed.add(pool)

    def save(self):
        if not self.changed or self.dir is None:
            return
        if papers.config.DRYRUN:
            print(f'DRYRUN: {self.dir} not saved')
            return
        os.makedirs(self.dir, exist_ok=True)
        written = set()
        for pool in sorted(self.changed):
            lib = Library()
            lib.add(ExplicitComment(f'{_POOL_COMMENT} {pool}'))
            if pool in self.pulls:
                lib.add(ExplicitComment(f'{_PULLED_COMMENT} {self.pulls[pool]}'))
            if pool in self.paths:
                lib.add(ExplicitComment(f'{_PATH_COMMENT} {self.paths[pool]}'))
            records = self.entries.get(pool, {})
            for key in sorted(records):
                lib.add(entry_copy(records[key]))
            where = self.paths.get(pool)
            path = os.path.join(self.dir, origin_file_name(pool, os.path.expanduser(where) if where else None))
            text = format_library(lib)
            if read_text(path) != text:  # a file that has this content already is not written
                write_atomic(path, text)
            written.add(os.path.realpath(path))
            if pool in self.read_from and os.path.realpath(self.read_from[pool]) != os.path.realpath(path):
                self.stale.add(self.read_from[pool])  # the file of an earlier name
            self.read_from[pool] = path
        for path in self.stale:
            if os.path.realpath(path) not in written and os.path.isfile(path):
                os.remove(path)
        self.changed, self.stale = set(), set()


def _same_fields(a, b):
    "same entry type and fields (values compared as written)"
    fields = lambda e: (e.entry_type.lower(), sorted((f.key, f.value) for f in e.fields))
    return fields(a) == fields(b)


# EXCHANGES BETWEEN A LIBRARY AND ITS POOL
# ========================================

class Exchange:
    """a library (configuration and bibliography) with its pools and origin
    records: the pool of the library, and the libraries given with `--pool
    PATH`. The origin records are used and written for every pool; the
    file links of a shallow library are those of the pool entries for its
    own pool only. The command saves: the origin first (`origin.save()`),
    then the library and the pools that changed (`changed_pools`)."""

    def __init__(self, config, biblio, pools=None, origin=None):
        self.config = config
        self.biblio = biblio
        self.pools = pools or Pools(config)
        self.origin = origin if origin is not None else Origin.for_library(config.libdir)
        self.pools.renamed = self.origin.rename_pool
        self.pools.located = self.origin.locate
        self.pools.set_known_ids(set(self.origin.entries) | set(self.origin.pulls))
        self.same = {}  # file deleted -> its identical copy that stays (see relink, delete_files)
        self.changed_pools = []  # the pools to save
        self.pushed_pools = []   # the pools pushed to (changed or not): after_push after the save
        self._after = {}  # pool id -> state of the push for after_push
        self._removed_links = {}  # (id of a library entry, pool id) -> its links the pool removed (see outgoing)
        path = self.pools.path()
        self.pool_id = self.pools._id(path) if path is not None else None

    def _changed(self, pool):
        if not any(p is pool for p in self.changed_pools):
            self.changed_pools.append(pool)

    def is_own(self, pool):
        "whether `pool` is the pool of the library (rather than a library given with --pool PATH)"
        return pool is not None and pool.id == self.pool_id

    # finding the pool entry of a library entry

    def pool_entry(self, e, pool):
        """(pool entry, origin record) of a library entry in `pool`: with an
        origin record, the pool entry of its pool key if it is the same paper
        as the origin copy or as the entry, else the same paper as the origin
        copy, then as the entry (see Pool.find), else the pool entry of the
        pool key if its identifiers do not contradict the origin copy (see
        Pool.by_key); without record, the same paper as the entry (record
        None). (None, record) if the pool does not have it."""
        record = self.origin.get(e, pool.id)
        d = self.biblio.distinct
        if record is not None:
            pe = pool.entry_of_key(record.pool_key)
            if pe is not None:
                union = pool.distinct(d)
                if same_paper(pe, record.entry, union).kind == SAME or same_paper(pe, e, union).kind == SAME:
                    return pe, record
            pe = pool.find(record.entry, d) or pool.find(e, d) or pool.by_key(record.pool_key, record.entry)
        else:
            pe = pool.find(e, d)
        return pe, record

    def merge_distinct(self, pool):
        "union of the pairs that are not the same paper, both ways"
        self.biblio.distinct.update(pool.biblio.distinct)
        pool.biblio.distinct.update(self.biblio.distinct)

    # the file links of a shallow library: those of the pool entry

    def _shares_links(self, pool):
        "a shallow library and its own pool: the library entry's file links are the pool entry's"
        return self.config.shallow and self.is_own(pool)

    def record(self, e, pool, base, pe):
        """record the origin of a library entry (origin.set): `base`, and in
        a shallow library, for its pool, the file links of the pool entry `pe`"""
        files = None
        if self._shares_links(pool):
            pending = self._removed_links.pop((id(e), pool.id), [])
            files = format_file(pool.biblio.get_files(pe) + pending, relative_to=self.biblio.relative_to)
        self.origin.set(e.key, pool.id, base, files=files)

    def new_links(self, e, pool):
        """in a shallow library, the file links that the command added to a
        library entry (not there when the library was loaded): they go to
        the pool entry as they are, wherever they point"""
        if not self._shares_links(pool):
            return []
        before = self.biblio.loaded_files(e)
        if before is None:
            return []
        old = {realpath(f) for f in before}
        return [f for f in self.biblio.get_files(e) if realpath(f) not in old]

    def pool_removed(self, e, pe, record, pool):
        """in a shallow library, the file links of a library entry that the
        pool entry had at the last exchange (origin record) and no longer
        has: real paths. A link that the pool entry never had stays."""
        if not self._shares_links(pool) or record is None or record.files is None:
            return set()
        base = {realpath(f) for f in parse_file(record.files, relative_to=self.biblio.relative_to)}
        now = {realpath(f) for f in pool.biblio.get_files(pe)}
        return {realpath(f) for f in self.biblio.get_files(e)} & (base - now)

    def outgoing(self, e, pool, pe, record):
        """the library entry as push sends it to the pool entry pe: without
        the file links that the pool removed since the last exchange (see
        pool_removed; pull removes them from the library)"""
        out = exchange_copy(e, self.biblio, pool.biblio, key=pe.key)
        removed = self.pool_removed(e, pe, record, pool)
        if removed:
            pool.biblio.set_files(out, [f for f in pool.biblio.get_files(out) if realpath(f) not in removed])
            # still in the record after the push: the next pull removes them from the library
            self._removed_links[(id(e), pool.id)] = [f for f in self.biblio.get_files(e) if realpath(f) in removed]
        return out

    # files

    def files_policy(self, mode=None, keep=(), pools=()):
        """what to do with the files of entries taken from a pool (see
        papers.files.FilesPolicy): in a shallow library, those of its pool
        are linked where they are; otherwise as the files mode says (a pool
        file is copied, never moved). In a shallow library, the files of
        another library go to the files directory of its pool (see
        papers.pools.use_pool_files). pools: the pools that the files come
        from (default: the pool of the library)."""
        if self.config.shallow and (not pools or any(self.is_own(p) for p in pools)):
            mode = 'link'
        mode = mode or self.config.files or 'move'
        if self.biblio.filesdir is None:
            mode = 'link'
        dirs = self.pools.files_dirs() + [p.filesdir for p in pools if p.filesdir]
        return FilesPolicy(mode, self.biblio.filesdir, current_config=self.config.file,
                           machine=self.config.machine, keep=keep, pool_dirs=dirs,
                           in_pool=self.config.shallow)

    def _place_files(self, e, policy):
        if policy.mode == 'link' or self.biblio.filesdir is None:
            return
        self.biblio.rename_entry_files(e, copy=policy)

    # pull
    # ----

    def _library_lookup(self, pool):
        """the lookups of library_entry, for the library as it is now:
        {lower-case pool key: lower-case library keys of the origin records
        of `pool` with that pool key, in the order of the records},
        {lower-case key: first library entry of that key}, and an
        IdentityIndex of the library"""
        by_pool_key = {}
        for key, record in self.origin.entries.get(pool.id, {}).items():
            by_pool_key.setdefault(get_entry_val(record, POOL_KEY_FIELD, '').lower(), []).append(key)
        keys = {}
        for x in self.biblio.entries:
            keys.setdefault(self.biblio.key(x), x)
        return by_pool_key, keys, IdentityIndex(self.biblio.entries)

    def library_entry(self, pe, pool, lookup=None):
        """the library entry of a pool entry: the entry whose origin record
        has its pool key, else the same paper; or None. lookup: the
        _library_lookup of the library, unchanged since"""
        by_pool_key, keys, index = lookup or self._library_lookup(pool)
        for key in by_pool_key.get(pe.key.lower(), []):
            e = keys.get(key)
            if e is not None:
                return e
        found = find_duplicates(pe, None, distinct_union(self.biblio.distinct, pool.biblio.distinct), index=index)
        return next((e for e, verdict in found if verdict.kind == SAME), None)

    def missing(self, pool):
        "the entries of the pool that are not in the library (no library entry, see library_entry)"
        lookup = self._library_lookup(pool)
        return [pe for pe in pool.biblio.entries if self.library_entry(pe, pool, lookup) is None]

    def sharing(self, entries, pool):
        """(shared, removed) among `entries`: the entries shared with `pool`,
        those whose paper the pool has (see pool_entry: by origin record,
        else by the same-paper rule), and the entries that the pool no
        longer has although they have an origin record of it (removed from
        the pool since the last exchange)"""
        shared, removed = [], []
        for e in entries:
            pe, record = self.pool_entry(e, pool)
            if pe is not None:
                shared.append(e)
            elif record is not None:
                removed.append(e)
        return shared, removed

    def shared(self, entries, pool):
        "the entries shared with `pool` (see sharing)"
        return self.sharing(entries, pool)[0]

    def forget(self, entries, pool):
        """drop the origin records of `pool` of entries that it no longer
        has (see sharing): they are no longer shared with it"""
        for e in entries:
            record = self.origin.get(e, pool.id)
            if record is not None:
                self.origin.remove(record.key, pool.id)

    def pull(self, entries, pool, resolver, mode=None, record_pull=True, new=(), named=()):
        """three-way merge of the entries of `pool` into the library entries
        (see papers.merge), and the pool entries `new` added to the library.
        An entry that the pool does not have is reported (`not found`) only
        if it is one of `named` (the entries named on the command line).
        pool None: nothing to merge. Return the outcome of each entry: list of (entry, pool, what)
        where what is 'updated', 'linked', 'unchanged', 'skipped', 'not
        found' or 'added'."""
        report = []
        if pool is not None:
            self.merge_distinct(pool)
            before = pool.bibtex_mtime()
        for e in entries:
            if resolver.quit:
                break
            pe, record = self.pool_entry(e, pool) if pool is not None else (None, None)
            if pe is None:
                if any(e is x for x in named):
                    report.append((e, None, 'not found'))
                continue
            report.append((e, pool, self._pull_one(e, pool, pe, record, resolver, mode)))
        for pe in new:
            report.append((self._pull_new(pe, pool, mode), pool, 'added'))
        # a pull that skipped (or quit) leaves pool changes to take: not a pull of the pool
        if record_pull and pool is not None and not resolver.quit \
                and not any(what == 'skipped' for _, _, what in report):
            self.origin.set_pulled(pool.id, before)
        return report

    def _pull_one(self, e, pool, pe, record, resolver, mode):
        if self._shares_links(pool):
            self.repair_links([e], pool=pool)
        incoming = exchange_copy(pe, pool.biblio, self.biblio)
        merge = Merge([e, incoming], relative_to=self.biblio.relative_to, exchange=True,
                      base=record.entry if record is not None else None)
        removed = self.pool_removed(e, pe, record, pool)
        if not merge.conflicts and not merge.additions and not merge.new_files and not removed:
            self.record(e, pool, pe, pe)
            return 'unchanged' if record is not None else 'linked'
        if merge.conflicts:
            decision = resolver.decide(merge, 'pull', Verdict(SAME, pool.label))
            if decision.kind != 'merge':
                return 'skipped'
            new = decision.entry
        else:
            new = merge.result()
        old_files = self.biblio.get_files(e)
        apply_entry(e, new)
        if removed:  # the pool entry no longer links to them
            self.biblio.set_files(e, [f for f in self.biblio.get_files(e) if realpath(f) not in removed])
        self._place_files(e, self.files_policy(mode, keep=old_files, pools=[pool]))
        self.record(e, pool, pe, pe)
        return 'updated'

    def _pull_new(self, pe, pool, mode):
        """add a pool entry to the library, under the pool key (with a letter
        suffix if the library has this key already); its files are linked
        in a shallow library (its own pool), else placed as the files mode says"""
        keys = {self.biblio.key(x) for x in self.biblio.entries}
        key = pe.key if pe.key.lower() not in keys else append_abc(pe.key, keys)
        e = exchange_copy(pe, pool.biblio, self.biblio, key=key)
        self.biblio.db.add(e)
        self._place_files(e, self.files_policy(mode, pools=[pool]))
        self.record(e, pool, pe, pe)
        return e

    def check(self, entries, pool, all_entries=True, options=''):
        """the report of `pull --check` with `pool`: a line on the pool if it
        changed since the last pull, on the entries whose pool version
        changed since it was taken, and on those removed from the pool (see
        removed_note; options: of the command, to repeat in it). No merge,
        nothing written."""
        lines = [f'{pool.label}: {pool_state(self.origin, pool)}'] if all_entries else []
        for e in entries:
            pe, record = self.pool_entry(e, pool)
            if pe is None:
                if record is not None:
                    lines.append(removed_note(e, pool, options))
                continue
            incoming = exchange_copy(pe, pool.biblio, self.biblio)
            if record is None:
                merge = Merge([e, incoming], relative_to=self.biblio.relative_to, exchange=True)
                if not merge.is_exact() or merge.new_files:
                    lines.append(f'{e.key}: in {pool.label} as {pe.key}, not pulled yet')
                continue
            merge = Merge([e, incoming], relative_to=self.biblio.relative_to, base=record.entry)
            changed = [f.name for f in merge.additions + merge.conflicts]
            if merge.new_files or self.pool_removed(e, pe, record, pool):
                changed.append('file')
            if changed:
                n = len(merge.conflicts)
                note = f' ({n} conflict{"s" if n > 1 else ""})' if n else ''
                lines.append(f'{e.key}: changed in {pool.label}: {", ".join(sorted(changed))}{note}')
        return lines

    # push
    # ----

    def push(self, entries, pool, resolver, include_new=True):
        """three-way merge of the library entries into the pool entries;
        entries new to the pool are added to it, with a key from the pool's
        key template. Return [(entry, pool, what)], what being 'added', 'updated', 'linked',
        'unchanged', 'skipped' or 'empty' (an entry without fields or key,
        not pushed)."""
        check_readable(pool)
        self.merge_distinct(pool)
        if pool.id not in self._after:
            before = pool.bibtex_mtime()
            # [the pool had not changed since the last exchange, a pushed entry left it ahead of the library]
            self._after[pool.id] = [before is None or self.origin.pulled(pool.id) == before, False]
        report = []
        for e in entries:
            if resolver.quit:
                break
            pe, record = self.pool_entry(e, pool)
            if pe is None:
                if include_new:
                    report.append((e, pool, self._push_new(e, pool)))
                continue
            report.append((e, pool, self._push_one(e, pool, pe, record, resolver)))
        if not any(p is pool for p in self.pushed_pools):
            self.pushed_pools.append(pool)
        if any(what in ('added', 'updated') for _, _, what in report):  # the pool entries changed
            self._changed(pool)
        return report

    def after_push(self, pool):
        """after the pool was saved (a pool that the push did not change is
        not written, see `push`): if it had not changed since the last
        exchange (or this is the first), the push does not count as a
        change of the pool, unless a pushed entry left the pool with
        something that the library does not have (a pull would bring it)"""
        state = self._after.get(pool.id)
        if state is None or state[1]:  # not pushed to, or left ahead of the library
            return
        if state[0] or self.origin.first_exchange(pool.id):
            self.origin.set_pulled(pool.id, pool.bibtex_mtime())

    def after_take(self, pool):
        """after `add` took entries from the pool (not saved): the first
        exchange with the pool records its modification time, as a pull"""
        if self.origin.first_exchange(pool.id) and self.origin.records(pool.id):
            self.origin.set_pulled(pool.id, pool.bibtex_mtime())

    def _pool_policy(self, pool, keep=()):
        "files pushed to a pool: copied (a hard link when possible), with the pool's name template"
        return FilesPolicy('copy', pool.filesdir, current_config=pool.config.file,
                           machine=self.config.machine, keep=keep, in_pool=True)

    def _push_new(self, e, pool):
        out = exchange_copy(e, self.biblio, pool.biblio)
        # in a shallow library, the links added by the command are linked where they are
        policy = self._pool_policy(pool, keep=self.new_links(e, pool))
        # an entry without fields, or without a key, is not written to the pool
        if not any(k not in ('file', 'ids') for k in out.fields_dict):
            logger.info(f'{e.key or "an entry without key"}: not pushed to {pool.label}: the entry has no fields')
            return 'empty'
        update_key = bool(pool.biblio.keyformat(out))
        if not update_key:  # the key template gives no key: the library key
            if not e.key:
                logger.info(f'an entry without key: not pushed to {pool.label}')
                return 'empty'
            if pool.biblio.key(out) in {pool.biblio.key(x) for x in pool.biblio.entries}:
                set_entry_key(out, pool.biblio.append_abc_to_key(out))
        new = pool.biblio.insert_entry(out, update_key=update_key, rename=pool.filesdir is not None, copy=policy)[0]
        pool.add_entry(new)
        self.record(e, pool, new, new)
        return 'added'

    def _push_one(self, e, pool, pe, record, resolver):
        outgoing = self.outgoing(e, pool, pe, record)
        merge = Merge([pe, outgoing], relative_to=pool.biblio.relative_to, exchange=True,
                      base=_rekey(record.entry, pe.key) if record is not None else None)
        if not merge.conflicts and not merge.additions and not merge.new_files:
            self._pushed(e, pool, pe, outgoing)
            return 'unchanged' if record is not None else 'linked'
        if merge.conflicts:
            decision = resolver.decide(merge, 'push', Verdict(SAME, pool.label))
            if decision.kind != 'merge':
                return 'skipped'
            new = decision.entry
        else:
            new = merge.result()
        old_files = pool.biblio.get_files(pe)
        pool.update_entry(pe, new)
        if pool.filesdir is not None:
            # in a shallow library, the links added by the command are linked where they are
            keep = old_files + self.new_links(e, pool)
            pool.biblio.rename_entry_files(pe, copy=self._pool_policy(pool, keep=keep))
        self._pushed(e, pool, pe, outgoing)
        return 'updated'

    def _pushed(self, e, pool, pe, outgoing):
        """record the origin of a pushed entry: the library's version, as
        sent (see the module documentation), so that what the pool entry
        has beyond it comes with the next pull"""
        self.record(e, pool, outgoing, pe)
        incoming = exchange_copy(pe, pool.biblio, self.biblio)
        after = Merge([e, incoming], relative_to=self.biblio.relative_to, base=outgoing)
        if after.additions or after.conflicts or after.new_files:
            self._after[pool.id][1] = True

    def push_links(self, entries, pool, resolver):
        """a shallow library: the pool entries of `entries` (whose file
        links changed in the command) link to the files that the command
        linked the library entries to, wherever they are, and to those
        that the library entries link to in the pool's files directory; and
        no longer to the files that the library entries no longer link to.
        Only the file links of the pool entry change (and in its origin
        record), and no file is deleted. A link that the library entry had
        when loaded, outside the pool's files directory, is not sent (`push`
        sends it, as the other fields). An entry that the pool does not
        have, with links to send, is pushed (added to the pool, as `add`
        does). Return [(entry, pool, what)], what being 'links' (the pool
        entry's links changed), or as Exchange.push says for the entries
        pushed."""
        if entries:
            check_readable(pool)
        report = []
        missing = []
        for e in entries:
            before = self.biblio.loaded_files(e) or []
            after = self.biblio.get_files(e)
            removed = {realpath(f) for f in before} - {realpath(f) for f in after}
            new = {realpath(f) for f in self.new_links(e, pool)}
            added = [f for f in after if realpath(f) in new or (pool.filesdir and is_inside(f, pool.filesdir))]
            pe, record = self.pool_entry(e, pool)
            if pe is None:
                if added:
                    missing.append(e)
                continue
            old = pool.biblio.get_files(pe)
            files = [f for f in old if realpath(f) not in removed]
            linked = {realpath(f) for f in files}
            files += [f for f in added if realpath(f) not in linked]
            if files == old:
                continue
            if pool.id not in self._after:
                before_mtime = pool.bibtex_mtime()
                if before_mtime is not None and self.origin.pulled(pool.id) == before_mtime:
                    # the pool had not changed since the last exchange: it has not now either
                    self._after[pool.id] = [True, False]
            pool.biblio.set_files(pe, files)
            pool._sizes = None
            self._changed(pool)
            if record is not None and self._shares_links(pool):
                self.origin.set_files(e.key, pool.id, format_file(files, relative_to=self.biblio.relative_to))
            report.append((e, pool, 'links'))
        if missing:
            report += self.push(missing, pool, resolver)
        return report

    # links to pool files
    # -------------------

    def pool_relinks(self, e, pool, broken):
        """the pool files for the broken links `broken` of a library entry:
        {link: [pool files]}, taken from the pool entry of the same paper
        (see pool_entry), among its files that exist and that the entry does
        not link to already:

        - the pool file of the same file name as the link;
        - otherwise, the pool file named `<name>--<link name>` (the pool
          renamed the file as an attachment, labelled with its former name),
          if only one is;
        - then, if one broken link and one pool file are left, that file;
        - otherwise, the first link into the files directory of the pool
          (the pool renamed its files) gets the pool entry's files left,
          and the other links into it are dropped ([]).

        A link without a pool file is not in the result."""
        if not broken:
            return {}
        pe, _ = self.pool_entry(e, pool)
        if pe is None:
            return {}
        linked = {realpath(f) for f in self.biblio.get_files(e) if os.path.exists(f)}
        left = [f for f in pool.biblio.get_files(pe) if os.path.exists(f) and realpath(f) not in linked]
        found = {}
        for link in broken:
            same = next((f for f in left if os.path.basename(f) == os.path.basename(link)), None)
            if same is not None:
                found[link] = [same]
                left.remove(same)
        for link in [link for link in broken if link not in found]:
            label = ATTACHMENT_SEP + os.path.basename(link)
            labelled = [f for f in left if os.path.basename(f).endswith(label)]
            if len(labelled) == 1:
                found[link] = labelled
                left.remove(labelled[0])
        rest = [link for link in broken if link not in found]
        if not rest or not left:
            return found
        if len(rest) == 1 and len(left) == 1:
            found[rest[0]] = left
        elif pool.filesdir:
            inside = [link for link in rest if is_inside(link, pool.filesdir)]
            if inside:
                found[inside[0]] = left
                found.update((link, []) for link in inside[1:])
        return found

    def repair_links(self, entries=None, pool=None):
        """replace the broken links to the files of a pool (default: the pool
        of the library; the pool renamed or moved them) by the files of the
        pool entry (see pool_relinks), linked where they are. Return
        [(entry, {old link: [new links]})] of the entries repaired."""
        pool = pool if pool is not None else self.pools.pool(quiet=True)
        if pool is None or not pool.filesdir:
            return []
        repaired = []
        for e in (self.biblio.entries if entries is None else entries):
            files = self.biblio.get_files(e)
            broken = [f for f in files if not os.path.exists(f) and is_inside(f, pool.filesdir)]
            found = self.pool_relinks(e, pool, broken)
            if not found:
                continue
            self.biblio.set_files(e, [g for f in files for g in found.get(f, [f])])
            repaired.append((e, found))
        return repaired

    # conversions of the files (papers config pool)
    # ---------------------------------------------

    def plan_own_files(self, dirs=None):
        """the pool files that the library links to (dirs: the files
        directories of the pool, by default the library's pool), to copy into
        its files directory: [(entry, files)]"""
        self.repair_links()
        dirs = self.pools.files_dirs() if dirs is None else [d for d in dirs if d]
        plan = []
        for e in self.biblio.entries:
            files = [f for f in self.biblio.get_files(e) if os.path.exists(f) and any(is_inside(f, d) for d in dirs)]
            if files:
                plan.append((e, files))
        return plan

    def own_files(self, plan, dirs):
        """copy (a hard link when possible) the files of plan_own_files into
        the files directory, with the library's name template, and relink
        them; the pool keeps its files"""
        if self.biblio.filesdir is None:
            raise PapersExit('the library has no files directory: set it with `papers config filesdir DIR` first')
        for e, files in plan:
            keep = [f for f in self.biblio.get_files(e) if f not in files]
            policy = FilesPolicy('copy', self.biblio.filesdir, current_config=self.config.file,
                                 machine=self.config.machine, keep=keep, pool_dirs=dirs)
            self.biblio.rename_entry_files(e, copy=policy)

    def plan_relink(self, pool):
        """what linking the library to the files of `pool` does (`papers
        config pool PATH`): (plan, missing). Each file that a library entry links
        to (existing files) must be linked by the pool entry of the same
        paper: the same file, or a file of the same content. plan:
        [(entry, [(file, pool file)])], the links to replace by the pool's
        copy; missing: the entries with a file that the pool entry does
        not have (or that the pool does not have)."""
        plan, missing = [], []
        for e in self.biblio.entries:
            files = [f for f in self.biblio.get_files(e) if os.path.isfile(f)]
            if not files:
                continue
            pe = self.pool_entry(e, pool)[0]
            pool_files = [pf for pf in pool.biblio.get_files(pe) if os.path.isfile(pf)] if pe is not None else []
            same = {realpath(pf) for pf in pool_files}
            hashes = None
            actions = []
            for f in files:
                if realpath(f) in same:
                    continue
                if hashes is None:
                    hashes = {}
                    for pf in pool_files:
                        hashes.setdefault(checksum(pf), pf)
                target = hashes.get(checksum(f))
                if target is None:
                    missing.append(e)
                    break
                actions.append((f, target))
            else:
                if actions:
                    plan.append((e, actions))
        return plan, missing

    def relink(self, plan, pool, keep_dirs=()):
        """apply plan_relink: the library entries link to the pool's copies.
        Return the files to delete once the library is saved: the library's
        own copies (in its files directory) that no entry of the library or
        of the pool links to, outside `keep_dirs` (files directories of
        pools). `same` maps each of them to its pool copy (see delete_files)."""
        delete = []
        filesdir = self.biblio.filesdir
        for e, actions in plan:
            mapping = {realpath(f): target for f, target in actions}
            files, seen = [], set()
            for f in self.biblio.get_files(e):
                f = mapping.get(realpath(f), f)
                if realpath(f) not in seen:
                    seen.add(realpath(f))
                    files.append(f)
            self.biblio.set_files(e, files)
            delete.extend(f for f, _ in actions if filesdir and is_inside(f, filesdir))
            self.same.update((f, target) for f, target in actions)
        linked = {realpath(f) for e in self.biblio.entries for f in self.biblio.get_files(e)}
        linked.update(realpath(f) for e in pool.biblio.entries for f in pool.biblio.get_files(e))
        dirs = [d for d in keep_dirs if d]
        return [f for f in dict.fromkeys(delete) if realpath(f) not in linked
                and not any(is_inside(f, d) for d in dirs)]


def removed_note(e, pool, options=''):
    """the note on a library entry that `pool` no longer has (see
    Exchange.sharing): the exchanges without KEY leave it out. options:
    those of the command (--pool PATH), to repeat in the note."""
    return f'{e.key}: removed from {pool.label} (`papers push{options} {e.key}` adds it back)'


def _rekey(e, key):
    e = entry_copy(e)
    set_entry_key(e, key)
    return e


def report_counts(report):
    """the counts of the outcomes of pull or push (see Exchange.pull, push):
    '1 added, 2 modified', or '' when nothing happened (the entries
    unchanged are not counted)"""
    counts = {}
    for _, _, what in report:
        if what == 'unchanged':
            continue
        # as the lines of the entries say
        what = {'updated': 'modified', 'links': 'with file links updated'}.get(what, what)
        counts[what] = counts.get(what, 0) + 1
    return ', '.join(f'{n} {what}' for what, n in counts.items())


def pool_state(origin, pool):
    """whether a pool changed since the last exchange with it (pull, push
    or add: a modification time check)"""
    pulled = origin.pulled(pool.id)
    current = pool.bibtex_mtime()
    if pulled is None:
        return 'never pulled' if origin.records(pool.id) else 'not pulled from yet'
    if current != pulled:
        return 'changed since last pull or push'
    return 'up to date'


# ADD: LOOK IN THE POOL FIRST
# ===========================

class PoolLookup:
    """the pool lookup of `add` (Biblio.pool_lookup): an added PDF, DOI or
    bibtex entry that is the same paper as a pool entry is taken from the
    pool, without fetching anything. The entries taken are recorded in the
    origin once inserted (see `inserted`). pool: the library to look in
    (`add --pool PATH`), by default the pool of the library."""

    def __init__(self, exchange, pool=None):
        self.exchange = exchange
        self.pool = pool if pool is not None else exchange.pools.pool()
        self._taken = {}
        self._same = {}  # the files given that have the content of a file of the pool entry
        self.taken_from = {}  # lower-case library key -> the pool of the entry taken

    def __bool__(self):
        return self.pool is not None

    def _take(self, biblio, pool, pe, key, entry=None, files=()):
        """the entry to insert for pool entry pe: the pool's fields and files,
        and the fields only in `entry` (an added bibtex entry), and the
        `files` the pool does not have (same content)"""
        new = exchange_copy(pe, pool.biblio, biblio, key=key)
        if entry is not None:
            merge = Merge([new, entry], relative_to=biblio.relative_to)
            merge.choose_all(0)
            new = merge.result()
        have = biblio.get_files(new)
        hashes = {checksum(f) for f in have if os.path.isfile(f)}
        extra = [f for f in files if not (os.path.isfile(f) and checksum(f) in hashes)]
        if extra:
            biblio.set_files(new, have + extra)
        self._taken[id(new)] = (pool, pe)
        self._same[id(new)] = [f for f in files if f not in extra]
        logger.info(f'found in {pool.label}: {pe.key}')
        return new

    def has_file(self, file):
        return self.pool.find_file(file)[0] is not None

    def pdf(self, biblio, pdf, files=(), doi=None):
        """the entry for an added PDF found in the pool (same file content, or
        a DOI of the PDF that is in the pool, its title in the text), or None"""
        pool = self.pool
        pe, _ = pool.find_file(pdf)
        if pe is not None:
            return self._take(biblio, pool, pe, biblio.keyformat(pe), files=files)
        if doi:
            return self.doi(biblio, doi, files)
        try:
            doi = parse_doi_from_pdf_metadata(pdf)
            if doi:
                return self.doi(biblio, doi, files)
            txt = pdfhead(pdf)
            candidates = parse_dois(txt, pdftail(pdf))
        except Exception as error:
            logger.debug(f'{pdf}: {error}')
            return None
        for candidate in candidates:
            pe = pool.find_doi(candidate)
            if pe is not None and title_in_text(get_entry_val(pe, 'title', ''), txt):
                return self._take(biblio, pool, pe, biblio.keyformat(pe), files=files)
        return None

    def doi(self, biblio, doi, files=()):
        "the entry for an added DOI found in the pool, or None"
        pe = self.pool.find_doi(doi)
        return self._take(biblio, self.pool, pe, biblio.keyformat(pe), files=files) if pe is not None else None

    def key(self, biblio, key, files=()):
        "the entry for `add --key KEY` of the pool entry of key KEY (ignoring case), or None"
        pe = next((x for x in self.pool.biblio.entries if x.key.lower() == key.lower()), None)
        return self._take(biblio, self.pool, pe, pe.key, files=files) if pe is not None else None

    def entry(self, biblio, e):
        "the entry for an added bibtex entry found in the pool (it keeps its key), or None"
        pe = self.pool.find(e, biblio.distinct)
        if pe is None:
            return None
        files = biblio.get_files(e)
        e = _strip(e, ('file',))
        return self._take(biblio, self.pool, pe, e.key, entry=e, files=files)

    def inserted(self, entry, result, biblio=None, rename=False, copy=False):
        """record the origin of the library entries that an entry taken from
        the pool ended in. In `move` mode (rename, and `copy` a FilesPolicy
        that moves the file), a file given that has the same content as a
        file that the entry links to now is removed: it is stored already"""
        pool, pe = self._taken.pop(id(entry), (None, None))
        same = self._same.pop(id(entry), [])
        if pool is None:
            return
        for e in result:
            self.taken_from[e.key.lower()] = pool
            if self.exchange.origin.get(e, pool.id) is None:
                self.exchange.record(e, pool, pe, pe)
        if biblio is not None and rename and callable(copy):
            self._remove_moved(biblio, result, [f for f in same if copy(f) == 'move'])

    def _remove_moved(self, biblio, result, files):
        linked = {realpath(f) for e in biblio.entries for f in biblio.get_files(e)}
        stored = {}
        for e in result:
            for f in biblio.get_files(e):
                if os.path.isfile(f):
                    stored.setdefault(checksum(f), f)
        pool_dir = self.pool.filesdir
        for f in files:
            if not os.path.isfile(f) or realpath(f) in linked or (pool_dir and is_inside(f, pool_dir)):
                continue
            target = stored.get(checksum(f))
            if target is None or os.path.samefile(target, f):
                continue
            if papers.config.DRYRUN:
                print(f'DRYRUN: {f} not removed (the same as {target})')
                continue
            print(f'{f}: removed, the same as {target} (files mode move)')
            journal.record('removed', f, target, digest=checksum(f))
            with journal.paused():  # recorded above: undo copies the identical file back
                journal.remove(f)


def use_pool_files(config, pools):
    """in a shallow library, `add` places the files in the pool, under
    the pool's name template: set them in the configuration of the run"""
    pool = pools.target()
    if pool.filesdir is None:
        raise PoolError(f'{pool.label} has no files directory, and this library is shallow (its files are '
                        'in the pool)')
    if config.source('name.template') == 'library':
        logger.warning('the name template of a shallow library is not used: the files are named '
                       f'with the template of {pool.label}')
    config.filesdir = pool.filesdir
    config.nameformat = pool.config.nameformat
    return pool


# EXPORT
# ======

def export(biblio, config, entries, dest, files='copy', library=True):
    """write the entries (and their files, as `files` says: copy, link or
    none) as a new library in directory `dest`, which must not exist or be
    empty: a self-contained library (pool none, its own files), to be
    handed over. Return (configuration,
    bibliography) of the new library, for the caller to save.

    library=False: `dest` is not made a library (no configuration, no
    bibtex; the caller writes the entries in other formats): the files are
    placed in `dest/files` all the same, named with the name template of
    the library, and the configuration returned is None."""
    if os.path.exists(dest) and (not os.path.isdir(dest) or os.listdir(dest)):
        raise PapersExit(f'{dest}: exists and is not an empty directory')
    if papers.config.DRYRUN:
        raise PapersExit('export does not support --dry-run')
    dest = os.path.abspath(dest)
    if library:
        name = os.path.basename(config.bibtex) if config.bibtex else 'papers.bib'
        new = create_library(dest, config.machine, bibtex=name)
        for setting in papers.config.SETTINGS:
            if setting.startswith(('name.', 'key.')) and config.source(setting) == 'library':
                new.set(setting, config.get(setting))
        new.save()
        if os.path.exists(new.bibtex) and not read_text(new.bibtex).strip():
            # the empty bibtex of the new library: removed, so that the save of
            # the export writes no backup of it (.papers.bib.backup)
            os.remove(new.bibtex)
        target = Biblio(filesdir=new.filesdir, nameformat=new.nameformat, keyformat=new.keyformat,
                        relative_to=os.path.dirname(new.bibtex), distinct=Distinct.for_library(new.libdir))
        current = new.file
    else:
        new, current = None, None
        os.makedirs(dest, exist_ok=True)
        target = Biblio(filesdir=os.path.join(dest, 'files'), nameformat=config.nameformat,
                        keyformat=config.keyformat, relative_to=dest)
    for e in entries:
        c = entry_for(e, biblio, target)
        if files == 'none' and 'file' in c.fields_dict:
            del c['file']
        target.db.add(c)
        if files == 'copy' and target.get_files(c):
            target.rename_entry_files(c, copy=FilesPolicy('copy', target.filesdir, current_config=current,
                                                          machine=config.machine))
    if library:
        target.distinct.update(biblio.distinct)
    return new, target


# STATUS
# ======

def pool_files_dir(config):
    "files directory of the pool of a shallow library, or None (no pool, or not readable)"
    try:
        pool = Pools(config).pool(quiet=True)
    except PoolError:
        return None
    return pool.filesdir if pool is not None else None


def status_line(config):
    """the pool of a library in `papers status`: its path, and how it stands
    with the library (see exchange_state); and the hint for the last line
    of `papers status`, or None"""
    path = config.pool_path()
    if path is None:
        return 'none', None
    pools = Pools(config)
    text = config.pool_label()
    hint = None
    if pools._is_self(path):
        note = 'this library: it has no pool'
    elif not os.path.exists(path):
        note = bcolors.WARNING + 'missing' + bcolors.ENDC
    else:
        try:
            note, hint = exchange_state(config, pools, path)
        except PoolError:
            note = bcolors.WARNING + 'not a library' + bcolors.ENDC
    return f'{text} ({note})', hint


# the hint of `papers status` for each state of a library and its pool
_HINTS = {
    'pool changed': '`papers pull --dry-run` shows the changes, `papers pull` takes them',
    'library changed': '`papers push --dry-run` shows the changes, `papers push` sends them',
    'both changed': '`papers sync --dry-run` shows the changes, `papers sync` exchanges them',
    'not pulled from yet': '`papers pull` takes the entries shared with the pool',
    'never pulled': '`papers pull` takes the changes of the pool',
}


def _fields(e):
    "the fields of an entry that an exchange compares (not the file links, nor the records of papers)"
    return {k.lower(): v.value for k, v in e.fields_dict.items()
            if k.lower() not in ('file', 'ids') and not k.lower().startswith('papers-')}


# the key of each entry of a bibtex text (not @comment, @string, @preamble)
_ENTRY_KEY = re.compile(r'(?m)^@\s*(\w+)\s*[{(]\s*([^,\s]+)\s*,')


def _keys(texts):
    "the lower-case keys of the entries of bibtex texts"
    return {m.group(2).lower() for t in texts for m in _ENTRY_KEY.finditer(t)
            if m.group(1).lower() not in ('comment', 'string', 'preamble')}


class _Pieces:
    """the pieces (see papers.history.pieces) of the library, its pool and
    its origin file for that pool, when status last found them in sync: a
    piece that did not change on any side holds entries still in sync. Kept
    with the history of the library, on the machine (exchanges.json)."""

    def __init__(self, config, pool, origin_path):
        from papers.backup import project_of  # papers.backup imports this module
        project, _ = project_of(config, create=False)
        self.path = os.path.join(project.dir, 'exchanges.json') if project is not None else None
        self.pool = pool
        self.files = {'library': config.bibtex, 'pool': pool.config.bibtex, 'origin': origin_path}
        self.now = {side: history.pieces(read_text(f) if f and os.path.exists(f) else '')
                    for side, f in self.files.items()}
        try:
            self.then = json.load(open(self.path, encoding='utf-8'))[pool.id] if self.path else None
        except (OSError, ValueError, KeyError, TypeError):
            self.then = None

    def changed(self):
        """(keys of the library, keys of the pool) of the entries in pieces
        that changed since, or None (not known: compare everything)"""
        if not isinstance(self.then, dict):
            return None
        if set(self.then.get('pool', ())) - set(self.now['pool']):
            return None  # pieces gone from the pool (an entry removed): their keys are not known
        new = {side: [p for d, p in self.now[side].items() if d not in set(self.then.get(side, ()))]
               for side in self.now}
        return _keys(new['library'] + new['origin']), _keys(new['pool'])

    def save(self, origin_path):
        "after status found the library and the pool in sync"
        if self.path is None or papers.config.DRYRUN:
            return
        self.now['origin'] = history.pieces(read_text(origin_path) if os.path.exists(origin_path) else '')
        try:
            data = json.load(open(self.path, encoding='utf-8'))
        except (OSError, ValueError):
            data = {}
        data[self.pool.id] = {side: sorted(p) for side, p in self.now.items()}
        write_atomic(self.path, json.dumps(data))


def exchange_state(config, pools, path):
    """how a library stands with its pool, for `papers status`: 'in sync',
    'pool changed', 'library changed' or 'both changed' (an entry exchanged
    with the pool differs from its origin copy on that side, as a pull or a
    push would find it), or not exchanged yet; and the hint of the state.
    A pool whose file changed without any difference for the library (e.g.
    the same change on both sides, or entries of other libraries) is in
    sync. Nothing of the library is written (its origin records stay as
    they are): only the pieces found in sync, on the machine (see _Pieces)."""
    origin = Origin.for_library(config.libdir) if config.bibtex else Origin()
    pools.set_known_ids(set(origin.entries) | set(origin.pulls))
    pool = pools.resolve(path)
    first = pool_state(origin, pool)
    if first in ('not pulled from yet', 'never pulled'):
        return first, _HINTS[first]
    if not config.bibtex or not os.path.exists(config.bibtex):
        return 'in sync', None
    moved = origin.pulled(pool.id) != pool.bibtex_mtime()
    origin_path = origin.file_of(pool.id)
    pieces = _Pieces(config, pool, origin_path)
    changed = pieces.changed()
    if changed == (set(), set()):  # no piece changed on any side since status found them in sync
        return 'in sync', None
    biblio = Biblio.load(config.bibtex, config.filesdir)
    exchange = Exchange(config, biblio, pools, origin=origin)
    pool_changed = library_changed = False
    for e in biblio.entries:
        record = origin.get(e, pool.id)
        if record is None:
            continue
        if changed is not None and e.key.lower() not in changed[0] and record.pool_key.lower() not in changed[1]:
            continue  # in pieces that changed on no side since they were in sync
        if not moved and _fields(e) == _fields(record.entry) and e.entry_type.lower() == record.entry.entry_type.lower():
            continue  # neither side changed (the pool file did not change)
        pe, record = exchange.pool_entry(e, pool)
        if pe is None:
            pool_changed = True  # removed from the pool
            continue
        incoming = exchange_copy(pe, pool.biblio, biblio)
        pulled = Merge([e, incoming], relative_to=biblio.relative_to, exchange=True, base=record.entry)
        if pulled.conflicts:
            pool_changed = library_changed = True
        elif pulled.additions or pulled.new_files or exchange.pool_removed(e, pe, record, pool):
            pool_changed = True
        outgoing = exchange.outgoing(e, pool, pe, record)
        pushed = Merge([pe, outgoing], relative_to=pool.biblio.relative_to, exchange=True,
                       base=_rekey(record.entry, pe.key))
        if pushed.conflicts or pushed.additions or pushed.new_files:
            library_changed = True
        if pool_changed and library_changed:
            break
    if pool_changed or library_changed:
        state = 'both changed' if pool_changed and library_changed else (
            'pool changed' if pool_changed else 'library changed')
        return state, _HINTS[state]
    if origin_path:
        pieces.save(origin_path)
    return 'in sync', None
