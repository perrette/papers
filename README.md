[![test](https://github.com/perrette/papers/workflows/CI/badge.svg)](https://github.com/perrette/papers/actions)
[![python](https://img.shields.io/badge/python-3.8-blue.svg)]()
[![python](https://img.shields.io/badge/python-3.9-blue.svg)]()
[![python](https://img.shields.io/badge/python-3.10-blue.svg)]()
[![python](https://img.shields.io/badge/python-3.11-blue.svg)]()

# papers

Command-line tool to manage bibliography (pdfs + bibtex)

> **WARNING**: This tool requires further development and testing, and is not fully production-ready as such (contributors welcome).

## Motivation

This project is an attempt to create a light-weight,
command-line bibliography managenent tool. Aims:

- maintain a PDF library (with appropriate naming)
- maintain one or several bibtex-compatible collections, linked to PDFs
- enough PDF-parsing capability to fetch metadata from the internet (i.e. [crossref](https://github.com/CrossRef/rest-api-doc) or google-scholar)


## Dependencies

- python 3.8+
- [poppler-utils](https://en.wikipedia.org/wiki/Poppler_(software)) (only:`pdftotext`): convert PDF to text for parsing
- [bibtexparser (1.0.1)](https://bibtexparser.readthedocs.io) : parse bibtex files
- [crossrefapi (1.2.0)](https://github.com/fabiobatalha/crossrefapi) : make polite requests to crossref API
- [scholarly (0.2.2)](https://github.com/OrganicIrradiation/scholarly) : interface for google scholar
- [rapidfuzz (0.2.0)](https://github.com/rhasspy/rapidfuzz) : calculate score to sort crossref requests
- [unidecode (0.04.21)](https://github.com/avian2/unidecode) : replace unicode with ascii equivalent

## Install

- `pip install papers-cli`
- install third-party dependencies (Ubuntu: `sudo apt install poppler-utils`)

Note there is another project registered on pypi as papers, hence `papers-cli` for command-line-interface.

## Getting started

This tool's interface is built like `git`, with main command `papers` and a range of subcommands.

### Extract PDF metadata and add to library

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

		$> papers add esd-4-11-2013.pdf --rename --copy --bibtex papers.bib --filesdir files --info
		INFO:papers:found doi:10.5194/esd-4-11-2013
		INFO:papers:new entry: perrette_landerer2013
		INFO:papers:mv /home/perrette/playground/papers/esd-4-11-2013.pdf files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf
		INFO:papers:renamed file(s): 1

(the `--info` argument asks for the above output information to be printed out to the terminal)

That is equivalent to doing:

    papers extract esd-4-11-2013.pdf > entry.bib
    papers add entry.bib --bibtex papers.bib --attachment esd-4-11-2013.pdf --rename --copy

See [Control fields when renaming file](#control-fields-when-renaming-file) for how to specify file naming patterns.

### Add library entry from its DOI

If you already know the DOI of a PDF, and don't want to gamble the fulltext search and match, you can indicate it via `--doi`:

    papers add esd-4-11-2013.pdf --doi 10.5194/esd-4-11-2013 --bibtex papers.bib

The `add` command above also works without any PDF (create a bibtex entry without file attachment).

    papers add --doi 10.5194/esd-4-11-2013 --bibtex papers.bib
    
### List entries (and edit etc...)

    $> papers list -l
    Perrette2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1)

`papers list` is a useful command, inspired from unix's `find` and `grep`.
It lets you search in your bibtex in a typical manner (including a number of special flags such as `--duplicates`, `--review-required`, `--broken-file`...),
then output the result in a number of formats (one-liner, raw bibtex, keys-only, selected fields) or let you perform actions on it (currently `--edit`, `--delete`).
For instance, it is possible to manually merge the duplicates with:

    $> papers list --duplicates --edit


### Control fields when renaming file

        $> papers add --rename --info --name-template "{AuthorX}{year}-{Title}" --name-title-sep '' --name-author-sep '' esd-4-11-2013
        INFO:papers:found doi:10.5194/esd-4-11-2013
        INFO:papers:new entry: perrette2013scaling
        INFO:papers:create directory: files/2013
        INFO:papers:mv /home/perrette/playground/papers/esd-4-11-2013.pdf files/PerretteEtAl2013-AScalingApproachToProjectRegionalSeaLevelRiseAndItsUncertainties.pdf
        INFO:papers:renamed file(s): 1

where '--name-template' is a python template (will be formated via .format() method) with valid fields being any field available in the bibtex. Fields not in the bibtex will remain untouched.

To rename `esd-4-11-2013.pdf` as `perrette_2013.pdf`, the template should be `--name-template {author}_{year} --name-author-num 1`
If that happens to be the entry ID, `ID` also works.

To `rename esd-4-11-2013.pdf` as `2013/Perrette2013-AScalingApproachToProjectRegionalSeaLevelRiseAndItsUncertainties.pdf`,
name-template should be `--name-template {year}/{Author}{year}-{Title} --name-title-sep ''` (note the case).

Entries are case-sensitive, and a few more fields are added, so that:
- 'author' generates 'perrette'
- 'Author' generates 'Perrette'
- 'AUTHOR' generates 'PERRETTE'
- 'authorX' generates 'perrette', 'perrette_and_landerer' or 'perrette_et_al' dependening on the number of authors
- 'AuthorX' same as authorX but capitalized

The modifiers are:

- `--name-title-sep` : separator for title words
- `--name-title-length` : max title length
- `--name-title-word-size` : min size to be considered a word
- `--name-title-word-num` : max number of title words

and similarly:

- `--name-author-sep` : separator for authors
- `--name-author-num` : number of authors to  (not relevant for `{authorX}`)

The same template and modifiers system applies to the bibtex key generation by replacing the prefix `--name-` with `--key-`, e.g. `--key-template`


In the common case where the bibtex (`--bibtex`), files directory  (`--filesdir`), and name and key formats (e.g. `--name-template`) do not change, it is convenient to
(install)[#install-make-bibtex-and-files-directory-persistent] `papers`.
Install comes with the option to git-track any change to the bibtex file (`--git`) options.


### install: make bibtex and files directory persistent

    $> papers install --bibtex papers.bib --filesdir files
    papers configuration
    * configuration file: /home/perrette/.config/papersconfig.json
    * cache directory:    /home/perrette/.cache/papers
    * absolute paths:     True
    * files directory:    files (1 files, 5.8 MB)
    * bibtex:            papers.bib (1 entries)

The configuration file is global (unless `--local` is specified), so from now on, any `papers`
command will know about these settings: no need to specify bibtex file or files directory.

Type `papers status -v` to check your configuration.

You also notice a cache directory. All internet requests such as crossref requests are saved in the cache directory.
This happens regardless of whether `papers` is installed or not.


#### local install

Sometimes it is desirable to have separate configurations. In that case a local install is the way to go:

    $> papers install --local
    Bibtex file name [default to existing: papers.bib] [Enter/Yes/No]:
    Files folder [default to new: papers] [Enter/Yes/No]: pdfs
    papers configuration
    * configuration file: .papers/config.json
    * cache directory:    /home/perrette/.cache/papers
    * absolute paths:     True
    * git-tracked:        False
    * git-lfs tracked:    False
    * files directory:    pdfs (90 files, 337.4 MB)
    * bibtex:             papers.bib (82 entries)


Creates a local configuration file in a hidden `.papers` folder.
By default, it expects existing or creates new `papers.bib` bibliography and `papers` files folder in the local directory, though `papers` will ask first unless explicitly provided.
Note that every call from a subfolder will also detect that configuration file (it has priority over global install).

By default, the local install is meant to be portable with bibtex and files, so the file paths are encoded relatively to the bibtex file.
If instead absolute paths make more sense (example use case: local bibtex file but central PDF folder), then simply specify `--absolute-paths` options:

    `papers install --local --absolute-paths --filesdir /path/to/central/pdfs`


#### uninstall

Getting confused with papers config files scattered in subfolders ? Check the config with

    papers status -v

and remove the configuration file by hand (`rm ...`). Or use `papers uninstall` command:

    papers uninstall

You may repeat `papers status -v` and cleaning until a satistfying state is reached, or remove all config files recursively up to (and including) global install:

    papers uninstall --recursive


### Relative versus Absolute path

By default, the file paths in the bibtex are stored as absolute paths (starting with `/`), except for local installs.
It is possible to change this behavious explicitly during install or in a case by case basis with `--relative-paths` or `--absolute-paths` options.
With or without install.


### Move library to a new location

Moving a library can be tricky.
Simple cases are:
- files are stored in a central repository, and the bibtex contains absolute paths. Then moving the bibtex by hand is fine.
- files are stored alongside the bibtex, and the bibtex contains relative paths. Just move around the folder containing bibtex and files
In any other cases, you risk breaking the file links.

Papers tries to be as little opinionated as possible about how files are organized, and so it relies on your own judgement and use case.
When loading a bibtex, it always inteprete relative file links as being relative to the bibtex file.
When saving a bibtex, it will save file links accordingly to the default setting path (usually absolute, unless local install or unless you specify otherwise).

In any case, the following set of commands will always work provided the initial file links are valid (optional parameters in brackets):

    touch new.bib
    papers add /path/to/old.bib --bib new.bib [ --rename ] [ --relative-paths ] [ --filesdir newfilesdir ]
    rm -f /path/to/old.bib


### check

It's easy to end up with duplicates in your bibtex. After adding PDFs, or every once in a while, do:

    papers check --duplicates


### filecheck

Check for broken links, rename files etc. Example:

    papers filecheck --rename

The command can be used to move around the file directory:

    papers filecheck --rename --filesdir newfilesdir

That command is also convenient to check on what's actually tracked and what is not. Example workflow

    papers filecheck --rename --filesdir tmp
    # check what's left over in your initial files directory, e.g.
    # papers extract files/leftover1.pdf
    # papers add files/leftover1.pdf
    # ...
    papers filecheck --rename --filesdir files


### Setup git-tracked library (optional)

    Install comes with the option to git-track any change to the bibtex file (`--git`) options.

    $> papers install --bibtex papers.bib --filesdir files --git

From now on, every change to the library will result in an automatic git commit.
And `papers git ...` command will work just as `git ...` executed from the bibtex directory.
E.g. `papers git add origin *REMOTE URL*`; `papers git lfs track files`; `papers git add files`; `papers git push`
Note this is an experimental feature at this stage, with potential for improvement.

This probably makes more sense for a global install (local installs usually have their own git tracking system).


### undo

Did a `papers add` and are unhappy with the result?

    papers undo

will revert to the previous version. If repeated, it will jump back and forth between latest and before-latest.

Better to git-track your bibliography to go back deeper into history.


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


Feature ideas (TODO: organize as issues for discussion)
-------------
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
