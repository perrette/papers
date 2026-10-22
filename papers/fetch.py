"""Bibliographic metadata over the network: crossref (by DOI and by
bibliographic search), doi.org content negotiation, arXiv, Google Scholar,
and the journal website, with the results cached (see papers.cache)."""
import json
import threading
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

import papers
from papers import logger
from papers.cache import cached
from papers.entries import get_entry_val, parse_string, format_library, entry_from_dict, library_from_entries
from papers.identifiers import arxiv_of_doi


# crossref "polite pool": identify the client and a contact address
USER_AGENT = f'papers/{papers.__version__} (https://github.com/perrette/papers; mailto:mahe.perrette@gmail.com)'
TIMEOUT = 30  # seconds

_thread_local = threading.local()

def http_get(url, **kw):
    """GET with a timeout, through a session per thread so that connections
    are reused across requests"""
    session = getattr(_thread_local, 'session', None)
    if session is None:
        session = _thread_local.session = requests.Session()
        session.headers['User-Agent'] = USER_AGENT
    kw.setdefault('timeout', TIMEOUT)
    return session.get(url, **kw)


class DOIRequestError(ValueError):
    pass

class DOINotFoundError(DOIRequestError):
    """the DOI does not exist (unknown to doi.org)"""


def _drop_references(message):
    # the cited references are most of the record's size, and are not used
    message.pop('reference', None)
    return message


def _migrate_crossref_cache(response):
    message = response.get('message') if isinstance(response, dict) else None
    return _drop_references(message) if isinstance(message, dict) else None


def fetch_crossref_by_doi(doi):
    """crossref record of a DOI ("message" field of the API response)"""
    response = http_get('https://api.crossref.org/works/' + quote(doi, safe='/'))
    if response.status_code == 404:
        raise DOINotFoundError(f'{doi}: not found on crossref')
    try:
        response.raise_for_status()
        return response.json()['message']
    except Exception as error:
        raise DOIRequestError(repr(doi)+': '+repr(error))


# CSL types (doi.org content negotiation) -> crossref types
CSL_TYPES = {
    'article-journal': 'journal-article',
    'chapter': 'book-chapter',
    'paper-conference': 'proceedings-article',
}

def fetch_csl_by_doi(doi):
    """metadata of a DOI of any registration agency (crossref, DataCite...)
    by content negotiation on doi.org, as a crossref-like record"""
    response = http_get('https://doi.org/' + quote(doi, safe='/'),
                        headers={'Accept': 'application/vnd.citationstyles.csl+json'})
    if response.status_code == 404:
        raise DOINotFoundError(f'{doi}: unknown to doi.org')
    if not response.ok or 'json' not in response.headers.get('content-type', ''):
        # the DOI exists but its metadata are not available (yet)
        raise DOIRequestError(f'{doi}: no metadata on doi.org (HTTP {response.status_code})')
    message = response.json()
    for field in ['title', 'container-title']:
        if isinstance(message.get(field), str):
            message[field] = [message[field]]
    message['type'] = CSL_TYPES.get(message.get('type'), message.get('type'))
    return message


@cached('doi', legacy='crossref.json', migrate=_migrate_crossref_cache, trim=_drop_references, not_found=DOINotFoundError,
        normalize=str.lower)
def fetch_doi_metadata(doi):
    """crossref-like record of a DOI: from the crossref API, or from doi.org
    for DOIs registered elsewhere (DataCite, mEDRA...). A DOI unknown to
    doi.org raises DOINotFoundError (remembered for a day: a new paper's
    DOI may be printed before it is registered). DOIs are case-insensitive:
    the queries use the DOI as given, the cache its lower case."""
    try:
        return fetch_crossref_by_doi(doi)
    except DOIRequestError as error:
        logger.debug(f'{error}: try doi.org')
    return fetch_csl_by_doi(doi)


@cached('arxiv', legacy='arxiv.json', migrate=lambda bibtex: None if bibtex.startswith('Error') else bibtex)
def fetch_bibtex_by_arxiv(arxiv_id):
    response = http_get(f"https://arxiv.org/bibtex/{arxiv_id}")
    if response.status_code != 200:
        raise DOIRequestError(f"{arxiv_id}: unable to fetch BibTeX from arxiv (HTTP {response.status_code})")
    return response.text


