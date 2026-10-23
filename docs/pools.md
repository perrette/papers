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

`pull`, `push` and `sync` merge each entry field by field: whatever one
side changed since the last exchange wins; if both sides changed the same
field, you decide (the origin copy is papers' memory of the entry at the
last exchange, see [Origin copies](#origin-copies)).

Nothing is pulled automatically, and nothing is pushed automatically
unless the `auto-push` setting is on (see [Auto-push](#auto-push)), except
that in a library that is not local, `add` adds the new entries to the pool
and the file links of an entry are updated in the pool entry (see
[Local or not](#local-or-not)).
An older project does not change because of work in a newer one.

## Local or not

The `local` setting of a library says where its files are:

- `local: false` (the default for new libraries): the files are in the files
  directory of the pool, and the library links to them. A paper used by
  several projects is stored once;
- `local: true`: the files are in the files directory of the library
  (`files/`).

`papers init --local` creates a local library without pool (`pool none`);
`papers init --local --pool PATH` creates a local library that uses the pool
PATH. Without `--local`, the default for new libraries is the `local`
setting of the global configuration (`papers config --global local true`).
A library without pool is local.

In a library that is not local, the file links are the pool entry's; the
library decides which entries it has. The `files` setting says how a new
file gets to the pool:

- `move` (the default) and `copy`: the file is placed in the pool's files
  directory (moved, or copied: a hard link when possible), named with the
  pool's name template (a name template set on the library is not used);
  the library entry and the pool entry link to it there;
- `link`: the file stays where it is, and the library entry and the pool
  entry both link to it there. This works on one machine; on another
  machine that uses the pool (a pool in a synchronized folder), such links
  are broken.

In a library that is not local:

- `add` places new files as the `files` setting says, and adds the new
  entries to the pool too, whatever the `auto-push` setting (their origin
  is recorded, see [Origin copies](#origin-copies)). A change that `add`
  makes to the fields of an entry the library has already is pushed only
  with auto-push;
- `papers file attach`, `file rename` and `file check --fix` place the
  files they handle in the same way;
- the file links are always pushed, whatever the `auto-push` setting: a
  command that changes the files of an entry (`file attach`, `file rename`,
  `file detach`, `file rm`, `file mv`, `file check --fix`, `edit`...) sets
  the links of the pool entry to match right away, and its line ends with
  `[file links also updated in pool ...]`. The pool entry gets the links
  that the command added, wherever they point, and the links of the
  library entry into the pool's files directory, and loses the links that
  the library entry no longer has. A link that the library entry had
  before the command, outside the pool's files directory, and that the
  pool entry does not have (for instance a file of the library's own
  `files/` from when it was local) is not sent; `push` sends it with the
  other fields. Only the links change: the other fields are pushed only
  with auto-push. An entry not shared with the pool gets the links of the
  pool entry of the same paper updated; if the pool does not have it, the
  entry is added to the pool, as `add` does;
- `file detach` never deletes a file. `file rm` removes the link from the
  pool entry too, and deletes the file unless another entry of the pool
  or of the library still links to it (`kept FILE: an entry of the pool
  links to it`);
- `pull` and `sync` link to the pool's files instead of copying them, and
  the library entry follows the pool entry's links: a link that the pool
  entry had at the last exchange and no longer has is removed from the
  library entry (the file is not deleted). A link that the pool entry never
  had stays. The origin copy records the pool entry's links for this
  (`papers-files`); an origin copy written before papers recorded them
  removes nothing until the next exchange. A one-time exchange (`--pool
  PATH`, another library) adds links only;
- when the pool renames a file, the link breaks: it is repaired by looking
  the entry up in the pool, when the library is loaded (saved on the next
  write) and by `papers file check --fix`. A broken link to a file outside
  the pool is relinked to the pool's file by `papers file check --fix`
  only (see [Reconnecting PDFs and a bibtex](files.md#reconnecting-pdfs-and-a-bibtex)).

In any library, `rm --delete-files` never deletes a file of the pool, nor
a file that a pool entry links to in a library that is not local, and it
does not change the pool entry. In a local library, `file rm` never deletes
a file of the pool either. Deleting a file in a pool breaks the links of the libraries that use
it: it shows up as a broken link there (`papers file check`). The pool keeps
no list of the libraries that depend on it.

### Sharing a project folder

A project folder shared with coauthors (git, Dropbox...) should be a local
library (`papers init --local --pool PATH`, `papers init --local` for no
pool, or `papers config local true`): the links of
a library that is not local point into your own pool, which the others do
not have.

A pool can be in a folder synchronized by a cloud client on the local disk
(e.g. `papers config --global pool ~/Dropbox/papers`): papers reads and
writes the files there, and the client synchronizes them.

### Changing `local` and `pool`

When a change copies files or deletes the library's copies, papers lists
what it will do and asks `Continue? [y/N]`; `-y` answers yes, `--dry-run`
only shows the list, and without a terminal the command stops with the list
(pass `-y`). The files of a pool are never deleted.

| Command | In a library that is not local | In a local library |
|---|---|---|
| `papers config local true` | the pool files it links to are copied into its files directory (hard links when possible), named with its name template, and the links rewritten; the pool keeps its files | nothing to do |
| `papers config local false` | nothing to do | the library links to the pool's copies of its PDFs, and its own copies are deleted (see below) |
| `papers config pool none` | as `local true`, and the library becomes local | the setting changes |
| `papers config pool PATH` (or `--unset pool`: the global pool) | the library links to the copies of its PDFs in the new pool (see below); the files of the former pool stay where they are | the setting changes |

`papers config local false`, and `papers config pool PATH` in a library
that is not local, only change the file links. Each PDF that the library
links to must already be linked by the pool entry of the same paper, in
the pool that the library will use: the same file, or a file of the same
content. Entries without PDF can stay out of the pool, and broken links do
not count (`papers file check --fix` relinks them afterwards). If an entry
has a PDF that the pool entry does not have, nothing is changed, and the
command lists the entries and the command that copies their PDFs to the
pool:

- `papers config local false`: `papers push KEY...`, or `papers push --all`
  when there are many entries;
- `papers config pool PATH`: `papers push --pool PATH KEY...` (a one-time
  push, which copies the PDFs to PATH), or `papers push --pool PATH --all`.

Otherwise the library links to the pool's copies. `local false` deletes
the library's own copies in its files directory, unless an entry of the
library or of the pool still links to them; `pool PATH` copies or moves no
file. These commands do not push entries or merge fields: `papers push`
does that. After `papers config pool PATH`, no entry is shared with the
new pool yet: `papers push KEY...` or `papers push --all` shares them.

To move the PDFs of a local library into a pool:

```
papers config pool PATH      # the pool, if the library has none
papers push --all            # copies the entries and their PDFs to the pool
papers config local false    # links to the pool's copies, deletes the library's
```

## Auto-push

`papers config auto-push true` makes the commands that change entries push
them to the pool, in a local library or not: `add`, `edit`, `tag`,
`list --add-tag` and the other actions of `list`, `check`, `file attach`,
`file rename`, `file detach`, `file rm`, `file mv` and `file check --fix`.
After the command, the entries it changed that are shared with the pool,
and the entries new to the library, are pushed as `papers push KEY...`
would push them, files included. The other entries are not pushed.

- `rm` is never pushed: removing an entry from the library does not
  remove it from the pool.
- A conflict (the same field changed in the pool since the last exchange)
  does not stop the command: the entry is saved in the library, is not
  pushed, and its line says so:

```
$ papers tag Smith_2020 --add bar
Modified -> Smith_2020: Climate sensitivity revisited (doi:10.1000/abc123, foo | bar) [not pushed: changed in the pool too; papers sync decides]
```

With `auto-push false` (the default, local or not), nothing is pushed
automatically, apart from the new entries of `add` and the file links in a
library that is not local (see [Local or not](#local-or-not)): run
`papers push` or `papers sync`.

## A finished paper

Do not sync the library of a finished paper. Its keys stay as they are,
but a `pull` can change journal abbreviations and other fields that the
paper was written with. Leave `auto-push` off there, and do not pull.

## Keys and identity

The key of an entry belongs to each library: it is what LaTeX documents
cite. `pull` and `push` never change the key of an entry that the library
they write to has. An entry new to the pool gets a key from the pool's key
template; an entry of the pool new to the library keeps the pool key, with
a letter suffix if the library has that key already (`Smith_2020b`).

Three fields are not merged by `pull` and `push`: each side keeps its own.

- the key, as above;
- `ids`, the former keys of the entry in that library: they mean nothing
  in the other library;
- `file`, the links of each library to its own copies of the files. A file
  that the other side has and this side does not is linked or copied (see
  [`papers pull`](#papers-pull) and [`papers push`](#papers-push)).

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
the time (`papers-time`); in a library that is not local, also the file
links of the pool entry after the exchange (`papers-files`), so that a pull
can tell a link that the pool entry removed from one it never had. The modification time is recorded at a pull of
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
field. A removed field counts as a change:

| Field since the origin copy | Result |
|---|---|
| changed or removed in the pool only | taken from the pool (`+` in the dialogue, `(removed)` for a removal) |
| changed or removed in the library only (e.g. a field adapted to a journal style) | kept, without asking |
| changed on both sides to different values, or removed on one side and changed on the other | a conflict (`!`) |
| removed on both sides | removed |

File links are merged: new files of the pool entry are linked in a
library that is not local, and otherwise copied into the library's files
directory as the `files` setting says. The key of the library entry never
changes. After the merge, the origin copy is the pool's current version.
A skipped conflict leaves the pool shown as changed in `papers status`.

An entry without origin copy (added before the pool was used, or with
`--no-pool`) is not shared: `pull` without KEY leaves it alone. Named on the
command line, or with `--all`, it is matched to the pool by the same-paper
rule. Its differences
with the pool entry are conflicts (there is no origin to tell which side
changed), a field that only the pool entry has is added, and the origin
copy is recorded afterwards ("linked").

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
pool entries. When a command also adds or changes the entry in the pool
(see [Auto-push](#auto-push)), or `add` takes it from the pool, its line
says so in brackets: `[also added to pool ~/Documents/papers]`,
`[also modified in pool ~/Documents/papers]`,
`[not pushed: changed in the pool too; papers sync decides]`,
`[from pool ~/Documents/papers]`.

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
  fields changed or removed in the library only are taken, fields changed
  or removed in the pool only are kept, conflicts are decided with `--on-duplicate` (`keep`: the
  pool values, `update`: the library values). The pool key does not change.

Push does not change the library: after it, the origin copy is the library
version that was pushed, and the fields that only the pool entry has come
with the next `pull` (or `papers sync`). The pool is created if it does not
exist yet.

### A pool with entries papers cannot read

An entry that the bibtex parser cannot read, such as one with a field
given twice or a missing brace, is kept in the file as it is, but papers
does not see it. Every command that loads that bibtex warns about it, with
its line. Papers does not write to a pool that has such an entry: it would
not find that paper there, and would add it again. `push`, `sync` and the
commands that add to the pool stop with an error, and nothing is changed,
until the entry is fixed in the pool's bibtex. Reading from the pool
(`pull`, `add` looking in the pool) still works.

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
`papers -C ~/Documents/papers undo` for the global pool. The origin copies
of the library are restored with its bibtex: see
[Undo in a library that has a pool](undo-redo.md#undo-in-a-library-that-has-a-pool).

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
- `papers file rename` in one library renames the shared PDF, and the
  link of the other library breaks. `papers file check` reports the broken
  link there. `papers file check --fix --search FOLDER` relinks it if the
  new name is the one that the library's name template gives the entry
  (the two libraries use the same template); otherwise attach the renamed
  file with `papers file attach KEY FILE`, and remove the link with
  `papers file detach --broken --key KEY`.
- `papers push --all` then `papers config local false` in one library
  deletes the shared PDFs once the pool has copies, and the links of the
  other library break. Once the other library uses the same pool,
  `papers file check --fix` relinks them to the pool's files (see
  [Reconnecting PDFs and a bibtex](files.md#reconnecting-pdfs-and-a-bibtex)).

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
papers config pool ../shared-with-bob     # the pool of tides from now on: it links to the
                                          # copies of the PDFs that export made
papers sync --all                         # the first time: records what is shared
papers sync                               # later changes, both ways
```
