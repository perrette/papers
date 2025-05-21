import os
from pathlib import Path
import shutil
import bisect
from unidecode import unidecode as unicode_to_ascii
import bibtexparser
from bibtexparser.customization import convert_to_unicode

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

from papers.duplicate import conflict_resolution_on_insert, entry_diff, merge_files, check_duplicates

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
    #     logger.warning('simplify string: failed to remove latex: '+str(error))
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
            db = bibtexparser.bibdatabase.BibDatabase()
        elif not isinstance(db, bibtexparser.bibdatabase.BibDatabase):
            raise TypeError('db must be of type BibDatabase')
        self.db = db
        self.nameformat = nameformat
        self.keyformat = keyformat
        self.similarity = similarity
        self.relative_to = os.path.sep if relative_to is None else relative_to
        self.sort()

    def move(self, file, newfile, copy=False, hardlink=False):
        return _move(file, newfile, copy=copy, dryrun=papers.config.DRYRUN, hardlink=hardlink)

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
    def load(cls, bibtex, filesdir, relative_to=None, **kw):
        # self.bibtex = bibtex
        bibtexs = open(bibtex).read()
        loaded_bib = cls(bibtexparser.loads(bibtexs), filesdir, relative_to=relative_to if relative_to is not None else os.path.dirname(bibtex), **kw)
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
        self.db.entries = sorted(self.db.entries, key=self.key)

    def index_sorted(self, entry):
        keys = [self.key(ei) for ei in self.db.entries]
        return bisect.bisect_left(keys, self.key(entry))

    def insert_entry(self, entry, update_key=False, check_duplicate=False, rename=False, copy=False, metadata={}, **checkopt):
        """
        """
        if metadata:
            files = self.get_files(entry) + self.get_files(metadata)
            self.set_files(metadata, files)

        if update_key:
            entry['ID'] = self.generate_key(entry)

        # additional checks on DOI etc...
        if check_duplicate:
            logger.debug('check duplicates : TRUE')
            return self.insert_entry_check(entry, update_key=update_key, rename=rename, copy=copy, **checkopt)
        else:
            logger.debug('check duplicates : FALSE')

        i = self.index_sorted(entry)  # based on current sort key (e.g. ID)

        if i < len(self.entries) and self.key(self.entries[i]) == self.key(entry):
            logger.info('key duplicate: '+self.key(self.entries[i]))

            if self.entries[i]["title"] == entry["title"]:
                logger.info('exact duplicate')
                return [ self.entries[i] ]

            if update_key:
                newkey = self.append_abc_to_key(entry)  # add abc
                logger.info('update key: {} => {}'.format(entry['ID'], newkey))
                entry['ID'] = newkey

            else:
                raise DuplicateKeyError('Key conflict. Try update_key is True or specify --key KEY explicitly')

        else:
            logger.info('new entry: '+self.key(entry))

        self.entries.insert(i, entry)

        if rename: self.rename_entry_files(entry, copy=copy)

        return [ entry ]

    def insert_entry_check(self, entry, update_key=False, mergefiles=True, on_conflict='i', rename=False, copy=False):
        duplicates = [e for e in self.entries if self.eq(e, entry)]

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

            if entry == candidate:
                logger.debug('exact duplicate')
                if rename: self.rename_entry_files(candidate, copy=copy)
                return [ entry ] # do nothing

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
                return [ entry ] # do nothing

            logger.debug('conflict resolution: '+on_conflict)
            resolved = conflict_resolution_on_insert(candidate, entry, mode=on_conflict)
            self.entries.remove(candidate) # maybe in resolved entries
            entries = []
            for e in resolved:
                entries.extend( self.insert_entry(e, update_key, rename=rename, copy=copy) )
            return entries


    def generate_key(self, entry):
        " generate a unique key not yet present in the record "
        keys = {self.key(e) for e in self.db.entries}
        key = self.keyformat(entry)
        if keys and key in keys: # and not isinstance(keys, set):
            key = append_abc(key, keys)
        return key

    def append_abc_to_key(self, entry):
        return append_abc(entry['ID'], keys={self.key(e) for e in self.entries})


    def set_files(self, entry, files, relative_to=None):
        entry['file'] = format_file(list(sorted(set(files), key=lambda f: files.index(f))), relative_to=relative_to or self.relative_to)
        # delete field if empty
        if not entry['file'].strip():
            del entry['file']

    def get_files(self, entry, relative_to=None):
        return parse_file(entry.get('file', ''), relative_to=relative_to or self.relative_to)

    def add_bibtex(self, bibtex, relative_to=None, attachments=None, convert_to_unicode=False, **kw):
        bib = bibtexparser.loads(bibtex)
        if convert_to_unicode:
            bib = bibtexparser.customization.convert_to_unicode(bib)
        entries = []
        for e in bib.entries:
            files = []
            if "file" in e:
                # make sure paths relative to other bibtex are inserted correctly
                files.extend(self.get_files(e, relative_to))
            if attachments:
                files.extend([os.path.abspath(f) for f in attachments])
            if files:
                self.set_files(e, files)

            entries.extend( self.insert_entry(e, **kw) )
        return entries


    def add_bibtex_file(self, file, **kw):
        bibtex = open(file).read()
        return self.add_bibtex(bibtex, relative_to=os.path.dirname(file), **kw)


    def fetch_doi(self, doi, **kw):
        bibtex = fetch_bibtex_by_doi(doi)
        kw["update_key"] = True  # fetched key is always updated
        return self.add_bibtex(bibtex, **kw)


    def add_pdf(self, pdf, attachments=None, search_doi=True, search_fulltext=True, scholar=False, doi=None, **kw):

        if str(pdf).startswith("http"):
            # if pdf is a URL, download it
            import requests, tempfile
            response = requests.get(pdf)
            if response.status_code == 200:
                pdf = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf').name
                with open(pdf, 'wb') as f:
                    f.write(response.content)
            else:
                raise ValueError(f"Failed to download PDF from {pdf}")

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

        self.set_files(entry, [os.path.abspath(f) for f in files])
        entry['ID'] = self.keyformat(entry)
        logger.debug('generated PDF key: '+entry['ID'])

        kw["update_key"] = True
        return self.insert_entry(entry, **kw)


    def scan_dir_iter(self, direc, search_doi=True, search_fulltext=True, **kw):

        for root, direcs, files in os.walk(direc):
            dirname = os.path.basename(root)
            if dirname.startswith('.'): continue
            if dirname.startswith('_'): continue

            # maybe a special entry directory?
            if os.path.exists(hidden_bibtex(root)):
                logger.debug('read from hidden bibtex')
                try:
                    entry = read_entry_dir(root, relative_to=self.relative_to)
                    yield from self.insert_entry(entry, **kw)
                except Exception:
                    logger.warning(root+'::'+str(error))
                continue

            for file in files:
                if file.startswith('.'):
                    continue
                path = os.path.join(root, file)
                try:
                    if file.endswith('.pdf'):
                        yield from self.add_pdf(path, search_doi=search_doi, search_fulltext=search_fulltext, **kw)
                    elif file.endswith('.bib'):
                        yield from self.add_bibtex_file(path, **kw)
                except Exception as error:
                    logger.warning(path+'::'+str(error))
                    continue

    def scan_dir(self, direc, **kw):
        " like scan_dir_iter but returns a list"
        return list(self.scan_dir_iter(direc, **kw))


    def format(self):
        return bibtexparser.dumps(self.db)

    def save(self, bibtex):
        if os.path.exists(bibtex):
            shutil.copy(bibtex, backupfile(bibtex))
        if self.relative_to not in (os.path.sep, None) and Path(self.relative_to).resolve() != Path(bibtex).parent.resolve():
            logger.warning("Saving bibtex file with relative paths may break links. Consider using `Biblio.update_file_path(Path(bibtex).parent)` before.")
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


    def rename_entry_files(self, e, copy=False, formatter=None, relative_to=None, hardlink=False):
        """ Rename files

        See `papers.filename.Format` class and REAMDE.md for infos.
        """

        if self.filesdir is None:
            raise ValueError('filesdir is None, cannot rename entries')

        files = self.get_files(e)
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
                # raise ValueError(file+': original file link is broken')
                logger.warning(file+': original file link is broken')
                newfile = file

            elif file != newfile:
                self.move(file, newfile, copy, hardlink=hardlink)
                # assert os.path.exists(newfile)
                # if not copy:
                #     assert not os.path.exists(file)
                count += 1

            newfiles = [newfile]
            self.set_files(e, newfiles, relative_to=relative_to)


        # several files: only rename container
        else:
            newdir = os.path.join(direc, newname)
            newfiles = []
            for file in files:
                newfile = os.path.join(newdir, os.path.basename(file))
                if not os.path.exists(file):
                    logger.warning(file+': original file link is broken')
                    newfile = file
                elif file != newfile:
                    self.move(file, newfile, copy, hardlink=hardlink)
                    # assert os.path.exists(newfile)
                    count += 1
                newfiles.append(newfile)
            self.set_files(e, newfiles, relative_to=relative_to)

            # create hidden bib entry for special dir
            bibname = hidden_bibtex(newdir)
            db = bibtexparser.bibdatabase.BibDatabase()
            db.entries.append(e)
            bibtex = bibtexparser.dumps(db)
            if not papers.config.DRYRUN:
                with open(bibname,'w') as f:
                    f.write(bibtex)

            # remove old direc if empty?
            direcs = list({os.path.dirname(file) for file in files})
            if len(direcs) == 1:
                leftovers = os.listdir(direcs[0])
                if not leftovers or len(leftovers) == 1 and leftovers[0] == os.path.basename(hidden_bibtex(direcs[0])):
                    logger.debug('remove tree: '+direcs[0])
                    if not papers.config.DRYRUN:
                        shutil.rmtree(direcs[0])
            else:
                logger.debug('some left overs, do not remove tree: '+direcs[0])

        # for f in parse_file(e['file'], self.relative_to):
        #     assert os.path.exists(f), f

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
                            logger.warning(e.get('ID','')+': '+k+': failed to encode: '+str(error))

        if fix_doi:
            if 'doi' in e and e['doi']:
                try:
                    doi = parse_doi('doi:'+e['doi'])
                except:
                    logger.warning(e.get('ID','')+': failed to fix doi: '+e['doi'])
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
                    logger.warning('...failed to fetch bibtex (doi): '+str(error))

            elif e.get('title','') and e.get('author','') and fetch_all:
                kw = {}
                kw['title'] = e['title']
                kw['author'] = ' '.join(family_names(e['author']))
                logger.info(e.get('ID','')+': fetch-all: '+str(kw))
                try:
                    bibtex = fetch_bibtex_by_fulltext_crossref('', **kw)
                except Exception as error:
                    logger.warning('...failed to fetch/update bibtex (all): '+str(error))

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
                logger.warning(e['ID']+': '+str(error)+': failed to convert latex symbols to unicode: '+file)

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
                logger.warning(error)

        # check existence
        if not os.path.exists(file):
            logger.warning(e['ID']+': "{}" does not exist'.format(file)+delete_broken*' ==> delete')
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
                logger.info(e['ID']+': file already exists (identical checksum): "{}"'.format(file))
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