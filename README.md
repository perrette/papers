![travis](https://travis-ci.org/perrette/myref.svg?branch=master)
[![Coverage Status](https://coveralls.io/repos/github/perrette/myref/badge.svg?branch=master)](https://coveralls.io/github/perrette/myref?branch=master)
# myref

Command-line tool to manage bibliography (pdfs + bibtex)


Motivation
----------
This project is an attempt to create a light-weight, 
command-line bibliography managenent tool. Aims:

- maintain a PDF library (with appropriate naming)
- maintain one or several bibtex-compatible collections, linked to PDFs
- some PDF-parsing capability (especially to extract DOI)
- fetch PDF metadata from the internet (i.e. [crossref](https://github.com/CrossRef/rest-api-doc)), preferably based on DOI


Why not JabRef or Mendeley?
--------------------------
- JabRef is nice, light-weight, but is not so good at managing PDFs.
- Mendeley is perfect at extracting metadata from PDF and managing your PDF library, 
but many issues remain (own experience, Ubuntu 14.04, Desktop Version 1.17):
    - very unstable
    - PDF automatic naming is too verbose, and sometimes the behaviour is unexpected (some PDFs remain in on obscure Downloaded folder, instead of in the main collection)
    - somewhat heavy (it offers functions of online syncing, etc)
    - poor seach capability (related to the point above)

Above-mentioned issues will with no doubt be improved in future releases, but they are a starting point for this project.


Internals
---------
For now (very much beta version), the project:
- manages one `bibtex` collection, maintained sorted according to entry keys
- [bibtexparser](https://bibtexparser.readthedocs.io/en/v0.6.2) is used to parse bibtexentries and libraries
- each entry (and associated keys) is obtained from [crossref API](https://github.com/CrossRef/rest-api-doc/issues/115#issuecomment-221821473) (note: the feature that allows to fetch a bibtex entry from DOI is undocumented...). So far it seems that the keys are unique, until seen otherwise...
- DOI is extracted from PDFs with regular expression search within the first two pages.


Dependencies
------------
- python 2 or 3
- `pdftotext` (third-party): convert PDF to text
    - Tested with v0.41
    - Natively installed on Ubuntu 14.04 (?). Part of poppler-utils.

- [bibtexparser](https://bibtexparser.readthedocs.io/en/v0.6.2)
    - pip install bibtexparser


Install
-------
- clone this project
- python setup.py install


Getting started
---------------
This tool's interface is built like `git`, with main command `myref` and a range of subcommands.

Start with PDF of your choice (modern enough to have a DOI, e.g. anything from the Copernicus publications). 
For the sake of the example, one of my owns: https://www.earth-syst-dynam.net/4/11/2013/esd-4-11-2013.pdf

- parse doi

        $> myref doi esd-4-11-2013.pdf    
        10.5194/esd-4-11-2013
    
- fetch bibtex based on doi

        $> myref fetch 10.5194/esd-4-11-2013
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

- add pdf to library

        $> myref add --rename esd-4-11-2013.pdf
        INFO:root:found doi:10.5194/esd-4-11-2013
        INFO:root:NEW ENTRY: perrette_2013
        INFO:root:mv esd-4-11-2013.pdf files/2013/Perrette_2013.pdf

    
In the above case, the sequence of actions is:
- read bibtex file if any, otherwise create new bibtex lib
- extract DOI from PDF
- fetch bibtex entry via [crossref API](https://github.com/CrossRef/rest-api-doc/issues/115#issuecomment-221821473)
- create entry if not already present
- link PDF and attachments to the enrty (`file` field)
- rename files if required
    - in the case of multiple files, a folder named after the key is created, and all associated files are copied into it, without further renaming.


- other commands: 

    - `myref filter ...` 
    - `myref merge ...` 
    - `myref undo ...` 

Consult inline help for more detailed documentation!


Current features
----------------
- parse PDF to extract DOI
- fetch bibtex entry from DOI (using crossref API)
- create and maintain bibtex file
- add entry as PDF
- add entry as bibtex
- scan directory for PDFs
- rename PDFs according to bibtex key and year
- some support for attachment
- display / search / filter entries : format as bibtex or key or whatever
- merging / update
- undo command
- global configuration file with default bibtex and files directory


Planned features
----------------
Mostly related to bibliography management:
- add manual entry 
- remove entry by key
- move library location (i.e. both on disk and in bibtex's `file` entry)
- fix broken PDF links
- better handling of attachment / multiple files
- key generation (especially for new entry addition)
- git saving of bibtex

As well as:
- parse other info (author name, year) from PDF, especially for old papers
    - maybe worthwhile to look into crossref's parser written in Ruby
- fetch bibtex from alternative info (author name, year...), especially for old papers
    - this is currently possible with the standard crossref API (and nice python package [crossrefapi](https://github.com/fabiobatalha/crossrefapi)), but the result is `json`    - not sure how to convert the json result `into` a `bibtex` file in the general case
    - for recent papers with DOI, a second request can be made, as workaround, but this feature is mostly inteded for old papers without DOI.

And some new, original features:
- integration with git (such as `pass` does)


All this in a set of planned commands:
- `myref new (-k KEY | --auto-key) [--no-check] --author NAME --year YEAR [--file FILE [FILE...]] ...` : manually add one new entry (for the sake of completeness) 
- `myref link -k KEY [--no-check] [--overwrite] FILE [FILE...]` : add one or several file to *existing* entry, without any check on the files beyond existence
- `myref filecheck [--fix] [--rename] [--remove-broken] [--searchdir DIR [DIR...]] [--doi-check] ...` : perform check on bibtex file link (test broken, rename, re-link from other sources, remove broken, remove duplicate names, check that doi matches...)
- `myref config ...` : show/change global configuration options (default bibtex, filesdir, caching of DOI requests)
- `myref git ...` : any git command from myref's git repository


Suggestions welcomed for prioritizing / feature suggestion.
