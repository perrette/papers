"""The rules of design/formats.md that no other test checks: one test class
per section of the spec, each test's docstring names its section.

The conversions are checked on the texts papers writes and reads
(papers.formats.dumps and loads, the text of `papers export` files and of
`papers list --format`), the commands through the command line.
"""
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import papers
from papers import formats
from papers.bib import Biblio
from papers.config import CONFIG_FILE_LOCAL
from papers.encoding import format_entries
from papers.entries import parse_file, parse_string
from papers.utils import PapersExit

import tests.test_pools_onetime as onetime
from tests.common import FileTest, entry

HAS_RISPY = importlib.util.find_spec('rispy') is not None
needs_rispy = unittest.skipUnless(HAS_RISPY, 'rispy is not installed')


def parse(text):
    return parse_string(text).entries


def fields(e):
    return {f.key: f.value for f in e.fields}


def links(e):
    return parse_file(e.fields_dict['file'].value) if 'file' in e.fields_dict else []


def csl(bibtex, files=()):
    "the CSL-JSON items written for a bibtex text"
    return json.loads(formats.dumps(parse(bibtex), 'csl-json', files=lambda e: list(files)))


def csl_import(*items):
    "the entries read from CSL-JSON items"
    return formats.loads(json.dumps(list(items)), 'csl-json')


def csl_one(**item):
    [e] = csl_import(item)
    return e


def ris_import(text):
    return formats.loads(text, 'ris')


def ris_one(*lines):
    [e] = ris_import('TY  - ' + '\n'.join(lines) + '\nER  - \n')
    return e


def ris_text(bibtex, files=()):
    return formats.dumps(parse(bibtex), 'ris', files=lambda e: list(files))


def run_papers(*args, cwd=None, stdin=None):
    "papers in a subprocess (exit code, standard output, standard error)"
    env = dict(os.environ, PYTHONPATH=str(Path(papers.__file__).parents[1]))
    env.pop('NO_COLOR', None)
    res = subprocess.run([sys.executable, '-m', 'papers', *args], cwd=cwd, capture_output=True, text=True,
                         stdin=subprocess.DEVNULL if stdin is None else None, input=stdin, env=env)
    return res.returncode, res.stdout, res.stderr


class SpecLibrary(FileTest):
    "a library lib/ (FileTest), the output of commands"

    def out_err(self, cmd):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.lib(cmd)
        return out.getvalue(), err.getvalue()


# 1. Formats and where they are used
# ==================================

class TestFormatsTable(SpecLibrary):

    def test_ids_and_file_names(self):
        "formats.md 1: format ids, file names written by export and their order"
        self.assertEqual(formats.FORMATS, ('bibtex', 'ris', 'csl-json', 'bibjson'))
        self.assertEqual(formats.FILENAMES, {'bibtex': 'papers.bib', 'ris': 'papers.ris',
                                             'csl-json': 'papers.json', 'bibjson': 'papers.bib.json'})
        self.bib(entry('one2000'))
        out = self.out('export ../out --format bibjson,csl-json,bib')
        self.assertIn('(papers.bib, papers.json, papers.bib.json; files: copy)', out)
        self.assertEqual(sorted(os.listdir(self.path('out'))), ['.papers', 'files', 'papers.bib',
                                                               'papers.bib.json', 'papers.json'])


class TestFormatOfAFile(unittest.TestCase):

    def test_extensions(self):
        "formats.md 1.1: --format first, then the extensions longest first, case-insensitive, else bibtex"
        for name, fmt in [('a.bib.json', 'bibjson'), ('A.BIB.JSON', 'bibjson'), ('a.json', 'csl-json'),
                          ('a.Json', 'csl-json'), ('a.ris', 'ris'), ('a.RIS', 'ris'), ('a.bib', 'bibtex'),
                          ('a.txt', 'bibtex'), ('a', 'bibtex'), ('dir.ris/a.txt', 'bibtex'),
                          ('a.json.bib', 'bibtex')]:
            self.assertEqual(formats.file_format(name), fmt, name)
        self.assertEqual(formats.file_format('a.ris', 'csl-json'), 'csl-json')


class TestCommands(SpecLibrary):

    def test_recursive_reads_pdf_and_bib_only(self):
        "formats.md 1.2: add DIR --recursive reads the .bib files, not RIS, CSL-JSON or BibJSON"
        self.write('in', 'a.bib', content=entry('bib2000'))
        self.write('in', 'b.json', content=json.dumps([{'id': 'csl2000', 'type': 'book', 'title': 'CSL'}]))
        self.write('in', 'c.bib.json', content=json.dumps([{'id': 'bj2000', 'type': 'book', 'title': 'BJ'}]))
        self.write('in', 'd.ris', content='TY  - BOOK\nID  - ris2000\nTI  - RIS\nER  - \n')
        self.lib('add ../in --recursive --no-pool')
        self.assertEqual([e.key for e in Biblio.load(self.path('lib', 'papers.bib'), '').entries], ['bib2000'])

    def test_from_stdin_with_format(self):
        "formats.md 1.2: edit --from - is bibtex unless --format is given"
        self.bib(entry('one2000'))
        item = json.dumps([{'id': 'x', 'type': 'book', 'title': 'From CSL'}])
        with patch('sys.stdin', io.StringIO(item)), patch('papers.utils.stdin_is_terminal', return_value=False):
            self.lib('edit one2000 --from - --format csl-json')
        [e] = Biblio.load(self.path('lib', 'papers.bib'), '').entries
        self.assertEqual((e.key, e.entry_type, e['title']), ('one2000', 'book', 'From CSL'))

    def test_format_without_from(self):
        "formats.md 1.2: edit --format without --from is a usage error (exit 2)"
        self.bib(entry('one2000'))
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            self.lib('edit one2000 --format ris')
        self.assertEqual(cm.exception.code, 2)
        self.assertIn('--format is the format of --from FILE', err.getvalue())


class TestTextEncoding(SpecLibrary):

    def test_read_bom_and_crlf(self):
        "formats.md 1.3: UTF-8, a leading byte-order mark dropped; \\r\\n read as \\n in RIS"
        path = self.path('a.json')
        Path(path).write_bytes('\ufeff[{"id": "x", "type": "book", "title": "Göttingen"}]'.encode())
        [e] = formats.read_file(path, 'csl-json')
        self.assertEqual(e['title'], 'Göttingen')
        path = self.path('a.bib.json')
        Path(path).write_bytes('\ufeff[{"id": "x", "type": "book", "title": "T"}]'.encode())
        self.assertEqual(formats.read_file(path, 'bibjson')[0].key, 'x')

    @needs_rispy
    def test_ris_lone_cr(self):
        "formats.md 1.3: a lone \\r is not a line end in RIS"
        e = ris_one('BOOK\r\nTI  - A\rB\r\nPY  - 2000\r')
        self.assertEqual((e['title'], e['year']), ('A\rB', '2000'))

    def test_written_utf8_lf(self):
        "formats.md 1.3: export files in UTF-8, no byte-order mark, \\n line ends"
        self.bib('@book{x,\n title = {Göttingen},\n year = {2000}\n}\n')
        names = ['papers.json', 'papers.bib.json'] + (['papers.ris'] if HAS_RISPY else [])
        self.lib('export ../out --format ' + ','.join(['csl-json', 'bibjson'] + (['ris'] if HAS_RISPY else [])))
        for name in names:
            data = Path(self.path('out', name)).read_bytes()
            self.assertFalse(data.startswith(b'\xef\xbb\xbf'), name)
            self.assertIn('Göttingen'.encode('utf-8'), data, name)
            self.assertNotIn(b'\r', data, name)


# 2. Shared conversion rules
# ==========================

class TestValuesAsText(unittest.TestCase):

    def test_raw_fields(self):
        "formats.md 2.1: url, doi, file, eprint, isbn, issn are not decoded"
        [item] = csl(r'@book{x, title = {T}, url = {https://a.org/x\_y~z}, isbn = {978\_1},'
                     r' issn = {{1234-5678}}}')
        self.assertEqual((item['URL'], item['ISBN'], item['ISSN']), (r'https://a.org/x\_y~z', r'978\_1', '{1234-5678}'))

    def test_text_without_latex_is_trimmed_only(self):
        "formats.md 2.1: a value without \\ { } $ ~ % & is only trimmed (no ligature conversion)"
        [item] = csl("@book{x, title = {  a -- b ``q'' --- c  }, note = {x^2 #1}}")
        self.assertEqual((item['title'], item['note']), ("a -- b ``q'' --- c", 'x^2 #1'))

    def test_latex_decoded(self):
        "formats.md 2.1: a value with LaTeX is decoded (the decoded text itself is free)"
        [item] = csl(r'@book{x, title = {G{\"o}ttingen \& {S}ea}}')
        self.assertNotIn('{', item['title'])
        self.assertNotIn('\\', item['title'])


