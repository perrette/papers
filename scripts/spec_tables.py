"""Write, or check, the data tables of the specification (design/data/).

    python scripts/spec_tables.py          # write the tables
    python scripts/spec_tables.py --check  # exit 1 if a table differs

latex-characters.tsv: the (character, LaTeX text) pairs of papers/latexenc.py.
ascii-transliteration.tsv: the ASCII transliteration of every character that
the Unidecode package transliterates to a non-empty text.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'design', 'data')
sys.path.insert(0, os.path.join(HERE, '..'))


def escape(text):
    return text.replace('\\', '\\\\').replace('\t', '\\t').replace('\n', '\\n')


def latex_table():
    from papers.latexenc import unicode_to_latex, unicode_to_crappy_latex1
    lines = ['# The character table of the papers specification (bibtex.md, sections 4.1 and 4.2).',
             '# Origin: the W3C table of characters of MathML (http://www.w3.org/Math/characters/unicode.xml),',
             '# converted to a Python table by the GitHub user beniwohli (https://gist.github.com/798549,',
             '# 2011), then used by bibserver (github.com/okfn/bibserver, MIT license) and customized in',
             '# python-bibtexparser 1.x (accent spellings corrected); vendored in papers since 2017.',
             '# Columns: code point, kind (`encode`: the LaTeX text written for the character;',
             '# `accented`: another spelling of an accented letter), LaTeX text as written (no escapes;',
             '# a trailing space is part of the text). In table order. 28 rows of the original',
             '# whose character was broken by the conversion (such as `≂-00338`) are left out.',
             'code\tkind\tlatex']
    for kind, pairs in (('encode', unicode_to_latex), ('accented', unicode_to_crappy_latex1)):
        for char, latex in pairs:
            if len(char) != 1:  # rows broken by the conversion, such as '≂-00338': never used
                continue
            lines.append(f'U+{ord(char):04X}\t{kind}\t{latex}')
    return '\n'.join(lines) + '\n'


def ascii_table():
    import unidecode
    from importlib.metadata import version
    lines = ['# The ASCII transliteration table of the papers specification (bibtex.md, section 9.1;',
             '# library.md, Slugify).',
             f'# Origin: the Unidecode package {version("Unidecode")} (Tomaž Šolc, github.com/avian2/unidecode),',
             '# a port of the Perl module Text::Unidecode by Sean M. Burke (tables copyright 2001',
             '# Sean M. Burke). License: GNU General Public License, version 2 or later; this file is',
             '# under that license, unlike the rest of papers (MIT).',
             '# Columns: code point, ASCII text (backslash written \\\\, newline \\n). A character',
             '# below U+0080 is itself; a character not listed gives an empty text.',
             'code\tascii']
    for cp in range(0x80, 0x110000):
        if 0xD800 <= cp < 0xE000:
            continue
        text = unidecode.unidecode(chr(cp))
        if text:
            lines.append(f'U+{cp:04X}\t{escape(text)}')
    return '\n'.join(lines) + '\n'


TABLES = {'latex-characters.tsv': latex_table, 'ascii-transliteration.tsv': ascii_table}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--check', action='store_true')
    o = parser.parse_args()
    differ = []
    for name, make in TABLES.items():
        path = os.path.join(DATA, name)
        text = make()
        if o.check:
            with open(path, encoding='utf-8') as f:
                if f.read() != text:
                    differ.append(name)
        else:
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)
    if differ:
        print('differ from the code:', ', '.join(differ))
        sys.exit(1)


if __name__ == '__main__':
    main()
