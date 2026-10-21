import os
from pathlib import Path
import shutil
import tempfile
import requests
from unidecode import unidecode as unicode_to_ascii
import bibtexparser
from bibtexparser import Library

from papers.entries import (
    get_entry_val,
    set_entry_key,
    update_entry,
    entry_copy,
    entry_content_equal,
    parse_string,
    format_library,
    entry_from_dict,
    library_from_entries,
)
from papers.encoding import (
    latex_to_unicode_library,
    convert_entry_to_unicode,
)

import papers
from papers import logger

from papers.extract import extract_pdf_doi, isvaliddoi, parse_doi
from papers.extract import extract_pdf_metadata
from papers.extract import fetch_bibtex_by_fulltext_crossref, fetch_bibtex_by_doi

from papers.encoding import parse_file, format_file, standard_name, family_names, format_entries, update_file_path, format_entry
from papers.latexenc import unicode_to_latex, latex_to_unicode

from papers.filename import NAMEFORMAT, KEYFORMAT
from papers.utils import bcolors, checksum, move as _move
import papers.config

from papers.duplicate import (
    conflict_resolution_on_insert,
    entry_diff,
    merge_files,
    check_duplicates,
    entry_id,
    _build_duplicate_index,
    _get_duplicate_candidates,
    _add_to_duplicate_index,
)

# URL DOWNLOAD
# ============

def _basename_from_url(url):
    from urllib.parse import urlparse, unquote
    path = urlparse(url).path
    name = unquote(path.rsplit('/', 1)[-1]) or 'download'
    # strip characters that would break filesystem paths
    return name.replace('/', '_').replace('\\', '_')


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
        import mimetypes
        ext = mimetypes.guess_extension((ctype or '').split(';')[0].strip())
        if ext and not basename.lower().endswith(ext.lower()):
            basename += ext
    dest_dir = dest_dir or tempfile.mkdtemp(prefix='papers_dl_')
    local = os.path.join(dest_dir, basename)
    with open(local, 'wb') as f:
        f.write(response.content)
    return local


# KEY GENERATION
# ==============

def append_abc(key, keys=[]):
    """
    >>> append_abc('Author2000')
    'Author2000b'
    >>> append_abc('Author2000b')
    'Author2000c'
    >>> append_abc('Author2000', ['Author2000', 'Author2000b'])
    'Author2000c'
    """
    letters = list('abcdefghijklmnopqrstuvwxyz')

    if key[-1] in letters:
        i = letters.index(key[-1])
        letters = letters[i+1:]
        key = key[:-1]
    else:
        letters = letters[1:] # start at b

    for l in letters:
        Key = (key+l)
        if Key not in keys:
            key = Key
            break
    assert Key not in keys, 'not enough letters in the alphabets to solve key conflict? or maybe something went wrong...'
    return Key


# DUPLICATE DEFINITION (entry_id, author_id, title_id live in papers.duplicate)
# =============================================================================

FUZZY_RATIO = 80

# Default similarity is used in papers add
# False positive (to weak a test) and distinct entries will be merged
# False negative and duplicates will be created
# PARTIAL means that If either DOI or author+title agree, that is good enough to be considered a duplicate
# I cant think of any situation where two legitimately distinct papers test True with partial similarity.
DEFAULT_SIMILARITY = 'PARTIAL'

EXACT_DUPLICATES = 104
GOOD_DUPLICATES = 103
FAIR_DUPLICATES = 102
PARTIAL_DUPLICATES = 101
FUZZY_DUPLICATES = 100


def compare_entries(e1, e2, fuzzy=False):
    """assess two entries' similarity
    """
    if entry_content_equal(e1, e2):
        return EXACT_DUPLICATES

    id1 = entry_id(e1)
    id2 = entry_id(e2)

    logger.debug('{} ?= {}'.format(id1, id2))

    if id1 == id2:
        score = GOOD_DUPLICATES

    elif get_entry_val(e1, 'doi') and get_entry_val(e2, 'doi') and e1['doi'] == e2['doi']:
        score = FAIR_DUPLICATES

    # elif all([f1==f2 for f1, f2 in zip(id1, id2) if f1 and f2]): # ID and AUTHORTITLE agree
    #     score = FAIR_DUPLICATES
    # COMMENT: same as GOOD_DUPLICATES when all fields are defined, but also returns true when one field is missing in one entry

    elif any([f1==f2 for f1, f2 in zip(id1, id2) if f1 and f2]): # any of ID or AUTHORTITLE agree
        score = PARTIAL_DUPLICATES

    elif not fuzzy:
        score = 0

    else:
        from rapidfuzz.fuzz import token_set_ratio
        doi1, tag1 = id1
        doi2, tag2 = id2
        score = token_set_ratio(tag1, tag2)

    return score

