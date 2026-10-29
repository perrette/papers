"""The rules of design/bibtex.md that no other test checks: one class per
section of the specification, each test naming its section.

Most tests check what papers writes (the bytes of the bibtex, of
.papers/distinct.json) or what it reads from a bibtex text, through the
command line where that is how users meet the rule."""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from papers.bib import Biblio, append_abc
from papers.entries import get_entry_val, parse_string, parse_file, format_file
from papers.utils import PapersExit

from tests.common import LibraryTest, paperscmd


def written(text):
    "the text papers writes for a bibtex text (sorted and formatted, as at a save)"
    biblio = Biblio(parse_string(text))
    biblio.sort()
    return biblio.format()


def entries(text):
    "the entries papers reads from a bibtex text"
    return parse_string(text).entries


def fields(entry):
    "[(name, value)] of an entry, in order"
    return [(f.key, f.value) for f in entry.fields]


class SpecLibrary(LibraryTest):
    "a bibtex in a temporary directory, without library configuration (see LibraryTest)"

    def text(self):
        return Path(self.bibtex).read_text(encoding='utf-8')

    def touch(self):
        "make a change, so that the bibtex is saved"
        self.papers('edit spec0 --set note=x')


# 1. Text encoding and line endings
# =================================

class TestEncodingAndLineEnds(SpecLibrary):

    lib = '@misc{spec0,\n title = {T}\n}\n'

    def test_line_ends_read_and_written_as_lf(self):
        "bibtex.md 1: \\n, \\r\\n and \\r are read as \\n; papers writes \\n"
        Path(self.bibtex).write_bytes('@misc{spec0,\r\n title = {Zéd\r\nline\rthree}\r\n}\r\n'.encode('utf-8'))
        self.assertEqual(get_entry_val(self.entry('spec0'), 'title'), 'Zéd\nline\nthree')
        self.touch()
        data = Path(self.bibtex).read_bytes()
        self.assertNotIn(b'\r', data)
        self.assertEqual(data, '@misc{spec0,\n note = {x},\n title = {Zéd\nline\nthree}\n}\n'.encode('utf-8'))

    def test_invalid_utf8_stops(self):
        "bibtex.md 1: a bibtex that is not valid UTF-8 cannot be loaded"
        Path(self.bibtex).write_bytes(b'@misc{spec0,\n title = {Z\xe9d}\n}\n')  # latin-1
        with self.assertRaises((UnicodeDecodeError, PapersExit, SystemExit)):
            self.papers('list')

    def test_byte_order_mark_of_an_added_bibtex(self):
        "bibtex.md 1: the byte order mark of a bibtex given to papers add is dropped"
        other = self.path('other.bib')
        Path(other).write_bytes('﻿@misc{other1,\n title = {Other}\n}\n'.encode('utf-8'))
        self.papers(f'add {other}')
        self.assertIn('other1', self.entries())
        self.assertFalse(Path(self.bibtex).read_bytes().startswith(b'\xef\xbb\xbf'))

    def test_byte_order_mark_from_the_editor(self):
        "bibtex.md 1: the byte order mark of the text that comes back from the editor of papers edit is dropped"
        editor = self.path('editor.py')
        Path(editor).write_text('import sys\n'
                                'p = sys.argv[1]\n'
                                't = open(p, encoding="utf-8").read().replace("{T}", "{Edited}")\n'
                                'open(p, "w", encoding="utf-8").write("\\ufeff" + t)\n')
        self.papers('edit spec0', editor=f'python3 {editor}')
        self.assertEqual(get_entry_val(self.entry('spec0'), 'title'), 'Edited')
        self.assertTrue(self.text().startswith('@misc{spec0,'))

    def test_distinct_json_utf8_lf(self):
        "bibtex.md 1, 9.4: distinct.json is UTF-8 with \\n line ends"
        from papers.duplicate import Distinct
        path = self.path('.papers', 'distinct.json')
        d = Distinct(path=path)
        d.add(entries('@article{a, author = {Müller}, title = {Ünicode}}')[0],
              entries('@article{b, author = {Smith}, title = {Other}}')[0])
        d.save()
        data = Path(path).read_bytes()
        self.assertNotIn(b'\r', data)
        data.decode('ascii')  # non-ASCII characters are escaped


# 2. Reading
# ==========

class TestBlocks(unittest.TestCase):
    "bibtex.md 2.1"

    def test_block_kinds(self):
        "bibtex.md 2.1: entry, string, preamble, explicit and implicit comment, failed block"
        from bibtexparser.model import Entry, ExplicitComment, ImplicitComment, ParsingFailedBlock, Preamble, String
        lib = parse_string('% implicit\n@string{a = {A}}\n@preamble{"p"}\n@comment{explicit}\n'
                           '@article{k, title = {T}}\n@article{bad, title = {x}\n')
        self.assertEqual([type(b) for b in lib.blocks],
                         [ImplicitComment, String, Preamble, ExplicitComment, Entry, ParsingFailedBlock])

    def test_keyword_case_delimiters_whitespace(self):
        "bibtex.md 2.1: @ keyword in any case, {...} or (...), whitespace before the delimiter"
        lib = parse_string('@ARTICLE{a, title = {A}}\n@Article (b, title = {B})\n@String{s = {S}}\n'
                           '@Comment{c}\n@misc\t{d, title = {D}}\n')
        self.assertEqual([(e.entry_type, e.key) for e in lib.entries],
                         [('article', 'a'), ('article', 'b'), ('misc', 'd')])
        self.assertEqual([s.key for s in lib.strings], ['s'])
        self.assertEqual(len(lib.comments), 1)
        self.assertEqual(lib.failed_blocks, [])


class TestEntries(unittest.TestCase):
    "bibtex.md 2.2"

    def test_type_key_field_names(self):
        "bibtex.md 2.2: type lower-cased, any word; key trimmed, case kept; field names trimmed, lower-cased"
        e, = entries('@MyType{  SmithK2000 , TITLE = {T}, Journal = {J}}')
        self.assertEqual((e.entry_type, e.key), ('mytype', 'SmithK2000'))
        self.assertEqual([f.key for f in e.fields], ['title', 'journal'])

    def test_entry_without_fields(self):
        "bibtex.md 2.2: an entry with no comma and no fields is read, without fields"
        e, = entries('@misc{K0}')
        self.assertEqual((e.key, e.fields), ('K0', []))

    def test_values(self):
        "bibtex.md 2.2: value enclosing removed once, inside kept exactly; trailing comma; bare values"
        e, = entries('@article{k,\n'
                     ' title = { The {AMOC} \\& \n  more },\n'
                     ' note = "a \\"{b}\\" c",\n'
                     ' pages = 1--10,\n'
                     ' series = {a} # {b},\n'
                     ' month = jan,\n'
                     ' year = 2000,\n'
                     '}')
        self.assertEqual(fields(e), [('title', ' The {AMOC} \\& \n  more '),
                                     ('note', 'a \\"{b}\\" c'),
                                     ('pages', '1--10'), ('series', '{a} # {b}'), ('month', 'jan'),
                                     ('year', '2000')])
        self.assertEqual(written('@article{k, year = 2000, month = jan, pages = 1--10, series = {a} # {b}}'),
                         '@article{k,\n month = jan,\n pages = 1--10,\n series = {a} # {b},\n year = {2000}\n}\n')

    def test_values_not_decoded(self):
        "bibtex.md 2.2: LaTeX in values stays as written"
        e, = entries('@article{k, author = {M{\\"u}ller}, title = {A \\& B}}')
        self.assertEqual(fields(e), [('author', 'M{\\"u}ller'), ('title', 'A \\& B')])


