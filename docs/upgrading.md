# Upgrading from papers 2

papers 3 adds the following new features and concepts:

- **exchanges between libraries**: `papers pull`, `push` and `sync` copy
  entries from one library to another and keep them in sync, with a
  field-by-field merge (see [Pools](pools.md));
- **shallow libraries**: a project library that takes its entries from a
  shared library, the shared library  pool, and links to the pool's PDFs instead of
  copying them (see [Shallow libraries](shallow-libraries.md)). The shared
  library can be a library per topic (`~/Documents/papers/sealevel`), or
  one library for everything: the default library (see
  [A global shared library](global-library.md));
- **speed**: on a library of 10,000 entries, common commands take a third
  to a half of the time of papers 2 (`papers list` 0.87 s → 0.27 s,
  `papers add` 1.70 s → 0.69 s), and the duplicate checks are two orders
  of magnitude faster (`papers list --duplicates` on 1,000 entries:
  18.6 s → 0.13 s). Measured with papers 2.19.6 and 3.0.0b4 on the same
  machine and libraries (`scripts/generate_dummy_bib.py`);
- **new, cleaner commands**: `papers install` is replaced by `papers init`
  and `papers config`. Commands on attached files are grouped under
  `papers file`. `papers list` has more actions, and older forms are
  deprecated (see [What else changed](#what-else-changed));
- **RIS, CSL-JSON and BibJSON**: `papers add refs.ris` (or `.json`, `.bib.json`) imports them,
  `papers list --format` and `papers export` write them (see
  [Export](export.md));
- **a history of each library, without git**: every command tries as much as possible to be atomic;
  `papers undo` and `papers redo` take back any command with the files it
  moved, renamed or deleted (also outside the library, e.g. a PDF taken
  from `~/Downloads`), a change made outside papers is recorded as a step
  of its own, and `papers history` lists the steps. The history is kept on
  the computer, and git and git-lfs are no longer needed (see
  [Undo and redo](undo-redo.md)). The git backup of papers 2 is no longer
  used (see [Backups of earlier versions](git.md#backups-of-earlier-versions));
- **`papers status` and the pool**: a shallow library says whether it is
  `in sync` with its pool, or which side changed, and which command shows
  and exchanges the changes (see [Configuration](configuration.md#pools));
- **for programming and scripting**: `--porcelain` lists the entries a command added,
  modified, renamed or removed, and `papers edit KEY --from FILE`, `--set`,
  `--unset` and `--key` change an entry without an editor (used by
  [Papers Desktop](https://github.com/mathesislab/papers-desktop)).

## What changes for an existing setup

The bibtex files do not change format, and stay readable by papers 2 and
by other tools.

What does change, however:

- The configuration files:
    - the configuration of a project library moves from
      `.papersconfig.json` to `.papers/config.json` the next time papers
      writes it (also the first command that changes the library, which
      adds the `id` of its history). In a project repository, git shows the old file as
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
    | `papers backup` | `papers history` |
    | `papers uninstall` | `rm -r .papers`, and `papers history --remove` |
    | `--attachment` | `--attach` |
    | `-m/--mode` | `--on-duplicate` |
    | `--relative-paths` / `--absolute-paths` | `papers config paths relative` or `absolute` |

    `papers git` is removed, and the options `--git`, `--no-git`,
    `--git-lfs` and `--restore-files` are ignored (papers keeps its
    it's own history without using git, see [Undo and redo](undo-redo.md)).
    `papers install --global` is removed: it stops with an error, and
    changes nothing. `papers init PATH --global` creates the default
    library, and `papers config --global default PATH` registers an
    existing one.

- `papers list` keeps its search options and its actions `--edit`,
  `--delete`, `--add-tag`, `--rename` (with `--keep-source`) and `--open`,
  and has new ones: `--attach`, `--rm-tag`, `--detach`, `--detach-broken`, `--fix-files`,
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

papers 3 reads the configuration files of papers 2 as they are; nothing
is converted without the user deliberawtily issuing a command.

### The global configuration

The global library of papers 2 is defined by its global configuration
(`~/.config/papersconfig.json` on Linux). papers 3 keeps using it outside
of libraries, and prints a warning on every command:

```
$ papers list
papers: warning: found the global configuration of papers v2 (~/.config/papersconfig.json): it still applies outside of libraries; `papers migrate` turns it into a library, the default library
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
- The bibtex and the PDFs stay where they are. The git backup of papers 2
  is no longer used, and stays where it is until you delete it (see
  [Backups of earlier versions](git.md#backups-of-earlier-versions)). File links
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
`.papers/config.json` in papers 3. papers moves it the next time it writes
the configuration (e.g. `papers config`, or the first command that changes
the library, which adds the `id` of its history), and prints a line that
says so:

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
- The `files` setting (`move` by default, `copy`, `link` or `ask`) applies
  to `papers file rename` too, and `ask` asks for each file (see
  [Files](files.md#what-add-does-with-a-file)).
- `papers file` groups the commands on attached files: `attach`,
  `detach`, `rm`, `mv`, `rename`, `check`, `fix`, `clean` (see
  [Files](files.md)).
