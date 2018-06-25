# -*- coding: utf-8 -*-
from __future__ import print_function
import operator
import os
import itertools
import six
from six.moves import input as raw_input
import re
import difflib

import bibtexparser

import logging
logger = logging.getLogger(__name__)

from papers.extract import isvaliddoi, fetch_entry
from papers.encoding import parse_file, format_file, format_entries

from papers.config import bcolors


# SEARCH DUPLICATES
# =================


def _group_key(groups, check):
    for k in groups:
        for ee in groups[k]:
            if check(ee):
                return k
    return None


def groupby_equal(entries, eq=None):
    """groupby based on full equality (slow !)

    >>> groupby_equal([(1,0),(1,1),(1,2),(2,0),(3,0),(2,1),(4,0)], lambda e1, e2: e1[0]==e2[0])
    [(0, {(1, 0), (1, 1), (1, 2)}),
     (1, {(2, 0), (2, 1)}),
     (2, {(3, 0)}),
     (3, {(4, 0)})]
    """
    equal = eq or operator.eq
    groups = {}
    for e in entries:
        k = _group_key(groups, lambda ee: equal(ee,e))
        if k is None:
            group = []
            groups[len(groups)] = group
        else:
            group = groups[k]
        group.append(e)
    return sorted(six.iteritems(groups)) 


def search_duplicates(entries, key=None, eq=None, issorted=False, filter_key=None):
    """search for duplicates

    entries: list elements
    key: key to check for equality
    eq: binary operator for equality check (slower)
    issorted: if True and key is provided, skip sort 

    returns:
    - unique_entries : list (entries for which no duplicates where found)
    - duplicates : list of list (groups of duplicates)

    examples:
    >>> search_duplicates([(1,0), (1,1), (1,2), (2,0), (3,0), (2,1), (4,0)], key=lambda e: e[0])
    ([(3, 0), (4, 0)], [[(1, 0), (1, 1), (1, 2)], [(2, 0), (2, 1)]])

    >>> search_duplicates([(1,0), (1,1), (1,2), (2,0), (3,0), (2,1), (4,0)], eq=lambda e1, e2: e1[0]==e2[0])
    ([(3, 0), (4, 0)], [[(1, 2), (1, 0), (1, 1)], [(2, 0), (2, 1)]])
    """
    if key or eq is None:
        if not issorted:
            entries = sorted(entries, key=key)
        grouped = itertools.groupby(entries, key)

    else:
        grouped = groupby_equal(entries, eq)

    duplicates = []
    unique_entries = []

    for e, g in grouped:
        group = list(g)
        if len(group) > 1 and (not filter_key or filter_key(e)):
            logger.info('key:'+str(e))
            duplicates.append(group)
        else:
            logger.debug('unique:'+str(e))
            unique_entries.extend(group)

    return unique_entries, duplicates


def list_duplicates(entries, **kw):
    entries, duplicate_groups = search_duplicates(entries, **kw)
    return list(itertools.chain(*duplicate_groups))


def list_uniques(entries, **kw):
    entries, duplicate_groups = search_duplicates(entries, **kw)
    return entries



# ANALYZE DUPLICATES
# ==================


class ConflictingField(object):
    def __init__(self, choices=[]):
        self.choices = choices

    def resolve(self, force=False):
        # TODO: remove `force` argument
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


def handle_merge_conflict(merged):
    # TODO: boil down this command to the minimum, or build all into a merge class
    
    if not isinstance(merged, MergedEntry):
        return merged  # all GOOD_DUPLICATES !

    elif isinstance(merged, MergedEntry):
        fields = [k for k in merged if isinstance(merged[k], ConflictingField)]
        raise ValueError('conflicting entries for fields: '+str(fields))

    return merged



class DummyBcolors:
    def __getattr__(self, s):
        return ''
dummybcolors = DummyBcolors()



def _colordiffline(line, sign=None):
    if sign == '+' or line.startswith('+'):
        return bcolors.OKGREEN + line + bcolors.ENDC
    elif sign == '-' or line.startswith('-'):
        return bcolors.FAIL + line + bcolors.ENDC
    elif sign == '?' or line.startswith('?'):
        return bcolors.WARNING + line + bcolors.ENDC
    elif sign == '!' or line.startswith('!'):
        return bcolors.BOLD + bcolors.WARNING + line + bcolors.ENDC
    elif sign == '*' or line.startswith('*'):
        return bcolors.BOLD + line + bcolors.ENDC
    # elif sign == '>' or line.startswith('>'):
        # return bcolors.BOLD + line + bcolors.ENDC    
        # return bcolors.BOLD + bcolors.WARNING + line + bcolors.ENDC
    else:
        return line


