"""Pools: the libraries that a library exchanges entries with.

A library lists its pools in the `pools` setting: names of the per-machine
configuration, or paths relative to the library. Any library can be a pool.

- `Pools` resolves the `pools` setting to libraries, loaded when first used
  and kept for the run. A library never uses itself as a pool.
- `Origin` is `.papers/origin.bib` of a library: for each entry taken from a
  pool (or pulled, or pushed), the pool's version of the entry at that time,
  under the library's key, with the pool it came from (`papers-pool`), the
  pool's key (`papers-pool-key`) and the time (`papers-time`). It also holds
  the modification time of each pool's bibtex at the last pull, so that
  `status` and `pull --check` can tell that a pool changed since.
- `Exchange` does what involves a library and its pools: `add` looking in
  the pools first (`PoolLookup`), `pull`, `push`, the light conversions of
  `migrate --light/--full`, and the repair of broken links to pool files.
- `export` writes a selection of a library as a new library.

The key of an entry belongs to each library: `pull` and `push` never change
the key of the library they write to. An entry of the library is matched to
its pool entry by the identity rule (papers.duplicate.same_paper) applied to
its origin copy, then to the entry itself.
"""
import datetime
import os
from types import SimpleNamespace

from bibtexparser import Library
from bibtexparser.model import ExplicitComment

import papers.config
from papers import logger
from papers.config import Config, is_pool_path, CONFIG_FILE_LOCAL, LIBRARY_CONFIG_FILES
from papers.duplicate import Distinct, IdentityIndex, find_duplicates, same_paper, SAME, Verdict
from papers.entries import get_entry_val, set_entry_key, entry_copy, parse_string, format_library
from papers.files import realpath, is_inside
from papers.merge import Merge, apply_entry
from papers.utils import PapersExit, checksum, bcolors


class PoolError(PapersExit):
    "a pool that cannot be used (unknown name, missing, not a library)"


# LIBRARIES
# =========

def library_config_file(path):
    "the configuration file of the library in directory `path`, or None"
    for name in LIBRARY_CONFIG_FILES:
        file = os.path.join(path, name)
        if os.path.isfile(file):
            return file
    return None


def create_library(path, machine, bibtex='papers.bib', git=None):
    """create a library in directory `path` (as `papers init` does, without
    questions), and return its configuration file"""
    from papers.install import resolve_install, apply_install, DefaultAsker
    os.makedirs(path, exist_ok=True)
    o = SimpleNamespace(bibtex=os.path.join(path, bibtex), filesdir=os.path.join(path, 'files'),
                        reset=False, paths=None, absolute_paths=None, pool=None, gitdir=None,
                        editor=None, git=git, git_lfs=None)
    plan = resolve_install(Config(machine=machine), o, asker=DefaultAsker(),
                           target=os.path.join(path, CONFIG_FILE_LOCAL))
    print(f'create the library {path}')
    return apply_install(plan).file


def load_biblio(config):
    "the bibliography of a library, without creating its bibtex if it does not exist yet"
    from papers.bib import Biblio, get_biblio
    if config.bibtex and os.path.exists(config.bibtex):
        return get_biblio(config)
    relative_to = os.path.sep if config.absolute_paths else os.path.dirname(config.bibtex)
    return Biblio(filesdir=config.filesdir, nameformat=config.nameformat, keyformat=config.keyformat,
                  relative_to=relative_to, distinct=Distinct.for_bibtex(config.bibtex))


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


def mtime(file):
    "modification time of a file in nanoseconds, or None"
    try:
        return os.stat(file).st_mtime_ns
    except OSError:
        return None


# POOLS
# =====

