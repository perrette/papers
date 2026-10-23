# Quickstart

`papers` works like `git`: one command with subcommands, run inside a
project folder that holds a library. A library is a bibtex file, a
configuration file (`.papersconfig.json`) and, if it keeps its own PDFs, a
`files/` folder.

This page shows a common use case: a project with its own bibtex and PDFs,
whose papers are then shared through a pool with a second project. It is
also the way from a papers 2 project library to papers 3.

## Install

The 3.0 beta is not on PyPI yet. Install it from the `v3` branch:

```
pip install git+https://github.com/perrette/papers.git@v3
```

See [Installation](installation.md) for the requirements.

## 1. A project with its own PDFs

`papers init --local` creates a library that keeps its own PDFs, in
`files/`, and has no pool:

```
$ cd ~/projects/sealevel
$ papers init --local
$ papers add ~/Downloads/esd-4-11-2013.pdf
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1)
$ papers add --doi 10.1111/j.1365-246X.1978.tb04232.x
Added -> bretreger_mather1978: Modelling ocean-loading effects on tidal gravity in Australi... (doi:10.1111/j.1365-246X.1978.tb04232.x)
```

The DOI is read from the PDF, the entry is fetched from crossref, and the
PDF is moved to `files/` and renamed after the entry.

For more: [Adding entries](adding-entries.md), [Files](files.md)
(attachments, renaming, moving), [Listing and searching](listing.md),
[Undo and redo](undo-redo.md).

## 2. Sharing its papers through a pool

A pool is a library in a shared location: a bibtex and a folder of PDFs.
Here it is `~/Documents/papers/sealevel`, a pool for the sea level papers.
Declare it, and send all entries to it:

```
$ papers config pool ~/Documents/papers/sealevel
$ papers push --all
create the library ~/Documents/papers/sealevel
Added -> bretreger_mather1978: Modelling ocean-loading effects on tidal gravity in Australi... (doi:10.1111/j.1365-246X.1978.tb04232.x) [to pool ~/Documents/papers/sealevel]
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1) [to pool ~/Documents/papers/sealevel]
push to pool ~/Documents/papers/sealevel: 2 added
```

The pool now has the entries and a copy of the PDFs. To keep only the
pool's copies, set `local` to `false`: the library links to the PDFs of the
pool, and its own copies are deleted (papers asks first). This step is
optional; a project folder shared with coauthors should stay local. See
[Local or not](pools.md#local-or-not).

```
$ papers config local false
```

## 3. A second project that uses the pool

```
$ cd ~/projects/tides
$ papers init --pool ~/Documents/papers/sealevel
$ papers add --doi 10.5194/esd-4-11-2013
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1) [from pool ~/Documents/papers/sealevel]
$ papers add ~/Downloads/bg-8-515-2011.pdf
Added -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, file:1) [also added to pool ~/Documents/papers/sealevel]
```

`add` looks in the pool first: a paper the pool has is taken from it, with
its PDF, and nothing is fetched or copied. A new paper goes to the library
and to the pool, since this library is not local and keeps its PDFs in the
pool. In a local library with a pool, a new paper goes to the pool only if
the `auto-push` setting is on, or with `papers push`. See
[Local or not](pools.md#local-or-not) and [Auto-push](pools.md#auto-push).

Each library has only the entries it asks for. Changes to shared entries,
made in either project, are exchanged with `papers sync`. See
[Pools](pools.md) for `pull`, `push`, `sync` and the merge.

## The default setup

`papers init` without option declares the global pool,
`~/Documents/papers`, and is not local. All projects created this way
share one pool and its PDFs: a paper added in one project is in the pool
for the others, and steps 1 and 2 are not needed. The global pool is set
with `papers config --global pool PATH`. See
[Libraries and pools](pools.md#libraries-and-pools).

Coming from papers 2: see [Upgrading from papers 2](upgrading.md).
