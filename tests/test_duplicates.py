"""Tests for papers duplicate detection and merging (21% -> higher coverage)"""
import os
import subprocess as sp
import tempfile
import unittest

import bibtexparser
from papers.entries import parse_string as bp_parse_string

from papers.bib import Biblio
from papers.duplicate import (
    search_duplicates,
    list_duplicates,
    list_uniques,
    groupby_equal,
    merge_entries,
    MergedEntry,
    ConflictingField,
)
from papers.entries import entry_from_dict, get_entry_val
from tests.common import PAPERSCMD, paperscmd, BibTest


class TestDuplicateSearch(unittest.TestCase):
    """Unit tests for search_duplicates, list_duplicates, list_uniques"""

    def test_search_duplicates_by_key(self):
        entries = [(1, 0), (1, 1), (1, 2), (2, 0), (3, 0), (2, 1), (4, 0)]
        uniques, dups = search_duplicates(entries, key=lambda e: e[0])
        self.assertEqual(len(uniques), 2)  # (3,0) and (4,0)
        self.assertEqual(len(dups), 2)  # 2 groups of duplicates
        self.assertEqual(len(dups[0]), 3)  # three (1,x)
        self.assertEqual(len(dups[1]), 2)  # two (2,x)

    def test_list_duplicates_returns_all_duplicate_entries(self):
        entries = [(1, 0), (1, 1), (2, 0), (2, 1)]
        result = list_duplicates(entries, key=lambda e: e[0])
        # list_duplicates returns entries in duplicate groups (groups with len > 1)
        self.assertEqual(len(result), 4)  # (1,0), (1,1), (2,0), (2,1)

    def test_list_uniques_returns_only_unique_entries(self):
        entries = [(1, 0), (1, 1), (3, 0), (4, 0)]
        result = list_uniques(entries, key=lambda e: e[0])
        self.assertEqual(len(result), 2)  # (3,0), (4,0)


class TestGroupbyEqual(unittest.TestCase):

    def test_groups_by_equality(self):
        entries = [(1, 0), (1, 1), (1, 2), (2, 0), (3, 0), (2, 1), (4, 0)]
        groups = groupby_equal(entries, eq=lambda e1, e2: e1[0] == e2[0])
        self.assertEqual(len(groups), 4)


class TestMergeEntries(unittest.TestCase):

    def test_merge_identical_entries(self):
        e1 = {"author": "Smith", "year": "2020"}
        e2 = {"author": "Smith", "year": "2020"}
        merged = merge_entries([e1, e2])
        self.assertEqual(merged["author"], "Smith")
        self.assertEqual(merged["year"], "2020")

    def test_merge_conflicting_entries(self):
        e1 = {"author": "Smith", "year": "2020"}
        e2 = {"author": "Jones", "year": "2020"}
        merged = merge_entries([e1, e2])
        self.assertIsInstance(merged["author"], ConflictingField)
        self.assertEqual(merged["year"], "2020")

    def test_merge_force_resolves_conflicts(self):
        e1 = {"author": "Smith"}
        e2 = {"author": "Jones"}
        merged = merge_entries([e1, e2], force=True)
        self.assertIsInstance(merged, dict)
        self.assertIn(merged["author"], ["Smith", "Jones"])


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
        """test Biblio's eq method for duplicates.
        Parse a and b separately so v2 (which collapses duplicate keys in one parse) yields two entries.
        """
        db1 = bp_parse_string(a)
        db2 = bp_parse_string(b)
        e1, e2 = db1.entries[0], db2.entries[0]
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


