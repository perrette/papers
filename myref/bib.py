from __future__ import print_function
import os, json
import logging
logging.basicConfig(level=logging.INFO)
import argparse
import subprocess as sp
import shutil

import bibtexparser

from myref.sortedcollection import SortedCollection


def getentryfiles(e):
    'list of (fname, ftype) '
    files = e.get('file','').strip()
    if not files: 
        return []
    else:
        return [ef.split(':') for ef in files.split(';') ]

def setentryfiles(e, files):
    efiles = []
    for file in files: 
        base, ext = os.path.splitext(file)
        efiles.append(file + ':' + ext[1:])
    e['file'] = ';'.join(efiles)


def move(f1, f2):
    dirname = os.path.dirname(f2)
    if not os.path.exists(dirname):
        logging.info('create directory: '+dirname)
        os.makedirs(dirname)
    logging.info('mv '+f1+' '+f2)
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
        if keys and keys[i] == self.key(e):
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
        setentryfiles(entry, files)

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


def extract_doi(pdf, txtdir='/tmp'):
    txtfile = os.path.join(txtdir, pdf + '.txt')
    if not os.path.exists(txtfile):
        sp.check_call(['pdftotext',pdf, txtfile])
    else:
        logging.info('file already present: '+txtfile)
    cmd = "grep -o 'doi:.*[^ ,]\+' '{}' | head -1".format(txtfile)
    logging.info(cmd)
    output = sp.check_output(cmd, shell=True).format(txtfile)
    if not output.startswith('doi:'):
        raise ValueError('failed to extract doi')
    return output[4:].strip()


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

    my.add_pdf(o.pdf, rename=o.rename, attachments=o.attachments)
    my.save()

if __name__ == '__main__':
    main()
