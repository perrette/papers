# Quickstart

`papers` works like `git`: one command with subcommands, run inside a
project folder that holds a library. A library is a bibtex file, a
configuration file (`.papers/config.json`) and, if it keeps its own PDFs, a
`files/` folder.

This page shows two cases: a self-contained project, with its own bibtex
and PDFs, and a shallow project that uses the first one as its pool.

## Install

The 3.0 beta is published on PyPI as a pre-release:

```
pip install --pre papers-cli
```

See [Installation](installation.md) for the requirements.

## 1. A self-contained project

`papers init` creates a self-contained library: its own entries, and its
own PDFs in `files/`.

```
$ cd ~/projects/sealevel
$ papers init
created the library ~/projects/sealevel
* bibtex:  papers.bib
* files:   files (the files directory of the library)
* backup:  git
`papers status -v` shows all settings
$ papers add ~/Downloads/esd-4-11-2013.pdf
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1)
$ papers add --doi 10.1111/j.1365-246X.1978.tb04232.x
Added -> bretreger_mather1978: Modelling ocean-loading effects on tidal gravity in Australi... (doi:10.1111/j.1365-246X.1978.tb04232.x)
```

The DOI is read from the PDF, the entry is fetched from crossref, and the
PDF is moved to `files/` and renamed after the entry.

A self-contained library is also a library that other projects can use.

## 2. A shallow project that uses it

`papers init --pool PATH` creates a shallow library: it takes its entries
from the library `PATH`, its pool, and links to the PDFs there. `PATH` is
a self-contained library, such as the project above, or a library kept for
sharing, e.g. `~/Documents/papers` (see
[A global shared library](global-library.md)).

```
$ cd ~/projects/tides
$ papers init --pool ../sealevel
created the library ~/projects/tides
* bibtex:  papers.bib
* files:   in the pool (shallow library)
* pool:    ../sealevel
* backup:  git
`papers status -v` shows all settings
$ papers add --doi 10.5194/esd-4-11-2013
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1) [from pool ../sealevel]
$ papers add ~/Downloads/bg-8-515-2011.pdf
Added -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, file:1) [also added to pool ../sealevel]
```

`add` looks in the pool first: a paper the pool has is taken from it, with
its PDF, and nothing is fetched or copied. A new paper goes to the library
and to the pool, and its PDF to the pool's `files/`. Each library has only
the entries it asks for: `tides` has two entries, `sealevel` three.

Changes to the shared entries, made in either project, are exchanged with
`papers sync`. After a tag added in `sealevel`:

```
$ papers sync
Modified -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1, sea-level) [from pool ../sealevel]
```

## More

- [Adding entries](adding-entries.md): PDFs, DOIs, bibtex files, duplicates;
- [Files](files.md): attachments, renaming, moving;
- [Listing and searching](listing.md);
- [Pools](pools.md): `pull`, `push`, `sync` and the merge, exchanges with
  any library (`--pool PATH`);
- [Shallow libraries](shallow-libraries.md): files, changing the pool,
  auto-push, topic libraries, and a comparison with a shared files folder;
- [Export](export.md): a library to hand over.

Coming from papers 2: see [Upgrading from papers 2](upgrading.md).