def entry_diff(e_old, e, color=True):
    " update diff "
    s_old = format_entries([e_old])
    s = format_entries([e])
    ndiff = difflib.ndiff(s_old.splitlines(1), s.splitlines(1))
    diff = ''.join(ndiff)
    if color:
        return "\n".join([_colordiffline(line) for line in diff.splitlines()])
    else:
        return diff


def entry_ndiff(entries, color=True):
    ' diff of many entries '
    m = merge_entries(entries)
    SECRET_STRING = 'REPLACE_{}_FIELD'
    regex = re.compile(SECRET_STRING.format('(.*)')) # reg exp to find
    choices = {}
    somemissing = []
    for k in m:
        if isinstance(m[k], ConflictingField):
            choices[k] = m[k].choices
            m[k] = SECRET_STRING.format(k)
        elif any(k not in e for e in entries):
            somemissing.append(k)
    db = bibtexparser.bibdatabase.BibDatabase()
    db.entries.append(m)
    s = bibtexparser.dumps(db)
    lines = []
    for line in s.splitlines():
        matches = regex.findall(line)
        if matches:
            k = matches[0]
            template = SECRET_STRING.format(k)
            lines.append(u'\u2304'*3)
            for c in choices[k]:
                newline = '  '+line.replace(template, u'{}'.format(c))
                lines.append(_colordiffline(newline, '!') if color else newline)
                lines.append('---')
            lines.pop() # remove last ---
            # lines.append('^^^')
            lines.append(u'\u2303'*3)
        elif any('{} = {{'.format(k) in line for k in somemissing):
            newline = '  '+line
            lines.append(_colordiffline(newline, sign='*') if color else newline)
        elif not line.startswith(('@','}')):
            lines.append('  '+line)
        else:
            lines.append(line)
    return '\n'.join(lines)


def entry_sdiff(entries, color=True, bcolors=bcolors, best=None):
    """split diff
    """
    if not entries:
        return ''
    assert all(entries), 'some entries are empty'

    if not color:
        bcolors = dummybcolors

    db = bibtexparser.bibdatabase.BibDatabase()
    db.entries.append(None)

    merged = merge_entries(entries)
    conflicting_fields = [k for k in merged if isinstance(merged[k], ConflictingField)]
    somemissing = [k for k in merged if any(k not in e for e in entries)]

    entry_strings = []

    for i, entry in enumerate(entries):
        db.entries[0] = entry
        string = bibtexparser.dumps(db)
        if six.PY2:
            string = string.decode('utf-8') # decode to avoid failure in replace
        # color the conflicting fields
        lines = []
        for line in string.splitlines():
            for k in conflicting_fields+somemissing:
                fmt = lambda s : (bcolors.WARNING if k in conflicting_fields else bcolors.BOLD)+s+bcolors.ENDC
                if k != k.lower() and '@' in line:
                    line = line.replace(entry[k], fmt(entry[k]))
                elif line.strip().startswith('{} = {{'.format(k)):
                    line = fmt(line)
            lines.append(line)
        string = '\n'.join(lines)
        if best is None:
            entry_strings.append(bcolors.OKBLUE+'* ('+str(i+1)+')'+bcolors.ENDC+'\n'+string)
        elif entry == best:
            entry_strings.append(bcolors.OKBLUE+'* ('+str(i+1)+')'+bcolors.ENDC+'\n'+string)
        else:
            entry_strings.append(bcolors.OKBLUE+'  ('+str(i+1)+')'+bcolors.ENDC+'\n'+string)

    return '\n'.join(entry_strings)



# RESOLVE DUPLICATES
# ==================

def merge_files(entries):
    files = []
    for e in entries:
        for f in parse_file(e.get('file','')):
            if f not in files:
                files.append(f)
    return format_file(files)   