class TestNamesToParts(unittest.TestCase):

    def test_examples(self):
        "formats.md 2.2: the examples of the table, as CSL-JSON name objects"
        table = [
            ('Perrette, M.', [{'family': 'Perrette', 'given': 'M.'}]),
            ('van der Berg, Jan', [{'family': 'Berg', 'given': 'Jan', 'non-dropping-particle': 'van der'}]),
            ('Ludwig van Beethoven', [{'family': 'Beethoven', 'given': 'Ludwig', 'non-dropping-particle': 'van'}]),
            ('Smith, Jr, John', [{'family': 'Smith', 'given': 'John', 'suffix': 'Jr'}]),
            ('{World Health Organization}', [{'literal': 'World Health Organization'}]),
            ('jean de la fontaine', [{'family': 'fontaine', 'non-dropping-particle': 'jean de la'}]),
            ('Doe, Jr, Jane, X', [{'family': 'Doe', 'given': 'Jane, X', 'suffix': 'Jr'}]),
            ('Doe, Jr,', [{'family': 'Doe', 'suffix': 'Jr'}]),
            ('A AND B', [{'family': 'B', 'given': 'A AND'}]),
            ('Plato', [{'family': 'Plato'}]),
            ('{Barnes and Noble} and Smith,  John ', [{'literal': 'Barnes and Noble'},
                                                     {'family': 'Smith', 'given': 'John'}]),
            ('{van} Gogh, Vincent', [{'family': 'Gogh', 'given': 'Vincent', 'non-dropping-particle': 'van'}]),
            ('de, Jean', [{'family': 'de', 'given': 'Jean'}]),
        ]
        for name, parts in table:
            [item] = csl('@book{x, author = {' + name + '}}')
            self.assertEqual(item['author'], parts, name)
            self.assertEqual([list(p) for p in item['author']], [list(p) for p in parts], name)  # key order


class TestPartsToNames(unittest.TestCase):

    def test_rules(self):
        "formats.md 2.3: CSL name objects as bibtex names"
        table = [
            ([{'literal': 'World Health Organization'}], '{World Health Organization}'),
            (['A plain string'], '{A plain string}'),
            ([{'family': 'Berg', 'given': 'Jan', 'non-dropping-particle': 'van der'}], 'van der Berg, Jan'),
            ([{'family': 'Berg', 'given': 'Jan', 'dropping-particle': 'van'}], 'Berg, Jan van'),
            ([{'family': 'Smith', 'given': 'John', 'suffix': 'Jr'}], 'Smith, Jr, John'),
            ([{'family': 'Doe', 'suffix': 'Jr'}], 'Doe, Jr,'),
            ([{'family': 'Plato'}], 'Plato'),
            ([{'family': 'Doe', 'given': 'Jane'}, {'family': 'Roe'}], 'Doe, Jane and Roe'),
            ([{'family': 'Doe', 'literal': 'ignored'}], 'Doe'),
        ]
        for names, bibtex in table:
            e = csl_one(type='book', title='T', author=names)
            self.assertEqual(e['author'], bibtex, names)

    def test_one_name_not_in_an_array(self):
        "formats.md 2.3, 3.3: an author value that is a string or an object is one name"
        self.assertEqual(csl_one(type='book', title='T', author='Smith, John')['author'], '{Smith, John}')
        self.assertEqual(csl_one(type='book', title='T', editor={'family': 'Doe', 'given': 'Jane'})['editor'],
                         'Doe, Jane')


class TestDates(unittest.TestCase):

    def test_date_text(self):
        "formats.md 2.4: date text to numbers (read from a CSL-JSON raw date)"
        for text, expected in [('2013', {'year': '2013'}), ('2013-05', {'year': '2013', 'month': '5'}),
                               ('2013/05/02/', {'year': '2013', 'month': '5'}),
                               (' 2013-05-02T00:00', {'year': '2013', 'month': '5'}), ('13-05', {}),
                               ('2013-00-05', {'year': '2013'}), ('2013-5-0', {'year': '2013', 'month': '5'}),
                               ('May 2013', {})]:
            e = csl_one(type='book', title='T', issued={'raw': text})
            self.assertEqual({k: v for k, v in fields(e).items() if k in ('year', 'month')}, expected, text)

    def test_date_of_an_entry(self):
        "formats.md 2.4: year (digits) and month, else the date field; the day of date unused with a year"
        for bibtex, issued in [('year = {2013}, month = may', {'date-parts': [[2013, 5]]}),
                               ('year = {{2013}}, month = {{12}}', {'date-parts': [[2013, 12]]}),
                               ('year = {2013}, month = {September}', {'date-parts': [[2013, 9]]}),
                               ('year = {2013}, month = {13}', {'date-parts': [[2013]]}),
                               ('year = {2013}, month = {xyz}', {'date-parts': [[2013]]}),
                               ('year = {2013}, date = {2013-05-02}', {'date-parts': [[2013]]}),
                               ('year = {in press}, date = {2013-05-02}', {'date-parts': [[2013, 5, 2]]}),
                               ('date = {2013-05}', {'date-parts': [[2013, 5]]}),
                               ('year = {n.d.}', {'literal': 'n.d.'})]:
            [item] = csl('@book{x, title = {T}, ' + bibtex + '}')
            self.assertEqual(item['issued'], issued, bibtex)

    def test_month_numbers(self):
        "formats.md 2.4: month parsing: digits 1-12, else the first three letters"
        for month, number in [('1', 1), ('01', 1), ('12', 12), ('0', None), ('jan', 1), ('Feb.', 2),
                              ('{March}', 3), ('dec', 12), ('June', 6), ('ju', None), ('x', None)]:
            [item] = csl('@book{x, title = {T}, year = {2000}, month = {' + month + '}}')
            self.assertEqual(item['issued'], {'date-parts': [[2000, number] if number else [2000]]}, month)

    def test_date_to_fields(self):
        "formats.md 2.4: year and month as decimal text, the day dropped"
        e = csl_one(type='book', title='T', issued={'date-parts': [[2013, 5, 2]]})
        self.assertEqual((e['year'], e['month'], 'day' in fields(e)), ('2013', '5', False))


class TestPages(unittest.TestCase):

    def test_to_bibtex(self):
        "formats.md 2.5: two parts give first--second, other values are kept trimmed"
        for page, pages in [('123-130', '123--130'), ('123 – 130', '123--130'), ('1—2', '1--2'),
                            ('1--2', '1--2'), ('1-2-3', '1-2-3'), (' e123 ', 'e123'), ('5-', '5-')]:
            self.assertEqual(csl_one(type='book', title='T', page=page)['pages'], pages, page)

    def test_first_and_last(self):
        "formats.md 2.5: first and last page of a bibtex value (CSL page)"
        for pages, page in [('11--29', '11-29'), ('11 - 29', '11-29'), ('11', '11'), ('1-2-3', '1-2-3')]:
            [item] = csl('@book{x, title = {T}, pages = {' + pages + '}}')
            self.assertEqual(item['page'], page, pages)

    @needs_rispy
    def test_first_and_last_ris(self):
        "formats.md 2.5: first and last page of a bibtex value (RIS SP and EP)"
        for pages, lines in [('11--29', ['SP  - 11', 'EP  - 29']), ('11', ['SP  - 11']),
                             ('1-2-3', ['SP  - 1', 'EP  - 2'])]:
            text = ris_text('@book{x, title = {T}, pages = {' + pages + '}}')
            self.assertEqual([l for l in text.splitlines() if l[:2] in ('SP', 'EP')], lines, pages)


class TestDOI(unittest.TestCase):

    def test_clean(self):
        "formats.md 2.6: the prefixes removed from a DOI, case-insensitive"
        for doi in ['10.1/x', ' 10.1/x ', 'https://doi.org/10.1/x', 'http://doi.org/10.1/x',
                    'HTTPS://DX.DOI.ORG/10.1/x', 'http://dx.doi.org/10.1/x', 'doi:10.1/x', 'DOI: 10.1/x']:
            self.assertEqual(csl_one(type='book', title='T', DOI=doi)['doi'], '10.1/x', doi)
            [item] = csl('@book{x, title = {T}, doi = {' + doi + '}}')
            self.assertEqual(item['DOI'], '10.1/x', doi)
        self.assertEqual(csl_one(type='book', title='T', DOI='https://example.org/10.1/x')['doi'],
                         'https://example.org/10.1/x')


class TestKeys(unittest.TestCase):

    def test_usable_keys(self):
        "formats.md 2.7: an imported key is kept when it matches the pattern and is not ITEM-<digits>"
        for key, kept in [('smith2000', 'smith2000'), (' smith2000 ', 'smith2000'), ('a:b.c+d-e_f', 'a:b.c+d-e_f'),
                          ('Müller2000', 'Müller2000'), ('ITEM-x', 'ITEM-x'), ('ITEM-12', ''), ('12', ''),
                          ('2000smith', ''), ('http://zotero.org/users/1/items/AB', ''), ('a b', ''),
                          ('_x', ''), ('a/b', '')]:
            self.assertEqual(csl_one(id=key, type='book', title='T').key, kept, key)
            self.assertEqual(formats.loads(json.dumps([{'id': key, 'type': 'book'}]), 'bibjson')[0].key, kept, key)


class TestFileLinks(unittest.TestCase):

    def test_items(self):
        "formats.md 2.8: file:// URLs, other URLs left out, description:path:type, drive paths"
        with self.assertLogs('papers', 'WARNING') as logs:
            e = csl_one(type='book', title='T', file=[
                'file:///abs/c%20d.pdf', 'file://host/abs/e.pdf', 'http://example.org/x.pdf',
                'internal-pdf://123/x.pdf', 'desc:files/a.pdf:pdf', ':files/b:c.pdf:pdf', r'C:\x.pdf', 'C:/y.pdf',
                'a:b.pdf', '  ', ' plain.pdf '])
        self.assertEqual(links(e), ['/abs/c d.pdf', '/abs/e.pdf', 'files/a.pdf', 'files/b:c.pdf', r'C:\x.pdf',
                                    'C:/y.pdf', 'a:b.pdf', 'plain.pdf'])
        self.assertEqual(logs.output, ['WARNING:papers:file link left out (not a local file): http://example.org/x.pdf',
                                       'WARNING:papers:file link left out (not a local file): internal-pdf://123/x.pdf'])

    def test_string_split(self):
        "formats.md 2.8: a string is split on ;"
        e = csl_one(type='book', title='T', file='a.pdf; ;b.pdf')
        self.assertEqual(links(e), ['a.pdf', 'b.pdf'])


