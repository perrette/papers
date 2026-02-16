"""Compatibility layer for bibtexparser v2.

Provides helpers for value access (v2 Entry.get returns Field, not value),
LaTeX-to-unicode conversion, and parse/write with empty-string handling.
"""

import bibtexparser
from bibtexparser import Library
from bibtexparser.model import Entry, Field


def get_entry_val(entry, key, default=''):
    """Get field value from an entry (bibtexparser v2 Entry or dict-like).

    In v2, entry.get(key, default) returns a Field object when present, not the value.
    This helper returns the string value for both v1-style dicts and v2 Entry.
    """
    if hasattr(entry, 'fields_dict'):
        # v2 Entry: special keys
        if key == 'ID':
            return entry.key
        if key == 'ENTRYTYPE':
            return entry.entry_type
        f = entry.fields_dict.get(key)
        return f.value if f is not None else default
    return entry.get(key, default)


def set_entry_key(entry, key):
    """Set the citation key of an entry (ID). In v2, entry['ID'] = x would add a literal
    Field that the writer would output; we only set entry.key so the writer uses it in @type{key}."""
    if hasattr(entry, 'key'):
        entry.key = key
    else:
        entry['ID'] = key


def update_entry(entry, other):
    """Merge key-value pairs from other into entry (dict.update style). Works with v2 Entry.
    Skips ENTRYTYPE/ID as writable fields so the writer does not emit them (v2 uses entry_type/key)."""
    for k, v in other.items():
        if k == 'ID':
            set_entry_key(entry, v)
        elif k == 'ENTRYTYPE':
            if hasattr(entry, 'entry_type'):
                entry.entry_type = v
        else:
            entry[k] = v


def entry_content_equal(entry, other, skip_keys=()):
    """Compare two entries by normalized content (field keys and values). Use instead of entry == other for v2 Entry.
    By default compares all fields including ID and file, to match v1 dict equality (no behavioural change)."""
    if entry is other:
        return True
    try:
        entry_rest = {k: get_entry_val(entry, k, '') for k, _ in entry.items() if k not in skip_keys}
        other_rest = {k: get_entry_val(other, k, '') for k, _ in other.items() if k not in skip_keys}
        return entry_rest == other_rest
    except Exception:
        return False


def entry_copy(entry):
    """Return a copy of an entry. v2 Entry has no .copy() method."""
    if hasattr(entry, 'fields_dict'):
        from bibtexparser.model import Entry as BpEntry, Field
        fields = [Field(f.key, f.value) for f in entry.fields]
        return BpEntry(entry_type=entry.entry_type, key=entry.key, fields=fields)
    return dict(entry)


def latex_to_unicode_library(library):
    """Apply LaTeX-to-Unicode decoding to a library (replaces v1 convert_to_unicode)."""
    from bibtexparser.middlewares import LatexDecodingMiddleware
    return LatexDecodingMiddleware().transform(library=library)


def convert_entry_to_unicode(entry):
    """Convert a single entry's LaTeX field values to unicode in place (replaces v1 convert_to_unicode(entry))."""
    lib = library_from_entries([entry])
    lib = latex_to_unicode_library(lib)
    update_entry(entry, lib.entries[0])


def parse_string(bibtex_str):
    """Parse a BibTeX string; returns Library. Handles empty string."""
    if not bibtex_str or not bibtex_str.strip():
        return Library()
    return bibtexparser.parse_string(bibtex_str)


def parse_file(path, encoding='utf-8'):
    """Parse a BibTeX file; returns Library."""
    return bibtexparser.parse_file(path, encoding=encoding)


def write_string(library):
    """Serialize a Library to a BibTeX string (single-space indent, double newline between entries).
    Fields are written in alphabetical order (v1-compatible) without mutating the input library."""
    from copy import deepcopy
    from bibtexparser.middlewares import SortFieldsAlphabeticallyMiddleware
    from bibtexparser.writer import BibtexFormat
    lib = deepcopy(library)
    lib = SortFieldsAlphabeticallyMiddleware().transform(library=lib)
    fmt = BibtexFormat()
    fmt.indent = " "  # test_add expected strings use one space, not tab
    fmt.block_separator = "\n"  # one newline between entries (entry already ends with \n => one blank line)
    return bibtexparser.write_string(lib, bibtex_format=fmt)


def entry_from_dict(d):
    """Build a v2 Entry from a dict (e.g. from crossref_to_bibtex)."""
    entry_type = d.get('ENTRYTYPE', 'misc')
    key = d.get('ID', 'unknown')
    fields = [
        Field(k, v) for k, v in d.items()
        if k not in ('ENTRYTYPE', 'ID')
    ]
    return Entry(entry_type=entry_type, key=key, fields=fields)


def library_from_entries(entries):
    """Build a Library from a list of Entry or dict-like entries."""
    lib = Library()
    for e in entries:
        if isinstance(e, Entry):
            lib.add(e)
        else:
            lib.add(entry_from_dict(dict(e.items())))
    return lib


def entry_to_unicode_dict(entry):
    """Return a dict of entry fields (excluding ID) with LaTeX decoded to unicode (for comparison)."""
    lib = library_from_entries([entry])
    lib = latex_to_unicode_library(lib)
    e = lib.entries[0]
    return {k: e[k] for k, _ in e.items() if k != 'ID'}
