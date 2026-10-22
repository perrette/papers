# Pools

## Libraries and pools

A **library** is a bibtex file, a files directory and a configuration file
(`.papersconfig.json`), as created by `papers init` (see
[Configuration](configuration.md#libraries)). Each project usually has its
own library.

A **pool** is a library that other libraries exchange entries with. Nothing
in the pool marks it as a pool: a library acts as a pool when another
library lists it in its `pools` setting. Any library can serve as a pool,
and a pool can be used by several libraries. Separate pools (e.g. one per
research field) are separate folders.

A library lists its pools as names or paths:

```
papers config pools default ../shared-with-bob
```

A name is looked up in the global configuration (`papers pool add`,
below), so that the same project works on machines where the pool is in a
different place. A path (it contains a `/`, or starts with `.` or `~`) is
relative to the library. Without global configuration, the name
`default` is `~/Documents/papers`, and a library created without `--pool`
has `"pools": ["default"]`. A library never uses itself as a pool.

What a library does with its pools:

- `papers add` looks in the pools first;
- `papers pull` updates the entries of the library from the pools;
- `papers push` adds entries of the library to its first pool, or updates
  them there;
- `papers status` and `papers pull --check` tell whether a pool changed
  since the last pull.

Nothing is pulled or pushed automatically, except with the `sync` setting
and in light libraries (below): an older project does not change because of
work in a newer one.

A **light library** has no files of its own: its file links point to the
files of its first pool (see [Light libraries](#light-libraries)).

## Keys and identity

The key of an entry belongs to each library: it is what LaTeX documents
cite. `pull` and `push` never change the key of the library they write to.
A pool may name the same paper differently, and an entry new to a pool gets
a key from the pool's key template.

A library entry and a pool entry are matched by the same rule as duplicates
(see [Same paper](adding-entries.md#same-paper)): same DOI, arXiv
identifier, ISBN (two books), or else the same authors and title. The pairs
recorded as "not the same paper" (`.papers/distinct.json`) are merged both
ways on `pull` and `push`.

## Origin copies

`.papers/origin.bib`, next to the bibtex of the library, records for each
entry taken from a pool (by `add`, `pull` or `push`) the pool's version of
the entry at that time, under the library's key, with the pool it came from
(`papers-pool`), the key in the pool (`papers-pool-key`) and the time
(`papers-time`). It also records the modification time of each pool's
bibtex at the last pull. The file is part of the git backup of the library
(see [Git integration](git.md)).

The origin copy is the third version of a three-way merge: comparing the
library entry and the pool entry with it tells which side changed a field.

## `add` looks in the pools first

When the paper added is already in a pool, `papers add` takes the pool's
entry, without querying crossref:

- a PDF with the same content as a file of a pool entry, or whose DOI (from
  the PDF metadata, or a DOI of its text whose title in the pool appears in
  the text) is in a pool;
- a DOI (`papers add --doi DOI`) that a pool entry has;
- an entry of an added bibtex that is the same paper as a pool entry: the
  pool's fields are taken, the entry keeps its key, and its fields that the
  pool entry does not have are kept.

The entry gets the pool's files: in `copy` and `move` mode they are copied
into the library's files directory (a hard link when possible), named with
the library's name template; a pool file is never moved. In `link` mode,
and in a light library, the entry links to the pool's file. The origin copy
is recorded. `--no-pool` skips the lookup.

With `papers config sync push` (default `none`), `add` also adds the entries
new to the library to the first pool, as `papers push` would. Changes to
existing entries are never pushed automatically.

## `papers pull`

```
papers pull [KEY...|-] [--on-duplicate MODE] [--check]
```

For each entry of the library (or the entries named), papers finds its pool
entry (the pool of the origin copy first, then the pools in order) and
merges it into the library entry, field by field:

| Field changed since the origin copy | Result |
|---|---|
| in the pool only | taken from the pool (`+` in the dialogue) |
| in the library only (e.g. a field adapted to a journal style) | kept, without asking |
| on both sides, to different values | a conflict (`!`) |

A field removed on one side keeps the other side's state: removed in the
pool, it stays in the library; removed in the library, it does not come
back. File links are merged: new files of the pool entry are copied into
the library's files directory as the `files` setting says (linked in `link`
mode and in light libraries). The key of the library entry never changes.
After the merge, the origin copy is the pool's current version.

An entry without origin copy (added before the pool was used, or with
`--no-pool`) is matched to the pools by the same-paper rule. Its differences
with the pool entry are conflicts (there is no origin to tell which side
changed), and the origin copy is recorded afterwards ("linked").

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

`papers pull --check` only reports: whether each pool changed since the last
pull (a modification time check), and the entries whose pool version
changed since their origin copy, with the fields. `papers status` shows the
first part too.

## `papers push`

```
papers push [KEY...|-] [--pool NAME|PATH] [--on-duplicate MODE]
```

The reverse of `pull`, into the first pool (or `--pool`):

- an entry that is not in the pool is added to it, with a key from the
  pool's key template; its files are copied into the pool's files directory
  (a hard link when possible), named with the pool's name template;
- an entry that is in the pool is merged three-way into the pool entry:
  fields changed in the library only are taken, fields changed in the pool
  only are kept, conflicts are decided with `--on-duplicate` (`keep`: the
  pool values, `update`: the library values). The pool key does not change.

The origin copies are updated. The default pool is created the first time
something is pushed to it.

## `papers export`

```
papers export DIR [KEY...|-] [--files copy|link|none] [--pool]
```

writes the entries (all without KEY) as a new library in `DIR`, which must
not exist or be empty: its bibtex, its files directory, and its
configuration (with the name and key templates that the library sets). File
links are relative to the new bibtex.

- `--files copy` (default) copies the files into `DIR/files` (hard links
  when possible), named with the name template;
- `--files link` links to the files where they are;
- `--files none` leaves the file links out.

`--pool` also adds `DIR` to the pools of the library, and records the
exported entries as origin copies: this turns a library into a pool.
`papers add DIR --recursive` adds an exported library to another one.

## `papers pool`

The pool names of the global configuration:

```
papers pool add NAME PATH      # same as: papers config --global pools.NAME PATH
papers pool remove NAME
papers pool list               # or: papers pool
```

`papers pool list` shows the pools of the global configuration and those of the current
library, with their paths and whether each changed since the last pull.

## Light libraries

A light library links to the files of its first pool instead of keeping its
own. This saves the copies when many projects use the same papers. Being
light changes what papers does with files:

- `add` places new files in the first pool, named with the pool's name
  template (a name template set on the light library is not used), and so
  adds the entry to the pool too; `papers file attach` and
  `papers file rename` do the same with the files they place;
- `pull` links to the pool's files instead of copying them;
- `rm --delete-files` and `file rm` never delete a file
  of a pool (this holds in any library);
- when a pool renames a file, the link breaks: it is repaired by looking the
  entry up in the pools, when the library is loaded (saved on the next
  write) and by `papers file check --fix`.

`light` is not a setting of `papers config`, because changing it changes
the links and the files:

- `papers migrate --light` replaces each file that the first pool has for
  the same paper, with the same content (checksum), by a link to the pool's
  file, and deletes the library's copy in its files directory. A file that
  is not in the pool is never deleted: the command lists those entries and
  asks to `papers push` them first. Then the library is light.
- `papers migrate --full` copies (hard links when possible) the pool files
  that the library links to into its files directory, named with its name
  template, and relinks them. Then the library is not light any more.

`papers init --light` creates a light library.

Deleting a file in a pool breaks the links of the light libraries that use
it: it shows up as a broken link there (`papers file check`). The pool
keeps no list of the libraries that depend on it.

## Example

A shared pool in `~/Documents/papers`, and two projects:

```
papers init ~/Documents/papers            # the default pool
mkdir -p ~/projects/sealevel ~/projects/tides
cd ~/projects/sealevel
papers init                               # pools: default
papers add ~/Downloads/esd-4-11-2013.pdf  # fetched from crossref, files/...
papers push                               # now also in ~/Documents/papers

cd ~/projects/tides
papers init
papers add --doi 10.5194/esd-4-11-2013    # taken from the pool: no query, the file is copied
```

Later, the entry is completed in the pool (e.g. its pages), and adapted in
`tides` (a journal abbreviation):

```
cd ~/projects/tides
papers status                  # pools: ... (changed since last pull)
papers pull --check            # perrette_landerer2013: changed in pool default: pages
papers pull                    # pages taken; the journal abbreviation is kept
```

A project shared with a colleague: export it as its own library, used as a
second pool by both:

```
cd ~/projects/sealevel
papers export ../shared-with-bob --pool   # pools: default ../shared-with-bob
papers push --pool ../shared-with-bob     # later changes
```

To save disk space in `tides`, make it light once its files are in the
pool:

```
papers push
papers migrate --light
```