class Pool:
    """a library used as a pool. `id` is how the library names it in its
    origin records: the pool name, or the path relative to the library."""

    def __init__(self, id, path, config):
        self.id = id
        self.path = path
        self.config = config
        self._biblio = None
        self._index = None
        self._sizes = None

    def __repr__(self):
        return f'Pool({self.id!r}, {self.path!r})'

    @property
    def label(self):
        return f'pool {self.id}'

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

    def find(self, entry, distinct=None):
        "the pool entry that is the same paper as `entry` (SAME verdict only), or None"
        pairs = self.biblio.distinct.pairs + (distinct.pairs if distinct is not None else [])
        found = find_duplicates(entry, self.biblio.entries, Distinct(pairs), index=self.index)
        return next((e for e, verdict in found if verdict.kind == SAME), None)

    def by_key(self, key, origin):
        """the pool entry of key `key` (the pool key of an origin record) if
        its identifiers do not contradict the origin copy: found this way
        when the title (the only identifier of entries without DOI) changed
        on both sides"""
        key = (key or '').lower()
        pe = next((x for x in self.biblio.entries if x.key.lower() == key), None) if key else None
        if pe is None:
            return None
        if same_paper(pe, origin).reason in ('different DOIs', 'different arXiv ids', 'different ISBNs'):
            return None
        return pe

    def find_doi(self, doi):
        from bibtexparser.model import Entry, Field
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
        self._sizes = None

    def update_entry(self, e, new):
        "replace the content of a pool entry (keeping the lookups up to date)"
        if self._index is not None:
            self._index.remove(e)
        apply_entry(e, new)
        self.add_entry(e)


class Pools:
    """the pools of a library (its `pools` setting), resolved when first
    used and kept for the run"""

    def __init__(self, config):
        self.config = config
        self._cache = {}

    @property
    def libdir(self):
        "the directory of the library (paths of the pools setting are relative to it)"
        return str(self.config.configdir) if self.config.file else os.getcwd()

    def _is_self(self, path):
        return self.config.file is not None and realpath(path) == realpath(self.libdir)

    def _id(self, pool, path):
        if not is_pool_path(pool):
            return pool
        # a path given on the command line: as the library's pools setting
        # writes it if it is one of them, else relative to the library
        for name in self.config.pools:
            if is_pool_path(name) and realpath(self.config.pool_path(name)) == realpath(path):
                return name
        rel = os.path.relpath(path, self.libdir)
        return rel if rel.startswith('.') else os.path.join('.', rel)

    def resolve(self, pool, relative_to=None, create=False):
        """the Pool of a name or path (relative to `relative_to`, by default
        the library). create: create the library if it does not exist."""
        if is_pool_path(pool):
            path = os.path.abspath(os.path.join(relative_to or self.libdir, os.path.expanduser(pool)))
        else:
            path = self.config.machine.pool_path(pool)
            if path is None:
                raise PoolError(f'unknown pool name: {pool} (define it with `papers pool add {pool} PATH`, '
                                'or write a path with a / to use a folder)')
        key = realpath(path)
        if key in self._cache:
            return self._cache[key]
        if self._is_self(path):
            raise PoolError(f'pool {pool}: {path} is this library')
        configfile = library_config_file(path)
        if configfile is None:
            if create:
                configfile = create_library(path, self.config.machine)
            elif not os.path.exists(path):
                raise PoolError(f'pool {pool}: {path} does not exist')
            else:
                raise PoolError(f'pool {pool}: {path} is not a library (no {CONFIG_FILE_LOCAL}): '
                                f'create it with `papers init {path}`')
        pool_ = Pool(self._id(pool, path), path, Config.load(configfile, machine=self.config.machine))
        self._cache[key] = pool_
        return pool_

    def all(self, quiet=False):
        """the pools of the library that can be used, in order. A pool that
        does not exist (yet) is left out silently, another error is a
        warning (none with quiet)."""
        pools = []
        for name in self.config.pools:
            path = self.config.pool_path(name)
            if path is not None and self._is_self(path):
                continue
            if path is not None and not os.path.exists(path):
                logger.debug(f'pool {name}: {path} does not exist')
                continue
            try:
                pools.append(self.resolve(name))
            except PoolError as error:
                if not quiet:
                    logger.warning(str(error))
        return pools

    def first(self, create=False):
        """the first pool of the library (where push and light libraries
        write). The default pool is created if it does not exist yet."""
        for name in self.config.pools:
            path = self.config.pool_path(name)
            if path is not None and self._is_self(path):
                continue
            return self.resolve(name, create=create and name == 'default')
        raise PoolError('the library has no pools: set them with `papers config pools NAME|PATH...`')

    def get(self, pool, create=False):
        "a pool named on the command line: a name, or a path relative to the current directory"
        return self.resolve(pool, relative_to=os.getcwd(), create=create and pool == 'default')

    def by_id(self, id):
        "the pool of an origin record, or None if it cannot be used"
        try:
            return self.resolve(id)
        except PoolError as error:
            logger.warning(str(error))
            return None

    def files_dirs(self):
        "the files directories of the pools that exist"
        return [p.filesdir for p in self.all(quiet=True) if p.filesdir]


