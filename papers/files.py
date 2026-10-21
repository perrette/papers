"""The files of a library: what `add` does with a file (the `files` setting),
and the file operations of `papers file`, `papers rm`.

Links of the bibtex are compared by real path (symbolic links resolved).
"""
import os
import shutil
import tempfile

from papers import logger
from papers.entries import get_entry_val
from papers.bib import DOWNLOAD_PREFIX
from papers.config import Config, LIBRARY_CONFIG_FILES
from papers.utils import checksum, search_config, PapersExit


FILES_MODES = ('move', 'copy', 'link')


def realpath(path):
    return os.path.normcase(os.path.realpath(path))


def is_inside(path, folder):
    "path is folder or inside it (real paths)"
    if folder is None:
        return False
    path, folder = realpath(path), realpath(folder)
    return path == folder or path.startswith(folder.rstrip(os.path.sep) + os.path.sep)


def is_download(file):
    "a file downloaded by papers into a temporary directory (see bib.download_url)"
    parent = os.path.dirname(os.path.abspath(file))
    return (os.path.basename(parent).startswith(DOWNLOAD_PREFIX)
            and is_inside(parent, tempfile.gettempdir()))


class OtherLibraries:
    """finds the library a file belongs to: a library whose configuration is
    found in the file's directory or above, and whose files directory
    contains the file (only the files directory is checked, not the links
    of the library's bibtex)"""

    def __init__(self, current=None, machine=None):
        "current: configuration file of the current library (not an other library)"
        self.current = realpath(current) if current else None
        self.machine = machine
        self._cache = {}

    def _config(self, configfile):
        if configfile not in self._cache:
            try:
                self._cache[configfile] = Config.load(configfile, machine=self.machine)
            except Exception as error:
                logger.debug(f'{configfile}: {error}')
                self._cache[configfile] = None
        return self._cache[configfile]

    def owner(self, file):
        "configuration of the other library whose files directory holds `file`, or None"
        start = os.path.dirname(os.path.abspath(file))
        while True:
            configfile = search_config(LIBRARY_CONFIG_FILES, start_dir=start, default=None)
            if configfile is None:
                return None
            # the configuration file is in <library>/ or <library>/.papers/
            libdir = os.path.dirname(configfile)
            if os.path.basename(libdir) == '.papers':
                libdir = os.path.dirname(libdir)
            if self.current is None or realpath(configfile) != self.current:
                config = self._config(configfile)
                if config is not None and config.filesdir and is_inside(file, config.filesdir):
                    return config
            parent = os.path.dirname(libdir)
            if parent == libdir:
                return None
            start = parent


class FilesPolicy:
    """what to do with each file placed in the files directory (the `copy`
    argument of Biblio.rename_entry_files): 'move', 'copy' (a hard link when
    possible) or 'link' (leave it where it is).

    - mode is the `files` setting (or its command-line override);
    - a file that belongs to another library (see OtherLibraries) is never
      moved: `move` falls back to `copy` for it, so that the other library
      keeps its link;
    - a file already in the library's files directory is moved (renamed)
      in copy mode too, since a copy would leave an unlinked file there;
    - a file downloaded by papers into a temporary directory is always moved;
    - `keep` lists files to leave where they are, whatever the mode (e.g. the
      files an entry already had before `file attach`);
    - a file in the files directory of a pool (`pool_dirs`) is never moved:
      it is copied (a hard link when possible), or linked in link mode;
    - with `light`, `filesdir` is the files directory of the pool of a light
      library (papers.pools.use_pool_files): the files already there are
      linked where they are, never renamed, since other libraries may link
      to them.
    """

    def __init__(self, mode, filesdir=None, current_config=None, machine=None, keep=(), pool_dirs=(), light=False):
        if mode not in FILES_MODES:
            raise ValueError(f'files mode must be one of {", ".join(FILES_MODES)}, got {mode!r}')
        self.mode = mode
        self.filesdir = filesdir
        self.others = OtherLibraries(current_config, machine=machine)
        self.keep = {realpath(f) for f in keep}
        self.pool_dirs = [d for d in pool_dirs if d]
        self.light = light
        self._said = set()

    def __call__(self, file):
        if is_download(file):
            return 'move'
        if realpath(file) in self.keep:
            return 'link'
        if self.mode == 'link':
            return 'link'
        if is_inside(file, self.filesdir):
            return 'link' if self.light else 'move'
        if any(is_inside(file, d) for d in self.pool_dirs):
            return 'copy'
        if self.mode == 'move':
            owner = self.others.owner(file)
            if owner is not None:
                if file not in self._said:
                    print(f'{file} belongs to the library in {owner.configdir}: copied, not moved')
                    self._said.add(file)
                return 'copy'
        return self.mode


