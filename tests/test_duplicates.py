"""Duplicate detection (same_paper, distinct.json), merge, the dialogue, and
the --on-duplicate option of add and check (see design/duplicates.md)"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from papers.bib import Biblio
from papers.cli.common import edit_entries
from papers.duplicate import (
    same_paper, SAME, DIFFERENT, ASK, Distinct, duplicate_groups, fuzzy_pairs,
)
from papers.entries import entry_from_dict, parse_string
from papers.merge import (
    Merge, Dialogue, DuplicateError, names_compatible, CONFLICT, ADDED, SAME as UNCHANGED,
)
from tests.common import paperscmd


def entry(key='key', type='article', **fields):
    return entry_from_dict(dict(fields, ID=key, ENTRYTYPE=type))


def kind(a, b, distinct=None):
    return same_paper(a, b, distinct).kind


SMITH = dict(author='Smith, John and Doe, Jane', title='Climate sensitivity revisited', year='2020')


# IDENTITY
# ========

class TestIdentifiers(unittest.TestCase):

    def test_doi_case_and_prefix(self):
        a = entry('a', doi='10.1000/ABC123', title='One')
        b = entry('b', doi='https://doi.org/10.1000/abc123', title='Other title')
        self.assertEqual(kind(a, b), SAME)
        self.assertIn('same DOI 10.1000/abc123', same_paper(a, b).reason)

    def test_different_dois_are_different_papers(self):
        # same authors and title: the 2019 preprint and the 2020 article
        a = entry('a', doi='10.1000/abc123', **SMITH)
        b = entry('b', type='misc', doi='10.5194/egusphere-2019-1', **SMITH)
        self.assertEqual(kind(a, b), DIFFERENT)

    def test_arxiv_eprint(self):
        a = entry('a', eprint='2101.01234v2', archivePrefix='arXiv', title='One')
        b = entry('b', eprint='arXiv:2101.01234', title='Two')  # no archivePrefix
        self.assertEqual(kind(a, b), SAME)

    def test_arxiv_doi_and_eprint(self):
        a = entry('a', doi='10.48550/arXiv.2101.01234', title='One')
        b = entry('b', eprint='2101.01234', title='Two')
        self.assertEqual(kind(a, b), SAME)

    def test_other_archive_is_not_arxiv(self):
        a = entry('a', eprint='2101.01234', archivePrefix='HAL', title='One', author='A, B')
        b = entry('b', eprint='2101.01234', title='Two', author='C, D')
        self.assertEqual(kind(a, b), DIFFERENT)

    def test_different_arxiv_ids(self):
        a = entry('a', eprint='2101.01234', **SMITH)
        b = entry('b', eprint='2101.09999', **SMITH)
        self.assertEqual(kind(a, b), DIFFERENT)

    def test_isbn_books(self):
        a = entry('a', type='book', isbn='0-306-40615-2', title='A book')
        b = entry('b', type='book', isbn='978-0-306-40615-7', title='The book')
        self.assertEqual(kind(a, b), SAME)

    def test_isbn_different_books(self):
        a = entry('a', type='book', isbn='0-306-40615-2', **SMITH)
        b = entry('b', type='book', isbn='978-3-16-148410-0', **SMITH)  # another edition
        self.assertEqual(kind(a, b), DIFFERENT)

    def test_isbn_ignored_for_chapters(self):
        # a chapter carries the ISBN of its book
        book = entry('a', type='book', isbn='0-306-40615-2', author='Ed, A', title='Handbook')
        chapter = entry('b', type='incollection', isbn='0-306-40615-2', author='Smith, J', title='Chapter')
        self.assertEqual(kind(book, chapter), DIFFERENT)

    def test_author_title(self):
        a = entry('a', author='Smith, John and Doe, Jane', title='Climate {Sensitivity}  revisited')
        b = entry('b', author='J. Smith and J. Doe', title='climate sensitivity revisited')
        self.assertEqual(kind(a, b), SAME)
        self.assertEqual(same_paper(a, b).reason, 'same title and authors')

    def test_author_title_accents(self):
        a = entry('a', author='M{\\"u}ller, H.', title='Über alles')
        b = entry('b', author='Müller, Hans', title='{\\"U}ber alles')
        self.assertEqual(kind(a, b), SAME)

    def test_title_without_authors_is_not_enough(self):
        a = entry('a', title='Editorial')
        b = entry('b', title='Editorial')
        self.assertEqual(kind(a, b), DIFFERENT)

    def test_one_doi_only_falls_back_to_author_title(self):
        a = entry('a', doi='10.1000/abc123', **SMITH)
        b = entry('b', **SMITH)
        self.assertEqual(kind(a, b), SAME)

    def test_order_doi_before_arxiv(self):
        a = entry('a', doi='10.1000/a', eprint='2101.01234', **SMITH)
        b = entry('b', doi='10.1000/b', eprint='2101.01234', **SMITH)
        self.assertEqual(kind(a, b), DIFFERENT)

    def test_order_arxiv_before_author_title(self):
        a = entry('a', doi='10.1000/a', eprint='2101.01234', title='One', author='A, B')
        b = entry('b', eprint='2101.01234', title='Two', author='C, D')
        self.assertEqual(kind(a, b), SAME)  # b has no DOI: the arXiv id decides

    def test_order_isbn_before_author_title(self):
        a = entry('a', type='book', isbn='0-306-40615-2', **SMITH)
        b = entry('b', type='book', isbn='978-3-16-148410-0', **SMITH)
        self.assertEqual(kind(a, b), DIFFERENT)


class TestTitleGuard(unittest.TestCase):

    def test_types_and_titles_differ(self):
        # a chapter exported with the DOI of its book
        book = entry('a', type='book', doi='10.1000/book', title='Handbook of climate')
        chapter = entry('b', type='incollection', doi='10.1000/book', title='Sea level rise')
        v = same_paper(book, chapter)
        self.assertEqual(v.kind, ASK)
        self.assertIn('entry types', v.reason)

    def test_same_type_always_same(self):
        a = entry('a', doi='10.1000/x', title='Handbook of climate')
        b = entry('b', doi='10.1000/x', title='Sea level rise')
        self.assertEqual(kind(a, b), SAME)

    def test_titles_equal_after_normalization(self):
        a = entry('a', doi='10.1000/x', title='Climate sensitivity revisited')
        b = entry('b', type='misc', doi='10.1000/x', title='{Climate} Sensitivity  Revisited')
        self.assertEqual(kind(a, b), SAME)

    def test_dataset_of_article(self):
        # a near-identical title is not enough when the types differ
        a = entry('a', doi='10.1000/x', title='Climate sensitivity revisited')
        b = entry('b', type='misc', doi='10.1000/x', title='Data for: Climate sensitivity revisited')
        self.assertEqual(kind(a, b), ASK)

    def test_arxiv_guard(self):
        a = entry('a', eprint='2101.01234', title='Climate sensitivity revisited')
        b = entry('b', type='misc', eprint='2101.01234', title='Data and code')
        self.assertEqual(kind(a, b), ASK)


class TestDistinct(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bibtex = os.path.join(self.tmp.name, 'papers.bib')

    def tearDown(self):
        self.tmp.cleanup()

    def test_recorded_and_honoured(self):
        a = entry('a', **SMITH)
        b = entry('b', **SMITH)
        d = Distinct.for_bibtex(self.bibtex)
        self.assertEqual(kind(a, b, d), SAME)
        d.add(a, b)
        d.save()
        path = os.path.join(self.tmp.name, '.papers', 'distinct.json')
        self.assertEqual(json.load(open(path))['distinct'],
                         [[{'authortitle': 'smith doe|climate sensitivity revisited'}] * 2])
        d2 = Distinct.for_bibtex(self.bibtex)
        self.assertEqual(kind(a, b, d2), DIFFERENT)
        self.assertEqual(kind(b, a, d2), DIFFERENT)

    def test_identities_not_keys(self):
        d = Distinct()
        d.add(entry('a', **SMITH), entry('b', **SMITH))
        # other keys, same identities
        self.assertEqual(kind(entry('x', **SMITH), entry('y', **SMITH), d), DIFFERENT)

    def test_title_guard_pair(self):
        book = entry('a', type='book', doi='10.1000/book', title='Handbook of climate')
        chapter = entry('b', type='incollection', doi='10.1000/book', title='Sea level rise')
        d = Distinct()
        d.add(book, chapter)
        self.assertEqual(kind(book, chapter, d), DIFFERENT)
        # another chapter of the same book is still asked about
        other = entry('c', type='incollection', doi='10.1000/book', title='Ocean tides')
        self.assertEqual(kind(book, other, d), ASK)

    def test_does_not_leak_to_other_entries(self):
        with_doi = entry('a', doi='10.1000/abc123', **SMITH)
        without = entry('b', **SMITH)
        preprint = entry('c', doi='10.5194/egusphere-2019-1', **SMITH)
        d = Distinct()
        d.add(with_doi, without)
        self.assertEqual(kind(with_doi, without, d), DIFFERENT)
        self.assertEqual(kind(without, preprint, d), SAME)

    def test_update(self):
        d1, d2 = Distinct(), Distinct()
        d2.add(entry('a', doi='10.1/a'), entry('b', doi='10.1/b'))
        d1.update(d2)
        d1.update(d2)
        self.assertEqual(len(d1.pairs), 1)


class TestGroups(unittest.TestCase):

    def test_copy_without_doi_goes_with_one_entry(self):
        article = entry('article', doi='10.1000/abc123', journal='Nature', **SMITH)
        copy = entry('copy', **SMITH)
        preprint = entry('preprint', type='misc', doi='10.5194/egusphere-2019-1', **SMITH)
        groups = duplicate_groups([copy, preprint, article])
        self.assertEqual(len(groups), 1)
        self.assertEqual([e.key for e in groups[0].entries], ['article', 'copy'])  # most fields first

    def test_ask_group(self):
        book = entry('a', type='book', doi='10.1000/book', title='Handbook of climate')
        chapter = entry('b', type='incollection', doi='10.1000/book', title='Sea level rise')
        groups = duplicate_groups([book, chapter])
        self.assertEqual(groups[0].kind, ASK)

    def test_fuzzy_pairs(self):
        a = entry('a', author='Smith, J.', title='Climate sensitivity revisited')
        b = entry('b', author='Smith, J.', title='Climate sensitivity revisited again')
        c = entry('c', author='Brown, B.', title='Ocean tides')
        self.assertEqual([(x.key, y.key) for x, y in fuzzy_pairs([a, b, c])], [('a', 'b')])


# MERGE
# =====

class TestNames(unittest.TestCase):

    def test_initials(self):
        self.assertTrue(names_compatible('Smith, John and Doe, Jane', 'Smith, J. and Doe, J.'))
        self.assertTrue(names_compatible('Smith, John D.', 'J. Smith'))
        self.assertTrue(names_compatible('Perrette, M.', 'M. Perrette'))

    def test_different_first_names(self):
        self.assertFalse(names_compatible('Smith, John', 'Smith, Jane'))
        self.assertFalse(names_compatible('Smith, J.', 'Jones, J.'))
        self.assertFalse(names_compatible('Smith, J.', 'Smith, J. and Doe, J.'))

    def test_fuller_form_kept_from_either_side(self):
        full, short = 'Smith, John and Doe, Jane', 'Smith, J. and Doe, J.'
        m = Merge([entry('a', author=short, title='T'), entry('b', author=full, title='T')])
        self.assertEqual(m.conflicts, [])
        self.assertEqual(m.result()['author'], full)
        m = Merge([entry('a', author=full, title='T'), entry('b', author=short, title='T')])
        self.assertEqual(m.result()['author'], full)

    def test_different_names_conflict(self):
        m = Merge([entry('a', author='Smith, John'), entry('b', author='Smith, Jane')])
        self.assertEqual([f.name for f in m.conflicts], ['author'])


class TestMerge(unittest.TestCase):

    def test_model(self):
        lib = entry('smith2020climate', doi='10.1000/abc123', journal='Nature', keywords='climate, mine',
                    file=':/tmp/files/smith.pdf:pdf', **SMITH)
        new = entry('Smith_2020', doi='10.1000/ABC123', journal='Nature Climate Change', volume='10',
                    file=':/tmp/other/smith-preprint.pdf:pdf',
                    author='Smith, J. and Doe, J.', title='Climate Sensitivity Revisited', year='2020')
        m = Merge([lib, new])
        status = {f.name: f.status for f in m.fields}
        self.assertEqual(status['journal'], CONFLICT)
        self.assertEqual(status['volume'], ADDED)
        for name in ('doi', 'title', 'author', 'year', 'keywords'):
            self.assertEqual(status[name], UNCHANGED, name)
        self.assertFalse(m.is_exact())
        r = m.result()
        self.assertEqual(r.key, 'smith2020climate')
        self.assertEqual(r['doi'], '10.1000/abc123')            # target's spelling
        self.assertEqual(r['title'], 'Climate sensitivity revisited')
        self.assertEqual(r['journal'], 'Nature')
        self.assertEqual(r['volume'], '10')
        self.assertEqual(r['file'], ':/tmp/files/smith.pdf:pdf;:/tmp/other/smith-preprint.pdf:pdf')
        m.choose_all(1)
        self.assertEqual(m.result()['journal'], 'Nature Climate Change')
        self.assertEqual(m.result().key, 'smith2020climate')

    def test_files_by_real_path(self):
        with tempfile.TemporaryDirectory() as d:
            pdf = os.path.join(d, 'a.pdf')
            Path(pdf).write_text('x')
            os.symlink(pdf, os.path.join(d, 'link.pdf'))
            m = Merge([entry('a', file=f':{pdf}:pdf'), entry('b', file=f':{d}/./link.pdf:pdf')])
            self.assertEqual(m.files, [pdf])
            self.assertEqual(m.new_files, [])
            self.assertTrue(m.is_exact())

    def test_keys_to_ids(self):
        a = entry('a', ids='old, b', title='T')
        b = entry('b', title='T')
        c = entry('c', ids='a, old2', title='T')
        m = Merge([a, b, c], keys_to_ids=True)
        self.assertEqual(m.result()['ids'], 'old, b, old2, c')

    def test_no_ids_in_add(self):
        m = Merge([entry('a', title='T'), entry('b', title='T')])
        self.assertNotIn('ids', m.result())

    def test_with_target(self):
        m = Merge([entry('a', journal='J1'), entry('b', journal='J2')], keys_to_ids=True).with_target(1)
        self.assertEqual(m.result().key, 'b')
        self.assertEqual(m.result()['journal'], 'J2')
        self.assertEqual(m.result()['ids'], 'a')


class TestDialogue(unittest.TestCase):

    def merge(self):
        lib = entry('smith2020climate', doi='10.1000/abc123', journal='Nature', **SMITH)
        new = entry('Smith_2020', doi='10.1000/abc123', journal='Nature Climate Change', volume='10', **SMITH)
        return Merge([lib, new])

    def test_screen(self):
        text = Dialogue(self.merge(), 'add', 'same DOI 10.1000/abc123').screen()
        self.assertIn('Already in library: smith2020climate (same DOI 10.1000/abc123)', text)
        self.assertIn('!  journal = {Nature}', text)
        self.assertIn('!            2: {Nature Climate Change}', text)
        self.assertIn('+  volume  = {10}', text)
        self.assertIn('   title   = {Climate sensitivity revisited}', text)
        self.assertIn('1 conflict. The key smith2020climate is kept', text)
        self.assertIn('n not the same paper (add Smith_2020 separately)', text)
        self.assertNotIn('t N', text)

    def test_check_screen(self):
        text = Dialogue(Merge(self.merge().entries, keys_to_ids=True), 'check').screen()
        self.assertIn('2: Smith_2020 (kept in ids)', text)
        self.assertIn('t N make entry N the target', text)
        self.assertIn('Entry 2 is removed after the merge', text)

    def test_parse(self):
        d = Dialogue(self.merge(), 'add')
        self.assertEqual(d.parse('2').kind, 'take')
        self.assertEqual(d.parse('2').index, 1)
        self.assertEqual(d.parse('3').kind, 'invalid')
        self.assertEqual(d.parse('t 2').kind, 'invalid')  # check only
        for answer, k in [('f', 'fields'), ('e', 'edit'), ('n', 'distinct'), ('s', 'skip'),
                          ('q', 'quit'), ('?', 'help'), ('u', 'invalid')]:
            self.assertEqual(d.parse(answer).kind, k, answer)
        d = Dialogue(Merge(self.merge().entries, keys_to_ids=True), 'check')
        self.assertEqual(d.parse('t 2').kind, 'target')
        self.assertEqual(d.parse('t2').index, 1)

    def test_edit_text(self):
        m = self.merge()
        text = m.edit_text()
        self.assertIn('% journal = {Nature Climate Change}   (2)', text)
        e = m.parse_edit(text.replace('journal = {Nature}', 'journal = {Science}').replace('smith2020climate', 'otherkey'))
        self.assertEqual(e.key, 'smith2020climate')
        self.assertEqual(e['journal'], 'Science')
        self.assertIsNone(m.parse_edit('@article{a,\n title = {x}\n}\n@article{b,\n title = {y}\n}'))
        self.assertIsNone(m.parse_edit('- journal = {x}'))


# ADD
# ===

LIB = """@article{smith2020climate,
 author = {Smith, John and Doe, Jane},
 doi = {10.1000/abc123},
 file = {:files/smith.pdf:pdf},
 journal = {Nature},
 keywords = {climate, mine},
 title = {Climate sensitivity revisited},
 year = {2020}
}
"""

NEW = """@article{Smith_2020,
 author = {Smith, J. and Doe, J.},
 doi = {10.1000/ABC123},
 file = {:other/smith-preprint.pdf:pdf},
 journal = {Nature Climate Change},
 title = {Climate Sensitivity Revisited},
 volume = {10},
 year = {2020}
}
"""

EXACT = """@article{otherkey,
 author = {Smith, J. and Doe, J.},
 doi = {10.1000/abc123},
 file = {:other/smith-preprint.pdf:pdf},
 title = {Climate sensitivity revisited}
}
"""


class LibraryTest(unittest.TestCase):

    lib = LIB

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.realpath(self.tmp.name)
        self.bibtex = self.path('papers.bib')
        Path(self.bibtex).write_text(self.lib)

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, *p):
        return os.path.join(self.dir, *p)

    def write(self, name, content):
        Path(self.path(name)).write_text(content)
        return self.path(name)

    def papers(self, cmd, answers=None, editor=None):
        "run papers in the library directory; the text it printed"
        out = io.StringIO()
        env = {'EDITOR': editor} if editor else {}
        with patch('builtins.input', side_effect=list(answers or [])), patch.dict(os.environ, env), \
                redirect_stdout(out):
            paperscmd(f'{cmd} --bibtex {self.bibtex} --no-git', cwd=self.dir)
        return out.getvalue()

    def entries(self):
        return {e.key: e for e in Biblio.load(self.bibtex, '').entries}

    def entry(self, key):
        return self.entries()[key]

    def distinct(self):
        path = self.path('.papers', 'distinct.json')
        return json.load(open(path))['distinct'] if os.path.exists(path) else []


class TestAddOnDuplicate(LibraryTest):

    def setUp(self):
        super().setUp()
        self.new = self.write('new.bib', NEW)

    def test_default_without_terminal_is_error(self):
        with self.assertRaises(DuplicateError) as cm:
            self.papers(f'add {self.new}')
        self.assertIn('--on-duplicate', str(cm.exception))
        self.assertIn('already in library as smith2020climate', str(cm.exception))
        self.assertEqual(Path(self.bibtex).read_text(), LIB)

    def test_error_exit_status(self):
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).parent.parent))
        res = subprocess.run([sys.executable, '-m', 'papers', 'add', 'new.bib', '--bibtex', 'papers.bib', '--no-git'],
                             cwd=self.dir, stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env)
        self.assertEqual(res.returncode, 1)
        self.assertIn('Pass --on-duplicate with one of: ask, keep, update, skip', res.stderr)
        self.assertNotIn('Traceback', res.stderr)

    def test_keep(self):
        self.papers(f'add {self.new} --on-duplicate keep')
        e = self.entry('smith2020climate')
        self.assertEqual(len(self.entries()), 1)
        self.assertEqual(e['journal'], 'Nature')
        self.assertEqual(e['volume'], '10')
        self.assertEqual(e['author'], 'Smith, John and Doe, Jane')
        self.assertEqual(e['title'], 'Climate sensitivity revisited')
        self.assertEqual(e['file'], ':files/smith.pdf:pdf;:other/smith-preprint.pdf:pdf')
        self.assertNotIn('ids', e)

    def test_update(self):
        self.papers(f'add {self.new} --on-duplicate update')
        e = self.entry('smith2020climate')  # the library key
        self.assertEqual(len(self.entries()), 1)
        self.assertEqual(e['journal'], 'Nature Climate Change')
        self.assertEqual(e['keywords'], 'climate, mine')  # fields only in the library stay
        self.assertEqual(e['author'], 'Smith, John and Doe, Jane')  # fuller form

    def test_update_key_does_not_change_the_library_key(self):
        self.papers(f'add {self.new} --on-duplicate update -u')
        self.assertEqual(list(self.entries()), ['smith2020climate'])

    def test_update_key_new_entries_only(self):
        other = self.write('other.bib', '@article{X,\n author = {Brown, Bob},\n title = {Ocean tides},\n year = {2001}\n}\n')
        self.papers(f'add {other} {self.new} --on-duplicate keep -u')
        self.assertEqual(sorted(self.entries()), ['brown2001', 'smith2020climate'])

    def test_skip(self):
        out = self.papers(f'add {self.new} --on-duplicate skip')
        self.assertEqual(Path(self.bibtex).read_text(), LIB)
        self.assertIn('skipped: Smith_2020 (already in library: smith2020climate)', out)

    def test_exact_duplicate_never_asks(self):
        exact = self.write('exact.bib', EXACT)
        out = self.papers(f'add {exact}')  # no terminal: would be an error if it asked
        self.assertIn('already in library: smith2020climate (+1 file)', out)
        e = self.entry('smith2020climate')
        self.assertEqual(e['file'], ':files/smith.pdf:pdf;:other/smith-preprint.pdf:pdf')
        self.assertEqual(len(self.entries()), 1)

    def test_no_check_duplicate(self):
        self.papers(f'add {self.new} --no-check-duplicate')
        self.assertEqual(sorted(self.entries()), ['Smith_2020', 'smith2020climate'])

    def test_add_dir(self):
        os.makedirs(self.path('dir'))
        Path(self.path('dir', 'new.bib')).write_text(NEW)
        self.papers(f'add {self.path("dir")} --recursive --on-duplicate keep')
        self.assertEqual(list(self.entries()), ['smith2020climate'])
        self.assertEqual(self.entry('smith2020climate')['volume'], '10')

    def test_add_dir_error(self):
        os.makedirs(self.path('dir'))
        Path(self.path('dir', 'new.bib')).write_text(NEW)
        with self.assertRaises(DuplicateError):
            self.papers(f'add {self.path("dir")} --recursive')
        self.assertEqual(Path(self.bibtex).read_text(), LIB)


class TestAddDialogue(LibraryTest):

    def setUp(self):
        super().setUp()
        self.new = self.write('new.bib', NEW)

    def add(self, *answers, editor=None):
        return self.papers(f'add {self.new} --on-duplicate ask', answers=answers, editor=editor)

    def test_1(self):
        out = self.add('1')
        self.assertIn('!  journal  = {Nature}', out)
        e = self.entry('smith2020climate')
        self.assertEqual((e['journal'], e['volume']), ('Nature', '10'))

    def test_2(self):
        self.add('2')
        self.assertEqual(list(self.entries()), ['smith2020climate'])
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature Climate Change')

    def test_f(self):
        out = self.add('f', '3', '2')  # 3 is invalid
        self.assertIn('  1  Nature                 library', out)
        self.assertIn('  2  Nature Climate Change  new', out)
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature Climate Change')

    def test_e(self):
        editor = "sed -i -e 's/journal = {Nature}/journal = {Science}/'"
        self.add('e', editor=editor)
        e = self.entry('smith2020climate')
        self.assertEqual((e['journal'], e['volume']), ('Science', '10'))
        self.assertEqual(len(self.entries()), 1)

    def test_failed_edit_goes_back_to_the_menu(self):
        # an editor that fails, then one that leaves text that is not one entry:
        # never insert both entries
        self.add('e', 's', editor='false')
        self.assertEqual(Path(self.bibtex).read_text(), LIB)
        self.add('e', 's', editor="sh -c 'echo \"- journal = {x}\" > \"$0\"'")
        self.assertEqual(Path(self.bibtex).read_text(), LIB)

    def test_n(self):
        self.add('n')
        self.assertEqual(sorted(self.entries()), ['Smith_2020', 'smith2020climate'])
        self.assertEqual(len(self.distinct()), 1)
        # not asked again
        self.papers(f'add {self.write("again.bib", NEW.replace("Smith_2020", "Smith_2020b"))}')
        self.assertEqual(len(self.entries()), 3)

    def test_n_same_key_gets_a_free_key(self):
        same_key = self.write('samekey.bib', NEW.replace('Smith_2020', 'smith2020climate'))
        self.papers(f'add {same_key} --on-duplicate ask', answers=['n'])
        entries = self.entries()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries['smith2020climate']['journal'], 'Nature')

    def test_s(self):
        self.add('s')
        self.assertEqual(Path(self.bibtex).read_text(), LIB)

    def test_q_skips_remaining_duplicates(self):
        both = self.write('both.bib', NEW + '\n' + NEW.replace('Smith_2020', 'Smith_2020b')
                          + '\n@article{X,\n author = {Brown, Bob},\n title = {Ocean tides}\n}\n')
        self.papers(f'add {both} --on-duplicate ask', answers=['q'])
        self.assertEqual(sorted(self.entries()), ['X', 'smith2020climate'])
        self.assertNotIn('volume', self.entry('smith2020climate'))

    def test_help_and_invalid(self):
        out = self.add('?', 'u', 'x', '1')
        self.assertIn('not the same paper: add the new entry separately', out)
        self.assertIn("invalid answer: 'u'", out)

    def test_title_guard_asks(self):
        chapter = self.write('chapter.bib', '@incollection{chap,\n doi = {10.1000/abc123},\n'
                             ' title = {Sea level rise in the next century}\n}\n')
        with self.assertRaises(DuplicateError):
            self.papers(f'add {chapter}')
        # keep does not merge it either
        self.papers(f'add {chapter} --on-duplicate keep')
        self.assertEqual(list(self.entries()), ['smith2020climate'])
        out = self.papers(f'add {chapter} --on-duplicate ask', answers=['n'])
        self.assertIn('but the entry types (article, incollection) and the titles differ', out)
        self.assertEqual(sorted(self.entries()), ['chap', 'smith2020climate'])
        self.assertEqual(len(self.distinct()), 1)


class TestAddDeprecated(LibraryTest):

    def setUp(self):
        super().setUp()
        self.new = self.write('new.bib', NEW)

    def warns(self, cmd, text):
        with self.assertLogs('papers', level='WARNING') as logs:
            self.papers(cmd)
        self.assertIn(text, '\n'.join(logs.output))

    def test_mode_u(self):
        self.warns(f'add {self.new} -m u', '-m/--mode u is deprecated: use --on-duplicate keep')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature')

    def test_mode_U(self):
        self.warns(f'add {self.new} -m U', 'use --on-duplicate update')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature Climate Change')

    def test_mode_o(self):
        self.warns(f'add {self.new} -m o', 'use --on-duplicate update (the key and the fields only in the library')
        self.assertEqual(self.entry('smith2020climate')['keywords'], 'climate, mine')

    def test_mode_s(self):
        self.warns(f'add {self.new} -m s', 'use --on-duplicate skip')
        self.assertEqual(Path(self.bibtex).read_text(), LIB)

    def test_mode_r(self):
        with self.assertRaises(DuplicateError):
            self.papers(f'add {self.new} -m r')

    def test_mode_a(self):
        self.warns(f'add {self.new} -m a', 'use --no-check-duplicate')
        self.assertEqual(sorted(self.entries()), ['Smith_2020', 'smith2020climate'])

    def test_option_wins(self):
        self.warns(f'add {self.new} -m u --on-duplicate update', 'deprecated')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature Climate Change')

    def test_no_merge_files(self):
        self.warns(f'add {self.new} --no-merge-files --on-duplicate keep', '--no-merge-files is deprecated')
        self.assertIn('other/smith-preprint.pdf', self.entry('smith2020climate')['file'])


# CHECK
# =====

GROUP = LIB + """
@article{Smith_2020,
 author = {Smith, J. and Doe, J.},
 file = {:other/smith-preprint.pdf:pdf},
 journal = {Nature Climate Change},
 title = {Climate Sensitivity Revisited},
 year = {2020}
}

