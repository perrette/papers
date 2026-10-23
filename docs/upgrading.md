# Upgrading from papers 2

In papers 2 you had one global library, or a library tied to a project
with its own PDFs. In papers 3 every library is tied to a project, and
libraries can share entries and PDFs through a pool. A pool is a library
in a shared location: a bibtex and a folder of PDFs. The global pool is
`~/Documents/papers`; you can add others, for instance one per topic
(`~/Documents/papers/sealevel`). Each library uses one pool, or none, and
different libraries can use different pools. A library either keeps its
own copy of the PDFs (`local true`) or links to the PDFs of its pool
(`local false`).

## What becomes of a papers 2 setup

| papers 2 | papers 3 |
|---|---|
| the global library (`papers install --global`) | the global pool. It is still a library: commands run outside of any project act on it, and `papers -C DIR` reaches it from anywhere |
| a project library (`papers install --local`) with its own PDFs | a local library (`local true`). It reads the global pool, but writes nothing to it unless you push. With `papers config pool none` it is the same as a new `papers init --local` |
| several project libraries with a common `filesdir` | still works, without a pool (see [A shared files folder without a pool](pools.md#a-shared-files-folder-without-a-pool)); a pool is more efficient |
| `papers install` | `papers init` to create a library, `papers config` to change it; `papers install` is a deprecated alias |

## What happens on the first run

papers 3 reads the configuration files of papers 2 as they are. Nothing
is converted without a command.

### The global configuration

The global library of papers 2 is defined by its global configuration
(`~/.config/papersconfig.json` on Linux). papers 3 keeps using it outside
of libraries, and prints a warning on every command:

```
$ papers list
WARNING:papers:found the global configuration of papers v2 (~/.config/papersconfig.json): it still applies outside of libraries; `papers migrate` turns it into a library and the global pool
perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1)
```

`papers migrate` converts it. In this example the global library of
papers 2 is `~/bibliography/papers.bib`:

```
$ papers migrate
global configuration of papers v2: ~/.config/papersconfig.json
  create the library configuration ~/bibliography/.papersconfig.json (paths: absolute)
  register ~/bibliography as the global pool in ~/.config/papers/config.json
  rename ~/.config/papersconfig.json to ~/.config/papersconfig.json.v2.bak
```

- The library gets a configuration file next to its bibtex, with the
  settings of papers 2. It keeps its own files and has no pool itself.
- Its directory becomes the global pool, unless the global configuration
  of papers 3 already sets another one. The global pool is then
  `~/bibliography`, not `~/Documents/papers`.
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
needs no migration. papers 3 reads it as a local library that uses the
global pool:

- its PDFs stay in its own files directory;
- `papers add` looks in the global pool first. A paper found there is taken
  with its PDF, copied into the project's files directory (a hard link when
  possible);
- nothing is written to the pool unless you run `papers push` (or turn
  `auto-push` on).

`papers config pool none` stops the lookups in the global pool.
`papers config pool PATH` makes it use another pool.

## Topic pools

The main new use of papers 3: each project keeps its own bibtex, the one
its LaTeX document cites, while the PDFs and the curated entries of a topic
live once in a topic pool. A new project on the same topic takes the
entries and PDFs it needs from the pool, without fetching anything or
storing a PDF twice. A correction made in one project reaches the others
with `papers sync`.

To turn an existing project library into the start of a topic pool:

```
cd ~/projects/sealevel
papers config pool ~/Documents/papers/sealevel   # the topic pool
papers push --all          # copies the entries and their PDFs to the pool
papers config local false  # optional: link to the pool's PDFs, delete the project's copies
```

`papers push --all` creates the pool if it does not exist yet (its parent
folder must exist). It copies the PDFs as hard links when possible, so the
PDFs are not read again and nothing is fetched. `papers config local false`
refuses until the pool has every PDF of the library, and then names the
entries to push.

A new project on the same topic:

```
cd ~/projects/tides
papers init --pool ~/Documents/papers/sealevel
papers add --doi 10.5194/esd-4-11-2013   # taken from the pool, with its PDFs
papers pull perrette_yool2011            # or by key
papers sync                              # later: exchange the changes both ways
```

The [Quickstart](quickstart.md) runs through these steps with their
output, and [Pools](pools.md) describes the exchanges.

## What else changed

- `papers init` replaces `papers install`: it asks no questions, and fails
  if the folder has a library already (use `papers config`). By default it
  creates a library that uses the global pool and links to its PDFs; use
  `papers init --local` for a project that keeps its own PDFs, as in
  papers 2.
- `papers config` gets and sets the settings, in the style of
  `git config` (see [Configuration](configuration.md#settings)).
- The global configuration of papers 3 is `~/.config/papers/config.json`
  on Linux. It holds the global pool and default settings, and defines no
  library.
