# -*- coding: utf-8 -*-
from __future__ import print_function
import os, json
import logging
logging.basicConfig(level=logging.INFO)
import argparse
import subprocess as sp
import shutil
import re
import bisect
import itertools
import six
import six.moves.urllib.request

import bibtexparser


DRYRUN = False


# Parse / format bibtex file entry
# ================================

def _parse_file(file):
    """ parse a single file entry
    """
    sfile = file.split(':')
    
    if len(sfile) == 1:  # no ':'
        path, type = file, ''

    elif len(sfile) == 2:
        path, type = sfile

    elif len(sfile) == 3:
        basename, path, type = sfile

    else:
        raise ValueError('unknown "file" format: file')

    return path


def _format_file(file, type=None):
    if not type:
        type = os.path.splitext(file)[1].strip('.')
    return ':'+file+':'+type


def parse_file(file):
    if not file:
        return []
    else:
        return [_parse_file(f) for f in file.split(';')]


def format_file(file_types):
    return ';'.join([_format_file(f) for f in file_types])


def getentryfiles(e):
    'list of (fname, ftype) '
    files = e.get('file','').strip()
    return parse_file(files)


def setentryfiles(e, files, overwrite=True): #, interactive=True):
    if not overwrite:
        files = getentryfiles(e) + files
    e['file'] = format_file(files)


# move / copy

def move(f1, f2, copy=False):
    dirname = os.path.dirname(f2)
    if not os.path.exists(dirname):
        logging.info('create directory: '+dirname)
        os.makedirs(dirname)
    if copy:
        cmd = 'cp {} {}'.format(f1, f2)
        logging.info(cmd)
        if not DRYRUN:
            shutil.copy(f1, f2)
    else:
        cmd = 'mv {} {}'.format(f1, f2)
        logging.info(cmd)
        if not DRYRUN:
            shutil.move(f1, f2)



# PDF parsing / crossref requests
# ===============================

def readpdf(pdf, first=None, last=None, keeptxt=False):
    txtfile = pdf.replace('.pdf','.txt')
    # txtfile = os.path.join(os.path.dirname(pdf), pdf.replace('.pdf','.txt'))
    if True: #not os.path.exists(txtfile):
        # logging.info(' '.join(['pdftotext','"'+pdf+'"', '"'+txtfile+'"']))
        cmd = ['pdftotext']
        if first is not None: cmd.extend(['-f',str(first)])
        if last is not None: cmd.extend(['-l',str(last)])
        cmd.append(pdf)
        sp.check_call(cmd)
    else:
        logging.info('file already present: '+txtfile)
    txt = open(txtfile).read()
    if not keeptxt:
        os.remove(txtfile)
    return txt


def extract_doi(pdf, space_digit=True):
    txt = readpdf(pdf, first=1, last=1)

    try:
        doi = parse_doi(txt, space_digit=space_digit)

    except ValueError:
        # sometimes first page is blank
        txt = readpdf(pdf, first=2, last=2)
        doi = parse_doi(txt, space_digit=space_digit)

    return doi

def parse_doi(txt, space_digit=False):
    # cut the reference part...

    # doi = r"10\.\d\d\d\d/[^ ,]+"  # this ignore line breaks
    doi = r"10\.\d\d\d\d/.*?"

    # sometimes an underscore is converted as space
    if space_digit:
        doi += r"[ \d]*"  # also accept empty space followed by digit

    # expression ends with a comma, empty space or newline
    stop = r"[, \n]"

    # expression starts with doi:
    prefixes = ['doi:', 'doi: ', 'doi ', 'dx\.doi\.org/', 'doi/']
    prefix = '[' + '|'.join(prefixes) + ']' # match any of those

    # full expression, capture doi as a group
    regexp = prefix + "(" + doi + ")" + stop

    matches = re.compile(regexp).findall(' '+txt.lower()+' ')

    if not matches:
        raise ValueError('parse_doi::no matches')

    match = matches[0]

    # clean expression
    doi = match.replace('\n','').strip('.')

    if space_digit:
        doi = doi.replace(' ','_')

    # quality check 
    assert len(doi) > 8, 'failed to extract doi: '+doi

    return doi 


def isvaliddoi(doi):
    try:
        doi2 = parse_doi(doi)
    except:
        return False
    return doi == doi2


def ask_doi(max=3):
    doi = raw_input('doi : ')
    count = 1
    while not isvaliddoi(doi):
        count += 1
        if count > max:
            raise ValueError('invalid doi: '+doi)
        doi = raw_input('Valid DOI looks like 10.NNNN/... Please try again. doi : ')
    return doi


