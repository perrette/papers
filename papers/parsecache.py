"""A cache of the parsed bibtex, by piece: the bibtex is cut as the history
cuts it (papers.history.pieces, about 32 entries a piece), and the blocks
that bibtexparser's splitter makes of each piece are kept, by the checksum
of the piece, in the cache folder of the machine (papers.config.CACHE_DIR).
A piece seen before is not split again.

The bibtex stays the only source: a piece is found by its content, so a
change made outside papers only splits the pieces it changed. The blocks of
all pieces make one Library, in order (duplicate keys across pieces are
found as the splitter finds them), and the middlewares of bibtexparser run
on it as on a parsed file (@string references across pieces resolve).

A piece whose blocks are not all entries, strings, preambles or comments
(a block that failed to parse, a duplicate key within the piece, an entry
cut by a line starting with @ inside a value) is not cached, and the whole
text is then parsed as before.
"""
import json
import os

import bibtexparser
from bibtexparser import Library
from bibtexparser.entrypoint import _build_parse_stack
from bibtexparser.model import Entry, ExplicitComment, Field, ImplicitComment, Preamble, String
from bibtexparser.splitter import Splitter

from papers import history, logger

# the size of the cache (bytes), beyond which the pieces least recently used are removed
CACHE_SIZE = 50 * 1024 * 1024
FORMAT = 1  # of the cached blocks: a cache of another format is not read

_KINDS = {Entry: 'entry', String: 'string', Preamble: 'preamble',
          ExplicitComment: 'explicit', ImplicitComment: 'implicit'}


def _dump(block):
    kind = _KINDS.get(type(block))
    if kind is None:
        return None
    d = {'kind': kind, 'line': block.start_line, 'raw': block.raw}
    if kind == 'entry':
        d.update(type=block.entry_type, key=block.key,
                 fields=[[f.key, f.value, f.start_line] for f in block.fields])
    elif kind == 'string':
        d.update(key=block.key, value=block.value)
    elif kind == 'preamble':
        d.update(value=block.value)
    else:
        d.update(comment=block.comment)
    return d


def _load(d, offset):
    "a block of the cache, its lines moved by `offset` (the lines of the text before its piece)"
    line = d['line'] + offset if d['line'] is not None else None
    kind = d['kind']
    if kind == 'entry':
        fields = [Field(k, v, start_line=l + offset if l is not None else None) for k, v, l in d['fields']]
        return Entry(d['type'], d['key'], fields, start_line=line, raw=d['raw'])
    if kind == 'string':
        return String(d['key'], d['value'], start_line=line, raw=d['raw'])
    if kind == 'preamble':
        return Preamble(d['value'], start_line=line, raw=d['raw'])
    cls = ExplicitComment if kind == 'explicit' else ImplicitComment
    return cls(d['comment'], start_line=line, raw=d['raw'])


class Cache:
    def __init__(self, root):
        self.root = root

    def _path(self, digest):
        return os.path.join(self.root, digest[:2], digest + '.json')

    def get(self, digest):
        "the blocks of a piece (dicts), or None"
        try:
            with open(self._path(digest)) as f:
                data = json.load(f)
            if data.get('format') != FORMAT:
                return None
            os.utime(self._path(digest))  # recently used
            return data['blocks']
        except (OSError, ValueError, AttributeError):
            return None

    def put(self, digest, blocks):
        path = self._path(digest)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = f'{path}.{os.getpid()}.tmp'
            with open(tmp, 'w') as f:
                json.dump({'format': FORMAT, 'blocks': blocks}, f)
            os.replace(tmp, path)
        except OSError as error:
            logger.debug(f'{path}: not cached ({error})')

    def prune(self, size=CACHE_SIZE):
        "remove the pieces least recently used beyond `size` bytes"
        files = []
        for dirpath, _, names in os.walk(self.root):
            for name in names:
                path = os.path.join(dirpath, name)
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                files.append((st.st_mtime, st.st_size, path))
        total = sum(size for _, size, _ in files)
        for _, file_size, path in sorted(files):
            if total <= size:
                break
            try:
                os.remove(path)
            except OSError:
                pass
            total -= file_size


def parse(text, cache):
    """the Library of a bibtex text, as bibtexparser.parse_string makes it
    (before papers' own middleware), with the blocks of the pieces seen
    before taken from `cache`"""
    blocks, offset, added = [], 0, False
    for digest, piece in _ordered(text):
        dumped = cache.get(digest)
        if dumped is None:
            split = Splitter(bibstr=piece).split().blocks
            dumped = [_dump(b) for b in split]
            if any(d is None for d in dumped):
                return bibtexparser.parse_string(text)  # a block that is not cached: the whole text
            cache.put(digest, dumped)
            added = True
        blocks.extend(_load(d, offset) for d in dumped)
        offset += piece.count('\n')
    library = Library()
    library.add(blocks, fail_on_duplicate_key=False)
    for middleware in _build_parse_stack(None, None):
        library = middleware.transform(library=library)
    if added:
        cache.prune()
    return library


def _ordered(text):
    "[(checksum, piece)] of a text, in order (a piece can come twice)"
    return [(history.sha256(p.encode('utf-8')), p) for p in history._pieces(text)]
