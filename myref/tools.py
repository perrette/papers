from __future__ import print_function
import os
import logging
import shutil
import json
import six
import subprocess as sp
import six.moves.urllib.request
import re
import hashlib
from crossref.restful import Works, Etiquette
import bibtexparser

import myref
from myref.config import config

my_etiquette = Etiquette('myref', myref.__version__, 'https://github.com/perrette/myref', 'mahe.perrette@gmail.com')

DRYRUN = False

class bcolors:
    # https://stackoverflow.com/a/287944/2192272
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

    def str(self, s, modifier):
        return modifier + s + self.ENDC





# misc
# ----
def unique(entries):
    entries_ = []
    for e in entries:
        if e not in entries_:
            entries_.append(e)
    return entries_


def check_filesdir(folder):
    folder_size = 0
    file_count = 0
    for (path, dirs, files) in os.walk(folder):
      for file in files:
        filename = os.path.join(path, file)
        if filename.endswith('.pdf'):
            folder_size += os.path.getsize(filename)
            file_count += 1
    return file_count, folder_size



def hash_bytestr_iter(bytesiter, hasher, ashexstr=False):
    for block in bytesiter:
        hasher.update(block)
    return (hasher.hexdigest() if ashexstr else hasher.digest())

def file_as_blockiter(afile, blocksize=65536):
    with afile:
        block = afile.read(blocksize)
        while len(block) > 0:
            yield block
            block = afile.read(blocksize)

def checksum(fname):
    """memory-efficient check sum (sha256)

    source: https://stackoverflow.com/a/3431835/2192272
    """
    return hash_bytestr_iter(file_as_blockiter(open(fname, 'rb')), hashlib.sha256())

# move / copy

def move(f1, f2, copy=False, interactive=True):
    dirname = os.path.dirname(f2)
    if dirname and not os.path.exists(dirname):
        logging.info('create directory: '+dirname)
        os.makedirs(dirname)
    if f1 == f2:
        logging.info('dest is identical to src: '+f1)
        return 
    if os.path.exists(f2):
        ans = raw_input('dest file already exists: '+f2+'. Replace? (y/n) ')
        if ans != 'y':
            return

    if copy:
        cmd = u'cp {} {}'.format(f1, f2)
        logging.info(cmd)
        if not DRYRUN:
            shutil.copy(f1, f2)
    else:
        cmd = u'mv {} {}'.format(f1, f2)
        logging.info(cmd)
        if not DRYRUN:
            shutil.move(f1, f2)


# PDF parsing / crossref requests
# ===============================

def readpdf(pdf, first=None, last=None, keeptxt=False):
    txtfile = pdf.replace('.pdf','.txt')
    # txtfile = os.path.join(os.path.dirname(pdf), pdf.replace('.pdf','.txt'))
    if True: #not os.path.exists(txtfile):
        # logging.info(' '.join(['pdftotext','"'+pdf+'"', '"'+txtfile+'"']))
        cmd = ['pdftotext']
        if first is not None: cmd.extend(['-f',str(first)])
        if last is not None: cmd.extend(['-l',str(last)])
        cmd.append(pdf)
        sp.check_call(cmd)
    else:
        logging.info('file already present: '+txtfile)
    txt = open(txtfile).read()
    if not keeptxt:
        os.remove(txtfile)
    return txt


def parse_doi(txt, space_digit=False):
    # cut the reference part...

    # doi = r"10\.\d\d\d\d/[^ ,]+"  # this ignore line breaks
    doi = r"10\.\d\d\d\d/.*?"

    # sometimes an underscore is converted as space
    if space_digit:
        doi += r"[ \d]*"  # also accept empty space followed by digit

    # expression ends with a comma, empty space or newline
    stop = r"[, \n]"

    # expression starts with doi:
    prefixes = ['doi:', 'doi: ', 'doi ', 'dx\.doi\.org/', 'doi/']
    prefix = '[' + '|'.join(prefixes) + ']' # match any of those

    # full expression, capture doi as a group
    regexp = prefix + "(" + doi + ")" + stop

    matches = re.compile(regexp).findall(' '+txt.lower()+' ')

    if not matches:
        raise ValueError('parse_doi::no matches')

    match = matches[0]

    # clean expression
    doi = match.replace('\n','').strip('.')

    if space_digit:
        doi = doi.replace(' ','_')

    if doi.lower().endswith('.received'):
        doi = doi[:-len('.received')]

    # quality check 
    assert len(doi) > 8, 'failed to extract doi: '+doi

    return doi


def isvaliddoi(doi):
    try:
        doi2 = parse_doi(doi)
    except:
        return False
    return doi.lower() == doi2.lower()


def pdfhead(pdf, maxpages=10, minwords=200):
    """ read pdf header
    """
    i = 0
    txt = ''
    while len(txt.strip().split()) < minwords and i < maxpages:
        i += 1
        logging.debug('read pdf page: '+str(i))
        txt += readpdf(pdf, first=i, last=i)
    return txt


def extract_doi(pdf, space_digit=True):
    return parse_doi(pdfhead(pdf), space_digit=space_digit)


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