@misc{smith2019preprint,
 author = {Smith, John and Doe, Jane},
 doi = {10.5194/egusphere-2019-1},
 title = {Climate sensitivity revisited},
 year = {2019}
}

@article{brown2021,
 author = {Brown, Bob},
 title = {Other},
 year = {2021}
}
"""


class TestCheckOnDuplicate(LibraryTest):

    lib = GROUP

    def test_default_without_terminal_is_error(self):
        with self.assertRaises(DuplicateError) as cm:
            self.papers('check --duplicates')
        self.assertIn('same paper: smith2020climate, Smith_2020', str(cm.exception))
        self.assertIn('--on-duplicate', str(cm.exception))
        self.assertEqual(Path(self.bibtex).read_text(), GROUP)

    def test_keep(self):
        out = self.papers('check --duplicates --on-duplicate keep')
        self.assertIn('merged into smith2020climate: Smith_2020 (kept in ids)', out)
        entries = self.entries()
        self.assertEqual(sorted(entries), ['brown2021', 'smith2019preprint', 'smith2020climate'])
        e = entries['smith2020climate']
        self.assertEqual(e['journal'], 'Nature')
        self.assertEqual(e['ids'], 'Smith_2020')
        self.assertEqual(e['file'], ':files/smith.pdf:pdf;:other/smith-preprint.pdf:pdf')
        self.assertEqual(entries['smith2019preprint']['doi'], '10.5194/egusphere-2019-1')

    def test_ids_appended_without_repetition(self):
        Path(self.bibtex).write_text(GROUP.replace(' journal = {Nature},', ' ids = {old, Smith_2020},\n journal = {Nature},'))
        self.papers('check --duplicates --on-duplicate keep')
        self.assertEqual(self.entry('smith2020climate')['ids'], 'old, Smith_2020')

    def test_skip(self):
        self.papers('check --duplicates --on-duplicate skip')
        self.assertEqual(len(self.entries()), 4)

    def test_force_is_skip(self):
        self.papers('check --duplicates --force')
        self.assertEqual(len(self.entries()), 4)

    def test_update_not_available(self):
        with self.assertRaises(SystemExit):
            self.papers('check --duplicates --on-duplicate update')

    def test_mode_m(self):
        with self.assertLogs('papers', level='WARNING') as logs:
            self.papers('check --duplicates -m m')
        self.assertIn('use --on-duplicate keep', '\n'.join(logs.output))
        self.assertEqual(len(self.entries()), 3)


class TestCheckDialogue(LibraryTest):

    lib = GROUP

    def check(self, *answers, editor=None):
        return self.papers('check --duplicates --on-duplicate ask', answers=answers, editor=editor)

    def test_1(self):
        out = self.check('1')
        self.assertIn('2: Smith_2020 (kept in ids)', out)
        e = self.entry('smith2020climate')
        self.assertEqual((e['journal'], e['ids']), ('Nature', 'Smith_2020'))

    def test_2(self):
        self.check('2')
        e = self.entry('smith2020climate')
        self.assertEqual(e['journal'], 'Nature Climate Change')
        self.assertNotIn('Smith_2020', self.entries())

    def test_t(self):
        out = self.check('t 2', '1')
        self.assertIn('merged into Smith_2020: smith2020climate (kept in ids)', out)
        e = self.entry('Smith_2020')
        self.assertEqual(e['journal'], 'Nature Climate Change')
        self.assertEqual(e['doi'], '10.1000/abc123')
        self.assertEqual(e['ids'], 'smith2020climate')
        self.assertEqual(e['author'], 'Smith, John and Doe, Jane')
        self.assertNotIn('smith2020climate', self.entries())

    def test_f(self):
        self.check('f', '2')
        self.assertEqual(self.entry('smith2020climate')['journal'], 'Nature Climate Change')

    def test_e(self):
        self.check('e', editor="sed -i -e 's/journal = {Nature}/journal = {Science}/'")
        e = self.entry('smith2020climate')
        self.assertEqual((e['journal'], e['ids']), ('Science', 'Smith_2020'))
        self.assertEqual(len(self.entries()), 3)

    def test_failed_edit(self):
        self.check('e', 's', editor='false')
        self.assertEqual(len(self.entries()), 4)

    def test_n_remembered(self):
        self.check('n')
        self.assertEqual(len(self.entries()), 4)
        self.assertEqual(len(self.distinct()), 1)
        # the next check does not ask about this pair, but finds the copy
        # without DOI and the preprint (same authors and title)
        with self.assertRaises(DuplicateError) as cm:
            self.papers('check --duplicates')
        self.assertIn('same paper: Smith_2020, smith2019preprint', str(cm.exception))

    def test_s_and_q(self):
        self.check('s')
        self.assertEqual(len(self.entries()), 4)
        self.check('q')
        self.assertEqual(len(self.entries()), 4)


# LIST
# ====

class TestListDuplicates(LibraryTest):

    lib = GROUP + """
