"""RIS, CSL-JSON and BibJSON: the mappings of papers.formats, the import of
sample exports (tests/formats), `papers export --format`, `papers list
--format`, `papers add FILE.ris|FILE.json|FILE.bib.json`, and what happens
when rispy is missing.

tests/formats/csl-data.json is the CSL-JSON schema of
https://github.com/citation-style-language/schema
(schemas/input/csl-data.json, commit 40b3ce0, 2022-03-21, MIT license).
tests/formats/bibjson.json has the two example records of the BibJSON page
(https://github.com/rufuspollock-okfn/bibjson, index.html).
"""
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from papers import formats
from papers.bib import Biblio
from papers.entries import parse_file, parse_string
from papers.formats import (csl_to_entry, entry_to_csl, entry_to_ris, format_bibtex_names, load_rispy,
                            loads_csl, parse_bibtex_names, read_file, ris_to_entry)
from papers.utils import PapersExit

from tests.common import FileTest

HERE = os.path.dirname(__file__)
FIXTURES = os.path.join(HERE, 'formats')
HAS_RISPY = importlib.util.find_spec('rispy') is not None
HAS_JSONSCHEMA = importlib.util.find_spec('jsonschema') is not None
needs_rispy = unittest.skipUnless(HAS_RISPY, 'rispy is not installed')

ESD_PDF = os.path.join(HERE, 'downloadedpapers', 'esd-4-11-2013.pdf')

SAMPLE = r"""@article{perrette_landerer2013,
 author = {Perrette, M. and Landerer, F. and Riva, R. and Frieler, K. and Meinshausen, M.},
 doi = {10.5194/esd-4-11-2013},
 journal = {Earth System Dynamics},
 number = {1},
 pages = {11--29},
 title = {A scaling approach to project regional sea level rise and its uncertainties},
 volume = {4},
 year = {2013},
 month = jan,
 keywords = {sea level, climate},
 abstract = {Sea level rise.},
 url = {https://esd.copernicus.org/articles/4/11/2013/},
 issn = {2190-4987}
}

@incollection{weiss2019,
 author = {Wei{\ss}, J{\"u}rgen and Ludwig van Beethoven and {World Health Organization}},
 editor = {de la Fontaine, Jean},
 title = {Coastal flooding},
 booktitle = {Climate Change and Coastal Zones},
 series = {Lecture Notes},
 publisher = {Springer},
 address = {Cham},
 edition = {2},
 isbn = {978-3-030-00000-0},
 pages = {101--125},
 year = {2019}
}

@inproceedings{smith2018,
 author = {Smith, Anna and Doe, John},
 title = {Ice sheet instabilities},
 booktitle = {Proceedings of the Glaciology Conference},
 pages = {45--52},
 year = {2018}
}

@phdthesis{smith2020,
 author = {Smith, Anna},
 title = {Ice sheets and sea level},
 school = {University of Potsdam},
 year = {2020}
}

@techreport{ipcc2023,
 author = {{IPCC}},
 title = {Climate Change 2023: Synthesis Report},
 institution = {IPCC},
 address = {Geneva},
 number = {AR6},
 year = {2023}
}

@book{muller2001,
 author = {M{\"u}ller, Jr, J{\"o}rg},
 title = {A book},
 publisher = {Springer},
 year = {2001}
}

@misc{data2021,
 author = {Doe, John},
 title = {A dataset},
 year = {2021},
 note = {version 2}
}
"""

# the fields compared after a round trip (the values as unicode)
MAIN = ['author', 'editor', 'title', 'journal', 'booktitle', 'year', 'month', 'volume', 'number', 'pages',
        'doi', 'url', 'isbn', 'issn', 'publisher', 'school', 'institution', 'address', 'abstract', 'keywords',
        'note', 'edition', 'series']

UNICODE = {
    'weiss2019': {'author': 'Weiß, Jürgen and van Beethoven, Ludwig and {World Health Organization}'},
    'muller2001': {'author': 'Müller, Jr, Jörg'},
    'ipcc2023': {'author': '{IPCC}'},
    'perrette_landerer2013': {'month': '1'},
}


def sample_entries():
    return parse_string(SAMPLE).entries


def fields(e):
    return {f.key: f.value for f in e.fields}


