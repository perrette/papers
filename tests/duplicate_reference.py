"""REFERENCE COPY, not used by papers: papers.duplicate as it was before its
speed-ups (memoized identity, index positions, shared Distinct union), for
the equivalence test of tests/test_duplicate_equivalence.py.

Whether two entries are the same paper.

`same_paper(a, b, distinct)` is the only duplicate rule of papers: `add`
(including `add DIR`), `check --duplicates` and `list --duplicates` use it,
and so will `pull` and `push`. It compares, in this order:

1. the DOI (case-insensitive, without doi.org/ or doi: prefix);
2. the arXiv identifier (`eprint` with `archivePrefix = arXiv` or no
   archivePrefix, and the arXiv DOIs 10.48550/arXiv.<id>), without version;
3. the ISBN, for two @book entries only (a chapter carries the ISBN of its
   book, and each edition has its own);
4. otherwise the family names of the authors and the title, normalized
   (case, braces, accents, whitespace), both non-empty on both sides.

The first identifier that both entries have decides: equal values make the
same paper, different values two papers. Title guard: equal identifiers with
different entry types AND different titles (normalized; e.g. a chapter
exported with the DOI of its book, a dataset "Data for: X" deposited under
the DOI of article "X") give "ask" instead of "same".

Pairs that the user answered "not the same paper" for are kept in
`.papers/distinct.json` of the library (see `Distinct`), and same_paper
returns "different" for them.
"""
import json
import os
import re

from unidecode import unidecode

from papers import logger
from papers.entries import get_entry_val
from papers.identifiers import normalize_doi, normalize_isbn, entry_arxiv
from papers.latexenc import latex_to_unicode


SAME = 'same'
DIFFERENT = 'different'
ASK = 'ask'

# minimum author+title score of `list --duplicates --fuzzy`
FUZZY_RATIO = 80

# minimum title score for a search result to be taken for the entry
# (`check --fetch-all`)
TITLE_MATCH_RATIO = 90


class Verdict:
    """result of same_paper: `kind` is SAME, DIFFERENT or ASK, `reason`
    says why (e.g. "same DOI 10.1000/xyz")"""

    def __init__(self, kind, reason=''):
        self.kind = kind
        self.reason = reason

    def __eq__(self, other):
        if isinstance(other, str):
            return self.kind == other
        return isinstance(other, Verdict) and (self.kind, self.reason) == (other.kind, other.reason)

    def __repr__(self):
        return f'Verdict({self.kind!r}, {self.reason!r})'


# NORMALIZATION
# =============

def normalize_text(s):
    """lower case, LaTeX and accents to ASCII, no braces, single spaces"""
    if not s:
        return ''
    s = latex_to_unicode(s)
    s = unidecode(s)
    s = s.replace('{', '').replace('}', '')
    return ' '.join(s.lower().split())


def split_names(field):
    "the names of an author (or editor) field"
    return [n.strip() for n in re.split(r'\s+and\s+', field or '') if n.strip()]


def parse_name(name):
    """(family, given) of one name: 'Smith, John', 'John Smith', or
    '{van der Berg}, Jane'. Given names may be empty."""
    name = name.strip()
    if ',' in name:
        family, given = name.split(',', 1)
        return family.strip(), given.strip()
    # last word, keeping a braced group together
    m = re.match(r'^(.*?)\s*(\{[^{}]*\}|\S+)$', name)
    if not m:
        return name, ''
    return m.group(2), m.group(1).strip()


def family_name_ids(field):
    "normalized family names of an author field"
    return [normalize_text(parse_name(n)[0]) for n in split_names(field)]


def author_id(e):
    return ' '.join(family_name_ids(get_entry_val(e, 'author', '')))


def title_id(e):
    return normalize_text(get_entry_val(e, 'title', ''))


def authortitle_id(e):
    "normalized 'authors|title', or '' when the authors or the title are missing"
    author, title = author_id(e), title_id(e)
    if not author or not title:
        return ''
    return author + '|' + title


def entry_type(e):
    return get_entry_val(e, 'ENTRYTYPE', '').lower()


# IDENTITY
# ========

def doi_id(e):
    return normalize_doi(get_entry_val(e, 'doi', '')) or ''


def isbn_ids(e):
    "the normalized ISBNs of a @book entry (none for other types)"
    if entry_type(e) != 'book':
        return frozenset()
    values = re.split(r'[,;]', get_entry_val(e, 'isbn', ''))
    return frozenset(i for i in (normalize_isbn(v) for v in values if v.strip()) if i)


def identity(e):
    """the identifiers of an entry: dict with the keys doi, arxiv, isbn
    (comma-separated, books only) and authortitle (or title, without
    authors), those it has"""
    ident = {}
    if doi_id(e):
        ident['doi'] = doi_id(e)
    if entry_arxiv(e):
        ident['arxiv'] = entry_arxiv(e)
    if isbn_ids(e):
        ident['isbn'] = ','.join(sorted(isbn_ids(e)))
    if authortitle_id(e):
        ident['authortitle'] = authortitle_id(e)
    elif title_id(e):
        # no authors: the title tells apart entries that share an identifier
        ident['title'] = title_id(e)
    return ident


