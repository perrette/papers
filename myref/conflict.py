"""Conflict resolution
"""
import bibtexparser
import os
import itertools

from myref.tools import bcolors, parse_file, format_file

def unique(entries):
    entries_ = []
    for e in entries:
        if e not in entries_:
            entries_.append(e)
    return entries_


def choose_entry_interactive(entries, extra=[], msg=''):
    db = bibtexparser.loads('')
    db.entries.append({})

    merged = merge_entries(entries)
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