# ORIGIN COPIES
# =============

ORIGIN_FILE = os.path.join('.papers', 'origin.bib')
POOL_FIELD = 'papers-pool'
POOL_KEY_FIELD = 'papers-pool-key'
TIME_FIELD = 'papers-time'
_ORIGIN_FIELDS = (POOL_FIELD, POOL_KEY_FIELD, TIME_FIELD)
# @comment{papers-pull <pool bibtex mtime in ns> <pool id>}
_PULL_COMMENT = 'papers-pull'


class Record:
    """the origin record of a library entry: `entry` is the pool's version
    (under the library key, without the papers-* fields and file links)"""

    def __init__(self, key, pool, pool_key, time, entry):
        self.key = key
        self.pool = pool
        self.pool_key = pool_key
        self.time = time
        self.entry = entry

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
    """`.papers/origin.bib` of a library (see the module documentation)"""

    def __init__(self, path=None):
        self.path = path
        self.entries = {}  # lower-case library key -> entry with the papers-* fields
        self.pulls = {}    # pool id -> mtime (ns) of the pool bibtex at the last pull
        self.changed = False

    @classmethod
    def for_bibtex(cls, bibtex):
        return cls.load(os.path.join(os.path.dirname(os.path.abspath(bibtex)), ORIGIN_FILE))

    @classmethod
    def load(cls, path):
        origin = cls(path)
        if not os.path.exists(path):
            return origin
        try:
            lib = parse_string(open(path).read())
        except Exception as error:
            logger.warning(f'{path}: could not be read ({error}); ignored')
            return origin
        for block in lib.comments:
            words = block.comment.strip().split(None, 2)
            if len(words) == 3 and words[0] == _PULL_COMMENT and words[1].isdigit():
                origin.pulls[words[2]] = int(words[1])
        for e in lib.entries:
            origin.entries[e.key.lower()] = e
        return origin

    def __len__(self):
        return len(self.entries)

    def _record(self, e):
        return Record(e.key, get_entry_val(e, POOL_FIELD, ''), get_entry_val(e, POOL_KEY_FIELD, ''),
                      get_entry_val(e, TIME_FIELD, ''), _strip(e, _ORIGIN_FIELDS))

    def get(self, entry):
        "the record of a library entry (by key, or by a former key of its ids field), or None"
        keys = [get_entry_val(entry, 'ID', '')] + [k.strip() for k in get_entry_val(entry, 'ids', '').split(',')]
        for key in keys:
            if key and key.lower() in self.entries:
                return self._record(self.entries[key.lower()])
        return None

    def records(self, pool=None):
        return [self._record(e) for e in self.entries.values() if pool is None or get_entry_val(e, POOL_FIELD, '') == pool]

    def set(self, key, pool, pool_entry):
        """record the pool's version of an entry (the record does not change
        if it is the same as before, its time included)"""
        from bibtexparser.model import Field
        new = _strip(pool_entry, ('file',) + _ORIGIN_FIELDS)
        old = self.entries.get(key.lower())
        if old is not None and get_entry_val(old, POOL_FIELD, '') == pool \
                and get_entry_val(old, POOL_KEY_FIELD, '') == pool_entry.key \
                and _same_fields(_strip(old, _ORIGIN_FIELDS), new):
            return
        set_entry_key(new, key)
        new.fields += [Field(POOL_FIELD, pool), Field(POOL_KEY_FIELD, pool_entry.key), Field(TIME_FIELD, _now())]
        self.entries[key.lower()] = new
        self.changed = True

    def remove(self, key):
        if self.entries.pop(key.lower(), None) is not None:
            self.changed = True

    def pulled(self, pool):
        "mtime (ns) of the pool's bibtex at the last pull, or None"
        return self.pulls.get(pool)

    def set_pulled(self, pool, mtime_ns):
        if mtime_ns is not None and self.pulls.get(pool) != mtime_ns:
            self.pulls[pool] = mtime_ns
            self.changed = True

    def save(self):
        if not self.changed or self.path is None:
            return
        if papers.config.DRYRUN:
            logger.info(f'DRYRUN: not saving {self.path}')
            return
        lib = Library()
        for pool, mtime_ns in sorted(self.pulls.items()):
            lib.add(ExplicitComment(f'{_PULL_COMMENT} {mtime_ns} {pool}'))
        for key in sorted(self.entries):
            lib.add(entry_copy(self.entries[key]))
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w') as f:
            f.write(format_library(lib))
        self.changed = False


