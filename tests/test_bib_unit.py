"""Unit tests for papers.bib helpers (66% -> higher coverage)"""
import unittest

from papers.bib import (
    append_abc,
    isvalidkey,
    compare_entries,
    are_duplicates,
    EXACT_DUPLICATES,
    GOOD_DUPLICATES,
    FAIR_DUPLICATES,
    PARTIAL_DUPLICATES,
)


class TestAppendAbc(unittest.TestCase):

    def test_append_b_to_new_key(self):
        self.assertEqual(append_abc('Author2000'), 'Author2000b')

    def test_append_c_after_b(self):
        self.assertEqual(append_abc('Author2000b'), 'Author2000c')

    def test_with_existing_keys(self):
        result = append_abc('Author2000', ['Author2000', 'Author2000b'])
        self.assertEqual(result, 'Author2000c')


class TestIsvalidkey(unittest.TestCase):

    def test_valid_key(self):
        self.assertTrue(isvalidkey('Author2020'))
        self.assertTrue(isvalidkey('Smith'))

    def test_invalid_starts_with_digit(self):
        self.assertFalse(isvalidkey('2020Author'))
        self.assertFalse(isvalidkey('10.5194/bg-8-515-2011'))

    def test_empty_key(self):
        self.assertFalse(isvalidkey(''))
        self.assertFalse(isvalidkey(None))


class TestCompareEntries(unittest.TestCase):

    def test_exact_duplicates(self):
        e = {"author": "Smith", "title": "Test", "year": "2020", "doi": "10.1234/test"}
        self.assertEqual(compare_entries(e, e), EXACT_DUPLICATES)

    def test_good_duplicates_same_author_title_doi(self):
        e1 = {"author": "Smith, John", "title": "A paper", "year": "2020", "doi": "10.1234/test"}
        e2 = {"author": "Smith, John", "title": "A paper", "year": "2021", "doi": "10.1234/test"}
        self.assertEqual(compare_entries(e1, e2), GOOD_DUPLICATES)

    def test_partial_duplicates_same_author_title_diff_doi(self):
        e1 = {"author": "Smith, John", "title": "A paper", "year": "2020", "doi": "10.1234/a"}
        e2 = {"author": "Smith, John", "title": "A paper", "year": "2020", "doi": "10.1234/b"}
        self.assertEqual(compare_entries(e1, e2), PARTIAL_DUPLICATES)

    def test_fair_duplicates_same_doi(self):
        e1 = {"author": "Smith", "title": "Paper A", "year": "2020", "doi": "10.5194/bg-8-515-2011"}
        e2 = {"author": "Jones", "title": "Paper B", "year": "2021", "doi": "10.5194/bg-8-515-2011"}
        self.assertEqual(compare_entries(e1, e2), FAIR_DUPLICATES)


class TestAreDuplicates(unittest.TestCase):

    def test_exact_are_duplicates(self):
        e = {"author": "Smith", "title": "Test", "year": "2020"}
        self.assertTrue(are_duplicates(e, e, similarity="EXACT"))

    def test_partial_same_doi(self):
        e1 = {"author": "A", "title": "X", "doi": "10.1234/x"}
        e2 = {"author": "B", "title": "Y", "doi": "10.1234/x"}
        self.assertTrue(are_duplicates(e1, e2, similarity="PARTIAL"))