def links(e):
    "the paths of the file links of an entry, as written"
    return parse_file(e.fields_dict['file'].value) if 'file' in e.fields_dict else []


class TestNames(unittest.TestCase):

    def test_parse(self):
        self.assertEqual(parse_bibtex_names('Perrette, M. and Ludwig van Beethoven and {World Health Organization}'
                                            ' and M{\\"u}ller, Jr, J{\\"o}rg and de la Fontaine, Jean'), [
            {'family': 'Perrette', 'given': 'M.'},
            {'family': 'Beethoven', 'given': 'Ludwig', 'non-dropping-particle': 'van'},
            {'literal': 'World Health Organization'},
            {'family': 'Müller', 'given': 'Jörg', 'suffix': 'Jr'},
            {'family': 'Fontaine', 'given': 'Jean', 'non-dropping-particle': 'de la'},
        ])

    def test_one_word_and_braces(self):
        self.assertEqual(parse_bibtex_names('Plato and {Barnes and Noble}'),
                         [{'family': 'Plato'}, {'literal': 'Barnes and Noble'}])

    def test_format(self):
        self.assertEqual(format_bibtex_names([{'family': 'Beethoven', 'given': 'Ludwig',
                                               'non-dropping-particle': 'van'}, {'literal': 'IPCC'},
                                              {'family': 'Müller', 'given': 'Jörg', 'suffix': 'Jr'}]),
                         'van Beethoven, Ludwig and {IPCC} and Müller, Jr, Jörg')


