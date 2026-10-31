"""The version of the PDFs that papers file fetch attaches (.papers/files.json), papers file fetch
--upgrade, and the versions in papers list (history.md 10, library.md "The free PDF of an entry",
formats.md 6), with the network mocked"""
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path

from papers.formats import dumps
from papers.utils import checksum
from tests.common import entry
from tests.test_file_fetch import DOI, PDF, FetchTest, location, pdf_bytes

AM = 'https://repo.example.edu/am.pdf'


class VersionsTest(FetchTest):
    "smith2020 gets an accepted manuscript: the publisher refuses its PDF"

    def setUp(self):
        super().setUp()
        self.bib(entry('smith2020', doi=DOI))
        self.publisher(content=403)
        self.web.openalex[DOI] = [location(AM, 'acceptedVersion')]
        self.web.files[AM] = pdf_bytes('am')

    def files_json(self):
        path = self.path('lib', '.papers', 'files.json')
        return json.loads(Path(path).read_text()) if os.path.exists(path) else None

    def version_of(self, path):
        data = self.files_json()
        return data.get('versions', {}).get(data['files'].get(path))

    def fetch_accepted(self):
        self.lib('file fetch smith2020')
        file, = self.files('smith2020')
        return file, os.path.relpath(file, self.path('lib'))

    def publish(self):
        "the publisher gives its PDF now"
        self.web.files[PDF] = pdf_bytes('vor')


class TestFilesJson(VersionsTest):

    def test_written_by_fetch(self):
        file, rel = self.fetch_accepted()
        self.assertEqual(self.files_json(), {'files': {rel: checksum(file).hex()},
                                             'versions': {checksum(file).hex(): 'accepted'}})
        text = Path(self.path('lib', '.papers', 'files.json')).read_text()
        self.assertEqual(text, json.dumps(self.files_json(), indent=1, sort_keys=True) + '\n')

    def test_add_fetch_pdf(self):
        from unittest import mock
        from tests.test_file_fetch import BIBTEX
        self.bib()
        self.publisher()
        with mock.patch('papers.bib.fetch_bibtex_by_doi', return_value=BIBTEX):
            out = self.out(f'add --doi {DOI} --fetch-pdf')
        key, = [line.split()[2].rstrip(':') for line in out.splitlines() if line.startswith('Added')]
        file, = self.files(key)
        self.assertEqual(self.version_of(os.path.relpath(file, self.path('lib'))), 'published')

    def test_no_version_for_a_file_attached_by_hand(self):
        self.write('downloads', 'x.pdf', content='pdf x')
        self.lib(f'file attach smith2020 {self.path("downloads", "x.pdf")} --copy')
        self.assertNotIn('versions', self.files_json())

    def test_supplements_have_no_version(self):
        self.publisher(pdf=PDF, links=[('https://journals.example.org/suppl.pdf', 'Supplement')])
        self.web.files['https://journals.example.org/suppl.pdf'] = pdf_bytes('suppl')
        self.lib('file fetch smith2020 --supplements')
        self.assertEqual(len(self.files('smith2020')), 2)
        self.assertEqual(sorted(self.files_json()['versions'].values()), ['published'])

    def test_with_the_checksums_setting_off(self):
        self.lib('config checksums false')
        file, rel = self.fetch_accepted()
        self.assertEqual(self.version_of(rel), 'accepted')

    def test_kept_when_the_file_moves(self):
        file, rel = self.fetch_accepted()
        self.lib(f'file mv {file} {self.path("lib", "files", "moved.pdf")}')
        new, = self.files('smith2020')
        self.assertNotEqual(new, file)
        self.assertEqual(self.version_of(os.path.relpath(new, self.path('lib'))), 'accepted')

    def test_dropped_with_the_checksum(self):
        file, rel = self.fetch_accepted()
        self.write('downloads', 'x.pdf', content='pdf x')
        self.lib(f'file attach smith2020 {self.path("downloads", "x.pdf")} --copy')
        self.lib(f'file rm {file}')
        self.assertNotIn(rel, self.files_json()['files'])
        self.assertNotIn('versions', self.files_json())

    def test_old_file_without_versions(self):
        file, rel = self.fetch_accepted()
        path = self.path('lib', '.papers', 'files.json')
        Path(path).write_text(json.dumps({'files': {rel: checksum(file).hex()}}, indent=1) + '\n')
        self.assertEqual(self.out('list --format files'), f'smith2020 unknown {file}\n')
        self.lib('file checksum')
        self.assertEqual(self.files_json(), {'files': {rel: checksum(file).hex()}})

    def test_undo_restores_the_versions(self):
        file, rel = self.fetch_accepted()
        self.lib('undo')
        self.assertIsNone(self.files_json())
        self.lib('redo')
        self.assertEqual(self.version_of(rel), 'accepted')


