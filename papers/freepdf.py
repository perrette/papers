"""The free PDF of a paper, from its DOI or arXiv id (`papers file fetch`,
`papers add --fetch-pdf`, `papers fetch --pdf`). Only open-access copies.

The links are tried in this order, until one gives a PDF (its first bytes
are `%PDF`): a published version, else an accepted manuscript, else a
submitted version (preprint):

1. the publisher's page (`https://doi.org/<DOI>`, then the article page):
   its `citation_pdf_url` tag, a published version;
2. OpenAlex (`GET /works/doi:<DOI>`, see papers.openalex.work_locations):
   the open-access locations with a PDF, by version;
3. arXiv: `https://arxiv.org/pdf/<id>`, a submitted version.

The publisher's page is read first, and OpenAlex only when the publisher
gives no PDF. A download that is refused (HTTP error, not a PDF) moves to the
next link; when none is left, the error gives the links to open in a
browser. When an accepted or submitted version is found after the published
version was refused, the published links are given too (Found.refused). The supplements are the PDFs that the article page links with
"suppl" in the URL or the text of the link, and its
`citation_supplementary_material` tags.

The checksum (sha256) and size of each PDF downloaded are kept in the cache
of the machine, by URL (see `known_download`): before a URL is downloaded
again, the caller looks for a file of that checksum (`local` of
fetch_pdf), already linked by the entry or in the library.

papers says what it is in its user agent (with the email address of
PAPERS_MAILTO when it is set), and waits a second between two requests to
the same site.
"""
import os
import re
import shutil
import threading
import time
from collections import namedtuple

import papers
import papers.config
from papers import logger
from papers.files import download_url
from papers.identifiers import arxiv_of_doi, normalize_arxiv
from papers import fetch, openalex

VERSIONS = ('published', 'accepted', 'submitted')  # the order of preference
VERSION_NAMES = {'published': 'published version', 'accepted': 'accepted manuscript',
                 'submitted': 'submitted version', 'supplement': 'supplement'}
_OPENALEX_VERSIONS = {'publishedVersion': 'published', 'acceptedVersion': 'accepted',
                      'submittedVersion': 'submitted'}
LEAST_VERSIONS = ('published', 'accepted', 'any')  # the choices of --version
INTERVAL = 1.0  # seconds between two requests to a site


class NoPDF(ValueError):
    """no PDF could be downloaded: the message ends with the links to open in
    a browser (`links`)"""

    def __init__(self, message, links=()):
        super().__init__(message)
        self.links = list(links)


class Link(namedtuple('Link', 'url version')):
    """a PDF to try: its URL, and its version (published, accepted,
    submitted, or supplement)"""

    @property
    def host(self):
        return _host(self.url)

    def describe(self):
        "e.g. published version, from journals.example.org"
        return f'{VERSION_NAMES[self.version]}, from {self.host}'


def _host(url):
    from urllib.parse import urlparse  # imported when used: papers starts faster
    return urlparse(url).netloc


def user_agent():
    mailto = os.environ.get(openalex.MAILTO_ENV)
    return (f'papers/{papers.__version__} (https://github.com/perrette/papers'
            + (f'; mailto:{mailto}' if mailto else '') + ')')


_lock = threading.Lock()
_last = {}  # host: time of the last request


def _wait(url):
    "wait until the last request to the site of url is INTERVAL ago"
    host = _host(url)
    with _lock:
        if host in _last:
            wait = INTERVAL - (time.monotonic() - _last[host])
            if wait > 0:
                time.sleep(wait)
        _last[host] = time.monotonic()


def page_links(html, base_url):
    """the PDF (citation_pdf_url) and the supplements (PDF links with "suppl"
    in the URL or the text, citation_supplementary_material) of an article page"""
    from urllib.parse import urljoin
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')

    def meta(name):
        return [urljoin(base_url, m['content'].strip()) for m in soup.find_all('meta', attrs={'name': name})
                if m.get('content', '').strip()]
    pdf = next(iter(meta('citation_pdf_url')), None)
    supplements = []
    for url in meta('citation_supplementary_material'):
        if url not in supplements and url != pdf:
            supplements.append(url)
    for a in soup.find_all('a', href=True):
        url = urljoin(base_url, a['href'].strip())
        if '.pdf' not in url.lower():
            continue
        if 'suppl' in url.lower() or 'suppl' in a.get_text().lower():
            if url not in supplements and url != pdf:
                supplements.append(url)
    return pdf, supplements


