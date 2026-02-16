import os
import json
import subprocess as sp
import re
import tempfile

import requests
from crossref.restful import Works, Etiquette
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


my_etiquette = Etiquette('papers', papers.__version__, 'https://github.com/perrette/papers', 'mahe.perrette@gmail.com')
work = Works(etiquette=my_etiquette)

class DOIParsingError(ValueError):
    pass

class DOIRequestError(ValueError):
    pass


# PDF parsing / crossref requests
# ===============================
def readpdf_fitz(pdf_path, pages=None, first=None, last=None):
    import fitz

    # Open the PDF file
    document = fitz.open(pdf_path)
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
        return readpdf_fitz(pdf, first=first, last=last)
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
REGEXP = re.compile(r'[doi,doi.org/][\s\.\:]{0,2}(10\.\d{4,9}/[-._;()/:a-z0-9]+)')
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

def parse_doi_from_pdf_metadata_poppler(pdf_path):
    """Extract DOI from PDF metadata using pdfinfo (poppler-utils)."""
    try:
        result = sp.run(['pdfinfo', '-meta', pdf_path],
                       capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return _parse_doi_from_metadata_string(result.stdout)
    except Exception:
        pass
    return None

def parse_doi_from_pdf_metadata_fitz(pdf_path):
    """Extract DOI from PDF metadata using PyMuPDF/fitz."""
    import fitz

    with fitz.open(pdf_path) as doc:
        metadata = doc.metadata

        # Try direct metadata fields first
        if metadata:
            # Check common metadata fields
            for key in ['subject', 'keywords', 'title']:
                value = metadata.get(key, '')
                if value and '10.' in value:
                    # Try to extract DOI from the field
                    doi_match = re.search(r'10\.\d{4,9}/[-._;()/:a-z0-9]+', value, re.IGNORECASE)
                    if doi_match:
                        return doi_match.group(0)

        # Fall back to XMP metadata
        xmp = doc.get_xml_metadata() if hasattr(doc, 'get_xml_metadata') else doc.xref_get_key(-1, "Metadata")
        if xmp:
            xmp_str = xmp if isinstance(xmp, str) else xmp.decode('utf-8', errors='ignore')
            return _parse_doi_from_metadata_string(xmp_str)


def parse_doi_from_pdf_metadata(pdf_path):
    """Extract DOI from PDF metadata (tries fitz, falls back to poppler)."""
    # Try fitz first (no subprocess overhead)

    try:
        return parse_doi_from_pdf_metadata_fitz(pdf_path)
    except ImportError:
        # Fall back to poppler-utils
        return parse_doi_from_pdf_metadata_poppler(pdf_path)

def parse_doi(txt):
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
    matches = REGEXP.findall(txt_lower)

    if not matches:
        # Try arxiv pattern
        match = ARXIV.search(txt_lower)
        if match:
            return f"10.48550/arXiv.{match.group(1)}"

        raise DOIParsingError('parse_doi::no matches')

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

    # Remove non-DOI suffixes: known publisher paths and common junk
    # Strategy: if we find these patterns, remove them AND everything after
    suffixes = [
        # Publisher-specific paths
        '/-/dcsupplemental',
        '/-/dc',
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

    # Quality check
    if len(doi) <= 8:
        raise DOIParsingError('failed to extract doi: '+doi)

    return doi
def isvaliddoi(doi):
    try:
        doi2 = parse_doi('doi:'+doi)
    except:
        return False
    return doi.lower() == doi2.lower()


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
    # Try PDF metadata first (fast and reliable for many publishers)
    metadata_doi = parse_doi_from_pdf_metadata(pdf)
    if metadata_doi:
        return metadata_doi

    # Fall back to text extraction if metadata doesn't have DOI
    return parse_doi(pdfhead(pdf, image=image))


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

    assert len(query_txt.split()) >= 3, 'needs at least 3 query words, got: '+repr(query_txt)
    return query_txt


def extract_txt_metadata(txt, search_doi=True, search_fulltext=False, max_query_words=200, scholar=False):
    """
    extract metadata from text, by parsing and doi-query, or by fulltext query in google scholar
    """
    assert search_doi or search_fulltext, 'no search criteria specified for metadata'

    bibtex = None

    if search_doi:
        try:
            logger.debug('parse doi')
            doi = parse_doi(txt)
            logger.info('found doi:'+doi)
            logger.debug('query bibtex by doi')
            bibtex = fetch_bibtex_by_doi(doi)
            logger.debug('doi query successful')

        except DOIParsingError as error:
            logger.debug('doi parsing error: '+str(error))

        except DOIRequestError as error:
            return '''@misc{{{doi},
             doi = {{{doi}}},
             url = {{http://dx.doi.org/{doi}}},
            }}'''.format(doi=doi)

        except ValueError as error:
            raise
            # logger.debug(u'failed to obtained bibtex by doi search: '+str(error))

    if search_fulltext and not bibtex:
        logger.debug('query bibtex by fulltext')
        query_txt = query_text(txt, max_query_words)
        if scholar:
            bibtex = fetch_bibtex_by_fulltext_scholar(query_txt)
        else:
            bibtex = fetch_bibtex_by_fulltext_crossref(query_txt)
        logger.debug('fulltext query successful')

    if not bibtex:
        raise ValueError('failed to extract metadata')

    return bibtex


def extract_pdf_metadata(pdf, search_doi=True, search_fulltext=True, maxpages=10, minwords=200, image=False, **kw):
    txt = pdfhead(pdf, maxpages, minwords, image=image)
    return extract_txt_metadata(txt, search_doi, search_fulltext, **kw)

@cached('crossref.json')
def fetch_crossref_by_doi(doi):
    url = "http://api.crossref.org/works/"+doi
    response = work.do_http_request('get', url, custom_header={'user-agent': str(work.etiquette)})
    try:
        response.raise_for_status()
    except Exception as error:
        raise DOIRequestError(repr(doi)+': '+repr(error))
    return response.json()

@cached('arxiv.json')
def fetch_bibtex_by_arxiv(arxiv_id):
    url = f"https://arxiv.org/bibtex/{arxiv_id}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        return f"Error: Unable to fetch BibTeX (HTTP {response.status_code})"

def fetch_bibtex_by_doi(doi):
    if "arxiv" in doi.lower():
        return fetch_bibtex_by_arxiv(doi.split("arXiv.")[1])
    try:
        json_data = fetch_crossref_by_doi(doi)
        return crossref_to_bibtex(json_data['message'])
    except DOIRequestError as error:
        pass

    try:
        return fetch_bibtex_on_journal_website(doi, as_string=True)
    except:
        pass

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


@cached('scholar-bibtex.json', hashed_key=True)
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


# @cached('crossref-bibtex-fulltext.json', hashed_key=True)
def fetch_bibtex_by_fulltext_crossref(txt, **kw):
    logger.debug('crossref fulltext seach:\n'+txt)

    # get the most likely match of the first results
    # results = []
    # for i, r in enumerate(work.query(txt).sort('score')):
    #     results.append(r)
    #     if i > 50:
    #         break
    query = work.query(txt, **kw).sort('score')
    query_result = query.do_http_request('get', query.url, custom_header={'user-agent':str(query.etiquette)}).text
    results = json.loads(query_result)['message']['items']

    if len(results) > 1:
        maxscore = 0
        result = results[0]
        for res in results:
            score = _crossref_score(txt, res)
            if score > maxscore:
                maxscore = score
                result = res
        logger.info('score: '+str(maxscore))

    elif len(results) == 0:
        raise ValueError('crossref fulltext: no results')

    else:
        result = results[0]

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
    response = requests.get(url)
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
    response = requests.get(url)
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
