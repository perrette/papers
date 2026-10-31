"""papers file fetch, add --fetch-pdf, fetch --pdf: the free PDF of an entry, with the network mocked"""
import io
import os
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import papers.config
from papers import freepdf, openalex
from papers.utils import PapersExit
from tests.common import FileTest, entry

DOI = '10.1000/ocean'
PAGE = 'https://journals.example.org/article/ocean'
PDF = 'https://journals.example.org/article/ocean.pdf'
BIBTEX = ('@article{smith2020,\n author = {Smith, Ann},\n doi = {10.1000/ocean},\n'
          ' journal = {Ocean},\n title = {The ocean},\n year = {2020}\n}\n')


def pdf_bytes(name):
    return b'%PDF-1.4\n' + name.encode() + b'\n%%EOF\n'


def page(pdf=None, links=(), meta=()):
    head = f'<meta name="citation_pdf_url" content="{pdf}">' if pdf else ''
    head += ''.join(f'<meta name="citation_supplementary_material" content="{url}">' for url in meta)
    body = ''.join(f'<a href="{url}">{text}</a>' for url, text in links)
    return f'<html><head>{head}</head><body>{body}</body></html>'


def location(pdf_url, version, landing=None, is_oa=True):
    return {'pdf_url': pdf_url, 'landing_page_url': landing, 'version': version, 'is_oa': is_oa,
            'source': {'display_name': 'somewhere'}}


class Response:
    def __init__(self, status_code=200, text='', url='', content=b'', headers=None, json=None):
        self.status_code, self.text, self.url, self.content = status_code, text, url, content
        self.headers = headers or {}
        self._json = json
        self.ok = status_code < 400

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.exceptions.HTTPError(f'{self.status_code} Error for url: {self.url}', response=self)


class Web:
    """the sites: pages {url: (final url, html)}, openalex {doi: [locations] or None (404)}, ids {doi:
    ids of the work}, files {url: bytes, an HTTP status, (status, headers), or a list of these, the
    answers in turn}; the requests are in `requests`"""

    def __init__(self, test):
        self.pages, self.openalex, self.files, self.ids = {}, {}, {}, {}
        self.requests = []
        for target, fun in [('papers.fetch.http_get', self.get_page), ('papers.openalex.http_get', self.get_work),
                            ('requests.get', self.get_file)]:
            patcher = mock.patch(target, fun)
            patcher.start()
            test.addCleanup(patcher.stop)

    def get_page(self, url, **kw):
        self.requests.append(('page', url, kw.get('headers')))
        if url not in self.pages:
            return Response(404, url=url)
        final, html = self.pages[url]
        return Response(200, text=html, url=final, headers={'content-type': 'text/html'})

    def get_work(self, url, params=None, **kw):
        self.requests.append(('openalex', url, params))
        doi = url.split('/works/doi:', 1)[1]
        if self.openalex.get(doi) is None:
            return Response(404, json={'error': 'not found'})
        return Response(200, json={'id': 'https://openalex.org/W1', 'locations': self.openalex[doi],
                                   'ids': self.ids.get(doi, {})})

    def get_file(self, url, headers=None, **kw):
        self.requests.append(('file', url, headers))
        content = self.files.get(url, 404)
        if isinstance(content, list):  # the answers of the requests in turn
            content = content.pop(0) if len(content) > 1 else content[0]
        if isinstance(content, tuple):  # (HTTP status, headers)
            return Response(content[0], url=url, headers={'content-type': 'text/html', **content[1]})
        if isinstance(content, int):
            return Response(content, url=url, headers={'content-type': 'text/html'})
        if content.startswith(b'%PDF'):
            return Response(200, url=url, content=content, headers={'content-type': 'application/pdf'})
        return Response(200, url=url, content=content, headers={'content-type': 'text/html'})

    def downloads(self):
        return [url for kind, url, _ in self.requests if kind == 'file']


class FetchTest(FileTest):

    def setUp(self):
        super().setUp()
        self.lib('config filesdir files')
        cache = tempfile.TemporaryDirectory()
        self.addCleanup(cache.cleanup)
        old = papers.config.CACHE_DIR
        papers.config.CACHE_DIR = cache.name
        self.addCleanup(setattr, papers.config, 'CACHE_DIR', old)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for name in (openalex.API_KEY_ENV, openalex.MAILTO_ENV):
            os.environ.pop(name, None)
        for target in ('papers.freepdf._wait', 'papers.openalex._throttle'):
            patcher = mock.patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.web = Web(self)
        self.temp_before = self.temp_downloads()

    def publisher(self, doi=DOI, pdf=PDF, content=None, links=(), meta=()):
        "the article page of the DOI, with its PDF"
        self.web.pages['https://doi.org/' + doi] = (PAGE + doi, page(pdf, links, meta))
        if pdf:
            self.web.files[pdf] = pdf_bytes(pdf) if content is None else content

    def bibtext(self):
        return Path(self.path('lib', 'papers.bib')).read_text()

    @staticmethod
    def temp_downloads():
        return {d for d in os.listdir(tempfile.gettempdir()) if d.startswith('papers_dl_')}

    def downloads_left(self):
        "the temporary folders of the downloads that the test left"
        return sorted(self.temp_downloads() - self.temp_before)


