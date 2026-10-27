"""The file operations of a command, the trash of a library, and `restore`,
which brings the files from one state of the library to another (undo,
redo, restore).

Each operation is a dict: `op` is moved (a file or a folder, renamed or
moved to another folder), copied, trashed (a file deleted by the command,
kept in the trash of the library, see `remove`) or removed (deleted for
good); `src` the path before, `dst` the path after (for removed: the
identical file that was kept, if any); `checksum` the sha256 of the file
(None for a folder). With the git backup, the operations of a command are
committed with its snapshot (JOURNAL_FILE); without it, the operations of
the last command are kept in the backup folder of the library, next to the
previous bibtex (see journal_file). The operations done after the save of
the library (e.g. the files deleted by papers rm) join them when the
command ends (see papers.library.finish_journal).

`restore` compares the files that the entries link to in the two states:
the operations say what the commands did (moved or copied, deleted or only
unlinked, where from), the checksums find the files (see papers.checksums).
"""
import json
import os
import shutil
import time
from contextlib import contextmanager

import papers.config
from papers import logger
from papers.utils import checksum

# the operations of a command, in the backup directory (one per commit)
JOURNAL_FILE = 'files-journal.json'

# the trash of a library, in its backup directory: the files deleted by its commands
TRASH_DIR = 'trash'

_ops = []
_owner = None  # real path of the bibtex of the library of the command
_paused = 0
_trash = None  # (directory, days, megabytes) of the trash of the library of the command
_saved = None  # where the operations of the command went: ('git', gitdir, commit) or ('file', bibtex)


def start(bibtex, trash=None):
    """a new command, on the library of this bibtex; trash: (directory,
    days, megabytes) of its trash (see `remove`)"""
    global _owner, _trash, _saved
    _ops.clear()
    _owner = os.path.realpath(bibtex) if bibtex else None
    _trash = trash
    _saved = None


@contextmanager
def paused():
    "file operations that are not the command's (e.g. the copies of the git-lfs backup)"
    global _paused
    _paused += 1
    try:
        yield
    finally:
        _paused -= 1


def _checksum(path):
    "sha256 of a file, as text (None for a folder)"
    return checksum(path).hex() if os.path.isfile(path) else None


def record(op, src, dst=None, digest=None):
    """record an operation done (moved, copied: after it, the checksum of
    dst; removed: give the checksum, taken before)"""
    if _paused or papers.config.DRYRUN:
        return
    src, dst = os.path.abspath(src), dst and os.path.abspath(dst)
    if isinstance(digest, bytes):
        digest = digest.hex()
    if digest is None and op in ('moved', 'copied'):
        digest = _checksum(dst)
    _ops.append({'op': op, 'src': src, 'dst': dst, 'checksum': digest})


def take(bibtex):
    """the operations of the command if it acts on the library of this
    bibtex, and forget them (they belong to its next snapshot)"""
    if not bibtex or _owner != os.path.realpath(bibtex):
        return []
    ops = list(_ops)
    _ops.clear()
    return ops


def pending(bibtex):
    "the operations of the command so far, if it acts on the library of this bibtex"
    return list(_ops) if is_owner(bibtex) else []


def is_owner(bibtex):
    "the library of this bibtex is the library of the command"
    return bool(bibtex) and _owner == os.path.realpath(bibtex)


def saved(how):
    "where the operations of the command went (see `leftover`)"
    global _saved
    _saved = how


def leftover():
    """the operations done since the last snapshot of the library of the
    command, and where that snapshot is (see `saved`), or None"""
    ops = list(_ops)
    _ops.clear()
    return ops, _saved


# the trash
# =========

MB = 1024 * 1024


def trash_capacity():
    "the size of the trash of the library of the command, in megabytes, or None (no trash)"
    return _trash[2] if _trash is not None else None