def cached(file):
    def decorator(fun):
        if os.path.exists(file):
            cache = json.load(open(file))
        else:
            cache = {}
        def decorated(doi):
            if doi in cache:
                return cache[doi]
            else:
                res = cache[doi] = fun(doi)
                if not DRYRUN:
                    json.dump(cache, open(file,'w'))
            return res
        return decorated
    return decorator


@cached('.crossref-bibtex.json')
def fetch_bibtex_by_doi(doi):
    url = "http://api.crossref.org/works/"+doi+"/transform/application/x-bibtex"
    response = six.moves.urllib.request.urlopen(url)
    bibtex = response.read()
    if six.PY3:
        bibtex = bibtex.decode()
    return bibtex.strip()

@cached('.crossref.json')
def fetch_json_by_doi(doi):
    url = "http://api.crossref.org/works/"+doi+"/transform/application/json"
    response = six.moves.urllib.request.urlopen(url)
    jsontxt = response.read()
    if six.PY3:
        jsontxt = jsontxt.decode()
    return jsontxt.dumps(json)


def json_to_bibtex(js):
    raise NotImplementedError()

def bibtex_to_json(js):
    raise NotImplementedError()

# main config
# ===========
class ConflictError(ValueError):
    pass


def unique(entries):
    entries_ = []
    for e in entries:
        if e not in entries_:
            entries_.append(e)
    return entries_


class bcolors:
    # https://stackoverflow.com/a/287944/2192272
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def choose_entry_interactive(entries, extra=[], msg=''):
    db = bibtexparser.loads('')
    db.entries.append({})

    merged = merge_entries(entries).resolve()
    conflicting_fields = [k for k in merged if isinstance(merged[k], ConflictingField)]

    for i, entry in enumerate(entries):
        db.entries[0] = entry
        string = bibtexparser.dumps(db)
        # color the conflicting fields
        for k in conflicting_fields:
            string = string.replace(entry[k], bcolors.FAIL+entry[k]+bcolors.ENDC)

        print(bcolors.OKBLUE+'* ('+str(i+1)+')'+bcolors.ENDC+'\n'+string)
    entry_choices = [str(i+1) for i in range(len(entries))]
    choices = entry_choices + extra
    i = 0
    choices_msg = ", ".join(['('+e+')' for e in entry_choices])
    while (i not in choices):
        i = raw_input('{}pick entry in {}{}{}\n>>> '.format(bcolors.OKBLUE,choices_msg,msg, bcolors.ENDC))
    if i in entry_choices:
        return entries[int(i)-1]
    else:
        return i


def best_entry(entries, fields=None):
    """keep the best entry of a list of entries

    strategy:
    - filter out exact duplicate
    - keep fied with non-zero ID
    - for each field in fields, keep the entry where this field is documented (doi first)
    - keep the entry with the smallest ID
    """
    if len(entries) == 0:
        raise ValueError('at least one entry is required')

    # keep unique entries
    entries = unique(entries)

    if len(entries) == 1:
        return entries

    # pick the entry with one of preferred fields
    if fields is None:
        fields = ['ID', 'doi','author','year','title']

    for f in fields:
        if any([e.get(f,'') for e in entries]):
            entries = [e for e in entries if e.get(f,'')]
            if len(entries) == 1:
                return entries

    # just pick one, based on the smallest key
    e = entries[0]
    for ei in entries[1:]:
        if ei['ID'] < e['ID']:
            e = ei

    return e


def merge_files(entries):
    files = []
    for e in entries:
        for f in parse_file(e.get('file','')):
            if f not in files:
                files.append(f)
    return format_file(files)


def smallest_key(entries):
    keys = [e['ID'] for e in entries if e.get('ID','')]
    if not keys:
        return ''
    return min(keys)


class ConflictingField(object):
    def __init__(self, choices=[]):
        self.choices = choices

    def resolve(self, strict=True, force=False):
        if force: 
            strict = False
        choices = self.choices if strict else [v for v in self.choices if v]

        if len(choices) == 1 or force:
            return choices[0]
        else:
            return self


class MergedEntry(dict):

    def isresolved(self):
        return not any([isinstance(self[k], ConflictingField) for k in self])

    def resolve(self, strict=True, force=False):
        for k in self:
            if isinstance(self[k], ConflictingField):
                self[k] = self[k].resolve(strict, force)

        return dict(self) if self.isresolved() else self


