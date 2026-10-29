"""ASCII transliteration: the table of design/data/ascii-transliteration.tsv
(AnyAscii), used by the same-paper rule, the slugs of file names and keys."""
import re

__all__ = ['to_ascii']

_NOT_ASCII = re.compile(r'[^\x00-\x7f]+')


def _transliterate(match):
    from anyascii import anyascii
    return anyascii(match.group())


def to_ascii(text):
    "`text` with each character replaced by its ASCII transliteration"
    # one character at a time, so only the runs of non-ASCII characters need the table
    return _NOT_ASCII.sub(_transliterate, text)
