# Upgrading from papers 2

In papers 2 you had one global library, or a library tied to a project
with its own PDFs. In papers 3 a library is either self-contained (its own
entries and PDFs, no pool) or shallow: it uses another library as its
pool, takes its entries from there and links to the pool's PDFs. Any
self-contained library can be the pool of others: a project, a library
per topic (`~/Documents/papers/sealevel`), or one library for everything
(`~/Documents/papers`, see [A global shared library](global-library.md)).
Any library can also exchange entries with another library given on the
command line (`--pool PATH`).

## What becomes of a papers 2 setup

| papers 2 | papers 3 |
|---|---|
| the global library (`papers install --global`) | the default library, after `papers migrate`, where it is. It is a self-contained library: commands run outside of any project act on it, `papers init --shallow` creates a project that uses it as pool, and `papers -C DIR` reaches it from anywhere |
| a project library (`papers install --local`) with its own PDFs | a self-contained library (`pool none`), the same as a new `papers init`. `papers config pool PATH` makes it a shallow library of PATH, once PATH has its PDFs |
| several project libraries with a common `filesdir` | still works, with self-contained libraries (see [A shared files folder without a pool](pools.md#a-shared-files-folder-without-a-pool)); exchanges between libraries and shallow libraries are more efficient |
| `papers install` | `papers init` to create a library, `papers config` to change it; `papers install` is a deprecated alias |
| `papers install --global` | an error that changes nothing: `papers init PATH --global` creates the default library (for example `papers init ~/Documents/papers/default --global`), `papers config --global default PATH` registers an existing library |

## What happens on the first run

papers 3 reads the configuration files of papers 2 as they are. Nothing
is converted without a command.

### The global configuration

The global library of papers 2 is defined by its global configuration
(`~/.config/papersconfig.json` on Linux). papers 3 keeps using it outside
of libraries, and prints a warning on every command:

```
$ papers list
WARNING:papers:found the global configuration of papers v2 (~/.config/papersconfig.json): it still applies outside of libraries; `papers migrate` turns it into a library, the default library
perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1)
```

`papers migrate` converts it. In this example the global library of
papers 2 is `~/bibliography/papers.bib`:

```
$ papers migrate
global configuration of papers v2: ~/.config/papersconfig.json
  create the library configuration ~/bibliography/.papersconfig.json (paths: absolute)
  register ~/bibliography as the default library in ~/.config/papers/config.json
  rename ~/.config/papersconfig.json to ~/.config/papersconfig.json.v2.bak
```

- The library gets a configuration file next to its bibtex, with the
  settings of papers 2. It is self-contained: it keeps its own files and
  has no pool.
- It is registered as the default library, where it is, unless the global
  configuration of papers 3 already sets another one: commands run
  outside of any project act on it, and `papers init --shallow` creates a
  project that uses it as pool (see
  [A global shared library](global-library.md)).
- The bibtex, the PDFs and the git backup stay where they are. File links
  stay absolute, as they were; `papers migrate --relative` makes them
  relative to the bibtex.
- `papers migrate --dry-run` shows what it would do. Running
  `papers migrate` a second time does nothing.

`papers migrate --folders` is a separate step: it moves the files that
papers before 2.19 kept in one folder per entry into the files directory.
See [Migrating from papers 2](configuration.md#migrating-from-papers-2) for
the details.

### Project libraries

A project library of papers 2 (`.papersconfig.json` without `"version"`)
needs no migration. papers 3 reads it as a self-contained library (no
pool): its PDFs stay in its own files directory, and it works as in
papers 2.

It can take papers from another library without changing:
`papers add --pool ~/Documents/papers --doi DOI` takes a paper that
`~/Documents/papers` has, with a copy of its PDF (a hard link when
possible), and `papers sync --pool ~/Documents/papers` exchanges later
changes of the entries taken. Nothing new is written to that library
unless you push to it.

## Sharing papers between projects

The main new use of papers 3: each project keeps its own bibtex, the one
its LaTeX document cites, while the PDFs and the curated entries of a topic
live once in one library. A new project on the same topic takes the
entries and PDFs it needs from there, without fetching anything or storing
a PDF twice. A correction made in one project reaches the others with
`papers sync`.

An existing project library can be that library as it is: a new project
uses it as pool.

```
cd ~/projects/tides
papers init --pool ../sealevel           # a shallow library
papers add --doi 10.5194/esd-4-11-2013   # taken from ../sealevel, with its PDF
papers pull perrette_yool2011            # or by key
papers sync                              # later: exchange the changes both ways
```

To move the PDFs of an existing project into a library of the topic, and
make the project shallow:

```
cd ~/projects/sealevel
papers push --pool ~/Documents/papers/sealevel --all   # copies the entries and their PDFs there
papers config pool ~/Documents/papers/sealevel         # link to its PDFs, delete the project's copies
```

`papers push --pool PATH --all` creates the library PATH if it does not
exist yet (its parent folder must exist). It copies the PDFs as hard links
when possible, so the PDFs are not read again and nothing is fetched.
`papers config pool PATH` refuses until PATH has every PDF of the library,
and then names the entries to push.

The [Quickstart](quickstart.md) runs through a self-contained project and
a shallow project with their output, and [Pools](pools.md) describes the
exchanges.

## What else changed

- `papers init` replaces `papers install`: it asks no questions, and fails
  if the folder has a library already (use `papers config`). By default it
  creates a self-contained library, which keeps its own PDFs, as in
  papers 2; `papers init --pool PATH` creates a shallow library.
- `papers config` gets and sets the settings, in the style of
  `git config` (see [Configuration](configuration.md#settings)).
- The global configuration of papers 3 is `~/.config/papers/config.json`
  on Linux. It holds default settings, and optionally the default library
  (`papers config --global default PATH`).
