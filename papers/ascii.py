"""ASCII transliteration: the table of design/data/ascii-transliteration.tsv
(AnyAscii), used by the same-paper rule, the slugs of file names and keys."""
from anyascii import anyascii

__all__ = ['to_ascii']


def to_ascii(text):
    "`text` with each character replaced by its ASCII transliteration"
    return anyascii(text)
