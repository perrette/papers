"""papers file check [--fix] [--search DIR]: the broken links relinked to
the files of the pool or of the --search folders"""
import io
import os
from contextlib import redirect_stdout
from pathlib import Path

from papers.bib import Biblio
from papers.config import short_home
from papers.utils import PapersExit

from tests.common import ConfigTest


def entry(key, *files, doi=None, author='Some One', title=None):
    file = ';'.join(f':{f}:pdf' for f in files)
    return (f"@article{{{key},\n author = {{{author}}},\n"
            + (f" doi = {{{doi}}},\n" if doi else "")
            + (f" file = {{{file}}},\n" if files else "")
            + f" title = {{{title or 'Title of ' + key}}},\n year = {{2000}}\n}}\n\n")


class RelinkTest(ConfigTest):
    """a pool in pool/ with the entry smith2000 (DOI 10.1000/smith) and its
    file pool/files/smith.pdf, and a local library in lib/ (files: move)
    that uses it"""

    def setUp(self):
        super().setUp()
        self.papers('init pool --no-git --pool none')
        self.pool_pdf = self.write('pool', 'files', 'smith.pdf')
        Path(self.path('pool', 'papers.bib')).write_text(entry('smith2000', 'files/smith.pdf', doi='10.1000/smith'))
        self.papers('init lib --no-git --pool ../pool --local')
        self.lib('config files move')

    def lib(self, cmd):
        return self.papers(cmd, cwd=self.path('lib'))

    def out(self, cmd, where='lib'):
        out = io.StringIO()
        with redirect_stdout(out):
            self.papers(cmd, cwd=self.path(where))
        return out.getvalue()

    def write(self, *p, content=None):
        path = self.path(*p)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Path(path).write_text(content or os.path.basename(path))
        return path

    def bib(self, *entries, where='lib'):
        Path(self.path(where, 'papers.bib')).write_text(''.join(entries))

    def files(self, key, where='lib'):
        biblio = Biblio.load(self.path(where, 'papers.bib'), '')
        e = next(e for e in biblio.entries if e.key == key)
        return biblio.get_files(e)

    def listdir(self, *p):
        return sorted(os.listdir(self.path(*p)))


class TestPoolLocal(RelinkTest):

    def setUp(self):
        super().setUp()
        self.gone = self.path('gone', 'smith-paper.pdf')
        self.bib(entry('smith2000a', self.gone, doi='10.1000/SMITH'))

    def test_report(self):
        out = self.out('file check')
        self.assertIn(f'smith2000a: broken link: {self.gone} -> {self.pool_pdf} (from the pool; relink with --fix)',
                      out)
        self.assertIn('1 link can be relinked (papers file check --fix), 0 without a file found', out)
        self.assertEqual(self.files('smith2000a'), [self.gone])

    def test_fix_copies_the_pool_file(self):
        out = self.out('file check --fix')
        new, = self.files('smith2000a')
        self.assertIn(f'smith2000a: relinked to {short_home(new)} (from the pool)', out)
        self.assertIn('1 link relinked, 0 still broken\n', out)
        self.assertTrue(new.startswith(self.path('lib', 'files')))
        self.assertTrue(os.path.samefile(new, self.pool_pdf))  # a hard link
        self.assertEqual(self.listdir('pool', 'files'), ['smith.pdf'])
        self.assertIn('no issue found', self.out('file check'))

    def test_dry_run(self):
        out = self.out('file check --fix --dry-run')
        self.assertIn(f'DRYRUN: smith2000a: relink {self.gone} -> {self.pool_pdf} (from the pool)', out)
        self.assertIn('DRYRUN: 1 link relinked, 0 still broken', out)
        self.assertEqual(self.files('smith2000a'), [self.gone])
        self.assertEqual(os.listdir(self.path('lib', 'files')), [])

    def test_pool_file_outside_the_pool_files_directory(self):
        # a file of a pool entry is never moved, even outside the files directory of the pool
        external = self.write('elsewhere', 'smith.pdf')
        self.bib(entry('smith2000', external, doi='10.1000/smith'), where='pool')
        self.lib('file check --fix')
        new, = self.files('smith2000a')
        self.assertTrue(new.startswith(self.path('lib', 'files')))
        self.assertTrue(os.path.exists(external))
        self.assertTrue(os.path.samefile(new, external))

    def test_link_mode_links_the_pool_file(self):
        self.lib('config files link')
        self.lib('file check --fix')
        self.assertEqual(self.files('smith2000a'), [self.pool_pdf])

    def test_same_name(self):
        # two broken links: the one of the same name as a pool file is relinked to it
        si = self.write('pool', 'files', 'smith-si.pdf')
        self.bib(entry('smith2000', 'files/smith.pdf', 'files/smith-si.pdf', doi='10.1000/smith'), where='pool')
        other = self.path('gone', 'other.pdf')
        self.bib(entry('smith2000a', self.path('gone', 'smith-si.pdf'), other, doi='10.1000/smith'))
        self.lib('config files link')
        out = self.out('file check --fix')
        self.assertEqual(self.files('smith2000a'), [si, other])
        self.assertIn('1 link relinked, 1 still broken (papers file detach --broken removes them)', out)

    def test_no_guess(self):
        # two broken links of other names, one pool file: nothing is relinked
        links = [self.path('gone', 'a.pdf'), self.path('gone', 'b.pdf')]
        self.bib(entry('smith2000a', *links, doi='10.1000/smith'))
        out = self.out('file check --fix')
        self.assertEqual(self.files('smith2000a'), links)
        self.assertIn('0 links relinked, 2 still broken', out)

    def test_other_paper(self):
        self.bib(entry('other2000', self.gone, doi='10.1000/other'))
        out = self.out('file check')
        self.assertIn(f'other2000: broken link: {self.gone} (remove it with', out)
        self.assertIn('0 links can be relinked, 1 without a file found', out)

    def test_selected_entries(self):
        self.bib(entry('smith2000a', self.gone, doi='10.1000/smith'), entry('two2000', self.path('gone', 'x.pdf')))
        out = self.out('file check --fix two2000')
        self.assertEqual(self.files('smith2000a'), [self.gone])
        self.assertIn('0 links relinked, 1 still broken', out)