class TestVersions(FetchTest):

    def setUp(self):
        super().setUp()
        self.bib(entry('smith2020', doi=DOI))

    def test_published_version_from_the_publisher(self):
        self.publisher()
        out = self.out('file fetch smith2020')
        file, = self.files('smith2020')
        self.assertTrue(file.startswith(self.path('lib', 'files')))
        self.assertEqual(Path(file).read_bytes(), pdf_bytes(PDF))
        self.assertIn(f'smith2020: files/{os.path.basename(file)} (published version, from journals.example.org)',
                      out)
        self.assertFalse([r for r in self.web.requests if r[0] == 'openalex'])  # not needed
        # papers says what it is
        agent = next(h for kind, _, h in self.web.requests if kind == 'file')['User-Agent']
        self.assertTrue(agent.startswith(f'papers/{papers.__version__} '))

    def test_publisher_refuses_then_openalex_published_before_accepted(self):
        self.publisher(content=b'<html>login</html>')
        self.web.openalex[DOI] = [location('https://repo.example.edu/am.pdf', 'acceptedVersion'),
                                  location('https://pmc.example.gov/vor.pdf', 'publishedVersion'),
                                  location('https://closed.example.com/x.pdf', 'publishedVersion', is_oa=False)]
        self.web.files['https://repo.example.edu/am.pdf'] = pdf_bytes('am')
        self.web.files['https://pmc.example.gov/vor.pdf'] = pdf_bytes('vor')
        out = self.out('file fetch smith2020')
        self.assertIn('(published version, from pmc.example.gov)', out)
        self.assertEqual(Path(self.files('smith2020')[0]).read_bytes(), pdf_bytes('vor'))
        self.assertEqual(self.web.downloads(), [PDF, 'https://pmc.example.gov/vor.pdf'])

    def test_accepted_then_submitted(self):
        self.publisher(pdf=None)
        self.web.openalex[DOI] = [location('https://preprints.example.org/s.pdf', 'submittedVersion'),
                                  location('https://repo.example.edu/am.pdf', 'acceptedVersion')]
        self.web.files['https://repo.example.edu/am.pdf'] = 403
        self.web.files['https://preprints.example.org/s.pdf'] = pdf_bytes('s')
        out = self.out('file fetch smith2020')
        self.assertIn('(submitted version, from preprints.example.org)', out)
        self.assertEqual(self.web.downloads(), ['https://repo.example.edu/am.pdf', 'https://preprints.example.org/s.pdf'])

    def test_version_published_refuses_the_others(self):
        self.publisher(pdf=None)
        self.web.openalex[DOI] = [location('https://repo.example.edu/am.pdf', 'acceptedVersion',
                                           landing='https://repo.example.edu/am')]
        self.web.files['https://repo.example.edu/am.pdf'] = pdf_bytes('am')
        with self.assertLogs('papers', 'ERROR') as logs, self.assertRaises(PapersExit):
            self.lib('file fetch smith2020 --version published')
        self.assertEqual(self.files('smith2020'), [])
        self.assertEqual(self.web.downloads(), [])
        message = '\n'.join(logs.output)
        self.assertIn('smith2020: no free PDF found', message)
        self.assertIn('open in a browser: https://doi.org/10.1000/ocean, https://repo.example.edu/am', message)

    def test_none_works_the_links_to_open_and_the_others_attached(self):
        self.bib(entry('smith2020', doi=DOI), entry('other2020', doi='10.1000/other'))
        self.publisher(content=b'<html>a challenge</html>')
        self.web.openalex[DOI] = []
        self.publisher(doi='10.1000/other', pdf='https://journals.example.org/other.pdf')
        err = io.StringIO()
        with redirect_stderr(err), self.assertNoLogs('papers', 'ERROR'), self.assertRaises(PapersExit):
            self.lib('file fetch smith2020 other2020')
        # several entries: one line for the entry without PDF, not an error
        self.assertIn(f'smith2020: no PDF ({PDF} (published version): not a PDF; OpenAlex: no open-access PDF; '
                      f'open {PDF}, https://doi.org/{DOI} in a browser)\n', err.getvalue())
        self.assertNotIn('error', err.getvalue())
        self.assertEqual(self.files('smith2020'), [])
        self.assertEqual(len(self.files('other2020')), 1)  # saved
        self.assertEqual(self.downloads_left(), [])

    def test_published_refused_gives_its_link(self):
        # library.md "The free PDF of an entry": an accepted version attached after the published one was
        # refused: the message gives the published link to open in a browser
        self.publisher(content=403)
        self.web.openalex[DOI] = [location('https://repo.example.edu/am.pdf', 'acceptedVersion')]
        self.web.files['https://repo.example.edu/am.pdf'] = pdf_bytes('am')
        out = self.out('file fetch smith2020')
        file, = self.files('smith2020')
        self.assertIn(f'smith2020: files/{os.path.basename(file)} (accepted manuscript, from repo.example.edu; '
                      f'the published version was refused: open {PDF} in a browser)', out)

    def test_publisher_page_refused_gives_its_link(self):
        # the publisher's page itself refused (no PDF link): the page is the link to open
        self.bib('@article{arx2021,\n doi = {10.1000/ocean},\n eprint = {2101.01234},\n title = {T},\n'
                 ' year = {2021}\n}\n')
        self.web.openalex[DOI] = []
        self.web.files['https://arxiv.org/pdf/2101.01234'] = pdf_bytes('arxiv')
        out = self.out('file fetch arx2021')
        self.assertIn('(submitted version, from arxiv.org; the published version was refused: '
                      f'open https://doi.org/{DOI} in a browser)', out)

    def test_no_published_link_says_nothing(self):
        # the page gave no PDF link and OpenAlex no published location: nothing was refused
        self.publisher(pdf=None)
        self.web.openalex[DOI] = [location('https://repo.example.edu/am.pdf', 'acceptedVersion')]
        self.web.files['https://repo.example.edu/am.pdf'] = pdf_bytes('am')
        out = self.out('file fetch smith2020')
        self.assertIn('(accepted manuscript, from repo.example.edu)', out)
        self.assertNotIn('refused', out)

    def test_arxiv(self):
        self.bib('@article{arx2021,\n eprint = {2101.01234},\n archiveprefix = {arXiv},\n title = {T},\n'
                 ' year = {2021}\n}\n')
        self.web.files['https://arxiv.org/pdf/2101.01234'] = pdf_bytes('arxiv')
        out = self.out('file fetch arx2021')
        self.assertIn('(submitted version, from arxiv.org)', out)
        self.assertEqual(Path(self.files('arx2021')[0]).read_bytes(), pdf_bytes('arxiv'))
        self.assertEqual(self.web.downloads(), ['https://arxiv.org/pdf/2101.01234'])

    def test_arxiv_after_the_doi(self):
        self.bib('@article{arx2021,\n doi = {10.1000/ocean},\n eprint = {2101.01234},\n title = {T},\n'
                 ' year = {2021}\n}\n')
        self.publisher(pdf=None)
        self.web.openalex[DOI] = []
        self.web.files['https://arxiv.org/pdf/2101.01234'] = pdf_bytes('arxiv')
        self.assertIn('(submitted version, from arxiv.org)', self.out('file fetch arx2021'))
        self.assertEqual(self.web.downloads(), ['https://arxiv.org/pdf/2101.01234'])

    def test_no_identifier(self):
        self.bib(entry('nodoi2000'))
        with self.assertLogs('papers', 'ERROR') as logs, self.assertRaises(PapersExit):
            self.lib('file fetch nodoi2000')
        self.assertIn('nodoi2000: no DOI or arXiv id', '\n'.join(logs.output))

    def test_openalex_not_found_is_cached(self):
        self.publisher(pdf=None)
        for _ in range(2):
            with self.assertLogs('papers', 'ERROR'), self.assertRaises(PapersExit):
                self.lib('file fetch smith2020')
        self.assertEqual(len([r for r in self.web.requests if r[0] == 'openalex']), 1)


