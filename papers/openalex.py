"""Full-text search on OpenAlex (https://api.openalex.org), the open alternative
to Google Scholar (`--openalex`, see papers.fetch.fetch_bibtex_by_fulltext_scholar).

OpenAlex is an open catalogue (CC0 data) with an API, where Google Scholar is
scraped (and often blocks it). The search takes the text query that papers
makes of a PDF (papers.extract.query_text) and works like the crossref search:

1. `GET /works?search.semantic=QUERY`: the works whose title and abstract are
   closest in meaning to the query. The plain `search=` needs every word of the
   query, so a query of 200 words finds nothing. A request without a paid key
   may have at most 1500 characters (HTTP 400 above): the query is cut there at
   a word. A semantic search is limited to one request per second.
2. Each work is read as a crossref record, so that the score of papers applies
   (`papers.fetch._crossref_score`: family names, title and abstract with the
   text), and the works are ranked by it.
3. With a check of the title (`accept`: the text of the PDF has it, as for every
   result of papers), the first work in score order that passes is taken; the
   copies of a work (a preprint, the abstract of a conference... that OpenAlex
   has with the title of the paper) come after the published works. If none
   passes, the best one is returned, and the caller's own check rejects it.
4. A work with a DOI gives its BibTeX the usual way (`fetch_bibtex_by_doi`:
   crossref, doi.org, arXiv). A work without DOI, or whose DOI has no metadata,
   gives an entry made of the OpenAlex record, as papers makes it of a crossref
   record (the key is the DOI, else the OpenAlex id).

Without a key, OpenAlex allows about 100 searches a day (shared by the
network); a free key (https://openalex.org/settings/api) has ten times as many.
The key is read from the environment variable OPENALEX_API_KEY, and the email
address that identifies the user (the "polite pool") from PAPERS_MAILTO, when
they are set. The answers are cached (see papers.cache), by the query.
"""
import json
import os
import re
import threading
import time

from papers import logger
from papers.cache import cached
from papers.fetch import (DOIRequestError, _crossref_score, crossref_to_bibtex,
                          fetch_bibtex_by_doi, http_get)

API = 'https://api.openalex.org/works'

# the fields of a work that are asked for
SELECT = ('id,doi,title,display_name,type,type_crossref,publication_year,biblio,'
          'primary_location,authorships,abstract_inverted_index')

ROWS = 10  # works scored (crossref: 5; a search costs the same up to 50)
QUERY_LENGTH = 1500  # characters
INTERVAL = 1.1  # seconds between two requests (the limit of a semantic search is one a second)

API_KEY_ENV = 'OPENALEX_API_KEY'
MAILTO_ENV = 'PAPERS_MAILTO'

_request_lock = threading.Lock()
_last_request = None


class OpenAlexError(OSError):
    """an answer of OpenAlex that is an error, or no answer (message without the key)"""


# the query
# =========

def truncate(text, length=QUERY_LENGTH):
    """the first `length` characters of a text, up to a space (a word is not cut)"""
    if len(text) <= length:
        return text
    if text[length].isspace():
        return text[:length].rstrip()
    head = text[:length]
    cut = max(head.rfind(' '), head.rfind('\n'), head.rfind('\t'))
    return head[:cut].rstrip() if cut > 0 else head


def _throttle():
    """wait until the last request is INTERVAL ago"""
    global _last_request
    with _request_lock:
        if _last_request is not None:
            wait = INTERVAL - (time.monotonic() - _last_request)
            if wait > 0:
                time.sleep(wait)
        _last_request = time.monotonic()


def _redact(text, params):
    for secret in (params.get('api_key'), params.get('mailto')):
        if secret:
            text = text.replace(secret, '***')
    return text


def _http_error(response, params):
    try:
        body = response.json()
    except ValueError:
        body = None
    said = next((body[k] for k in ('message', 'error') if isinstance(body, dict) and isinstance(body.get(k), str)), '')
    message = f'OpenAlex: HTTP {response.status_code}' + (f': {said}' if said else '')
    if response.status_code == 429 and not params.get('api_key'):
        message += f' (without a free API key OpenAlex allows about 100 searches a day: set {API_KEY_ENV})'
    return OpenAlexError(_redact(message, params))


