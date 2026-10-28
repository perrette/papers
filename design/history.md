# The history: undo, redo, restore, revert

This file specifies the history of the libraries: the store on disk, the
states it holds, how a command records them, how undo, redo, restore and
`papers history --revert` use them, the retention, `.papers/files.json`
and the parse cache.

Other files of this specification:

- the library on disk, its configuration, the settings, the lock:
  `library.md`;
- the bibtex, the `file` field, entry identity and merge: `bibtex.md`;
- the origin records `.papers/origin/`, pull, push, sync, the dialogue on
  conflicts: `exchange.md`;
- the export formats: `formats.md`.

Two kinds of rules appear below:

- **Contract**: file names, JSON keys, value formats and the rules that
  decide what is stored and what a stored value means. Two implementations
  that share one store must agree on them: each must read what the other
  wrote, and undo what the other did.
- **Free**: messages, the order of internal steps that leaves the same
  result on disk, prompts, thresholds marked as such. Another
  implementation may differ.

When a section does not say, the rule is part of the contract.

Terms used below:

- **real path**: absolute path with symbolic links resolved;
- **normalized path**: absolute path with `.` and `..` removed and
  repeated separators merged, symbolic links not resolved;
- **sha256**: the SHA-256 digest written as 64 lowercase hexadecimal
  characters;
- **library directory** and **directory of the bibtex**: see `library.md`.
  In the usual layout they are the same folder.

## 1. What the history is

The history keeps the states of each library on the machine, so that a
command can be undone with its files. It is not synced or shared with the
library: a library copied to another computer starts with an empty history
there. papers does not use git.

One **store** holds the histories of all libraries of the user (unless a
library asks for a store of its own, see 2.6). In a store:

- a **project** is the history of one library, named by the library's
  `id` (see `library.md`, "The `id` field");
- a **place** is where a copy of that library is: the real path of its
  bibtex. Copies of a library folder share the `id`, so they are places
  of one project; their states branch from the copy on;
- a **state** (a "step" in the messages) is one snapshot: the bibtex, some
  files of `.papers/`, and the file operations of the command that made
  it. States form a tree (each names its parent);
- a **head** is the current state of a place, with its redo list.

## 2. The store on disk

### 2.1 Location

The root of the store is the `history-dir` setting, when set, else
`<data dir>/history`:

| Platform | `<data dir>` |
|---|---|
| Linux and other Unix | `$XDG_DATA_HOME/papers`, or `~/.local/share/papers` when `XDG_DATA_HOME` is not set |
| macOS | `~/Library/Application Support/papers` |
| Windows | `%LOCALAPPDATA%\papers\papers` |

Rules:

- `history-dir` is read from the machine configuration only; a library
  cannot set it (see `library.md`, settings table). A leading `~` is
  expanded. A relative value is resolved against the current directory
  (see `library.md`, open question 14).
- The folders are created when first written. Nothing is created by a
  command that changes nothing.

An implementation must find the same folder on the same computer
(contract).

### 2.2 Layout

```
<root>/
  objects/
    ab/ab12…ef                  a piece of text, zlib-compressed, named by the sha256 of its uncompressed bytes
  file-objects/
    ab/ab12…ef.pdf              a file deleted by a command, named by its sha256 and its extension
  projects/
    <id>/
      heads.json                the heads of the places of the project
      exchanges.json            not part of the history: the pieces of `papers status` (see exchange.md 14.4)
      states/
        000001.json             one state per file
        000002.json
  separate/
    <id>/                       a store of its own for the library <id> (history-separate), same layout
```

`<id>` matches `[0-9A-Za-z_-]+` (an implementation refuses other values).
The folder of an object is the first two characters of its name.

### 2.3 Objects: pieces of text

The bibtex and each kept `.papers/` file (see 3.3) are stored as a list of
pieces. The text is the concatenation of its pieces, byte for byte.

**Cutting a text into pieces** (contract: two implementations must cut
the same text the same way, or they store the same bibtex twice and the
parse cache and the size accounting differ; a reader only concatenates, so
reading does not depend on it):

1. Encode the text as UTF-8.
2. Cut it into **segments** before each line that starts with `@`: a cut
   is made at offset 0 and after each `\n` that is followed by `@`. Only
   `\n` ends a line (`\r\n` works because the `\n` is last; a lone `\r`
   does not end a line). Empty segments are dropped. So the first segment
   is the text before the first `@` line (comments), when there is any;
   each other segment starts with `@` and runs to the next line that
   starts with `@`.
3. Group consecutive segments into pieces. A piece ends after a segment
   when either:
   - the piece now has `PIECE_MAX` = 256 segments, or
   - `crc32(segment bytes) mod PIECE_ENTRIES == 0`, with `PIECE_ENTRIES`
     = 32 and crc32 the CRC-32 of zlib and PNG (IEEE 802.3 polynomial,
     unsigned 32-bit result).

   The last piece holds the remaining segments.
4. The empty text has no pieces (`"pieces": []`).

The test depends only on the segment itself, so adding or removing one
entry changes the piece it is in (and at most merges or splits it with its
neighbour); the other pieces are those of the earlier states.

Example: the text `% comment\n` followed by 40 entries of the form
`@article{kN,\n title = {T},\n}\n\n` for N = 0..39 has 41 segments. The
segment of `k30` has crc32 977124256, a multiple of 32: the first piece
holds the comment and `k0`…`k30` (32 segments), the second `k31`…`k39`.

**An object file**:

- name: the sha256 of the uncompressed UTF-8 bytes of the piece, no
  extension;
- content: the bytes compressed in the zlib format (RFC 1950). The
  compression level is free; a reader accepts any zlib stream;
- written to a temporary file in the same folder, then renamed over the
  final name (a reader never sees half an object). The temporary name ends
  with `.tmp` (Python uses `<name>.<pid>.tmp`). Files ending with `.tmp`
  are not objects;
- when the object exists already, it is not written again, but its
  modification time is set to now. The retention keeps objects younger
  than one hour (2.8, section 9); refreshing the time protects an object
  that a state about to be written refers to. Contract.

A text is UTF-8. A missing or unreadable piece makes the state unusable:
undo, redo and restore stop with `the history of the library is damaged:
piece <sha256> is missing from the history`.

### 2.4 File objects: deleted files

A file that a command deletes is moved into the store (see 5.6), so that
undo can bring it back.

- Path: `file-objects/<first two hex>/<sha256><extension>`, where
  `<extension>` is the extension of the deleted file's name including its
  dot, as written (`.pdf`, `.PDF`), or nothing.
- Lookup by checksum: any file in `file-objects/<first two hex>/` whose
  name, up to its first `.`, is the sha256. An implementation must not
  leave other files in these folders whose name starts with
  `<sha256>.` (a temporary file must not use that pattern).
- Storing a file whose checksum is already stored: the new file is
  deleted, and the stored one gets its modification time set to now.
- Storing a new file: it is moved (renamed, or copied then deleted across
  file systems) to its path, and its modification time is set to now.
- File objects are shared by all projects of the store: a file deleted by
  two libraries is stored once. Undo finds a file by checksum in the whole
  store, not only among the files of its project.

### 2.5 States and their numbers

A state is a JSON file `projects/<id>/states/NNNNNN.json`, where `NNNNNN`
is the state number written with at least six digits, zero-padded
(`000042.json`; `1234567.json` after 999999). A reader takes every file
whose name is digits followed by `.json` and whose content is a JSON
object; other files are ignored.

Allocating a number (contract):

1. `n` = the largest number present in `states/` + 1 (1 for an empty
   project).
2. Create `states/<n>.json` exclusively (fail if it exists). If it exists,
   `n` = `n` + 1 and try again.
3. Write the JSON into the created file.

