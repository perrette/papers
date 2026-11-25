"""papers open --web and papers list --open-web: the web page of entries,
in the browser (mocked), through open_in_browser"""
import io
from contextlib import redirect_stdout
from unittest.mock import patch

import papers.config
from papers.cli.common import BROWSER_ASK, open_in_browser
from papers.utils import PapersExit
from tests.common import FileTest


def bibtex(key, **fields):
    return f'@article{{{key},\n' + ''.join(f' {k} = {{{v}}},\n' for k, v in fields.items()) + ' title = {T}\n}\n\n'


class TestOpenInBrowser(FileTest):
    "the helper: the question before many pages, -y, without a terminal, --dry-run"

    URLS = [f'https://doi.org/10.1000/{i}' for i in range(BROWSER_ASK + 1)]

    def setUp(self):
        super().setUp()
        patcher = patch('webbrowser.open_new_tab', return_value=True)
        self.opened = patcher.start()
        self.addCleanup(patcher.stop)

    def urls(self):
        return [c.args[0] for c in self.opened.call_args_list]

    def test_opens_each_url(self):
        with self.assertLogs('papers', 'INFO') as logs:
            open_in_browser(self.URLS[:2])
        self.assertEqual(self.urls(), self.URLS[:2])
        self.assertIn(f'INFO:papers:opening {self.URLS[0]} ...', logs.output)

    def test_up_to_the_threshold_without_question(self):
        with patch('papers.cli.common.stdin_is_terminal', return_value=False):
            open_in_browser(self.URLS[:BROWSER_ASK])
        self.assertEqual(len(self.urls()), BROWSER_ASK)

    def test_asks_in_a_terminal(self):
        with patch('papers.cli.common.stdin_is_terminal', return_value=True):
            with patch('builtins.input', return_value='n'), self.assertRaisesRegex(PapersExit, 'nothing was opened'):
                open_in_browser(self.URLS)
            self.assertEqual(self.urls(), [])
            with patch('builtins.input', return_value='y') as asked:
                open_in_browser(self.URLS)
        self.assertIn(f'{BROWSER_ASK + 1} web pages', asked.call_args.args[0])
        self.assertEqual(self.urls(), self.URLS)

    def test_no_terminal_refuses(self):
        with patch('papers.cli.common.stdin_is_terminal', return_value=False):
            with self.assertRaisesRegex(PapersExit, 'no terminal to confirm; pass -y/--yes'):
                open_in_browser(self.URLS)
        self.assertEqual(self.urls(), [])

    def test_yes(self):
        with patch('papers.cli.common.stdin_is_terminal', return_value=False):
            open_in_browser(self.URLS, yes=True)
        self.assertEqual(self.urls(), self.URLS)

    def test_dry_run(self):
        out = io.StringIO()
        with patch.object(papers.config, 'DRYRUN', True), redirect_stdout(out):
            open_in_browser(self.URLS)  # no question either
        self.assertEqual(self.urls(), [])
        self.assertEqual(out.getvalue(), ''.join(f'DRYRUN: open {url}\n' for url in self.URLS))

    def test_no_browser(self):
        self.opened.return_value = False
        with self.assertRaisesRegex(PapersExit, 'no web browser found'):
            open_in_browser(self.URLS[:1])