class TestStringsAndPreamble(unittest.TestCase):
    "bibtex.md 2.3"

    def test_references_resolved(self):
        "bibtex.md 2.3: a bare word naming a string (any case, defined before or after) takes its value"
        text = ('@article{a, journal = JGR}\n'
                '@String{jgr = "Journal of Geophysical Research"}\n'
                '@article{b, journal = jgr, note = jgr # " extra"}\n')
        a, b = entries(text)
        self.assertEqual(get_entry_val(a, 'journal'), 'Journal of Geophysical Research')
        self.assertEqual(get_entry_val(b, 'journal'), 'Journal of Geophysical Research')
        self.assertEqual(get_entry_val(b, 'note'), 'jgr # " extra"')  # concatenation: bare

    def test_later_string_wins(self):
        "bibtex.md 2.3: of two strings whose names differ only by case, the later one wins"
        e, = entries('@string{Abc = {first}}\n@string{abc = {second}}\n@article{k, journal = ABC}\n')
        self.assertEqual(get_entry_val(e, 'journal'), 'second')

    def test_written(self):
        "bibtex.md 2.3: the reference is written as the value, the @string block is kept; the preamble as written"
        self.assertEqual(written('@String( jgr = "JGR" )\n@preamble{ "\\noop" }\n@article{k, journal = jgr}\n'),
                         '@string{jgr = {JGR}}\n\n@preamble{ "\\noop" }\n\n@article{k,\n journal = {JGR}\n}\n')


class TestComments(unittest.TestCase):
    "bibtex.md 2.4"

    def test_explicit_comment_trimmed(self):
        "bibtex.md 2.4: an explicit comment is trimmed"
        self.assertEqual(written('@comment{  some text \n }\n'), '@comment{some text}\n')

    def test_implicit_comment_one_block(self):
        "bibtex.md 2.4: the text between two blocks is one implicit comment, trimmed"
        lib = parse_string('@misc{a}\n\n\n   % one\n\n% two\nfree text  \n\n@misc{b}\n')
        self.assertEqual([c.comment for c in lib.comments], ['% one\n\n% two\nfree text'])

    def test_percent_is_not_special(self):
        "bibtex.md 2.4: % @article{x, ...} is an entry; an e-mail address is text"
        lib = parse_string('% @article{x, title = {X}}\nwrite to me@example.org\n')
        self.assertEqual([e.key for e in lib.entries], ['x'])
        self.assertEqual([c.comment for c in lib.comments], ['%', 'write to me@example.org'])


class TestFailedBlocks(SpecLibrary):
    "bibtex.md 2.5"

    lib = ('@misc{spec0,\n title = {T}\n}\n\n'
           '@article{twice,\n title = {A},\n title = {B}\n}\n\n'
           '@article{broken,\n title = {no end\n'
           '@article{after, title = {LeQua @ {CLEF}}}\n\n'
           '@article{spec0,\n title = {same key}\n}\n')

    def test_kinds_and_warning(self):
        "bibtex.md 2.5: syntax error, field given twice, duplicate key; the warning names the lines"
        from papers.bib import unreadable_message
        biblio = Biblio.load(self.bibtex, '')
        self.assertEqual([e.key for e in biblio.entries], ['spec0', 'after'])
        self.assertEqual(biblio.unreadable, [(5, "a field given twice: 'title'"), (10, 'syntax error'),
                                             (14, "a key given twice (keys ignore case): 'spec0'")])
        self.assertEqual(unreadable_message('papers.bib', [(5, 'syntax error'), (7, 'syntax error')]),
                         'papers.bib: 2 entries could not be read (line 5: syntax error; line 7: syntax error): '
                         'papers ignores them until they are fixed')

    def test_at_starts_a_block(self):
        "bibtex.md 2.5: an @ first on a line ends the open failed block; elsewhere in a value it is text"
        biblio = Biblio.load(self.bibtex, '')
        self.assertEqual(get_entry_val(biblio.entries[1], 'title'), 'LeQua @ {CLEF}')
        broken = biblio.db.failed_blocks[1]
        self.assertEqual(broken.raw.rstrip('\n'), '@article{broken,\n title = {no end')

    def test_written_back_unchanged(self):
        "bibtex.md 2.5, 3.2: failed blocks are kept as raw text under a warning line; a second save changes nothing"
        self.touch()
        first = self.text()
        self.assertIn('% WARNING Parsing failed for the following 4 lines.\n'
                      '@article{twice,\n title = {A},\n title = {B}\n}\n\n', first)
        self.assertIn('% WARNING Parsing failed for the following 2 lines.\n'
                      '@article{broken,\n title = {no end\n\n', first)
        self.papers('edit spec0 --set note=y')
        self.assertEqual(self.text(), first.replace('note = {x}', 'note = {y}'))

    def test_field_names_and_keys_ignore_case(self):
        "bibtex.md 2.5, 2.6: Title and title are a field given twice; smith2000 after Smith2000 a key given twice"
        biblio = Biblio(parse_string('@article{Smith2000, title = {A}}\n@article{x, Title = {B}, title = {C}}\n'
                                     '@article{smith2000, title = {D}}\n'))
        self.assertEqual([e.key for e in biblio.entries], ['Smith2000'])
        self.assertEqual(len(biblio.db.failed_blocks), 2)


class TestDuplicateKeys(unittest.TestCase):
    "bibtex.md 2.6"

    def test_strings(self):
        "bibtex.md 2.5, 2.6: a string with exactly the name of an earlier one is a failed block; another case is read"
        lib = parse_string('@string{a = {1}}\n@string{a = {2}}\n@string{A = {3}}\n')
        self.assertEqual([type(b).__name__ for b in lib.blocks], ['String', 'DuplicateBlockKeyBlock', 'String'])

    def test_first_is_read(self):
        "bibtex.md 2.6: of two entries with the same key, in any case, the first is read, the second is a failed block"
        lib = parse_string('@article{Smith2000, title = {A}}\n@article{Smith2000, title = {B}}\n'
                           '@article{SMITH2000, title = {C}}\n')
        self.assertEqual([get_entry_val(e, 'title') for e in lib.entries], ['A'])
        self.assertEqual(len(lib.failed_blocks), 2)
        self.assertEqual(written('@article{b, title = {A}}\n@article{B, title = {B}}\n'),
                         '@article{b,\n title = {A}\n}\n\n'
                         '% WARNING Parsing failed for the following 1 lines.\n@article{B, title = {B}}\n\n')


# 3. Writing
# ==========

