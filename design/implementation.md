# The Python implementation: internal structure

This document is **not part of the specification**. The other files of
`design/` say what papers does on disk and on the command line; they
leave the internal structure free. This one describes how the Python
implementation is built where the choice of data structure or algorithm
matters for speed, memory or concurrency, why it was built that way, and
what another implementation (the Rust one, the desktop application) could
do differently. Nothing here binds another implementation, and where this
document and the specification differ, the specification is right.

Module names (`papers/bib.py`, ...) refer to the Python implementation.

## 1. Measurements

The numbers below were measured on a laptop (Intel Core Ultra 5 125U,
Python 3.14, bibtexparser 2.0.1), on generated libraries, with the
history and the caches in a temporary folder on tmpfs (so file system
costs are lower than on a disk). Each entry is an `@article` with 1 to 6
authors (some with LaTeX accents or non-ASCII names), a title of 5 to 14
words, year, journal, volume, pages; 70% have a DOI, 30% an abstract of
150 words, 20% keywords. The file is in papers' output format (sorted,
one-space indent), about 660 bytes per entry:

| Entries | Bibtex size | Pieces (history.md 2.3) |
|---|---|---|
| 1 000 | 0.7 MB | 34 |
| 10 000 | 6.6 MB | 326 |
| 50 000 | 33 MB | 1 580 |

Times are the best of 1 to 3 runs, in milliseconds unless said otherwise.
They show orders of magnitude, not benchmarks.

## 2. The bibtex in memory

### 2.1 Structure

The Python implementation uses bibtexparser 2 (`bibtexparser.Library`):
a list of blocks (`Entry`, `String`, `Preamble`, `ExplicitComment`,
`ImplicitComment`, and the failed blocks), and dictionaries by key for
entries and strings. An `Entry` has a type, a key, a list of `Field`
objects (name, value, start line) and the raw text it was read from.
papers wraps the library in `Biblio` (`papers/bib.py`), which adds the
files directory, the `distinct.json` pairs and what is needed to detect
changes.

After parsing, `entries.lowercase_fields` turns field names to lower
case and turns into failed blocks the entries that BibTeX would reject
for case reasons (a field given twice up to case, a key equal up to case
to an earlier one, bibtex.md 2.5 and 2.6).

Costs:

- `Library.entries` builds a new list by filtering the blocks at each
  access: 0.27 ms for 10 000 entries. Code that reads `biblio.entries`
  inside a loop over entries is quadratic (see 8.5).
- `Library.remove` and `replace` search the block list linearly.
- Memory: about 4.7 kB per entry after parsing, about 7 times the text
  (10 000 entries: +47 MB; 50 000 entries: +236 MB of peak RSS). Each
  entry keeps its raw text, each field a Python object with its value
  string and line number.

### 2.2 Writing

A save sorts the blocks (`entries.sort_blocks`, the comments above a
block stay with it) and formats the whole library
(`entries.format_library`). bibtexparser's own writer deep-copies every
block; papers copies only the `Field` objects (the value strings are
shared) and runs the enclosing step on the copies.

The output format is canonical (bibtex.md 3): formatting a file that
papers wrote gives the same text. So an entry that did not change is
written back byte for byte without being kept as text: it is formatted
again and gives the same bytes. The only blocks written from their raw
text are the failed blocks.

Before writing, `Biblio.save` compares the new text with the file:

- `read_state` keeps the path, `(st_size, st_mtime_ns)` and the text as
  read or last written. If size and time are unchanged, the remembered
  text is used; otherwise the file is read again and compared
  (`BibtexChanged` if another program changed it).
- If the new text equals the text on disk, the file is not written.
- Otherwise `utils.write_atomic` writes a temporary file in the same
  folder, `fsync`s it, keeps the permissions, and renames it over the
  file. The folder itself is not `fsync`ed.

`Biblio.unchanged` avoids even the formatting when nothing changed: at
load, `mark_loaded` keeps copies of the entries; `unchanged` compares
`Counter`s of `(type, key, sorted fields)` tuples of the loaded and the
current entries. `changed_entries` matches entries by key, by a key they
had earlier in the command, or by a former key in `ids`.

| | 1 000 | 10 000 | 50 000 |
|---|---|---|---|
| parse, without cache | 71 | 709 | 3 325 |
| `sort_blocks` | 0.7 | 18 | 89 |
| `format_library` (sorted) | 11 | 130 | 718 |
| sha256 of the whole text | 0.8 | 8 | 44 |

