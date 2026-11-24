"""--openalex: the search of OpenAlex, with the network mocked"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

import requests

import papers.config
from papers import openalex
from papers.extract import extract_txt_metadata, title_in_text_strict
from papers.fetch import DOINotFoundError, DOIRequestError
from papers.utils import PapersExit
from tests.common import FileTest

PAPER = 'Greenland ice sheet mass balance under climate warming'
TEXT = ('Greenland ice sheet mass balance under climate warming\n\n'
        'Ann Author, Bo Writer\n\nWe study the mass balance of the Greenland ice sheet.')


def work(title=PAPER, doi='https://doi.org/10.1000/gis', id='W1', kind='article', year=2020,
         authors=('Ann Author', 'Bo Writer'), **kw):
    """a work as the search returns it, trimmed (see openalex._trim)"""
    w = {'id': 'https://openalex.org/' + id, 'type': kind, 'publication_year': year, 'title': title,
         'authorships': [{'raw_author_name': a} for a in authors],
         'primary_location': {'landing_page_url': None,
                              'source': {'display_name': 'Nature', 'type': 'journal',
                                         'host_organization_name': 'Nature Portfolio'}}}
    if doi:
        w['doi'] = doi
    w.update(kw)
    return w


class FakeResponse:
    def __init__(self, status_code=200, json=None):
        self.status_code = status_code
        self._json = json

    def json(self):
        if isinstance(self._json, Exception):
            raise self._json
        return self._json


def answer(*works):
    return FakeResponse(json={'results': list(works)})


class OpenAlexTest(unittest.TestCase):
    """a cache of its own, no wait between requests, no key and no address in the environment"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        old = papers.config.CACHE_DIR
        papers.config.CACHE_DIR = self.tmp.name
        self.addCleanup(setattr, papers.config, 'CACHE_DIR', old)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for name in (openalex.API_KEY_ENV, openalex.MAILTO_ENV):
            os.environ.pop(name, None)
        throttle = mock.patch('papers.openalex._throttle')
        throttle.start()
        self.addCleanup(throttle.stop)

    def get(self, *responses):
        """mock http_get: the requests (url, params), the answers in turn"""
        calls = []
        responses = list(responses)

        def http_get(url, **kw):
            calls.append((url, kw.get('params')))
            response = responses.pop(0) if len(responses) > 1 else responses[0]
            if isinstance(response, Exception):
                raise response
            return response
        patch = mock.patch('papers.openalex.http_get', http_get)
        patch.start()
        self.addCleanup(patch.stop)
        return calls