class TestBlockOrder(unittest.TestCase):
    "bibtex.md 3.1"

    def test_order(self):
        "bibtex.md 3.1: chunks sorted by rank and key, by code point; comments stay above their block"
        text = ('@article{alpha1999, title = {a}}\n'
                '% above Zeta\n@article{Zeta2020, title = {z}}\n'
                '@comment{above Beta}\n@article{Beta2001, title = {b}}\n'
                '@preamble{"p2"}\n@string{zz = {Z}}\n@preamble{"p1"}\n@string{aa = {A}}\n'
                '@article{bad, title = {x}\n'
                '@article{alpha2000, title = {a}}\n'
                '% trailing\n')
        out = written(text)
        order = [line for line in out.splitlines() if line.startswith(('@', '%'))]
        self.assertEqual(order, ['@string{aa = {A}}', '@string{zz = {Z}}', '@preamble{"p2"}', '@preamble{"p1"}',
                                 '@comment{above Beta}', '@article{Beta2001,', '% above Zeta', '@article{Zeta2020,',
                                 '@article{alpha1999,', '@article{alpha2000,', '% trailing',
                                 '% WARNING Parsing failed for the following 1 lines.', '@article{bad, title = {x}'])


class TestLayout(unittest.TestCase):
    "bibtex.md 3.2"

    def test_entry(self):
        "bibtex.md 3.2: one field per line, one space of indentation, fields sorted by code point, stable"
        self.assertEqual(written('@Article{K, x_y = {4}, x-a = {3}, abstract = {2}, a1 = {1}}'),
                         '@article{K,\n a1 = {1},\n abstract = {2},\n x-a = {3},\n x_y = {4}\n}\n')

    def test_entry_without_fields(self):
        "bibtex.md 3.2: an entry without fields"
        self.assertEqual(written('@misc{K0}'), '@misc{K0,\n}\n')

    def test_multiline_value(self):
        "bibtex.md 3.2: a value with newlines is written with them"
        self.assertEqual(written('@misc{K, abstract = {one\n    two}}'), '@misc{K,\n abstract = {one\n    two}\n}\n')

    def test_other_blocks_and_separators(self):
        "bibtex.md 3.2: string, preamble, comments; one empty line between blocks; no blank line at the end"
        self.assertEqual(written('% c\n@STRING(s = "v")\n@preamble{ x }\n@comment{ e }\n@misc{k, t = {1}}\n'),
                         '% c\n\n@string{s = {v}}\n\n@preamble{ x }\n\n@comment{e}\n\n@misc{k,\n t = {1}\n}\n')

    def test_failed_block_last(self):
        "bibtex.md 3.2: a failed block last: the file ends with one empty line"
        self.assertEqual(written('@misc{k, t = {1}}\n@misc{bad, t = {\n'),
                         '@misc{k,\n t = {1}\n}\n\n% WARNING Parsing failed for the following 1 lines.\n'
                         '@misc{bad, t = {\n\n')

    def test_empty_library(self):
        "bibtex.md 3.2: a library with no blocks is written as an empty file"
        self.assertEqual(written(''), '')

    def test_warning_line_removed_at_reading(self):
        "bibtex.md 3.2: a comment that is only a warning line is dropped at reading"
        text = '% WARNING Parsing failed for the following 3 lines.\n\n@misc{k, t = {1}}\n'
        self.assertEqual(written(text), '@misc{k,\n t = {1}\n}\n')


class TestValues(unittest.TestCase):
    "bibtex.md 3.3"

    def test_braces(self):
        "bibtex.md 3.3: values in braces, integers too, quotes never used"
        self.assertEqual(written('@misc{k, title = "A", number = 007, year = 2000}'),
                         '@misc{k,\n number = {007},\n title = {A},\n year = {2000}\n}\n')

    def test_bare_value_that_cannot_stay_bare(self):
        "bibtex.md 3.3: a bare value that would not read back unenclosed is written in braces"
        from bibtexparser.model import Field
        from papers.entries import format_library, library_from_entries
        e, = entries('@misc{k, month = jan}')
        for value in ('a, b', 'a = b', 'x\ny', '{open'):
            e.fields[0] = Field('month', value)
            e.fields[0].enclosing = 'no-enclosing'
            self.assertNotIn(f'month = {value}', format_library(library_from_entries([e])), value)

    def test_value_set_by_papers(self):
        "bibtex.md 3.3: a value set by papers is written in braces"
        biblio = Biblio(parse_string('@misc{k, month = jan}'))
        biblio.entries[0]['month'] = 'feb'
        self.assertEqual(biblio.format(), '@misc{k,\n month = {feb}\n}\n')

    def test_example(self):
        "bibtex.md 3.3: the example of the specification"
        text = ('% my library\n@String{ agu = "AGU" }\n\n@ARTICLE{smith2000,\n'
                '  Title    = "The {AMOC} and sea level",\n  Author   = {Smith, John and Doe, Jane},\n'
                '  journal  = agu,\n  Year     = 2000,\n  month    = jan,\n'
                '  file     = {Full Text:files/smith2000.pdf:application/pdf},\n}\n\n'
                '@book{Brown1999, title={A book}, isbn={0-306-40615-2}}\n')
        self.assertEqual(written(text),
                         '% my library\n\n@string{agu = {AGU}}\n\n@book{Brown1999,\n isbn = {0-306-40615-2},\n'
                         ' title = {A book}\n}\n\n@article{smith2000,\n author = {Smith, John and Doe, Jane},\n'
                         ' file = {Full Text:files/smith2000.pdf:application/pdf},\n journal = {AGU},\n'
                         ' month = jan,\n title = {The {AMOC} and sea level},\n year = {2000}\n}\n')

    def test_merge_keeps_bare(self):
        "bibtex.md 3.3, 10.7: a merged value stays bare when it is the bare value of one of the entries"
        from papers.merge import Merge
        a, b = entries('@article{a, title = {T}, author = {Smith, J}, year = {2000}}\n'
                       '@article{b, title = {T}, author = {Smith, J}, month = jan, note = {x}, year = {2000}}\n')
        merged = Merge([a, b]).result()
        from papers.entries import format_library, library_from_entries
        text = format_library(library_from_entries([merged]))
        self.assertIn(' month = jan,\n', text)
        self.assertIn(' note = {x},\n', text)


class TestWhenWritten(SpecLibrary):
    "bibtex.md 3.4"

    lib = '@misc{spec0,\n title = {T}\n}\n'

    def test_unchanged_text_not_written(self):
        "bibtex.md 3.4: a text already on disk is not written (modification time kept)"
        os.utime(self.bibtex, ns=(1, 1))
        biblio = Biblio.load(self.bibtex, '')
        biblio.save(self.bibtex)
        self.assertEqual(os.stat(self.bibtex).st_mtime_ns, 1)

    def test_changed_on_disk_refused(self):
        "bibtex.md 3.4: a bibtex written by another program since papers read it is not written"
        from papers.bib import BibtexChanged
        biblio = Biblio.load(self.bibtex, '')
        Path(self.bibtex).write_text('@misc{other,\n title = {O}\n}\n')
        biblio.entries[0]['note'] = 'x'
        with self.assertRaises(BibtexChanged):
            biblio.save(self.bibtex)
        self.assertEqual(self.text(), '@misc{other,\n title = {O}\n}\n')


