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

Start with PDF of your choice (modern enough to have a DOI, e.g. anything from the Copernicus publications). 
For the sake of the example, one of my owns: https://www.earth-syst-dynam.net/4/11/2013/esd-4-11-2013.pdf

- parse doi

        myref doi esd-4-11-2013.pdf
    
        10.5194/esd-4-11-2013
    
- fetch bibtex based on doi

        myref fetch 10.5194/esd-4-11-2013
        
    output:
    
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

        myref add --rename esd-4-11-2013.pdf
        
    output:
    
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


Consult inline help for more detailed documentation!