class TestQuery(OpenAlexTest):

    def test_cut_at_a_word(self):
        self.assertEqual(openalex.truncate('one two three', 100), 'one two three')
        self.assertEqual(openalex.truncate('one two three', 9), 'one two')
        self.assertEqual(openalex.truncate('one two three', 7), 'one two')  # the word ends there
        self.assertEqual(openalex.truncate('onetwothree', 5), 'onetw')
        self.assertEqual(openalex.truncate('é é é', 2), 'é')

    def test_long_query_is_cut_at_1500_characters(self):
        calls = self.get(answer(work()))
        query = ' '.join(['climate'] * 400)  # 3199 characters
        openalex.fetch_bibtex_by_fulltext_openalex(query)
        sent = calls[0][1]['search.semantic']
        self.assertLessEqual(len(sent), 1500)
        self.assertGreater(len(sent), 1490)
        self.assertEqual(set(sent.split()), {'climate'})  # no word is cut

    def test_semantic_search_of_the_work_fields(self):
        calls = self.get(answer(work()))
        with mock.patch('papers.openalex.fetch_bibtex_by_doi', return_value='@misc{x}'):
            openalex.fetch_bibtex_by_fulltext_openalex(PAPER)
        url, params = calls[0]
        self.assertEqual(url, 'https://api.openalex.org/works')
        self.assertEqual(params['search.semantic'], PAPER)
        self.assertNotIn('search', params)  # the plain search needs every word
        self.assertEqual(params['per-page'], openalex.ROWS)
        self.assertIn('abstract_inverted_index', params['select'])

    def test_email_and_key_from_the_environment(self):
        calls = self.get(answer(work()))
        with mock.patch('papers.openalex.fetch_bibtex_by_doi', return_value='@misc{x}'):
            openalex.fetch_bibtex_by_fulltext_openalex(PAPER)
            self.assertNotIn('mailto', calls[0][1])
            self.assertNotIn('api_key', calls[0][1])
            os.environ[openalex.MAILTO_ENV] = 'me@example.org'
            os.environ[openalex.API_KEY_ENV] = 'secret'
            openalex.fetch_bibtex_by_fulltext_openalex(PAPER + ' again')
        self.assertEqual(calls[1][1]['mailto'], 'me@example.org')
        self.assertEqual(calls[1][1]['api_key'], 'secret')

    def test_answers_are_cached_whatever_the_key(self):
        calls = self.get(answer(work()))
        with mock.patch('papers.openalex.fetch_bibtex_by_doi', return_value='@misc{x}'):
            openalex.fetch_bibtex_by_fulltext_openalex(PAPER)
            os.environ[openalex.API_KEY_ENV] = 'secret'
            openalex.fetch_bibtex_by_fulltext_openalex(PAPER)
            openalex.fetch_bibtex_by_fulltext_openalex(PAPER + ' other')
        self.assertEqual(len(calls), 2)
        self.assertTrue(os.listdir(os.path.join(self.tmp.name, 'openalex')))

    def test_no_cache_for_an_error(self):
        calls = self.get(FakeResponse(500, {}), answer(work()))
        with mock.patch('papers.openalex.fetch_bibtex_by_doi', return_value='@misc{x}'):
            with self.assertRaises(openalex.OpenAlexError):
                openalex.fetch_bibtex_by_fulltext_openalex(PAPER)
            self.assertEqual(openalex.fetch_bibtex_by_fulltext_openalex(PAPER), '@misc{x}')
        self.assertEqual(len(calls), 2)


class TestThrottle(unittest.TestCase):

    def test_one_request_a_second(self):
        waits = []
        with mock.patch.object(openalex, '_last_request', None), \
                mock.patch('papers.openalex.time.sleep', waits.append), \
                mock.patch('papers.openalex.time.monotonic', side_effect=[100.0, 100.3, 100.3, 105.0, 105.0]):
            openalex._throttle()  # the first request does not wait
            openalex._throttle()  # 0.3 s later
            openalex._throttle()  # long after
        self.assertEqual(len(waits), 1)
        self.assertAlmostEqual(waits[0], openalex.INTERVAL - 0.3)
        self.assertGreaterEqual(openalex.INTERVAL, 1.0)


