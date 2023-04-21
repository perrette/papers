import os
from pathlib import Path
import logging
# logger.basicConfig(level=logger.INFO)
import argparse
import subprocess as sp
import shutil
import bisect
import itertools

import bibtexparser
from bibtexparser.customization import convert_to_unicode

import papers
from papers import logger

from papers.extract import extract_pdf_doi, isvaliddoi, parse_doi
from papers.extract import extract_pdf_metadata
from papers.extract import fetch_bibtex_by_fulltext_crossref, fetch_bibtex_by_doi

from papers.encoding import unicode_to_latex, unicode_to_ascii
from papers.encoding import parse_file, format_file, standard_name, family_names, format_entries, update_file_path

from papers.config import config, bcolors, checksum, move, search_config, CONFIG_FILE, DATA_DIR

from papers.duplicate import check_duplicates, resolve_duplicates, conflict_resolution_on_insert
from papers.duplicate import search_duplicates, list_duplicates, list_uniques, merge_files, edit_entries
from papers.duplicate import entry_diff

# DRYRUN = False

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


# DUPLICATE DEFINITION
# ====================

def _remove_unicode(s, replace='_'):
    s2 = []
    for c in s:
        if ord(c) > 128:
            c = replace
        s2.append(c)
    return ''.join(s2)


def _simplify_string(s):
    ' replace unicode, strip, lower case '
    # try:
    #     s = latex_to_unicode(s)
    # except Exception as error:
    #     raise
    #     logger.warn('simplify string: failed to remove latex: '+str(error))
    s = _remove_unicode(s)
    return s.lower().strip()


def author_id(e):
    return _simplify_string(' '.join(family_names(e.get('author',''))))

def title_id(e):
    return _simplify_string(e.get('title',''))

def entry_id(e):
    """entry identifier which is not the bibtex key
    """
    authortitle = ''.join([author_id(e),title_id(e)])
    return (e.get('doi','').lower(), authortitle)


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
    if e1 == e2:
        return EXACT_DUPLICATES

    id1 = entry_id(e1)
    id2 = entry_id(e2)

    logger.debug('{} ?= {}'.format(id1, id2))

    if id1 == id2:
        score = GOOD_DUPLICATES

    elif e1.get('doi') and e2.get('doi') and e1['doi'] == e2['doi']:
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
    " save metadata for a bundle of files "
    dirname = os.path.basename(direc)
    return os.path.join(direc, '.'+dirname+'.bib')


def read_entry_dir(direc, update_files=True, relative_to=None):
    """add a directory that contain files from a single entry
    """
    dirname = os.path.basename(direc)
    hidden_bib = hidden_bibtex(direc)
    if not os.path.exists(hidden_bib):
        raise TypeError('hidden bib missing: not an entry dir')

    db = bibtexparser.loads(open(hidden_bib).read())
    assert len(db.entries) == 1, 'hidden bib must have one entry, got: '+str(len(db.entries))
    entry = db.entries[0]

    if update_files:
        for root, direcs, files in os.walk(direc):
            break # do not look further in subdirectories, cause any rename would flatten the tree
        files = [os.path.join(direc, file) for file in files if not file.startswith('.')]

    entry['file'] = format_file(files, relative_to=relative_to)
    return entry


def backupfile(bibtex):
    return os.path.join(os.path.dirname(bibtex), '.'+os.path.basename(bibtex)+'.backup')

class DuplicateKeyError(ValueError):
    pass