# links
# =====

def linked_files(biblio, entries=None):
    "real path of each linked file -> the entries that link to it"
    links = {}
    for e in (biblio.entries if entries is None else entries):
        for file in biblio.get_files(e):
            links.setdefault(realpath(file), []).append(e)
    return links


# papers file mv
# ==============

class Move:
    "one move of `papers file mv`: a file or a folder"
    def __init__(self, src, target):
        self.src = src
        self.real = realpath(src)  # before the move
        self.target = target
        self.isdir = os.path.isdir(src) and not os.path.islink(src)

    def new_path(self, real):
        "where the file of real path `real` is after the move, or None if it does not move"
        if real == self.real:
            return self.target
        if self.isdir and real.startswith(self.real.rstrip(os.path.sep) + os.path.sep):
            return os.path.join(self.target, os.path.relpath(real, self.real))
        return None


def plan_moves(biblio, sources, dest, force=False, protected=()):
    """the moves of `papers file mv SRC... DEST`, following the rules of
    `git mv`. All checks are done here, before anything moves:

    1. a source file that no entry links to is an error;
    2. a source folder must contain at least one linked file (the whole
       folder moves, unlinked files included);
    3. with several sources, the destination must be an existing folder;
    4. a destination that exists as a file is an error, unless force;
    and a source folder must not contain one of the `protected` files (the
    bibtex, the library configuration).
    """
    links = linked_files(biblio)
    dest = os.path.abspath(dest)
    errors = []
    if len(sources) > 1 and not os.path.isdir(dest):
        raise PapersExit(f'{dest}: with several sources, the destination must be an existing folder')
    moves = []
    for src in sources:
        src = os.path.abspath(src)
        if not os.path.lexists(src):
            errors.append(f'{src}: does not exist')
            continue
        move = Move(src, os.path.join(dest, os.path.basename(src)) if os.path.isdir(dest) else dest)
        if move.isdir:
            if not any(move.new_path(real) for real in links):
                errors.append(f'{src}: no entry links to a file in this folder')
                continue
            for file in protected:
                if file and move.new_path(realpath(file)):
                    errors.append(f'{src}: contains {file}, which cannot be moved with `papers file mv`')
        elif move.real not in links:
            errors.append(f'{src}: no entry links to this file')
            continue
        target = move.target
        if realpath(target) == move.real:
            errors.append(f'{src}: source and destination are the same')
        elif move.isdir and is_inside(target, src):
            errors.append(f'{src}: cannot move a folder inside itself')
        elif os.path.lexists(target):
            if os.path.isdir(target):
                errors.append(f'{target}: destination exists')
            elif move.isdir:
                errors.append(f'{target}: destination exists as a file')
            elif not force:
                errors.append(f'{target}: destination exists (-f/--force replaces it)')
        moves.append(move)
    for i, a in enumerate(moves):
        for b in moves[i+1:]:
            if a.real == b.real:
                errors.append(f'{a.src}: given twice')
            elif a.new_path(b.real) or b.new_path(a.real):
                errors.append(f'{b.src if a.new_path(b.real) else a.src}: inside another source')
            elif realpath(a.target) == realpath(b.target):
                errors.append(f'{a.src}, {b.src}: same destination {a.target}')
    if errors:
        raise PapersExit('\n'.join(errors) + '\nnothing was moved')
    return moves


def link_snapshot(biblio):
    "the file links of each entry with their real paths, taken before anything moves"
    snapshot = []
    for e in biblio.entries:
        files = biblio.get_files(e)
        snapshot.append((e, files, [realpath(f) for f in files]))
    return snapshot