def titles_differ(a, b):
    "both titles known, and different after normalization"
    ta, tb = title_id(a), title_id(b)
    return bool(ta and tb and ta != tb)


def search_result_mismatch(e, found, ratio=TITLE_MATCH_RATIO):
    """why a bibliographic search result `found` is not the paper of entry
    `e`, or '' when it is: the normalized titles must be equal or score at
    least `ratio` (rapidfuzz ratio, 0-100), and the authors must have a
    family name in common"""
    from rapidfuzz.fuzz import ratio as fuzz_ratio
    ta, tb = title_id(e), title_id(found)
    if not ta or not tb:
        return 'no title'
    if ta != tb:
        score = fuzz_ratio(ta, tb)
        if score < ratio:
            return f'different title ({score:.0f}% similar)'
    common = set(family_name_ids(get_entry_val(e, 'author', ''))) & set(family_name_ids(get_entry_val(found, 'author', '')))
    if not common - {''}:
        return 'no author in common'
    return ''


def _guard(a, b, reason):
    "the title guard on equal identifiers"
    if entry_type(a) != entry_type(b) and titles_differ(a, b):
        return Verdict(ASK, f'{reason}, but the entry types ({entry_type(a)}, {entry_type(b)}) '
                            'and the titles differ')
    return Verdict(SAME, reason)


def same_paper(a, b, distinct=None):
    """Verdict(SAME, DIFFERENT or ASK, reason) for two entries (see the module
    documentation). `distinct` is a Distinct, or None."""
    if distinct is not None and distinct.contains(a, b):
        return Verdict(DIFFERENT, 'marked as not the same paper (.papers/distinct.json)')

    doi_a, doi_b = doi_id(a), doi_id(b)
    if doi_a and doi_b:
        if doi_a != doi_b:
            return Verdict(DIFFERENT, 'different DOIs')
        return _guard(a, b, f'same DOI {doi_a}')

    arxiv_a, arxiv_b = entry_arxiv(a), entry_arxiv(b)
    if arxiv_a and arxiv_b:
        if arxiv_a != arxiv_b:
            return Verdict(DIFFERENT, 'different arXiv ids')
        return _guard(a, b, f'same arXiv id {arxiv_a}')

    isbn_a, isbn_b = isbn_ids(a), isbn_ids(b)
    if isbn_a and isbn_b:
        common = isbn_a & isbn_b
        if not common:
            return Verdict(DIFFERENT, 'different ISBNs')
        return Verdict(SAME, f'same ISBN {min(common)}')

    at_a, at_b = authortitle_id(a), authortitle_id(b)
    if at_a and at_b and at_a == at_b:
        return Verdict(SAME, 'same title and authors')
    return Verdict(DIFFERENT, 'no common identifier')


# NOT THE SAME PAPER
# ==================

DISTINCT_FILE = os.path.join('.papers', 'distinct.json')


def _side_matches(recorded, ident):
    """a recorded identity matches the identity of an entry when they have
    the same DOI, arXiv id and ISBN (or both none of them), and the same
    authors and title (or title) when both have them"""
    if not recorded:
        return False
    for k in ('doi', 'arxiv', 'isbn'):
        if recorded.get(k) != ident.get(k):
            return False
    for k in ('authortitle', 'title'):
        if k in recorded and k in ident and recorded[k] != ident[k]:
            return False
    return True


class Distinct:
    """Pairs of entries that are not the same paper, recorded by identity
    (see `identity`), not by key, so that the file means the same in every
    library. Stored in .papers/distinct.json next to the bibtex:

        {"distinct": [[{"doi": "10.1000/a", "authortitle": "..."}, {...}], ...]}
    """

    def __init__(self, pairs=None, path=None):
        self.pairs = list(pairs or [])
        self.path = path
        self.changed = False

    @classmethod
    def for_bibtex(cls, bibtex):
        "the pairs recorded for the library of this bibtex file"
        path = os.path.join(os.path.dirname(os.path.abspath(bibtex)), DISTINCT_FILE)
        return cls.load(path)

    @classmethod
    def load(cls, path):
        pairs = []
        if os.path.exists(path):
            try:
                with open(path) as f:
                    pairs = [p for p in json.load(f).get('distinct', [])
                             if isinstance(p, list) and len(p) == 2]
            except (ValueError, OSError, AttributeError) as error:
                logger.warning(f'{path}: could not be read ({error}); ignored')
        return cls(pairs, path)

    def contains(self, a, b):
        ia, ib = identity(a), identity(b)
        for x, y in self.pairs:
            if (_side_matches(x, ia) and _side_matches(y, ib)) or (_side_matches(y, ia) and _side_matches(x, ib)):
                return True
        return False

    def add(self, a, b):
        "record that entries a and b are not the same paper"
        ia, ib = identity(a), identity(b)
        if not ia or not ib or self.contains(a, b):
            return
        self.pairs.append([ia, ib])
        self.changed = True

    def update(self, other):
        "union with the pairs of another Distinct (e.g. of a pool, on pull or push)"
        for pair in other.pairs:
            if pair not in self.pairs and [pair[1], pair[0]] not in self.pairs:
                self.pairs.append(pair)
                self.changed = True

    def save(self, path=None):
        path = path or self.path
        if not self.changed or path is None:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump({'distinct': self.pairs}, f, indent=1, sort_keys=True)
            f.write('\n')
        self.changed = False