def remove(path, trash=True):
    """delete a file for the command: it goes to the trash of the library
    (recorded, `undo` brings it back), unless trash=False, there is no
    trash, the file is larger than the trash, or the operation is not the
    command's (`paused`); then it is deleted (recorded as removed)"""
    if papers.config.DRYRUN:
        return
    if _paused or not trash or _trash is None or not os.path.isfile(path):
        if not _paused and os.path.isfile(path):
            record('removed', path, digest=_checksum(path))
        os.remove(path)
        return
    directory, days, megabytes = _trash
    size = os.path.getsize(path)
    if size > megabytes * MB:
        logger.warning(f'{path}: larger than the trash ({size / MB:.0f} MB > {megabytes} MB, '
                       f'the trash-size setting): deleted')
        record('removed', path, digest=_checksum(path))
        os.remove(path)
        return
    digest = _checksum(path)
    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, digest + os.path.splitext(path)[1])
    if os.path.exists(target):
        os.remove(path)  # the trash has this content already
    else:
        shutil.move(path, target)
    os.utime(target)  # the time it entered the trash
    record('trashed', path, target, digest)
    empty_trash(directory, days, megabytes)


def _to_system_trash(path):
    """a file that leaves the trash of the library goes to the trash of the
    system (the user empties it), or is deleted if there is none"""
    try:
        from send2trash import send2trash
        send2trash(path)
    except Exception as error:  # no trash of the system (e.g. a server), or no send2trash
        logger.debug(f'{path}: not sent to the trash of the system ({error}): deleted')
        os.remove(path)


def empty_trash(directory, days, megabytes):
    """the files of the trash older than `days`, then the oldest ones beyond
    `megabytes`, go to the trash of the system"""
    if not os.path.isdir(directory):
        return
    files = [os.path.join(directory, f) for f in os.listdir(directory)]
    files = sorted((os.path.getmtime(f), os.path.getsize(f), f) for f in files if os.path.isfile(f))
    limit = time.time() - days * 86400
    total = sum(size for _, size, _ in files)
    for mtime, size, f in files:  # the oldest first
        if mtime >= limit and total <= megabytes * MB:
            break
        logger.info(f'{f}: leaves the trash of the library, to the trash of the system')
        _to_system_trash(f)
        total -= size


def trash_size(directory):
    "files and bytes in the trash"
    if not os.path.isdir(directory):
        return 0, 0
    files = [os.path.join(directory, f) for f in os.listdir(directory)]
    return len(files), sum(os.path.getsize(f) for f in files if os.path.isfile(f))


# without the git backup: the operations of the last command
# ==========================================================

def journal_file(backupdir):
    "the operations of the last command, in the backup folder of the library, next to the previous bibtex"
    return os.path.join(backupdir, 'previous-files.json')


def save_last(bibtex, backupdir, ops):
    "after a command that wrote the bibtex (git backup off); no operations: no file"
    if papers.config.DRYRUN:
        return
    if is_owner(bibtex):
        saved(('file', bibtex, backupdir))
    if not ops:
        if os.path.exists(journal_file(backupdir)):
            os.remove(journal_file(backupdir))
        return
    os.makedirs(backupdir, exist_ok=True)
    with open(journal_file(backupdir), 'w') as f:
        json.dump({'bibtex': _checksum(bibtex), 'state': 'done', 'ops': ops}, f, indent=1)


def append_last(bibtex, backupdir, ops):
    "operations done after the save of the bibtex (git backup off): join those of its last change"
    path = journal_file(backupdir)
    os.makedirs(backupdir, exist_ok=True)
    journal = {'bibtex': _checksum(bibtex), 'state': 'done', 'ops': []}
    if os.path.exists(path):
        try:
            journal = json.load(open(path))
        except (OSError, ValueError):
            pass
    journal['ops'] = (journal.get('ops') or []) + ops
    with open(path, 'w') as f:
        json.dump(journal, f, indent=1)


def swap_last(bibtex, backupdir, current, target, pool_dirs=()):
    """the bibtex is swapped with its previous version (undo or redo without
    git): bring the files from the links of the bibtex (current) to those of
    the previous version (target), see `restore`. To call before the swap;
    return the lines of the report, and the journal to save after the swap
    (see save_swapped), or None."""
    path = journal_file(backupdir)
    if not os.path.exists(path) or not os.path.exists(bibtex):
        return [], None
    try:
        journal = json.load(open(path))
    except (OSError, ValueError):
        return [], None
    if journal.get('bibtex') != _checksum(bibtex):
        return [], None  # the bibtex changed since: the operations are not those of its last change
    undo = journal.get('state') == 'done'
    lines = restore(current, target, journal.get('ops') or [], undo, pool_dirs=pool_dirs,
                    trash_dir=os.path.join(backupdir, TRASH_DIR))
    journal['state'] = 'undone' if undo else 'done'
    return lines, journal