def fetch_bibtex_by_doi(doi):
    arxiv = arxiv_of_doi(doi)
    if arxiv:
        return fetch_bibtex_by_arxiv(arxiv)
    try:
        return crossref_to_bibtex(fetch_doi_metadata(doi))
    except DOINotFoundError:
        raise
    except DOIRequestError as error:
        logger.debug(str(error))

    # registered but without metadata (yet): the publisher's page may link a bibtex
    try:
        return fetch_bibtex_on_journal_website(doi, as_string=True)
    except Exception as error:
        logger.debug(f'{doi}: no bibtex on the journal website: {error}')

    raise DOIRequestError(f"Unable to fetch BibTeX for DOI {doi}")


def _scholar_score(txt, bib):
    # high score means high similarity
    from rapidfuzz.fuzz import token_set_ratio
    return sum(token_set_ratio(bib[k], txt) for k in ['title', 'author', 'abstract'] if k in bib)


@cached('scholar', hashed_key=True)
def fetch_bibtex_by_fulltext_scholar(txt, assess_results=True):
    from scholarly import scholarly
    logger.debug(txt)
    search_query = scholarly.search_pubs(txt)

    # get the most likely match of the first results
    results = list(search_query)
    if len(results) > 1 and assess_results:
        maxscore = 0
        result = results[0]
        for res in results:
            score = _scholar_score(txt, res.bib)
            if score > maxscore:
                maxscore = score
                result = res
    else:
        result = results[0]

    return scholarly.bibtex(result)

def _crossref_score(txt, r):
    # high score means high similarity
    from rapidfuzz.fuzz import token_set_ratio
    score = 0
    if 'author' in r:
        author = ' '.join([p['family'] for p in r.get('author',[]) if 'family' in p])
        score += token_set_ratio(author, txt)
    if 'title' in r:
        score += token_set_ratio(r['title'][0], txt)
    if 'abstract' in r:
        score += token_set_ratio(r['abstract'], txt)
    return score

def map_crossref_to_bibtex_type(crossref_type):
    mapping = {
        "journal-article": "article",
        "book": "book",
        "book-chapter": "incollection",  # or sometimes inbook
        "proceedings-article": "inproceedings",
        "conference-paper": "inproceedings",
        "report": "techreport",
        "thesis": "phdthesis",  # or "mastersthesis" based on additional info
    }
    return mapping.get(crossref_type, "misc")


def format_authors(authors):
    """Converts a list of author dicts to a BibTeX-friendly string."""
    author_list = []
    for author in authors:
        given = author.get("given", "")
        family = author.get("family", "")
        # Format as "Family, Given" for BibTeX
        formatted = f"{family}, {given}" if family else given
        author_list.append(formatted)
    return " and ".join(author_list)


def crossref_to_bibtex(message):
    entry_type = message.get('type', 'misc')  # Default to 'misc' if type is not specified

    # Common fields
    bib_entry = {
        'title': message.get('title', [''])[0],
        'author': format_authors(message.get('author', [])),
        'doi': message.get('DOI', ''),
        'url': message.get('URL', ''),
        'ENTRYTYPE': map_crossref_to_bibtex_type(entry_type),
        'ID': message.get('DOI', '')
    }

    # Year: Look for publication date in several possible places
    date_parts = None
    for date_field in ["published-print", "published-online", "issued"]:
        if date_field in message and "date-parts" in message[date_field]:
            date_parts = message[date_field]["date-parts"][0]
            break
    if date_parts and len(date_parts) > 0:
        bib_entry["year"] = str(date_parts[0])
    else:
        bib_entry["year"] = "0000"

    # Fields specific to entry types
    if entry_type == 'journal-article':
        bib_entry.update({
            'journal': message.get('container-title', [''])[0],
            'volume': message.get('volume', ''),
            'number': message.get('issue', ''),
            'pages': message.get('page', ''),
        })
    elif entry_type == 'book':
        bib_entry.update({
            'publisher': message.get('publisher', ''),
            'address': message.get('publisher-location', ''),
            'editor': format_authors(message.get('editor', [])),
            'isbn': message.get('ISBN', [''])[0],
        })


    elif entry_type == 'proceedings-article':
        bib_entry.update({
            'booktitle': message.get('container-title', [''])[0],
            'publisher': message.get('publisher', ''),
            'editor': format_authors(message.get('editor', [])),
        })
    elif entry_type == 'report':
        bib_entry.update({
            'institution': message.get('institution', {}).get('name', ''),
        })
    elif entry_type == 'thesis':
        bib_entry.update({
            'school': message.get('institution', {}).get('name', ''),
            'type': message.get('type', ''),
        })

    bib_entry = {k: v for k, v in bib_entry.items() if v}  # Remove empty fields

    # Build entry and library (v2 API)
    entry = entry_from_dict(bib_entry)
    lib = library_from_entries([entry])
    bibtex_str = format_library(lib)

    return bibtex_str