Ideas for another implementation:

- Keep the byte range (or the text) of each entry as read. When an entry
  has not changed since load and the file was written by papers, its
  output is its input; only changed entries need formatting, and the
  output is a concatenation in sorted order. A file not written by papers
  (another layout) still needs a full format once.
- An arena of entries with interned field names and values as slices of
  the file buffer would bring the memory close to the size of the text.
- A vector of entries plus a key index (`HashMap<lowercase key, index>`)
  makes the lookups that Python does by scanning (`_insert_new` scans
  `entries_dict`) constant time.

## 3. The parse cache

`papers/parsecache.py`, history.md 11. The text is cut into pieces as the
history cuts it (2.3 there), and for each piece the blocks that
bibtexparser's splitter makes of it are stored as JSON under
`<cache dir>/parsed/<ab>/<sha256>.json`. At load, each piece is looked up
by its sha256; the blocks of all pieces are joined (line numbers shifted
by the lines of the pieces before) and the rest of bibtexparser's parse
(the middlewares: enclosing removal, `@string` interpolation, duplicate
keys) runs on the whole library. A piece with a block that is not an
entry, string, preamble or comment is not cached and the whole text is
parsed without the cache.

Why by piece: an edit outside papers, an undo, or a sync client that
replaces the file changes only the pieces it touches; the cache is found
by content and needs no invalidation.

| | 1 000 | 10 000 | 50 000 |
|---|---|---|---|
| parse, without cache | 71 | 709 | 3 325 |
| parse, cache filled by this parse | 110 | 1 127 | 4 995 |
| parse, warm cache | 41 | 366 | 2 568 (partly warm, see below) |
| cache size on disk | 1.5 MB | 14.8 MB | 52 MB (limit) |

Observations:

- With a warm cache, half the time (10 000 entries: 0.37 s of 0.62 s
  under the profiler) is the bibtexparser middlewares, which run again on
  every entry, and 0.12 s is `lowercase_fields`. The JSON reading is
  about 0.05 s. Caching the blocks after the enclosing step and the case
  rules (both are local to an entry) would leave only the `@string`
  interpolation and the duplicate-key pass for the whole library.
- The cache JSON is 2.2 times the size of the bibtex (it holds the raw
  text and the values). The limit is 50 MB for all libraries of the
  machine. A library of 50 000 entries does not fit: 1 136 of its 1 580
  pieces stay, and at each load the first ~440 pieces miss, are parsed and
  written again (about 20 MB), and the pruning then removes them again,
  since they are the oldest by modification time. A size limit relative
  to the libraries in use, or a more compact format, avoids this.
- After a parse that added pieces, the whole cache folder is walked to
  prune it (one `stat` per file).

Ideas for another implementation:

- A native parser at 100–200 MB/s parses 33 MB in well under a second;
  a cache may not be needed. If one is, it must not be written into
  `<cache dir>/parsed/` (contract, history.md 11).
- A binary format (one file per library: pieces and their parsed entries,
  memory-mapped) would cost one read instead of one file per piece.

## 4. The history store

`papers/history.py` (the store, independent of the rest of papers),
`papers/backup.py` (recording, undo, redo, restore), `papers/journal.py`
(file operations). The layout and the rules are in history.md 2.

### 4.1 Pieces and content addressing

`Store.put_text` cuts the text (`_pieces`: a regex split before each line
that starts with `@`, then grouping by `crc32(segment) mod 32 == 0`, at
most 256 segments), computes the sha256 of each piece, and for each
piece either refreshes the modification time of the existing object
(`os.utime`) or writes it compressed (zlib, default level) through a
temporary file and a rename.

A one-entry change rewrites one piece (or two, when the change creates or
removes a cut point). All states share the unchanged pieces; all projects
of a store share identical pieces (a library and its copy).

| | 1 000 | 10 000 | 50 000 |
|---|---|---|---|
| cut + sha256 of every piece | 4 | 46 | 246 |
| `put_text`, empty store | 17 | 163 | 882 |
| `put_text`, all pieces present (stat + utime each) | 4 | 43 | 240 |
| read a whole state back (`Store.text`) | 6 | 65 | 382 |
| compressed size of one copy | 0.13 MB | 1.2 MB | 6.1 MB |