class TestChoice(OpenAlexTest):
    """the best of the works by the score of papers and the check of the title"""

    def fetch(self, works, text=TEXT, accept=True):
        shutil.rmtree(os.path.join(self.tmp.name, 'openalex'), ignore_errors=True)  # not the answer of the last call
        self.get(answer(*works))
        accept = (lambda title: title_in_text_strict(title, text)) if accept else None
        with mock.patch('papers.openalex.fetch_bibtex_by_doi', side_effect=lambda doi: f'@misc{{{doi}}}') as by_doi:
            return openalex.fetch_bibtex_by_fulltext_openalex(text, accept=accept), by_doi

    def test_best_score_first(self):
        other = work(title='Antarctic ice shelves in a warming world', doi='10.1000/ant', id='W2', authors=('Zed Zee',))
        bibtex, _ = self.fetch([other, work()], accept=False)
        self.assertEqual(bibtex, '@misc{10.1000/gis}')

    def test_first_of_equal_scores(self):
        a, b = work(doi='10.1000/a'), work(doi='10.1000/b', id='W2')
        self.assertEqual(self.fetch([a, b])[0], '@misc{10.1000/a}')
        self.assertEqual(self.fetch([b, a])[0], '@misc{10.1000/b}')

    def test_title_must_be_in_the_text(self):
        # the best by score has a title that the text does not have (a cited paper)
        cited = work(title='Mass balance of the Greenland ice sheet from 1992 to 2018', doi='10.1000/cited', id='W2',
                     authors=('Ann Author', 'Bo Writer'))
        text = TEXT + ' We use the data of the Greenland ice sheet from 1992 to 2018.'
        bibtex, _ = self.fetch([cited, work()], text=text)
        self.assertEqual(bibtex, '@misc{10.1000/gis}')

    def test_no_title_in_the_text_gives_the_best(self):
        # the caller's own check rejects it
        bibtex, _ = self.fetch([work(title='Something else entirely of this kind', doi='10.1000/x')])
        self.assertEqual(bibtex, '@misc{10.1000/x}')

    def test_short_titles_do_not_pass(self):
        # a journal name, or a word of every text, is in the text (title_in_text lets it pass too)
        journal = work(title='Nature', doi='10.1000/nature', id='W2', authors=('Ann Author', 'Bo Writer'))
        self.assertTrue(title_in_text_strict(PAPER, 'x ' + PAPER))
        self.assertFalse(title_in_text_strict('Nature', 'published in Nature'))
        self.assertFalse(title_in_text_strict('abcde fghij klmno pqrs', 'abcde fghij klmno pqrs'))  # 19 letters
        self.assertTrue(title_in_text_strict('abcde fghij klmno pqrst', 'abcde fghij klmno pqrst'))  # 20
        self.assertEqual(self.fetch([journal, work()], text=TEXT + ' Nature')[0], '@misc{10.1000/gis}')

    def test_published_works_before_their_copies(self):
        preprint = work(doi='10.31223/preprint', id='W2', kind='preprint',
                        abstract='We study the mass balance of the Greenland ice sheet.')
        self.assertEqual(self.fetch([preprint, work()])[0], '@misc{10.1000/gis}')
        # copies only: the best of them
        self.assertEqual(self.fetch([preprint])[0], '@misc{10.31223/preprint}')
        abstract = work(doi=None, id='W3', kind='conference-abstract')
        self.assertTrue(openalex.is_copy(abstract))
        self.assertFalse(openalex.is_copy(work(kind='book-chapter')))

    def test_without_check_the_best_is_taken(self):
        copy = work(doi='10.31223/preprint', id='W2', kind='preprint',
                    abstract='We study the mass balance of the Greenland ice sheet.')
        self.assertEqual(self.fetch([copy, work()], accept=False)[0], '@misc{10.31223/preprint}')

    def test_no_results(self):
        self.get(answer())
        with self.assertRaisesRegex(ValueError, 'no results'):
            openalex.fetch_bibtex_by_fulltext_openalex(TEXT)


