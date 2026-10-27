"""The fields of an entry cannot place its files outside the files directory"""
import os
import tempfile
import unittest
from pathlib import Path

from papers.bib import Biblio
from papers.filename import Format, make_template_fields, path_safe
from tests.common import paperscmd

TRAVERSALS = ['../../escaped/x', '/../../../escaped/x', '..', '/etc/x', '..\\..\\escaped\\x']


class TestPathSafe(unittest.TestCase):

    def test_separators(self):
        self.assertEqual(path_safe('a/b\\c\0d'), 'a-b-c-d')
        self.assertEqual(path_safe('..'), '--')
        self.assertEqual(path_safe('.'), '-')
        self.assertEqual(path_safe('2013'), '2013')
        self.assertEqual(path_safe(2013), '2013')
        self.assertIsNone(path_safe(None))

    def test_fields(self):
        for value in TRAVERSALS:
            fields = make_template_fields({'author': 'Doe, John', 'title': 'A title', 'year': value,
                                           'journal': value, 'ID': value, 'doi': value})
            for name in ('year', 'journal', 'ID', 'doi'):
                self.assertNotIn('/', fields[name])
                self.assertNotIn('\\', fields[name])
                self.assertNotEqual(fields[name].strip('.'), '')


class TestRename(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir = self.temp_dir.name
        self.filesdir = os.path.join(self.dir, 'lib', 'files')

    def tearDown(self):
        self.temp_dir.cleanup()

    def outside(self):
        "files written outside the files directory, other than the source"
        found = []
        for root, dirs, files in os.walk(self.dir):
            for f in files:
                path = os.path.join(root, f)
                if not path.startswith(self.filesdir + os.sep) and f != 'source.pdf':
                    found.append(path)
        return found

    def rename(self, fields, nameformat=None):
        source = os.path.join(self.dir, 'source.pdf')
        Path(source).write_text('payload')
        kw = {'nameformat': nameformat} if nameformat else {}
        biblio = Biblio(filesdir=self.filesdir, **kw)
        entry = {'ENTRYTYPE': 'article', 'ID': 'x', 'author': 'Doe, John', 'title': 'A title'}
        entry.update(fields)
        biblio.add_bibtex('@article{x,\n' + ''.join(f' {k} = {{{v}}},\n' for k, v in entry.items()
                                                       if k not in ('ENTRYTYPE', 'ID')) + '}')
        e = biblio.entries[0]
        biblio.set_files(e, [source])
        biblio.rename_entry_files(e)
        return biblio.get_files(e)

    def test_fields_stay_inside(self):
        for value in TRAVERSALS:
            for field in ('year', 'journal', 'doi'):
                template = '{authorX}_{' + field + '}_{title}'
                files = self.rename({field: value}, Format(template))
                self.assertEqual(self.outside(), [], (field, value))
                self.assertTrue(files[0].startswith(self.filesdir + os.sep), (field, value))

    def test_template_outside_is_refused(self):
        for template in ('../{author}', '/tmp/{author}', '{author}/../../x', '.'):
            files = self.rename({'year': '2020'}, Format(template))
            self.assertEqual(files, [os.path.join(self.dir, 'source.pdf')], template)
            self.assertEqual(self.outside(), [], template)

    def test_subfolders_still_work(self):
        files = self.rename({'year': '2020'}, Format('{year}/{author}'))
        self.assertEqual(files, [os.path.join(self.filesdir, '2020', 'doe.pdf')])


class TestAddBibtex(unittest.TestCase):
    "papers add of a .bib with a crafted year, as in the advisory"

    def test_add(self):
        with tempfile.TemporaryDirectory() as dir:
            os.makedirs(os.path.join(dir, 'evil'))
            Path(dir, 'evil', 'payload.pdf').write_text('payload')
            Path(dir, 'evil', 'evil.bib').write_text(
                '@article{x,\n author = {Doe, John},\n year = {/../../../escaped/x},\n'
                ' title = {Some title},\n file = {payload.pdf},\n}\n')
            bib = os.path.join(dir, 'lib', 'papers.bib')
            filesdir = os.path.join(dir, 'lib', 'files')
            os.makedirs(os.path.dirname(bib))
            Path(bib).write_text('')
            paperscmd(f'add {dir}/evil/evil.bib --bibtex {bib} --filesdir {filesdir} --rename')
            self.assertFalse(os.path.exists(os.path.join(dir, 'escaped')))
            pdfs = [os.path.join(r, f) for r, _, fs in os.walk(dir) for f in fs if f.endswith('.pdf')]
            self.assertEqual(len(pdfs), 1)
            self.assertTrue(pdfs[0].startswith(filesdir + os.sep), pdfs)