# record fields used by crossref_to_bibtex and _crossref_score
CROSSREF_SELECT = ','.join(['DOI', 'URL', 'type', 'title', 'author', 'editor', 'container-title',
    'volume', 'issue', 'page', 'publisher', 'publisher-location', 'ISBN', 'issued',
    'published-print', 'published-online', 'abstract'])


@cached('crossref-query', hashed_key=True)
def _crossref_query(params):
    response = http_get('https://api.crossref.org/works', params=json.loads(params))
    response.raise_for_status()
    return response.json()['message']['items']


def fetch_bibtex_by_fulltext_crossref(txt, title=None, author=None, rows=5):
    """best match of a crossref bibliographic search (title, authors, other text)"""
    if author and not isinstance(author, str):
        author = ' '.join(author)
    params = {'rows': rows, 'select': CROSSREF_SELECT}
    query = ' '.join(x for x in [title, txt] if x)
    if query:
        params['query.bibliographic'] = query
    if author:
        params['query.author'] = author
    logger.debug('crossref fulltext search: ' + repr(params))
    results = _crossref_query(json.dumps(params, sort_keys=True))

    if len(results) == 0:
        raise ValueError('crossref fulltext: no results')

    scoretxt = ' '.join(x for x in [query, author] if x)
    result = max(results, key=lambda res: _crossref_score(scoretxt, res))
    logger.info('score: '+str(_crossref_score(scoretxt, result)))

    # convert to bibtex
    return crossref_to_bibtex(result).strip()


# BIBTEX FROM THE JOURNAL WEBSITE
# ===============================
# For DOIs registered without metadata yet (the ESD journal prints DOIs
# before crossref has them): look for a link to a .bib file on the page
# the DOI resolves to, and take the entry with that DOI.

def fetch_html(url):
    response = http_get(url)
    response.raise_for_status()  # Raise an error for bad status codes
    return response.text

def find_bibtex_links(html_content, base_url):
    soup = BeautifulSoup(html_content, 'html.parser')

    for link in soup.find_all('a', href=True):
        href = link['href']
        if href.endswith('.bib'):
            full_url = urljoin(base_url, href)
            yield full_url

def download_bibtex(url):
    response = http_get(url)
    response.raise_for_status()
    return response.text

def parse_bibtex(bibtex_content, target_doi):
    bib_database = parse_string(bibtex_content)
    for entry in bib_database.entries:
        if (get_entry_val(entry, 'doi', '') or get_entry_val(entry, 'DOI', '')).lower() == target_doi.lower():
            return entry
    return None

def fetch_bibtex_on_journal_website(doi, as_string=False):
    base_url = f"https://doi.org/{doi}"
    html_content = fetch_html(base_url)
    for bibtex_url in find_bibtex_links(html_content, base_url):
        bibtex_content = download_bibtex(bibtex_url)
        bibtex_entry = parse_bibtex(bibtex_content, doi)
        if bibtex_entry:
            if as_string:
                return bibtex_content
            else:
                return bibtex_entry

    raise DOIRequestError("No matching BibTeX entry found for the given DOI.")
