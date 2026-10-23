"""papers file check and papers file fix [--search DIR]: the broken links relinked to
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
    """a library in pool/ with the entry smith2000 (DOI 10.1000/smith) and
    its file pool/files/smith.pdf, and a self-contained library in lib/
    (files: move)"""

    def setUp(self):
        super().setUp()
        self.papers('init pool --no-git')
        self.pool_pdf = self.write('pool', 'files', 'smith.pdf')
        Path(self.path('pool', 'papers.bib')).write_text(entry('smith2000', 'files/smith.pdf', doi='10.1000/smith'))
        self.papers('init lib --no-git')
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


class TestPoolRelink(RelinkTest):
    "lib/ is a shallow library of pool/"

    def setUp(self):
        super().setUp()
        self.lib('config pool ../pool -y')
        self.gone = self.path('gone', 'smith-paper.pdf')
        self.bib(entry('smith2000a', self.gone, doi='10.1000/SMITH'))

    def test_report(self):
        out = self.out('file check')
        self.assertIn(f'smith2000a: broken link: {self.gone} -> {self.pool_pdf} (from the pool)',
                      out)
        self.assertIn('1 link can be relinked, 0 without a file found', out)
        self.assertIn('1 link can be repaired: `papers file fix`', out)
        self.assertEqual(self.files('smith2000a'), [self.gone])

    def test_report_hint_with_keys(self):
        out = self.out('file check smith2000a')
        self.assertIn('1 link can be repaired: `papers file fix smith2000a`', out)

    def test_fix_links_the_pool_file(self):
        out = self.out('file fix')
        self.assertIn(f'smith2000a: relinked to {short_home(self.pool_pdf)} (from the pool)', out)
        self.assertIn('1 link relinked, 0 still broken\n', out)
        self.assertEqual(self.files('smith2000a'), [self.pool_pdf])
        self.assertEqual(self.listdir('pool', 'files'), ['smith.pdf'])
        self.assertEqual(self.files('smith2000', where='pool'), [self.pool_pdf])
        self.assertIn('no issue found', self.out('file check'))

    def test_dry_run(self):
        out = self.out('file fix --dry-run')
        self.assertIn(f'DRYRUN: smith2000a: relink {self.gone} -> {self.pool_pdf} (from the pool)', out)
        self.assertIn('DRYRUN: 1 link relinked, 0 still broken', out)
        self.assertNotIn('can be repaired', out)
        self.assertEqual(self.files('smith2000a'), [self.gone])
        self.assertEqual(self.files('smith2000', where='pool'), [self.pool_pdf])

    def test_pool_file_outside_the_pool_files_directory(self):
        # a file of a pool entry is never moved, even outside the files directory of the pool
        external = self.write('elsewhere', 'smith.pdf')
        self.bib(entry('smith2000', external, doi='10.1000/smith'), where='pool')
        self.lib('file fix')
        self.assertEqual(self.files('smith2000a'), [external])
        self.assertTrue(os.path.exists(external))

    def test_link_mode_links_the_pool_file(self):
        self.lib('config files link')
        self.lib('file fix')
        self.assertEqual(self.files('smith2000a'), [self.pool_pdf])

    def test_same_name(self):
        # three broken links: the one of the same name as a pool file is relinked to it, the
        # others (two links, one pool file left) are not paired
        si = self.write('pool', 'files', 'smith-si.pdf')
        self.bib(entry('smith2000', 'files/smith.pdf', 'files/smith-si.pdf', doi='10.1000/smith'), where='pool')
        others = [self.path('gone', 'other.pdf'), self.path('gone', 'more.pdf')]
        self.bib(entry('smith2000a', self.path('gone', 'smith-si.pdf'), *others, doi='10.1000/smith'))
        self.lib('config files link')
        out = self.out('file fix')
        self.assertEqual(self.files('smith2000a'), [si] + others)
        self.assertIn('1 link relinked, 2 still broken (papers file detach --broken removes them)', out)

    def test_label_then_pair(self):
        # the pool renamed both files: the supplement by its label, then the one link and the one file left
        main = self.write('pool', 'files', 'smith_2000.pdf')
        si = self.write('pool', 'files', 'smith_2000--supp.pdf')
        self.bib(entry('smith2000', 'files/smith_2000.pdf', 'files/smith_2000--supp.pdf', doi='10.1000/smith'),
                 where='pool')
        self.bib(entry('smith2000a', self.path('gone', 'paper.pdf'), self.path('gone', 'supp.pdf'),
                       doi='10.1000/smith'))
        self.lib('config files link')
        out = self.out('file fix')
        self.assertEqual(self.files('smith2000a'), [main, si])
        self.assertIn('2 links relinked, 0 still broken', out)

    def test_pairing_ambiguous(self):
        # two links and two pool files, no name in common: nothing is guessed
        self.write('pool', 'files', 'x.pdf')
        self.write('pool', 'files', 'y.pdf')
        self.bib(entry('smith2000', 'files/x.pdf', 'files/y.pdf', doi='10.1000/smith'), where='pool')
        links = [self.path('gone', 'a.pdf'), self.path('gone', 'b.pdf')]
        self.bib(entry('smith2000a', *links, doi='10.1000/smith'))
        out = self.out('file fix')
        self.assertEqual(self.files('smith2000a'), links)
        self.assertIn('0 links relinked, 2 still broken', out)

    def test_label_ambiguous(self):
        # two pool files with the label of the link: neither is taken by the label; and
        # with two links and two files left, nothing is paired
        self.write('pool', 'files', 'x--supp.pdf')
        self.write('pool', 'files', 'y--supp.pdf')
        self.bib(entry('smith2000', 'files/x--supp.pdf', 'files/y--supp.pdf', doi='10.1000/smith'), where='pool')
        links = [self.path('gone', 'supp.pdf'), self.path('gone', 'b.pdf')]
        self.bib(entry('smith2000a', *links, doi='10.1000/smith'))
        self.out('file fix')
        self.assertEqual(self.files('smith2000a'), links)

    def test_no_guess(self):
        # two broken links of other names, one pool file: nothing is relinked
        links = [self.path('gone', 'a.pdf'), self.path('gone', 'b.pdf')]
        self.bib(entry('smith2000a', *links, doi='10.1000/smith'))
        out = self.out('file fix')
        self.assertEqual(self.files('smith2000a'), links)
        self.assertIn('0 links relinked, 2 still broken', out)

    def test_other_paper(self):
        self.bib(entry('other2000', self.gone, doi='10.1000/other'))
        out = self.out('file check')
        self.assertIn(f'other2000: broken link: {self.gone} (remove it with', out)
        self.assertIn('0 links can be relinked, 1 without a file found', out)
        self.assertNotIn('can be repaired', out)

    def test_selected_entries(self):
        self.bib(entry('smith2000a', self.gone, doi='10.1000/smith'), entry('two2000', self.path('gone', 'x.pdf')))
        out = self.out('file fix two2000')
        self.assertEqual(self.files('smith2000a'), [self.gone])
        self.assertIn('0 links relinked, 1 still broken', out)



class TestSearch(RelinkTest):

    def setUp(self):
        super().setUp()
        self.gone = self.path('gone', 'paper.pdf')
        self.bib(entry('one2000', self.gone))
        self.template = 'one_2000_title-of-one2000.pdf'  # the default name template

    def test_basename(self):
        found = self.write('downloads', 'sub', 'paper.pdf')
        out = self.out('file check --search ../downloads')
        self.assertIn(f'one2000: broken link: {self.gone} -> {found} (found in {self.path("downloads")})',
                      out)
        self.assertIn(f'1 link can be repaired: `papers file fix --search {self.path("downloads")}`', out)
        out = self.out('file fix --search ../downloads')
        new = self.path('lib', 'files', self.template)
        self.assertEqual(self.files('one2000'), [new])
        self.assertIn(f'one2000: relinked to {new} (found in {self.path("downloads")})', out)
        # files: move, but a file found is never moved: copied (a hard link)
        self.assertTrue(os.path.samefile(new, found))
        self.assertEqual(os.stat(found).st_nlink, 2)
        self.assertEqual(Path(new).read_text(), 'paper.pdf')

    def test_move(self):
        found = self.write('downloads', 'paper.pdf')
        out = self.out('file fix --search ../downloads --move')
        new = self.path('lib', 'files', self.template)
        self.assertEqual(self.files('one2000'), [new])
        self.assertIn(f'one2000: relinked to {new} (found in {self.path("downloads")})', out)
        self.assertFalse(os.path.exists(found))
        self.assertEqual(Path(new).read_text(), 'paper.pdf')

    def test_move_copies_the_files_of_another_library(self):
        # a file in the files directory of another library stays there with --move
        found = self.write('pool', 'files', 'paper.pdf')
        out = self.out('file fix --search ../pool/files --move')
        new = self.path('lib', 'files', self.template)
        self.assertEqual(self.files('one2000'), [new])
        self.assertIn(f'{found} belongs to the library in {self.path("pool")}: copied, not moved', out)
        self.assertTrue(os.path.samefile(new, found))

    def test_found_in_the_files_directory(self):
        # a file found in the files directory (shared with another library?) is not renamed
        found = self.write('lib', 'files', 'paper.pdf')
        self.lib('file fix --search files')
        new = self.path('lib', 'files', self.template)
        self.assertEqual(self.files('one2000'), [new])
        self.assertTrue(os.path.samefile(new, found))

    def test_move_without_files_directory(self):
        self.lib('config --unset filesdir')
        self.write('downloads', 'paper.pdf')
        with self.assertRaisesRegex(PapersExit, '--move: the library has no files directory'):
            self.lib('file fix --search ../downloads --move')

    def test_link_mode(self):
        # link mode: the file found is linked where it is
        found = self.write('downloads', 'paper.pdf')
        self.lib('config files link')
        self.lib('file fix --search ../downloads')
        self.assertEqual(self.files('one2000'), [found])

    def test_hint_with_bibtex_and_directory(self):
        self.write('downloads', 'paper.pdf')
        out = self.out('file check --bibtex papers.bib --search ../downloads')
        self.assertIn('1 link can be repaired: '
                      f'`papers file fix --bibtex papers.bib --search {self.path("downloads")}`', out)
        out = self.out('-C lib file check one2000 --search ../downloads', where='.')
        self.assertIn('1 link can be repaired: '
                      f'`papers -C lib file fix one2000 --search {self.path("downloads")}`', out)

    def test_no_issues_line_after_a_full_fix(self):
        self.write('downloads', 'paper.pdf')
        out = self.out('file fix --search ../downloads')
        self.assertIn('1 link relinked, 0 still broken', out)
        self.assertNotIn('issue(s)', out)
        self.assertNotIn('no issue found', out)

    def test_issues_left_line(self):
        self.bib(entry('one2000', self.gone), entry('two2000', self.path('gone', 'two.pdf')))
        self.write('downloads', 'paper.pdf')
        out = self.out('file fix --search ../downloads')
        self.assertIn('1 link relinked, 1 still broken', out)
        self.assertIn('1 issue(s) left in the files of 2 entries', out)

    def test_template_name(self):
        found = self.write('downloads', self.template)
        self.write('downloads', 'other.pdf')
        self.lib('config files copy')
        self.lib('file fix --search ../downloads')
        new, = self.files('one2000')
        self.assertTrue(os.path.samefile(new, found))  # files: copy (a hard link)
        self.assertTrue(new.startswith(self.path('lib', 'files')))

    def test_several_search_folders(self):
        found = self.write('b', 'paper.pdf')
        self.write('a', 'x.pdf')
        self.lib('config files link')
        self.lib('file fix --search ../a --search ../b')
        self.assertEqual(self.files('one2000'), [found])

    def test_ambiguous(self):
        a = self.write('a', 'paper.pdf')
        b = self.write('b', 'sub', 'paper.pdf')
        out = self.out('file fix --search ../a --search ../b')
        self.assertIn(f'one2000: broken link: {self.gone}: several files match in the --search folders: '
                      f'{a}, {b} (not relinked)', out)
        self.assertNotIn('remove it with', out)
        self.assertIn('0 links relinked, 1 still broken', out)
        self.assertEqual(self.files('one2000'), [self.gone])
        self.assertTrue(os.path.exists(a) and os.path.exists(b))

    def test_same_file_for_two_entries(self):
        self.bib(entry('one2000', self.gone), entry('two2000', self.path('gone2', 'paper.pdf')))
        found = self.write('downloads', 'paper.pdf')
        out = self.out('file fix --search ../downloads')
        self.assertIn(f'one2000: broken link: {self.gone}: {found} matches the broken links of one2000, two2000 '
                      '(not relinked)', out)
        self.assertEqual(self.files('one2000'), [self.gone])
        self.assertTrue(os.path.exists(found))

    def test_pool_first(self):
        self.lib('config pool ../pool -y')
        self.bib(entry('smith2000a', self.path('gone', 'smith.pdf'), doi='10.1000/smith'))
        self.write('downloads', 'smith.pdf')
        self.lib('config files link')
        out = self.out('file fix --search ../downloads')
        self.assertIn('(from the pool)', out)
        self.assertEqual(self.files('smith2000a'), [self.pool_pdf])

    def test_not_a_folder(self):
        with self.assertRaisesRegex(PapersExit, '--search ../nope: not a folder'):
            self.lib('file check --search ../nope')

    def test_shallow_copies_into_the_pool(self):
        self.lib('config pool ../pool -y')
        found = self.write('downloads', 'paper.pdf')
        out = self.out('file fix --search ../downloads')
        new, = self.files('one2000')
        self.assertTrue(new.startswith(self.path('pool', 'files')))
        self.assertIn(f'one2000: relinked to {short_home(new)} (found in {self.path("downloads")})', out)
        self.assertTrue(os.path.samefile(new, found))
        # auto-push false: the entry, not in the pool, goes there with its file (file links are always pushed)
        self.assertIn('one2000: also added to pool ../pool', out)
        self.assertEqual(self.files('one2000', where='pool'), [new])


class TestOtherLibrary(RelinkTest):
    """papers file fix --pool PATH: lib/ (self-contained, files: move) takes
    the files of the library pool/ (not its pool), by paper identity"""

    def setUp(self):
        super().setUp()
        self.gone = self.path('gone', 'smith-paper.pdf')  # not the name of the file of pool/
        self.bib(entry('smith2000a', self.gone, doi='10.1000/SMITH'))
        self.template = 'one_2000_title-of-smith2000a.pdf'
        self.pool_bib = Path(self.path('pool', 'papers.bib')).read_text()

    def test_check(self):
        out = self.out('file check --pool ../pool')
        self.assertIn(f'smith2000a: broken link: {self.gone} -> {self.pool_pdf} (from the library ../pool)', out)
        self.assertIn(f'1 link can be repaired: `papers file fix --pool {self.path("pool")}`', out)
        self.assertEqual(self.files('smith2000a'), [self.gone])

    def test_fix_copies_by_identity(self):
        before = Path(self.path('lib', 'papers.bib')).read_text()
        out = self.out('file fix --pool ../pool')
        new = self.path('lib', 'files', self.template)
        self.assertIn(f'smith2000a: relinked to {new} (from the library ../pool)', out)
        self.assertEqual(self.files('smith2000a'), [new])
        # copied (a hard link), the pool file stays where it is
        self.assertTrue(os.path.exists(self.pool_pdf))
        self.assertTrue(os.path.samefile(new, self.pool_pdf))
        self.assertEqual(os.stat(self.pool_pdf).st_nlink, 2)
        # only the link changed, in the library; PATH is unchanged and no origin record is written
        after = Path(self.path('lib', 'papers.bib')).read_text()
        self.assertEqual(after.replace(os.path.join('files', self.template), self.gone).strip(), before.strip())
        self.assertEqual(Path(self.path('pool', 'papers.bib')).read_text(), self.pool_bib)
        self.assertFalse(os.path.exists(self.path('lib', '.papers', 'origin')))
        self.assertNotIn('issue(s)', out)

    def test_move_still_copies(self):
        self.lib('file fix --pool ../pool --move')
        self.assertTrue(os.path.exists(self.pool_pdf))

    def test_file_of_the_entry_outside_the_files_directory(self):
        external = self.write('elsewhere', 'smith.pdf')
        self.bib(entry('smith2000', external, doi='10.1000/smith'), where='pool')
        self.lib('file fix --pool ../pool --move')
        new, = self.files('smith2000a')
        self.assertTrue(os.path.samefile(new, external))

    def test_link_mode(self):
        self.lib('config files link')
        self.lib('file fix --pool ../pool')
        self.assertEqual(self.files('smith2000a'), [self.pool_pdf])

    def test_other_paper(self):
        self.bib(entry('other2000', self.gone, doi='10.1000/other'))
        out = self.out('file fix --pool ../pool')
        self.assertIn('0 links relinked, 1 still broken', out)

    def test_not_a_library(self):
        os.makedirs(self.path('plain'))
        with self.assertRaisesRegex(PapersExit, 'create it first with `papers init'):
            self.lib('file fix --pool ../plain')

    def test_then_search(self):
        # a link that PATH has no file for is looked for in the --search folders
        self.bib(entry('smith2000a', self.gone, doi='10.1000/SMITH'), entry('one2000', self.path('gone', 'x.pdf')))
        found = self.write('downloads', 'x.pdf')
        out = self.out('file fix --pool ../pool --search ../downloads')
        self.assertIn('2 links relinked, 0 still broken', out)
        self.assertIn('(from the library ../pool)', out)
        self.assertIn(f'(found in {self.path("downloads")})', out)
        self.assertTrue(os.path.exists(found))

    def test_shallow_library_copies_into_its_pool(self):
        # lib/ is a shallow library of own/, whose entry has no file: the file of pool/ is copied
        # into the files directory of own/, and the entry of own/ links to it
        self.papers('init own --no-git')
        self.bib(entry('smith2000', doi='10.1000/smith'), where='own')
        self.lib('config pool ../own -y')
        out = self.out('file fix --pool ../pool')
        new, = self.files('smith2000a')
        self.assertTrue(new.startswith(self.path('own', 'files')), new)
        self.assertTrue(os.path.samefile(new, self.pool_pdf))
        self.assertEqual(self.files('smith2000', where='own'), [new])
        self.assertIn('smith2000a: file links also updated in pool ../own', out)
        self.assertEqual(Path(self.path('pool', 'papers.bib')).read_text(), self.pool_bib)

    def test_own_pool_first(self):
        # the pool of the library has the file: PATH is not used
        self.papers('init own --no-git')
        own_pdf = self.write('own', 'files', 'smith.pdf')
        self.bib(entry('smith2000', 'files/smith.pdf', doi='10.1000/smith'), where='own')
        self.lib('config pool ../own -y')
        out = self.out('file fix --pool ../pool')
        self.assertIn('(from the pool)', out)
        self.assertEqual(self.files('smith2000a'), [own_pdf])


class TestSharedFilesDir(ConfigTest):
    """the case of two libraries of papers v2 that share a files directory:
    one of them moves to a pool, which moves the files of the other"""

    def setUp(self):
        super().setUp()
        for name in ('lib1', 'lib2'):
            self.papers(f'init {name} --no-git', cwd=self.dir)
            self.papers('config filesdir ../shared', cwd=self.path(name))
            self.papers('config files move', cwd=self.path(name))
        self.papers('init P --no-git', cwd=self.dir)  # the library that lib1 moves to
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
        self.run_in('lib1', 'push --pool ../P --all')
        self.run_in('lib1', 'config pool ../P -y')
        # lib1 linked the pool's copies, and deleted its own
        self.assertEqual(sorted(os.listdir(self.path('shared'))), ['c.pdf'])
        self.run_in('lib2', 'push --pool ../P c2000')  # the others are in the pool already
        out = io.StringIO()
        with redirect_stdout(out):
            self.run_in('lib2', 'config pool ../P -y')
        self.assertIn('2 links were already broken: `papers file fix` relinks those that the pool has',
                      out.getvalue())
        out = io.StringIO()
        with redirect_stdout(out):
            self.run_in('lib2', 'file fix')
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
        # the pool renamed both files of the entry (template name, and name--label for the
        # supplement): the supplement is found by its label, the PDF as the one file left
        Path(self.path('shared', 'b-si.pdf')).write_text('b-si')
        for name in ('lib1', 'lib2'):
            bibtex = Path(self.path(name, 'papers.bib'))
            bibtex.write_text(bibtex.read_text().replace(
                'file = {:../shared/b.pdf:pdf}', 'file = {:../shared/b.pdf:pdf;:../shared/b-si.pdf:pdf}'))
        self.run_in('lib1', 'push --pool ../P --all')
        self.run_in('lib1', 'config pool ../P -y')
        self.run_in('lib2', 'push --pool ../P c2000')
        self.run_in('lib2', 'config pool ../P -y')
        out = io.StringIO()
        with redirect_stdout(out):
            self.run_in('lib2', 'file fix')
        self.assertIn('3 links relinked, 0 still broken', out.getvalue())
        biblio = Biblio.load(self.path('lib2', 'papers.bib'), '')
        beta = next(e for e in biblio.entries if e.key == 'beta2000')
        self.assertEqual([Path(f).read_text() for f in biblio.get_files(beta)], ['b', 'b-si'])
        self.assertEqual(len(os.listdir(self.path('P', 'files'))), 5)

    def test_no_broken_link_no_hint(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.run_in('lib1', 'push --pool ../P --all')
            self.run_in('lib1', 'config pool ../P -y')
        self.assertNotIn('already broken', out.getvalue())
