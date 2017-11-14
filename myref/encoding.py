import os
import six
import bibtexparser


# fix bibtexparser issue
if six.PY2:
    _bloads = bibtexparser.loads 
    _bdumps = bibtexparser.dumps
    bibtexparser.loads = lambda s: _bloads(s.decode('utf-8') if type(s) is str else s)
    bibtexparser.dumps = lambda db: _bdumps(db).encode('utf-8')



# string conversions
# ==================
UPDATE_LATEX_TABLE = {
    u'&': '\\&',
    u'$': '\\$',
    u'<': '\\textless',
    u'>': '\\textgreater',
}

LATEX_TO_UNICODE = None

def latex_to_unicode(string):
    """ replace things like "{\_}" and "{\'{e}}'" with unicode characters _ and é
    """
    global LATEX_TO_UNICODE
    if LATEX_TO_UNICODE is None:
        import myref.unicode_to_latex as ul 
        ul.unicode_to_latex.update(UPDATE_LATEX_TABLE)
        LATEX_TO_UNICODE = {v.strip():k for k,v in six.iteritems(ul.unicode_to_latex)}
    string = string.replace('{}','') #.replace('{\\}','')
    # try:
    string = string.format(**LATEX_TO_UNICODE)
    # except (KeyError, ValueError) as error:
    #     logging.warn('failed to replace latex: '+str(error))
    return string


def unicode_to_latex(string):
    import myref.unicode_to_latex as ul 

    lstring = []
    for c in string:
        if ord(c) < 128:
            lstring.append(c)
        else:
            lstring.append('{'+ul.unicode_to_latex[c].strip()+'}')
    return ''.join(lstring)

    # ID = str(''.join([c if ord(c) < 128 else '_' for c in ID]))  # make sure the resulting string is ASCII

def unicode_to_ascii(string):
    from unidecode import unidecode
    return unidecode(string)

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



# Parse name entry
# ================

def outermost_bracket_groups(string, type='{}'):
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
    brackets = outermost_bracket_groups(family)
    if len(brackets) == 1 and brackets[0] == family[1:-1]:
        family = family[1:-1] # strip name' bracket
    return family


def formatted_name(author):
    names = []
    for name in bibtexparser.customization.getnames([strip_outmost_brackets(nm) for nm in author.split(' and ')]):
        family, given = name.split(',')
        family = strip_outmost_brackets(family.strip())
        # given = strip_outmost_brackets(given.strip())
        names.append(', '.join([family.strip(), given.strip()]))
    return ' and '.join(names)


def family_names(author_field):
    authors = formatted_name(author_field).split(' and ')
    return [nm.split(',')[0] for nm in authors]
