# -*- coding: utf-8 -*-
from __future__ import print_function
import os, json, sys
import logging
# logging.basicConfig(level=logging.INFO)
import argparse
import subprocess as sp
import shutil
import bisect
import itertools
import six
import difflib

import bibtexparser

import myref
from myref.tools import (bcolors, move, extract_doi, fetch_bibtex_by_doi, isvaliddoi, checksum, extract_pdf_metadata)
from myref.config import config
from myref.conflict import (merge_files, merge_entries, parse_file, format_file,
    handle_merge_conflict, search_duplicates, choose_entry_interactive, unique)

DRYRUN = False
 

# Parse / format bibtex file entry
# ================================

def getentryfiles(e):
    'list of (fname, ftype) '
    files = e.get('file','').strip()
    return parse_file(files)


def setentryfiles(e, files, overwrite=True): #, interactive=True):
    if not overwrite:
        files = getentryfiles(e) + files
    e['file'] = format_file(files)



def format_entries(entries):
    db = bibtexparser.loads('')
    db.entries.extend(entries)
    return bibtexparser.dumps(db)
 

if six.PY2:
    _bloads = bibtexparser.loads 
    _bdumps = bibtexparser.dumps
    bibtexparser.loads = lambda s: _bloads(s.decode('utf-8'))
    bibtexparser.dumps = lambda db: _bdumps(db).encode('utf-8')


def hidden_bibtex(direc):
    " save metadata for a bundle of files "
    dirname = os.path.basename(direc)
    return os.path.join(direc, '.'+dirname+'.bib')


def read_entry_dir(self, direc, update_files=True):
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

    entry['file'] = format_file(files)
    return entry



def backupfile(bibtex):
    return os.path.join(os.path.dirname(bibtex), '.'+os.path.basename(bibtex)+'.backup')

