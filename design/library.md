# The library on disk

This file specifies what a library is on disk, its configuration, the
machine configuration, how a command finds its library, pools and shallow
libraries as far as the configuration goes, the files directory and the
name and key templates, the path safety rules and the lock.

Other files of this specification:

- the bibtex file and its `file` field: `bibtex.md`;
- the history (undo, redo, restore) and `.papers/files.json`: `history.md`;
- the origin records `.papers/origin/` and the exchanges with pools:
  `exchange.md`;
- the export formats: `formats.md`.

Two kinds of rules appear below:

- **Contract**: file names, JSON keys, value formats and resolution rules.
  Any implementation must read and write them identically, so that papers
  and another implementation can work on the same library.
- **Free**: messages, timings, prompts, the order of
  internal steps. Another implementation may differ.

Each section says which is which. When it does not say, the rule is part
of the contract.

## Terms

- **Library directory**: the directory that holds the library
  configuration, `.papers/config.json`.
- **Library configuration**: `.papers/config.json` (or the legacy file
  `.papersconfig.json`, see [Legacy configuration files](#legacy-configuration-files)).
- **Machine configuration** (also "global configuration"): one file per
  user account, with the default library and the default values of the
  settings.
- **Self-contained library**: a library without pool. It has its own
  entries and its own files.
- **Shallow library**: a library with a pool. Its file links point into
  the pool's files directory.
- **Pool**: a library without pool that a shallow library takes its files
  from and adds its new entries to.

## Layout

```
<library directory>/
  papers.bib                  the bibtex (any name and place: the bibtex setting)
  files/                      the files directory (any name and place: the filesdir setting)
  .papers/
    config.json               the library configuration
    .gitignore                "*\n"
    lock                      present while a command writes the library
    lock.<hex>.stale          transient, while a stale lock is taken over
    files.json                checksums of the linked files      (see history.md)
    distinct.json             pairs of entries that are not the same paper
    origin/<name>-<hash>.bib  one origin file per pool             (see exchange.md)
    origin.bib                legacy, earlier v3 builds: read and migrated (see exchange.md)
    backup/                   legacy git backup of earlier v3 builds: no longer used
```

Contract:

- `config.json`, `lock`, `files.json` and `.gitignore` are in the `.papers`
  folder of the **library directory**.
- `distinct.json`, `origin/` and `origin.bib` are in the `.papers` folder
  of the **directory of the bibtex**. In the usual layout (bibtex in the
  library directory) this is the same folder. When the bibtex is in
  another directory the two differ (see [Open questions](#open-questions)).
- Nothing else in `.papers/` is read by papers. The history is outside the
  library (see `history.md`).

### `.papers/.gitignore`

Content: the two bytes `*\n` (everything ignored). papers writes it each
time it saves the library configuration, when either:

- the file does not exist, or
- its content is exactly `backup/\n` (the file that earlier versions wrote).

Any other content is left as it is (the user wrote it). The file is not
written when the configuration is not saved (for example when only the
`id` is added, or when the lock creates `.papers/`).

### `.papers/distinct.json`

Pairs of entries that the user declared to be different papers: format,
writing and matching in `bibtex.md` section 9.4.

### `.papers/files.json`, `.papers/origin/`

- `files.json`: `{"files": {path: sha256}}` with the paths written as the
  file links of the bibtex. See `history.md`.
- `origin/`: one bibtex file per pool. See `exchange.md`.

## The library configuration: `.papers/config.json`

### Format

Contract:

- A JSON object, UTF-8.
- papers writes it with keys sorted, an indent of two spaces, the
  separators `,` and `: `, LF line endings on every platform, and no final
  newline. Characters outside ASCII are written as `\uXXXX` escapes, so
  the file papers writes is ASCII. Readers must accept any valid JSON
  formatting, and UTF-8 text (see [Open questions](#open-questions) for how
  papers reads it).
- papers writes it atomically: to a temporary file in the same directory,
  then renamed over the old file. A symbolic link at the path is followed
  (its target is written). The permissions of an existing file are kept.
  (Atomic writing is free; the format is the
  contract.)

Example (a shallow library):

```json
{
  "auto-push": true,
  "bibtex": "papers.bib",
  "filesdir": "files",
  "id": "ec83827ce59c4988ab592d6d752d716b",
  "nameformat": {
    "template": "{author}_{year}"
  },
  "pool": "../pool",
  "version": 3
}
```

### Keys

| JSON key | Type | Meaning |
|---|---|---|
| `version` | integer | Format version. papers writes `3`. Absent: a file of papers 2. |
| `id` | string | Identifier of the library (see [The `id` field](#the-id-field)). |
| `bibtex` | string or null | Path of the bibtex, relative to the library directory. |
| `filesdir` | string or null | Path of the files directory, relative to the library directory. null or absent: no files directory. |
| `pool` | string | `none`, or the path of the pool (see [Pools](#pools-and-shallow-libraries)). |
| `paths` | `"relative"` or `"absolute"` | How the file links of the bibtex are written. |
| `files` | `"ask"`, `"move"`, `"copy"`, `"link"` | What `add` and the file commands do with a file outside the files directory. |
| `auto-push` | boolean | Shallow library: commands that change entries push them to the pool. |
| `editor` | string | Command that opens a text editor. |
| `checksums` | boolean | Commands write the checksums of the files they touch to `files.json`. |
| `history-size` | integer | Size limit of the library's own history store, in MB (see `history.md`). |
| `history-separate` | boolean | The library has a history store of its own (see `history.md`). |
| `nameformat` | object | The file name template and its modifiers (see below). |
| `keyformat` | object | The key template and its modifiers (see below). |

The keys of `nameformat` and `keyformat` are:

| JSON key (in `nameformat` / `keyformat`) | Setting name | Type |
|---|---|---|
| `template` | `name.template` / `key.template` | string |
| `author_num` | `name.author-num` / `key.author-num` | integer |
| `author_sep` | `name.author-sep` / `key.author-sep` | string |
| `title_word_num` | `name.title-word-num` / `key.title-word-num` | integer |
| `title_word_size` | `name.title-word-size` / `key.title-word-size` | integer |
| `title_length` | `name.title-length` / `key.title-length` | integer |
| `title_sep` | `name.title-sep` / `key.title-sep` | string |
| `unknown_template` | `name.unknown-template` / `key.unknown-template` | string |
| `unknown_strict` | `name.unknown-strict` / `key.unknown-strict` | boolean |

Note the spelling: setting names use hyphens (`name.author-num`), the JSON
keys inside `nameformat`/`keyformat` use underscores (`author_num`). The
other JSON keys are the setting names themselves, with hyphens
(`auto-push`, `history-size`).

`history-dir` and `keep-deleted-files` are settings of the machine only.
In a library configuration they are ignored when read and never written.

### Which keys papers writes

Contract (the reader must accept files with more or fewer keys; this
section says what papers produces):

- `bibtex` and `filesdir` are always written, as null when unset.
- `version` is always written (`3`).
- `id` is written when the library has one.
- Every other setting (`pool` included) is written when the library sets
  it, that is when either:
  - it was given explicitly: present in the file when papers read it
    (whatever its value), set by `papers init`, or set by
    `papers config NAME VALUE`. It is written even when its value equals
    the value it would inherit (the machine configuration's value, else the
    built-in default);
  - or its value differs from the inherited value.

  The other settings are not written: the library follows the machine
  configuration for them. A library that does not write `pool` has no
  pool. `nameformat` and `keyformat` hold only their written members, and
  are omitted when empty.
- The machine-only settings and the keys that papers does not know are
  dropped when papers saves the file.

`papers init` writes `pool` (`none` by default) and `paths` (the value of
`--paths`, else the inherited value), and the settings given as its
options (`--editor`, the name and key template options). A new library so
keeps its link style whatever the machine configuration of the computer
that opens it later.

`papers config --unset NAME` makes a setting inherited again: it is
removed from the file (`bibtex` and `filesdir` are written as null;
without `pool` the library has no pool). `papers config --prune` unsets
each setting present in the file whose value equals its inherited value,
except `bibtex`, `filesdir` and `pool`, and removes the keys of the
settings of papers 2 (`git`, `gitlfs`, `backup_files`, `gitdir`,
`trash-days`, `trash-size`).

### Reading

Contract:

1. Parse the JSON. (papers stops with the parser's error on an invalid
   file.)
2. `version`: absent means 2. A value that is not an integer (booleans
   excluded) is an error. A value greater than 3 is an error: the file was
   written by a newer papers. For version 3 and above, the keys
   `absolute_paths` and `backup_files` are discarded.
3. Version 2 files: see [Legacy configuration files](#legacy-configuration-files).
4. Keys of earlier v3 builds:
   - `light`, `local`, `sync` are discarded;
   - `pool` written as a list: a list with one non-empty string is that
     path; an empty list is `none`; more than one path is an error that
     names the file;
   - `pools` (a list) when `pool` is absent: its first item gives the
     pool. `default` means the default library of the machine
     configuration (or `none` if there is none). `none`, or an item that
     contains a path separator or starts with `.` or `~`, is taken as the
     pool path. Another item is a pool name, looked up in the `pools`
     object of the machine configuration; an unknown name is a warning and
     the library has no pool. An empty list is `none`.
5. `id`: kept only if it is a string of exactly 32 characters in
   `[0-9a-f]`. Otherwise it is ignored.
6. Each setting present with a non-null value is set. The removed settings
   `git`, `git-lfs`, `gitdir`, `trash-days`, `trash-size` and unknown keys
   are ignored.
7. `bibtex` and `filesdir` are resolved against the library directory (see
   [Relative paths](#relative-paths)).

Values read from the file are not checked against their types (see
[Open questions](#open-questions)). Values given on the command line are
checked: booleans accept `true yes on 1` and `false no off 0` (any case),
integers must parse, choices must be one of the listed values.

### The `id` field

Contract:

- 32 lowercase hexadecimal characters: a random UUID version 4 without
  dashes.
- It names the library's project in the history store (see `history.md`).
  Copies of a library folder share it, and thus share a history.
- It also names the library as a pool in the origin records of the
  libraries that exchange with it, so that the records follow the pool
  when its folder moves (see `exchange.md`, sections 2.3 and 3.9).
- When a command needs it and the library has none, papers creates one and
  writes it at once: it reads the JSON of the configuration file from
  disk, sets `id`, and writes the file back (same formatting as above).
  Only `id` changes: the other keys are written as read. This also applies
  to a legacy `.papersconfig.json`, which is not moved for this.
- With `--dry-run`, no id is created.
- A bibtex without library configuration has no id; its history is named
  from its path (see `history.md`).

### Relative paths

Contract:

- The **library directory** of a configuration file is the parent of
  `.papers` for a file named `config.json` in a folder named `.papers`, and
  the directory of the file otherwise (the legacy `.papersconfig.json`).
- `bibtex` and `filesdir`: on reading, a relative path is joined to the
  library directory with its symbolic links resolved, then normalised
  lexically (`.` and `..` removed, symbolic links inside the path kept). An
  absolute path stays absolute. A leading `~` is **not** expanded.
- On writing, papers writes `bibtex` and `filesdir` relative to the
  library directory (symbolic links resolved on both sides), with `..`
  components when the target is outside it. When no relative path exists
  (another drive on Windows), the path is written as given.
- `pool`: a leading `~` is expanded to the home directory; a relative path
  is joined to the library directory (symbolic links resolved), then
  normalised. See [The pool setting](#the-pool-setting) for how papers
  writes it.
- Paths given on the command line to `papers config bibtex|filesdir` are
  relative to the current directory; papers converts them to absolute
  paths, then writes them relative to the library directory.

## Legacy configuration files

### Library configuration of papers 2: `.papersconfig.json`

Contract:

- In each directory where papers looks for a library, it looks for both
  `.papers/config.json` and `.papersconfig.json`. A directory with both is
  an error that names both files; nothing is changed.
- A `.papersconfig.json` is read like `.papers/config.json`, with the
  version 2 rules:
  - its library directory is the directory of the file;
  - the key `local` is discarded; if `local` is `false`, the file is a
    global configuration of papers 2 (see below);
  - `absolute_paths` (boolean) gives `paths` when `paths` is absent:
    `true` is `absolute`, `false` is `relative`;
  - `backup_files` is ignored;
  - a version 2 file without `pool` is a self-contained library.
- When papers saves such a configuration, it first moves the file to
  `.papers/config.json` in the same directory (an error if that exists),
  then writes it there. `papers migrate`, run in the library, does the
  same move.
- A version 2 file is recognised by the missing `version`, not by its
  name.

### Global configuration of papers 2: `papersconfig.json`

Contract:

- Location: the user configuration directory of the platform, without an
  application subfolder: `$XDG_CONFIG_HOME/papersconfig.json` on Linux
  (default `~/.config/papersconfig.json`),
  `~/Library/Application Support/papersconfig.json` on macOS,
  `%LOCALAPPDATA%\papersconfig.json` on Windows.
- It defines a library for the whole account (no library directory: its
  paths are absolute, resolved with symbolic links). When it has no
  `paths` (or `absolute_paths`), `paths` is `absolute`.
- A file is a global configuration of papers 2 when its version is 2 and
  either `local` is `false`, or `local` is absent and its file name is
  `papersconfig.json`.
- While it exists, it is used by commands run outside of any library,
  before the default library (see [Finding the library](#finding-the-library-of-a-command)).
  Commands other than `migrate` print a warning. Commands that change
  settings refuse to write it (`papers migrate` first). It has no lock,
  no `files.json`, and no `id`; papers writes it, if ever, with
  `"local": false` and no `version`.
- `papers migrate` turns it into a library: it writes
  `.papers/config.json` in the directory of its bibtex (unless a library
  configuration exists there; then that one is kept), with its explicit
  settings, `pool: none`, and `paths` as before (or `relative` with
  `--relative`, which also rewrites the links). It registers that
  directory as the default library unless another default library is set,
  and renames the old file to `papersconfig.json.v2.bak`. A configuration
  without bibtex creates no library; the file is still renamed.

Older locations of this file, moved at the start of every command
(free: when; contract: the locations):

- `$XDG_DATA_HOME/config.json` (default `~/.local/share/config.json`) on
  every platform;
- `$XDG_CONFIG_HOME/papersconfig.json` (default `~/.config/papersconfig.json`)
  on every platform (on Linux this is the current location).

If the current location does not exist, the older file is moved there.
Otherwise a warning asks the user to delete the older file.

## The machine configuration

### Location

Contract: `config.json` in the user configuration directory of the
platform, in an application folder `papers`:

| Platform | Path |
|---|---|
| Linux and other Unix | `$XDG_CONFIG_HOME/papers/config.json` (default `~/.config/papers/config.json`) |
| macOS | `~/Library/Application Support/papers/config.json` |
| Windows | `%LOCALAPPDATA%\papers\papers\config.json` |

(The Windows path repeats `papers`: author folder, then application
folder.) Other folders of the machine, for reference:

| What | Linux default | macOS | Windows |
|---|---|---|---|
| data (`history/` lives here, see `history.md`) | `~/.local/share/papers` | `~/Library/Application Support/papers` | `%LOCALAPPDATA%\papers\papers` |
| cache | `~/.cache/papers` | `~/Library/Caches/papers` | `%LOCALAPPDATA%\papers\papers\Cache` |

### Format

Contract: a JSON object with the layout of a library configuration:

```json
{
  "default": "~/Documents/papers",
  "editor": "vim",
  "history-size": 100,
  "nameformat": {"template": "{author}_{year}"},
  "version": 3
}
```

| JSON key | Meaning |
|---|---|
| `version` | `3` when written by papers; same version rules as the library configuration (greater than 3 is an error). |
| `default` | The default library: a path, written with `~` for the home directory when under it. Absent or empty: none. |
| every setting except `bibtex`, `filesdir`, `pool` | The default value for libraries that do not set it. |
| `history-dir`, `keep-deleted-files` | Machine-only settings (see `history.md`). |
| `pool` | Legacy (earlier v3 builds). Discarded on reading, with a warning unless it is `none`. |
| `pools` | Legacy: an object `{name: path}` of earlier v3 builds, used only to read `pools` lists of library configurations. Discarded when papers rewrites the file. |

Reading: a file that cannot be parsed is ignored with a warning (all
defaults apply). A missing file means no settings.

Writing (free except for the format): papers writes the
whole object with `version: 3`, in the format of the library
configuration (keys sorted, indent two spaces, ASCII with `\uXXXX`
escapes, LF line endings, no final newline), atomically through a
temporary file in the same directory.

`default` (contract for the meaning):

- set with `papers config --global default PATH` (PATH must be an
  existing library without pool; `none` removes the key) or
  `papers init PATH --global`;
- used outside of any library, and as the pool of `papers init --shallow`;
- read by expanding a leading `~` and making it absolute (a relative value
  is relative to the current directory).

## Settings

### Table

"Where" says which configuration may hold the setting: L = library
configuration, M = machine configuration.

| Setting | Type | Default | Where | Meaning |
|---|---|---|---|---|
| `bibtex` | path | none | L | The bibtex file. |
| `filesdir` | path | none | L | The files directory. none: files stay where they are, `file rename` is an error. |
| `pool` | `none` or path | `none` | L | The pool. See [Pools](#pools-and-shallow-libraries). |
| `paths` | `relative`, `absolute` | `relative` | L, M | File links in the bibtex: relative to the directory of the bibtex, or absolute. Setting it rewrites the links of the bibtex. |
| `files` | `ask`, `move`, `copy`, `link` | `move` | L, M | See [The files setting](#the-files-setting). |
| `auto-push` | bool | `false` | L, M | In a shallow library, commands that change entries push them to the pool (see `exchange.md`). No effect in a self-contained library. |
| `editor` | string | none | L, M | Editor command. It wins over `$VISUAL` and `$EDITOR`. |
| `checksums` | bool | `true` | L, M | Commands write checksums to `files.json` (see `history.md`). |
| `history-dir` | string | none (the data folder's `history/`) | M only | Folder of the history store. A leading `~` is expanded. |
| `history-size` | int (MB) | `500` | L, M | Machine value: the shared store. Library value: its separate store only. `0`: no limit. |
| `history-separate` | bool | `false` | L, M | The library keeps a history store of its own. |
| `keep-deleted-files` | bool | `true` | M only | Deleted files are kept by the history (else: system trash). |
| `name.template` | string | `{authorX}_{year}_{title}` | L, M | File name template. |
| `name.author-num` | int | `2` | L, M | Number of authors in `{author}`. |
| `name.author-sep` | string | `_` | L, M | Separator of authors. |
| `name.title-word-num` | int | `100` | L, M | Maximum number of title words. |
| `name.title-word-size` | int | `1` | L, M | Minimum length of a title word. |
| `name.title-length` | int | `100` | L, M | Maximum length of the title part. |
| `name.title-sep` | string | `-` | L, M | Separator of title words. |
| `name.unknown-template` | string | `unknown_{doi_or_id}` | L, M | Template for an entry without author, year or title. |
| `name.unknown-strict` | bool | `false` | L, M | Use the unknown template only when all three are missing. |
| `key.template` | string | `{author}{year}` | L, M | Key template. |
| `key.author-num` | int | `2` | L, M | |
| `key.author-sep` | string | `_` | L, M | |
| `key.title-word-num` | int | `100` | L, M | |
| `key.title-word-size` | int | `1` | L, M | |
| `key.title-length` | int | `100` | L, M | |
| `key.title-sep` | string | `-` | L, M | |
| `key.unknown-template` | string | `{doi_}` | L, M | |
| `key.unknown-strict` | bool | `false` | L, M | |
| `default` | path or none | none | M only | The default library. |

The defaults are part of the contract: a library that does not write a
setting relies on them.

### Precedence

Contract:

1. Command-line options for one command (`--bibtex`, `--filesdir`,
   `--name-*`, `--key-*`, `--move/--copy/--link` for `files`, the
   deprecated `--absolute-paths/--relative-paths`).
2. The library configuration, if it sets the setting.
3. The machine configuration, if it sets it.
4. The built-in default.

Exceptions:

- `pool` comes only from the library configuration. Without it, the pool
  is `none`. The machine configuration has no pool.
- `bibtex` and `filesdir` come only from the library configuration (or
  the command line).
- `history-dir` and `keep-deleted-files` come only from the machine
  configuration. `papers config` refuses to set them in a library.
- For the shared history store, `history-size` is the machine value; for a
  separate store, the library value (see `history.md`).
- In a shallow library, the files go to the pool's files directory, named
  with the pool's name settings: the library's `filesdir` and `name.*` are
  not used (see below). The library's `key.*` settings are used.

`papers config` (free for the display) shows the source
of each value as `library`, `global` or `default`.

## Finding the library of a command

Contract (other implementations must find the same library):

1. **`-C DIR`**: options `-C DIR` (or `-CDIR`) placed before the command
   name change the current directory before anything else. Several `-C`
   combine as in git: each is joined to the previous one (an absolute one
   replaces it). A `DIR` that is not a directory is an error.
2. **Search upwards**: from the current directory (made absolute, symbolic
   links not resolved), look in each directory for `.papers/config.json`
   or `.papersconfig.json` (both in one directory: an error), then in its
   parent, and so on. The filesystem root itself is never searched. The
   first directory found is the library.
3. If none is found and the global configuration of papers 2 exists, it
   is used.
4. Otherwise, if the machine configuration has a `default` and it is an
   existing directory, its library configuration is used (if the
   directory has none, there is no library).
5. Otherwise there is no library. Commands that need one stop with an
   error (`no library found here: papers init`); `papers status` and
   `papers config --global` still work.

**`--bibtex FILE`** (commands that act on a library):

- If FILE is the bibtex of the library found above (same real path), that
  library is used.
- Else, the search of step 2 runs from the directory of FILE. If it finds
  a library whose bibtex is FILE (same real path), that library is used.
- Else, FILE is used with the settings of the library found above (or the
  defaults), as a **bibtex without library**: no configuration file is
  written, no `id`, no lock, no `files.json`; its history is named from its
  path (see `history.md`).
- The bibtex path of the command is then FILE as given (relative to the
  current directory).

**`--filesdir DIR`** replaces the files directory for the command.

`papers init [DIR]` creates the library in the current directory or in
DIR (created with its parents if missing; removed again if the command
fails and they are still empty). A directory that already has a library
configuration is an error. A library inside another library is allowed
(warning). `--bibtex` and `--filesdir` of `init` are relative to the new
library directory. Defaults: bibtex `papers.bib` if it exists, else the
first existing `*.bib` of the directory (sorted by name), else `papers.bib`; files directory `files`,
or the first existing one of `files`, `pdfs`, `pdf`, `papers`,
`bibliography`. `init` creates the empty bibtex and, for a self-contained
library, the files directory (free: the defaults of
`init` are behaviour, not file format).

## Pools and shallow libraries

The exchanges with a pool (`add`, `pull`, `push`, `sync`, the repair of
links) are specified in `exchange.md`. This section covers the setting
and the states it gives.

### The pool setting

Values:

- `none` (also the value when the key is absent): no pool.
- a path: relative to the library directory (`../shared`, `./sub`), with
  a leading `~`, or absolute.

How papers writes a path given by the user (contract, so that libraries
move with their folder):

- if the path was given relative, or points to the library directory or
  inside it: written relative to the library directory, starting with `.`
  (`./x` added when the relative path does not start with `.`);
- otherwise: absolute, with `~` for the home directory when under it.

The base of a relative path given by the user: the library directory for
`papers init --pool PATH`; the current directory for
`papers config pool PATH`. `papers init --shallow` takes the `default` of
the machine configuration as written (usually with `~`).

### States

Contract:

- **Self-contained**: `pool` is `none`.
- **Shallow**: the library has a configuration file, its `pool` is a
  path, and that path (real path) is not the library directory itself.
- **Its own pool**: a `pool` that resolves to the library directory (for
  example `.`). The library is then treated exactly as having no pool: it
  is not shallow and has no pool. `papers init --pool PATH` refuses it;
  `papers config pool .` accepts it.
- There is no marker of being a pool: any self-contained library can be a
  pool.

Rules on the pool (contract for the conditions; the checks are behaviour):

- The pool must be an existing library (a directory with a library
  configuration) without pool of its own. `init --pool`, `config pool`,
  `config --global default` and `--pool PATH` on the exchange commands
  check this and stop otherwise, changing nothing.
- A pool that is missing or not a library: commands that only read it
  print a warning and go on without it; commands that write to it stop
  with an error. The parent directory missing is reported as a possible
  unmounted disk.

### Files of a shallow library

- New files go to the **files directory of the pool**, named with the
  **pool's** `name.*` settings. The library's `filesdir` is not used,
  except as the destination of `papers config pool none`; its `name.*`
  settings are ignored (a warning when the library sets `name.template`).
- A pool without files directory: adding a file is an error.
- The file links of the library entries are the pool entries' links.
- `papers init --pool` writes `filesdir` (default `files`) but does not
  create the folder.
- Changing the pool moves files (the repair of broken links before
  `pool none`: `exchange.md` section 15.3):
  - `pool none` in a shallow library: the pool files the library links to
    are copied (hard links when possible) into the library's files
    directory, and the links follow;
  - `pool PATH` in a self-contained library: each file of the library must
    already be in the matching pool entry (same file or same content); the
    library then links to the pool's copy and its own copy is deleted.
    Otherwise nothing changes and the entries are named.
  papers lists the changes and asks first (`-y`, `--dry-run`; without a
  terminal, an error).

## The files directory

### The files setting

What `add`, `file attach` and `file rename` do with each file of an
entry. The modes are `move`, `copy` (a hard link when possible, else a
copy), `link` (the file stays where it is and is linked there), and `ask`
(asked per file: `m`, `c`, `l`; uppercase answers apply to all the next
files; Enter is `link`; without a terminal every file is linked, with a
warning). The rules, in order (the first that applies decides):

1. a file that papers downloaded into its temporary folder: move;
2. a file the command must leave in place (for example the files an entry
   had before `file attach`): link;
3. mode `link`: link;
4. a file that `file fix` found: copy (link if it is already in the
   pool's files directory, in a shallow library);
5. a file already inside the files directory: move (renamed in place);
   in a shallow library, a file already in the pool's files directory:
   link (never renamed: other libraries may link to it);
6. a file of a pool entry: copy (link in a shallow library);
7. a file inside the files directory of a pool: copy;
8. otherwise the mode (asked, with `ask`). A `move` of a file that lies in
   the files directory of another library becomes a copy. "Another
   library" means: a library configuration found from the file's
   directory upwards, other than the current library, whose files
   directory contains the file.

The mode set, the rules are behaviour that another implementation should
follow so that files are not lost; the exact prompts are free.

### File names

Contract:

- The first file of an entry is placed at
  `<files directory>/<name><ext>`, where `<name>` is the name template
  applied to the entry (see below) and `<ext>` is the extension of the
  file's current name (the part from the last `.` of the base name, case
  kept; empty if none).
- The name may contain `/` (and `\` on Windows) from the template itself:
  it then names subfolders of the files directory, created as needed.
- Each other file of the entry is placed at
  `<files directory>/<name>--<label><ext>`. `<label>` is the base name of
  the file without its extension, with a leading `<prefix>--` removed when
  `<prefix>` is the current base name (without extension) of the first
  file or the base name of `<name>`, and the label would not be empty. So
  a second rename keeps the label.
- When two files of one entry get the same path, the later ones get
  `-2`, `-3`, … appended to the label: `<name>--<label>-2<ext>`.
  Comparison is case-insensitive on Windows only.
- A file of another entry is never replaced. When the destination path
  exists (a file, a folder or a symbolic link):
  - if it is the file itself (same real path), or a file with the same
    content (same sha256), that path is used: the source is removed (move)
    or nothing is done (copy), and the entry links to that path. Two
    entries can so link to one file;
  - otherwise `-2` is inserted before the extension (the part from the
    last `.` of the base name), then `-3`, and so on, until a path is free
    or holds the file itself or the same content:
    `<name>-2<ext>`, `<name>--<label>-2<ext>`.

  This applies to each file of the entry, after the suffixes between the
  files of one entry. A rename later finds the file at its suffixed name
  (the file itself) and leaves it there while the plain name is taken.
- A case-only rename on a case-insensitive file system renames the file
  in place.
- Files of the layout of papers before 2.19 (a folder `<name>/` with a
  hidden `.<name>.bib`) are moved into the flat layout when renamed; the
  folder is removed when only the hidden bibtex is left.

## Name and key templates

### Syntax

A template is text with placeholders `{name}`. `{{` and `}}` are literal
braces. An unknown placeholder is an error that lists the available ones.
papers formats templates with Python's format syntax, so format
specifications (`{title:.20}`) and indexing also work there; this is not
part of the contract (see [Open questions](#open-questions)).

### Placeholders

Contract. Input: the fields of the entry. A missing `author` is
`unknown`, a missing `year` is `0000`, a missing `title` is empty.

**Author names.** The `author` field is lowercased and formatted as
`check --format-name` does (`bibtex.md` section 3.5: split at brace
depth 0, each name as "family, given"; a name in braces stays whole).
The result is split on ` and `, and the family name of each author is
the text before its first comma (`John {van der Berg}` gives
`{van der berg}`). These two splits do not look at braces (see
`bibtex.md`, open question 16). Each family name is slugified (see
below). Then:

| Placeholder | Value |
|---|---|
| `author` | The first `author-num` slugs, joined with `author-sep`. |
| `Author` | Same, each slug with its first character uppercased (the rest stays lowercase). |
| `AUTHOR` | `author` uppercased. |
| `AuthorX` | From all authors, first character uppercased: one author: `A`; two: `A and B`; three or more: `A et al`; then spaces replaced by `author-sep`. |
| `authorX` | `AuthorX` lowercased. |

Examples with `author-sep` `_`: `doe`, `doe_and_smith`, `doe_et_al`.

**Title.** If `title-word-num` is 0 or the title is empty: empty.
Otherwise: slugify the title, split on `-`, keep the words of at least
`title-word-size` characters, keep the first `title-word-num` of them,
then drop the last word while more than one word remains and the words
joined with `title-sep` are longer than `title-length`; if the one word
left is longer than `title-length`, cut it to that length.

| Placeholder | Value |
|---|---|
| `title` | The words joined with `title-sep`. |
| `Title` | The words, each with its first character uppercased, joined with `title-sep`. |

**Other fields.** "Path-safe" means: `/`, `\` and NUL replaced by `-`;
a non-empty value made only of dots replaced by as many `-`.

| Placeholder | Value |
|---|---|
| `year` | The `year` field (or `0000`), path-safe. |
| `journal` | The `journal` field, path-safe. A missing journal gives the text `None` (see [Open questions](#open-questions)). |
| `key`, `ID` | The entry key, path-safe. |
| `doi` | The `doi` field (or empty), path-safe. |
| `doi_` | The `doi` field slugified. |
| `doi_or_id` | The `doi` field slugified, or the key slugified if there is no doi. |

**Slugify.** In order:

1. each run of `'` replaced by `-`;
2. Unicode NFKD, then transliteration to ASCII (`ü` → `u`, `ß` → `ss`,
   `Œ` → `oe`, other scripts romanised);
3. HTML entities decoded: named (`&amp;`), decimal (`&#38;`) and
   hexadecimal (`&#x26;`);
4. Unicode NFKD again; lower case;
5. remaining `'` removed; a `,` between two digits removed;
6. each run of characters other than `a-z` and `0-9` and `-` replaced by
   `-`; runs of `-` collapsed to one; leading and trailing `-` removed.

Examples: `Müller` → `muller`, `l'eau` → `l-eau`,
`10.1000/xyz(1)` → `10-1000-xyz-1`, `1,000` → `1000`. The transliteration table is that of
the Unidecode family; another implementation must use a compatible table
to produce the same names (see [Open questions](#open-questions)).

**Unknown entries.** When `unknown-template` is non-empty and the entry is
"unknown", the unknown template is used instead of the template. An
entry is unknown when its `author` field is missing or equal to
`unknown`, its `year` is missing or equal to `0000`, or its `title` is
missing or empty: any of the three, or all three with `unknown-strict`.

### File names

The name template gives `<name>` (see [File names](#file-names)). The
whole result is checked by the path safety rule below. There is no limit
on the length of the whole name; only the title part is limited by
`title-length`.

### Keys

- The key template gives a key for entries created from a PDF or a DOI,
  for entries without key, and with `--update-key`/`--auto-key`. Entries
  added from a bibtex file keep their key otherwise.
- Collisions: the letter suffix rule of `bibtex.md` section 8. The
  entry's own key does not count as taken: an entry whose key is already
  the template's keeps it (`check --auto-key` leaves `smith2000` as it
  is).
- The key is not otherwise transformed: the template decides its
  characters (bibtex key validity is in `bibtex.md`).

## Path safety

Contract: no field of an entry may make papers write a file outside the
intended folder.

1. The placeholders `year`, `journal`, `key`, `ID`, `doi` are path-safe
   (separators and NUL replaced, all-dot values replaced). The other
   placeholders are slugs, which contain no separator.
2. After formatting, the target is the files directory (absolute) joined
   with the name, normalised lexically (`.` and `..` resolved, without
   following symbolic links). If the target is not strictly inside the
   files directory (it is the directory itself, or the common path of the
   two is not the files directory), papers refuses: an error names the
   entry, and its files stay where they are with their links unchanged.
   This covers templates such as `../{author}`, `/tmp/{author}`,
   `{author}/../../x` and `.`.
3. Labels of the other files come from base names, which contain no
   separator.
4. Templates may still create subfolders (`{year}/{author}`): separators
   from the template itself are kept.

Other names derived from data (origin file names) are slugified (see
`exchange.md`).

## The lock: `.papers/lock`

A command that writes a library holds its lock, so that two commands (or
papers and another program following the same rules) do not write it at
the same time. Everything in this section is contract, except the values
marked as free.

### File

- Path: `.papers/lock` in the library directory (`.papers/` is created if
  missing). A bibtex without library has no lock. Nothing is locked with
  `--dry-run`.
- Content: a JSON object:

  ```json
  {"token": "3f9a0c2e5b8d4a7f9e1c6b2d8a4f0e3c", "pid": 12345, "host": "laptop", "command": "papers add paper.pdf"}
  ```

  | Key | Meaning |
  |---|---|
  | `token` | 32 random hexadecimal characters, new for each acquisition. Identifies the holder. |
  | `pid` | Process id of the holder (integer). |
  | `host` | Host name of the holder's computer. |
  | `command` | The command line, for messages. |

### Protocol

**Acquire.**

1. Create the file exclusively (fail if it exists) and write the JSON.
   Success: the lock is held.
2. Otherwise read the file. A file that cannot be parsed, or is not an
   object, counts as "being written" (empty content). Record its
   signature: modification time (nanoseconds), size and inode.
3. The lock is **stale** if either:
   - its signature has not changed for `LIFETIME` seconds, measured on the
     waiting command's own monotonic clock from the moment it first saw
     that signature (the clocks of two computers are never compared; a
     waiter always observes for at least `LIFETIME`);
   - or its `host` is this computer's host name, its `pid` is an integer,
     and no process with that pid exists (not checked on Windows).
4. A stale lock is taken over, then the command goes back to step 1:
   1. rename `.papers/lock` to `.papers/lock.<hex>.stale`, `<hex>` 32
      random hexadecimal characters (if the file is gone, nothing to do).
      The rename is atomic: of two waiters, only one gets the file;
   2. if the signature of the renamed file is the one judged stale, remove
      it;
   3. otherwise the renamed file is a fresh lock that another command
      created meanwhile: put it back as `.papers/lock` with a hard link
      (which fails if a lock was created there again meanwhile; the fresh
      lock is then not put back), and remove the renamed name.
5. Otherwise wait `POLL` seconds and go back to step 1. After `WAIT`
   seconds the command stops with an error naming the holder.

**Refresh.** While it holds the lock, the holder sets the modification
time of the file to the current time every `REFRESH` seconds, if the file
still has its token. The file is never rewritten, so a holder that lost
its lock cannot overwrite the lock of the command that took it over. (A
refresh between the token read and the time change can touch a lock just
taken over: it only keeps that lock fresh.)

**Check before writing.** Before it writes the library, the holder reads
the lock:

- another token: the lock was taken over. The command stops, writing
  nothing more;
- no file (removed by a command that found it stale): the holder creates
  it again exclusively; if that fails, it stops as above;
- unreadable content: go on.

**Release.** At the end of the command (also after an error or an
interrupt, and at process exit), the holder removes the file if it still
has its token.

**Order.** A command locks the library of the command line first (when it
writes), then each pool or other library it opens while it holds a lock
(before it reads it). A command run in the pool locks the pool only. A
command also takes the lock just before saving a library if it did not
take it at the start.

**Values.**

| Name | Value | Status |
|---|---|---|
| `LIFETIME` | 10 s | contract (a holder must refresh well within it) |
| `REFRESH` | 2 s | contract upper bound in practice; must be well below `LIFETIME` |
| `WAIT` | 30 s | free |
| `POLL` | 0.1 s | free |

A lock does not help in a folder synchronised by a service (Dropbox,
Nextcloud): the file reaches the other computers too late.

Commands that do not write (`list` without a writing action, `status`)
take no lock. `init`, `config` and `migrate` take no lock at the start;
`config` takes it when it saves the bibtex (for example `config paths`,
`config pool`).

## Open questions

1. **`.papers/` of the bibtex directory vs of the library directory.**
   `config.json`, `lock` and `files.json` are under the library directory
   (papers/config.py:249, papers/lock.py:62, papers/checksums.py:23-27), but
   `distinct.json` and `origin/` are under the directory of the bibtex
   (papers/duplicate.py:318, papers/pools.py:552). The history lists the
   `.papers/` files relative to the bibtex directory
   (papers/backup.py:101-109), so `files.json` is not recorded when the
   bibtex is in a subfolder. Which folder is intended?
2. **`{journal}` of an entry without journal is `None`.**
   papers/filename.py:83 uses `None` as the default, and the formatting
   prints it as the text `None`.
3. **Template syntax is Python's.** papers/filename.py:131 uses
   `str.format`, which accepts format specs, conversions and indexing.
   Should the contract be only `{name}`, `{{`, `}}`? The docstring at
   papers/filename.py:157 also claims that other case variants
   (`{AuTHoR}`) read the entry field; they are an unknown-placeholder
   error.
4. **Slugify transliteration is not pinned.** The names depend on the
   transliteration library chosen by python-slugify at run time
   (`text-unidecode` or `Unidecode`), papers/filename.py:4. A Rust
   implementation needs a fixed table.
5. **No file-name length or character limit.** Only the title part is
   limited (papers/filename.py:8-17). Path-safe values keep characters
   invalid on Windows (`: * ? " < > |`), papers/filename.py:36-46, for
   example in `{journal}` or `{doi}`.
6. **Values in config.json are not type-checked.**
   papers/config.py:671-674 sets whatever JSON value is present
   (`"auto-push": "no"` is true; `"pool": 3` fails later). A library
   configuration that is not valid JSON is an unhandled error
   (papers/config.py:650), whereas an invalid machine configuration is
   ignored with a warning (papers/config.py:360-363).
7. **Unknown keys are dropped on save.** `tojson` writes only known
   settings (papers/config.py:612-628). A newer implementation's keys
   would be lost when papers saves the file. Should unknown keys be kept?
8. **`~` in `bibtex`/`filesdir` is not expanded**
   (papers/config.py:604-609), whereas it is in `pool`
   (papers/config.py:564) and `default` (papers/config.py:389).
9. **Relative `default` and `history-dir` resolve against the current
   directory** (papers/config.py:389, papers/backup.py:45), not against
   the machine configuration's folder.
10. **The configured pool is not re-checked for a pool of its own.** The
    check is done when the setting is made (papers/pools.py:180-191) and
    for `--pool PATH` (papers/pools.py:194-198, 427-431), but not when the
    configured pool is resolved (papers/pools.py:375-399, 406-419). A pool
    that later takes a pool is still used.
11. **`papers config pool .` is accepted, `papers init --pool .` is
    refused.** papers/cli/library_cmds.py:410 checks only when the new
    value gives a pool; papers/cli/library_cmds.py:57 refuses it.
12. **Base of a relative pool path differs.** `init --pool` is relative to
    the library directory (papers/cli/library_cmds.py:56), `config pool`
    to the current directory (papers/cli/library_cmds.py:407).
13. **Locks of two libraries in opposite orders.** A command in L1 with
    `--pool L2` and a command in L2 with `--pool L1` each hold one lock
    and wait for the other; one fails after `WAIT`
    (papers/pools.py:395-396).
14. **`.gitignore` only on configuration save.** papers/config.py:642-643:
    a `.papers/` created by the lock, the `id` or the origin records of a
    library whose configuration papers never saved (for example a
    `.papersconfig.json` library) has no `.gitignore`.
15. **Machine configuration drops the legacy `pools` names.** The names of
    earlier v3 builds are taken out when the file is read
    (papers/config.py:351) and not written back
    (papers/config.py:391-395): the first save of the machine
    configuration loses them, while unsaved earlier-v3 libraries still
    need them to find their pool.
16. **Legacy global location comment.** papers/library.py:21 says
    `~/.local/share/papers/config.json`; the code checks
    `$XDG_DATA_HOME/config.json` (papers/config.py:39), which matches what
    old versions wrote. The docstring or the path is wrong.
17. **`id` written into `.papersconfig.json`.** The `id` is added to a
    legacy file in place (papers/config.py:482-487), while any other save
    moves it to `.papers/config.json` first (papers/config.py:637-638).
18. **Install docstring.** papers/install.py:290 says the default target
    is `.papersconfig.json`; the code uses `.papers/config.json`
    (papers/install.py:304).
19. **Configuration files are read in the platform's encoding.** papers
    writes `config.json` (library and machine) and `.gitignore` as UTF-8
    (ASCII with escapes for the JSON), but reads them without naming an
    encoding (papers/config.py:242, 361, 486, 650): a file of another
    implementation with raw UTF-8 characters outside ASCII (a path in
    `bibtex`, an `editor` command) is misread on Windows with a non-UTF-8
    locale. Read them as UTF-8?
20. **A fresh lock renamed aside is lost without hard links.** The
    takeover puts a fresh lock back with a hard link
    (papers/lock.py:97-113); on a file system without hard links (some
    network or FAT drives) the link fails and the fresh lock is removed.
    Its holder finds no file at its next check and creates it again
    (papers/lock.py:190), but it may have written files in between, and
    another waiter may take the lock meanwhile.