class TestEditFromLinks(SpecLibrary):

    def test_relative_to_file(self):
        "formats.md 2.8: edit --from FILE (CSL-JSON): relative links are relative to the directory of FILE"
        self.bib(entry('one2000'))
        new = self.write('down', 'new.json', content=json.dumps([{'id': 'x', 'type': 'book', 'title': 'T',
                                                                    'file': 'paper.pdf'}]))
        self.lib(f'edit one2000 --from {new}')
        biblio = Biblio.load(self.path('lib', 'papers.bib'), '')
        self.assertEqual(biblio.get_files(biblio.entries[0]), [self.path('down', 'paper.pdf')])

    def test_stdin_as_written(self):
        "formats.md 2.8: edit --from -: the links are stored as written (relative to the library's bibtex)"
        self.bib(entry('one2000'))
        with patch('sys.stdin', io.StringIO('@article{x,\n title = {T},\n file = {:paper.pdf:pdf}\n}\n')), \
                patch('papers.utils.stdin_is_terminal', return_value=False):
            self.lib('edit one2000 --from -')
        biblio = Biblio.load(self.path('lib', 'papers.bib'), '')
        self.assertEqual(biblio.get_files(biblio.entries[0]), [self.path('lib', 'paper.pdf')])


class TestLatexEscape(unittest.TestCase):

    def test_escaped_fields(self):
        "formats.md 2.9: & % # _ escaped in the fields imported from CSL-JSON, except the raw ones"
        e = csl_one(id='x', type='article-journal', title=r'R&D 5% #1 a_b \& done', note='a&b',
                    author=[{'family': 'AT&T'}], URL='https://a.org/a_b?x=1&y=2', DOI='10.1/a_b%',
                    ISBN='1_2', ISSN='3_4', keyword='a_b, c&d', accessed={'raw': '2020-01-02'},
                    custom={'file': ['files/a_b.pdf']})
        self.assertEqual(fields(e), {
            'author': r'AT\&T', 'title': r'R\&D 5\% \#1 a\_b \& done', 'url': 'https://a.org/a_b?x=1&y=2',
            'doi': '10.1/a_b%', 'isbn': '1_2', 'issn': '3_4', 'note': r'a\&b', 'keywords': 'a_b, c&d',
            'urldate': '2020-01-02', 'file': ':files/a_b.pdf:pdf'})

    def test_bibjson_unchanged(self):
        "formats.md 2.9: BibJSON values are read unchanged"
        [e] = formats.loads(json.dumps([{'id': 'x', 'type': 'book', 'title': 'R&D 5% a_b'}]), 'bibjson')
        self.assertEqual(e['title'], 'R&D 5% a_b')

    @needs_rispy
    def test_ris_escaped(self):
        "formats.md 2.9: & % # _ escaped in the fields imported from RIS, except the raw ones"
        e = ris_one('BOOK', 'TI  - A&B_C', 'UR  - https://a.org/a_b', 'KW  - a_b', 'Y2  - 2020_01',
                    'SN  - 1_2', 'L1  - files/a_b.pdf')
        self.assertEqual((e['title'], e['url'], e['keywords'], e['urldate'], e['isbn'], links(e)),
                         (r'A\&B\_C', 'https://a.org/a_b', 'a_b', '2020_01', '1_2', ['files/a_b.pdf']))


# 3. CSL-JSON
# ===========

CSL_EXPORT_TYPES = {'article': 'article-journal', 'book': 'book', 'proceedings': 'book', 'booklet': 'pamphlet',
                    'inbook': 'chapter', 'incollection': 'chapter', 'inproceedings': 'paper-conference',
                    'conference': 'paper-conference', 'phdthesis': 'thesis', 'mastersthesis': 'thesis',
                    'thesis': 'thesis', 'techreport': 'report', 'report': 'report', 'manual': 'report',
                    'misc': 'document', 'online': 'webpage', 'electronic': 'webpage', 'www': 'webpage',
                    'dataset': 'dataset', 'software': 'software', 'unpublished': 'manuscript', 'patent': 'patent',
                    'other': 'document', 'Article': 'article-journal'}

CSL_IMPORT_TYPES = {'article-journal': 'article', 'article-magazine': 'article', 'article-newspaper': 'article',
                    'article': 'misc', 'book': 'book', 'pamphlet': 'booklet', 'chapter': 'incollection',
                    'entry-encyclopedia': 'incollection', 'entry-dictionary': 'incollection',
                    'paper-conference': 'inproceedings', 'thesis': 'phdthesis', 'report': 'techreport',
                    'webpage': 'online', 'post': 'online', 'post-weblog': 'online', 'dataset': 'dataset',
                    'software': 'software', 'patent': 'patent', 'manuscript': 'unpublished', 'document': 'misc',
                    'map': 'misc', None: 'misc'}


class TestCSLTypes(unittest.TestCase):

    def test_export(self):
        "formats.md 3.1: bibtex to CSL types (lower case), misc with eprint is article"
        for bibtex, csl_type in CSL_EXPORT_TYPES.items():
            [item] = csl('@' + bibtex + '{x, title = {T}}')
            self.assertEqual(item['type'], csl_type, bibtex)
        [item] = csl('@misc{x, title = {T}, eprint = {2101.00001}}')
        self.assertEqual(item['type'], 'article')

    def test_import(self):
        "formats.md 3.1: CSL to bibtex types; a thesis of genre master is a mastersthesis"
        for csl_type, bibtex in CSL_IMPORT_TYPES.items():
            item = {'title': 'T'} if csl_type is None else {'type': csl_type, 'title': 'T'}
            self.assertEqual(csl_one(**item).entry_type, bibtex, csl_type)
        self.assertEqual(csl_one(type='thesis', genre='MASTER thesis').entry_type, 'mastersthesis')
        self.assertEqual(csl_one(type='thesis', genre='Diplom').entry_type, 'phdthesis')


class TestCSLExportFields(unittest.TestCase):

    def test_key_order(self):
        "formats.md 3.2: the keys of an item, in the order of the table"
        [item] = csl(r'''@article{k,
 urldate = {2024-03-01}, keywords = {b, a}, month = may, year = {2013}, pages = {1--2}, number = {3},
 journal = {J}, pmcid = {PMC1}, pmid = {1}, series = {S}, language = {en}, edition = {2}, note = {N},
 abstract = {A}, address = {Potsdam}, publisher = {P}, issn = {1234-5678}, isbn = {978}, url = {https://u},
 doi = {10.1/x}, volume = {4}, title = {T}, translator = {Roe, R.}, editor = {Ed, E.}, author = {Doe, J.},
 eprint = {e}, crossref = {c}, ids = {old}, papers-x = {y}}''', files=['files/a.pdf'])
        self.assertEqual(list(item), ['id', 'citation-key', 'type', 'author', 'editor', 'translator', 'title',
                                      'volume', 'DOI', 'URL', 'ISBN', 'ISSN', 'publisher', 'publisher-place',
                                      'abstract', 'note', 'edition', 'language', 'collection-title', 'PMID',
                                      'PMCID', 'container-title', 'issue', 'page', 'keyword', 'issued',
                                      'accessed', 'custom'])
        self.assertEqual(item['issued'], {'date-parts': [[2013, 5]]})
        self.assertEqual(item['accessed'], {'date-parts': [[2024, 3, 1]]})
        self.assertEqual(item['custom'], {'file': ['files/a.pdf']})
        self.assertEqual(item['author'], [{'family': 'Doe', 'given': 'J.'}])

    def test_publisher_fallback_and_genre(self):
        "formats.md 3.2: publisher from school, institution, organization at its position; genre"
        [item] = csl('@techreport{k, title = {T}, institution = {I}, organization = {O}, address = {A},'
                     ' type = {Working paper}, number = {7}, year = {2020}}')
        self.assertEqual(list(item), ['id', 'citation-key', 'type', 'title', 'publisher', 'publisher-place',
                                      'number', 'genre', 'issued'])
        self.assertEqual((item['publisher'], item['genre'], item['number']), ('I', 'Working paper', '7'))
        for bibtex, genre in [('@phdthesis{k, type = {Diss.}, school = {S}}', 'PhD thesis'),
                              ('@mastersthesis{k, school = {S}}', "Master's thesis"),
                              ('@thesis{k, type = {Habil.}}', 'Habil.'), ('@manual{k, type = {Guide}}', 'Guide'),
                              ('@book{k, type = {Novel}}', None), ('@thesis{k}', None)]:
            [item] = csl(bibtex)
            self.assertEqual(item.get('genre'), genre, bibtex)
        [item] = csl('@book{k, publisher = {P}, school = {S}}')
        self.assertEqual(item['publisher'], 'P')
        [item] = csl('@book{k, organization = {O}}')
        self.assertEqual(item['publisher'], 'O')

    def test_container_issue_keywords(self):
        "formats.md 3.2: container-title, issue or number, keyword as a string"
        for bibtex, key, value in [('@article{k, number = {3}}', 'issue', '3'),
                                   ('@book{k, number = {3}}', 'number', '3'),
                                   ('@book{k, issue = {2}, number = {3}}', 'issue', '2')]:
            [item] = csl(bibtex)
            self.assertEqual((key in item, item.get(key)), (True, value), bibtex)
        [item] = csl('@incollection{k, booktitle = {B}}')
        self.assertEqual(item['container-title'], 'B')
        [item] = csl('@incollection{k, booktitle = {B}, journal = {J}}')
        self.assertEqual(item['container-title'], 'J')
        [item] = csl('@book{k, keywords = { a, b;c ,, d }}')
        self.assertEqual(item['keyword'], 'a, b;c, d')

    def test_dates(self):
        "formats.md 3.2: issued as date-parts or literal, accessed only when urldate gives numbers"
        [item] = csl('@book{k, year = {2013}, urldate = {yesterday}}')
        self.assertEqual(item['issued'], {'date-parts': [[2013]]})
        self.assertNotIn('accessed', item)
        [item] = csl('@book{k, title = {T}}')
        self.assertNotIn('issued', item)

    def test_values(self):
        "formats.md 3.2: date numbers are integers, other values strings; empty values left out"
        [item] = csl('@book{k, volume = {4}, year = {2013}, note = {}, title = {T}}')
        self.assertEqual(item['volume'], '4')
        self.assertIsInstance(item['issued']['date-parts'][0][0], int)
        self.assertNotIn('note', item)


