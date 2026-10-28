# Pools

## Libraries and pools

A **library** is a bibtex file, a files directory and a configuration file
(`.papers/config.json`), as created by `papers init` (see
[Configuration](configuration.md#libraries)). Each project usually has its
own library.

A **pool** is a library that another library takes entries from or
exchanges entries with. Nothing in a library marks it as a pool: any
library without pool of its own can serve as one, and a pool can be used
by several libraries.

A library is in one of two states, given by its `pool` setting alone:

- **self-contained**: no pool (`pool: none`, or no `pool` setting). The
  library has its own entries and its own PDFs, in its files directory.
  `papers init` creates such a library.
- **shallow**: a pool, the path of another library. The library takes its
  entries from the pool and links to the pool's PDFs. `papers init --pool
  PATH` creates such a library. See [Shallow libraries](shallow-libraries.md).

Any library, self-contained or shallow, can also exchange entries with
another library given on the command line, `--pool PATH`, e.g. a folder
shared with a coauthor (see
[Exchanges with any library](#exchanges-with-any-library)).

What a library does with its pool, or with the library of `--pool PATH`:

- `papers add` looks in the pool first (`papers add --pool PATH` looks in
  PATH);
- `papers pull` updates the entries shared with the pool, and adds the
  entries of the pool named, or all of them with `--all`;
- `papers push` updates the entries shared with the pool, and adds the
  entries named, or all of them with `--all`;
- `papers sync` does both;
- `papers status` (pool of a shallow library) and `papers pull --check`
  tell whether the pool changed since the last exchange with it: `up to
  date`, or `changed since last pull or push`;
- `papers file fix` relinks the broken links to the files of the pool entry
  of the same paper (`papers file fix --pool PATH` also looks in PATH, which
  may have a pool itself; nothing changes in PATH and no origin copy is
  recorded, see
  [Reconnecting PDFs and a bibtex](files.md#reconnecting-pdfs-and-a-bibtex)).

An entry is **shared** with a pool when the pool has the same paper: the
pool entry of its origin copy (see [Origin copies](#origin-copies)), else
the same paper by the same-paper rule (see
[Keys and identity](#keys-and-identity)). Without KEY or `--all`, `pull`,
`push` and `sync` exchange the shared entries only, with an origin copy or
not.

An exchange goes one level only: the pool has no pool, and a library given
with `--pool PATH` must have none either (`PATH has a pool itself`).

Nothing is pulled automatically. Nothing is pushed automatically, except
in a shallow library: `add` adds the new entries to the pool, the file
links of an entry are updated in the pool entry, and with the `auto-push`
setting the changes of the shared entries are pushed too (see
[Shallow libraries](shallow-libraries.md#auto-push)). An older project does
not change because of work in a newer one.

The [Quickstart](quickstart.md) shows a self-contained project and a
shallow project that uses it. [A global shared library](global-library.md)
describes one library used as the pool of all projects.

## Merging

`pull`, `push` and `sync` merge each entry field by field. The origin copy
is papers' memory of the entry at the last exchange (see
[Origin copies](#origin-copies)). Comparing each side with it tells which
side changed a field. A removed field counts as a change:

| Field since the origin copy | Result |
|---|---|
| changed or removed on the side that sends only (the pool for `pull`, the library for `push`) | taken |
| changed or removed on the side that receives only (e.g. a field adapted to a journal style) | kept, without asking |
| changed on both sides to different values, or removed on one side and changed on the other | a conflict |
| removed on both sides | removed |

Conflicts are decided in the dialogue or with `--on-duplicate` (see
[`papers pull`](#papers-pull) and [`papers push`](#papers-push)). An entry
without origin copy has no base: each field that differs is a conflict. The
first exchange of such an entry (e.g. the first `sync` with a library given
with `--pool PATH` that has papers of the library) asks about these
conflicts once: afterwards the origin copy is recorded, and the next
exchanges merge three-way.

### Removed entries

An entry is never removed by an exchange:

- `papers rm KEY` removes the entry from the library only. `push` and
  `sync` do not remove it from the pool.
- An entry removed from the pool stays in the libraries that have it. It
  is no longer shared: `pull`, `push` and `sync` without KEY or `--all`
  (and the auto-push of a shallow library) leave it out, and note it once:

  ```
  smith2020: removed from pool ~/Documents/papers (`papers push smith2020` adds it back)
  ```

  Its origin copy for the pool is dropped, so the note does not come again.
  `push KEY` and `push --all` add it to the pool again; `pull KEY` reports
  it as `Not found`; `pull --check` lists it with the note (and drops
  nothing). Remove it from the library with `papers rm KEY`.

## `papers pull`

```
papers pull [KEY...|-] [--all] [--pool PATH] [--on-duplicate MODE] [--check]
```

Without KEY, `pull` updates the entries shared with the pool (the pool
has the same paper). For each of them (or each entry named, or every entry with
`--all`), papers finds its entry in the pool (by its origin copy,
else by the same-paper rule) and merges it into the library entry, field by
field (see [Merging](#merging)). The pool is the side that sends: a field
changed or removed in the pool only is taken (`+` in the dialogue,
`(removed)` for a removal), a field changed in the library only is kept,
and a conflict is marked `!`.

File links are merged: new files of the pool entry are linked in a
shallow library (from its own pool), and otherwise copied into the files
directory as the `files` setting says. The key of the library entry never
changes. After the merge, the origin copy is the pool's current version.
A skipped conflict leaves the pool shown as changed in `papers status`.

An entry without origin copy (added before the pool was used, or with
`--no-pool`) is matched to the pool by the same-paper rule. Its differences
with the pool entry are conflicts (there is no origin to tell which side
changed), a field that only the pool entry has is added, and the origin
copy is recorded afterwards ("linked").

An entry that the pool does not have is reported (`Not found`) only when it
is named on the command line. Without KEY, it is left as it is (with a
note if it was removed from the pool, see [Removed entries](#removed-entries)).

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
then the counts when more than one entry changed or was not exchanged:
`added`, `modified`, `skipped`, `not found`, and `linked` (an entry
without origin copy, the same as its pool entry: its origin copy is
recorded). The entries unchanged are not counted. When nothing changed,
`pull` prints one line, `nothing to pull from pool ../sealevel`. `push`
prints the same lines for the pool entries. When a
command also adds or changes the entry in the pool (see
[Auto-push](shallow-libraries.md#auto-push)), or `add` takes it from the
pool, its line says so in brackets: `[also added to pool
~/Documents/papers]`, `[also modified in pool ~/Documents/papers]`, `[not
pushed: changed in the pool too; papers sync decides]`, `[from pool
~/Documents/papers]`.

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
`--pool PATH`. Without KEY, only the entries shared with the pool (the
pool has the same paper) are pushed; an entry removed from the pool is not
added back (see [Removed entries](#removed-entries)). `push KEY...` pushes
the entries named,
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

## `papers sync`

```
papers sync [KEY...|-] [--all] [--pool PATH] [--on-duplicate MODE]
```

runs `papers pull`, then `papers push` of the same entries:

- without KEY, the entries shared with the pool (the pool has the same
  paper). An entry that the pool does not have is not exchanged: name it,
  or use `--all`;
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
nothing to sync with pool ../sealevel
```

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

An entry with an origin copy is first looked up under the pool key of its
origin copy: that pool entry is taken if it is the same paper as the origin
copy or as the entry. Otherwise, e.g. when the pool key now names another
paper, the pool entry is found by the rule above (from the origin copy,
then from the entry), and last under the pool key, if its DOI, arXiv
identifier and ISBN do not differ from those of the origin copy (both
titles changed). When the pool has the same paper twice, the entry of the
origin copy is the one exchanged.

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
pool as changed until the next pull. The files are part of the history of
the library (see [Undo and redo](undo-redo.md)), which `papers undo`
restores with its bibtex.

The files of all pools are kept: after `papers config pool PATH`, the
library uses the file of PATH (with the origin copies of the exchanges
with `--pool PATH`, if any), and setting the pool back to an earlier one
finds its origin copies again.

Earlier v3 beta versions kept all the origin copies in one file,
`.papers/origin.bib`: papers splits it into these files the first time it
reads it, and removes it.

The origin copy is the third version of a three-way merge. It is the
version of the side that sent the entry, as it was sent: the pool entry
after `add` and `pull`, the library entry after `push`. What the receiving
side has beyond it is a change of that side, for the next exchange the
other way: a field that only the pool entry has comes with the next
`pull`; a field that only the library entry has goes to the pool with the
next `push`.

`papers add other.bib` copies the entries of `other.bib` once, and keeps no
memory of where they came from. The entries taken with `papers pull` stay
linked to the pool through their origin copy: later pulls bring the
corrections made in the pool.

## Exchanges with any library

`--pool PATH` on `pull`, `push` and `sync` exchanges with the library at
`PATH`, from any library: self-contained or shallow. PATH must be a
library without pool: no command creates it, `papers init PATH` does. The
exchange works as with the pool of a library:

- the origin copies are recorded for PATH, in its own file of
  `.papers/origin/`: the next exchange with PATH is a three-way merge, and
  a field changed on one side only needs no decision;
- without KEY or `--all`, the exchange handles the entries shared with
  PATH (PATH has the same paper);
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
the entries new to the library to its pool, as `add` does (`also added to
pool ...`); the changes of the fields go to the pool with `papers push`,
or with auto-push. See
[Topic libraries](shallow-libraries.md#use-case-topic-libraries) for an
example.

`papers config pool PATH` makes PATH the pool of the library (see
[Changing the pool](shallow-libraries.md#changing-the-pool)); the origin
copies recorded for PATH stay valid, however PATH is written.

A folder shared with a coauthor, exchanged with from time to time:

```
cd ~/projects/sealevel
papers export ../shared-with-bob mine2022 smith2020   # a self-contained library for Bob
papers sync --pool ../shared-with-bob                  # the changes of the shared entries, both ways
papers sync --pool ../shared-with-bob --all            # also the entries missing on each side
```

`papers export` is described in [Export](export.md).

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

### `add --pool PATH`

`papers add --pool PATH` looks in the library PATH instead (PATH must be a
library without pool), in the same way: a paper that PATH has is taken from
it with its files, copied as the files mode says (in a shallow library,
into the files directory of its pool, and the entry goes to its pool too,
as any new entry), and the origin copy is recorded for PATH, so that
`papers pull --pool PATH` brings the later corrections. Nothing new is sent
to PATH. This is not `papers -C PATH add`, which adds to the library PATH.

## A pool with entries papers cannot read

An entry that the bibtex parser cannot read, such as one with a field
given twice or a missing brace, is kept in the file as it is, but papers
does not see it. Every command that loads that bibtex warns about it, with
its line. Papers does not write to a pool that has such an entry: it would
not find that paper there, and would add it again. `push`, `sync` and the
commands that add to the pool stop with an error, and nothing is changed,
until the entry is fixed in the pool's bibtex. Reading from the pool
(`pull`, `add` looking in the pool) still works.

## A finished paper

Do not sync the library of a finished paper. Its keys stay as they are,
but a `pull` can change journal abbreviations and other fields that the
paper was written with. Leave `auto-push` off there, and do not pull.

## Undo in a pool

A pool is a library with its own history (see
[Undo and redo](undo-redo.md)). `papers undo` in a
library undoes a change of that library only: an entry that `add` also
added to the pool stays in the pool. To undo a change in the pool, run the
command in the pool, e.g. `papers -C ../sealevel undo`. The origin copies
of the library are restored with its bibtex: see
[Undo in a library that has a pool](undo-redo.md#undo-in-a-library-that-has-a-pool).
