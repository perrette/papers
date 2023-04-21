import os
import bibtexparser
from unidecode import unidecode as unicode_to_ascii
from papers.latexenc import unicode_to_latex
from papers import logger

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


def parse_file(file, relative_to=None):
    " return list of absolute paths "
    if not file:
        return []
    else:
        files = [_parse_file(f) for f in file.split(';')]
        if relative_to is not None:
            files = [os.path.abspath(os.path.join(relative_to, f)) for f in files]

    return files


def update_file_path(entry, from_relative_to, to_relative_to, check=False):
    if 'file' in entry:
        old_file = entry["file"]
        file_path = parse_file(entry["file"], from_relative_to)
        if check:
            for f in file_path:
                assert os.path.exists(f), f"{f} does not exist"
        new_file = format_file(file_path, to_relative_to)
        if new_file != old_file:
            logger.debug(f"""update_file_path {entry.get("ID")} {old_file} (relative to {repr(from_relative_to)}) {new_file} (relative to {repr(to_relative_to)})""")
            # logger.debug(f"""{entry.get("ID")}: update file {old_file} to {new_file}""")
        entry["file"] = new_file
        if old_file != new_file:
            return (old_file, new_file)


def format_file(files, relative_to=None):
    # make sure the path is right
    if relative_to is not None:
        msg = f"FORMAT FILE {', '.join(files)}"
        if relative_to == os.path.sep:
            files = [os.path.abspath(p) for p in files]
        else:
            files = [os.path.normpath(os.path.relpath(p, relative_to)) for p in files]
        msg += f" => {', '.join(files)}"
        logger.debug(msg)
    return ';'.join([_format_file(f) for f in files])


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
    return " and ".join(bibtexparser.customization.author({"author": author}).get("author",[]))


def family_names(author_field):
    authors = standard_name(author_field).split(' and ')
    return [nm.split(',')[0] for nm in authors]