class TestCSLImportFields(unittest.TestCase):

    def test_simple_fields(self):
        "formats.md 3.3: the keys of rows 7-21; arrays give their first element, numbers their decimal text"
        e = csl_one(type='book', title=['First', 'Second'], volume=4, DOI='doi:10.1/x', URL='https://u',
                    ISBN='978', ISSN='1234', publisher='P', **{'publisher-place': 'Potsdam'}, abstract='A',
                    note='N', edition=2, language='en', **{'collection-title': 'S'}, PMID='1', PMCID='PMC1',
                    other='ignored')
        self.assertEqual(fields(e), {'title': 'First', 'volume': '4', 'doi': '10.1/x', 'url': 'https://u',
                                     'isbn': '978', 'issn': '1234', 'publisher': 'P', 'address': 'Potsdam',
                                     'abstract': 'A', 'note': 'N', 'edition': '2', 'language': 'en',
                                     'series': 'S', 'pmid': '1', 'pmcid': 'PMC1'})

    def test_number_pages_publisher_genre(self):
        "formats.md 3.3: number, pages, publisher of a thesis or report, genre of a report"
        self.assertEqual(csl_one(type='book', issue='2', number='3')['number'], '2')
        self.assertEqual(csl_one(type='book', number=3)['number'], '3')
        self.assertEqual(csl_one(type='book', page='1-2')['pages'], '1--2')
        self.assertEqual(fields(csl_one(type='thesis', publisher='ETH')), {'school': 'ETH'})
        self.assertEqual(fields(csl_one(type='thesis', genre="Master's", publisher='ETH')), {'school': 'ETH'})
        self.assertEqual(fields(csl_one(type='report', publisher='PIK', genre='WP')),
                         {'institution': 'PIK', 'type': 'WP'})
        self.assertEqual(fields(csl_one(type='book', publisher='P', genre='G')), {'publisher': 'P'})

    def test_keywords(self):
        "formats.md 3.3: keyword (an array joined first) split on , or ; and joined with , "
        self.assertEqual(csl_one(type='book', keyword='a;b , c')['keywords'], 'a, b, c')
        self.assertEqual(csl_one(type='book', keyword=['a; b', 'c'])['keywords'], 'a, b, c')

    def test_issued_and_accessed(self):
        "formats.md 3.3: issued from date-parts, else raw, else literal; accessed zero-padded"
        for issued, year in [({'date-parts': [[2013, 5]], 'raw': '2001'}, ('2013', '5')),
                             ({'date-parts': [['2013', '5']]}, ('2013', '5')),
                             ({'raw': '2001-02', 'literal': '2002'}, ('2001', '2')),
                             ({'literal': '2002'}, ('2002', None)), ('2003-04', ('2003', '4'))]:
            e = csl_one(type='book', issued=issued)
            self.assertEqual((e['year'], fields(e).get('month')), year, issued)
        self.assertEqual(csl_one(type='book', accessed={'date-parts': [[2020, 3, 4]]})['urldate'], '2020-03-04')
        self.assertEqual(csl_one(type='book', accessed={'raw': '2020-3'})['urldate'], '2020-03')

    def test_files_and_key(self):
        "formats.md 3.3: file then custom.file; key from citation-key, else id"
        e = csl_one(id='a2000', type='book', file='a.pdf', custom={'file': ['b.pdf']})
        self.assertEqual((e.key, links(e)), ('a2000', ['a.pdf', 'b.pdf']))
        self.assertEqual(csl_one(id='a2000', **{'citation-key': 'b2000'}).key, 'b2000')
        self.assertEqual(csl_one(id='a2000', **{'citation-key': '12'}).key, 'a2000')


class TestCSLDocument(SpecLibrary):

    def test_reading(self):
        "formats.md 3.4: an array, an object with items, or one item; errors"
        item = {'id': 'a2000', 'type': 'book'}
        for data in ([item], {'items': [item]}, item):
            self.assertEqual([e.key for e in formats.loads(json.dumps(data), 'csl-json')], ['a2000'])
        for text, error in [('{"a": 1', 'not a CSL-JSON file: '), ('[1]', 'not a CSL-JSON file: a list of items is expected'),
                            ('"x"', 'not a CSL-JSON file: a list of items is expected'),
                            ('{"items": 1}', 'not a CSL-JSON file: a list of items is expected')]:
            with self.assertRaises(ValueError) as cm:
                formats.loads(text, 'csl-json')
            self.assertTrue(str(cm.exception).startswith(error), text)

    def test_add_error_exit(self):
        "formats.md 3.4: an unreadable CSL-JSON file is an error of add (exit 1)"
        self.bib(entry('one2000'))
        self.write('bad.json', content='[1]')
        code, out, err = run_papers('add', '../bad.json', '--no-pool', cwd=self.path('lib'))
        self.assertEqual(code, 1)
        self.assertIn('papers: error: ', err)
        self.assertIn('a list of items is expected', err)

    def test_example(self):
        "formats.md 3.4: the example of papers list --format csl-json"
        self.bib('@techreport{rep2020,\n author = {Doe, Jane},\n title = {Report},\n institution = {PIK},\n'
                 ' address = {Potsdam},\n type = {Working paper},\n year = {2020}\n}\n')
        self.assertEqual(self.out('list rep2020 --format csl-json'), EXAMPLE_CSL)


EXAMPLE_CSL = '''[
  {
    "id": "rep2020",
    "citation-key": "rep2020",
    "type": "report",
    "author": [
      {
        "family": "Doe",
        "given": "Jane"
      }
    ],
    "title": "Report",
    "publisher": "PIK",
    "publisher-place": "Potsdam",
    "genre": "Working paper",
    "issued": {
      "date-parts": [
        [
          2020
        ]
      ]
    }
  }
]
'''


class TestCSLLost(unittest.TestCase):

    def test_round_trip(self):
        "formats.md 3.5: month as a number, journal or booktitle by type, school or institution, issue"
        bibtex = ('@article{a, title = {T}, year = {2013}, month = may, issue = {2}, eprint = {e}}\n'
                  '@manual{m, title = {M}, organization = {O}}\n'
                  '@book{b, title = {B}, booktitle = {C}}\n'
                  '@inbook{i, title = {I}, booktitle = {C}}\n')
        a, m, b, i = formats.loads(formats.dumps(parse(bibtex), 'csl-json'), 'csl-json')
        self.assertEqual((a.entry_type, fields(a)), ('article', {'title': 'T', 'year': '2013', 'month': '5',
                                                                 'number': '2'}))
        self.assertEqual((m.entry_type, fields(m)), ('techreport', {'title': 'M', 'institution': 'O'}))
        self.assertEqual((b.entry_type, fields(b)), ('book', {'title': 'B', 'journal': 'C'}))
        self.assertEqual((i.entry_type, fields(i)), ('incollection', {'title': 'I', 'booktitle': 'C'}))


# 4. RIS
# ======

@needs_rispy
class TestRISLines(unittest.TestCase):

    def test_tag_lines(self):
        "formats.md 4.1: a tag line is [A-Z][A-Z0-9] + '  -' + a separator; other lines continue"
        e = ris_one('BOOK', 'TI  - Title', 'ti  - lower', '1A  - not a tag', 'T1  -x',
                    'KW  - k', 'kw  - also continued', 'KW  -')
        self.assertEqual(e['title'], 'Title ti  - lower 1A  - not a tag')
        self.assertEqual(e['keywords'], 'k, kw  - also continued')
        self.assertEqual(ris_one('BOOK', 'T1  -XTitle')['title'], 'Title')


