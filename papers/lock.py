"""The locks of the libraries: a command that writes a library holds its
lock, .papers/lock, so that two commands (or papers and another program
that follows the same rules) do not write it at the same time.

A lock is a lease: a file created only if it does not exist, with a JSON
object {token, pid, host, command}. Its holder touches it (its modification
time) every REFRESH seconds (a thread), as long as the command runs; the
file is never rewritten, so a holder that lost its lock cannot overwrite
the lock of another command. A waiting command takes the lock over when it
is stale:

- the file did not change for LIFETIME seconds, measured on the clock of
  the waiting command (the clocks of two computers are never compared);
- or it names this computer and a process that no longer exists.

To take it over, the waiting command renames the stale file to a name of
its own (one step: two waiting commands cannot both get it) and checks that
the file it renamed is the one it found stale; a fresh lock taken by a
faster command meanwhile is put back (a hard link, or a copy with the same
token on a file system without hard links).

Before writing the library, the holder checks that the lock still has its
token (see `check`): a holder that could not refresh it in time (e.g. the
computer was asleep) stops instead of writing over the command that took
the lock over. The holder removes the lock at the end of the command, if
it still has its token.

A command locks the library of the command line first, then its pool
(see papers.pools.Pools.resolve); a command in the pool locks the pool
only: two commands never wait for each other. A lock does not help in a
folder synchronized by a service (Dropbox, Nextcloud…): the file reaches
the other computers seconds or minutes later.
"""
import atexit
import json
import os
import socket
import sys
import threading
import time
import uuid

import papers.config
from papers import logger
from papers.utils import PapersExit

LIFETIME = 10  # seconds without refresh after which a lock is stale
REFRESH = 2  # seconds between two refreshes by the holder
WAIT = 30  # seconds a command waits for a lock that is not stale
POLL = 0.1  # seconds between two looks at the lock of another command

LOCK_FILE = 'lock'


class LockError(PapersExit):
    "the lock of a library could not be taken, or was lost"


def lock_path(config):
    "the lock file of a library (.papers/lock), or None (a bibtex without library)"
    if not config.file or not config.is_library:
        return None
    return os.path.join(config.libdir, '.papers', LOCK_FILE)


# the locks held by this process: {real path of the lock file: content}
_held = {}
_thread = None
_stop = threading.Event()
_mutex = threading.Lock()


def _content(command):
    return {'token': uuid.uuid4().hex, 'pid': os.getpid(), 'host': socket.gethostname(), 'command': command}


def _read(path):
    "the content of a lock file, {} if it cannot be read (being written), None if it does not exist"
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {}


def _signature(path):
    "what changes when the lock file is refreshed or replaced (None: no file)"
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    return st.st_mtime_ns, st.st_size, st.st_ino


def _take_over(path, signature):
    """remove the stale lock file whose signature is `signature`: renamed
    first (one step), then removed if it is that file; a fresh lock found
    there instead is put back (unless another lock was created meanwhile),
    as a copy on a file system without hard links"""
    aside = f'{path}.{uuid.uuid4().hex}.stale'
    try:
        os.rename(path, aside)
    except FileNotFoundError:
        return
    if _signature(aside) == signature:
        os.remove(aside)
        return
    try:
        os.link(aside, path)  # put back: only if no lock was created meanwhile
    except FileExistsError:
        pass  # its holder finds another token at its check and stops
    except OSError:  # no hard links (some network or FAT drives): put back as a copy, same token
        content = _read(aside)
        if not content:  # still being written by its holder
            time.sleep(POLL)
            content = _read(aside)
        _create(path, content or {})
    os.remove(aside)


def _create(path, content):
    "create the lock file if it does not exist; return True if created"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, 'w') as f:
        json.dump(content, f)
    return True


def _process_gone(other):
    "the lock names this computer and a process that no longer exists"
    if other.get('host') != socket.gethostname() or not isinstance(other.get('pid'), int):
        return False
    if sys.platform == 'win32':  # os.kill would end the process: the lifetime decides
        return False
    try:
        os.kill(other['pid'], 0)
    except ProcessLookupError:
        return True
    except OSError:  # e.g. the process of another user
        return False
    return False


def _describe(other):
    if not other:
        return 'another command'
    return f'{other.get("command") or "another command"} (pid {other.get("pid")} on {other.get("host")})'


def acquire(config, command=None, wait=None):
    """take the lock of the library of `config` (nothing for a bibtex
    without library, or one this process holds already), waiting up to
    `wait` seconds (WAIT) for the command that holds it; LockError after"""
    path = lock_path(config)
    if path is None or papers.config.DRYRUN:
        return
    key = os.path.realpath(path)
    if key in _held:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    content = _content(command or 'papers ' + ' '.join(sys.argv[1:]))
    wait = WAIT if wait is None else wait
    start = time.monotonic()
    seen, since, told = None, None, False
    while True:
        if _create(path, content):
            break
        other = _read(path)
        signature = _signature(path)
        now = time.monotonic()
        if signature != seen:
            seen, since = signature, now
        stale = signature is not None and (now - since >= LIFETIME or (other and _process_gone(other)))
        if stale:
            logger.info(f'{papers.config.short_home(path)}: stale lock of {_describe(other)}, taken over')
            _take_over(path, signature)
            seen = None
            continue
        if now - start >= wait:
            raise LockError(f'{papers.config.short_home(os.path.dirname(os.path.dirname(path)))} is locked by '
                            f'{_describe(other)}: try again when it is done (the lock is {path})')
        if not told and now - start >= 1:
            logger.warning(f'waiting for {papers.config.short_home(os.path.dirname(os.path.dirname(path)))}: '
                           f'locked by {_describe(other)}')
            told = True
        time.sleep(POLL)
    with _mutex:
        _held[key] = content
    _start_refresh()


def check(config):
    """before writing the library of `config`: LockError if this process
    took its lock and lost it (not refreshed in time, taken over)"""
    path = lock_path(config)
    if path is None or papers.config.DRYRUN:
        return
    content = _held.get(os.path.realpath(path))
    if content is None:
        return
    other = _read(path)
    if other and other.get('token') != content['token']:
        with _mutex:
            _held.pop(os.path.realpath(path), None)
        raise LockError(f'{papers.config.short_home(path)}: the lock was taken over by {_describe(other)} '
                        f'(this command could not refresh it in time): nothing more is written')
    if other is None:  # removed by a command that found it stale: taken again, if still free
        if not _create(path, content):
            with _mutex:
                _held.pop(os.path.realpath(path), None)
            raise LockError(f'{papers.config.short_home(path)}: the lock was taken over by '
                            f'{_describe(_read(path))}: nothing more is written')


def release_all():
    "remove the locks of this process (those that still have its token)"
    _stop.set()
    with _mutex:
        held = list(_held.items())
        _held.clear()
    for path, content in held:
        if (_read(path) or {}).get('token') == content['token']:
            try:
                os.remove(path)
            except OSError:
                pass


def held():
    "the lock files held by this process"
    return sorted(_held)


def _refresh():
    while not _stop.wait(REFRESH):
        with _mutex:
            held = list(_held.items())
        for path, content in held:
            try:
                if (_read(path) or {}).get('token') == content['token']:
                    os.utime(path)
            except OSError as error:
                logger.debug(f'{path}: lock not refreshed: {error}')


def _start_refresh():
    global _thread
    if _thread is None or not _thread.is_alive():
        _stop.clear()
        _thread = threading.Thread(target=_refresh, name='papers-lock', daemon=True)
        _thread.start()


atexit.register(release_all)
