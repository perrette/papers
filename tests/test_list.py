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
