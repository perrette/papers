#!/usr/bin/env python3
"""Check the DOI extraction of papers against a library.

Each entry with a DOI and a PDF says which DOI should be found in that PDF.
The script runs the extraction of `papers extract --doi-only` on the first
PDF of each such entry and compares:

- ok: the DOI of the entry was found;
- different: another DOI was found;
- none: no DOI was found;
- unreadable: the PDF could not be read.

The DOI comes either from the PDF metadata (no network query) or from the
text, where each candidate is checked against its title on crossref (cached
after the first run). Nothing is written to the library.

Usage:
  python scripts/doi_benchmark.py [LIBRARY] [--metadata-only] [--workers N] [--csv FILE]
"""
import argparse
import csv
import logging
import os
import sys
from collections import Counter

from papers import logger
from papers.entries import get_entry_val
from papers.extract import extract_pdf_doi, parse_doi_from_pdf_metadata, prefetch_pdf_metadata
from papers.identifiers import normalize_doi
from papers.library import find_config, get_biblio

OUTCOMES = ['ok', 'different', 'none', 'unreadable']


def cases(biblio):
    "(key, expected DOI, PDF) for each entry with a DOI and a PDF"
    for e in biblio.entries:
        doi = normalize_doi(get_entry_val(e, 'doi', ''))
        pdfs = [f for f in biblio.get_files(e) if f.lower().endswith('.pdf') and os.path.isfile(f)]
        if doi and pdfs:
            yield get_entry_val(e, 'ID', ''), doi, pdfs[0]


def check(key, expected, pdf, metadata_only=False):
    "the result row of one PDF"
    row = dict(key=key, expected=expected, found='', source='', outcome='none', file=pdf)
    try:
        found = parse_doi_from_pdf_metadata(pdf)
        if found:
            row['source'] = 'metadata'
        elif not metadata_only:
            row['source'] = 'text'
            found = extract_pdf_doi(pdf)
    except ValueError:  # no DOI in the text (DOIParsingError)
        found = None
    except Exception as error:
        row['outcome'], row['found'] = 'unreadable', str(error)
        return row
    if found:
        row['found'] = found
        row['outcome'] = 'ok' if normalize_doi(found) == expected else 'different'
    return row


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('library', nargs='?', default='.',
                        help='the folder of the library (default: the library of the current folder, or the default library)')
    parser.add_argument('--metadata-only', action='store_true',
                        help='only read the PDF metadata: no text parsing, no network query')
    parser.add_argument('--workers', type=int, default=3,
                        help='crossref requests at a time, to fill the cache before the check (default: 3)')
    parser.add_argument('--csv', help='write one row per PDF to this file')
    parser.add_argument('-v', '--verbose', action='store_true', help='print the PDFs that fail')
    o = parser.parse_args(args)

    config = find_config(o.library)
    if config.bibtex is None:
        parser.error(f'no library found in {o.library}')
    todo = list(cases(get_biblio(config)))
    print(f'{config.bibtex}: {len(todo)} entries with a DOI and a PDF', file=sys.stderr)

    level = logger.level
    logger.setLevel(logging.CRITICAL)  # the extraction warns on each failure
    try:
        if not o.metadata_only:
            # the crossref queries of the PDFs without DOI in their metadata, concurrently
            pdfs = [pdf for _, _, pdf in todo if not _metadata_doi(pdf)]
            print(f'query crossref for {len(pdfs)} PDFs without DOI in their metadata', file=sys.stderr)
            prefetch_pdf_metadata(pdfs, workers=o.workers, search_fulltext=False)
        rows = [check(*case, metadata_only=o.metadata_only) for case in todo]
    finally:
        logger.setLevel(level)

    report(rows, metadata_only=o.metadata_only)
    if o.verbose:
        for row in rows:
            if row['outcome'] != 'ok':
                print(f"{row['outcome']:10s} {row['key']}: expected {row['expected']}, found {row['found'] or '-'} ({row['file']})")
    if o.csv:
        with open(o.csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ['key'])
            writer.writeheader()
            writer.writerows(rows)


def _metadata_doi(pdf):
    try:
        return parse_doi_from_pdf_metadata(pdf)
    except Exception:
        return None


def report(rows, metadata_only=False):
    "the outcomes by source of the DOI"
    counts = Counter((row['source'] or '-', row['outcome']) for row in rows)
    sources = ['metadata', '-'] if metadata_only else ['metadata', 'text', '-']
    print(f"{'source':10s}" + ''.join(f'{x:>12s}' for x in OUTCOMES + ['total']))
    for source in sources:
        n = [counts[source, x] for x in OUTCOMES]
        if sum(n):
            print(f'{source:10s}' + ''.join(f'{x:12d}' for x in n + [sum(n)]))
    n = [sum(counts[s, x] for s in sources) for x in OUTCOMES]
    print(f"{'all':10s}" + ''.join(f'{x:12d}' for x in n + [sum(n)]))
    if rows:
        print(f"success: {100 * n[0] / len(rows):.0f}%")


if __name__ == '__main__':
    main()