def extract_txt_metadata(txt, search_doi=True, search_fulltext=False, space_digit=True, max_query_words=200, scholar=False):
    """extract metadata from text, by parsing and doi-query, or by fulltext query in google scholar
    """
    assert search_doi or search_fulltext, 'no search criteria specified for metadata'

    bibtex = None

    if search_doi:
        try:
            logging.debug('parse doi')
            doi = parse_doi(txt, space_digit=space_digit)
            logging.info('found doi:'+doi)
            logging.debug('query bibtex by doi')
            bibtex = fetch_bibtex_by_doi(doi)
            logging.debug('doi query successful')

        except ValueError as error:
            logging.debug(u'failed to obtained bibtex by doi search: '+str(error))

    if search_fulltext and not bibtex:
        logging.debug('query bibtex by fulltext')
        query_txt = query_text(txt, max_query_words)
        if scholar:
            bibtex = fetch_bibtex_by_fulltext_scholar(query_txt)
        else:
            bibtex = fetch_bibtex_by_fulltext_crossref(query_txt)
        logging.debug('fulltext query successful')

    if not bibtex:
        raise ValueError('failed to extract metadata')

    return bibtex


def extract_pdf_metadata(pdf, search_doi=True, search_fulltext=True, maxpages=10, minwords=200, **kw):
    txt = pdfhead(pdf, maxpages, minwords)
    return extract_txt_metadata(txt, search_doi, search_fulltext, **kw)



def cached(file, hashed_key=False):
    def decorator(fun):
        if os.path.exists(file):
            cache = json.load(open(file))
        else:
            cache = {}
        def decorated(doi):
            if hashed_key: # use hashed parameter as key (for full text query)
                if six.PY3:
                    key = hashlib.sha256(doi.encode('utf-8')).hexdigest()[:6]
                else:
                    key = hashlib.sha256(doi).hexdigest()[:6]
            else:
                key = doi
            if key in cache:
                logging.debug('load from cache: '+repr((file, key)))
                return cache[key]
            else:
                res = cache[key] = fun(doi)
                if not DRYRUN:
                    json.dump(cache, open(file,'w'))
            return res
        return decorated
    return decorator


@cached(os.path.join(config.cache, 'crossref-bibtex.json'))
def fetch_bibtex_by_doi(doi):
    url = "http://api.crossref.org/works/"+doi+"/transform/application/x-bibtex"
    work = Works(etiquette=my_etiquette)
    bibtex = work.do_http_request('get', url, custom_header=str(work.etiquette)).text
    return bibtex.strip()


@cached(os.path.join(config.cache, 'crossref.json'))
def fetch_json_by_doi(doi):
    url = "http://api.crossref.org/works/"+doi+"/transform/application/json"
    work = Works(etiquette=my_etiquette)
    jsontxt = work.do_http_request('get', url, custom_header=str(work.etiquette)).text
    return jsontxt.dumps(json)


def _get_page_fast(pagerequest):
    """Return the data for a page on scholar.google.com"""
    import scholarly
    resp = scholarly._SESSION.get(pagerequest, headers=scholarly._HEADERS, cookies=scholarly._COOKIES)
    if resp.status_code == 200:
        return resp.text
    else:
        raise Exception('Error: {0} {1}'.format(resp.status_code, resp.reason))


def _scholar_score(txt, bib):
    # high score means high similarity
    from fuzzywuzzy.fuzz import token_set_ratio
    return sum([token_set_ratio(bib[k], txt) for k in ['title', 'author', 'abstract'] if k in bib])


@cached(os.path.join(config.cache, 'scholar-bibtex.json'), hashed_key=True)
def fetch_bibtex_by_fulltext_scholar(txt, assess_results=True):
    import scholarly
    scholarly._get_page = _get_page_fast  # remove waiting time
    logging.debug(txt)
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
        raise NotImplementedError('no bibtex import linke. Make crossref request using title?')
    return bibtex



def _crossref_get_author(res, sep=u'; '):
    return sep.join([p.get('given','') + p['family'] for p in res.get('author',[]) if 'family' in p])


def _crossref_score(txt, r):
    # high score means high similarity
    from fuzzywuzzy.fuzz import token_set_ratio
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
        bib['author'] = ' and '.join([p.get('given','') + ' '+ family(p)
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
    year = str(bib.get('year','XXXX'))
    if 'author' in r:
        ID = r['author'][0]['family'] + u'_' + six.u(year)
    else:
        ID = year
    # if six.PY2:
        # ID = str(''.join([c if ord(c) < 128 else '_' for c in ID]))  # make sure the resulting string is ASCII
    bib['ID'] = ID

    db = bibtexparser.loads('')
    db.entries.append(bib)
    return bibtexparser.dumps(db)


# @cached(os.path.join(config.cache, 'crossref-bibtex-fulltext.json'), hashed_key=True)
def fetch_bibtex_by_fulltext_crossref(txt, **kw):
    work = Works(etiquette=my_etiquette)
    logging.debug(six.u('crossref fulltext seach:\n')+six.u(txt))

    # get the most likely match of the first results
    # results = []
    # for i, r in enumerate(work.query(txt).sort('score')):
    #     results.append(r)
    #     if i > 50:
    #         break
    query = work.query(txt, **kw).sort('score')
    query_result = query.do_http_request('get', query.url, custom_header=str(query.etiquette)).text
    results = json.loads(query_result)['message']['items']

    if len(results) > 1:
        maxscore = 0
        result = results[0]
        for res in results:
            score = _crossref_score(txt, res)
            if score > maxscore:
                maxscore = score
                result = res
        logging.info('score: '+str(maxscore))

    elif len(results) == 0:
        raise ValueError('crossref fulltext: no results')

    else:
        result = results[0]

    # convert to bibtex
    return crossref_to_bibtex(result).strip()

