# -*- coding: utf-8 -*-
from __future__ import print_function
import os, json, sys
import logging
logging.basicConfig(level=logging.INFO)
import argparse
import subprocess as sp
import shutil
import bisect
import itertools
import six
import difflib

import bibtexparser

import myref
from myref.tools import (bcolors, move, check_filesdir, extract_doi, 
    fetch_bibtex_by_doi, isvaliddoi)
from myref.config import config
from myref.conflict import (merge_files, merge_entries, parse_file, format_file,
    handle_merge_conflict, search_duplicates, choose_entry_interactive, unique)

DRYRUN = False


def config_status(self, check_files=False, verbose=False):
    lines = []
    lines.append(bcolors.BOLD+'myref configuration'+bcolors.ENDC)
    if verbose:
        lines.append('* configuration file: '+self.file) 
        lines.append('* cache directory:    '+self.cache) 
        lines.append('* data directory:     '+self.data) 

    if not os.path.exists(self.filesdir):
        status = bcolors.WARNING+' (missing)'+bcolors.ENDC
    elif not os.listdir(self.filesdir):
        status = bcolors.WARNING+' (empty)'+bcolors.ENDC
    elif check_files:
        file_count, folder_size = check_filesdir(self.filesdir)
        status = bcolors.OKBLUE+" ({} files, {:.1f} MB)".format(file_count, folder_size/(1024*1024.0))+bcolors.ENDC
    else:
        status = ''

    files = self.filesdir
    lines.append('* files directory:    '+files+status) 

    if not os.path.exists(self.bibtex):
        status = bcolors.WARNING+' (missing)'+bcolors.ENDC 
    elif check_files:
        try:
            db = bibtexparser.load(open(self.bibtex))
            status = bcolors.OKBLUE+' ({} entries)'.format(len(db.entries))+bcolors.ENDC
        except:
            status = bcolors.FAIL+' (fails)'+bcolors.ENDC 
    else:
        status = ''
    lines.append('* bibtex:            '+self.bibtex+status)

    # if verbose:
    #     collections = self.collections()
    #     status = bcolors.WARNING+' none'+bcolors.ENDC if not collections else ''
    #     lines.append('* other collections:'+status)
    #     for i, nm in enumerate(collections):
    #         if i > 10:
    #             lines.append('    '+'({} more collections...)'.format(len(collections)-10))
    #             break
    #         status = ' (*)' if nm == self.collection else ''
    #         lines.append('    '+nm+status)



    return '\n'.join(lines)


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
                ans = raw_input('update key {} ==> {} ? [Y/n or (i)gnore] '.format(entry['ID'], candidate['ID']))
                if ans == 'i': 
                    return 
                update_key = ans.lower() == 'y'

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


    def add_pdf(self, pdf, attachments=None, rename=False, copy=False, space_digit=True, **kw):

        doi = extract_doi(pdf, space_digit=space_digit)
        logging.info('found doi:'+doi)

        # get bib tex based on doi
        bibtex = fetch_bibtex_by_doi(doi)
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
            

    def scan_dir(self, direc, **kw):
        for root, direcs, files in os.walk(direc):
            dirname = os.path.basename(root)
            if dirname.startswith('.'): continue
            if dirname.startswith('_'): continue
            for file in files:
                path = os.path.join(root, file)
                try:
                    if file.endswith('.pdf'): 
                        self.add_pdf(path, **kw)
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

        # make a git commit?
        if os.path.exists(os.path.join(config.data, '.git')):
            target = os.path.join(config.data, os.path.basename(bibtex))
            if bibtex != target:
                shutil.copy(bibtex, target)
            with open(os.devnull, 'w') as shutup:
                sp.call(['git','add',target], stdout=shutup, stderr=shutup, cwd=config.data)
                sp.call(['git','commit','-m', 'myref'+' '.join(sys.argv[1:])], stdout=shutup, stderr=shutup, cwd=config.data)


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
                    extra=['s','q'], msg=' or (s)kip or (q)uit')
            
                if e == 's':
                    ignore_unresolved = True

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
        direc = os.path.join(self.filesdir, e['year'])

        if not files:
            logging.info('no files to rename')
            return

        count = 0
        if len(files) == 1:
            file = files[0]
            base, ext = os.path.splitext(file)
            newfile = os.path.join(direc, e['ID']+ext)
            if not os.path.exists(file):
                raise ValueError(file+': original file link is broken')
            elif file != newfile:
                move(file, newfile, copy)
                count += 1
            newfiles = [newfile]

        # several files: only rename container
        else:
            newdir = os.path.join(direc, e['ID'])
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
        if count > 0:
            logging.info('renamed file(s): {}'.format(count))


    def rename_entries_files(self, copy=False):
        for e in self.db.entries:
            try:
                self.rename_entry_files(e, copy)
            except Exception as error:
                logging.error(str(error))
                continue