class Search:
    """the links of the PDF of a paper (DOI and/or arXiv id), in the order
    they are tried; `least`: the least final version wanted (see
    LEAST_VERSIONS). `notes` says what each source gave, `browser` the
    pages to open in a browser."""

    def __init__(self, doi=None, arxiv=None, least='any'):
        if doi and arxiv_of_doi(doi):  # an arXiv DOI: the paper of arXiv
            arxiv = arxiv or normalize_arxiv(arxiv_of_doi(doi))
            doi = None
        self.doi, self.arxiv = doi, arxiv
        self.versions = VERSIONS[:VERSIONS.index(least) + 1] if least in VERSIONS else VERSIONS
        self.notes = []
        self.browser = []
        self.page_refused = None  # the URL of the publisher's page, when it gave an HTTP or network error
        self._page = None

    def page(self):
        "(PDF link, supplements) of the publisher's page, read once"
        if self._page is None:
            self._page = (None, [])
            if self.doi:
                url = 'https://doi.org/' + self.doi
                self.browser.append(url)
                _wait(url)
                try:
                    html, final = fetch.fetch_html(url, headers={'User-Agent': user_agent()})
                    self._page = page_links(html, final)
                    if not self._page[0]:
                        self.notes.append(f'{_host(final)}: no PDF link on the article page')
                except Exception as error:  # HTTP error, network error
                    self.page_refused = url
                    self.notes.append(f'{url}: {_reason(error)}')
        return self._page

    def openalex(self):
        "the open-access PDFs of OpenAlex, by version"
        try:
            locations = openalex.work_locations(self.doi)
        except openalex.WorkNotFound:
            self.notes.append('OpenAlex: no work of this DOI')
            return []
        except OSError as error:  # OpenAlexError: its message has no key
            self.notes.append(str(error))
            return []
        links = []
        for x in locations:
            version = _OPENALEX_VERSIONS.get(x.get('version'))
            if x.get('is_oa') and x.get('landing_page_url') and x['landing_page_url'] not in self.browser:
                self.browser.append(x['landing_page_url'])
            if x.get('is_oa') and x.get('pdf_url') and version in self.versions:
                links.append(Link(x['pdf_url'], version))
        if not links:
            self.notes.append('OpenAlex: no open-access PDF' + ('' if self.versions == VERSIONS else
                                                                  ' of the versions asked'))
        return sorted(links, key=lambda link: VERSIONS.index(link.version))  # stable: the best location first

    def links(self):
        "the links to try, in order (the sources are read as they are needed)"
        seen = set()

        def new(link):
            if link.url in seen:
                return False
            seen.add(link.url)
            return True
        if self.doi:
            pdf, _ = self.page()
            if pdf and new(Link(pdf, 'published')):
                yield Link(pdf, 'published')
            for link in self.openalex():
                if new(link):
                    yield link
        if self.arxiv and 'submitted' in self.versions:
            if not any(re.search(r'arxiv\.org/(pdf|abs)/' + re.escape(self.arxiv), url, re.I) for url in seen):
                url = f'https://arxiv.org/pdf/{self.arxiv}'
                self.browser.append(f'https://arxiv.org/abs/{self.arxiv}')
                if new(Link(url, 'submitted')):
                    yield Link(url, 'submitted')

    def supplements(self):
        return [Link(url, 'supplement') for url in self.page()[1]] if self.doi else []


# the downloads of the machine: URL -> checksum
# =============================================

def _download_cache_file(url):
    import hashlib
    from papers.cache import _cache_path
    key = hashlib.sha256(url.encode('utf-8')).hexdigest()[:32]
    return _cache_path(os.path.join(papers.config.CACHE_DIR, 'downloads'), key)


def known_download(url):
    """{'sha256': hex digest, 'size': bytes} of the PDF that url gave the
    last time it was downloaded on this machine, or None"""
    from papers.cache import _read_cache_file
    data = _read_cache_file(_download_cache_file(url))
    if isinstance(data, dict) and data.get('url') == url and data.get('sha256') and 'size' in data:
        return data
    return None