class TestEntry(OpenAlexTest):

    def test_doi_path(self):
        self.get(answer(work()))
        with mock.patch('papers.openalex.fetch_bibtex_by_doi', return_value='@article{10.1000/gis,\n}') as by_doi:
            self.assertEqual(openalex.fetch_bibtex_by_fulltext_openalex(TEXT), '@article{10.1000/gis,\n}')
        by_doi.assert_called_once_with('10.1000/gis')  # without its url

    def test_doi_without_metadata_gives_the_openalex_entry(self):
        self.get(answer(work()))
        for error in [DOIRequestError('no metadata'), DOINotFoundError('not found')]:
            with mock.patch('papers.openalex.fetch_bibtex_by_doi', side_effect=error), self.assertLogs('papers', 'INFO'):
                bibtex = openalex.fetch_bibtex_by_fulltext_openalex(TEXT)
            self.assertIn('@article{10.1000/gis,', bibtex)
            self.assertIn(PAPER, bibtex)

    def test_network_error_of_the_doi_path_is_raised(self):
        self.get(answer(work()))
        with mock.patch('papers.openalex.fetch_bibtex_by_doi', side_effect=requests.ConnectionError('down')):
            with self.assertRaises(OSError):
                openalex.fetch_bibtex_by_fulltext_openalex(TEXT)

    def test_work_without_doi(self):
        w = work(doi=None, id='W2741809807', year=2019,
                 authors=('Ann Author', 'van der Berg, Bo'),
                 biblio={'volume': '579', 'issue': '7798', 'first_page': '233', 'last_page': '239'},
                 abstract='We study the mass balance of the Greenland ice sheet.')
        w['primary_location']['landing_page_url'] = 'https://example.org/paper'
        self.get(answer(w))
        with mock.patch('papers.openalex.fetch_bibtex_by_doi') as by_doi:
            bibtex = openalex.fetch_bibtex_by_fulltext_openalex(TEXT)
        by_doi.assert_not_called()
        from papers.entries import parse_string, get_entry_val
        entry = parse_string(bibtex).entries[0]
        self.assertEqual(entry.entry_type, 'article')
        self.assertEqual(entry.key, 'W2741809807')
        for field, value in [('title', PAPER), ('author', 'Author, Ann and van der Berg, Bo'), ('year', '2019'),
                             ('journal', 'Nature'), ('volume', '579'), ('number', '7798'),
                             ('pages', '233-239'), ('url', 'https://example.org/paper')]:
            self.assertEqual(get_entry_val(entry, field), value, field)
        self.assertIsNone(get_entry_val(entry, 'doi', None))

    def test_types(self):
        kind = lambda **kw: openalex.work_record(work(**kw))['type']
        self.assertEqual(kind(type_crossref='book-chapter', kind='article'), 'book-chapter')
        self.assertEqual(kind(kind='article'), 'journal-article')
        conference = {'type': 'conference', 'display_name': 'Proc'}
        self.assertEqual(kind(primary_location={'source': conference}), 'proceedings-article')
        self.assertEqual(kind(primary_location={'source': {'type': 'repository'}}), 'posted-content')
        self.assertEqual(kind(kind='preprint'), 'posted-content')
        self.assertEqual(kind(kind='dissertation'), 'thesis')
        self.assertEqual(kind(kind='book'), 'book')
        self.assertEqual(kind(kind='dataset'), 'dataset')

    def test_names(self):
        pair = lambda g, f: (g, f)
        self.assertEqual(openalex.split_name('Alexander Robinson'), pair('Alexander', 'Robinson'))
        self.assertEqual(openalex.split_name('Jason E. Box'), pair('Jason E.', 'Box'))
        self.assertEqual(openalex.split_name('Dirk van As'), pair('Dirk', 'van As'))
        self.assertEqual(openalex.split_name('Ludwig van der Waals'), pair('Ludwig', 'van der Waals'))
        self.assertEqual(openalex.split_name('Perrette, Mahé'), pair('Mahé', 'Perrette'))
        self.assertEqual(openalex.split_name('Marie‐Luise Kapsch'), pair('Marie-Luise', 'Kapsch'))
        self.assertEqual(openalex.split_name('IPCC'), pair('IPCC', ''))
        self.assertEqual(openalex.split_name('van Angelen'), pair('van', 'Angelen'))

    def test_doi_and_abstract(self):
        self.assertEqual(openalex.work_doi({'doi': 'https://doi.org/10.1/x'}), '10.1/x')
        self.assertEqual(openalex.work_doi({'doi': '10.1/x'}), '10.1/x')
        self.assertIsNone(openalex.work_doi({'doi': None}))
        self.assertEqual(openalex._abstract({'is': [1], 'This': [0], 'it': [2, 3]}), 'This is it it')
        self.assertEqual(openalex._abstract(None), '')

    def test_the_cache_has_the_abstract_as_text(self):
        self.get(answer({**work(), 'abstract_inverted_index': {'Hello': [0], 'world': [1]},
                         'authorships': [{'raw_author_name': 'A B', 'institutions': [{'x': 1}]}]}))
        works = openalex._search('{"search.semantic": "q"}')
        self.assertEqual(works[0]['abstract'], 'Hello world')
        self.assertNotIn('abstract_inverted_index', works[0])
        self.assertEqual(works[0]['authorships'], [{'raw_author_name': 'A B'}])


