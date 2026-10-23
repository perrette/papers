# Upgrading from papers 2

papers 3 adds the following new functionalities:

- **exchanges between libraries**: `papers pull`, `push` and `sync` copy
  entries from one library to another and keep them in step, with a
  field-by-field merge (see [Pools](pools.md));
- **shallow libraries**: a project library that takes its entries from a
  shared library, its pool, and links to the pool's PDFs instead of
  copying them (see [Shallow libraries](shallow-libraries.md)). The shared
  library can be a library per topic (`~/Documents/papers/sealevel`), or
  one library for everything, the default library (see
  [A global shared library](global-library.md));
- **a review of the commands**: `papers init` and `papers config` replace
  `papers install`, the commands on attached files are grouped under
  `papers file`, and older forms are deprecated (see
  [What else changed](#what-else-changed)).

## What changes for an existing setup

The bibtex files do not change format, and stay readable by papers 2 and
by other tools. What changes:

- The configuration files:
    - the configuration of a project library moves from
      `.papersconfig.json` to `.papers/config.json` the next time papers
      saves it. In a project repository, git shows the old file as
      deleted; scripts that read it need the new path;
    - `papers migrate` turns the global configuration of papers 2
      (`~/.config/papersconfig.json` on Linux) into the configuration of
      the global library, and renames it to `papersconfig.json.v2.bak`.
      Until then, papers 3 keeps using it outside of libraries, with a
      warning on every command;
    - papers 2 does not read the new configuration files. To go back to
      papers 2, restore `.papersconfig.json` (e.g. from the project
      repository) or `papersconfig.json.v2.bak`.
- Some commands and options are deprecated. They still work, print a
  warning that names the new form, and are removed in papers 4:

    | stop using | use instead |
    |---|---|
    | `papers install` | `papers init` to create a library, `papers config` to change it |
    | `papers filecheck` | `papers file check`, `papers file fix` and the other `papers file` commands |
    | `papers list ... --copy` | `papers list ... --rename --keep-source` |
    | `papers list ... --add-files FILE...` | `papers list ... --attach FILE...` |
    | `papers list ... --fetch` | `papers check --fetch --fetch-all --fix-doi --fix-key --format-name KEY...`, or `papers list ... -K \| papers check --fetch ... -` |
    | `papers doi` | `papers extract --doi-only` |
    | `papers restore-backup` | `papers restore` |
    | `--attachment` | `--attach` |
    | `-m/--mode` | `--on-duplicate` |
    | `--relative-paths` / `--absolute-paths` | `papers config paths relative` or `absolute` |

    `papers install --global` is removed: it stops with an error, and
    changes nothing. `papers init PATH --global` creates the default
    library, and `papers config --global default PATH` registers an
    existing one.

- `papers list` keeps its search options and its actions `--edit`,
  `--delete`, `--add-tag`, `--rename` (with `--keep-source`) and `--open`,
  and has new ones: `--attach`, `--rm-tag`, `--detach`, `--fix-files`,
  `--push`, `--pull`, `--sync` and `--export`. Each runs the command it
  stands for on the listed entries (see [Actions on the listed entries](listing.md#actions-on-the-listed-entries)).
  The other commands read the keys listed by `papers list -K` with `-`,
  e.g. `papers list --no-file -K | papers check --fetch -y -`. A command
  that reads the keys from a pipe cannot ask questions: answer them with
  its options, as `-y` here (see [Piping](listing.md#piping)).
- The output of `papers status`, `papers init` and of the exchanges
  changed: scripts that parse it need updating.

## What becomes of a papers 2 setup

| papers 2 | papers 3 |
|---|---|
| the global library (`papers install --global`) | the default library, after `papers migrate`, where it is: a self-contained library that commands run outside of any project act on (`papers -C DIR` reaches it from anywhere too) |
| a project library (`papers install --local`) with its own PDFs | a self-contained library, the same as a new `papers init`. `papers config pool PATH` makes it a shallow library of PATH, once PATH has its PDFs |
| several project libraries with a common `filesdir` | still works (see [Comparison](shallow-libraries.md#comparison)). The model preferred in papers 3, which is also more efficient, is a shared library (a pool) and project-bound "shallow" libraries connected to it |

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
  create the library configuration ~/bibliography/.papers/config.json (paths: absolute)
  register ~/bibliography as the default library in ~/.config/papers/config.json
  rename ~/.config/papersconfig.json to ~/.config/papersconfig.json.v2.bak
```

- The library gets a configuration file, `.papers/config.json` in the
  directory of its bibtex, with the settings of papers 2. It is self-contained: it keeps its own files and
  has no pool.
- It is registered as the default library, where it is, unless the global
  configuration of papers 3 already sets another one: commands run
  outside of any project act on it (see
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

A project library of papers 2 needs no migration. papers 3 reads it as a
self-contained library (no pool): its PDFs stay in its own files
directory, and it works as in papers 2.

Its configuration file, `.papersconfig.json` in papers 2, is
`.papers/config.json` in papers 3. papers moves it the next time it saves
the configuration (e.g. `papers config`), and prints a line that says so:

```
$ papers config editor vim
moved ~/projects/sealevel/.papersconfig.json to ~/projects/sealevel/.papers/config.json
```

`papers migrate`, run in the library, moves it too (`--dry-run` shows
it). A directory that has both files is an error, and papers changes
nothing: remove the one you do not want to keep.

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
papers init ~/Documents/papers/sealevel                # a new self-contained library
papers push --pool ~/Documents/papers/sealevel --all   # copies the entries and their PDFs there
papers config pool ~/Documents/papers/sealevel         # link to its PDFs, delete the project's copies
```

`papers push --pool PATH` requires PATH to be a library already
(`papers init PATH` creates it). It copies the PDFs as hard links
when possible, so the PDFs are not read again and nothing is fetched.
`papers config pool PATH` refuses until PATH has every PDF of the library,
and then names the entries to push.

The [Quickstart](quickstart.md) runs through a self-contained project and
a shallow project with their output, [Shallow libraries](shallow-libraries.md)
describes shallow libraries, and [Pools](pools.md) describes the
exchanges.

## What else changed

- `papers init` asks no questions, and fails if the folder has a library
  already (use `papers config`). By default it creates a self-contained
  library, which keeps its own PDFs, as in papers 2;
  `papers init --pool PATH` creates a shallow library.
- `papers config` gets and sets the settings, in the style of
  `git config` (see [Configuration](configuration.md#settings)).
- The global configuration of papers 3 is `~/.config/papers/config.json`
  on Linux. It holds default settings, and optionally the default library
  (`papers config --global default PATH`).
- `papers file` groups the commands on attached files: `attach`,
  `detach`, `rm`, `mv`, `rename`, `check`, `fix`, `clean` (see
  [Files](files.md)).
