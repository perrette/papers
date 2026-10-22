# Configuration

## Libraries

A library is a bibtex file, a files directory, and a configuration file
next to them (`.papersconfig.json`). `papers init` creates one in the
current directory, and `papers init DIR` in the directory `DIR` (created if
missing, with its parents):

```
$> papers init
papers library: /home/perrette/projects/sealevel
version 3.0.0
* configuration file: .papersconfig.json
* per-machine config: /home/perrette/.config/papers/config.json (none)
* cache directory:    /home/perrette/.cache/papers
* backup (git):       True
* backup files (git-lfs): False
* backup directory:   /home/perrette/.local/share/papers/backups/sealevel-papers-3f9a1c2b
* files directory:    files (empty)
* bibtex:             papers.bib (empty)
* pools:
    default: /home/perrette/Documents/papers (missing)
...
```

By default the bibtex is `papers.bib` (or the first `.bib` file present in
the directory) and the files directory is `files` (or an existing `pdfs`,
`pdf`, `papers` or `bibliography` folder). The options of `papers init` are
`--bibtex`, `--filesdir`, `--pool NAME|PATH...` (see [Pools](#pools)),
`--paths relative|absolute`, `--git`/`--no-git`, `--git-lfs`, `--editor`, `--light`
(see [Light libraries](pools.md#light-libraries)) and
the name and key format options (see [Renaming files and keys](renaming.md)).
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

Outside of any library, commands act on the default pool if it is a library
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
papers config pools default ../shared  # settings with several values
```

Each setting comes from the library configuration if it sets it, otherwise
from the per-machine configuration, otherwise from its built-in default.
`papers config` without argument shows the source of each setting as
`(library)`, `(machine)` or `(default)`.

| Setting | Values |
|---|---|
| `bibtex` | path of the bibtex file |
| `filesdir` | path of the files directory |
| `pools` | names or paths of the library's pools (default: `default`) |
| `paths` | `relative` (default) or `absolute`: how file links are written in the bibtex |
| `files` | `move` (default), `copy` or `link`: what `papers add` does with a file (see [Files](files.md#what-add-does-with-a-file)) |
| `sync` | `none` (default) or `push`: `papers add` also adds the new entries to the first pool (see [Pools](pools.md)) |
| `git` | `true` or `false`: back up the bibtex with git (see [Git integration](git.md)) |
| `git-lfs` | `true` or `false`: also back up the files with git-lfs |
| `editor` | command that opens a text editor, e.g. `vim` or `subl -w` |
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
current bibtex. Setting `paths` rewrites the file links of the bibtex. `light`
is not a setting of `papers config`: it is changed with
`papers migrate --light` and `papers migrate --full`, because it also
changes the file links and the files (see
[Light libraries](pools.md#light-libraries)).

### Per-machine configuration

`papers config --machine` (or `--global`) reads and writes the per-machine
configuration instead of the library's: `~/.config/papers/config.json` on
Linux (the platform's user configuration directory elsewhere). It holds the
pool names and the settings used by libraries that do not set them
(everything except `bibtex`, `filesdir` and `pools`):

```
papers config --machine editor vim
papers config --machine name.template '{author}_{year}'
papers config --machine pools.teaching /mnt/shared/teaching
papers config --machine                # list it
```

`papers init` stores `paths`, `git` and `git-lfs` in the new library, taking
their values from the per-machine configuration when it sets them. The other
settings are only stored in the library when you set them.

## Pools

A pool is a library that other libraries exchange entries with (see
[Pools](pools.md) for `add`, `pull`, `push`, `export` and light
libraries). Each library
lists its pools in the `pools` setting, as names or paths. A name is looked
up in the per-machine configuration (`pools.NAME`, or `papers pool add NAME
PATH`), so that the same library
works on machines where the pool is in a different place. An entry that
contains a `/` or starts with `.` or `~` is a path, relative to the library
(e.g. `../shared-with-bob`).

Without per-machine configuration, the pool `default` is
`~/Documents/papers`. It is also the library that commands act on outside of
any library, once it is one:

```
papers init ~/Documents/papers
```

`papers status` lists the pools of the library with their paths, says when
a pool is missing or is not a library, and whether it changed since the last
`papers pull`. It also shows whether the library is light, and the `sync`
setting.

## Relative versus absolute paths

The file links in the bibtex are relative to the bibtex directory by default,
so that a library folder can be moved or shared with its files. Set
`papers config paths absolute` to store absolute paths instead, e.g. for a
bibtex that links to files in a central folder.

The options `--relative-paths` and `--absolute-paths` of the commands still
override the setting for one command, with a deprecation warning.

## Migrating from papers 2

`papers migrate` performs the one-time upgrades from version 2:

- The global configuration of version 2 (`~/.config/papersconfig.json` on
  Linux) defined a library for the whole user account. `papers migrate`
  writes its settings to a library configuration next to its bibtex (if
  there is none yet), registers the directory of that bibtex as the
  `default` pool in the per-machine configuration (unless another default
  pool is set there), and renames the old file to `papersconfig.json.v2.bak`.
  The bibtex, files and backup stay where they are. File links stay
  absolute, as they were, unless `--relative` is passed. Running
  `papers migrate` again does nothing. Until then, papers prints a warning
  and keeps using the global configuration outside of libraries.
- `papers migrate --folders` moves the files of entries that are still kept
  in folders of papers before 2.19 (`<name>/` with a hidden `.<name>.bib`)
  into the files directory, named after the name template (as
  `papers file rename` names them).

Library configurations (`.papersconfig.json`) of version 2 keep working
without migration. The configuration files written by version 3 carry
`"version": 3`; a file without `version` is read as a file of version 2. A
file with a higher version was written by a newer papers, and papers stops
with an error.

### `papers install`

`papers install` is a deprecated alias of `papers init` that asks for the
bibtex, the files directory and git (`--no-prompt` accepts the defaults). On
an existing library it updates the library configuration, as in version 2,
with a deprecation warning: use `papers config` instead (`--edit` and
`--reset` keep working). `papers install --global` writes the library
configuration next to the bibtex and registers its directory as the `default`
pool; if a global configuration of version 2 exists, it first migrates it as
`papers migrate` does. `--local` is ignored.

## Uninstall

```
papers uninstall
```

removes the library configuration and reports what it leaves behind (the
bibtex file, the files directory, and the backup directory if any). Pass
`--remove-backup` to also remove the backup directory. It never removes the
per-machine configuration. From outside of any library it does not remove
the default pool's configuration: run `papers -C DIR uninstall` for that.

`papers uninstall --recursive` (deprecated) also removes the library
configurations of the parent directories, and the global configuration of
version 2 if there is one.

## Cache

All internet requests, such as crossref requests, are saved in the cache
directory (shown by `papers status -v`), whether or not a library is
configured. The metadata of each DOI is a json file under `doi/`, e.g.
`doi/10.1126/science.1166510.json` (DOIs that do not exist are remembered for
a day). Deleting the directory, or any file in it, is safe: the requests are
made again when needed.
