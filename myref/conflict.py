"""Conflict resolution
"""
import bibtexparser
import os
import itertools

from myref.tools import bcolors

def unique(entries):
    entries_ = []
    for e in entries:
        if e not in entries_:
            entries_.append(e)
    return entries_


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


# class ConflictResolution(object):
#     def __init__(self, entries):
#         self.entries = entries

#     def ask(self):
#         choose_entry_interactive(self.entries, 
#             extra=['m','s','f','k','e','c'], 
#             msg='(m)erge or (s)plit or (f)etch doi or generate (k)ey or (e)dit or (c)ancel (skip)')

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



def best_entry(entries, fields=None):
    """best guess among a list of entries, based on field availability

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
        fields = ['ID', 'doi','author','year','title','file']

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

    def resolve(self, force=False):
        choices = [v for v in self.choices if v]

        if len(choices) == 1 or force:
            return choices[0]
        else:
            return self


class MergedEntry(dict):

    def isresolved(self):
        return not any([isinstance(self[k], ConflictingField) for k in self])

    def resolve(self, force=False):
        for k in self:
            if isinstance(self[k], ConflictingField):
                self[k] = self[k].resolve(force)

        return dict(self) if self.isresolved() else self


def merge_entries(entries, force=False):
    merged = MergedEntry() # dict
    for e in entries:
        for k in e:
            if k not in merged:
                merged[k] = ConflictingField([])
            if e[k] not in merged[k].choices:
                merged[k].choices.append(e[k])
    return merged.resolve(force)


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




#   def insert_entry(self, entry, check=True, overwrite=False, merge=False, 
#         strict=True, force=False, interactive=True, mergefiles=True):
#         """
#         check : check whether key already exists
#         overwrite : overwrite existing entry?
#         merge : merge with existing entry?
#         force : never mind conflicting fields when merging
#         """
#         keys = [self.key(ei) for ei in self.db.entries]
#         i = bisect.bisect_left(keys, entry['ID'].lower())

#         if not check:
#             self.db.entries.insert(i, entry)
#             return entry

#         samekey = False
#         samedoi = False

#         if i < len(keys):
#             # check for key duplicate
#             if keys[i] == self.key(entry):
#                 samekey = True 

#         # check for doi duplicate
#         if 'doi' in entry and isvaliddoi(entry['doi']):
#             # try to check the same-key element first, to spare a search
#             if samekey and entry['doi'] == self.db.entries[i].get('doi',''):
#                 samedoi = True
#             else:
#                 j = self.locate_doi(entry['doi'])
#                 if j < len(self.db.entries):
#                     samedoi = True
#                     i = j  # priority
#                     samekey = entry['ID'] == self.db.entries[i].get('doi','')

#         if samekey or samedoi:
#             msg_extra = (overwrite*' => overwrite') or (merge*' => merge')
#             if samedoi:
#                 logging.info('entry DOI already present: '+self.key(entry)+', doi:'+entry['doi']+msg_extra)
#             else:
#                 logging.info('entry key already present: '+self.key(entry)+msg_extra)

#             duplicates = [self.db.entries[i], entry]

#             if overwrite:
#                 if not samekey and not force:
#                     tmpl = 'entry key will be replaced {}{} >>> {}{}. Continue? (y/n) '
#                     ans = raw_input(tmpl.format(bcolors.WARNING, self.db.entries[i]['ID'], 
#                         entry['ID'], bcolors.ENDC))
#                     if ans != 'y':
#                         return

#                 if mergefiles:
#                     self.db.entries[i]['file'] = merge_files(duplicates)

#                 self.db.entries[i] = entry
#                 return entry
            
#             # if entry['ID'] != self.db.entries[i]['ID']:
#             #     tmpl = 'imported entry key will be replaced {} >>> {}'
#             #     logging.warn(tmpl.format(self.db.entries[i]['ID'], entry['ID']))
#             # entry['ID'] = self.db.entries[i]['ID']

#             if merge:
#                 merged = merge_entries(duplicates, strict=strict, force=force)
#                 if mergefiles:
#                     merged['file'] = merge_files(duplicates)
#                 try:
#                     e = handle_merge_conflict(merged)
#                 except Exception as error:
#                     if not interactive:
#                         raise
#                     print()
#                     print('!!! Failed to merge:',str(error),' !!!')
#                     print()
#                     e = choose_entry_interactive(unique(duplicates), 
#                         extra=['n','q'], msg=' or (n)ot a duplicate or (q)uit')
#                     if e == 'q':
#                         raise
#                     elif e == 'n':
#                         if samekey:
#                             entry['ID'] = self.generate_key(entry)
#                             return self.insert_entry(entry, check=False)
#                         else:
#                             logging.info('NEW ENTRY: '+self.key(entry))
#                             self.db.entries.insert(i, entry)                      
#                             return

#                 self.db.entries[i] = e


#             else:
#                 if mergefiles:
#                     self.db.entries[i]['file'] = merge_files(duplicates)
        
#         else:
#             logging.info('NEW ENTRY: '+self.key(entry))
#             self.db.entries.insert(i, entry)

#         return self.db.entries[i]




# def merge_duplicates(self, key, interactive=True, fetch=False, force=False, 
#         resolve={}, ignore_unresolved=True, mergefiles=True, strict=False):
#         """
#         Find and merge duplicate keys. Leave unsolved keys.

#         key: callable or key for grouping duplicates
#         interactive: interactive solving of conflicts
#         conflict: method in case of unresolved conflict
#         **kw : passed to merge_entries
#         """
#         if isinstance(key, six.string_types):
#             key = lambda e: e[key]

#         self.db.entries, duplicates = search_duplicates(self.db.entries, key)


#         if interactive and len(duplicates) > 0:
#             raw_input(str(len(duplicates))+' duplicate(s) to remove (press any key) ')

#         # attempt to merge duplicates
#         conflicts = []
#         for entries in duplicates:
#             merged = merge_entries(entries, strict=strict, force=force)
#             if mergefiles:
#                 merged['file'] = merge_files(entries)
#             try:
#                 e = handle_merge_conflict(merged, fetch=fetch)
#             except Exception as error:
#                 logging.warn(str(error))
#                 conflicts.append(unique(entries))
#                 continue
#             self.insert_entry(e, check=False)


#         if interactive and len(conflicts) > 0:
#             raw_input(str(len(conflicts))+' conflict(s) to solve (press any key) ')

#         # now deal with conflicts
#         for entries in conflicts:

#             if interactive:
#                 e = choose_entry_interactive(entries, 
#                     extra=['s','q'], msg=' or (s)kip or (q)uit')
            
#                 if e == 's':
#                     ignore_unresolved = True

#                 elif e == 'q':
#                     interactive = False
#                     ignore_unresolved = True

#                 else:
#                     self.insert_entry(e, check=False)
#                     continue

#             if ignore_unresolved:
#                 for e in entries:
#                     self.insert_entry(e, check=False)
#             else:
#                 raise ValueError('conflicting entries')