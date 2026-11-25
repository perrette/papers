"""The network part of a command runs without the lock of the library; the
command then takes the lock, reads the library again and applies its
results to that state (papers.lock, papers.cli.common.lock_library):
papers file fetch and papers add, with the network mocked."""
import io
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import papers.backup
import papers.lock
from papers.config import Config
from papers.utils import PapersExit
from tests.common import entry
from tests.test_file_fetch import DOI, PDF, FetchTest, pdf_bytes


class LockTest(FetchTest):

    def setUp(self):
        super().setUp()
        self.bib(entry('smith2020', doi=DOI), entry('other2000'))
        self.lib('tag other2000 --add seed')  # the library has a state of its own
        self.publisher()

    def lock_file(self):
        return self.path('lib', '.papers', 'lock')

    def assert_unlocked(self):
        self.assertFalse(os.path.exists(self.lock_file()))
        self.assertEqual(papers.lock.held(), [])

    def other_command(self, cmd):
        "another command, run while this one is in its network part"
        argv = sys.argv[:]
        try:
            self.lib(cmd)
        finally:
            sys.argv[:] = argv  # the message of the step of this command

    def during_download(self, fun):
        "fun() runs at the first download of a file, before its answer"
        get_file, done = self.web.get_file, []

        def get(url, **kw):
            if not done:
                done.append(url)
                fun()
            return get_file(url, **kw)
        patcher = mock.patch('requests.get', get)
        patcher.start()
        self.addCleanup(patcher.stop)

    def steps(self):
        "the messages of the steps of the library, the last first"
        config = Config.load(self.path('lib', '.papers', 'config.json'))
        project, place = papers.backup.project_of(config, create=False)
        return [project.state(n)['message'] for n in project.line(project.head(place)['state'])]

    def tags(self, key):
        return Path(self.path('lib', 'papers.bib')).read_text().split(f'{{{key},')[1].split('\n}')[0]


class TestFileFetch(LockTest):

    def test_not_locked_during_the_download(self):
        self.during_download(self.assert_unlocked)
        self.lib('file fetch smith2020')
        self.assertEqual(len(self.files('smith2020')), 1)
        self.assertFalse(os.path.exists(self.lock_file()))

    def test_library_changed_during_the_download(self):
        # the change of the other command is kept, as a step of its own
        self.during_download(lambda: self.other_command('tag other2000 --add x'))
        self.lib('file fetch smith2020')
        self.assertIn('x', self.tags('other2000'))
        self.assertEqual(len(self.files('smith2020')), 1)
        self.assertEqual(self.steps()[:3], ['papers file fetch smith2020', 'papers tag other2000 --add x',
                                            'papers tag other2000 --add seed'])
        self.lib('undo')
        self.assertEqual(self.files('smith2020'), [])
        self.assertIn('x', self.tags('other2000'))

    def test_entry_removed_during_the_download(self):
        # nothing attached to the entry removed (exit 1); the other entry gets its PDF
        self.bib(entry('smith2020', doi=DOI), entry('gone2000', doi='10.1000/gone'))
        self.publisher(doi='10.1000/gone', pdf='https://journals.example.org/gone.pdf')
        self.during_download(lambda: self.other_command('rm gone2000 -y'))
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(PapersExit):
            self.lib('file fetch smith2020 gone2000')
        self.assertIn('gone2000: no longer in the library (removed, or its key changed, since the download): '
                      'nothing attached\n', out.getvalue())
        self.assertNotIn('gone2000', self.bibtext())
        self.assertEqual(len(self.files('smith2020')), 1)
        self.assertEqual(self.libfiles(), [os.path.basename(self.files('smith2020')[0])])
        self.assertEqual(self.downloads_left(), [])

    def test_entry_got_a_pdf_during_the_download(self):
        mine = self.write('src', 'mine.pdf', content='mine')
        self.during_download(lambda: self.other_command(f'file attach smith2020 {mine}'))
        out = self.out('file fetch smith2020')
        self.assertIn(f'smith2020: has a PDF now (since the download): {PDF} not attached', out)
        files = self.files('smith2020')
        self.assertEqual(len(files), 1)
        self.assertEqual(Path(files[0]).read_text(), 'mine')
        self.assertEqual(self.libfiles(), [])  # linked where it is, as attach left it
        self.assertEqual(self.downloads_left(), [])

    def test_same_file_linked_during_the_download(self):
        # the downloaded PDF is now a file of another entry: linked, not attached twice
        same = self.write('src', 'same.pdf')
        Path(same).write_bytes(pdf_bytes(PDF))
        self.during_download(lambda: self.other_command(f'file attach other2000 {same}'))
        out = self.out('file fetch smith2020')
        self.assertIn('same file as other2000', out)
        self.assertEqual(self.files('smith2020'), self.files('other2000'))
        self.assertEqual(self.libfiles(), [])  # linked where it is, as attach left it
        self.assertEqual(self.downloads_left(), [])

    def test_interrupted_during_the_downloads(self):
        self.bib(entry('smith2020', doi=DOI), entry('next2000', doi='10.1000/next'))
        self.publisher(doi='10.1000/next', pdf='https://journals.example.org/next.pdf')
        before = self.bibtext()
        get_file = self.web.get_file

        def get(url, **kw):
            if url.endswith('next.pdf'):
                raise KeyboardInterrupt
            return get_file(url, **kw)
        with mock.patch('requests.get', get), self.assertRaises(KeyboardInterrupt):
            self.lib('file fetch smith2020 next2000')
        self.assertEqual(self.bibtext(), before)
        self.assertEqual(self.libfiles(), [])
        self.assertEqual(self.downloads_left(), [])  # that of smith2020 too
        self.assertFalse(os.path.exists(self.lock_file()))

    def test_lock_waited_for_after_the_downloads(self):
        # the lock taken by another command during the download: the attachment waits for it
        def other():
            papers.lock._create(self.lock_file(), {'token': 'other', 'pid': -1, 'host': 'elsewhere'})
        self.during_download(other)
        with mock.patch.object(papers.lock, 'WAIT', 0), self.assertRaises(papers.lock.LockError):
            self.lib('file fetch smith2020')
        os.remove(self.lock_file())
        self.assertEqual(self.files('smith2020'), [])
        self.assertEqual(self.libfiles(), [])
        self.assertEqual(self.downloads_left(), [])


