[![test](https://github.com/perrette/papers/workflows/CI/badge.svg)](https://github.com/perrette/papers/actions)
[![python](https://img.shields.io/badge/python-3.8-blue.svg)]()
[![python](https://img.shields.io/badge/python-3.9-blue.svg)]()
[![python](https://img.shields.io/badge/python-3.10-blue.svg)]()

# papers

Command-line tool to manage bibliography (pdfs + bibtex)

> **WARNING**: This tool requires further development and testing, and is not production-ready as such (contributors welcome).

Motivation
----------
This project is an attempt to create a light-weight,
command-line bibliography managenent tool. Aims:

- maintain a PDF library (with appropriate naming)
- maintain one or several bibtex-compatible collections, linked to PDFs
- enough PDF-parsing capability to fetch metadata from the internet (i.e. [crossref](https://github.com/CrossRef/rest-api-doc) or google-scholar)


Dependencies
------------
- python 3.8+
- [poppler-utils](https://en.wikipedia.org/wiki/Poppler_(software)) (only:`pdftotext`): convert PDF to text for parsing
- [bibtexparser (1.0.1)](https://bibtexparser.readthedocs.io) : parse bibtex files
- [crossrefapi (1.2.0)](https://github.com/fabiobatalha/crossrefapi) : make polite requests to crossref API
- [scholarly (0.2.2)](https://github.com/OrganicIrradiation/scholarly) : interface for google scholar
- [rapidfuzz (0.2.0)](https://github.com/rhasspy/rapidfuzz) : calculate score to sort crossref requests
- [unidecode (0.04.21)](https://github.com/avian2/unidecode) : replace unicode with ascii equivalent

Install
-------
- `pip install papers-cli`
- install third-party dependencies (Ubuntu: `sudo apt install poppler-utils`)

Note there is another project registered on pypi as papers, hence `papers-cli` for command-line-interface.

Getting started
---------------
This tool's interface is built like `git`, with main command `papers` and a range of subcommands.

Start with PDF of your choice (modern enough to have a DOI, e.g. anything from the Copernicus publications).
For the sake of the example, one of my owns: https://www.earth-syst-dynam.net/4/11/2013/esd-4-11-2013.pdf

- extract pdf metadata (doi-based if available, otherwise crossref, or google scholar if so specified)

        $> papers extract esd-4-11-2013.pdf
        @article{Perrette_2013,
            doi = {10.5194/esd-4-11-2013},
            url = {https://doi.org/10.5194%2Fesd-4-11-2013},
            year = 2013,
            month = {jan},
            publisher = {Copernicus {GmbH}},
            volume = {4},
            number = {1},
            pages = {11--29},
            author = {M. Perrette and F. Landerer and R. Riva and K. Frieler and M. Meinshausen},
            title = {A scaling approach to project regional sea level rise and its uncertainties},
            journal = {Earth System Dynamics}
        }

- add pdf to `papers.bib`  library, and rename a copy of it in a files directory `files`.

        $> papers add --rename --copy --bibtex papers.bib --filesdir files esd-4-11-2013.pdf --info
    	INFO:papers:found doi:10.5194/esd-4-11-2013
    	INFO:papers:new entry: perrette_2013
    	INFO:papers:create directory: files/2013
    	INFO:papers:mv /home/perrette/playground/papers/esd-4-11-2013.pdf files/2013/Perrette_2013.pdf
    	INFO:papers:renamed file(s): 1

(the `--info` argument asks for the above output information to be printed out to the terminal)

In the common case where the bibtex (`--bibtex`) and files directory  (`--filesdir`) do not change,
it is convenient to *install* `papers`.
Install comes with the option to git-track any change to the bibtex file (`--git`) options.

- setup git-tracked library (optional)

        $> papers install --bibtex papers.bib --filesdir files --git --gitdir ./
        papers configuration
        * configuration file: /home/perrette/.config/papersconfig.json
        * cache directory:    /home/perrette/.cache/papers
        * git-tracked:        True
        * git directory :     ./
        * files directory:    files (1 files, 5.8 MB)
        * bibtex:            papers.bib (1 entries)

Note the existing bibtex file was detected but untouched.
The configuration file is global (unless `--local` is specified), so from now on, any `papers`
command will know about these settings. Type `papers status -v` to check your
configuration.
You also notice that crossref requests are saved in the cache directory.
This happens regardless of whether `papers` is installed or not.
From now on, no need to specify bibtex file or files directory.

- list entries (and edit etc...)

        $> papers list -l
        Perrette2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1)

`papers list` is a useful command, inspired from unix's `find` and `grep`.
It lets you search in your bibtex in a typical manner (including a number of special flags such as `--duplicates`, `--review-required`, `--broken-file`...),
then output the result in a number of formats (one-liner, raw bibtex, keys-only, selected fields) or let you perform actions on it (currently `--edit`, `--delete`).
For instance, it is possible to manually merge the duplicates with:

        $> papers list --duplicates --edit


- other commands:

    - `papers status ...`
    - `papers check ...`
    - `papers filecheck ...`
    - `papers undo ...`
    - `papers git ...`

Consult inline help for more detailed documentation!


Current features
----------------
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
- undo command (`papers undo`)
- configuration file with default bibtex and files directory (`papers install --bibtex BIB --filesdir DIR ...`)
- integration with git (`papers install --git --gitdir DIR` and e.g. `papers git ...` to setup a remote, push...)
- display / search / list entries : format as bibtex or key or whatever (`papers list ... [-k | -l]`)
- list + edit or remove entry by key or else  (`papers list ... [--edit, --delete]`)
- fix broken PDF links (`papers filecheck ...`):
    - remove duplicate file names (always) or file copies (`--hash-check`)
    - remove missing link (`--delete-missing`)
    - fix files name after a Mendeley export (`--fix-mendeley`):
        - leading '/' missing is added
        - latex characters, e.g. `{\_}` or `{\'{e}}` replaced with unicode


Planned features
----------------
- `papers encode`: text encoding in bibtex entries (latex, unicode, ascii)
- additional checks on entries:
    - duplicate-authors and more like [here](https://github.com/tdegeus/bibparse)
- support collections (distinct bibtex entries, same files directory)
    - or maybe more like ´papers update-from OTHER.bib´ to update changes based on DOI / key
    - could also use git branches / merge
- associate bibtex to existing pdf collection (to move library location)
- fetch PDFs for existing entries? Bindings with [sopaper](https://github.com/ppwwyyxx/SoPaper)
- lazy loading of modules (optimization)


Tests
-----
Test coverage in progress...

Currently covers:
- `papers extract`
    - parse pdf DOI
    - fetch bibtex on crossref based on DOI
    - fetch bibtex on crossref based fulltext search
    - fetch bibtex on google-scholar based fulltext search
- `papers add`
    - add entry and manage conflict
    - add pdf file, bibtex, directory
    - add one pdf file with attachment (beta, API will change)
- `papers check --duplicates`
    - conflict resolution
- `papers install` (superficial test)
- internals:
    - duplicate test with levels `EXACT`, `GOOD`, `FAIR` (the default), `PARTIAL`


Todo (more bug prone until then !):
- `papers check` (fix DOI etc.)
- `papers filecheck` (especially rename files, including those with attachment)
- `papers list`
- `papers status`
- `papers install` (extend)
- `papers undo`
- `papers git`


Why not JabRef, Zotero or Mendeley (or...) ?
--------------------------------------------
- JabRef (2.10) is nice, light-weight, but is not so good at managing PDFs.
- Zotero (5.0) features excellent PDF import capability, but it needs to be manually one by one and is a little slow. Not very flexible.
- Mendeley (1.17) is perfect at automatically extracting metadata from downloaded PDF and managing your PDF library,
but it is not open source, and many issues remain (own experience, Ubuntu 14.04, Desktop Version 1.17):
    - very unstable
    - PDF automatic naming is too verbose, and sometimes the behaviour is unexpected (some PDFs remain in on obscure Downloaded folder, instead of in the main collection)
    - somewhat heavy (it offers functions of online syncing, etc)
    - poor seach capability (related to the point above)

Above-mentioned issues will with no doubt be improved in future releases, but they are a starting point for this project.
Anyway, a command-line tool is per se a good idea for faster development,
as noted [here](https://forums.zotero.org/discussion/43386/zotero-cli-version),
but so far I could only find zotero clients for their online API
(like [pyzotero](https://github.com/urschrei/pyzotero) or [zotero-cli](https://github.com/jbaiter/zotero-cli)).
Please contact me if you know another interesting project.
