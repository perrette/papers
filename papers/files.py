"""The files of a library: what `add` does with a file (the `files` setting),
the names of the files of an entry, the download of files, the scan of a
directory by `add --recursive`, and the file operations of `papers file`
and `papers rm`.

Links of the bibtex are compared by real path (symbolic links resolved).
"""
import mimetypes
import os
import shutil
import tempfile
from urllib.parse import urlparse, unquote

import requests

import papers.config
from papers import logger
from papers.config import Config, LIBRARY_CONFIG_FILES
from papers.encoding import parse_file, format_file
from papers.entries import get_entry_val, parse_string
from papers.extract import extract_pdf_doi, isvaliddoi
from papers.latexenc import latex_to_unicode
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


# downloads
# =========

def _basename_from_url(url):
    path = urlparse(url).path
    name = unquote(path.rsplit('/', 1)[-1]) or 'download'
    # strip characters that would break filesystem paths
    return name.replace('/', '_').replace('\\', '_')


# prefix of the temporary directories of downloaded files
DOWNLOAD_PREFIX = 'papers_dl_'


def download_url(url, expect_pdf=False, dest_dir=None):
    """Download a URL to a local file and return its path.

    The file is saved into a fresh temporary directory using the URL's
    basename so that downstream renaming preserves a meaningful filename.

    If ``expect_pdf`` is True, the response must look like a PDF (content-type
    containing ``pdf`` or bytes beginning with ``%PDF``); otherwise only
    HTML responses are rejected (e.g. login/landing pages).
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "application/pdf,*/*;q=0.8" if expect_pdf else "*/*",
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
    except requests.exceptions.RequestException as err:
        raise ValueError(
            f"Failed to download from {url}: {type(err).__name__}: {err}. "
            "The connection failed before any HTTP response was received — "
            "this is often transient (try again), or due to TLS/network issues."
        ) from err
    ctype = response.headers.get("content-type", "").lower()
    if response.status_code != 200:
        hint = ""
        if response.headers.get("x-amzn-waf-action") or response.status_code == 202:
            hint = (" — server appears to require a JavaScript/CAPTCHA challenge "
                    "(AWS WAF or similar); download manually in a browser "
                    "and re-run with the local file path")
        raise ValueError(
            f"Failed to download from {url}: HTTP {response.status_code} "
            f"(content-type: {ctype or 'unknown'}){hint}"
        )
    if expect_pdf:
        if "pdf" not in ctype and not response.content.startswith(b"%PDF"):
            raise ValueError(
                f"URL did not return a PDF: {url} (content-type: {ctype or 'unknown'}). "
                "The server likely returned an HTML landing/login page; "
                "download the PDF manually in a browser and re-run with the local file path."
            )
    else:
        if "html" in ctype or response.content[:512].lstrip().lower().startswith((b"<!doctype html", b"<html")):
            raise ValueError(
                f"URL returned an HTML page rather than a file: {url} "
                f"(content-type: {ctype or 'unknown'}). The server likely returned "
                "a landing/login page; download the file manually in a browser "
                "and re-run with the local file path."
            )

    basename = _basename_from_url(url)
    if expect_pdf:
        if not basename.lower().endswith('.pdf'):
            basename += '.pdf'
    else:
        ext = mimetypes.guess_extension((ctype or '').split(';')[0].strip())
        if ext and not basename.lower().endswith(ext.lower()):
            basename += ext
    dest_dir = dest_dir or tempfile.mkdtemp(prefix=DOWNLOAD_PREFIX)
    local = os.path.join(dest_dir, basename)
    with open(local, 'wb') as f:
        f.write(response.content)
    return local


def is_download(file):
    "a file downloaded by papers into a temporary directory (see download_url)"
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


def files_policy(config, mode, pool_dirs=(), keep=()):
    """the FilesPolicy of a library (its configuration) for a files mode;
    pool_dirs: the files directories of its pools"""
    # files placed in the pool by a light library (see papers.pools.use_pool_files)
    light = config.light and any(realpath(config.filesdir or '') == realpath(d) for d in pool_dirs)
    return FilesPolicy(mode, config.filesdir, current_config=config.file, machine=config.machine, keep=keep,
                       pool_dirs=pool_dirs, light=light)


# names of the files of an entry, directory scan
# ===============================================

def hidden_bibtex(direc):
    """metadata of a directory of files of a single entry (layout of versions
    before 2.19, still read by `papers add` and `filecheck --clean-filesdir`)"""
    dirname = os.path.basename(direc)
    return os.path.join(direc, '.'+dirname+'.bib')


def read_entry_dir(direc, update_files=True, relative_to=None):
    """add a directory that contain files from a single entry
    """
    hidden_bib = hidden_bibtex(direc)
    if not os.path.exists(hidden_bib):
        raise TypeError('hidden bib missing: not an entry dir')

    db = parse_string(open(hidden_bib).read())
    assert len(db.entries) == 1, 'hidden bib must have one entry, got: '+str(len(db.entries))
    entry = db.entries[0]

    if update_files:
        for root, direcs, files in os.walk(direc):
            break # do not look further in subdirectories, cause any rename would flatten the tree
        files = [os.path.join(direc, file) for file in files if not file.startswith('.')]

    entry['file'] = format_file(files, relative_to=relative_to)
    return entry


# separates the entry name from the label of its other files: <name>--<label>.<ext>
ATTACHMENT_SEP = '--'


def attachment_label(file, prefixes=()):
    """label of an entry's file other than the first one: its name without
    extension, stripped of a '<prefix>--' already added by a rename"""
    stem = os.path.splitext(os.path.basename(file))[0]
    for prefix in prefixes:
        head = prefix + ATTACHMENT_SEP
        if prefix and stem.startswith(head) and len(stem) > len(head):
            return stem[len(head):]
    return stem


def attachment_names(files, target):
    """new paths of an entry's files: target.<ext> for the first one,
    target--<label>.<ext> for the others (see `attachment_label`),
    with a -2, -3... suffix if two labels coincide"""
    newfiles = [target + os.path.splitext(files[0])[1]]
    # prefixes of a previous rename: the current name of the first file, the target name
    prefixes = [os.path.splitext(os.path.basename(files[0]))[0], os.path.basename(target)]
    taken = {os.path.normcase(newfiles[0])}
    for file in files[1:]:
        ext = os.path.splitext(file)[1]
        label = attachment_label(file, prefixes)
        newfile = target + ATTACHMENT_SEP + label + ext
        i = 2
        while os.path.normcase(newfile) in taken:
            newfile = f'{target}{ATTACHMENT_SEP}{label}-{i}{ext}'
            i += 1
        taken.add(os.path.normcase(newfile))
        newfiles.append(newfile)
    return newfiles


def remove_entry_dir_if_empty(direc):
    """remove a directory of previous versions' layout (<name>/ with a hidden
    .<name>.bib) when nothing but the hidden bibtex is left in it"""
    hidden_bib = hidden_bibtex(direc)
    if not os.path.isfile(hidden_bib):
        return
    leftovers = [f for f in os.listdir(direc) if f != os.path.basename(hidden_bib)]
    if leftovers:
        logger.info(f'keep directory {direc}: other files remain ({", ".join(sorted(leftovers))})')
        return
    logger.info('remove directory: '+direc)
    if not papers.config.DRYRUN:
        shutil.rmtree(direc)


def group_attachments(names):
    """split the file names of a directory into main files and attachments:
    <name>--<label>.<ext> is an attachment of <name>.pdf when that file is
    among the names (the layout of `Biblio.rename_entry_files`). Returns a
    dict {main: [attachments]} in which every name that is not an attachment
    is a main file (with an empty list in most cases)."""
    stems = {os.path.splitext(name)[0]: name for name in names if name.lower().endswith('.pdf')}
    groups = {}
    attached = {}
    for name in names:
        stem = os.path.splitext(name)[0]
        # the longest main stem that this name continues with '--'
        prefixes = [s for s in stems if stems[s] != name and stem.startswith(s + ATTACHMENT_SEP)]
        if prefixes:
            attached[name] = stems[max(prefixes, key=len)]
    for name in names:
        if name not in attached:
            groups[name] = []
    for name in names:
        if name in attached:
            main = attached[name]
            while main in attached:  # a--b--c.pdf continues a--b.pdf, an attachment of a.pdf
                main = attached[main]
            groups[main].append(name)
    return groups


def scan_dir_walk(direc):
    """the files scanned by Biblio.scan_dir: yield ('entry', dir, []) for
    entry directories of the pre-2.19 layout (with a hidden bibtex), and
    ('file', path, attachments) for other files, where attachments are the
    files named after it (see `group_attachments`)"""
    top = os.path.abspath(direc)
    for root, direcs, files in os.walk(direc):
        dirname = os.path.basename(root)
        # never skip the scan root itself: basename('.') == '.' looks hidden
        if os.path.abspath(root) != top:
            if dirname.startswith('.'): continue
            if dirname.startswith('_'): continue

        if os.path.exists(hidden_bibtex(root)):
            yield 'entry', root, []
            continue

        names = sorted(file for file in files if not file.startswith('.'))
        for name, attachments in group_attachments(names).items():
            yield 'file', os.path.join(root, name), [os.path.join(root, a) for a in attachments]


def scan_dir_items(direc, quiet=False):
    """the items of `scan_dir_walk`, in the order Biblio.scan_dir adds them:
    entry directories and bibtex files first, then the other files, without
    those linked from the bibtex files (their entry comes from the bibtex,
    so they are neither parsed nor looked up online)"""
    first, others = [], []
    for item in scan_dir_walk(direc):
        kind, path, _ = item
        (first if kind == 'entry' or path.lower().endswith('.bib') else others).append(item)
    linked = set()
    for kind, path, _ in first:
        if kind != 'file':
            continue
        try:
            db = parse_string(open(path).read())
        except Exception as error:
            logger.warning(path+'::'+str(error))
            continue
        relative_to = os.path.dirname(os.path.abspath(path))
        for e in db.entries:
            for file in parse_file(get_entry_val(e, 'file', ''), relative_to=relative_to):
                linked.add(os.path.realpath(file))
    rest = []
    for item in others:
        if os.path.realpath(item[1]) in linked:
            if not quiet:
                logger.info(f'{item[1]}: linked from a scanned bibtex file, not scanned')
            continue
        rest.append(item)
    return first + rest


# papers file rename, attach, detach
# ==================================

def rename_files(biblio, entries, config, pool_dirs=(), keep_source=False):
    """place the files of the entries in the files directory, under their
    template name (a file that belongs to another library is copied, see
    FilesPolicy)"""
    if config.filesdir is None:
        raise PapersExit('the library has no files directory: pass --filesdir, '
                         'or set it with `papers config filesdir DIR`')
    policy = files_policy(config, 'copy' if keep_source else 'move', pool_dirs)
    for e in entries:
        try:
            biblio.rename_entry_files(e, copy=policy)
        except Exception as error:
            logger.error(f"{get_entry_val(e, 'ID', '')}: {error}")


def attach_files(biblio, e, files, config, mode, pool_dirs=()):
    """add files to the links of an entry, and place them as the files mode
    says (the files the entry had stay where they are)"""
    old = biblio.get_files(e)
    new = []
    for f in files:
        if str(f).startswith("http://") or str(f).startswith("https://"):
            new.append(download_url(f, expect_pdf=False))  # moved into the files directory
        elif not os.path.exists(f):
            raise PapersExit(f"file {f} does not exist")
        else:
            new.append(os.path.abspath(f))
    biblio.set_files(e, old + new)
    if mode != 'link' or any(is_download(f) for f in new):
        biblio.rename_entry_files(e, copy=files_policy(config, mode, pool_dirs, keep=old))


def detach_links(biblio, e, files):
    "remove links from an entry (files are compared by real path)"
    remove = {realpath(f) for f in files}
    biblio.set_files(e, [f for f in biblio.get_files(e) if realpath(f) not in remove])


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


def remove_entries(biblio, entries, filesdir, pool_dirs=()):
    """remove entries from the bibliography, and return the files that only
    they linked to, as files_to_delete does (inside, outside, kept, in_pool)"""
    files = [f for e in entries for f in biblio.get_files(e)]
    for e in entries:
        biblio.db.remove(e)
    return files_to_delete(biblio, files, filesdir, pool_dirs=pool_dirs)


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

def entry_filecheck_metadata(e, file, image=False):
    ''' parse pdf metadata and compare with entry: only doi for now
    '''
    if 'doi' not in e:
        raise ValueError(get_entry_val(e, 'ID', '')+': no doi, skip PDF parsing')

    try:
        doi = extract_pdf_doi(file, image=image)
    except Exception:
        raise ValueError(get_entry_val(e, 'ID', '')+': failed to parse doi: "{}"'.format(file))
    if not isvaliddoi(doi):
        raise ValueError(get_entry_val(e, 'ID', '')+': invalid parsed doi: '+doi)

    if doi.lower() != e['doi'].lower():
        raise ValueError(get_entry_val(e, 'ID', '')+': doi: entry <=> pdf : {} <=> {}'.format(e['doi'].lower(), doi.lower()))


def fix_mendeley_path(file, key=''):
    """the path of a file link as saved by Mendeley, repaired: latex symbols
    (e.g. "{\\_}") converted, and the leading "/" restored when it was omitted
    (home/... instead of /home/...)"""
    try:
        file = latex_to_unicode(file)
    except KeyError as error:
        logger.warning(key+': '+str(error)+': failed to convert latex symbols to unicode: '+file)

    # fix root (e.g. path starts with home instead of /home)
    dirname = os.path.dirname(file)
    candidate = os.path.sep + file
    if (not file.startswith(os.path.sep) and dirname # only apply when some directory name is specified
        and not os.path.exists(dirname)
        and os.path.exists(os.path.dirname(candidate))): # simply requires that '/'+directory exists
            file = candidate
    return file


def check_entry_files(biblio, e, metadata=False, fix=False):
    """the problems of the files of an entry, as lines to print:
    broken links, links that a repair of the path would fix (links saved by
    Mendeley), the same file linked twice, identical files (same checksum),
    and with metadata=True a DOI of the PDF that differs from the entry's.

    fix: apply the safe repairs (repaired paths; remove the second link of
    the same or an identical file, the file itself is kept).
    """
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


# papers file clean
# =================

def clean_filesdir(biblio, interactive=True, ignore_files=None, ignore_folders=None):
    """remove the files of the files directory that no entry links to, and
    the folders of versions before 2.19 (<name>/ with a hidden .<name>.bib)
    that no entry links to. Subfolders are scanned too (name templates may
    contain /); hidden files and folders, .bib files and folders named in
    ignore_folders are skipped. Returns the removed files."""
    if biblio.filesdir is None:
        raise ValueError('filesdir is not defined, cannot clean')
    removed_files = []

    allfiles = set(realpath(file) for e in biblio.entries for file in biblio.get_files(e))
    if ignore_files:
        for f in ignore_files:
            allfiles.add(realpath(f))
    allfolders = set(realpath(folder) for e in biblio.entries for folder in {os.path.dirname(file) for file in biblio.get_files(e)})

    ignore_folders = [realpath(f) if os.path.sep in f else f for f in (ignore_folders or [])]

    def _remove(path, folder=False):
        if papers.config.DRYRUN:
            print(f'DRYRUN: remove {path}')
        elif folder:
            shutil.rmtree(path)
        else:
            os.remove(path)

    for root, direcs, files in os.walk(biblio.filesdir):

        ANS = None  # Y(es) or N(o) for all files in this folder (reset at each pass)
        if realpath(root) in ignore_folders:
            direcs[:] = []
            continue
        for file in sorted(files):
            path = os.path.abspath(os.path.join(root, file))
            if file.startswith('.') or file.endswith('.bib'):
                continue
            if realpath(path) not in allfiles:
                name = os.path.relpath(path, biblio.filesdir)
                if interactive:
                    if ANS is None:
                        ans = input(f"File: {name} not in library. Remove ? [Y/n/Y/N] ")
                    else:
                        ans = ANS
                    if ans in ['Y', 'N']:
                        ans = ANS = ans.lower()  # same reply for all files in this folder
                    if ans.lower() == 'y':
                        _remove(path)
                        removed_files.append(path)
                else:
                    logger.info(f"Remove unlinked file {name}.")
                    _remove(path)
                    removed_files.append(path)

        subfolders = []
        for direc in sorted(direcs):
            # hidden folders (.git...) are never scanned
            if direc.startswith('.') or direc in ignore_folders:
                continue
            direcpath = os.path.abspath(os.path.join(root, direc))
            if realpath(direcpath) in ignore_folders:
                continue

            # folders of an entry with several files (versions before 2.19):
            # removed as a whole when no entry links to them, never scanned
            if not os.path.exists(hidden_bibtex(direcpath)):
                subfolders.append(direc)
                continue

            if realpath(direcpath) not in allfolders:
                name = os.path.relpath(direcpath, biblio.filesdir)
                if interactive:
                    ans = input(f"Folder: {name} not in library. Remove ? [Y/n] ")
                    if ans.lower() == 'y':
                        _remove(direcpath, folder=True)
                else:
                    logger.info(f"Remove folder {name}.")
                    _remove(direcpath, folder=True)

        direcs[:] = subfolders

    return removed_files
