"""The history of a library: its states in the history of the machine (see
papers.history and design/history.md), for undo, redo and restore.

The project of a library is named by the identifier of its configuration
(see Config.library_id); its place is the real path of its bibtex. Before
a command writes the bibtex, `sync_head` records what is on disk if it is
not the current state (changed outside papers); after, `record` adds the
state of the command, with its file operations (see papers.journal).
`go_to` brings the library to another state: the bibtex, the files of
.papers/ (origin records, distinct.json, files.json) and the files.

A command that also writes another library (its pool: add in a shallow
library, auto-push, push, sync) records the step of that library in its
own: `pools` ({project id of the pool: {'state': n, 'base': its state before
the command, 'config': path of its configuration}}; base is the parent of n,
unless the command saved the pool several times). Undo and redo in the library take the pool step along:
undone (redone) when the pool is still where the command left it (where
the undo left it), else reverted (see papers.revert; the state of a revert
lists the steps it takes back in `reverts`). The step of the pool
records the folder of the library that made it (`from`).

The old backups (the git repository .papers/backup of the v3 branch, the
folders of ~/.local/share/papers/backups of earlier versions) are no
longer used: `stale_backups` lists them.
"""
import os
import sys
import time

import papers.checksums
import papers.config
import papers.utils
from papers import history, journal, lock, logger
from papers.checksums import FILES_JSON
from papers.duplicate import DISTINCT_FILE
from papers.utils import PapersExit, stdin_is_terminal

MB = 1024 * 1024
DAY = 86400
# without files deleted, the store is pruned every PRUNE_EVERY states (of the library)
PRUNE_EVERY = 50


def history_root(config):
    "the folder of the history of the machine (the history-dir setting)"
    if not config.history_dir:
        return papers.config.HISTORY_DIR
    # a relative path is relative to the folder of the global configuration (where history-dir is set)
    return config.machine.absolute(config.history_dir)


def store(config, id=None):
    """the store of the library `id`: the store shared by the libraries, or
    with the history-separate setting, a store of its own"""
    root = history_root(config)
    if config.history_separate and id:
        root = os.path.join(root, 'separate', id)
    return history.Store(root)


def all_stores(config):
    "the shared store and the separate ones"
    root = history_root(config)
    stores = [history.Store(root)]
    separate = os.path.join(root, 'separate')
    if os.path.isdir(separate):
        stores += [history.Store(os.path.join(separate, d)) for d in sorted(os.listdir(separate))]
    return stores


def history_size(config, st=None):
    """history-size in megabytes (0: no limit) of the store st (by default,
    that of the library): that of the library for a store of its own (the
    history-separate setting), that of the machine for the shared store"""
    separate = config.history_separate if st is None else os.path.basename(
        os.path.dirname(st.root)) == 'separate'
    value = config.history_size if separate else config.machine.get('history-size')
    if value is None:
        value = papers.config.default_value('history-size')
    return max(0, int(value or 0))


def _limit(config, st=None):
    return history_size(config, st) * MB


def project_of(config, create=True):
    """the project and the place of the library (None, None without bibtex,
    or without identifier when create is False)"""
    if not config.bibtex:
        return None, None
    place = os.path.realpath(config.bibtex)
    if config.file and config.is_library:
        id = config.library_id(create=create and not papers.config.DRYRUN)
        if id is None:
            return None, None
    else:
        id = history.sha256(place.encode())[:32]  # a bibtex without library: by its path
    return store(config, id).project(id), place


# the files of the library in a state
# ===================================

def _library_names(config):
    "the files of .papers/ that belong to the states of the library (relative to the library folder)"
    from papers.pools import ORIGIN_DIR, LEGACY_ORIGIN_FILE  # papers.pools imports this module
    libdir = config.libdir
    names = {DISTINCT_FILE, LEGACY_ORIGIN_FILE, FILES_JSON}
    origin = os.path.join(libdir, ORIGIN_DIR)
    if os.path.isdir(origin):
        names.update(os.path.join(ORIGIN_DIR, f) for f in os.listdir(origin) if f.endswith('.bib'))
    return sorted(n for n in names if os.path.isfile(os.path.join(libdir, n)))


