# Exchanges between a library and its pool

This file specifies how a library exchanges entries with its pool, or with
another library given on the command line (`--pool PATH`): the origin
records in `.papers/origin/`, which entries are shared, the three-way
merge, `pull`, `push`, `sync`, the automatic pushes of a shallow library,
`add` looking in the pool first, the pool line of `papers status`, and the
links of a shallow library to the files of its pool.

Other files of this specification:

- the layout of a library, the `pool` setting, the states self-contained
  and shallow, the files setting and the name templates, the lock:
  `library.md`;
- the bibtex format, the `file` and `ids` fields, the same-paper rule,
  `distinct.json`, the two-way merge and the key suffix rule: `bibtex.md`;
- the history (undo, redo, the steps of a pool linked to the steps of a
  library): `history.md`;
- the line format of an entry in reports (`Added -> KEY: TITLE (...)`) and
  `--porcelain`: `formats.md`.

Two labels are used:

- **Contract**: file names, file contents and the rules that decide them.
  Two implementations working on the same libraries must read and write
  them identically.
- **Free**: messages, prompts, the order of internal steps, caches. An
  implementation may differ, as long as the contracts hold.

A section that says neither is contract.

## 1. Terms

- **Library**: the library of the command (the current library).
- **Pool of the library**: the library named by its `pool` setting
  (`library.md`). A library with a pool is **shallow**.
- **Other library**: a library given with `--pool PATH` on `pull`, `push`,
  `sync` and `add` (and on `list --pull/--push/--sync`). An exchange with
  it is a **one-time exchange**. It is handled like the pool of the
  library, except where this file says otherwise.
- **Pool**, below, means either of them: the library on the other side of
  an exchange.
- **Record** (origin record, origin copy): what the library remembers of an
  entry it exchanged with a pool (section 3).
- **Base**: the entry of a record, the third version of a three-way merge.
- **Library key**, **pool key**: the key of the entry in each library. The
  two may differ.
- **Shares links with the pool**: a shallow library and its own pool (not
  an other library). Its file links are those of the pool entries
  (section 15).

## 2. The pools of a command

### 2.1 Which pool

- `pull`, `push`, `sync` (and `list --pull/--push/--sync`): the other
  library of `--pool PATH`, else the pool of the library. Without either:
  the error `this library has no pool: give one with `--pool PATH``, and
  nothing is changed.
- `add`: looks in the other library of `--pool PATH`, else in the pool of
  the library; `--no-pool` disables the lookup (section 13). `--pool` and
  `--no-pool` together are an error.
- The automatic pushes (section 12) always go to the pool of the library.

### 2.2 Rules on a pool (contract for the conditions)

- A pool is a directory with a library configuration (`library.md`). A
  command never creates it. When it is missing, the message says
  `papers init PATH` creates it; when its parent directory is missing too,
  it suggests a disk not mounted. The exchange commands stop, and nothing
  is changed.
- An exchange goes one level: the other library of `--pool PATH` must have
  no pool itself (`PATH has a pool itself (...)`). The pool of the library
  is checked when the `pool` setting is set (`library.md`).
- A library is never its own pool: a pool path that resolves (real path)
  to the library directory is an error `pool X: this is the library
  itself` for `--pool`, and means "no pool" for the setting (`library.md`).
- A `--pool PATH` that resolves to the pool of the library is the pool of
  the library: same records, same file links (section 2.3).
- A pool with entries that could not be parsed (failed blocks, `bibtex.md`
  section 2.5) is not written to: `push`, `sync`, the automatic pushes and
  the link updates stop with an error naming the blocks and
  `Fix <pool bibtex> before writing to the pool (nothing was changed)`.
  Reading from it (`pull`, `add`) works.
- A command that holds the lock of its library also takes the lock of
  each pool it resolves, before reading it (lock protocol: `library.md`).

### 2.3 The pool id (contract)

The records name each pool by a **pool id**, a text. It is computed once
per command for each pool.

**Library identifier.** A pool whose library has an identifier (the `id`
of its library configuration, 32 lower-case hexadecimal digits,
`library.md`) has that identifier as pool id
(`7e5754a0ccd246968e910bcd2a16dcf2`). It stays when the library or the
pool moves: after a move, `papers config pool NEWPATH` finds the records
again. A configuration that cannot be read, or an `id` that is not 32
lower-case hexadecimal digits, counts as no identifier.

**Path ids.** Any other id is a **path id**: the pool's path, as earlier
versions (up to 3.0.0b5) named every pool, and as papers still names a pool
whose library has no identifier yet (a library that never recorded a
history step). A path id **designates** a pool when the id, with a leading
`~` expanded to the home directory and joined to the library directory
(absolute ids stay absolute), has the same real path as the pool
directory.

The pool id of a pool, in this order:

1. With a library identifier: the identifier. If one of the path ids
   already present in `.papers/origin/` (in the `papers-pool` comments,
   and in the `papers-pulled` entries of the legacy file) designates the
   pool, its records move to the identifier (section 3.9). `papers status`
   does not move them: it uses the path id until an exchange has moved
   them.
2. Without identifier: the first path id present in `.papers/origin/` that
   designates the pool, the ids tried in sorted order (plain string
   order).
3. Else, for the pool of the library: the `pool` setting as written in
   the configuration (`../pool`, `~/Documents/papers`).
4. Else (an other library): the path of the pool relative to the library
   directory, with `./` prepended when it does not start with `.`
   (`../shared-with-bob`, `./sub`, `../../home/me/Documents/bob`). This is
   relative even when PATH was given absolute or with `~`.

A pool without identifier gets one when a command first records a step in
its history (a push records one, `history.md`); the next exchange then
moves its records from the path id to the identifier.

The name shown in messages (`pool ../pool`) is free: papers shows the pool
of the library as its setting writes it, and `--pool PATH` as given on the
command line (an absolute path with `~` for the home directory).

## 3. Origin records

### 3.1 Files (contract)

`.papers/origin/` in the directory of the bibtex (`library.md`, Layout)
holds one bibtex file per pool:

```
.papers/origin/<name>-<hash>.bib
```

- `<hash>`: the first 6 hexadecimal digits (lower case) of the SHA-1 of
  the pool id encoded in UTF-8.