@book{handbook,
 doi = {10.1000/book},
 title = {Handbook of climate}
}

@incollection{chapter,
 doi = {10.1000/book},
 title = {Sea level rise}
}
"""

    def keys(self, cmd):
        return self.papers(cmd + ' -K').split()

    def test_duplicates(self):
        self.assertEqual(self.keys('list --duplicates'), ['smith2020climate', 'Smith_2020', 'handbook', 'chapter'])

    def test_invert(self):
        self.assertEqual(sorted(self.keys('list --duplicates --invert')), ['brown2021', 'smith2019preprint'])

    def test_distinct(self):
        d = Distinct.for_bibtex(self.bibtex)
        entries = self.entries()
        d.add(entries['handbook'], entries['chapter'])
        d.save()
        self.assertEqual(self.keys('list --duplicates'), ['smith2020climate', 'Smith_2020'])

    def test_fuzzy(self):
        self.assertIn('smith2019preprint', self.keys('list --duplicates --fuzzy'))

    def test_deprecated(self):
        for option in ('--duplicates-doi', '--duplicates-tit', '--duplicates-key'):
            with self.assertLogs('papers', level='WARNING') as logs:
                keys = self.keys(f'list {option}')
            self.assertIn('deprecated: use --duplicates', '\n'.join(logs.output))
            self.assertEqual(len(keys), 4)
        with self.assertLogs('papers', level='WARNING') as logs:
            self.assertEqual(len(self.keys('list --duplicates --similarity FAIR')), 4)
        self.assertIn('--similarity is deprecated and ignored', '\n'.join(logs.output))


class TestEditEntries(unittest.TestCase):

    def test_editor_failure_returns_originals(self):
        entries = parse_string('@article{A2000,\n title = {One}\n}').entries
        self.assertIs(edit_entries(entries, editor='false'), entries)


class TestEditEntriesTempFile(unittest.TestCase):

    bib = """@article{A2000,
 author = {A. Author},
 title = {One},
 year = {2000}
}"""

    def test_temporary_file_removed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            with patch('tempfile.tempdir', d):
                edit_entries(parse_string(self.bib).entries, editor='true')
            self.assertEqual(os.listdir(d), [])

    def test_editor_fallback(self):
        # without $EDITOR, the command used to be "None <file>"
        with patch.dict(os.environ, {}, clear=False) as env, patch('os.system', return_value=1) as system:
            env.pop('EDITOR', None)
            env.pop('VISUAL', None)
            edit_entries(parse_string(self.bib).entries)
        self.assertTrue(system.call_args[0][0].startswith('vi '))