def _read(path):
    with open(path, encoding='utf-8', newline='') as f:
        return f.read()


def _bibtex_text(config):
    return _read(config.bibtex) if os.path.exists(config.bibtex) else ''


def _texts(config):
    "the text of the bibtex and of the files of .papers/, as they are on disk"
    return _bibtex_text(config), {name: _read(os.path.join(config.libdir, name)) for name in _library_names(config)}


def _snapshot(config, st, files=None, texts=None):
    """the bibtex and the files of .papers/, stored; files: those of another
    state (the files of .papers/ are not read); texts: the texts to store
    (see _texts), instead of those on disk"""
    text, others = texts or (_bibtex_text(config), None)
    if files is None:
        if others is None:
            others = _texts(config)[1]
        files = {name: st.put_text(content) for name, content in others.items()}
    return {'bibtex': {'pieces': st.put_text(text), 'sha': history.sha256(text.encode('utf-8'))},
            'files': files}


def _relative_ops(ops, config):
    """the paths of the operations as the library writes its links: relative
    to the folder of the bibtex for a file in it (relative paths), else absolute"""
    if config.absolute_paths:
        return ops
    root = os.path.dirname(os.path.abspath(config.bibtex))

    def rel(path):
        if path and os.path.isabs(path):
            r = os.path.relpath(path, root)
            if r != '..' and not r.startswith('..' + os.sep):
                return r
        return path
    return [dict(op, src=rel(op['src']), dst=rel(op.get('dst'))) for op in ops]


def _absolute_ops(ops, config):
    root = os.path.dirname(os.path.abspath(config.bibtex))

    def ab(path):
        return os.path.normpath(os.path.join(root, path)) if path and not os.path.isabs(path) else path
    return [dict(op, src=ab(op['src']), dst=ab(op.get('dst'))) for op in ops]


def _deleted_refs(ops):
    return sorted({op['checksum'] for op in ops if op['op'] == 'trashed' and op.get('checksum')})


# recording
# =========

def _message():
    return 'papers ' + ' '.join(sys.argv[1:])


def mark(config, **fields):
    "fields of the next state of the library of `config` (see _fields)"
    _fields.setdefault(os.path.realpath(config.bibtex), {}).update(fields)


def sync_head(config, project=None, place=None):
    """the current state of the library, before a command writes it: the
    state of its place; a new place starts from the state that has its
    bibtex (a moved or copied library). If the bibtex on disk is not that
    state, it is recorded first: changed outside papers (or, without
    history yet, the library before its first command). Return the number
    of the state, or None (no bibtex, dry run)."""
    if project is None:
        project, place = project_of(config)
    if project is None or papers.config.DRYRUN:
        return None
    text = _bibtex_text(config)
    sha = history.sha256(text.encode('utf-8'))
    head = project.head(place)
    if head is None:
        project.forget_missing_places()
        n = project.start_state(sha)
        if n is not None:
            project.set_head(place, n)
            head = project.head(place)
    if head is not None and project.state(head['state'])['bibtex'].get('sha') == sha:
        return head['state']
    texts = None
    if head is None:
        kind, message, files = 'start', 'the library before its first recorded command', None
        texts = _before.get(place)  # the library before the command (see start)
        if texts is not None:
            sha = history.sha256(texts[0].encode('utf-8'))
    else:
        kind, message = 'outside', 'changed outside papers'
        files = project.state(head['state']).get('files')
        logger.info(f'{os.path.basename(config.bibtex)} changed outside papers since its last state: recorded')
    state = dict(parent=head['state'] if head else None, time=time.time(), kind=kind, message=message,
                 ops=[], deleted=[], **_snapshot(config, project.store, files=files, texts=texts))
    n = project.add(state)
    project.set_head(place, n)
    if head is None and texts is not None and texts[0] != text:
        return sync_head(config, project, place)  # changed by the command before its save: recorded after
    return n


