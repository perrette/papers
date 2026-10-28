import os
from pathlib import Path

from bibtexparser.middlewares import LatexDecodingMiddleware

from papers.entries import (
    get_entry_val,
    library_from_entries,
    format_library,
    update_entry,
    parse_file,
    split_depth0,
)
from papers.utils import ansi_link as link, bcolors


def format_entries(entries):
    lib = library_from_entries(entries)
    return format_library(lib)


def latex_to_unicode_library(library):
    """Apply LaTeX-to-Unicode decoding to a library."""
    return LatexDecodingMiddleware().transform(library=library)


def convert_entry_to_unicode(entry):
    """Convert a single entry's LaTeX field values to unicode in place."""
    lib = library_from_entries([entry])
    lib = latex_to_unicode_library(lib)
    update_entry(entry, lib.entries[0])


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

def standard_name(author):
    """Normalize author string to 'Last, First' per author (e.g. 'John Smith and Jane Doe' -> 'Smith, John and Doe, Jane').
    A part in braces is one word: 'John {van der Berg}' -> '{van der Berg}, John'; '{World Health Organization}' stays."""
    result = []
    for p in split_depth0(author, r'\s+and\s+'):
        if not p:
            continue
        if len(split_depth0(p, r',')) > 1:
            result.append(p)
        else:
            tokens = split_depth0(p, r'\s+')
            result.append(tokens[-1] + ", " + ' '.join(tokens[:-1]) if len(tokens) > 1 else p)
    return " and ".join(result)


def family_names(author_field):
    authors = standard_name(author_field).split(' and ')
    return [nm.split(',')[0] for nm in authors]
