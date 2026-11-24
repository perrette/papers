"""File moves and configuration paths (no network: dummy files, bibtex input)"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from papers.bib import Biblio
from papers.files import group_attachments
from papers.config import Config, CONFIG_FILE_LOCAL
from papers.utils import move
from tests.common import paperscmd, BibTest


ENTRY = """@article{smith2020,
 author = {Smith, John},
 title = {A test},
 year = {2020},
 file = {:a.pdf:pdf}
}
"""


class TestMoveSameFile(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir = self.temp_dir.name
        self.file = os.path.join(self.dir, 'a.pdf')
        Path(self.file).write_text('a')

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_relative_vs_absolute(self):
        cwd = os.getcwd()
        os.chdir(self.dir)
        try:
            move(self.file, 'a.pdf', interactive=False)
        finally:
            os.chdir(cwd)
        self.assertTrue(os.path.exists(self.file))

    def test_symlinked_directory(self):
        link = os.path.join(self.dir, 'link')
        os.symlink(self.dir, link)
        move(self.file, os.path.join(link, 'a.pdf'), interactive=False)
        self.assertTrue(os.path.exists(self.file))

    def test_hardlink_is_moved(self):
        other = os.path.join(self.dir, 'b.pdf')
        os.link(self.file, other)
        move(self.file, other, interactive=False)
        self.assertFalse(os.path.exists(self.file))
        self.assertEqual(Path(other).read_text(), 'a')


class TestRenameInPlace(BibTest):
    """rename files already at their place, with a relative --filesdir"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir = self.temp_dir.name
        Path(self.dir, 'a.pdf').write_text('a')
        Path(self.dir, 'b.pdf').write_text('b')
        Path(self.dir, 'in.bib').write_text(ENTRY)
        Path(self.dir, 'lib.bib').write_text('')
        self.opts = '--bibtex lib.bib --filesdir files --relative-paths'

    def tearDown(self):
        self.temp_dir.cleanup()

    def papers(self, cmd):
        return paperscmd(f'{cmd} {self.opts}', cwd=self.dir)

    def files(self):
        biblio = Biblio.load(os.path.join(self.dir, 'lib.bib'), None)
        return biblio.get_files(biblio.entries[0])

    def assertFilesExist(self, n):
        files = self.files()
        self.assertEqual(len(files), n)
        for f in files:
            self.assertTrue(os.path.exists(f), f)

    def test_single_file(self):
        self.papers('add in.bib --rename')
        self.assertFilesExist(1)
        self.papers('filecheck --rename')
        self.assertFilesExist(1)
        self.papers('list --rename')
        self.assertFilesExist(1)

    def test_several_files(self):
        self.papers('add in.bib --rename')
        self.papers('list --add-files b.pdf --rename')
        self.assertFilesExist(2)
        self.papers('filecheck --rename')
        self.assertFilesExist(2)
        self.papers('list --rename')
        self.assertFilesExist(2)


SHARED = """@article{smith2020,
 author = {Smith, John},
 title = {A test},
 year = {2020},
 file = {:files/shared.pdf:pdf}
}

@article{jones2021,
 author = {Jones, Jane},
 title = {Another test},
 year = {2021},
 file = {:files/shared.pdf:pdf}
}
"""