@needs_rispy
class TestRISReading(unittest.TestCase):

    def test_records(self):
        "formats.md 4.2: lines outside records skipped, records from TY to ER, the last without ER read"
        text = ('Provider: x\n\nTY  - BOOK\nTI  - One\nER  - \nbetween\n\nTY  - JOUR\nTI  - Two\nER  -\n'
                'TY  - GEN\nTI  - Three\n')
        self.assertEqual([e['title'] for e in ris_import(text)], ['One', 'Two', 'Three'])

    def test_continuation(self):
        "formats.md 4.2: a continuation adds an item to a list tag, a space and text to a single tag"
        e = ris_one('BOOK', 'TI  - A long', '   title  ', 'AB  - first', 'second', 'AU  - Doe, J', 'Roe, R')
        self.assertEqual((e['title'], e['abstract'], e['author']), ('A long title', 'first second',
                                                                    'Doe, J and Roe, R'))

    def test_stray_lines(self):
        "formats.md 4.2: blank lines in a record, and lines between TY and the first tag, are dropped"
        e = ris_one('BOOK', 'stray', '', 'KW  - a', '', '  ', 'TI  - T')
        self.assertEqual((e['title'], e['keywords']), ('T', 'a'))

    def test_single_and_list_tags(self):
        "formats.md 4.2: single tags keep their first value, list tags all; UR split on ;"
        e = ris_one('JOUR', 'TI  - First', 'TI  - Second', 'VL  - 1', 'VL  - 2', 'A1  - Doe, J', 'A1  - Roe, R',
                    'UR  - https://a.org; https://b.org')
        self.assertEqual((e['title'], e['volume'], e['author'], e['url']),
                         ('First', '1', 'Doe, J and Roe, R', 'https://a.org'))
        e = ris_one('JOUR', 'UR  - https://doi.org/10.1/x; https://b.org')
        self.assertEqual((e['url'], e['doi']), ('https://b.org', '10.1/x'))

    def test_unknown_tags_and_errors(self):
        "formats.md 4.2: unknown tags ignored; a text without record is an error, a blank text is empty"
        e = ris_one('BOOK', 'TI  - T', 'ZZ  - unknown', 'C1  - custom')
        self.assertEqual(fields(e), {'title': 'T'})
        with self.assertRaises(ValueError) as cm:
            ris_import('no record\nhere\n')
        self.assertEqual(str(cm.exception), 'not a RIS file: no record found (a record starts with TY  - )')
        self.assertEqual(ris_import(' \n\n'), [])


EXAMPLE_BIB = r'''@article{perrette2013,
 author = {Perrette, M. and van der Berg, Jan and {World Health Organization} and Smith, Jr, John},
 title = {A scaling approach to sea level},
 journal = {Earth System Dynamics},
 year = {2013},
 month = may,
 volume = {4},
 number = {1},
 pages = {11--29},
 doi = {https://doi.org/10.5194/esd-4-11-2013},
 url = {https://esd.copernicus.org/x},
 urldate = {2024-03-01},
 issn = {2190-4979},
 abstract = {Sea level
 rise.},
 keywords = {sea level, ice; amoc},
 note = {A note},
 file = {:files/perrette2013.pdf:pdf}
}

@techreport{rep2020,
 author = {Doe, Jane},
 translator = {Roe, Jr,},
 title = {Report},
 institution = {PIK},
 address = {Potsdam},
 type = {Working paper},
 year = {2020}
}

@mastersthesis{th2019,
 author = {Doe, Jane},
 title = {Thesis},
 school = {ETH},
 year = {2019}
}
'''

EXAMPLE_RIS = '''TY  - JOUR
ID  - perrette2013
AU  - Perrette, M.
AU  - van der Berg, Jan
AU  - World Health Organization
AU  - Smith, John, Jr
TI  - A scaling approach to sea level
T2  - Earth System Dynamics
PY  - 2013
DA  - 2013/05/
VL  - 4
IS  - 1
SP  - 11
EP  - 29
DO  - 10.5194/esd-4-11-2013
UR  - https://esd.copernicus.org/x
Y2  - 2024-03-01
SN  - 2190-4979
AB  - Sea level
 rise.
KW  - sea level
KW  - ice; amoc
N1  - A note
L1  - files/perrette_et_al_2013_a-scaling-approach-to-sea-level.pdf
ER  -

TY  - RPRT
ID  - rep2020
AU  - Doe, Jane
A4  - Roe, , Jr
TI  - Report
PY  - 2020
PB  - PIK
CY  - Potsdam
M3  - Working paper
ER  -

TY  - THES
ID  - th2019
AU  - Doe, Jane
TI  - Thesis
PY  - 2019
PB  - ETH
M3  - Master's thesis
ER  -
'''.replace('ER  -\n', 'ER  - \n')  # the ER line ends with a space


@needs_rispy
class TestRISWriting(SpecLibrary):

    def test_example(self):
        "formats.md 4.3: the example of papers export --format ris, byte for byte"
        self.bib(EXAMPLE_BIB)
        self.write('lib', 'files', 'perrette2013.pdf')
        self.lib('export ../out --format ris')
        self.assertEqual(Path(self.path('out', 'papers.ris')).read_text(), EXAMPLE_RIS)

    def test_no_entries(self):
        "formats.md 4.3: no entries is the empty text"
        self.assertEqual(formats.dumps([], 'ris'), '')

    def test_tags(self):
        "formats.md 4.3: ED, T3, IS from issue, SN isbn then issn, PB fallbacks, ET, LA, M3 of the types"
        text = ris_text('@incollection{k, editor = {Ed, E. and {Org}}, booktitle = {B}, series = {S},'
                        ' issue = {2}, number = {3}, isbn = {978}, issn = {1234-5678}, organization = {O},'
                        ' edition = {2}, language = {en}, type = {Chapter}}')
        self.assertEqual(text, 'TY  - CHAP\nID  - k\nED  - Ed, E.\nED  - Org\nT2  - B\nT3  - S\nIS  - 2\n'
                               'SN  - 978\nSN  - 1234-5678\nPB  - O\nET  - 2\nLA  - en\nER  - \n')
        for bibtex, m3 in [('@phdthesis{k, type = {Diss}}', 'Diss'), ('@thesis{k, type = {Habil}}', 'Habil'),
                           ('@report{k, type = {WP}}', 'WP'), ('@mastersthesis{k, type = {Diplom}}', 'Diplom'),
                           ('@phdthesis{k}', None), ('@book{k, type = {Novel}}', None)]:
            lines = [l for l in ris_text(bibtex).splitlines() if l.startswith('M3')]
            self.assertEqual(lines, [f'M3  - {m3}'] if m3 else [], bibtex)

    def test_dates(self):
        "formats.md 4.3: PY the year, DA only with a month (zero-padded, trailing /)"
        for bibtex, lines in [('year = {2013}', ['PY  - 2013']), ('date = {2013-05-02}', ['PY  - 2013', 'DA  - 2013/05/02/']),
                              ('year = {in press}', ['PY  - in press'])]:
            text = ris_text('@book{k, ' + bibtex + '}')
            self.assertEqual([l for l in text.splitlines() if l[:2] in ('PY', 'DA')], lines, bibtex)


RIS_EXPORT_TYPES = {'article': 'JOUR', 'book': 'BOOK', 'booklet': 'PAMP', 'inbook': 'CHAP', 'incollection': 'CHAP',
                    'inproceedings': 'CPAPER', 'conference': 'CPAPER', 'proceedings': 'CONF', 'phdthesis': 'THES',
                    'mastersthesis': 'THES', 'thesis': 'THES', 'techreport': 'RPRT', 'report': 'RPRT',
                    'manual': 'RPRT', 'misc': 'GEN', 'online': 'ELEC', 'electronic': 'ELEC', 'www': 'ELEC',
                    'dataset': 'DATA', 'software': 'COMP', 'unpublished': 'UNPB', 'patent': 'PAT', 'other': 'GEN',
                    'ARTICLE': 'JOUR'}

RIS_IMPORT_TYPES = {'JOUR': 'article', 'JFULL': 'article', 'EJOUR': 'article', 'MGZN': 'article', 'NEWS': 'article',
                    'INPR': 'article', 'BOOK': 'book', 'EBOOK': 'book', 'EDBOOK': 'book', 'PAMP': 'booklet',
                    'CHAP': 'incollection', 'ECHAP': 'incollection', 'ENCYC': 'incollection', 'DICT': 'incollection',
                    'CPAPER': 'inproceedings', 'CONF': 'inproceedings', 'THES': 'phdthesis', 'RPRT': 'techreport',
                    'GOVDOC': 'techreport', 'GEN': 'misc', 'ELEC': 'online', 'BLOG': 'online', 'DATA': 'dataset',
                    'DBASE': 'dataset', 'COMP': 'software', 'UNPB': 'unpublished', 'MANSCPT': 'unpublished',
                    'PAT': 'patent', 'ABST': 'misc', 'jour': 'article', ' BOOK ': 'book'}


@needs_rispy
class TestRISTypes(unittest.TestCase):

    def test_export(self):
        "formats.md 4.4: bibtex to RIS types"
        for bibtex, ris in RIS_EXPORT_TYPES.items():
            self.assertTrue(ris_text('@' + bibtex + '{k}').startswith(f'TY  - {ris}\n'), bibtex)

    def test_import(self):
        "formats.md 4.4: RIS to bibtex types (trimmed, upper-cased); THES with an M3 of master"
        for ris, bibtex in RIS_IMPORT_TYPES.items():
            self.assertEqual(ris_one(ris, 'TI  - T').entry_type, bibtex, ris)
        self.assertEqual(ris_one('THES', 'M3  - MASTER thesis').entry_type, 'mastersthesis')
        self.assertEqual(ris_one('THES', 'M3  - Diplom').entry_type, 'phdthesis')