class TestNormalized(SpecLibrary):
    "bibtex.md 3.5"

    lib = ('@ARTICLE{spec0,\n  Title = "The {AMOC}",\n  author = {M{\\"u}ller, J. and Doe, Jane},\n'
           '  keywords = {a;b, c},\n  file = {Desc:x.pdf:application/pdf},\n  doi = {https://doi.org/10.1/X}\n}\n')

    def test_only_layout(self):
        "bibtex.md 3.5: a save changes only order, case of types and names, enclosing and strings"
        self.touch()
        self.assertEqual(self.text(), '@article{spec0,\n author = {M{\\"u}ller, J. and Doe, Jane},\n'
                                      ' doi = {https://doi.org/10.1/X},\n file = {Desc:x.pdf:application/pdf},\n'
                                      ' keywords = {a;b, c},\n note = {x},\n title = {The {AMOC}}\n}\n')

    def test_name_formatting(self):
        "bibtex.md 3.5: Family, Given; splits at brace depth 0"
        from papers.encoding import standard_name
        self.assertEqual(standard_name('John {van der Berg} and Smith, J. and {World Health Organization} and '
                                       'Jane  Doe AND x and {Barnes and Noble}'),
                         '{van der Berg}, John and Smith, J. and {World Health Organization} and '
                         'x, Jane Doe AND and {Barnes and Noble}')


# 4. LaTeX and Unicode
# ====================

class TestLatexToUnicode(unittest.TestCase):
    "bibtex.md 4.1"

    def decode(self, cases, **kw):
        from papers.latex import latex_to_unicode
        for latex, text in cases.items():
            self.assertEqual(latex_to_unicode(latex, **kw), text, latex)

    def test_accents(self):
        "bibtex.md 4.1: an accent goes on the first character of its argument, in every spelling"
        self.decode({'{\\"u}': 'ü', '\\"{u}': 'ü', '\\"u': 'ü', "\\'e": 'é', "\\' e": 'é', 'T\\^ete': 'Tête',
                     '\\c c': 'ç', '\\c{c}a': 'ça', '\\v{S}koda': 'Škoda', "{\\'{\\i}}": 'í', "\\'\\i": 'í',
                     '\\H{o}': 'ő', '\\k{a}': 'ą', '\\r{a}': 'å', '\\u{g}': 'ğ', '\\={a}': 'ā', '\\.{z}': 'ż',
                     '\\d{s}': 'ṣ', "\\'{\\\"u}": 'ǘ', '\\acute{\\ddot{\\iota}}': 'ΐ', '\\"{}': ''})

    def test_characters(self):
        "bibtex.md 4.1: commands that name a character, and escaped characters"
        self.decode({'\\o': 'ø', '{\\O}': 'Ø', '\\ss{}': 'ß', '\\AA ngstr': 'Ångstr', '{\\ae}': 'æ', '\\l': 'ł',
                     'A{\\dh}algeirsd{\\\'o}ttir': 'Aðalgeirsdóttir', '{\\th}': 'þ', '$\\alpha$-decay': 'α-decay',
                     '\\Omega': 'Ω', '\\textendash': '–', 'x\\space y': 'x y',
                     '50\\%': '50%', 'a \\& b': 'a & b', '\\$\\#\\_\\{\\}': '$#_{}'})

    def test_other_commands(self):
        "bibtex.md 4.1: formatting commands give their argument, other commands are kept as written"
        self.decode({'\\textit{Foo} bar': 'Foo bar', '\\emph{x}': 'x', '\\url{x}': 'x', '\\mbox{CO2}': 'CO2',
                     '\\foo{bar} baz': '\\foobar baz', 'a\\-b': 'ab', 'a\\,b': 'a b'})

    def test_text_signs(self):
        "bibtex.md 4.1: braces and $ dropped, ~ a no-break space, -- and --- dashes, `` and '' quotes"
        self.decode({'a {b} c': 'a b c', 'CO$_2$': 'CO_2', 'a~b': 'a\u00a0b', 'Ice--ocean': 'Ice–ocean',
                     'a---b': 'a—b', "``x''": '"x"', 'plain text': 'plain text', '': ''})

    def test_paths(self):
        "bibtex.md 4.1: in a file path only the commands and braces are decoded"
        self.decode({'a--b~c$d.pdf': 'a--b~c$d.pdf', 'x{\\_}{\\"u}.pdf': 'x_ü.pdf'}, text=False)

    def test_unicode_to_latex_decodes_back(self):
        "bibtex.md 4.1: the text written by check --encoding latex (4.2) decodes to the same text"
        from papers.latex import latex_to_unicode
        from papers.latexenc import string_to_latex
        for text in ('Müller', 'Ångström', 'Straße', 'Łódź', 'Dvořák', 'Þór', 'αβγ', 'François Ça', '50% & x_1'):
            self.assertEqual(latex_to_unicode(string_to_latex(text)), text, text)

class TestUnicodeToLatex(SpecLibrary):
    "bibtex.md 4.2"

    lib = ('@article{spec0,\n abstract = {Müller},\n doi = {10.1/a_b},\n eprint = {a_b},\n file = {:x_y.pdf:pdf},\n'
           ' ids = {old_key},\n isbn = {ü},\n issn = {ü},\n note = {Müller étoile_x ~ 50% & {GCM}},\n'
           ' title = {Über},\n url = {http://x/a_b}\n}\n')

    def test_check_encoding_latex(self):
        "bibtex.md 4.2: each character by its table text; fields abstract, file, doi, url, eprint, isbn, issn, ids kept"
        self.papers('check --encoding latex -y')
        e = self.entry('spec0')
        self.assertEqual(get_entry_val(e, 'note'), 'M{\\"u}ller {\\\'e}toile\\_x \\textasciitilde  50\\% \\& {GCM}')
        self.assertEqual(get_entry_val(e, 'title'), '{\\"U}ber')
        for name, value in [('abstract', 'Müller'), ('doi', '10.1/a_b'), ('eprint', 'a_b'), ('file', ':x_y.pdf:pdf'),
                            ('ids', 'old_key'), ('isbn', 'ü'), ('issn', 'ü'), ('url', 'http://x/a_b')]:
            self.assertEqual(get_entry_val(e, name), value, name)


# 5. The file field
# =================

class TestFileSyntax(unittest.TestCase):
    "bibtex.md 5.1"

    def test_reading(self):
        "bibtex.md 5.1: links separated by ;, three forms, empty links skipped, paths trimmed, no escaping"
        cases = {
            'a.pdf': ['a.pdf'], 'a.pdf:pdf': ['a.pdf'], 'Desc:dir/a: b.pdf:pdf': ['dir/a: b.pdf'],
            'Full Text:files/x.pdf:application/pdf': ['files/x.pdf'],
            ';;a.pdf; ;b.pdf': ['a.pdf', 'b.pdf'], ' a.pdf :pdf': ['a.pdf'],
            'a\\:b.pdf': ['a\\'], 'C:\\x.pdf': ['C'], '::pdf': [],
        }
        for field, paths in cases.items():
            self.assertEqual(parse_file(field), paths, field)

    def test_writing(self):
        "bibtex.md 5.1: :path:type, the type the extension as written, links joined by ; without spaces"
        self.assertEqual(format_file(['files/smith2000.pdf', '../other/notes.txt', 'files/README', 'x.tar.gz',
                                      'dir/.hidden', 'A.PDF']),
                         ':files/smith2000.pdf:pdf;:../other/notes.txt:txt;:files/README:;:x.tar.gz:gz;'
                         ':dir/.hidden:;:A.PDF:PDF')


