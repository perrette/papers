from __future__ import print_function
import os
import json
import six
import subprocess as sp
# import six.moves.urllib.request
import re
import shutil
import tempfile

from crossref.restful import Works, Etiquette
import bibtexparser

import papers
from papers.config import cached
from papers import logger
from papers.encoding import family_names, latex_to_unicode

my_etiquette = Etiquette('papers', papers.__version__, 'https://github.com/perrette/papers', 'mahe.perrette@gmail.com')


class DOIParsingError(ValueError):
    pass

class DOIRequestError(ValueError):
    pass


# PDF parsing / crossref requests
# ===============================

def readpdf(pdf, first=None, last=None):

    if not os.path.isfile(pdf):
        raise ValueError(repr(pdf) + ": not a file")

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
    """ read pdf header
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
    """extract metadata from text, by parsing and doi-query, or by fulltext query in google scholar
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
            logger.debug(u'doi parsing error: '+str(error))

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



@cached('crossref-bibtex.json')
def fetch_bibtex_by_doi(doi):
    url = "http://api.crossref.org/works/"+doi+"/transform/application/x-bibtex"
    work = Works(etiquette=my_etiquette)
    response = work.do_http_request('get', url, custom_header={'user-agent': str(work.etiquette)})
    if response.ok:
        bibtex = response.text.strip()
        return bibtex
    raise DOIRequestError(repr(doi)+': '+response.text)


@cached('crossref.json')
def fetch_json_by_doi(doi):
    url = "http://api.crossref.org/works/"+doi+"/transform/application/json"
    work = Works(etiquette=my_etiquette)
    jsontxt = work.do_http_request('get', url, custom_header={'user-agent': str(work.etiquette)}).text
    return jsontxt.dumps(json)


def _get_page_fast(pagerequest):
    """Return the data for a page on scholar.google.com"""
    import scholarly.scholarly as scholarly
    resp = scholarly._SESSION.get(pagerequest, headers=scholarly._HEADERS, cookies=scholarly._COOKIES)
    if resp.status_code == 200:
        return resp.text
    else:
        raise Exception('Error: {0} {1}'.format(resp.status_code, resp.reason))


def _scholar_score(txt, bib):
    # high score means high similarity
    from rapidfuzz.fuzz import token_set_ratio
    return sum([token_set_ratio(bib[k], txt) for k in ['title', 'author', 'abstract'] if k in bib])


@cached('scholar-bibtex.json', hashed_key=True)
def fetch_bibtex_by_fulltext_scholar(txt, assess_results=True):
    import scholarly.scholarly
    scholarly._get_page = _get_page_fast  # remove waiting time
    logger.debug(txt)
    search_query = scholarly.search_pubs_query(txt)

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

    # use url_scholarbib to get bibtex from google
    if getattr(result, 'url_scholarbib', ''):
        bibtex = scholarly._get_page(result.url_scholarbib).strip()
    else:
        raise NotImplementedError('no bibtex import link. Make crossref request using title?')
    return bibtex



def _crossref_get_author(res, sep=u'; '):
    return sep.join([p.get('given','') + p['family'] for p in res.get('author',[]) if 'family' in p])


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


def crossref_to_bibtex(r):
    """convert crossref result to bibtex
    """
    bib = {}

    if 'author' in r:
        family = lambda p: p['family'] if len(p['family'].split()) == 1 else u'{'+p['family']+u'}'
        bib['author'] = ' and '.join([family(p) + ', '+ p.get('given','')
            for p in r.get('author',[]) if 'family' in p])

    # for k in ['issued','published-print', 'published-online']:
    k = 'issued'
    if k in r and 'date-parts' in r[k] and len(r[k]['date-parts'])>0:
        date = r[k]['date-parts'][0]
        bib['year'] = str(date[0])
        if len(date) >= 2:
            bib['month'] = str(date[1])
        # break

    if 'DOI' in r: bib['doi'] = r['DOI']
    if 'URL' in r: bib['url'] = r['URL']
    if 'title' in r: bib['title'] = r['title'][0]
    if 'container-title' in r: bib['journal'] = r['container-title'][0]
    if 'volume' in r: bib['volume'] = r['volume']
    if 'issue' in r: bib['number'] = r['issue']
    if 'page' in r: bib['pages'] = r['page']
    if 'publisher' in r: bib['publisher'] = r['publisher']

    # entry type
    type = bib.get('type','journal-article')
    type_mapping = {'journal-article':'article'}
    bib['ENTRYTYPE'] = type_mapping.get(type, type)

    # bibtex key
    year = str(bib.get('year','0000'))
    if 'author' in r:
        ID = r['author'][0]['family'] + u'_' + six.u(year)
    else:
        ID = year
    # if six.PY2:
        # ID = str(''.join([c if ord(c) < 128 else '_' for c in ID]))  # make sure the resulting string is ASCII
    bib['ID'] = ID

    db = bibtexparser.bibdatabase.BibDatabase()
    db.entries.append(bib)
    return bibtexparser.dumps(db)


# @cached('crossref-bibtex-fulltext.json', hashed_key=True)
def fetch_bibtex_by_fulltext_crossref(txt, **kw):
    work = Works(etiquette=my_etiquette)
    logger.debug(six.u('crossref fulltext seach:\n')+six.u(txt))

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
        kw = {}
        if e.get('author',''):
            kw['author'] = latex_to_unicode(family_names(e['author']))
        if e.get('title',''):
            kw['title'] = latex_to_unicode(family_names(e['title']))
        if kw:
            bibtex = fetch_bibtex_by_fulltext_crossref('', **kw)
        else:
            ValueError('no author not title field')
    db = bibtexparser.loads(bibtex)
    return db.entries[0]