class TestRenameSharedFile(BibTest):
    """regression: two entries link to one file (see free_name); renaming
    the files of one of them moved the file and broke the other's link: it
    is copied (a hard link when possible), not moved"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir = self.temp_dir.name
        os.makedirs(os.path.join(self.dir, 'files'))
        self.shared = os.path.join(self.dir, 'files', 'shared.pdf')
        Path(self.shared).write_text('shared')
        Path(self.dir, 'lib.bib').write_text(SHARED)
        self.opts = '--bibtex lib.bib --filesdir files --relative-paths'

    def tearDown(self):
        self.temp_dir.cleanup()

    def files(self):
        biblio = Biblio.load(os.path.join(self.dir, 'lib.bib'), None)
        return {e['ID']: biblio.get_files(e) for e in biblio.entries}

    def test_rename_one(self):
        out = paperscmd(f'file rename smith2020 --move {self.opts}', cwd=self.dir, sp_cmd='check_output')
        files = self.files()
        smith = os.path.join(self.dir, 'files', 'smith_2020_a-test.pdf')
        self.assertEqual(files['smith2020'], [smith])
        self.assertEqual(files['jones2021'], [self.shared])
        self.assertTrue(os.path.exists(self.shared))
        self.assertEqual(Path(smith).read_text(), 'shared')
        self.assertIn('copied', out)

    def test_rename_all(self):
        # the first entry gets a copy; the last one, which alone links to the file then, moves it
        paperscmd(f'file rename --move {self.opts}', cwd=self.dir)
        files = self.files()
        for key, name in [('smith2020', 'smith_2020_a-test.pdf'), ('jones2021', 'jones_2021_another-test.pdf')]:
            self.assertEqual(files[key], [os.path.join(self.dir, 'files', name)])
            self.assertTrue(os.path.exists(files[key][0]))
        self.assertFalse(os.path.exists(self.shared))

    def test_attach_file_of_another_entry(self):
        # file attach of a file that another entry links to: copied too
        Path(self.dir, 'lib.bib').write_text(SHARED.rsplit(' file = ', 1)[0] + '}\n')  # jones2021: no file
        self.assertEqual(self.files()['jones2021'], [])
        out = paperscmd(f'file attach jones2021 files/shared.pdf --move {self.opts}', cwd=self.dir,
                        sp_cmd='check_output')
        files = self.files()
        jones = os.path.join(self.dir, 'files', 'jones_2021_another-test.pdf')
        self.assertEqual(files['jones2021'], [jones])
        self.assertEqual(files['smith2020'], [self.shared])
        self.assertTrue(os.path.exists(self.shared))
        self.assertTrue(os.path.exists(jones))
        self.assertIn('copied', out)


class TestLocalConfigSubfolder(BibTest):
    """local configuration whose bibtex lives in a subfolder"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir = self.temp_dir.name
        os.makedirs(os.path.join(self.dir, 'refs'))
        Path(self.dir, 'refs', 'papers.bib').write_text('')

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_from_another_directory(self):
        configfile = os.path.join(self.dir, CONFIG_FILE_LOCAL)
        config = Config(file=configfile, is_library=True,
                        bibtex=os.path.join(self.dir, 'refs', 'papers.bib'),
                        filesdir=os.path.join(self.dir, 'files'))
        config.save()
        js = json.load(open(configfile))
        self.assertEqual(js['bibtex'], os.path.join('refs', 'papers.bib'))
        self.assertEqual(js['filesdir'], 'files')


