#!/bin/env python3
import os
import logging
import urllib.request

DOWNDIR = os.path.join(os.path.dirname(__file__), 'downloadedpapers')

URL = {
    'bg-8-515-2011.pdf': 'https://www.biogeosciences.net/8/515/2011/bg-8-515-2011.pdf',
    'esd-4-11-2013.pdf': 'https://www.earth-syst-dynam.net/4/11/2013/esd-4-11-2013.pdf',
    'esd-4-11-2013-supplement.pdf': 'https://www.earth-syst-dynam.net/4/11/2013/esd-4-11-2013-supplement.pdf',
}


def _downloadpdf(url, filename, overwrite=False):

    if os.path.exists(filename) and not overwrite:
        logging.info(filename+' already present')
        return

    direc = os.path.dirname(filename)

    if direc and not os.path.exists(direc):
        os.makedirs(direc)

    print('download',url,'to',filename)

    response = urllib.request.urlopen(url)
    resp = response.read()

    with open(filename, 'wb') as f:
        f.write(resp)


def downloadpdf(pdf):
    fname = os.path.join(DOWNDIR, pdf)
    url = URL[pdf]
    _downloadpdf(url, fname)
    return fname


def downloadall():
    for pdf in URL:
        downloadpdf(pdf)


if __name__ == '__main__':
    downloadall()