# the commands that do not change a library, or that move in its history themselves
_NO_START = {'status', 'config', 'init', 'install', 'uninstall', 'migrate', 'history', 'backup', 'git',
             'undo', 'redo', 'restore', 'restore-backup'}


# the library before the command, for its first state: {place: texts (see _texts)}
_before = {}

# fields of the next state of a library, {place: fields} (e.g. reverts: the steps a revert takes back)
_fields = {}

# the steps that the command added to the histories of other libraries (its pools),
# for the next step of its own library: {project id: {'state': n, 'config': path}}
_linked = {}


def start(config, cmd):
    """at the start of a command: the library as it is before it, kept in
    memory, for its first state if it has no history yet (the command may
    write the files of .papers/ before it saves the bibtex; see sync_head).
    Nothing is written: a command that changes nothing leaves no trace."""
    _before.clear()
    _linked.clear()
    _fields.clear()
    if cmd in _NO_START or papers.config.DRYRUN or not config.bibtex or not os.path.exists(config.bibtex):
        return
    try:
        project, place = project_of(config, create=False)
        if project is None or project.head(place) is None:
            _before[os.path.realpath(config.bibtex)] = _texts(config)
    except Exception as error:
        logger.debug(f'the library before the command is not kept: {error}')


def record(config, message=None, ops=None):
    """after the save of the library: its state, with the file operations of
    the command (ops: those given, instead of those of the journal); return
    the number of the state, or None. The state of another library than
    that of the command (its pool) is linked to the next state of the
    library of the command (see _linked)."""
    project, place = project_of(config)
    if project is None or papers.config.DRYRUN:
        return None
    head = project.head(place)
    # the library had no state (e.g. its bibtex created by the command): the command is its first state
    parent = head['state'] if head else None
    ops = _relative_ops(journal.take(config.bibtex) if ops is None else ops, config)
    snap = _snapshot(config, project.store)
    own = journal.is_owner(config.bibtex)
    linked = dict(_linked) if own else {}
    previous = project.state(parent) if parent is not None else None
    if (previous and not ops and not linked and previous['bibtex'] == snap['bibtex']
            and previous.get('files') == snap['files']):
        n = parent
    else:
        state = dict(parent=parent, time=time.time(), kind='command', message=message or _message(),
                     ops=ops, deleted=_deleted_refs(ops), **snap)
        if linked:
            state['pools'] = linked
            _linked.clear()
        state.update(_fields.pop(place, {}))
        if not own and journal.owner():
            state['from'] = os.path.dirname(journal.owner())
        n = project.add(state)
        project.set_head(place, n)
        if not own and config.file and config.is_library:
            # the pool saved several times by the command: its last state, and its state before the first save
            first = _linked.get(project.id, {}).get('base', parent)
            _linked[project.id] = {'state': n, 'base': first, 'config': os.path.abspath(config.file)}
    if own and n != parent:
        # the operations done after the save join this state; after a save that added none, they
        # make a state of their own at the end of the command (not that of the previous command)
        journal.saved((config, n))
    if any(op['op'] == 'trashed' for op in ops) or len(project.states()) % PRUNE_EVERY == 0:
        prune(config, project.store)
    return n


def add_operations(config, n, ops):
    "the operations done after the save of the library join its state n, if it is still current"
    project, place = project_of(config)
    head = project.head(place) if project else None
    if head is None or head['state'] != n:
        logger.warning(f'{len(ops)} file operation(s) not recorded for undo: the library changed since')
        return
    state = dict(project.state(n))
    state['ops'] = state.get('ops', []) + _relative_ops(ops, config)
    state['deleted'] = _deleted_refs(state['ops'])
    project.update(n, state)
    if state['deleted']:
        prune(config, project.store)


