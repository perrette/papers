# Quickstart

`papers` works like `git`: a main command with subcommands, run inside a
folder that holds a library. A library is a bibtex file, its PDFs, and a
small configuration file `.papersconfig.json`.

This page shows three ways to use it:

- [A. One library](#a-one-library): a bibtex file and its PDFs in one folder.
- [B. Projects that share one PDF folder](#b-projects-that-share-one-pdf-folder):
  each project has its own bibtex, and all PDFs are kept in
  `~/Documents/papers` (the default).
- [C. A new project from earlier work](#c-a-new-project-from-earlier-work):
  take entries from the shared folder or from another project.

The examples use two papers of the Copernicus journals, whose PDFs contain
their DOI. `papers` reads the DOI from the PDF and fetches the bibtex entry
from crossref.

## Install

```
pip install --pre papers-cli
```

`--pre` installs the 3.0 beta. Python 3.11 or later is needed. See
[Installation](installation.md) for other ways to install.

## A. One library

Create a library whose PDFs stay in the folder itself:

```
$ cd ~/thesis
$ papers init --local
created the library ~/thesis
* bibtex:  papers.bib
* files:   files (the files directory of the library)
* backup:  git
`papers status -v` shows all settings
```

Add a PDF. It is moved into `files/` and renamed after the entry:

```
$ papers add ~/Downloads/esd-4-11-2013.pdf
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1)
$ ls files
perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf
```

Add an entry from its DOI, without a PDF:

```
$ papers add --doi 10.5194/bg-8-515-2011
Added -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011)
```

Attach another file to an entry, such as a supplement:

```
$ papers file attach perrette_landerer2013 ~/Downloads/esd-4-11-2013-supplement.pdf
Modified -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, files:2)
$ ls files
perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties--esd-4-11-2013-supplement.pdf
perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf
```

List and search:

```
$ papers list
perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, files:2)
perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011)
$ papers list -a yool
perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011)
```

Every change to the bibtex is recorded in a git repository of its own (when
git is installed), so `papers undo` takes back the last change.

`--move` is the default for the PDFs given to `add`; `--copy` keeps the
original too (a hard link when possible), and `--link` leaves the file where
it is. See [Adding entries](adding-entries.md), [Files](files.md) and
[Listing and searching](listing.md).

## B. Projects that share one PDF folder

Without `--local`, the PDFs of a library go to one shared folder, the global
pool, `~/Documents/papers`. Each project keeps its own bibtex, with only the
papers it cites, and links to the PDFs in the pool:

```
$ cd ~/projects/sea-level
$ papers init
created the library ~/projects/sea-level
* bibtex:  papers.bib
* files:   in the pool ~/Documents/papers
* backup:  git
`papers status -v` shows all settings
```

The pool is created the first time a file goes there. `add` puts the PDF in
the pool and the entry in both bibtex files:

```
$ papers add ~/Downloads/esd-4-11-2013.pdf
added: perrette_landerer2013 (pool ~/Documents/papers)
push to pool ~/Documents/papers: 1 added
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1)
$ ls ~/Documents/papers/files
perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf
$ grep "file =" papers.bib
 file = {:../../Documents/papers/files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf:pdf},
```

When another project adds the same paper, it is found in the pool: nothing
is fetched online, and the PDF is not copied again.

```
$ cd ~/projects/new-paper
$ papers init
$ papers add --doi 10.5194/esd-4-11-2013
found in pool ~/Documents/papers: perrette_landerer2013
push to pool ~/Documents/papers: 1 unchanged
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1)
```

The pool is an ordinary library: `papers -C ~/Documents/papers list` lists
all your papers.

To keep the PDFs in the project instead, for example when the project
folder is shared with coauthors (git, Dropbox), use `papers init --local`,
or later `papers config local true`, which copies the project's PDFs from
the pool. See [Pools](pools.md).

## C. A new project from earlier work

Take entries from the pool by key (or DOI):

```
$ cd ~/projects/new-paper
$ papers pull perrette_yool2011
added: perrette_yool2011 (pool ~/Documents/papers)
pull: 1 added
Added -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011)
```

Or take all the entries of another project:

```
$ cd ~/projects/review
$ papers init
$ papers pull --pool ../sea-level --all
```

The entries taken with `pull` stay linked to their source. A correction
made in one project and sent to the pool with `papers push` reaches the
other projects with `papers pull`:

```
$ cd ~/projects/sea-level
$ papers tag perrette_yool2011 --add arctic
$ papers push
updated: perrette_yool2011 (pool ~/Documents/papers)
push to pool ~/Documents/papers: 1 unchanged, 1 updated

$ cd ~/projects/new-paper
$ papers status
[...]
* pool:               ~/Documents/papers (global pool, changed since last pull or push)
$ papers pull
updated: perrette_yool2011 (pool ~/Documents/papers)
pull: 1 unchanged, 1 updated
```

`papers sync` runs `pull`, then `push`. Each project keeps its own keys:
`pull` and `push` never rename the entries of the library they write to.

## Settings

`papers config` shows and changes the settings of the library, and
`papers config --global` the defaults for all libraries of your user
account. For example, to keep the shared folder elsewhere:

```
$ papers config --global pool /data/papers
```

or to never use a shared folder:

```
$ papers config --global pool none
```

See [Configuration](configuration.md). Users of papers 2.x: see
[Upgrading from v2](upgrading.md).
