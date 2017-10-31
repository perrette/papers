from __future__ import print_function
import os, json
import logging
logging.basicConfig(level=logging.INFO)
import argparse
import subprocess as sp
import shutil
import re
import bisect

import bibtexparser

from myref.sortedcollection import SortedCollection


def getentryfiles(e):
    'list of (fname, ftype) '
    files = e.get('file','').strip()
    if not files: 
        return []
    else:
        return [ef.split(':') for ef in files.split(';') ]

def setentryfiles(e, files, overwrite=True):
    if not overwrite:
        existingfiles = [fname for fname, ftype in getentryfiles(e)]
    else:
        existingfiles = []
    efiles = []
    for file in files: 
        base, ext = os.path.splitext(file)
        efiles.append(file + ':' + ext[1:])
    e['file'] = ';'.join(efiles + existingfiles)


def move(f1, f2):
    dirname = os.path.dirname(f2)
    if not os.path.exists(dirname):
        logging.info('create directory: '+dirname)
        os.makedirs(dirname)
    cmd = 'mv '+f1.decode('utf-8')+' '+f2
    logging.info(cmd)
    shutil.move(f1, f2)


# main config
# ===========
class MyRef(object):
    """main config
    """
    def __init__(self, bibtex, filesdir):
        self.filesdir = filesdir
        self.txt = '/tmp'
        self.bibtex = bibtex
        self.db = bibtexparser.load(open(bibtex))
        # assume an already sorted list
        self.key_field = 'ID'

    @classmethod
    def newbib(cls, bibtex, filesdir):
        assert not os.path.exists(bibtex)
        open(bibtex,'w').write('')
        return cls(bibtex, filesdir)


    def key(self, e):
        return e[self.key_field]

    def sort(self):
        self.db.entries = sorted(self.db.entries, self.key)

    def insert_entry(self, e, replace=False):
        import bisect
        keys = [self.key(ei) for ei in self.db.entries]
        i = bisect.bisect_left(keys, self.key(e))
        if i < len(keys) and keys[i] == self.key(e):
            logging.info('entry already present: '+self.key(e) + replace*' => replace')
            if replace:
                self.db.entries[i] = e
            return self.db.entries[i]
        else:
            logging.info('new entry: '+self.key(e))
            self.db.entries.insert(i, e)
            return e

    def save(self):
        s = bibtexparser.dumps(self.db)
        s = s.encode('utf-8')
        open(self.bibtex, 'w').write(s)


    def rename_entry_files(self, e):

        files = getentryfiles(e)
        # newname = entrydir(e, root)
        direc = os.path.join(self.filesdir, e['year'])

        if not files:
            logging.info('no files to rename')
            return

        if len(files) == 1:
            logging.info('one file to rename')
            file, type = files[0]
            base, ext = os.path.splitext(file)
            newfile = os.path.join(direc, e['ID']+ext)
            move(file, newfile)
            e['file'] = newfile + ':' +type

        # several files: only rename container
        else:
            logging.info('several files to rename')
            newdir = os.path.join(direc, e['ID'])
            efiles = []
            for file, ftype in files:
                newfile = os.path.join(newdir, os.path.basename(file))
                move(file, newfile)
                efiles.append(file + ':' + ftype)
            e['file'] = ';'.join(efiles)


    def add_pdf(self, pdf, rename=False, attachments=None):
        doi = extract_doi(pdf, '.')
        logging.info('found doi:'+doi)

        # get bib tex based on doi
        bibtex = fetch_bibtex(doi)

        bib = bibtexparser.loads(bibtex)
        entry = bib.entries[0]

        # add entry to library
        entry = self.insert_entry(entry, replace=False)

        # add pdf to entry
        files = [pdf]
        if attachments:
            files += attachments
        setentryfiles(entry, files, overwrite=True)

        # rename files
        if rename:
            self.rename_entry_files(entry)


    # @staticmethod
    # def _create_folder(self, name):
    #     if not os.path.exists(name):
    #         logging.info('create: '+name)
    #         os.makedirs(name)
    #     else:
    #         logging.info('folder already present: '+name)        


