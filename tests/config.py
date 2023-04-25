import unittest
import os, subprocess as sp
import tempfile, shutil
import difflib
from pathlib import Path

from papers.extract import extract_pdf_metadata
from papers.bib import Biblio, bibtexparser, parse_file, format_file
from tests.download import downloadpdf

# Using python -m papers instead of papers otherwise pytest --cov does not detect the call
PAPERSCMD = f'python3 -m papers'

def paperscmd(cmd, sp_cmd="check_output"):
    return run(f'{PAPERSCMD} '+cmd, sp_cmd=sp_cmd)

def run(cmd, sp_cmd="check_output"):
    print(cmd)
    if sp_cmd == "check_output":
        return str(sp.check_output(cmd, shell=True).strip().decode())
    else:
        return str(getattr(sp, sp_cmd)(cmd, shell=True))