def save_swapped(bibtex, backupdir, journal):
    "after the swap of swap_last: the journal of the bibtex now in place"
    journal['bibtex'] = _checksum(bibtex)
    with open(journal_file(backupdir), 'w') as f:
        json.dump(journal, f, indent=1)


# restore: from one state of the files to another
# ===============================================

def _show(path):
    relative = os.path.relpath(path)
    return relative if not relative.startswith('..') else papers.config.short_home(path)


def _arrow(src, dst, verb):
    "the line of a file put at another path: renamed in the same folder"
    if os.path.dirname(src) == os.path.dirname(dst) and verb.startswith('moved'):
        return f'    {_show(src)} --> {verb.replace("moved", "renamed")} {os.path.basename(dst)}'
    return f'    {_show(src)} --> {verb} {_show(dst)}'


def _place(src, dst, copy=False):
    parent = os.path.dirname(dst)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if copy:
        shutil.copy2(src, dst)
    else:
        shutil.move(src, dst)


def _inside(path, dirs):
    real = os.path.realpath(path)
    return any(real.startswith(os.path.realpath(d) + os.sep) for d in dirs if d)


def lfs_object(gitdir, digest):
    "the copy of a file of this checksum in the git-lfs store of a backup, or None"
    if not gitdir or not digest:
        return None
    path = os.path.join(gitdir, '.git', 'lfs', 'objects', digest[:2], digest[2:4], digest)
    return path if os.path.isfile(path) else None


def trash_object(trash_dir, digest):
    "the file of this checksum in the trash, or None"
    if not trash_dir or not digest or not os.path.isdir(trash_dir):
        return None
    for name in os.listdir(trash_dir):
        if os.path.splitext(name)[0] == digest:
            return os.path.join(trash_dir, name)
    return None


