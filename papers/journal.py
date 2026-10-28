"""The file operations of a command, the files it deletes, and `restore`,
which brings the files from one state of the library to another (undo,
redo, restore).

Each operation is a dict: `op` is moved (a file or a folder, renamed or
moved to another folder), copied, trashed (a file deleted by the command,
kept in the history of the machine, see `remove`) or removed (deleted for
good, or sent to the trash of the system); `src` the path before, `dst` the
path after (for removed: the identical file that was kept, if any);
`checksum` the sha256 of the file (None for a folder). The operations of a
command are recorded with its state in the history (see papers.backup);
those done after the save of the library (e.g. the files deleted by papers
rm) join them when the command ends (see papers.library.finish_journal).

`restore` compares the files that the entries link to in the two states:
the operations say what the commands did (moved or copied, deleted or only
unlinked, where from), the checksums find the files (see papers.checksums).
"""
import os
import shutil
from contextlib import contextmanager

import papers.config
from papers import logger
from papers.utils import checksum

_ops = []
_owner = None  # real path of the bibtex of the library of the command
_paused = 0
_unrecorded = 0
_deleted = None  # where the files that the command deletes go (see papers.backup.Deleted), or None
_saved = None  # where the operations of the command went (see papers.backup.record)
# the answer to the questions before deleting files (see papers.files.delete_files): -y/--yes
ASSUME_YES = False


def start(bibtex, deleted=None):
    """a new command, on the library of this bibtex; deleted: where the
    files that it deletes go (see `remove`)"""
    global _owner, _deleted, _saved
    _ops.clear()
    _owner = os.path.realpath(bibtex) if bibtex else None
    _deleted = deleted
    _saved = None


@contextmanager
def unrecorded():
    """file operations that are not recorded, but done as the command's (a
    file deleted goes to the history): those of undo, redo and restore,
    which move in the history and are not a step of it"""
    global _unrecorded
    _unrecorded += 1
    try:
        yield
    finally:
        _unrecorded -= 1


@contextmanager
def paused():
    "file operations that are not the command's"
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
    if _paused or _unrecorded or papers.config.DRYRUN:
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


def rollback(bibtex, find_deleted=None):
    """put back the files of the operations of the command on the library of
    this bibtex, the last one first, and forget them (e.g. its save was
    refused: the bibtex does not record them). The safety rules of `restore`
    hold: no file is overwritten, a file changed since stays. Return the
    lines of the report."""
    ops = pending(bibtex)
    lines = []
    for op in reversed(ops):
        src, dst, digest = op['src'], op.get('dst'), op.get('checksum')
        if op['op'] in ('moved', 'copied') and dst and os.path.lexists(dst):
            if digest and os.path.isfile(dst) and _checksum(dst) != digest:
                lines.append(f'    {_show(dst)}: changed since: left as it is')
            elif op['op'] == 'moved' and not os.path.lexists(src):
                _place(dst, src)
                lines.append(_arrow(dst, src, 'moved back to'))
            elif op['op'] == 'copied' and os.path.isfile(src):
                os.remove(dst)
                lines.append(f'    {_show(dst)}: removed (a copy of {_show(src)})')
            else:
                lines.append(f'    {_show(dst)}: not moved back, {_show(src)} exists')
        elif op['op'] == 'trashed' and not os.path.lexists(src):
            found = find_deleted(digest) if find_deleted else None
            if found:
                _place(found, src, copy=True)
                lines.append(f'    {_show(src)}: restored from the history')
        elif op['op'] == 'removed' and not op.get('dst') and not os.path.lexists(src):
            lines.append(f'    {_show(src)}: deleted by the command, not restored')
    if is_owner(bibtex):
        _ops.clear()
    return lines


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


# the files deleted by the command
# =================================

MB = 1024 * 1024


def guard(total, count):
    """before deleting `count` files of `total` bytes: True (they are kept
    for undo), False (to the trash of the system: undo cannot bring them
    back) or None (the user said no: keep the files)"""
    if _deleted is None or papers.config.DRYRUN:
        return True
    return _deleted.guard(total, count)


def keeps_deleted():
    "the files that the command deletes are kept in the history"
    return _deleted is not None and _deleted.keep


def remove(path, trash=True):
    """delete a file for the command: it is kept in the history of the
    machine (recorded, `undo` brings it back), unless trash=False, the
    keep-deleted-files setting is off, or the operation is not the
    command's (`paused`); then it goes to the trash of the system, or is
    deleted (recorded as removed)"""
    if papers.config.DRYRUN:
        return
    if _paused or not trash or _deleted is None or not _deleted.keep or not os.path.isfile(path):
        if not _paused and os.path.isfile(path):
            record('removed', path, digest=_checksum(path))
        if _paused or not os.path.isfile(path):
            os.remove(path)
        else:
            to_system_trash(path)
        return
    digest = _checksum(path)
    _deleted.store.put_file(path, digest)
    record('trashed', path, None, digest)


def to_system_trash(path):
    """a file that papers does not keep goes to the trash of the system
    (the user empties it), or is deleted if there is none"""
    try:
        from send2trash import send2trash
        send2trash(path)
    except Exception as error:  # no trash of the system (e.g. a server), or no send2trash
        logger.debug(f'{path}: not sent to the trash of the system ({error}): deleted')
        if os.path.exists(path):
            os.remove(path)


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


def restore(current, target, ops, undo, hashes=None, pool_dirs=(), find_deleted=None):
    """bring the files from one state of the library to another (undo,
    redo, restore). current, target: the paths of the files that the
    entries link to, now and in the state restored; ops: the operations of
    the commands between the two states, oldest first; undo: the state
    restored is the earlier one; hashes: the checksums of the files of the
    state restored ({path: sha256}, see papers.checksums).

    A file that the restored state links to and that does not exist is
    taken from: the other end of a move or copy of the commands; a file of
    the same checksum (one that no entry links to any more is moved, one
    that an entry links to, or a file of the pool, is copied); the files
    deleted by the commands (find_deleted: checksum -> path, or None). Then the files that the
    commands put in place and that the restored state does not link go
    back: moved back to where they came from, or deleted (a copy; a
    file that the command deleted, when redone, goes to the history). Files
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
        found = find_deleted(want) if find_deleted and want else None
        if found:
            _place(found, path, copy=True)  # the history keeps it, for the other states
            lines.append(f'    {_show(path)}: restored from the history')
            continue
        deleted = [op for op in ops if op['src'] == path and op['op'] in ('trashed', 'removed')]
        if deleted and deleted[-1]['op'] == 'trashed':
            lines.append(f'    {_show(path)}: no longer in the history (see the history-size setting), '
                         'not restored')
        elif deleted or want:
            lines.append(f'    {_show(path)}: deleted by the command, not restored')

    # the files that no entry links to, deleted by the commands (e.g. papers file clean):
    # brought back by undo, deleted again by redo
    for op in (reversed(ops) if undo else ops):
        path = op['src']
        if op['op'] != 'trashed' or path in current or path in target or path in reported:
            continue
        reported.add(path)
        if undo and not os.path.lexists(path):
            found = find_deleted(op.get('checksum')) if find_deleted else None
            if found:
                _place(found, path, copy=True)
                lines.append(f'    {_show(path)}: restored from the history')
            else:
                lines.append(f'    {_show(path)}: no longer in the history (see the history-size setting), '
                             'not restored')
        elif not undo and os.path.isfile(path) and digest(path) == op.get('checksum'):
            remove(path)
            lines.append(f'    {_show(path)}: deleted again (kept in the history)')

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
                lines.append(f'    {_show(path)}: deleted again (kept in the history)')
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