def prune(config, st):
    """drop the oldest steps beyond history-size, and remove the pieces and
    files that no step needs any more (also with history-size 0, no limit:
    then no step is dropped)"""
    limit = _limit(config, st)
    dropped = st.prune(limit, discard=journal.to_system_trash)
    if dropped:
        logger.info(f'{len(dropped)} old step(s) dropped from the history '
                    f'(history-size: {history_size(config, st)} MB)')


# the files that a command deletes
# ================================

class Deleted:
    """where the files that a command deletes go (see papers.journal.remove):
    the store, unless the keep-deleted-files setting is off; and the
    question before deleting more than the history keeps"""
    def __init__(self, config):
        self.config = config
        self.keep = bool(config.keep_deleted_files)
        self._store = None

    @property
    def store(self):
        "the store of the library (its identifier is made when it deletes a file, not before)"
        if self._store is None:
            project, _ = project_of(self.config)
            self._store = project.store if project else store(self.config)
        return self._store

    def guard(self, total, count):
        if not self.keep:
            return False
        limit = _limit(self.config, self.store)
        size = history_size(self.config, self.store)
        if not limit:
            return True
        what = f'{count} file{"s" if count > 1 else ""} to delete, {total / MB:.0f} MB'
        if total > limit:
            question = (f'{what}: more than the history keeps (history-size: {size} MB).\n'
                        f'- This command cannot be undone: the files go to the trash of the system, '
                        f'not to the history (the history keeps its steps).')
            return False if _ask(question) else None
        dropped = self.store.prune(limit, extra=total, dry=True)
        if not dropped:
            return True
        now = time.time()
        recent = sum(1 for _, _, s in dropped if now - s.get('time', 0) < DAY)
        count_all = sum(len(self.store.project(id).states()) for id in self.store.project_ids())
        if recent or 2 * len(dropped) > count_all:
            question = (f'{what}: to keep them for undo, the history drops {len(dropped)} of its '
                        f'{count_all} steps' + (f', {recent} of them from the last day' if recent else '')
                        + f' (history-size: {size} MB).')
            return True if _ask(question) else None
        return True


def _ask(question):
    "True to proceed: -y/--yes, or the answer of the user; without a terminal, False"
    if journal.ASSUME_YES:
        return True
    print(question)
    if not stdin_is_terminal():
        logger.warning('no terminal to confirm: the files are kept (-y/--yes proceeds)')
        return False
    return input('Proceed? [y/N] ').strip().lower() in ('y', 'yes')


# going to another state
# ======================

def _pool_dirs(config):
    "the files directory of the pool of a shallow library: a file moved there is copied back by undo"
    if not config.shallow:
        return []
    from papers.pools import pool_files_dir  # papers.pools imports this module
    return [pool_files_dir(config)]


def describe(project, n):
    "the line of a state: identifier (short), command, time, and the library that made it (a step of a pool)"
    state = project.state(n)
    when = time.strftime('%Y-%m-%d %H:%M', time.localtime(state.get('time', 0)))
    origin = f', from {papers.config.short_home(state["from"])}' if state.get('from') else ''
    return f'{history.short(n)} {state.get("message", "")} ({when}{origin})'


def resolve(project, ref):
    "the identifier of the step that `ref` names (see Project.resolve); PapersExit if none or several"
    try:
        n = project.resolve(ref)
    except ValueError as error:
        raise PapersExit(str(error))
    if n is None:
        raise PapersExit(f'no step {ref} in the history of the library (see `papers history`)')
    return n


def state_hashes(config, project, n):
    "the checksums of the files of the state n ({path: sha256}, from its files.json)"
    pieces = (project.state(n).get('files') or {}).get(FILES_JSON)
    return papers.checksums.parse(project.store.text(pieces) if pieces else '{}', config)


