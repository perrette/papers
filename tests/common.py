import subprocess as sp
import unittest
import difflib
from tests.download import downloadpdf

# Using python -m papers instead of papers otherwise pytest --cov does not detect the call
PAPERSCMD = f'python3 -m papers'

def paperscmd(cmd, sp_cmd="check_output"):
    return run(f'{PAPERSCMD} '+cmd, sp_cmd=sp_cmd)

def run(cmd, sp_cmd="check_output"):
    print(cmd)
    if sp_cmd == "check_output":
        return str(sp.check_output(cmd, shell=True).strip().decode())
    else:
        return str(getattr(sp, sp_cmd)(cmd, shell=True))



def prepare_paper():
    pdf = downloadpdf('bg-8-515-2011.pdf')
    doi = '10.5194/bg-8-515-2011'
    key = 'Perrette_2011'
    newkey = 'perrette_yool2011'
    year = '2011'
    bibtex = """@article{Perrette_2011,
    author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
    doi = {10.5194/bg-8-515-2011},
    journal = {Biogeosciences},
    month = {feb},
    number = {2},
    pages = {515--524},
    publisher = {Copernicus {GmbH}},
    title = {Near-ubiquity of ice-edge blooms in the Arctic},
    url = {https://doi.org/10.5194%2Fbg-8-515-2011},
    volume = {8},
    year = 2011,
}"""

    file_rename = "perrette_et_al_2011_near-ubiquity-of-ice-edge-blooms-in-the-arctic.pdf"

    return pdf, doi, key, newkey, year, bibtex, file_rename


def prepare_paper2():
    pdf = downloadpdf('esd-4-11-2013.pdf')
    si = downloadpdf('esd-4-11-2013-supplement.pdf')
    doi = '10.5194/esd-4-11-2013'
    key = 'Perrette_2013'
    newkey = 'perrette_landerer2013'
    year = '2013'
    bibtex = """@article{Perrette_2013,
    author = {M. Perrette and F. Landerer and R. Riva and K. Frieler and M. Meinshausen},
    doi = {10.5194/esd-4-11-2013},
    journal = {Earth System Dynamics},
    month = {jan},
    number = {1},
    pages = {11--29},
    publisher = {Copernicus {GmbH}},
    title = {A scaling approach to project regional sea level rise and its uncertainties},
    url = {https://doi.org/10.5194%2Fesd-4-11-2013},
    volume = {4},
    year = 2013,
}"""
    file_rename = "perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf"

    return pdf, si, doi, key, newkey, year, bibtex, file_rename



class BibTest(unittest.TestCase):
    """base class for bib tests: create a new bibliography
    """

    def assertMultiLineEqual(self, first, second, msg=None):
        """Assert that two multi-line strings are equal.

        If they aren't, show a nice diff.
        source: https://stackoverflow.com/a/3943697/2192272
        """
        self.assertTrue(isinstance(first, str),
                'First argument is not a string')
        self.assertTrue(isinstance(second, str),
                'Second argument is not a string')

        if first != second:
            message = ''.join(difflib.ndiff(first.splitlines(True),
                                                second.splitlines(True)))
            if msg:
                message += " : " + msg
            self.fail("Multi-line strings are unequal:\n" + message)