class TestFlatLayout(BibTest):
    """the files of an entry: <name>.<ext> and <name>--<label>.<ext>"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir = self.temp_dir.name
        self.filesdir = os.path.join(self.dir, 'files')
        self.biblio = Biblio(filesdir=self.filesdir)
        self.biblio.add_bibtex(ENTRY.replace('file = {:a.pdf:pdf}', ''))
        self.entry = self.biblio.entries[0]
        self.name = self.biblio.nameformat(self.entry)

    def tearDown(self):
        self.temp_dir.cleanup()

    def touch(self, *names):
        paths = []
        for name in names:
            path = os.path.join(self.dir, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            Path(path).write_text(name)
            paths.append(path)
        return paths

    def rename(self, files=None):
        if files is not None:
            self.biblio.set_files(self.entry, files)
        self.biblio.rename_entry_files(self.entry)
        return [os.path.relpath(f, self.filesdir) for f in self.biblio.get_files(self.entry)]

    def test_names(self):
        files = self.rename(self.touch('a.pdf', 'supplement.pdf', 'data.zip'))
        n = self.name
        self.assertEqual(files, [f'{n}.pdf', f'{n}--supplement.pdf', f'{n}--data.zip'])
        self.assertEqual(Path(self.filesdir, f'{n}--data.zip').read_text(), 'data.zip')
        # renaming again changes nothing
        self.assertEqual(self.rename(), files)

    def test_new_name_keeps_labels(self):
        self.rename(self.touch('a.pdf', 'supplement.pdf'))
        self.entry['year'] = '2021'
        n = self.biblio.nameformat(self.entry)
        self.assertNotEqual(n, self.name)
        self.assertEqual(self.rename(), [f'{n}.pdf', f'{n}--supplement.pdf'])
        self.assertEqual(sorted(os.listdir(self.filesdir)), [f'{n}--supplement.pdf', f'{n}.pdf'])

    def test_same_labels(self):
        files = self.rename(self.touch('a.pdf', 'x/si.pdf', 'y/si.pdf'))
        n = self.name
        self.assertEqual(files, [f'{n}.pdf', f'{n}--si.pdf', f'{n}--si-2.pdf'])
        self.assertEqual(self.rename(), files)

    def test_slug_labels(self):
        "the label is the slug of the file's name: lower case, ASCII, words joined with '-'"
        files = self.rename(self.touch('a.pdf', 'Geophysical Research Letters - 2011 - Rignot (SI).pdf',
                                       'Données_été.csv'))
        n = self.name
        self.assertEqual(files, [f'{n}.pdf', f'{n}--geophysical-research-letters-2011-rignot-si.pdf',
                                 f'{n}--donnees-ete.csv'])
        self.assertEqual(self.rename(), files)

    def test_slug_label_of_a_renamed_file(self):
        "a file named <name>--<label> by an earlier version gets the slug of its label"
        n = self.name
        files = self.rename(self.touch('a.pdf', f'{n}--Supplementary Data.pdf'))
        self.assertEqual(files, [f'{n}.pdf', f'{n}--supplementary-data.pdf'])

    def test_slug_label_keeps_separators(self):
        "the parts of a label between '--' are slugified one by one"
        files = self.rename(self.touch('a.pdf', 'Info DOI--Supp Data.zip'))
        self.assertEqual(files, [f'{self.name}.pdf', f'{self.name}--info-doi--supp-data.zip'])

    def test_empty_slug_label(self):
        "a label without letters or digits is kept as it is"
        files = self.rename(self.touch('a.pdf', '+++.pdf'))
        self.assertEqual(files, [f'{self.name}.pdf', f'{self.name}--+++.pdf'])

    def test_legacy_directory(self):
        n = self.name
        legacy = self.touch(f'files/{n}/{n}.pdf', f'files/{n}/si.pdf', f'files/{n}/.{n}.bib')[:2]
        self.assertEqual(self.rename(legacy), [f'{n}.pdf', f'{n}--si.pdf'])
        self.assertFalse(os.path.exists(os.path.join(self.filesdir, n)))

    def test_legacy_directory_with_other_files(self):
        n = self.name
        legacy = self.touch(f'files/{n}/{n}.pdf', f'files/{n}/si.pdf', f'files/{n}/.{n}.bib', f'files/{n}/notes.txt')[:2]
        self.assertEqual(self.rename(legacy), [f'{n}.pdf', f'{n}--si.pdf'])
        self.assertTrue(os.path.exists(os.path.join(self.filesdir, n, 'notes.txt')))

    def test_source_directory_is_kept(self):
        self.rename(self.touch('downloads/a.pdf', 'downloads/b.pdf'))
        self.assertTrue(os.path.isdir(os.path.join(self.dir, 'downloads')))


class TestGroupAttachments(unittest.TestCase):

    def test_groups(self):
        names = ['main.pdf', 'main--si.pdf', 'main--sound.mp3', 'other.pdf', 'notes.txt']
        self.assertEqual(group_attachments(names), {
            'main.pdf': ['main--si.pdf', 'main--sound.mp3'],
            'other.pdf': [],
            'notes.txt': [],
        })

    def test_attachment_without_main(self):
        # no x.pdf: x--si.pdf is a paper of its own
        self.assertEqual(group_attachments(['x--si.pdf', 'y.pdf']), {'x--si.pdf': [], 'y.pdf': []})

    def test_main_must_be_pdf(self):
        self.assertEqual(group_attachments(['x.djvu', 'x--si.pdf']), {'x.djvu': [], 'x--si.pdf': []})

    def test_longest_main(self):
        # a main file whose own name contains '--'
        names = ['a.pdf', 'a--b.pdf', 'a--b--c.pdf']
        self.assertEqual(group_attachments(names), {'a.pdf': ['a--b.pdf', 'a--b--c.pdf']})
        names = ['a--b.pdf', 'a--b--c.pdf']
        self.assertEqual(group_attachments(names), {'a--b.pdf': ['a--b--c.pdf']})

    def test_prefix_without_separator(self):
        self.assertEqual(group_attachments(['a.pdf', 'ab.pdf', 'a-b.pdf']), {'a.pdf': [], 'ab.pdf': [], 'a-b.pdf': []})


class TestScanFlatLayout(BibTest):
    """papers add --recursive on a files directory of the flat layout"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir = self.temp_dir.name
        self.files = os.path.join(self.dir, 'files')
        os.makedirs(self.files)
        for name in ['main.pdf', 'main--si.pdf', 'main--sound.mp3', 'other.pdf']:
            Path(self.files, name).write_text(name)
        Path(self.dir, 'lib.bib').write_text('')
        self.scanned = []

    def tearDown(self):
        self.temp_dir.cleanup()

    def fake_metadata(self, pdf, *args, **kwargs):
        self.scanned.append(os.path.basename(pdf))
        name = os.path.splitext(os.path.basename(pdf))[0]
        return f'@article{{{name},\n author = {{{name.capitalize()}, A.}},\n title = {{Paper {name}}},\n year = {{2020}}\n}}\n'

    def test_scan(self):
        from unittest import mock
        with mock.patch('papers.bib.extract_pdf_metadata', self.fake_metadata), \
                mock.patch('papers.cli.entry_cmds.prefetch_pdf_metadata', lambda *a, **k: None):
            paperscmd('add --recursive files --bibtex lib.bib --relative-paths', cwd=self.dir)
        self.assertEqual(sorted(self.scanned), ['main.pdf', 'other.pdf'])
        biblio = Biblio.load(os.path.join(self.dir, 'lib.bib'), None)
        files = {e['title']: [os.path.basename(f) for f in biblio.get_files(e)] for e in biblio.entries}
        self.assertEqual(files, {
            'Paper main': ['main.pdf', 'main--si.pdf', 'main--sound.mp3'],
            'Paper other': ['other.pdf'],
        })

    def test_scan_with_bibtex(self):
        """files linked from a bibtex of the scanned tree are not scanned"""
        from unittest import mock
        Path(self.files, 'main--sound.mp3').unlink()
        Path(self.dir, 'scanned').mkdir()
        os.rename(self.files, os.path.join(self.dir, 'scanned', 'files'))
        Path(self.dir, 'scanned', 'refs.bib').write_text("""@article{mykey,
 author = {Main, A.},
 title = {Paper main, adapted title},
 year = {2020},
 file = {:files/main.pdf:pdf;:files/main--si.pdf:pdf}
}
""")
        with mock.patch('papers.bib.extract_pdf_metadata', self.fake_metadata), \
                mock.patch('papers.cli.entry_cmds.prefetch_pdf_metadata', lambda *a, **k: None):
            paperscmd('add --recursive scanned --bibtex lib.bib --relative-paths', cwd=self.dir)
        self.assertEqual(self.scanned, ['other.pdf'])
        biblio = Biblio.load(os.path.join(self.dir, 'lib.bib'), None)
        files = {e.key: [os.path.relpath(f, self.dir) for f in biblio.get_files(e)] for e in biblio.entries}
        self.assertEqual(files, {
            'mykey': [os.path.join('scanned', 'files', 'main.pdf'), os.path.join('scanned', 'files', 'main--si.pdf')],
            'other2020': [os.path.join('scanned', 'files', 'other.pdf')],
        })
        self.assertEqual(biblio.entries[0]['title'], 'Paper main, adapted title')