def remember_download(url, path):
    from papers.cache import _write_cache_file
    from papers.utils import checksum
    if papers.config.DRYRUN:
        return
    _write_cache_file({'url': url, 'sha256': checksum(path).hex(), 'size': os.path.getsize(path)},
                      _download_cache_file(url))


def download(link):
    """download a link into a temporary folder: the path, or ValueError if the
    answer is not a PDF (its first bytes are %PDF). Its checksum is
    remembered (known_download)."""
    _wait(link.url)
    path = download_url(link.url, expect_pdf=True, user_agent=user_agent())
    with open(path, 'rb') as f:
        head = f.read(1024)
    if b'%PDF' not in head:
        discard(path)
        raise ValueError(f'{link.url}: not a PDF')
    remember_download(link.url, path)
    return path


class Found(namedtuple('Found', 'path link how other refused')):
    """a PDF for a link: how is 'downloaded' (path: a temporary file),
    'has' (path: a file of the entry, with the content the link gave),
    'linked' (path: the file of another entry `other`, the key) or 'known'
    (path: a file of the library that no entry links to). refused: the
    links of the published version that were refused before this one, an
    accepted or submitted version, was found (to open in a browser)."""
    __slots__ = ()

    def __new__(cls, path, link, how='downloaded', other=None, refused=()):
        return super().__new__(cls, path, link, how, other, tuple(refused))

    def describe(self):
        "e.g. accepted manuscript, from repo.example.org; the published version was refused: open URL in a browser"
        if not self.refused:
            return self.link.describe()
        return (f'{self.link.describe()}; the published version was refused: '
                f'open {", ".join(self.refused)} in a browser')


def get(link, local=None):
    """the Found of a link: what `local(link, known)` finds for a URL
    downloaded before (known: see known_download), else the download"""
    known = known_download(link.url) if local else None
    found = local(link, known) if known else None
    if found:
        return found
    return Found(download(link), link)


def discard(path):
    "remove a downloaded file and its temporary folder"
    shutil.rmtree(os.path.dirname(path), ignore_errors=True)


def fetch_pdf(search, local=None):
    """the Found of the first link of the search that gives a PDF (see get);
    NoPDF if none does"""
    tried = []
    for link in search.links():
        try:
            found = get(link, local)
        except (ValueError, OSError) as error:
            logger.info(f'{link.url} ({VERSION_NAMES[link.version]}): {error}')
            tried.append((link, error))
            continue
        if link.version != 'published':
            refused = [x.url for x, _ in tried if x.version == 'published']
            if search.page_refused and search.page_refused not in refused:
                refused.append(search.page_refused)
            found = found._replace(refused=tuple(refused))
        return found
    raise NoPDF(no_pdf_message(search, tried), browser_links(search, tried))


def _reason(error):
    "the short reason of a refused download"
    response = getattr(error, 'response', None)  # an HTTP error of requests
    if response is not None and getattr(response, 'status_code', None):
        return f'HTTP {response.status_code}'
    text = str(error)
    m = re.search(r'HTTP \d+', text)
    if m:
        return m.group(0)
    if 'did not return a PDF' in text or 'not a PDF' in text:
        return 'not a PDF'
    return text.split('. ')[0]


def no_pdf_message(search, tried):
    if not search.doi and not search.arxiv:
        return 'no DOI or arXiv id to look for a PDF'
    lines = ['no PDF could be downloaded' if tried else 'no free PDF found']
    lines += [f'  {link.url} ({VERSION_NAMES[link.version]}): {_reason(error)}' for link, error in tried]
    lines += [f'  {note}' for note in search.notes]
    links = browser_links(search, tried)
    if links:
        lines.append('open in a browser: ' + ', '.join(links))
    return '\n'.join(lines)


def browser_links(search, tried):
    "the links to open in a browser when no PDF was found: those tried, then the pages"
    urls = [link.url for link, _ in tried]
    return urls + [url for url in search.browser if url not in urls]


def fetch_supplements(search, local=None):
    "[Found] of the supplements that give PDFs (see get; the others are warned about)"
    found = []
    for link in search.supplements():
        try:
            found.append(get(link, local))
        except (ValueError, OSError) as error:
            logger.warning(f'supplement {link.url}: {_reason(error)} (not attached)')
    return found
