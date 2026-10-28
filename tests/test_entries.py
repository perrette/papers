"""Unit tests for papers.entries: the file field"""
import os
import tempfile
import unittest

from papers.entries import parse_file, format_file, update_file_path


class TestBibtexFileEntry(unittest.TestCase):

    def test_parse_file(self):
        file = parse_file('file.pdf:/path/to/file.pdf:pdf')
        self.assertEqual(file, ['/path/to/file.pdf'])
        file = parse_file(':/path/to/file.pdf:pdf')
        self.assertEqual(file, ['/path/to/file.pdf'])
        file = parse_file('/path/to/file.pdf:pdf')
        self.assertEqual(file, ['/path/to/file.pdf'])
        file = parse_file('/path/to/file.pdf')
        self.assertEqual(file, ['/path/to/file.pdf'])
        file = parse_file(':/path/to/file.pdf:')
        self.assertEqual(file, ['/path/to/file.pdf'])


    def test_parse_files(self):
        files = parse_file(':/path/to/file1.pdf:pdf;:/path/to/file2.pdf:pdf')
        self.assertEqual(files, ['/path/to/file1.pdf','/path/to/file2.pdf'])

    def test_parse_file_colon_in_path(self):
        # issue #95: the path itself may contain colons (e.g. journal names)
        file = parse_file(':/path/to/American Economic Journal: Applied Economics.pdf:pdf')
        self.assertEqual(file, ['/path/to/American Economic Journal: Applied Economics.pdf'])
        file = parse_file('desc:/path/with:colon.pdf:pdf')
        self.assertEqual(file, ['/path/with:colon.pdf'])

    def test_parse_file_empty_path_ignored(self):
        # issue #91: an empty path used to resolve to the library directory itself
        self.assertEqual(parse_file('::pdf', relative_to='/some/dir'), [])
        self.assertEqual(parse_file(':/path/to/file.pdf:pdf;', relative_to=None), ['/path/to/file.pdf'])


    def test_format_file(self):
        field = format_file(['/path/to/file.pdf'])
        self.assertEqual(field, ':/path/to/file.pdf:pdf')


    def test_format_files(self):
        field = format_file(['/path/to/file1.pdf','/path/to/file2.pdf'])
        self.assertEqual(field, ':/path/to/file1.pdf:pdf;:/path/to/file2.pdf:pdf')

    def test_format_file_relative_to_root(self):
        """format_file with relative_to=os.sep uses abspath"""
        paths = [os.path.abspath('/tmp/file.pdf')]
        result = format_file(paths, relative_to=os.path.sep)
        self.assertIn('file.pdf', result)


class TestUpdateFilePath(unittest.TestCase):

    def test_update_file_path_changes_path(self):
        with tempfile.TemporaryDirectory() as base:
            sub1 = os.path.join(base, "dir1")
            sub2 = os.path.join(base, "dir2")
            os.makedirs(sub1)
            os.makedirs(sub2)
            pdf_path = os.path.join(sub1, "file.pdf")
            open(pdf_path, "wb").close()
            entry = {"ID": "test", "file": f":{pdf_path}:pdf"}
            result = update_file_path(entry, from_relative_to=sub1, to_relative_to=sub2)
            self.assertIsNotNone(result)
            old_file, new_file = result
            self.assertIn("file.pdf", new_file)

    def test_update_file_path_check_exists(self):
        with tempfile.TemporaryDirectory() as base:
            sub = os.path.join(base, "dir")
            os.makedirs(sub)
            pdf_path = os.path.join(sub, "file.pdf")
            open(pdf_path, "wb").close()
            entry = {"ID": "test", "file": f":{pdf_path}:pdf"}
            update_file_path(entry, from_relative_to=base, to_relative_to=base, check=True)
            self.assertIn("file", entry)


class TestGetEntryVal(unittest.TestCase):

    def test_values(self):
        from bibtexparser.model import Entry, Field
        from papers.entries import get_entry_val
        e = Entry('article', 'Key', [Field('title', 'first'), Field('doi', '10.1/x'), Field('title', 'second')])
        self.assertEqual(get_entry_val(e, 'ID'), 'Key')
        self.assertEqual(get_entry_val(e, 'ENTRYTYPE'), 'article')
        self.assertEqual(get_entry_val(e, 'title'), e.fields_dict['title'].value)  # the last one
        self.assertEqual(get_entry_val(e, 'title'), 'second')
        self.assertEqual(get_entry_val(e, 'year', 'none'), 'none')
        self.assertEqual(get_entry_val({'title': 'T'}, 'title'), 'T')
        self.assertEqual(get_entry_val({}, 'title', None), None)


def test_standard_name_braces():
    from papers.encoding import standard_name
    assert standard_name('John {van der Berg}') == '{van der Berg}, John'
    assert standard_name('{World Health Organization}') == '{World Health Organization}'
    assert standard_name('John Smith and\n  Jane Doe') == 'Smith, John and Doe, Jane'
    assert standard_name('Smith, John and {Barnes and Noble}') == 'Smith, John and {Barnes and Noble}'
    assert standard_name('Jean-Paul de la Fontaine') == 'Fontaine, Jean-Paul de la'


def test_tags_without_case():
    # Climate and climate are one tag, as --tag finds them: add, remove and rename agree
    from papers.cli.entry_cmds import add_tags, remove_tags, rename_tag
    from papers.encoding import parse_keywords
    from papers.entries import parse_string
    e, = parse_string('@article{a, keywords = {climate, Ice}}').entries
    add_tags([e], ['Climate', 'ocean', 'OCEAN'])
    assert parse_keywords(e) == ['climate', 'Ice', 'ocean']
    remove_tags([e], ['ice'])
    assert parse_keywords(e) == ['climate', 'ocean']
    assert rename_tag([e], 'CLIMATE', 'Climate') == 1  # a rename can change the case
    assert parse_keywords(e) == ['Climate', 'ocean']
    add_tags([e], ['Climate/amoc'])
    assert rename_tag([e], 'climate', 'sea') == 1
    assert parse_keywords(e) == ['sea', 'ocean', 'sea/amoc']
