"""papers file fix, check and fetch: the file of a broken link found in the
library itself by checksum, in its pool, and in the other libraries of the
machine (the places of the history store) by checksum"""
import io
import os
import shutil
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from papers.config import short_home
from papers.otherlibs import OtherLibraries

from tests.test_file_fetch import FetchTest
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

    def found_in_other(self):
        return f'(found in {short_home(self.path("other"))})'

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
        self.lost('one2000', 'pdf doe')  # another title, no DOI: by checksum
        out = self.out('file check')
        self.assertIn(f'one2000: broken link: {short_home(self.path("lib", "files", "one2000.pdf"))} -> '
                      f'{short_home(self.other_pdf)} {self.found_in_other()}', out)
        out = self.out('file fix')
        self.assertIn(self.found_in_other(), out)
        file, = self.files('one2000')
        self.assertEqual(os.path.dirname(file), self.path('lib', 'files'))
        self.assertEqual(Path(file).read_text(), 'pdf doe')
        self.assertOtherUnchanged()

    def test_same_paper_without_checksum_not_taken(self):
        # the same DOI as doe2020 of other/, no checksum recorded for the link: other/ is not searched
        self.bib(entry('doe2020a', self.path('gone', 'ice.pdf'), doi='10.1000/doe'))
        out = self.out('file fix')
        self.assertIn('0 links relinked, 1 still broken', out)

    def test_other_content_not_taken(self):
        self.lost('one2000', 'pdf other')
        self.assertIn('0 links relinked, 1 still broken', self.out('file fix'))

    def test_move_setting_copies(self):
        self.lib('config files move')
        self.lost('one2000', 'pdf doe')
        self.out('file fix')
        file, = self.files('one2000')
        self.assertEqual(os.path.dirname(file), self.path('lib', 'files'))
        self.assertTrue(os.path.exists(self.other_pdf))
        self.assertOtherUnchanged()

    def test_gone_library_skipped(self):
        shutil.move(self.path('other'), self.path('moved'))
        self.lost('one2000', 'pdf doe')
        out = self.out('file fix')
        self.assertIn('0 links relinked, 1 still broken', out)

    def test_dry_run(self):
        self.lost('one2000', 'pdf doe')
        before = self.bibtext()
        out = self.out('file fix --dry-run')
        self.assertIn(f'DRYRUN: one2000: relink {short_home(self.path("lib", "files", "one2000.pdf"))} -> '
                      f'{short_home(self.other_pdf)} {self.found_in_other()}', out)
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

    def test_missing_without_pdf_link_downloads(self):
        # the same paper in other/ with a PDF: not looked for, downloaded
        self.bib(entry('doe2020a', doi='10.1000/doe'))
        self.out('file fetch --missing')
        self.assertEqual(len(self.web.downloads()), 1)
        file, = self.files('doe2020a')
        self.assertTrue(Path(file).read_bytes().startswith(b'%PDF'))
        self.assertOtherUnchanged()

    def test_missing_broken_link_by_checksum(self):
        self.lost('doe2020a', 'pdf doe', doi='10.1000/doe')
        out = self.out('file fetch --missing')
        self.assertIn('not downloaded', out)
        self.assertEqual(self.web.downloads(), [])
        self.assertEqual(Path(self.files('doe2020a')[0]).read_text(), 'pdf doe')
        self.assertOtherUnchanged()

    def test_key_still_downloads(self):
        self.bib(entry('doe2020a', doi='10.1000/doe'))
        self.out('file fetch doe2020a')
        self.assertEqual(len(self.web.downloads()), 1)
        file, = self.files('doe2020a')
        self.assertTrue(Path(file).read_bytes().startswith(b'%PDF'))