def _trim(work):
    """what is read of a work (the cache has no more): the abstract as text,
    no affiliations and other pages of the record"""
    out = {k: work[k] for k in ('id', 'doi', 'title', 'display_name', 'type', 'type_crossref',
                                'publication_year', 'biblio') if work.get(k) is not None}
    abstract = _abstract(work.get('abstract_inverted_index'))
    if abstract:
        out['abstract'] = abstract
    out['authorships'] = [
        {k: v for k, v in [('raw_author_name', a.get('raw_author_name')),
                           ('display_name', (a.get('author') or {}).get('display_name'))] if v}
        for a in work.get('authorships') or []]
    location = work.get('primary_location') or {}
    source = location.get('source') or {}
    out['primary_location'] = {
        'landing_page_url': location.get('landing_page_url'),
        'source': {k: source.get(k) for k in ('display_name', 'type', 'host_organization_name')},
    }
    return out


def _abstract(index):
    """the abstract from its inverted index (word -> positions)"""
    if not isinstance(index, dict):
        return ''
    words = sorted((position, word) for word, positions in index.items() for position in positions)
    return ' '.join(word for _, word in words)


@cached('openalex', hashed_key=True)
def _search(params):
    """the works of a semantic search, trimmed (`params`: json of the query,
    the cache key: not the email address or the key, which do not change the answer)"""
    params = json.loads(params)
    request = dict(params)
    if os.environ.get(MAILTO_ENV):
        request['mailto'] = os.environ[MAILTO_ENV]
    if os.environ.get(API_KEY_ENV):
        request['api_key'] = os.environ[API_KEY_ENV]
    logger.debug('openalex search: ' + repr(params))
    _throttle()
    try:
        response = http_get(API, params=request)
    except OSError as error:  # requests' errors; they may show the url, with the key
        raise OpenAlexError(_redact(f'OpenAlex: {error}', request)) from None
    if response.status_code >= 400:
        raise _http_error(response, request)
    try:
        return [_trim(work) for work in response.json()['results']]
    except (ValueError, KeyError, TypeError, AttributeError):
        raise OpenAlexError('OpenAlex: unexpected answer') from None


# the works
# =========

def work_doi(work):
    """the DOI of a work, without its URL"""
    doi = (work.get('doi') or '').strip()
    return re.sub(r'^(https?://(dx\.)?doi\.org/|doi:)', '', doi, flags=re.I) or None


def work_title(work):
    return (work.get('title') or work.get('display_name') or '').strip()


def is_copy(work):
    """a work that is a copy of another, as OpenAlex has them with the same
    title: a preprint, the abstract of a conference, a review, a data set..."""
    return work.get('type') in ('preprint', 'conference-abstract', 'peer-review', 'paratext',
                                'dataset', 'supplementary-materials')


PARTICLES = {'van', 'von', 'der', 'den', 'de', 'del', 'della', 'di', 'da', 'dos', 'du', 'la', 'le',
             'ten', 'ter', 'bin', 'ibn', 'al', 'el'}


def split_name(name):
    """(given, family) of a name: `Family, Given` as it is written, else the
    family name is the last word with the particles before it; a name of one
    word (an organization) is a given name"""
    name = ' '.join(name.replace('‐', '-').replace('‑', '-').split())
    if ',' in name:
        family, given = name.split(',', 1)
        return given.strip(), family.strip()
    words = name.split(' ')
    if len(words) < 2:
        return name, ''
    start = len(words) - 1
    while start > 1 and words[start - 1] in PARTICLES:
        start -= 1
    return ' '.join(words[:start]), ' '.join(words[start:])


def _crossref_type(work):
    if work.get('type_crossref'):
        return work['type_crossref']
    kind = work.get('type') or ''
    source_type = (work.get('primary_location') or {}).get('source', {}).get('type')
    if kind in ('article', 'review', 'letter', 'editorial', 'erratum'):
        return {None: 'journal-article', 'journal': 'journal-article',
                'conference': 'proceedings-article'}.get(source_type, 'posted-content')
    return {'preprint': 'posted-content', 'dissertation': 'thesis'}.get(kind, kind)