class Biblio:
    """main config
    """
    def __init__(self, db=None, filesdir=None, key_field='ID', nameformat=None, keyformat=None, similarity=DEFAULT_SIMILARITY, relative_to=None):
        """
        relative_to : bibtex directory, optional
            use relative paths instead of absolute path
        """
        self.filesdir = filesdir
        # assume an already sorted list
        self.key_field = key_field
        if db is None:
            db = bibtexparser.bibdatabase.BibDatabase()
        elif not isinstance(db, bibtexparser.bibdatabase.BibDatabase):
            raise TypeError('db must be of type BibDatabase')
        self.db = db
        self.nameformat = nameformat or config.nameformat
        self.keyformat = keyformat or config.keyformat
        self.similarity = similarity
        self.relative_to = os.path.sep if relative_to is None else relative_to
        self.sort()

    @property
    def entries(self):
        return self.db.entries

    @entries.setter
    def entries(self, entries):
        assert isinstance(entries, list)
        self.db.entries = entries

    @classmethod
    def loads(cls, bibtex, filesdir):
        db = bibtexparser.loads(bibtex)
        return cls(db, filesdir)

    def dumps(self):
        return bibtexparser.dumps(self.db)

    @classmethod
    def load(cls, bibtex, filesdir, relative_to=None):
        # self.bibtex = bibtex
        bibtexs = open(bibtex).read()
        loaded_bib = cls(bibtexparser.loads(bibtexs), filesdir, relative_to=os.path.dirname(bibtex))
        if relative_to is None:
            relative_to = os.path.sep if config.absolute_paths else os.path.dirname(bibtex)
        if loaded_bib.relative_to != relative_to:
            loaded_bib.update_file_path(relative_to)

        return loaded_bib

    # make sure the path is right
    # def assert_files_exist(self):
    #     for e in self.entries:
    #         files = parse_file(e["file"], self.relative_to)
    #         for f in files:
    #             assert os.path.exists(f), f"{f} does not exist"

    @classmethod
    def newbib(cls, bibtex, filesdir, relative_to=None):
        assert not os.path.exists(bibtex)
        if os.path.dirname(bibtex) and not os.path.exists(os.path.dirname(bibtex)):
            os.makedirs(os.path.dirname(bibtex))
        open(bibtex,'w').write('')
        return cls.load(bibtex, filesdir, relative_to=relative_to)

    def key(self, e):
        return e[self.key_field].lower()

    def eq(self, e1, e2):
        return are_duplicates(e1, e2, similarity=self.similarity)

    def __contains___(self, entry):
        return any({self.eq(entry, e) for e in self.entries})


    def sort(self):
        self.db.entries = sorted(self.db.entries, key=self.key)

    def index_sorted(self, entry):
        keys = [self.key(ei) for ei in self.db.entries]
        return bisect.bisect_left(keys, self.key(entry))


    def insert_entry(self, entry, update_key=False, check_duplicate=False, rename=False, copy=False, **checkopt):
        """
        """
        # additional checks on DOI etc...
        if check_duplicate:
            logger.debug('check duplicates : TRUE')
            self.insert_entry_check(entry, update_key=update_key, rename=rename, copy=copy, **checkopt)
            return
        else:
            logger.debug('check duplicates : FALSE')

        i = self.index_sorted(entry)  # based on current sort key (e.g. ID)

        if i < len(self.entries) and self.key(self.entries[i]) == self.key(entry):
            logger.info('key duplicate: '+self.key(self.entries[i]))

            if update_key:
                newkey = self.append_abc_to_key(entry)  # add abc
                logger.info('update key: {} => {}'.format(entry['ID'], newkey))
                entry['ID'] = newkey

            else:
                raise DuplicateKeyError('this error can be avoided if update_key is True')

        else:
            logger.info('new entry: '+self.key(entry))

        self.entries.insert(i, entry)

        if rename: self.rename_entry_files(entry, copy=copy)


    def insert_entry_check(self, entry, update_key=False, mergefiles=True, on_conflict='i', rename=False, copy=False):

        duplicates = [e for e in self.entries if self.eq(e, entry)]

        if not duplicates:
            logger.debug('not a duplicate')
            self.insert_entry(entry, update_key, rename=rename, copy=copy)


        elif duplicates:
            # some duplicates...
            logger.debug('duplicate(s) found: {}'.format(len(duplicates)))

            # pick only the most similar duplicate, if more than one
            # the point of check_duplicate is to avoid increasing disorder, not to clean the existing mess
            if len(duplicates) > 1:
                duplicates.sort(key=lambda e: compare_entries(entry, e), reverse=True)

            candidate = duplicates[0]

            if entry == candidate:
                logger.debug('exact duplicate')
                if rename: self.rename_entry_files(candidate, copy=copy)
                return  # do nothing

            if update_key and entry['ID'] != candidate['ID']:
                logger.info('duplicate :: update key to match existing entry: {} => {}'.format(entry['ID'], candidate['ID']))
                entry['ID'] = candidate['ID']

            if mergefiles:

                file = merge_files([candidate, entry], relative_to=self.relative_to)
                if len({file, entry.get('file',''), candidate.get('file','')}) > 1:
                    logger.info('duplicate :: merge files')
                    entry['file'] = candidate['file'] = file


            if entry == candidate:
                logger.debug('fixed: exact duplicate')
                entry = candidate
                if rename: self.rename_entry_files(candidate, copy=copy)
                return  # do nothing

            logger.debug('conflict resolution: '+on_conflict)
            resolved = conflict_resolution_on_insert(candidate, entry, mode=on_conflict)
            self.entries.remove(candidate) # maybe in resolved entries
            for e in resolved:
                self.insert_entry(e, update_key, rename=rename, copy=copy)


    def generate_key(self, entry):
        " generate a unique key not yet present in the record "
        keys = {self.key(e) for e in self.db.entries}
        key = self.keyformat(entry)
        if keys and key in keys: # and not isinstance(keys, set):
            key = append_abc(key, keys)
        return key

    def append_abc_to_key(self, entry):
        return append_abc(entry['ID'], keys={self.key(e) for e in self.entries})


    def add_bibtex(self, bibtex, relative_to=None, attachments=None, convert_to_unicode=False, **kw):
        bib = bibtexparser.loads(bibtex)
        if convert_to_unicode:
            bib = bibtexparser.customization.convert_to_unicode(bib)
        for e in bib.entries:
            files = []
            if "file" in e:
                # make sure paths relative to other bibtex are inserted correctly
                files.extend(parse_file(e["file"], relative_to=relative_to))
            if attachments:
                files.extend([os.path.abspath(f) for f in attachments])
            if files:
                e["file"] = format_file(list(set(files)), relative_to=self.relative_to)

            self.insert_entry(e, **kw)


    def add_bibtex_file(self, file, **kw):
        bibtex = open(file).read()
        return self.add_bibtex(bibtex, relative_to=os.path.dirname(file), **kw)


    def fetch_doi(self, doi, **kw):
        bibtex = fetch_bibtex_by_doi(doi)
        self.add_bibtex(bibtex, **kw)


    def add_pdf(self, pdf, attachments=None, search_doi=True, search_fulltext=True, scholar=False, doi=None, **kw):

        if doi:
            bibtex = fetch_bibtex_by_doi(doi)
        else:
            bibtex = extract_pdf_metadata(pdf, search_doi, search_fulltext, scholar=scholar)

        bib = bibtexparser.loads(bibtex)
        entry = bib.entries[0]

        # convert curly brackets to unicode
        entry = convert_to_unicode(entry)

        files = [pdf] if pdf else []
        if attachments:
            files += attachments

        entry['file'] = format_file([os.path.abspath(f) for f in files], relative_to=self.relative_to)
        entry['ID'] = self.generate_key(entry)
        logger.debug('generated PDF key: '+entry['ID'])

        kw.pop('update_key', True)
            # logger.warn('fetched key is always updated when adding PDF to existing bib')
        self.insert_entry(entry, update_key=True, **kw)


    def scan_dir(self, direc, search_doi=True, search_fulltext=True, **kw):

        for root, direcs, files in os.walk(direc):
            dirname = os.path.basename(root)
            if dirname.startswith('.'): continue
            if dirname.startswith('_'): continue

            # maybe a special entry directory?
            if os.path.exists(hidden_bibtex(root)):
                logger.debug('read from hidden bibtex')
                try:
                    entry = read_entry_dir(root, relative_to=self.relative_to)
                    self.insert_entry(entry, **kw)
                except Exception:
                    logger.warn(root+'::'+str(error))
                continue

            for file in files:
                if file.startswith('.'):
                    continue
                path = os.path.join(root, file)
                try:
                    if file.endswith('.pdf'):
                        self.add_pdf(path, search_doi=search_doi, search_fulltext=search_fulltext, **kw)
                    elif file.endswith('.bib'):
                        self.add_bibtex_file(path, **kw)
                except Exception as error:
                    logger.warn(path+'::'+str(error))
                    continue


    def format(self):
        return bibtexparser.dumps(self.db)

    def save(self, bibtex):
        if os.path.exists(bibtex):
            shutil.copy(bibtex, backupfile(bibtex))
        if self.relative_to not in (os.path.sep, None) and Path(self.relative_to).resolve() != Path(bibtex).parent.resolve():
            logger.warn("Saving bibtex file with relative paths may break links. Consider using `Biblio.update_file_path(Path(bibtex).parent)` before.")
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
        self.sort() # keep sorted


    def rename_entry_files(self, e, copy=False, formatter=None):
        """ Rename files

        See `papers.filename.Format` class and REAMDE.md for infos.
        """

        if self.filesdir is None:
            raise ValueError('filesdir is None, cannot rename entries')

        files = parse_file(e.get('file',''), relative_to=self.relative_to)
        # newname = entrydir(e, root)

        direc = self.filesdir

        if not files:
            logger.info('no files to rename')
            return

        newname = (formatter or self.nameformat)(e)
        count = 0
        if len(files) == 1:
            file = files[0]
            base, ext = os.path.splitext(file)
            newfile = os.path.join(direc, newname+ext)
            if not os.path.exists(file):
                raise ValueError(file+': original file link is broken')
            elif file != newfile:
                move(file, newfile, copy)
                # assert os.path.exists(newfile)
                # if not copy:
                #     assert not os.path.exists(file)
                count += 1
            newfiles = [newfile]
            e['file'] = format_file(newfiles, relative_to=self.relative_to)


        # several files: only rename container
        else:
            newdir = os.path.join(direc, newname)
            newfiles = []
            for file in files:
                newfile = os.path.join(newdir, os.path.basename(file))
                if not os.path.exists(file):
                    raise ValueError(file+': original file link is broken')
                elif file != newfile:
                    move(file, newfile, copy)
                    # assert os.path.exists(newfile)
                    count += 1
                newfiles.append(newfile)
            e['file'] = format_file(newfiles, relative_to=self.relative_to)

            # create hidden bib entry for special dir
            bibname = hidden_bibtex(newdir)
            db = bibtexparser.bibdatabase.BibDatabase()
            db.entries.append(e)
            bibtex = bibtexparser.dumps(db)
            with open(bibname,'w') as f:
                f.write(bibtex)

            # remove old direc if empty?
            direcs = list({os.path.dirname(file) for file in files})
            if len(direcs) == 1:
                leftovers = os.listdir(direcs[0])
                if not leftovers or len(leftovers) == 1 and leftovers[0] == os.path.basename(hidden_bibtex(direcs[0])):
                    logger.debug('remove tree: '+direcs[0])
                    shutil.rmtree(direcs[0])
            else:
                logger.debug('some left overs, do not remove tree: '+direcs[0])

        # for f in parse_file(e['file'], self.relative_to):
        #     assert os.path.exists(f), f

        if count > 0:
            logger.info('renamed file(s): {}'.format(count))


    def rename_entries_files(self, copy=False):
        for e in self.db.entries:
            try:
                self.rename_entry_files(e, copy)
            except Exception as error:
                logger.error(str(error))
                continue


    def fix_entry(self, e, fix_doi=True, fetch=False, fetch_all=False,
        fix_key=False, auto_key=False, key_ascii=False, encoding=None,
        format_name=True, interactive=False):

        e_old = e.copy()

        if format_name:
            for k in ['author','editor']:
                if k in e:
                    e[k] = standard_name(e[k])
                    if e[k] != e_old[k]:
                        logger.info(e.get('ID','')+': '+k+' name formatted')

        if encoding:

            assert encoding in ['unicode','latex'], e.get('ID','')+': unknown encoding: '+repr(encoding)

            logger.debug(e.get('ID','')+': update encoding')
            if encoding == "unicode":
                e = convert_to_unicode(e)
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
                            logger.warn(e.get('ID','')+': '+k+': failed to encode: '+str(error))

        if fix_doi:
            if 'doi' in e and e['doi']:
                try:
                    doi = parse_doi('doi:'+e['doi'])
                except:
                    logger.warn(e.get('ID','')+': failed to fix doi: '+e['doi'])
                    return

                if doi.lower() != e['doi'].lower():
                    logger.info(e.get('ID','')+': fix doi: {} ==> {}'.format(e['doi'], doi))
                    e['doi'] = doi
                else:
                    logger.debug(e.get('ID','')+': doi OK')
            else:
                logger.debug(e.get('ID','')+': no DOI')


        if fetch or fetch_all:
            bibtex = None
            if 'doi' in e and e['doi']:
                logger.info(e.get('ID','')+': fetch doi: '+e['doi'])
                try:
                    bibtex = fetch_bibtex_by_doi(e['doi'])
                except Exception as error:
                    logger.warn('...failed to fetch bibtex (doi): '+str(error))

            elif e.get('title','') and e.get('author','') and fetch_all:
                kw = {}
                kw['title'] = e['title']
                kw['author'] = ' '.join(family_names(e['author']))
                logger.info(e.get('ID','')+': fetch-all: '+str(kw))
                try:
                    bibtex = fetch_bibtex_by_fulltext_crossref('', **kw)
                except Exception as error:
                    logger.warn('...failed to fetch/update bibtex (all): '+str(error))

            if bibtex:
                db = bibtexparser.loads(bibtex)
                e2 = db.entries[0]
                self.fix_entry(e2, encoding=encoding, format_name=True)
                strip_e = lambda e_: {k:e_[k] for k in e_ if k not in ['ID', 'file'] and k in e2}
                if strip_e(e) != strip_e(e2):
                    logger.info('...fetch-update entry')
                    e.update(strip_e(e2))
                else:
                    logger.info('...fetch-update: already up to date')


        if fix_key or auto_key:
            if auto_key or not isvalidkey(e.get('ID','')):
                key = self.generate_key(e)
                if e.get('ID', '') != key:
                    logger.info('update key {} => {}'.format(e.get('ID', ''), key))
                    e['ID'] = key

        if key_ascii:
            e['ID'] = unicode_to_ascii(e['ID'])

        if interactive and e_old != e:
            print(bcolors.OKBLUE+'*** UPDATE ***'+bcolors.ENDC)
            print(entry_diff(e_old, e))

            if input('update ? [Y/n] or [Enter] ').lower() not in ('', 'y'):
                logger.info('cancel changes')
                e.update(e_old)
                for k in list(e.keys()):
                    if k not in e_old:
                        del e[k]