The exclusive create lets two commands (and two implementations) add
states to one project at once without losing one. A state is written once
and not changed afterwards, with two exceptions that rewrite the file
through a temporary file and a rename: the file operations done after the
save (5.5) and `--drop-files` (9.4). The writer uses one-space
indentation; the layout is free.

### 2.6 Separate stores

With the `history-separate` setting true, the library's project is in the
store `<root>/separate/<id>/` (same layout: `objects/`, `file-objects/`,
`projects/<id>/`). Its pieces and files are not shared with other
libraries, and its retention is counted alone.

- `history-separate` may be set by a library or by the machine
  configuration (the library's value wins). `history-dir` and
  `keep-deleted-files` are machine-only.
- A bibtex without library uses the shared store even with the setting.
- Changing the setting does not move a history: after the change the
  library finds no history in the other store and starts a new one there.
- `papers history --all` and `papers history --remove ID` look in the
  shared store and in each folder of `<root>/separate/`.

### 2.7 `heads.json`

```json
{
 "/home/u/papers/papers.bib": {
  "state": 12,
  "redo": [13, 14],
  "time": 1793189499.4354224
 },
 "/home/u/copy-of-papers/papers.bib": {
  "state": 9,
  "redo": [],
  "time": 1793189520.750887
 }
}
```

| Key | Type | Meaning |
|---|---|---|
| place (object key) | string | real path of the bibtex of the place |
| `state` | integer | the current state of the place |
| `redo` | list of integers | the states that `redo` goes to, the next one first |
| `time` | number | Unix time (seconds, fractional) of the last change of this head |

Rules:

- A head whose `state` no longer exists is treated as absent. Numbers in
  `redo` that no longer exist are skipped when read.
- The file is rewritten whole (temporary file and rename) each time a
  head changes: read, modify, write.
- A missing or unreadable file means no heads.

### 2.8 Writing order

Contract, so that a concurrent retention (section 9) never removes what a
state refers to:

1. write (or refresh) the objects and file objects of the state;
2. write the state;
3. write the head.

## 3. A state

### 3.1 Keys

| Key | Type | Present | Meaning |
|---|---|---|---|
| `parent` | integer or `null` | always | the state before; `null` for the first state of a project |
| `time` | number | always | Unix time (seconds, fractional) when the state was made |
| `kind` | string | always | `command`, `outside` or `start` (3.2) |
| `message` | string | always | the command line, or a description (3.2) |
| `ops` | list of objects | always | the file operations of the command (section 4) |
| `deleted` | list of strings | always | the sha256 of the file objects the state keeps (3.4) |
| `bibtex` | object | always | `{"pieces": [sha256…], "sha": sha256}` |
| `files` | object | always | `{name: [sha256…]}`: the kept `.papers/` files (3.3) |
| `pools` | object | when the command wrote a pool | `{pool project id: {"state": n, "config": path}}` (section 7) |
| `from` | string | in a pool's state made by a command of another library | real path of the directory of the bibtex of the library of that command |
| `reverts` | list of integers | in a state made by `--revert`, or by an undo/redo that reverted a pool step | the states it takes back (sections 7, 8) |

`bibtex.sha` is the sha256 of the whole bibtex text as UTF-8; the pieces
are those of 2.3. A bibtex that does not exist is stored as the empty
text.

The keys a reader must use: `parent`, `time`, `bibtex`, `files`, `ops`,
`deleted`, `pools`, `reverts`. `message` and `from` are shown to the user.
`kind` is written but never read by papers; a reader must accept a state
without it. A reader ignores unknown keys; an implementation that rewrites
a state (5.5, 9.4) keeps them.

### 3.2 Kinds and messages

| `kind` | When | `message` |
|---|---|---|
| `start` | the first state of a project: the library before its first recorded command | `the library before its first recorded command` |
| `outside` | the bibtex on disk is not the head's (changed by an editor, another program, a sync) | `changed outside papers` |
| `command` | a command changed the library | `papers ` followed by the arguments of the command line, joined by spaces (`papers add paper.pdf --move`) |

A pool step reverted by undo or redo has the message of the command
followed by `: revert of step N` or `: revert of steps N, M`
(`papers undo: revert of step 3`). The text of `message` is free; it is
for display.

### 3.3 The kept `.papers/` files

`files` maps a name, relative to the **directory of the bibtex**, to the
pieces of the file's text. The names kept are those of the following that
exist as files when the state is made:

- `.papers/distinct.json`
- `.papers/files.json`
- `.papers/origin.bib` (legacy origin file)
- `.papers/origin/<name>.bib`, each file of `.papers/origin/` ending in
  `.bib`

Not kept: `.papers/config.json`, `.papers/lock`, `.papers/.gitignore`,
anything else.

The names are written with the separator of the operating system
(`.papers/files.json` on Linux and macOS, `.papers\files.json` on
Windows). `files.json` belongs to the library directory but is looked up
here relative to the directory of the bibtex: when the two differ it is
not kept (see `library.md`, open question 1).

### 3.4 `deleted`

The sorted list, without repeats, of the checksums of the `trashed`
operations of `ops` (section 4). A file object is kept by the retention as
long as a state lists it in `deleted`. `--drop-files` removes checksums
from `deleted` and leaves `ops` unchanged (9.4).

### 3.5 Examples

A first state, before the bibtex existed:

```json
{
 "parent": null,
 "time": 1793189487.9236956,
 "kind": "start",
 "message": "the library before its first recorded command",
 "ops": [],
 "deleted": [],
 "bibtex": {
  "pieces": [],
  "sha": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
 },
 "files": {}
}
```

A command that moved a file into the library (relative paths):

```json
{
 "parent": 2,
 "time": 1793189488.0984843,
 "kind": "command",
 "message": "papers file attach a2000 dl/x.pdf",
 "ops": [
  {
   "op": "moved",
   "src": "dl/x.pdf",
   "dst": "files/doe_2000_a.pdf",
   "checksum": "2493a40c8dae940590f8b323c46051a641bebd740aa5d1997108043a9b301274"
  }
 ],
 "deleted": [],
 "bibtex": {
  "pieces": ["3cfdd27fe67f88d0d4dd5cfc05f618ca08451d74c7c8dc8615f430667b274de8"],
  "sha": "3cfdd27fe67f88d0d4dd5cfc05f618ca08451d74c7c8dc8615f430667b274de8"
 },
 "files": {
  ".papers/files.json": ["ee03e3bbacb71967291487b2cbce71242c12a0b6fe6defb49b7f3b588927d0e9"]
 }
}
```

A command that deleted a file, kept in the store (the `bibtex` digests
shortened here):

```json
{
 "parent": 7,
 "time": 1793189508.0299218,
 "kind": "command",
 "message": "papers rm a2000 --delete-files",
 "ops": [
  {"op": "trashed", "src": "files/doe_2000_a.pdf", "dst": null,
   "checksum": "2493a40c8dae940590f8b323c46051a641bebd740aa5d1997108043a9b301274"}
 ],
 "deleted": ["2493a40c8dae940590f8b323c46051a641bebd740aa5d1997108043a9b301274"],
 "bibtex": {"pieces": ["69e62f28…"], "sha": "69e62f28…"},
 "files": {}
}
```

A step of a shallow library whose command also wrote its pool (only the
keys of interest shown; `time`, `deleted`, `bibtex`, `files` as above):

```json
{
 "parent": 2,
 "kind": "command",
 "message": "papers file attach a2000 /home/u/dl/x.pdf --move",
 "ops": [
  {"op": "moved", "src": "/home/u/dl/x.pdf", "dst": "/home/u/pool/files/doe_2000_a.pdf",
   "checksum": "c0d475902344dc07282e196c6a17d49906f2700de4281fbda2cd8b7e34b65569"}
 ],
 "pools": {
  "cdfdf43306914db9a871d85cd252ae71": {"state": 3, "config": "/home/u/pool/.papers/config.json"}
 }
}
```

The pool's step made by that command:

```json
{
 "parent": 2,
 "kind": "command",
 "message": "papers file attach a2000 /home/u/dl/x.pdf --move",
 "ops": [],
 "from": "/home/u/lib"
}
```

The revert of that pool step by a later undo in the library, after the
pool moved on to step 4:

```json
{
 "parent": 4,
 "kind": "command",
 "message": "papers undo: revert of step 3",
 "ops": [],
 "reverts": [3],
 "from": "/home/u/lib"
}
```

## 4. File operations

`ops` lists the file operations of the command, oldest first. Each is an
object:

| Key | Type | Meaning |
|---|---|---|
| `op` | string | `moved`, `copied`, `trashed` or `removed` |
| `src` | string | the path before |
| `dst` | string or `null` | the path after (`moved`, `copied`); for `removed`, the identical file that stays, or `null`; `null` for `trashed` |
| `checksum` | string or `null` | sha256 of the file; `null` for a folder |

| `op` | Meaning |
|---|---|
| `moved` | a file or folder renamed or moved from `src` to `dst`. Checksum taken at `dst` after the move. |
| `copied` | a file copied (or hard-linked) from `src` to `dst`. Checksum taken at `dst`. |
| `trashed` | a file deleted by the command and kept in the store (`file-objects/`, by its checksum). |
| `removed` | a file deleted and not kept: sent to the system trash, or deleted. With a `dst`: the file at `dst` has the same content and stays (undo copies it back from there). Checksum taken before the deletion. |

What is recorded (contract for the meaning; which commands produce which
operation is part of each command's behaviour):

- the files placed by `add`, `file attach`, `file rename`, `file mv` and
  the exchanges with a pool (moved or copied, as the command did it). A
  file downloaded by papers into a temporary folder is not recorded;
- the files deleted by `rm --delete-files`, `file rm`, `file clean`, or
  replaced by a forced move (`trashed`, or `removed` when not kept);
- a file of a library deleted because its pool has the same content
  (`removed` with `dst`: the pool's copy).

Not recorded: the operations of undo, redo and restore (they move in the
history and are not a step of it); downloads; the writes of the bibtex
and of the `.papers/` files (they are in the state itself).

**Paths** (contract). The operations are recorded with absolute
normalized paths, then written into the state (unlike the file links of
the bibtex, a path outside the directory of the bibtex is never written
with `..`):

- if the library has relative paths (the `paths` setting is `relative`),
  a path inside the directory of the bibtex is written relative to it
  (`files/a.pdf`). "Inside" is decided on the text of the normalized path:
  the relative path is not `..` and does not start with `..` followed by
  a separator;
- any other path is written absolute (`/home/u/Downloads/x.pdf`);
- with `paths absolute`, all paths are absolute.

A reader resolves a relative path against the directory of the bibtex of
the library whose state it reads, and normalizes the result. So undo in a
copy of a library acts on the copy's own files (relative) and on the same
outside files (absolute). The separator is that of the operating system.

## 5. Recording

### 5.1 The place and the project of a library

- Place: the real path of the bibtex.
- Project id:
  - a library (a library configuration file): its `id`; created and
    written into the configuration when a state is first recorded (see
    `library.md`). Nothing is created with `--dry-run`, or by a command
    that changes nothing;
  - a bibtex without library: the first 32 characters of the sha256 of
    the UTF-8 bytes of the place. Moving such a bibtex loses its history.
- `papers export DIR` gives the new library a new id: it has a history of
  its own.

### 5.2 The head of a place, and changes made outside papers

Before a command writes the library (at its save, see 5.4), and at the
start of undo, redo, restore and `--revert`, the head of the place is
brought up to date (contract):

1. Read the bibtex on disk (missing: the empty text) and compute its
   `sha`.
2. If the place has no head (a new place: the library was moved, copied,
   or never recorded):
   1. remove from `heads.json` the places whose bibtex no longer exists;
   2. if the project has states, choose the **start state**: among the
      states whose `bibtex.sha` equals the sha on disk, the one with the
      largest `time` (then the largest number); if none matches, the
      state with the largest `time` (then number) of the project. Set the
      head of the place to it, with an empty redo list.

   A moved library thus continues its history; a copy branches from the
   state it was copied at.
3. If the head's `bibtex.sha` equals the sha on disk: done, the head is
   the current state.
4. Otherwise, if there is a head, add a state, child of the head, with:
   - `kind` `outside`, `message` `changed outside papers`, `ops` and
     `deleted` empty;
   - `bibtex`: the text on disk;
   - `files`: **those of the head**, copied from it; the `.papers/` files
     on disk are not read.

   The head moves to it, with an empty redo list. papers prints, at info
   level: `<bibtex name> changed outside papers since its last state:
   recorded`.
5. If the project has no state at all (step 2 found none), add the first
   state instead: `kind` `start`, `parent` `null`, and as content the
   library as it was when the command started (5.3), or, if that was not
   kept, the bibtex and `.papers/` files on disk now. The head moves to
   it. If the bibtex on disk now differs from the kept text (the command
   wrote the bibtex before its save), the procedure runs again from
   step 1, which adds an `outside` state on top.

Only the bibtex is compared. A change made outside papers to the kept
`.papers/` files alone is not detected; it becomes part of the next
command's state (see open questions).

### 5.3 The library before the command

When a command starts, if its library has no head yet, papers keeps in
memory the text of the bibtex and of the kept `.papers/` files, as they
are before the command. The first state (`start`) is made from them, so
that a command which writes a `.papers/` file before it saves the bibtex
still finds the library before itself in the history.

This is not done for `status`, `config`, `init`, `install`,
`uninstall`, `migrate`, `history`, `backup`, `git`, `undo`, `redo`,
`restore`, `restore-backup`, with `--dry-run`, or when the bibtex does not
exist (free: an implementation may decide differently, as long as the
first state is the library before its first recorded command).

Nothing is written at the start of a command: a command that changes
nothing leaves no trace (no state, no id, no store folder).

### 5.4 The state after a save

When a command saves a library (the bibtex, or other changes such as
origin records or `files.json`):

1. lock the library (see `library.md`, "The lock"), and check the lock;
2. bring the head up to date (5.2);
3. update `.papers/files.json` (section 10);
4. write the bibtex. If another program wrote it since papers read it
   (see `bibtex.md` 3.4), the save is refused: the file operations of the
   command so far are put back, the last first (never overwrite; a file
   whose content changed since stays; a moved file goes back if its
   source place is free; a copy is deleted if the original is still
   there; a `trashed` file comes back from the store; a `removed` file is
   reported), papers prints `the files of the command are put back:` with
   the lines, and no state is added;
5. make the new state:
   - `parent`: the head (or `null` if the place has no head);
   - `ops`: the operations of the command so far, if this library is the
     library of the command (the one of the command line); none for
     another library the command wrote (its pool). The operations are
     taken: they belong to this state only;
   - `deleted`: from `ops` (3.4);
   - `bibtex` and `files`: read from disk now;
   - `pools`: for the library of the command, the steps that the command
     added to other libraries before (section 7);
   - `from`: for another library than that of the command, the real path
     of the directory of the bibtex of the command's library;
   - `reverts`, and a different `message`: when the command marked them
     (`--revert`, the revert of a pool step).
6. **No state is added** when there is a parent, `ops` is empty, there is
   no `pools`, and `bibtex` (pieces and sha) and `files` equal those of
   the parent. The head stays.
7. Otherwise write the state and set the head of the place to it, with an
   empty redo list (a command after an undo starts a branch; the undone
   states stay in the tree, reachable with `papers restore N`).

A save of a library whose entries did not change since they were loaded,
without other changes, is skipped entirely (no lock, no state).

If recording fails after the bibtex was written, papers prints an error
and the command goes on: the save is not undone (free).

### 5.5 Operations after the save

Some operations happen after the save (for example `rm --delete-files`
deletes the files once the bibtex no longer links them). At the end of the
command, also after an error or an interrupt:

- if the library of the command recorded a state in this command: the
  operations done since join that state, if it is still the head of the
  place. The state file is rewritten (temporary file, rename) with `ops`
  extended and `deleted` recomputed. If the head moved on, the operations
  are not recorded and papers warns:
  `N file operation(s) not recorded for undo: the library changed since`;
- if the command recorded no state (for example `file clean`, which
  deletes files without changing the bibtex): the head is brought up to
  date (5.2), then a state is added with these operations and the bibtex
  and `.papers/` files on disk, as in 5.4 (never skipped by rule 6, since
  `ops` is not empty).

### 5.6 Deleted files

A file that a command deletes goes:

- to the store (`trashed`), when `keep-deleted-files` is true (the
  default) and the guard below allows it;
- to the system trash (`removed`, no `dst`), when `keep-deleted-files` is
  false, or the guard said so. Without a system trash, it is deleted;
- nowhere (`removed` with `dst`), when an identical file stays at `dst`:
  the file is deleted.

`keep-deleted-files` is read from the machine configuration only.

**The guard** (before a command deletes files of total size T bytes, T >
0, when files are kept). With `L` = `history-size` × 1048576 bytes of the
store (section 9):

1. `L` = 0 (no limit): keep them.
2. T > L: papers asks

   ```
   N files to delete, X MB: more than the history keeps (history-size: S MB).
   - This command cannot be undone: the files go to the trash of the system, not to the history.
   - The history of the libraries is dropped: no undo before this point.
   Proceed? [y/N]
   ```

   Yes: the files go to the system trash (not to the store). No: no file
   is deleted (`kept <file>` for each).
3. Otherwise compute, without changing anything, the states the retention
   would drop with T more bytes (9.2). If it drops any state younger than
   one day, or more than half of all the states of the store, papers asks
   `N files to delete, X MB: to keep them for undo, the history drops D of
   its A steps[, R of them from the last day] (history-size: S MB).` Yes:
   keep them in the store. No: no file is deleted.
4. Otherwise keep them.

`-y`/`--yes` answers yes. Without a terminal the answer is no, with the
warning `no terminal to confirm: the files are kept (-y/--yes proceeds)`.
The thresholds and texts are free; the outcomes (store, system trash, or
not deleted) are the behaviour users rely on.

### 5.7 Summary

| Situation | States added |
|---|---|
| a command that changes nothing | none |
| a command that saves an identical library, without operations | none |
| first command of a library | `start`, then the command's state |
| bibtex changed outside papers, then a command | `outside`, then the command's state |
| bibtex changed outside, then undo, redo, restore or `--revert` | `outside` (then, for `--revert`, the revert) |
| a command that writes a pool from a shallow library | a state in the pool's project (`from`), then one in the library's (`pools`) |
| undo, redo, restore | none in the library; a revert state in a pool when its step is reverted (section 7) |
| `--dry-run` | none |

## 6. Undo, redo, restore

### 6.1 The path between two states

The **line** of a state is the state, its parent, its parent's parent, …,
stopping at a state with `parent` `null` or whose parent no longer exists
(dropped by the retention).

From state A to state B:

- `back`: the states of the line of A, from A, down to (not including) the
  first one that is also on the line of B (the common ancestor); all of
  the line of A when there is none;
- `forward`: the states of the line of B, down to (not including) that
  common ancestor, in order from the oldest to B.

### 6.2 The commands

All three require a bibtex (otherwise
`no history: the library has no bibtex`), lock the library, and bring its
head up to date first (5.2). With `--dry-run` they read the head as it is
and change nothing.

**`papers undo [-n N] [--library-only]`** (N = 1 by default):

1. `line` = the line of the head. If it has N states or fewer: stop with
   `nothing to undo` (one state or none) or `only K step(s) to undo` (K =
   its length − 1).
2. target = `line[N]`; the steps undone are `line[0]` … `line[N−1]`.
3. Unless `--library-only`: find and move the pool steps (section 7),
   before the library.
4. Go to the target (6.3).
5. Head: the target; redo list: the steps undone, the nearest to the
   target first, followed by the previous redo list.

Since the head is brought up to date first, an undo right after an edit
made outside papers undoes that edit (and redo brings it back), and an
undo after an outside edit and a command goes back to the bibtex with the
edit.

**`papers redo [-n N] [--library-only]`**:

1. No head or an empty redo list: `nothing to redo`.
2. If bringing the head up to date (5.2) recorded an outside change:
   stop with ``nothing to redo: the library changed outside papers since
   the undo (recorded: `papers undo` goes back before that change)``. The
   redo list is then empty (the new state cleared it).
3. Fewer than N states in the redo list: `only K step(s) to redo`.
4. target = `redo[N−1]`; the steps redone are `redo[0]` … `redo[N−1]`.
5. Go to the target (6.3); head: the target; redo list: `redo[N]` … to
   the end.
6. Unless `--library-only`: the pool steps (section 7), after the library.

**`papers restore [N]`** (`--ref N` is the same; `restore-backup` is a
deprecated name; the bibtex need not exist):

1. Without N: target = the head (as read before step 2 of 5.2). This
   undoes a change made outside papers: it is recorded first, and redo
   brings it back. No head: `no history: nothing to restore`.
2. With N: the state N of the project, on any branch. Missing:
   ``no step N in the history of the library (see `papers history`)``.
3. If the current state (after 5.2) is the target:
   `nothing to restore: <bibtex name> is step N`.
4. Go to the target (6.3). Head: the target; redo list: `back` (6.1)
   reversed when `forward` is empty (the target is an ancestor: redo goes
   back to where the library was), else empty.
5. Pools are not touched.

Undo, redo and restore record no file operations and add no state to the
library (contract: they move the head). After undo and redo in a shallow
library with `auto-push`, a push may follow (7.6).

### 6.3 Going to a state

From the current state C to the target T (contract for the result):

1. Lock the library (held already) and check the lock.
2. Compute `back` and `forward` (6.1).
3. For each state S of `back`, in order (from C): if S has no parent, or
   its parent P no longer exists, stop going back. Otherwise, if S has
   operations, restore the files (6.4) from S to P: `current` = the links
   of S, `target` = the links of P, the operations of S, undo = true,
   checksums = `files.json` of P.
4. For each state S of `forward`, in order (oldest first): if S has
   operations and its parent P exists, restore the files from P to S:
   `current` = the links of P, `target` = the links of S, the operations
   of S, undo = false, checksums = `files.json` of S.
5. A last pass: `current` = the links of the bibtex on disk now,
   `target` = the links of T, no operations, undo = true when `forward`
   is empty, checksums = `files.json` of T. This brings back files that
   no operation explains (found by checksum or among the deleted files).
6. Write the bibtex of T (through a temporary file and a rename).
7. Write the kept `.papers/` files of T (their names resolved against the
   directory of the bibtex; a name that resolves outside that directory
   is skipped). Remove each kept file of C that T does not have, if it
   exists (`remove <path>: not in the restored state`, info level). A
   file that neither state has is left alone.

"The links of a state" are the files that its entries link to: the
`file` fields of the bibtex of the state (see `bibtex.md` 5), resolved
against the directory of the bibtex, as normalized absolute paths.

"`files.json` of a state" is the checksums in the state's
`.papers/files.json` (section 10), as `{normalized absolute path:
sha256}`; empty when the state has none.

### 6.4 Restoring the files

Inputs: `current` (set of paths linked now), `target` (set of paths linked
in the state restored), `ops` (absolute normalized paths, oldest first),
`undo` (the restored state is the earlier one), `hashes` (checksums of
the restored state), `pool_dirs` (folders whose files are copied, not
moved), `shared` (files another library links to: copied, not moved), the
store (deleted files by checksum).

Default `pool_dirs`: for a shallow library, the files directory of its
pool; otherwise none. `shared`: none, except in the undo of a library
whose pool steps were taken (7.4). Paths are compared as normalized path
strings; "inside a folder" compares real paths (the real path of the file
starts with the real path of the folder followed by a separator).

Definitions:

- `known(path)`: the expected checksum of a path: `hashes[path]` if
  present; otherwise the checksum of the first operation (in order) with
  a checksum whose `src` or `dst` is the path.
- `digest(path)`: the sha256 of the file on disk now, or none if it is not
  a file (computed once per path, and again after the file moves).
- `moves`: the operations `moved` and `copied`.
- `partners(path)`: for each operation of `moves`, the last one first:
  if its `src` is the path and it has a `dst`, yield (`dst`, operation);
  else if its `dst` is the path, yield (`src`, operation).
- `mentioned`: all `src` and `dst` of `moves`.
- `kept`: the `dst` of the `removed` operations that have one.
- `candidates`: the sorted list of (`current` ∪ `mentioned`) − `target`,
  followed by the sorted list of `target`.
- `reported`: a set of paths, initially empty.
- `<back>` below is the word ` back` when undo, empty otherwise.

**Pass 1: the files the restored state links and that are not linked
now.** For each path of `target` − `current`, sorted:

1. Let `want` = `known(path)`.
2. If something exists at the path (a file, folder or link): if `want` is
   set and `digest(path)` differs from it, then for each partner `other`
   that exists and is not in `reported`, report
   `<other>: not moved<back>, <path> exists` and add it to `reported`.
   Go to the next path. A file is never overwritten.
3. Find a source:
   1. among `partners(path)`, the first `other` that exists. If `want` is
      set, `other` is a file and `digest(other)` differs from `want`:
      report `<other>: not where the command left it (or changed since):
      left as it is`, add it to `reported`, and try the next partner.
      Otherwise the source is `other`, found through an operation; it is
      to be copied if the operation is `copied` and `other` is its `src`;
   2. if none and `want` is set: the first of `candidates`, other than
      the path, that is a file with `digest` equal to `want`; found by
      checksum, to be moved.
4. If a source was found: it is copied instead of moved when also any of:
   it is in `target`, it is in `kept`, it is inside one of `pool_dirs`,
   it is in `shared`. Create the parent folders of the path, then:
   - copied and found by checksum: copy; report
     `<path>: restored (a copy of <source>)`;
   - otherwise copy or move; report `<source> --> copied<back> to <path>`
     or `<source> --> moved<back> to <path>` (a move within one folder:
     `<source> --> renamed<back> to <file name>`).

   Go to the next path.
5. Else, if `want` is set and the store has a file object with that
   checksum: copy it to the path (the store keeps it, for the other
   states); report `<path>: restored from the history`. Go to the next
   path.
6. Else, among the operations whose `src` is the path and whose kind is
   `trashed` or `removed`: if the last one is `trashed`, report
   `<path>: no longer in the history (see the history-size setting), not
   restored`; else if there is one, or `want` is set, report
   `<path>: deleted by the command, not restored`.

**Pass 2: deleted files that no entry links** (for example `file clean`).
For each `trashed` operation, the last first when undo, the first first
otherwise, whose `src` is in neither `current` nor `target` nor
`reported`: add `src` to `reported`, then

- undo, and nothing exists at `src`: copy the file object of its checksum
  to `src` (`<src>: restored from the history`); if there is none:
  `<src>: no longer in the history (see the history-size setting), not
  restored`;
- redo, `src` is a file and `digest(src)` is the operation's checksum:
  delete it as a command deletes a file (5.6: to the store, or to the
  system trash; the guard is not asked); report
  `<src>: deleted again (kept in the history)`.

**Pass 3: the files the commands put in place that the restored state
does not link.** For each path of (`current` ∪ `mentioned`) − `target`,
sorted, that is not in `reported` and is a file:

- undo: go through `partners(path)`, the last operation first, keeping
  only those whose `dst` is the path, whose `src` does not exist, and
  whose `src` is not in `current`. For the first such operation:
  - it has a checksum and `digest(path)` differs:
    `<path>: not where the command left it (or changed since): left as it
    is`;
  - it is `moved`: move the file back to `src` (copy it if the path is
    inside one of `pool_dirs` or in `shared`); report
    `<path> --> moved back to <src>` (or `copied back to`, or within one
    folder `renamed back to <name>`);
  - it is `copied`: nothing.

  If no operation qualified: take the last `copied` operation whose `dst`
  is the path; if its `src` is a file with the same content as the path,
  delete the path (not to the store: the original stays) and report
  `<path>: removed (a copy of <src>)`.
- redo: take the last operation whose `src` is the path and whose kind is
  `trashed`, `removed` or `moved`. Skip the path if there is none, or if
  the operation has a checksum and `digest(path)` differs (the file
  changed since). Then:
  - `moved`: if its `dst` is in `target` and has the same content as the
    path (an undo copied it back from a pool that kept it): delete the
    path; report `<path> --> moved to <dst>`;
  - `trashed`: delete it as a command deletes a file (5.6); report
    `<path>: deleted again (kept in the history)`;
  - `removed`: delete it; report `<path>: removed again`.

Consequences (contract):

- no file is ever overwritten;
- a file whose content differs from the recorded checksum is left in
  place, with a line;
- a file that no operation touched and that no checksum identifies is
  left alone: an outside file that a command only unlinked is never
  deleted;
- a file found by checksum that an entry still links is copied, not
  moved; a file in the pool's files directory of a shallow library is
  copied back, so the pool entry keeps it.

The paths in the report lines are shown relative to the current
directory when they are below it, else absolute with `~` for the home
directory; each line is indented by four spaces (free).

### 6.5 The report

Free. papers prints:

```
undo: papers.bib restored to 12 papers add ~/Downloads/x.pdf --move (2026-10-22 14:03)
    files/doe_2013_a.pdf --> moved back to ~/Downloads/x.pdf
pool ../sealevel: also undone, restored to 31 papers push (2026-10-28 10:09, from ~/papers/lib)
2 file(s) of the files directory are linked by no entry now (`papers file clean` removes them):
  /home/u/papers/files/a.pdf
```

The first word is `undo`, `redo` or `restore`. A state is described as
`<number> <message> (<local time YYYY-MM-DD HH:MM>[, from <from>])`. The
last block lists the files of the files directory that the entries linked
before and no longer link. With `--dry-run`:
`DRYRUN: undo: papers.bib not restored to <state>`.

## 7. Undo and redo with a pool

### 7.1 The link

A command run in a library that also writes another library (in practice
its pool: `add` in a shallow library, a command with `auto-push`, `push`,
`sync`) saves the other library first. That save records a state in the
other library's project (5.4): its `ops` are empty (the operations belong
to the library of the command), and it has `from`. The command's library
then records, in its own next state, `pools`:

```json
"pools": {"<pool project id>": {"state": 31, "config": "/home/u/pool/.papers/config.json"}}
```

- key: the project id of the other library;
- `state`: the number of its state just made;
- `config`: the absolute path of the other library's configuration file.

There is one entry per project id: if the command saved the same other
library twice, the later state wins. The link is only added for another
library that has a configuration file. A library state with `pools` is
never skipped by rule 6 of 5.4.

### 7.2 Finding the pool steps

For undo, the steps are those undone, newest first; for redo, those
redone, oldest first. For each step S, for each entry (id, link) of its
`pools`, in order:

1. The first time an id is seen, open the pool:
   1. load the configuration file `link.config` (if it is a file); find
      its project and place (5.1), without creating an id;
   2. if its project id is `id`: **lock the pool** (wait as for any lock,
      see `library.md`) before reading its head. No other command writes
      it until the end of the undo;
   3. if the configuration is missing, its project id is not `id`, or the
      pool's place has no head: the line
      `the pool of step <link.state> is not found (at <config>): the library only`;
      this id is ignored for the rest of the command;
   4. if the sha of the pool's bibtex on disk is not that of the pool's
      head: the line
      `pool <name>: changed outside papers since its last step: the library only`;
      ignored likewise. The outside change is not recorded.

   The pool's position `at` starts at its head; its lists `taken` and
   `reverts` start empty.
2. Let `n` = `link.state` and `p` = the parent of the pool's state `n`. If
   the pool's state `n` no longer exists, or `p` is `null`: skip.
3. `before`, `after` = (`n`, `p`) for undo, (`p`, `n`) for redo.
4. If `at` = `after`: skip (already there).
5. If `at` = `before` and `reverts` is empty: append `n` to `taken`; `at`
   = `after`. The pool is still where the command left it (for redo:
   where the undo left it): its step is undone (redone) with the library.
6. Else, for undo: append `n` to `reverts` (the pool moved on: the step
   is reverted, section 8).
7. Else, for redo: in the line of the pool's `at`, the first (newest)
   state whose `reverts` contains `n`; if found, append it to `reverts`
   (the revert made by the undo is itself reverted). If not found,
   nothing.

Once a step of a pool is reverted, its later steps are reverted too
(rule 5 requires `reverts` to be empty).

`<name>` is the pool as the library's `pool` setting writes it when the
link points to that pool, else its folder with `~` (free).

### 7.3 Moving the pools

For each pool with steps:

- `taken` not empty: go to the state `at` in the pool (6.3), from its
  head, with its own default `pool_dirs` (none: a pool has no pool). Its
  head becomes `at`; its redo list: for undo, `taken` reversed followed by
  its previous redo list; for redo, its previous redo list without the
  states of `taken`. Line:
  `pool <name>: also undone, restored to <state>` (or `also redone`),
  followed by the file lines.
- `reverts` not empty: load the pool, revert each state of `reverts` in
  order (section 8) with conflicts decided by asking in a terminal, else
  `skip`. These reverts record no file operations. Save the pool with
  `reverts` = the list and the message `<command>: revert of step(s) …`.
  The pool's state has `from`. Lines:
  - a state was added:
    `pool <name>: changed since, so step(s) N reverted there: <state>`;
  - nothing changed:
    `pool <name>: changed since; step(s) N not reverted there (nothing to take back without changing what was done since)`;

  followed by the lines of the revert, indented by four spaces.

### 7.4 Order

- **Undo: the pools first, then the library.** The library's undo then
  knows what the pools link after their own undo: `shared` (6.4) is the
  set of files that the moved pools link now. If at least one pool moved
  and no pool was "not found" or "changed outside", `pool_dirs` is empty,
  so a file the command moved into the pool's files directory is moved
  back out (to `~/Downloads`, say) unless a pool still links it.
  Otherwise (`--library-only`, a pool not found, or no pool step) the
  default applies and pool files are copied back.
- **Redo: the library first, then the pools.** The library's redo moves
  the files into the pool's files directory again, so they are there when
  the pool's bibtex links them again.

The operations of such a command are in the library's state only, so the
library's undo moves the files, and the pool's undo only changes its
bibtex and `.papers/` files.

### 7.5 `--library-only`, and commands run in the pool

- `undo --library-only`, `redo --library-only`: no pool step is looked
  at; the pool stays as it is; files moved to the pool are copied back;
  no auto-push follows.
- `papers -C POOL undo` changes the pool only: its last step, whichever
  library made it (`from` names it). The library's link then no longer
  matches where the pool is; a later undo in the library reverts instead.
- `papers restore` never touches the pools.

### 7.6 Auto-push after undo and redo

After an undo or redo without `--library-only`, in a shallow library with
`auto-push` (not with `--dry-run`): the entries shared with the pool that
differ from their origin record are pushed (conflicts: `skip`; new
entries are not pushed). If the push updated an entry, the exchange is
saved (a pool state, then a library state with `pools`), and the library's
redo list from before the push is put back on its new head. In general
there is nothing to push: the undo restored the origin records with the
bibtex.

## 8. Revert: `papers history --revert N`

Takes back the changes of step N alone, as a new step; the later steps
stay. The library is locked, its head brought up to date (5.2).

Errors (nothing changes):

- no bibtex: `no library: --revert takes back a step of the history of a library`;
- no state N: ``no step N in the history of the library (see `papers history`)``;
- N not in the line of the head: ``step N is not in the current history of
  the library: `papers restore N` goes there``;
- N has no parent (or it was dropped): `step N is the first step of the
  history: nothing before it to go back to`.

Let P = the parent of N, and **before**, **after** = the entries of the
bibtex of P and of N, **now** = the entries of the library.

### 8.1 The entries step N changed

Keys are compared without case.

1. For each entry E of **after**: its counterpart in **before** is the
   entry with E's key; if there is none, the first key of E's `ids` field
   (comma-separated, trimmed, without case) that is a key of **before**
   and not a key of **after**. With a counterpart B: a change (B, E) if
   their contents differ (the type, the key and all fields, values
   compared as written); none if equal. Without: an addition (none, E).
2. Each entry of **before** that was no counterpart: a removal (B, none).

The entry **now** of an entry X of a state: the entry of the library with
X's key; else the entry whose `ids` contains X's key.

### 8.2 Rules per entry

- **Added by N** (none, E): no entry now: nothing. An entry now equal to E
  (as in 8.1, the `file` field ignored): removed. Otherwise kept, with the
  line ``<key>: added by step N and changed since: kept (`papers rm <key>`
  removes it)``.
- **Removed by N** (B, none): an entry now for B: nothing. Otherwise a
  copy of B is added, with B's file links (resolved against the directory
  of the bibtex, then written as the `paths` setting says).
- **Modified by N** (B, E): no entry now: the line
  `<key>: changed by step N and removed since: not added back`.
  Otherwise, with W = the entry now:
  1. A three-way merge of the fields, as pull does (see `exchange.md`):
     target W, other side B, base E, the tags (`keywords`) left out of
     all three. The key, `ids` and `file` are not merged (W's are kept).
     A field N changed (B ≠ E) that did not change since (W = E) goes back
     to its value in B; a field changed since only keeps W's; a field
     changed on both sides to different values is a conflict.
  2. Conflicts are decided as for pull with `--on-duplicate`: `ask` (the
     dialogue; the default in a terminal), `keep` (W's values), `update`
     (B's values), `skip`, `error` (stop before saving; the default
     without a terminal). Skipped (or any decision that is not a merge):
     the line `<key>: changed since step N too: left as it is`, and the
     entry is not changed at all.
  3. File links, one by one, compared by real path: W's links without
     those E has and B has not, followed by those B has and neither E nor
     the result has.
  4. Tags, one by one, without case: W's tags without those E has and B
     has not, followed by those B has and neither E nor the result has.
     Written as `keywords = {a, b}` (joined by `, `), or the field removed
     when there are none. Tags added since stay, without conflict.
  5. Key: if N changed the key (B's ≠ E's) and W still has E's key: W
     gets B's key back, unless another entry has B's key now (then the
     line `<key>: renamed by step N from <B key>, now another entry's key:
     the key stays`). B's key is removed from W's `ids` (the field removed
     when empty). The rename is followed as any rename is (crossref
     fields, the keys in the origin records, see `exchange.md`).

### 8.3 Files, `distinct.json`, origin records

- `distinct.json`: the pairs in N's file and not in P's are removed from
  the current pairs; those in P's and not in N's are added if absent. Two
  pairs are equal when they have the same two sides in either order
  (sides compared as JSON values).
- The files: restored as undo does (6.4) with: `current` = the links of
  the library before the revert, `target` = the links after the entry
  changes, the operations of N only, undo = true, checksums =
  `files.json` of P, the default `pool_dirs`. These operations are
  recorded: they are the file operations of the revert's state (unlike
  undo).
- Origin records (`.papers/origin/`): their content is not changed (only
  their keys follow a key changed back). The next pull or push compares
  with them.
- With `--dry-run`: the report of the entries, no files, nothing saved.

### 8.4 The state

The library is saved as after any command that changes entries (with
auto-push in a shallow library, the revert is pushed). The new state has
`reverts: [N]` and the message `papers history --revert N`. `papers undo`
takes it back like any step.

If step N also wrote a pool, the pool is not reverted. For each entry of
N's `pools` whose configuration file exists, papers prints:
``step N also changed pool <name> (its step M): `papers -C <name> history --revert M` takes it back there``.

## 9. Retention

### 9.1 The limit

`history-size`, in megabytes (1 MB = 1048576 bytes), 500 by default, 0
for no limit:

- for the shared store: the value of the machine configuration (a
  library's value is ignored);
- for a separate store (2.6): the library's value, else the machine's,
  else 500.

A store is recognised as separate when its parent folder is named
`separate`.

The size of a store is the sum of the sizes on disk of the files in
`objects/*/` and `file-objects/*/`, `.tmp` files excluded. States and
`heads.json` are not counted.

### 9.2 Pruning

Contract for what may be removed; when to prune is free.

1. **References**: every state of every project of the store refers to
   the pieces of its `bibtex`, the pieces of each of its `files`, and the
   file objects of its `deleted`.
2. **Protected states**: the current state of each place (`state` in
   `heads.json`) of each project. They are never dropped.
3. **Order**: the other states, sorted by `time`, then by number, oldest
   first, all projects together.
4. **Removable object**: no state refers to it, and its modification time
   is at least `GRACE` = 3600 seconds old.
5. `total` = the size of the store (+ the extra bytes about to be stored,
   for the guard of 5.6), minus the removable objects.
6. While the limit is not 0 and `total` > limit: drop the next state of
   the order; the objects it referred to that become removable are
   subtracted from `total`.
7. Remove the state files dropped and the removable objects. A removed
   file object goes to the system trash (deleted if there is none); a
   piece is deleted.

Consequences:

- the oldest states go first: the ancestors of a head are dropped before
  its recent steps, and undo stops where the line is cut (`only K
  step(s) to undo`);
- an object younger than one hour is never removed, so a command's
  objects are safe before its state is written;
- when the protected states alone hold more than the limit, all other
  states are dropped.

When papers prunes (free): after a state whose operations include a
`trashed` file; after operations added to a state (5.5), when it then has
`deleted` files; when a new state's number is a multiple of 50 (also when
no state was added and the head's number is one); after
`history --remove ID`. Nothing is pruned when the limit is 0. papers
prints, at info level, `N old step(s) dropped from the history
(history-size: S MB)`.

### 9.3 `papers history --remove [ID]`

- Without ID: if other places use the project, only this place's head is
  removed: `removed the history of <place>; the history of the library
  stays for the other folder(s) that use it: …`. Otherwise, after
  confirmation, the folder `projects/<id>/` is deleted (`removed the
  history of the library (K steps)`). The pieces and files stay until a
  later prune removes them.
- With ID: the project of that id in the shared store or a separate
  store (the first found); after confirmation, its folder is deleted and
  that store is pruned. Unknown: ``no history of a library ID (see
  `papers history --all`)``.
- The confirmation: `-y`/`--yes` skips it; without a terminal the command
  stops with an error.
- No project: `the library has no history`.

### 9.4 `papers history --drop-files N|PATH`

The files the history keeps for one step, or for one deleted path:

1. Find them: for state N (or, with a path, every state of the project),
   each `trashed` operation (paths made absolute as in section 4) whose
   checksum is in the state's `deleted`, whose `src` equals the given path
   (absolute, `~` expanded, normalized) when a path is given, and whose
   file object exists. No state N: ``no step N in the history of the
   library (see `papers history`)``. None found: `the history keeps no
   file deleted by step N` (or `from PATH`).
2. List them with their sizes and ask (`-y` skips; without a terminal,
   an error).
3. Remove their checksums from `deleted` in every state of the project
   (rewriting those states). `ops` stays: undo reports
   `no longer in the history (see the history-size setting), not
   restored`.
4. Each file object that no state of any project of the store lists in
   `deleted` goes to the system trash. One that another project keeps
   stays (and undo in this library can still find it by checksum).

### 9.5 `keep-deleted-files`

Machine setting, true by default. False: files deleted by commands go to
the system trash (5.6), `papers history` says `deleted files not kept:
keep-deleted-files false`, and undo reports `deleted by the command, not
restored`.

## 10. `.papers/files.json`

The checksums of the files that the entries link to. Location: `.papers/`
of the library directory; a bibtex without library has none.

```json
{
 "files": {
  "../out/y.pdf": "7e4fa2eb8c7ac089739d5defc4489fad68a100d92082ca35c6b40a4524821f87",
  "files/doe_2000_a.pdf": "2493a40c8dae940590f8b323c46051a641bebd740aa5d1997108043a9b301274"
 }
}
```

- Keys: the path of a file, relative to the directory of the bibtex (with
  `..` for a file outside it), or absolute with `paths absolute`. Values:
  sha256 of the file's content.
- Written with one-space indentation, sorted keys and a final newline,
  through a temporary file and a rename. When there is no checksum left,
  the file is deleted.
- Read: each key resolved against the directory of the bibtex and
  normalized. An unreadable file means no checksums.

When it is written: at each save of the library (5.4, before the bibtex):

1. keep the checksums of the paths still linked by an entry; drop the
   others;
2. with the `checksums` setting true (the default): compute the checksum
   of the files that the command moved or copied (the `dst` of its
   operations so far) and of the files linked now but not when the
   library was loaded, when they are linked and exist;
3. write the file if the result differs from what was read.

`papers file checksum` writes the checksums of all linked files (or of
the entries given), as a save with other changes.

How undo uses it: the file is one of the kept `.papers/` files, so each
state has the checksums of its links. Going to a state, the checksums of
the state restored give `want` (6.4): a file whose path is free is found
by its content wherever the commands left it, or among the deleted files;
a file at its path with another content is not overwritten and not
moved.

## 11. The parse cache

papers keeps a cache of parsed bibtex pieces, so that a large bibtex is
not parsed again in full at each command (see `bibtex.md` 2.7).

- Location: `<cache dir>/parsed/<first two hex>/<sha256>.json`, where
  `<cache dir>` is `$XDG_CACHE_HOME/papers` or `~/.cache/papers` (Linux),
  `~/Library/Caches/papers` (macOS), `%LOCALAPPDATA%\papers\papers\Cache`
  (Windows), and the sha256 is that of a piece cut as in 2.3.
- Content: `{"format": 1, "blocks": [...]}`, the blocks that the Python
  bibtex parser makes of the piece (kind, line within the piece, raw
  text, type, key, fields with their line). A file of another `format`,
  or unreadable, is ignored.
- A piece is cached only when every block is an entry, a string, a
  preamble or a comment. Otherwise (a failed block, a duplicate key within
  the piece, an entry cut by a line that starts with `@` inside a value)
  the whole text is parsed without the cache.
- The blocks of all pieces, in order, make the parsed library; the rules
  that apply to the whole file (duplicate keys across pieces, `@string`
  references across pieces) run on it as on a parse of the whole text.
- Reading a cached piece sets its modification time to now. After a
  parse that added pieces, the least recently used files are removed
  until the cache holds at most 50 MB.

Contract:

- The cache must never change a result: a parse with it gives the same
  blocks, values, line numbers and failed blocks as a parse of the whole
  text without it.
- The format is that of the Python parser. Another implementation does
  not read it, and must not write into `<cache dir>/parsed/` (it would
  give Python wrong blocks). Having a cache, and its location, are free
  otherwise.

## 12. `papers history`

Free (display), except where it names stored data.

```
  13 papers rm smith2020 --delete-files (2026-10-22 14:10)  (undone: `papers redo`)
> 12 papers add ~/Downloads/x.pdf --move (2026-10-22 14:03)
  11 papers tag smith2020 --add climate (2026-10-21 09:12)  [3.2 MB of deleted files]
  ... 4 older step(s) (-n 0 shows them all)
history: ~/.local/share/papers/history, 3.2 MB (up to 500 MB: the history-size setting; deleted files kept)
stale: ~/.local/share/papers/backups (backup of an earlier papers, 12.0 MB, no longer used) — delete with: rm -rf ~/.local/share/papers/backups
```

- The redo list first, the furthest state at the top, marked
  ``(undone: `papers redo`)``; then the line of the head, the head marked
  `>`, at most `-n` states (20 by default, 0: all).
- `[X of deleted files]`: the size of the file objects of the state's
  `deleted` that exist.
- No head: `no history yet: each command that changes the library records
  a step`.
- `--all`: for each store with projects, its root and size; for each
  project: `* <id>: K steps, X MB of its own, last used at <place>` (own:
  the objects that only this project refers to; last used: the place with
  the largest head `time`).

**Old backups** (`stale:` lines). papers lists, and never deletes, the
backups of earlier versions:

- `.papers/backup` in the library directory (the git backup of earlier
  v3 builds);
- `<data dir>/backups` and `$XDG_DATA_HOME/papers/backups` (or
  `~/.local/share/papers/backups`), the backups of papers 3.0.0b2 and
  earlier (the second is the location used on every platform by older
  versions; listed once when they are the same folder).

Each with its total size. There is no migration from them.

## 13. Two implementations on one store

Python papers and another implementation may run at the same time on the
same machine, on the same store. What makes this safe, and what does not:

- **Objects** are named by content and written by rename: two writers of
  the same object write the same bytes. Temporary files end with `.tmp`
  and have a name of their own per process.
- **State numbers** are allocated by exclusive create (2.5): no two
  states get one number.
- **The library** is protected by its lock (see `library.md`): a command
  that writes a library, and undo, redo, restore and revert, hold it;
  undo and redo also lock each pool before reading its head (7.2). Both
  implementations must take the same lock file.
- **The writing order** (2.8) and the modification time of reused objects
  protect against a concurrent prune.
- **Not protected**:
  - `heads.json` is read, changed and rewritten without a lock of its
    own. Two places of one project (a library and its copy, which have
    different locks) written at the same moment can lose one head update;
  - a prune running between the write of a state and the write of its
    head may drop that state (it is not yet a head; it is the newest, so
    it is dropped last);
  - `--drop-files` and `--remove` change states and projects without a
    lock.

  An implementation may add a lock for these; it must not require one
  from the other implementation.
- The store keeps no format version. A new key in a state must be
  optional for the other implementation (3.1).

## Open questions

1. **A state number can be given again.** A new number is the largest
   present + 1 (papers/history.py:290). If the retention drops the
   highest-numbered state of a project (a redo-able state of a project
   not used for a while, papers/history.py:180-206), the next state takes
   its number. A redo list (papers/history.py:345 keeps the numbers that
   exist), a `pools` link of a library (papers/backup.py:287) or a
   `reverts` list that named the dropped state then names an unrelated
   one.
2. **"The history of the libraries is dropped" is not done.** The question
   before deleting more than `history-size` says so
   (papers/backup.py:349-352), but on yes the files go to the system trash
   and nothing is pruned (papers/journal.py:189-196,
   papers/backup.py:290): the history stays.
3. **A pool step reverted by undo or redo records no file operations.**
   The revert and the pool's save run without recording
   (papers/backup.py:582-588), and the pool is not the library of the
   command, so its state has `ops: []` (papers/backup.py:267) even when
   the revert moved files. `papers -C POOL undo` of that revert brings no
   file back.
4. **Unreachable line in revert.** For an entry removed by step N, an
   entry with its key is found first by the "entry now" lookup, which
   returns early (papers/revert.py:151-152); the check "another entry has
   its key now: not added back" (papers/revert.py:153-155) can never
   apply.
5. **The outside state does not read `.papers/`.** It copies the files of
   the head (papers/backup.py:210), and outside changes are detected on
   the bibtex only (papers/backup.py:200). An edit of `distinct.json` or
   of an origin record made outside papers becomes part of the next
   command's state, and undoing that command takes it back too.
6. **No state, but the operations after the save still join one.** When
   rule 6 of 5.4 adds no state, the head (the previous command's state)
   is still given as where the command's later operations go
   (papers/backup.py:272-289); operations done after that save then join
   the previous command's state (papers/backup.py:295-305).
7. **Several saves of one pool in one command.** `pools` holds one state
   per pool id (papers/backup.py:287): if a command saves the same pool
   twice, undo takes back the last pool step only. Can it happen (sync
   with pull and push)?
8. **Auto-push after undo and redo.** The push state is a child of the
   restored state, but the old redo list is put back on it
   (papers/cli/backup_cmds.py:46-52): redo then leaves the push state for
   a sibling branch, and the push state is in no redo list. Also, a pool
   revert made by the undo leaves a pending pool link
   (papers/backup.py:286-287) that this push state then records as its
   `pools`.
9. **Restored text is not byte for byte everywhere.** The bibtex and the
   `.papers/` files are read as UTF-8 without newline translation
   (papers/backup.py:112-114) but written in text mode with the locale's
   encoding (papers/utils.py:283, called from papers/backup.py:453 and
   471). On Windows `\r\n` becomes `\r\r\n`; with a non-UTF-8 locale the
   encoding changes. A bibtex that is not UTF-8 cannot be recorded
   (papers/backup.py:113).
10. **"deleted again (kept in the history)" with keep-deleted-files
    false.** The line is printed whatever happened to the file
    (papers/journal.py:369-370, 405-406); with the setting false it went
    to the system trash.
11. **`history-size 0` never removes anything.** Pruning returns at once
    when the limit is 0 (papers/backup.py:312), so objects no state refers
    to (after `--remove`, after `--drop-files` of a shared file) stay for
    ever. `--remove` of the last place does not prune at all
    (papers/cli/backup_cmds.py:122-139).
12. **Recent unreferenced objects count but cannot be freed.** Objects
    younger than `GRACE` that no state refers to (for example written by
    a concurrent command) count in `total` (papers/history.py:198-200)
    but are never subtracted, so they make the prune drop more states.
13. **`papers history` ignores a bibtex without library.** The command is
    not a library command (papers/cli/parser.py:1035), so
    `papers history --bibtex x.bib` says "no library"
    (papers/cli/backup_cmds.py:225-229), while `papers undo --bibtex x.bib`
    works on that bibtex's history.
14. **Kept `.papers/` files relative to the bibtex directory.** The names
    are looked up in the directory of the bibtex
    (papers/backup.py:101-109) while `files.json` is in the library
    directory (papers/checksums.py:23-27): see `library.md`, open
    question 1.
15. **Separators in stored paths.** The names in `files` and the relative
    paths in `ops` use the separator of the operating system
    (papers/backup.py:140-153, papers/checksums.py:19), so a store is not
    portable between Windows and other systems. Should the stored form
    use `/`?
16. **Separate store recognised by its folder name.** The retention of a
    store uses the library's `history-size` when the store's parent
    folder is named `separate` (papers/backup.py:71-72); a library's own
    `history-size` is ignored in the shared store. Intended?
17. **The pool step's `from` is the bibtex directory**, not the library
    directory (papers/backup.py:283): they differ when the bibtex is in a
    subfolder.
18. **`kind` is never read.** It is written (papers/backup.py:212, 276)
    and documented, but nothing uses it. Keep it in the contract?