500 commands that each change one entry of the 10 000-entry library
(measured with `Store` directly): 4.9 MB of objects (1.2 MB for the first
copy, then about 7 kB per step), and 10.6 MB of state files.

A state lists the sha256 of each piece of its bibtex: 326 pieces give a
state file of 21 kB, 1 580 pieces about 105 kB. The state files are not
counted by `history-size` (history.md 9.1), and in this test they are
twice the size of the objects. Ideas: write the piece list once per
distinct bibtex (a "tree" object named by the sha256 of the list, as git
does), so that a state refers to one tree; or store the list as a
difference from the parent. Either changes the format, so it would be a
change of the specification.

### 4.2 Reading states

`Project.states()` reads every state file of the project on its first
call and keeps them in memory for the command: 26 ms for 500 states of 21
kB. Most commands that save call it (the head, `start_state`, the count
for pruning every 50 states). It grows linearly with the number of states
times the number of pieces.

Ideas: read only the states on the line of the head (follow `parent`),
and read the others only for pruning and `papers history --all`; or keep
an index file of `(id, parent, time, bibtex sha)` per project, rebuilt
when it disagrees with the folder listing.

### 4.3 Pruning

`Store.prune` (history.md 9.2) lists the sizes of all objects
(`os.scandir` of the 256 folders), reads all states of all projects,
counts references per object, sorts the unprotected states by time and
drops them oldest first until the size fits. Its cost is linear in
objects + states × pieces: it keeps one `Project` per id for the whole
prune, so each state file is read once. (Before, each dropped state was
removed through a new `Project` whose `drop` read every state file again,
quadratic in the number of states: 500 states of the 10 000-entry library,
162 dropped, took 3.8 s; now 0.08 s.)

Pruning runs after a command that deleted files, after `history
--remove`, and when the number of states of the project is a multiple of
50, so its cost is paid by about one command in 50.

### 4.4 Writing order and crash safety

The contract order (history.md 2.8: objects, then state, then head)
protects against a concurrent prune: an object written or refreshed less
than an hour ago is not removed while its state is not yet written.

The order of a save (`library.savebib`):

1. `backup.sync_head`: if the bibtex on disk is not the head's state, it
   is recorded first (`outside` or `start`). A command may have written
   origin records before its save; for that case `backup.start` keeps
   the texts of the library as they were at the start of the command, in
   memory, and `sync_head` records those;
2. `.papers/files.json` (`checksums.update`);
3. the bibtex (`write_atomic`), then `.papers/distinct.json`;
4. `backup.record`: objects, state, head.

A crash between 3 and 4 leaves a bibtex that the history does not have.
The next command finds that the bibtex is not the head's state and
records it as changed outside papers: the content is safe, but the file
operations of the crashed command are not in a state, so undo cannot put
the moved files back by operation (it can still find them by checksum).

Durability is left to the operating system: `history._write` (objects,
`heads.json`) and `Project.add` (states) do not `fsync`, and
`write_atomic` does not `fsync` the folder. After a power loss, a file
system may keep the rename and lose the data, leaving an empty object
that a state refers to, or an empty state file. Such files are detected
when read (history.md 2.9): `Store.text` raises `history.Damaged` (a
`KeyError`) for a piece missing, empty or not zlib; `Store.check_file`
for a file object whose sha256 differs; `Project.states` sets aside the
state files that are not JSON (`Project.damaged`). `backup._plan` reads
the texts and checks the file objects a move needs before `go_to` changes
anything (the texts it read are those `go_to` then uses, so this costs no
second read; checking a file object hashes it once more before it is
copied back), and `papers history` checks the size of the objects of the
states it lists (one `stat` each: 14 ms for 20 states of the 10 000-entry
library). An implementation that wants durability
can `fsync` each object and the folder before writing the state; the cost
is one `fsync` per new piece, usually one or two per command.

### 4.5 Undo, redo, restore

`backup.go_to` walks from the current state to the target (the path
through the common ancestor, `Project.path`), and for each step with file
operations calls `journal.restore` with the file links of the two states.
The links are found by parsing the full bibtex of each state, through the
parse cache and the same middleware as a library load (`lowercase_fields`
included). One parser (`backup.parser`) serves the whole command: the
files linked before and after (`_time_travel`), the states of the path
and the bibtex on disk; it keeps each parsed text, so a text is parsed
once even when two states, or a state and the file on disk, have it (the
common case: the bibtex on disk is the current state). An undo of one
step parses two texts. For 10 000 entries, `papers undo` of a `file
attach` took 2.9 s and now takes 1.1 s, measured on the same machine (it
parsed the library six times, three of them without the cache).

