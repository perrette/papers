import os
import bibtexparser
from pathlib import Path
from unidecode import unidecode as unicode_to_ascii
from papers.utils import ansi_link as link, bcolors
from papers import logger
from papers.bibtexparser_compat import get_entry_val, parse_string, write_string, library_from_entries


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
            logger.debug(f"""update_file_path {get_entry_val(entry, 'ID', '')} {old_file} (relative to {repr(from_relative_to)}) {new_file} (relative to {repr(to_relative_to)})""")
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
    lib = library_from_entries(entries)
    return write_string(lib)

def parse_keywords(e):
    return [w.strip() for w in get_entry_val(e, 'keywords', '').split(',') if w.strip()]

def format_key(e, no_key=False):
    if no_key:
        key = lambda e: ''
    else:
        n = len(parse_file(get_entry_val(e, 'file', '')))
        key = lambda e: n*(bcolors.BOLD)+bcolors.OKBLUE+get_entry_val(e, 'ID', '')+':'+bcolors.ENDC
    return key(e)

def format_entry(biblio, e, no_key=False, prefix=""):
    """One-liner formatter
    """
    tit = get_entry_val(e, 'title', '')[:60]+ ('...' if len(get_entry_val(e, 'title', ''))>60 else '')
    info = []
    if get_entry_val(e, 'doi', ''):
        info.append(link(f"https://doi.org/{e['doi']}", 'doi:'+e['doi']))

    files = parse_file(get_entry_val(e, 'file', ''), relative_to=biblio.relative_to)
    n = len(files)

    if n:
        file_link = f"file:///{Path(files[0]).resolve()}" if n == 1 else f"file:///{Path(os.path.commonpath(files)).resolve()}"
        ansi_link = link(file_link, f'{"file" if n == 1 else "files"}:{str(n)}')
        info.append(bcolors.OKGREEN+ansi_link+bcolors.ENDC)

    if get_entry_val(e, 'keywords', ''):
        keywords = parse_keywords(e)
        info.append(bcolors.WARNING+" | ".join(keywords)+bcolors.ENDC)

    infotag = '('+', '.join(info)+')' if info else ''
    if prefix:
        prefixtag = f"{bcolors.WARNING}{prefix} -> {bcolors.ENDC}"
    else:
        prefixtag = ""
    return f"{prefixtag}{format_key(e, no_key=no_key)} {tit} {infotag}"


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
    """Normalize author string to 'Last, First' per author (e.g. 'John Smith and Jane Doe' -> 'Smith, John and Doe, Jane')."""
    parts = [s.strip() for s in author.split(" and ")]
    result = []
    for p in parts:
        if "," in p:
            result.append(p)
        else:
            tokens = p.rsplit(" ", 1)
            result.append(tokens[1] + ", " + tokens[0] if len(tokens) == 2 else p)
    return " and ".join(result)


def family_names(author_field):
    authors = standard_name(author_field).split(' and ')
    return [nm.split(',')[0] for nm in authors]
