# Pools

## Libraries and pools

A **library** is a bibtex file, a files directory and a configuration file
(`.papers/config.json`), as created by `papers init` (see
[Configuration](configuration.md#libraries)). Each project usually has its
own library.

A library is in one of two states, given by its `pool` setting alone:

- **self-contained**: no pool (`pool: none`, or no `pool` setting). The
  library has its own entries and its own PDFs, in its files directory.
  `papers init` creates such a library.
- **shallow**: a pool, the path of another library. The library takes its
  entries from the pool and links to the pool's PDFs: its file links are
  those of the pool entries, and the entries and PDFs that it adds go to
  the pool too. `papers init --pool PATH` creates such a library.

The pool of a shallow library must be an existing library without pool of
its own (a self-contained library): `papers init --pool PATH` and
`papers config pool PATH` stop with an error otherwise, and nothing is
created or changed. Nothing in a library marks it as a pool: any
self-contained library can serve as the pool of shallow libraries, and a
pool can be used by several libraries. The pool path is written in the
configuration relative to the library when it is given relative, or when
it is under the library (e.g. `../sealevel`); another path is written with
`~` for the home directory, or absolute.

Any library, self-contained or shallow, can also exchange entries with
another library given on the command line, `--pool PATH`, e.g. a folder
shared with a coauthor (see
[Exchanges with any library](#exchanges-with-any-library)).

What a library does with its pool, or with the library of `--pool PATH`:

- `papers add` looks in the pool first (`papers add --pool PATH` looks in
  PATH);
- `papers pull` updates the entries shared with the pool, and adds the
  entries of the pool named, or all of them with `--all`;
- `papers push` updates the entries shared with the pool (those taken from
  it, or added to it before), and adds the entries named, or all of them
  with `--all`;
- `papers sync` does both;
- `papers status` (pool of a shallow library) and `papers pull --check`
  tell whether the pool changed since the last exchange with it: `up to
  date`, or `changed since last pull or push`.

An exchange goes one level only: the pool has no pool, and a library given
with `--pool PATH` must have none either (`PATH has a pool itself`).

`pull`, `push` and `sync` merge each entry field by field: whatever one
side changed since the last exchange wins; if both sides changed the same
field, you decide (the origin copy is papers' memory of the entry at the
last exchange, see [Origin copies](#origin-copies)).

Nothing is pulled automatically. Nothing is pushed automatically, except
in a shallow library: `add` adds the new entries to the pool, the file
links of an entry are updated in the pool entry (see
[Shallow libraries](#shallow-libraries)), and with the `auto-push` setting
the changes of the shared entries are pushed too (see
[Auto-push](#auto-push)). An older project does not change because of work
in a newer one.

The [Quickstart](quickstart.md) shows a self-contained project and a
shallow project that uses it. [A global shared library](global-library.md)
describes one library used as the pool of all projects.

## Shallow libraries

In a shallow library, the file links are the pool entry's; the library
decides which entries it has. The `files` setting says how a new file gets
to the pool:

- `move` (the default) and `copy`: the file is placed in the pool's files
  directory (moved, or copied: a hard link when possible), named with the
  pool's name template (a name template set on the library is not used);
  the library entry and the pool entry link to it there;
- `link`: the file stays where it is, and the library entry and the pool
  entry both link to it there. This works on one machine; on another
  machine that uses the pool (a pool in a synchronized folder), such links
  are broken.

A shallow library has no files directory of its own: `papers init --pool
PATH` does not create one.

In a shallow library:

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
  `files/` from when it was self-contained) is not sent; `push` sends it
  with the other fields. Only the links change: the other fields are
  pushed only with auto-push. An entry not shared with the pool gets the
  links of the pool entry of the same paper updated; if the pool does not
  have it, the entry is added to the pool, as `add` does;
- removing a file and removing an entry are different:
  - `papers file detach KEY FILE` removes the link from the library entry
    and from the pool entry; the file stays;
  - `papers file rm FILE` removes the link from both and deletes the file,
    unless another entry of the pool or of the library still links to it
    (`kept FILE: an entry of the pool links to it`). The PDF is removed for
    every library that uses the pool;
  - `papers rm KEY` removes the entry from the library only. The pool entry
    and its files stay, also with `--delete-files` (which deletes the files
    of removed entries in a self-contained library);
- `pull` and `sync` with the pool link to the pool's files instead of
  copying them, and the library entry follows the pool entry's links: a
  link that the pool entry had at the last exchange and no longer has is
  removed from the library entry (the file is not deleted). A link that
  the pool entry never had stays. The origin copy records the pool entry's
  links for this, in its `file` field; an origin copy without it removes
  nothing until the next exchange;
- when the pool renames a file, the link breaks: it is repaired by looking
  the entry up in the pool, when the library is loaded (saved on the next
  write) and by `papers file check --fix`. A broken link to a file outside
  the pool is relinked to the pool's file by `papers file check --fix`
  only (see [Reconnecting PDFs and a bibtex](files.md#reconnecting-pdfs-and-a-bibtex)).

Deleting a file of the pool, with `papers file rm` in a shallow library or
in the pool itself, breaks the links of the other libraries that use it,
until their next `pull` or `sync` removes the link. `papers file check`
shows the broken link meanwhile. The pool keeps no list of the libraries
that depend on it.

A project folder shared with coauthors (git, Dropbox...) should be a
self-contained library: the links of a shallow library point into your own
pool, which the others do not have. Such a project can still exchange
entries with your libraries through `--pool PATH`.

A pool can be in a folder synchronized by a cloud client on the local disk
(e.g. `~/Dropbox/papers`): papers reads and writes the files there, and
the client synchronizes them.

### Changing the pool

`papers config pool PATH|none` changes the state of a library, and its
files follow. When a change copies files or deletes the library's copies,
papers lists what it will do and asks `Continue? [y/N]`; `-y` answers yes,
`--dry-run` only shows the list, and without a terminal the command stops
with the list (pass `-y`). The files of a pool are never deleted.

| Command | In a self-contained library | In a shallow library |
|---|---|---|
| `papers config pool PATH` | the library becomes shallow: it links to the copies of its PDFs in PATH, and its own copies are deleted (see below) | the library links to the copies of its PDFs in the new pool (see below); the files of the former pool stay where they are |
| `papers config pool none` (or `--unset pool`) | nothing to do | the library becomes self-contained: the pool files that it links to are copied into its files directory (hard links when possible), named with its name template, and the links rewritten; the pool keeps its files |

PATH must be an existing library without pool. Each PDF that the library
links to must already be linked by the entry of the same paper in PATH:
the same file, or a file of the same content. Entries without PDF need not
be in PATH, and broken links do not count (`papers file check --fix`
relinks them afterwards). If an entry has a PDF that PATH does not have,
nothing is changed, and the command lists the entries (the first ten, and
the number of the others) and the command that copies their PDFs there:
`papers push --pool PATH KEY...`, or `papers push --pool PATH --all` when
there are more than ten.

Otherwise the library links to the copies in PATH. The library's own
copies, in its files directory, are deleted, unless an entry of the
library or of PATH still links to them; nothing is copied or moved. These
commands do not push entries or merge fields: `papers push` does that. The
entries exchanged with PATH before (with `--pool PATH`) are shared with it
already: their origin copies are those of the new pool.

To move the PDFs of a self-contained library into another library:

```
papers init PATH                # if PATH is not a library yet
papers push --pool PATH --all   # copies the entries and their PDFs to PATH
papers config pool PATH         # links to the copies in PATH, deletes the library's own
```

## Exchanges with any library

`--pool PATH` on `pull`, `push` and `sync` exchanges with the library at
`PATH`, from any library: self-contained or shallow. PATH must be a
library without pool: no command creates it, `papers init PATH` does. The
exchange works as with
the pool of a library:

- the origin copies are recorded for PATH, in its own file of
  `.papers/origin/`: the next exchange with PATH is a three-way merge, and
  a field changed on one side only needs no decision;
- without KEY or `--all`, the exchange handles the entries exchanged with
  PATH before (those with an origin copy for PATH);
- `papers sync --pool PATH KEY...` takes the entries named from PATH that
  the library does not have, sends to PATH those that it does not have,
  and merges the others both ways;
- `papers pull --pool PATH --all` takes every entry of PATH, and
  `papers push --pool PATH --all` sends every entry of the library.

An entry that has no origin copy for PATH yet (the first exchange) has no
base: each field that differs is a conflict, decided in the dialogue or
with `--on-duplicate`.

```
$ papers sync --pool ../shared-with-bob
nothing to sync with pool ../shared-with-bob: no entries shared with it (`papers sync --pool ../shared-with-bob --all` adds the entries missing on each side)
```

The files are copied, as the `files` setting says (a file of PATH is
never moved): the entries taken from PATH get copies of its files (a hard
link when possible) and the entries sent to PATH get copies of theirs in
its files directory. The file links of a shallow library are those of the
pool entries for its own pool only. A shallow library that takes entries
from PATH places their files in the files directory of its pool, and adds
the entries new to the library to its pool, as `add` does (`[also added to
pool ...]`); the changes of the fields go to the pool with `papers push`,
or with auto-push.

`papers config pool PATH` makes PATH the pool of the library (see
[Changing the pool](#changing-the-pool)); the origin copies recorded for
PATH stay valid, however PATH is written.

## Auto-push

`papers config auto-push true` in a shallow library makes the commands that
change entries push them to the pool: `add`, `edit`, `tag`, `list
--add-tag` and the other actions of `list`, `check`, `file attach`, `file
rename`, `file detach`, `file rm`, `file mv` and `file check --fix`. After
the command, the entries it changed that are shared with the pool, and the
entries new to the library, are pushed as `papers push KEY...` would push
them, files included. The other entries are not pushed. In a
self-contained library, the setting has no effect (it has no pool; the
libraries of `--pool PATH` only get what `push` and `sync` send).

- `rm` is never pushed: removing an entry from the library does not
  remove it from the pool.
- A conflict (the same field changed in the pool since the last exchange)
  does not stop the command: the entry is saved in the library, is not
  pushed, and its line says so:

```
$ papers tag Smith_2020 --add bar
Modified -> Smith_2020: Climate sensitivity revisited (doi:10.1000/abc123, foo | bar) [not pushed: changed in the pool too; papers sync decides]
```

With `auto-push false` (the default), nothing is pushed automatically,
apart from the new entries of `add` and the file links of a shallow
library (see [Shallow libraries](#shallow-libraries)): run `papers push` or
`papers sync`.

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
pool: the pool of the library, and each library exchanged with through
`--pool PATH`. A file is named after the folder of the pool and the start
of a hash of its path as the library names it, e.g.
`shared-with-bob-d15650.bib` for `../shared-with-bob`, or
`papers-<hash>.bib` for `~/Documents/papers`. The first lines of the file
name the pool and give the modification time of its bibtex at the last
exchange. In a library whose pool is `../shared-with-bob`, after `papers
pull agnew_farrell1978` and `papers pull`:

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

The file records, for each entry exchanged with the pool (by `add`, `pull`
or `push`), its origin copy, under the library's key, with the key in the
pool (`papers-pool-key`) and the time (`papers-time`). In a shallow
library, the origin copy for its pool also keeps its `file` field, the
file links of the pool entry after the exchange, so that a pull can tell a
link that the pool entry removed from one it never had (the origin copies
for other libraries have no `file` field). The file links are not part of
the three-way merge. The modification time is recorded at a pull of all
entries that skipped no conflict, or a push or an add when the pool had
not changed since the previous exchange (or when it is the first
exchange). A push that leaves the pool entry with fields or files that the
library entry does not have does not count: `papers status` then shows the
pool as changed until the next pull. The files are part of the git backup
of the library (see [Git integration](git.md)).

The files of all pools are kept: after `papers config pool PATH`, the
library uses the file of PATH (with the origin copies of the exchanges
with `--pool PATH`, if any), and setting the pool back to an earlier one
finds its origin copies again.

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

The entry gets the pool's files: in a shallow library, the entry links to
the pool's file; otherwise, in `copy` and `move` mode they are copied into
the library's files directory (a hard link when possible), named with the
library's name template, and in `link` mode the entry links to the pool's
file. A pool file is never moved. A PDF given that has the same content as
a file of the pool entry is removed in `move` mode, since it is stored
already, and kept in `copy` and `link` mode; a PDF with other content is
attached to the entry as another file, placed as the files mode says. The
origin copy is recorded. `--no-pool` skips the lookup.

`papers add --pool PATH` looks in the library PATH instead (PATH must be a
library without pool), in the same way: a paper that PATH has is taken from
it with its files, copied as the files mode says (in a shallow library,
into the files directory of its pool, and the entry goes to its pool too,
as any new entry), and the origin copy is recorded for PATH, so that
`papers pull --pool PATH` brings the later corrections. Nothing new is sent
to PATH. This is not `papers -C PATH add`, which adds to the library PATH.

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
shallow library (from its own pool), and otherwise copied into the files
directory as the `files` setting says. The key of the library entry never
changes. After the merge, the origin copy is the pool's current version.
A skipped conflict leaves the pool shown as changed in `papers status`.

An entry without origin copy (added before the pool was used, or with
`--no-pool`) is not shared: `pull` without KEY leaves it alone. Named on the
command line, or with `--all`, it is matched to the pool by the same-paper
rule. Its differences with the pool entry are conflicts (there is no
origin to tell which side changed), a field that only the pool entry has
is added, and the origin copy is recorded afterwards ("linked").

An entry that the pool does not have is reported (`Not found`) only when it
is named on the command line. Without KEY, it is left as it is.

A KEY is looked up in the library first, then in the pool (its key, DOI,
arXiv identifier or ISBN): an entry of the pool that the library does not
have is added to it (`added`), with its origin copy, under the pool key
(see [Keys and identity](#keys-and-identity)); its files are linked in a
shallow library, otherwise copied as the `files` setting says (a hard link
when possible). An identifier found in neither is an error, and nothing is
changed. `--all` adds every entry of the pool that the library does not
have (same-paper rule). A pool that does not exist or is not a library is
an error of `pull`, `pull --check` and `sync`, and nothing is changed
(`papers init PATH` creates it).
Without `--pool PATH`, a self-contained library has no pool to pull from:
`this library has no pool: give one with --pool PATH`.

`pull` prints one line per entry added (`Added ->`), modified
(`Modified ->`), left with a conflict (`Conflict ->`) or, among the entries
named, not found in the pool (`Not found ->`), with the pool in brackets,
then the counts when more than one entry was involved: `added`,
`modified`, `skipped`, `not found`, `unchanged`, and `linked` (an entry
without origin copy, the same as its pool entry: its origin copy is
recorded). `push` prints the same lines for the pool entries. When a
command also adds or changes the entry in the pool (see
[Auto-push](#auto-push)), or `add` takes it from the pool, its line says so
in brackets: `[also added to pool ~/Documents/papers]`, `[also modified in
pool ~/Documents/papers]`, `[not pushed: changed in the pool too; papers
sync decides]`, `[from pool ~/Documents/papers]`.

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
shared with the pool). `papers status` shows the first part too, for the
pool of a shallow library.

## `papers push`

```
papers push [KEY...|-] [--all] [--pool PATH] [--on-duplicate MODE]
```

The reverse of `pull`, into the pool of the library or the library of
`--pool PATH`. Without KEY, only the entries shared with the pool are
pushed: those with an origin copy from it (taken from it by `add` or
`pull`, or pushed to it before). `push KEY...` pushes the entries named,
and `push --all` every entry of the library:

- an entry that is not in the pool is added to it, with a key from the
  pool's key template; its files are copied into the pool's files directory
  (a hard link when possible), named with the pool's name template;
- an entry that is in the pool is merged three-way into the pool entry:
  fields changed or removed in the library only are taken, fields changed
  or removed in the pool only are kept, conflicts are decided with
  `--on-duplicate` (`keep`: the pool values, `update`: the library values).
  The pool key does not change.

Push does not change the library: after it, the origin copy is the library
version that was pushed, and the fields that only the pool entry has come
with the next `pull` (or `papers sync`). A pool that does not exist or is
not a library is an error of `push`, and nothing is changed: the message
suggests `papers init PATH` (and, when the parent folder of PATH is missing
too, that a disk may not be mounted).

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
nothing to sync with pool ../sealevel (2 entries unchanged)
```

## Undo in a pool

A pool is a library with its own backup history (see
[Git integration](git.md)). `papers undo` in a library undoes a change of
that library only: an entry that `add` also added to the pool stays in the
pool. To undo a change in the pool, run the command in the pool, e.g.
`papers -C ../sealevel undo`. The origin copies of the library are
restored with its bibtex: see
[Undo in a library that has a pool](undo-redo.md#undo-in-a-library-that-has-a-pool).

## `papers export`

```
papers export DIR [KEY...|-] [--files copy|link|none]
```

writes the entries (all without KEY) as a new library in `DIR`, which must
not exist or be empty, to hand over: its bibtex, its files directory, and
its configuration (a self-contained library, with the name and key
templates that the library sets). File links are relative to the new
bibtex.

- `--files copy` (default) copies the files into `DIR/files` (hard links
  when possible), named with the name template;
- `--files link` links to the files where they are;
- `--files none` leaves the file links out.

`papers add DIR --recursive` adds an exported library to another one, and
`papers config pool DIR` makes it the pool of the library (the export has
copies of its PDFs).

## A shared files folder without a pool

In papers 2, several libraries could keep their PDFs in one folder: each
library has its own bibtex, and a `filesdir` that points to a common
folder outside the project, e.g. `~/Documents/papers/sealevel` used by two
projects. This setup still works in v3, with self-contained libraries.

Each library has its own bibtex, and knows nothing of the others: adding to
the second library a paper that the first one has (even its PDF, already
in the shared folder) reads the PDF again, extracts its DOI and fetches the
entry from crossref (the request is answered from the cache when the same
DOI was fetched on this machine). Changes to an entry in one library do
not reach the other.

papers 3 offers two other ways:

1. exchanges with any library: `papers add --pool PATH` takes a paper that
   the library PATH has, without reading the PDF or fetching anything, and
   `papers sync --pool PATH` keeps the entries exchanged up to date. Each
   library keeps its own copies of the PDFs (hard links when possible);
2. shallow projects that link to the PDFs of a shared library: a project
   created with `papers init --pool PATH` takes its entries from PATH and
   links to its PDFs, and the papers it adds go to PATH. Each PDF is stored
   once.

A shared files folder without a pool is enough when the libraries are
independent, and you do not want a shared bibliography. To set it up:

```
papers init --filesdir ~/Documents/papers/sealevel   # a new library
papers config filesdir ~/Documents/papers/sealevel   # an existing library
```

A library configuration of papers 2 has no `pool` setting: it is read as a
self-contained library, as in papers 2.

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
- `papers push --pool PATH --all` then `papers config pool PATH` in one
  library deletes the shared PDFs once PATH has copies, and the links of
  the other library break. Once the other library uses the same pool
  (`papers config pool PATH`, which counts the broken links),
  `papers file check --fix` relinks them to the pool's files (see
  [Reconnecting PDFs and a bibtex](files.md#reconnecting-pdfs-and-a-bibtex)).

## Example

A self-contained project, `sealevel`, and a shallow project, `tides`, that
uses it as pool:

```
cd ~/projects/sealevel
papers init                               # self-contained
papers add ~/Downloads/esd-4-11-2013.pdf  # fetched from crossref; the PDF goes to files/

cd ~/projects/tides
papers init --pool ../sealevel            # shallow
papers add --doi 10.5194/esd-4-11-2013    # taken from sealevel: no query, the file is linked
```

Later, the entry is completed in `sealevel` (e.g. its pages), and adapted
in `tides` (a journal abbreviation):

```
cd ~/projects/tides
papers status                  # pool: ../sealevel (changed since last pull or push)
papers pull --check            # perrette_landerer2013: changed in pool ../sealevel: pages
papers pull                    # pages taken; the journal abbreviation is kept
```

A folder shared with a coauthor, exchanged with from time to time:

```
cd ~/projects/sealevel
papers export ../shared-with-bob mine2022 smith2020   # a self-contained library for Bob
papers sync --pool ../shared-with-bob --all            # the first time: records what is shared
papers sync --pool ../shared-with-bob                  # later changes, both ways
```
