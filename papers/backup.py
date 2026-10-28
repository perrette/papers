"""The history of a library: its states in the history of the machine (see
papers.history and design/history.md), for undo, redo and restore.

The project of a library is named by the identifier of its configuration
(see Config.library_id); its place is the real path of its bibtex. Before
a command writes the bibtex, `sync_head` records what is on disk if it is
not the current state (changed outside papers); after, `record` adds the
state of the command, with its file operations (see papers.journal).
`go_to` brings the library to another state: the bibtex, the files of
.papers/ (origin records, distinct.json, files.json) and the files.

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
from papers import history, journal, logger
from papers.checksums import FILES_JSON
from papers.duplicate import DISTINCT_FILE
from papers.utils import PapersExit, stdin_is_terminal

MB = 1024 * 1024
DAY = 86400
# without files deleted, the store is pruned every PRUNE_EVERY states
PRUNE_EVERY = 50


def history_root(config):
    "the folder of the history of the machine (the history-dir setting)"
    return os.path.expanduser(config.history_dir or papers.config.HISTORY_DIR)


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
    "the files of .papers/ that belong to the states of the library (relative to the folder of the bibtex)"
    from papers.pools import ORIGIN_DIR, LEGACY_ORIGIN_FILE  # papers.pools imports this module
    libdir = os.path.dirname(os.path.abspath(config.bibtex))
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
    libdir = os.path.dirname(os.path.abspath(config.bibtex))
    return _bibtex_text(config), {name: _read(os.path.join(libdir, name)) for name in _library_names(config)}


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


def start(config, cmd):
    """at the start of a command: the library as it is before it, kept in
    memory, for its first state if it has no history yet (the command may
    write the files of .papers/ before it saves the bibtex; see sync_head).
    Nothing is written: a command that changes nothing leaves no trace."""
    _before.clear()
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
    the number of the state, or None"""
    project, place = project_of(config)
    if project is None or papers.config.DRYRUN:
        return None
    head = project.head(place)
    # the library had no state (e.g. its bibtex created by the command): the command is its first state
    parent = head['state'] if head else None
    ops = _relative_ops(journal.take(config.bibtex) if ops is None else ops, config)
    snap = _snapshot(config, project.store)
    previous = project.state(parent) if parent is not None else None
    if previous and not ops and previous['bibtex'] == snap['bibtex'] and previous.get('files') == snap['files']:
        n = parent
    else:
        n = project.add(dict(parent=parent, time=time.time(), kind='command', message=message or _message(),
                             ops=ops, deleted=_deleted_refs(ops), **snap))
        project.set_head(place, n)
    if journal.is_owner(config.bibtex):
        journal.saved((config, n))
    if any(op['op'] == 'trashed' for op in ops) or n % PRUNE_EVERY == 0:
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
    limit = _limit(config, st)
    if not limit:
        return
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
                        f'not to the history.\n'
                        f'- The history of the libraries is dropped: no undo before this point.')
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
    "the line of a state: number, command, time"
    state = project.state(n)
    when = time.strftime('%Y-%m-%d %H:%M', time.localtime(state.get('time', 0)))
    return f'{n} {state.get("message", "")} ({when})'


def go_to(config, project, cur, target):
    """bring the library from the state `cur` to the state `target`: the
    files (command by command, then by checksum), the bibtex and the files
    of .papers/. Return the lines of the report on the files."""
    from bibtexparser import parse_string
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

    def hashes(n):
        pieces = (project.state(n).get('files') or {}).get(FILES_JSON)
        return papers.checksums.parse(st.text(pieces) if pieces else '{}', config)

    def ops(n):
        return _absolute_ops(project.state(n).get('ops') or [], config)

    kw = dict(pool_dirs=_pool_dirs(config), find_deleted=st.file_object)
    back, forward = project.path(cur, target)
    lines = []
    for n in back:
        parent = project.state(n).get('parent')
        if parent is None or project.state(parent) is None:
            break
        if ops(n):
            lines += journal.restore(links(n), links(parent), ops(n), True, hashes=hashes(parent), **kw)
    for n in forward:
        parent = project.state(n).get('parent')
        if ops(n) and parent is not None and project.state(parent) is not None:
            lines += journal.restore(links(parent), links(n), ops(n), False, hashes=hashes(n), **kw)
    current = papers.checksums.bibtex_links(config.bibtex, relative_to)
    lines += journal.restore(current, links(target), [], not forward, hashes=hashes(target), **kw)

    papers.utils.write_atomic(config.bibtex, text(target))
    _write_library_files(config, project, cur, target)
    return lines


def _write_library_files(config, project, cur, target):
    """the files of .papers/ of the state `target`; those of the state `cur`
    that `target` has not are removed (a file no state had is left alone)"""
    libdir = os.path.dirname(os.path.abspath(config.bibtex))

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


def undo(config, steps=1):
    """go back `steps` states; return (project, state restored, report on
    the files; None with --dry-run)"""
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
        return project, target, None
    redo = list(reversed(line[:steps])) + project.head(place)['redo']
    lines = go_to(config, project, cur, target)
    project.set_head(place, target, redo)
    return project, target, lines


def redo(config, steps=1):
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
        return project, target, None
    lines = go_to(config, project, cur, target)
    project.set_head(place, target, head['redo'][steps:])
    return project, target, lines


def restore(config, n=None):
    """go to the state n of the project of the library; without n, to the
    current state (the changes made outside papers since are undone, and
    recorded: `papers redo` brings them back). Return as undo."""
    project, place = _require(config)
    head = project.head(place)
    if n is None:
        if head is None:
            raise PapersExit('no history: nothing to restore')
        target = head['state']
    elif project.state(n) is None:
        raise PapersExit(f'no step {n} in the history of the library (see `papers history`)')
    else:
        target = n
    if papers.config.DRYRUN:
        return project, target, None
    cur = sync_head(config, project, place)
    if cur == target:
        raise PapersExit(f'nothing to restore: {os.path.basename(config.bibtex)} is step {target}')
    lines = go_to(config, project, cur, target)
    back, forward = project.path(cur, target)
    project.set_head(place, target, list(reversed(back)) if not forward else [])
    return project, target, lines


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
