# Features

## Current features

- parse PDF to extract DOI
- fetch bibtex entry from DOI (using crossref API)
- fetch bibtex entry by fulltext search (using crossref API or google scholar)
- create and maintain bibtex file
- add entry as PDF (`papers add ...`)
- add entry as bibtex (`papers add ...`)
- scan directory for PDFs (`papers add ...`)
- rename PDFs according to bibtex key and year (`papers filecheck --rename [--copy]`)
- some support for attachment
- merging (`papers check --duplicates ...`)
- fix entries (`papers check --format-name --encoding unicode --fix-doi --fix-key ...`)
- configuration file with default bibtex and files directory (`papers install --bibtex BIB --filesdir DIR ...`)
- integration with git
- undo/redo command (`papers undo / redo`)
- display / search / list entries: format as bibtex or key or whatever (`papers list ... [--key-only, -l]`)
- list + edit or remove entry by key or else (`papers list ... [--edit, --delete]`)
- fix broken PDF links (`papers filecheck ...`):
    - remove duplicate file names (always) or file copies (`--hash-check`)
    - remove missing link (`--delete-missing`)
    - fix files name after a Mendeley export (`--fix-mendeley`):
        - leading `/` missing is added
        - latex characters, e.g. `{\_}` or `{\'{e}}` replaced with unicode

## Tests

Test coverage is improving (now 80%).

Currently covers:

- `papers extract` (test on a handful of PDFs)
    - parse pdf DOI
    - fetch bibtex on crossref based on DOI
    - fetch bibtex on crossref based on fulltext search
    - fetch bibtex on google-scholar based on fulltext search
- `papers add`
    - add entry and manage conflict
    - add pdf file, bibtex, directory
    - add one pdf file with attachment (beta, API will change)
    - conflict resolution
- `papers install`
- internals:
    - duplicate test with levels `EXACT`, `GOOD`, `FAIR` (the default), `PARTIAL`
- `papers list`
- `papers undo / redo` (partial)
- `papers filecheck --rename` (superficial)
- `papers check --duplicate` (fix DOI etc.) (superficial)