def are_duplicates(e1, e2, similarity=DEFAULT_SIMILARITY, fuzzy_ratio=FUZZY_RATIO):
    level = dict(
        EXACT = EXACT_DUPLICATES,
        GOOD = GOOD_DUPLICATES,
        FAIR = FAIR_DUPLICATES,
        PARTIAL = PARTIAL_DUPLICATES,
        FUZZY = FUZZY_DUPLICATES,
        )
    try:
        target = level[similarity]
    except KeyError:
        raise ValueError('similarity must be one of EXACT, GOOD, FAIR, PARTIAL, FUZZY')

    score = compare_entries(e1, e2, fuzzy=target==FUZZY_DUPLICATES)
    logger.debug('score: {}, target: {}, similarity: {}'.format(score, target, similarity))
    return score >= target


def hidden_bibtex(direc):
    """metadata of a directory of files of a single entry (layout of versions
    before 2.19, still read by `papers add` and `filecheck --clean-filesdir`)"""
    dirname = os.path.basename(direc)
    return os.path.join(direc, '.'+dirname+'.bib')


def read_entry_dir(direc, update_files=True, relative_to=None):
    """add a directory that contain files from a single entry
    """
    dirname = os.path.basename(direc)
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


def backupfile(bibtex):
    return os.path.join(os.path.dirname(bibtex), '.'+os.path.basename(bibtex)+'.backup')

class DuplicateKeyError(ValueError):
    pass

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


