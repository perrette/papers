# Features

## Current features

- parse PDF to extract DOI
- fetch bibtex entry from DOI (using crossref API, or doi.org for DOIs registered elsewhere, e.g. DataCite)
- fetch bibtex entry by fulltext search (using crossref API or google scholar)
- create and maintain bibtex file
- add entry as PDF (`papers add ...`)
- add entry as bibtex (`papers add ...`)
- scan directory for PDFs (`papers add ...`)
- move, copy or link the added PDFs into a files directory (`files` setting, `papers add --move/--copy/--link`)
- rename PDFs according to bibtex key and year (`papers file rename [--keep-source]`)
- move files and folders and update the links (`papers file mv`)
- attachments (e.g. supplementary material), named after the main file (`papers add ... --attach FILE`, `papers file attach KEY FILE`)
- duplicate detection by DOI, arXiv id, ISBN or authors and title, and merging (`papers add`, `papers check --duplicates`)
- fix entries (`papers check --format-name --encoding unicode --fix-doi --fix-key ...`)
- library configuration with its bibtex, files directory and settings (`papers init --bibtex BIB --filesdir DIR ...`, `papers config`)
- integration with git
- undo/redo command (`papers undo / redo`)
- display / search / list entries: format as bibtex or key or whatever (`papers list ... --format line|bibtex|key`, or `-l`, `--plain`, `-K`)
- edit, remove and tag entries by key or DOI, or from a pipe (`papers edit`, `papers rm`, `papers tag`, `papers list ... -K | papers rm -`)
- check and fix file links (`papers file check`, `papers file fix`, `papers file detach --broken`, `papers file clean`):
    - report broken links, files linked twice and identical files
    - remove duplicate links (`papers file fix`)
    - fix files name after a Mendeley export (`papers file fix`):
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
    - add one pdf file with attachments
    - conflict resolution
- `papers init`, `papers config` (including the file moves of `pool`), `papers migrate`, `papers install`
- `papers pull`, `papers push`, `papers sync`, `papers export` (pools)
- internals:
    - duplicate rule (identifiers and their order, title guard, `.papers/distinct.json`), merge and dialogue
- `papers list`
- `papers undo / redo` (partial)
- `papers file` subcommands, `papers rm`, `papers tag`, `papers edit`
- `papers check --duplicates` and the other checks (fix DOI etc.) (superficial)
