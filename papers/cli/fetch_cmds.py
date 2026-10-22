"""papers fetch, extract, and doi (deprecated) (no library needed)"""
import os
from pathlib import Path

from papers import logger
from papers.extract import extract_pdf_doi, extract_pdf_metadata
from papers.fetch import fetch_bibtex_by_doi, fetch_bibtex_by_fulltext_crossref, fetch_bibtex_by_fulltext_scholar
from papers.identifiers import strip_doi
from papers.utils import PapersExit


def doicmd(parser, o, config):
    logger.warning('`papers doi` is deprecated: use `papers extract --doi-only`')
    try:
        print(extract_pdf_doi(o.pdf, image=o.image))
    except ValueError as error:
        raise PapersExit(f'{o.pdf}: {error}')


def fetchcmd(parser, o, config):
    # either one or several DOIs
    dois = [strip_doi(field) for field in o.doi_or_text]  # the case of arXiv ids matters
    if all(dois):
        if o.scholar:
            parser.error("Fetching from DOI does not support Google Scholar option")
        for doi in dois:
            print(fetch_bibtex_by_doi(doi))
        return

    # or one full text search
    field = " ".join(o.doi_or_text)
    if o.scholar:
        print(fetch_bibtex_by_fulltext_scholar(field))
    else:
        print(fetch_bibtex_by_fulltext_crossref(field))


def _collect_pdf_files(paths, recursive=False):
    """Expand the extract arguments into a list of PDF files.

    Plain files are taken as given; directories require `recursive` and are
    scanned for PDF files (case-insensitively).
    """
    files = []
    for path in paths:
        if os.path.isdir(path):
            if not recursive:
                raise ValueError(f'{path} is a directory, requires -R/--recursive to scan')
            files.extend(sorted(str(p) for p in Path(path).rglob('*')
                                if p.is_file() and p.suffix.lower() == '.pdf'))
        else:
            files.append(path)
    return files


def extractcmd(parser, o, config):
    try:
        files = _collect_pdf_files(o.pdf, recursive=o.recursive)
    except ValueError as error:
        parser.error(str(error))
    if not files:
        logger.warning('no PDF file found')
        return
    failed = 0
    for file in files:
        if len(files) > 1:
            print(f'% {file}')
        try:
            if not os.path.isfile(file):
                raise ValueError('no such file' if not os.path.exists(file) else 'not a file')
            if o.doi_only:
                print(extract_pdf_doi(file, image=o.image))
                continue
            print(extract_pdf_metadata(file, search_doi=not o.fulltext, search_fulltext=True, scholar=o.scholar, minwords=o.word_count, max_query_words=o.word_count, image=o.image))
        except ValueError as error:  # DOIParsingError among them: no DOI or metadata found
            if len(files) == 1:
                raise PapersExit(f'{file}: {error}')
            logger.error(f'{file}: {error}')
            failed += 1
        except Exception as error:
            if len(files) == 1:
                raise
            logger.error(f'{file}: {error}')
            failed += 1
    if failed:
        raise PapersExit(f'{failed} of {len(files)} files failed')