def merge_entries(entries, strict=True, force=False):
    merged = MergedEntry() # dict
    for e in entries:
        for k in e:
            if k not in merged:
                merged[k] = ConflictingField([])
            if e[k] not in merged[k].choices:
                merged[k].choices.append(e[k])
    return merged.resolve(strict, force)


def handle_merge_conflict(merged, fetch=False, force=False):
    
    if not isinstance(merged, MergedEntry):
        return merged  # all good !

    if fetch:
        try:
            fix_fetch_entry_metadata(merged)
        except Exception as error:
            if not force: 
                raise
            else:
                logging.warn('failed to fetch metadata: '+str(error))

    if force:
        merged = merged.resolve(force=True)

    if isinstance(merged, MergedEntry):
        fields = [k for k in merged if isinstance(merged[k], ConflictingField)]
        raise ValueError('conflicting entries for fields: '+str(fields))

    return merged


def fix_fetch_entry_metadata(entry):
    assert entry.get('doi',''), 'missing DOI'
    assert not isinstance(entry['doi'], MergedEntry), \
        'conflicting doi: '+str(entry['doi'].choices)
    assert isvaliddoi(entry['doi']), 'invalid DOI' 
    bibtex = fetch_bibtex_by_doi(entry['doi'])
    bib = bibtexparser.loads(bibtex)
    e = bib.entries[0]
    entry.update({k:e[k] for k in e if k != 'file' and k != 'ID'})

   

def search_duplicates(entries, key=None, issorted=False):
    """search for duplicates

    returns:
    - unique_entries : list (entries for which no duplicates where found)
    - duplicates : list of list (groups of duplicates)
    """
    if not issorted:
        entries = sorted(entries, key=key)
    duplicates = []
    unique_entries = []
    for e, g in itertools.groupby(entries, key):
        group = list(g)
        if len(group) == 1:
            unique_entries.append(group[0])
        else:
            duplicates.append(group)
    return unique_entries, duplicates


def format_entries(entries):
    db = bibtexparser.loads('')
    db.entries.extend(entries)
    return format_db(db)
 

def format_db(db):
    """utf-8 encode of bibtexparser dump
    """
    s = bibtexparser.dumps(db)
    if six.PY2:
        s = s.encode('utf-8')
    return s


