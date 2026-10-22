"""Identifiers of an entry on the command line: the commands that take KEY
accept the key, a former key (biblatex `ids` field), a DOI, an arXiv
identifier or an ISBN, and `-` reads them from the standard input.

This is about naming entries of one library, not about deciding whether two
entries are the same paper (see papers.duplicate).
"""
import re
import sys

from papers.entries import get_entry_val
from papers.utils import PapersExit

ACCEPTED = 'key, DOI, arXiv id or ISBN'

_DOI_PREFIX = re.compile(r'^(https?://(dx\.)?doi\.org/|doi:\s*)', re.IGNORECASE)
_ARXIV_PREFIX = re.compile(r'^(arxiv:\s*|https?://arxiv\.org/(abs|pdf)/)', re.IGNORECASE)
_ARXIV_NEW = re.compile(r'^(\d{4}\.\d{4,5})(v\d+)?$')
_ARXIV_OLD = re.compile(r'^([a-z][a-z\-]*(\.[a-z]{2})?/\d{7})(v\d+)?$', re.IGNORECASE)
_ARXIV_DOI = re.compile(r'^10\.48550/arxiv\.(.+)$', re.IGNORECASE)


def strip_doi(text):
    """a DOI without doi.org/ or doi: prefix, in its original case (the case
    matters in the arXiv identifier of an arXiv DOI, e.g. math.AG/0601001);
    None if it is not a DOI"""
    doi = _DOI_PREFIX.sub('', text.strip()).strip()
    return doi if doi.startswith('10.') and '/' in doi else None


def normalize_doi(text):
    "a DOI in lower case, without doi.org/ or doi: prefix (for comparison); None if it is not a DOI"
    doi = strip_doi(text)
    return doi.lower() if doi else None


def normalize_arxiv(text):
    """an arXiv identifier without version and arXiv: prefix (2101.01234,
    hep-th/9901001), in lower case; None if it is not one"""
    s = _ARXIV_PREFIX.sub('', text.strip()).strip()
    if s.lower().endswith('.pdf'):
        s = s[:-4]
    m = _ARXIV_NEW.match(s) or _ARXIV_OLD.match(s)
    return m.group(1).lower() if m else None


def normalize_isbn(text):
    """the ISBN-13 of an ISBN-10 or ISBN-13 (hyphens and spaces allowed,
    check digit verified); None if it is not one"""
    s = re.sub(r'[\s\-]', '', text.strip())
    if s.lower().startswith('isbn'):
        s = s[4:].lstrip(':')
    s = s.upper()
    if re.fullmatch(r'\d{9}[\dX]', s):
        digits = [10 if c == 'X' else int(c) for c in s]
        if sum((10 - i) * d for i, d in enumerate(digits)) % 11:
            return None
        core = '978' + s[:9]
        check = (10 - sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(core)) % 10) % 10
        return core + str(check)
    if re.fullmatch(r'\d{13}', s):
        if sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(s)) % 10:
            return None
        return s
    return None


def arxiv_of_doi(doi):
    "the arXiv identifier of an arXiv DOI (10.48550/arXiv.<id>), as written in the DOI, or None"
    m = _ARXIV_DOI.match(doi.strip())
    return m.group(1) if m else None


def _eprint_arxiv(e):
    "the arXiv identifier of the eprint field (arXiv or no archivePrefix), or None"
    prefix = get_entry_val(e, 'archiveprefix', '') or get_entry_val(e, 'archivePrefix', '')
    if prefix.strip().lower() in ('', 'arxiv'):
        return normalize_arxiv(get_entry_val(e, 'eprint', ''))
    return None


def _doi_arxiv(e):
    "the arXiv identifier of an arXiv DOI of the entry, or None"
    doi = normalize_doi(get_entry_val(e, 'doi', ''))
    arxiv = arxiv_of_doi(doi) if doi else None
    return normalize_arxiv(arxiv) if arxiv else None


def entry_arxiv(e):
    "the arXiv identifier of an entry: of the eprint field, else of an arXiv DOI ('' if none)"
    return _eprint_arxiv(e) or _doi_arxiv(e) or ''


def parse_identifier(arg):
    """(kind, normalized value) of a command-line identifier, kind being
    'doi', 'arxiv', 'isbn' or 'key'. Raise ValueError for an argument that
    starts with a digit (keys cannot) and is none of the others."""
    doi = normalize_doi(arg)
    if doi:
        return 'doi', doi
    arxiv = normalize_arxiv(arg)
    if arxiv:
        return 'arxiv', arxiv
    isbn = normalize_isbn(arg)
    if isbn:
        return 'isbn', isbn
    if arg.strip()[:1].isdigit():
        raise ValueError(f'{arg}: not a {ACCEPTED} (a key cannot start with a digit)')
    return 'key', arg.strip().lower()


def _split(value, sep=','):
    return [v.strip() for v in re.split(sep, value or '') if v.strip()]


def entry_identifiers(e):
    "the (kind, value) identifiers of an entry (see parse_identifier)"
    ids = {('key', get_entry_val(e, 'ID', '').lower())}
    for alias in _split(get_entry_val(e, 'ids', '')):
        ids.add(('key', alias.lower()))
    doi = normalize_doi(get_entry_val(e, 'doi', ''))
    if doi:
        ids.add(('doi', doi))
    # both, if the eprint field and the DOI disagree
    for arxiv in (_doi_arxiv(e), _eprint_arxiv(e)):
        if arxiv:
            ids.add(('arxiv', arxiv))
    for isbn in _split(get_entry_val(e, 'isbn', ''), '[,;]'):
        isbn = normalize_isbn(isbn)
        if isbn:
            ids.add(('isbn', isbn))
    return ids


def read_selection(args, stdin=None):
    """the identifiers of the command line, where `-` stands for the lines
    of the standard input (one per line, blank lines ignored)"""
    selection = []
    for arg in args:
        if arg == '-':
            text = (stdin or sys.stdin).read()
            selection.extend(line.strip() for line in text.splitlines() if line.strip())
        else:
            selection.append(arg)
    return selection


def select_entries(biblio, args, stdin=None):
    """the entries named by identifiers (see parse_identifier; `-` reads them
    from the standard input), in the order given and without repetition.

    An identifier that matches no entry, or several entries (e.g. an ISBN
    shared by the chapters of a book), is an error, raised before the command
    changes anything."""
    selection = read_selection(args, stdin=stdin)
    index = {}
    for e in biblio.entries:
        for ident in entry_identifiers(e):
            matches = index.setdefault(ident, [])
            if not any(e is x for x in matches):
                matches.append(e)
    entries = []
    errors = []
    for arg in selection:
        try:
            ident = parse_identifier(arg)
        except ValueError as error:
            errors.append(str(error))
            continue
        found = index.get(ident, [])
        if not found and ident[0] == 'doi':
            # a key that is a DOI (entries fetched with the DOI as key)
            found = index.get(('key', ident[1]), [])
        if not found:
            errors.append(f'{arg}: no entry found')
        elif len(found) > 1:
            errors.append(f'{arg}: several entries match: '
                          + ', '.join(get_entry_val(e, 'ID', '') for e in found))
        elif not any(found[0] is x for x in entries):
            entries.append(found[0])
    if errors:
        raise PapersExit('\n'.join(errors) + '\n(nothing was changed)')
    return entries
