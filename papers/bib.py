import difflib
import os
import re
from collections import Counter
from pathlib import Path
import shutil
from papers.ascii import to_ascii as unicode_to_ascii
from bibtexparser import Library
from bibtexparser.model import Entry, Field

from papers.entries import (
    get_entry_val,
    set_entry_key,
    update_entry,
    entry_copy,
    entry_content_equal,
    parse_string,
    format_library,
    sort_blocks,
    library_from_entries,
    parse_file,
    format_file,
    update_file_path,
)
from papers.encoding import (
    latex_to_unicode_library,
    convert_entry_to_unicode,
)

import papers
from papers import logger

from papers.extract import parse_doi
from papers.extract import (extract_pdf_metadata, parse_doi_from_pdf_metadata, parse_dois, pdfhead, pdftail,
                            title_in_text)
from papers.fetch import fetch_bibtex_by_fulltext_crossref, fetch_bibtex_by_doi
from papers.identifiers import DIGITS

from papers.encoding import standard_name, family_names, format_entries
from papers.latexenc import string_to_latex

from papers.filename import NAMEFORMAT, KEYFORMAT, fallback_key
from papers.files import (download_url, read_entry_dir, attachment_names, free_name, remove_entry_dir_if_empty,
                          realpath, scan_dir_items, is_download)
from papers import journal
from papers.utils import bcolors, checksum, move as _move, write_atomic, PapersExit
import papers.config

from papers.duplicate import (
    SAME,
    Distinct,
    IdentityIndex,
    find_duplicates,
    duplicate_groups,
    same_paper,
    search_result_mismatch,
)
from papers.merge import Merge, Resolver, Decision, DuplicateError, apply_entry, option_hint


# the fields of `add --key` and `--type` in the metadata of insert_entry
METADATA_NAMES = {'ID': 'key', 'ENTRYTYPE': 'type'}

# the fields that check --encoding latex leaves as they are
LATEX_SKIP = {'abstract', 'file', 'doi', 'url', 'eprint', 'isbn', 'issn', 'ids'}