class TestCSL(unittest.TestCase):

    def test_article(self):
        e = sample_entries()[0]
        item = entry_to_csl(e, ['files/a.pdf'])
        self.assertEqual(item['id'], 'perrette_landerer2013')
        self.assertEqual(item['type'], 'article-journal')
        self.assertEqual(item['container-title'], 'Earth System Dynamics')
        self.assertEqual(item['issue'], '1')
        self.assertEqual(item['page'], '11-29')
        self.assertEqual(item['DOI'], '10.5194/esd-4-11-2013')
        self.assertEqual(item['issued'], {'date-parts': [[2013, 1]]})
        self.assertEqual(item['author'][0], {'family': 'Perrette', 'given': 'M.'})
        self.assertEqual(item['custom'], {'file': ['files/a.pdf']})

    def test_types(self):
        types_ = {e.key: entry_to_csl(e)['type'] for e in sample_entries()}
        self.assertEqual(types_, {'perrette_landerer2013': 'article-journal', 'weiss2019': 'chapter',
                                  'smith2018': 'paper-conference', 'smith2020': 'thesis', 'ipcc2023': 'report',
                                  'muller2001': 'book', 'data2021': 'document'})

    def test_round_trip(self):
        for e in sample_entries():
            back = csl_to_entry(json.loads(json.dumps(entry_to_csl(e, ['files/x.pdf']))))
            self.assertEqual(back.key, e.key)
            self.assertEqual(back.entry_type, e.entry_type)
            self.assertEqual(links(back), ['files/x.pdf'])
            self._same_fields(e, back)

    def _same_fields(self, e, back, changes=()):
        expected = {k: v for k, v in fields(e).items() if k in MAIN}
        expected.update(UNICODE.get(e.key, {}))
        expected.update(dict(changes).get(e.key, {}))
        expected = {k: formats._latex_to_unicode(v) if k not in ('author', 'editor', 'pages') else v
                    for k, v in expected.items()}
        self.assertEqual({k: v for k, v in fields(back).items() if k in MAIN}, expected, e.key)

    def test_file_key(self):
        # a non-standard file key (a text separated by ; or a list) is read too
        e = csl_to_entry({'id': 'x', 'type': 'book', 'title': 'T', 'file': 'a.pdf;/abs/b.pdf'})
        self.assertEqual(links(e), ['a.pdf', '/abs/b.pdf'])
        e = csl_to_entry({'id': 'x', 'type': 'book', 'title': 'T', 'file': ['file:///abs/c%20d.pdf']})
        self.assertEqual(links(e), ['/abs/c d.pdf'])

    def test_key(self):
        self.assertEqual(csl_to_entry({'id': 'http://zotero.org/users/1/items/AB', 'type': 'book'}).key, '')
        self.assertEqual(csl_to_entry({'id': 'ITEM-1', 'type': 'book'}).key, '')
        self.assertEqual(csl_to_entry({'id': '12', 'citation-key': 'smith2000', 'type': 'book'}).key, 'smith2000')

    def test_zotero_export(self):
        entries = read_file(os.path.join(FIXTURES, 'zotero.json'), 'csl-json')
        self.assertEqual([e.entry_type for e in entries], ['article', 'incollection', 'techreport', 'phdthesis'])
        article, chapter, report, thesis = [fields(e) for e in entries]
        self.assertEqual(entries[0].key, '')  # a Zotero URI: the key template gives it a key
        self.assertEqual(article['journal'], 'Earth System Dynamics')
        self.assertEqual(article['pages'], '11--29')
        self.assertEqual((article['year'], article['month']), ('2013', '1'))
        self.assertEqual(article['urldate'], '2024-03-01')
        self.assertEqual(article['author'].split(' and ')[0], 'Perrette, M.')
        self.assertEqual(chapter['author'], 'Weiß, Jürgen and van Beethoven, Ludwig')
        self.assertEqual(chapter['editor'], 'de la Fontaine, Jean')
        self.assertEqual(chapter['booktitle'], 'Climate Change and Coastal Zones')
        self.assertEqual(chapter['series'], 'Lecture Notes in Earth System Sciences')
        self.assertEqual(report['author'], '{Intergovernmental Panel on Climate Change}')
        self.assertEqual(report['institution'], 'IPCC')
        self.assertEqual(report['keywords'], 'climate, assessment')
        self.assertEqual(thesis['school'], 'University of Potsdam')
        self.assertEqual(entries[3].key, 'smith2020thesis')
        self.assertEqual(thesis['year'], '2020')

    def test_not_csl(self):
        with self.assertRaisesRegex(ValueError, 'not a CSL-JSON file'):
            loads_csl('{"a": 1')
        with self.assertRaisesRegex(ValueError, 'list of items'):
            loads_csl('[1, 2]')

    @unittest.skipUnless(HAS_JSONSCHEMA, 'jsonschema is not installed')
    def test_schema(self):
        import jsonschema
        schema = json.load(open(os.path.join(FIXTURES, 'csl-data.json')))
        items = json.loads(formats.dumps_csl(sample_entries(), files=lambda e: ['files/a.pdf']))
        jsonschema.validate(items, schema)
        # the Zotero sample is valid, and so is its round trip
        zotero = json.load(open(os.path.join(FIXTURES, 'zotero.json')))
        jsonschema.validate(zotero, schema)
        entries = read_file(os.path.join(FIXTURES, 'zotero.json'), 'csl-json')
        for i, e in enumerate(entries):
            e.key = e.key or f'key{i}'
        jsonschema.validate(json.loads(formats.dumps_csl(entries)), schema)

    @unittest.skipUnless(shutil.which('pandoc'), 'pandoc is not installed')
    def test_same_as_pandoc(self):
        # the main fields as `pandoc -f bibtex -t csljson` writes them
        out = subprocess.run(['pandoc', '-f', 'bibtex', '-t', 'csljson'], input=SAMPLE, capture_output=True,
                             text=True, check=True).stdout
        theirs = {item['id']: item for item in json.loads(out)}
        ours = {item['id']: item for item in json.loads(formats.dumps_csl(sample_entries()))}
        self.assertEqual(sorted(theirs), sorted(ours))

        def names(item, field):
            return [n.get('family') or n.get('literal') for n in item.get(field, [])]

        for key, item in ours.items():
            other = theirs[key]
            for field in ['title', 'container-title', 'DOI', 'URL', 'page', 'volume', 'issue', 'publisher',
                          'publisher-place', 'ISBN', 'ISSN', 'edition', 'collection-title']:
                if field in other or field in item:  # pandoc changes English titles to sentence case
                    self.assertEqual(str(item.get(field)).lower(), str(other.get(field)).lower(), f'{key} {field}')
            self.assertEqual(item['issued']['date-parts'][0][0], other['issued']['date-parts'][0][0], key)
            for field in ['author', 'editor']:
                self.assertEqual(names(item, field), names(other, field), f'{key} {field}')
            if key not in ('data2021', 'smith2020', 'ipcc2023'):  # misc, thesis, report: other choices
                self.assertEqual(item['type'], other['type'], key)


