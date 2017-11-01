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
- JabRef is nice, light-weight, but is not so good as managing PDFs.
- Mendeley is perfect at extracting metadata from PDF and managing your PDF library, 
but many issues remain (own experience, Ubuntu 14.04, Desktop Version 1.17):
    - very unstable
    - PDF renaming is too verbose, and sometimes the behaviour is unexpected (some PDFs remain in on obscure Downloaded folder, instead of in the main collection)
    - somewhat heavy (it offers many functions of online syncing, etc)
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

    usage: myref [-h] {add,doi,fetch} ...

    library management tool

    positional arguments:
      {add,doi,fetch}

    optional arguments:
      -h, --help  show this help message and exit


- `myref doi`: parse DOI from PDF

    usage: myref doi [-h] [--space-digit] pdf

    optional arguments:
      --space-digit  space digit fix


- `myref fetch` : fetch bibtex from DOI

    usage: myref fetch [-h] doi


- `myref add`: Add a PDF to bibliography:

    - read bibtex file if any, otherwise create new bibtex lib
    - extract DOI from PDF
    - fetch bibtex entry via [crossref API](https://github.com/CrossRef/rest-api-doc/issues/115#issuecomment-221821473)
    - create entry if not already present
    - link PDF and attachments to the enrty (`file` field)
    - rename files if required
        - in the case of multiple files, a folder named after the key is created, and all associated files are copied into it, without further renaming.

    
Example:

        myref add -r myfile.pdf


Usage:

    usage: myref add [-h] [--bibtex BIBTEX] [--filesdir FILESDIR]
                     [-a ATTACHMENTS [ATTACHMENTS ...]] [-r] [-o]
                     pdf

    add PDF to library

    positional arguments:
      pdf

    optional arguments:
      -h, --help            show this help message and exit
      --bibtex BIBTEX       myref.bib
      --filesdir FILESDIR   files
      -a ATTACHMENTS [ATTACHMENTS ...], --attachments ATTACHMENTS [ATTACHMENTS ...]
                            supplementary material
      -r, --rename          rename PDFs according to key
      -o, --overwrite       if the entry already exists, overwrite any existing
                            files instead of appending

