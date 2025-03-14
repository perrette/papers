import os
import subprocess as sp
import tempfile
import unittest

import bibtexparser

from papers.bib import Biblio
from tests.common import PAPERSCMD, paperscmd, BibTest


class SimilarityBase(unittest.TestCase):

    similarity = None

    reference = """@article{Perrette_2011,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 doi = {10.5194/bg-8-515-2011},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
 year = {2011}
}"""

    anotherkey = """@article{OtherKey,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 doi = {10.5194/bg-8-515-2011},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
 year = {2011}
}"""

    missingfield = """@article{Perrette_2011,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 doi = {10.5194/bg-8-515-2011},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
}"""

    missingdoi = """@article{Perrette_2011,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
}"""

    missingtitauthor = """@article{Perrette_2011,
 doi = {10.5194/bg-8-515-2011},
}"""

    conflictauthor = """@article{Perrette_2011,
 author = {SomeOneElse},
 doi = {10.5194/bg-8-515-2011},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
}"""

    conflictdoi = """@article{Perrette_2011,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 doi = {10.5194/XXX},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
}"""

    conflictyear = """@article{Perrette_2011,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 doi = {10.5194/bg-8-515-2011},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
 year = {2012}
}"""


    def isduplicate(self, a, b):
        """test Biblio's eq method for duplicates
        """
        db = bibtexparser.loads(a+'\n'+b)
        e1, e2 = db.entries
        refs = Biblio(similarity=self.similarity)
        return refs.eq(e1, e2)


class TestDuplicatesExact(SimilarityBase):

    similarity = 'EXACT'

    def test_exactsame(self):
        self.assertTrue(self.isduplicate(self.reference, self.reference))

    def test_anotherkey(self):
        self.assertFalse(self.isduplicate(self.reference, self.anotherkey))

    def test_missingfield(self):
        self.assertFalse(self.isduplicate(self.reference, self.missingfield))

    def test_missingdoi(self):
        self.assertFalse(self.isduplicate(self.reference, self.missingdoi))

    def test_missingtitauthor(self):
        self.assertFalse(self.isduplicate(self.reference, self.missingtitauthor))

    def test_conflictauthor(self):
        self.assertFalse(self.isduplicate(self.reference, self.conflictauthor))

    def test_conflictdoi(self):
        self.assertFalse(self.isduplicate(self.reference, self.conflictdoi))

    def test_conflictyear(self):
        self.assertFalse(self.isduplicate(self.reference, self.conflictyear))


class TestDuplicatesGood(TestDuplicatesExact):

    similarity = 'GOOD'

    def test_anotherkey(self):
        self.assertTrue(self.isduplicate(self.reference, self.anotherkey))

    def test_missingfield(self):
        self.assertTrue(self.isduplicate(self.reference, self.missingfield))

    def test_conflictyear(self):
        self.assertTrue(self.isduplicate(self.reference, self.conflictyear))


class TestDuplicatesFair(TestDuplicatesGood):

    similarity = 'FAIR'

    def test_missingtitauthor(self):
        self.assertTrue(self.isduplicate(self.reference, self.missingtitauthor))

    def test_conflictauthor(self):
        self.assertTrue(self.isduplicate(self.reference, self.conflictauthor))


class TestDuplicatesPartial(TestDuplicatesFair):

    similarity = 'PARTIAL'

    def test_missingdoi(self):
        self.assertTrue(self.isduplicate(self.reference, self.missingdoi))

    def test_conflictdoi(self):
        self.assertTrue(self.isduplicate(self.reference, self.conflictdoi))


class TestDuplicates(TestDuplicatesPartial):

    @staticmethod
    def isduplicate(a, b):
        """test Biblio's eq method for duplicates
        """
        db = bibtexparser.loads(a+'\n'+b)
        e1, e2 = db.entries
        refs = Biblio()
        return refs.eq(e1, e2)


class TestDuplicatesAdd(TestDuplicates):

    def setUp(self):
        self.mybib = tempfile.mktemp(prefix='papers.bib')
        self.otherbib = tempfile.mktemp(prefix='papers.otherbib')

    def tearDown(self):
        os.remove(self.mybib)
        os.remove(self.otherbib)

    def isduplicate(self, a, b):
        """test Biblio's eq method in 'add' mode
        """
        open(self.mybib, 'w').write(a)
        open(self.otherbib, 'w').write(b)
        res = paperscmd(f'add {self.otherbib} --bibtex {self.mybib} --update-key --mode r --debug', sp_cmd="call")
        return res != 0

    @unittest.skip("skip cause does not make sense with add")
    def test_exactsame(self):
        pass

    @unittest.skip("skip cause does not make sense with add")
    def test_anotherkey(self):
        pass



