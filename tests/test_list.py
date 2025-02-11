import bibtexparser
from tests.common import LocalInstallTest, Biblio, tempfile
from papers.utils import strip_all

bibtex = """@article{Perrette_2011,
 author = {M. Perrette and A. Yool and G. D. Quartly and E. E. Popova},
 doi = {10.5194/bg-8-515-2011},
 file = {article.pdf:pdf; supplement.mov:mov},
 journal = {Biogeosciences},
 keywords = {kiwi, ocean},
 link = {https://doi.org/10.5194%2Fbg-8-515-2011},
 month = {feb},
 number = {2},
 pages = {515--524},
 publisher = {Copernicus {GmbH}},
 title = {Near-ubiquity of ice-edge blooms in the Arctic},
 volume = {8},
 year = {2011}
}"""


class ListTest(LocalInstallTest):
    initial_content = bibtex
    anotherbib_content = None


class FormattingTest(ListTest):

    def test_format(self):
        out = self.papers(f'list -l', sp_cmd='check_output')
        self.assertEqual(strip_all(out), "Perrette_2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, files:2, kiwi | ocean)")

        out = self.papers(f'list --key-only', sp_cmd='check_output')
        self.assertEqual(out, "Perrette_2011")

        out = self.papers(f'list -f month doi', sp_cmd='check_output')
        self.assertEqual(strip_all(out), "Perrette_2011: feb 10.5194/bg-8-515-2011")


class SearchTest(ListTest):

    def test_list_title(self):
        out = self.papers(f'list --plain --title "ice-edge blooms"', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

    def test_list_title_fuzzy(self):
        out = self.papers(f'list --plain --title "ice edge bloom arctc"', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers(f'list --plain --title "ice edge bloom arctc" --fuzzy', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

    def test_list_title_multiple(self):
        out = self.papers(f'list --plain --title ice edge', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        out = self.papers(f'list --plain --title ice edge antarctic', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers(f'list --plain --title ice edge antarctic --any', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

    def test_list_author(self):
        out = self.papers(f'list --plain --author perrette', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        out = self.papers(f'list --plain --author perrette balafon', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers(f'list --plain --author perrette balafon --any', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

    def test_list_key(self):
        out = self.papers(f'list --plain --key perrette', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        out = self.papers(f'list --plain --key perrette --strict', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers(f'list --plain --key perrette_2011 --strict', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

    def test_list_year(self):
        out = self.papers(f'list --plain --year 201', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        out = self.papers(f'list --plain --year 201 --strict', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers(f'list --plain --year 2011 --strict', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

    def test_list_tag(self):
        out = self.papers(f'list --plain --tag kiwi', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        out = self.papers(f'list --plain --tag kiwi ocean', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        out = self.papers(f'list --plain --tag kiwi bonobo', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers(f'list --plain --tag kiwi bonobo --any', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)


    def test_list_combined(self):
        out = self.papers(f'list --plain --year 2011 --author perrette', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        # Here we'd need the full name (never useful in practice)
        out = self.papers(f'list --plain --year 2011 --author perrette --strict', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers(f'list --plain --year 2021 --author perrette', sp_cmd='check_output')
        self.assertEqual(out, "")

        # --any has no effect on multiple strings
        out = self.papers(f'list --plain --year 2021 --author perrette --any', sp_cmd='check_output')
        self.assertEqual(out, "")


    def test_list_fullsearch(self):
        out = self.papers(f'list --plain 2011 perrette', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        # --strict is deactivated
        out = self.papers(f'list --plain 2011 perrette --strict', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)

        out = self.papers(f'list --plain 2021 perrette', sp_cmd='check_output')
        self.assertEqual(out, "")

        # any works well on full search strings
        out = self.papers(f'list --plain 2021 perrette --any', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.initial_content)


class EditTest(ListTest):
    def test_delete(self):
        out = self.papers(f'list --author perrette --delete', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers(f'list', sp_cmd='check_output')
        self.assertEqual(out, "")


    def test_add_tag(self):

        out = self.papers(f'list --tag newtag', sp_cmd='check_output')
        self.assertEqual(out, "")

        self.papers(f'list --author perrette --add-tag newtag -1')
        # self.assertEqual(strip_all(out), "Perrette_2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, files:2, kiwi | ocean | newtag)")

        out = self.papers(f'list --tag newtag -1', sp_cmd='check_output')
        self.assertEqual(strip_all(out), "Perrette_2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, files:2, kiwi | ocean | newtag)")

    def test_add_files(self):

        with tempfile.NamedTemporaryFile() as temp, tempfile.NamedTemporaryFile() as temp2:
            out = self.papers(f'list 2011 perrette -1', sp_cmd='check_output')
            self.assertEqual(strip_all(out), "Perrette_2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, files:2, kiwi | ocean)")

            out = self.papers(f'list 2011 perrette --add-files {temp.name}  {temp2.name} --rename --copy', sp_cmd='check_output')

            out = self.papers(f'list 2011 perrette -1', sp_cmd='check_output')
            self.assertEqual(strip_all(out), "Perrette_2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, files:4, kiwi | ocean)")