FETCHED = ('@article{fetched2000,\n author = {Fetched, Author},\n doi = {10.1000/fetched},\n'
           ' title = {Fetched title},\n year = {2000}\n}\n')


class TestAdd(LockTest):

    def test_pdf_metadata_fetched_before_the_lock(self):
        pdf = self.write('src', 'paper.pdf')
        prefetch = mock.Mock(side_effect=lambda *a, **k: self.assert_unlocked())
        with mock.patch('papers.cli.entry_cmds.prefetch_pdf_metadata', prefetch), \
                mock.patch('papers.bib.extract_pdf_metadata', return_value=FETCHED):
            self.lib(f'add {pdf}')
        prefetch.assert_called_once()  # also for one PDF
        self.assertEqual(prefetch.call_args[0][0], [pdf])
        self.assertIn('fetched2000', self.bibtext())

    def test_doi_fetched_before_the_lock(self):
        fetch = mock.Mock(side_effect=lambda doi: (self.assert_unlocked(), FETCHED)[1])
        with mock.patch('papers.cli.entry_cmds.fetch_bibtex_by_doi', fetch), \
                mock.patch('papers.bib.fetch_bibtex_by_doi', return_value=FETCHED):
            self.lib('add --doi 10.1000/fetched')
        fetch.assert_called_once_with('10.1000/fetched')
        self.assertIn('fetched2000', self.bibtext())

    def test_library_changed_during_the_lookup(self):
        def fetch(doi):
            self.other_command('tag other2000 --add x')
            return FETCHED
        with mock.patch('papers.cli.entry_cmds.fetch_bibtex_by_doi', fetch), \
                mock.patch('papers.bib.fetch_bibtex_by_doi', return_value=FETCHED):
            self.lib('add --doi 10.1000/fetched')
        self.assertIn('x', self.tags('other2000'))
        self.assertIn('fetched2000', self.bibtext())
        self.assertEqual(self.steps()[:2], ['papers add --doi 10.1000/fetched', 'papers tag other2000 --add x'])
