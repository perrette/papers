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
from bibtexparser.customization import convert_to_unicode

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
        return readpdf_fitz(pdf, first=first, last=last)

    return txt


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

REGEXP = re.compile(r'[doi,doi.org/][\s\.\:]{0,2}(10\.\d{4}[\d\:\.\-\/a-z]+)[A-Z\s,\n]')
ARXIV = re.compile(r'arxiv:\s*(\d{4}\.\d{4,5})')

def parse_doi(txt):
    # based on: https://doeidoei.wordpress.com/2009/10/22/regular-expression-to-match-a-doi-digital-object-identifier/
    # doi = r'[doi|DOI][\s\.\:]{0,2}(10\.\d{4}[\d\:\.\-\/a-z]+)[A-Z\s]'

    # maybe try that? (need to convert to python-regex)
    # https://www.crossref.org/blog/dois-and-matching-regular-expressions/
    # a. /^10.\d{4,9}/[-._;()/:A-Z0-9]+$/i
    # b. /^10.1002/[^\s]+$/i
    # c. /^10.\d{4}/\d+-\d+X?(\d+)\d+<[\d\w]+:[\d\w]*>\d+.\d+.\w+;\d$/i
    # d. /^10.1021/\w\w\d++$/i
    # e. /^10.1207/[\w\d]+\&\d+_\d+$/i

    matches = REGEXP.findall(' '+txt.lower()+' ')

    if not matches:

        # try arxiv pattern
        match = ARXIV.search(txt.lower())
        if match:
            arxiv_id = match.group(1)
            matches = [ f"10.48550/arXiv.{arxiv_id}" ]

        else:
            raise DOIParsingError('parse_doi::no matches')

    match = matches[0]

    # clean expression
    doi = match.replace('\n','').strip('.')

    if doi.lower().endswith('.received'):
        doi = doi[:-len('.received')]

    # quality check
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
        return fetch_bibtex_on_journal_website(doi)
    except:
        pass

    raise DOIRequestError(f"Unable to fetch BibTeX for DOI {doi}")


@cached('crossref-json.json')
def fetch_json_by_doi(doi):
    url = "http://api.crossref.org/works/"+doi+"/transform/application/json"
    jsontxt = work.do_http_request('get', url, custom_header={'user-agent': str(work.etiquette)}).text
    return jsontxt.dumps(json)



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

    # Create a BibDatabase object
    db = bibtexparser.bibdatabase.BibDatabase()
    db.entries = [bib_entry]

    # Write to a BibTeX string
    writer = bibtexparser.bwriter.BibTexWriter()
    bibtex_str = writer.write(db)

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
        e = convert_to_unicode(e)
        kw = {}
        if e.get('author',''):
            kw['author'] = family_names(e['author'])
        if e.get('title',''):
            kw['title'] = e['title']
        if kw:
            bibtex = fetch_bibtex_by_fulltext_crossref('', **kw)
        else:
            ValueError('no author nor title field')
    db = bibtexparser.loads(bibtex)
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
    bib_database = bibtexparser.loads(bibtex_content)
    for entry in bib_database.entries:
        if (entry.get('doi', '') or entry.get('DOI', '')).lower() == target_doi.lower():
            return entry
    return None

def fetch_bibtex_on_journal_website(doi):
    base_url = f"https://doi.org/{doi}"
    html_content = fetch_html(base_url)
    for bibtex_url in find_bibtex_links(html_content, base_url):
        bibtex_content = download_bibtex(bibtex_url)
        bibtex_entry = parse_bibtex(bibtex_content, doi)
        if bibtex_entry:
            return bibtex_entry

    raise DOIRequestError("No matching BibTeX entry found for the given DOI.")