`journal.restore` computes checksums lazily (a `digest` memo per call)
and only of the files it considers: those linked now or in the target,
and those named by the operations. It never checksums the whole files
directory.

Ideas: compare the pieces of the two states and parse only the pieces
that differ (the links of the other entries are the same); memoize the
links per state.

An inconsistency found here, fixed: `go_to` parsed the states with
bibtexparser directly, without `lowercase_fields`, so a state recorded
from a file edited outside papers with `File = {...}` (capitalized, as
older JabRef writes) had no links for undo. `revert._state_entries` still
parses the states with bibtexparser directly.

## 5. The duplicate search

`papers/duplicate.py`, bibtex.md 9. `tests/duplicate_reference.py` is
the version before the speed-ups described here, kept for an equivalence
test.

### 5.1 Identity memo

`identifiers_of(e)` returns a `NamedTuple` of the normalized identifiers
(type, DOI, arXiv id, ISBN set, authors, title, authors|title). It is
memoized (`functools.lru_cache`, 2^18 entries) by the tuple of the raw
values of the 8 fields it depends on, so an edited entry gets new
identifiers and an unchanged one is not normalized again. `normalize_text`
has its own memo of the same size, and skips the LaTeX decoder for ASCII
text without `\`, `{`, `}`.

| | 1 000 | 10 000 | 50 000 |
|---|---|---|---|
| `identifiers_of` all entries, cold memo | 28 | 260 | 1 376 |
| same, warm memo | 2.6 | 29 | 166 |

The memo is per process: in the command line it serves the many
`same_paper` calls of one command. A long-running process (the desktop
application) would keep it across commands.

### 5.2 Index

`IdentityIndex` maps `(kind, value)` to the entries that have it: `doi`,
`arxiv`, each `isbn`, and `authortitle` (or `title` for entries without
authors). The candidates of an entry are the entries that share one of
its keys. This is complete for the rule: every verdict other than
`different` needs an equal DOI, arXiv id, ISBN or author-title, which is a
shared key. The index keeps each entry's insertion position, so results
can be ordered by library order without an `O(n)` position map per
lookup (the reference version built one at each call, which made `add`
of many entries quadratic).

When an entry is merged, the caller removes it from the index, changes
it, and adds it again (`bib._insert_entry_check`, `pools.Pool.update_entry`);
`remove` computes the keys from the current values, so changing an
indexed entry without this sequence would leave it under its old keys.

`duplicate_groups` joins the candidate pairs with a union-find, then
splits each connected set greedily (bibtex.md 9.5), which is quadratic in
the size of a set (sets are small, except many entries sharing one DOI).

| | 1 000 | 10 000 | 50 000 |
|---|---|---|---|
| `duplicate_groups`, cold memo | 44 | 401 | 2 200 |
| `duplicate_groups`, warm memo | 16 | 176 | 955 |
| reference version (`tests/duplicate_reference.py`) | 177 | 1 648 | |
| 100 `find_duplicates` with an index | 1.1 | 0.8 | 0.8 |
| same, reference version | 9.4 | 76 | |
| all pairs with `same_paper`, warm memo | 3 600 | (~360 s) | |

`Distinct.contains` (the pairs of `distinct.json`) compares the identity
of both entries with every recorded pair, at each `same_paper` call. It is
linear in the number of pairs; with many pairs, an index of the recorded
sides by DOI, arXiv id, ISBN and author-title would make it constant.
`distinct_union` returns the same union object while its parts do not
change, so the union of a library and its pool is not rebuilt per call.

`fuzzy_pairs` (`list --duplicates --fuzzy`) compares all pairs with
rapidfuzz and is quadratic; it is for listing only.

## 6. The LaTeX decoder and the text normalization

`papers/latex.py` decodes LaTeX to Unicode character by character, as
bibtex.md 4.1 says: accent commands, named characters (a table built once
from `papers/latexenc.py`), formatting commands dropped, then NFC.

The loop tested each character against the special cases, including four
`str.startswith` calls per character in text mode (`---`, `--`, ` `` `,
`''`). On a pull of 10 000 entries, 15 million `startswith` calls came from
this loop, about 1.3 s under the profiler, mostly from the merge comparing
abstracts (`merge.equivalent` normalized both values; it now compares plain equality first). Decoding author and
title of 10 000 entries took 288 ms.

Fixed: the loop now copies each run of characters that are not special
(text mode: not `\ { } $ ~ - ` '`; paths: not `\ { }`) in one step (a
regular expression), and the special characters go through the cases as
before. The ASCII transliteration (`papers/ascii.py`) looks up the table
only for the runs of non-ASCII characters (the table maps one character at
a time, so the result is the same), and `normalize_text` returns a plain
ASCII text (none of `\ { } $ ~`, no `--`, ``` `` ```, `''`) lower-cased and spaced without the other
steps, as bibtex.md 9.1 allows. `papers list WORDS` normalizes the whole
text of each entry (formats.md 6.1); on 358 generated entries it took
151 ms CPU (`papers list` alone: 104 ms), now 111 ms (`papers list`: 90 ms);
on 3 000 entries 553 ms, now 279 ms (`papers list`: 196 ms). The fields are
not normalized one by one: the normalization of the joined text is not
always the join of the normalized fields (the shortcut for a plain ASCII
text applies to the whole text, and a command at the end of a field can
take the start of the next one as its argument).

