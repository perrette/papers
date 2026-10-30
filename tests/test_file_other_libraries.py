"""papers file fix, check and fetch: the file of a broken link found in the
library itself by checksum, in its pool, and in the other libraries of the
machine (the places of the history store)"""
import io
import os
import shutil
from contextlib import redirect_stdout
from pathlib import Path

from papers.config import short_home

from tests.test_file_fetch import DOI, PDF, FetchTest
from tests.test_file_relink import entry


def tree(top):
    "{relative path: (content, mtime)} of the files under top (to see that nothing changed)"
    found = {}
    for root, _, files in os.walk(top):
        for name in files:
            path = os.path.join(root, name)
            found[os.path.relpath(path, top)] = (Path(path).read_bytes(), os.stat(path).st_mtime_ns)
    return found


class OtherLibrariesTest(FetchTest):
    """lib/ (files: copy, files directory lib/files), and the library
    other/, which the history of the machine knows: its entry doe2020 (DOI
    10.1000/doe) links to other/files/doe.pdf, whose checksum its
    .papers/files.json has"""

    def setUp(self):
        super().setUp()
        self.lib('config files copy')
        self.papers('init other')
        self.other_pdf = self.write('other', 'files', 'doe.pdf', content='pdf doe')
        Path(self.path('other', 'papers.bib')).write_text(
            entry('doe2020', 'files/doe.pdf', doi='10.1000/doe', author='Doe, Jane', title='Ice'))
        self.papers('file checksum', cwd=self.path('other'))  # a step: other/ is a place of the history
        self.other_before = tree(self.path('other'))

    def out(self, cmd, where='lib'):
        out = io.StringIO()
        with redirect_stdout(out):
            self.papers(cmd, cwd=self.path(where))
        return out.getvalue()

    def assertOtherUnchanged(self):
        self.assertEqual(tree(self.path('other')), self.other_before)

    def lost(self, key, content, **kw):
        "an entry of lib/ whose file lib/files/<key>.pdf had `content`, its checksum recorded, then deleted"
        path = self.write('lib', 'files', key + '.pdf', content=content)
        Path(self.path('lib', 'papers.bib')).write_text(entry(key, 'files/' + key + '.pdf', **kw))
        self.lib('file checksum')
        os.remove(path)
        return path


class TestFix(OtherLibrariesTest):

    def test_own_files_directory_by_checksum(self):
        # renamed by hand in the files directory: found by its checksum, renamed in place (files: copy)
        old = self.lost('one2000', 'pdf one')
        self.write('lib', 'files', 'renamed.pdf', content='pdf one')
        out = self.out('file fix')
        self.assertIn('(same content, in the library)', out)
        file, = self.files('one2000')
        self.assertEqual(Path(file).read_text(), 'pdf one')
        self.assertEqual(sorted(os.listdir(self.path('lib', 'files'))), [os.path.basename(file)])
        self.assertNotEqual(file, old)

    def test_own_file_of_another_entry_by_checksum(self):
        shared = self.write('lib', 'files', 'shared.pdf', content='pdf one')
        old = self.write('lib', 'files', 'one.pdf', content='pdf one')
        self.bib(entry('one2000', 'files/one.pdf'), entry('two2000', 'files/shared.pdf', title='Other'))
        self.lib('file checksum')
        os.remove(old)
        out = self.out('file fix')
        self.assertIn('one2000: relinked to', out)
        self.assertIn('(same content as the file of two2000)', out)
        self.assertEqual(self.files('one2000'), [shared])  # linked where it is

    def test_other_library_by_checksum(self):
        self.lost('one2000', 'pdf doe')  # another title, no DOI: by checksum only
        out = self.out('file check')
        self.assertIn(f'one2000: broken link: {short_home(self.path("lib", "files", "one2000.pdf"))} -> {short_home(self.other_pdf)} '
                      f'(found in {short_home(self.path("other"))} (entry doe2020))', out)
        out = self.out('file fix')
        self.assertIn(f'(found in {short_home(self.path("other"))} (entry doe2020))', out)
        file, = self.files('one2000')
        self.assertEqual(os.path.dirname(file), self.path('lib', 'files'))
        self.assertEqual(Path(file).read_text(), 'pdf doe')
        self.assertOtherUnchanged()

    def test_other_library_by_doi(self):
        self.bib(entry('doe2020a', self.path('gone', 'ice.pdf'), doi='10.1000/DOE'))
        out = self.out('file fix')
        self.assertIn('doe2020a: relinked to', out)
        self.assertIn(f'(found in {short_home(self.path("other"))} (entry doe2020))', out)
        file, = self.files('doe2020a')
        self.assertEqual(Path(file).read_text(), 'pdf doe')
        self.assertEqual(os.path.dirname(file), self.path('lib', 'files'))
        self.assertOtherUnchanged()

    def test_move_setting_copies(self):
        self.lib('config files move')
        self.bib(entry('doe2020a', self.path('gone', 'ice.pdf'), doi='10.1000/doe'))
        self.out('file fix')
        file, = self.files('doe2020a')
        self.assertEqual(os.path.dirname(file), self.path('lib', 'files'))
        self.assertTrue(os.path.exists(self.other_pdf))
        self.assertOtherUnchanged()

    def test_other_paper_not_taken(self):
        self.bib(entry('doe2020a', self.path('gone', 'ice.pdf'), doi='10.1000/other'))
        out = self.out('file fix')
        self.assertIn('0 links relinked, 1 still broken', out)

    def test_gone_library_skipped(self):
        shutil.move(self.path('other'), self.path('moved'))
        self.bib(entry('doe2020a', self.path('gone', 'ice.pdf'), doi='10.1000/doe'))
        out = self.out('file fix')
        self.assertIn('0 links relinked, 1 still broken', out)

    def test_dry_run(self):
        self.bib(entry('doe2020a', self.path('gone', 'ice.pdf'), doi='10.1000/doe'))
        before = self.bibtext()
        out = self.out('file fix --dry-run')
        self.assertIn(f'DRYRUN: doe2020a: relink {short_home(self.path("gone", "ice.pdf"))} -> '
                      f'{short_home(self.other_pdf)} (found in {short_home(self.path("other"))} (entry doe2020))',
                      out)
        self.assertEqual(self.bibtext(), before)