def go_to(config, project, cur, target, pool_dirs=None, shared=()):
    """bring the library from the state `cur` to the state `target`: the
    files (command by command, then by checksum), the bibtex and the files
    of .papers/. pool_dirs: the folders whose files are copied back, not
    moved (by default, the files directory of the pool of a shallow
    library, see _pool_dirs); shared: the files that another library links
    to, also copied back. Return the lines of the report on the files."""
    from bibtexparser import parse_string
    lock.acquire(config)  # held already by a command that writes the library (see papers.lock)
    lock.check(config)
    st = project.store
    relative_to = os.path.dirname(os.path.abspath(config.bibtex))
    texts = {}

    def text(n):
        if n not in texts:
            try:
                texts[n] = st.text(project.state(n)['bibtex']['pieces'])
            except KeyError as error:
                raise PapersExit(f'the history of the library is damaged: {error}')
        return texts[n]

    def links(n):
        return papers.checksums.entry_links(parse_string(text(n)).entries, relative_to)

    def ops(n):
        return _absolute_ops(project.state(n).get('ops') or [], config)

    kw = dict(pool_dirs=_pool_dirs(config) if pool_dirs is None else pool_dirs, find_deleted=st.file_object,
              shared={os.path.normpath(f) for f in shared})
    back, forward = project.path(cur, target)
    lines = []
    with journal.unrecorded():  # moving in the history is not a step of it
        for n in back:
            parent = project.state(n).get('parent')
            if parent is None or project.state(parent) is None:
                break
            if ops(n):
                lines += journal.restore(links(n), links(parent), ops(n), True,
                                         hashes=state_hashes(config, project, parent), **kw)
        for n in forward:
            parent = project.state(n).get('parent')
            if ops(n) and parent is not None and project.state(parent) is not None:
                lines += journal.restore(links(parent), links(n), ops(n), False,
                                         hashes=state_hashes(config, project, n), **kw)
        current = papers.checksums.bibtex_links(config.bibtex, relative_to)
        lines += journal.restore(current, links(target), [], not forward,
                                 hashes=state_hashes(config, project, target), **kw)

    papers.utils.write_atomic(config.bibtex, text(target))
    _write_library_files(config, project, cur, target)
    return lines


