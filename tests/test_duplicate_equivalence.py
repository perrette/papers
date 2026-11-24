"""The speed-ups of papers.duplicate (memoized identity, index positions,
Distinct union) give the verdicts of the implementation before them
(tests/duplicate_reference.py), on a generated library with planted
duplicates"""
import random
import unittest

from bibtexparser.model import Entry, Field

import papers.duplicate as new
import tests.duplicate_reference as ref

AUTHORS = ['M{\\"u}ller, J{\\"o}rg', 'Müller, Jörg', 'Smith, John', '{van der Berg}, Jane', 'Ångström, A.',
           'Dupont, Pierre and Martin, Marie', 'Li, Wei and Smith, John', '']
TITLES = ['Sea level rise', 'Sea Level {Rise}', 'Sea   level  rise ', 'Data for: Sea level rise', 'Ice sheets',
          'Ice sheet {\\"O}l', 'Glacier melt', '']


def make_library(n=200, seed=1):
    rnd = random.Random(seed)
    entries = []
    for i in range(n):
        fields = []
        kind = rnd.choice(['article', 'article', 'book', 'incollection', 'misc', 'dataset'])
        if rnd.random() < 0.5:
            fields.append(Field('doi', rnd.choice(['10.1000/A', '10.1000/a', 'https://doi.org/10.1000/a',
                                                   '10.1000/b', '10.48550/arXiv.2101.01234', f'10.1000/{i}'])))
        if rnd.random() < 0.15:
            fields.append(Field('eprint', rnd.choice(['2101.01234', '2101.01234v2', 'hep-th/9901001', '1999.9999'])))
            if rnd.random() < 0.5:
                fields.append(Field('archivePrefix', rnd.choice(['arXiv', 'other'])))
        if rnd.random() < 0.2:
            fields.append(Field('isbn', rnd.choice(['978-3-16-148410-0', '3-16-148410-X', '0-306-40615-2',
                                                    '978-3-16-148410-0, 0-306-40615-2', 'bad'])))
        author = rnd.choice(AUTHORS)
        if author:
            fields.append(Field('author', author))
        title = rnd.choice(TITLES) if rnd.random() < 0.4 else f'Paper number {i % 97}'
        if title:
            fields.append(Field('title', title))
        fields.append(Field('year', str(2000 + i % 5)))
        entries.append(Entry(kind, f'k{i}', fields))
    return entries


def verdict(v):
    return v.kind, v.reason


def describe_found(found):
    return [(id(e), v.kind, v.reason) for e, v in found]


def describe_groups(groups):
    return [([id(e) for e in g.entries], g.kind, g.reason) for g in groups]


