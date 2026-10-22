"""Metadata of a PDF: its text, the DOIs it contains, and the bibtex of the
paper, checked against the text (the queries themselves are in
papers.fetch)."""
import os
import subprocess as sp
import re
import tempfile

import logging
from concurrent.futures import ThreadPoolExecutor

from unidecode import unidecode

from papers import logger
from papers.entries import get_entry_val, parse_string
from papers.fetch import (DOIRequestError, fetch_bibtex_by_doi, fetch_bibtex_by_fulltext_crossref,
                          fetch_bibtex_by_fulltext_scholar)


class DOIParsingError(ValueError):
    pass


# PDF reading
# ===========
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
    "text of a PDF with pdftotext (poppler-utils), when PyMuPDF is not installed"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmptxt = os.path.join(tmpdir, 'pdf.txt')
        cmd = ['pdftotext']
        if first is not None: cmd.extend(['-f', str(first)])
        if last is not None: cmd.extend(['-l', str(last)])
        cmd.extend([pdf, tmptxt])
        logger.info(' '.join(cmd))
        sp.check_call(cmd)
        return open(tmptxt).read()

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

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpbase = os.path.join(tmpdir, 'pdf')
        tmppng = tmpbase + '.png'
        tmptxt = tmpbase + '.txt'

        # 1st create a .png image from the uniq pdf file
        cmd = ['pdftoppm', '-singlefile', '-png', '-q']
        if first is not None: cmd.extend(['-f', str(first)])
        if last is not None: cmd.extend(['-l', str(last)])
        cmd.extend([pdf, tmpbase])
        logger.info(' '.join(cmd))
        sp.check_call(cmd)

        # 2nd extract text from .png using tesseract
        cmd = ["tesseract", tmppng, tmpbase, "-l", "eng", "quiet"]
        logger.info(' '.join(cmd))
        sp.check_call(cmd)

        return open(tmptxt).read()

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
    except DOIParsingError:
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

    raise ValueError('failed to extract metadata: pass the DOI with --doi, or, without DOI, add the entry with --title, --author, --year... and the PDF with --attach')


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
