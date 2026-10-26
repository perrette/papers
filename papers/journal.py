"""The file operations of a command, recorded so that `papers undo` and
`papers redo` move the files back and forth with the bibtex (one step).

Each operation is a dict: `op` is moved (a file or a folder, renamed or
moved to another folder), copied, or removed; `src` the path before, `dst`
the path after (for removed: the identical file that was kept, if any);
`checksum` the sha256 of the file (None for a folder). With the git
backup, the operations of a command are committed with its snapshot
(JOURNAL_FILE); without it, the operations of the last command are kept
next to the backup of the bibtex (see journal_file).

An operation is reversed (or replayed) only when the files are where it
left them, with the same content, and the place they go back to is free;
otherwise it is reported and nothing is done for that file.
"""
import json
import os
import shutil
from contextlib import contextmanager

import papers.config
from papers import logger
from papers.utils import checksum

# the operations of a command, in the backup directory (one per commit)
JOURNAL_FILE = 'files-journal.json'

_ops = []
_owner = None  # real path of the bibtex of the library of the command
_paused = 0


def start(bibtex):
    "a new command, on the library of this bibtex"
    global _owner
    _ops.clear()
    _owner = os.path.realpath(bibtex) if bibtex else None


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


def record_deletions(files):
    """files that the command deletes after it saves the bibtex (e.g. papers
    rm --delete-files): recorded before the save, with the snapshot"""
    for f in files:
        if os.path.isfile(f):
            record('removed', f, digest=_checksum(f))


def take(bibtex):
    """the operations of the command if it acts on the library of this
    bibtex, and forget them (they belong to its next snapshot)"""
    if not bibtex or _owner != os.path.realpath(bibtex):
        return []
    ops = list(_ops)
    _ops.clear()
    return ops


# without the git backup: the operations of the last command
# ==========================================================

def journal_file(bibtex):
    "the operations of the last command, next to the backup of the bibtex (see papers.bib.backupfile)"
    return os.path.join(os.path.dirname(bibtex), '.' + os.path.basename(bibtex) + '.files.json')


def save_last(bibtex, ops):
    "after a command that wrote the bibtex (git backup off); no operations: no file"
    if papers.config.DRYRUN:
        return
    if not ops:
        if os.path.exists(journal_file(bibtex)):
            os.remove(journal_file(bibtex))
        return
    with open(journal_file(bibtex), 'w') as f:
        json.dump({'bibtex': _checksum(bibtex), 'state': 'done', 'ops': ops}, f, indent=1)


def swap_last(bibtex, pool_dirs=()):
    """the bibtex was swapped with its backup (undo or redo without git):
    reverse the operations of the last command, or replay them if they
    were reversed. To call before the swap; return the lines of the report,
    and the journal to save after the swap (see save_swapped), or None."""
    path = journal_file(bibtex)
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


def save_swapped(bibtex, journal):
    "after the swap of swap_last: the journal of the bibtex now in place"
    journal['bibtex'] = _checksum(bibtex)
    with open(journal_file(bibtex), 'w') as f:
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