class Biblio:
    """
    The bibtex object that we operate on, which is mainly used to read and write to dynamically, and can then send the changes to be stored in a specified bibtex file on disk.
    """
    def __init__(self, db=None, filesdir=None, key_field='ID', nameformat=NAMEFORMAT, keyformat=KEYFORMAT, similarity=DEFAULT_SIMILARITY, relative_to=None):
        """
        relative_to : bibtex directory, optional
            use relative paths instead of absolute path
        """
        self.filesdir = filesdir
        # assume an already sorted list
        self.key_field = key_field
        if db is None:
            db = Library()
        elif not isinstance(db, Library):
            raise TypeError('db must be of type Library')
        self.db = db
        self.nameformat = nameformat
        self.keyformat = keyformat
        self.similarity = similarity
        self.relative_to = os.path.sep if relative_to is None else relative_to

    def move(self, file, newfile, copy=False, hardlink=False):
        return _move(file, newfile, copy=copy, dryrun=papers.config.DRYRUN, hardlink=hardlink)

    @property
    def entries(self):
        return self.db.entries

    @entries.setter
    def entries(self, entries):
        assert isinstance(entries, list)
        # Public API: remove all entries then add new list (keeps _entries_by_key in sync)
        for e in list(self.db.entries):
            self.db.remove(e)
        for e in entries:
            self.db.add(e)

    @classmethod
    def loads(cls, bibtex, filesdir):
        db = parse_string(bibtex)
        return cls(db, filesdir)

    def dumps(self):
        return format_library(self.db)

    @classmethod
    def load(cls, bibtex, filesdir, relative_to=None, **kw):
        bibtexs = open(bibtex).read()
        loaded_bib = cls(parse_string(bibtexs), filesdir, relative_to=relative_to if relative_to is not None else os.path.dirname(bibtex), **kw)
        return loaded_bib

    # make sure the path is right
    # def assert_files_exist(self):
    #     for e in self.entries:
    #         files = parse_file(e["file"], self.relative_to)
    #         for f in files:
    #             assert os.path.exists(f), f"{f} does not exist"

    @classmethod
    def newbib(cls, bibtex, filesdir, relative_to=None, **kw):
        assert not os.path.exists(bibtex)
        if os.path.dirname(bibtex) and not os.path.exists(os.path.dirname(bibtex)):
            os.makedirs(os.path.dirname(bibtex))
        open(bibtex,'w').write('')
        return cls.load(bibtex, filesdir, relative_to=relative_to, **kw)

    def key(self, e):
        return e[self.key_field].lower()

    def eq(self, e1, e2):
        return are_duplicates(e1, e2, similarity=self.similarity)

    def __contains___(self, entry):
        return any({self.eq(entry, e) for e in self.entries})


    def sort(self):
        """Re-order library by block type and entry key (public API: SortBlocksByTypeAndKeyMiddleware)."""
        from bibtexparser.middlewares import SortBlocksByTypeAndKeyMiddleware
        self.db = SortBlocksByTypeAndKeyMiddleware().transform(library=self.db)

    def insert_entry(self, entry, update_key=False, check_duplicate=False, rename=False, copy=False, metadata={}, **checkopt):
        """
        """
        if metadata:
            files = self.get_files(entry) + self.get_files(metadata)
            self.set_files(metadata, files)

        if update_key:
            set_entry_key(entry, self.generate_key(entry))

        # additional checks on DOI etc...
        if check_duplicate:
            logger.debug('check duplicates : TRUE')
            return self.insert_entry_check(
                entry, update_key=update_key, rename=rename, copy=copy,
                duplicate_index=checkopt.pop('duplicate_index', None), **checkopt
            )
        else:
            logger.debug('check duplicates : FALSE')

        # Key duplicate check: lookup by key (public API), case-insensitive to match entries_dict keys
        key_lower = self.key(entry)
        existing_same_key = next(
            (e for k, e in self.db.entries_dict.items() if k.lower() == key_lower),
            None,
        )
        if existing_same_key is not None:
            logger.info('key duplicate: '+self.key(existing_same_key))

            if get_entry_val(existing_same_key, 'title', '') == get_entry_val(entry, 'title', ''):
                logger.info('exact duplicate')
                # keep the files of the new entry
                files = self.get_files(existing_same_key) + self.get_files(entry)
                if files:
                    self.set_files(existing_same_key, files)
                if rename: self.rename_entry_files(existing_same_key, copy=copy)
                return [ existing_same_key ]

            if update_key:
                newkey = self.generate_key(entry)  # unique key from content (e.g. DOI)
                logger.info('update key: {} => {}'.format(get_entry_val(entry, 'ID', ''), newkey))
                set_entry_key(entry, newkey)

            else:
                raise DuplicateKeyError('Key conflict. Try update_key is True or specify --key KEY explicitly')

        else:
            logger.info('new entry: '+self.key(entry))

        self.db.add(entry)

        if rename: self.rename_entry_files(entry, copy=copy)

        return [ entry ]

    def insert_entry_check(self, entry, update_key=False, mergefiles=True, on_conflict='i', rename=False, copy=False, duplicate_index=None):
        # FUZZY can match on token_set_ratio(authortitle) without same doi/authortitle, so index would miss some duplicates
        if self.similarity == 'FUZZY':
            candidates = self.entries
        elif duplicate_index is not None:
            by_doi, by_authortitle = duplicate_index
            candidates = _get_duplicate_candidates(entry, by_doi, by_authortitle)
        else:
            by_doi, by_authortitle = _build_duplicate_index(self.entries)
            candidates = _get_duplicate_candidates(entry, by_doi, by_authortitle)
        duplicates = [e for e in candidates if self.eq(e, entry)]

        if not duplicates:
            logger.debug('not a duplicate')
            return self.insert_entry(entry, update_key, rename=rename, copy=copy)


        else:
            # some duplicates...
            logger.debug('duplicate(s) found: {}'.format(len(duplicates)))

            # pick only the most similar duplicate, if more than one
            # the point of check_duplicate is to avoid increasing disorder, not to clean the existing mess
            if len(duplicates) > 1:
                duplicates.sort(key=lambda e: compare_entries(entry, e), reverse=True)

            candidate = duplicates[0]

            if entry_content_equal(entry, candidate):
                logger.debug('exact duplicate')
                if mergefiles:
                    file = merge_files([candidate, entry], relative_to=self.relative_to)
                    if file and get_entry_val(candidate, 'file', '') != file:
                        candidate['file'] = file
                if rename: self.rename_entry_files(candidate, copy=copy)
                return [ candidate ]

            if update_key and get_entry_val(entry, 'ID', '') != get_entry_val(candidate, 'ID', ''):
                logger.info('duplicate :: update key to match existing entry: {} => {}'.format(get_entry_val(entry, 'ID', ''), get_entry_val(candidate, 'ID', '')))
                set_entry_key(entry, get_entry_val(candidate, 'ID', ''))
                if entry_content_equal(entry, candidate):
                    logger.debug('fixed: exact duplicate after key sync')
                    if rename: self.rename_entry_files(candidate, copy=copy)
                    return [ candidate ]

            if mergefiles:

                file = merge_files([candidate, entry], relative_to=self.relative_to)
                if len({file, get_entry_val(entry, 'file', ''), get_entry_val(candidate, 'file', '')}) > 1:
                    logger.info('duplicate :: merge files')
                    entry['file'] = candidate['file'] = file


            if entry_content_equal(entry, candidate):
                logger.debug('fixed: exact duplicate')
                if rename: self.rename_entry_files(candidate, copy=copy)
                return [ candidate ]

            logger.debug('conflict resolution: '+on_conflict)
            candidate_key_before = get_entry_val(candidate, 'ID', '')
            resolved = conflict_resolution_on_insert(candidate, entry, mode=on_conflict)
            # remove(block) uses block.key; conflict_resolution may have updated candidate.key in place (e.g. mode U).
            # Restore original key so remove() finds the right dict entry, then restore key for re-insert.
            candidate_key_after = get_entry_val(candidate, 'ID', '') if resolved and resolved[0] is candidate else None
            if hasattr(candidate, 'key'):
                candidate.key = candidate_key_before
            self.db.remove(candidate)
            if candidate_key_after is not None and hasattr(candidate, 'key'):
                candidate.key = candidate_key_after
            entries = []
            for e in resolved:
                # the existing entry keeps its key (and so does the single
                # resolved entry that carries it, e.g. an overwrite with
                # --update-key): only entries new to the library get a key
                # regenerated from the template
                keeps_key = e is candidate or (
                    len(resolved) == 1 and get_entry_val(e, 'ID', '') == candidate_key_before)
                if not keeps_key and not update_key and self.key(e) in {self.key(x) for x in self.entries}:
                    # both entries kept (append): the new one needs a free key
                    newkey = self.append_abc_to_key(e)
                    logger.info('key conflict: {} => {}'.format(get_entry_val(e, 'ID', ''), newkey))
                    set_entry_key(e, newkey)
                entries.extend( self.insert_entry(e, update_key and not keeps_key, rename=rename, copy=copy) )
            return entries


    def generate_key(self, entry):
        " generate a unique key not yet present in the record "
        keys = {self.key(e) for e in self.db.entries}
        key = self.keyformat(entry)
        if keys and key in keys: # and not isinstance(keys, set):
            key = append_abc(key, keys)
        return key

    def append_abc_to_key(self, entry):
        return append_abc(get_entry_val(entry, 'ID', ''), keys={self.key(e) for e in self.entries})


    def set_files(self, entry, files, relative_to=None):
        if relative_to is None:
            relative_to = self.relative_to
        entry['file'] = format_file(list(sorted(set(files), key=lambda f: files.index(f))), relative_to=relative_to)
        # delete field if empty
        if not entry['file'].strip():
            del entry['file']

    def get_files(self, entry, relative_to=None):
        if relative_to is None:
            relative_to = self.relative_to
        return parse_file(get_entry_val(entry, 'file', ''), relative_to=relative_to)

    def add_bibtex(self, bibtex, relative_to=None, attachments=None, convert_to_unicode=False, **kw):
        bib = parse_string(bibtex)
        if convert_to_unicode:
            bib = latex_to_unicode_library(bib)
        entries = []
        # Build index once so duplicate check is O(candidates) not O(library size) per entry
        check_dup = kw.get('check_duplicate', True)
        if check_dup and bib.entries:
            duplicate_index = _build_duplicate_index(self.entries)
        else:
            duplicate_index = None
        for e in bib.entries:
            files = []
            if "file" in e:
                # make sure paths relative to other bibtex are inserted correctly
                files.extend(self.get_files(e, relative_to))
            if attachments:
                files.extend([os.path.abspath(f) for f in attachments])
            if files:
                self.set_files(e, files)

            run_kw = dict(kw)
            if duplicate_index is not None:
                run_kw['duplicate_index'] = duplicate_index
            added = self.insert_entry(e, **run_kw)
            entries.extend(added)
            if duplicate_index is not None:
                for new_e in added:
                    _add_to_duplicate_index(new_e, duplicate_index[0], duplicate_index[1])
        return entries


    def add_bibtex_file(self, file, **kw):
        bibtex = open(file).read()
        # file links in the added bibtex are relative to its own directory
        # (the absolute path matters: dirname('papers.bib') is '')
        return self.add_bibtex(bibtex, relative_to=os.path.dirname(os.path.abspath(file)), **kw)


    def fetch_doi(self, doi, **kw):
        bibtex = fetch_bibtex_by_doi(doi)
        kw["update_key"] = True  # fetched key is always updated
        return self.add_bibtex(bibtex, **kw)


    def add_pdf(self, pdf, attachments=None, search_doi=True, search_fulltext=True, scholar=False, doi=None, **kw):

        if str(pdf).startswith("http"):
            pdf = download_url(pdf, expect_pdf=True)
            kw['rename'] = True  # always rename downloaded files

        if doi:
            bibtex = fetch_bibtex_by_doi(doi)
        else:
            bibtex = extract_pdf_metadata(pdf, search_doi, search_fulltext, scholar=scholar)
        bib = parse_string(bibtex)
        entry = bib.entries[0]

        # convert curly brackets to unicode
        lib = library_from_entries([entry])
        lib = latex_to_unicode_library(lib)
        entry = lib.entries[0]

        files = [pdf] if pdf else []
        if attachments:
            files += attachments

        self.set_files(entry, [os.path.abspath(f) for f in files])
        set_entry_key(entry, self.keyformat(entry))
        logger.debug('generated PDF key: '+entry['ID'])

        kw["update_key"] = True
        return self.insert_entry(entry, **kw)


    def scan_dir_iter(self, direc, search_doi=True, search_fulltext=True, **kw):

        for kind, path, attachments in scan_dir_items(direc):
            # a special entry directory
            if kind == 'entry':
                logger.debug('read from hidden bibtex')
                try:
                    entry = read_entry_dir(path, relative_to=self.relative_to)
                    yield from self.insert_entry(entry, **kw)
                except Exception as error:
                    logger.warning(path+'::'+str(error))
                continue

            try:
                if path.lower().endswith('.pdf'):
                    yield from self.add_pdf(path, attachments=attachments, search_doi=search_doi, search_fulltext=search_fulltext, **kw)
                elif path.lower().endswith('.bib'):
                    yield from self.add_bibtex_file(path, **kw)
            except EOFError:
                raise  # a question without answer stops the scan
            except Exception as error:
                logger.warning(path+'::'+str(error))
                continue

    def scan_dir(self, direc, **kw):
        " like scan_dir_iter but returns a list"
        return list(self.scan_dir_iter(direc, **kw))


    def format(self):
        """Return the library as a BibTeX string. Does not sort; call sort() first if you need ordered output."""
        return format_library(self.db)

    def save(self, bibtex):
        if os.path.exists(bibtex):
            shutil.copy(bibtex, backupfile(bibtex))
        if self.relative_to not in (os.path.sep, None) and Path(self.relative_to).resolve() != Path(bibtex).parent.resolve():
            logger.warning("Saving bibtex file with relative paths may break links. Consider using `Biblio.update_file_path(Path(bibtex).parent)` before.")
        self.sort()  # consistent order before writing
        s = self.format()
        open(bibtex, 'w').write(s)


    def update_file_path(self, relative_to):
        """
        relative_to: new path root:
            None: absolute path
            otherwise: different file root (the bibtex directory)
        """
        updates = []
        for e in self.entries:
            update = update_file_path(e, self.relative_to, relative_to)
            if update is not None:
                updates.append(update)
        if len(updates):
            logger.info(f"{len(updates)} entry files were updated")
        self.relative_to = relative_to



    def check_duplicates(self, key=None, eq=None, mode='i'):
        """remove duplicates, in some sensse (see papers.conflict.check_duplicates)
        """
        self.entries = check_duplicates(self.entries, key=key, eq=eq or self.eq, issorted=key is self.key, mode=mode)


    def rename_entry_files(self, e, copy=False, formatter=None, relative_to=None, hardlink=False):
        """ Rename files

        The first file is named after the entry: <filesdir>/<name>.<ext>, and
        any other file is placed next to it as <name>--<label>.<ext>, where
        <label> is the file's original name (see `attachment_names`).
        Directories of previous versions (<name>/ with a hidden .<name>.bib)
        are emptied into that layout, and removed when nothing else is left.

        See `papers.filename.Format` class and REAMDE.md for infos.
        """

        if self.filesdir is None:
            raise ValueError('filesdir is None, cannot rename entries')

        files = self.get_files(e)

        if not files:
            logger.info('no files to rename')
            return

        newname = (formatter or self.nameformat)(e)
        # absolute, to compare with the (absolute) current file paths
        target = os.path.join(os.path.abspath(self.filesdir), newname)

        count = 0
        newfiles = []
        for file, newfile in zip(files, attachment_names(files, target)):
            if not os.path.exists(file):
                logger.warning(file+': original file link is broken')
                newfile = file
            elif file != newfile:
                self.move(file, newfile, copy, hardlink=hardlink)
                count += 1
            newfiles.append(newfile)
        self.set_files(e, newfiles, relative_to=relative_to)

        if not copy:
            for direc in {os.path.dirname(file) for file in files}:
                remove_entry_dir_if_empty(direc)

        if count > 0:
            logger.info('renamed file(s): {}'.format(count))


    def rename_entries_files(self, copy=False, relative_to=None, hardlink=False):
        for e in self.db.entries:
            try:
                self.rename_entry_files(e, copy, relative_to=relative_to, hardlink=hardlink)
            except Exception as error:
                logger.error(str(error))
                continue
        if relative_to is not None:
            self.relative_to = relative_to


    def fix_entry(self, e, fix_doi=True, fetch=False, fetch_all=False,
        fix_key=False, auto_key=False, key_ascii=False, encoding=None,
        format_name=True, interactive=False):
        """
        Given an entry in an existing Bilio object, checks the format name and encoding.  Will fetch additional info if it's missing.
        """

        e_old = entry_copy(e)

        if format_name:
            for k in ['author','editor']:
                if k in e:
                    e[k] = standard_name(e[k])
                    if e[k] != e_old[k]:
                        logger.info(get_entry_val(e, 'ID', '')+': '+k+' name formatted')

        if encoding:

            assert encoding in ['unicode','latex'], get_entry_val(e, 'ID', '')+': unknown encoding: '+repr(encoding)

            logger.debug(get_entry_val(e, 'ID', '')+': update encoding')
            if encoding == "unicode":
                convert_entry_to_unicode(e)
            else:
                for k in e:
                    if k == k.lower() and k != 'abstract': # all but ENTRYTYPE, ID, abstract
                        try:
                            if encoding == 'unicode':
                                e[k] = latex_to_unicode(e[k])
                            elif encoding == 'latex':
                                e[k] = unicode_to_latex(e[k])
                        # except KeyError as error:
                        except (KeyError, ValueError) as error:
                            logger.warning(get_entry_val(e, 'ID', '')+': '+k+': failed to encode: '+str(error))

        if fix_doi:
            if 'doi' in e and e['doi']:
                try:
                    doi = parse_doi('doi:'+e['doi'])
                except:
                    logger.warning(get_entry_val(e, 'ID', '')+': failed to fix doi: '+e['doi'])
                    return

                if doi.lower() != e['doi'].lower():
                    logger.info(get_entry_val(e, 'ID', '')+': fix doi: {} ==> {}'.format(e['doi'], doi))
                    e['doi'] = doi
                else:
                    logger.debug(get_entry_val(e, 'ID', '')+': doi OK')
            else:
                logger.debug(get_entry_val(e, 'ID', '')+': no DOI')


        if fetch or fetch_all:
            bibtex = None
            if 'doi' in e and e['doi']:
                logger.info(get_entry_val(e, 'ID', '')+': fetch doi: '+e['doi'])
                try:
                    bibtex = fetch_bibtex_by_doi(e['doi'])
                except Exception as error:
                    logger.warning('...failed to fetch bibtex (doi): '+str(error))

            elif get_entry_val(e, 'title', '') and get_entry_val(e, 'author', '') and fetch_all:
                kw = {}
                kw['title'] = e['title']
                kw['author'] = ' '.join(family_names(e['author']))
                logger.info(get_entry_val(e, 'ID', '')+': fetch-all: '+str(kw))
                try:
                    bibtex = fetch_bibtex_by_fulltext_crossref('', **kw)
                except Exception as error:
                    logger.warning('...failed to fetch/update bibtex (all): '+str(error))

            if bibtex:
                db = parse_string(bibtex)
                e2 = db.entries[0]
                self.fix_entry(e2, encoding=encoding, format_name=True)
                strip_e = lambda e_: {k: e_[k] for k, _ in e_.items() if k not in ['ID', 'file'] and k in e2}
                if strip_e(e) != strip_e(e2):
                    logger.info('...fetch-update entry')
                    for k, v in strip_e(e2).items():
                        e[k] = v
                else:
                    logger.info('...fetch-update: already up to date')


        if fix_key or auto_key:
            if auto_key or not isvalidkey(get_entry_val(e, 'ID','')):
                key = self.generate_key(e)
                if get_entry_val(e, 'ID', '') != key:
                    logger.info('update key {} => {}'.format(get_entry_val(e, 'ID', ''), key))
                    set_entry_key(e, key)

        if key_ascii:
            set_entry_key(e, unicode_to_ascii(get_entry_val(e, 'ID', '')))

        if interactive and not entry_content_equal(e_old, e):
            print(bcolors.OKBLUE+'*** UPDATE ***'+bcolors.ENDC)
            print(entry_diff(e_old, e))

            if input('update? [Y/n] ').lower() not in ('', 'y'):
                logger.info('cancel changes')
                update_entry(e, e_old)
                for k in [k for k, _ in e.items()]:
                    if k not in e_old:
                        del e[k]