class TestAddResolveDuplicate(BibTest):

    original = """@article{Perrette_2011,
 doi = {10.5194/bg-8-515-2011},
 journal = {Biogeosciences},
 year = {RareYear}
}"""


    conflict = """@article{AnotherKey,
 author = {New Author Field},
 doi = {10.5194/bg-8-515-2011},
 journal = {ConflictJournal}
}"""


    def setUp(self):
        self.mybib = tempfile.mktemp(prefix='papers.bib')
        self.otherbib = tempfile.mktemp(prefix='papers.otherbib')
        open(self.mybib, 'w').write(self.original)

    def tearDown(self):
        os.remove(self.mybib)
        os.remove(self.otherbib)

    def command(self, mode):
        return f'echo {mode} | {PAPERSCMD} add {self.otherbib} --bibtex {self.mybib} --debug'

    def test_overwrite(self):

        expected = self.conflict

        open(self.otherbib, 'w').write(self.conflict)
        sp.check_call(self.command('o'), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change


    def test_skip(self):

        expected = self.original

        open(self.otherbib, 'w').write(self.conflict)
        sp.check_call(self.command('s'), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_append(self):
        open(self.otherbib, 'w').write(self.conflict)
        sp.check_call(self.command('a'), shell=True)
        # paperscmd(f'add {} --bibtex {} --debug'.format(self.otherbib, self.mybib))
        expected = self.conflict + '\n\n' + self.original
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change


    def test_raises(self):
        # update key to new entry, but does not merge...
        open(self.otherbib, 'w').write(self.conflict)
        func = lambda: sp.check_call(self.command('r'), shell=True)
        self.assertRaises(Exception, func)


    def test_original_updated_from_conflict(self):

        expected = """@article{Perrette_2011,
 author = {New Author Field},
 doi = {10.5194/bg-8-515-2011},
 journal = {Biogeosciences},
 year = {RareYear}
}"""

        open(self.otherbib, 'w').write(self.conflict)
        sp.check_call(self.command('u'), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change


    def test_conflict_updated_from_original(self):

        expected = """@article{AnotherKey,
 author = {New Author Field},
 doi = {10.5194/bg-8-515-2011},
 journal = {ConflictJournal},
 year = {RareYear}
}"""

        open(self.otherbib, 'w').write(self.conflict)
        sp.check_call(self.command('U'), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change


    def test_conflict_updated_from_original_but_originalkey(self):

        expected = """@article{10.5194/bg-8-515-2011,
 author = {New Author Field},
 doi = {10.5194/bg-8-515-2011},
 journal = {ConflictJournal},
 year = {RareYear}
}"""
        open(self.otherbib, 'w').write(self.conflict)
        sp.check_call(self.command('U') + ' --update-key', shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change



class TestAddResolveDuplicateCommand(TestAddResolveDuplicate):

    def command(self, mode):
        return f'{PAPERSCMD} add {self.otherbib} --bibtex {self.mybib} --mode {mode} --debug'



class TestCheckResolveDuplicate(BibTest):

    original = """@article{Perrette_2011,
 doi = {10.5194/bg-8-515-2011},
 journal = {Biogeosciences},
 year = {RareYear}
}"""


    conflict = """@article{AnotherKey,
 author = {New Author Field},
 doi = {10.5194/bg-8-515-2011},
 journal = {ConflictJournal}
}"""


    def setUp(self):
        self.mybib = tempfile.mktemp(prefix='papers.bib')
        open(self.mybib, 'w').write(self.original + '\n\n' + self.conflict)

    def tearDown(self):
        os.remove(self.mybib)

    def command(self, mode):
        return f'echo {mode} | {PAPERSCMD} check --duplicates --bibtex {self.mybib} --debug'

    def test_pick_conflict_1(self):

        expected = self.conflict

        sp.check_call(self.command('1'), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change

    def test_pick_reference_2(self):

        expected = self.original

        sp.check_call(self.command('2'), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change


    def test_skip_check(self):

        expected = self.conflict + '\n\n' + self.original

        sp.check_call(self.command('s'), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change


    def test_not_a_duplicate(self):

        expected = self.conflict + '\n\n' + self.original

        sp.check_call(self.command('n'), shell=True)
        self.assertMultiLineEqual(open(self.mybib).read().strip(), expected) # entries did not change


    def test_raises(self):
        # update key to new entry, but does not merge...
        func = lambda: sp.check_call(self.command('r'), shell=True)
        self.assertRaises(Exception, func)


    def test_merge(self):
        # update key to new entry, but does not merge...
        expected = """@article{AnotherKey,
         author = {New Author Field},
         doi = {10.5194/bg-8-515-2011},
         journal = {ConflictJournal},
         year = {RareYear}
        }"""
        func = lambda: sp.check_call(self.command('m\n3'), shell=True)
        self.assertRaises(Exception, func)