class TestErrors(OpenAlexTest):

    def test_http_400(self):
        self.get(FakeResponse(400, {'error': 'Invalid query parameters error', 'message': 'search.semantic too long'}))
        with self.assertRaisesRegex(openalex.OpenAlexError, '^OpenAlex: HTTP 400: search.semantic too long$'):
            openalex.fetch_bibtex_by_fulltext_openalex(TEXT)

    def test_http_429_names_the_key(self):
        self.get(FakeResponse(429, {'message': 'Rate limit exceeded'}))
        with self.assertRaisesRegex(openalex.OpenAlexError, r'^OpenAlex: HTTP 429: Rate limit exceeded \(.*100 searches a day.*OPENALEX_API_KEY\)$'):
            openalex.fetch_bibtex_by_fulltext_openalex(TEXT)
        # with a key, it is another limit
        os.environ[openalex.API_KEY_ENV] = 'secret'
        with self.assertRaisesRegex(openalex.OpenAlexError, '^OpenAlex: HTTP 429: Rate limit exceeded$'):
            openalex.fetch_bibtex_by_fulltext_openalex(TEXT + ' more')

    def test_http_error_without_a_message(self):
        self.get(FakeResponse(503, ValueError('not json')))
        with self.assertRaisesRegex(openalex.OpenAlexError, '^OpenAlex: HTTP 503$'):
            openalex.fetch_bibtex_by_fulltext_openalex(TEXT)

    def test_network_error_does_not_show_the_key(self):
        os.environ[openalex.API_KEY_ENV] = 'secret'
        os.environ[openalex.MAILTO_ENV] = 'me@example.org'
        self.get(requests.ConnectionError('Max retries exceeded with url: /works?api_key=secret&mailto=me@example.org'))
        with self.assertRaises(openalex.OpenAlexError) as raised:
            openalex.fetch_bibtex_by_fulltext_openalex(TEXT)
        self.assertEqual(str(raised.exception), 'OpenAlex: Max retries exceeded with url: /works?api_key=***&mailto=***')

    def test_unexpected_answer(self):
        for body in [{'meta': {}}, ValueError('not json'), ['x']]:
            self.get(FakeResponse(200, body))
            with self.assertRaisesRegex(openalex.OpenAlexError, '^OpenAlex: unexpected answer$'):
                openalex.fetch_bibtex_by_fulltext_openalex(TEXT)

    def test_an_os_error(self):
        self.assertTrue(issubclass(openalex.OpenAlexError, OSError))  # as the errors of requests: a clean exit of the commands


class TestExtract(OpenAlexTest):
    """extract_txt_metadata(openalex=True)"""

    def test_accepted_only_with_its_title_in_the_text(self):
        self.get(answer(work()))
        text = 'A paper\n\n' + TEXT + ' ' + ' '.join(['word'] * 20)
        with mock.patch('papers.openalex.fetch_bibtex_by_doi', side_effect=lambda doi: f'@article{{{doi},\n title = {{{PAPER}}}\n}}'):
            bibtex = extract_txt_metadata(text, search_doi=False, search_fulltext=True, openalex=True)
        self.assertIn('10.1000/gis', bibtex)

    def test_another_title_is_rejected(self):
        self.get(answer(work(title='A quite different title of a paper')))
        with mock.patch('papers.openalex.fetch_bibtex_by_doi',
                        side_effect=lambda doi: '@article{x,\n title = {A quite different title of a paper}\n}'):
            with self.assertLogs('papers', 'WARNING') as logs, self.assertRaises(ValueError):
                extract_txt_metadata(TEXT + ' word word', search_doi=False, search_fulltext=True, openalex=True)
        self.assertIn('title not found', logs.output[0])

    def test_failure_is_a_warning(self):
        self.get(FakeResponse(429, {'message': 'Rate limit exceeded'}))
        with self.assertLogs('papers', 'WARNING') as logs, self.assertRaises(ValueError):
            extract_txt_metadata(TEXT, search_doi=False, search_fulltext=True, openalex=True)
        self.assertIn('fulltext query failed: OpenAlex: HTTP 429', logs.output[0])

    def test_crossref_is_not_used(self):
        self.get(answer(work()))
        with mock.patch('papers.extract.fetch_bibtex_by_fulltext_crossref') as crossref, \
                mock.patch('papers.openalex.fetch_bibtex_by_doi', return_value='@article{x,\n title = {%s}\n}' % PAPER):
            extract_txt_metadata(TEXT + ' word word', search_doi=False, search_fulltext=True, openalex=True)
        crossref.assert_not_called()