class MyRef(object):
    """main config
    """
    def __init__(self, db, filesdir, key_field='ID'):
        self.filesdir = filesdir
        self.txt = '/tmp'
        # assume an already sorted list
        self.key_field = key_field
        if not isinstance(db, bibtexparser.bibdatabase.BibDatabase):
            raise TypeError('db must of type BibDatabase')
        self.db = db
        self.sort()

    @property
    def entries(self):
        return self.db.entries

    @classmethod
    def loads(cls, bibtex, filesdir):
        db = bibtexparser.loads(bibtex)
        return cls(db, filesdir)

    def dumps(self):
        return bibtexparser.dumps(self.db)

    @classmethod
    def load(cls, bibtex, filesdir):
        # self.bibtex = bibtex
        bibtexs = open(bibtex).read()
        return cls(bibtexparser.loads(bibtexs), filesdir)

    @classmethod
    def newbib(cls, bibtex, filesdir):
        assert not os.path.exists(bibtex)
        if os.path.dirname(bibtex) and not os.path.exists(os.path.dirname(bibtex)):
            os.makedirs(os.path.dirname(bibtex))
        open(bibtex,'w').write('')
        return cls.load(bibtex, filesdir)

    def key(self, e):
        return e[self.key_field].lower()

    def doi(self, e):
        return e.get('doi','')

    def validdoi(self, e):
        doi = self.doi(e)
        return doi if isvaliddoi(doi) else ''

    def sort(self):
        self.db.entries = sorted(self.db.entries, key=self.key)

    def set_sortkey(self, key_field):
        self.key_field = key_field
        self.sort()

    def index_sorted(self, entry):
        keys = [self.key(ei) for ei in self.db.entries]
        return bisect.bisect_left(keys, self.key(entry))


    def insert_entry(self, entry, on_conflict='r', mergefiles=True, 
        update_key=False, check_doi=True, interactive=True):
        """
        check : check whether key already exists
        on_conflict (key): 
            'a': append (for later handling)
            's': skip (do not insert new entry)
            'o': overwrite (newer wins...)
            Anything else: raise error
        mergefiles : if two entries are identical besides the 'file' field, just merge files

        Note that doi are not checked at this stage. Use merging / check tool later.
        ----
        """
        # additional checks on DOI
        if check_doi:
            self._entry_check_doi(entry, update_key=update_key, interactive=interactive)


        i = self.index_sorted(entry)  # based on current sort key (e.g. ID)

        if i < len(self.entries) and self.key(entry) == self.key(self.entries[i]):
            candidate = self.entries[i]
        else:
            candidate = None

        # the keys do not match, just insert at new position without further checking
        if not candidate:
            logging.info('new entry: '+self.key(entry))
            self.entries.insert(i, entry)

        # the keys match: see what needs to be done
        else:

            nofile = lambda e : {k:e[k] for k in e if k != 'file'}

            if entry == candidate:
                logging.info('entry already present: '+self.key(entry))

            # all files match besides 'file' ?
            elif mergefiles and nofile(entry) == nofile(candidate):
                logging.info('entry already present: '+self.key(entry))
                candidate['file'] = merge_files([candidate, entry])

            # some fields do not match
            else:
                msg = 'conflict: '+self.key(entry)
                action = ''

                if interactive:
                    ans = choose_entry_interactive([self.entries[i], entry],['m','a','d'],
                        ' or try (m)erging or (a)ppend new anyway or (d)elete')
                    if ans in list('mad'):
                        on_conflict = ans
                    else:
                        self.entries[i] = entry
                        return entry

                if on_conflict == 'o':
                    action = ' ==> overwrite'
                    self.entries[i] = entry         

                elif on_conflict == 's':
                    action = ' ==> skip'

                elif on_conflict == 'a':
                    action = ' ==> append'
                    self.entries.insert(i, entry)
                
                elif on_conflict == 'd':
                    action = ' ==> delete'
                    del self.entries[i]

                elif on_conflict == 'm':
                    action = ' ==> merge'
                    merged = merge_entries([self.entries[i], entry])
                    merged = handle_merge_conflict(merged)
                    self.entries[i] = merged

                else:
                    raise ValueError(msg)

                logging.warn(msg+action)

        return self.entries[i]


    def _entry_check_doi(self, entry, update_key=False, interactive=True):
        """check DOI duplicate, and update_key if desired, prior to insert entry
        """
        doi = self.validdoi(entry) # only consider valid dois
        key = self.key(entry) # 
        if doi:
            conflicting_doi = [e for e in self.entries 
                                    if self.doi(e) == doi and self.key(e) != key]
        else:
            conflicting_doi = []
 
        if conflicting_doi:
            candidate = conflicting_doi[0]
            msg = '!!! {}: insert conflict with existing doi: {} ({})'.format(
                self.key(entry), doi, candidate['ID'])
            logging.warn(msg)

            if not update_key and interactive:
                print('''Duplicates detected (same DOI). Keys are distinct. Choices:
(1) update key and merge (keep old): {k2} ==> {k}
(2) keep original keys (create duplicates)
(3) error/skip insert'''.format(k=candidate['ID'], k2=entry['ID']))
                ans = None
                while ans not in list('123'):
                    ans = raw_input('choice: ')
                if ans == '2': 
                    return 
                else:
                    update_key = ans == '1'

            if update_key:
                logging.info('update key {} ==> {}'.format(entry['ID'], candidate['ID']))
                entry['ID'] = candidate['ID']

            else:
                raise ValueError(msg)


    def add_bibtex(self, bibtex, **kw):
        bib = bibtexparser.loads(bibtex)
        for e in bib.entries:
            self.insert_entry(e, **kw)


    def add_bibtex_file(self, file, **kw):
        bibtex = open(file).read()
        return self.add_bibtex(bibtex, **kw)


    def fetch_doi(self, doi, **kw):
        bibtex = fetch_bibtex_by_doi(doi)
        self.add_bibtex(bibtex, **kw)


    def add_pdf(self, pdf, attachments=None, rename=False, copy=False, search_doi=True, search_fulltext=True, space_digit=True, scholar=False, **kw):
        
        bibtex = extract_pdf_metadata(pdf, search_doi, search_fulltext, space_digit=space_digit, scholar=scholar)

        bib = bibtexparser.loads(bibtex)
        entry = bib.entries[0]

        files = [pdf]
        if attachments:
            files += attachments

        entry['file'] = format_file([os.path.abspath(f) for f in files])
        kw.pop('update_key', True)
            # logging.warn('fetched key is always updated when adding PDF to existing bib')
        self.insert_entry(entry, update_key=True, **kw)

        if rename:
            self.rename_entry_files(entry, copy=copy)
            

    def scan_dir(self, direc, search_doi=True, search_fulltext=True, **kw):
        
        for root, direcs, files in os.walk(direc):
            dirname = os.path.basename(root)
            if dirname.startswith('.'): continue
            if dirname.startswith('_'): continue
        
            # maybe a special entry directory?
            if os.path.exists(hidden_bibtex(root)):
                try:
                    entry = read_entry_dir(root)
                    self.insert_entry(entry, **kw)
                except Exception:  
                    logging.warn(root+'::'+str(error))
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
                    logging.warn(path+'::'+str(error))
                    continue

    def generate_key(self, entry):
        " generate a unique key not yet present in the record "
        keys = [self.key(e) for e in self.db.entries]
        names = bibtexparser.customization.getnames(entry['author'].split(' and '))
        letters = list(' bcdefghijklmnopqrstuvwxyz')
        key = names[0].split(',')[0].strip().capitalize() + '_' + entry.get('year','XXXX')
        for l in letters:
            Key = (key+l).capitalize()
            if Key.lower() not in keys:
                break
        assert Key.lower() not in keys
        return Key


    def format(self):
        return bibtexparser.dumps(self.db)

    def save(self, bibtex):
        s = self.format()
        if os.path.exists(bibtex):
            shutil.copy(bibtex, backupfile(bibtex))
        open(bibtex, 'w').write(s)


    def merge_duplicates(self, key, interactive=True, fetch=False, force=False, 
        resolve={}, ignore_unresolved=True, mergefiles=True):
        """
        Find and merge duplicate keys. Leave unsolved keys.

        key: callable or key for grouping duplicates
        interactive: interactive solving of conflicts
        conflict: method in case of unresolved conflict
        **kw : passed to merge_entries
        """
        if isinstance(key, six.string_types):
            key = lambda e: e[key]

        self.db.entries, duplicates = search_duplicates(self.db.entries, key)


        if interactive and len(duplicates) > 0:
            raw_input(str(len(duplicates))+' duplicate(s) to remove (press any key) ')

        # attempt to merge duplicates
        conflicts = []
        for entries in duplicates:
            merged = merge_entries(entries, force=force)
            if mergefiles:
                merged['file'] = merge_files(entries)
            try:
                e = handle_merge_conflict(merged, fetch=fetch)
            except Exception as error:
                logging.warn(str(error))
                conflicts.append(unique(entries))
                continue
            self.insert_entry(e, mergefiles=mergefiles)


        if interactive and len(conflicts) > 0:
            raw_input(str(len(conflicts))+' conflict(s) to solve (press any key) ')

        # now deal with conflicts
        for entries in conflicts:

            if interactive:
                e = choose_entry_interactive(entries, 
                    extra=['s','d','q'], msg=' or (s)kip or (d)elete or (q)uit')
            
                if e == 's':
                    ignore_unresolved = True

                elif e == 'd':
                    continue

                elif e == 'q':
                    interactive = False
                    ignore_unresolved = True

                else:
                    self.insert_entry(e, mergefiles=mergefiles)
                    continue

            if ignore_unresolved:
                for e in entries:
                    self.insert_entry(e, mergefiles=mergefiles)
            else:
                raise ValueError('conflicting entries')


    def merge_duplicate_keys(self, **kw):
        return self.merge_duplicates(self.key, **kw)

    def _doi_key(self):
        """used in merge_duplicate_dois and to list duplicates"""
        counts = [0]
        def key(e):
            if isvaliddoi(e.get('doi','')):
                return e['doi']
            else:
                counts[0] += 1
                return counts[0]
        return key

    def merge_duplicate_dois(self, **kw):
        """merge entries with duplicate dois (exclude papers with no doi)
        """
        return self.merge_duplicates(self._doi_key(), **kw)


    def merge_entries(self, keys, **kw):
        """merge entries with the provided keys
        """
        def binary_key(e):
            return self.key(e) in keys
        return self.merge_duplicates(binary_key, **kw)


    def rename_entry_files(self, e, copy=False):

        files = getentryfiles(e)
        # newname = entrydir(e, root)
        direc = os.path.join(self.filesdir, e.get('year','0000'))

        if not files:
            logging.info('no files to rename')
            return

        autoname = lambda e: e['ID'].replace(':','-').replace(';','-') # ':' and ';' are forbidden in file name

        count = 0
        if len(files) == 1:
            file = files[0]
            base, ext = os.path.splitext(file)
            newfile = os.path.join(direc, autoname(e)+ext)
            if not os.path.exists(file):
                raise ValueError(file+': original file link is broken')
            elif file != newfile:
                move(file, newfile, copy)
                count += 1
            newfiles = [newfile]
            setentryfiles(e, newfiles)


        # several files: only rename container
        else:
            newdir = os.path.join(direc, autoname(e))
            newfiles = []
            for file in files:
                newfile = os.path.join(newdir, os.path.basename(file))
                if not os.path.exists(file):
                    raise ValueError(file+': original file link is broken')
                elif file != newfile:
                    move(file, newfile, copy)
                    count += 1
                newfiles.append(newfile)
            setentryfiles(e, newfiles)

            # create hidden bib entry for special dir
            bibname = hidden_bibtex(newdir)
            db = bibtexparser.loads('')
            db.entries.append(e)
            bibtex = bibtexparser.dumps(db)
            with open(bibname,'w') as f:
                f.write(bibtex)

            # remove old direc if empty?
            direcs = unique([os.path.dirname(file) for file in files])
            if len(direcs) == 1:
                leftovers = os.listdir(direcs[0])
                if not leftovers or len(leftovers) == 1 and leftovers[0] == os.path.basename(hidden_bibtex(direcs[0])):
                    logging.debug('remove tree: '+direcs[0])
                    shutil.rmtree(direcs[0])
            else:
                logging.debug('some left overs, do not remove tree: '+direcs[0])

        if count > 0:
            logging.info('renamed file(s): {}'.format(count))


    def rename_entries_files(self, copy=False):
        for e in self.db.entries:
            try:
                self.rename_entry_files(e, copy)
            except Exception as error:
                logging.error(str(error))
                continue


