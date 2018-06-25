
import os
import six
import bibtexparser
from papers.latexenc import latex_to_unicode, unicode_to_latex
from unidecode import unidecode as unicode_to_ascii

# fix bibtexparser issue
if six.PY2:
    _bloads = bibtexparser.loads 
    _bdumps = bibtexparser.dumps
    bibtexparser.loads = lambda s: (_bloads(s.decode('utf-8') if type(s) is str else s))
    bibtexparser.dumps = lambda db: _bdumps(db).encode('utf-8')


# fix bibtexparser call on empty strings
_bloads_orig = bibtexparser.loads
def _bloads_fixed(s):
    if s == '':
        return bibtexparser.bibdatabase.BibDatabase()
    else:
        return _bloads_orig(s)
bibtexparser.loads = _bloads_fixed


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
        raise ValueError('unknown `file` format: '+ repr(file))

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


def format_entries(entries):
    db = bibtexparser.bibdatabase.BibDatabase()
    db.entries.extend(entries)
    return bibtexparser.dumps(db)

# Parse name entry
# ================

def _outermost_bracket_groups(string, type='{}'):
    '''
    >>> outermost_bracket_groups('{my name}')
    ['my name']
    >>> outermost_bracket_groups("{my nam\\'{e}}")
    ["my nam\\\'{e}"]
    >>> outermost_bracket_groups('{my} {name}')
    ['my', 'name']
    >>> outermost_bracket_groups("{my} {nam\\'{e}}")
    ['my', "nam\\'{e}"]
    '''
    l, r = type
    level = 0
    matches = []
    for c in string:
        if c == l:
            level += 1
            if level == 1:
                expr = []
        elif c == r:
            level -= 1
            if level == 0:  # close main
                matches.append(''.join(expr))
        elif level >= 1:
            expr.append(c)
    return matches


def strip_outmost_brackets(family):
    # strip brakets
    brackets = _outermost_bracket_groups(family)
    if len(brackets) == 1 and brackets[0] == family[1:-1]:
        family = family[1:-1] # strip name' bracket
    return family


def standard_name(author):
    names = []
    for name in bibtexparser.customization.getnames([strip_outmost_brackets(nm) for nm in author.split(' and ')]):
        family, given = name.split(',')
        family = strip_outmost_brackets(family.strip())
        # given = strip_outmost_brackets(given.strip())
        names.append(', '.join([family.strip(), given.strip()]))
    return ' and '.join(names)


def family_names(author_field):
    authors = standard_name(author_field).split(' and ')
    return [nm.split(',')[0] for nm in authors]