class MyRef(object):
    """main config
    """
    def __init__(self, bibtex, filesdir, key_field='ID'):
        self.filesdir = filesdir
        self.txt = '/tmp'
        self.bibtex = bibtex
        bibtexs = open(bibtex).read()
        if six.PY2:
            bibtexs = bibtexs.decode('utf-8')
        self.db = bibtexparser.loads(bibtexs)
        # assume an already sorted list
        self.key_field = key_field
        self.sort()

    @classmethod
    def newbib(cls, bibtex, filesdir):
        assert not os.path.exists(bibtex)
        open(bibtex,'w').write('')
        return cls(bibtex, filesdir)

    def key(self, e):
        return e[self.key_field].lower()

    def sort(self):
        self.db.entries = sorted(self.db.entries, key=self.key)

    def locate_doi(self, doi):
        assert doi
        for i, entry in enumerate(self.db.entries):
            if doi == entry.get('doi',''):
                return i 
        return len(self.db.entries)

    def insert_entry(self, entry, check=True, overwrite=False, merge=False, 
        strict=True, force=False, interactive=True, mergefiles=True):
        """
        check : check whether key already exists
        overwrite : overwrite existing entry?
        merge : merge with existing entry?
        force : never mind conflicting fields when merging
        """
        keys = [self.key(ei) for ei in self.db.entries]
        i = bisect.bisect_left(keys, self.key(entry))

        if not check:
            self.db.entries.insert(i, entry)
            return entry

        samekey = False
        samedoi = False

        if i < len(keys):
            # check for key duplicate
            if keys[i] == self.key(entry):
                samekey = True 
            # check for doi duplicate
            elif 'doi' in entry and isvaliddoi(entry['doi']):
                j = self.locate_doi(entry['doi'])
                if j < len(self.db.entries):
                    samedoi = True
                    i = j

        if samekey or samedoi:
            msg_extra = (overwrite*' => overwrite') or (merge*' => merge')
            if samekey:
                logging.info('entry key already present: '+self.key(entry)+msg_extra)
            else:
                logging.info('entry DOI already present: '+self.key(entry)+msg_extra)

            duplicates = [self.db.entries[i], entry]

            if overwrite:
                if not samekey and not force:
                    tmpl = 'entry key will be replaced {}{} >>> {}{}. Continue? (y/n) '
                    ans = raw_input(tmpl.format(bcolors.WARNING, self.db.entries[i]['ID'], 
                        entry['ID'], bcolors.ENDC))
                    if ans != 'y':
                        return

                if mergefiles:
                    self.db.entries[i]['file'] = merge_files(duplicates)

                self.db.entries[i] = entry
                return entry
            
            entry['ID'] = self.db.entries[i]['ID']

            if merge:
                merged = merge_entries(duplicates, strict=strict, force=force)
                if mergefiles:
                    merged['file'] = merge_files(duplicates)
                try:
                    e = handle_merge_conflict(merged)
                except Exception as error:
                    if not interactive:
                        raise
                    print()
                    print('!!! Failed to merge:',str(error),' !!!')
                    print()
                    e = choose_entry_interactive(unique(duplicates), extra=['q'], msg=' or (q)uit')
                    if e == 'q':
                        raise
                self.db.entries[i] = e


            else:
                if mergefiles:
                    self.db.entries[i]['file'] = merge_files(duplicates)
        
        else:
            logging.info('NEW ENTRY: '+self.key(entry))
            self.db.entries.insert(i, entry)

        return self.db.entries[i]



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

        entry['file'] = format_file(files)

        self.insert_entry(entry, **kw)

        if rename:
            self.rename_entry_files(entry, copy=copy)
            

    def scan_dir(self, direc, **kw):
        for root, direcs, files in os.walk(direc):
            dirname = os.path.basename(root)
            if dirname.startswith('.'): continue
            if dirname.startswith('_'): continue
            for file in files:
                try:
                    if file.endswith('.pdf'): 
                        self.add_pdf(file, **kw)
                    elif file.endswith('.bib'):
                        self.add_bibtex_file(file, **kw)
                except Exception as error:
                    logging.warn(file+'::'+str(error))
                    continue


    def format(self):
        return format_db(self.db)

    def save(self):
        s = self.format()
        open(self.bibtex, 'w').write(s)


    def merge_duplicates(self, key, interactive=True, fetch=False, force=False, 
        resolve={}, ignore_unresolved=True, mergefiles=True, strict=False):
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
            merged = merge_entries(entries, strict=strict, force=force)
            if mergefiles:
                merged['file'] = merge_files(entries)
            try:
                e = handle_merge_conflict(merged, fetch=fetch)
            except Exception as error:
                logging.warn(str(error))
                conflicts.append(unique(entries))
                continue
            self.insert_entry(e, check=False)


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
                    self.insert_entry(e, check=False)
                    continue

            if ignore_unresolved:
                for e in entries:
                    self.insert_entry(e, check=False)
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
            if file != newfile:
                move(file, newfile, copy)
                count += 1
            newfiles = [newfile]

        # several files: only rename container
        else:
            newdir = os.path.join(direc, e['ID'])
            newfiles = []
            for file in files:
                newfile = os.path.join(newdir, os.path.basename(file))
                if file != newfile:
                    move(file, newfile, copy)
                    count += 1
                newfiles.append(newfile)

        setentryfiles(e, newfiles)
        if count > 0:
            logging.info('renamed file(s): {}'.format(count))


    def rename_entries_files(self, copy=False):
        for e in self.db.entries:
            self.rename_entry_files(e, copy)


# default_config = Config()

