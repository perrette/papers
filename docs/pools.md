# Pools

## Libraries and pools

A **library** is a bibtex file, a files directory and a configuration file
(`.papersconfig.json`), as created by `papers init` (see
[Configuration](configuration.md#libraries)). Each project usually has its
own library.

A **pool** is a library that other libraries exchange entries with. Nothing
in the pool marks it as a pool: any library can serve as one, and a pool can
be used by several libraries. The pool of a library is its `pool` setting:

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
directory exists. The same holds for a global pool outside the home
directory (e.g. `/media/usb/papers` while the disk is not mounted): the
command stops before changing anything.

`papers init` in the folder of the global pool creates the pool itself: a
library without pool, with its own files. Outside of any library, commands
act on the global pool once it is a library. `papers config --global pool
none` turns sharing off: new libraries get `pool: none`.

What a library does with its pool:

- `papers add` looks in the pool first;
- `papers pull` updates the entries shared with the pool, and adds the
  entries of the pool named, or all of them with `--all`;
- `papers push` updates the entries shared with the pool (those taken from
  it, or added to it before), and adds the entries named, or all of them
  with `--all`;
- `papers sync` does both;
- `papers status` and `papers pull --check` tell whether the pool changed
  since the last exchange with it: `up to date`, or `changed since last
  pull or push`.

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

`.papers/origin/`, next to the bibtex of the library, holds one file per
pool: `global.bib` for the global pool, and for another pool the name of
its folder and the start of a hash of its path, e.g.
`shared-with-bob-d15650.bib`. The first lines of the file name the pool and
give the modification time of its bibtex at the last exchange. In a
library whose pool is `../shared-with-bob`, after `papers pull
agnew_farrell1978` and `papers pull`:

```
@comment{papers-pool ../shared-with-bob}

@comment{papers-pulled 1792681264781917448}

@article{agnew_farrell1978,
 author = {Agnew, D. C. and Farrell, W. E.},
 papers-pool-key = {agnew_farrell1978},
 papers-time = {2026-10-22T17:01:45+02:00},
 title = {Self-consistent equilibrium ocean tides},
 year = {1978}
}
```

Only the file of the pool of the library is used and written. The files of
earlier pools are kept: after `papers config pool PATH`, the library starts
the file of the new pool, and setting the pool back to an earlier one finds
its origin copies again. The file records, for each entry
exchanged with the pool (by `add`, `pull` or `push`), its origin copy,
under the library's key, with the key in the pool (`papers-pool-key`) and
the time (`papers-time`). The modification time is recorded at a pull of
all entries that skipped no conflict, or a push or an add when the pool
had not changed since the previous exchange (or when it is the first
exchange). A push that leaves the pool entry with fields or files that the
library entry does not have does not count: `papers status` then shows the
pool as changed until the next pull. The files are part of the git backup
of the library (see [Git integration](git.md)).

Earlier v3 beta versions kept all the origin copies in one file,
`.papers/origin.bib`: papers splits it into these files the first time it
reads it, and removes it.

The origin copy is the third version of a three-way merge: comparing the
library entry and the pool entry with it tells which side changed a field.
It is the version of the side that sent the entry, as it was sent: the pool
entry after `add` and `pull`, the library entry after `push`. What the
receiving side has beyond it is a change of that side, for the next
exchange the other way: a field that only the pool entry has comes with the
next `pull`; a field that only the library entry has goes to the pool with
the next `push`.

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
- a key (`papers add --key KEY`, with no file, DOI or other field) that a
  pool entry has, ignoring case: the entry keeps the pool key. Without such
  an entry (and without a library entry of that key), `add` stops with an
  error;
- an entry of an added bibtex that is the same paper as a pool entry: the
  pool's fields are taken, the entry keeps its key, and its fields that the
  pool entry does not have are kept.

The entry gets the pool's files: in a local library in `copy` and `move`
mode they are copied into the library's files directory (a hard link when
possible), named with the library's name template; a pool file is never
moved. In `link` mode, and in a library that is not local, the entry links
to the pool's file. A PDF given that has the same content as a file of
the pool entry is removed in `move` mode, since it is stored already, and
kept in `copy` and `link` mode; a PDF with other content is attached to
the entry as another file, placed as the files mode says. The origin copy
is recorded. `--no-pool` skips the
lookup.

## `papers pull`

```
papers pull [KEY...|-] [--all] [--pool PATH] [--on-duplicate MODE] [--check]
```

Without KEY, `pull` updates the entries shared with the pool: those with
an origin copy. For each of them (or each entry named, or every entry with
`--all`), papers finds its entry in the pool (by its origin copy,
else by the same-paper rule) and merges it into the library entry, field by
field:

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
A skipped conflict leaves the pool shown as changed in `papers status`.

An entry without origin copy (added before the pool was used, or with
`--no-pool`) is not shared: `pull` without KEY leaves it alone. Named on the
command line, or with `--all`, it is matched to the pool by the same-paper
rule. Its differences
with the pool entry are conflicts (there is no origin to tell which side
changed), and the origin copy is recorded afterwards ("linked").

An entry that the pool does not have is reported (`Not found`) only when it
is named on the command line. Without KEY, it is left as it is.

A KEY is looked up in the library first, then in the pool (its key, DOI,
arXiv identifier or ISBN): an entry of the pool that the library does not
have is added to it (`added`), with its origin copy, under the pool key
(see [Keys and identity](#keys-and-identity)); its files are linked in a
library that is not local, otherwise copied as the `files` setting says (a
hard link when possible). An identifier found in neither is an error, and
nothing is changed. `--all` adds every entry of the pool that the library
does not have (same-paper rule). Without KEY or `--all`, `pull` only
updates the entries shared with the pool, like `push` and `sync`. A pool
that does not exist or is not a library is an error of `pull`, `pull --check` and `sync`, and nothing is changed
(the global pool that was not created yet is not: there is nothing to
pull).

`--pool PATH` pulls from another library once, see
[One-time exchanges](#one-time-exchanges).

`pull` prints one line per entry added (`Added ->`), modified
(`Modified ->`), left with a conflict (`Conflict ->`) or, among the entries
named, not found in the pool (`Not found ->`), with the pool in brackets,
then the counts when more than one entry was involved: `added`,
`modified`, `skipped`, `not found`, `unchanged`, and `linked` (an entry
without origin copy, the same as its pool entry: its origin copy is
recorded). `push` prints the same lines for the
pool entries. When `add` (or `file attach`) also adds or changes the entry
in the pool, or takes it from the pool, its line says so in brackets:
`[also added to pool ~/Documents/papers]`, `[from pool ~/Documents/papers]`.

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
changed since their origin copy, with the fields (without KEY, the entries
shared with the pool). `papers status` shows the
first part too.

## `papers push`

```
papers push [KEY...|-] [--all] [--pool PATH] [--on-duplicate MODE]
```

The reverse of `pull`, into the pool of the library (or `--pool PATH`,
once, see [One-time exchanges](#one-time-exchanges)). Without KEY, only the
entries shared with the pool are pushed: those with an origin copy from it
(taken from it by `add` or `pull`, or pushed to it before). `push KEY...`
pushes the entries named, and `push --all` every entry of the library:

- an entry that is not in the pool is added to it, with a key from the
  pool's key template; its files are copied into the pool's files directory
  (a hard link when possible), named with the pool's name template;
- an entry that is in the pool is merged three-way into the pool entry:
  fields changed in the library only are taken, fields changed in the pool
  only are kept, conflicts are decided with `--on-duplicate` (`keep`: the
  pool values, `update`: the library values). The pool key does not change.

Push does not change the library: after it, the origin copy is the library
version that was pushed, and the fields that only the pool entry has come
with the next `pull` (or `papers sync`). The pool is created if it does not
exist yet.

## `papers sync`

```
papers sync [KEY...|-] [--all] [--pool PATH] [--on-duplicate MODE]
```

runs `papers pull`, then `papers push` of the same entries:

- without KEY, the entries shared with the pool (with an origin copy from
  it). An entry added to the library with `--no-pool`, or before the pool
  was used, is not exchanged: name it, or use `--all`;
- with KEY..., the entries named. A KEY that only the pool has is added to
  the library, as with `pull`, and a KEY that only the library has is
  added to the pool, as with `push`;
- with `--all`, `pull --all` then `push --all`: each side gets the entries
  it does not have.

If the pull leaves conflicts undecided (skipped, or the dialogue quit),
nothing is pushed: decide them with `papers pull`, then sync again. When
nothing changed, `sync` prints one line:

```
$ papers sync
nothing to sync with pool ~/Documents/papers (2 entries unchanged)
```

## One-time exchanges

`--pool PATH` on `pull`, `push` and `sync` exchanges with the library at
`PATH` once, e.g. a folder shared with a coauthor. It reads and writes only
that library, not the pool of the library, and records no origin copy: no
entry becomes shared with it, and the origin copies of the pool do not
change. When `PATH` is the pool of the library, `--pool PATH` is the usual
exchange.

- `papers sync --pool PATH KEY...` takes the entries named from `PATH`
  that the library does not have, sends to `PATH` those that it does not
  have, and merges the others both ways;
- `papers pull --pool PATH --all` takes every entry of `PATH`, and
  `papers push --pool PATH --all` sends every entry of the library;
- an entry taken from `PATH` is shared with no pool; an entry sent to
  `PATH` stays shared with the pool of the library if it was.

Without an origin copy, there is nothing to tell which side changed a
field: each field that differs is a conflict, decided in the dialogue or
with `--on-duplicate`. Without KEY or `--all`, nothing is exchanged:

```
$ papers sync --pool ../shared-with-bob
nothing to sync with pool ../shared-with-bob: not the pool of the library, so no entries are shared with it (`papers sync --pool PATH KEY...` or `--all` exchanges entries with it once)
```

The entries taken from it link to its files in a library that is not local
(in a local library, they are copied as the `files` setting says), and the
entries sent to it get copies of their files in its files directory.

## Undo in a pool

A pool is a library with its own backup history (see
[Git integration](git.md)). `papers undo` in a library undoes a change of
that library only: an entry that `add` also added to the pool stays in the
pool. To undo a change in the pool, run the command in the pool, e.g.
`papers -C ~/Documents/papers undo` for the global pool.

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

## A shared files folder without a pool

In papers 2, several libraries could keep their PDFs in one folder: each
library has its own bibtex, no pool (`pool: none`), its own files
(`local: true`), and a `filesdir` that points to a common folder outside
the project, e.g. `~/Documents/papers/sealevel` used by two projects. This
setup still works in v3.

It is less efficient than a pool. Each library has its own bibtex, and
knows nothing of the others: adding to the second library a paper that the
first one has (even its PDF, already in the shared folder) reads the PDF
again, extracts its DOI and fetches the entry from crossref (the request is
answered from the cache when the same DOI was fetched on this machine).
Changes to an entry in one library do not reach the other.

The pool model of v3 avoids this: by default, a library is not local (it
has no files of its own) and its entries are copies of the entries of the
pool, whose PDFs are in the pool's files folder. A paper that is in the
pool already is taken from it, without reading the PDF or fetching anything,
and `papers sync` keeps the copies up to date. In both setups, each PDF is
stored once.

A shared files folder without a pool is enough when the libraries are
independent, and you do not want a central bibliography. To set it up:

```
papers init --pool none --filesdir ~/Documents/papers/sealevel   # local, since it has no pool
papers config pool none                                          # in an existing library
papers config filesdir ~/Documents/papers/sealevel               # the shared folder
papers config --global pool none   # no pool for the libraries that do not set one, new ones included
```

A library configuration of papers 2 without `pool` setting is read as a
local library (its files are its own) that uses the global pool. It looks
entries up in the global pool if that exists, but writes nothing to it:
`add` in a local library adds new entries to the pool only with
`auto-push`, and `push` and `sync` without KEY exchange only the entries
shared with the pool. `papers config pool none` stops the lookups.

What to watch for, since each library only knows its own entries:

- `papers file clean` in one library lists the PDFs of the other
  libraries in the shared folder as unlinked, and deletes them once
  confirmed (or with `-y`). Use `--dry-run` to see the list.
- `papers rm --delete-files` and `papers file rm` keep a PDF that another
  entry of the same library links to, but not one that another library
  links to.
- `papers file rename` in one library renames the shared PDF, and the link of the other library breaks. `papers file check`
  reports the broken link there, and `--fix` does not repair it (the repair
  of broken links only covers the files of a pool): remove the link with
  `papers file detach --broken --key KEY`, and attach the renamed file with
  `papers file attach KEY FILE`.

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
papers status                  # pool: ~/Documents/papers (global pool, changed since last pull or push)
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
papers sync --all                         # the first time: records what is shared
papers sync                               # later changes, both ways
```