def moved_links(snapshot, moves):
    """the new file links of the entries after the moves (see link_snapshot):
    [(entry, old files, new files)] for the entries that change"""
    changes = []
    for e, files, reals in snapshot:
        newfiles = []
        for file, real in zip(files, reals):
            new = next(filter(None, (m.new_path(real) for m in moves)), None)
            newfiles.append(new or file)
        if newfiles != files:
            changes.append((e, files, newfiles))
    return changes


def execute_moves(moves, force=False):
    """move the files and folders; return the moves done, and the error that
    stopped them (or None)"""
    done = []
    for move in moves:
        try:
            parent = os.path.dirname(move.target)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent)
            if force and os.path.isfile(move.target) and not move.isdir:
                os.remove(move.target)
            logger.info(f'mv {move.src} {move.target}')
            shutil.move(move.src, move.target)
        except OSError as error:
            return done, error
        done.append(move)
    return done, None


# papers rm, papers file detach --delete-files
# ===========================================

def files_to_delete(biblio, removed_files, filesdir, remaining=None, pool_dirs=()):
    """the files of removed entries or links that may be deleted:
    (inside, outside, kept, in_pool) where `inside` are in the files
    directory, `outside` are elsewhere, `kept` are still linked by a
    remaining entry, and `in_pool` are in the files directory of a pool
    (`pool_dirs`): those two are never deleted. Only existing files are
    returned, once each.
    """
    still_linked = linked_files(biblio, remaining)
    inside, outside, kept, in_pool = [], [], [], []
    seen = set()
    for file in removed_files:
        real = realpath(file)
        if real in seen or not os.path.exists(file):
            continue
        seen.add(real)
        if real in still_linked:
            kept.append(file)
        elif any(is_inside(file, d) for d in pool_dirs if d) and not is_inside(file, filesdir):
            in_pool.append(file)
        elif is_inside(file, filesdir):
            inside.append(file)
        else:
            outside.append(file)
    return inside, outside, kept, in_pool


def is_hard_link(file):
    return os.path.isfile(file) and os.stat(file).st_nlink > 1


def describe_file(file):
    "a file in a list of files to delete"
    if is_hard_link(file):
        return f'{file} (a hard link: only this link is deleted, the file remains at its other links)'
    return file


def delete_files(files, dryrun=False):
    for file in files:
        note = ' (hard link: the other links remain)' if is_hard_link(file) else ''
        print(f'{"DRYRUN: " if dryrun else ""}delete {file}{note}')
        if not dryrun:
            os.remove(file)


# papers file check
# =================

def check_entry_files(biblio, e, metadata=False, fix=False):
    """the problems of the files of an entry, as lines to print:
    broken links, links that a repair of the path would fix (links saved by
    Mendeley), the same file linked twice, identical files (same checksum),
    and with metadata=True a DOI of the PDF that differs from the entry's.

    fix: apply the safe repairs (repaired paths; remove the second link of
    the same or an identical file, the file itself is kept).
    """
    from papers.bib import fix_mendeley_path, entry_filecheck_metadata

    key = get_entry_val(e, 'ID', '')
    files = biblio.get_files(e)
    newfiles = []
    issues = []
    seen = {}
    hashes = {}
    done = 'fixed' if fix else 'fix with --fix'
    for file in files:
        if not os.path.exists(file):
            repaired = fix_mendeley_path(file, key=key)
            if repaired != file and os.path.exists(repaired):
                issues.append(f'{key}: path can be repaired: {file} -> {repaired} ({done})')
                if fix:
                    file = repaired
            else:
                issues.append(f'{key}: broken link: {file} (remove it with `papers file detach --broken {key}`)')
                newfiles.append(file)
                continue
        real = realpath(file)
        if real in seen:
            issues.append(f'{key}: the same file is linked twice: {seen[real]} and {file} ({done})')
            continue
        seen[real] = file
        if len(files) > 1 and os.path.isfile(file):
            hash_ = checksum(file)
            if hash_ in hashes:
                issues.append(f'{key}: identical files: {hashes[hash_]} and {file} '
                              f'({"link removed" if fix else "fix with --fix: removes the second link"})')
                if fix:
                    continue
            hashes.setdefault(hash_, file)
        if metadata and file.lower().endswith('.pdf'):
            try:
                entry_filecheck_metadata(e, file)
            except ValueError as error:
                issues.append(str(error))
        newfiles.append(file)
    if fix and newfiles != files:
        biblio.set_files(e, newfiles)
    return issues