def get_biblio(config):
    """
    This function initializes a Biblio object based on the bibtex file specified as command line argument or in config file.
    If no bibtex file is specified, it raises a ValueError().
    """
    if config.bibtex is None:
        raise ValueError('bibtex is not initialized')
    relative_to = os.path.sep if config.absolute_paths else (os.path.dirname(config.bibtex) if config.bibtex else None)
    if config.bibtex and os.path.exists(config.bibtex):
        biblio = Biblio.load(config.bibtex, config.filesdir, nameformat=config.nameformat, keyformat=config.keyformat)
        if biblio.relative_to != relative_to:
            biblio.update_file_path(relative_to)
    else:
        biblio = Biblio.newbib(config.bibtex, config.filesdir, relative_to=relative_to, nameformat=config.nameformat, keyformat=config.keyformat)
    return biblio


def isvalidkey(key):
    return key and not key[0].isdigit()


def entry_filecheck_metadata(e, file, image=False):
    ''' parse pdf metadata and compare with entry: only doi for now
    '''
    if 'doi' not in e:
        raise ValueError(get_entry_val(e, 'ID', '')+': no doi, skip PDF parsing')

    try:
        doi = extract_pdf_doi(file, image=image)
    except Exception as error:
        raise ValueError(get_entry_val(e, 'ID', '')+': failed to parse doi: "{}"'.format(file))
    if not isvaliddoi(doi):
        raise ValueError(get_entry_val(e, 'ID', '')+': invalid parsed doi: '+doi)

    if doi.lower() != e['doi'].lower():
        raise ValueError(get_entry_val(e, 'ID', '')+': doi: entry <=> pdf : {} <=> {}'.format(e['doi'].lower(), doi.lower()))