class TestWebPages(FileTest):
    "the web page of an entry: its DOI, else its url field, else its arXiv id; else reported"

    def setUp(self):
        super().setUp()
        self.bib(bibtex('doi2000', doi='10.1002/(SICI)1097-0258:15<1661::AID>3.0.CO;2-2', url='https://x.org/a'),
                 bibtex('url2000', url='https://example.org/b'),
                 bibtex('arxiv2000', eprint='2101.00001', archiveprefix='arXiv'),
                 bibtex('arxivdoi2000', doi='10.48550/arXiv.2101.00002'),
                 bibtex('none2000'))
        self.pdf = self.write('lib', 'files', 'a.pdf')
        patcher = patch('webbrowser.open_new_tab', return_value=True)
        self.opened = patcher.start()
        self.addCleanup(patcher.stop)

    def urls(self):
        return [c.args[0] for c in self.opened.call_args_list]

    def test_fallbacks(self):
        self.lib('open --web doi2000 url2000 arxiv2000 arxivdoi2000')
        self.assertEqual(self.urls(), [
            'https://doi.org/10.1002/%28SICI%291097-0258%3A15%3C1661%3A%3AAID%3E3.0.CO%3B2-2',
            'https://example.org/b',
            'https://arxiv.org/abs/2101.00001',
            'https://doi.org/10.48550/arXiv.2101.00002'])

    def test_none_is_reported_after_the_others(self):
        with self.assertLogs('papers', 'ERROR') as logs, self.assertRaises(PapersExit):
            self.lib('open --web none2000 url2000 unknown2000')
        self.assertEqual(self.urls(), ['https://example.org/b'])
        self.assertIn('ERROR:papers:none2000: no DOI, url or arXiv id: no web page to open', logs.output)
        self.assertTrue(any('unknown2000' in line for line in logs.output))

    def test_a_file_is_an_error(self):
        with patch('papers.cli.entry_cmds.open_with_system') as viewer, \
                self.assertLogs('papers', 'ERROR') as logs, self.assertRaises(PapersExit):
            self.lib(f'open --web {self.pdf} url2000')
        viewer.assert_not_called()
        self.assertEqual(self.urls(), ['https://example.org/b'])
        self.assertIn('a file, not an entry', logs.output[0])

    def test_keys_from_the_standard_input(self):
        with patch('sys.stdin', io.StringIO('url2000\narxiv2000\n')):
            self.lib('open --web -')
        self.assertEqual(self.urls(), ['https://example.org/b', 'https://arxiv.org/abs/2101.00001'])

    def test_dry_run_and_porcelain(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.lib('open --web url2000 --dry-run')
        self.assertEqual(out.getvalue(), 'DRYRUN: open https://example.org/b\n')
        out = io.StringIO()
        with redirect_stdout(out):
            self.lib('open --web url2000 --porcelain')
        self.assertEqual(out.getvalue(), '')
        self.assertEqual(self.urls(), ['https://example.org/b'])

    def test_yes(self):
        self.bib(*[bibtex(f'e{i}', url=f'https://example.org/{i}') for i in range(BROWSER_ASK + 1)])
        keys = ' '.join(f'e{i}' for i in range(BROWSER_ASK + 1))
        with patch('papers.cli.common.stdin_is_terminal', return_value=False):
            with self.assertRaisesRegex(PapersExit, 'no terminal'):
                self.lib(f'open --web {keys}')
            self.assertEqual(self.urls(), [])
            self.lib(f'open --web -y {keys}')
        self.assertEqual(len(self.urls()), BROWSER_ASK + 1)

    def test_list_open_web(self):
        self.lib('list --open-web --any --key url2000 arxiv2000')
        listed = self.urls()
        self.opened.reset_mock()
        self.lib('open --web url2000 arxiv2000')
        self.assertEqual(listed, self.urls())
        self.assertEqual(len(listed), 2)

    def test_list_open_web_reports_and_asks(self):
        with self.assertLogs('papers', 'ERROR'), self.assertRaises(PapersExit):
            self.lib('list --open-web --any --key none2000 url2000')
        self.assertEqual(self.urls(), ['https://example.org/b'])
        self.bib(*[bibtex(f'e{i}', url=f'https://example.org/{i}') for i in range(BROWSER_ASK + 1)])
        self.opened.reset_mock()
        with patch('papers.cli.common.stdin_is_terminal', return_value=False):
            with self.assertRaisesRegex(PapersExit, 'no terminal'):
                self.lib('list --open-web')
            self.lib('list --open-web --yes')
        self.assertEqual(len(self.urls()), BROWSER_ASK + 1)

    def test_list_yes_goes_with_open_web(self):
        with self.assertRaises(SystemExit):
            self.lib('list --yes')
        with self.assertRaises(SystemExit):
            self.lib('list --open --open-web')

    def test_list_open_web_does_not_lock(self):
        with patch('papers.lock.acquire') as acquire:
            self.lib('list --open-web --key url2000')
        acquire.assert_not_called()
