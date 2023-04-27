import bibtexparser
from tests.common import LocalInstallTest, Biblio


class ListTest(LocalInstallTest):

    def setUp(self):
        super().setUp()
        self.papers(f'add {self.anotherbib}')

    def test_list_title(self):
        out = self.papers(f'list --title "ice-edge blooms"', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.anotherbib_content)

    def test_list_title_fuzzy(self):
        out = self.papers(f'list --title "ice edge bloom arctc"', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers(f'list --title "ice edge bloom arctc" --fuzzy', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.anotherbib_content)

    def test_list_title_multiple(self):
        out = self.papers(f'list --title ice edge', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.anotherbib_content)

        out = self.papers(f'list --title ice edge antarctic', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers(f'list --title ice edge antarctic --any', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.anotherbib_content)

    def test_list_author(self):
        out = self.papers(f'list --author perrette', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.anotherbib_content)

        out = self.papers(f'list --author perrette balafon', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers(f'list --author perrette balafon --any', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.anotherbib_content)

    def test_list_key(self):
        out = self.papers(f'list --key perrette', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.anotherbib_content)

        out = self.papers(f'list --key perrette --strict', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers(f'list --key perrette_2011 --strict', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.anotherbib_content)

    def test_list_year(self):
        out = self.papers(f'list --year 201', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.anotherbib_content)

        out = self.papers(f'list --year 201 --strict', sp_cmd='check_output')
        self.assertEqual(out, "")

        out = self.papers(f'list --year 2011 --strict', sp_cmd='check_output')
        self.assertMultiLineEqual(out, self.anotherbib_content)