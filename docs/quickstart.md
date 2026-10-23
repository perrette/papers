# Quickstart

`papers` works like `git`: one command with subcommands, run inside a
project folder that holds a library. A library is a bibtex file, a
configuration file (`.papersconfig.json`) and, if it keeps its own PDFs, a
`files/` folder.

This page follows one story:

1. a project with its own bibtex and PDFs;
2. its papers moved to a pool, a shared library for one topic;
3. a second project that uses the same pool.

The examples use papers of the Copernicus journals, whose PDFs contain
their DOI: `papers` reads the DOI from the PDF and fetches the bibtex entry
from crossref.

## Install

The 3.0 beta is not on PyPI yet. Install it from the `v3` branch:

```
pip install git+https://github.com/perrette/papers.git@v3
```

Python 3.11 or later is needed. `pip install papers-cli` installs papers 2.
See [Installation](installation.md) for the external dependencies.

## 1. A self-contained project

`papers init --local` creates a library that keeps its own PDFs, in
`files/`, and exchanges nothing with other libraries:

```
$ cd ~/projects/sealevel
$ papers init --local
created the library ~/projects/sealevel
* bibtex:  papers.bib
* files:   files (the files directory of the library)
* backup:  git
`papers status -v` shows all settings
```

Commands run in this folder, or below it, use this library.

Add a PDF. Its DOI is read from the PDF, the entry is fetched, and the PDF
is moved to `files/` and renamed after the entry:

```
$ papers add ~/Downloads/esd-4-11-2013.pdf
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1)
```

Attach another file to the entry, such as a supplement. It is named after
the entry, with its original name as a label:

```
$ papers file attach perrette_landerer2013 ~/Downloads/esd-4-11-2013-supplement.pdf
Modified -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, files:2)
$ ls files
perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties--esd-4-11-2013-supplement.pdf
perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf
```

Add an entry from its DOI, without a PDF:

```
$ papers add --doi 10.1111/j.1365-246X.1978.tb04232.x
Added -> bretreger_mather1978: Modelling ocean-loading effects on tidal gravity in Australi... (doi:10.1111/j.1365-246X.1978.tb04232.x)
```

`add` also takes a bibtex file (`papers add refs.bib`), a folder of PDFs
(`papers add -R ~/Downloads/papers/`), or fields given by hand. See
[Adding entries](adding-entries.md) and [Files](files.md).

List and search:

```
$ papers list
bretreger_mather1978: Modelling ocean-loading effects on tidal gravity in Australi... (doi:10.1111/j.1365-246X.1978.tb04232.x)
perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, files:2)
$ papers list -a perrette
perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, files:2)
$ papers list perrette_landerer2013 --format bibtex
@article{perrette_landerer2013,
 author = {Perrette, M. and Landerer, F. and Riva, R. and Frieler, K. and Meinshausen, M.},
 doi = {10.5194/esd-4-11-2013},
 file = {:files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf:pdf;:files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties--esd-4-11-2013-supplement.pdf:pdf},
 journal = {Earth System Dynamics},
 number = {1},
 pages = {11-29},
 title = {A scaling approach to project regional sea level rise and its uncertainties},
 url = {https://doi.org/10.5194/esd-4-11-2013},
 volume = {4},
 year = {2013}
}
```

`papers list -K` prints the keys only, to pass them to another command
(`papers list -a yool -K | papers file rename -`). See
[Listing and searching](listing.md).

Every change to the bibtex is recorded in a git repository of its own:
`papers undo` takes back the last change, and `papers redo` restores it.
See [Undo and redo](undo-redo.md).

## 2. Sharing it through a pool

A pool is a library in a shared location: a bibtex and a folder of PDFs.
Other libraries take entries and PDFs from it, and send theirs to it. Here
the pool is `~/Documents/papers/sealevel`, one pool for the sea level
papers.

Set the pool of the library, and send all its entries to it:

```
$ papers config pool ~/Documents/papers/sealevel
pool = ~/Documents/papers/sealevel (in ~/projects/sealevel/.papersconfig.json)
$ papers push --all
create the library ~/Documents/papers/sealevel
Added -> bretreger_mather1978: Modelling ocean-loading effects on tidal gravity in Australi... (doi:10.1111/j.1365-246X.1978.tb04232.x) [to pool ~/Documents/papers/sealevel]
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, files:2) [to pool ~/Documents/papers/sealevel]
push to pool ~/Documents/papers/sealevel: 2 added
$ ls ~/Documents/papers/sealevel/files
perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties--esd-4-11-2013-supplement.pdf
perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf
```

`push` creates the pool if it does not exist (its parent folder must
exist). The PDFs are copied to the pool, as hard links when possible. The
library still has its own copies.

To keep only the pool's copies, set `local` to `false`. The library then
links to the PDFs of the pool, and its own copies are deleted. papers lists
what it will do and asks first (`-y` does not ask):