def isvalidkey(key):
    return key and not key[0].isdigit()


def requiresreview(e):
    if not isvalidkey(e.get('ID','')): return True
    if 'doi' in e and not isvaliddoi(e['doi']): return True
    if 'author' not in e: return True
    if 'title' not in e: return True
    if 'year' not in e: return True
    return False


def entry_filecheck_metadata(e, file, image=False):
    ''' parse pdf metadata and compare with entry: only doi for now
    '''
    if 'doi' not in e:
        raise ValueError(e['ID']+': no doi, skip PDF parsing')

    try:
        doi = extract_pdf_doi(file, image=image)
    except Exception as error:
        raise ValueError(e['ID']+': failed to parse doi: "{}"'.format(file))
    if not isvaliddoi(doi):
        raise ValueError(e['ID']+': invalid parsed doi: '+doi)

    if doi.lower() != e['doi'].lower():
        raise ValueError(e['ID']+': doi: entry <=> pdf : {} <=> {}'.format(e['doi'].lower(), doi.lower()))


def entry_filecheck(e, delete_broken=False, fix_mendeley=False,
    check_hash=False, check_metadata=False, interactive=True, image=False, relative_to=None):

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
            logger.info(e['ID']+': remove duplicate path: "{}"'.format(fixed.get(file, file)))
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
                logger.warn(e['ID']+': '+str(error)+': failed to convert latex symbols to unicode: '+file)

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
                logger.info(e['ID']+': file name fixed: "{}" => "{}".'.format(old, file))
                fixed[old] = file # keep record of fixed files

        # parse PDF and check for metadata
        if check_metadata and file.endswith('.pdf'):
            try:
                entry_filecheck_metadata(e, file, image=image)
            except ValueError as error:
                logger.warn(error)

        # check existence
        if not os.path.exists(file):
            logger.warn(e['ID']+': "{}" does not exist'.format(file)+delete_broken*' ==> delete')
            if delete_broken:
                logger.info('delete file from entry: "{}"'.format(file))
                continue
            elif interactive:
                ans = input('delete file from entry ? [Y/n] ')
                if ans.lower() == 'y':
                    continue

        elif check_hash:
            # hash_ = hashlib.sha256(open(file, 'rb').read()).digest()
            hash_ = checksum(file) # a litftle faster
            if hash_ in hashes:
                logger.info(e['ID']+': file already exists (identical checksum): "{}"'.format(file))
                continue
            hashes.add(hash_)

        newfiles.append(file)

    e['file'] = format_file(newfiles, relative_to=relative_to)