@needs_rispy
class TestRISImportFields(unittest.TestCase):

    def test_names(self):
        "formats.md 4.5: author from AU then A1, editor from ED or A2 for some types, translator from A4"
        e = ris_one('CHAP', 'A1  - First, A', 'AU  - Second, B', 'A2  - Ed, E', 'A4  - Tr, T')
        self.assertEqual((e['author'], e['editor'], e['translator']), ('Second, B and First, A', 'Ed, E', 'Tr, T'))
        e = ris_one('JOUR', 'AU  - Doe, J', 'A2  - Ed, E')
        self.assertNotIn('editor', fields(e))
        e = ris_one('BOOK', 'ED  - One, O', 'A2  - Ed, E')
        self.assertEqual(e['editor'], 'One, O')

    def test_ris_names(self):
        "formats.md 4.5: RIS names to bibtex names"
        for name, bibtex in [('Smith', 'Smith'), ('John Smith', '{John Smith}'), ('Smith, John', 'Smith, John'),
                             ('Smith,', 'Smith'), ('Smith, John, Jr', 'Smith, Jr, John'), ('Doe, , Jr', 'Doe, Jr,'),
                             ('Smith, John, ', 'Smith, John'), (' Smith ,  John ', 'Smith, John'),
                             ('{A, B}, C', '{A, C, B}')]:
            self.assertEqual(ris_one('BOOK', 'AU  - ' + name)['author'], bibtex, name)

    def test_titles_and_container(self):
        "formats.md 4.5: title from TI, T1; the container from T2, JF, JO, JA, J2 (booktitle for parts)"
        self.assertEqual(ris_one('JOUR', 'T1  - One', 'TI  - Two')['title'], 'Two')
        self.assertEqual(ris_one('JOUR', 'T1  - One')['title'], 'One')
        self.assertEqual(ris_one('JOUR', 'J2  - E', 'JA  - D', 'JO  - C', 'JF  - B')['journal'], 'B')
        self.assertEqual(ris_one('JOUR', 'J2  - E', 'JA  - D')['journal'], 'D')
        for ris, name in [('CHAP', 'booktitle'), ('CPAPER', 'booktitle'), ('BOOK', 'journal'), ('GEN', 'journal'),
                          ('JOUR', 'journal')]:
            self.assertEqual(fields(ris_one(ris, 'T2  - C')).get(name), 'C', ris)
        self.assertEqual(ris_one('BOOK', 'T3  - S')['series'], 'S')

    def test_dates(self):
        "formats.md 4.5: year and month from PY, Y1, DA"
        for lines, expected in [(['PY  - 2013'], ('2013', None)), (['Y1  - 2013/05/02/'], ('2013', '5')),
                                (['PY  - 2013', 'DA  - 2013/05/'], ('2013', '5')),
                                (['PY  - 2013', 'DA  - 2014/05/'], ('2013', None)),
                                (['PY  - 2013', 'Y1  - 2013/06'], ('2013', '6')),
                                (['PY  - 2013', 'Y1  - 2013/06', 'DA  - 2013/07'], ('2013', '7')),
                                (['DA  - 2013/07'], ('2013', '7'))]:
            e = ris_one('JOUR', *lines)
            self.assertEqual((e['year'], fields(e).get('month')), expected, lines)

    def test_pages(self):
        "formats.md 4.5: pages from SP and EP"
        for lines, pages in [(['SP  - 11', 'EP  - 29'], '11--29'), (['SP  - 11', 'EP  - 11'], '11'),
                             (['SP  - 11-29'], '11--29'), (['EP  - 29'], None)]:
            self.assertEqual(fields(ris_one('JOUR', *lines)).get('pages'), pages, lines)

    def test_identifiers(self):
        "formats.md 4.5: doi, url, issn and isbn"
        e = ris_one('JOUR', 'DO  - https://doi.org/10.1/x', 'UR  - https://doi.org/10.2/y', 'UR  - https://a.org')
        self.assertEqual((e['doi'], e['url']), ('10.1/x', 'https://a.org'))
        e = ris_one('JOUR', 'SN  - 1234-567X (Print)', 'SN  - 978-3-16 ', 'SN  - 2345-6789', 'SN  - 978-0')
        self.assertEqual((e['issn'], e['isbn']), ('1234-567X (Print)', '978-3-16'))

    def test_other_fields(self):
        "formats.md 4.5: publisher, address, abstract, keywords, note, edition, language, type, urldate, key"
        e = ris_one('RPRT', 'ID  - rep2020', 'PB  - PIK', 'PB  - other', 'CY  - Potsdam', 'N2  - Abstract 2',
                    'KW  - a; b', 'KW  - c, d', 'N1  - one ', 'N1  - ', 'N1  - two', 'ET  - 2', 'LA  - en',
                    'M3  - WP', 'Y2  - 2020-01-02')
        self.assertEqual(e.key, 'rep2020')
        self.assertEqual(fields(e), {'institution': 'PIK', 'address': 'Potsdam', 'abstract': 'Abstract 2',
                                     'keywords': 'a, b, c, d', 'note': 'one; two', 'edition': '2', 'language': 'en',
                                     'type': 'WP', 'urldate': '2020-01-02'})
        self.assertEqual(ris_one('JOUR', 'AB  - A', 'N2  - B')['abstract'], 'A')
        self.assertEqual(fields(ris_one('THES', 'PB  - ETH', 'M3  - PhD')), {'school': 'ETH', 'type': 'PhD'})
        self.assertEqual(fields(ris_one('THES', 'PB  - ETH', 'M3  - Master')), {'school': 'ETH'})
        self.assertEqual(fields(ris_one('BOOK', 'PB  - P', 'M3  - Novel')), {'publisher': 'P'})


@needs_rispy
class TestRISLost(unittest.TestCase):

    def test_keyword_with_semicolon(self):
        "formats.md 4.6: a keyword with ; exported as one KW line comes back as two keywords"
        text = ris_text('@book{k, keywords = {ice; amoc}, pmid = {1}, eprint = {e}}')
        self.assertEqual(text, 'TY  - BOOK\nID  - k\nKW  - ice; amoc\nER  - \n')
        self.assertEqual(ris_import(text)[0]['keywords'], 'ice, amoc')


# 5. BibJSON
# ==========

EXAMPLE_BIBJSON = '''{
  "metadata": {
    "records": 2,
    "namespace": {
      "bibtex": "https://www.bibtex.org/Format/"
    }
  },
  "records": [
    {
      "type": "techreport",
      "id": "rep2020",
      "title": "R{\\\\'e}port \\\\& co",
      "author": [
        {
          "name": "Doe, Jane"
        },
        {
          "name": "{IPCC}"
        }
      ],
      "month": "may",
      "bibtex:type": "Working paper",
      "journal": {
        "name": "J"
      },
      "editor": [
        {
          "name": "Not, A."
        },
        {
          "name": "List, B."
        }
      ]
    },
    {
      "type": "misc",
      "id": "b2000",
      "title": "B",
      "file": [
        "../lib/files/b.pdf"
      ]
    }
  ]
}
'''


class TestBibJSONWriting(SpecLibrary):

    def test_example(self):
        "formats.md 5.1: the collection, the record keys in their order, namespaced keys"
        self.bib("@TechReport{rep2020,\n title = {R{\\'e}port \\& co},\n author = {Doe, Jane and {IPCC}},\n"
                 " month = may,\n type = {Working paper},\n journal = {J},\n Editor = {Not, A. and List, B.}\n}\n\n"
                 "@misc{b2000,\n title = {B},\n file = {:files/b.pdf:pdf}\n}\n")
        self.write('lib', 'files', 'b.pdf')
        self.lib('export ../out --format bibjson --files link')
        self.assertEqual(Path(self.path('out', 'papers.bib.json')).read_text(), EXAMPLE_BIBJSON)

    def test_without_namespace(self):
        "formats.md 5.1: no bibtex: key, no namespace"
        self.assertEqual(json.loads(formats.dumps(parse('@book{k, title = {T}}'), 'bibjson'))['metadata'],
                         {'records': 1})
        for name in ('type', 'id', 'cid', 'collection', 'identifier', 'link', 'license'):
            record = json.loads(formats.dumps(parse('@book{k, ' + name + ' = {x}}'), 'bibjson'))['records'][0]
            self.assertEqual(record, {'type': 'book', 'id': 'k', 'bibtex:' + name: 'x'}, name)


class TestBibJSONReading(unittest.TestCase):

    def read(self, *records):
        return formats.loads(json.dumps(list(records)), 'bibjson')

    def test_records(self):
        "formats.md 5.2: an object with records, any other object one record, else an error"
        record = {'type': 'book', 'id': 'k'}
        for data in ({'records': [record]}, record, [record]):
            self.assertEqual([e.key for e in formats.loads(json.dumps(data), 'bibjson')], ['k'])
        for text in ('[1]', '"x"', '{"records": {}}'):
            with self.assertRaises(ValueError) as cm:
                formats.loads(text, 'bibjson')
            self.assertEqual(str(cm.exception), 'not a BibJSON file: a collection {"records": [...]} or a list of '
                                                'records is expected', text)
        with self.assertRaisesRegex(ValueError, '^not a BibJSON file: '):
            formats.loads('{', 'bibjson')

    def test_type_key_and_skipped(self):
        "formats.md 5.2: entry type lower-cased or misc, key id or cid, bibtex:<name>, skipped keys"
        [e] = self.read({'type': 'TechReport', 'cid': 'c2000', 'bibtex:type': 'WP', 'bibtex:any': 'x', '_x': 1,
                         'collection': 'c', 'identifier': [], 'link': [], 'license': 'l', 'note': None})
        self.assertEqual((e.entry_type, e.key, fields(e)), ('techreport', 'c2000', {'type': 'WP', 'any': 'x'}))
        [e] = self.read({'type': '', 'id': 'i2000', 'cid': 'c2000'})
        self.assertEqual((e.entry_type, e.key), ('misc', 'i2000'))
        [e] = self.read({})
        self.assertEqual((e.entry_type, e.key), ('misc', ''))

    def test_values(self):
        "formats.md 5.2: names, objects, arrays, booleans, numbers as written"
        [e] = formats.loads('[{"author": ["Doe, J", {"name": "Roe, R"}, null], "editor": "Ed, E",'
                            ' "journal": {"title": "x"}, "publisher": {"name": "P"}, "keywords": ["a", null, ["b", "c"]],'
                            ' "ok": true, "no": false, "year": 2000, "pages": 1.50, "volume": -1e3}]', 'bibjson')
        self.assertEqual(fields(e), {'author': 'Doe, J and Roe, R', 'editor': 'Ed, E', 'publisher': 'P',
                                     'keywords': 'a, b, c', 'ok': 'true', 'no': 'false', 'year': '2000',
                                     'pages': '1.50', 'volume': '-1e3'})

    def test_doi_and_file(self):
        "formats.md 5.2: doi from the identifiers when there is no doi key; file"
        [e] = self.read({'identifier': [{'type': 'issn', 'id': '1'}, {'type': 'DOI', 'id': 'doi:10.1/x'},
                                        {'type': 'doi', 'id': '10.2/y'}], 'file': ['a.pdf', 'file:///b.pdf']})
        self.assertEqual((e['doi'], links(e)), ('10.1/x', ['a.pdf', '/b.pdf']))
        [e] = self.read({'doi': '10.3/z', 'identifier': [{'type': 'doi', 'id': '10.2/y'}]})
        self.assertEqual(e['doi'], '10.3/z')