- `<name>`: the last component of a path, after normalizing it (`../pool/`
  and `../x/../pool` give `pool`; separators are those of the platform),
  turned into a slug (the slugify rule of `library.md`, Name and key
  templates); `pool` if the slug is empty. The path is the
  `papers-pool-path` of the file (section 3.2, with a leading `~`
  expanded) when it has one; else the pool id if it is a path id; else
  there is none and the name is `pool`.

Examples: pool id `7e5754a0ccd246968e910bcd2a16dcf2` with
`papers-pool-path ~/papers/shared-with-bob` gives
`shared-with-bob-569371.bib`, and without `papers-pool-path`
`pool-569371.bib`. Path ids: `../pool` gives `pool-615fe0.bib`;
`../shared-with-bob` gives `shared-with-bob-d15650.bib`;
`~/Documents/papers` gives `papers-e311da.bib`; `../My Papers` gives
`my-papers-94036c.bib`. The hash is of the id as written: `../pool/` gives
`pool-b6adbc.bib`.

The files of earlier pools stay. Setting the pool back to one of them, or
exchanging with it again, finds its records again (through the pool id,
section 2.3).

### 3.2 Format (contract)

A file is a bibtex file written as the library writes its bibtex
(`bibtex.md` section 3: fields sorted, one space of indentation, values in
braces unless bare (`bibtex.md` section 3.3), a blank line between blocks; UTF-8, LF line endings on every
platform). Its blocks, in order:

1. `@comment{papers-pool <pool id>}`: always.
2. `@comment{papers-pulled <mtime>}`: the modification time of the pool's
   bibtex, in integer nanoseconds since the epoch, at the last exchange
   that counts (section 3.6). Absent if none.
3. `@comment{papers-pool-path <path>}`: where the pool was when its
   records moved from a path id to its library identifier (section 3.9):
   the absolute path of the pool directory, with `~` for the home
   directory. Kept as read when the file is written again; not updated
   when the pool moves later. Absent if the records never moved (see the
   open questions). It is information for the reader and gives the file
   name (3.1); papers does not use it to find the pool.
4. One entry per record, sorted by lower-case library key.

Example, in a shallow library whose pool is `../pool`:

```
@comment{papers-pool 7e5754a0ccd246968e910bcd2a16dcf2}

@comment{papers-pulled 1793189510108569698}

@comment{papers-pool-path ~/papers/pool}

@article{Other2021,
 author = {Brown, Bob},
 file = {},
 papers-pool-key = {brown2021},
 papers-time = {2026-10-28T13:11:33+01:00},
 title = {Another paper},
 year = {2021}
}

@article{Smith2020,
 author = {Smith, John and Doe, Jane},
 doi = {10.1000/abc},
 file = {:../pool/files/smith_and_doe_2020_a-title-of-a-paper.txt:txt},
 journal = {Nature Geo},
 papers-pool-key = {smith_doe2020},
 papers-time = {2026-10-28T13:11:50+01:00},
 title = {A title of a paper},
 year = {2020}
}
```

The same record in a self-contained library, or for an other library, has
no `file` field.

### 3.3 What a record holds (contract)

Each entry of the file is the record of one library entry for that pool:

| Part | Meaning |
|---|---|
| entry key | the library key of the entry |
| entry type and the ordinary fields | the base: the entry as last exchanged (below) |
| `papers-pool-key` | the key of the entry in the pool |
| `papers-time` | when the record was last written: local time, ISO 8601 with the UTC offset, to the second (`2026-10-28T13:11:33+01:00`) |
| `file` | only when the library shares links with this pool: the file links of the pool entry after the exchange, written as the library writes its links (relative to the library's bibtex directory, or absolute, per its `paths` setting). Present and empty (`file = {}`) when the pool entry has no file. Not part of the base |
| `papers-pool` | only in the legacy file (section 3.8); not in the per-pool files |
| `papers-files` | written by development builds; ignored when read, removed when the record's file links are next set |

The base is the version of the side that **sent** the entry, as sent:

- `pull` and `add` from the pool: the pool entry (with its fields as in
  the pool; see the open questions about `ids`);
- `push` of an entry the pool has: the library entry as sent to the pool
  (without `file` and `ids`);
- `push` of an entry new to the pool: the new pool entry as inserted.

The receiving side has taken all of the base into account (taken, kept or
declined). What it has beyond the base shows as its own change at the next
exchange the other way: after a push, the fields only the pool entry has
come with the next pull; after a pull, the fields the library kept go to
the pool with the next push.

When reading a record as a base, the fields `papers-pool`,
`papers-pool-key`, `papers-time`, `papers-files` and `file` are removed;
the key is not used by the merge.

### 3.4 Reading (contract)

- Every file of `.papers/origin/` whose name ends in `.bib` is read, in
  sorted name order. The file name is not used to identify the pool: the
  `papers-pool` comment is. A file without it is ignored with a warning; a
  file that cannot be parsed is ignored with a warning.
- A comment is split on whitespace into a first word and the rest
  (trimmed). `papers-pool <id>` gives the id; `papers-pulled <digits>`
  gives the time (anything else than digits is ignored);
  `papers-pool-path <path>` gives the path.
- Records are indexed by pool id and lower-case library key. Two records
  of the same key for the same pool (in one file or in two files of the
  same id): the last read wins.
- The record of a library entry for a pool is the record of its key, else
  of one of its former keys (its `ids` field, `bibtex.md` section 7.1),
  without case.

### 3.5 Writing (contract for the content; free for the timing)

Records are written:

| When | Record |
|---|---|
| `pull`: an entry merged (`updated`), equal (`unchanged`), first matched (`linked`) or added (`added`) | the pool entry |
| `push`: an entry merged, equal or first matched | the library entry as sent |
| `push`: an entry added to the pool | the pool entry as inserted |
| `add` takes an entry from the pool (section 13) | the pool entry, if the library entry has no record for that pool yet |
| a link update of a shallow library (section 12.3) | only the `file` field of an existing record |

- A skipped conflict, and an entry not pushed for lack of fields, write
  no record. An entry that the pool no longer has loses its record in the
  exchanges without KEY and in the automatic pushes (section 4.3).
- Setting a record that has the same pool key and the same entry type and
  fields (values compared as written, field order aside) as the existing
  one does not change it: its `papers-time` stays. Only its `file` field is
  updated (removed when the library does not share links with the pool).
- A file is written only for the pools whose records or time changed, in
  full, atomically, and only if its content differs from the file on
  disk. The directory is created when needed.
- When the file of a pool is written under its name (3.1), the file its
  records were read from (the last one read for that id), if it has
  another name, is removed. So is the file of a path id whose records
  moved to an identifier (3.9).
- The records are saved before the library's bibtex, so that the history
  step of the library includes them (`history.md`). With `--dry-run`
  nothing is written.

### 3.6 The exchange time `papers-pulled` (contract)

The time says that the library has taken into account everything the pool
had at that time. It is set to the modification time of the pool's
bibtex (integer nanoseconds):

- **pull** without KEY and without a list selection (`--all` allowed): the
  time measured before the pull, if no conflict was skipped and the
  dialogue was not quit. A pull of named entries does not set it.
- **push** (also the automatic pushes): after the pool is saved, the new
  time, if both:
  - the pool had not changed since the last exchange (its time equals the
    recorded time before the first push of the command), or this is the
    first exchange with it (no time recorded and no record when the
    command started); and
  - no pushed entry left the pool entry with something the library entry
    does not have: after the push, a merge of the pool entry into the
    library entry with the base just recorded has no addition, no conflict
    and no new file.
- **link updates** (section 12.3) count as a push only when the pool had
  not changed since the last exchange.
- **add** from the pool (section 13): when this is the first exchange with
  the pool and the command pushed nothing to it, the pool's time.
- **status** (section 14): when it finds the library in sync with a pool
  whose bibtex changed, the current time.

In `sync`, the pull sets the time first, so the push that follows sees an
unchanged pool.

### 3.7 Renamed keys (contract)

When a command changes the key of a library entry (`edit --key`, `check
--fix-key`, ...; the same entry, its old key no longer in the library, its
new key not in it when loaded), its records in every pool file follow:
the record is moved to the new key (an existing record under the new key
is replaced). The pool key is unchanged. This happens when the library is
saved, and before the automatic push of a shallow library looks the
records up.

### 3.8 Legacy file `.papers/origin.bib` (contract for reading)

Earlier v3 builds kept all records in one file next to `origin/`:

- each record has a field `papers-pool = {<pool id>}` (missing: the empty
  id);
- the times are comments `@comment{papers-pull <mtime> <pool id>}`.

When it exists, it is read after `origin/`; its records and times are
added where `origin/` has none for that pool and key. Then all pools are
written as per-pool files (without `papers-pool` fields) and the legacy
file is removed (not with `--dry-run`).

### 3.9 Records under a path id (contract)

When the pool id of a pool is its library identifier and a path id of
`.papers/origin/` designates the same pool (2.3), the records of the path
id move to the identifier:

- each record of the path id is added under the identifier, unless the
  identifier has a record of the same lower-case library key (that one
  stays);
- the exchange time of the path id becomes that of the identifier, unless
  the identifier has one;
- `papers-pool-path` is set to the pool directory (3.2);
- at the save, the file of the identifier is written (named as 3.1 says)
  and the file of the path id is removed.

This happens in every command that exchanges with the pool (pull, push,
sync, the automatic pushes, `add` from the pool, the link updates), and
is saved with the command's other records (not with `--dry-run`). `papers
status` does not move records. A path id that does not designate the pool
of the command (an earlier pool, a pool not found) stays.

## 4. Matching entries

### 4.1 The pool entry of a library entry (contract)

For a library entry and a pool, with `D` the union of the not-same-paper
pairs of both `distinct.json` files (`bibtex.md` section 9.4):

1. With a record for this pool:
   1. the pool entry whose key is the record's pool key (without case;
      the first if several), if it is the same paper (`same` verdict, with
      `D`) as the base or as the library entry;
   2. else the first pool entry (pool order) that is the same paper as the
      base;
   3. else the first that is the same paper as the library entry;
   4. else the pool entry of the record's pool key, if no identifier of it
      contradicts the base (different DOIs, arXiv ids or ISBNs; the pairs
      of `D` are not consulted). This finds an entry without DOI whose
      title changed on both sides.
2. Without record: the first pool entry that is the same paper as the
   library entry.

Only `same` verdicts match; an `ask` verdict (title guard) is no match.
When the pool has the same paper twice, the entry of the record's pool key
is the one exchanged.

### 4.2 The library entry of a pool entry (contract)

Used by `pull KEY` (a KEY found in the pool) and `pull --all`:

1. the library entry whose key has a record for this pool with this pool
   key (without case), the first in record order;
2. else the first library entry that is the same paper (with `D`).

A pool entry without library entry is **missing** from the library.

### 4.3 Shared, removed, without record

- An entry is **shared** with a pool when 4.1 finds a pool entry, with a
  record or not. The record is only the base of the merge.
- An entry is **removed from the pool** when it has a record for the pool
  and 4.1 finds nothing.
- An entry **without record** that the pool has is shared; its first
  exchange has no base (section 5.4).

Without KEY or `--all`, `pull`, `push`, `sync` and the automatic pushes
exchange the shared entries only. For each entry removed from the pool
they print, once:

```
Other2021: removed from pool ../pool (`papers push Other2021` adds it back)
```

(with `--pool PATH`, the command in the note repeats `--pool PATH`), and
drop its record for that pool, so that the entry is no longer shared and
the note does not come again. The entry stays in the library. `push KEY`
and `push --all` add it to the pool again; `pull KEY` reports it
`Not found`; `pull --check` lists it with the note and drops nothing.

No exchange removes an entry: `rm` in the library does not remove it from
the pool, and an entry removed from the pool stays in the library.

## 5. The merge of an exchange

### 5.1 Sides (contract)

The merge combines a **target** (entry 1) with an **incoming** entry
(entry 2):

| Command | Target (keeps its key) | Incoming | Base |
|---|---|---|---|
| `pull` | the library entry | the pool entry | the record |
| `push` | the pool entry | the library entry | the record, under the pool key |

The incoming entry is a copy without `ids`, its file links written for
the target's library (resolved, then written with the target library's
path rules).

### 5.2 Fields each side keeps (contract)

- the key: the key of the target is kept. `pull` and `push` never change a
  key of the library they write to;
- `ids`: the target's own `ids` only (former keys mean nothing in the
  other library);
- `file`: not merged as a field. The links are the union of both sides,
  the target's first (`bibtex.md` section 10.4); the **new files** are the
  links of the union whose real path is not among the target's links.
  The files are then placed (sections 6, 7). The base's `file` field is
  never used.

All other fields, and the entry type (compared in lower case), are merged
one by one.

### 5.3 The three-way rule (contract)

For a field, with `t` the target's value, `o` the incoming value and `b`
the base's value (an empty or whitespace-only value counts as absent;
"equal" means equivalent, `bibtex.md` section 10.3):

| Case | Status | Result |
|---|---|---|
| `t` and `o` both present and equal | same | the preferred value (`bibtex.md` 10.3: the target's spelling; for `author`/`editor` the fuller given names) |
| `b` absent, `o` absent | same (added in the target) | `t` |
| `b` absent, `t` absent | addition (`+`) | `o` |
| `o` equal to `b` | same (changed or removed in the target) | `t` (absent: no field) |
| `t` equal to `b` | addition (changed or removed in the incoming entry) | `o` (absent: the field is removed; shown `(removed)`) |
| otherwise | conflict (`!`): changed on both sides, removed on one and changed on the other, or added on both with different values | decided (5.6); by default `t` |

A field absent from `t` and `o` is not in the result, whatever `b` has
(removed on both sides). A field changed on both sides to equal values is
not a conflict.

A change to an equivalent value (case, braces, accents, initials) is
"same": it is not sent by itself. When the entry is rewritten for another
reason, each field gets the preferred value (see the open questions).

### 5.4 Without base (contract)

An entry without record (first exchange, or a record dropped) is merged
two-way, with the fields of 5.2 kept by each side:

| Case | Status | Result |
|---|---|---|
| all present values equal, target has one | same | preferred |
| target only | same | `t` |
| incoming only | addition | `o` |
| different values | conflict | decided (5.6) |

### 5.5 Outcome (contract)

- No conflict, no addition, no new file (and, in `pull` of a library that
  shares links, no link removed by the pool, section 15.2): nothing is
  written to the target; the record is set. The outcome is `unchanged`
  with a record, `linked` without.
- No conflict: the result is applied (`updated`).
- Conflicts: decided by the `--on-duplicate` mode. A decision to merge
  applies the decided entry (`updated`); a skip changes nothing and sets no
  record (`skipped`), so the entry comes again next time.

Applying the result replaces the target's type and fields by those of the
result: the merged fields with a value, `file` (the union) and `ids` (the
target's).

### 5.6 `--on-duplicate` (contract for the decisions; free for the dialogue)

| Mode | Conflicts |
|---|---|
| `ask` | the dialogue (5.7) |
| `keep` | each conflict takes the target's value: the library's in `pull`, the pool's in `push` |
| `update` | each conflict takes the incoming value (a removal is taken as a removal): the pool's in `pull`, the library's in `push` |
| `skip` | the entry is not changed (`skipped`) |
| `error` | the command stops with an error before saving anything |

- Default: `ask` when standard input is a terminal, else `error`.
- Additions are taken in every mode; only conflicts are decided.
- `sync` uses the same mode for its pull and its push. So `sync
  --on-duplicate keep` ends with the library's values on both sides, and
  `update` with the pool's.
- The automatic pushes always use `skip` (section 12).
- The `error` message (free): `Smith2020: changed in the library and in
  pool ../pool (smith_doe2020; 1 conflict)` (pull) or `smith_doe2020:
  changed in the library and in pool ../pool (Smith2020; 1 conflict)`
  (push), then `Pass --on-duplicate with one of: ask, keep, update, skip
  (ask is the default in a terminal), see `papers pull --help`.`

### 5.7 The dialogue (free; outline)

The dialogue is that of duplicates (`bibtex.md` section 10.6), with labels
`library`/`pool` (pull) or `pool`/`library` (push), a header `KEY <- pool
X (POOLKEY)` or `KEY -> pool X (POOLKEY)`, each field marked
(` `, `+`, `!`) with a note on where it changed (`changed in pool`,
`removed in library, changed in pool`, ...), and the answers: `1` keep the
target's values, `2` take the incoming values, `f` field by field
(conflicts, then the additions, which can be declined), `e` edit the
merged entry, `s` skip, `q` quit (skip this entry and every remaining
one), `?` help. "Not the same paper" is not offered. After `q`, the
command stops processing entries; the pull then does not set
`papers-pulled`, and `sync` does not push.

## 6. `papers pull`

```
papers pull [KEY...|-] [--all] [--pool PATH] [--on-duplicate MODE] [--check]
```

`--check`: section 9.

### 6.1 Selection

1. Without KEY: all library entries; without `--all`, reduced to the
   shared entries (section 4.3, with the notes and the records dropped for
   the entries removed from the pool).
2. With KEY...: each identifier (key, DOI, arXiv id, ISBN, or `-` for
   standard input; selection rules of the command line) is looked up in
   the library first. Those not found are looked up in the pool: a pool
   entry with a library entry (4.2) selects that library entry; one
   without is a **new** entry. An identifier found in neither is an error,
   before anything changes.
3. `--all`: also every pool entry missing from the library (4.2) is new.
4. `papers list ... --pull`: the listed entries, no new entries, no
   shared filter.

### 6.2 Steps

1. The pairs of both `distinct.json` files are united, both ways (each
   side gets the pairs it does not have; a pair equal in either order is
   not added twice).
2. For each selected library entry, in library order: find its pool entry
   (4.1). None: reported `not found` if the entry was named on the
   command line, else left out. Else, in a library that shares links,
   repair its broken links to pool files (15.3), then merge (section 5)
   and apply.
3. For each new pool entry: add it to the library (6.3).
4. Set `papers-pulled` (3.6).
5. In a shallow library pulling from an other library: push the new
   entries to its own pool (section 12, as after `add`).
6. Save: the pools written, the origin records, then the library.

### 6.3 New entries (contract)

- Key: the pool key; if the library has it already (without case), the
  letter suffix rule of `bibtex.md` section 8 (`other2021` gives
  `other2021b`).
- Fields: those of the pool entry, without `ids`; its links written for
  the library.
- Files: placed as in 6.4.
- Record: the pool entry.

### 6.4 Files of a pull

- A library that shares links with the pool: the pool's files are linked
  where they are, in the pool's files directory. Links that the pool
  entry removed since the record are removed (15.2).
- Otherwise (a self-contained library, or an other library): the files
  new to the library entry are placed as the `files` setting says
  (`library.md`, The files setting); a file of a pool is copied (a hard
  link when possible), never moved; `link` links it where it is. The
  files the entry had before stay where they are. Without files
  directory, the files are linked.
- A shallow library pulling from an other library places them in its own
  pool's files directory, named with its pool's name template (as `add`
  does, 15.1).

## 7. `papers push`

```
papers push [KEY...|-] [--all] [--pool PATH] [--on-duplicate MODE]
```

### 7.1 Selection

- Without KEY: the shared entries (4.3). If there are none:
  `push to pool ../pool: no entries shared with it (`papers push KEY` or
  `papers push --all` adds entries to it)` (with `--pool PATH` repeated),
  and only the dropped records are saved.
- KEY...: the entries named (in the library only).
- `--all`: every library entry, including those removed from the pool.
- `list ... --push`: the listed entries.

### 7.2 Steps

1. The pool must be readable (2.2). The pairs of both `distinct.json` are
   united (6.2).
2. For each entry, in order: find its pool entry (4.1).
   - Found: merge (section 5, the pool entry as target) and apply to the
     pool entry. In a library that shares links with the pool, the
     incoming entry leaves out the links that the pool removed since the
     last exchange (15.2): push does not add them back. Files: the links of the result that the pool entry did
     not have are copied (a hard link when possible) into the pool's files
     directory, named with the pool's name template; the pool entry's
     own links stay; in a shallow library, the links that the command
     added to the library entry (not present when it was loaded) are kept
     where they are. The record is the library entry as sent.
   - Not found (with KEY, `--all`, or an automatic push of a new entry):
     add it (7.3).
3. Save the pools that changed, then set `papers-pulled` (3.6), then the
   records, then the library.

A push does not change the library entries.

### 7.3 Entries new to the pool (contract)

- An entry with no field other than `file` and `ids` is not pushed
  (`empty`).
- Key: from the pool's key template (`library.md`), with the suffix rule
  of `bibtex.md` section 8 against the pool's keys. If the template gives
  no key: the library key (an entry without key is `empty`), with a
  suffix if the pool has it.
- Fields: those of the library entry, without `ids`.
- Files: copied (a hard link when possible) into the pool's files
  directory, named with the pool's name template. In a shallow library,
  the links that the command added are linked where they are, and files
  already in the pool's files directory are linked there.
- Record: the new pool entry.

## 8. `papers sync`

```
papers sync [KEY...|-] [--all] [--pool PATH] [--on-duplicate MODE]
```

1. A pull (section 6) of the selection: without KEY the shared entries,
   with KEY the entries named (a KEY only in the pool is added to the
   library), with `--all` also the missing pool entries.
2. If the pull skipped a conflict or the dialogue was quit: the pull is
   saved, then the error `not pushed: the pull left conflicts undecided
   (KEY, ...). Decide them with `papers pull`, then run `papers sync`
   again` (or `(quit)`); exit status 1.
3. A push (section 7) of the same selection: without KEY the shared
   entries (after the pull), with KEY the entries named (a KEY only in the
   library is added to the pool), with `--all` every library entry.
4. Report (section 11.3).

## 9. `papers pull --check`

Reports only; nothing is merged or written.

- Selection: as `pull`, but without KEY (and without `--all`) the shared
  entries and the entries removed from the pool; no record is dropped.
- Lines, in order:
  - without KEY: `pool ../pool: <state>` with the state of 14.2 (`up to
    date`, `changed since last pull or push`, `never pulled`, `not pulled
    from yet`);
  - an entry removed from the pool: the note of 4.3;
  - an entry without record whose pool entry differs (a conflict, an
    addition or a new file): `KEY: in pool ../pool as POOLKEY, not pulled
    yet`;
  - an entry with record: the fields the pull would take or decide (the
    additions and the conflicts of the three-way merge), plus `file` if
    there are new files or links removed by the pool, sorted:
    `Smith2020: changed in pool ../pool: journal, note, year`, with
    ` (1 conflict)` / ` (2 conflicts)` when there are conflicts.
- No line: `nothing to pull`.

## 10. One-time exchanges: `--pool PATH`

- The other library is resolved as in 2.2 (it must have no pool), and
  gets a pool id (2.3) and its own origin file. Its records work as those
  of the pool: the next exchange is three-way.
- Its records never have a `file` field. The file links of a shallow
  library are those of its own pool only.
- Files taken from it are copied as the `files` setting says (never
  moved); files sent to it are copied into its files directory.
- A shallow library places the files it takes in its own pool's files
  directory (15.1), and pushes the entries new to the library to its own
  pool, as `add` does (`[also added to pool ...]`). The changes of fields
  go to its own pool with `push`, or with auto-push.
- Nothing is pushed to the other library automatically.

## 11. Reports (free, but the words are used by the documentation)

### 11.1 Entry lines

One line per entry added, modified, skipped, not found or not pushed,
with the entry line format of `formats.md` section 6 and a note in
brackets:

| Command | Outcome | Line |
|---|---|---|
| pull | added | `Added -> other2021b: Third paper  [from pool ../pool]` |
| pull | updated | `Modified -> Smith2020: A title of a paper (doi:10.1000/abc) [from pool ../pool]` |
| pull | skipped | `Conflict -> KEY: ... [skipped, not taken from pool ../pool]` |
| pull | not found | `Not found -> KEY: ... [not in pool ../pool]` |
| push | added | `Added -> Other2021: Another paper  [to pool ../pool]` |
| push | updated | `Modified -> Smith2020: ... [in pool ../pool]` |
| push | skipped | `Conflict -> KEY: ... [skipped, not pushed to pool ../pool]` |
| push | empty | `Not pushed -> KEY: ... [no fields or no key, not pushed to pool ../pool]` |

The entry shown is the library entry (its key), also for push.
`unchanged` and `linked` have no line.

### 11.2 Counts

After the lines, when more than one entry was not `unchanged`, or when
there is no line: `pull from pool ../pool: 1 modified, 1 added` (`push to
pool ...`), counting the outcomes other than `unchanged` in the order they
first appear, with the words `added`, `modified`, `linked`, `skipped`,
`not found`, `empty`; or `nothing to pull from pool ../pool` (`nothing to
push to pool ...`).

### 11.3 `sync`

The pull's lines (without `not found`) and counts, then the push's. When
neither has a line nor a count: `nothing to sync with pool ../pool`, or,
without KEY and with nothing exchanged, `nothing to sync with pool
../pool: no entries shared with it (`papers sync --all` adds the entries
missing on each side)`.

## 12. Automatic pushes of a shallow library

Only a shallow library pushes on its own, and only to its own pool. A
self-contained library ignores the `auto-push` setting. Nothing is ever
pulled automatically.

### 12.1 What is pushed (contract)

After a command that changes entries (`add`, `edit`, `tag`, `check`, the
actions of `list` that change entries, `file attach`, `file rename`,
`file mv`, `file detach`, `file rm`, `file fix`, `history --revert`, and
undo/redo with auto-push, see `history.md`), before the library is saved:

1. **New entries** (not in the library when it was loaded, by key or
   former key): always pushed, as `push KEY` (added to the pool, or merged
   if the pool has the paper).
2. **Modified entries** (changed since loaded; an entry renamed in the
   command, or found by a former key in its `ids`, is modified): with `auto-push true`, those shared
   with the pool are pushed. Those removed from the pool get the note and
   lose their record (4.3).
3. **File links**: the new or modified entries whose set of links (real
   paths) changed since loaded get their links updated in the pool entry
   (12.3), whatever `auto-push` says, except the entries just added to
   the pool or not pushed for lack of fields.

Removed entries are never pushed (`rm` does not reach the pool). The
pushes use `--on-duplicate skip`: an entry changed in the pool too (a
conflict) is saved in the library, not pushed, and gets the note
`not pushed: changed in the pool too; papers sync decides`. When the pool
cannot be used, the command warns `not pushed to the pool: <reason>` and
saves the library.

### 12.2 Notes

The line of each entry in the command's report gets a note in brackets
(several joined by `; `):

| Outcome | Note |
|---|---|
| added | `also added to pool ../pool` |
| updated | `also modified in pool ../pool` |
| links | `file links also updated in pool ../pool` (not when the entry was also `updated`) |
| skipped | `not pushed: changed in the pool too; papers sync decides` |
| empty | `not pushed to pool ../pool: no fields or no key` |
| removed | `removed from pool ../pool (`papers push KEY` adds it back)` |
| taken by `add` | `from pool X` (section 13), first |

Example: `Added -> perrette_yool2011: Near-ubiquity ... [from pool
~/Documents/papers/arctic; also added to pool ~/Documents/papers/sealevel]`.
Commands that do not list the entries print `KEY: <note>` lines. The counts
of the push are logged at info level: `push to pool ../pool: 1 with file
links updated`. With `--porcelain`, the notes are not printed
(`formats.md` section 7).

### 12.3 Link updates (contract)

For an entry whose links changed in the command, with `before` its links
when loaded and `after` its links now:

- the links to send: those of `after` that the command added (not in
  `before`), wherever they point, and those of `after` inside the pool's
  files directory;
- the links removed: those of `before` not in `after`.

The pool entry (4.1) becomes: its links without the removed ones, then
the links to send that it does not have. Only its `file` field changes;
no file is copied or deleted. If it did not change, nothing is done. The
record's `file` field is set to the new links (when the entry has a
record). An entry that the pool does not have, with links to send, is
pushed (added to the pool, 7.3). A link that the entry had when loaded,
outside the pool's files directory, is not sent: `push` sends it with the
other fields.

## 13. `add` looks in the pool first

### 13.1 Lookup (contract for what is matched)

`add` looks in the pool of the library, or in the other library of
`add --pool PATH`, unless `--no-pool`, before any network query. For a
PDF, a DOI and `--key`, the library is looked at first (a paper it has
gets the files attached, `bibtex.md`); an entry of an added file is looked
up in the pool first, and the entry taken then goes through the duplicate
check of the library like any added entry.

| Added | Pool entry taken | Key of the new entry |
|---|---|---|
| a PDF | a pool entry with a file of the same content (same real path, or same size and checksum); else the DOI given with `--doi`, else the DOI of the PDF metadata (the pool entry of that DOI); else the first DOI found in the text of the PDF whose pool entry's title appears in the text | from the library's key template |
| `--doi DOI` | the pool entry of that DOI (same-paper rule on the DOI alone) | from the library's key template |
| `--key KEY` alone | the pool entry of key KEY, without case (when the library has no entry of that key) | the pool key |
| an entry of an added bibtex (or RIS, CSL-JSON) file | the pool entry that is the same paper (with the library's `distinct.json`) | the added entry's key |

The entry inserted:

- the pool entry's fields, without `ids`; for an added bibtex entry, also
  its fields that the pool entry does not have (the pool's values win
  conflicts);
- the pool entry's files; plus the files given that have a content
  different from all of them (they are placed as the files mode says);
- inserted as any added entry (duplicate check in the library, key
  suffix);
- the record of the library entry it ended in is set (the pool entry as
  base), if it has none for that pool.

Files: in a shallow library from its own pool, linked where they are;
otherwise copied (a hard link when possible) into the files directory as
the files mode says, or linked in `link` mode; a pool file is never
moved. In `move` mode, a file given that has the same content as a file
the entry links to now is removed (it is stored already), unless it is in
the pool's files directory or another entry links to it.

`add --key KEY` when neither the library nor the pool has KEY:
`nothing to add: no file, identifier or bibtex given, and no entry KEY in
pool X`.

### 13.2 After the lookup

- In a shallow library, the new entries are pushed to its own pool
  (section 12), also those taken from an other library with `--pool PATH`.
  Nothing new is sent to the other library.
- The first exchange with the pool records `papers-pulled` (3.6).
- The report line of an entry taken says `[from pool X]`.

## 14. `papers status`

### 14.1 The pool line

In a shallow library, `papers status` prints `* pool:   <pool setting>
(<state>)` for its pool, then, for some states, a hint as the last line.
A library without pool (or that is its own pool) has no pool line.

| State | Condition | Hint |
|---|---|---|
| `missing` | the pool directory does not exist | |
| `not a library` | the directory has no library configuration | |
| `not pulled from yet` | no `papers-pulled` and no record for the pool | `` `papers pull` takes the entries shared with the pool `` |
| `never pulled` | no `papers-pulled`, but records | `` `papers pull` takes the changes of the pool `` |
| `in sync` | 14.3 finds no difference (or the library has no bibtex) | |
| `pool changed` | 14.3 | `` `papers pull --dry-run` shows the changes, `papers pull` takes them `` |
| `library changed` | 14.3 | `` `papers push --dry-run` shows the changes, `papers push` sends them `` |
| `both changed` | 14.3 | `` `papers sync --dry-run` shows the changes, `papers sync` exchanges them `` |

The state words are free text, but the Desktop application and the
documentation use them; keep them.

### 14.2 The time check (`pull --check`)

`pull --check` uses the recorded time only: `never pulled` / `not pulled
from yet` as above; `changed since last pull or push` when the pool's
bibtex time differs from `papers-pulled`; else `up to date`.

### 14.3 The content comparison (contract for the result)

`status` compares each library entry that has a record for the pool, as
pull and push would find it:

1. Entries without record are not considered.
2. If the pool's bibtex time equals `papers-pulled` and the entry's fields
   equal the base's fields, the entry is skipped. Fields here: names in
   lower case, values as written, without `file`, `ids` and the
   `papers-*` fields; the entry type and the key are not compared.
3. Else find the pool entry (4.1). None: **pool changed** (removed from
   the pool).
4. The pull merge (5.1, library as target, base the record): a conflict
   means **both changed**; an addition, a new file or a link removed by
   the pool (15.2) means **pool changed**.
5. The push merge (pool as target, the incoming entry as push sends it,
   without the links that the pool removed, 7.2): a conflict, an addition
   or a new file means **library changed**.
6. Stop when both are found.

The library is read as on disk, without the repair of links (15.3).

When nothing differs and the pool's bibtex changed since `papers-pulled`
(other entries of the pool changed, or the same change was made on both
sides), status records the current time in the origin file, as a pull
would (not with `--dry-run`).

### 14.4 The fast comparison by pieces (free; contract for the file if written)

To avoid comparing every entry, `status` keeps, for each pool, the pieces
of three texts when it last found them in sync: the library's bibtex, the
pool's bibtex and the library's origin file for that pool.

- Pieces: the text cut as the history cuts the bibtex (`history.md`:
  before each line that starts with `@`, groups of entries ending after an
  entry whose CRC-32 of its UTF-8 text is divisible by 32, or after 256
  entries), each named by the SHA-256 (hexadecimal) of its UTF-8 text. A
  missing file is the empty text.
- Stored in `exchanges.json` in the history folder of the library's
  project (`history.md` 2.2: `projects/<library id>/exchanges.json`, in
  the shared store or in the separate store of the library), as one
  JSON object: `{"<pool id>": {"library": [...], "pool": [...],
  "origin": [...]}}`, each list the sorted checksums. Written in compact
  form: separators `, ` and `: `, no indentation, no final newline, non-ASCII characters escaped as `\uXXXX`.
  A library without id has no such file. A file or an entry that cannot
  be read means "not known".
- Use: the pieces of each text now that are not in the stored list are
  new. The keys of the entries in the new pieces (`@type{key,` at the
  start of a line, not `@comment`, `@string`, `@preamble`), in lower
  case: library and origin pieces give library keys, pool pieces give
  pool keys. If there is no new piece anywhere, the state is `in sync`
  without reading the entries. Else only the entries whose library key,
  or record pool key, is among those keys are compared (14.3).
- Written: after 14.3 finds `in sync` (the origin pieces taken after the
  origin file was updated), and after the fast path when it updated the
  time. Not with `--dry-run`.

An implementation may skip this cache and compare every entry. If it
writes `exchanges.json`, it must write exactly this content: papers trusts
it.

## 15. Shallow libraries and the files of the pool

The layout and the files setting of a shallow library are in `library.md`
(Pools and shallow libraries; The files directory). This section covers
what the exchanges do with the files.

### 15.1 The pool's files directory

Where a shallow library places files (its pool's files directory, the
pool's name template, never renaming a file already there) is in
`library.md`, Files of a shallow library and The files setting; it
applies also to
`pull`/`sync`/`add` with an other library.

### 15.2 Links that the pool removed (contract)

In a library that shares links with its pool, a pull of an entry with a
record that has a `file` field removes from the library entry the links
(by real path) that the record has and the pool entry no longer has. A
link the pool entry never had stays. A record without `file` field removes
nothing. No file is deleted. (The library entry may be left with an empty
`file = {}` field; see the open questions.)

A push sends the library entry without these links (7.2), so the pool
entry does not get them back. The record written by that push keeps them
in its `file` field (the pool entry's links, then these), so that the next
pull still removes them from the library. `papers status` compares the same
way (14.3): such a link makes `pool changed`, not `both changed`.

### 15.3 Repair of broken links to pool files (contract for the choice)

A link of a library entry is repaired when it is broken (no file at its
path) and lies inside the files directory of the pool of the library. The
candidates are the files of the pool entry of the same paper (4.1) that
exist and that the entry does not link to already. For the broken links
of one entry:

1. a link gets the candidate of the same base name;
2. else the one candidate named `<anything>--<base name of the link>` (the
   pool renamed the file as an attachment labelled with its former name),
   if exactly one is;
3. then, if one link and one candidate are left, that candidate;
4. else, if links are left, the first of them gets all the remaining
   candidates and the others are removed.

A link without candidate stays as it is. The repaired links replace the
broken ones in place.

When:

- each time a shallow library is loaded by a command (logged at info
  level: `KEY: broken link to a pool file repaired: [...]`); the library is
  then written at the next save of the command, even if nothing else
  changed;
- in `pull`, before the merge of each shared entry;
- by `papers file fix`, and before `papers config pool none` copies the
  pool files.

`papers status` does not repair (14.3).

### 15.4 Changing the pool

`papers config pool PATH|none` converts the links (copy of the pool files
into the library, or relinking to the pool's copies): `library.md`, Files
of a shallow library. The records of PATH, if any, are found again through
its pool id (2.3).

## 16. The history (outline)

Details are in `history.md`.

- Each library has its own history. A state of a library includes its
  origin files (`.papers/origin/*.bib`, and the legacy `origin.bib`) and
  its `distinct.json`, with the bibtex. Undo, redo and restore bring the
  records back with the entries, so the bases match the entries again.
- A command that writes a pool (a push, an automatic push, `add` in a
  shallow library) also makes a state in the pool's history. The library's
  state names the pool's state (by the pool's project id and the path of
  its configuration). Undo in the library takes the pool's step back when
  the pool is still where the command left it, and otherwise reverts that
  step as a new step of the pool; `undo --library-only` leaves the pool.
- Redo after an undo that took the pool's step back, when the pool changed
  since, does the step again in the pool, as a new step of the pool.
- After undo or redo in a shallow library with auto-push, the shared
  entries that differ from their records are pushed (conflicts skipped).
  A push that sends something is a new step: the redo list is dropped, as
  after any command, and a line says so (free).
- `exchanges.json` (14.4) lives in the library's history folder but is
  not part of the states.

## Open questions

1. **Status ignores a change of entry type.** When the pool's bibtex time
   is unchanged, an entry whose fields equal its base is skipped without
   comparing the entry type, so a library entry changed from `@article`
   to `@book` shows `in sync`, while `push` would send it.
   `papers/pools.py:1552` (`_fields`), `papers/pools.py:1644`.
2. **Status reads the library without repairing pool links.** A file the
   pool renamed makes `status` say `both changed`, while `pull` repairs
   the link at load and reports `nothing to pull`.
   `papers/pools.py:1635`; repair at load in `papers/library.py:100`.
3. **Empty `file` fields.** Records of a shallow library store `file = {}`
   for a pool entry without files (`papers/pools.py:758`), and the removal
   of links in a pull can leave `file = {}` in the library bibtex
   (`papers/pools.py:918`). Is an empty field intended, or should it be
   absent?
4. **The base of a pull keeps the pool's `ids`.** The record of `pull` and
   `add` is the pool entry with only `file` and the `papers-*` fields
   removed, so it may hold the pool's `ids` (former pool keys), which the
   merge ignores. `papers/pools.py:605`.
5. **The base of a push of a new entry is the pool entry as inserted**,
   not the library entry as sent, unlike the other pushes.
   `papers/pools.py:1035`.
6. **The piece cache can miss an entry removed from the pool** when its
   piece disappears without a new piece appearing (a piece made of that
   entry alone). `status` then says `in sync`, while `pull` would print
   the removal note. `papers/pools.py:1587-1596`.
7. **`status` writes without lock or history step.** It may rewrite the
   origin file (`papers-pulled`) and `exchanges.json`, outside a command
   that locks the library and without a state in the history.
   `papers/pools.py:1631-1633`, `papers/pools.py:1668-1671`.
8. **`status` ignores shared entries without record.** An entry matched by
   the same-paper rule but never exchanged is not compared, although
   `pull` would link or merge it. `papers/pools.py:1640`.
9. **`never pulled` versus `not pulled from yet`.** The names do not say
   the difference (records without exchange time, versus no record).
   `papers/pools.py:1306-1312`.
10. **Origin files under another name.** Every `.bib` file of
    `.papers/origin/` is read, but a pool is always written to its
    computed name, and only the last file read for its id is removed then
    (3.5). A second file of the same `papers-pool` id (copied, or named by
    another implementation) whose name sorts before the computed file's is
    never rewritten nor removed: its records lose to the computed file's,
    but a record that the computed file no longer has (dropped by an
    exchange) comes back from it. `papers/pools.py:555-593`,
    `papers/pools.py:740-747`.
11. **Two path ids for one pool.** If two path ids designate the same pool,
    one exchange moves only the first in sorted order to the identifier
    (or, without identifier, uses it); the records of the other are
    ignored until the next exchange moves them, where the records already
    under the identifier win. `papers/pools.py:350-351`.
12. **Record lookup by key under a reused pool key.** Step 4 of 4.1 takes
    the pool entry of the record's pool key when no identifier
    contradicts the base: an entry without DOI, arXiv id or ISBN that the
    pool replaced by another paper under the same key is matched.
    `papers/pools.py:260-270`, `papers/pools.py:737`.
13. **Equivalent changes are not sent.** A change to an equivalent value
    (case, braces, initials to full names) is not exchanged by itself;
    when the entry is rewritten for another reason, the names take the
    fuller form, which may be either side's. `papers/merge.py:157-160`,
    `papers/pools.py:907-909`.
14. **`add` from a pool sets the exchange time on the first exchange
    only.** A later `add --pool PATH` from an unchanged other library does
    not update `papers-pulled`. `papers/pools.py:1007-1011`.
15. **The dialogue says the origin is the pool version** (`origin = the
    pool version at the last pull or push`), also after a push, where
    the base is the library's version. `papers/merge.py:506`.
16. **`keep` and `update` mean opposite sides in pull and push.** `keep`
    keeps the target (library in pull, pool in push). In `sync` the same
    word is used for both steps. Is that the intended reading of the
    option? `papers/merge.py:823`, `papers/cli/pool_cmds.py:200-215`.
17. **Rekey overwrites.** When a key is renamed to a key that already has
    a record for a pool (a record left by a removed entry), that record is
    replaced silently. `papers/pools.py:637-644`.
18. **`papers-pool-path` is written only when records move.** A pool
    whose library has its identifier at the first exchange gets no
    `papers-pool-path` line, so its origin file is named `pool-<hash>.bib`
    whatever its folder, while `docs/pools.md` says the file is named
    after the pool folder and records where the pool was. Should the path
    be written at every exchange? `papers/pools.py:697`,
    `papers/pools.py:730-736`.
19. **`status` names the origin file without `papers-pool-path`.** For the
    fast comparison (14.4), `status` reads the origin file under the name
    computed from the pool id alone: a file named after the pool folder
    is not found, its pieces are those of the empty text, and a change of
    the records alone is not seen. `papers/pools.py:1710`.
20. **Origin files are read with the platform encoding.** They are written
    as UTF-8, but read with the platform's default encoding, without
    dropping a byte order mark, unlike the bibtex; the same holds for the
    pool's configuration when its identifier is read.
    `papers/pools.py:480`, `papers/pools.py:570`.