class TestFilePaths(SpecLibrary):
    "bibtex.md 5.2"

    lib = '@misc{spec0,\n title = {T}\n}\n'

    def test_relative_to_bibtex(self):
        "bibtex.md 5.2: a relative path is relative to the bibtex directory; written relative and normalized"
        biblio = Biblio.load(self.bibtex, '')
        self.assertEqual(biblio.get_files(biblio.entries[0]), [])
        os.makedirs(self.path('files'))
        outside = os.path.join(os.path.dirname(self.dir), 'other', 'notes.txt')
        biblio.set_files(biblio.entries[0], [self.path('files', '.', 'a.pdf'), outside,
                                             self.path('files', '.', 'a.pdf')])
        self.assertEqual(get_entry_val(biblio.entries[0], 'file'),
                         ':files/a.pdf:pdf;:../other/notes.txt:txt')
        self.assertEqual(biblio.get_files(biblio.entries[0]), [self.path('files', 'a.pdf'),
                                                               os.path.normpath(outside)])

    def test_one_file_however_written(self):
        "bibtex.md 5.2: two spellings of one file are one link"
        biblio = Biblio.load(self.bibtex, '')
        biblio.set_files(biblio.entries[0], [self.path('files', '.', 'a.pdf'), self.path('files', 'a.pdf')])
        self.assertEqual(get_entry_val(biblio.entries[0], 'file'), ':files/a.pdf:pdf')

    def test_no_link_left(self):
        "bibtex.md 5.2: if no link is left, the field is removed"
        biblio = Biblio(parse_string('@misc{k, file = {:a.pdf:pdf}}'), relative_to=self.dir)
        biblio.set_files(biblio.entries[0], [])
        self.assertNotIn('file', biblio.entries[0])

    def test_rewritten_at_load(self):
        "bibtex.md 5.2: at load, absolute links of a relative library become relative, and the reverse"
        lib = self.path('lib')
        os.makedirs(lib)
        bibtex = os.path.join(lib, 'papers.bib')
        paperscmd('init --bibtex papers.bib', cwd=lib)
        Path(bibtex).write_text('@misc{spec0,\n file = {Desc:%s:application/pdf;b.pdf:PDF},\n title = {T}\n}\n'
                                % os.path.join(lib, 'a.pdf'))
        paperscmd('edit spec0 --set note=x', cwd=lib)
        self.assertIn(' file = {:a.pdf:pdf;:b.pdf:pdf},\n', Path(bibtex).read_text())
        paperscmd('config paths absolute', cwd=lib)
        self.assertIn(' file = {:%s:pdf;:%s:pdf},\n' % (os.path.join(lib, 'a.pdf'), os.path.join(lib, 'b.pdf')),
                      Path(bibtex).read_text())


# 6. The keywords field and tags
# ==============================

class TestTags(SpecLibrary):
    "bibtex.md 6"

    lib = ('@misc{spec0,\n keywords = {a;b,  c ,, climate/amoc/tipping},\n title = {T}\n}\n\n'
           '@misc{spec1,\n keywords = {Climate},\n title = {U}\n}\n')

    def tags(self, key):
        from papers.encoding import parse_keywords
        return parse_keywords(self.entry(key))

    def test_syntax(self):
        "bibtex.md 6: split on , only, trimmed, empty tags dropped; the field is not rewritten until tags change"
        self.assertEqual(self.tags('spec0'), ['a;b', 'c', 'climate/amoc/tipping'])
        self.papers('edit spec1 --set note=x')
        self.assertIn(' keywords = {a;b,  c ,, climate/amoc/tipping},\n', self.text())
        self.papers('tag spec0 --add d')
        self.assertIn(' keywords = {a;b, c, climate/amoc/tipping, d},\n', self.text())
        self.papers('tag spec0 --rm a;b c climate/amoc/tipping d')
        self.assertNotIn('keywords', self.entry('spec0'))

    def test_add_remove_rename_ignore_case(self):
        "bibtex.md 6: add, remove and rename compare tags without case; the spelling already there is kept"
        self.papers('tag spec1 --add climate x X')
        self.assertEqual(self.tags('spec1'), ['Climate', 'x'])
        self.papers('tag spec1 --rm CLIMATE')
        self.assertEqual(self.tags('spec1'), ['x'])
        self.papers('tag --rename CLIMATE ocean')
        self.assertEqual(self.tags('spec0'), ['a;b', 'c', 'ocean/amoc/tipping'])

    def test_counting(self):
        "bibtex.md 6: an entry counts once for each of its tags and for each of their parents"
        from papers.cli.entry_cmds import tag_counts
        self.assertEqual(tag_counts(self.entries().values()),
                         {'a;b': 1, 'c': 1, 'climate': 1, 'climate/amoc': 1, 'climate/amoc/tipping': 1, 'Climate': 1})

    def test_matching(self):
        "bibtex.md 6: --tag: lower case, trailing / dropped, shell pattern on the whole tag, or a parent"
        from papers.cli.entry_cmds import tag_matches
        self.assertTrue(tag_matches('Climate/AMOC', 'climate/'))
        self.assertTrue(tag_matches('climate/amoc', 'clim*'))
        self.assertTrue(tag_matches('climate/amoc', 'c?imate/[a-z]moc'))
        self.assertFalse(tag_matches('climate-review', 'climate'))
        self.assertFalse(tag_matches('climate', 'climate/amoc'))


# 7. Keys: ids and crossref
# =========================

class TestIds(SpecLibrary):
    "bibtex.md 7.1"

    lib = ('@misc{spec0,\n ids = { old1 ,, Old2,},\n title = {T}\n}\n\n'
           '@misc{old2,\n title = {U}\n}\n')

    def test_read_and_selected(self):
        "bibtex.md 7.1: ids split on , and trimmed; a former key selects the entry; the key of an entry wins"
        from papers.identifiers import entry_identifiers
        self.assertTrue({('key', 'old1'), ('key', 'old2')} <= entry_identifiers(self.entry('spec0')))
        self.papers('edit OLD1 --set note=a')
        self.assertEqual(get_entry_val(self.entry('spec0'), 'note'), 'a')
        self.papers('edit old2 --set note=b')
        self.assertEqual(get_entry_val(self.entry('old2'), 'note'), 'b')
        self.assertEqual(get_entry_val(self.entry('spec0'), 'note'), 'a')

    def test_keep_old_key_written(self):
        "bibtex.md 7.1: --keep-old-key appends the former key, ids written joined by ', '"
        self.papers('edit spec0 --key new2000 --keep-old-key')
        self.assertIn(' ids = {old1, Old2, spec0},\n', self.text())