class TestBibJSON(unittest.TestCase):

    def test_article(self):
        record = formats.entry_to_bibjson(sample_entries()[0], ['files/a.pdf'])
        self.assertEqual((record['type'], record['id']), ('article', 'perrette_landerer2013'))
        self.assertEqual(record['author'][0], {'name': 'Perrette, M.'})
        self.assertEqual(record['journal'], {'name': 'Earth System Dynamics'})
        self.assertEqual(record['file'], ['files/a.pdf'])
        collection = json.loads(formats.dumps_bibjson(sample_entries()))
        self.assertEqual(collection['metadata'], {'records': 7})
        self.assertEqual(len(collection['records']), 7)

    def test_round_trip(self):
        # nothing is lost: the fields as they are, LaTeX included
        entries = sample_entries()
        back = formats.loads_bibjson(formats.dumps_bibjson(entries, files=lambda e: ['files/x.pdf']))
        for e, b in zip(entries, back):
            self.assertEqual((b.key, b.entry_type), (e.key, e.entry_type))
            self.assertEqual(links(b), ['files/x.pdf'])
            self.assertEqual({k: v for k, v in fields(b).items() if k != 'file'},
                             {k: v for k, v in fields(e).items() if k != 'file'}, e.key)

    def test_spec_examples(self):
        first, second = read_file(os.path.join(FIXTURES, 'bibjson.json'), 'bibjson')
        self.assertEqual(first.key, '')  # no id: papers makes one
        self.assertEqual(fields(first)['author'].split(' and ')[:2], ['Richard Jones', 'Mark MacGillivray'])
        self.assertEqual(fields(first)['journal'], 'Journal of Cheminformatics')
        self.assertEqual(fields(first)['doi'], '10.1186/1758-2946-3-47')  # from the identifiers
        self.assertNotIn('link', fields(first))
        self.assertEqual(second.key, 'ID_1')
        self.assertEqual(fields(second)['author'], 'Erdös, Paul')
        self.assertEqual(fields(second)['journal'], 'American Journal of Mathematics')
        self.assertNotIn('collection', fields(second))

    def test_one_record_or_list(self):
        record = {'type': 'book', 'id': 'b2000', 'title': 'T', 'keywords': ['a', 'b'], 'file': 'b.pdf'}
        for text in (json.dumps(record), json.dumps([record])):
            [e] = formats.loads_bibjson(text)
            self.assertEqual((e.key, e.entry_type, fields(e)['keywords']), ('b2000', 'book', 'a, b'))
            self.assertEqual(links(e), ['b.pdf'])

    def test_not_bibjson(self):
        self.assertRaises(ValueError, formats.loads_bibjson, 'not json')
        self.assertRaises(ValueError, formats.loads_bibjson, '"a string"')

    def test_file_format(self):
        self.assertEqual(formats.file_format('a/papers.bib.json'), 'bibjson')
        self.assertEqual(formats.file_format('a/papers.JSON'), 'csl-json')
        self.assertEqual(formats.file_format('a/papers.ris'), 'ris')
        self.assertEqual(formats.file_format('a/refs.txt'), 'bibtex')
        self.assertEqual(formats.file_format('a/refs.txt', 'bibjson'), 'bibjson')