def _same_fields(a, b):
    "same entry type and fields (values compared as written)"
    fields = lambda e: (e.entry_type.lower(), sorted((f.key, f.value) for f in e.fields))
    return fields(a) == fields(b)


# EXCHANGES BETWEEN A LIBRARY AND ITS POOLS
# =========================================

class Exchange:
    """a library (configuration and bibliography) with its pools and origin
    records. The command saves: the origin first (`origin.save()`), then
    the library and the pools that changed (`changed_pools`)."""

    def __init__(self, config, biblio, pools=None, origin=None):
        self.config = config
        self.biblio = biblio
        self.pools = pools or Pools(config)
        self.origin = origin if origin is not None else Origin.for_bibtex(config.bibtex)
        self.changed_pools = []

    def _changed(self, pool):
        if not any(p is pool for p in self.changed_pools):
            self.changed_pools.append(pool)

    # finding the pool entry of a library entry

    def pool_entry(self, e, pools=None):
        """(pool, pool entry, origin record) of a library entry, among `pools`
        (default: those of the library). The origin record's pool comes
        first, then the pools in order; record is None for an entry found
        without record (or in another pool than the record's)."""
        record = self.origin.get(e)
        pools = list(pools) if pools is not None else self.pools.all()
        if record is not None:
            pool = next((p for p in pools if p.id == record.pool), None)
            if pool is not None:
                pe = pool.find(record.entry, self.biblio.distinct) or pool.find(e, self.biblio.distinct) \
                    or pool.by_key(record.pool_key, record.entry)
                if pe is not None:
                    return pool, pe, record
        for pool in pools:
            pe = pool.find(e, self.biblio.distinct)
            if pe is not None:
                return pool, pe, (record if record is not None and record.pool == pool.id else None)
        return None, None, record

    def merge_distinct(self, pool):
        "union of the pairs that are not the same paper, both ways"
        self.biblio.distinct.update(pool.biblio.distinct)
        pool.biblio.distinct.update(self.biblio.distinct)

    # files

    def files_policy(self, mode=None, keep=()):
        """what to do with the files of entries taken from pools (see
        papers.files.FilesPolicy): in a light library they are linked where
        they are, otherwise as the files mode says (a pool file is copied,
        never moved)"""
        from papers.files import FilesPolicy
        if self.config.light:
            mode = 'link'
        mode = mode or self.config.files or 'move'
        if self.biblio.filesdir is None:
            mode = 'link'
        return FilesPolicy(mode, self.biblio.filesdir, current_config=self.config.file,
                           machine=self.config.machine, keep=keep, pool_dirs=self.pools.files_dirs())

    def _place_files(self, e, policy):
        if policy.mode == 'link' or self.biblio.filesdir is None:
            return
        self.biblio.rename_entry_files(e, copy=policy)

    # pull
    # ----

    def pull(self, entries, resolver, mode=None, record_pull=True):
        """three-way merge of the pool entries into the library entries
        (see papers.merge). Return the outcome of each entry: list of
        (entry, pool, what) where what is 'updated', 'linked', 'unchanged',
        'skipped' or 'not found'."""
        report = []
        pools = self.pools.all()
        for pool in pools:
            self.merge_distinct(pool)
        mtimes = {pool.id: pool.bibtex_mtime() for pool in pools}
        for e in entries:
            if resolver.quit:
                break
            pool, pe, record = self.pool_entry(e, pools)
            if pe is None:
                if record is not None:
                    report.append((e, None, 'not found'))
                continue
            report.append((e, pool, self._pull_one(e, pool, pe, record, resolver, mode)))
        if record_pull:
            for pool in pools:
                self.origin.set_pulled(pool.id, mtimes[pool.id])
        return report

    def _pull_one(self, e, pool, pe, record, resolver, mode):
        if self.config.light:
            self.repair_links([e], pools=[pool])
        incoming = entry_for(pe, pool.biblio, self.biblio)
        merge = Merge([e, incoming], relative_to=self.biblio.relative_to,
                      base=record.entry if record is not None else None)
        if not merge.conflicts and not merge.additions and not merge.new_files:
            self.origin.set(e.key, pool.id, pe)
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
        self._place_files(e, self.files_policy(mode, keep=old_files))
        self.origin.set(e.key, pool.id, pe)
        return 'updated'

    def check(self, entries, all_entries=True):
        """the report of `pull --check`: lines on the pools that changed
        since the last pull, and on the entries whose pool version changed
        since it was taken (no merge, nothing written)"""
        lines = []
        pools = self.pools.all()
        if all_entries:
            for pool in pools:
                lines.append(f'{pool.label}: {pool_state(self.origin, pool)}')
        for e in entries:
            pool, pe, record = self.pool_entry(e, pools)
            if pe is None:
                if record is not None:
                    lines.append(f'{e.key}: not found in pool {record.pool}')
                continue
            incoming = entry_for(pe, pool.biblio, self.biblio)
            if record is None:
                merge = Merge([e, incoming], relative_to=self.biblio.relative_to)
                if not merge.is_exact() or merge.new_files:
                    lines.append(f'{e.key}: in {pool.label} as {pe.key}, not pulled yet')
                continue
            merge = Merge([e, incoming], relative_to=self.biblio.relative_to, base=record.entry)
            changed = [f.name for f in merge.additions + merge.conflicts]
            if merge.new_files:
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
        key template. Return [(entry, pool, what)], what being 'added', 'updated',
        'linked', 'unchanged' or 'skipped'."""
        self.merge_distinct(pool)
        before = pool.bibtex_mtime()
        unchanged_since_pull = before is None or self.origin.pulled(pool.id) == before
        report = []
        for e in entries:
            if resolver.quit:
                break
            _, pe, record = self.pool_entry(e, [pool])
            if pe is None:
                if include_new:
                    report.append((e, pool, self._push_new(e, pool)))
                continue
            report.append((e, pool, self._push_one(e, pool, pe, record, resolver)))
        self._changed(pool)
        self._unchanged_since_pull = unchanged_since_pull
        return report

    def push_added(self, touched, new, resolver):
        """after `add`: in a light library, the entries added to or changed
        in the library go to its first pool (which holds their files); with
        `sync push`, the entries new to the library. Return the report of
        the push (see `push`)."""
        if self.config.light:
            targets = touched
        elif self.config.sync == 'push':
            targets = new
        else:
            return []
        unique = []
        for e in targets:
            if not any(e is x for x in unique):
                unique.append(e)
        if not unique:
            return []
        return self.push(unique, self.pools.first(create=True), resolver)

    def after_push(self, pool):
        """after the pool was saved: if it had not changed since the last
        pull, the push does not count as a change of the pool"""
        if getattr(self, '_unchanged_since_pull', False):
            self.origin.set_pulled(pool.id, pool.bibtex_mtime())

    def _pool_policy(self, pool, keep=()):
        "files pushed to a pool: copied (a hard link when possible), with the pool's name template"
        from papers.files import FilesPolicy
        return FilesPolicy('copy', pool.filesdir, current_config=pool.config.file,
                           machine=self.config.machine, keep=keep, light=True)

    def _push_new(self, e, pool):
        out = entry_for(e, self.biblio, pool.biblio)
        policy = self._pool_policy(pool)
        if 'ids' in out.fields_dict:
            del out['ids']  # former keys of the library
        new = pool.biblio.insert_entry(out, update_key=True, rename=pool.filesdir is not None, copy=policy)[0]
        pool.add_entry(new)
        self.origin.set(e.key, pool.id, new)
        return 'added'

    def _push_one(self, e, pool, pe, record, resolver):
        outgoing = entry_for(e, self.biblio, pool.biblio, key=pe.key)
        merge = Merge([pe, outgoing], relative_to=pool.biblio.relative_to,
                      base=_rekey(record.entry, pe.key) if record is not None else None)
        if not merge.conflicts and not merge.additions and not merge.new_files:
            self.origin.set(e.key, pool.id, pe)
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
            pool.biblio.rename_entry_files(pe, copy=self._pool_policy(pool, keep=old_files))
        self.origin.set(e.key, pool.id, pe)
        return 'updated'

    # light libraries
    # ---------------

    def repair_links(self, entries=None, pools=None):
        """replace the broken links to the files of a pool (a pool renamed
        or moved them) by the files of the pool entry. Return [(entry, old
        links, new links)] of the entries repaired."""
        pools = list(pools) if pools is not None else self.pools.all(quiet=True)
        dirs = [p.filesdir for p in pools if p.filesdir]
        repaired = []
        for e in (self.biblio.entries if entries is None else entries):
            files = self.biblio.get_files(e)
            broken = [f for f in files if not os.path.exists(f) and any(is_inside(f, d) for d in dirs)]
            if not broken:
                continue
            pool, pe, _ = self.pool_entry(e, pools)
            if pe is None:
                continue
            linked = {realpath(f) for f in files if os.path.exists(f)}
            new = [f for f in pool.biblio.get_files(pe) if os.path.exists(f) and realpath(f) not in linked]
            if not new:
                continue
            newfiles = [f for f in files if f not in broken] + new
            self.biblio.set_files(e, newfiles)
            repaired.append((e, files, newfiles))
        return repaired

    def to_light(self):
        """link the files of the library to the same files of the first pool
        (same paper, same content). Return (relinked entries, entries with
        files that are not in the pool, files to delete once the bibtex is
        saved, files relinked but kept since they are outside the files
        directory)."""
        pool = self.pools.first()
        if pool.filesdir is None:
            raise PoolError(f'{pool.label} has no files directory')
        relinked, missing, delete, kept = [], [], [], []
        for e in self.biblio.entries:
            files = self.biblio.get_files(e)
            own = [f for f in files if os.path.isfile(f) and not is_inside(f, pool.filesdir)]
            if not own:
                continue
            _, pe, _ = self.pool_entry(e, [pool])
            pool_files = {}
            if pe is not None:
                for f in pool.biblio.get_files(pe):
                    if os.path.isfile(f):
                        pool_files.setdefault(checksum(f), f)
            newfiles, complete = [], True
            for f in files:
                target = pool_files.get(checksum(f)) if f in own else f
                if target is None:
                    complete = False
                    target = f
                elif f in own:
                    (delete if is_inside(f, self.biblio.filesdir) else kept).append(f)
                if target not in newfiles:
                    newfiles.append(target)
            if not complete:
                missing.append(e)
            if newfiles != files:
                self.biblio.set_files(e, newfiles)
                relinked.append(e)
                if pe is not None:
                    self.origin.set(e.key, pool.id, pe)
        # never delete a file that an entry still links to
        linked = {realpath(f) for e in self.biblio.entries for f in self.biblio.get_files(e)}
        delete = [f for f in delete if realpath(f) not in linked]
        return relinked, missing, delete, kept

    def to_full(self):
        """copy (a hard link when possible) the pool files that the library
        links to into its files directory, with the library's name template.
        Return the entries whose links changed."""
        if self.biblio.filesdir is None:
            raise PapersExit('the library has no files directory: set it with `papers config filesdir DIR` first')
        self.repair_links()
        dirs = self.pools.files_dirs()
        changed = []
        for e in self.biblio.entries:
            files = self.biblio.get_files(e)
            if not any(os.path.exists(f) and any(is_inside(f, d) for d in dirs) for f in files):
                continue
            keep = [f for f in files if not any(is_inside(f, d) for d in dirs)]
            from papers.files import FilesPolicy
            policy = FilesPolicy('copy', self.biblio.filesdir, current_config=self.config.file,
                                 machine=self.config.machine, keep=keep, pool_dirs=dirs)
            self.biblio.rename_entry_files(e, copy=policy)
            if self.biblio.get_files(e) != files:
                changed.append(e)
        return changed


def _rekey(e, key):
    e = entry_copy(e)
    set_entry_key(e, key)
    return e


def report_lines(report, verb):
    """lines on the outcome of pull or push (see Exchange.pull, push): one
    per entry that changed, was skipped or is not found, then the counts"""
    counts = {}
    lines = []
    for e, pool, what in report:
        counts[what] = counts.get(what, 0) + 1
        if what != 'unchanged':
            lines.append(f'{what}: {e.key}' + (f' ({pool.label})' if pool is not None else ''))
    if counts:
        lines.append(f'{verb}: ' + ', '.join(f'{n} {what}' for what, n in counts.items()))
    else:
        lines.append(f'{verb}: nothing to do')
    return lines


def pool_state(origin, pool):
    "whether a pool changed since the last pull (a modification time check)"
    pulled = origin.pulled(pool.id)
    current = pool.bibtex_mtime()
    if pulled is None:
        return 'never pulled' if origin.records(pool.id) else 'not pulled from yet'
    if current != pulled:
        return 'changed since last pull'
    return 'unchanged since last pull'


# ADD: LOOK IN THE POOLS FIRST
# ============================

class PoolLookup:
    """the pool lookup of `add` (Biblio.pool_lookup): an added PDF, DOI or
    bibtex entry that is the same paper as a pool entry is taken from the
    pool, without fetching anything. The entries taken are recorded in the
    origin once inserted (see `inserted`)."""

    def __init__(self, exchange):
        self.exchange = exchange
        self.pools = exchange.pools.all()
        self._taken = {}

    def __bool__(self):
        return bool(self.pools)

    def _take(self, biblio, pool, pe, key, entry=None, files=()):
        """the entry to insert for pool entry pe: the pool's fields and files,
        and the fields only in `entry` (an added bibtex entry), and the
        `files` the pool does not have (same content)"""
        new = entry_for(pe, pool.biblio, biblio, key=key)
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
        print(f'found in {pool.label}: {pe.key}')
        return new

    def has_file(self, file):
        return any(pool.find_file(file)[0] is not None for pool in self.pools)

    def pdf(self, biblio, pdf, files=(), doi=None):
        """the entry for an added PDF found in a pool (same file content, or
        a DOI of the PDF that is in a pool, its title in the text), or None"""
        for pool in self.pools:
            pe, _ = pool.find_file(pdf)
            if pe is not None:
                return self._take(biblio, pool, pe, biblio.keyformat(pe), files=files)
        if doi:
            return self.doi(biblio, doi, files)
        from papers.extract import parse_doi_from_pdf_metadata, parse_dois, pdfhead, pdftail, title_in_text
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
            for pool in self.pools:
                pe = pool.find_doi(candidate)
                if pe is not None and title_in_text(get_entry_val(pe, 'title', ''), txt):
                    return self._take(biblio, pool, pe, biblio.keyformat(pe), files=files)
        return None

    def doi(self, biblio, doi, files=()):
        "the entry for an added DOI found in a pool, or None"
        for pool in self.pools:
            pe = pool.find_doi(doi)
            if pe is not None:
                return self._take(biblio, pool, pe, biblio.keyformat(pe), files=files)
        return None

    def entry(self, biblio, e):
        "the entry for an added bibtex entry found in a pool (it keeps its key), or None"
        for pool in self.pools:
            pe = pool.find(e, biblio.distinct)
            if pe is not None:
                files = biblio.get_files(e)
                e = _strip(e, ('file',))
                return self._take(biblio, pool, pe, e.key, entry=e, files=files)
        return None

    def is_taken(self, entry):
        return id(entry) in self._taken

    def inserted(self, entry, result):
        "record the origin of the library entries that an entry taken from a pool ended in"
        pool, pe = self._taken.pop(id(entry), (None, None))
        if pool is None:
            return
        for e in result:
            if self.exchange.origin.get(e) is None:
                self.exchange.origin.set(e.key, pool.id, pe)


def use_pool_files(config, pools):
    """in a light library, `add` places the files in the first pool, under
    the pool's name template: set them in the configuration of the run"""
    pool = pools.first(create=True)
    if pool.filesdir is None:
        raise PoolError(f'{pool.label} has no files directory, and this library is light')
    if config.source('name.template') == 'library':
        logger.warning('the name template of a light library is not used: the files are named '
                       f'with the template of {pool.label}')
    config.filesdir = pool.filesdir
    config.nameformat = pool.config.nameformat
    return pool


