# Quickstart

`papers` works like `git`: one command with subcommands, run inside a
folder that holds a library. A library is a bibtex file and a small
configuration file, `.papersconfig.json`. By default the PDFs of all your
libraries are kept in one folder, `~/Documents/papers`, called the pool, so
that a paper used in several projects is stored once.

The examples below use two papers of the Copernicus journals, whose PDFs
contain their DOI: `papers` reads the DOI from the PDF and fetches the
bibtex entry from crossref.

## Install

```
pip install --pre papers-cli
```

`--pre` installs the 3.0 beta. Python 3.11 or later is needed. See
[Installation](installation.md) for other ways to install.

## Create a library

Run `papers init` in the folder of your project:

```
$ cd ~/projects/sea-level
$ papers init
created the library ~/projects/sea-level
* bibtex:  papers.bib
* files:   in the pool ~/Documents/papers
* backup:  git
`papers status -v` shows all settings
```

Commands run in this folder, or below it, use this library.

## Add papers

Add a PDF. It is moved to the pool and renamed after the entry, and the
entry is added to the bibtex of the project and to the pool's own bibtex
(the pool is created the first time):

```
$ papers add ~/Downloads/esd-4-11-2013.pdf
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1) [also added to pool ~/Documents/papers]
$ ls ~/Documents/papers/files
perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf
$ grep "file =" papers.bib
 file = {:../../Documents/papers/files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf:pdf},
```

Add an entry from its DOI, without a PDF:

```
$ papers add --doi 10.5194/bg-8-515-2011
Added -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011) [also added to pool ~/Documents/papers]
```

Attach another file to an entry, such as a supplement. It is named after
the entry, with its original name as a label:

```
$ papers file attach perrette_landerer2013 ~/Downloads/esd-4-11-2013-supplement.pdf
Modified -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, files:2) [also modified in pool ~/Documents/papers]
$ ls ~/Documents/papers/files
perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties--esd-4-11-2013-supplement.pdf
perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf
```

`add` also takes a bibtex file (`papers add refs.bib`), a folder of PDFs
(`papers add -R ~/Downloads/papers/`), or fields given by hand. See
[Adding entries](adding-entries.md) and [Files](files.md).

## List and search

```
$ papers list
perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, files:2)
perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011)
$ papers list -a yool
perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011)
```

`papers list --format bibtex` prints the entries as bibtex, and
`papers list -K` prints their keys only, to pass them to another command
(`papers list -a yool -K | papers file rename -`). See
[Listing and searching](listing.md).

## Undo

Every change to the bibtex is recorded in a git repository of its own, so
`papers undo` takes back the last change of the library (when git is
installed). It acts on this library only: the pool keeps what was added to
it. See [Git integration](git.md).

## A second project

In another project, a paper that is already in the pool is taken from it:
nothing is fetched online, and the PDF is not stored twice.

```
$ cd ~/projects/new-paper
$ papers init
$ papers add --doi 10.5194/esd-4-11-2013
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, files:2) [from pool ~/Documents/papers]
```

Take entries from the pool by key (or DOI) with `pull`:

```
$ papers pull perrette_yool2011
Added -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011) [from pool ~/Documents/papers]
```

or all the entries of an earlier project:

```
$ cd ~/projects/review
$ papers init
$ papers pull --pool ../sea-level --all
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, files:2) [from pool ../sea-level]
Added -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011) [from pool ../sea-level]
pull from pool ../sea-level: 2 added
```

The pool is an ordinary library: `papers -C ~/Documents/papers list` lists
all your papers.

## Keep projects up to date

The entries taken from the pool stay linked to it. A correction made in one
project is sent to the pool with `papers push`, and reaches the other
projects with `papers pull`:

```
$ cd ~/projects/sea-level
$ papers tag perrette_yool2011 --add arctic
Modified -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, arctic)
$ papers push
Modified -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, arctic) [in pool ~/Documents/papers]
push to pool ~/Documents/papers: 1 unchanged, 1 updated

$ cd ~/projects/new-paper
$ papers status
[...]
* pool:               ~/Documents/papers (global pool, changed since last pull or push)
$ papers pull
Modified -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, arctic) [from pool ~/Documents/papers]
pull from pool ~/Documents/papers: 1 unchanged, 1 updated
```

`papers sync` runs `pull`, then `push`. Nothing is exchanged without these
commands, except that `add` adds new papers to the pool. Each project keeps
its own keys: `pull` and `push` never rename the entries of the library
they write to. See [Pools](pools.md).

## Keep the PDFs in the project

With `--local`, a library keeps its PDFs in its own `files/` folder, for
example when the project folder is shared with coauthors (git, Dropbox):
the links of a library that uses the pool point to your own
`~/Documents/papers`, which they do not have.

```
$ cd ~/thesis
$ papers init --local
created the library ~/thesis
* bibtex:  papers.bib
* files:   files (the files directory of the library)
* backup:  git
`papers status -v` shows all settings
```

A local library still uses the pool for entries: `add` looks there first,
and `pull` and `push` work as above; only the PDFs are copied into the
project (as hard links when they are on the same disk, which takes no
space). `papers config local true` turns an existing library into a local
one, and copies its PDFs:

```
$ cd ~/projects/new-paper
$ papers config local true
copy 2 files of the pool into files (hard links when possible), and link to the copies (the pool keeps its files):
  perrette_landerer2013: ~/Documents/papers/files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf
  perrette_landerer2013: ~/Documents/papers/files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties--esd-4-11-2013-supplement.pdf
Continue? [y/N] y
Modified -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, files:2)
local = true (in ~/projects/new-paper/.papersconfig.json)
```

`papers init --pool none` creates a library without any pool: its PDFs are
in the project, and nothing is shared.

## Settings

`papers config` shows and changes the settings of the library, and
`papers config --global` the defaults of your user account. For example,
to keep the pool elsewhere:

```
$ papers config --global pool /data/papers
```

or to use no pool at all:

```
$ papers config --global pool none
```

See [Configuration](configuration.md).
