"""Unit tests of papers.library: legacy configuration files, get_biblio,
savebib"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import papers.config
import papers.library
from papers.config import Config, CONFIG_FILE_LOCAL
from papers.library import check_legacy_global_config, get_biblio, savebib


class TmpTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.realpath(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, *p):
        return os.path.join(self.dir, *p)


class TestLegacyConfig(TmpTest):

    def patch(self, legacy, current):
        return mock.patch.multiple(papers.library, CONFIG_FILE_LEGACY=legacy, CONFIG_FILE_LEGACY_XDG=self.path('none'),
                                   CONFIG_FILE=current)

    def test_global_config_is_moved(self):
        Path(self.path('legacy.json')).write_text('{}')
        with self.patch(self.path('legacy.json'), self.path('new', 'config.json')), \
                self.assertLogs('papers', level='WARNING'):
            check_legacy_global_config()
        self.assertTrue(os.path.exists(self.path('new', 'config.json')))
        self.assertFalse(os.path.exists(self.path('legacy.json')))

    def test_both_exist(self):
        Path(self.path('legacy.json')).write_text('{}')
        Path(self.path('config.json')).write_text('{}')
        with self.patch(self.path('legacy.json'), self.path('config.json')), \
                self.assertLogs('papers', level='WARNING') as logs:
            check_legacy_global_config()
        self.assertIn('Delete to remove this warning', logs.output[0])
        self.assertTrue(os.path.exists(self.path('legacy.json')))

    # .papers/config.json as papers v2.2 to v2.4 wrote it (`papers install
    # --local`): paths relative to the library directory, the parent of
    # .papers (v2 read them against Path(file).parent.parent), and the
    # backup directory .papers itself
    V2_DOT_PAPERS = ('{"absolute_paths": false, "backup_files": false, "bibtex": "papers.bib", '
                     '"editor": null, "filesdir": "files", "git": true, "gitdir": ".papers", '
                     '"gitlfs": false, "local": true}')

    def v2_library(self):
        os.makedirs(self.path('lib', '.papers'))
        Path(self.path('lib', '.papers', 'config.json')).write_text(self.V2_DOT_PAPERS)
        return self.path('lib', '.papers', 'config.json')

    def assert_v2_paths(self, config):
        self.assertEqual(config.bibtex, self.path('lib', 'papers.bib'))
        self.assertEqual(config.filesdir, self.path('lib', 'files'))
        self.assertEqual(str(config.configdir), self.path('lib'))

    def test_v2_dot_papers_read_in_place(self):
        # used to resolve the paths against .papers/
        config = Config.load(self.v2_library(), machine=papers.config.MachineConfig())
        self.assert_v2_paths(config)

    def test_v2_dot_papers_found_in_place(self):
        self.v2_library()
        with mock.patch.object(papers.library, 'CONFIG_FILE', self.path('none.json')):
            config = papers.library.find_config(self.path('lib'), machine=papers.config.MachineConfig())
        self.assertEqual(config.file, self.path('lib', '.papers', 'config.json'))
        self.assert_v2_paths(config)

    def test_v2_dot_papers_saved_in_place(self):
        config = Config.load(self.v2_library(), machine=papers.config.MachineConfig())
        config.save()
        self.assert_v2_paths(Config.load(config.file, machine=papers.config.MachineConfig()))


class TestGetBiblio(TmpTest):

    def test_no_bibtex(self):
        with self.assertRaises(ValueError):
            get_biblio(Config())

    def test_creates_bibtex(self):
        config = Config(bibtex=self.path('sub', 'papers.bib'), filesdir=self.path('files'))
        biblio = get_biblio(config)
        self.assertEqual(biblio.entries, [])
        self.assertTrue(os.path.exists(self.path('sub', 'papers.bib')))

    def test_pool_link_repair_failure_is_a_warning(self):
        Path(self.path('papers.bib')).write_text('')
        config = Config(file=self.path(CONFIG_FILE_LOCAL), bibtex=self.path('papers.bib'),
                        filesdir=self.path('files'), pool=self.path('pool'))  # a shallow library
        with mock.patch('papers.pools.Exchange', side_effect=RuntimeError('broken pool')), \
                self.assertLogs('papers', level='WARNING') as logs:
            get_biblio(config)
        self.assertIn('broken pool', logs.output[0])

    def test_absolute_links_made_relative(self):
        # paths relative: an absolute link is rewritten at load, in memory
        abspath = self.path('files', 'a.pdf')
        text = '@article{a,\n file = {:%s:pdf},\n title = {A}\n}\n' % abspath
        Path(self.path('papers.bib')).write_text(text)
        biblio = get_biblio(Config(bibtex=self.path('papers.bib'), filesdir=self.path('files')))
        self.assertEqual(biblio.entries[0]['file'], ':' + os.path.join('files', 'a.pdf') + ':pdf')
        self.assertTrue(biblio.load_changes)
        self.assertEqual(Path(self.path('papers.bib')).read_text(), text)

    def test_relative_links_left_alone(self):
        Path(self.path('papers.bib')).write_text('@article{a,\n file = {files/a.pdf:PDF},\n title = {A}\n}\n')
        biblio = get_biblio(Config(bibtex=self.path('papers.bib'), filesdir=self.path('files')))
        self.assertEqual(biblio.entries[0]['file'], 'files/a.pdf:PDF')
        self.assertFalse(biblio.load_changes)

    def test_link_on_another_drive_stays_absolute(self):
        from papers.entries import format_file
        with mock.patch('os.path.relpath', side_effect=ValueError('path is on mount C:, start on mount D:')):
            self.assertEqual(format_file([self.path('a.pdf')], relative_to=self.dir), ':' + self.path('a.pdf') + ':pdf')


class TestSavebib(TmpTest):

    def test_dry_run(self):
        config = Config(bibtex=self.path('papers.bib'))
        biblio = mock.Mock()
        papers.config.DRYRUN = True
        try:
            savebib(biblio, config)
        finally:
            papers.config.DRYRUN = False
        biblio.save.assert_not_called()

    def test_history_failure_keeps_the_save(self):
        config = Config(bibtex=self.path('papers.bib'))
        biblio = mock.Mock()
        with mock.patch('papers.backup.record', side_effect=OSError('disk full')), \
                self.assertLogs('papers', level='ERROR') as logs:
            savebib(biblio, config)
        biblio.save.assert_called_once_with(config.bibtex)
        self.assertIn('its history failed: disk full', logs.output[-1])
