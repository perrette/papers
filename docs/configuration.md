# Configuration

## Libraries

A library is a bibtex file, a files directory, and a configuration file
`.papers/config.json` in the library directory. The `.papers/` folder also
holds the origin copies of the entries exchanged with pools and the pairs
recorded as not the same paper, also when the bibtex is in another folder.
Versions up to 3.0.0b5 wrote these two next to the bibtex: papers moves
them to the `.papers/` of the library when it opens the library, unless the
folder of the bibtex is a library of its own. `papers init` creates a
library in the current directory, and `papers init DIR` in the directory
`DIR` (created if missing, with its parents):

```
$> papers init
created the library ~/projects/sealevel
* bibtex:  papers.bib
* files:   files (the files directory of the library)
`papers config` lists and sets the settings
```

By default the library is self-contained (no pool), the bibtex is
`papers.bib` (or the first `.bib` file present in the directory) and the
files directory is `files` (or an existing `pdfs`, `pdf`, `papers` or
`bibliography` folder). The options of `papers init` are `--bibtex`,
`--filesdir`, `--pool PATH` and `--shallow` (see [Pools](#pools)),
`--global` (see [Global configuration](#global-configuration)),
`--paths relative|absolute`, `--editor`
and the name and key format options (see
[Renaming files and keys](renaming.md)).
With `DIR`, the paths given to `--bibtex`, `--filesdir` and `--pool` are
relative to the current directory, as `DIR` is (`papers init lib --bibtex
lib/refs.bib`).
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

Outside of any library, commands act on the default library if the global
configuration sets one (see [A global shared library](global-library.md)),
and otherwise fail: `no library found here: papers init`.

Type `papers status` to see which library a command acts on: where its
bibtex and its files are, and how it stands with its pool. `papers status -v` also
shows the number of steps of its history, the configuration file, the cache directory and
the version. `papers config` lists the settings and where each one comes from.

## Settings

`papers config` gets and sets the settings, in the style of `git config`:

```
papers config                          # list the settings and where each comes from
papers config name.template            # print one setting
papers config name.template '{author}_{year}_{title}'   # set it in the library
papers config --unset name.template    # remove it from the library
papers config --prune                  # remove the values equal to the global or default value
```

Each setting comes from the library configuration if it sets it, otherwise
from the global configuration, otherwise from its built-in default. The
exception is `pool`: it comes only from the library configuration, and a
library that does not set it has no pool (`none`).
`papers config` without argument shows the source of each setting as
`(library)`, `(global)` or `(default)`. In a shallow library, `filesdir`
and the `name.*` settings are marked `not used: shallow library`: the
files are in the pool, named with the pool's template (`filesdir` is where
`papers config pool none` copies them).

The library configuration keeps the settings given to the library
(`papers init --paths absolute`, `papers config NAME VALUE`), even when the
value is the global or default one; the other settings follow the global
configuration. `papers config --unset NAME` removes a setting from the
file, and the library then follows the global configuration again.
`papers config --prune` removes all the values equal to the global or
default value (`pool` stays).

| Setting | Values |
|---|---|
| `bibtex` | path of the bibtex file |
| `filesdir` | path of the files directory |
| `pool` | path of the library's pool (relative to the library, or with `~`): the library is shallow; or `none` (the value when the library does not set it): the library is self-contained (see [Pools](pools.md#libraries-and-pools)) |
| `paths` | `relative` (default) or `absolute`: how file links are written in the bibtex |
| `files` | `move` (default), `copy`, `link` or `ask`: what `papers add`, `file attach` and `file rename` do with a file outside the files directory (see [Files](files.md#what-add-does-with-a-file)); in a shallow library, how the file gets to the pool: moved or copied into its files directory, or linked where it is by the library and the pool entry |
| `auto-push` | `false` (default) or `true`: in a shallow library, the commands that change entries push them to the pool (the entries shared with it, and new ones), see [Auto-push](shallow-libraries.md#auto-push); no effect in a self-contained library |
| `checksums` | `true` (default): the commands write the checksum of the files they move, copy, add or link in `.papers/files.json`, for undo (see [Checksums](undo-redo.md#checksums)) |
| `editor` | command that opens a text editor, e.g. `vim` or `subl -w` (it wins over `$VISUAL` and `$EDITOR`, which are used without it) |
| `history-size` | `500` (default): the size of the history (see [Undo and redo](undo-redo.md#deleted-files)), in MB, `0` for no limit; papers asks before a command that deletes more. In the global configuration: the history shared by the libraries; in a library: its own history, with `history-separate` |
| `history-separate` | `false` (default) or `true`: the library keeps its history in a store of its own (see [Where the history is](undo-redo.md#where-the-history-is)) |
| `history-dir` | global only: the folder of the history (default: `~/.local/share/papers/history` on Linux) |
| `keep-deleted-files` | global only: `true` (default) or `false`: the files that the commands delete are kept by the history, for undo; with `false`, they go to the trash of the system |
| `name.template`, `name.author-num`, `name.author-sep`, `name.title-word-num`, `name.title-word-size`, `name.title-length`, `name.title-sep`, `name.unknown-template`, `name.unknown-strict` | file name format |
| `key.template`, `key.author-num`, `key.author-sep`, `key.title-word-num`, `key.title-word-size`, `key.title-length`, `key.title-sep`, `key.unknown-template`, `key.unknown-strict` | bibtex key format |

The name and key settings correspond to the `--name-*` and `--key-*` options
of the commands (see [Renaming files and keys](renaming.md)), which override
them for one command.

Paths in the library configuration are stored relative to its directory, so
that the library can be moved or shared as a whole. `papers config bibtex`,
`papers config filesdir` and the list of `papers config` show them as
absolute paths.

A path given on the command line is relative to the current directory, as
for any other command: `papers config bibtex`, `papers config filesdir`,
`papers config pool`, `papers config --global default` and `papers config
--global history-dir`, and `papers init DIR --bibtex FILE --filesdir FOLDER
--pool PATH` (relative to the current directory, not to DIR). papers then
stores it as the setting is written: relative to the library for `bibtex`
and `filesdir`, as described below for `pool`, and absolute (with `~` for
the home directory) for `default` and `history-dir`.

A configuration file (of a library or the global one) that is not valid
JSON, or that gives a setting a value of the wrong type (for example
`"auto-push": "no"` instead of `false`, or a number for `pool`), is an
error: papers names the file and the setting and does nothing until the
file is corrected.

`history-dir` and `keep-deleted-files` can only be set in the global
configuration (`papers config --global`): a library you receive from
someone cannot choose where your history goes, or what it keeps.

Setting `paths` rewrites the file links of the bibtex.
Setting `pool` changes where the library links its files: `pool PATH` (an
existing library without pool) links to the copies of the library's PDFs
in PATH, and requires PATH to have them already (`papers push --pool PATH`
copies them there); in a shallow library, `pool none` copies the pool
files that the library links to into its files directory. papers lists
what it will do and asks to continue (`-y` does not ask, `--dry-run` only
lists; see [Changing the pool](shallow-libraries.md#changing-the-pool)).

### Global configuration

`papers config --global` reads and writes the global configuration (per
user, as in `git config --global`) instead of the library's:
`~/.config/papers/config.json` on Linux (the platform's user configuration
directory elsewhere). It holds the default settings of the libraries that
do not set them (everything except `bibtex`, `filesdir` and `pool`: the
global configuration has no pool), and optionally the default library.

```
papers config --global editor vim
papers config --global name.template '{author}_{year}'
papers config --global default ~/Documents/papers   # the default library
papers config --global                              # list it
```

`default` is the path of the default library, an existing library without
pool, or `none` to remove it (`--unset default` too). It is used for two
things: the library that commands act on outside of any library, and the
pool of `papers init --shallow`. `papers init PATH --global` creates a
self-contained library at `PATH` and sets it as the default library
(`papers init . --global` for the current directory). `papers migrate` sets
the global library of papers v2 as the default library. See
[A global shared library](global-library.md).

`papers init` stores `pool` and `paths` in the new
library, taking their values from the global configuration when it sets
them. The other settings are only stored in the library when you set them.
Changing the default library later does not change the libraries created
with `papers init --shallow` before: each keeps the pool written in its
configuration.

## Pools

A pool is a library that other libraries exchange entries with (see
[Pools](pools.md) for `add`, `pull`, `push` and `sync`, and [Export](export.md)). A library
has at most one pool, its `pool` setting: a path relative to the library
(e.g. `../shared-with-bob`), a path with `~` or absolute, or `none`. A
library that does not set it has no pool. The pool must be an existing
library without pool: `papers init --pool PATH` and `papers config pool
PATH` check it, and stop otherwise. They also refuse a PATH that is the
library itself (`.`, or its path written another way). A pool that takes a pool of its own
later is checked again by `pull`, `push`, `sync` and the commands that add
entries or files to the pool: they stop with an error (the automatic push
after a command prints a warning instead). `papers init --shallow` writes the
default library of the global configuration as the pool, with `~` as the
global configuration writes it, so that a project copied to another
machine with the same layout finds its pool there.

A configuration file written by a test build that took several pools may
store `pool` as a list: a list of one path is read as that path, and a list
of several paths is an error that names the file. Write one path, or
`none`, in that file.

The pool setting gives the state of the library. Without pool, the
library is self-contained: its own entries and files. With a pool, it is
shallow: its file links are the pool entry's, and the entries it adds go
to the pool too; the library decides which entries it has. A project
folder shared with others (git, Dropbox) should be self-contained: the
links of a shallow library point into your own pool.

```
papers init                    # self-contained
papers init --pool ../shared   # shallow: the pool is ../shared
papers init --shallow          # shallow: the pool is the default library
```

`papers status` shows where the files of the library are: its files
directory (self-contained library), or in the pool (shallow library). For
a shallow library, it also shows the pool: its path, and how the library
stands with it:

- `in sync`: the entries exchanged with the pool are the same on both
  sides;
- `pool changed`: the pool has changes to take, and the last line of
  `papers status` says how: `` `papers pull --dry-run` shows the changes,
  `papers pull` takes them ``;
- `library changed`: the library has changes to send (`papers push`), e.g.
  made in an editor, or with `auto-push` off;
- `both changed`: both (`papers sync`);
- `not pulled from yet`, `missing`, `not a library`.

papers compares the entries, not only the files: a pool that changed in
entries the library does not have, or the same change made on both sides,
is in sync. Once it found them in sync, papers remembers (with the history
of the library, on the computer) the pieces of the library, of the pool and
of the origin copies at that time, and later compares only the entries of
the pieces that changed since: a single change does not cost a comparison
of the whole library. `papers status -v` also shows the number of steps of the
history of the library (see [Undo and redo](undo-redo.md)).

## Relative versus absolute paths

The file links in the bibtex are relative to the bibtex directory by default,
so that a library folder can be moved or shared with its files. Set
`papers config paths absolute` to store absolute paths instead, e.g. for a
bibtex that links to files in a central folder.

The options `--relative-paths` and `--absolute-paths` of the commands still
override the setting for one command, with a deprecation warning.

A library in the git repository of a project leaves `.papers/` out of it
(papers writes `.papers/.gitignore`): see [Using git](git.md).

## Migrating from papers 2

[Upgrading from papers 2](upgrading.md) gives an overview. `papers migrate`
performs the one-time upgrades from version 2:

- The global configuration of version 2 (`~/.config/papersconfig.json` on
  Linux) defined a library for the whole user account. `papers migrate`
  writes its settings to a library configuration `.papers/config.json` in
  the directory of its bibtex (if there is none yet; a self-contained library: it keeps its files and has
  no pool), registers the directory of that bibtex as the default library
  in the global configuration (unless another default library is set
  there), and renames the old file to `papersconfig.json.v2.bak`.
  The bibtex and files stay where they are. File links stay
  absolute, as they were, unless `--relative` is passed. Running
  `papers migrate` again does nothing. Until then, papers prints a warning
  and keeps using the global configuration outside of libraries.
- `papers migrate --folders` moves the files of entries that are still kept
  in folders of papers before 2.19 (`<name>/` with a hidden `.<name>.bib`)
  into the files directory, named after the name template (as
  `papers file rename` names them).

Library configurations of version 2 keep working without migration: they
are read as self-contained libraries (their files are their own, no pool),
as in version 2. Their file is moved to `.papers/config.json` the next
time papers saves the configuration (e.g. `papers config`), or by
`papers migrate` run in the library (see
[Upgrading from papers 2](upgrading.md#project-libraries)). The configuration files written by version 3 carry
`"version": 3`; a file without `version` is read as a file of version 2. A
file with a higher version was written by a newer papers, and papers stops
with an error.

### `papers install`

`papers install` is a deprecated alias of `papers init` that asks for the
bibtex and the files directory (`-y/--yes` accepts the defaults;
`--no-prompt` and `--force` are its deprecated forms). On
an existing library it updates the library configuration, as in version 2,
with a deprecation warning: use `papers config` instead (`--edit` and
`--reset` keep working). `papers install --global` is no longer supported:
it stops with an error and changes nothing. Create the default library
with `papers init PATH --global` (for example `papers init
~/Documents/papers/default --global`), or register an existing library
with `papers config --global default PATH`. `--local` is ignored.

## Uninstall

`papers uninstall` is deprecated: `rm -r .papers` removes the configuration
of a library, and `papers history --remove` its history.
`papers uninstall` removes the library configuration and reports what it
leaves behind (the bibtex file, the files directory, the history).
`--remove-history` (or its older name `--remove-backup`) also removes the
history. It never removes the
global configuration. From outside of any library it does not remove
the default library's configuration: run `papers -C DIR uninstall` for that.

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
