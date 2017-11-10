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

from myref.config import config

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

    # quality check 
    assert len(doi) > 8, 'failed to extract doi: '+doi

    return doi 


def isvaliddoi(doi):
    try:
        doi2 = parse_doi(doi)
    except:
        return False
    return doi == doi2


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


def extract_txt_metadata(txt, search_doi=True, search_fulltext=False, space_digit=True, max_query_words=200):
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
        bibtex = fetch_bibtex_by_fulltext(query_txt)
        logging.debug('fulltext query successful')

    if not bibtex:
        raise ValueError('failed to extract metadata')

    return bibtex


def extract_pdf_metadata(pdf, search_doi=True, search_fulltext=True, maxpages=10, minwords=200, **kw):
    txt = pdfhead(pdf, maxpages, minwords)
    return extract_txt_metadata(txt, search_doi, search_fulltext, **kw)



def ask_doi(max=3):
    doi = raw_input('doi : ')
    count = 1
    while not isvaliddoi(doi):
        count += 1
        if count > max:
            raise ValueError('invalid doi: '+doi)
        doi = raw_input('Valid DOI looks like 10.NNNN/... Please try again. doi : ')
    return doi


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
    response = six.moves.urllib.request.urlopen(url)
    bibtex = response.read()
    if six.PY3:
        bibtex = bibtex.decode()
    return bibtex.strip()

@cached(os.path.join(config.cache, 'crossref.json'))
def fetch_json_by_doi(doi):
    url = "http://api.crossref.org/works/"+doi+"/transform/application/json"
    response = six.moves.urllib.request.urlopen(url)
    jsontxt = response.read()
    if six.PY3:
        jsontxt = jsontxt.decode()
    return jsontxt.dumps(json)


def _get_page_fast(pagerequest):
    """Return the data for a page on scholar.google.com"""
    import scholarly
    resp = scholarly._SESSION.get(pagerequest, headers=scholarly._HEADERS, cookies=scholarly._COOKIES)
    if resp.status_code == 200:
        return resp.text
    else:
        raise Exception('Error: {0} {1}'.format(resp.status_code, resp.reason))


def _score_scholar(txt, bib):
    # high score means high similarity
    from fuzzywuzzy.fuzz import token_set_ratio
    return sum([token_set_ratio(bib[k], txt) for k in ['title', 'author', 'abstract'] if k in bib])

@cached(os.path.join(config.cache, 'scholar-bibtex.json'), hashed_key=True)
def fetch_bibtex_by_fulltext(txt, assess_results=True):
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
            score = _score_scholar(txt, res.bib)
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

# url = "http://api.crossref.org/works/"+doi+"/transform/application/x-bibtex"
    # response = six.moves.urllib.request.urlopen(url)
    # bibtex = response.read()
    # if six.PY3:
        # bibtex = bibtex.decode()
    return bibtex.strip()


def json_to_bibtex(js):
    raise NotImplementedError()

def bibtex_to_json(js):
    raise NotImplementedError()



    # Parse / format bibtex file entry
# ================================

def _parse_file(file):
    """ parse a single file entry
    """
    sfile = file.split(':')
    
    if len(sfile) == 1:  # no ':'
        path, type = file, ''

    elif len(sfile) == 2:
        path, type = sfile

    elif len(sfile) == 3:
        basename, path, type = sfile

    else:
        raise ValueError('unknown `file` format: '+ repr(file))

    return path


def _format_file(file, type=None):
    if not type:
        type = os.path.splitext(file)[1].strip('.')
    return ':'+file+':'+type


def parse_file(file):
    if not file:
        return []
    else:
        return [_parse_file(f) for f in file.split(';')]


def format_file(file_types):
    return ';'.join([_format_file(f) for f in file_types])