def entry_filecheck_metadata(e, file):
    ''' parse pdf metadata and compare with entry: only doi for now
    '''
    if 'doi' not in e:
        raise ValueError(e['ID']+': no doi, skip PDF parsing')

    try:
        doi = extract_doi(file)
    except Exception as error:
        raise ValueError(e['ID']+': failed to parse doi: "{}"'.format(file))
    if not isvaliddoi(doi):
        raise ValueError(e['ID']+': invalid parsed doi: '+doi)

    if doi.lower() != e['doi'].lower():
        raise ValueError(e['ID']+': doi: entry <=> pdf : {} <=> {}'.format(e['doi'].lower(), doi.lower()))


LATEX_TO_UNICODE = None

def latex_to_unicode(string):
    """ replace things like "{\_}" and "{\'{e}}'" with unicode characters _ and é
    """
    global LATEX_TO_UNICODE
    if LATEX_TO_UNICODE is None:
        import myref.unicode_to_latex as ul 
        LATEX_TO_UNICODE = {v.strip():k for k,v in six.iteritems(ul.unicode_to_latex)}
    return string.format(**LATEX_TO_UNICODE)




def entry_filecheck(e, delete_broken=False, fix_mendeley=False, 
    check_hash=False, check_metadata=False, interactive=True):

    if 'file' not in e:
        return
    
    if check_hash:
        import hashlib

    newfiles = []
    hashes = set()
    realpaths = set()
    fixed = {}

    for i, file in enumerate(parse_file(e['file'])):

        realpath = os.path.realpath(file)
        if realpath in realpaths:
            logging.info(e['ID']+': remove duplicate path: "{}"'.format(fixed.get(file, file)))
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
                logging.warn(e['ID']+': '+str(error)+': failed to convert latex symbols to unicode: '+file)

            # fix root (e.g. path starts with home instead of /home)
            dirname = os.path.dirname(file)
            candidate = os.path.sep + file
            if (not file.startswith(os.path.sep) and dirname # only apply when some directory name is specified
                and not os.path.exists(dirname) 
                and os.path.exists(os.path.dirname(candidate))): # simply requires that '/'+directory exists 
                # and os.path.exists(newfile)):
                    # logging.info('prepend "/" to file name: "{}"'.format(file))
                    file = candidate

            if old != file:
                logging.info(e['ID']+u': file name fixed: "{}" => "{}".'.format(old, file))
                fixed[old] = file # keep record of fixed files

        # parse PDF and check for metadata
        if check_metadata and file.endswith('.pdf'):
            try:
                entry_filecheck_metadata(e, file)
            except ValueError as error:
                logging.warn(error)

        # check existence
        if not os.path.exists(file):
            logging.warn(e['ID']+': "{}" does not exist'.format(file)+delete_broken*' ==> delete')
            if delete_broken:
                logging.info('delete file from entry: "{}"'.format(file))
                continue
            elif interactive:
                ans = raw_input('delete file from entry ? [Y/n] ')
                if ans.lower == 'y':
                    continue

        elif check_hash:
            # hash_ = hashlib.sha256(open(file, 'rb').read()).digest()
            hash_ = checksum(file) # a litftle faster
            if hash_ in hashes:
                logging.info(e['ID']+': file already exists (identical checksum): "{}"'.format(file))
                continue
            hashes.add(hash_)

        newfiles.append(file)

    e['file'] = format_file(newfiles)