`FieldMerge` calls `equivalent` on every present value. It used to
normalize values also when they were equal as strings, so equal
abstracts went through the decoder and filled the `normalize_text` memo
(up to 2^18 values, rarely hit, since abstracts are unique). Fixed:
`equivalent` compares the values as strings first, and only values that
differ are normalized.

Ideas: copy runs of characters that are not `\ { } $ ~ - ` '` in one step
(a regex or `memchr`-style search for the next special character);
memoize only short values (names, titles).

Contract note: the character table and the ASCII transliteration table
(AnyAscii, `papers/ascii.py` in Python) decide the same-paper rule and
file names. Both are published in `design/data/`; another implementation
can load them as data, or use AnyAscii, which exists in many languages.

## 7. File checksums

`papers/checksums.py`, history.md 10. `.papers/files.json` is the only
persistent store of checksums; there is no cache keyed by size and
modification time. At a save, the checksums of the paths no longer linked
are dropped, and checksums are computed only for the files the command
moved or copied and the links new since load (streamed sha256), and for
the PDFs `papers file fetch` attached or replaced (their version is kept by
checksum, `Biblio.pdf_versions` until the save). A command that touches few
files reads few files. `papers file checksum` reads all
linked files.

Within a command, `journal.restore` memoizes the digests it computes;
`bib._same_content` and `pools.Pool.find_file` compare sizes first and
compute checksums only for files of the same size, but do not memoize them
across calls.

Idea: a machine-local cache of `(device, inode, size, mtime_ns) ->
sha256` would let `papers file check` and undo skip reading files that did
not change; it would be free (not shared between implementations).

### 7.1 The other libraries