class TestPool(OtherLibrariesTest):
    """lib/ is a shallow library of other/: other/ is its pool, searched once
    (as the pool), not again as another library"""

    def setUp(self):
        super().setUp()
        self.lib('config pool ../other -y')

    def test_same_paper(self):
        self.bib(entry('doe2020a', self.path('gone', 'ice.pdf'), doi='10.1000/doe'))
        out = self.out('file fix')
        self.assertIn(f'doe2020a: relinked to {short_home(self.other_pdf)} (from the pool)', out)

    def test_by_checksum(self):
        self.lost('one2000', 'pdf doe')
        out = self.out('file check')
        self.assertIn(f'one2000: broken link: {short_home(self.path("lib", "files", "one2000.pdf"))} -> {short_home(self.other_pdf)} '
                      f'(from the pool, same content)', out)


class TestFetch(OtherLibrariesTest):

    def setUp(self):
        super().setUp()
        self.publisher(doi='10.1000/doe')

    def test_missing_takes_the_pdf_of_the_same_paper(self):
        self.bib(entry('doe2020a', doi='10.1000/doe'))
        out = self.out('file fetch --missing')
        self.assertIn(f'(found in {short_home(self.path("other"))} (entry doe2020)), not downloaded', out)
        file, = self.files('doe2020a')
        self.assertEqual(Path(file).read_text(), 'pdf doe')
        self.assertEqual(os.path.dirname(file), self.path('lib', 'files'))
        self.assertEqual(self.web.downloads(), [])
        self.assertOtherUnchanged()

    def test_missing_dry_run(self):
        self.bib(entry('doe2020a', doi='10.1000/doe'))
        before = self.bibtext()
        out = self.out('file fetch --missing --dry-run')
        self.assertIn(f'DRYRUN: doe2020a: would attach {short_home(self.other_pdf)} '
                      f'(found in {short_home(self.path("other"))} (entry doe2020))', out)
        self.assertNotIn('would download', out)
        self.assertEqual(self.bibtext(), before)

    def test_missing_broken_link(self):
        self.bib(entry('doe2020a', 'files/ice.pdf', doi='10.1000/doe'))
        out = self.out('file fetch --missing')
        self.assertIn('not downloaded', out)
        self.assertEqual(self.web.downloads(), [])
        self.assertEqual(Path(self.files('doe2020a')[0]).read_text(), 'pdf doe')

    def test_key_still_downloads(self):
        self.bib(entry('doe2020a', doi='10.1000/doe'))
        self.out('file fetch doe2020a')
        self.assertEqual(len(self.web.downloads()), 1)
        file, = self.files('doe2020a')
        self.assertTrue(Path(file).read_bytes().startswith(b'%PDF'))

    def test_other_paper_downloads(self):
        self.bib(entry('smith2020', doi=DOI))
        self.publisher()
        self.out('file fetch --missing')
        self.assertEqual(self.web.downloads(), [PDF])
