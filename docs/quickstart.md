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
installed), and `papers redo` restores it:

```
$ papers undo
undo: papers.bib restored to 7f9ad3e papers add --doi 10.5194/bg-8-515-2011 (2026-10-22 15:37)
$ papers redo
redo: papers.bib restored to 55b0a37 papers file attach perrette_landerer2013 /home/you/Downloads/esd-4-11-2013-supplement.pdf (2026-10-22 15:37)
```

The pool is a library with its own git history: `papers undo` in a project
undoes only the project, and `papers -C ~/Documents/papers undo` undoes a
change in the pool. See [Undo and redo](undo-redo.md) and
[Undo in a pool](pools.md#undo-in-a-pool).

## A second project

In another project, `add --doi` or `add --key` finds a paper that is already
in the pool: nothing is fetched online, and the PDF is not stored twice.

```
$ cd ~/projects/new-paper
$ papers init
$ papers add --doi 10.5194/esd-4-11-2013
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, files:2) [from pool ~/Documents/papers]
$ papers add --key perrette_yool2011
Added -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011) [from pool ~/Documents/papers]
```

The pool is an ordinary library: `papers -C ~/Documents/papers list` lists
all your papers.

## Keep libraries in sync

The entries taken from the pool stay linked to it. `papers sync` sends the
changes of the library to the pool and brings the changes of the pool into
the library. A tag added in the first project reaches the second one:

```
$ cd ~/projects/sea-level
$ papers tag perrette_yool2011 --add arctic
Modified -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, arctic)
$ papers sync
pull from pool ~/Documents/papers: 2 unchanged
Modified -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, arctic) [in pool ~/Documents/papers]
push to pool ~/Documents/papers: 1 unchanged, 1 updated

$ cd ~/projects/new-paper
$ papers sync
Modified -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, arctic) [from pool ~/Documents/papers]
pull from pool ~/Documents/papers: 1 unchanged, 1 updated
push to pool ~/Documents/papers: 2 unchanged
```

`papers sync --pool PATH` syncs with another library instead, such as a
folder shared with a coauthor. It reads and writes only that library, not
the global pool. A KEY that only that library has is added, and the entry
links to the PDF of that library (in a library that is not local, as
here):

```
$ papers sync --pool ../shared-with-bob agnew_farrell1978
Added -> agnew_farrell1978: Self-consistent equilibrium ocean tides (file:1) [from pool ../shared-with-bob]
push to pool ../shared-with-bob: 1 unchanged
```

Without KEY, all the entries of the library are synced: the ones the other
library does not have are added to it, with copies of their PDFs.

Nothing is exchanged without these commands, except that `add` adds new
papers to the pool. Each library keeps its own keys. `papers pull` and
`papers push` do each half of `sync`, and `papers status` tells whether the
pool changed since the last exchange: see [Pools](pools.md).

## Where the PDFs are

By default the PDFs of all your libraries are in the pool,
`~/Documents/papers`, and the bibtex of each library links to them there
(`papers config --global pool PATH` moves the default pool elsewhere). A
project folder shared with others (git, Dropbox) should keep its own PDFs,
in its `files/` folder: create it with `papers init --local`, or run
`papers config local true` in an existing library, which copies its PDFs
from the pool (as hard links when possible). A local library still uses
the pool for entries. `papers init --pool none` creates a library without
pool: its PDFs are in the project, and nothing is shared. See
[Pools](configuration.md#pools) in the configuration, and
[Local or not](pools.md#local-or-not) and
[Changing `local` and `pool`](pools.md#changing-local-and-pool) in the Pools
guide.