def main():

    if os.path.exists(config.file):
        config.load()

    main = argparse.ArgumentParser(description='library management tool')
    subparsers = main.add_subparsers(dest='cmd')

    cfg = argparse.ArgumentParser(add_help=False)
    grp = cfg.add_argument_group('config')
    grp.add_argument('--filesdir', default=config.filesdir, 
        help='files directory (default: %(default)s)')
    grp.add_argument('--bibtex', default=config.bibtex,
        help='bibtex database (default: %(default)s)')

    install_parser = subparsers.add_parser('install', description='setup or update myref install',
        parents=[cfg])
    install_parser.add_argument('--reset-paths', action='store_true') 

    grp = install_parser.add_argument_group('status')
    # grp.add_argument('-l','--status', action='store_true')
    grp.add_argument('-v','--verbose', action='store_true')
    grp.add_argument('-c','--check-files', action='store_true')


    def main_install(o):

        old = o.bibtex

        if o.bibtex:
            config.bibtex = o.bibtex
            config.save()

        if o.filesdir is not None:
            config.filesdir = o.filesdir
            config.save()

        if o.reset_paths:
            config.reset()
            config.save()

        # create bibtex file if not existing
        if not os.path.exists(o.bibtex):
            logging.info('create empty bibliography database: '+o.bibtex)
            open(o.bibtex,'w').write('')

        # create bibtex file if not existing
        if not os.path.exists(o.filesdir):
            logging.info('create empty files directory: '+o.filesdir)
            os.makedirs(o.filesdir)

        # if o.status or o.verbose:
        print(config_status(config, check_files=o.check_files, verbose=o.verbose))
        # print('(-h for usage)')
        # install_parser.print_usage()
        # else:
            # install_parser.print_help()


    parser = subparsers.add_parser('add', description='add PDF(s) or bibtex(s) to library',
        parents=[cfg])
    parser.add_argument('file', nargs='+')
    # parser.add_argument('-f','--force', action='store_true', help='disable interactive')

    grp = parser.add_argument_group('duplicate check')
    grp.add_argument('--no-check-doi', action='store_true', 
        help='disable DOI check (faster, create duplicates)')
    grp.add_argument('--no-merge-files', action='store_true', 
        help='distinct "file" field considered a conflict, all other things being equal')
    # grp.add_argument('--no-merge-files', action='store_true', 
        # help='distinct "file" field considered a conflict, all other things being equal')
    # parser.add_argument('--safe', action='store_true', 
    #     help='safe mode: always throw an error if anything strange is detected')
    grp.add_argument('-f', '--force', action='store_true', help='no interactive')
    grp.add_argument('-u','--update-key', action='store_true', 
        help='always update imported key in case an existing file with same DOI is detected')
    grp.add_argument('-m', '--mode', default='r', choices=['a', 'o', 'm', 's'],
        help='force mode: in case of conflict, the default is to raise an exception, \
        unless "mode" is set to (a)ppend anyway, (o)verwrite, (m)erge  or (s)skip key.')

    parser.add_argument('--recursive', action='store_true', 
        help='accept directory as argument, for recursive scan \
        of .pdf files (bibtex files are ignored in this mode')
    parser.add_argument('--ignore-errors', action='store_true', 
        help='ignore errors when adding multiple files')
    parser.add_argument('--dry-run', action='store_true', 
            help='no PDF renaming/copying, no bibtex writing on disk (for testing)')


    grp = parser.add_argument_group('attached files')
    grp.add_argument('-a','--attachment', nargs='+', help=argparse.SUPPRESS) #'supplementary material')
    grp.add_argument('-r','--rename', action='store_true', 
        help='rename PDFs according to key')
    grp.add_argument('-c','--copy', action='store_true', 
        help='copy file instead of moving them')



    def addpdf(o):
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
            parser.exit(1)

        kw = {'on_conflict':o.mode, 'check_doi':not o.no_check_doi, 
            'mergefiles':not o.no_merge_files, 'update_key':o.update_key, 
            'interactive':not o.force}

        for file in o.file:
            try:
                if os.path.isdir(file):
                    if o.recursive:
                        my.scan_dir(file, rename=o.rename, copy=o.copy, **kw)
                    else:
                        raise ValueError(file+' is a directory, requires --recursive to explore')

                elif file.endswith('.pdf'):
                    my.add_pdf(file, attachments=o.attachment, rename=o.rename, copy=o.copy, **kw)

                else: # file.endswith('.bib'):
                    my.add_bibtex_file(file, **kw)

            except Exception as error:
                # print(error) 
                # parser.error(str(error))
                raise
                logging.error(str(error))
                if not o.ignore_errors:
                    if len(o.file) or (os.isdir(file) and o.recursive)> 1: 
                        logging.error('use --ignore to add other files anyway')
                    parser.exit(1)

        if not o.dry_run:
            my.save(o.bibtex)



