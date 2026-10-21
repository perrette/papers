import difflib
import os
from pathlib import Path
import shutil
from unidecode import unidecode as unicode_to_ascii
from bibtexparser import Library
from bibtexparser.middlewares import SortBlocksByTypeAndKeyMiddleware

from papers.entries import (
    get_entry_val,
    set_entry_key,
    update_entry,
    entry_copy,
    entry_content_equal,
    parse_string,
    format_library,
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
from papers.extract import extract_pdf_metadata
from papers.fetch import fetch_bibtex_by_fulltext_crossref, fetch_bibtex_by_doi

from papers.encoding import standard_name, family_names, format_entries
from papers.latexenc import unicode_to_latex

from papers.filename import NAMEFORMAT, KEYFORMAT
from papers.files import (download_url, read_entry_dir, attachment_names, remove_entry_dir_if_empty,
                          scan_dir_items)
from papers.utils import bcolors, move as _move, PapersExit
import papers.config

from papers.duplicate import (
    SAME,
    Distinct,
    IdentityIndex,
    find_duplicates,
    duplicate_groups,
)
from papers.merge import Merge, Resolver, Decision, DuplicateError, apply_entry, option_hint


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


def backupfile(bibtex):
    return os.path.join(os.path.dirname(bibtex), '.'+os.path.basename(bibtex)+'.backup')

class DuplicateKeyError(PapersExit):
    "a new entry has the key of another paper of the library"

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
        # `add` looks in the pools first (see papers.pools.PoolLookup)
        self.pool_lookup = None

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
    def load(cls, bibtex, filesdir, relative_to=None, **kw):
        bibtexs = open(bibtex).read()
        kw.setdefault('distinct', Distinct.for_bibtex(bibtex))
        loaded_bib = cls(parse_string(bibtexs), filesdir, relative_to=relative_to if relative_to is not None else os.path.dirname(bibtex), **kw)
        return loaded_bib

    @classmethod
    def newbib(cls, bibtex, filesdir, relative_to=None, **kw):
        assert not os.path.exists(bibtex)
        if os.path.dirname(bibtex) and not os.path.exists(os.path.dirname(bibtex)):
            os.makedirs(os.path.dirname(bibtex))
        open(bibtex,'w').write('')
        return cls.load(bibtex, filesdir, relative_to=relative_to, **kw)

    def key(self, e):
        return e['ID'].lower()


    def sort(self):
        """Re-order library by block type and entry key (public API: SortBlocksByTypeAndKeyMiddleware)."""
        self.db = SortBlocksByTypeAndKeyMiddleware().transform(library=self.db)

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
        """
        if metadata:
            files = self.get_files(entry) + self.get_files(metadata)
            self.set_files(metadata, files)

        if check_duplicate:
            resolver = on_duplicate if isinstance(on_duplicate, Resolver) else Resolver(on_duplicate)
            return self._insert_entry_check(entry, resolver, update_key=update_key, rename=rename, copy=copy,
                                            index=duplicate_index)

        return self._insert_new(entry, update_key=update_key, rename=rename, copy=copy, index=duplicate_index)

    def _insert_new(self, entry, update_key=False, rename=False, copy=False, index=None, free_key=False):
        "insert an entry new to the library"
        if update_key:
            set_entry_key(entry, self.generate_key(entry))

        # Key duplicate check: lookup by key (public API), case-insensitive to match entries_dict keys
        key_lower = self.key(entry)
        existing_same_key = next(
            (e for k, e in self.db.entries_dict.items() if k.lower() == key_lower),
            None,
        )
        if existing_same_key is not None:
            logger.info('key duplicate: '+self.key(existing_same_key))

            if free_key:
                newkey = self.append_abc_to_key(entry)
                logger.info('key conflict: {} => {}'.format(get_entry_val(entry, 'ID', ''), newkey))
                set_entry_key(entry, newkey)

            elif get_entry_val(existing_same_key, 'title', '') == get_entry_val(entry, 'title', ''):
                logger.info('exact duplicate')
                # keep the files of the new entry
                files = self.get_files(existing_same_key) + self.get_files(entry)
                if files:
                    self.set_files(existing_same_key, files)
                if rename: self.rename_entry_files(existing_same_key, copy=copy)
                return [ existing_same_key ]

            elif update_key:
                newkey = self.generate_key(entry)  # unique key from content (e.g. DOI)
                logger.info('update key: {} => {}'.format(get_entry_val(entry, 'ID', ''), newkey))
                set_entry_key(entry, newkey)

            else:
                raise DuplicateKeyError(f'{get_entry_val(entry, "ID", "")}: this key is already in the library, '
                                        'for another paper: pass -u/--update-key to generate a new key, '
                                        'or --key KEY')

        else:
            logger.info('new entry: '+self.key(entry))

        self.db.add(entry)
        if index is not None:
            index.add(entry)

        if rename: self.rename_entry_files(entry, copy=copy)

        return [ entry ]

    def _insert_entry_check(self, entry, resolver, update_key=False, rename=False, copy=False, index=None):
        found = find_duplicates(entry, self.entries, self.distinct, index=index)
        if not found:
            logger.debug('not a duplicate')
            return self._insert_new(entry, update_key=update_key, rename=rename, copy=copy, index=index)

        existing, verdict = found[0]
        logger.debug(f'duplicate of {get_entry_val(existing, "ID", "")}: {verdict.reason}')
        merge = Merge([existing, entry], relative_to=self.relative_to)

        if verdict.kind == SAME and merge.is_exact():
            decision = Decision('merge', merge, merge.result())
            n = len(merge.new_files)
            print(f'already in library: {merge.key}' + (f' (+{n} file{"s" if n > 1 else ""})' if n else ''))
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
        return []


    def generate_key(self, entry):
        " generate a unique key not yet present in the record "
        keys = {self.key(e) for e in self.db.entries}
        key = self.keyformat(entry)
        if keys and key in keys:
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
        # one index for all entries, so that the duplicate search compares an
        # entry with the entries that share an identifier only
        if kw.get('check_duplicate') and kw.get('duplicate_index') is None and bib.entries:
            kw['duplicate_index'] = IdentityIndex(self.entries)
        for e in bib.entries:
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
        self.pool_lookup.inserted(entry, result)
        return result


    def add_bibtex_file(self, file, **kw):
        bibtex = open(file).read()
        # file links in the added bibtex are relative to its own directory
        # (the absolute path matters: dirname('papers.bib') is '')
        return self.add_bibtex(bibtex, relative_to=os.path.dirname(os.path.abspath(file)), **kw)


    def fetch_doi(self, doi, **kw):
        attachments = [os.path.abspath(f) for f in kw.get('attachments') or []]
        taken = self.pool_lookup.doi(self, doi, attachments) if self.pool_lookup else None
        if taken is not None:
            kw.pop('attachments', None)
            kw["update_key"] = True
            return self._insert_taken(taken, **kw)
        bibtex = fetch_bibtex_by_doi(doi)
        kw["update_key"] = True  # fetched key is always updated
        return self.add_bibtex(bibtex, **kw)


    def add_pdf(self, pdf, attachments=None, search_doi=True, search_fulltext=True, scholar=False, doi=None, **kw):

        if str(pdf).startswith("http"):
            pdf = download_url(pdf, expect_pdf=True)
            kw['rename'] = True  # always rename downloaded files

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

    def save(self, bibtex):
        if os.path.exists(bibtex):
            shutil.copy(bibtex, backupfile(bibtex))
        if self.relative_to not in (os.path.sep, None) and Path(self.relative_to).resolve() != Path(bibtex).parent.resolve():
            logger.warning("Saving bibtex file with relative paths may break links. Consider using `Biblio.update_file_path(Path(bibtex).parent)` before.")
        self.sort()  # consistent order before writing
        s = self.format()
        open(bibtex, 'w').write(s)
        if self.distinct.changed:
            if self.distinct.path is None:
                ondisk = Distinct.for_bibtex(bibtex)
                ondisk.update(self.distinct)
                self.distinct = ondisk
            self.distinct.save()


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
            return

        newname = (formatter or self.nameformat)(e)
        # absolute, to compare with the (absolute) current file paths
        target = os.path.join(os.path.abspath(self.filesdir), newname)

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
                self.move(file, newfile, action == 'copy', hardlink=hardlink)
                count += 1
            newfiles.append(newfile)
        self.set_files(e, newfiles, relative_to=relative_to)

        for direc in {os.path.dirname(file) for file, action in zip(files, actions) if action == 'move'}:
            remove_entry_dir_if_empty(direc)

        if count > 0:
            logger.info('renamed file(s): {}'.format(count))


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
                for k in e:
                    if k == k.lower() and k != 'abstract': # all but ENTRYTYPE, ID, abstract
                        try:
                            e[k] = unicode_to_latex(e[k])
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


def isvalidkey(key):
    return key and not key[0].isdigit()