`papers/otherlibs.py`, library.md "The file of a broken link", step 4.
At the first lookup of a command (a broken link with a checksum in the
library's `files.json`), the `files.json` kept in the head state of each
other place (history.md 3.3) is read and reversed in memory (checksum ->
paths); no bibtex is parsed, and nothing is kept between commands. With
nothing to repair, nothing is read.

Measured with `file fix --dry-run` in a library of 2 000 entries with 100
broken links (50 whose content is in another library), and 5 other
libraries of N entries, one in ten with a file: 0.20 s for N = 10 000
(median of 10 runs; reading the five `files.json`, 5 000 files, takes
about 0.01 s of it), against 0.18 s with an index of these files in the
cache, removed to keep the code simple. The same command
without any other library takes 0.15 s; a search that parsed the bibtex
of each other library took 4.7 s.

## 8. Pools and exchanges

`papers/pools.py`, `papers/merge.py`, exchange.md.

### 8.1 Origin records

`Origin` reads every `.bib` file of `.papers/origin/` (one per pool id)
into `{pool id: {lower-case library key: record entry}}`. A record is the
pool entry as last exchanged, without `file` and `ids`, with
`papers-pool-key` and `papers-time`. For a library fully exchanged with
its pool, the origin file is about the size of the bibtex (7.5 MB for the
10 000-entry library).

Origin files were parsed without the parse cache, and a pull of a
shallow library loaded them twice (to repair the links to the pool files
when the library is loaded, then for the exchange): about 2.6 s for the
10 000-entry library under the profiler. Fixed: they are parsed through
the parse cache (3), and `Origin` keeps each parsed file with its text,
so a later load in the same process that reads the same text reuses it.
The loads then share the entry objects, so `Origin` never changes a
record in place (`set_files` and `rekey` replace it by a copy). The
origin files take room in the parse cache, about as much as the
bibtex.

### 8.2 Matching and the three-way merge

`Exchange.pool_entry` finds the pool entry of a library entry: the record
(dictionary lookup by key, then by former keys), the pool entry of the
record's pool key (a dictionary of the pool built once), checked with
`same_paper`; else `Pool.find` through an `IdentityIndex` of the pool.
`library_entry` does the reverse with a map from pool key to library keys
and an index of the library. Each lookup is constant time on average.

The three-way merge (`merge.Merge` with `base`) is per entry and per
field: `FieldMerge` compares target, other and base, with the
equivalence rules (case, braces, names). Its cost is linear in the number
of fields; the expensive part is the normalization of long values (6).

### 8.3 `papers status`: the fast path by pieces

exchange.md 14.4. `status` keeps the sorted piece checksums of the
library, the pool and the origin file when they were last in sync
(`exchanges.json`). If no piece changed on any side, the state is `in
sync` without parsing the entries; else only the entries whose keys occur
in the new pieces (found with a regex on the piece text) are compared.
This uses the same cut as the history and costs one sha256 pass over the
three texts. In the Python implementation the origin records are loaded
(and parsed in full) before this check, so the fast path still pays for
that parse, now through the parse cache (8.1): `status` with the
10 000-entry pool in sync went from 1.45 s to 1.1 s, of which about half
is that parse and half the parse of the library for the bibtex line of
`status`. Reading only the comments of the origin file (the pool id and
the pull time) before the check would remove the first half.

### 8.4 Costs measured

`papers pull --all` into an empty shallow library (wall time of the
command), before and after the fixes of 8.5 (measured one after the
other on the same machine, so the "before" numbers differ a little from
the first measurement: 0.65, 2.4 and 13.8 s for the first pull):

| Pool entries | first pull (all new) | second pull (nothing changes) |
|---|---|---|
| 1 000 | 0.86 s → 0.42 s | 0.83 s → 0.53 s |
| 3 000 | 2.85 s → 0.98 s | 2.8 s → 1.42 s |
| 10 000 | 17.0 s → 3.5 s | 8.8 s → 4.8 s |

`papers status` with the 10 000-entry pool in sync: 1.45 s → 1.1 s.

Both pulls are now about linear. What remains of the second pull is per
entry: finding the pool entry of each library entry (`pool_entry`, with
`same_paper`), the three-way merge, the index of the library for
`missing` (`--all`), and the parse of the library, the pool and the
origin file.

### 8.5 Quadratic steps found while measuring

All fixed; none of them changed a result. They mattered from a few
thousand entries.

- `Exchange._pull_new` built the set of all library keys for each new
  entry: 50 million calls for 10 000 new entries. Fixed: `Exchange.pull`
  builds the set once and each new key is added to it.
- `cli/pool_cmds._pull_selection` checked `not any(pe is x for x in new)`
  for each missing entry: quadratic in the number of new entries. Fixed:
  a set of the `id` of the entries found.
- `Config.shallow` (through `has_pool`, `is_pool_library`, `pool_path`,
  `configdir`) resolved paths with `realpath` at each call, and the
  exchange calls it several times per entry (30 000 calls, about 6 s
  under the profiler for 10 000 entries). Fixed: the three values are
  kept with what they were computed from (the configuration file, the
  pool setting, and the current directory for a relative file) and
  computed again when one of these changes (`papers config pool`,
  `init`) or after a save.
- The origin records were parsed twice per pull, without the parse
  cache (8.1). Fixed.
- Equal values were normalized by the merge (6). Fixed.

## 9. The lock and concurrency

`papers/lock.py`, library.md "The lock", history.md 13.

The lock is a lease: `.papers/lock` created with `O_CREAT | O_EXCL`,
holding `{token, pid, host, command}`. A daemon thread touches it
(`os.utime`) every 2 s while the command runs. A waiting command polls
every 0.1 s, for up to 30 s; it takes the lock over when the file's
signature `(mtime_ns, size, inode)` has not changed for 10 s on its own
clock, or when the file names a process of this host that no longer
exists. A take-over renames the file to a unique name (one atomic step,
so two waiters cannot both win), checks that the renamed file is the one
found stale, and puts a fresh lock back (a hard link, or a copy with the
same token where hard links are not supported). Before writing, the holder
checks that the file still has its token (`lock.check`).

Why a lease and not `flock`/`fcntl`: the lock must work between two
implementations and across a network file system, and a lock file with a
token can be checked by any program. It does not work across computers
that see the folder through a sync service, which delivers the file late.

Notes for another implementation:

- The refresh needs a timer independent of the main work (a thread, or a
  timer in an event loop). A holder blocked for more than 10 s (a laptop
  that sleeps) loses the lock; `check` before each write detects it.
- `release_all` read the token and then removed the file: if the lock
  was taken over between the two steps, it removed the other command's
  lock. Fixed: it renames the file aside (as a take-over does), checks
  the token of the renamed file, and removes it only if it is its own;
  otherwise it puts it back (library.md, The lock, Release).
- In a long-running process that runs several commands, `release_all`
  stops the refresh thread; a lock taken again immediately after could
  find the old thread still alive (it exits a moment later) and not start
  a new one (`_start_refresh` only checked `is_alive`). Fixed: each thread
  has its own stop signal, and a thread told to stop is replaced by a new
  one.

Within one process, the Python implementation is single-threaded apart
from the lock refresh and the network requests of `add DIR` (a thread
pool for crossref, with a `requests` session per thread; PyMuPDF is
called from the main thread only). Two commands on the same library are
serialized by the lock. Two places of one project (a library and its
copy, which have different locks) can write the project's `heads.json` at
the same time (history.md 13, "Not protected").

## 10. Startup

The command line imports what every command needs and imports the heavy
dependencies when first used: `requests`, `rapidfuzz`, `scholarly`,
`bs4`, PyMuPDF. `papers --version` took 88 ms (Python itself: 21 ms;
importing `papers.cli`: 44 ms). On a library of one entry, `papers list`
took 80–100 ms; on 10 000 entries 430 ms (warm parse cache), `add` of
one entry about 0.9 s, `undo` 1.7 s (about 1.1 s since the change of 4.5).

Fixed in part: the standard modules that only some commands use are now
imported in the functions that use them: `urllib.parse` (with
`ipaddress`), `subprocess`, `platform`, `socket`, `uuid`, `hashlib`,
`difflib`, `concurrent.futures`, `mimetypes`, `html.entities` (and the
regular expression of the HTML references, built on first use), AnyAscii
and `papers/latexenc.py`. CPU time (best of 40, a library of 358
generated entries, Python 3.14): `papers --version` 86 ms, now 69 ms;
`papers list` 104 ms, now 90 ms; `papers status` 106 ms, now 87 ms.

What is left: `logging` (18 ms, most of it `traceback`, which imports
`_colorize`, `dataclasses` and `inspect` in Python 3.14), bibtexparser and
pylatexenc (7 ms, needed by every command that reads the library, also
imported by `--version` through the configuration), `platformdirs` (5 ms
with `typing`), `shutil` (3.5 ms with the compression modules), and the
argument parser: `get_parser` builds the parsers of all commands (about
300 arguments) at each start, 10 ms, of which about 4 ms are calls of
`gettext.find` by argparse (one per translated text, none cached when no
translation exists). Building only the parser of the command given would
remove most of it.

For an implementation in a compiled language, startup is negligible, and
the cost of a command is the parse, the format and the history; for the
desktop application, which keeps the library in memory, it is the cost of
detecting a change on disk (the size and modification time check of 2.2,
then the pieces of 3 to re-read only what changed).

## 11. Summary of the costs of one command

For a library of 10 000 entries in the Python implementation, a command
that changes one entry spends about:

| Step | ms |
|---|---|
| startup | 70–90 |
| read and parse (warm cache) | 370 |
| sort and format | 150 |
| compare with the file, write | 10–20 |
| history: read the text again, cut, store pieces, state, head | about 100 |
| read the states of the project | 25 per 500 states |
| pruning, one command in 50 (4.3) | 80 per 500 states |

The parse and the format are linear in the size of the library and done
in full at every command. Reusing the text of unchanged entries (2.2),
caching parsed values rather than split blocks (3), and parsing only the
pieces that differ (3, 4.5) are the main ways to make a command
proportional to what it changes.