class TestUpgrade(VersionsTest):

    def test_replaces_under_the_same_name(self):
        file, rel = self.fetch_accepted()
        self.publish()
        out = self.out('file fetch --upgrade')
        self.assertIn(f'smith2020: {rel}: accepted manuscript replaced by the published version, '
                      'from journals.example.org', out)
        self.assertEqual(self.files('smith2020'), [file])
        self.assertEqual(Path(file).read_bytes(), pdf_bytes('vor'))
        self.assertEqual(self.files_json(), {'files': {rel: checksum(file).hex()},
                                             'versions': {checksum(file).hex(): 'published'}})
        self.assertEqual(self.libfiles(), [os.path.basename(file)])

    def test_undo_brings_the_old_file_back(self):
        file, rel = self.fetch_accepted()
        self.publish()
        self.lib('file fetch --upgrade smith2020')
        self.lib('undo')
        self.assertEqual(Path(file).read_bytes(), pdf_bytes('am'))
        self.assertEqual(self.version_of(rel), 'accepted')
        self.assertEqual(self.libfiles(), [os.path.basename(file)])
        self.lib('redo')
        self.assertEqual(Path(file).read_bytes(), pdf_bytes('vor'))
        self.assertEqual(self.version_of(rel), 'published')
        self.lib('undo')
        self.assertEqual(Path(file).read_bytes(), pdf_bytes('am'))

    def test_undo_leaves_a_file_changed_since(self):
        file, rel = self.fetch_accepted()
        self.publish()
        self.lib('file fetch --upgrade smith2020')
        Path(file).write_bytes(b'%PDF annotated')
        self.lib('undo')
        self.assertEqual(Path(file).read_bytes(), b'%PDF annotated')

    def test_operations_of_the_step(self):
        file, rel = self.fetch_accepted()
        old = checksum(file).hex()
        self.publish()
        self.lib('file fetch --upgrade smith2020')
        from papers import backup
        from papers.config import CONFIG_FILE_LOCAL, Config
        project, place = backup.project_of(Config.load(self.path('lib', CONFIG_FILE_LOCAL)), create=False)
        ops = project.state(project.head(place)['state'])['ops']
        new = checksum(file).hex()
        self.assertEqual([(op['op'], op['dst'] == rel, op['checksum']) for op in ops],
                         [('trashed', False, old), ('copied', True, new)])
        self.assertEqual(ops[0]['src'], rel)

    def test_only_the_published_version(self):
        self.fetch_accepted()
        self.web.requests.clear()
        self.lib('file fetch --upgrade')
        self.assertEqual(self.web.downloads(), [PDF])  # not the accepted manuscript again

    def test_no_published_version_changes_nothing(self):
        file, rel = self.fetch_accepted()
        before = self.files_json()
        history = self.out('history')
        out = self.out('file fetch --upgrade smith2020')
        self.assertIn(f'smith2020: {rel} (accepted manuscript) kept: no PDF could be downloaded', out)
        self.assertIn(f'open in a browser: {PDF}', out)
        self.assertEqual(Path(file).read_bytes(), pdf_bytes('am'))
        self.assertEqual(self.files_json(), before)
        self.assertEqual(self.out('history'), history)

    def test_dry_run(self):
        file, rel = self.fetch_accepted()
        self.publish()
        out = self.out('file fetch --upgrade --dry-run')
        self.assertIn(f'DRYRUN: smith2020: would download {PDF} (published version, from journals.example.org)'
                      f', in place of {rel} (accepted manuscript)', out)
        self.assertEqual(Path(file).read_bytes(), pdf_bytes('am'))
        self.assertEqual(self.version_of(rel), 'accepted')

    def test_entries_without_lower_version(self):
        self.write('lib', 'files', 'a.pdf', content='pdf a')
        self.bib(entry('smith2020', doi=DOI), entry('hand2000', 'files/a.pdf', doi='10.1000/hand'))
        self.fetch_accepted()
        self.publish()
        out = self.out('file fetch --upgrade hand2000')
        self.assertIn('hand2000: no accepted manuscript or submitted version to replace', out)
        self.assertEqual(self.web.downloads(), [PDF, AM])  # the first fetch only
        out = self.out('file fetch --upgrade')  # all entries: those with a lower version
        self.assertNotIn('hand2000', out)
        self.assertIn('smith2020: files/', out)
        self.assertIn('replaced by the published version', out)

    def test_nothing_to_upgrade(self):
        self.assertIn('no entry has an accepted manuscript or a submitted version',
                      self.out('file fetch --upgrade'))

    def test_summary_of_several_entries(self):
        self.bib(entry('smith2020', doi=DOI), entry('ice2020', doi='10.1000/ice'))
        self.publisher(doi='10.1000/ice', pdf='https://journals.example.org/ice.pdf', content=403)
        self.web.openalex['10.1000/ice'] = [location('https://repo.example.edu/ice.pdf', 'submittedVersion')]
        self.web.files['https://repo.example.edu/ice.pdf'] = pdf_bytes('ice')
        self.lib('file fetch smith2020 ice2020')
        self.publish()
        out = self.out('file fetch --upgrade')
        self.assertIn('summary of 2 entries:\n  1 replaced by the published version\n'
                      '  1 without published version (kept as they are)\nopen in a browser:\n'
                      '  ice2020: https://journals.example.org/ice.pdf', out)

    def test_options_that_do_not_go_with_it(self):
        for option in ('--missing', '--again', '--supplements', '--version published', '--search .'):
            with self.subTest(option), self.assertRaises(SystemExit) as error:
                self.lib(f'file fetch --upgrade {option}')
            self.assertEqual(error.exception.code, 2)


