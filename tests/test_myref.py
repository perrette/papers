from __future__ import absolute_import

import unittest
import os, subprocess as sp

from utils import myref
from download import downloadpdf


def run(cmd):
    return sp.check_output(cmd, shell=True)


class Test(unittest.TestCase):

    def setUp(self):
        self.pdf = downloadpdf('bg-8-515-2011.pdf')
        self.doi = '10.5194/bg-8-515-2011'

    def test_doi(self):
        self.assertEqual(run('myref doi '+self.pdf).strip(), self.doi)

    def test_bibtex(self):
        bibtex = """@article{Perrette_2011,
	doi = {10.5194/bg-8-515-2011},
	url = {https://doi.org/10.5194%2Fbg-8-515-2011},
	year = 2011,
	month = {feb},
	publisher = {Copernicus {GmbH}},
	volume = {8},
	number = {2},
	pages = {515--524},
	author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
	title = {Near-ubiquity of ice-edge blooms in the Arctic},
	journal = {Biogeosciences}
}"""
        self.assertEqual(run('myref fetch '+self.doi).strip(), bibtex)
	    

if __name__ == '__main__':
    unittest.main()