# EXPORT
# ======

def export(biblio, config, entries, dest, files='copy', git=None):
    """write the entries (and their files, as `files` says: copy, link or
    none) as a new library in directory `dest`, which must not exist or be
    empty. Return (configuration, bibliography) of the new library, for the
    caller to save."""
    from papers.bib import Biblio
    if os.path.exists(dest) and (not os.path.isdir(dest) or os.listdir(dest)):
        raise PapersExit(f'{dest}: exists and is not an empty directory')
    if papers.config.DRYRUN:
        raise PapersExit('export does not support --dry-run')
    name = os.path.basename(config.bibtex) if config.bibtex else 'papers.bib'
    new = Config.load(create_library(os.path.abspath(dest), config.machine, bibtex=name, git=git),
                      machine=config.machine)
    for setting in papers.config.SETTINGS:
        if setting.startswith(('name.', 'key.')) and config.source(setting) == 'library':
            new.set(setting, config.get(setting))
    new.save()
    target = Biblio(filesdir=new.filesdir, nameformat=new.nameformat, keyformat=new.keyformat,
                    relative_to=os.path.dirname(new.bibtex), distinct=Distinct.for_bibtex(new.bibtex))
    from papers.files import FilesPolicy
    for e in entries:
        c = entry_for(e, biblio, target)
        if files == 'none' and 'file' in c.fields_dict:
            del c['file']
        target.db.add(c)
        if files == 'copy' and target.get_files(c):
            target.rename_entry_files(c, copy=FilesPolicy('copy', target.filesdir, current_config=new.file,
                                                          machine=config.machine))
    target.distinct.update(biblio.distinct)
    return new, target


