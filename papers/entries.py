"""Entry and library I/O (bibtexparser v2).

Value access, entry copy/compare, parse/format, and the `file` field
(parse_file, format_file). Used by bib, encoding, duplicate, extract.
No dependency on bib or encoding to avoid circular imports.
"""
import copy
import os
import re

import bibtexparser
from bibtexparser import Library
from bibtexparser.middlewares.enclosing import AddEnclosingMiddleware
from bibtexparser.model import (DuplicateBlockKeyBlock, DuplicateFieldKeyBlock, Entry, ExplicitComment, Field,
                                ImplicitComment, ParsingFailedBlock, Preamble, String)
from bibtexparser.writer import BibtexFormat, write

from papers import logger


def get_entry_val(entry, key, default=''):
    """Get field value from an entry (v2 Entry or dict-like). Of a field
    given twice, the last one (as Entry.fields_dict, without building it)."""
    if isinstance(entry, Entry):
        if key == 'ID':
            return entry.key
        if key == 'ENTRYTYPE':
            return entry.entry_type
        for f in reversed(entry.fields):
            if f.key == key:
                return f.value
        return default
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


def lowercase_fields(library):
    """the field names of the entries in lower case (BibTeX ignores their
    case: older JabRef files write Title, Keywords...), in place. BibTeX
    also ignores the case of the keys: an entry with two fields that differ
    only by case (Title and title), or with the key of an entry before it
    in another case (smith2000 after Smith2000), is a failed block, as
    bibtexparser makes an entry with a field or key given twice exactly
    (its text is written back, see papers.bib.unreadable_blocks)"""
    keys = {}
    for e in list(library.entries):
        names = [f.key.lower() for f in e.fields]
        twice = {name for name in names if names.count(name) > 1}
        previous = keys.get(e.key.lower())
        if twice:
            library.replace(e, DuplicateFieldKeyBlock(twice, e), fail_on_duplicate_key=False)
        elif previous is not None:
            library.replace(e, DuplicateBlockKeyBlock(e.key, previous, e, e.start_line, e.raw),
                            fail_on_duplicate_key=False)
        else:
            keys[e.key.lower()] = e
            for f in e.fields:
                if f.key != f.key.lower():
                    f.key = f.key.lower()
    return library


def parse_string(bibtex_str, cache=None):
    """Parse a BibTeX string; returns Library. Handles empty string. cache:
    a papers.parsecache.Cache, whose pieces seen before are not parsed again"""
    if not bibtex_str or not bibtex_str.strip():
        return Library()
    if cache is not None:
        from papers.parsecache import parse  # papers.parsecache imports bibtexparser only
        return lowercase_fields(parse(bibtex_str, cache))
    return lowercase_fields(bibtexparser.parse_string(bibtex_str))


def parse_bibtex_file(path, encoding='utf-8'):
    """Parse a BibTeX file; returns Library."""
    return lowercase_fields(bibtexparser.parse_file(path, encoding=encoding))


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


# the enclosing of bibtexparser's default unparse stack (default_unparse_stack)
_ENCLOSING = AddEnclosingMiddleware(allow_inplace_modification=True, default_enclosing="{",
                                    reuse_previous_enclosing=False, enclose_integers=True)


def _writable_copy(block):
    """a copy of a block that the enclosing may change: new Field objects
    for an entry (its values are strings, shared), a deep copy otherwise
    (strings, preambles, comments: few)"""
    if isinstance(block, Entry):
        fields = []
        for f in block.fields:
            field = Field(f.key, f.value)
            if getattr(f, 'enclosing', None) is not None:  # e.g. month = jan
                field.enclosing = f.enclosing
            fields.append(field)
        return Entry(block.entry_type, block.key, fields)
    return copy.deepcopy(block)


# the line that bibtexparser writes above a block it could not parse
_FAILED_COMMENT = re.compile(r'% WARNING Parsing failed for the following \d+ lines\.')


def _without_failed_comments(block):
    """`block` without the lines that bibtexparser wrote above an unreadable
    block at the previous saves (it writes them again), or None if nothing
    else is left of it. They are in a comment, or at the end of the text of
    the unreadable block before (which runs to the next @). The blank lines
    at the end of an unreadable block go too: the blank line written after
    each block would be read back into it, one more at each save."""
    if isinstance(block, ParsingFailedBlock) and block.raw:
        lines = [line for line in block.raw.splitlines() if not _FAILED_COMMENT.fullmatch(line.strip())]
        raw = '\n'.join(lines).rstrip() + '\n'
        if raw != block.raw:
            block = copy.copy(block)
            block._raw = raw
        return block
    if not isinstance(block, ImplicitComment) or not _FAILED_COMMENT.search(block.comment):
        return block
    lines = [line for line in block.comment.splitlines() if not _FAILED_COMMENT.fullmatch(line.strip())]
    comment = '\n'.join(lines).strip('\n')
    return ImplicitComment(comment, start_line=block.start_line) if comment.strip() else None


def format_library(library):
    """Serialize a Library to a BibTeX string (single-space indent, newline between entries).
    Fields in alphabetical order. Mutates the library in place (field order).

    The text is that of bibtexparser.write_string with its default unparse
    stack, which deep-copies every block: here the values are enclosed in
    light copies of the blocks, written as they are (bibtexparser.writer)."""
    for e in library.entries:
        e.fields = sorted(e.fields, key=lambda f: f.key)
    blocks = [_without_failed_comments(b) for b in library.blocks]
    blocks = [_ENCLOSING.transform_block(_writable_copy(b), library) for b in blocks if b is not None]
    fmt = BibtexFormat()
    fmt.indent = " "
    fmt.block_separator = "\n"
    return write(Library(blocks=blocks, fail_on_duplicate_key=False), bibtex_format=fmt)


def split_depth0(value, sep_regex):
    "split a bibtex value on a separator outside braces"
    parts, depth, start = [], 0, 0
    pattern = re.compile(sep_regex)
    i = 0
    while i < len(value):
        c = value[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        elif depth == 0:
            m = pattern.match(value, i)
            if m:
                parts.append(value[start:i])
                start = i = m.end()
                continue
        i += 1
    parts.append(value[start:])
    return [p.strip() for p in parts]


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
