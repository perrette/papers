"""The file operations of a command, recorded so that `papers undo` and
`papers redo` move the files back and forth with the bibtex (one step).

Each operation is a dict: `op` is moved (a file or a folder, renamed or
moved to another folder), copied, trashed (a file deleted by the command,
kept in the trash of the library, see `remove`) or removed (deleted for
good); `src` the path before, `dst` the path after (for removed: the
identical file that was kept, if any); `checksum` the sha256 of the file
(None for a folder). With the git backup, the operations of a command are
committed with its snapshot (JOURNAL_FILE); without it, the operations of
the last command are kept in the backup folder of the library, next to the
previous bibtex (see journal_file). The operations done after the save of the library (e.g.
the files deleted by papers rm) join them when the command ends (see
papers.library.finish_journal).

An operation is reversed (or replayed) only when the files are where it
left them, with the same content, and the place they go back to is free;
otherwise it is reported and nothing is done for that file.
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


def empty_trash(directory, days, megabytes):
    "remove the files of the trash older than `days`, then the oldest ones beyond `megabytes`"
    if not os.path.isdir(directory):
        return
    files = [os.path.join(directory, f) for f in os.listdir(directory)]
    files = sorted((os.path.getmtime(f), os.path.getsize(f), f) for f in files if os.path.isfile(f))
    limit = time.time() - days * 86400
    total = sum(size for _, size, _ in files)
    for mtime, size, f in files:  # the oldest first
        if mtime >= limit and total <= megabytes * MB:
            break
        logger.info(f'{f}: removed from the trash')
        os.remove(f)
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


def swap_last(bibtex, backupdir, pool_dirs=()):
    """the bibtex was swapped with its backup (undo or redo without git):
    reverse the operations of the last command, or replay them if they
    were reversed. To call before the swap; return the lines of the report,
    and the journal to save after the swap (see save_swapped), or None."""
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
    lines = (reverse if undo else replay)(journal.get('ops') or [], pool_dirs)
    journal['state'] = 'undone' if undo else 'done'
    return lines, journal


def save_swapped(bibtex, backupdir, journal):
    "after the swap of swap_last: the journal of the bibtex now in place"
    journal['bibtex'] = _checksum(bibtex)
    with open(journal_file(backupdir), 'w') as f:
        json.dump(journal, f, indent=1)


# reverse and replay
# ==================

def _show(path):
    relative = os.path.relpath(path)
    return relative if not relative.startswith('..') else papers.config.short_home(path)


def _arrow(src, dst, verb):
    "the line of a file put at another path: renamed in the same folder"
    if os.path.dirname(src) == os.path.dirname(dst) and verb.startswith('moved'):
        return f'    {_show(src)} --> {verb.replace("moved", "renamed")} {os.path.basename(dst)}'
    return f'    {_show(src)} --> {verb} {_show(dst)}'


def _same(path, digest):
    "path is the file of this checksum (a folder: exists)"
    if digest is None:
        return os.path.isdir(path)
    return _checksum(path) == digest


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


def reverse(ops, pool_dirs=()):
    """undo the operations, the last one first; a file moved into the files
    directory of the pool (pool_dirs) is copied back, the pool keeps it.
    Return the lines of the report."""
    lines = []
    for op in reversed(ops):
        kind, src, dst, digest = op['op'], op['src'], op.get('dst'), op.get('checksum')
        if kind in ('moved', 'copied') and not _same(dst, digest):
            lines.append(f'    {_show(dst)}: not where the command left it (or changed since): left as it is')
        elif kind == 'moved' and os.path.exists(src):
            lines.append(f'    {_show(dst)}: not moved back, {_show(src)} exists')
        elif kind == 'moved':
            copy = _inside(dst, pool_dirs)
            _place(dst, src, copy=copy)
            lines.append(_arrow(dst, src, 'copied back to' if copy else 'moved back to'))
        elif kind == 'copied' and not _same(src, digest):
            lines.append(f'    {_show(dst)}: kept, the original {_show(src)} is missing or changed')
        elif kind == 'copied':
            os.remove(dst)
            lines.append(f'    {_show(dst)}: removed (a copy of {_show(src)})')
        elif kind == 'trashed' and os.path.exists(src):
            lines.append(f'    {_show(src)}: exists, not restored from the trash')
        elif kind == 'trashed' and _same(dst, digest):
            _place(dst, src)
            lines.append(f'    {_show(src)}: restored from the trash')
        elif kind == 'trashed':
            lines.append(f'    {_show(src)}: no longer in the trash (see the trash-days and trash-size settings), '
                         'not restored')
        elif kind == 'removed' and os.path.exists(src):
            lines.append(f'    {_show(src)}: exists, not restored')
        elif kind == 'removed' and dst and _same(dst, digest):
            _place(dst, src, copy=True)
            lines.append(f'    {_show(src)}: restored (a copy of {_show(dst)})')
        elif kind == 'removed':
            lines.append(f'    {_show(src)}: deleted by the command, not restored')
    return lines


def replay(ops, pool_dirs=()):
    "redo the operations reversed by `reverse`, the first one first; return the lines of the report"
    lines = []
    for op in ops:
        kind, src, dst, digest = op['op'], op['src'], op.get('dst'), op.get('checksum')
        if kind in ('moved', 'copied') and not _same(src, digest):
            lines.append(f'    {_show(src)}: not where it was (or changed since): left as it is')
        elif kind == 'moved' and _inside(dst, pool_dirs) and _same(dst, digest):
            # copied back from the pool by `reverse`: the pool has the file
            os.remove(src)
            lines.append(_arrow(src, dst, 'moved to'))
        elif kind in ('moved', 'copied') and os.path.exists(dst):
            lines.append(f'    {_show(src)}: not {kind} again, {_show(dst)} exists')
        elif kind in ('moved', 'copied'):
            _place(src, dst, copy=kind == 'copied')
            lines.append(_arrow(src, dst, f'{kind} to'))
        elif kind == 'trashed' and _same(src, digest):
            if os.path.exists(dst):
                os.remove(src)
            else:
                _place(src, dst)
            os.utime(dst)
            lines.append(f'    {_show(src)}: deleted again (to the trash)')
        elif kind == 'removed' and _same(src, digest):
            os.remove(src)
            lines.append(f'    {_show(src)}: removed again')
    return lines


def report(kind, lines):
    "print the file lines of undo / redo"
    if lines:
        print(f'{kind}: the files of the command')
        print('\n'.join(lines))
    logger.debug(f'{kind}: {len(lines)} file operations')
