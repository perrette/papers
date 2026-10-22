"""Unit tests of papers.library: legacy configuration files, get_biblio,
savebib"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import papers.config
import papers.library
from papers.config import Config
from papers.library import check_legacy_config, check_legacy_global_config, get_biblio, savebib


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

    def test_library_config_in_dot_papers(self):
        os.makedirs(self.path('lib', '.papers'))
        Path(self.path('lib', '.papers', 'config.json')).write_text('{}')
        new = check_legacy_config(self.path('lib', '.papers', 'config.json'))
        self.assertEqual(new, self.path('lib', '.papersconfig.json'))
        self.assertTrue(os.path.exists(new))

    def test_missing_file_is_returned_as_is(self):
        self.assertEqual(check_legacy_config(self.path('none.json')), self.path('none.json'))


class TestGetBiblio(TmpTest):

    def test_no_bibtex(self):
        with self.assertRaises(ValueError):
            get_biblio(Config())

    def test_creates_bibtex(self):
        config = Config(bibtex=self.path('sub', 'papers.bib'), filesdir=self.path('files'))
        biblio = get_biblio(config)
        self.assertEqual(biblio.entries, [])
        self.assertTrue(os.path.exists(self.path('sub', 'papers.bib')))

    def test_light_library_repair_failure_is_a_warning(self):
        Path(self.path('papers.bib')).write_text('')
        config = Config(bibtex=self.path('papers.bib'), filesdir=self.path('files'))
        config.light = True
        with mock.patch('papers.pools.Exchange', side_effect=RuntimeError('broken pool')), \
                self.assertLogs('papers', level='WARNING') as logs:
            get_biblio(config)
        self.assertIn('broken pool', logs.output[0])


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

    def test_backup_failure_keeps_the_save(self):
        config = Config(bibtex=self.path('papers.bib'), git=True)
        biblio = mock.Mock()
        with mock.patch('papers.library.silent_backup_bib', side_effect=OSError('no git')), \
                self.assertLogs('papers', level='ERROR') as logs:
            savebib(biblio, config)
        biblio.save.assert_called_once_with(config.bibtex)
        self.assertIn('its git backup failed: no git', logs.output[0])
