"""papers fetch, extract, and doi (deprecated) (no library needed)"""
import os
import shutil
from pathlib import Path

import papers.utils
from papers import freepdf, logger
from papers.extract import extract_pdf_doi, extract_pdf_metadata
from papers.fetch import DOIRequestError, fetch_bibtex_by_doi, fetch_bibtex_by_fulltext_crossref, fetch_bibtex_by_fulltext_scholar
from papers.openalex import fetch_bibtex_by_fulltext_openalex
from papers.identifiers import normalize_arxiv, strip_doi
from papers.utils import PapersExit


def doicmd(parser, o, config):
    logger.warning('`papers doi` is deprecated: use `papers extract --doi-only`')
    try:
        print(extract_pdf_doi(o.pdf, image=o.image))
    except ValueError as error:
        raise PapersExit(f'{o.pdf}: {error}')


def _pdf_name(found, doi, arxiv):
    """the file name of `papers fetch --pdf`: that of the URL when it looks
    like the paper's (a digit in it), else made of the DOI or arXiv id"""
    name = os.path.basename(found.path)
    if any(c.isdigit() for c in os.path.splitext(name)[0]):
        return name
    return (doi or arxiv).replace('/', '_') + '.pdf'


def fetch_pdfs(parser, o):
    """papers fetch --pdf: download the free PDF of DOIs or arXiv ids (see papers.freepdf).
    With --porcelain, the lines of each argument (formats.md 7.2): `downloaded ID VERSION URL FILE`
    and a `refused-published ID URL` per published link refused before it, or a `refused ID URL`
    per link to open in a browser, or `failed ID` when there is none"""
    if o.scholar or o.openalex:
        parser.error('--pdf does not take --scholar or --openalex')
    if o.output and len(o.doi_or_text) > 1:
        parser.error('-o/--output FILE takes one DOI')
    porcelain = papers.utils.PORCELAIN

    def lines(*lines):
        if porcelain is not None:
            for line in lines:
                print(line, file=porcelain)
    failed = 0
    for arg in o.doi_or_text:
        doi = strip_doi(arg)
        arxiv = None if doi else normalize_arxiv(arg)
        try:
            if not doi and not arxiv:
                raise ValueError('not a DOI or arXiv id')
            found = freepdf.fetch_pdf(freepdf.Search(doi, arxiv, o.least_version))
            target = o.output or _pdf_name(found, doi, arxiv)
            if os.path.isdir(target):
                target = os.path.join(target, _pdf_name(found, doi, arxiv))
            if os.path.exists(target):
                freepdf.discard(found.path)
                raise ValueError(f'{target} exists: not replaced (-o FILE writes another file)')
            shutil.move(found.path, target)
            freepdf.discard(found.path)
        except ValueError as error:  # NoPDF among them
            links = getattr(error, 'links', [])
            lines(*([f'refused {arg} {url}' for url in links] or [f'failed {arg}']))
            if len(o.doi_or_text) == 1:
                raise PapersExit(f'{arg}: {error}')
            logger.error(f'{arg}: {error}')
            failed += 1
            continue
        print(f'{target} ({found.describe()})')
        lines(f'downloaded {arg} {found.link.version} {found.link.url} {target}',
              *[f'refused-published {arg} {url}' for url in found.refused])
    if failed:
        raise PapersExit(f'{failed} of {len(o.doi_or_text)} PDFs not downloaded')


def fetchcmd(parser, o, config):
    if o.pdf:
        return fetch_pdfs(parser, o)
    if o.output or o.least_version != 'any':
        parser.error('-o/--output and --version go with --pdf')
    # either one or several DOIs
    dois = [strip_doi(field) for field in o.doi_or_text]  # the case of arXiv ids matters
    if all(dois):
        if o.scholar or o.openalex:
            parser.error("Fetching from DOI does not support the options --scholar and --openalex")
        for doi in dois:
            try:
                print(fetch_bibtex_by_doi(doi))
            except DOIRequestError as error:  # its message names the DOI
                raise PapersExit(str(error)) from error
            except OSError as error:  # network error
                raise PapersExit(f'{doi}: {error}') from error
        return

    # or one full text search
    field = " ".join(o.doi_or_text)
    try:
        if o.scholar:
            print(fetch_bibtex_by_fulltext_scholar(field))
        elif o.openalex:
            print(fetch_bibtex_by_fulltext_openalex(field))
        else:
            print(fetch_bibtex_by_fulltext_crossref(field))
    except (ValueError, OSError) as error:  # no result, network error
        raise PapersExit(str(error)) from error


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
            print(extract_pdf_metadata(file, search_doi=not o.fulltext, search_fulltext=True, scholar=o.scholar, openalex=o.openalex, minwords=o.word_count, max_query_words=o.word_count, image=o.image))
        except ValueError as error:  # DOIParsingError among them: no DOI or metadata found
            if len(files) == 1:
                raise PapersExit(f'{file}: {error}')
            logger.error(f'{file}: {error}')
            failed += 1
        except Exception as error:  # e.g. not a PDF, network error
            if len(files) == 1:
                raise PapersExit(f'{file}: {error}') from error
            logger.error(f'{file}: {error}')
            failed += 1
    if failed:
        raise PapersExit(f'{failed} of {len(files)} files failed')