def main():

    configfile = search_config([os.path.join(".papers", "config.json")], start_dir=".", default=config.file)

    if os.path.exists(configfile):
        config.file = configfile
        config.load()

    else:
        config.bibtex = None
        config.filesdir = None

    parser = argparse.ArgumentParser(description='library management tool')
    subparsers = parser.add_subparsers(dest='cmd')

    # configuration (re-used everywhere)
    # =============
    loggingp = argparse.ArgumentParser(add_help=False)
    grp = loggingp.add_argument_group('logging level (default warn)')
    egrp = grp.add_mutually_exclusive_group()
    egrp.add_argument('--debug', action='store_const', dest='logging_level', const=logging.DEBUG)
    egrp.add_argument('--info', action='store_const', dest='logging_level', const=logging.INFO)
    egrp.add_argument('--warn', action='store_const', dest='logging_level', const=logging.WARN)
    egrp.add_argument('--error', action='store_const', dest='logging_level', const=logging.ERROR)

    cfg = argparse.ArgumentParser(add_help=False, parents=[loggingp])
    grp = cfg.add_argument_group('config')
    grp.add_argument('--filesdir', default=None,
        help=f'files directory (default: {config.filesdir}')
    grp.add_argument('--bibtex', default=None,
        help=f'bibtex database (default: {config.bibtex}')
    grp.add_argument('--dry-run', action='store_true',
        help='no PDF renaming/copying, no bibtex writing on disk (for testing)')
    grp.add_argument('--no-prompt', action='store_false', dest="prompt",
        help='no prompt, use default (useful for tests)')
    grp.add_argument('--relative-paths', action="store_false", dest="absolute_paths", default=None)
    grp.add_argument('--absolute-paths', action="store_true", default=None)

    keyfmt = argparse.ArgumentParser(add_help=False)
    grp = keyfmt.add_argument_group('bibtex key format')
    grp.add_argument('--key-template', default=config.keyformat.template,
        help='python template for generating keys (default:%(default)s)')
    grp.add_argument('--key-author-num', type=int, default=config.keyformat.author_num,
        help='number of authors to include in key (default:%(default)s)')
    grp.add_argument('--key-author-sep', default=config.keyformat.author_sep,
        help='separator for authors in key (default:%(default)s)')
    grp.add_argument('--key-title-word-num', type=int, default=config.keyformat.title_word_num,
        help='number of title words to include in key (default:%(default)s)')
    grp.add_argument('--key-title-word-size', type=int, default=config.keyformat.title_word_size,
        help='number of title words to include in key (default:%(default)s)')
    grp.add_argument('--key-title-sep', default=config.keyformat.title_sep,
        help='separator for title words in key (default:%(default)s)')

    namefmt = argparse.ArgumentParser(add_help=False)
    grp = namefmt.add_argument_group('filename format')
    grp.add_argument('--name-template', default=config.nameformat.template,
        help='python template for renaming files (default:%(default)s)')
    grp.add_argument('--name-author-num', type=int, default=config.nameformat.author_num,
        help='number of authors to include in filename (default:%(default)s)')
    grp.add_argument('--name-author-sep', default=config.nameformat.author_sep,
        help='separator for authors in filename (default:%(default)s)')
    grp.add_argument('--name-title-word-num', type=int, default=config.nameformat.title_word_num,
        help='number of title words to include in filename (default:%(default)s)')
    grp.add_argument('--name-title-word-size', type=int, default=config.nameformat.title_word_size,
        help='min size of title words to include in filename (default:%(default)s)')
    grp.add_argument('--name-title-length', type=int, default=config.nameformat.title_length,
        help='title length to include in filename (default:%(default)s)')
    grp.add_argument('--name-title-sep', default=config.nameformat.title_sep,
        help='separator for title words in filename (default:%(default)s)')


    def set_keyformat_config_from_cmd(o):
        config.keyformat.template = o.key_template
        config.keyformat.author_num = o.key_author_num
        config.keyformat.author_sep = o.key_author_sep
        config.keyformat.title_word_num = o.key_title_word_num
        config.keyformat.title_word_size = o.key_title_word_size
        config.keyformat.title_sep = o.key_title_sep

    def set_nameformat_config_from_cmd(o):
        config.nameformat.template = o.name_template
        config.nameformat.author_num = o.name_author_num
        config.nameformat.author_sep = o.name_author_sep
        config.nameformat.title_length = o.name_title_length
        config.nameformat.title_word_num = o.name_title_word_num
        config.nameformat.title_word_size = o.name_title_word_size
        config.nameformat.title_sep = o.name_title_sep


    # status
    # ======
    statusp = subparsers.add_parser('status',
        description='view install status',
        parents=[cfg])
    statusp.add_argument('--no-check-files', action='store_true', help='faster, less info')
    statusp.add_argument('-v','--verbose', action='store_true', help='app status info')

    def statuscmd(o):
        print(config.status(check_files=not o.no_check_files, verbose=o.verbose))


    # install
    # =======

    installp = subparsers.add_parser('install', description='setup or update papers install',
        parents=[cfg, namefmt, keyfmt])
    installp.add_argument('--reset-paths', action='store_true', help=argparse.SUPPRESS)
    # egrp = installp.add_mutually_exclusive_group()
    installp.add_argument('--local', action="store_true",
        help="""setup papers locally in current directory (global install by default), exposing bibtex and filesdir,
        and having the rest under .papers (config options). Only keep the cache globally.
        This might not play out too well with git tracking (local install usuall have their own git) but might be OK.""")

    installp.add_argument('--git', action='store_true',
        help="""Track bibtex files with git.
        Each time the bibtex is modified, a copy of the file is saved in a git-tracked
        global directory (see papers status), and committed. Note the original bibtex name is
        kept, so that different files can be tracked simultaneously, as long as the names do
        not conflict. This option is mainly useful for backup purposes (local or remote).
        Use in combination with `papers git`'
        """)
    installp.add_argument('--gitdir', default=None, help=f'default: {config.gitdir} or local')

    grp = installp.add_argument_group('status')
    # grp.add_argument('-l','--status', action='store_true')
    # grp.add_argument('-v','--verbose', action='store_true')
    # grp.add_argument('-c','--check-files', action='store_true')
    grp.add_argument('--no-check-files', action='store_true', help='faster, less info')
    # grp.add_argument('-v','--verbose', action='store_true', help='app status info')


    def installcmd(o):

        set_nameformat_config_from_cmd(o)
        set_keyformat_config_from_cmd(o)

        checkdirs = ["files", "pdfs", "pdf", "papers", "bibliography"]
        default_bibtex = "papers.bib"
        default_filesdir = "files"

        if o.local:
            datadir = gitdir = ".papers"
            papersconfig = ".papers/config.json"
            workdir = Path('.')
            biblios = list(workdir.glob("*.bib"))

            if o.absolute_paths is None:
                o.absolute_paths = False

        else:
            datadir = config.data
            gitdir = config.gitdir
            papersconfig = CONFIG_FILE
            workdir = Path(DATA_DIR)
            biblios = list(Path('.').glob("*.bib")) + list(workdir.glob("*.bib"))
            checkdirs = [os.path.join(papers.config.DATA_DIR, "files")] + checkdirs

            if o.absolute_paths is None:
                o.absolute_paths = True

        biblios = [default_bibtex] + [f for f in biblios if Path(f) != Path(default_bibtex)]

        if config.filesdir:
            checkdirs = [config.filesdir] + checkdirs

        for d in checkdirs:
            if os.path.exists(str(d)):
                default_filesdir = d
                break

        RESET_DEFAULT = ('none', 'null', 'unset', 'undefined', 'reset', 'delete', 'no', 'n')
        ACCEPT_DEFAULT = ('yes', 'y')

        if not o.bibtex:
            if len(biblios) > 1:
                logger.warn("Several bibtex files found: "+" ".join([str(b) for b in biblios]))
            if biblios:
                default_bibtex = biblios[0]
            if o.prompt:
                if os.path.exists(default_bibtex):
                    user_input = input(f"Bibtex file name [default to existing: {default_bibtex}] [Enter/Yes/No]: ")
                else:
                    user_input = input(f"Bibtex file name [default to new: {default_bibtex}] [Enter/Yes/No]: ")
                if user_input:
                    if user_input.lower() in RESET_DEFAULT:
                        default_bibtex = None
                    elif user_input.lower() in ACCEPT_DEFAULT:
                        pass
                    else:
                        default_bibtex = Path(user_input)
            o.bibtex = default_bibtex

        if not o.filesdir:
            if o.prompt:
                if Path(default_filesdir).exists():
                    user_input = input(f"Files folder [default to existing: {default_filesdir}] [Enter/Yes/No]: ")
                else:
                    user_input = input(f"Files folder [default to new: {default_filesdir}] [Enter/Yes/No]: ")
                if user_input:
                    if user_input.lower() in RESET_DEFAULT:
                        default_filesdir = None
                    elif user_input.lower() in ACCEPT_DEFAULT:
                        pass
                    else:
                        default_filesdir = user_input
            o.filesdir = default_filesdir


        config.bibtex = o.bibtex
        config.filesdir = o.filesdir
        config.gitdir = gitdir
        config.data = datadir
        config.file = papersconfig
        config.local = o.local
        config.absolute_paths = o.absolute_paths


        if config.git and not o.git and o.bibtex == config.bibtex:
            ans = input('stop git tracking (this will not affect actual git directory)? [Y/n] ')
            if ans.lower() != 'y':
                o.git = True

        if o.reset_paths:
            config.reset()

        config.git = o.git

        # create bibtex file if not existing
        bibtex = Path(o.bibtex) if o.bibtex else None

        if bibtex and not bibtex.exists():
            logger.info('create empty bibliography database: '+o.bibtex)
            bibtex.parent.mkdir(parents=True, exist_ok=True)
            bibtex.open('w', encoding="utf-8").write('')

        # create bibtex file if not existing
        filesdir = Path(o.filesdir) if o.filesdir else None
        if filesdir and not filesdir.exists():
            logger.info('create empty files directory: '+o.filesdir)
            filesdir.mkdir(parents=True)

        if o.git and not os.path.exists(config._gitdir):
            config.gitinit()

        logger.info('save config file: '+config.file)
        if o.local:
            os.makedirs(".papers", exist_ok=True)
        else:
            from papers.config import CONFIG_HOME
            os.makedirs(CONFIG_HOME, exist_ok=True)
        config.save()

        print(config.status(check_files=not o.no_check_files, verbose=True))


    def savebib(my):
        logger.info('save '+config.bibtex)
        if papers.config.DRYRUN:
            return
        if my is not None:
            my.save(config.bibtex)
        if config.git:
            config.gitcommit()

    # uninstall
    # =======
    uninstallp = subparsers.add_parser('uninstall', description='remove configuration file',
        parents=[cfg])
    uninstallp.add_argument("--recursive", action="store_true", help="if true, uninstall all papers configuration found on the path, recursively (config file only)")

    def _dir_is_empty(dir):
        with os.scandir(dir) as it:
            return not any(it)

    def uninstallcmd(o):
        if Path(config.file).exists():
            logger.info(f"remove {config.file}")
            os.remove(config.file)
            parent = os.path.dirname(config.file)
            if _dir_is_empty(parent):
                logger.info(f"remove {parent}")
                os.rmdir(parent)
            papers.config.config = papers.config.Config()
        else:
            logger.info(f"no config file to remove")
            return

        if o.recursive:
            config.file = search_config([os.path.join(".papers", "config.json")], start_dir=".", default=CONFIG_FILE)
            uninstallcmd(o)


    # add
    # ===
    addp = subparsers.add_parser('add', description='add PDF(s) or bibtex(s) to library',
        parents=[cfg, namefmt, keyfmt])
    addp.add_argument('file', nargs='*', default=[])
    # addp.add_argument('-f','--force', action='store_true', help='disable interactive')

    grp = addp.add_argument_group('duplicate check')
    grp.add_argument('--no-check-duplicate', action='store_true',
        help='disable duplicate check (faster, create duplicates)')
    grp.add_argument('--no-merge-files', action='store_true',
        help='distinct "file" field considered a conflict, all other things being equal')
    grp.add_argument('-u', '--update-key', action='store_true',
        help='update added key according to any existing duplicate (otherwise an error might be raised on identical insert key)')
    # grp.add_argument('-f', '--force', action='store_true', help='no interactive')
    grp.add_argument('-m', '--mode', default='i', choices=['u', 'U', 'o', 's', 'r', 'i','a'],
        help='''if duplicates are found, the default is to start an (i)nteractive dialogue,
        unless "mode" is set to (r)aise, (s)skip new, (u)pdate missing, (U)pdate with new, (o)verwrite completely.
        ''')

    grp = addp.add_argument_group('directory scan')
    grp.add_argument('--recursive', action='store_true',
        help='accept directory as argument, for recursive scan \
        of .pdf files (bibtex files are ignored in this mode')
    grp.add_argument('--ignore-errors', action='store_true',
        help='ignore errors when adding multiple files')

    grp = addp.add_argument_group('pdf metadata')
    grp.add_argument('--doi', help='provide DOI -- skip parsing PDF')
    grp.add_argument('--no-query-doi', action='store_true', help='do not attempt to parse and query doi')
    grp.add_argument('--no-query-fulltext', action='store_true', help='do not attempt to query fulltext in case doi query fails')
    grp.add_argument('--scholar', action='store_true', help='use google scholar instead of crossref')

    grp = addp.add_argument_group('attached files')
    grp.add_argument('-a','--attachment', nargs='+') #'supplementary material')
    grp.add_argument('-r','--rename', action='store_true',
        help='rename PDFs according to key')
    grp.add_argument('-c','--copy', action='store_true',
        help='copy file instead of moving them')



    def addcmd(o):

        set_nameformat_config_from_cmd(o)
        set_keyformat_config_from_cmd(o)

        if os.path.exists(config.bibtex):
            my = Biblio.load(config.bibtex, config.filesdir)
        else:
            my = Biblio.newbib(config.bibtex, config.filesdir)

        kw = {'on_conflict':o.mode, 'check_duplicate':not o.no_check_duplicate,
            'mergefiles':not o.no_merge_files, 'update_key':o.update_key}

        if len(o.file) > 1:
            if o.attachment:
                logger.error('--attachment is only valid for one PDF / BIBTEX entry')
                addp.exit(1)
            if o.doi:
                logger.error('--doi is only valid for one added file')
                addp.exit(1)

        if len(o.file) == 0:
            if not o.doi:
                logger.error('Please provide either a PDF file or BIBTEX entry or specify `--doi DOI`')
                addp.exit(1)
            elif o.no_query_doi:
                logger.error('If no file is present, --no-query-doi is not compatible with --doi')
                addp.exit(1)
            else:
                my.fetch_doi(o.doi, attachments=o.attachment, rename=o.rename, copy=o.copy, **kw)

        for file in o.file:
            try:
                if os.path.isdir(file):
                    if o.recursive:
                        my.scan_dir(file, rename=o.rename, copy=o.copy,
                            search_doi=not o.no_query_doi,
                            search_fulltext=not o.no_query_fulltext,
                              **kw)
                    else:
                        raise ValueError(file+' is a directory, requires --recursive to explore')

                elif file.endswith('.pdf'):
                    my.add_pdf(file, attachments=o.attachment, rename=o.rename, copy=o.copy,
                            search_doi=not o.no_query_doi,
                            search_fulltext=not o.no_query_fulltext,
                            scholar=o.scholar, doi=o.doi,
                            **kw)

                else: # file.endswith('.bib'):
                    my.add_bibtex_file(file, **kw)

            except Exception as error:
                # print(error)
                # addp.error(str(error))
                raise
                logger.error(str(error))
                if not o.ignore_errors:
                    if len(o.file) or (os.isdir(file) and o.recursive)> 1:
                        logger.error('use --ignore to add other files anyway')
                    addp.exit(1)

        savebib(my)


    # check
    # =====
    checkp = subparsers.add_parser('check', description='check and fix entries',
        parents=[cfg, keyfmt])
    checkp.add_argument('-k', '--keys', nargs='+', help='apply check on this key subset')
    checkp.add_argument('-f','--force', action='store_true', help='do not ask')

    grp = checkp.add_argument_group('entry key')
    grp.add_argument('--fix-key', action='store_true', help='fix key based on author name and date (in case misssing or digit)')
    grp.add_argument('--key-ascii', action='store_true', help='replace keys unicode character with ascii')
    grp.add_argument('--auto-key', action='store_true', help='new, auto-generated key for all entries')