@needs_rispy
class TestRIS(unittest.TestCase):

    def test_article(self):
        ref = entry_to_ris(sample_entries()[0], ['files/a.pdf'])
        self.assertEqual(ref['type_of_reference'], 'JOUR')
        self.assertEqual(ref['authors'][0], 'Perrette, M.')
        self.assertEqual(ref['secondary_title'], 'Earth System Dynamics')
        self.assertEqual((ref['start_page'], ref['end_page']), ('11', '29'))
        self.assertEqual(ref['file_attachments1'], ['files/a.pdf'])
        text = formats.dumps_ris(sample_entries()[:1], files=lambda e: ['files/a.pdf'])
        self.assertTrue(text.startswith('TY  - JOUR\n'))  # no record number line
        for line in ['ID  - perrette_landerer2013', 'T2  - Earth System Dynamics', 'PY  - 2013',
                     'DA  - 2013/01/', 'SP  - 11', 'EP  - 29', 'DO  - 10.5194/esd-4-11-2013',
                     'KW  - sea level', 'KW  - climate', 'L1  - files/a.pdf', 'ER  - ']:
            self.assertIn(line + '\n', text)

    def test_round_trip(self):
        entries = sample_entries()
        text = formats.dumps_ris(entries, files=lambda e: ['files/x.pdf', 'files/y.pdf'])
        back = formats.loads_ris(text)
        self.assertEqual(len(back), len(entries))
        for e, b in zip(entries, back):
            self.assertEqual(b.key, e.key)
            self.assertEqual(b.entry_type, {'misc': 'misc'}.get(e.entry_type, e.entry_type), e.key)
            self.assertEqual(links(b), ['files/x.pdf', 'files/y.pdf'])
            # a one-word name has no braces in RIS
            TestCSL._same_fields(self, e, b, changes={'ipcc2023': {'author': 'IPCC'}})

    def test_endnote_export(self):
        # UTF-8 with a byte order mark, CRLF line ends, record numbers as ID, A2 editors
        with self.assertLogs('papers', 'WARNING') as logs:
            entries = read_file(os.path.join(FIXTURES, 'endnote.ris'), 'ris')
        self.assertIn('internal-pdf://', logs.output[0])  # an EndNote link, not a file
        self.assertEqual([e.entry_type for e in entries], ['article', 'incollection', 'techreport'])
        self.assertEqual([e.key for e in entries], ['', '', ''])
        article, chapter, report = [fields(e) for e in entries]
        self.assertEqual(article['title'], 'A scaling approach to project regional sea level rise and its '
                                           'uncertainties')
        self.assertEqual(article['journal'], 'Earth System Dynamics')
        self.assertEqual((article['year'], article['month']), ('2013', '1'))
        self.assertEqual(article['abstract'], 'Sea level rise is a major hazard for coastal areas.')
        self.assertEqual(article['keywords'], 'sea level, climate projections')
        self.assertEqual(article['doi'], '10.5194/esd-4-11-2013')
        self.assertNotIn('url', article)  # the DOI link
        self.assertNotIn('file', article)
        self.assertEqual(chapter['editor'], 'de la Fontaine, Jean')
        self.assertEqual(chapter['author'], 'Weiß, Jürgen and van Beethoven, Ludwig')
        self.assertEqual(chapter['isbn'], '978-3-030-00000-0')
        self.assertEqual(chapter['series'], 'Lecture Notes in Earth System Sciences')
        self.assertEqual(report['author'], '{Intergovernmental Panel on Climate Change}')
        self.assertEqual(report['keywords'], 'climate, assessment')
        self.assertEqual(report['type'], 'Synthesis Report')

    def test_wos_export(self):
        entries = read_file(os.path.join(FIXTURES, 'wos.ris'), 'ris')
        self.assertEqual([e.entry_type for e in entries], ['inproceedings', 'article'])
        conf, article = [fields(e) for e in entries]
        self.assertEqual(conf['booktitle'], 'PROCEEDINGS OF THE INTERNATIONAL GLACIOLOGY CONFERENCE')
        self.assertEqual(conf['year'], '2018')
        self.assertEqual(conf['issn'], '1234-5678')
        self.assertEqual(article['author'].split(' and ')[0], 'Perrette, M')
        self.assertEqual(article['pages'], '11--29')

    def test_file_links(self):
        e = ris_to_entry({'type_of_reference': 'JOUR', 'title': 'T',
                          'file_attachments1': ['files/a.pdf', 'file:///abs/b.pdf']})
        self.assertEqual(links(e), ['files/a.pdf', '/abs/b.pdf'])

    def test_blank_line_after_ty(self):
        # rispy reads a blank line (or a line without tag) after TY as the continuation of the last tag
        # (an error when the last tag of the previous record holds one value, e.g. TI)
        text = ('TY  - JOUR\nKW  - a\nTI  - First\nER  - \n\n'
                'TY  - JOUR\n\nTI  - Second\nKW  - b\n\nAU  - Smith, J\nER  - \n\n'
                'TY  - JOUR\nstray text\nTI  - Third\nER  - \n')
        first, second, third = formats.loads_ris(text)
        self.assertEqual((first['title'], second['title'], third['title']), ('First', 'Second', 'Third'))
        self.assertEqual(second['keywords'], 'b')
        self.assertEqual(second['author'], 'Smith, J')

    def test_not_ris(self):
        with self.assertRaisesRegex(ValueError, 'not a RIS file'):
            formats.loads_ris('@article{x, title={T}}')