def work_record(work):
    """the work as a crossref record (what crossref_to_bibtex and the score read)"""
    record = {'type': _crossref_type(work)}
    doi = work_doi(work)
    location = work.get('primary_location') or {}
    source = location.get('source') or {}
    if doi:
        record['DOI'] = doi
        record['URL'] = 'https://doi.org/' + doi
    else:
        record['URL'] = location.get('landing_page_url') or work.get('id') or ''
    if work_title(work):
        record['title'] = [work_title(work)]
    authors = []
    for authorship in work.get('authorships') or []:
        name = authorship.get('raw_author_name') or authorship.get('display_name')
        if name:
            given, family = split_name(name)
            authors.append({k: v for k, v in [('given', given), ('family', family)] if v})
    if authors:
        record['author'] = authors
    if work.get('publication_year') is not None:
        record['issued'] = {'date-parts': [[work['publication_year']]]}
    if source.get('display_name'):
        record['container-title'] = [source['display_name']]
    if source.get('host_organization_name'):
        record['publisher'] = source['host_organization_name']
    biblio = work.get('biblio') or {}
    if biblio.get('volume'):
        record['volume'] = biblio['volume']
    if biblio.get('issue'):
        record['issue'] = biblio['issue']
    first, last = biblio.get('first_page'), biblio.get('last_page')
    if first:
        record['page'] = f'{first}-{last}' if last and last != first else first
    if work.get('abstract'):
        record['abstract'] = work['abstract']
    return record


def work_bibtex(work):
    """the BibTeX made of a work alone: the key is its DOI, else its OpenAlex id"""
    key = (work.get('id') or '').rsplit('/', 1)[-1]
    return crossref_to_bibtex(work_record(work), key=key)


def bibtex_of_work(work):
    """the BibTeX of the DOI of a work, as papers makes it, else made of the work"""
    doi = work_doi(work)
    if doi:
        try:
            return fetch_bibtex_by_doi(doi)
        except DOIRequestError as error:
            logger.info(f'{doi}: no metadata ({error}), the entry is made of the OpenAlex record')
    return work_bibtex(work)


# the search
# ==========

def fetch_bibtex_by_fulltext_openalex(txt, accept=None, rows=ROWS):
    """best match of an OpenAlex search of the text, as BibTeX.

    accept: check of a title (True if it is that of the paper of the text): the
    best work that passes is taken, the published ones before their copies
    """
    query = truncate(txt)
    works = _search(json.dumps({'search.semantic': query, 'per-page': rows, 'select': SELECT}, sort_keys=True))
    if not works:
        raise ValueError('openalex fulltext: no results')

    scores = [_crossref_score(txt, work_record(work)) for work in works]
    order = sorted(range(len(works)), key=lambda i: -scores[i])  # the first of equal scores first
    ranked = [works[i] for i in order]
    chosen = ranked[0]
    if accept is not None:
        accepted = [work for work in ranked if work_title(work) and accept(work_title(work))]
        if accepted:
            chosen = next((work for work in accepted if not is_copy(work)), accepted[0])
    logger.debug('score: ' + str(scores[works.index(chosen)]))
    return bibtex_of_work(chosen).strip()


# the open-access copies of a work (papers.freepdf)
# ===================================================

WORK_SELECT = 'id,doi,open_access,best_oa_location,locations'


class WorkNotFound(OpenAlexError):
    """a DOI that OpenAlex does not have (HTTP 404)"""


def _trim_location(location):
    source = location.get('source') or {}
    return {'pdf_url': location.get('pdf_url'), 'landing_page_url': location.get('landing_page_url'),
            'version': location.get('version'), 'is_oa': bool(location.get('is_oa')),
            'source': source.get('display_name')}


@cached('openalex-work', not_found=WorkNotFound, normalize=str.lower)
def work_locations(doi):
    """the locations of the work of a DOI (`GET /works/doi:<DOI>`, one request),
    trimmed: pdf_url, landing_page_url, version (publishedVersion,
    acceptedVersion, submittedVersion), is_oa and source (its name); the best
    open-access location first. A DOI unknown to OpenAlex raises WorkNotFound."""
    from urllib.parse import quote
    request = {'select': WORK_SELECT}
    if os.environ.get(MAILTO_ENV):
        request['mailto'] = os.environ[MAILTO_ENV]
    if os.environ.get(API_KEY_ENV):
        request['api_key'] = os.environ[API_KEY_ENV]
    logger.debug('openalex work: ' + doi)
    _throttle()
    try:
        response = http_get(f'{API}/doi:{quote(doi, safe="/")}', params=request)
    except OSError as error:
        raise OpenAlexError(_redact(f'OpenAlex: {error}', request)) from None
    if response.status_code == 404:
        raise WorkNotFound(f'{doi}: not found on OpenAlex')
    if response.status_code >= 400:
        raise _http_error(response, request)
    try:
        work = response.json()
        locations = [work['best_oa_location']] if work.get('best_oa_location') else []
        locations += [x for x in work.get('locations') or [] if x and x not in locations]
        return [_trim_location(x) for x in locations]
    except (ValueError, KeyError, TypeError, AttributeError):
        raise OpenAlexError('OpenAlex: unexpected answer') from None