class TestOtherLibraries(OtherLibrariesTest):
    """the other libraries are searched by checksum, as the
    .papers/files.json of the head state of each place has it
    (papers.otherlibs.OtherLibraries), read once per command when needed"""

    def setUp(self):
        super().setUp()
        self.read = []  # the places whose files.json was read
        checksums = OtherLibraries.checksums

        def counted(project, n, place):
            self.read.append(place)
            return checksums(project, n, place)
        patcher = mock.patch.object(OtherLibraries, 'checksums', staticmethod(counted))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_nothing_broken_nothing_searched(self):
        self.write('lib', 'files', 'ice.pdf', content='pdf')
        self.bib(entry('doe2020a', 'files/ice.pdf', doi='10.1000/doe'))
        self.publisher(doi='10.1000/doe')
        with mock.patch.object(OtherLibraries, 'places', side_effect=AssertionError('searched')):
            self.out('file check')
            self.out('file fix')
            self.out('file fetch --missing --dry-run')
        self.assertEqual(self.read, [])

    def test_no_checksum_nothing_searched(self):
        self.bib(entry('doe2020a', self.path('gone', 'ice.pdf'), doi='10.1000/doe'))
        self.out('file check')
        self.assertEqual(self.read, [])

    def test_place_read_once_per_command(self):
        self.lost('one2000', 'pdf doe')
        self.write('lib', 'files', 'two.pdf', content='pdf two')
        Path(self.path('lib', 'papers.bib')).write_text(
            entry('one2000', 'files/one2000.pdf') + entry('two2000', 'files/two.pdf', title='Two'))
        self.lib('file checksum')
        os.remove(self.path('lib', 'files', 'two.pdf'))
        self.assertIn(self.found_in_other(), self.out('file check'))
        # other/ only (lib/ is the library itself), once for the two broken links
        self.assertEqual(self.read, [os.path.realpath(self.path('other', 'papers.bib'))])
        self.out('file check')
        self.assertEqual(len(self.read), 2)  # read again by the next command

    def test_no_file_index_in_cache(self):
        import papers.config
        self.lost('one2000', 'pdf doe')
        self.assertIn(self.found_in_other(), self.out('file fix'))
        self.assertFalse(os.path.exists(os.path.join(papers.config.CACHE_DIR, 'file-index')))

    def test_new_head_seen(self):
        self.lost('one2000', 'pdf doe')
        self.out('file check')
        # a new file in other/, recorded by a command there: found at the next search
        new = self.write('other', 'files', 'new.pdf', content='pdf new')
        Path(self.path('other', 'papers.bib')).write_text(
            entry('doe2020', 'files/doe.pdf', doi='10.1000/doe', author='Doe, Jane', title='Ice')
            + entry('new2020', 'files/new.pdf'))
        self.papers('file checksum', cwd=self.path('other'))
        self.lost('two2000', 'pdf new')
        self.assertIn(f'-> {short_home(new)} {self.found_in_other()}', self.out('file check'))

    def test_edit_outside_papers_seen_after_a_command(self):
        new = self.write('other', 'files', 'new.pdf', content='pdf new')
        Path(self.path('other', 'papers.bib')).write_text(
            entry('doe2020', 'files/doe.pdf', doi='10.1000/doe', author='Doe, Jane', title='Ice')
            + entry('new2020', 'files/new.pdf'))
        self.lost('two2000', 'pdf new')
        self.assertIn('0 links relinked, 1 still broken', self.out('file fix --dry-run'))  # not in the head state
        self.papers('file checksum', cwd=self.path('other'))
        self.assertIn(f'-> {short_home(new)} {self.found_in_other()}', self.out('file check'))

    def test_missing_file_skipped(self):
        self.lost('one2000', 'pdf doe')
        os.remove(self.other_pdf)  # still in the files.json of the head state of other/
        self.assertIn('0 links relinked, 1 still broken', self.out('file fix'))

    def test_changed_content_skipped(self):
        self.lost('one2000', 'pdf doe')
        Path(self.other_pdf).write_text('pdf changed')
        self.assertIn('0 links relinked, 1 still broken', self.out('file fix'))

    def test_gone_place_skipped(self):
        self.lost('one2000', 'pdf doe')
        self.out('file check')
        shutil.move(self.path('other'), self.path('moved'))
        self.assertIn('0 links relinked, 1 still broken', self.out('file fix'))
        self.assertNotIn(os.path.realpath(self.path('other', 'papers.bib')), self.read[1:])