class TestPoolNonLocal(RelinkTest):

    def setUp(self):
        super().setUp()
        self.lib('config local false -y')
        self.gone = self.path('gone', 'smith-paper.pdf')
        self.bib(entry('smith2000a', self.gone, doi='10.1000/smith'))

    def test_report(self):
        out = self.out('file check')
        self.assertIn(f'-> {self.pool_pdf} (from the pool; relink with --fix)', out)
        self.assertEqual(self.files('smith2000a'), [self.gone])

    def test_fix_links_the_pool_file(self):
        out = self.out('file check --fix')
        self.assertIn(f'smith2000a: relinked to {short_home(self.pool_pdf)} (from the pool)', out)
        self.assertEqual(self.files('smith2000a'), [self.pool_pdf])
        self.assertEqual(self.listdir('pool', 'files'), ['smith.pdf'])
        self.assertEqual(self.files('smith2000', where='pool'), [self.pool_pdf])


class TestSearch(RelinkTest):

    def setUp(self):
        super().setUp()
        self.gone = self.path('gone', 'paper.pdf')
        self.bib(entry('one2000', self.gone))
        self.template = 'one_2000_title-of-one2000.pdf'  # the default name template

    def test_basename(self):
        found = self.write('downloads', 'sub', 'paper.pdf')
        out = self.out('file check --search ../downloads')
        self.assertIn(f'one2000: broken link: {self.gone} -> {found} (found in {self.path("downloads")}; '
                      'relink with --fix)', out)
        out = self.out('file check --fix --search ../downloads')
        new = self.path('lib', 'files', self.template)
        self.assertEqual(self.files('one2000'), [new])
        self.assertIn(f'one2000: relinked to {new} (found in {self.path("downloads")})', out)
        self.assertFalse(os.path.exists(found))  # files: move
        self.assertEqual(Path(new).read_text(), 'paper.pdf')

    def test_template_name(self):
        found = self.write('downloads', self.template)
        self.write('downloads', 'other.pdf')
        self.lib('config files copy')
        self.lib('file check --fix --search ../downloads')
        new, = self.files('one2000')
        self.assertTrue(os.path.samefile(new, found))  # files: copy (a hard link)
        self.assertTrue(new.startswith(self.path('lib', 'files')))

    def test_several_search_folders(self):
        found = self.write('b', 'paper.pdf')
        self.write('a', 'x.pdf')
        self.lib('config files link')
        self.lib('file check --fix --search ../a --search ../b')
        self.assertEqual(self.files('one2000'), [found])

    def test_ambiguous(self):
        a = self.write('a', 'paper.pdf')
        b = self.write('b', 'sub', 'paper.pdf')
        out = self.out('file check --fix --search ../a --search ../b')
        self.assertIn(f'one2000: broken link: {self.gone}: several files match in the --search folders: '
                      f'{a}, {b} (not relinked)', out)
        self.assertNotIn('remove it with', out)
        self.assertIn('0 links relinked, 1 still broken', out)
        self.assertEqual(self.files('one2000'), [self.gone])
        self.assertTrue(os.path.exists(a) and os.path.exists(b))

    def test_same_file_for_two_entries(self):
        self.bib(entry('one2000', self.gone), entry('two2000', self.path('gone2', 'paper.pdf')))
        found = self.write('downloads', 'paper.pdf')
        out = self.out('file check --fix --search ../downloads')
        self.assertIn(f'one2000: broken link: {self.gone}: {found} matches the broken links of one2000, two2000 '
                      '(not relinked)', out)
        self.assertEqual(self.files('one2000'), [self.gone])
        self.assertTrue(os.path.exists(found))

    def test_pool_first(self):
        self.bib(entry('smith2000a', self.path('gone', 'smith.pdf'), doi='10.1000/smith'))
        self.write('downloads', 'smith.pdf')
        self.lib('config files link')
        out = self.out('file check --fix --search ../downloads')
        self.assertIn('(from the pool)', out)
        self.assertEqual(self.files('smith2000a'), [self.pool_pdf])

    def test_not_a_folder(self):
        with self.assertRaisesRegex(PapersExit, '--search ../nope: not a folder'):
            self.lib('file check --search ../nope')

    def test_non_local_moves_into_the_pool(self):
        self.lib('config local false -y')
        found = self.write('downloads', 'paper.pdf')
        out = self.out('file check --fix --search ../downloads')
        new, = self.files('one2000')
        self.assertTrue(new.startswith(self.path('pool', 'files')))
        self.assertIn(f'one2000: relinked to {short_home(new)} (found in {self.path("downloads")})', out)
        self.assertFalse(os.path.exists(found))
        self.assertEqual(self.files('one2000', where='pool'), [new])  # pushed to the pool, as file attach does