class TestEquivalence(unittest.TestCase):

    def setUp(self):
        self.entries = make_library()
        rnd = random.Random(2)
        pairs = []
        for _ in range(30):
            a, b = rnd.sample(self.entries, 2)
            ia, ib = ref.identity(a), ref.identity(b)
            if ia and ib:
                pairs.append([ia, ib])
        self.ref_distinct = ref.Distinct(pairs)
        self.new_distinct = new.Distinct([list(p) for p in pairs])

    def test_identity(self):
        for e in self.entries:
            self.assertEqual(new.identity(e), ref.identity(e))
            self.assertEqual(new.authortitle_id(e), ref.authortitle_id(e))
            self.assertEqual(new.isbn_ids(e), ref.isbn_ids(e))

    def test_same_paper(self):
        rnd = random.Random(3)
        for _ in range(2000):
            a, b = rnd.sample(self.entries, 2)
            for distinct in ((None, None), (self.ref_distinct, self.new_distinct)):
                self.assertEqual(verdict(new.same_paper(a, b, distinct[1])), verdict(ref.same_paper(a, b, distinct[0])))

    def test_planted_cases(self):
        same_doi_other_title = (Entry('article', 'a', [Field('doi', '10.1/x'), Field('title', 'X')]),
                                Entry('dataset', 'b', [Field('doi', '10.1/X'), Field('title', 'Data for: X')]))
        other_doi_same_title = (Entry('article', 'a', [Field('doi', '10.1/x'), Field('title', 'X'), Field('author', 'A, B')]),
                                Entry('article', 'b', [Field('doi', '10.1/y'), Field('title', 'X'), Field('author', 'A, B')]))
        no_doi = (Entry('article', 'a', [Field('title', 'Sea {L}evel'), Field('author', 'M{\\"u}ller, J.')]),
                  Entry('misc', 'b', [Field('title', 'sea level'), Field('author', 'Müller, Jörg')]))
        for (a, b), kind in [(same_doi_other_title, new.ASK), (other_doi_same_title, new.DIFFERENT), (no_doi, new.SAME)]:
            self.assertEqual(new.same_paper(a, b).kind, kind)
            self.assertEqual(verdict(new.same_paper(a, b)), verdict(ref.same_paper(a, b)))

    def test_find_duplicates(self):
        index = new.IdentityIndex(self.entries)
        for e in self.entries:
            expected = describe_found(ref.find_duplicates(e, self.entries, self.ref_distinct))
            self.assertEqual(describe_found(new.find_duplicates(e, self.entries, self.new_distinct)), expected)
            self.assertEqual(describe_found(new.find_duplicates(e, None, self.new_distinct, index=index)), expected)
            self.assertEqual(describe_found(new.find_duplicates(e, self.entries, self.new_distinct, index=index)),
                             expected)

    def test_find_duplicates_in_a_part(self):
        "with an index of all entries, only the entries given are searched, in their order"
        index = new.IdentityIndex(self.entries)
        part = self.entries[::3][::-1]
        for e in self.entries[:100]:
            self.assertEqual(describe_found(new.find_duplicates(e, part, self.new_distinct, index=index)),
                             describe_found(ref.find_duplicates(e, part, self.ref_distinct)))

    def test_updated_entry_keeps_its_position(self):
        index = new.IdentityIndex(self.entries)
        e = self.entries[5]
        index.remove(e)
        e['title'] = 'Glacier melt'
        index.add(e)
        for x in self.entries[:50]:
            self.assertEqual(describe_found(new.find_duplicates(x, None, None, index=index)),
                             describe_found(ref.find_duplicates(x, self.entries)))

    def test_duplicate_groups(self):
        described = []
        for distinct in ((None, None), (self.ref_distinct, self.new_distinct)):
            groups = describe_groups(new.duplicate_groups(self.entries, distinct[1]))
            self.assertEqual(groups, describe_groups(ref.duplicate_groups(self.entries, distinct[0])))
            described.append(groups)
        # the library has groups of both kinds, and the distinct pairs change them
        self.assertEqual({kind for _, kind, _ in described[0]}, {new.SAME, new.ASK})
        self.assertNotEqual(described[0], described[1])

    def test_memo_follows_edits(self):
        e = Entry('article', 'k', [Field('doi', '10.1/a'), Field('title', 'T'), Field('author', 'A, B')])
        self.assertEqual(new.identity(e)['doi'], '10.1/a')
        e['doi'] = '10.1/b'
        e['title'] = 'Other'
        self.assertEqual(new.identity(e), ref.identity(e))

    def test_distinct_union(self):
        a, b = new.Distinct([[{'doi': '1'}, {'doi': '2'}]]), new.Distinct()
        union = new.distinct_union(a, b)
        self.assertIs(new.distinct_union(a, b), union)
        b.pairs.append([{'doi': '3'}, {'doi': '4'}])
        union2 = new.distinct_union(a, b)
        self.assertIsNot(union2, union)
        self.assertEqual(len(union2.pairs), 2)
        self.assertEqual(len(new.distinct_union(a, None).pairs), 1)


if __name__ == '__main__':
    unittest.main()