def restore(current, target, ops, undo, hashes=None, pool_dirs=(), trash_dir=None, gitdir=None):
    """bring the files from one state of the library to another (undo,
    redo, restore). current, target: the paths of the files that the
    entries link to, now and in the state restored; ops: the operations of
    the commands between the two states, oldest first; undo: the state
    restored is the earlier one; hashes: the checksums of the files of the
    state restored ({path: sha256}, see papers.checksums).

    A file that the restored state links to and that does not exist is
    taken from: the other end of a move or copy of the commands; a file of
    the same checksum (one that no entry links to any more is moved, one
    that an entry links to, or a file of the pool, is copied); the trash;
    the git-lfs store of the backup (gitdir). Then the files that the
    commands put in place and that the restored state does not link go
    back: moved back to where they came from, or deleted (a copy; a
    file that the command deleted, when redone, goes to the trash). Files
    are never overwritten, and a file that changed since the command stays
    as it is; files that the commands did not touch are left alone.
    Return the lines of the report."""
    lines = []
    back = ' back' if undo else ''
    current, target = set(current), set(target)
    known = dict(hashes or {})
    moves = [op for op in ops if op['op'] in ('moved', 'copied')]
    for op in ops:
        for path in (op['src'], op.get('dst')):
            if path and op.get('checksum') and op['op'] in ('moved', 'copied', 'trashed', 'removed'):
                known.setdefault(path, op['checksum'])
    digests = {}

    def digest(path):
        if path not in digests:
            digests[path] = _checksum(path) if os.path.isfile(path) else None
        return digests[path]

    def partners(path):
        "the other ends of the moves and copies of `path`, the last command first, with the operation"
        for op in reversed(moves):
            if op['src'] == path and op['dst']:
                yield op['dst'], op
            elif op.get('dst') == path:
                yield op['src'], op

    mentioned = {p for op in moves for p in (op['src'], op['dst']) if p}
    # the identical files kept when the commands deleted a file (e.g. that of the pool): copied
    kept = {op['dst'] for op in ops if op['op'] == 'removed' and op.get('dst')}
    candidates = sorted((current | mentioned) - target) + sorted(target)
    reported = set()

    def place(path, src, copy, verb):
        "put the file src at path, and report it"
        _place(src, path, copy=copy)
        digests.pop(src, None)
        digests.pop(path, None)
        lines.append(_arrow(src, path, verb))

    for path in sorted(target - current):
        want = known.get(path)
        if os.path.lexists(path):
            # the place is taken by another file: what the command put elsewhere stays there
            if want and digest(path) != want:
                for other, _ in partners(path):
                    if os.path.exists(other) and other not in reported:
                        lines.append(f'    {_show(other)}: not moved{back}, {_show(path)} exists')
                        reported.add(other)
            continue
        source = None
        for other, op in partners(path):
            if not os.path.exists(other):
                continue
            if want and os.path.isfile(other) and digest(other) != want:
                lines.append(f'    {_show(other)}: not where the command left it (or changed since): left as it is')
                reported.add(other)
                continue
            source = other, op['op'] == 'copied' and other == op['src'], True
            break
        if source is None and want:
            other = next((c for c in candidates if c != path and os.path.isfile(c) and digest(c) == want), None)
            if other is not None:
                source = other, False, False
        if source is not None:
            other, copy, moved_by_command = source
            copy = copy or other in target or other in kept or _inside(other, pool_dirs)
            if copy and not moved_by_command:
                _place(other, path, copy=True)
                lines.append(f'    {_show(path)}: restored (a copy of {_show(other)})')
            else:
                place(path, other, copy, ('copied' if copy else 'moved') + back + ' to')
            continue
        found = trash_object(trash_dir, want)
        if found:
            _place(found, path)
            lines.append(f'    {_show(path)}: restored from the trash')
            continue
        found = lfs_object(gitdir, want)
        if found:
            _place(found, path, copy=True)
            lines.append(f'    {_show(path)}: restored from the git-lfs copy')
            continue
        deleted = [op for op in ops if op['src'] == path and op['op'] in ('trashed', 'removed')]
        if deleted and deleted[-1]['op'] == 'trashed':
            lines.append(f'    {_show(path)}: no longer in the trash (see the trash-days and trash-size settings), '
                         'not restored')
        elif deleted or want:
            lines.append(f'    {_show(path)}: deleted by the command, not restored')

    # the files that the commands put in place, and that the restored state does not link
    for path in sorted((current | mentioned) - target):
        if path in reported or not os.path.isfile(path):
            continue
        if undo:
            for other, op in partners(path):
                if op['dst'] != path or os.path.lexists(other) or other in current:
                    continue
                if op.get('checksum') and digest(path) != op['checksum']:
                    lines.append(f'    {_show(path)}: not where the command left it (or changed since): '
                                 'left as it is')
                elif op['op'] == 'moved':
                    copy = _inside(path, pool_dirs)
                    place(other, path, copy, ('copied' if copy else 'moved') + ' back to')
                break
            else:
                copied = next((op for op in reversed(moves) if op['op'] == 'copied' and op['dst'] == path), None)
                if copied and os.path.isfile(copied['src']) and digest(copied['src']) == digest(path):
                    os.remove(path)
                    lines.append(f'    {_show(path)}: removed (a copy of {_show(copied["src"])})')
        else:
            deleted = next((op for op in reversed(ops) if op['src'] == path
                            and op['op'] in ('trashed', 'removed', 'moved')), None)
            if deleted is None or (deleted.get('checksum') and digest(path) != deleted['checksum']):
                continue
            if deleted['op'] == 'moved':
                # copied back by the undo (e.g. from the pool, which keeps it): moved again
                if deleted['dst'] in target and digest(deleted['dst']) == digest(path):
                    os.remove(path)
                    lines.append(_arrow(path, deleted['dst'], 'moved to'))
            elif deleted['op'] == 'trashed':
                remove(path)
                lines.append(f'    {_show(path)}: deleted again (to the trash)')
            else:
                os.remove(path)
                lines.append(f'    {_show(path)}: removed again')
    return lines


def report(kind, lines):
    "print the file lines of undo / redo"
    if lines:
        print(f'{kind}: the files of the command')
        print('\n'.join(lines))
    logger.debug(f'{kind}: {len(lines)} file operations')