def entry_diff(e_old, e, color=True):
    "line diff of two entries, as bibtex"
    lines = difflib.ndiff(format_entries([e_old]).splitlines(1), format_entries([e]).splitlines(1))
    diff = ''.join(lines)
    if not color:
        return diff
    colors = {'+': bcolors.OKGREEN, '-': bcolors.FAIL, '?': bcolors.WARNING}
    return '\n'.join(colors[line[0]] + line + bcolors.ENDC if line[:1] in colors else line
                     for line in diff.splitlines())

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
    >>> append_abc('Author2000B')
    'Author2000C'
    >>> append_abc('Author2000z')
    'Author2000za'
    """
    alphabet = 'abcdefghijklmnopqrstuvwxyz'
    keys = {k.lower() for k in keys}  # keys are compared ignoring case

    # a letter after a digit is a suffix of this function (Author2000b), in
    # either case
    last = key[-1:]
    if len(key) > 1 and last.lower() in alphabet and key[-2] in DIGITS:
        letters = alphabet[alphabet.index(last.lower())+1:]
        if last.isupper():
            letters = letters.upper()
        base = key[:-1]
    else:
        letters = alphabet[1:] # start at b
        base = key

    # no letter left (after z): a second letter (Author2000za)
    for k in [base + l for l in letters] + [key + l for l in alphabet]:
        if k.lower() not in keys:
            return k
    raise ValueError(f'{key}: no free key with a letter suffix')


def _same_content(file, files):
    "the first of `files` with the content of `file` (same size, then same checksum), or None"
    try:
        size = os.path.getsize(file)
    except OSError:
        return None
    for f in files:
        if os.path.isfile(f) and os.path.getsize(f) == size and checksum(f) == checksum(file):
            return f
    return None


def read_text(file):
    """the content of a text file (UTF-8, as `write_atomic` writes it; without the byte order mark
    that some editors write first), or None if it cannot be read"""
    try:
        with open(file, encoding='utf-8-sig') as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None

def parse_cache():
    "the cache of the parsed bibtex (see papers.parsecache), in the cache folder of the machine"
    from papers.parsecache import Cache
    return Cache(os.path.join(papers.config.CACHE_DIR, 'parsed'))


class BibtexChanged(PapersExit):
    "the bibtex was written by another program since papers read it"


class DuplicateKeyError(PapersExit):
    "a new entry has the key of another paper of the library"

def unreadable_blocks(db):
    """the entries of a parsed bibtex that bibtexparser could not read (a
    field given twice, a syntax error): [(line, reason)]. Their text is
    written back as it is, but papers does not see them."""
    found = []
    for block in getattr(db, 'failed_blocks', []):
        if type(block).__name__ == 'DuplicateFieldKeyBlock':
            reason = str(block.error).split('. Note')[0].replace('Duplicate field keys on entry', 'a field given twice')
        elif type(block).__name__ == 'DuplicateBlockKeyBlock':
            reason = f"a key given twice (keys ignore case): '{block.key}'"
        else:
            reason = 'syntax error'
        found.append(((block.start_line or 0) + 1, reason))
    return found


def unreadable_message(bibtex, unreadable, outcome='papers ignores them until they are fixed'):
    lines = '; '.join(f'line {line}: {reason}' for line, reason in unreadable)
    n = len(unreadable)
    home = os.path.expanduser('~')
    if bibtex.startswith(home + os.sep):
        bibtex = '~' + bibtex[len(home):]
    return (f'{bibtex}: {n} entr{"ies" if n > 1 else "y"} could not be read ({lines}): '
            + outcome)


class Biblio:
    """
    The bibtex object that we operate on, which is mainly used to read and write to dynamically, and can then send the changes to be stored in a specified bibtex file on disk.
    """
    def __init__(self, db=None, filesdir=None, nameformat=NAMEFORMAT, keyformat=KEYFORMAT, relative_to=None, distinct=None):
        """
        relative_to : bibtex directory, optional
            use relative paths instead of absolute path
        """
        self.filesdir = filesdir
        if db is None:
            db = Library()
        elif not isinstance(db, Library):
            raise TypeError('db must be of type Library')
        self.db = db
        self.nameformat = nameformat
        self.keyformat = keyformat
        # pairs of entries that are not the same paper (see papers.duplicate.Distinct)
        self.distinct = distinct if distinct is not None else Distinct()
        self.relative_to = os.path.sep if relative_to is None else relative_to
        # `add` looks in the pool first (see papers.pools.PoolLookup)
        self.pool_lookup = None
        # the entries as loaded (see mark_loaded, changed_entries)
        self.loaded_entries = None
        self.loaded_keys = ()
        self._loaded = None
        # {new path: (original path, 'moved' or 'copied')}: the files placed by the command, for its report
        self.placed = {}
        # the library entries that duplicates skipped by insert_entry were of: considered by the command
        self.skipped = []

    def move(self, file, newfile, copy=False, hardlink=False):
        result = _move(file, newfile, copy=copy, dryrun=papers.config.DRYRUN, hardlink=hardlink)
        if not papers.config.DRYRUN and os.path.realpath(file) != os.path.realpath(newfile):
            source, _ = self.placed.pop(file, (file, None))  # a file placed twice: from where it was
            self.placed[newfile] = (source, 'copied' if copy else 'moved')
            if not is_download(file):  # a download is not put back into its temporary folder
                journal.record('copied' if copy else 'moved', file, newfile)
        return result

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

    unreadable = ()  # [(line, reason)] of the entries of the bibtex that could not be read
    read_state = None  # (path, size and modification time, text) of the bibtex as read or last written

    def _remember(self, bibtex, text):
        path = os.path.realpath(bibtex)
        st = os.stat(path)
        self.read_state = (path, (st.st_size, st.st_mtime_ns), text)

    def _current_text(self, bibtex):
        """the text of `bibtex` on disk; raise BibtexChanged if it is not the
        text that this library read or last wrote (another program wrote it
        since). The text is read only when its size or modification time
        changed."""
        path = os.path.realpath(bibtex)
        if self.read_state is None or self.read_state[0] != path:
            return read_text(bibtex)
        st = os.stat(path)
        if (st.st_size, st.st_mtime_ns) == self.read_state[1]:
            return self.read_state[2]
        text = read_text(bibtex)
        if text != self.read_state[2]:
            raise BibtexChanged(f'{bibtex} changed since papers read it (another program wrote it meanwhile): '
                                'papers did not write it, and put back the files that the command moved, '
                                'copied or deleted. Run the command again.')
        return text

    @classmethod
    def load(cls, bibtex, filesdir, relative_to=None, **kw):
        with open(bibtex, encoding='utf-8-sig') as f:  # UTF-8, without a byte order mark (see read_text)
            bibtexs = f.read()
        if 'distinct' not in kw:  # not read twice (a warning of an unreadable file twice)
            kw['distinct'] = Distinct.for_library(papers.config.library_dir(bibtex))
        db = parse_string(bibtexs, cache=parse_cache())
        loaded_bib = cls(db, filesdir, relative_to=relative_to if relative_to is not None else os.path.dirname(bibtex), **kw)
        loaded_bib._remember(bibtex, bibtexs)
        loaded_bib.unreadable = unreadable_blocks(db)
        if loaded_bib.unreadable:
            logger.warning(unreadable_message(bibtex, loaded_bib.unreadable))
        return loaded_bib

    @classmethod
    def newbib(cls, bibtex, filesdir, relative_to=None, **kw):
        assert not os.path.exists(bibtex)
        if os.path.dirname(bibtex) and not os.path.exists(os.path.dirname(bibtex)):
            os.makedirs(os.path.dirname(bibtex))
        write_atomic(bibtex, '')
        return cls.load(bibtex, filesdir, relative_to=relative_to, **kw)

    def key(self, e):
        return e['ID'].lower()

    @staticmethod
    def _state(e):
        return e.entry_type.lower(), sorted((f.key, str(f.value)) for f in e.fields)

    def mark_loaded(self):
        """remember the entries as they are now (as loaded), for
        changed_entries and the report of the changes of a command
        (loaded_entries: copies of the entries; loaded_relative_to)"""
        self.loaded_entries = [entry_copy(e) for e in self.entries]
        self.loaded_keys = [(e, e.key) for e in self.entries]  # the entries themselves, for renamed_keys
        self.loaded_relative_to = self.relative_to
        self._loaded = None

    def renamed_keys(self):
        """[(old, new)]: the entries whose key changed since mark_loaded (the
        same entry; its old key no longer in the library, its new key not in
        it when loaded: not a merge; or a change of case only, the key being
        that of no other entry), [] without mark_loaded"""
        if self.loaded_entries is None:
            return []
        now = Counter(e.key.lower() for e in self.entries)
        before = Counter(key.lower() for _, key in self.loaded_keys)
        present = {id(e) for e in self.entries}

        def renamed(e, old):
            if e.key.lower() == old.lower():
                return e.key != old and now[old.lower()] == before[old.lower()] == 1
            return old.lower() not in now and e.key.lower() not in before
        return [(old, e.key) for e, old in self.loaded_keys if id(e) in present and renamed(e, old)]

    def rekey_references(self, old, new):
        "the crossref fields of the entries that name `old` (a key that changed to `new`)"
        for e in self.entries:
            if get_entry_val(e, 'crossref', '').lower() == old.lower():
                e['crossref'] = new

    def set_key(self, e, new, keep_old=False):
        """change the key of entry `e` to `new` (with keep_old, its former key
        goes to its ids field, where papers and biblatex still find it); the
        records of the exchanges with pools follow when the library is saved
        (see papers.library.savebib)"""
        if not isvalidkey(new) or _KEY_FORBIDDEN.search(new):
            raise PapersExit(f'{new!r} is not a valid key (no spaces, commas, braces, quotes, or #%~=()\\; '
                             'not starting with a digit)')
        if any(x is not e and x.key.lower() == new.lower() for x in self.entries):
            raise PapersExit(f'{new}: another entry of the library has this key')
        old = e.key
        set_entry_key(e, new)
        # ids: never the key itself, and each former key once
        ids = [i.strip() for i in get_entry_val(e, 'ids', '').split(',') if i.strip()]
        kept = [i for i in ids if i.lower() != new.lower()]
        if keep_old and old.lower() not in {i.lower() for i in kept} | {new.lower()}:
            kept.append(old)
        if kept != ids:
            if kept:
                e['ids'] = ', '.join(kept)
            else:
                del e['ids']

    @property
    def loaded(self):
        "{lower-case key: state} of the entries as loaded (see mark_loaded), or None"
        if self.loaded_entries is None:
            return None
        if self._loaded is None:
            self._loaded = {self.key(e): self._state(e) for e in self.loaded_entries}
        return self._loaded

    def changed_entries(self):
        """(new, modified): the entries added since mark_loaded (neither their
        key nor a former key of their ids field was there), and those that
        changed (an entry whose key changed and that has its former key in
        ids is modified). Removed entries are in neither. Without
        mark_loaded, nothing changed."""
        if self.loaded is None:
            return [], []
        new, modified = [], []
        renamed = self._renamed_map()
        for e in self.entries:
            state = self._loaded_state(e, renamed)
            if state is None:
                new.append(e)
            elif state != self._state(e):
                modified.append(e)
        return new, modified

    def _renamed_map(self):
        "{lower-case new key: lower-case old key} of renamed_keys"
        return {new.lower(): old.lower() for old, new in self.renamed_keys()}

    def _loaded_state(self, e, renamed):
        """the state of an entry as loaded: by its key, a key it had before
        in the command (`renamed`, see _renamed_map), or a former key of its
        ids field; None for an entry new since mark_loaded"""
        former = [k.strip().lower() for k in get_entry_val(e, 'ids', '').split(',')]
        keys = [self.key(e), renamed.get(self.key(e))] + former
        return next((self.loaded[k] for k in keys if k in self.loaded), None)

    # what changed when the library was loaded, before mark_loaded (file links
    # converted to the `paths` setting, links to pool files repaired): saved
    # even if the command changes nothing
    load_changes = False

    def unchanged(self):
        """True if the entries are as loaded (see mark_loaded: the same
        keys, types and fields), nothing changed at load (load_changes) and
        no pair was added to distinct; False without mark_loaded"""
        if self.loaded_entries is None or self.load_changes or self.distinct.changed:
            return False
        if len(self.loaded_entries) != len(self.db.entries):
            return False
        exact = lambda e: (e.entry_type, e.key, tuple(sorted((f.key, str(f.value)) for f in e.fields)))
        return Counter(map(exact, self.loaded_entries)) == Counter(map(exact, self.db.entries))

    def loaded_files(self, e):
        """the files of an entry as loaded (see mark_loaded): [] for an entry
        new since, None without mark_loaded"""
        if self.loaded is None:
            return None
        state = self._loaded_state(e, self._renamed_map())
        value = next((v for k, v in state[1] if k == 'file'), '') if state is not None else ''
        return parse_file(value, relative_to=self.relative_to)


    def sort(self):
        """Re-order the library by block type and entry key (see
        papers.entries.sort_blocks): the entries stay the same objects"""
        self.db = sort_blocks(self.db)

    def insert_entry(self, entry, update_key=False, check_duplicate=False, rename=False, copy=False, metadata={},
                     on_duplicate='error', duplicate_index=None):
        """insert an entry, and return the entries of the library it ended in
        (none when a duplicate was skipped).

        update_key: give the entry a key from the key template (entries new
            to the library only: a duplicate keeps the key of the library)
        check_duplicate: look for the same paper in the library (see
            papers.duplicate.same_paper), and merge or not as `on_duplicate`
            says: one of ask, keep, update, skip, error, or a Resolver
        duplicate_index: an IdentityIndex of the library, kept up to date
        metadata: fields given on the command line (`add --title...`), as a
            dict: they replace the fields of the entry, the files of its
            `file` field are added to the entry's, and an `ID` sets the key
            (which update_key then leaves as it is)
        """
        if metadata:
            self.apply_metadata(entry, metadata)
            if 'ID' in metadata:
                update_key = False

        if check_duplicate:
            resolver = on_duplicate if isinstance(on_duplicate, Resolver) else Resolver(on_duplicate)
            return self._insert_entry_check(entry, resolver, update_key=update_key, rename=rename, copy=copy,
                                            index=duplicate_index)

        return self._insert_new(entry, update_key=update_key, rename=rename, copy=copy, index=duplicate_index)

    def apply_metadata(self, entry, metadata):
        """set the fields of `metadata` (a dict, see insert_entry) in the
        entry; the files of its `file` field are added to the entry's"""
        fields = {k: v for k, v in metadata.items() if k != 'file'}
        update_entry(entry, fields)
        files = self.get_files(entry) + self.get_files(metadata)
        if files:
            self.set_files(entry, files)

    def _insert_new(self, entry, update_key=False, rename=False, copy=False, index=None, free_key=False):
        "insert an entry new to the library"
        if update_key or not self.key(entry):
            set_entry_key(entry, self.generate_key(entry, new=True))

        # Key duplicate check: lookup by key (public API), case-insensitive to match entries_dict keys
        key_lower = self.key(entry)
        existing_same_key = next(
            (e for k, e in self.db.entries_dict.items() if k.lower() == key_lower),
            None,
        )
        if existing_same_key is not None:
            logger.debug('key duplicate: '+self.key(existing_same_key))

            if free_key:
                newkey = self.append_abc_to_key(entry)
                logger.info('key conflict: {} => {}'.format(get_entry_val(entry, 'ID', ''), newkey))
                set_entry_key(entry, newkey)

            elif same_paper(existing_same_key, entry, self.distinct).kind == SAME \
                    and Merge([existing_same_key, entry], relative_to=self.relative_to).is_exact():
                # the same paper with nothing to decide, as for "already in library" (equivalent
                # values, such as titles that differ only by case or braces, are no difference)
                logger.info('exact duplicate')
                # keep the files of the new entry
                files = self.get_files(existing_same_key) + self.get_files(entry)
                if files:
                    self.set_files(existing_same_key, files)
                if rename: self.rename_entry_files(existing_same_key, copy=copy)
                return [ existing_same_key ]

            else:  # (with update_key, the key generated above is not in the library)
                raise DuplicateKeyError(f'{get_entry_val(entry, "ID", "")}: this key is already in the library, '
                                        'for another paper or another version of it: pass -u/--update-key to generate a new key, '
                                        'or --key KEY')

        else:
            logger.info('new entry: '+self.key(entry))

        self.db.add(entry)
        if index is not None:
            index.add(entry)

        if rename: self.rename_entry_files(entry, copy=copy)

        return [ entry ]

    def _insert_entry_check(self, entry, resolver, update_key=False, rename=False, copy=False, index=None):
        # the index (see add_entries) has the entries of the library, in their order
        found = find_duplicates(entry, self.entries if index is None else None, self.distinct, index=index)
        if not found:
            logger.debug('not a duplicate')
            return self._insert_new(entry, update_key=update_key, rename=rename, copy=copy, index=index)

        existing, verdict = found[0]
        logger.debug(f'duplicate of {get_entry_val(existing, "ID", "")}: {verdict.reason}')
        merge = Merge([existing, entry], relative_to=self.relative_to)

        if verdict.kind == SAME and merge.is_exact():
            decision = Decision('merge', merge, merge.result())
            if not merge.new_files:  # otherwise the entry is reported Modified, with its new files
                print(f'already in library: {merge.key}')
        else:
            decision = resolver.decide(merge, 'add', verdict)

        if decision.kind == 'merge':
            if index is not None:
                index.remove(existing)
            apply_entry(existing, decision.entry)
            if index is not None:
                index.add(existing)
            if rename: self.rename_entry_files(existing, copy=copy)
            return [ existing ]

        if decision.kind == 'distinct':
            self.distinct.add(existing, entry)
            return self._insert_new(entry, update_key=update_key, rename=rename, copy=copy, index=index, free_key=True)

        print(f'skipped: {get_entry_val(entry, "ID", "")} (already in library: {merge.key})')
        self.skipped.append(existing)
        return []


    def generate_key(self, entry, new=False):
        """the key of the key template for the entry, with a letter suffix if
        another entry of the library has it (the entry's own key is not taken).
        An empty key from the template: empty (a renamed entry keeps its key),
        or for a `new` entry the key of fallback_key"""
        keys = {self.key(e) for e in self.db.entries if e is not entry}
        key = self.keyformat(entry)
        if not key and not new:
            return key
        if not key:
            key = fallback_key(entry)
        if key.lower() in keys:
            key = append_abc(key, keys)
        return key

    def append_abc_to_key(self, entry):
        return append_abc(get_entry_val(entry, 'ID', ''), keys={self.key(e) for e in self.entries})


    def set_files(self, entry, files, relative_to=None):
        if relative_to is None:
            relative_to = self.relative_to
        unique, seen = [], set()
        for f in files:  # a repeat: the same file, however written (files/./a.pdf, files/a.pdf)
            path = os.path.normpath(os.path.join(relative_to or '', f))
            if path not in seen:
                seen.add(path)
                unique.append(f)
        entry['file'] = format_file(unique, relative_to=relative_to)
        # delete field if empty
        if not entry['file'].strip():
            del entry['file']

    def get_files(self, entry, relative_to=None):
        if relative_to is None:
            relative_to = self.relative_to
        return parse_file(get_entry_val(entry, 'file', ''), relative_to=relative_to)

    def add_bibtex(self, bibtex, relative_to=None, attachments=None, convert_to_unicode=False, **kw):
        bib = parse_string(bibtex)
        unreadable = unreadable_blocks(bib)
        if unreadable:
            logger.warning(unreadable_message('the added bibtex', unreadable, 'they are not added'))
        if convert_to_unicode:
            bib = latex_to_unicode_library(bib)
        return self.add_entries(bib.entries, relative_to=relative_to, attachments=attachments, **kw)

    def add_entries(self, added, relative_to=None, attachments=None, what='bibtex', **kw):
        """add entries read from a file (bibtex, RIS, CSL-JSON...): their file
        links are relative to `relative_to`; an entry without key gets one from
        the key template"""
        fields = [k for k in kw.get('metadata') or {} if k != 'file']
        if fields and len(added) > 1:
            raise ValueError(f'the {what} has {len(added)} entries: the fields given on the command line '
                             '(--title, --key, --metadata...) apply to one entry only')
        entries = []
        # one index for all entries, so that the duplicate search compares an
        # entry with the entries that share an identifier only
        if kw.get('check_duplicate') and kw.get('duplicate_index') is None and added:
            kw['duplicate_index'] = IdentityIndex(self.entries)
        for e in added:
            if not e.key:
                set_entry_key(e, self.generate_key(e, new=True))
            files = []
            if "file" in e:
                # make sure paths relative to other bibtex are inserted correctly
                files.extend(self.get_files(e, relative_to))
            if attachments:
                files.extend([os.path.abspath(f) for f in attachments])
            if files:
                self.set_files(e, files)

            taken = self.pool_lookup.entry(self, e) if self.pool_lookup else None
            if taken is not None:
                entries.extend(self._insert_taken(taken, **kw))
            else:
                entries.extend(self.insert_entry(e, **kw))
        return entries

    def _insert_taken(self, entry, **kw):
        "insert an entry taken from a pool, and record its origin"
        result = self.insert_entry(entry, **kw)
        self.pool_lookup.inserted(entry, result, self, rename=kw.get('rename', False), copy=kw.get('copy', False))
        return result


    def add_bibtex_file(self, file, **kw):
        with open(file, encoding='utf-8-sig') as f:
            bibtex = f.read()
        # file links in the added bibtex are relative to its own directory
        # (the absolute path matters: dirname('papers.bib') is '')
        return self.add_bibtex(bibtex, relative_to=os.path.dirname(os.path.abspath(file)), **kw)

    def add_file_of_format(self, file, fmt, **kw):
        "add the entries of a RIS, CSL-JSON or BibJSON file (see papers.formats)"
        from papers.formats import LABELS, read_file
        return self.add_entries(read_file(file, fmt), relative_to=os.path.dirname(os.path.abspath(file)),
                                what=f'{LABELS[fmt]} file', **kw)


    def find_doi(self, doi):
        "the library entry that is the same paper as an entry of DOI `doi` (an arXiv DOI matches the eprint), or None"
        found = find_duplicates(Entry('misc', 'doi', [Field('doi', doi)]), self.entries, self.distinct)
        return next((e for e, verdict in found if verdict.kind == SAME), None)

    def find_pdf(self, pdf):
        """the library entry of the DOI of a PDF, or None, without network
        query: the DOI of the PDF metadata, else a DOI of the text whose
        library entry has its title in the text"""
        try:
            doi = parse_doi_from_pdf_metadata(pdf)
            if doi:
                return self.find_doi(doi)
            txt = pdfhead(pdf)
            candidates = parse_dois(txt, pdftail(pdf))
        except Exception as error:
            logger.debug(f'{pdf}: {error}')
            return None
        for candidate in candidates:
            e = self.find_doi(candidate)
            if e is not None and title_in_text(get_entry_val(e, 'title', ''), txt):
                return e
        return None

    def attach_to_existing(self, e, files, rename=False, copy=False, **kw):
        """`add` of the files of a paper that the library has (same DOI): the
        files are added to the entry and placed as `file attach` does, the
        entry's fields and other files are not touched (nor by the fields of
        `metadata`, given on the command line: `papers edit` changes them).
        Return [e]."""
        ignored = [k for k in kw.get('metadata') or {} if k not in ('file', 'doi')]
        if ignored:
            names = ', '.join(METADATA_NAMES.get(k, k) for k in ignored)
            logger.warning(f'{e.key} is already in the library: its fields are not changed '
                           f'(ignored: {names}; use `papers edit {e.key}`)')
        old = self.get_files(e)
        known = {realpath(f) for f in old}
        new = [os.path.abspath(f) for f in files if realpath(f) not in known]
        # a file with the content of a file of the entry is not attached again
        same = {f: _same_content(f, old) for f in new}
        new = [f for f in new if same[f] is None]
        if not new:  # otherwise the entry is reported Modified, with its new files
            print(f'already in library: {e.key}')
        for f, other in same.items():
            if other is not None:
                print(f'{f}: not attached, the entry has the same file: {other}')
        if not new:
            return [e]
        self.set_files(e, old + new)
        if rename:
            if callable(copy):
                policy = lambda f: 'link' if realpath(f) in known else copy(f)
            else:
                policy = lambda f: 'link' if realpath(f) in known else ('copy' if copy else 'move')
            self.rename_entry_files(e, copy=policy)
        return [e]

    def fetch_doi(self, doi, **kw):
        attachments = [os.path.abspath(f) for f in kw.get('attachments') or []]
        existing = self.find_doi(doi) if kw.get('check_duplicate') else None
        if existing is not None:
            return self.attach_to_existing(existing, attachments, **kw)
        taken =self.pool_lookup.doi(self, doi, attachments) if self.pool_lookup else None
        if taken is not None:
            kw.pop('attachments', None)
            kw["update_key"] = True
            return self._insert_taken(taken, **kw)
        bibtex = fetch_bibtex_by_doi(doi)
        kw["update_key"] = True  # fetched key is always updated
        return self.add_bibtex(bibtex, **kw)


    def add_key(self, key, **kw):
        """`add --key KEY` alone: the library entry of key KEY (ignoring
        case) gets the attachments, else the pool entry of key KEY is
        taken. Return the entries, or None if no pool has the key."""
        attachments = [os.path.abspath(f) for f in kw.pop('attachments', None) or []]
        # the key of the library or pool entry is kept as it is written there
        kw['metadata'] = {k: v for k, v in (kw.get('metadata') or {}).items() if k != 'ID'}
        existing = next((e for e in self.entries if self.key(e) == key.lower()), None)
        if existing is not None:
            return self.attach_to_existing(existing, attachments, **kw)
        taken = self.pool_lookup.key(self, key, attachments) if self.pool_lookup else None
        if taken is None:
            return None
        return self._insert_taken(taken, **kw)


    def add_pdf(self, pdf, attachments=None, search_doi=True, search_fulltext=True, scholar=False, doi=None, **kw):

        if str(pdf).startswith("http"):
            pdf = download_url(pdf, expect_pdf=True)
            kw['rename'] = True  # always rename downloaded files

        # the library first (same DOI: the files are attached to its entry), then the pools, then online
        if kw.get('check_duplicate'):
            existing = self.find_doi(doi) if doi else (self.find_pdf(pdf) if search_doi else None)
            if existing is not None:
                return self.attach_to_existing(existing, [pdf] + list(attachments or []), **kw)

        if self.pool_lookup:
            files = [os.path.abspath(f) for f in [pdf] + list(attachments or [])]
            taken = self.pool_lookup.pdf(self, files[0], files=files, doi=doi)
            if taken is not None:
                kw["update_key"] = True
                return self._insert_taken(taken, **kw)

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
                except (EOFError, DuplicateError):
                    raise
                except Exception as error:
                    logger.warning(path+'::'+str(error))
                continue

            try:
                if path.lower().endswith('.pdf'):
                    yield from self.add_pdf(path, attachments=attachments, search_doi=search_doi, search_fulltext=search_fulltext, **kw)
                elif path.lower().endswith('.bib'):
                    yield from self.add_bibtex_file(path, **kw)
            except (EOFError, DuplicateError):
                raise  # a question without answer, or --on-duplicate error, stops the scan
            except Exception as error:
                logger.warning(path+'::'+str(error))
                continue

    def scan_dir(self, direc, **kw):
        " like scan_dir_iter but returns a list"
        return list(self.scan_dir_iter(direc, **kw))


    def format(self):
        """Return the library as a BibTeX string. Does not sort; call sort() first if you need ordered output."""
        return format_library(self.db)

    def save(self, bibtex, backup=None):
        """write the library to `bibtex` (the previous version goes to
        `backup`, if given). A bibtex that has this content already is not
        written: its modification time (and its backup) stay as they are.
        The file is replaced in one step (see write_atomic). A bibtex that
        another program wrote since this library read it is not written:
        BibtexChanged."""
        if self.relative_to not in (os.path.sep, None) and Path(self.relative_to).resolve() != Path(bibtex).parent.resolve():
            logger.warning("Saving bibtex file with relative paths may break links. Consider using `Biblio.update_file_path(Path(bibtex).parent)` before.")
        self.sort()  # consistent order before writing
        s = self.format()
        if os.path.exists(bibtex):
            if self._current_text(bibtex) == s:
                logger.debug(f'{bibtex}: unchanged, not written')
            else:
                if backup:
                    shutil.copy(bibtex, backup)
                write_atomic(bibtex, s)
        else:
            write_atomic(bibtex, s)
        self._remember(bibtex, s)
        if self.distinct.changed:
            if self.distinct.path is None:
                ondisk = Distinct.for_library(papers.config.library_dir(bibtex))
                ondisk.update(self.distinct)
                self.distinct = ondisk
            self.distinct.save()


    def update_file_path(self, relative_to):
        """
        relative_to: new path root:
            None: absolute path
            otherwise: different file root (the bibtex directory)
        Return the [(old, new)] file fields that changed.
        """
        updates = []
        for e in self.entries:
            update = update_file_path(e, self.relative_to, relative_to)
            if update is not None:
                updates.append(update)
        if len(updates):
            logger.info(f"{len(updates)} entry files were updated")
        self.relative_to = relative_to
        return updates

    def relative_links(self):
        """the absolute links of a library with relative links rewritten
        relative to the bibtex directory (a link to another drive on Windows
        stays absolute). Return the [(old, new)] file fields that changed."""
        updates = []
        for e in self.entries:
            if any(os.path.isabs(f) for f in parse_file(get_entry_val(e, 'file', ''))):
                update = update_file_path(e, self.relative_to, self.relative_to)
                if update is not None:
                    updates.append(update)
        return updates



    def check_duplicates(self, on_duplicate='error'):
        """merge the entries of the library that are the same paper (see
        papers.duplicate.duplicate_groups). The target of each group (entry
        1) is the entry with most fields; it keeps its key, and the keys of
        the other entries go to its ids field.

        on_duplicate: ask, keep, skip, error, or a Resolver
        """
        resolver = on_duplicate if isinstance(on_duplicate, Resolver) else Resolver(on_duplicate)
        if resolver.mode == 'update':
            raise ValueError('--on-duplicate update is not available for check (no side is new)')
        groups = duplicate_groups(self.entries, self.distinct)
        logger.info(f'{len(groups)} group(s) of duplicates')
        if resolver.mode == 'skip':
            return
        if resolver.mode == 'error' and groups:
            lines = []
            for g in groups:
                lines.append(Resolver.describe(Merge(g.entries, relative_to=self.relative_to, keys_to_ids=True),
                                               'check', g))
            raise DuplicateError('\n'.join(lines) + '\n' + option_hint('check'))

        for g in groups:
            if resolver.quit:
                break
            merge = Merge(g.entries, relative_to=self.relative_to, keys_to_ids=True)
            if g.kind == SAME and merge.is_exact():
                decision = Decision('merge', merge, merge.result())
            else:
                decision = resolver.decide(merge, 'check', g)

            if decision.kind == 'merge':
                target = decision.merge.target
                others = decision.merge.others
                apply_entry(target, decision.entry)
                for e in others:
                    self.db.remove(e)
                    if e.key.lower() != target.key.lower():
                        self.rekey_references(e.key, target.key)  # a crossref to the entry merged into the target
                print(f'merged into {get_entry_val(target, "ID", "")}: '
                      + ', '.join(get_entry_val(e, 'ID', '') for e in others) + ' (kept in ids)')

            elif decision.kind == 'distinct':
                for i, a in enumerate(g.entries):
                    for b in g.entries[i+1:]:
                        self.distinct.add(a, b)

    def rename_entry_files(self, e, copy=False, formatter=None, relative_to=None, hardlink=True):
        """ Rename files

        The first file is named after the entry: <filesdir>/<name>.<ext>, and
        any other file is placed next to it as <name>--<label>.<ext>, where
        <label> is the file's original name (see `attachment_names`).
        Directories of previous versions (<name>/ with a hidden .<name>.bib)
        are emptied into that layout, and removed when nothing else is left.
        Returns False when the name points outside the files directory (the
        files are left where they are), True otherwise.

        copy: keep the original file (a hard link when possible, with
            hardlink=True, otherwise a copy). It can also be a function that
            tells for each file what to do: 'move', 'copy', or 'link' (leave
            the file where it is), see papers.files.FilesPolicy.

        See `papers.filename.Format` class and REAMDE.md for infos.
        """

        if self.filesdir is None:
            raise ValueError('filesdir is None, cannot rename entries')

        files = self.get_files(e)

        if not files:
            logger.info('no files to rename')
            return True

        newname = (formatter or self.nameformat)(e)
        # absolute, to compare with the (absolute) current file paths
        filesdir = os.path.abspath(self.filesdir)
        target = os.path.normpath(os.path.join(filesdir, newname))
        if os.path.commonpath([filesdir, target]) != filesdir or target == filesdir:
            logger.error(f'{get_entry_val(e, "ID", "")}: the file name {newname!r} points outside the files directory: the files are left where they are')
            return False

        if callable(copy):
            actions = [copy(file) for file in files]
        else:
            actions = ['copy' if copy else 'move' for file in files]

        count = 0
        newfiles = []
        for file, newfile, action in zip(files, attachment_names(files, target), actions):
            if action == 'link':
                newfile = file
            elif not os.path.exists(file):
                logger.warning(file+': original file link is broken')
                newfile = file
            elif file != newfile:
                newfile = free_name(newfile, file)  # the name of another entry's file: a suffix
                if file != newfile:
                    self.move(file, newfile, action == 'copy', hardlink=hardlink)
                    count += 1
            newfiles.append(newfile)
        self.set_files(e, newfiles, relative_to=relative_to)

        for direc in {os.path.dirname(file) for file, action in zip(files, actions) if action == 'move'}:
            remove_entry_dir_if_empty(direc)

        if count > 0:
            logger.info('renamed file(s): {}'.format(count))
        return True


    def rename_entries_files(self, copy=False, relative_to=None, hardlink=True):
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
                # all fields but the abstract, and the paths and identifiers
                # (string_to_latex escapes _ and ~)
                for k in [k for k, _ in e.items() if k not in LATEX_SKIP]:
                    if k == k.lower():  # not ENTRYTYPE, ID
                        try:
                            e[k] = string_to_latex(e[k])
                        except (KeyError, ValueError) as error:
                            logger.warning(get_entry_val(e, 'ID', '')+': '+k+': failed to encode: '+str(error))

        if fix_doi:
            if 'doi' in e and e['doi']:
                try:
                    doi = parse_doi('doi:'+e['doi'])
                except Exception:
                    # keep the DOI as it is, and go on with the other fixes
                    logger.warning(get_entry_val(e, 'ID', '')+': failed to fix doi: '+e['doi'])
                    doi = e['doi']

                if doi.lower() != e['doi'].lower():
                    logger.info(get_entry_val(e, 'ID', '')+': fix doi: {} ==> {}'.format(e['doi'], doi))
                    e['doi'] = doi
                else:
                    logger.debug(get_entry_val(e, 'ID', '')+': doi OK')
            else:
                logger.debug(get_entry_val(e, 'ID', '')+': no DOI')


        if fetch or fetch_all:
            bibtex = None
            searched = False
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
                    searched = True
                except Exception as error:
                    logger.warning('...failed to fetch/update bibtex (all): '+str(error))

            if bibtex:
                db = parse_string(bibtex)
                e2 = db.entries[0]
                self.fix_entry(e2, encoding=encoding, format_name=True)
                # the best search result may be another paper
                mismatch = searched and search_result_mismatch(e, e2)
                if mismatch:
                    logger.warning('...fetch-all: rejected search result ({}): {} ({})'.format(
                        mismatch, get_entry_val(e2, 'title', ''), get_entry_val(e2, 'doi', 'no doi')))
                    bibtex = None
            if bibtex:
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
                if not key:  # never renamed to an empty key
                    logger.warning(f"{get_entry_val(e, 'ID', '')}: the key template gives an empty key: the key stays")
                elif get_entry_val(e, 'ID', '') != key:
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


# the characters that a bibtex key cannot have
_KEY_FORBIDDEN = re.compile(r'[\s,{}"#%~=()\\]')


def isvalidkey(key):
    return key and key[0] not in DIGITS