def readpdf(pdf, txtdir='/tmp'):
    txtfile = os.path.join(txtdir, pdf.replace('.pdf','.txt'))
    if not os.path.exists(txtfile):
        # logging.info(' '.join(['pdftotext','"'+pdf+'"', '"'+txtfile+'"']))
        sp.check_call(['pdftotext',pdf])
    else:
        logging.info('file already present: '+txtfile)
    return open(txtfile).read()


def extract_doi(pdf, txtdir='/tmp', space_digit=True):
    txt = readpdf(pdf, txtdir)

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

    match = re.compile(regexp).findall(txt.lower())[0]

    # clean expression
    doi = match.replace('\n','').strip('.')

    if space_digit:
        doi = doi.replace(' ','_')

    # quality check 
    assert len(doi) > 8, 'failed to extract doi: '+doi

    return doi 

    # # now try out more things
    # cmd = "grep -io -e 'doi:10.[^ ,]\+' \
    #                 -e 'doi: 10.[^ ,]\+' \
    #                 -e 'doi 10.[^ ,]\+' \
    #                 -e 'dx.doi.org/10.[^ ,]\+' \
    #                 -e 'doi/10.[^ ,]\+' \
    #                 '{}' | head -1".format(txtfile)
    # # logging.info(cmd)
    # output = sp.check_output(cmd, shell=True).format(txtfile)
    # if output.lower().startswith('dx.doi.org/'):
    #     return output[11:].strip()
    # for c in '[]{}':
    #     if c in output:
    #         raise ValueError('invalid doi: '+str(output))
    # if not output.lower().startswith('doi'):
    #     raise ValueError('failed to extract doi: '+str(output))
    # return output[4:].strip().strip('.')


def cached(file):
    def decorator(fun):
        if os.path.exists(file):
            cache = json.load(open(file))
        else:
            cache = {}
        def decorated(doi):
            if doi in cache:
                return cache[doi]
            else:
                res = cache[doi] = fun(doi)
                json.dump(cache, open(file,'w'))
            return res
        return decorated
    return decorator


@cached('.crossref-bibtex.json')
def fetch_bibtex(doi):
    import urllib2
    url = "http://api.crossref.org/works/"+doi+"/transform/application/x-bibtex"
    response = urllib2.urlopen(url)
    html = response.read()
    return html.decode('utf-8')

# default_config = Config()

def main():
    parser = argparse.ArgumentParser(description='add PDF to library')
    parser.add_argument('pdf')
    parser.add_argument('--bibtex', default='myref.bib',help='%(default)s')
    parser.add_argument('--filesdir', default='files', help='%(default)s')
    parser.add_argument('-a','--attachments', nargs='+', help='supplementary material')
    parser.add_argument('-r','--rename', action='store_true')
    # parser.add_argument('---','--rename', action='store_true')
    # parser.add_argument('-c', '--config-file', 
        # default=os.path.join(CONFIG_FOLDER, 'config.json'))
    # parser.add_argument('--data-location', default='')
    # parser.add_argument('--pdf-folder', default='pdfs')
    # parser.add_argument('--text-folder', default='texts')
    # parser.add_argument('--bib', default='myref.bib', help='bibtex file')

    o = parser.parse_args()

    if os.path.exists(o.bibtex):
        my = MyRef(o.bibtex, o.filesdir)
    else:
        my = MyRef.newbib(o.bibtex, o.filesdir)

    try:
        my.add_pdf(o.pdf, rename=o.rename, attachments=o.attachments)
    except Exception as error:
        # print(error) 
        # parser.error(str(error))
        raise
        logging.error(str(error))
        parser.exit(1)
    my.save()

if __name__ == '__main__':
    main()