def main():

    # import sys
    # import codecs
    # sys.stdout = codecs.getwriter('utf8')(sys.stdout)

    main = argparse.ArgumentParser(description='library management tool')
    subparsers = main.add_subparsers(dest='cmd')

    config = argparse.ArgumentParser(add_help=False)
    grp = config.add_argument_group('config')
    grp.add_argument('--bibtex', default='myref.bib',help='%(default)s')
    grp.add_argument('--filesdir', default='files', help='%(default)s')


    parser = subparsers.add_parser('add', description='add PDF(s) or bibtex(s) to library',
        parents=[config])
    parser.add_argument('file', nargs='+')
    parser.add_argument('--ignore-errors', action='store_true', 
        help='ignore errors when adding multiple files')
    parser.add_argument('--recursive', action='store_true', 
        help='accept directory as argument, for recursive scan \
        of .pdf files (bibtex files are ignored in this mode')
    parser.add_argument('--dry-run', action='store_true', 
            help='no PDF renaming/copying, no bibtex writing on disk (for testing)')

    grp = parser.add_argument_group('merge/conflict')
    mgrp = grp.add_mutually_exclusive_group()
    mgrp.add_argument('-o', '--overwrite', action='store_true', 
        help='overwrite existing entries (the default is to just merge files)')
    mgrp.add_argument('-m', '--merge', action='store_true', 
        help='attempt to merge with existing entry (experimental)')
    # mgrp = grp.add_argument('--conflict', default='ignore', choices=['ignore'])
    # conflict.add_argument('-m', '--merge-files', action='store_true')
    #     help='merge new entry files with existing one (otherwise they are ignored)')
    # conflict.add_argument('--merge-files', action='store_true') 
    # grp.add_argument('--append', action='store_true', 
    #         help='if the entry already exists, append instead of overwriting file')
    # grp.add_argument('--merge', action='store_true', 
            # help='if the entry already exists, append instead of overwriting file')

    grp = parser.add_argument_group('files')
    grp.add_argument('-a','--attachment', nargs='+', help=argparse.SUPPRESS) #'supplementary material')
    grp.add_argument('-r','--rename', action='store_true', 
        help='rename PDFs according to key')
    grp.add_argument('-c','--copy', action='store_true', 
        help='copy file instead of moving them')



    def addpdf(o):
        global DRYRUN
        DRYRUN = o.dry_run
        if os.path.exists(o.bibtex):
            my = MyRef(o.bibtex, o.filesdir)
        else:
            my = MyRef.newbib(o.bibtex, o.filesdir)

        if len(o.file) > 1 and o.attachment:
            logging.error('--attachment is only valid for one added file')
            parser.exit(1)


        kw = dict(overwrite=o.overwrite, merge=o.merge)

        for file in o.file:
            try:
                if os.path.isdir(file):
                    if o.recursive:
                        my.scan_dir(file, rename=o.rename, copy=o.copy, **kw)
                    else:
                        raise ValueError(file+' is a directory, requires --recursive to explore')

                elif file.endswith('.pdf'):
                    my.add_pdf(file, attachments=o.attachment, rename=o.rename, copy=o.copy, **kw)

                elif file.endswith('.bib'):
                    my.add_bibtex_file(file, **kw)

                else:
                    raise ValueError('unknown file type:'+file)

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
            my.save()




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

    subp = subparsers.add_parser('merge', description='merge duplicates', 
        parents=[config, conflict])
    # subp.add_argument('-m', '--merge', action='store_true', help='merge duplicates')
    # subp.add_argument('--merge', action='store_true', help='merge duplicates')
    # subp.add_argument('--doi', action='store_true', help='DOI duplicate')
    subp.add_argument('--keys', nargs='+', help='merge these keys')

    def merge_duplicate(o):
        my = MyRef(o.bibtex, o.filesdir)
        kw = dict(force=o.force, fetch=o.fetch, ignore_unresolved=o.ignore)
        my.merge_duplicate_keys(**kw)
        my.merge_duplicate_dois(**kw)
        if o.keys:
            my.merge_entries(o.keys, **kw)
        my.save()

    parser = subparsers.add_parser('list', description='list (a subset of) entries',
        parents=[config])

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

    grp = parser.add_argument_group('formatting')
    mgrp = grp.add_mutually_exclusive_group()
    mgrp.add_argument('-k','--key-only', action='store_true')
    mgrp.add_argument('-s', '--short', action='store_true')
    mgrp.add_argument('-f', '--field', nargs='+', help='specific fields only')
    grp.add_argument('--no-key', action='store_true')

    grp = parser.add_argument_group('special')
    grp.add_argument('--invalid-doi', action='store_true', help='invalid dois')

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
        elif o.short:
            for e in entries:
                tit = e['title'][:60]+ ('...' if len(e['title'])>60 else '')
                doi = ('(doi:'+e['doi']+')') if e.get('doi','') else ''
                print(key(e), tit, doi)
        else:
            print(format_entries(entries))


    # parser.add_argument_group

    parser = subparsers.add_parser('doi', description='parse DOI from PDF')
    parser.add_argument('pdf')
    parser.add_argument('--space-digit', action='store_true', help='space digit fix')

    parser = subparsers.add_parser('fetch', description='fetch bibtex from DOI')
    parser.add_argument('doi')

    o = main.parse_args()

    if o.cmd == 'add':
        addpdf(o)
    elif o.cmd == 'list':
        listing(o)
    elif o.cmd == 'merge':
        merge_duplicate(o)
    elif o.cmd == 'doi':
        print(extract_doi(o.pdf, o.space_digit))
    elif o.cmd == 'fetch':
        print(fetch_bibtex_by_doi(o.doi))

if __name__ == '__main__':
    main()