class TestMoreSources(FetchTest):
    """library.md "The free PDF of an entry": the landing pages of OpenAlex (repositories), Europe PMC,
    and the retry after HTTP 429"""

    REPO = 'https://repo.example.edu/handle/1'
    REPO_PDF = 'https://repo.example.edu/bitstream/1/paper.pdf'

    def setUp(self):
        super().setUp()
        self.bib(entry('smith2020', doi=DOI))
        self.publisher(content=b'<html>a check page</html>')
        sleep = mock.patch('papers.freepdf.time.sleep')
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def test_landing_page_citation_pdf_url(self):
        self.web.openalex[DOI] = [location(None, 'acceptedVersion', landing=self.REPO),
                                  location('https://preprints.example.org/s.pdf', 'submittedVersion')]
        self.web.pages[self.REPO] = (self.REPO, page('/bitstream/1/paper.pdf'))
        self.web.files[self.REPO_PDF] = pdf_bytes('am')
        out = self.out('file fetch smith2020')
        self.assertIn('(accepted manuscript, from repo.example.edu; the published version was refused', out)
        self.assertEqual(Path(self.files('smith2020')[0]).read_bytes(), pdf_bytes('am'))
        self.assertEqual(self.web.downloads(), [PDF, self.REPO_PDF])
        agent = next(h for kind, url, h in self.web.requests if url == self.REPO)['User-Agent']
        self.assertTrue(agent.startswith('papers/'))

    def test_landing_page_of_a_repository_doi_follows_the_redirection(self):
        landing = 'https://doi.org/10.34657/351'
        self.web.openalex[DOI] = [location(None, 'publishedVersion', landing=landing)]
        self.web.pages[landing] = (self.REPO, page('/bitstream/1/paper.pdf'))
        self.web.files[self.REPO_PDF] = pdf_bytes('vor')
        self.assertIn('(published version, from repo.example.edu)', self.out('file fetch smith2020'))

    def test_landing_page_without_the_tag_is_to_open(self):
        self.web.openalex[DOI] = [location(None, 'acceptedVersion', landing=self.REPO)]
        self.web.pages[self.REPO] = (self.REPO, page(links=[('/bitstream/1/paper.pdf', 'PDF')]))
        with self.assertLogs('papers', 'ERROR') as logs, self.assertRaises(PapersExit):
            self.lib('file fetch smith2020')
        message = '\n'.join(logs.output)
        self.assertIn('repo.example.edu: no PDF link on the landing page', message)
        self.assertIn(f'open in a browser: {PDF}, https://doi.org/{DOI}, {self.REPO}', message)
        self.assertEqual(self.web.downloads(), [PDF])  # no other link of the page

    def test_landing_page_of_the_publisher_is_not_read_again(self):
        self.web.openalex[DOI] = [location(None, 'publishedVersion', landing='https://doi.org/' + DOI)]
        with self.assertLogs('papers', 'ERROR'), self.assertRaises(PapersExit):
            self.lib('file fetch smith2020')
        self.assertEqual(len([r for r in self.web.requests if r[0] == 'page']), 1)

    def test_europe_pmc_before_pmc(self):
        pmc = 'https://pmc.ncbi.nlm.nih.gov/articles/PMC10495961/pdf/x.pdf'
        europe = 'https://europepmc.org/articles/PMC10495961?pdf=render'
        self.web.openalex[DOI] = [location(pmc, 'publishedVersion',
                                           landing='https://pmc.ncbi.nlm.nih.gov/articles/PMC10495961'),
                                  location('https://repo.example.edu/am.pdf', 'acceptedVersion')]
        self.web.files[pmc] = b'<html>a check page</html>'
        self.web.files[europe] = pdf_bytes('vor')
        out = self.out('file fetch smith2020')
        self.assertIn('(published version, from europepmc.org)', out)
        self.assertEqual(self.web.downloads(), [PDF, europe])
        self.assertEqual([r for r in self.web.requests if r[0] == 'page'],  # the PMC page is not read
                         [('page', 'https://doi.org/' + DOI, mock.ANY)])

    def test_europe_pmc_of_the_openalex_ids(self):
        europe = 'https://europepmc.org/articles/PMC123?pdf=render'
        self.web.files[europe] = pdf_bytes('vor')
        self.web.ids[DOI] = {'pmcid': 'https://www.ncbi.nlm.nih.gov/pmc/articles/123'}
        self.web.openalex[DOI] = [location('https://repo.example.edu/am.pdf', 'acceptedVersion')]
        self.assertIn('(published version, from europepmc.org)', self.out('file fetch smith2020'))
        self.assertEqual(self.web.downloads(), [PDF, europe])

    def test_europe_pmc_of_the_pmcid_field(self):
        europe = 'https://europepmc.org/articles/PMC123?pdf=render'
        self.web.files[europe] = pdf_bytes('vor')
        self.bib('@article{nodoi2020,\n pmcid = {PMC123},\n title = {T},\n year = {2020}\n}\n')
        self.assertIn('(published version, from europepmc.org)', self.out('file fetch nodoi2020'))
        self.assertEqual(self.web.downloads(), [europe])

    def test_429_then_the_pdf(self):
        self.web.openalex[DOI] = [location('https://repo.example.edu/am.pdf', 'acceptedVersion')]
        self.web.files['https://repo.example.edu/am.pdf'] = [(429, {'Retry-After': '120'}), pdf_bytes('am')]
        with self.assertLogs('papers', 'DEBUG') as logs:
            out = self.out('file fetch smith2020')
        self.assertIn('(accepted manuscript, from repo.example.edu', out)
        self.sleep.assert_called_once_with(30)  # at most 30 s
        self.assertIn('https://repo.example.edu/am.pdf: HTTP 429, retried in 30 s', '\n'.join(logs.output))

    def test_429_twice_moves_on(self):
        self.web.openalex[DOI] = [location('https://repo.example.edu/am.pdf', 'acceptedVersion'),
                                  location('https://preprints.example.org/s.pdf', 'submittedVersion')]
        self.web.files['https://repo.example.edu/am.pdf'] = (429, {})
        self.web.files['https://preprints.example.org/s.pdf'] = pdf_bytes('s')
        self.assertIn('(submitted version, from preprints.example.org', self.out('file fetch smith2020'))
        self.sleep.assert_called_once_with(5)  # without Retry-After
        self.assertEqual(self.web.downloads(), [PDF, 'https://repo.example.edu/am.pdf',
                                                'https://repo.example.edu/am.pdf',
                                                'https://preprints.example.org/s.pdf'])

    def test_429_of_a_page(self):
        calls = []

        def fetch_html(url, headers=None):
            calls.append(url)
            if len(calls) == 1:
                Response(429, url=url, headers={'Retry-After': '2'}).raise_for_status()
            return page(PDF), url
        with mock.patch('papers.fetch.fetch_html', fetch_html):
            self.web.files[PDF] = pdf_bytes('vor')
            self.assertIn('(published version', self.out('file fetch smith2020'))
        self.assertEqual(calls, ['https://doi.org/' + DOI] * 2)
        self.sleep.assert_called_once_with(2)