#     grp.add_argument('--nauthor', type=int, default=config.nauthor, help='number of authors to include in key (default:%(default)s)')
#     grp.add_argument('--ntitle', type=int, default=config.ntitle, help='number of title words to include in key (default:%(default)s)')
    # grp.add_argument('--ascii-key', action='store_true', help='replace unicode characters with closest ascii')

    grp = checkp.add_argument_group('crossref fetch and fix')
    grp.add_argument('--fix-doi', action='store_true', help='fix doi for some common issues (e.g. DOI: inside doi, .received at the end')
    grp.add_argument('--fetch', action='store_true', help='fetch metadata from doi and update entry')
    grp.add_argument('--fetch-all', action='store_true', help='fetch metadata from title and author field and update entry (only when doi is missing)')

    grp = checkp.add_argument_group('names')
    grp.add_argument('--format-name', action='store_true', help='author name as family, given, without brackets')
    grp.add_argument('--encoding', choices=['latex','unicode'], help='bibtex field encoding')

    grp = checkp.add_argument_group('merge/conflict')
    grp.add_argument('--duplicates',action='store_true', help='solve duplicates')
    grp.add_argument('-m', '--mode', default='i', choices=list('ims'), help='''(i)interactive mode by default, otherwise (m)erge or (s)kip failed''')
    # grp.add_argument('--ignore', action='store_true', help='ignore unresolved conflicts')
    # checkp.add_argument('--merge-keys', nargs='+', help='only merge remove / merge duplicates')
    # checkp.add_argument('--duplicates',action='store_true', help='remove / merge duplicates')

    def checkcmd(o):
        set_keyformat_config_from_cmd(o)
        my = Biblio.load(config.bibtex, config.filesdir)

        # if o.fix_all:
        #     o.fix_doi = True
        #     o.fetch_all = True
        #     o.fix_key = True

        for e in my.entries:
            if o.keys and e.get('ID','') not in o.keys:
                continue
            my.fix_entry(e, fix_doi=o.fix_doi, fetch=o.fetch, fetch_all=o.fetch_all, fix_key=o.fix_key,
                auto_key=o.auto_key, format_name=o.format_name, encoding=o.encoding,
                key_ascii=o.key_ascii, interactive=not o.force)


        if o.duplicates:
            my.check_duplicates(mode=o.mode)

        savebib(my)


    # filecheck
    # =====
    filecheckp = subparsers.add_parser('filecheck', description='check attached file(s)',
        parents=[cfg, namefmt])
    # filecheckp.add_argument('-f','--force', action='store_true',
    #     help='do not ask before performing actions')

    # action on files
    filecheckp.add_argument('-r','--rename', action='store_true',
        help='rename files')
    filecheckp.add_argument('-c','--copy', action='store_true',
        help='in combination with --rename, keep a copy of the file in its original location')

    # various metadata and duplicate checks
    filecheckp.add_argument('--metadata-check', action='store_true',
        help='parse pdf metadata and check against metadata (currently doi only)')

    filecheckp.add_argument('--hash-check', action='store_true',
        help='check file hash sum to remove any duplicates')

    filecheckp.add_argument('-d', '--delete-broken', action='store_true',
        help='remove file entry if the file link is broken')

    filecheckp.add_argument('--fix-mendeley', action='store_true',
        help='fix a Mendeley bug where the leading "/" is omitted.')

    filecheckp.add_argument('--force', action='store_true', help='no interactive prompt, strictly follow options')
    # filecheckp.add_argument('--search-for-files', action='store_true',
    #     help='search for missing files')
    # filecheckp.add_argument('--searchdir', nargs='+',
    #     help='search missing file link for existing bibtex entries, based on doi')
    # filecheckp.add_argument('-D', '--delete-free', action='store_true',
        # help='delete file which is not associated with any entry')
    # filecheckp.add_argument('-a', '--all', action='store_true', help='--hash and --meta')

    def filecheckcmd(o):
        set_nameformat_config_from_cmd(o)

        my = Biblio.load(config.bibtex, config.filesdir)

        # fix ':home' entry as saved by Mendeley
        for e in my.entries:
            entry_filecheck(e, delete_broken=o.delete_broken, fix_mendeley=o.fix_mendeley,
                check_hash=o.hash_check, check_metadata=o.metadata_check, interactive=not o.force, relative_to=my.relative_to)

        if o.rename:
            my.rename_entries_files(o.copy)

        savebib(my)

    # list
    # ======
    listp = subparsers.add_parser('list', description='list (a subset of) entries',
        parents=[cfg])

    mgrp = listp.add_mutually_exclusive_group()
    mgrp.add_argument('--strict', action='store_true', help='exact matching - instead of substring (only (*): title, author, abstract)')
    mgrp.add_argument('--fuzzy', action='store_true', help='fuzzy matching - instead of substring (only (*): title, author, abstract)')
    listp.add_argument('--fuzzy-ratio', type=int, default=FUZZY_RATIO, help='threshold for fuzzy matching of title, author, abstract (default:%(default)s)')
    listp.add_argument('--similarity', choices=['EXACT','GOOD','FAIR','PARTIAL','FUZZY'], default=DEFAULT_SIMILARITY, help='duplicate testing (default:%(default)s)')
    listp.add_argument('--invert', action='store_true')

    grp = listp.add_argument_group('search')
    grp.add_argument('-a','--author', nargs='+', help='any of the authors (*)')
    grp.add_argument('--first-author', nargs='+')
    grp.add_argument('-y','--year', nargs='+')
    grp.add_argument('-t','--title', help='title (*)')
    grp.add_argument('--abstract', help='abstract (*)')
    grp.add_argument('--key', nargs='+')
    grp.add_argument('--doi', nargs='+')


    grp = listp.add_argument_group('check')
    grp.add_argument('--duplicates-key', action='store_true', help='list key duplicates only')
    grp.add_argument('--duplicates-doi', action='store_true', help='list doi duplicates only')
    grp.add_argument('--duplicates-tit', action='store_true', help='list tit duplicates only')
    grp.add_argument('--duplicates', action='store_true', help='list all duplicates (see --similarity)')
    grp.add_argument('--has-file', action='store_true')
    grp.add_argument('--no-file', action='store_true')
    grp.add_argument('--broken-file', action='store_true')
    grp.add_argument('--review-required', action='store_true', help='suspicious entry (invalid dois, missing field etc.)')

    grp = listp.add_argument_group('formatting')
    mgrp = grp.add_mutually_exclusive_group()
    mgrp.add_argument('-k','--key-only', action='store_true')
    mgrp.add_argument('-l', '--one-liner', action='store_true', help='one liner')
    mgrp.add_argument('-f', '--field', nargs='+', help='specific field(s) only')
    grp.add_argument('--no-key', action='store_true')

    grp = listp.add_argument_group('action on listed results (pipe)')
    grp.add_argument('--delete', action='store_true')
    grp.add_argument('--edit', action='store_true', help='interactive edit text file with entries, and re-insert them')
    grp.add_argument('--fetch', action='store_true', help='fetch and fix metadata')
    # grp.add_argument('--merge-duplicates', action='store_true')

    def listcmd(o):
        import fnmatch   # unix-like match

        my = Biblio.load(config.bibtex, config.filesdir)
        entries = my.db.entries

        if o.fuzzy:
            from rapidfuzz import fuzz

        def match(word, target, fuzzy=False, substring=False):
            if isinstance(target, list):
                return any([match(word, t, fuzzy, substring) for t in target])

            if fuzzy:
                res = fuzz.token_set_ratio(word, target, score_cutoff=o.fuzzy_ratio) > o.fuzzy_ratio
            elif substring:
                res = target.lower() in word.lower()
            else:
                res = fnmatch.fnmatch(word.lower(), target.lower())

            return res if not o.invert else not res


        def longmatch(word, target):
            return match(word, target, fuzzy=o.fuzzy, substring=not o.strict)


        if o.review_required:
            if o.invert:
                entries = [e for e in entries if not requiresreview(e)]
            else:
                entries = [e for e in entries if requiresreview(e)]
                for e in entries:
                    if 'doi' in e and not isvaliddoi(e['doi']):
                        e['doi'] = bcolors.FAIL + e['doi'] + bcolors.ENDC
        if o.has_file:
            entries = [e for e in entries if e.get('file','')]
        if o.no_file:
            entries = [e for e in entries if not e.get('file','')]
        if o.broken_file:
            entries = [e for e in entries if e.get('file','') and any([not os.path.exists(f) for f in parse_file(e['file'], relative_to=my.relative_to)])]


        if o.doi:
            entries = [e for e in entries if 'doi' in e and match(e['doi'], o.doi)]
        if o.key:
            entries = [e for e in entries if 'ID' in e and match(e['ID'], o.key)]
        if o.year:
            entries = [e for e in entries if 'year' in e and match(e['year'], o.year)]
        if o.first_author:
            first_author = lambda field : family_names(field)[0]
            entries = [e for e in entries if 'author' in e and match(firstauthor(e['author']), o.author)]
        if o.author:
            author = lambda field : ' '.join(family_names(field))
            entries = [e for e in entries if 'author' in e and longmatch(author(e['author']), o.author)]
        if o.title:
            entries = [e for e in entries if 'title' in e and longmatch(e['title'], o.title)]
        if o.abstract:
            entries = [e for e in entries if 'abstract' in e and longmatch(e['abstract'], o.abstract)]

        _check_duplicates = lambda uniques, groups: uniques if o.invert else list(itertools.chain(*groups))

        # if o.duplicates_key or o.duplicates_doi or o.duplicates_tit or o.duplicates or o.duplicates_fuzzy:
        list_dup = list_uniques if o.invert else list_duplicates

        if o.duplicates_key:
            entries = list_dup(entries, key=my.key, issorted=True)
        if o.duplicates_doi:
            entries = list_dup(entries, key=lambda e:e.get('doi',''), filter_key=isvaliddoi)
        if o.duplicates_tit:
            entries = list_dup(entries, key=title_id)
        if o.duplicates:
            # QUESTION MARK: in latest HEAD before merge with @malfatti's PR, I used hard-coded "PARTIAL".
            # I think that's because we might need to be inclusive here, whereas the default is conservative (parameter used for several functions with possibly differing requirements).
            # (otherwise we'd have used the command-line option o.similarity, or possibly DEFAULT_SIMILARITY)
            # Might need to revise later (the question mark is from a review after a long time without use)
            eq = lambda a, b: a['ID'] == b['ID'] or are_duplicates(a, b, similarity="PARTIAL", fuzzy_ratio=o.fuzzy_ratio)
            entries = list_dup(entries, eq=eq)

        def nfiles(e):
            return len(parse_file(e.get('file',''), relative_to=my.relative_to))

        if o.no_key:
            key = lambda e: ''
        else:
            # key = lambda e: bcolors.OKBLUE+e['ID']+filetag(e)+':'+bcolors.ENDC
            key = lambda e: nfiles(e)*(bcolors.BOLD)+bcolors.OKBLUE+e['ID']+':'+bcolors.ENDC

        if o.edit:
            otherentries = [e for e in my.db.entries if e not in entries]
            try:
                entries = edit_entries(entries)
                my.db.entries = otherentries + entries
            except Exception as error:
                logger.error(str(error))
                return

            savebib(my)

        elif o.fetch:
            for e in entries:
                my.fix_entry(e, fix_doi=True, fix_key=True, fetch_all=True, interactive=True)
            savebib(my)

        elif o.delete:
            for e in entries:
                my.db.entries.remove(e)
            savebib(my)

        elif o.field:
            # entries = [{k:e[k] for k in e if k in o.field+['ID','ENTRYTYPE']} for e in entries]
            for e in entries:
                print(key(e),*[e.get(k, "") for k in o.field])
        elif o.key_only:
            for e in entries:
                print(e['ID'].encode('utf-8'))
        elif o.one_liner:
            for e in entries:
                tit = e.get('title', '')[:60]+ ('...' if len(e.get('title', ''))>60 else '')
                info = []
                if e.get('doi',''):
                    info.append('doi:'+e['doi'])
                n = nfiles(e)
                if n:
                    info.append(bcolors.OKGREEN+'file:'+str(n)+bcolors.ENDC)
                infotag = '('+', '.join(info)+')' if info else ''
                print(key(e), tit, infotag)
        else:
            print(format_entries(entries))


    # doi
    # ===
    doip = subparsers.add_parser('doi', description='parse DOI from PDF')
    doip.add_argument('pdf')
    doip.add_argument('--image', action='store_true', help='convert to image and use tesseract instead of pdftotext')

    def doicmd(o):
        print(extract_pdf_doi(o.pdf, image=o.image))

    # fetch
    # =====
    fetchp = subparsers.add_parser('fetch', description='fetch bibtex from DOI')
    fetchp.add_argument('doi')

    def fetchcmd(o):
        print(fetch_bibtex_by_doi(o.doi))


    # extract
    # ========
    extractp = subparsers.add_parser('extract', description='extract pdf metadata', parents=[loggingp])
    extractp.add_argument('pdf')
    extractp.add_argument('-n', '--word-count', type=int, default=200)
    extractp.add_argument('--fulltext', action='store_true', help='fulltext only (otherwise DOI-based)')
    extractp.add_argument('--scholar', action='store_true', help='use google scholar instead of default crossref for fulltext search')
    extractp.add_argument('--image', action='store_true', help='convert to image and use tesseract instead of pdftotext')

    def extractcmd(o):
        print(extract_pdf_metadata(o.pdf, search_doi=not o.fulltext, search_fulltext=True, scholar=o.scholar, minwords=o.word_count, max_query_words=o.word_count, image=o.image))
        # print(fetch_bibtex_by_doi(o.doi))

    # *** Pure OS related file checks ***

    # undo
    # ====
    undop = subparsers.add_parser('undo', parents=[cfg])

    def undocmd(o):
        back = backupfile(config.bibtex)
        tmp = config.bibtex + '.tmp'
        # my = :config.bibtex, config.filesdir)
        logger.info(config.bibtex+' <==> '+back)
        shutil.copy(config.bibtex, tmp)
        shutil.move(back, config.bibtex)
        shutil.move(tmp, back)
        # o.savebib()



    # git
    # ===
    gitp = subparsers.add_parser('git', description='git subcommand')
    gitp.add_argument('gitargs', nargs=argparse.REMAINDER)


    def gitcmd(o):
        try:
            out = sp.check_output(['git']+o.gitargs, cwd=config.gitdir)
            print(out.decode())
        except:
            gitp.error('failed to execute git command')


    o = parser.parse_args()

    # verbosity
    if getattr(o,'logging_level',None):
        logger.setLevel(o.logging_level)
    # modify disk state?
    if hasattr(o,'dry_run'):
        papers.config.DRYRUN = o.dry_run

    if o.cmd == 'status':
        return statuscmd(o)

    def check_install():

        if getattr(o, "bibtex", None) is not None:
            config.bibtex = o.bibtex
        if getattr(o, "filesdir", None) is not None:
            config.filesdir = o.filesdir
        if getattr(o, "absolute_paths", None) is not None:
            config.absolute_paths = o.absolute_paths

        install_doc = f"first execute `papers install --bibtex {config.bibtex or '...'} [ --local ]`"
        if not config.bibtex:
            print(f"--bibtex must be specified, or {install_doc}")
            parser.exit(1)
        elif not os.path.exists(config.bibtex):
            print(f'papers: error: no bibtex file found, do `touch {config.bibtex}` or {install_doc}')
            parser.exit(1)
        logger.info('bibtex: '+config.bibtex)
        logger.info('filesdir: '+config.filesdir)
        return True

    if o.cmd == 'install':
        installcmd(o)
    elif o.cmd == 'uninstall':
        uninstallcmd(o)
        print(config.status(verbose=True))
    elif o.cmd == 'add':
        check_install() and addcmd(o)
    elif o.cmd == 'check':
        check_install() and checkcmd(o)
    elif o.cmd == 'filecheck':
        check_install() and filecheckcmd(o)
    elif o.cmd == 'list':
        check_install() and listcmd(o)
    elif o.cmd == 'undo':
        check_install() and undocmd(o)
    elif o.cmd == 'git':
        check_install() and gitcmd(o)
    elif o.cmd == 'doi':
        doicmd(o)
    elif o.cmd == 'fetch':
        fetchcmd(o)
    elif o.cmd == 'extract':
        extractcmd(o)
    else:
        parser.print_help()
        parser.exit(1)
        # raise ValueError('this is a bug')


if __name__ == '__main__':
    main()
