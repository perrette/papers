"""Unit tests of the remaining branches of papers.merge, papers.duplicate and
papers.identifiers"""
import os
import tempfile
import unittest
from unittest import mock

from papers.duplicate import (Distinct, IdentityIndex, SAME, Verdict, find_duplicates, identity, parse_name,
                              _side_matches)
from papers.entries import parse_string
from papers.identifiers import normalize_isbn
from papers.merge import SAME as UNCHANGED, Answer, Decision, Dialogue, FieldMerge, Merge, Resolver, _oneline, ask


def entries(bibtex):
    return parse_string(bibtex).entries


A = '@article{a, author = {Smith, John}, doi = {10.1000/a}, journal = {J1}, title = {T}, year = {2000}}'
B = '@article{b, author = {Smith, John}, doi = {10.1000/a}, journal = {J2}, title = {T}, year = {2000}}'
C = '@article{c, author = {Smith, John}, doi = {10.1000/a}, journal = {J2}, title = {T}, year = {2000}}'


class TestMerge(unittest.TestCase):

    def test_three_way_needs_two_entries(self):
        a, b, c = entries(A + B + C)
        with self.assertRaises(ValueError):
            Merge([a, b, c], base=a)

    def test_empty_values(self):
        f = FieldMerge('note', ['', None])
        self.assertEqual((f.status, f.value), (UNCHANGED, ''))

    def test_alternatives_group_equal_values(self):
        # entries 2 and 3 have the same journal: one alternative for both
        merge = Merge(entries(A + B + C), keys_to_ids=True)
        f = next(f for f in merge.conflicts if f.name == 'journal')
        self.assertEqual(f.alternatives(), [([1, 2], 'J2')])
        self.assertIn('Entries 2, 3 are removed after the merge', Dialogue(merge, 'check').summary())

    def test_parse_edit_malformed_field(self):
        merge = Merge(entries(A + B))
        with self.assertLogs('papers', level='ERROR'):
            self.assertIsNone(merge.parse_edit('@article{a,\n bad.name = {x}\n}\n'))

    def test_parse_edit_error(self):
        merge = Merge(entries(A + B))
        with mock.patch('papers.merge.parse_string', side_effect=ValueError('bad')), \
                self.assertLogs('papers', level='ERROR'):
            self.assertIsNone(merge.parse_edit('@article{a}'))

    def test_oneline(self):
        self.assertEqual(_oneline('a  b\n c'), 'a b c')
        self.assertEqual(_oneline('abcdefghij', width=6), 'abc...')

    def test_reprs(self):
        self.assertEqual(repr(Answer('take', 1)), "Answer('take', 1)")
        self.assertEqual(repr(Decision('skip')), "Decision('skip')")
        self.assertEqual(repr(Verdict(SAME, 'same DOI')), "Verdict('same', 'same DOI')")

    def test_bad_mode(self):
        with self.assertRaises(ValueError):
            Resolver('maybe')


class TestDialogue(unittest.TestCase):

    def test_check_help(self):
        merge = Merge(entries(A + B), keys_to_ids=True)
        help = Dialogue(merge, 'check').help()
        self.assertIn('t N', help)
        self.assertIn('not the same paper', help)

    def test_f_without_field_questions(self):
        a, b = entries(A + A.replace('{a,', '{b,'))
        dialogue = Dialogue(Merge([a, b]), 'add')
        self.assertEqual(dialogue.parse('f').kind, 'invalid')

    def test_field_question_edit(self):
        outputs = []
        answers = iter(['f', 'e'])
        merge = Merge(entries(A + B))
        with mock.patch('papers.merge.edit_text', return_value=A.replace('J1', 'J3')):
            decision = ask(merge, 'add', input=lambda prompt: next(answers), output=outputs.append, color=False)
        self.assertEqual(decision.kind, 'merge')
        self.assertEqual(decision.entry['journal'], 'J3')


class TestDuplicate(unittest.TestCase):

    def test_verdict_equality(self):
        self.assertEqual(Verdict(SAME, 'x'), SAME)
        self.assertEqual(Verdict(SAME, 'x'), Verdict(SAME, 'x'))
        self.assertNotEqual(Verdict(SAME, 'x'), 1)

    def test_parse_name(self):
        self.assertEqual(parse_name('Smith, John'), ('Smith', 'John'))
        self.assertEqual(parse_name('John {van der Berg}'), ('{van der Berg}', 'John'))
        self.assertEqual(parse_name(''), ('', ''))
        self.assertEqual(parse_name('{Smith, Jones and Co}'), ('{Smith, Jones and Co}', ''))
        self.assertEqual(parse_name('{Smith, Jones}, Ltd'), ('{Smith, Jones}', 'Ltd'))

    def test_split_names_outside_braces(self):
        from papers.duplicate import split_names, author_id
        self.assertEqual(split_names('{Barnes and Noble} and Smith, J.'), ['{Barnes and Noble}', 'Smith, J.'])
        self.assertEqual(author_id({'author': '{Barnes and Noble} and Smith, J.'}), 'barnes and noble smith')

    def test_identity_of_a_book(self):
        book, = entries('@book{b, isbn = {0-306-40615-2}, title = {T}}')
        self.assertEqual(identity(book), {'isbn': '9780306406157', 'title': 't'})

    def test_side_matches_empty(self):
        self.assertFalse(_side_matches({}, {'doi': '10.1/a'}))

    def test_distinct_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'distinct.json')
            with open(path, 'w') as f:
                f.write('[1, 2]')  # not a dict
            with self.assertLogs('papers', level='WARNING'):
                self.assertEqual(Distinct.load(path).pairs, [])

    def test_distinct_add_without_identity(self):
        a, = entries('@misc{a}')
        b, = entries(A)
        distinct = Distinct()
        distinct.add(a, b)
        self.assertEqual(distinct.pairs, [])
        self.assertFalse(distinct.changed)

    def test_find_duplicates_of_other_entries_only(self):
        # the index may hold entries that are not in the list searched
        a, b = entries(A + B)
        index = IdentityIndex([a, b])
        self.assertEqual(find_duplicates(a, [a], index=index), [])
        self.assertEqual([e.key for e, _ in find_duplicates(a, [a, b], index=index)], ['b'])

    def test_isbn_prefix(self):
        self.assertEqual(normalize_isbn('ISBN: 978-0-306-40615-7'), '9780306406157')


def test_bare_value_stays_bare():
    # month = jan is a bibtex month name, not the text "jan": a merge keeps it bare
    from papers.entries import format_library, library_from_entries, parse_string
    from papers.merge import Merge
    a, b = parse_string('@article{a, month = jan, title = {T}}\n@article{b, title = {T}, year = {2000}}').entries
    text = format_library(library_from_entries([Merge([a, b]).result()]))
    assert ' month = jan,' in text, text
    assert ' year = {2000}' in text, text
    # written into the library entry
    from papers.merge import apply_entry
    apply_entry(b, Merge([b, a]).result())
    assert ' month = jan,' in format_library(library_from_entries([b]))