class TestNoPdfMessages(FetchTest):
    "library.md \"The free PDF of an entry\": one entry without PDF is an error, of several a line each"

    def setUp(self):
        super().setUp()
        self.bib(entry('smith2020', doi=DOI), entry('nodoi2000'))
        self.publisher(pdf=None)
        self.web.openalex[DOI] = []

    def test_one_entry_is_an_error(self):
        with self.assertLogs('papers', 'ERROR') as logs, self.assertRaises(PapersExit):
            self.lib('file fetch smith2020')
        self.assertIn('ERROR:papers:smith2020: no free PDF found', logs.output[0])

    def test_several_entries_a_line_each(self):
        err, out = io.StringIO(), io.StringIO()
        with redirect_stderr(err), redirect_stdout(out), self.assertNoLogs('papers', 'ERROR'), \
                self.assertRaises(PapersExit):
            self.lib('file fetch smith2020 nodoi2000')
        self.assertEqual(err.getvalue(),
                         'smith2020: no PDF (journals.example.org: no PDF link on the article page; '
                         f'OpenAlex: no open-access PDF; open https://doi.org/{DOI} in a browser)\n'
                         'nodoi2000: no PDF (no DOI or arXiv id to look for a PDF)\n')
        self.assertIn('summary of 2 entries:', out.getvalue())