# def merge_entries(entries, method='strict', resolve={}, mergefiles=True, fields=None):
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

    subp = subparsers.add_parser('undo', parents=[cfg])

    def undo(o):
        back = backupfile(o.bibtex)
        tmp = o.bibtex + '.tmp'
        # my = MyRef(o.bibtex, o.filesdir)
        logging.info(o.bibtex+' <==> '+back)
        shutil.copy(o.bibtex, tmp)
        shutil.move(back, o.bibtex)
        shutil.move(tmp, back)


    subp = subparsers.add_parser('merge', description='merge duplicates', 
        parents=[cfg, conflict])
    # subp.add_argument('-m', '--merge', action='store_true', help='merge duplicates')
    # subp.add_argument('--merge', action='store_true', help='merge duplicates')
    # subp.add_argument('--doi', action='store_true', help='DOI duplicate')
    subp.add_argument('--keys', nargs='+', help='merge these keys')

    def merge_duplicate(o):
        my = MyRef.load(o.bibtex, o.filesdir)
        kw = dict(force=o.force, fetch=o.fetch, ignore_unresolved=o.ignore)
        my.merge_duplicate_keys(**kw)
        my.merge_duplicate_dois(**kw)
        if o.keys:
            my.merge_entries(o.keys, **kw)
        my.save(o.bibtex)

    parser = subparsers.add_parser('filter', description='filter (a subset of) entries',
        parents=[cfg])

    mgrp = parser.add_mutually_exclusive_group()
    mgrp.add_argument('--strict', action='store_true', help='exact matching')
    mgrp.add_argument('--fuzzy', action='store_true', help='fuzzy matching')
    parser.add_argument('--fuzzy-ratio', type=int, default=80, help='default:%(default)s')
    parser.add_argument('--invert', action='store_true')

    grp = parser.add_argument_group('search')
    grp.add_argument('-a','--author',nargs='+')
    grp.add_argument('-y','--year', nargs='+')
    grp.add_argument('-t','--title')
    grp.add_argument('--key', nargs='+')
    grp.add_argument('--doi', nargs='+')

    grp = parser.add_argument_group('problem')
    grp.add_argument('--invalid-doi', action='store_true', help='invalid dois')
    # grp.add_argument('--invalid-file', action='store_true', help='invalid file')
    # grp.add_argument('--valid-file', action='store_true', help='valid file')

    grp = parser.add_argument_group('formatting')
    mgrp = grp.add_mutually_exclusive_group()
    mgrp.add_argument('-k','--key-only', action='store_true')
    mgrp.add_argument('-l', '--list', action='store_true', help='one liner')
    mgrp.add_argument('-f', '--field', nargs='+', help='specific fields only')
    grp.add_argument('--no-key', action='store_true')


    grp = parser.add_argument_group('action')
    parser.add_argument('--delete', action='store_true')

    def listing(o):
        my = MyRef(o.bibtex, o.filesdir)
        entries = my.db.entries

        if o.fuzzy:
            from fuzzywuzzy import fuzz

        def match(word, target):
            if isinstance(target, list):
                return any([match(word, t) for t in target])
            if o.fuzzy:
                res = fuzz.token_set_ratio(word.lower(), target.lower()) > o.fuzzy_ratio
            elif o.strict:
                res = word.lower() == target.lower()
            else:
                res = target.lower() in word.lower()

            return not res if o.invert else res


        if o.invalid_doi:
            check = lambda e : 'doi' in e and not isvaliddoi(e['doi'])
            if o.invert:
                entries = [e for e in entries if not check(e)]
                for e in entries:
                    e['doi'] = bcolors.FAIL + e['doi'] + bcolors.ENDC
            else:
                entries = [e for e in entries if check(e)]

        if o.author:
            entries = [e for e in entries if 'author' in e and match(e['author'], o.author)]
        if o.year:
            entries = [e for e in entries if 'year' in e and match(e['year'], o.year)]
        if o.title:
            entries = [e for e in entries if 'title' in e and match(e['title'], o.title)]
        if o.doi:
            entries = [e for e in entries if 'doi' in e and match(e['doi'], o.doi)]
        if o.key:
            entries = [e for e in entries if match(e['ID'], o.key)]

        if o.no_key:
            key = lambda e: ''
        else:
            key = lambda e: bcolors.OKBLUE+e['ID']+':'+bcolors.ENDC

        if o.field:
            # entries = [{k:e[k] for k in e if k in o.field+['ID','ENTRYTYPE']} for e in entries]
            for e in entries:
                print(key(e),*[e[k] for k in o.field])
        elif o.key_only:
            for e in entries:
                print(e['ID'])
        elif o.list:
            for e in entries:
                tit = e['title'][:60]+ ('...' if len(e['title'])>60 else '')
                doi = ('(doi:'+e['doi']+')') if e.get('doi','') else ''
                print(key(e), tit, doi)
        elif o.delete:
            for e in entries:
                my.db.entries.remove(e)
            my.save(o.bibtex)
        else:
            print(format_entries(entries))


    # parser.add_argument_group

    parser = subparsers.add_parser('doi', description='parse DOI from PDF')
    parser.add_argument('pdf')
    parser.add_argument('--space-digit', action='store_true', help='space digit fix')

    parser = subparsers.add_parser('fetch', description='fetch bibtex from DOI')
    parser.add_argument('doi')

    gitp = subparsers.add_parser('git', description='git subcommand')
    gitp.add_argument('gitargs', nargs=argparse.REMAINDER)


    o = main.parse_args()

    # o.bibtex = config.bibtex
    # o.filesdir = config.filesdir

    if o.cmd == 'install':
        return main_install(o)

    def check_install():
        if not os.path.exists(o.bibtex):
            print('myref: error: no bibtex file found, use `myref install`')
            main.exit(1)

    if o.cmd == 'add':
        check_install()
        addpdf(o)
    elif o.cmd == 'merge':
        check_install()
        merge_duplicate(o)
    elif o.cmd == 'undo':
        check_install()
        undo(o)
    elif o.cmd == 'filter':
        check_install()
        listing(o)
    elif o.cmd == 'git':
        check_install()
        try:
            out = sp.check_output(['git']+o.gitargs, cwd=config.data)
            print(out)
        except:
            gitp.error('failed to execute git command')
    elif o.cmd == 'doi':
        print(extract_doi(o.pdf, o.space_digit))
    elif o.cmd == 'fetch':
        print(fetch_bibtex_by_doi(o.doi))
    else:
        raise ValueError('this is a bug')


if __name__ == '__main__':
    main()