class TestRispyMissing(unittest.TestCase):
    "load_rispy when rispy is not installed (the import fails; pip is mocked, nothing is installed)"

    def setUp(self):
        patcher = patch.dict(sys.modules, {'rispy': None})  # `import rispy` raises ImportError
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_no_terminal(self):
        with patch('subprocess.run') as run:
            with self.assertRaisesRegex(PapersExit, r'RIS needs the rispy package.*`pip install rispy`.*'
                                                    r'`pipx inject papers-cli rispy`.*papers-cli\[ris\]'):
                load_rispy(interactive=False)
        run.assert_not_called()

    def test_terminal_no(self):
        with patch('subprocess.run') as run, redirect_stderr(io.StringIO()) as err:
            with self.assertRaisesRegex(PapersExit, 'rispy not installed'):
                load_rispy(interactive=True, input=lambda prompt: 'n')
        run.assert_not_called()
        self.assertIn(f'install it now (`{sys.executable} -m pip install rispy`)? [y/N]', err.getvalue())

    def test_terminal_yes(self):
        fake = types.ModuleType('rispy')

        def pip(command, **kw):
            self.assertEqual(command, [sys.executable, '-m', 'pip', 'install', 'rispy'])
            sys.modules['rispy'] = fake  # as if installed
            return subprocess.CompletedProcess(command, 0)

        with patch('subprocess.run', side_effect=pip) as run, redirect_stderr(io.StringIO()):
            self.assertIs(load_rispy(interactive=True, input=lambda prompt: 'y'), fake)
        run.assert_called_once()

    def test_pip_fails(self):
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 1)), \
                redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(PapersExit, 'failed: install it with'):
                load_rispy(interactive=True, input=lambda prompt: 'y')

    def test_no_pip(self):
        real = importlib.util.find_spec
        with patch('importlib.util.find_spec', side_effect=lambda name, *a: None if name == 'pip'
                   else real(name, *a)):
            with self.assertRaisesRegex(PapersExit, 'pip is not available.*uv tool install papers-cli --with rispy'):
                load_rispy(interactive=True, input=lambda prompt: 'y')


class LibraryCommands(FileTest):
    "a library lib/ with the sample entries, and a copy of a PDF linked to the first one"

    def setUp(self):
        super().setUp()
        pdf = self.path('lib', 'files', 'perrette2013.pdf')
        shutil.copy(ESD_PDF, pdf)
        text = SAMPLE.replace(' issn = {2190-4987}\n', ' issn = {2190-4987},\n file = {:files/perrette2013.pdf:pdf}\n')
        Path(self.path('lib', 'papers.bib')).write_text(text)
        self.pdf = pdf

    def entries(self, *p):
        biblio = Biblio.load(self.path(*p), '')
        return biblio, {e.key: e for e in biblio.entries}