def _write_library_files(config, project, cur, target):
    """the files of .papers/ of the state `target`; those of the state `cur`
    that `target` has not are removed (a file no state had is left alone)"""
    libdir = config.libdir

    def inside(name):
        return not os.path.relpath(os.path.join(libdir, name), libdir).startswith('..')

    files = project.state(target).get('files') or {}
    for name, pieces in files.items():
        if inside(name):
            path = os.path.join(libdir, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            papers.utils.write_atomic(path, project.store.text(pieces))
    for name in (project.state(cur).get('files') or {}):
        path = os.path.join(libdir, name)
        if name not in files and inside(name) and os.path.isfile(path):
            logger.info(f'remove {path}: not in the restored state')
            os.remove(path)


def _require(config):
    project, place = project_of(config)
    if project is None:
        raise PapersExit('no history: the library has no bibtex')
    return project, place


class _Pool:
    "a pool whose steps go with those of the library (see pool_steps)"
    def __init__(self, config, project, place, head, shown):
        self.config, self.project, self.place, self.head, self.shown = config, project, place, head, shown
        self.at = head['state']  # where the pool is, once the steps taken so far are
        self.taken = []  # the steps undone (redone) in the pool
        self.reverts = []  # the steps reverted in the pool (it moved on since)
        self.again = []  # the steps done again in the pool (redo: it moved on since the undo of the step)
        self.bases = {}  # step of reverts or again -> the state it is compared with (see pool_steps)


def _shown(config, pool_config):
    "how the messages name a pool: as the pool setting of the library writes it, else with ~"
    root = papers.config.config_root(pool_config.file)
    own = config.pool_path()
    if own is not None and os.path.realpath(own) == os.path.realpath(root):
        return config.pool_label()
    return papers.config.short_home(root)


def _pool(config, id, link):
    """the pool of a link (see _linked), as a _Pool, or a message: not
    found, or its bibtex changed outside papers since its last step"""
    file = link.get('config')
    pool_config = papers.config.Config.load(file, machine=config.machine) if file and os.path.isfile(file) else None
    project, place = project_of(pool_config, create=False) if pool_config else (None, None)
    if project is not None and project.id == id:
        lock.acquire(pool_config)  # before looking where the pool is: no other command writes it until the end
    if project is None or project.id != id or project.head(place) is None:
        return f'the pool of step {history.short(link["state"])} is not found (at {papers.config.short_home(file)})'
    pool = _Pool(pool_config, project, place, project.head(place), _shown(config, pool_config))
    if history.sha256(_bibtex_text(pool_config).encode('utf-8')) != project.state(pool.at)['bibtex'].get('sha'):
        return f'pool {pool.shown}: changed outside papers since its last step'
    return pool


def pool_steps(config, project, steps, undo):
    """the steps of the pools that go with the steps of the library undone
    (undo) or redone, `steps` in the order they are taken. A pool still at
    the step linked to a library step (for redo: where the undo left it)
    takes it back (does it again); once it moved on, the linked steps are
    reverted (for redo: the reverts made by the undo are reverted, and the
    steps that the undo took back are done again, see papers.revert).
    Return ([_Pool], the lines of the pools not found)."""
    pools, lines, gone = {}, [], set()
    for s in steps:
        for id, link in (project.state(s).get('pools') or {}).items():
            if id in gone:
                continue
            if id not in pools:
                pool = _pool(config, id, link)
                if isinstance(pool, str):
                    lines.append(f'{pool}: the library only')
                    gone.add(id)
                    continue
                pools[id] = pool
            pool = pools[id]
            n = link['state']
            # the pool's state before the command (several saves of the pool: before the first one)
            parent = link.get('base', (pool.project.state(n) or {}).get('parent'))
            if pool.project.state(n) is None or parent is None or pool.project.state(parent) is None:
                continue  # no longer in the history of the pool
            before, after = (n, parent) if undo else (parent, n)
            if pool.at == after:
                continue  # there already
            if pool.at == before and not pool.reverts:
                pool.taken.append(n)
                pool.at = after
            elif undo:
                pool.reverts.append(n)
                pool.bases[n] = parent
            else:
                line = pool.project.line(pool.at)
                revert = next((r for r in line if n in (pool.project.state(r).get('reverts') or [])), None)
                if revert is not None:
                    pool.reverts.append(revert)
                else:  # the undo took step n back there, and the pool moved on since: done again
                    pool.again.append(n)
                    pool.bases[n] = parent
    return [p for p in pools.values() if p.taken or p.reverts or p.again], lines


def _move_pools(config, pools, undo, kind):
    """bring the pools to the steps found by pool_steps (undo, redo), then
    revert the others (a new step of the pool); return the lines of the report"""
    import papers.revert  # papers.revert imports this module
    from papers.library import get_biblio, savebib
    from papers.merge import Resolver
    lines = []
    for pool in pools:
        if pool.taken:
            cur = pool.head['state']
            file_lines = go_to(pool.config, pool.project, cur, pool.at)
            redo = (list(reversed(pool.taken)) + pool.head['redo'] if undo
                    else [n for n in pool.head['redo'] if n not in pool.taken])
            pool.project.set_head(pool.place, pool.at, redo)
            lines.append(f'pool {pool.shown}: also {kind}, restored to {describe(pool.project, pool.at)}')
            lines += file_lines
        if pool.reverts or pool.again:
            # a conflict (an entry changed in the pool since) is asked in a terminal, else left as it is
            resolver = Resolver('ask' if stdin_is_terminal() else 'skip')
            biblio = get_biblio(pool.config)
            before = pool.project.head(pool.place)['state']
            revert_lines = []
            with journal.captured() as ops:  # the files of the pool: in its state, not in a step of the library
                for n in pool.reverts:
                    revert_lines += papers.revert.revert(pool.config, biblio, n, resolver, anywhere=True,
                                                         parent=pool.bases.get(n))
                for n in pool.again:
                    revert_lines += papers.revert.revert(pool.config, biblio, n, resolver, forward=True,
                                                         anywhere=True, parent=pool.bases.get(n))
                plural = lambda steps: f'step{"s" if len(steps) > 1 else ""} {", ".join(map(history.short, steps))}'
                what = ([f'revert of {plural(pool.reverts)}'] if pool.reverts else []) + (
                    [f'{plural(pool.again)} again'] if pool.again else [])
                mark(pool.config, reverts=list(pool.reverts), message=f'{_message()}: {", ".join(what)}')
                savebib(biblio, pool.config)
            pool.project = pool.project.store.project(pool.project.id)  # with the state of the revert
            head = pool.project.head(pool.place)['state']
            if ops and head != before:
                add_operations(pool.config, head, ops)
            done = ' and '.join(([f'{plural(pool.reverts)} reverted'] if pool.reverts else [])
                                + ([f'{plural(pool.again)} done again'] if pool.again else []))
            if head != before:
                lines.append(f'pool {pool.shown}: changed since, so {done} there: {describe(pool.project, head)}')
            else:
                lines.append(f'pool {pool.shown}: changed since; nothing changed there for {", ".join(what)} '
                             f'(the entries changed since are left as they are)')
            lines += ['    ' + line for line in revert_lines]
    return lines


def undo(config, steps=1, library_only=False):
    """go back `steps` states, the pool too for the steps that wrote it
    (unless library_only, see pool_steps); return (project, state restored,
    report on the files; None with --dry-run, report on the pools)"""
    project, place = _require(config)
    if papers.config.DRYRUN:
        cur = (project.head(place) or {}).get('state')
    else:
        cur = sync_head(config, project, place)
    line = project.line(cur) if cur is not None else []
    if len(line) <= steps:
        raise PapersExit('nothing to undo' if len(line) <= 1 else f'only {len(line) - 1} step(s) to undo')
    target = line[steps]
    if papers.config.DRYRUN:
        return project, target, None, []
    pools, missing = pool_steps(config, project, line[:steps], True) if not library_only else ([], [])
    redo = list(reversed(line[:steps])) + project.head(place)['redo']
    # the pools first: the files the command moved to a pool are moved back, unless the pool still links them
    pool_lines = _move_pools(config, pools, True, 'undone')
    shared = [f for p in pools for f in papers.checksums.bibtex_links(
        p.config.bibtex, os.path.dirname(os.path.abspath(p.config.bibtex)))]
    lines = go_to(config, project, cur, target, pool_dirs=[] if pools and not missing else None, shared=shared)
    project.set_head(place, target, redo)
    return project, target, lines, missing + pool_lines


def redo(config, steps=1, library_only=False):
    "go forward `steps` states (see undo)"
    project, place = _require(config)
    head = project.head(place)
    if head is None or not head['redo']:
        raise PapersExit('nothing to redo')
    cur = head['state']
    if not papers.config.DRYRUN and sync_head(config, project, place) != cur:
        raise PapersExit('nothing to redo: the library changed outside papers since the undo (recorded: '
                         '`papers undo` goes back before that change)')
    if len(head['redo']) < steps:
        raise PapersExit(f'only {len(head["redo"])} step(s) to redo')
    target = head['redo'][steps - 1]
    if papers.config.DRYRUN:
        return project, target, None, []
    pools, pool_lines = pool_steps(config, project, head['redo'][:steps], False) if not library_only else ([], [])
    # the library first: the files the command moved to the pool are there when the pool comes back
    lines = go_to(config, project, cur, target)
    project.set_head(place, target, head['redo'][steps:])
    return project, target, lines, pool_lines + _move_pools(config, pools, False, 'redone')


def restore(config, n=None):
    """go to the state n of the project of the library; without n, to the
    current state (the changes made outside papers since are undone, and
    recorded: `papers redo` brings them back). Return as undo (the library
    only: no pool)."""
    project, place = _require(config)
    head = project.head(place)
    if n is None:
        if head is None:
            raise PapersExit('no history: nothing to restore')
        target = head['state']
    else:
        target = resolve(project, n)
    if papers.config.DRYRUN:
        return project, target, None, []
    cur = sync_head(config, project, place)
    if cur == target:
        raise PapersExit(f'nothing to restore: {os.path.basename(config.bibtex)} is step {history.short(target)}')
    lines = go_to(config, project, cur, target)
    back, forward = project.path(cur, target)
    project.set_head(place, target, list(reversed(back)) if not forward else [])
    return project, target, lines, []


# the files kept by the history
# =============================

def kept_size(project, n):
    "bytes of the files that the state n keeps (the files its command deleted, still in the history)"
    total = 0
    for digest in project.state(n).get('deleted') or []:
        path = project.store.file_object(digest)
        if path:
            total += os.path.getsize(path)
    return total


def deleted_file(config, path):
    """a file deleted from `path` that the history still keeps: (its copy in
    the history, the step that deleted it), or None. The checksum is that of
    the last step that deleted a file there, else that of .papers/files.json."""
    project, _ = project_of(config, create=False)
    if project is None:
        return None
    path = os.path.normpath(os.path.abspath(path))
    states = project.states()
    for n in sorted(states, key=lambda n: states[n].get('time', 0), reverse=True):
        for op in _absolute_ops(states[n].get('ops') or [], config):
            if op['op'] == 'trashed' and op.get('checksum') and os.path.normpath(op['src']) == path:
                stored = project.store.file_object(op['checksum'])
                if stored:
                    return stored, n
    file = papers.checksums.files_json(config)
    digest = papers.checksums.parse(_read(file), config).get(path) if file and os.path.isfile(file) else None
    stored = project.store.file_object(digest) if digest else None
    return (stored, None) if stored else None


def is_path(target):
    "a path, not a step: a file that exists, or a name with a folder separator or a dot"
    return os.path.exists(target) or os.sep in target or '/' in target or '.' in target


def files_to_drop(config, project, target):
    """the files kept by the history that `target` names: a step (its
    identifier or a prefix of it: the files its command deleted), or a path
    (the file deleted from that place, by any step; see is_path). Return
    {checksum: (path before the deletion, bytes)}."""
    found = {}
    states = project.states()
    if not is_path(target):
        chosen, path = [resolve(project, target)], None
    else:
        chosen, path = list(states), os.path.abspath(os.path.expanduser(target))
    for n in chosen:
        for op in _absolute_ops(states[n].get('ops') or [], config):
            digest = op.get('checksum')
            if op['op'] != 'trashed' or digest not in (states[n].get('deleted') or []):
                continue
            if path is not None and os.path.normpath(op['src']) != os.path.normpath(path):
                continue
            stored = project.store.file_object(digest)
            if stored:
                found[digest] = (op['src'], os.path.getsize(stored))
    return found


def drop_files(project, digests):
    """remove files from the history: no state refers to them any more (their
    steps stay: undo says they are no longer in the history), and they go to
    the trash of the system, unless another library of the store keeps them"""
    for n, state in project.states().items():
        kept = [d for d in state.get('deleted') or [] if d not in digests]
        if kept != (state.get('deleted') or []):
            project.update(n, dict(state, deleted=kept))
    used = {d for id in project.store.project_ids() for s in project.store.project(id).states().values()
            for d in s.get('deleted') or []}
    for digest in digests:
        path = project.store.file_object(digest)
        if path and digest not in used:
            journal.to_system_trash(path)


# the old backups
# ===============

def _size(path):
    total = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def stale_backups(config):
    """the backups of earlier versions that papers no longer uses: [(path, bytes)]"""
    found = []
    if config.file and config.is_library:
        local = os.path.join(papers.config.config_root(config.file), papers.config.BACKUP_DIR_LOCAL)
        if os.path.isdir(local):
            found.append(local)
    for root in dict.fromkeys([papers.config.BACKUP_DIR, papers.config.BACKUP_DIR_LEGACY]):
        if os.path.isdir(root):
            found.append(root)
    return [(path, _size(path)) for path in found]