class TestKeyValidity(SpecLibrary):
    "bibtex.md 7.2"

    lib = '@misc{spec0,\n title = {T}\n}\n\n@misc{Other,\n title = {U}\n}\n'

    def test_refused(self):
        "bibtex.md 7.2: empty, leading digit, whitespace, , { } \" # % ~ = ( ) \\, or the key of another entry"
        for key in ['1abc', 'a\tb', 'other'] + [f'a{c}b' for c in ',{}"#%~=()\\']:
            with self.assertRaises(PapersExit, msg=key):
                self.papers(f"edit spec0 --key '{key}'")
        self.assertEqual(sorted(self.entries()), ['Other', 'spec0'])
        self.papers('edit spec0 --key a-b_c:d.e/f+g')
        self.assertIn('a-b_c:d.e/f+g', self.entries())


class TestCrossref(SpecLibrary):
    "bibtex.md 7.3"

    lib = ('@book{spec0,\n title = {Proceedings}\n}\n\n'
           '@inproceedings{talk,\n crossref = {SPEC0},\n related = {spec0},\n title = {T},\n xdata = {spec0}\n}\n')

    def test_follows_renames(self):
        "bibtex.md 7.3: a crossref equal to the old key (without case) follows; xdata, related, xref do not"
        self.papers('edit spec0 --key proc2000')
        talk = self.entry('talk')
        self.assertEqual(get_entry_val(talk, 'crossref'), 'proc2000')
        self.assertEqual((get_entry_val(talk, 'related'), get_entry_val(talk, 'xdata')), ('spec0', 'spec0'))


# 8. Key collisions when entries are added
# ========================================

class TestKeySuffix(unittest.TestCase):
    "bibtex.md 8"

    def test_suffix_rule(self):
        "bibtex.md 8: the letter after a digit is a previous suffix, in its case; then b-z; then a second letter"
        alphabet = 'abcdefghijklmnopqrstuvwxyz'
        cases = [
            ('Author2000', ['author2000'], 'Author2000b'),
            ('Author2000', ['author2000', 'AUTHOR2000B'], 'Author2000c'),
            ('Author2000b', ['author2000b'], 'Author2000c'),
            ('Author2000B', ['author2000b'], 'Author2000C'),
            ('Author2000z', ['author2000z'], 'Author2000za'),
            ('Author2000Z', ['author2000z'], 'Author2000Za'),
            ('Ab', ['ab'], 'Abb'),
            ('Ab', ['ab'] + ['ab' + c for c in alphabet[1:]], 'Aba'),
        ]
        for key, taken, expected in cases:
            self.assertEqual(append_abc(key, taken), expected, (key, taken))
        with self.assertRaises(ValueError):
            append_abc('Ab', ['ab'] + ['ab' + c for c in alphabet])

    def test_entry_without_key(self):
        "bibtex.md 8: an added entry without key gets the key of the template, with a suffix if taken"
        from bibtexparser.model import Entry, Field
        biblio = Biblio(parse_string('@article{smith2000, author = {Smith, John}, title = {A}, year = {2000}}'))
        biblio.add_entries([Entry('article', '', [Field('author', 'Smith, Jane'), Field('title', 'B'),
                                                  Field('year', '2000')])])
        self.assertEqual(sorted(e.key for e in biblio.entries), ['smith2000', 'smith2000b'])

    def test_given_key_taken(self):
        "bibtex.md 8: a given key that is taken: folded in when the same paper with nothing to merge, else an error"
        from papers.bib import DuplicateKeyError
        lib = '@article{k, author = {Smith, John}, title = {The Title}, year = {2000}}'
        biblio = Biblio(parse_string(lib), relative_to='/x')
        added, = entries('@article{K, author = {Smith, J.}, title = {the {T}itle}, year = {2000}, file = {:/x/a.pdf:pdf}}')
        self.assertEqual(biblio.insert_entry(added), biblio.entries)
        self.assertEqual(get_entry_val(biblio.entries[0], 'file'), ':a.pdf:pdf')
        other, = entries('@article{K, author = {Smith, John}, title = {The Title}, year = {2001}}')
        with self.assertRaises(DuplicateKeyError):
            biblio.insert_entry(other)
        with_field, = entries('@article{K, author = {Smith, John}, title = {The Title}, year = {2000}, pages = {1}}')
        with self.assertRaises(DuplicateKeyError):
            biblio.insert_entry(with_field)


# 9. Entry identity: the same-paper rule
# ======================================

class TestNormalization(unittest.TestCase):
    "bibtex.md 9.1"

    def test_norm(self):
        "bibtex.md 9.1: LaTeX decoded, Unidecode, no braces, lower case, single spaces"
        from papers.duplicate import normalize_text
        cases = {'': '', 'Sea  {Level}\n rise ': 'sea level rise', 'M{\\"u}ller': 'muller', 'Müller': 'muller',
                 'Straße': 'strasse', 'Ångström': 'angstrom', '{\\AA}ngstr{\\"o}m': 'angstrom',
                 'T\\^ete': 'tete', "\\'Ecole": 'ecole', '\\textit{Ice} sheets': 'ice sheets'}
        for text, norm in cases.items():
            self.assertEqual(normalize_text(text), norm, text)


class TestIdentifiersOfAnEntry(unittest.TestCase):
    "bibtex.md 9.2"

    def ident(self, text):
        from papers.duplicate import identity
        return identity(entries(text)[0])

    def test_doi(self):
        "bibtex.md 9.2: DOI prefixes removed, starts with 10. and has /, lower case"
        from papers.identifiers import normalize_doi
        for text in (' 10.1000/ABC ', 'http://doi.org/10.1000/abc', 'HTTPS://DOI.ORG/10.1000/abc',
                     'http://dx.doi.org/10.1000/abc', 'https://dx.doi.org/10.1000/abc', 'doi:10.1000/abc',
                     'DOI:   10.1000/abc'):
            self.assertEqual(normalize_doi(text), '10.1000/abc', text)
        for text in ('11.1000/abc', '10.1000', 'see 10.1000/abc'):
            self.assertIsNone(normalize_doi(text), text)

    def test_arxiv(self):
        "bibtex.md 9.2: arXiv id from eprint (archiveprefix empty or arXiv), else from an arXiv DOI"
        from papers.identifiers import normalize_arxiv
        cases = {'2101.01234': '2101.01234', '2101.01234v3': '2101.01234', 'arXiv: 2101.0123': '2101.0123',
                 'https://arxiv.org/abs/2101.01234v2': '2101.01234', 'http://arxiv.org/pdf/2101.01234.pdf': '2101.01234',
                 'hep-th/9901001': 'hep-th/9901001', 'math.AG/0601001v1': 'math.ag/0601001'}
        for text, arxiv in cases.items():
            self.assertEqual(normalize_arxiv(text), arxiv, text)
        for text in ('2101.012', '21010.1234', 'hep-th/990100', 'x'):
            self.assertIsNone(normalize_arxiv(text), text)
        self.assertEqual(self.ident('@misc{a, eprint = {2101.01234}, archiveprefix = { ARXIV }}'),
                         {'arxiv': '2101.01234'})
        self.assertEqual(self.ident('@misc{a, eprint = {2101.01234}, archiveprefix = {HAL}}'), {})
        self.assertEqual(self.ident('@misc{a, doi = {10.48550/arXiv.math.AG/0601001}}'),
                         {'doi': '10.48550/arxiv.math.ag/0601001', 'arxiv': 'math.ag/0601001'})

    def test_isbn(self):
        "bibtex.md 9.2: books only; split on , and ;; ISBN-10 converted to ISBN-13; invalid ones ignored"
        self.assertEqual(self.ident('@book{a, isbn = {ISBN: 0-306-40615-2; 978-3-16-148410-0, 0-306-40615-3, '
                                    'isbn 080442957x}}'),
                         {'isbn': '9780306406157,9780804429573,9783161484100'})
        self.assertEqual(self.ident('@incollection{a, isbn = {0-306-40615-2}}'), {})

    def test_authors_and_title(self):
        "bibtex.md 9.2: family names (before the first comma at depth 0, else the last word or {...} group), normalized"
        self.assertEqual(self.ident('@article{a, author = {Smith, John and Jane {van der Berg} and M{\\"u}ller and '
                                    '{Barnes and Noble}}, editor = {Ed, A}, title = {The {T}itle}}'),
                         {'authortitle': 'smith van der berg muller barnes and noble|the title'})
        self.assertEqual(self.ident('@article{a, title = {Only a title}}'), {'title': 'only a title'})
        self.assertEqual(self.ident('@article{a, author = {Smith}}'), {})