def entry_filecheck(e, delete_broken=False, fix_mendeley=False,
    check_hash=False, check_metadata=False, interactive=True, image=False, relative_to=None):
    """
    Checks the bib entry file actually corresponds to an existing, correct file on disk.
    """

    if 'file' not in e:
        return

    if check_hash:
        import hashlib

    newfiles = []
    hashes = set()
    realpaths = set()
    fixed = {}

    for i, file in enumerate(parse_file(e['file'], relative_to=relative_to)):

        realpath = os.path.realpath(file)
        if realpath in realpaths:
            logger.info(get_entry_val(e, 'ID', '')+': remove duplicate path: "{}"'.format(fixed.get(file, file)))
            continue
        realpaths.add(realpath) # put here so that for identical
                                   # files that are checked and finally not
                                   # included, the work is done only once

        if fix_mendeley and not os.path.exists(file):
            old = file

            # replace any "{\_}" with "_"
            try:
                file = latex_to_unicode(file)
            except KeyError as error:
                logger.warning(get_entry_val(e, 'ID', '')+': '+str(error)+': failed to convert latex symbols to unicode: '+file)

            # fix root (e.g. path starts with home instead of /home)
            dirname = os.path.dirname(file)
            candidate = os.path.sep + file
            if (not file.startswith(os.path.sep) and dirname # only apply when some directory name is specified
                and not os.path.exists(dirname)
                and os.path.exists(os.path.dirname(candidate))): # simply requires that '/'+directory exists
                # and os.path.exists(newfile)):
                    # logger.info('prepend "/" to file name: "{}"'.format(file))
                    file = candidate

            if old != file:
                logger.info(get_entry_val(e, 'ID', '')+': file name fixed: "{}" => "{}".'.format(old, file))
                fixed[old] = file # keep record of fixed files

        # parse PDF and check for metadata
        if check_metadata and file.lower().endswith('.pdf'):
            try:
                entry_filecheck_metadata(e, file, image=image)
            except ValueError as error:
                logger.warning(error)

        # check existence
        if not os.path.exists(file):
            logger.warning(get_entry_val(e, 'ID', '')+': "{}" does not exist'.format(file)+delete_broken*' ==> delete')
            if delete_broken:
                logger.info('delete file from entry: "{}"'.format(file))
                continue
            elif interactive:
                ans = input('delete file from entry ? [Y/n] ')
                if ans.lower() == 'y':
                    continue

        elif check_hash:
            # hash_ = hashlib.sha256(open(file, 'rb').read()).digest()
            hash_ = checksum(file) # a little faster
            if hash_ in hashes:
                logger.info(get_entry_val(e, 'ID', '')+': file already exists (identical checksum): "{}"'.format(file))
                continue
            hashes.add(hash_)

        newfiles.append(file)

    e['file'] = format_file(newfiles, relative_to=relative_to)


