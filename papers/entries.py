"""Entry and library I/O (bibtexparser v2).

Value access, entry copy/compare, parse/format. Used by bib, encoding, duplicate, extract.
No dependency on bib or encoding to avoid circular imports.
"""

import bibtexparser
from bibtexparser import Library
from bibtexparser.middlewares import SortFieldsAlphabeticallyMiddleware
from bibtexparser.model import Entry, Field
from bibtexparser.writer import BibtexFormat


def get_entry_val(entry, key, default=''):
    """Get field value from an entry (v2 Entry or dict-like)."""
    if hasattr(entry, 'fields_dict'):
        if key == 'ID':
            return entry.key
        if key == 'ENTRYTYPE':
            return entry.entry_type
        f = entry.fields_dict.get(key)
        return f.value if f is not None else default
    return entry.get(key, default)


def set_entry_key(entry, key):
    """Set the citation key (ID). For v2, only set entry.key so the writer does not emit a literal ID field."""
    if hasattr(entry, 'key'):
        entry.key = key
    else:
        entry['ID'] = key


def update_entry(entry, other):
    """Merge key-value pairs from other into entry. Skips ENTRYTYPE/ID as writable fields for v2."""
    for k, v in other.items():
        if k == 'ID':
            set_entry_key(entry, v)
        elif k == 'ENTRYTYPE':
            if hasattr(entry, 'entry_type'):
                entry.entry_type = v
        else:
            entry[k] = v


def entry_content_equal(entry, other, skip_keys=()):
    """Compare two entries by normalized content. Use instead of entry == other for v2 Entry."""
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
        fields = [Field(f.key, f.value) for f in entry.fields]
        return Entry(entry_type=entry.entry_type, key=entry.key, fields=fields)
    return dict(entry)


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


def parse_string(bibtex_str):
    """Parse a BibTeX string; returns Library. Handles empty string."""
    if not bibtex_str or not bibtex_str.strip():
        return Library()
    return bibtexparser.parse_string(bibtex_str)


def parse_file(path, encoding='utf-8'):
    """Parse a BibTeX file; returns Library."""
    return bibtexparser.parse_file(path, encoding=encoding)


def format_library(library):
    """Serialize a Library to a BibTeX string (single-space indent, newline between entries).
    Fields in alphabetical order. Mutates the library in place (field order)."""
    library = SortFieldsAlphabeticallyMiddleware().transform(library=library)
    fmt = BibtexFormat()
    fmt.indent = " "
    fmt.block_separator = "\n"
    return bibtexparser.write_string(library, bibtex_format=fmt)
