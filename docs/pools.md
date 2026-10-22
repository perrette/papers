# Pools

## Libraries and pools

A **library** is a bibtex file, a files directory and a configuration file
(`.papersconfig.json`), as created by `papers init` (see
[Configuration](configuration.md#libraries)). Each project usually has its
own library.

A **pool** is a library that other libraries exchange entries with. Nothing
in the pool marks it as a pool: any library can serve as one, and a pool can
be used by several libraries. A library has one pool, its `pool` setting:

- by default, the **global pool**: the `pool` setting of the global
  configuration, `~/Documents/papers` unless set otherwise
  (`papers config --global pool PATH`). A library that uses the global pool
  stores no path: the same project, copied to another machine, uses the
  global pool of that machine;
- a path, set with `papers init --pool PATH` or `papers config pool PATH`. A
  path written relative, or under the library, is stored relative to the
  library (e.g. `../shared-with-bob`); another path is stored as given;
- `none`: the library exchanges entries with no pool.

The global pool does not have to exist: papers creates it (as
`papers init ~/Documents/papers` would) the first time it writes to it, and
before that a library finds nothing in it, without a warning. A pool given
by path that does not exist is a warning (a typo, a disk that is not
mounted); papers creates it when it writes to it only if its parent
directory exists.

`papers init` in the folder of the global pool creates the pool itself: a
library without pool, with its own files. Outside of any library, commands
act on the global pool once it is a library. `papers config --global pool
none` turns sharing off: new libraries get `pool: none`.

What a library does with its pool:

- `papers add` looks in the pool first;
- `papers pull` updates the entries of the library from the pool, and adds
  entries of the pool to the library;
- `papers push` adds entries of the library to the pool, or updates them
  there;
- `papers sync` does both;
- `papers status` and `papers pull --check` tell whether the pool changed
  since the last pull.

Nothing is pulled or pushed automatically, except in libraries that are not
local and with the `auto-push` setting (below): an older project does not
change because of work in a newer one.

## Local or not

The `local` setting of a library says where its files are:

- `local: false` (the default for new libraries): the files are in the files
  directory of the pool, and the library links to them. A paper used by
  several projects is stored once;
- `local: true`: the files are in the files directory of the library
  (`files/`).

`papers init --local` creates a local library; the default for new libraries
is the `local` setting of the global configuration
(`papers config --global local true`). A library without pool is local.

In a library that is not local:

- `add` places new files in the pool's files directory, named with the
  pool's name template (a name template set on the library is not used),
  and adds the entry to the pool too (its origin is recorded, see
  [Origin copies](#origin-copies)); `papers file attach` and
  `papers file rename` do the same with the files they place;
- `pull` links to the pool's files instead of copying them;
- when the pool renames a file, the link breaks: it is repaired by looking
  the entry up in the pool, when the library is loaded (saved on the next
  write) and by `papers file check --fix`.

In any library, `rm --delete-files` and `file rm` never delete a file of the
pool. Deleting a file in a pool breaks the links of the libraries that use
it: it shows up as a broken link there (`papers file check`). The pool keeps
no list of the libraries that depend on it.

A local library with `papers config auto-push true` also adds the entries
new to it to its pool when `papers add` adds them, as `papers push` would.
Changes to existing entries are never pushed automatically.

### Sharing a project folder

A project folder shared with coauthors (git, Dropbox...) should be a local
library (`papers init --local`, or `papers config local true`): the links of
a library that is not local point into your own pool, which the others do
not have.

A pool can be in a folder synchronized by a cloud client on the local disk
(e.g. `papers config --global pool ~/Dropbox/papers`): papers reads and
writes the files there, and the client synchronizes them.

### Changing `local` and `pool`

Changing these settings moves the files of the library. papers lists what
it will do and asks `Continue? [y/N]`; `-y` answers yes, `--dry-run` only
shows the list, and without a terminal the command stops with the list
(pass `-y`). A file that is not safely in a pool is never deleted, and the
files of a pool are never deleted.

| Command | In a library that is not local | In a local library |
|---|---|---|
| `papers config local true` | the pool files it links to are copied into its files directory (hard links when possible), named with its name template, and the links rewritten; the pool keeps its files | nothing to do |
| `papers config local false` | nothing to do | the files of its files directory go to the pool: a file that the pool entry of the same paper has (same content) becomes a link to the pool's copy, and the library's copy is deleted; the others are moved into the pool's files directory with the pool's name template and attached to the pool entry; entries that the pool does not have are added to it; the links are rewritten |
| `papers config pool none` | as `local true`, and the library becomes local | the setting changes |
| `papers config pool PATH` (or `--unset pool`: the global pool) | the files go to the new pool, as with `local false`; the files of the former pool are copied there (hard links when possible), since other projects may use them | the setting changes |

Metadata is not merged by these commands: `papers push` does that.

## Keys and identity

The key of an entry belongs to each library: it is what LaTeX documents
cite. `pull` and `push` never change the key of an entry that the library
they write to has. An entry new to the pool gets a key from the pool's key
template; an entry of the pool new to the library keeps the pool key, with
a letter suffix if the library has that key already (`Smith_2020b`).

A library entry and a pool entry are matched by the same rule as duplicates
(see [Same paper](adding-entries.md#same-paper)): same DOI, arXiv
identifier, ISBN (two books), or else the same authors and title. The pairs
recorded as "not the same paper" (`.papers/distinct.json`) are merged both
ways on `pull` and `push`.

## Origin copies

`.papers/origin.bib`, next to the bibtex of the library, records for each
entry taken from a pool (by `add`, `pull` or `push`) the pool's version of
the entry at that time, under the library's key, with the pool it came from
(`papers-pool`: `global` for the global pool, otherwise the path of the
pool relative to the library), the key in the pool (`papers-pool-key`) and
the time (`papers-time`). It also records the modification time of the
pool's bibtex at the last pull. The file is part of the git backup of the
library (see [Git integration](git.md)).

The origin copy is the third version of a three-way merge: comparing the
library entry and the pool entry with it tells which side changed a field.

`papers add other.bib` copies the entries of `other.bib` once, and keeps no
memory of where they came from. The entries taken with `papers pull` stay
linked to the pool through their origin copy: later pulls bring the
corrections made in the pool.

## `add` looks in the pool first

When the paper added is already in the pool, `papers add` takes the pool's
entry, without querying crossref:

- a PDF with the same content as a file of a pool entry, or whose DOI (from
  the PDF metadata, or a DOI of its text whose title in the pool appears in
  the text) is in the pool;
- a DOI (`papers add --doi DOI`) that a pool entry has;
- an entry of an added bibtex that is the same paper as a pool entry: the
  pool's fields are taken, the entry keeps its key, and its fields that the
  pool entry does not have are kept.

The entry gets the pool's files: in a local library in `copy` and `move`
mode they are copied into the library's files directory (a hard link when
possible), named with the library's name template; a pool file is never
moved. In `link` mode, and in a library that is not local, the entry links
to the pool's file. The origin copy is recorded. `--no-pool` skips the
lookup.

## `papers pull`

```
papers pull [KEY...|-] [--all] [--pool PATH] [--on-duplicate MODE] [--check]
```

For each entry of the library (or the entries named), papers finds its pool
entry (by its origin copy, else by the same-paper rule) and merges it into
the library entry, field by field:

| Field changed since the origin copy | Result |
|---|---|
| in the pool only | taken from the pool (`+` in the dialogue) |
| in the library only (e.g. a field adapted to a journal style) | kept, without asking |
| on both sides, to different values | a conflict (`!`) |

A field removed on one side keeps the other side's state: removed in the
pool, it stays in the library; removed in the library, it does not come
back. File links are merged: new files of the pool entry are linked in a
library that is not local, and otherwise copied into the library's files
directory as the `files` setting says. The key of the library entry never
changes. After the merge, the origin copy is the pool's current version.

An entry without origin copy (added before the pool was used, or with
`--no-pool`) is matched to the pool by the same-paper rule. Its differences
with the pool entry are conflicts (there is no origin to tell which side
changed), and the origin copy is recorded afterwards ("linked").

A KEY is looked up in the library first, then in the pool (its key, DOI,
arXiv identifier or ISBN): an entry of the pool that the library does not
have is added to it, with its origin copy (`added`), under the pool key
(see [Keys and identity](#keys-and-identity)); its files are linked in a
library that is not local, otherwise copied as the `files` setting says (a
hard link when possible). An identifier found in neither is an error, and
nothing is changed. `--all` adds every entry of the pool that the library
does not have (same-paper rule). Without KEY or `--all`, `pull` only updates
the entries of the library.

`--pool PATH` pulls from another pool, once: the origin copies record that
pool.

Conflicts are decided as for duplicates (see
[The dialogue](adding-entries.md#the-dialogue)), with `--on-duplicate`:

| Mode | Conflicts |
|---|---|
| `ask` (default in a terminal) | the dialogue: `1` keeps the library values, `2` takes the pool values, `f` goes field by field (also through the changes from the pool), `e` edits, `s` skips, `q` quits |
| `keep` | the library values are kept |
| `update` | the pool values are taken |
| `skip` | the entry is not changed, and its origin copy is not updated: it comes again next time |
| `error` (default without a terminal) | stop before saving anything |

Fields changed in the pool only need no decision: they are taken in every
mode.

`papers pull --check` only reports: whether the pool changed since the last
pull (a modification time check), and the entries whose pool version
changed since their origin copy, with the fields. `papers status` shows the
first part too.

## `papers push`

```
papers push [KEY...|-] [--pool PATH] [--on-duplicate MODE]
```

The reverse of `pull`, into the pool of the library (or `--pool PATH`,
once):

- an entry that is not in the pool is added to it, with a key from the
  pool's key template; its files are copied into the pool's files directory
  (a hard link when possible), named with the pool's name template;
- an entry that is in the pool is merged three-way into the pool entry:
  fields changed in the library only are taken, fields changed in the pool
  only are kept, conflicts are decided with `--on-duplicate` (`keep`: the
  pool values, `update`: the library values). The pool key does not change.

The origin copies are updated. The pool is created if it does not exist
yet.

## `papers sync`

```
papers sync [KEY...|-] [--pool PATH] [--on-duplicate MODE]
```

runs `papers pull`, then `papers push` of the same entries (all without
KEY). If the pull leaves conflicts undecided (skipped, or the dialogue
quit), nothing is pushed: decide them with `papers pull`, then sync again.

## `papers export`

```
papers export DIR [KEY...|-] [--files copy|link|none]
```

writes the entries (all without KEY) as a new library in `DIR`, which must
not exist or be empty, to hand over: its bibtex, its files directory, and
its configuration (with the name and key templates that the library sets,
`local: true` and `pool: none`). File links are relative to the new bibtex.

- `--files copy` (default) copies the files into `DIR/files` (hard links
  when possible), named with the name template;
- `--files link` links to the files where they are;
- `--files none` leaves the file links out.

`papers add DIR --recursive` adds an exported library to another one, and
`papers config pool DIR` makes it the pool of the library.

## Example

The global pool in `~/Documents/papers`, and two projects:

```
mkdir -p ~/projects/sealevel ~/projects/tides
cd ~/projects/sealevel
papers init                               # the global pool, not local
papers add ~/Downloads/esd-4-11-2013.pdf  # fetched from crossref; the PDF goes to
                                          # ~/Documents/papers/files, the entry to both

cd ~/projects/tides
papers init
papers add --doi 10.5194/esd-4-11-2013    # taken from the pool: no query, the file is linked
```

Later, the entry is completed in the pool (e.g. its pages), and adapted in
`tides` (a journal abbreviation):

```
cd ~/projects/tides
papers status                  # pool: ~/Documents/papers (global pool, changed since last pull)
papers pull --check            # perrette_landerer2013: changed in pool ~/Documents/papers: pages
papers pull                    # pages taken; the journal abbreviation is kept
```

A project shared with a colleague through git keeps its own files:

```
cd ~/projects/sealevel
papers config local true       # copies the pool files into files/ (hard links), after asking
```

A folder shared with someone as a separate pool, for one project:

```
cd ~/projects/tides
papers export ../shared-with-bob          # a library of its own
papers config pool ../shared-with-bob     # the pool of tides from now on
papers sync                               # later changes, both ways
```