class TestSamePaperRule(unittest.TestCase):
    "bibtex.md 9.3"

    def kind(self, text):
        from papers.duplicate import same_paper
        a, b = entries(text)
        return same_paper(a, b).kind

    def test_isbn_has_no_title_guard(self):
        "bibtex.md 9.3: an ISBN in common gives same, without title guard"
        self.assertEqual(self.kind('@book{a, isbn = {0-306-40615-2}, title = {One}}\n'
                                   '@book{b, isbn = {0-306-40615-2, 978-3-16-148410-0}, title = {Two}}'), 'same')

    def test_title_guard_needs_both_titles(self):
        "bibtex.md 9.3: the title guard asks only when both titles are non-empty and differ"
        self.assertEqual(self.kind('@book{a, doi = {10.1/x}, title = {One}}\n@misc{b, doi = {10.1/X}}'), 'same')
        self.assertEqual(self.kind('@book{a, doi = {10.1/x}, title = {One}}\n@misc{b, doi = {10.1/X}, title = {Two}}'),
                         'ask')


class TestDistinctFile(SpecLibrary):
    "bibtex.md 9.4"

    lib = ('@article{spec0,\n author = {Smith, John and Doe, Jane},\n doi = {10.1/ABC},\n title = {The title}\n}\n\n'
           '@article{spec1,\n author = {M{\\"u}ller},\n title = {Unicode T}\n}\n')

    def test_format(self):
        "bibtex.md 9.4: the identities of the pair, one space of indentation, keys sorted, \\u escapes, final newline"
        from papers.duplicate import Distinct
        path = self.path('.papers', 'distinct.json')
        d = Distinct.for_library(self.dir)
        a, b = self.entry('spec0'), self.entry('spec1')
        d.add(a, b)
        d.add(b, a)  # already recorded
        book, = entries('@book{b, isbn = {978-3-16-148410-0, 0-306-40615-2}, title = {Ünï}, eprint = {2101.01234}}')
        d.add(a, book)
        d.save()
        self.assertEqual(Path(path).read_bytes().decode('ascii'),
                         '{\n "distinct": [\n  [\n   {\n    "authortitle": "smith doe|the title",\n'
                         '    "doi": "10.1/abc"\n   },\n   {\n    "authortitle": "muller|unicode t"\n   }\n  ],\n'
                         '  [\n   {\n    "authortitle": "smith doe|the title",\n    "doi": "10.1/abc"\n   },\n'
                         '   {\n    "arxiv": "2101.01234",\n    "isbn": "9780306406157,9783161484100",\n'
                         '    "title": "uni"\n   }\n  ]\n ]\n}\n')

    def test_reading(self):
        "bibtex.md 9.4: elements that are not lists of two are ignored; raw UTF-8 and a byte order mark are read"
        from papers.duplicate import Distinct
        os.makedirs(self.path('.papers'))
        Path(self.path('.papers', 'distinct.json')).write_bytes(
            ('﻿{"distinct": [[{"authortitle": "x|y"}], 3, [{"authortitle": "müller|ü"}, '
             '{"authortitle": "b|c"}]]}').encode('utf-8'))
        d = Distinct.for_library(self.dir)
        self.assertEqual(d.pairs, [[{'authortitle': 'müller|ü'}, {'authortitle': 'b|c'}]])

    def test_reading_bad_values(self):
        "bibtex.md 9.4: a `distinct` that is not an array makes the file unreadable (warning); pairs of non-objects are ignored"
        from papers.duplicate import Distinct
        os.makedirs(self.path('.papers'))
        path = Path(self.path('.papers', 'distinct.json'))
        for text in ('{"distinct": 5}', '{"distinct": null}', '{"distinct": {}}'):
            path.write_text(text)
            with self.assertLogs('papers', level='WARNING'):
                self.assertEqual(Distinct.for_library(self.dir).pairs, [])
        path.write_text('{"distinct": [["a", "b"], [{"title": "t"}, 3], [{"title": "t"}, {"title": "u"}]]}')
        self.assertEqual(Distinct.for_library(self.dir).pairs, [[{'title': 't'}, {'title': 'u'}]])
        self.assertFalse(Distinct.for_library(self.dir).contains(self.entry('spec0'), self.entry('spec1')))

    def test_matching(self):
        "bibtex.md 9.4: doi, arxiv and isbn equal (absent on both counts as equal), authortitle and title where both have them"
        from papers.duplicate import Distinct
        d = Distinct([[{'doi': '10.1/a', 'authortitle': 'a|b'}, {'title': 't'}]])
        a, = entries('@article{a, doi = {10.1/A}, title = {Other}, author = {Z}}')
        b, = entries('@article{b, title = {T}}')
        c, = entries('@article{c, title = {T}, doi = {10.1/c}}')
        d2, = entries('@article{d, doi = {10.1/A}}')  # no authortitle: matches the recorded side
        self.assertFalse(d.contains(a, b))  # authortitle differs
        self.assertFalse(d.contains(d2, c))  # c has a doi, the recorded side none
        self.assertTrue(d.contains(b, d2))  # either order

    def test_in_the_library_folder(self):
        "bibtex.md 9.4: distinct.json is in .papers/ of the library folder, also when the bibtex is elsewhere"
        lib = self.path('lib')
        os.makedirs(os.path.join(lib, 'bib'))
        paperscmd('init --bibtex bib/papers.bib', cwd=lib)
        bibtex = os.path.join(lib, 'bib', 'papers.bib')
        Path(bibtex).write_text('@article{a,\n author = {Smith, J.},\n journal = {A},\n title = {T}\n}\n\n'
                                '@article{b,\n author = {Smith, John},\n journal = {B},\n title = {T}\n}\n')
        with patch('builtins.input', side_effect=['n']), redirect_stdout(io.StringIO()):
            paperscmd('check --duplicates --on-duplicate ask', cwd=lib)
        self.assertTrue(os.path.exists(os.path.join(lib, '.papers', 'distinct.json')))
        self.assertFalse(os.path.exists(os.path.join(lib, 'bib', '.papers', 'distinct.json')))

    def test_union(self):
        "bibtex.md 9.4: an exchange takes the union of the pairs (a pair equal in either order is not added again)"
        from papers.duplicate import Distinct
        x, y, z = {'doi': '10.1/x'}, {'doi': '10.1/y'}, {'doi': '10.1/z'}
        d = Distinct([[x, y]])
        d.update(Distinct([[y, x], [x, z]]))
        self.assertEqual(d.pairs, [[x, y], [x, z]])


