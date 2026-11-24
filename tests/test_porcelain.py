"""--porcelain: the entries a command added, modified or removed, for programs"""
import io
import sys
from contextlib import redirect_stderr, redirect_stdout

from tests.common import FileTest, entry


class TestPorcelain(FileTest):

    def setUp(self):
        super().setUp()
        self.bib(entry('one2000'), entry('two2000'))

    def run_porcelain(self, cmd):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.lib(cmd + ' --porcelain')
        return out.getvalue().splitlines(), err.getvalue()

    def test_add(self):
        new = self.write('new.bib', content=entry('three2000'))
        lines, _ = self.run_porcelain(f'add {new}')
        self.assertEqual(lines, ['added three2000'])
        lines, _ = self.run_porcelain(f'add {new}')
        self.assertEqual(lines, ['existing three2000'])

    def test_add_skipped_duplicate_is_existing(self):
        # a duplicate skipped by --on-duplicate skip: the library entry it is of was considered
        new = self.write('new.bib', content=entry('other2000', doi='10.1/one').replace('year', 'journal = {J},\n year'))
        self.lib('edit one2000 --set doi=10.1/one')
        lines, err = self.run_porcelain(f'add {new} --on-duplicate skip')
        self.assertEqual(lines, ['existing one2000'])
        self.assertIn('skipped: other2000', err)

    def test_tag_and_rm(self):
        self.assertEqual(self.run_porcelain('tag one2000 --add x')[0], ['modified one2000'])
        self.assertEqual(self.run_porcelain('rm two2000 --keep-files')[0], ['removed two2000'])

    def test_tag_rename(self):
        self.run_porcelain('tag one2000 two2000 --add climate')
        lines, err = self.run_porcelain('tag --rename climate ocean')
        self.assertEqual(lines, ['modified one2000', 'modified two2000'])
        self.assertIn('renamed tag climate to ocean in 2 entries', err)
        self.assertEqual(self.run_porcelain('tag --rename nothing other')[0], [])

    def test_other_messages_on_stderr(self):
        # the human messages of the command go to the standard error
        lines, err = self.run_porcelain('tag one2000 two2000 --add x')
        self.assertEqual(lines, ['modified one2000', 'modified two2000'])
        lines, err = self.run_porcelain('tag')
        self.assertEqual(lines, [])
        self.assertIn('x (2)', err)

    def test_stdout_restored(self):
        stdout = sys.stdout
        self.run_porcelain('tag one2000 --add y')
        self.assertIs(sys.stdout, stdout)

    def test_list_on_stdout(self):
        # the listing of papers list is its data: on the standard output
        self.assertEqual(self.run_porcelain('list -K')[0], ['one2000', 'two2000'])
        self.assertEqual(self.run_porcelain('list --field year')[0], ['one2000: 2000', 'two2000: 2000'])
        # a list action prints the porcelain lines of its command
        self.assertEqual(self.run_porcelain('list one2000 --add-tag x')[0], ['modified one2000'])