class TestSharedFilesDir(ConfigTest):
    """the case of two libraries of papers v2 that share a files directory:
    one of them moves to a pool, which moves the files of the other"""

    def setUp(self):
        super().setUp()
        for name in ('lib1', 'lib2'):
            self.papers(f'init {name} --no-git --pool none --local', cwd=self.dir)
            self.papers('config filesdir ../shared', cwd=self.path(name))
            self.papers('config files move', cwd=self.path(name))
        os.makedirs(self.path('shared'))
        for name in ('a', 'b', 'c', 'd'):
            Path(self.path('shared', f'{name}.pdf')).write_text(name)
        # both libraries link to a.pdf and b.pdf (other keys in lib2), lib2 also to c.pdf, lib1 to d.pdf
        Path(self.path('lib1', 'papers.bib')).write_text(
            entry('a2000', '../shared/a.pdf', doi='10.1000/a', author='Alpha, A')
            + entry('b2000', '../shared/b.pdf', doi='10.1000/b', author='Beta, B')
            + entry('d2000', '../shared/d.pdf', doi='10.1000/d', author='Delta, D'))
        Path(self.path('lib2', 'papers.bib')).write_text(
            entry('alpha2000', '../shared/a.pdf', doi='10.1000/a', author='Alpha, A')
            + entry('beta2000', '../shared/b.pdf', doi='10.1000/b', author='Beta, B')
            + entry('c2000', '../shared/c.pdf', doi='10.1000/c', author='Gamma, C'))

    def run_in(self, name, cmd):
        return self.papers(cmd, cwd=self.path(name))

    def test_relink(self):
        self.run_in('lib1', 'config pool ../P')
        self.run_in('lib1', 'config local false -y')
        self.assertEqual(sorted(os.listdir(self.path('shared'))), ['c.pdf'])  # lib1 moved its files to the pool
        self.run_in('lib2', 'config pool ../P')
        self.run_in('lib2', 'config local false -y')
        out = io.StringIO()
        with redirect_stdout(out):
            self.run_in('lib2', 'file check --fix')
        self.assertIn('2 links relinked, 0 still broken', out.getvalue())

        biblio = Biblio.load(self.path('lib2', 'papers.bib'), '')
        links = [f for e in biblio.entries for f in biblio.get_files(e)]
        self.assertEqual(len(links), 3)
        for f in links:
            self.assertTrue(os.path.exists(f), f)
            self.assertTrue(f.startswith(self.path('P', 'files')), f)
        pool = Biblio.load(self.path('P', 'papers.bib'), '')
        self.assertEqual(len(pool.entries), 4)  # a, b, c, d
        pool_files = sorted(os.listdir(self.path('P', 'files')))
        self.assertEqual(len(pool_files), 4)  # no duplicate PDF
        self.assertEqual(sorted(Path(self.path('P', 'files', f)).read_text() for f in pool_files),
                         ['a', 'b', 'c', 'd'])
        self.assertEqual(os.listdir(self.path('shared')), [])
        out = io.StringIO()
        with redirect_stdout(out):
            self.run_in('lib1', 'file check')
            self.run_in('lib2', 'file check')
        self.assertEqual(out.getvalue().count('no issue found'), 2)

    def test_entry_with_two_files(self):
        # the pool renamed both files of the entry: neither has the name of a link, and the
        # pool entry has two files: the links are not relinked (`papers add -R` is the fallback)
        Path(self.path('shared', 'b-si.pdf')).write_text('b-si')
        for name in ('lib1', 'lib2'):
            bibtex = Path(self.path(name, 'papers.bib'))
            bibtex.write_text(bibtex.read_text().replace(
                'file = {:../shared/b.pdf:pdf}', 'file = {:../shared/b.pdf:pdf;:../shared/b-si.pdf:pdf}'))
        for name in ('lib1', 'lib2'):
            self.run_in(name, 'config pool ../P')
            self.run_in(name, 'config local false -y')
        out = io.StringIO()
        with redirect_stdout(out):
            self.run_in('lib2', 'file check --fix')
        self.assertIn('1 link relinked, 2 still broken', out.getvalue())