def _ask_pick_loop(entries, extra=[], select=False):

    entry_choices = [str(i+1) for i in range(len(entries))]
    if select:
        select_choices = ['-'+c for c in entry_choices]
    else:
        select_choices = []
    choices = entry_choices + select_choices + extra

    def _process_choice(i):
        i = i.strip()
        if i in entry_choices:
            return entries[int(i)-1]
        elif i in select_choices:
            return [e for e in entries if e != entries[int(i)-1]]
        elif select and len(i.lstrip('-').split()) > 1:
            if i.startswith('-'):
                deselect = [_process_choice(ii) for ii in i[1:].split()]
                return [e for e in entries if e not in deselect]
            else:
                return [_process_choice(ii) for ii in i.split()]
        elif i in choices:
            return i
        else:
            raise ValueError(i)

    while True:
        print('choices: '+', '.join(choices))
        i = raw_input('>>> ')
        try:
            return _process_choice(i)
        except:
            continue


def choose_entry_interactive(entries, extra=[], msg='', select=False, best=None):

    print(entry_sdiff(entries, best=best))

    if msg:
        print(msg)
    else:
        print()
    return _ask_pick_loop(entries, extra, select)



def edit_entries(entries, diff=False, ndiff=False):
    '''edit entries and insert result in database 
    '''
    # write the listed entries to temporary file
    import tempfile
    # filename = tempfile.mktemp(prefix='.', suffix='.txt', dir=os.path.curdir)
    filename = tempfile.mktemp(suffix='.txt')

    if (diff or ndiff) and len(entries) > 1:
        if ndiff or len(entries) > 2:
            entrystring = entry_ndiff(entries, color=False)
        else:
            entrystring = entry_diff(*entries, color=False)
    else:
        db = bibtexparser.bibdatabase.BibDatabase()
        db.entries.extend(entries)
        entrystring = bibtexparser.dumps(db)

    if six.PY2:
        entrystring = entrystring.encode('utf-8')

    with open(filename, 'w') as f:
        f.write(entrystring)

    res = os.system('%s %s' % (os.getenv('EDITOR'), filename))

    if res == 0:
        logger.info('sucessfully edited file, insert edited entries')
        db = bibtexparser.loads(open(filename).read())
        return db.entries

        raise ValueError('error when editing entries file: '+filename)




def score(e):
    ' entry score, in terms of reliability '
    return (100*('doi' in e and isvaliddoi(e['doi'])) + 50*('title' in e) + 10*('author' in e) + 1*('file' in e))*100 + len(e)


def bestentry(entries):
    return sorted(entries, key=score)[-1]


class DuplicateSkip(Exception):
    pass

class DuplicateSkipAll(Exception):
    pass


class DuplicateHandler(object):

    def __init__(self, entries):
        self.entries = entries

    # view methods
    def viewdiff(self, color=True, update=False):
        if len(self.entries) == 2 and update:
            return entry_diff(*self.entries, color=color)
        else:
            return entry_ndiff(self.entries, color=color)

    def viewsplit(self, color=False):
        return entry_sdiff(self.entries, color=color, best=self.best())

    def format(self, diffview=False, update=False, color=True):
        return self.viewdiff(color, update) if diffview else self.viewsplit(color)

    # action methods
    def remove_duplicates(self):
        self.entries = unique(self.entries) # note: loose order

    def edit(self, diffview=False, update=False):
        self.entries = edit_entries(self.entries, diff=diffview, ndiff=not update)

    def delete(self):
        self.entries = []
    
    def best(self):
        return bestentry(self.entries)

    def fetch(self):
        # pick best entry to update from
        return fetch_entry(self.best())

    def merge_files(self):
        file = merge_files(self.entries)
        if file:
            for e in self.entries:
                e['file'] = file

    def merge(self):
        self.merge_files()
        merged = merge_entries(self.entries)
        try:
            e = handle_merge_conflict(merged)
            self.entries = [e]

        except Exception as error:
            logger.warn(str(error))
            best = self.best()
            for k in list(merged.keys()):
                if isinstance(merged[k], ConflictingField):
                    merged[k] = best[k] # ID, ENTRYFIELD
                    # if k != k.lower():
                    # else:
                    #     del merged[k]
            self.entries.append(merged)

    # interactive loops
    def interactive_loop(self, diffview=False, update=False):

        self.remove_duplicates()

        while len(self.entries) > 1:

            choices = list('mefdnsSvV')
            txt = '''

(m)erge
(e)dit
(f)etch metadata
(d)elete
(n)ot a duplicate (validate several entries)
(s)kip (cancel)
(S)kip all 
(v)iew toggle (diff - split)
(V)iew toggle for diff mode
'''
            if not diffview:
                msg = bcolors.OKBLUE + 'Pick entry or choose one of the following actions:'+bcolors.ENDC+txt
                e = choose_entry_interactive(self.entries, extra=choices, msg=msg, select=True, best=self.best())
            else:
                print(entry_ndiff(self.entries))
                print(bcolors.OKBLUE + 'Choose one of the following actions:'+bcolors.ENDC + txt)
