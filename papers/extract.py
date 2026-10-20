import os
import json
import subprocess as sp
import re
import tempfile

import threading
import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests
import bibtexparser

import papers
from papers.config import cached
from papers import logger
from papers.encoding import family_names
from papers.entries import (
    get_entry_val,
    parse_string,
    format_library,
    entry_from_dict,
    library_from_entries,
)
from papers.encoding import latex_to_unicode_library

from bs4 import BeautifulSoup
from urllib.parse import urljoin


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


class DOIParsingError(ValueError):
    pass

class DOIRequestError(ValueError):
    pass

class DOINotFoundError(DOIRequestError):
    """the DOI does not exist (unknown to doi.org)"""


# PDF parsing / crossref requests
# ===============================
def readpdf_pymupdf(pdf_path, pages=None, first=None, last=None):
    import pymupdf

    # Open the PDF file
    document = pymupdf.open(pdf_path)
    text = ""

    # Iterate through the pages
    for page_num in range(len(document)):
        if pages is not None and page_num+1 not in pages:
            continue
        elif first is not None and page_num+1 < first:
            continue
        elif last is not None and page_num+1 > last:
            continue
        page = document.load_page(page_num)
        text += page.get_text()

    return text

def readpdf_poputils(pdf, first=None, last=None, pages=None):
    # DEPRECATED
    tmptxt = tempfile.mktemp(suffix='.txt')

    cmd = ['pdftotext']
    if first is not None: cmd.extend(['-f', str(first)])
    if last is not None: cmd.extend(['-l', str(last)])
    cmd.extend([pdf, tmptxt])
    logger.info(' '.join(cmd))
    sp.check_call(cmd)

    txt = open(tmptxt).read()
    os.remove(tmptxt)

    return txt

def readpdf(pdf, first=None, last=None):
    # TODO the python package pdftotext can do this directly, with no temp file and no I/O.
    if not os.path.isfile(pdf):
        raise ValueError(repr(pdf) + ": not a file")
    try:
        return readpdf_pymupdf(pdf, first=first, last=last)
    except ImportError:
        logger.warning("PyMuPDF not installed, using pdftotext")
        return readpdf_poputils(pdf, first=first, last=last)


def readpdf_image(pdf, first=None, last=None):

    if not os.path.isfile(pdf):
        raise ValueError(repr(pdf) + ": not a file")

    tmpbase = tempfile.mktemp()
    tmppng = tmpbase + '.png'
    tmptxt = tmpbase + '.txt'

    # 1st create a .png image from the uniq pdf file
    cmd = ['pdftoppm', '-singlefile', '-png', '-q']
    if first is not None: cmd.extend(['-f', str(first)])
    if last is not None: cmd.extend(['-l', str(last)])
    cmd.extend([pdf, tmpbase])
    logger.info(' '.join(cmd))
    # print(' '.join(cmd))
    sp.check_call(cmd)

    # 2nd extract text from .png using tesseract
    cmd = ["tesseract", tmppng, tmpbase, "-l", "eng", "quiet"]
    logger.info(' '.join(cmd))
    # print(' '.join(cmd))
    sp.check_call(cmd)

    txt = open(tmptxt).read()

    os.remove(tmptxt)
    os.remove(tmppng)

    return txt

# CrossRef DOI standard: /^10.\d{4,9}/[-._;()/:A-Z0-9]+$/i
# any DOI not glued to a preceding word, number or dot (bare DOIs included:
# Science and AGU print the article's DOI alone on a line)
REGEXP = re.compile(r'(?<![\w.\-])(10\.\d{4,9}/[-._;()/:a-z0-9]+)')
# DOI introduced by a "doi" label or a doi.org URL
LABELED_REGEXP = re.compile(r'(?:doi:?\s*|doi\.org/)(10\.\d{4,9}/[-._;()/:a-z0-9]+)')
ARXIV = re.compile(r'arxiv:\s*(\d{4}\.\d{4,5})')

