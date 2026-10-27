# A global shared library

One way to use papers: a single library, for instance `~/Documents/papers`,
holds all your entries and PDFs, and each project is a shallow library
that uses it as pool. A paper is fetched and stored once, the first time a
project adds it; the other projects take it from the shared library. This
is close to the global library of papers 2, with one bibtex per project
on top.

papers supports this with an optional **default library** in the global
configuration (`~/.config/papers/config.json` on Linux):

- `papers init --shallow` creates a shallow library whose pool is the
  default library;
- commands run outside of any library act on the default library.

## Create it

`papers init PATH --global` creates a self-contained library at `PATH` and
registers it as the default library. `PATH` is required:
`papers init . --global` registers the current directory.

```
$ papers init ~/Documents/papers --global
created the library ~/Documents/papers
* bibtex:  papers.bib
* files:   files (the files directory of the library)
* backup:  bibtex history (git)
`papers config` lists and sets the settings
registered ~/Documents/papers as the default library in ~/.config/papers/config.json
```

An existing library is registered with `papers config --global default
PATH`. The default library must be a library without pool;
`papers config --global default none` (or `--unset default`) removes the
setting, and does not change the library.

```
$ papers config --global default
~/Documents/papers
```

## Projects that use it

```
$ cd ~/projects/ice
$ papers init --shallow
created the library ~/projects/ice
* bibtex:  papers.bib
* files:   in the pool (shallow library)
* pool:    ~/Documents/papers
* backup:  bibtex history (git)
`papers config` lists and sets the settings
$ papers add --doi 10.5194/esd-4-11-2013
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013) [also added to pool ~/Documents/papers]
```

`papers init --shallow` is `papers init --pool ~/Documents/papers`: the pool
is written in the project's configuration as the global configuration
writes it (with `~`), so that a project copied to another machine with the
same layout finds it there. Changing the default library later does not
change the projects created before. Without a default library,
`papers init --shallow` stops:

```
$ papers init --shallow
ERROR:papers:no default library: `papers init PATH --global` or `papers config --global default PATH`
```

See [Shallow libraries](shallow-libraries.md) for what a shallow library does with its pool: `add`
looks in it first and adds the new papers to it, and `papers sync`
exchanges the changes of the shared entries.

## Outside of any project

A command run outside of any library acts on the default library, and
`papers status` says so:

```
$ cd ~
$ papers list
perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013)
$ papers status
papers library: ~/Documents/papers (default library, set in ~/.config/papers/config.json)
* bibtex: Documents/papers/papers.bib (1 entries, 0 file links)
* files:  Documents/papers/files (the files directory of the library, empty)
* backup: bibtex history (git)
`papers config` lists and sets the settings
```

The default library can take papers from other libraries too, e.g. a
self-contained project (see
[Exchanges with any library](pools.md#exchanges-with-any-library)):

```
$ papers add --pool ~/projects/sealevel --doi 10.5194/bg-8-515-2011
Added -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, file:1) [from pool ../../projects/sealevel]
```

Without a default library, a command outside of any library stops:

```
$ papers config --global default none
$ papers list
ERROR:papers:no library found here: `papers init`, or pass --bibtex
$ papers status
papers library: (no library found: create one with `papers init`)
* default library:    none
```

`papers -C DIR` runs a command in the library `DIR` from anywhere, e.g.
`papers -C ~/Documents/papers undo`. `papers uninstall` run outside of any
library does not remove the default library's configuration: run
`papers -C ~/Documents/papers uninstall` for that.

## From papers 2

The global library of papers 2 becomes the default library with
`papers migrate`, where it is (see
[Upgrading from papers 2](upgrading.md)). Its project libraries become
self-contained libraries; `papers config pool PATH` makes one of them a
shallow library of the default library, once the default library has its
PDFs (`papers push --pool PATH --all` copies them there).