# .replace('(s)','('+_colordiffline('s','-')+')'))
                ans = None
                while ans not in choices:
                    print('choices: '+', '.join(choices))
                    ans = raw_input('>>> ')
                e = ans

            if e == 'm':
                self.merge() 

            elif e == 'e':
                self.edit(diffview, update)

            elif e == 'd':
                self.delete()

            elif e == 'f':
                self.entries.append(self.fetch())
                self.remove_duplicates()

            elif e == 'S':
                raise DuplicateSkipAll()

            elif e == 's':
                raise DuplicateSkip()

            elif e == 'n':
                break

            elif isinstance(e, dict):
                self.entries = [e]

            elif isinstance(e, list):
                self.entries = e

            elif e == 'v':
                diffview = not diffview  # toggle view

            elif e == 'V':
                if not diffview:
                    diffview = True  # toggle view
                else:
                    update = not update

            else:
                print(e)
                raise ValueError('this is a bug')

        return self.entries



def resolve_duplicates(duplicates, mode='i'):
    conflict = DuplicateHandler(duplicates)
    conflict.remove_duplicates()

    if len(conflict.entries) > 1:
        if mode == 'i':
            conflict.interactive_loop()
        elif mode == 's':
            pass
        else:
            print(conflict.format())
            raise ValueError('unresolved conflicts')

    return conflict.entries
    

def check_duplicates(entries, key=None, eq=None, issorted=False, filter_key=None, mode='i'):
    """check duplicates, given a key or equality function
    !! resolved duplicates are appended to the list of entries
    """
    entries, duplicate_groups = search_duplicates(entries, key, eq, issorted, filter_key)
    logger.info(str(len(duplicate_groups))+' duplicate(s)')

    for duplicates in duplicate_groups:
        try:
            entries.extend(resolve_duplicates(duplicates, mode))
        except DuplicateSkip:
            entries.extend(duplicates)
        except DuplicateSkipAll:
            entries.extend(itertools.chain(duplicates))        
            break
    return entries



# SPECIAL CASE OF CONFLICT RESOLUTION: on insert
# ==============================================

def conflict_resolution_on_insert(old, new, mode='i'):
    """conflict resolution with two entries
    """
    if mode == 'i':
        print(entry_diff(old, new))
        print(bcolors.OKBLUE + 'what to do? ')
        print('''
(u)pdate missing (discard conflicting fields in new entry)
(U)pdate other (overwrite conflicting fields in old entry)
(o)verwrite
(e)dit diff
(E)dit split (not a duplicate)
(s)kip
(a)ppend anyway
(r)aise'''.strip()
.replace('(u)','('+_colordiffline('u','+')+')')  # green lines will be added 
.replace('(o)','('+_colordiffline('o','-')+')') + bcolors.ENDC
)
# .replace('(s)','('+_colordiffline('s','-')+')'))
        choices = list('uUoeEsar')
        ans = None
        while ans not in choices:
            print('choices: '+', '.join(choices))
            ans = raw_input('>>> ')
        mode = ans

    # overwrite?
    if mode == 'o':
        resolved = [new]

    elif mode == 'a':
        resolved = [old, new]

    elif mode == 'u':
        logger.info('update missing fields')
        new.update(old)
        old.update(new)
        resolved = [old]

    elif mode == 'U':
        logger.info('update with other')
        old.update(new)
        resolved = [old]

    # skip
    elif mode == 's':
        resolved = [old]

    # edit
    elif mode == 'e':
        resolved = edit_entries([old, new], diff=True)

    elif mode == 'E':
        resolved = edit_entries([old, new])

    else:
        raise ValueError('conflicting entries')

    return resolved




# DEPRECATED TOOLS
# ================

def unique(entries):
    entries_ = []
    for e in entries:
        if e not in entries_:
            entries_.append(e)
    return entries_

# class DoiKey(object):
#     def __init__(self, valid=False):
#         self.count = -1
#         self.valid = valid

#     def plusone(self):
#         self.count += 1
#         return self.count

#     def key(self, e):
#         if self.valid:
#             return (e.get('doi','') and isvaliddoi(e['doi']))  or self.plusone()
#         else:
#             return e.get('doi','') or self.plusone()