class TestBibJSONLost(unittest.TestCase):

    def test_round_trip(self):
        "formats.md 5.3: fields kept, a field starting with _ lost, a month macro comes back braced"
        [e] = parse('@book{k, title = {T{\\"o}}, type = {X}, _private = {p}, month = may}')
        text = formats.dumps([e], 'bibjson')
        [back] = formats.loads(text, 'bibjson')
        self.assertEqual(fields(back), {'title': 'T{\\"o}', 'type': 'X', 'month': 'may'})
        self.assertIn('month = {may}', format_entries([back]))


# 6. papers list output
# =====================

class TestListOutput(SpecLibrary):

    def test_no_entry(self):
        "formats.md 6: the output of each format when no entry is listed"
        self.bib(entry('one2000'))
        self.assertEqual(self.out('list --key none2000 -K'), '')
        self.assertEqual(self.out('list --key none2000 --format bibtex'), '\n')
        self.assertEqual(self.out('list --key none2000 --format csl-json'), '[]\n')
        self.assertEqual(self.out('list --key none2000 --format bibjson'),
                         '{\n  "metadata": {\n    "records": 0\n  },\n  "records": []\n}\n')
        if HAS_RISPY:
            self.assertEqual(self.out('list --key none2000 --format ris'), '')

    def test_bibtex(self):
        "formats.md 6: --format bibtex: the entries as the library writes them, then one \\n"
        self.bib(entry('one2000', 'files/one.pdf'))
        text = Path(self.path('lib', 'papers.bib')).read_text()
        self.lib('tag one2000 --add x')  # saved as papers writes it
        text = Path(self.path('lib', 'papers.bib')).read_text()
        self.assertEqual(self.out('list --format bibtex'), text + '\n')
        self.assertIn('file = {:files/one.pdf:pdf}', text)

    def test_field(self):
        "formats.md 6: --field: KEY: and the raw values separated by spaces, --no-key the values only"
        self.bib('@book{one2000,\n title = {T{\\"o}},\n year = {2000}\n}\n')
        self.assertEqual(self.out('list --field year note title'), 'one2000: 2000  T{\\"o}\n')
        self.assertEqual(self.out('list --field note year --no-key'), ' 2000\n')
        self.assertEqual(self.out('list --field year --no-key'), '2000\n')

    def test_search_normalized(self):
        "formats.md 6.1: the search words and the texts of the entries compared after norm (bibtex.md 9.1)"
        self.bib('@article{latex2000,\n author = {M{\\"u}ller, Jan},\n title = {{S}ea level},\n year = {2000}\n}\n',
                 '@article{plain2000,\n author = {Müller, Jan},\n title = {Straße},\n year = {2000}\n}\n')
        both = 'latex2000\nplain2000\n'
        self.assertEqual(self.out('list -K Muller'), both)
        self.assertEqual(self.out('list -K Müller'), both)
        self.assertEqual(self.out('list -K --author muller'), both)
        self.assertEqual(self.out("list -K --first-author 'M{\\\"u}ller' --strict"), both)
        self.assertEqual(self.out('list -K --title "sea level"'), 'latex2000\n')
        self.assertEqual(self.out('list -K --title strasse'), 'plain2000\n')

    def test_other_formats_paths(self):
        "formats.md 6: RIS, CSL-JSON, BibJSON: absolute normalised paths, symlinks not resolved"
        os.symlink(self.path('lib', 'files'), self.path('lib', 'link'))
        self.bib(entry('one2000', 'link/../link/one.pdf'))
        [item] = json.loads(self.out('list --format csl-json'))
        self.assertEqual(item['custom'], {'file': [self.path('lib', 'link', 'one.pdf')]})

    def test_line_format(self):
        "formats.md 6: KEY: TITLE INFO, the title cut at 60 characters, the items of INFO"
        title = 'x' * 61
        self.bib(entry('one2000', 'files/a.pdf', doi='10.1/x').replace('Title of one2000', title),
                 '@book{two2000,\n title = {Short},\n keywords = {a, b; c}\n}\n', '@book{three2000}\n')
        self.assertEqual(self.out('list'), f'one2000: {"x" * 60}... (doi:10.1/x, file:1)\n'
                                           'two2000: Short (a | b; c)\nthree2000:  \n')
        self.assertEqual(self.out('list --key two2000 --no-key'), ' Short (a | b; c)\n')


# 7. --porcelain
# ==============

class TestPorcelainStreams(SpecLibrary):

    def test_formats_on_stdout(self):
        "formats.md 7.1: the listing of papers list on standard output, other output on standard error"
        self.bib(entry('one2000'))
        out, err = self.out_err('list --format csl-json --porcelain')
        self.assertEqual(json.loads(out)[0]['id'], 'one2000')
        out, err = self.out_err('export ../out --format csl-json --porcelain')
        self.assertEqual(out, '')
        self.assertIn('exported 1 entries', err)

    def test_commands_without_lines(self):
        "formats.md 7.2: commands that print no porcelain lines write nothing on standard output"
        self.bib(entry('one2000'))
        self.lib('tag one2000 --add x')
        for cmd in ('status', 'undo', 'redo', 'file check', 'config', 'tag'):
            out, err = self.out_err(cmd + ' --porcelain')
            self.assertEqual(out, '', cmd)


class TestPorcelainLines(SpecLibrary):

    def test_order(self):
        "formats.md 7.2: removed, renamed, added, then modified, each sorted by code point"
        self.bib(entry('b2000'), entry('Z2000'), entry('a2000'), entry('c2000'))
        out, _ = self.out_err('tag b2000 Z2000 a2000 --add x --porcelain')
        self.assertEqual(out, 'modified Z2000\nmodified a2000\nmodified b2000\n')
        out, _ = self.out_err('rm c2000 a2000 --keep-files --porcelain')
        self.assertEqual(out, 'removed a2000\nremoved c2000\n')

    def test_existing_only_for_add(self):
        "formats.md 7.2: unchanged touched entries are existing for add only"
        self.bib(entry('one2000'))
        self.lib('tag one2000 --add x')
        out, _ = self.out_err('tag one2000 --add x --porcelain')
        self.assertEqual(out, '')

    def test_content_equality(self):
        "formats.md 7.2: content equality ignores the order of the fields"
        self.bib(entry('one2000'))
        new = self.write('new.bib', content='@article{x,\n year = {2000},\n title = {Title of one2000},\n'
                                             ' author = {Some One}\n}\n')
        self.assertEqual(self.out_err(f'edit one2000 --from {new} --porcelain')[0], '')
        new = self.write('new.bib', content='@article{x,\n year = {2001},\n title = {Title of one2000}\n}\n')
        self.assertEqual(self.out_err(f'edit one2000 --from {new} --porcelain')[0], 'modified one2000\n')

    def test_add_lines(self):
        "formats.md 7.2: add: added, modified and existing lines"
        self.bib(entry('one2000'), entry('two2000'))
        new = self.write('new.bib', content=entry('three2000') + entry('one2000').replace(
            'year = {2000}', 'year = {2000},\n volume = {3}') + entry('two2000'))
        out, _ = self.out_err(f'add {new} --on-duplicate update --no-pool --porcelain')
        self.assertEqual(out, 'added three2000\nmodified one2000\nexisting two2000\n')


class TestPorcelainCommands(SpecLibrary):

    def porcelain(self, cmd):
        return self.out_err(cmd + ' --porcelain')[0]

    def test_file_commands(self):
        "formats.md 7.2: file attach and file rename print modified lines"
        self.bib(entry('one2000'))
        pdf = self.write('a.pdf')
        self.assertEqual(self.porcelain(f'file attach one2000 {pdf} --copy'), 'modified one2000\n')
        self.lib('config name.template "{key}-x"')
        self.assertEqual(self.porcelain('file rename --move'), 'modified one2000\n')

    def test_history_revert(self):
        "formats.md 7.2: history --revert prints the lines of the entries it changed"
        self.bib(entry('one2000'))
        self.lib('tag one2000 --add x')
        self.lib('rm one2000 --keep-files')
        [step] = [line.split()[1] for line in self.out('history').splitlines() if 'papers rm' in line]
        self.assertEqual(self.porcelain(f'history --revert {step}'), 'added one2000\n')