# CANDIDATES AND GROUPS
# =====================

def _index_keys(e):
    ident = identity(e)
    keys = [(k, v) for k, v in ident.items() if k != 'isbn']
    keys += [('isbn', i) for i in isbn_ids(e)]
    return keys


class IdentityIndex:
    """entries by identifier, so that a duplicate search only compares an
    entry with the entries that share one of its identifiers"""

    def __init__(self, entries=()):
        self._index = {}
        for e in entries:
            self.add(e)

    def add(self, e):
        for k in _index_keys(e):
            matches = self._index.setdefault(k, [])
            if not any(x is e for x in matches):
                matches.append(e)

    def remove(self, e):
        for k in _index_keys(e):
            matches = self._index.get(k, [])
            matches[:] = [x for x in matches if x is not e]

    def candidates(self, e):
        out = []
        for k in _index_keys(e):
            for x in self._index.get(k, []):
                if x is not e and not any(x is y for y in out):
                    out.append(x)
        return out


def find_duplicates(entry, entries, distinct=None, index=None):
    """[(other, verdict)] for the entries that are the same paper as `entry`
    (SAME first, then ASK), in the order of `entries`"""
    if index is None:
        index = IdentityIndex(entries)
    candidates = index.candidates(entry)
    order = {id(e): i for i, e in enumerate(entries)}
    found = []
    for other in candidates:
        if id(other) not in order:
            continue
        verdict = same_paper(other, entry, distinct)
        if verdict.kind != DIFFERENT:
            found.append((other, verdict))
    found.sort(key=lambda ov: (ov[1].kind != SAME, order[id(ov[0])]))
    return found


class Group:
    """entries of the library that are the same paper. entries[0] is the
    entry with most fields (the proposed target of a merge). `kind` is SAME,
    or ASK when the title guard fires for a pair of the group."""

    def __init__(self, entries, kind, reason):
        self.entries = entries
        self.kind = kind
        self.reason = reason


def _nfields(e):
    return len(list(e.items()))


def duplicate_groups(entries, distinct=None):
    """the groups of 2 or more entries that are the same paper.

    Entries linked by SAME or ASK verdicts are grouped, and a group never
    holds two entries that are different papers: when a copy without DOI
    matches two entries with different DOIs by authors and title, it goes
    with the first of them (most fields first), and the other is left out."""
    entries = list(entries)
    index = IdentityIndex(entries)
    position = {id(e): i for i, e in enumerate(entries)}
    parent = list(range(len(entries)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, e in enumerate(entries):
        for other in index.candidates(e):
            j = position[id(other)]
            if j > i and same_paper(e, other, distinct).kind != DIFFERENT:
                parent[find(j)] = find(i)

    components = {}
    for i in range(len(entries)):
        components.setdefault(find(i), []).append(entries[i])

    groups = []
    for root in sorted(components):
        component = sorted(components[root], key=lambda e: -_nfields(e))
        parts = []
        for e in component:
            for part in parts:
                verdicts = [same_paper(x, e, distinct) for x in part]
                if all(v.kind != DIFFERENT for v in verdicts):
                    part.append(e)
                    break
            else:
                parts.append([e])
        for part in parts:
            if len(part) < 2:
                continue
            kind, reason = SAME, ''
            for i, a in enumerate(part):
                for b in part[i+1:]:
                    v = same_paper(a, b, distinct)
                    if v.kind == ASK and kind == SAME:
                        kind, reason = ASK, v.reason
                    elif not reason:
                        reason = v.reason
            groups.append(Group(part, kind, reason))
    return groups


def fuzzy_pairs(entries, ratio=FUZZY_RATIO):
    """pairs of entries whose authors and titles score at least `ratio`
    (rapidfuzz token_set_ratio, 0-100). For listing only: papers never
    merges on this."""
    from rapidfuzz.fuzz import token_set_ratio
    ids = [(e, author_id(e) + ' ' + title_id(e)) for e in entries]
    ids = [(e, s) for e, s in ids if s.strip()]
    pairs = []
    for i, (a, sa) in enumerate(ids):
        for b, sb in ids[i+1:]:
            if token_set_ratio(sa, sb, score_cutoff=ratio):
                pairs.append((a, b))
    return pairs
