"""Unit tests for papers.utils (80% -> higher coverage)"""
import os
import tempfile
import unittest

from papers.utils import (
    strip_colors,
    strip_ansi_link,
    strip_all,
    search_config,
    check_filesdir,
    bcolors,
)


class TestStripColors(unittest.TestCase):

    def test_strip_okgreen(self):
        s = f"{bcolors.OKGREEN}green{bcolors.ENDC}"
        self.assertEqual(strip_colors(s), "green")

    def test_strip_bold(self):
        s = f"{bcolors.BOLD}bold{bcolors.ENDC}"
        self.assertEqual(strip_colors(s), "bold")


class TestStripAnsiLink(unittest.TestCase):

    def test_strip_link_keeps_label(self):
        # OSC 8 ; params ; URI ST label OSC 8 ;; ST
        s = "\033]8;;https://example.com\033\\click\033]8;;\033\\"
        result = strip_ansi_link(s)
        self.assertIn("click", result)
        self.assertNotIn("example.com", result)


class TestStripAll(unittest.TestCase):

    def test_strips_both_colors_and_links(self):
        s = f"{bcolors.OKBLUE}\033]8;;url\033\\link\033]8;;\033\\{bcolors.ENDC}"
        result = strip_all(s)
        self.assertEqual(result, "link")


class TestSearchConfig(unittest.TestCase):

    def test_finds_file_in_current_dir(self):
        with tempfile.TemporaryDirectory() as d:
            config_file = os.path.join(d, "config.json")
            open(config_file, 'w').close()
            result = search_config(["config.json"], d)
            self.assertEqual(result, config_file)

    def test_returns_default_when_not_found(self):
        with tempfile.TemporaryDirectory() as d:
            result = search_config(["nonexistent.json"], d, default="/default")
            self.assertEqual(result, "/default")

    def test_searches_parent_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            subdir = os.path.join(d, "sub", "deep")
            os.makedirs(subdir)
            config_file = os.path.join(d, "papersconfig.json")
            open(config_file, 'w').close()
            result = search_config(["papersconfig.json"], subdir)
            self.assertEqual(result, config_file)


class TestCheckFilesdir(unittest.TestCase):

    def test_counts_pdfs(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "a.pdf"), 'wb').write(b"x" * 1000)
            open(os.path.join(d, "b.pdf"), 'wb').write(b"y" * 500)
            open(os.path.join(d, "readme.txt"), 'wb').write(b"text")
            count, size = check_filesdir(d)
            self.assertEqual(count, 2)
            self.assertEqual(size, 1500)