class TestList(VersionsTest):

    def setUp(self):
        super().setUp()
        self.write('lib', 'files', 'a.pdf', content='pdf a')
        self.bib(entry('smith2020', doi=DOI), entry('hand2000', 'files/a.pdf'), entry('none2000'))
        self.file, _ = self.fetch_accepted()
        self.hand = self.path('lib', 'files', 'a.pdf')

    def test_format_files(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.lib('list --format files --porcelain')
        self.assertEqual(out.getvalue(), f'hand2000 unknown {self.hand}\nsmith2020 accepted {self.file}\n')

    def test_json(self):
        csl = json.loads(self.out('list --format csl-json'))
        csl = {item['id']: item for item in csl}
        self.assertEqual(csl['smith2020']['custom'], {'file': [self.file], 'file-version': {self.file: 'accepted'}})
        self.assertEqual(csl['hand2000']['custom'], {'file': [self.hand]})
        bibjson = {r['id']: r for r in json.loads(self.out('list --format bibjson'))['records']}
        self.assertEqual(bibjson['smith2020']['file-version'], {self.file: 'accepted'})
        self.assertNotIn('file-version', bibjson['hand2000'])

    def test_export_has_no_version(self):
        self.lib(f'export {self.path("out")} --format csl-json')
        self.assertNotIn('file-version', Path(self.path('out', 'papers.json')).read_text())

    def test_pdf_version_filter(self):
        for version, keys in [('accepted', 'smith2020\n'), ('unknown', 'hand2000\n'), ('published', ''),
                              ('submitted', '')]:
            with self.subTest(version):
                self.assertEqual(self.out(f'list --pdf-version {version} -K'), keys)
        self.assertEqual(self.out('list --pdf-version accepted --invert -K'), 'hand2000\nnone2000\n')


class TestBibjsonField:
    "a field named file-version goes in bibtex:file-version (formats.md 5.1)"

    def test_field(self):
        from papers.entries import parse_string
        e, = parse_string('@misc{a,\n file-version = {x}\n}\n').entries
        record = json.loads(dumps([e], 'bibjson'))['records'][0]
        assert record['bibtex:file-version'] == 'x'
        assert 'file-version' not in record