class TestSelection(FetchTest):

    def setUp(self):
        super().setUp()
        self.a = self.write('lib', 'files', 'a.pdf')
        self.bib(entry('has2000', 'files/a.pdf', doi='10.1000/has'), entry('smith2020', doi=DOI))
        self.publisher()

    def test_missing(self):
        out = self.out('file fetch --missing')
        self.assertEqual(self.files('has2000'), [self.a])
        self.assertEqual(len(self.files('smith2020')), 1)
        self.assertEqual(self.web.downloads(), [PDF])
        self.assertNotIn('has2000', out)

    def test_needs_entries_or_missing(self):
        with self.assertRaises(SystemExit):
            self.lib('file fetch')

    def test_dry_run_changes_nothing(self):
        before = self.bibtext()
        out = self.out('file fetch --missing --dry-run')
        self.assertIn(f'DRYRUN: smith2020: would download {PDF} (published version, from journals.example.org)', out)
        self.assertEqual(self.bibtext(), before)
        self.assertEqual(self.web.downloads(), [])
        self.assertEqual(self.libfiles(), ['a.pdf'])

    def test_has_a_pdf_already(self):
        self.publisher(doi='10.1000/has', pdf='https://journals.example.org/has.pdf')
        out = self.out('file fetch has2000')
        self.assertIn('has2000: has a PDF already (--again to fetch it anyway)', out)
        self.assertEqual(self.web.downloads(), [])
        self.out('file fetch has2000 --again')
        self.assertEqual(len(self.files('has2000')), 2)

    def test_broken_link_is_no_pdf(self):
        "an entry whose PDF link is broken is fetched, by name and with --missing"
        os.remove(self.a)
        self.publisher(doi='10.1000/has', pdf='https://journals.example.org/has.pdf')
        out = self.out('file fetch --missing')
        self.assertNotIn('has a PDF already', out)
        self.assertIn('https://journals.example.org/has.pdf', self.web.downloads())

    def test_porcelain(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.lib('file fetch smith2020 --porcelain')
        self.assertEqual(out.getvalue(), 'modified smith2020\n')

    def test_undo(self):
        self.lib('file fetch smith2020')
        self.assertEqual(len(self.files('smith2020')), 1)
        self.lib('undo')
        self.assertEqual(self.files('smith2020'), [])
        self.lib('redo')
        self.assertEqual(len(self.files('smith2020')), 1)


class TestSummary(FetchTest):
    "library.md \"The free PDF of an entry\": a fetch of several entries ends with a summary"

    def setUp(self):
        super().setUp()
        self.write('lib', 'files', 'a.pdf')
        self.write('downloads', 'old.pdf', content='pdf old')
        self.bib(entry('pub2020', doi='10.1000/pub'), entry('acc2020', doi='10.1000/acc'),
                 entry('none2020', doi='10.1000/none'), entry('old2020', 'files/old.pdf', doi='10.1000/old'),
                 entry('has2000', 'files/a.pdf', doi='10.1000/has'))
        self.publisher(doi='10.1000/pub', pdf='https://journals.example.org/pub.pdf')
        self.publisher(doi='10.1000/acc', pdf='https://journals.example.org/acc.pdf', content=403)
        self.web.openalex['10.1000/acc'] = [location('https://repo.example.edu/acc.pdf', 'acceptedVersion')]
        self.web.files['https://repo.example.edu/acc.pdf'] = pdf_bytes('acc')
        self.publisher(doi='10.1000/none', pdf='https://journals.example.org/none.pdf', content=b'<html></html>')
        self.web.openalex['10.1000/none'] = []

    def test_missing(self):
        out = io.StringIO()
        with redirect_stderr(io.StringIO()), self.assertRaises(PapersExit), redirect_stdout(out):
            self.lib(f'file fetch --missing --search {self.path("downloads")}')
        out = out.getvalue()
        self.assertIn('summary of 4 entries:\n'
                      '  2 PDFs attached: 1 published version, 1 accepted manuscript\n'
                      '  1 found locally (repaired, not downloaded)\n'
                      '  1 without PDF\n'
                      'open in a browser:\n'
                      '  acc2020: https://journals.example.org/acc.pdf (published version refused; '
                      'accepted manuscript found)\n'
                      '  none2020: https://journals.example.org/none.pdf, https://doi.org/10.1000/none (no PDF)\n',
                      out)

    def test_refused_but_not_attached(self):
        # the accepted manuscript found is the file the entry has: counted once, as had, and not listed as refused
        Path(self.write('lib', 'files', 'acc.pdf')).write_bytes(pdf_bytes('acc'))
        self.bib(entry('pub2020', doi='10.1000/pub'), entry('acc2020', 'files/acc.pdf', doi='10.1000/acc'))
        out = self.out('file fetch pub2020 acc2020 --again')
        self.assertIn('acc2020: https://repo.example.edu/acc.pdf: not attached, the entry has the same file', out)
        self.assertIn('summary of 2 entries:\n'
                      '  1 PDF attached: 1 published version\n'
                      '  1 had the PDF already\n', out)
        self.assertNotIn('open in a browser', out.split('summary of')[1])

    def test_not_for_one_entry_or_a_dry_run(self):
        self.assertNotIn('summary', self.out('file fetch pub2020'))
        self.assertNotIn('summary', self.out(f'file fetch --missing --dry-run --search {self.path("downloads")}'))


class TestBrokenLinkRepair(FetchTest):
    "a broken PDF link gets the repair of `papers file fix` first; the download only if it gives no PDF"

    def setUp(self):
        super().setUp()
        self.old = self.path('lib', 'files', 'old.pdf')
        self.bib(entry('smith2020', 'files/old.pdf', doi=DOI))
        self.publisher()
        self.found = self.write('downloads', 'old.pdf', content='pdf old')

    def test_found_in_a_search_folder(self):
        # the files setting of the tests is link: linked where it is, as file fix does
        out = self.out('file fetch smith2020 --search ../downloads')
        self.assertRegex(out, r'smith2020: relinked \S+/downloads/old.pdf \(found in \S+/downloads\), not downloaded')
        self.assertEqual(self.files('smith2020'), [self.found])
        self.assertEqual(self.web.downloads(), [])

    def test_copied_into_the_files_directory(self):
        self.lib('config files copy')
        out = self.out('file fetch smith2020 --search ../downloads')
        file, = self.files('smith2020')
        self.assertIn(f'smith2020: relinked files/{os.path.basename(file)} (found in ', out)
        self.assertEqual(Path(file).read_text(), 'pdf old')
        self.assertEqual(os.path.dirname(file), self.path('lib', 'files'))
        self.assertTrue(os.path.exists(self.found))
        self.assertEqual(self.web.downloads(), [])

    def test_missing(self):
        out = self.out('file fetch --missing --search ../downloads')
        self.assertIn('not downloaded', out)
        self.assertEqual(self.web.downloads(), [])

    def test_restored_by_checksum(self):
        # deleted outside papers: its checksum in files.json, a copy of the same content in the history
        import papers.backup
        from papers.utils import checksum
        Path(self.old).write_text('pdf a')
        self.lib('file checksum')
        copy = self.write('copy.pdf', content='pdf a')
        papers.backup.Deleted(self.config()).store.put_file(copy, checksum(self.old).hex())
        os.remove(self.old)
        out = self.out('file fetch smith2020')
        self.assertIn('smith2020: files/old.pdf: restored from the history (deleted, its checksum known), '
                      'not downloaded', out)
        self.assertEqual(Path(self.old).read_text(), 'pdf a')
        self.assertEqual(self.files('smith2020'), [self.old])
        self.assertEqual(self.web.downloads(), [])

    def config(self):
        from papers.config import Config, CONFIG_FILE_LOCAL
        return Config.load(self.path('lib', CONFIG_FILE_LOCAL))

    def test_not_found_downloads(self):
        os.remove(self.found)
        out = self.out('file fetch smith2020 --search ../downloads')
        self.assertNotIn('relinked', out)
        self.assertEqual(self.web.downloads(), [PDF])
        self.assertEqual(len(self.files('smith2020')), 2)  # the broken link stays, as file fix leaves it

    def test_dry_run(self):
        before = self.bibtext()
        out = self.out('file fetch smith2020 --search ../downloads --dry-run')
        self.assertRegex(out, r'DRYRUN: smith2020: would relink files/old.pdf -> \S*downloads/old.pdf '
                              r'\(found in .*downloads\)')
        self.assertNotIn('would download', out)
        self.assertEqual(self.bibtext(), before)
        self.assertEqual(self.libfiles(), [])

    def test_again_downloads_too(self):
        out = self.out('file fetch smith2020 --search ../downloads --again')
        self.assertNotIn('not downloaded', out)
        self.assertEqual(self.web.downloads(), [PDF])
        self.assertEqual(len(self.files('smith2020')), 2)

    def test_one_step_with_the_downloads(self):
        self.bib(entry('smith2020', 'files/old.pdf', doi=DOI), entry('other2001', 'files/gone.pdf', doi='10.1000/b'))
        self.publisher(doi='10.1000/b', pdf='https://journals.example.org/b.pdf')
        self.lib('file fetch smith2020 other2001 --search ../downloads')
        self.assertEqual(self.web.downloads(), ['https://journals.example.org/b.pdf'])
        self.assertEqual(self.files('smith2020'), [self.found])
        self.assertEqual(len(self.libfiles()), 1)
        self.lib('undo')  # the relink and the download together
        self.assertEqual(self.files('smith2020'), [self.old])
        self.assertEqual(self.files('other2001'), [self.path('lib', 'files', 'gone.pdf')])
        self.lib('redo')
        self.assertEqual(self.files('smith2020'), [self.found])
        self.assertEqual(len(self.files('other2001')), 2)


class TestConfirmation(FetchTest):

    def setUp(self):
        super().setUp()
        self.bib(*[entry(f'e{i}x', doi=f'10.1000/e{i}') for i in range(51)])
        patcher = mock.patch('papers.cli.file_cmds.fetch_entry_pdfs', return_value=0)
        self.fetch = patcher.start()
        self.addCleanup(patcher.stop)

    def test_no_terminal_refuses(self):
        with mock.patch('papers.cli.file_cmds.stdin_is_terminal', return_value=False):
            with self.assertRaisesRegex(PapersExit, '51 entries with a DOI.*OPENALEX_API_KEY, pass -y/--yes'):
                self.lib('file fetch --missing')
        self.fetch.assert_not_called()

    def test_asks_in_a_terminal(self):
        with mock.patch('papers.cli.file_cmds.stdin_is_terminal', return_value=True):
            with mock.patch('builtins.input', return_value='n'), self.assertRaises(PapersExit):
                self.lib('file fetch --missing')
            self.fetch.assert_not_called()
            with mock.patch('builtins.input', return_value='y'):
                self.lib('file fetch --missing')
        self.fetch.assert_called_once()

    def test_yes_key_or_fewer_entries(self):
        with mock.patch('papers.cli.file_cmds.stdin_is_terminal', return_value=False):
            self.lib('file fetch --missing -y')
            os.environ[openalex.API_KEY_ENV] = 'key'
            self.lib('file fetch --missing')
            del os.environ[openalex.API_KEY_ENV]
            self.lib('file fetch ' + ' '.join(f'e{i}x' for i in range(51)))  # named: no question
            self.bib(*[entry(f'e{i}x', doi=f'10.1000/e{i}') for i in range(50)])
            self.lib('file fetch --missing')
        self.assertEqual(self.fetch.call_count, 4)


class TestSupplements(FetchTest):

    SUPPL = 'https://journals.example.org/article/ocean-supplement.pdf'
    TAGGED = 'https://journals.example.org/files/si-tables.pdf'

    def setUp(self):
        super().setUp()
        self.bib(entry('smith2020', doi=DOI))
        self.publisher(links=[(self.SUPPL, 'Supplement'), ('https://journals.example.org/data.zip', 'Supplement'),
                              ('https://journals.example.org/other.pdf', 'Other paper'),
                              ('https://journals.example.org/s2.pdf', 'Supplementary material')],
                       meta=[self.TAGGED])
        for url in (self.SUPPL, self.TAGGED):
            self.web.files[url] = pdf_bytes(url)
        self.web.files['https://journals.example.org/s2.pdf'] = b'<html>login</html>'

    def test_supplements(self):
        with self.assertLogs('papers', 'WARNING') as logs:
            out = self.out('file fetch smith2020 --supplements')
        main, tagged, suppl = self.files('smith2020')  # the tags first, then the links
        stem = os.path.splitext(os.path.basename(main))[0]
        self.assertEqual(os.path.basename(suppl), stem + '--ocean-supplement.pdf')
        self.assertEqual(os.path.basename(tagged), stem + '--si-tables.pdf')
        self.assertIn('(supplement, from journals.example.org)', out)
        self.assertIn('s2.pdf: not a PDF (not attached)', '\n'.join(logs.output))
        self.assertNotIn('https://journals.example.org/other.pdf', self.web.downloads())
        self.assertNotIn('https://journals.example.org/data.zip', self.web.downloads())

    def test_not_without_the_option(self):
        self.lib('file fetch smith2020')
        self.assertEqual(len(self.files('smith2020')), 1)

    def test_second_pass_with_supplements(self):
        self.lib('file fetch smith2020')
        self.web.requests.clear()
        out = self.out('file fetch smith2020 --supplements')
        self.assertIn('smith2020: has a PDF already', out)
        self.assertEqual(len(self.files('smith2020')), 3)
        self.assertNotIn(PDF, self.web.downloads())


class TestNoDuplicate(FetchTest):

    def setUp(self):
        super().setUp()
        self.bib(entry('smith2020', doi=DOI))
        self.publisher()

    def test_same_content_not_attached(self):
        # a file of the entry with the content of the PDF, which this machine did not download
        local = self.write('lib', 'files', 'mine.pdf')
        Path(local).write_bytes(pdf_bytes(PDF))
        self.bib(entry('smith2020', 'files/mine.pdf', doi=DOI))
        out = self.out('file fetch smith2020 --again')
        self.assertIn(f'smith2020: {PDF}: not attached, the entry has the same file: files/mine.pdf', out)
        self.assertEqual(self.files('smith2020'), [local])
        self.assertEqual(self.downloads_left(), [])

    def test_cache_a_the_entry_has_it(self):
        self.lib('file fetch smith2020')
        file, = self.files('smith2020')
        self.web.requests.clear()
        out = self.out('file fetch smith2020 --again')
        self.assertIn(f'smith2020: already has files/{os.path.basename(file)} (from journals.example.org)', out)
        self.assertEqual(self.web.downloads(), [])
        self.assertEqual(self.files('smith2020'), [file])

    def test_cache_b_another_entry_has_it(self):
        self.lib('file fetch smith2020')
        file, = self.files('smith2020')
        text = self.bibtext() + entry('copy2020', doi='10.1000/copy')
        Path(self.path('lib', 'papers.bib')).write_text(text)
        self.publisher(doi='10.1000/copy')  # the same PDF URL
        self.web.requests.clear()
        out = self.out('file fetch copy2020')
        self.assertEqual(self.web.downloads(), [])
        self.assertIn('same file as smith2020, not downloaded', out)
        self.assertEqual(self.files('copy2020'), [file])  # linked, not moved
        self.assertEqual(self.files('smith2020'), [file])

    def test_cache_c_a_miss_downloads(self):
        self.lib('file fetch smith2020')
        file, = self.files('smith2020')
        self.lib(f'file rm {file}')
        self.web.requests.clear()
        self.lib('file fetch smith2020')
        self.assertEqual(self.web.downloads(), [PDF])
        self.assertEqual(len(self.files('smith2020')), 1)

    def test_the_library_does_not_record_the_url(self):
        self.lib('file fetch smith2020')
        for root, _, files in os.walk(self.path('lib')):
            for name in files:
                path = os.path.join(root, name)
                if not name.endswith('.pdf'):
                    self.assertNotIn('journals.example.org', Path(path).read_text(errors='replace'), path)
        self.assertIsNotNone(freepdf.known_download(PDF))


class TestAddAndFetch(FetchTest):

    def test_add_doi_fetch_pdf(self):
        self.bib()
        self.publisher()
        with mock.patch('papers.bib.fetch_bibtex_by_doi', return_value=BIBTEX):
            out = self.out(f'add --doi {DOI} --fetch-pdf')
        key, = [line.split()[2].rstrip(':') for line in out.splitlines() if line.startswith('Added')]
        file, = self.files(key)
        self.assertEqual(Path(file).read_bytes(), pdf_bytes(PDF))
        self.assertIn('(published version, from journals.example.org)', out)
        self.lib('undo')
        self.assertEqual(self.bibtext().strip(), '')

    def test_add_fetch_pdf_failure_keeps_the_entry(self):
        self.bib()
        self.publisher(pdf=None)
        with mock.patch('papers.bib.fetch_bibtex_by_doi', return_value=BIBTEX):
            with self.assertLogs('papers', 'ERROR'), self.assertRaises(PapersExit):
                self.lib(f'add --doi {DOI} --fetch-pdf')
        self.assertIn('10.1000/ocean', self.bibtext())

    def test_add_fetch_pdf_needs_doi(self):
        with self.assertRaisesRegex(PapersExit, '--fetch-pdf goes with --doi'):
            self.lib('add --fetch-pdf --title x')

    def test_fetch_pdf_output(self):
        self.publisher()
        out = self.out(f'fetch --pdf {DOI} -o {self.path("paper.pdf")}')
        self.assertEqual(Path(self.path('paper.pdf')).read_bytes(), pdf_bytes(PDF))
        self.assertIn('paper.pdf (published version, from journals.example.org)', out)
        self.web.requests.clear()
        with self.assertRaisesRegex(PapersExit, 'exists: not replaced'):
            self.lib(f'fetch --pdf {DOI} -o {self.path("paper.pdf")}')
        self.assertEqual(self.web.requests, [])  # checked before the download
        self.assertEqual(self.downloads_left(), [])

    def test_fetch_pdf_into_the_current_directory(self):
        self.web.files['https://arxiv.org/pdf/2101.01234'] = pdf_bytes('arxiv')
        out = self.out('fetch --pdf arXiv:2101.01234')
        self.assertTrue(os.path.exists(self.path('lib', '2101.01234.pdf')))
        self.assertIn('2101.01234.pdf (submitted version, from arxiv.org)', out)

    def test_fetch_pdf_published_refused(self):
        self.publisher(content=b'<html>Just a moment...</html>')
        self.web.openalex[DOI] = [location('https://repo.example.edu/am.pdf', 'acceptedVersion')]
        self.web.files['https://repo.example.edu/am.pdf'] = pdf_bytes('am')
        out = self.out(f'fetch --pdf {DOI} -o {self.path("paper.pdf")}')
        self.assertIn(f'paper.pdf (accepted manuscript, from repo.example.edu; the published version was refused: '
                      f'open {PDF} in a browser)', out)

    def test_fetch_pdf_none(self):
        self.publisher(pdf=None)
        with self.assertRaisesRegex(PapersExit, f'^{DOI}: no free PDF found'):
            self.lib(f'fetch --pdf {DOI}')

    def test_output_without_pdf(self):
        with self.assertRaises(SystemExit):
            self.lib(f'fetch {DOI} -o x.pdf')


class TestFetchPdfPorcelain(FetchTest):
    """formats.md 7.2: the porcelain lines of `papers fetch --pdf`, one group per argument, in their order"""

    def porcelain(self, cmd, fails=False):
        out = io.StringIO()
        with redirect_stdout(out):
            if fails:
                with self.assertRaises(PapersExit):
                    self.lib(cmd + ' --porcelain')
            else:
                self.lib(cmd + ' --porcelain')
        return out.getvalue()

    def test_downloaded(self):
        self.publisher()
        target = self.path('paper.pdf')
        out = self.porcelain(f'fetch --pdf {DOI} -o {target}')
        self.assertEqual(out, f'downloaded {DOI} published {PDF} {target}\n')

    def test_downloaded_into_the_current_directory(self):
        self.web.files['https://arxiv.org/pdf/2101.01234'] = pdf_bytes('arxiv')
        out = self.porcelain('fetch --pdf arXiv:2101.01234')
        self.assertEqual(out, 'downloaded arXiv:2101.01234 submitted https://arxiv.org/pdf/2101.01234 2101.01234.pdf\n')

    def test_refused_published(self):
        self.publisher(content=403)
        self.web.openalex[DOI] = [location('https://repo.example.edu/am.pdf', 'acceptedVersion')]
        self.web.files['https://repo.example.edu/am.pdf'] = pdf_bytes('am')
        target = self.path('paper.pdf')
        out = self.porcelain(f'fetch --pdf {DOI} -o {target}')
        self.assertEqual(out, f'downloaded {DOI} accepted https://repo.example.edu/am.pdf {target}\n'
                              f'refused-published {DOI} {PDF}\n')

    def test_refused(self):
        self.publisher(content=b'<html>a challenge</html>')
        self.web.openalex[DOI] = []
        out = self.porcelain(f'fetch --pdf {DOI}', fails=True)
        self.assertEqual(out, f'refused {DOI} {PDF}\nrefused {DOI} https://doi.org/{DOI}\n')

    def test_failed(self):
        self.assertEqual(self.porcelain('fetch --pdf nothing', fails=True), 'failed nothing\n')

    def test_exists_output_checked_before_the_download(self):
        self.publisher(content=403)
        self.web.openalex[DOI] = [location('https://repo.example.edu/am.pdf', 'acceptedVersion')]
        self.web.files['https://repo.example.edu/am.pdf'] = pdf_bytes('am')
        target = self.path('paper.pdf')
        Path(target).write_text('x')
        out = self.porcelain(f'fetch --pdf {DOI} -o {target}', fails=True)
        self.assertEqual(out, f'exists {DOI} {target}\n')
        self.assertEqual(self.web.requests, [])  # nothing looked up nor downloaded
        self.assertEqual(Path(target).read_text(), 'x')

    def test_exists_name_of_the_link(self):
        # the name made from the link is known once its PDF is found: no other link is tried
        self.publisher()
        self.web.openalex[DOI] = [location('https://repo.example.edu/am.pdf', 'acceptedVersion')]
        Path(self.path('lib', '10.1000_ocean.pdf')).write_text('x')
        out = self.porcelain(f'fetch --pdf {DOI}', fails=True)
        self.assertEqual(out, f'exists {DOI} 10.1000_ocean.pdf\n')
        self.assertEqual(self.web.downloads(), [PDF])
        self.assertEqual(Path(self.path('lib', '10.1000_ocean.pdf')).read_text(), 'x')
        self.assertEqual(self.downloads_left(), [])

    def test_several_exit_status(self):
        self.publisher()
        self.publisher(doi='10.1000/other', pdf=None)
        self.web.openalex['10.1000/other'] = []
        with self.assertLogs('papers', 'ERROR'), self.assertRaisesRegex(PapersExit, '1 of 2 PDFs not downloaded'):
            out = io.StringIO()
            with redirect_stdout(out):
                self.lib(f'fetch --pdf 10.1000/other doi:{DOI} --porcelain')
        out = out.getvalue()
        name = '10.1000_ocean.pdf'
        self.assertEqual(out, f'refused 10.1000/other https://doi.org/10.1000/other\n'
                              f'downloaded doi:{DOI} published {PDF} {name}\n')
        self.assertTrue(os.path.exists(self.path('lib', name)))

    def test_all_downloaded_exit_0(self):
        self.publisher()
        self.web.files['https://arxiv.org/pdf/2101.01234'] = pdf_bytes('arxiv')
        out = self.porcelain(f'fetch --pdf {DOI} 2101.01234')
        self.assertEqual([line.split()[0] for line in out.splitlines()], ['downloaded', 'downloaded'])


class TestPageLinks(FetchTest):

    def test_relative_links(self):
        pdf, supplements = freepdf.page_links(
            page('/a/b.pdf', links=[('suppl/x.PDF', 'S'), ('y.pdf', 'Supplementary data'), ('z.pdf', 'PDF')]),
            'https://j.example.org/a/page')
        self.assertEqual(pdf, 'https://j.example.org/a/b.pdf')
        self.assertEqual(supplements, ['https://j.example.org/a/suppl/x.PDF', 'https://j.example.org/a/y.pdf'])

    def test_mailto_in_the_user_agent(self):
        self.assertNotIn('mailto', freepdf.user_agent())
        os.environ[openalex.MAILTO_ENV] = 'me@example.org'
        self.assertIn('mailto:me@example.org', freepdf.user_agent())

    def test_openalex_request(self):
        self.web.openalex[DOI] = [location('https://x.example.org/a.pdf', 'publishedVersion')]
        os.environ[openalex.API_KEY_ENV] = 'secret'
        locations = openalex.work_locations(DOI)
        self.assertEqual(locations[0]['pdf_url'], 'https://x.example.org/a.pdf')
        _, url, params = self.web.requests[-1]
        self.assertEqual(url, 'https://api.openalex.org/works/doi:10.1000/ocean')
        self.assertEqual(params['select'], openalex.WORK_SELECT)
        self.assertEqual(params['api_key'], 'secret')