def _parse_doi_from_metadata_string(metadata):
    """Extract DOI from XMP metadata string."""
    patterns = [
        r'<prism:doi>(10\.\d{4,9}/[-._;()/:a-z0-9]+)</prism:doi>',
        r'<dc:identifier>doi:(10\.\d{4,9}/[-._;()/:a-z0-9]+)</dc:identifier>',
        r'<pdfx:doi>(10\.\d{4,9}/[-._;()/:a-z0-9]+)</pdfx:doi>',
        r'<crossmark:DOI>(10\.\d{4,9}/[-._;()/:a-z0-9]+)</crossmark:DOI>',
    ]
    for pattern in patterns:
        match = re.search(pattern, metadata, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

def _parse_doi_from_info_fields(fields):
    """DOI in the document info fields (subject, keywords, title)"""
    for key in ['subject', 'keywords', 'title']:
        value = fields.get(key) or ''
        doi_match = re.search(r'10\.\d{4,9}/[-._;()/:a-z0-9]+', value, re.IGNORECASE)
        if doi_match:
            return doi_match.group(0)
    return None


def parse_doi_from_pdf_metadata_poppler(pdf_path):
    """Extract DOI from PDF metadata using pdfinfo (poppler-utils)."""
    try:
        result = sp.run(['pdfinfo', pdf_path], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            fields = dict(line.split(':', 1) for line in result.stdout.splitlines() if ':' in line)
            doi = _parse_doi_from_info_fields({k.strip().lower(): v.strip() for k, v in fields.items()})
            if doi:
                return doi
        result = sp.run(['pdfinfo', '-meta', pdf_path],
                       capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return _parse_doi_from_metadata_string(result.stdout)
    except Exception:
        pass
    return None

def parse_doi_from_pdf_metadata_pymupdf(pdf_path):
    """Extract DOI from PDF metadata using PyMuPDF."""
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        metadata = doc.metadata

        # Try direct metadata fields first
        if metadata:
            doi = _parse_doi_from_info_fields(metadata)
            if doi:
                return doi

        # Fall back to XMP metadata
        xmp = doc.get_xml_metadata() if hasattr(doc, 'get_xml_metadata') else doc.xref_get_key(-1, "Metadata")
        if xmp:
            xmp_str = xmp if isinstance(xmp, str) else xmp.decode('utf-8', errors='ignore')
            return _parse_doi_from_metadata_string(xmp_str)


def parse_doi_from_pdf_metadata(pdf_path):
    """Extract DOI from PDF metadata (tries pymupdf, falls back to poppler)."""
    # Try pymupdf first (no subprocess overhead)

    try:
        return parse_doi_from_pdf_metadata_pymupdf(pdf_path)
    except ImportError:
        # Fall back to poppler-utils
        return parse_doi_from_pdf_metadata_poppler(pdf_path)

# DOI prefixes of data repositories (Zenodo, Dryad, figshare, USGS, SEANOE,
# PANGAEA, NSIDC): a data DOI cited in a paper (abstract, data availability
# statement) is not the paper's own DOI
DATA_REPOSITORY_PREFIXES = ('10.5281', '10.5061', '10.6084', '10.5066', '10.17882', '10.1594', '10.5067')

def is_data_repository_doi(doi):
    return doi.lower().split('/')[0] in DATA_REPOSITORY_PREFIXES


def _normalize_doi_text(txt):
    # Remove invisible Unicode characters and normalize dashes and slashes
    # U+200B: zero-width space, U+00AD: soft hyphen, U+2013: en-dash, U+2014: em-dash
    # \x02: STX (Start of Text) sometimes used instead of slash in PDFs
    txt_clean = txt.replace('\u200b', '').replace('\xad', '').replace('\u2013', '-').replace('\u2014', '-').replace('\x02', '/')
    txt_lower = txt_clean.lower()

    # Handle DOI split at "10.\n<registrant>" (e.g., "10.\n1073/pnas.123")
    # Requires 4-9 digits (valid registrant) followed by slash
    txt_lower = re.sub(r'(10\.)\s*\n\s*(\d{4,9}/)', r'\1\2', txt_lower)

    # Special case: PNAS DOIs may be split at "10.1073/pnas. \n<digits>"
    # This is a very specific pattern that's safe to join
    txt_lower = re.sub(r'(10\.1073/pnas\.)\s*\n\s*(\d)', r'\1\2', txt_lower)

    # Handle DOIs split at dash-newline-alphanumeric (common in many publishers)
    # e.g., "10.1175/jcli-d-21-\n0636.1", "10.1175/JCLI-\nD-17-0112.s1"
    txt_lower = re.sub(r'(10\.\d{4,9}/[-._;()/:a-z0-9]+-)\s*\n\s*([a-z0-9])', r'\1\2', txt_lower)

    # Don't join across newlines generally - it causes more problems than it solves
    # The newline naturally stops incorrect matches from extending into following text
    return txt_lower


def _pick_doi(matches, txt_lower):
    """the most likely article DOI among the regexp matches (in order of appearance)"""
    # Start with first match as default
    doi = matches[0]

    # Prefer DOIs that appear in full URL context (e.g., www.pnas.org/cgi/doi/10.1073/...)
    # These are more likely to be the article's own DOI rather than citations
    if len(matches) > 1:
        url_patterns = [
            r'www\.[a-z]+\.org/[a-z/]+/(10\.\d{4,9}/[-._;()/:a-z0-9]+)',
            r'doi\.org/(10\.\d{4,9}/[-._;()/:a-z0-9]+)',
            r'dx\.doi\.org/(10\.\d{4,9}/[-._;()/:a-z0-9]+)',
        ]
        for pattern in url_patterns:
            url_matches = re.findall(pattern, txt_lower)
            # If any of our DOI matches appear in a URL, prefer the first one
            for doi_match in matches:
                if doi_match in url_matches:
                    doi = doi_match
                    break
            if doi in url_matches:  # Found a URL match, stop searching patterns
                break

    # If multiple matches and first is supplemental, prefer non-supplemental with same base
    # e.g., prefer "10.1175/jcli-d-16-0271.1" over "10.1175/jcli-d-16-0271.s1"
    if len(matches) > 1 and doi == matches[0]:
        # Check if first match is supplemental (.s<digit>)
        if re.search(r'\.s\d+\.?$', matches[0]):
            # Look for non-supplemental version with same base
            base = re.sub(r'\.s\d+\.?$', '', matches[0])
            for m in matches[1:]:
                if m.startswith(base) and not re.search(r'\.s\d+\.?$', m):
                    doi = m
                    break

    return doi


def _clean_doi(doi):
    # Remove non-DOI suffixes: known publisher paths and common junk
    # Strategy: if we find these patterns, remove them AND everything after
    suffixes = [
        # Publisher-specific paths
        '/-/dcsupplemental',
        '/-/dc',
        # Springer prints "(0123456789().,-volV)" right after the DOI
        '(0123456789',
        # Common file extension
        '.pdf',
        # Document status markers that clearly shouldn't be in DOI
        'preprint',
        'received',
        'published',
        'edited',
        'advance',
        'full',
        'abstract',
        '-supplement',
        'supplement',
    ]

    doi_lower = doi.lower()
    for suffix in suffixes:
        pos = doi_lower.find(suffix)
        if pos > 0:  # Found suffix (not at start)
            # For word-only suffixes, ensure they follow a valid DOI character
            if suffix.isalpha():
                prev_char = doi[pos-1]
                # Accept if preceded by alphanumeric, dash, underscore, slash, or dot
                if prev_char.isalnum() or prev_char in '.-_/':
                    doi = doi[:pos]
                    break
            else:
                # Non-word suffixes (paths, extensions) - just cut
                doi = doi[:pos]
                break

    # Clean up trailing periods and colons
    doi = doi.rstrip('.:')

    # Strip unbalanced trailing ')' — DOIs can contain parens but they must be balanced
    # (e.g. 10.1175/1520-0493(1990)118<2228:WMGD>2.0.CO;2). When a DOI is wrapped in
    # parens in the source ("(doi:10.../1)" or a URL ending in ")"), the regex greedily
    # includes the closing paren; this fixes that.
    while doi.endswith(')') and doi.count(')') > doi.count('('):
        doi = doi[:-1]

    # Quality check
    if len(doi) <= 8:
        raise DOIParsingError('failed to extract doi: '+doi)

    return doi


def parse_dois(txt, tail=''):
    """Return the DOIs found in the text, the most likely article DOI first.

    DOIs of data repositories (see DATA_REPOSITORY_PREFIXES) come last when
    other DOIs are present: they are cited by the paper, not the paper's own.

    tail is the end of the document (e.g. the cover page publishers append
    to the PDF): its labeled DOIs ("doi:", doi.org URL) are added after the
    DOIs of the text.
    """
    tail_dois = []
    for candidate in LABELED_REGEXP.findall(_normalize_doi_text(tail)):
        try:
            candidate = _clean_doi(candidate)
        except DOIParsingError:
            continue
        if candidate not in tail_dois:
            tail_dois.append(candidate)
    try:
        dois = _parse_dois(txt)
    except DOIParsingError:
        if not tail_dois:
            raise
        dois = []
    return dois + [doi for doi in tail_dois if doi not in dois]


def _parse_dois(txt):
    txt_lower = _normalize_doi_text(txt)
    matches = REGEXP.findall(txt_lower)

    if not matches:
        # Try arxiv pattern
        match = ARXIV.search(txt_lower)
        if match:
            return [f"10.48550/arXiv.{match.group(1)}"]

        raise DOIParsingError('parse_doi::no matches')

    matches = list(dict.fromkeys(matches))  # unique, in order of appearance
    articles = [m for m in matches if not is_data_repository_doi(m)] or matches
    data = [m for m in matches if m not in articles]

    doi = _pick_doi(articles, txt_lower)
    candidates = [doi] + [m for m in articles if m != doi] + data

    dois = []
    for candidate in candidates:
        try:
            candidate = _clean_doi(candidate)
        except DOIParsingError as error:
            logger.debug(str(error))
            continue
        if candidate not in dois:
            dois.append(candidate)
    if not dois:
        raise DOIParsingError('failed to extract doi: '+doi)
    return dois


def parse_doi(txt):
    return parse_dois(txt)[0]


def isvaliddoi(doi):
    try:
        doi2 = parse_doi('doi:'+doi)
    except:
        return False
    return doi.lower() == doi2.lower()


def pdftail(pdf):
    """text of the last page, if the pdf has more than one page
    (publishers such as AAAS append a cover page with the DOI)"""
    try:
        import pymupdf
    except ImportError:
        pages = re.search(r'^Pages:\s*(\d+)', sp.run(['pdfinfo', pdf], capture_output=True, text=True).stdout, re.M)
        if not pages or int(pages.group(1)) < 2:
            return ''
        return readpdf_poputils(pdf, first=int(pages.group(1)), last=int(pages.group(1)))
    with pymupdf.open(pdf) as document:
        if len(document) < 2:
            return ''
        return document[-1].get_text()


def pdfhead(pdf, maxpages=10, minwords=200, image=False):
    """
    read pdf header
    """
    i = 0
    txt = ''
    while len(txt.strip().split()) < minwords and i < maxpages:
        i += 1
        logger.debug('read pdf page: '+str(i))
        if image:
            txt += readpdf_image(pdf, first=i, last=i)
        else:
            txt += readpdf(pdf, first=i, last=i)
    return txt


def extract_pdf_doi(pdf, image=False):
    """The article's DOI: from the PDF metadata if present (trusted as is),
    otherwise the first DOI of the text whose title appears in the text
    (one crossref request per candidate)"""
    metadata_doi = parse_doi_from_pdf_metadata(pdf)
    if metadata_doi:
        return metadata_doi

    txt = pdfhead(pdf, image=image)
    tail = '' if image else pdftail(pdf)
    confirmed = confirm_doi(parse_dois(txt, tail), txt)  # the title is on the first page(s)
    if not confirmed:
        raise DOIParsingError('no DOI found whose title appears in the text')
    return confirmed[0]


def query_text(txt, max_query_words=200):
    # list of paragraphs
    paragraphs = re.split(r"\n\n", txt)

    # remove anything that starts with 'reference'
    query = []
    for p in paragraphs:
        if p.lower().startswith('reference'):
            continue
        query.append(p)

    query_txt = ' '.join(query)

    # limit overall length
    query_txt = ' '.join(query_txt.strip().split()[:max_query_words])

    if len(query_txt.split()) < 3:
        # a proper exception, not AssertionError: callers handle query failures
        raise ValueError('needs at least 3 query words, got: '+repr(query_txt))
    return query_txt


def _normalize_for_match(s):
    from unidecode import unidecode
    s = re.sub(r'<[^>]+>', '', s)  # markup in crossref titles, e.g. CO<sub>2</sub>
    return re.sub(r'[^a-z0-9]', '', unidecode(s).lower())


def title_in_text(title, txt):
    """True if the title appears in the text (ignoring case, accents, spacing
    and punctuation, so that line breaks and hyphenation do not matter)"""
    title = _normalize_for_match(title)
    if len(title) < 10:
        return True  # too short to tell
    return title in _normalize_for_match(txt)


def _bibtex_title(bibtex):
    entries = parse_string(bibtex).entries
    return get_entry_val(entries[0], 'title', '') if entries else ''


def confirm_doi(dois, txt):
    """The first candidate DOI whose title (from crossref) appears in the
    text, as (doi, bibtex), or None.

    A candidate is never accepted on faith: a DOI cited in the text, or the
    DOI of the previous article printed on the same page, is a valid DOI of
    another paper. DOIs without metadata or without title cannot be checked
    and are skipped.
    """
    for doi in dois:
        try:
            bibtex = fetch_bibtex_by_doi(doi)
        except DOIRequestError as error:
            logger.info(f'{doi}: no metadata found ({error})')
            continue
        title = _bibtex_title(bibtex)
        if not title:
            logger.info(f'{doi}: metadata without title, skip')
            continue
        if title_in_text(title, txt):
            return doi, bibtex
        logger.info(f'{doi}: title not found in the text: {title}')
    return None


def extract_txt_metadata(txt, search_doi=True, search_fulltext=False, max_query_words=200, scholar=False, tail=''):
    """
    extract metadata from text, by parsing and doi-query, or by fulltext query in google scholar

    The result is accepted only if its title appears in txt (not in the tail:
    for most papers the last page is the reference list, where cited papers
    have both their title and DOI). Raise ValueError otherwise.
    """
    assert search_doi or search_fulltext, 'no search criteria specified for metadata'

    dois = []

    if search_doi:
        try:
            logger.debug('parse doi')
            dois = parse_dois(txt, tail)
            logger.info('found doi(s): ' + ', '.join(dois))
        except DOIParsingError as error:
            logger.debug('doi parsing error: '+str(error))

        if dois:
            logger.debug('query bibtex by doi')
            confirmed = confirm_doi(dois, txt)
            if confirmed:
                logger.debug('doi query successful')
                return confirmed[1]
            logger.warning('no DOI found whose title appears in the text: ' + ', '.join(dois))

    if search_fulltext:
        logger.debug('query bibtex by fulltext')
        try:
            query_txt = query_text(txt, max_query_words)
            if scholar:
                bibtex = fetch_bibtex_by_fulltext_scholar(query_txt)
            else:
                bibtex = fetch_bibtex_by_fulltext_crossref(query_txt)
        except Exception as error:
            logger.warning(f'fulltext query failed: {error}')
        else:
            title = _bibtex_title(bibtex)
            if title and title_in_text(title, txt):
                logger.debug('fulltext query successful')
                return bibtex
            logger.warning(f'fulltext query: title not found in the text: {title[:100]}')

    raise ValueError('failed to extract metadata (pass the DOI explicitly with --doi)')


def _metadata_from_pdf_contents(metadata_doi, read_text, search_doi=True, search_fulltext=True, **kw):
    """the network part of extract_pdf_metadata: read_text() returns the text
    of the first pages and of the last page"""
    # a DOI in the PDF metadata is the article's own: no need to parse the text
    if search_doi and metadata_doi:
        logger.info(f'found doi in pdf metadata: {metadata_doi}')
        try:
            return fetch_bibtex_by_doi(metadata_doi)
        except DOIRequestError as error:
            logger.warning(f'{metadata_doi}: no metadata found ({error}), search the text')
    txt, tail = read_text()
    return extract_txt_metadata(txt, search_doi, search_fulltext, tail=tail, **kw)


def extract_pdf_metadata(pdf, search_doi=True, search_fulltext=True, maxpages=10, minwords=200, image=False, **kw):
    metadata_doi = parse_doi_from_pdf_metadata(pdf) if search_doi else None
    read_text = lambda: (pdfhead(pdf, maxpages, minwords, image=image), '' if image else pdftail(pdf))
    return _metadata_from_pdf_contents(metadata_doi, read_text, search_doi, search_fulltext, **kw)


def prefetch_pdf_metadata(pdfs, workers=3, search_doi=True, search_fulltext=True, **kw):
    """Fill the cache with the metadata of several PDFs, with up to `workers`
    requests at a time (crossref's limit), so that adding them one by one
    afterwards is fast. Errors and log messages are left to that second pass.
    """
    contents = []
    for pdf in pdfs:  # read in this thread: PyMuPDF is not thread-safe
        try:
            metadata_doi = parse_doi_from_pdf_metadata(pdf) if search_doi else None
            text = ('', '') if metadata_doi else (pdfhead(pdf), pdftail(pdf))
        except Exception:
            continue
        contents.append((metadata_doi, text))

    def fetch(content):
        metadata_doi, text = content
        try:
            _metadata_from_pdf_contents(metadata_doi, lambda: text, search_doi, search_fulltext, **kw)
        except Exception:
            pass

    logger.info(f'fetch the metadata of {len(contents)} PDFs')
    level = logger.level
    logger.setLevel(logging.CRITICAL)  # the second pass logs
    try:
        with ThreadPoolExecutor(workers) as executor:
            list(executor.map(fetch, contents))
    finally:
        logger.setLevel(level)

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


@cached('doi', legacy='crossref.json', migrate=_migrate_crossref_cache, trim=_drop_references, not_found=DOINotFoundError)
def fetch_doi_metadata(doi):
    """crossref-like record of a DOI: from the crossref API, or from doi.org
    for DOIs registered elsewhere (DataCite, mEDRA...). A DOI unknown to
    doi.org raises DOINotFoundError (remembered for a day: a new paper's
    DOI may be printed before it is registered)."""
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
    if "arxiv" in doi.lower():
        return fetch_bibtex_by_arxiv(doi.split("arXiv.")[1])
    try:
        return crossref_to_bibtex(fetch_doi_metadata(doi.lower()))
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


def _get_page_fast(pagerequest):
    """Return the data for a page on scholar.google.com"""
    from scholarly import scholarly
    resp = scholarly._SESSION.get(pagerequest, headers=scholarly._HEADERS, cookies=scholarly._COOKIES)
    if resp.status_code == 200:
        return resp.text
    else:
        raise Exception('Error: {} {}'.format(resp.status_code, resp.reason))


def _scholar_score(txt, bib):
    # high score means high similarity
    from rapidfuzz.fuzz import token_set_ratio
    return sum(token_set_ratio(bib[k], txt) for k in ['title', 'author', 'abstract'] if k in bib)


@cached('scholar', hashed_key=True)
def fetch_bibtex_by_fulltext_scholar(txt, assess_results=True):
    from scholarly import scholarly
    # scholarly._get_page = _get_page_fast  # remove waiting time
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
        # author_list.append(unidecode(formatted))
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


def fetch_entry(e):
    if 'doi' in e and isvaliddoi(e['doi']):
        bibtex = fetch_bibtex_by_doi(e['doi'])
    else:
        lib = library_from_entries([e] if hasattr(e, 'fields_dict') else [entry_from_dict(e)])
        lib = latex_to_unicode_library(lib)
        e = lib.entries[0] if lib.entries else e
        kw = {}
        if get_entry_val(e, 'author', ''):
            kw['author'] = family_names(e['author'])
        if get_entry_val(e, 'title', ''):
            kw['title'] = e['title']
        if kw:
            bibtex = fetch_bibtex_by_fulltext_crossref('', **kw)
        else:
            ValueError('no author nor title field')
    db = parse_string(bibtex)
    return db.entries[0]



############### HERE A HACK DESIGNED FOR THE ESD JOURNAL ################
# That journal often provides DOI that are not yet registered in crossref
# so we need to fetch the bibtex from the journal website
# Thanks Le Chat for near-instantaneous and elegantly designed code

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
