"""Entry and library I/O (bibtexparser v2).

Value access, entry copy/compare, parse/format, and the `file` field
(parse_file, format_file). Used by bib, encoding, duplicate, extract.
No dependency on bib or encoding to avoid circular imports.
"""
import os

import bibtexparser
from bibtexparser import Library
from bibtexparser.middlewares import SortFieldsAlphabeticallyMiddleware
from bibtexparser.model import Entry, ExplicitComment, Field, ImplicitComment, Preamble, String
from bibtexparser.writer import BibtexFormat

from papers import logger


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


def parse_bibtex_file(path, encoding='utf-8'):
    """Parse a BibTeX file; returns Library."""
    return bibtexparser.parse_file(path, encoding=encoding)


# the order of the blocks of a saved bibtex (that of bibtexparser's SortBlocksByTypeAndKeyMiddleware)
BLOCK_ORDER = (String, Preamble, Entry, ImplicitComment, ExplicitComment)


def _block_sort_key(block):
    try:
        type_index = BLOCK_ORDER.index(type(block))
    except ValueError:  # e.g. the blocks that could not be parsed: at the end
        type_index = len(BLOCK_ORDER)
    return type_index, getattr(block, 'key', '')


def sort_blocks(library):
    """a new Library of the blocks of `library` (the same objects) by type
    and key, the comments above a block staying with it, in the order
    of bibtexparser's SortBlocksByTypeAndKeyMiddleware (which deep-copies
    every block)"""
    chunks, chunk = [], []
    for block in library.blocks:
        chunk.append(block)
        if not isinstance(block, (ExplicitComment, ImplicitComment)):
            chunks.append(chunk)
            chunk = []
    if chunk:  # comments at the end: sorted by the last of them
        chunks.append(chunk)
    chunks.sort(key=lambda chunk: _block_sort_key(chunk[-1]))
    return Library(blocks=[block for chunk in chunks for block in chunk], fail_on_duplicate_key=False)


def format_library(library):
    """Serialize a Library to a BibTeX string (single-space indent, newline between entries).
    Fields in alphabetical order. Mutates the library in place (field order)."""
    library = SortFieldsAlphabeticallyMiddleware().transform(library=library)
    fmt = BibtexFormat()
    fmt.indent = " "
    fmt.block_separator = "\n"
    return bibtexparser.write_string(library, bibtex_format=fmt)


# The file field
# ==============

def _parse_file(file):
    """parse a single file entry: 'path', 'path:type' or 'description:path:type',
    where the path of the three-field form may itself contain colons
    (e.g. a journal name like ": Applied Economics" in the file name)
    """
    parts = file.split(':')

    if len(parts) == 1:  # no ':'
        return file

    if len(parts) == 2:
        path, type = parts
        return path

    # description:path:type -- description and type cannot contain ':'
    return ':'.join(parts[1:-1])


def _format_file(file, type=None):
    if not type:
        type = os.path.splitext(file)[1].strip('.')
    return ':'+file+':'+type


def parse_file(file, relative_to=None):
    " return list of absolute paths "
    if not file:
        return []

    files = []
    for f in file.split(';'):
        if not f.strip():
            continue
        path = _parse_file(f)
        if not path:
            # joining an empty path to relative_to would point at a directory
            logger.warning(f'empty file path in file field (ignored): {f!r}')
            continue
        files.append(path)
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