```
$ papers config local false
link to the copies in the pool ~/Documents/papers/sealevel for 2 files (same content); the library's copies in files (2 files) are deleted
(`papers config local false --dry-run` lists each file)
Continue? [y/N] y
Modified -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, files:2)
local = false (in ~/projects/sealevel/.papersconfig.json)
delete ~/projects/sealevel/files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf (hard link: the other links remain)
delete ~/projects/sealevel/files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties--esd-4-11-2013-supplement.pdf (hard link: the other links remain)
$ grep "file =" papers.bib
 file = {:../../Documents/papers/sealevel/files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf:pdf;:../../Documents/papers/sealevel/files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties--esd-4-11-2013-supplement.pdf:pdf},
```

`config local false` refuses as long as an entry has a PDF that the pool
entry does not have: it lists the keys, and the `papers push KEY...`
command that copies them. A project folder shared with coauthors (git,
Dropbox) should stay local, since the links of a library that is not local
point into your own pool. See [Local or not](pools.md#local-or-not) and
[Changing `local` and `pool`](pools.md#changing-local-and-pool).

## 3. A new project that uses the pool

```
$ cd ~/projects/tides
$ papers init --pool ~/Documents/papers/sealevel
created the library ~/projects/tides
* bibtex:  papers.bib
* files:   in the pool ~/Documents/papers/sealevel
* backup:  git
`papers status -v` shows all settings
```

This library is not local: its PDFs are in the pool. `add` looks in the
pool first. A paper that the pool has is taken from it, with its PDFs:
nothing is fetched and nothing is copied. A new paper goes to the library
and to the pool, and its PDF to the pool's `files/`:

```
$ papers add --doi 10.5194/esd-4-11-2013
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, files:2) [from pool ~/Documents/papers/sealevel]
$ papers add ~/Downloads/bg-8-515-2011.pdf
Added -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, file:1) [also added to pool ~/Documents/papers/sealevel]
```

The pool is an ordinary library:

```
$ papers -C ~/Documents/papers/sealevel list
bretreger_mather1978: Modelling ocean-loading effects on tidal gravity in Australi... (doi:10.1111/j.1365-246X.1978.tb04232.x)
perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, files:2)
perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, file:1)
```

Each library has the entries it asks for. The first project does not get
the new paper until it pulls it (`papers status` there shows the pool as
`changed since last pull or push`):

```
$ cd ~/projects/sealevel
$ papers pull perrette_yool2011
Added -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, file:1) [from pool ~/Documents/papers/sealevel]
```

## Keeping libraries in sync

The entries taken from the pool, or sent to it, are shared with it.
`papers sync` sends the changes of the shared entries to the pool and
brings the changes of the pool into the library. A tag added in one
project reaches the other:

```
$ cd ~/projects/sealevel
$ papers tag perrette_yool2011 --add arctic
Modified -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, file:1, arctic)
$ papers sync
pull from pool ~/Documents/papers/sealevel: 3 unchanged
Modified -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, file:1, arctic) [in pool ~/Documents/papers/sealevel]
push to pool ~/Documents/papers/sealevel: 2 unchanged, 1 modified

$ cd ~/projects/tides
$ papers sync
Modified -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, file:1, arctic) [from pool ~/Documents/papers/sealevel]
pull from pool ~/Documents/papers/sealevel: 1 unchanged, 1 modified
push to pool ~/Documents/papers/sealevel: 2 unchanged
$ papers sync
nothing to sync with pool ~/Documents/papers/sealevel (2 entries unchanged)
```

The merge is field by field, against the version of the last exchange:
a field changed on one side only is taken from that side, and a field
changed on both sides is a conflict that you decide. Each library keeps its
own keys. `papers pull` and `papers push` do each half of `sync`; with KEY
or `--all` they also add entries that the other side does not have. Nothing
is exchanged without these commands, except that `add` sends new papers to
the pool in a library that is not local, and the `auto-push` setting sends
the changes of each command (see [Auto-push](pools.md#auto-push)). See
[Pools](pools.md).

## Exchanging with a coauthor once

`--pool PATH` exchanges entries once with another library, such as a
folder shared with a coauthor. It reads and writes only that library, and
the entries exchanged are not shared with it afterwards. A KEY that only
that library has is added to yours; a KEY that only yours has is sent to
it, with copies of its PDFs:

```
$ papers sync --pool ../shared-with-bob agnew_farrell1978
Added -> agnew_farrell1978: Self-consistent equilibrium ocean tides (doi:10.1111/j.1365-246X.1978.tb04755.x) [from pool ../shared-with-bob]
push to pool ../shared-with-bob: 1 unchanged
$ papers sync --pool ../shared-with-bob perrette_yool2011
Added -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, file:1, arctic) [to pool ../shared-with-bob]
```

Without KEY, nothing is exchanged with that library; `--all` exchanges
everything once. See [One-time exchanges](pools.md#one-time-exchanges).

## Other setups

- `papers init` (no option) uses the global pool, `~/Documents/papers`,
  and is not local: the PDFs of all such projects are in
  `~/Documents/papers/files`.
- `papers init --local --pool PATH` keeps its own PDFs and exchanges entries
  with the pool `PATH`.
- Several libraries without a pool can share one PDF folder, as in papers 2
  (see [A shared files folder without a pool](pools.md#a-shared-files-folder-without-a-pool)).

Coming from papers 2: see [Upgrading from papers 2](upgrading.md).