def main():

    global DRYRUN

    global_config = config.file
    local_config = '.myrefconfig.json'

    if os.path.exists(local_config):
        config.file = local_config
    elif os.path.exists(global_config):
        config.file = global_config

    if os.path.exists(config.file):
        logging.debug('load config from: '+config.file)
        config.load()

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
    grp.add_argument('--filesdir', default=config.filesdir, 
        help='files directory (default: %(default)s)')
    grp.add_argument('--bibtex', default=config.bibtex,
        help='bibtex database (default: %(default)s)')
    grp.add_argument('--dry-run', action='store_true', 
        help='no PDF renaming/copying, no bibtex writing on disk (for testing)')

    # status
    # ======
    statusp = subparsers.add_parser('status', 
        description='view install status',
        parents=[cfg])
    statusp.add_argument('--no-check-files', action='store_true', help='faster, less info')
    statusp.add_argument('-v','--verbose', action='store_true', help='app status info')

    def statuscmd(o):
        if o.bibtex:
            config.bibtex = o.bibtex
        if o.filesdir is not None:
            config.filesdir = o.filesdir        
        print(config.status(check_files=not o.no_check_files, verbose=o.verbose))
        

    # install
    # =======

    installp = subparsers.add_parser('install', description='setup or update myref install',
        parents=[cfg])
    installp.add_argument('--reset-paths', action='store_true') 
    # egrp = installp.add_mutually_exclusive_group()
    installp.add_argument('--local', action='store_true', 
        help="""save config file in current directory (global install by default). 
        This file will be loaded instead of the global configuration file everytime 
        myref is executed from this directory. This will affect the default bibtex file, 
        the files directory, as well as the git-tracking option. Note this option does
        not imply anything about the actual location of bibtex file and files directory.
        """)
    installp.add_argument('--git', action='store_true', 
        help="""Track bibtex files with git. 
        Each time the bibtex is modified, a copy of the file is saved in a git-tracked
        global directory (see myref status), and committed. Note the original bibtex name is 
        kept, so that different files can be tracked simultaneously, as long as the names do
        not conflict. This option is mainly useful for backup purposes (local or remote).
        Use in combination with `myref git`'
        """) 
    installp.add_argument('--gitdir', default=config.gitdir, help='default: %(default)s')

    grp = installp.add_argument_group('status')
    # grp.add_argument('-l','--status', action='store_true')
    # grp.add_argument('-v','--verbose', action='store_true')
    # grp.add_argument('-c','--check-files', action='store_true')
    grp.add_argument('--no-check-files', action='store_true', help='faster, less info')
    # grp.add_argument('-v','--verbose', action='store_true', help='app status info')


    def installcmd(o):

        old = o.bibtex

        if config.git and not o.git and o.bibtex == config.bibtex:
            ans = raw_input('stop git tracking (this will not affect actual git directory)? [Y/n] ')
            if ans.lower() != 'y':
                o.git = True

        config.gitdir = o.gitdir

        if o.bibtex:
            config.bibtex = o.bibtex

        if o.filesdir is not None:
            config.filesdir = o.filesdir

        if o.reset_paths:
            config.reset()

        config.git = o.git

        # create bibtex file if not existing
        if not os.path.exists(o.bibtex):
            logging.info('create empty bibliography database: '+o.bibtex)
            open(o.bibtex,'w').write('')

        # create bibtex file if not existing
        if not os.path.exists(o.filesdir):
            logging.info('create empty files directory: '+o.filesdir)
            os.makedirs(o.filesdir)

        if not o.local and os.path.exists(local_config):
            logging.warn('Cannot make global install if local config file exists.')
            ans = None
            while ans not in ('1','2'):
                ans = raw_input('(1) remove local config file '+local_config+'\n(2) make local install\nChoice: ')
            if ans == '1':
                os.remove(local_config)
            else:
                o.local = True

        if not o.local:
            # save absolute path for global bibtex install
            config.bibtex = os.path.realpath(config.bibtex)
            config.filesdir = os.path.realpath(config.filesdir)
            config.gitdir = os.path.realpath(config.gitdir)

        if o.git and not os.path.exists(config._gitdir):
            config.gitinit()

        if o.local:
            logging.info('save local config file: '+local_config)
            config.file = local_config
        else:
            config.file = global_config
        config.save()

        print(config.status(check_files=not o.no_check_files, verbose=True))


    def savebib(my, o):
        logging.info(u'save '+o.bibtex)
        if DRYRUN:
            return
        if my is not None:
            my.save(o.bibtex)
        # commit when operated on the default bibtex file provided during installation
        # if config.git and os.path.samefile(config.bibtex, o.bibtex):
        if config.git and os.path.realpath(config.bibtex) == os.path.realpath(o.bibtex):
            config.bibtex = o.bibtex
            config.gitcommit()


    # add
    # ===
    addp = subparsers.add_parser('add', description='add PDF(s) or bibtex(s) to library',
        parents=[cfg])
    addp.add_argument('file', nargs='+')
    # addp.add_argument('-f','--force', action='store_true', help='disable interactive')

    grp = addp.add_argument_group('duplicate check')
    grp.add_argument('--no-check-doi', action='store_true', 
        help='disable DOI check (faster, create duplicates)')
    grp.add_argument('--no-merge-files', action='store_true', 
        help='distinct "file" field considered a conflict, all other things being equal')
    # grp.add_argument('--no-merge-files', action='store_true', 
        # help='distinct "file" field considered a conflict, all other things being equal')
    # addp.add_argument('--safe', action='store_true', 
    #     help='safe mode: always throw an error if anything strange is detected')
    grp.add_argument('-f', '--force', action='store_true', help='no interactive')
    grp.add_argument('-u','--update-key', action='store_true', 
        help='always update imported key in case an existing bibtex file with same DOI is detected')
    grp.add_argument('-m', '--mode', default='r', choices=['a', 'o', 'm', 's'],
        help='force mode: in case of conflict, the default is to raise an exception, \
        unless "mode" is set to (a)ppend anyway, (o)verwrite, (m)erge  or (s)skip key.')

    grp = addp.add_argument_group('directory scan')
    grp.add_argument('--recursive', action='store_true', 
        help='accept directory as argument, for recursive scan \
        of .pdf files (bibtex files are ignored in this mode')
    grp.add_argument('--ignore-errors', action='store_true', 
        help='ignore errors when adding multiple files')

    grp = addp.add_argument_group('pdf metadata')
    grp.add_argument('--no-query-doi', action='store_true', help='do not attempt to parse and query doi')
    grp.add_argument('--no-query-fulltext', action='store_true', help='do not attempt to query fulltext in case doi query fails')
    grp.add_argument('--scholar', action='store_true', help='use google scholar instead of crossref')

    grp = addp.add_argument_group('attached files')
    grp.add_argument('-a','--attachment', nargs='+', help=argparse.SUPPRESS) #'supplementary material')
    grp.add_argument('-r','--rename', action='store_true', 
        help='rename PDFs according to key')
    grp.add_argument('-c','--copy', action='store_true', 
        help='copy file instead of moving them')



    def addcmd(o):
        global DRYRUN
        import myref.tools
        DRYRUN = o.dry_run
        myref.tools.DRYRUN = o.dry_run

        if os.path.exists(o.bibtex):
            my = MyRef.load(o.bibtex, o.filesdir)
        else:
            my = MyRef.newbib(o.bibtex, o.filesdir)

        if len(o.file) > 1 and o.attachment:
            logging.error('--attachment is only valid for one added file')
            addp.exit(1)

        kw = {'on_conflict':o.mode, 'check_doi':not o.no_check_doi, 
            'mergefiles':not o.no_merge_files, 'update_key':o.update_key, 
            'interactive':not o.force}

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
                            scholar=o.scholar, 
                            **kw)

                else: # file.endswith('.bib'):
                    my.add_bibtex_file(file, **kw)

            except Exception as error:
                # print(error) 
                # addp.error(str(error))
                raise
                logging.error(str(error))
                if not o.ignore_errors:
                    if len(o.file) or (os.isdir(file) and o.recursive)> 1: 
                        logging.error('use --ignore to add other files anyway')
                    addp.exit(1)

        savebib(my, o)



    # merge
    # =====

    conflict = argparse.ArgumentParser(add_help=False)
    # conflict_options.add_argument('--merge', action='store_true', 
    #     help='merge non-conflicting entry fields')
    grp = conflict.add_argument_group('merge/conflict')
    # conflict.add_argument('--merge-files', action='store_true')
    # conflict_options.add_argument('-i', '--interactive', action='store_true')
    # g = conflict.add_mutually_exclusive_group()
    # g.add_argument('-D','--delete', action='store_true', help='delete conflicting entries')
    # g.add_argument('-w','--whatever', action='store_true', help='just pick one that looks good...')
    grp.add_argument('--fetch', action='store_true', help='fetch metadata from doi, if not conflicting')
    # grp.add_argument('-i','--interactive', action='store_true', help='interactive pick (the default)')
    grp.add_argument('--ignore', action='store_true', help='ignore unresolved conflicts')
    grp.add_argument('-f','--force', action='store_true', help='force merging')


    mergep = subparsers.add_parser('merge', description='merge duplicates', 
        parents=[cfg, conflict])
    # mergep.add_argument('-m', '--merge', action='store_true', help='merge duplicates')
    # mergep.add_argument('--merge', action='store_true', help='merge duplicates')
    # mergep.add_argument('--doi', action='store_true', help='DOI duplicate')
    mergep.add_argument('--keys', nargs='+', help='merge these keys')

    def mergecmd(o):
        my = MyRef.load(o.bibtex, o.filesdir)
        kw = dict(force=o.force, fetch=o.fetch, ignore_unresolved=o.ignore)
        my.merge_duplicate_keys(**kw)
        my.merge_duplicate_dois(**kw)
        if o.keys:
            my.merge_entries(o.keys, **kw)
        savebib(my, o)

    # check
    # =====
    filecheckp = subparsers.add_parser('filecheck', description='check attached file(s)',
        parents=[cfg])
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
        my = MyRef.load(o.bibtex, o.filesdir)

        # fix ':home' entry as saved by Mendeley
        for e in my.entries:
            entry_filecheck(e, delete_broken=o.delete_broken, fix_mendeley=o.fix_mendeley, 
                check_hash=o.hash_check, check_metadata=o.metadata_check, interactive=not o.force)

        if o.rename:
            my.rename_entries_files(o.copy)

        savebib(my, o)

    # list
    # ======
    listp = subparsers.add_parser('list', description='list (a subset of) entries',
        parents=[cfg])

    mgrp = listp.add_mutually_exclusive_group()
    mgrp.add_argument('--strict', action='store_true', help='exact matching - instead of substring (only (*): title, author, abstract)')
    mgrp.add_argument('--fuzzy', action='store_true', help='fuzzy matching - instead of substring (only (*): title, author, abstract)')
    listp.add_argument('--fuzzy-ratio', type=int, default=80, help='threshold for fuzzy matching of title, author, abstract (default:%(default)s)')
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
    grp.add_argument('--duplicates', action='store_true', help='list duplicates')
    grp.add_argument('--invalid-doi', action='store_true', help='invalid dois')
    grp.add_argument('--has-file', action='store_true')
    grp.add_argument('--no-file', action='store_true')
    grp.add_argument('--broken-file', action='store_true')
    # grp.add_argument('--invalid-file', action='store_true', help='invalid file')
    # grp.add_argument('--valid-file', action='store_true', help='valid file')

    grp = listp.add_argument_group('formatting')
    mgrp = grp.add_mutually_exclusive_group()
    mgrp.add_argument('-k','--key-only', action='store_true')
    mgrp.add_argument('-l', '--one-liner', action='store_true', help='one liner')
    mgrp.add_argument('-f', '--field', nargs='+', help='specific field(s) only')
    grp.add_argument('--no-key', action='store_true')

    grp = listp.add_argument_group('action on listed results (pipe)')
    grp.add_argument('--delete', action='store_true')
    grp.add_argument('--edit', action='store_true', help='interactive edit text file with entries, and re-insert them')
    # grp.add_argument('--merge-duplicates', action='store_true')

    def listcmd(o):
        import fnmatch   # unix-like match

        my = MyRef.load(o.bibtex, o.filesdir)
        entries = my.db.entries

        if o.fuzzy:
            from fuzzywuzzy import fuzz

        def match(word, target, fuzzy=False, substring=False):
            if isinstance(target, list):
                return any([match(word, t, fuzzy, substring) for t in target])

            if fuzzy:
                res = fuzz.token_set_ratio(word.lower(), target.lower()) > o.fuzzy_ratio
            elif substring:
                res = target.lower() in word.lower()
            else:
                res = fnmatch.fnmatch(word.lower(), target.lower())

            return res if not o.invert else not res


        def longmatch(word, target):
            return match(word, target, fuzzy=o.fuzzy, substring=not o.strict)


        def family_names(author_field):
            authors = bibtexparser.customization.getnames(author_field.split(' and '))
            return [nm.split(',')[0] for nm in authors]

        if o.invalid_doi:
            check = lambda e : 'doi' in e and not isvaliddoi(e['doi'])
            if o.invert:
                entries = [e for e in entries if not check(e)]
                for e in entries:
                    e['doi'] = bcolors.FAIL + e['doi'] + bcolors.ENDC
            else:
                entries = [e for e in entries if check(e)]


        if o.has_file:
            entries = [e for e in entries if e.get('file','')]
        if o.no_file:
            entries = [e for e in entries if not e.get('file','')]
        if o.broken_file:
            entries = [e for e in entries if e.get('file','') and any([not os.path.exists(f) for f in parse_file(e['file'])])]

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
            author = lambda field : u' '.join(family_names(field))
            entries = [e for e in entries if 'author' in e and longmatch(author(e['author']), o.author)]
        if o.title:
            entries = [e for e in entries if 'title' in e and longmatch(e['title'], o.title)]
        if o.abstract:
            entries = [e for e in entries if 'abstract' in e and longmatch(e['abstract'], o.abstract)]

        if o.duplicates:
            uniques, doi_duplicates = search_duplicates(entries, my._doi_key())
            _, key_duplicates = search_duplicates(uniques, lambda e: e.get('ID','').lower())
            entries = list(itertools.chain(*(doi_duplicates+key_duplicates)))

        if o.no_key:
            key = lambda e: ''
        else:
            key = lambda e: bcolors.OKBLUE+e['ID']+':'+bcolors.ENDC

        if o.edit:
            # write the listed entries to temporary file
            import tempfile
            # filename = tempfile.mktemp(prefix='.', suffix='.txt', dir=os.path.curdir)
            filename = tempfile.mktemp(suffix='.txt')
            db = bibtexparser.loads('')
            db.entries.extend(entries)
            entrystring = bibtexparser.dumps(db)
            with open(filename, 'w') as f:
                f.write(entrystring)
            res = os.system('%s %s' % (os.getenv('EDITOR'), filename))
            if res == 0:
                logging.info('sucessfully edited file, insert edited entries')
                my.db.entries = [e for e in my.entries if e not in entries]
                my.add_bibtex_file(filename)
                savebib(my, o)
            else:
                logging.error('error when editing entries file: '+filename)

        elif o.delete:
            for e in entries:
                my.db.entries.remove(e)
            savebib(my, o)

        elif o.field:
            # entries = [{k:e[k] for k in e if k in o.field+['ID','ENTRYTYPE']} for e in entries]
            for e in entries:
                print(key(e),*[e[k] for k in o.field])
        elif o.key_only:
            for e in entries:
                print(e['ID'].encode('utf-8'))
        elif o.one_liner:
            for e in entries:
                tit = e['title'][:60]+ ('...' if len(e['title'])>60 else '')
                doi = ('(doi:'+e['doi']+')') if e.get('doi','') else ''
                print(key(e), tit, doi)
        else:
            print(format_entries(entries))


    # doi
    # ===
    doip = subparsers.add_parser('doi', description='parse DOI from PDF')
    doip.add_argument('pdf')
    doip.add_argument('--space-digit', action='store_true', help='space digit fix')
    
    def doicmd(o):
        print(extract_doi(o.pdf, o.space_digit))

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

    def extractcmd(o):
        print(extract_pdf_metadata(o.pdf, search_doi=not o.fulltext, search_fulltext=True, scholar=o.scholar, minwords=o.word_count, max_query_words=o.word_count))
        # print(fetch_bibtex_by_doi(o.doi))

    # *** Pure OS related file checks ***

    # undo
    # ====
    undop = subparsers.add_parser('undo', parents=[cfg])

    def undocmd(o):
        back = backupfile(o.bibtex)
        tmp = o.bibtex + '.tmp'
        # my = MyRef(o.bibtex, o.filesdir)
        logging.info(o.bibtex+' <==> '+back)
        shutil.copy(o.bibtex, tmp)
        shutil.move(back, o.bibtex)
        shutil.move(tmp, back)
        savebib(None, o)

        

    # git
    # ===
    gitp = subparsers.add_parser('git', description='git subcommand')
    gitp.add_argument('gitargs', nargs=argparse.REMAINDER)


    def gitcmd(o):
        try:
            out = sp.check_output(['git']+o.gitargs, cwd=config.data)
            print(out)
        except:
            gitp.error('failed to execute git command')


    o = parser.parse_args()

    # verbosity
    if getattr(o,'logging_level',None):
        logging.getLogger().setLevel(o.logging_level)
    # modify disk state?
    if getattr(o,'dry_run', DRYRUN):
        DRYRUN = True
        import tools
        tools.DRYRUN = True

    if o.cmd == 'install':
        return installcmd(o)

    elif o.cmd == 'status':
        return statuscmd(o)

    def check_install():
        if not os.path.exists(o.bibtex):
            print('myref: error: no bibtex file found, use `myref install` or `touch {}`'.format(o.bibtex))
            parser.exit(1)
        logging.info('bibtex: '+o.bibtex)
        logging.info('filesdir: '+o.filesdir)
        return True

    if o.cmd == 'add':
        check_install() and addcmd(o)
    elif o.cmd == 'merge':
        check_install() and mergecmd(o)
    elif o.cmd == 'filecheck':
        check_install() and filecheckcmd(o)
    elif o.cmd == 'list':
        check_install() and listcmd(o)
    elif o.cmd == 'undo':
        check_install() and undocmd(o)
    elif o.cmd == 'git':
        gitcmd(o)
    elif o.cmd == 'doi':
        doicmd(o)
    elif o.cmd == 'fetch':
        fetchcmd(o)
    elif o.cmd == 'extract':
        extractcmd(o)
    else:
        raise ValueError('this is a bug')


if __name__ == '__main__':
    main()