class TestCommands(FileTest):
    """the option of fetch, extract and add"""

    def test_fetch(self):
        with mock.patch('papers.cli.fetch_cmds.fetch_bibtex_by_fulltext_openalex', return_value='@misc{x}') as search:
            self.assertEqual(self.out('fetch Climate sensitivity --openalex').strip(), '@misc{x}')
        search.assert_called_once_with('Climate sensitivity')

    def test_fetch_errors_are_clean(self):
        with mock.patch('papers.openalex.http_get', return_value=FakeResponse(400, {'message': 'query too long'})), \
                mock.patch('papers.openalex._throttle'), mock.patch('papers.config.CACHE_DIR', self.path('cache')):
            with self.assertRaisesRegex(PapersExit, '^OpenAlex: HTTP 400: query too long$'):
                self.lib('fetch Climate sensitivity revisited --openalex')
        with mock.patch('papers.openalex.http_get', side_effect=requests.exceptions.ProxyError('no proxy')), \
                mock.patch('papers.openalex._throttle'), mock.patch('papers.config.CACHE_DIR', self.path('cache')):
            with self.assertRaisesRegex(PapersExit, '^OpenAlex: no proxy$'):
                self.lib('fetch Climate sensitivity revisited --openalex')

    def test_fetch_a_doi_does_not_take_it(self):
        with self.assertRaises(SystemExit):
            self.lib('fetch 10.1000/a --openalex')

    def test_not_with_scholar(self):
        for cmd in ['fetch Climate sensitivity', f'extract {self.path("a.pdf")}', 'add a.pdf']:
            with self.assertRaises(SystemExit):
                self.lib(cmd + ' --scholar --openalex')

    def test_extract(self):
        pdf = self.write('src', 'a.pdf')
        with mock.patch('papers.cli.fetch_cmds.extract_pdf_metadata', return_value='@misc{x}') as extract:
            self.assertEqual(self.out(f'extract {pdf} --openalex').strip(), '@misc{x}')
        self.assertTrue(extract.call_args.kwargs['openalex'])
        self.assertFalse(extract.call_args.kwargs['scholar'])

    def test_add(self):
        pdf = self.write('src', 'a.pdf')
        with mock.patch('papers.bib.extract_pdf_metadata', return_value='@misc{x,\n title = {A title}\n}') as extract:
            self.lib(f'add {pdf} --openalex')
        self.assertTrue(extract.call_args.kwargs['openalex'])
        self.assertFalse(extract.call_args.kwargs['scholar'])

    def test_add_a_directory(self):
        self.write('src', 'a.pdf')
        with mock.patch('papers.bib.extract_pdf_metadata', return_value='@misc{x,\n title = {A title}\n}') as extract:
            self.lib(f'add -R {self.path("src")} --openalex')
        self.assertTrue(extract.call_args.kwargs['openalex'])

    def test_the_default_is_crossref(self):
        pdf = self.write('src', 'a.pdf')
        with mock.patch('papers.cli.fetch_cmds.extract_pdf_metadata', return_value='@misc{x}') as extract:
            self.out(f'extract {pdf}')
        self.assertFalse(extract.call_args.kwargs['openalex'])

    def test_help(self):
        import io
        from contextlib import redirect_stdout
        for cmd in ['add', 'extract', 'fetch']:
            out = io.StringIO()
            with redirect_stdout(out), self.assertRaises(SystemExit):
                self.lib(f'{cmd} --help')
            text = ' '.join(out.getvalue().split())
            self.assertIn('--openalex', text)
            self.assertIn('open API, CC0 data', text)
            self.assertIn('about 100 searches a day', text)