# STATUS
# ======

def status_lines(config):
    "lines of `papers status` on the pools of a library: path, and changes since the last pull"
    pools = Pools(config)
    origin = Origin.for_bibtex(config.bibtex) if config.bibtex else Origin()
    lines = []
    for name in config.pools:
        path = config.pool_path(name)
        label = name if not is_pool_path(name) else ''
        status = ''
        if path is not None and pools._is_self(path):
            status = ' (this library)'
        elif path is not None and not os.path.exists(path):
            status = bcolors.WARNING + ' (missing)' + bcolors.ENDC
        else:
            try:
                status = f' ({pool_state(origin, pools.resolve(name))})'
            except PoolError as error:
                reason = 'unknown pool name' if path is None else 'not a library'
                status = bcolors.WARNING + f' ({reason})' + bcolors.ENDC
        lines.append(f'    {label+": " if label else ""}{path or name}' + status)
    return lines


def machine_pool_lines(machine):
    "lines of `papers pool list` on the pools of the per-machine configuration"
    lines = []
    for name, path in machine.pools.items():
        full = machine.pool_path(name)
        if not os.path.exists(full):
            status = ' (missing)'
        elif library_config_file(full) is None:
            status = ' (not a library)'
        else:
            status = ''
        source = '' if name in machine.data.get('pools', {}) else ' (built-in default)'
        lines.append(f'    {name}: {path}{status}{source}')
    return lines


def pool_path_setting(config, path):
    "how the pools setting of a library writes the path of a pool: relative to the library, with a /"
    rel = os.path.relpath(os.path.abspath(path), config.configdir)
    return rel if rel.startswith('.') else os.path.join('.', rel)