class TestPorcelainConfigPool(onetime.OneTimeTest):

    def test_config_pool(self):
        "formats.md 7.2: config pool none prints the relinked entries"
        self.lib('config pool ../pool -y')
        self.lib('pull Smith_2020')
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            self.lib('config pool none -y --porcelain')
        self.assertEqual(out.getvalue(), 'modified Smith_2020\n')


class TestExitCodes(SpecLibrary):

    def test_codes(self):
        "formats.md 7.3: 0 success, 1 an error, 2 a usage error; papers: error: on standard error"
        self.bib(entry('one2000'))
        lib = self.path('lib')
        self.assertEqual(run_papers('list', '-K', cwd=lib), (0, 'one2000\n', ''))
        code, out, err = run_papers('export', '--dry-run', '../out', cwd=lib)
        self.assertEqual((code, out), (1, ''))
        self.assertEqual(err, 'papers: error: export does not support --dry-run\n')
        code, out, err = run_papers('list', '--no-such-option', cwd=lib)
        self.assertEqual(code, 2)
        self.assertIn('papers list: error: ', err)

    def test_refused_rename(self):
        "formats.md 7.3, library.md Path safety 2: a refused file rename is an error: exit 1, files unchanged"
        self.bib(entry('one2000'), entry('two2000'))
        self.lib(f'file attach one2000 {self.write("a.pdf")} --move')
        before = self.files('one2000')
        for template in ('../{author}', '{nope}'):
            for keys in ('', 'one2000 '):
                cmd = f"file rename --move {keys}--name-template '{template}'"
                with self.assertRaises(PapersExit, msg=cmd):
                    self.lib(cmd)
                self.assertEqual(self.files('one2000'), before)
        self.lib("config name.template '../{author}'")
        with self.assertRaises(PapersExit):
            self.lib('list one2000 --rename')
        self.lib("config name.template '{key}-x'")
        self.lib('file rename --move')  # exit 0
        self.assertEqual(self.libfiles(), ['one2000-x.pdf'])

    def test_refused_attach(self):
        "formats.md 7.3, library.md Path safety 2: a refused file attach exits 1, the link is kept"
        self.bib(entry('one2000'))
        pdf = self.write('a.pdf')
        lib = self.path('lib')
        code, out, err = run_papers('file', 'attach', 'one2000', pdf, '--copy', '--name-template', '../{author}', cwd=lib)
        self.assertEqual(code, 1)
        self.assertIn('points outside the files directory', err)
        self.assertEqual(self.files('one2000'), [pdf])
        self.lib("config name.template '../{author}'")
        self.lib('config files move')
        code, out, err = run_papers('list', '-k', 'one2000', '--attach', self.write('b.pdf'), cwd=lib)
        self.assertEqual(code, 1, err)

    def test_template_error(self):
        "formats.md 7.3, library.md Syntax: a template that cannot be formatted is a clean error, exit 1"
        self.bib(entry('one2000'))
        pdf = self.write('a.pdf')
        lib = self.path('lib')
        for template in ('{year.real}', '{year[x]}', '{nope}'):
            code, out, err = run_papers('file', 'attach', 'one2000', pdf, '--copy', '--name-template', template, cwd=lib)
            self.assertEqual(code, 1, template)
            self.assertTrue(err.startswith('papers: error: '), err)
            self.assertNotIn('Traceback', err)
        code, out, err = run_papers('add', '--title', 'T', '--author', 'A, B', '--year', '2001', '--key-template', '{year.real}', cwd=lib)
        self.assertEqual((code, err.startswith('papers: error: invalid key template')), (1, True), err)

    def test_question_without_input(self):
        "formats.md 7.3: a question with closed standard input exits 1"
        self.bib(entry('one2000', doi='10.1/x'))
        self.write('dup.bib', content=entry('other2000', doi='10.1/x').replace('Title of other2000', 'Other'))
        code, out, err = run_papers('add', '../dup.bib', '--no-pool', cwd=self.path('lib'))
        self.assertEqual(code, 1)
        self.assertIn('papers: error: ', err)


# 8. JSON text format
# ===================

class TestJSONText(unittest.TestCase):

    def test_bytes(self):
        "formats.md 8: indentation, separators, UTF-8, escapes, / not escaped, final \\n"
        [e] = parse('@book{k, url = {a}}')
        e['url'] = 'Gö "q" \\ / \t\n\r\b\f\x01\x1f\x7f'
        for fmt, key in (('csl-json', 'URL'), ('bibjson', 'url')):
            text = formats.dumps([e], fmt)
            self.assertIn(f'"{key}": "Gö \\"q\\" \\\\ / \\t\\n\\r\\b\\f\\u0001\\u001f\x7f"', text, fmt)
            self.assertTrue(text.endswith('}\n' if fmt == 'bibjson' else ']\n'), fmt)
            self.assertFalse(any(line != line.rstrip() for line in text.splitlines()), fmt)
        self.assertEqual(formats.dumps([e], 'csl-json').splitlines()[:3], ['[', '  {', '    "id": "k",'])


# 9. papers export layout
# =======================

class TestExportLayout(SpecLibrary):

    def setUp(self):
        super().setUp()
        self.bib(entry('one2000', 'files/one.pdf'), entry('two2000'))
        self.write('lib', 'files', 'one.pdf')

    def test_dir(self):
        "formats.md 9: DIR must not exist or be empty; --dry-run refused"
        os.makedirs(self.path('empty'))
        self.lib('export ../empty')
        self.assertTrue(os.path.exists(self.path('empty', 'papers.bib')))
        Path(self.path('file')).write_text('x')
        with self.assertRaisesRegex(PapersExit, 'file: exists and is not an empty directory'):
            self.lib('export ../file')
        with self.assertRaisesRegex(PapersExit, '^export does not support --dry-run$'):
            self.lib('export ../out --dry-run')
        self.assertFalse(os.path.exists(self.path('out')))

    def test_format_names(self):
        "formats.md 9: --format names, comma-separated, case-insensitive, trimmed, repeatable"
        for option, names in [('--format bib', ['papers.bib']), ('--format BibTeX', ['papers.bib']),
                              ('--format json', ['papers.json']), ('--format bib.json', ['papers.bib.json']),
                              ('--format " CSL-JSON , bibjson"', ['papers.bib.json', 'papers.json']),
                              ('--format json --format csl-json', ['papers.json'])] + (
                [('--format all', ['papers.bib', 'papers.bib.json', 'papers.json', 'papers.ris'])] if HAS_RISPY else []):
            shutil.rmtree(self.path('out'), ignore_errors=True)
            self.lib(f'export ../out {option}')
            self.assertEqual(sorted(n for n in os.listdir(self.path('out')) if n.startswith('papers')), names, option)

    def test_new_library(self):
        "formats.md 9: DIR a self-contained library: config, .gitignore, bibtex name, templates, distinct"
        os.makedirs(self.path('lib2'))
        self.papers('init --bibtex refs.bib', cwd=self.path('lib2'))
        Path(self.path('lib2', 'refs.bib')).write_text(entry('one2000') + entry('two2000'))
        self.papers('config name.template "{key}"', cwd=self.path('lib2'))
        self.papers('config key.author-num 1', cwd=self.path('lib2'))
        pair = [[{'authortitle': 'one|title of one2000'}, {'authortitle': 'one|title of two2000'}]]
        Path(self.path('lib2', '.papers', 'distinct.json')).write_text(json.dumps({'distinct': pair}))
        self.papers('export ../out', cwd=self.path('lib2'))
        self.assertTrue(os.path.exists(self.path('out', 'refs.bib')))
        self.assertTrue(os.path.exists(self.path('out', '.papers', '.gitignore')))
        config = json.load(open(self.path('out', CONFIG_FILE_LOCAL)))
        self.assertEqual((config['bibtex'], config['filesdir'], config['pool']), ('refs.bib', 'files', 'none'))
        self.assertEqual((config['nameformat'], config['keyformat']), ({'template': '{key}'}, {'author_num': 1}))
        self.assertEqual(json.load(open(self.path('out', '.papers', 'distinct.json')))['distinct'], pair)
        self.assertRegex(config['id'], '^[0-9a-f]{32}$')
        self.assertNotEqual(config['id'], json.load(open(self.path('lib2', CONFIG_FILE_LOCAL))).get('id'))

    def test_files(self):
        "formats.md 9: --files copy (named by the template), link, none; paths relative to DIR"
        self.lib('export ../out --format bib,csl-json')
        [one, two] = json.load(open(self.path('out', 'papers.json')))
        [copy] = one['custom']['file']
        self.assertTrue(copy.startswith('files/'))
        self.assertTrue(os.path.samefile(self.path('out', copy), self.path('lib', 'files', 'one.pdf')) or
                        Path(self.path('out', copy)).read_text() == 'one.pdf')
        self.lib('export ../link --format bib,csl-json --files link')
        [one, two] = json.load(open(self.path('link', 'papers.json')))
        self.assertEqual(one['custom'], {'file': ['../lib/files/one.pdf']})
        self.assertIn('file = {:../lib/files/one.pdf:pdf}', Path(self.path('link', 'papers.bib')).read_text())
        self.lib('export ../none --format csl-json --files none')
        [one, two] = json.load(open(self.path('none', 'papers.json')))
        self.assertNotIn('custom', one)