class TestFindingDuplicates(unittest.TestCase):
    "bibtex.md 9.5"

    def test_add_candidates(self):
        "bibtex.md 9.5: matches ordered same first, then ask, each in library order"
        from papers.duplicate import find_duplicates
        lib = entries('@book{ask1, doi = {10.1/x}, title = {Book}}\n'
                      '@article{same1, doi = {10.1/X}, title = {Chapter}}\n'
                      '@article{other, doi = {10.1/y}, title = {Chapter}}\n'
                      '@article{same2, author = {Smith}, title = {Chapter}}\n')
        added, = entries('@article{new, doi = {10.1/x}, author = {Smith}, title = {Chapter}}')
        self.assertEqual([(e.key, v.kind) for e, v in find_duplicates(added, lib)],
                         [('same1', 'same'), ('same2', 'same'), ('ask1', 'ask')])
        added, = entries('@article{new, author = {Smith}, title = {Chapter}}')
        self.assertEqual([e.key for e, v in find_duplicates(added, lib)], ['same2'])

    def test_groups(self):
        "bibtex.md 9.5: sets sorted by number of fields, most first, ties in library order; split by different"
        from papers.duplicate import duplicate_groups
        lib = entries('@article{few, author = {Smith}, title = {T}}\n'
                      '@article{doi1, author = {Smith}, title = {T}, doi = {10.1/a}}\n'
                      '@article{doi2, author = {Smith}, title = {T}, doi = {10.1/b}, year = {2000}}\n'
                      '@article{tie, author = {Smith}, title = {T}, doi = {10.1/a}}\n')
        self.assertEqual(sorted([e.key for e in g.entries] for g in duplicate_groups(lib)),
                         [['doi1', 'tie'], ['doi2', 'few']])  # the order of the groups is free


# 10. Merging entries that are the same paper (two-way)
# =====================================================

class TestTwoWayMerge(unittest.TestCase):
    "bibtex.md 10"

    def merge(self, text, **kw):
        from papers.merge import Merge
        return Merge(entries(text), **kw)

    def test_fields(self):
        "bibtex.md 10.2: status and value of each field; empty values are no value; type in lower case"
        m = self.merge('@Article{a, title = {T}, note = {}, journal = {J}, volume = { }}\n'
                       '@ARTICLE{b, title = {t}, pages = {}, journal = {K}, volume = {3}, year = {2000}}')
        status = {f.name: (f.status, f.value) for f in m.fields}
        self.assertEqual(status, {'ENTRYTYPE': (' ', 'article'), 'title': (' ', 'T'), 'note': (' ', ''),
                                  'journal': ('!', 'J'), 'volume': ('+', '3'), 'pages': (' ', None),
                                  'year': ('+', '2000')})
        r = m.result()
        self.assertEqual(fields(r), [('title', 'T'), ('note', ''), ('journal', 'J'), ('volume', '3'),
                                     ('year', '2000')])
        conflict = self.merge('@article{a, journal = { }}\n@article{b, journal = {K}}\n@article{c, journal = {L}}')
        self.assertEqual(conflict.result()['journal'], 'K')  # the first entry having one

    def test_equivalent_values(self):
        "bibtex.md 10.3: names compatible word by word up to the shorter; doi; other fields by norm"
        from papers.merge import equivalent
        self.assertTrue(equivalent('author', 'Smith, J.', 'John Smith'))
        self.assertTrue(equivalent('author', 'Smith, J.', 'Smith, John Quincy'))
        self.assertTrue(equivalent('editor', 'Smith, J. D.', 'Smith, John-David'))
        self.assertFalse(equivalent('author', 'Smith, Jo', 'Smith, John'))
        self.assertFalse(equivalent('author', 'Smith, J.', 'Smith, J. and Doe, J.'))
        self.assertTrue(equivalent('doi', 'https://doi.org/10.1/ABC', '10.1/abc'))
        self.assertTrue(equivalent('doi', 'not a doi', 'NOT  A {DOI}'))  # not DOIs: as other fields
        self.assertTrue(equivalent('title', 'Sea {L}evel  {\\"u}', 'sea level ü'))

    def test_preferred_value(self):
        "bibtex.md 10.3: the longest given names for author and editor (first on a tie); else the first present"
        m = self.merge('@article{a, author = {Smith, J.}, editor = {Doe, Jo}, title = {sea}}\n'
                       '@article{b, author = {Smith, John}, editor = {Doe, J.}, title = {Sea}}\n'
                       '@article{c, author = {John Smith}, editor = {Doe, Jo}, title = {SEA}}')
        r = m.result()
        self.assertEqual((r['author'], r['editor'], r['title']), ('Smith, John', 'Doe, Jo', 'sea'))

    def test_files_by_content(self):
        "bibtex.md 10.4: a link to a file with the content of a file already in the union is skipped"
        with tempfile.TemporaryDirectory() as d:
            for name, content in (('a.pdf', 'x'), ('b.pdf', 'x'), ('c.pdf', 'y')):
                Path(d, name).write_text(content)
            m = self.merge('@article{a, file = {:a.pdf:pdf}}\n@article{b, file = {:b.pdf:pdf;:c.pdf:pdf;:gone.pdf:pdf}}',
                           relative_to=d)
            self.assertEqual(m.result()['file'], ':a.pdf:pdf;:c.pdf:pdf;:gone.pdf:pdf')

    def test_keywords_conflict(self):
        "bibtex.md 6, 10.2: two keywords values that differ are a conflict, not merged as sets"
        m = self.merge('@article{a, keywords = {a, b}}\n@article{b, keywords = {b, c}}')
        self.assertEqual([f.name for f in m.conflicts], ['keywords'])

    def test_ids(self):
        "bibtex.md 10.5: ids of all entries, then the other keys (check); without case, first spelling; no field if empty"
        m = self.merge('@article{Key, ids = {Old, KEY}}\n@article{b, ids = {old, x}}\n@article{c}', keys_to_ids=True)
        self.assertEqual(m.result()['ids'], 'Old, x, b, c')
        self.assertNotIn('ids', self.merge('@article{a, ids = {A}}\n@article{b}').result())