def clean_filesdir(biblio, interactive=True, ignore_files=None, ignore_folders=None):
    if biblio.filesdir is None:
        raise ValueError('filesdir is not defined, cannot clean')
    removed_files = []

    allfiles = set(os.path.abspath(file) for e in biblio.entries for file in biblio.get_files(e))
    if ignore_files:
        for f in ignore_files:
            allfiles.add(os.path.abspath(f))
    allfolders = set(os.path.abspath(folder) for e in biblio.entries for folder in {os.path.dirname(file) for file in biblio.get_files(e)})

    if ignore_folders is None:
        ignore_folders = []

    for root, direcs, files in os.walk(biblio.filesdir):

        ANS = None  # Y(es) or N(o) for all files in this folder (reset at each pass)
        if root in ignore_folders:
            continue
        if '.git' in root.split(os.path.sep):
            continue
        for file in files:
            path = os.path.abspath(os.path.join(root, file))
            if file.startswith('.') or file.endswith('.bib'):
                continue
            if path not in allfiles:
                if interactive:
                    if ANS is None:
                        ans = input(f"File: {os.path.relpath(path, biblio.filesdir)} not in library. Remove ? [Y/n/Y/N] ")
                    else:
                        ans = ANS
                    if ans in ['Y', 'N']:
                        ans = ANS = ans.lower()  # same reply for all files in this folder
                    if ans.lower() == 'y':
                        os.remove(path)
                        removed_files.append(path)
                else:
                    logger.info(f"Remove unlinked file {os.path.relpath(path, biblio.filesdir)}.")
                    os.remove(path)
                    removed_files.append(path)

        for direc in direcs:
            if direc.startswith('.'):
                continue
            if direc in ignore_folders:
                continue

            # Check multifile entries
            bibtex = os.path.join(root, direc, '.'+direc+'.bib')
            if not os.path.exists(bibtex):
                continue

            direcpath = os.path.abspath(os.path.join(root, direc))

            if direcpath not in allfolders:
                if interactive:
                    ans = input(f"Folder: {os.path.relpath(direcpath, root)} not in library. Remove ? [Y/n] ")
                    if ans.lower() == 'y':
                        shutil.rmtree(os.path.join(root, direcpath))
                else:
                    logger.info(f"Remove folder {direc}.")
                    shutil.rmtree(os.path.join(root, direcpath))

        break

    return removed_files