class TestExportFormats(LibraryCommands):

    def test_default_bib(self):
        out = self.out('export ../out')
        self.assertIn('(papers.bib; files: copy)', out)
        self.assertEqual(sorted(os.listdir(self.path('out'))), ['.papers', 'files', 'papers.bib'])

    @needs_rispy
    def test_all(self):
        out = self.out('export ../out --format all')
        self.assertIn('(papers.bib, papers.ris, papers.json, papers.bib.json; files: copy)', out)
        self.assertNotIn('not a papers library', out)
        biblio, entries = self.entries('out', 'papers.bib')
        self.assertEqual(len(entries), 7)
        copy = biblio.get_files(entries['perrette_landerer2013'])[0]
        self.assertTrue(copy.startswith(self.path('out', 'files')))
        rel = os.path.relpath(copy, self.path('out'))
        # the links of each format: the copy, relative to out/
        items = {i['id']: i for i in json.load(open(self.path('out', 'papers.json')))}
        self.assertEqual(items['perrette_landerer2013']['custom'], {'file': [rel]})
        self.assertIn(f'L1  - {rel}\n', Path(self.path('out', 'papers.ris')).read_text())
        self.assertEqual(len(read_file(self.path('out', 'papers.ris'), 'ris')), 7)

    def test_csl_only(self):
        out = self.out('export ../out perrette_landerer2013 --format csl-json')
        self.assertIn('exported 1 entries', out)
        self.assertIn('(papers.json; files: copy)', out)
        self.assertIn('is not a papers library (no papers.bib)', out)
        self.assertEqual(sorted(os.listdir(self.path('out'))), ['files', 'papers.json'])
        items = json.load(open(self.path('out', 'papers.json')))
        [file] = items[0]['custom']['file']
        self.assertTrue(file.startswith('files/'))
        self.assertTrue(os.path.samefile(self.path('out', file), self.pdf))

    @needs_rispy
    def test_repeated_and_comma(self):
        self.lib('export ../out --format ris --format csl-json,ris')
        self.assertEqual(sorted(os.listdir(self.path('out'))), ['files', 'papers.json', 'papers.ris'])

    def test_bibjson(self):
        self.lib('export ../out --format bib.json')
        self.assertEqual(sorted(os.listdir(self.path('out'))), ['files', 'papers.bib.json'])
        records = json.load(open(self.path('out', 'papers.bib.json')))['records']
        record = next(r for r in records if r['id'] == 'perrette_landerer2013')
        [file] = record['file']
        self.assertTrue(file.startswith('files/'))
        self.assertTrue(os.path.samefile(self.path('out', file), self.pdf))

    def test_files_none(self):
        self.lib('export ../out --format csl-json --files none')
        items = json.load(open(self.path('out', 'papers.json')))
        self.assertNotIn('custom', items[0])

    def test_unknown_format(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            self.lib('export ../out --format endnote')


class TestListFormats(LibraryCommands):

    def test_csl_json(self):
        items = json.loads(self.out('list perrette --format csl-json'))
        self.assertEqual([i['id'] for i in items], ['perrette_landerer2013'])
        self.assertEqual(items[0]['custom'], {'file': [self.pdf]})  # absolute paths

    def test_bibjson(self):
        records = json.loads(self.out('list perrette --format bibjson'))['records']
        self.assertEqual([r['id'] for r in records], ['perrette_landerer2013'])
        self.assertEqual(records[0]['file'], [self.pdf])  # absolute paths

    @needs_rispy
    def test_ris(self):
        out = self.out('list --format ris')
        self.assertEqual(out.count('TY  - '), 7)
        self.assertIn(f'L1  - {self.pdf}\n', out)


class TestAddFormats(LibraryCommands):

    def keys(self):
        return sorted(self.entries('lib', 'papers.bib')[1])

    def test_add_json_duplicates(self):
        before = self.keys()
        out = self.out('add ../zotero.json --on-duplicate keep --no-pool'.replace(
            '../zotero.json', os.path.join(FIXTURES, 'zotero.json')))
        self.assertIn('perrette_landerer2013', out)
        _, entries = self.entries('lib', 'papers.bib')
        # the article is a duplicate: merged, it keeps its key and gets the fields it lacked
        self.assertEqual(entries['perrette_landerer2013'].fields_dict['language'].value, 'en')
        # the thesis is smith2020 (same authors and title), the others are new, with a key from the key template
        new = sorted(set(entries) - set(before))
        self.assertEqual(new, ['change2023', 'weiss_van-beethoven2019'])

    def test_add_json_skip(self):
        self.lib(f'add {os.path.join(FIXTURES, "zotero.json")} --on-duplicate skip --no-pool')
        _, entries = self.entries('lib', 'papers.bib')
        self.assertNotIn('language', entries['perrette_landerer2013'].fields_dict)

    def test_duplicate_error_without_terminal(self):
        before = Path(self.path('lib', 'papers.bib')).read_text()
        Path(self.path('dup.json')).write_text(json.dumps([{
            'id': 'x', 'type': 'article-journal', 'DOI': '10.5194/esd-4-11-2013', 'title': 'Other title',
            'author': [{'family': 'Perrette', 'given': 'M.'}], 'issued': {'date-parts': [[2013]]}}]))
        with self.assertRaises(Exception):
            self.lib('add ../dup.json --no-pool')
        self.assertEqual(Path(self.path('lib', 'papers.bib')).read_text(), before)

    @needs_rispy
    def test_add_ris_with_file(self):
        # a RIS file next to its PDF (as a Zotero export with files): the link is relative to the RIS file
        os.makedirs(self.path('zotero', 'files', '12'))
        shutil.copy(ESD_PDF, self.path('zotero', 'files', '12', 'paper.pdf'))
        Path(self.path('zotero', 'refs.ris')).write_text(
            'TY  - JOUR\nAU  - Doe, Jane\nTI  - A new paper\nT2  - Some Journal\nPY  - 2024\n'
            'DO  - 10.1234/new.2024\nL1  - files/12/paper.pdf\nER  - \n')
        self.lib('add ../zotero/refs.ris --no-pool')
        biblio, entries = self.entries('lib', 'papers.bib')
        [key] = set(entries) - {e.key for e in sample_entries()}
        self.assertEqual(entries[key].fields_dict['journal'].value, 'Some Journal')
        self.assertEqual(biblio.get_files(entries[key]), [self.path('zotero', 'files', '12', 'paper.pdf')])

    @needs_rispy
    def test_add_ris_duplicates(self):
        self.lib(f'add {os.path.join(FIXTURES, "endnote.ris")} --on-duplicate keep --no-pool')
        _, entries = self.entries('lib', 'papers.bib')
        self.assertEqual(len(entries), 7 + 2)  # the article and the chapter are in the library (DOI, authors+title)

    @needs_rispy
    def test_format_option(self):
        Path(self.path('refs.txt')).write_text('TY  - BOOK\nAU  - Doe, Jane\nTI  - A forced book\nPY  - 2024\nER  - \n')
        self.lib('add ../refs.txt --format ris --no-pool')
        _, entries = self.entries('lib', 'papers.bib')
        self.assertIn('A forced book', [e.fields_dict['title'].value for e in entries.values()])

    def test_add_bibjson(self):
        record = {'type': 'book', 'id': 'doe2024', 'author': [{'name': 'Doe, Jane'}], 'title': 'A BibJSON book',
                  'year': '2024'}
        Path(self.path('refs.bib.json')).write_text(json.dumps({'records': [record]}))
        self.lib('add ../refs.bib.json --no-pool')
        _, entries = self.entries('lib', 'papers.bib')
        self.assertEqual(entries['doe2024'].fields_dict['title'].value, 'A BibJSON book')

    def test_bibtex_by_default(self):
        # a file of another extension is bibtex, as before
        Path(self.path('refs.txt')).write_text('@book{doe2024, author={Doe, Jane}, title={A book}, year={2024}}')
        self.lib('add ../refs.txt --no-pool')
        self.assertIn('doe2024', self.keys())

    def test_metadata_one_entry_only(self):
        with self.assertRaisesRegex(PapersExit, 'the CSL-JSON file has 4 entries'):
            self.lib(f'add {os.path.join(FIXTURES, "zotero.json")} --title X --no-pool')


class TestRispyMissingCommands(LibraryCommands):
    "add of a RIS file, export --format ris and list --format ris stop before any change without rispy"

    def setUp(self):
        super().setUp()
        patcher = patch.dict(sys.modules, {'rispy': None})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_commands_change_nothing(self):
        Path(self.path('refs.ris')).write_text('TY  - JOUR\nTI  - T\nER  - \n')
        before = Path(self.path('lib', 'papers.bib')).read_text()
        with self.assertRaisesRegex(PapersExit, 'RIS needs the rispy package'):
            self.lib('add ../refs.ris')
        self.assertEqual(Path(self.path('lib', 'papers.bib')).read_text(), before)
        with self.assertRaisesRegex(PapersExit, 'RIS needs the rispy package'):
            self.lib('export ../out --format ris')
        self.assertFalse(os.path.exists(self.path('out')))
        with self.assertRaisesRegex(PapersExit, 'RIS needs the rispy package'):
            self.lib('list --format ris')
