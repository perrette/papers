# Configuration

## Libraries

A library is a bibtex file, a files directory, and a configuration file
next to them (`.papersconfig.json`). `papers init` creates one in the
current directory, and `papers init DIR` in the directory `DIR` (created if
missing, with its parents):

```
$> papers init
created the library ~/projects/sealevel
* bibtex:  papers.bib
* files:   in the pool ~/Documents/papers
* backup:  git
`papers status -v` shows all settings
```

By default the bibtex is `papers.bib` (or the first `.bib` file present in
the directory) and the files directory is `files` (or an existing `pdfs`,
`pdf`, `papers` or `bibliography` folder). The options of `papers init` are
`--bibtex`, `--filesdir`, `--pool PATH|none` and `--local` (see
[Pools](#pools)), `--paths relative|absolute`, `--git`/`--no-git`,
`--git-lfs`, `--editor` and the name and key format options (see
[Renaming files and keys](renaming.md)).
With `DIR`, the paths given to `--bibtex` and `--filesdir` are relative to
`DIR`.
`papers init` does not prompt, and fails if the directory already has a
library configuration: change the settings of an existing library with
`papers config`.

Every command run in the library directory or in one of its subdirectories
acts on that library. `-C DIR`, before the command name, runs papers as if it
was started in `DIR`:

```
papers -C ~/projects/sealevel list smith
```

`--bibtex` and `--filesdir` still override the library for one command. If
the bibtex given with `--bibtex` belongs to another library (a configuration
file in its directory or above), the settings of that library apply.

Outside of any library, commands act on the global pool if it is a library
(see [Pools](#pools)), and otherwise fail with a message that explains how to
create one.

Type `papers status` to see which library a command acts on, and
`papers status -v` to also see its settings and where each one comes from.

## Settings

`papers config` gets and sets the settings, in the style of `git config`:

```
papers config                          # list the settings and where each comes from
papers config name.template            # print one setting
papers config name.template '{author}_{year}_{title}'   # set it in the library
papers config --unset name.template    # remove it from the library
```

Each setting comes from the library configuration if it sets it, otherwise
from the global configuration, otherwise from its built-in default. The
exception is `pool`: it comes only from the library configuration, and a
library that does not set it has no pool (`none`).
`papers config` without argument shows the source of each setting as
`(library)`, `(global)` or `(default)`.

| Setting | Values |
|---|---|
| `bibtex` | path of the bibtex file |
| `filesdir` | path of the files directory |
| `pool` | path of the library's pool (relative to the library, or with `~`), or `none` (the value when the library does not set it; `papers init` writes the global pool by default) |
| `local` | `true`: the files are in the files directory of the library; `false`: in the files directory of the pool (see [Pools](pools.md#local-or-not)) |
| `paths` | `relative` (default) or `absolute`: how file links are written in the bibtex |
| `files` | `move` (default), `copy` or `link`: what `papers add` does with a file (see [Files](files.md#what-add-does-with-a-file)); in a library that is not local, how the file gets to the pool: moved or copied into its files directory, or linked where it is by the library and the pool entry |
| `auto-push` | `false` (default) or `true`: the commands that change entries push them to the pool (the entries shared with it, and new ones), see [Pools](pools.md#auto-push) |
| `git` | `true` or `false`: back up the bibtex with git (see [Git integration](git.md)) |
| `git-lfs` | `true` or `false`: also back up the files with git-lfs |
| `editor` | command that opens a text editor, e.g. `vim` or `subl -w` (it wins over `$VISUAL` and `$EDITOR`, which are used without it) |
| `name.template`, `name.author-num`, `name.author-sep`, `name.title-word-num`, `name.title-word-size`, `name.title-length`, `name.title-sep`, `name.unknown-template`, `name.unknown-strict` | file name format |
| `key.template`, `key.author-num`, `key.author-sep`, `key.title-word-num`, `key.title-word-size`, `key.title-length`, `key.title-sep`, `key.unknown-template`, `key.unknown-strict` | bibtex key format |

The name and key settings correspond to the `--name-*` and `--key-*` options
of the commands (see [Renaming files and keys](renaming.md)), which override
them for one command.

Paths in the library configuration are stored relative to its directory, so
that the library can be moved or shared as a whole. `papers config bibtex`,
`papers config filesdir` and the list of `papers config` show them as
absolute paths. A relative path given to set them is relative to the current
directory.

Setting `git` to `true` initializes the backup directory and records the
current bibtex. Setting `paths` rewrites the file links of the bibtex.
Setting `local` or `pool` changes where the library links its files:
`local true` (or `pool none`) copies the pool files that the library links
to into its files directory; `local false`, and `pool PATH` in a library
that is not local, link to the pool's copies of the library's PDFs, and
require the pool to have them already (`papers push` copies them there).
papers lists what it will do and asks to continue (`-y` does not ask,
`--dry-run` only lists; see
[Changing local and pool](pools.md#changing-local-and-pool)).
`local` is always set in a library (`papers init` stores it), so it has no
`--unset`.

### Global configuration

`papers config --global` reads and writes the global configuration (per
user, as in `git config --global`) instead of the library's:
`~/.config/papers/config.json` on Linux (the platform's user configuration
directory elsewhere). It holds the global pool and the default settings of
the libraries that do not set them (everything except `bibtex`, `filesdir`
and `pool`). It defines no library: the global library of papers v2 is now
the global pool (see [Pools](pools.md)).

```
papers config --global editor vim
papers config --global name.template '{author}_{year}'
papers config --global pool ~/Dropbox/papers   # the global pool
papers config --global local true              # new libraries keep their own files
papers config --global                         # list it
```

In the global configuration, `pool` is the path of the global pool (default
`~/Documents/papers`), or `none`. It is used for three things: the pool
that `papers init` writes in a new library (with `none`, new libraries get
`pool: none`, and so are local); the library that commands act on outside
of any library; and the target of `papers migrate` for the global library
of papers v2. `local` is the default of new libraries (default `false`).

`papers init` stores `pool`, `paths`, `git`, `git-lfs` and `local` in the
new library, taking their values from the global configuration when it sets
them. The other settings are only stored in the library when you set them.
Changing the global `pool` later does not change the libraries created
before: each keeps the pool written in its configuration.

## Pools

A pool is a library that other libraries exchange entries with (see
[Pools](pools.md) for `add`, `pull`, `push`, `sync` and `export`). A library
has one pool, its `pool` setting: a path relative to the library (e.g.
`../shared-with-bob`), a path with `~` or absolute, or `none`. A library
that does not set it has no pool. `papers init` writes the global pool (the
`pool` setting of the global configuration, `~/Documents/papers` without
one) unless `--pool` or `--local` says otherwise. It writes it as the global
configuration does, usually with `~`, so that a project copied to another
machine with the same layout finds its pool there. The global pool is
created the first time papers writes to it; it is also the library that
commands act on outside of any library, once it is one.

A configuration file written by a test build that took several pools may
store `pool` as a list: a list of one path is read as that path, and a list
of several paths is an error that names the file. Write one path, or
`none`, in that file.

`local` says where the files of the library are: in the files directory of
the pool (`false`, the default: the library links to them) or in its own
(`true`). In a library that is not local, the file links are the pool
entry's; the library decides which entries it has. A project folder shared with others (git, Dropbox) should be
local: the links of a library that is not local point into your own pool.

```
papers init                    # pool: the global pool, not local
papers init --local            # its own files, no pool
papers init --local --pool ../shared   # its own files, entries shared with ../shared
papers init --pool ../shared   # another pool
papers init --pool none        # no pool, hence local
```

`papers status` shows the pool of the library (its path, or none), whether
it is the global pool, is missing or is not a library, and whether it
changed since the last exchange with it. It also shows `local`, and the
`auto-push` setting of a library that has a pool.

## Relative versus absolute paths

The file links in the bibtex are relative to the bibtex directory by default,
so that a library folder can be moved or shared with its files. Set
`papers config paths absolute` to store absolute paths instead, e.g. for a
bibtex that links to files in a central folder.

The options `--relative-paths` and `--absolute-paths` of the commands still
override the setting for one command, with a deprecation warning.

## Migrating from papers 2

[Upgrading from papers 2](upgrading.md) gives an overview. `papers migrate`
performs the one-time upgrades from version 2:

- The global configuration of version 2 (`~/.config/papersconfig.json` on
  Linux) defined a library for the whole user account. `papers migrate`
  writes its settings to a library configuration next to its bibtex (if
  there is none yet; the library keeps its files and has no pool), makes the
  directory of that bibtex the global pool in the global configuration
  (unless another global pool is set there), and renames the old file to
  `papersconfig.json.v2.bak`.
  The bibtex, files and backup stay where they are. File links stay
  absolute, as they were, unless `--relative` is passed. Running
  `papers migrate` again does nothing. Until then, papers prints a warning
  and keeps using the global configuration outside of libraries.
- `papers migrate --folders` moves the files of entries that are still kept
  in folders of papers before 2.19 (`<name>/` with a hidden `.<name>.bib`)
  into the files directory, named after the name template (as
  `papers file rename` names them).

Library configurations (`.papersconfig.json`) of version 2 keep working
without migration: they are read as local libraries (their files are their
own) without pool (`pool none`), as in version 2. The configuration files written by version 3 carry
`"version": 3`; a file without `version` is read as a file of version 2. A
file with a higher version was written by a newer papers, and papers stops
with an error.

### `papers install`

`papers install` is a deprecated alias of `papers init` that asks for the
bibtex, the files directory and git (`-y/--yes` accepts the defaults;
`--no-prompt` and `--force` are its deprecated forms). On
an existing library it updates the library configuration, as in version 2,
with a deprecation warning: use `papers config` instead (`--edit` and
`--reset` keep working). `papers install --global` writes the library
configuration next to the bibtex and makes its directory the global pool;
if a global configuration of version 2 exists, it first migrates it as
`papers migrate` does. `--local` is ignored.

## Uninstall

```
papers uninstall
```

removes the library configuration and reports what it leaves behind (the
bibtex file, the files directory, and the backup directory if any). Pass
`--remove-backup` to also remove the backup directory. It never removes the
global configuration. From outside of any library it does not remove
the global pool's configuration: run `papers -C DIR uninstall` for that.

`papers uninstall --recursive` is deprecated and ignored (there is no global
library configuration to walk up to in v3): only the configuration of the
library is removed.

## Cache

All internet requests, such as crossref requests, are saved in the cache
directory (shown by `papers status -v`), whether or not a library is
configured. The metadata of each DOI is a json file under `doi/`, e.g.
`doi/10.1126/science.1166510.json` (DOIs that do not exist are remembered for
a day). Deleting the directory, or any file in it, is safe: the requests are
made again when needed.