class TestInsertEntryCheckSimilarityLevels(unittest.TestCase):
    """
    Test that insert_entry(..., check_duplicate=True) applies each similarity level
    correctly. Protects the duplicate-check logic (and index optimization) from
    regressions: duplicates must be merged, non-duplicates must be added.
    """

    def _add_entry(self, biblio, entry_dict, check_duplicate=True, on_conflict='u'):
        entry = entry_from_dict(entry_dict)
        return biblio.insert_entry(
            entry, check_duplicate=check_duplicate, on_conflict=on_conflict
        )

    def test_exact_duplicate_merged_non_duplicate_added(self):
        b = Biblio(similarity='EXACT')
        e1 = {'ENTRYTYPE': 'article', 'ID': 'Key1', 'author': 'Smith', 'title': 'Same', 'doi': '10.1/a', 'year': '2020'}
        self._add_entry(b, e1)
        self.assertEqual(len(b.entries), 1)
        # Same content (including same key) → entry_content_equal → exact duplicate → merge
        e2 = {'ENTRYTYPE': 'article', 'ID': 'Key1', 'author': 'Smith', 'title': 'Same', 'doi': '10.1/a', 'year': '2020'}
        merged = self._add_entry(b, e2)
        self.assertEqual(len(b.entries), 1, 'EXACT: duplicate should be merged')
        self.assertEqual(get_entry_val(merged[0], 'ID', '').lower(), 'key1', 'EXACT: should keep first entry')
        # Different title → not duplicate → add
        e3 = {'ENTRYTYPE': 'article', 'ID': 'Key3', 'author': 'Smith', 'title': 'Other', 'doi': '10.1/b', 'year': '2020'}
        self._add_entry(b, e3)
        self.assertEqual(len(b.entries), 2, 'EXACT: non-duplicate should be added')

    def test_good_duplicate_merged_non_duplicate_added(self):
        b = Biblio(similarity='GOOD')
        e1 = {'ENTRYTYPE': 'article', 'ID': 'Key1', 'author': 'Smith, John', 'title': 'A paper', 'doi': '10.1/a', 'year': '2020'}
        self._add_entry(b, e1)
        self.assertEqual(len(b.entries), 1)
        # Same (doi, authortitle), different key/year → GOOD duplicate → merge
        e2 = {'ENTRYTYPE': 'article', 'ID': 'Key2', 'author': 'Smith, John', 'title': 'A paper', 'doi': '10.1/a', 'year': '2021'}
        self._add_entry(b, e2)
        self.assertEqual(len(b.entries), 1, 'GOOD: duplicate should be merged')
        # Different authortitle → not duplicate
        e3 = {'ENTRYTYPE': 'article', 'ID': 'Key3', 'author': 'Jones', 'title': 'Other', 'doi': '10.1/b', 'year': '2020'}
        self._add_entry(b, e3)
        self.assertEqual(len(b.entries), 2, 'GOOD: non-duplicate should be added')

    def test_fair_duplicate_merged_non_duplicate_added(self):
        b = Biblio(similarity='FAIR')
        e1 = {'ENTRYTYPE': 'article', 'ID': 'Key1', 'author': 'Smith', 'title': 'Paper A', 'doi': '10.1/a', 'year': '2020'}
        self._add_entry(b, e1)
        self.assertEqual(len(b.entries), 1)
        # Same doi, different author/title → FAIR duplicate → merge
        e2 = {'ENTRYTYPE': 'article', 'ID': 'Key2', 'author': 'Jones', 'title': 'Paper B', 'doi': '10.1/a', 'year': '2021'}
        self._add_entry(b, e2)
        self.assertEqual(len(b.entries), 1, 'FAIR: duplicate (same doi) should be merged')
        # Different doi and different authortitle → not duplicate
        e3 = {'ENTRYTYPE': 'article', 'ID': 'Key3', 'author': 'Lee', 'title': 'Other', 'doi': '10.1/b', 'year': '2020'}
        self._add_entry(b, e3)
        self.assertEqual(len(b.entries), 2, 'FAIR: non-duplicate should be added')

    def test_partial_duplicate_merged_non_duplicate_added(self):
        b = Biblio(similarity='PARTIAL')
        e1 = {'ENTRYTYPE': 'article', 'ID': 'Key1', 'author': 'Smith', 'title': 'Same title', 'doi': '10.1/a', 'year': '2020'}
        self._add_entry(b, e1)
        self.assertEqual(len(b.entries), 1)
        # Same authortitle, different doi → PARTIAL duplicate → merge
        e2 = {'ENTRYTYPE': 'article', 'ID': 'Key2', 'author': 'Smith', 'title': 'Same title', 'doi': '10.1/b', 'year': '2021'}
        self._add_entry(b, e2)
        self.assertEqual(len(b.entries), 1, 'PARTIAL: duplicate (same authortitle) should be merged')
        # Different doi and different authortitle → not duplicate
        e3 = {'ENTRYTYPE': 'article', 'ID': 'Key3', 'author': 'Jones', 'title': 'Other', 'doi': '10.1/c', 'year': '2020'}
        self._add_entry(b, e3)
        self.assertEqual(len(b.entries), 2, 'PARTIAL: non-duplicate should be added')

    def test_fuzzy_duplicate_merged_non_duplicate_added(self):
        b = Biblio(similarity='FUZZY')
        # Same authortitle → GOOD duplicate (score 103 >= 100) → merge. Exercises FUZZY full-scan path.
        e1 = {'ENTRYTYPE': 'article', 'ID': 'Key1', 'author': 'Smith, John', 'title': 'Climate change impacts', 'doi': '', 'year': '2020'}
        self._add_entry(b, e1)
        self.assertEqual(len(b.entries), 1)
        e2 = {'ENTRYTYPE': 'article', 'ID': 'Key2', 'author': 'Smith, John', 'title': 'Climate change impacts', 'doi': '', 'year': '2021'}
        self._add_entry(b, e2)
        self.assertEqual(len(b.entries), 1, 'FUZZY: duplicate (same authortitle) should be merged')
        # Clearly different → not duplicate
        e3 = {'ENTRYTYPE': 'article', 'ID': 'Key3', 'author': 'Jones', 'title': 'Unrelated topic', 'doi': '10.1/x', 'year': '2020'}
        self._add_entry(b, e3)
        self.assertEqual(len(b.entries), 2, 'FUZZY: non-duplicate should be added')

    def test_batch_add_with_index_same_result_as_single_add(self):
        """Index optimization (add_bibtex) must yield same duplicate result as single inserts."""
        bib_with_dup = """@article{Key1,
 author = {Smith},
 title = {Same},
 doi = {10.1/a},
 year = {2020}
}
@article{Key2,
 author = {Smith},
 title = {Same},
 doi = {10.1/a},
 year = {2021}
}
"""
        b = Biblio(similarity='PARTIAL')
        b.add_bibtex(bib_with_dup, check_duplicate=True, on_conflict='u')
        # Key1 and Key2 are GOOD/PARTIAL duplicates (same doi, same authortitle) → merged to one
        self.assertEqual(len(b.entries), 1, 'add_bibtex with duplicate pair should merge (index path)')
        # Same bib added one-by-one should also merge
        b2 = Biblio(similarity='PARTIAL')
        db = bp_parse_string(bib_with_dup)
        for e in db.entries:
            b2.insert_entry(e, check_duplicate=True, on_conflict='u')
        self.assertEqual(len(b2.entries), 1, 'single inserts with duplicate pair should merge (no-index path)')


class TestDuplicates(TestDuplicatesPartial):

    @staticmethod
    def isduplicate(a, b):
        """test Biblio's eq method for duplicates.
        Parse a and b separately so v2 yields two entries."""
        db1 = bp_parse_string(a)
        db2 = bp_parse_string(b)
        e1, e2 = db1.entries[0], db2.entries[0]
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
        # Write conflict first so parse order is (1)=AnotherKey, (2)=Perrette_2011; pick 1/2 tests rely on this order
        open(self.mybib, 'w').write(self.conflict + '\n\n' + self.original)

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

