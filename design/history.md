# The history of a library (undo, redo, restore)

Design agreed on 2026-10-28. It replaces the git backup (`.papers/backup`,
the `git` and `git-lfs` settings) and the trash of the library.

## What the history is for

papers keeps the states of a library so that a mistaken command can be
undone, with its files. It is not a version control system: a user who wants
the history of the bibtex and of the PDFs puts the folder under git (or
another tool) themselves. papers does not use git.

The history belongs to the machine and to the user: it is not synced or
shared with the library, and a library received from someone brings none.

## Where

```
~/.local/share/papers/history/      (platformdirs.user_data_dir('papers') + /history)
  objects/ab/ab12…                  pieces of the bibtex and of the .papers/ files, compressed
  file-objects/ab/ab12….pdf         the files that papers deleted (the trash), by checksum
  projects/<id>/
    states/000001.json …            one state per command, in a tree (each names its parent)
    heads.json                      the current state of each folder that uses the project
```

One store for all libraries: identical pieces and files are stored once
(a pool and its libraries, the copies of a library). With the
`history-separate` setting, a library has a store of its own,
`<history-dir>/separate/<id>/`, laid out the same way.

## The identifier of a library

`.papers/config.json` has an `id` (random, written at the first command).
It names the project in the store; it means a shared history, not a unique
folder. A bibtex without a library has no configuration to hold it: its
identifier is made from the real path of the bibtex (moving it loses its
history).

`papers export DIR` gives the new library a new identifier.

## States, in a tree, with a head per folder

A state records: the time, the command line, its parent, the bibtex (the
list of its pieces and the checksum of the whole text), the files of
`.papers/` that belong to the library (origin records, `distinct.json`,
`files.json`), and the file operations of the command (moved, copied,
deleted: source, destination, checksum). The paths are written as the
library writes its links: relative to the bibtex when the library has
relative paths and the file is in its folder, absolute otherwise (the
`paths absolute` setting, a file outside the library: `~/Downloads`,
`~/Zotero/storage`). A copy of the library then acts on the files its
bibtex links to: its own files with relative paths, the files of the
original with absolute ones.

The bibtex is cut before each line that starts with `@` (an entry), and
the entries are grouped in pieces of about 32: a piece ends after an entry
whose checksum (crc32 % 32) says so, so that adding or removing an entry
changes only the piece it is in. Each piece is stored once (zlib, named by
its sha256). A command that changes one entry stores one piece of a few
KB; a library of 10000 entries is about 300 files. Rebuilding is a concatenation: the bibtex
comes back byte for byte (comments, `@string`, formatting).

`heads.json` maps the real path of each folder that uses the project to its
current state, and the states that `redo` goes forward to. A folder papers
has not seen (moved, copied, sent back) starts from the most recent state
whose bibtex is the one on disk; if none is, from the most recent state,
with a state "changed outside papers" on top. A moved folder continues; a
copy branches: both share the history up to the copy. A head whose folder
no longer exists is dropped.

- **A command** adds a state, child of the head, and moves the head to it.
- **Undo** moves the head to the parent; **redo** forward again. A command
  run after an undo starts a branch; the undone states stay in the tree
  (`papers restore N`) until the retention drops them.
- **Changed outside papers** (#120): before a command, undo, redo or
  restore writes, papers compares the bibtex on disk (and the files of
  `.papers/`) to the head. If they differ, it first records them as a state
  of their own, "changed outside papers". Undo then goes back to what was on
  disk before the command, not to the last state papers wrote (changes made
  by an editor, another program, or the other machine of a synced library
  are not dropped silently).

## Files

A file is identified by its checksum (sha256). The operations of a command
say where each file went; undo, redo and restore bring the files back with
the bibtex (the rules of `papers.journal.restore` are kept: never overwrite
a file; a file whose content changed since is left as it is, and said so;
a file outside the library that a command only unlinked is never deleted).

A file that papers deletes goes to `file-objects/` (named by its checksum),
unless `keep-deleted-files` is false: then it goes to the system trash
(send2trash), and undo says it is not restored.

Not in the history: older contents of a file (an annotated PDF replaces the
old one). An edited file is declared the same file with `papers file
checksum KEY` (a later pull request: the old checksum is recorded as
replaced by the new one, and the history follows it).

## Retention

One setting, `history-size` (megabytes, 500 by default, 0: no limit), for
a store: the pieces and the deleted files of all its projects. The value
of the machine configuration applies to the shared store; a library's own
value applies to its separate store only. The
limit applies to states: beyond it, the oldest states (of any project) are
dropped, then the pieces and files that no remaining state refers to. A
current head is never dropped. A deleted file that leaves the store goes to
the system trash. Pieces and files less than an hour old are not removed
(a command writes them before its state).

The guard: before a command deletes files, papers computes what the
retention would drop. It asks (`--yes` to proceed without asking; without a
terminal the command is refused) when:

- the command alone deletes more than `history-size`: it cannot be undone,
  its files go to the system trash, and the whole history before it is
  dropped;
- or the retention would drop states of the last day, or more than half of
  the states.

## Machine settings

`history-dir` and `keep-deleted-files` (and, in a later pull request,
`editor` and a `post-command` hook) are read from the machine configuration
only, never from a library's `.papers/config.json`: a library received from
someone cannot set them. `history-separate` and `history-size` may be set
by a library: its store stays in the folder of the machine.

## The first state, and refused saves

A library without history gets a first state, the library before its first
command. papers reads it (in memory) when the command starts, and records
it when the command saves: a command that changes nothing writes nothing,
not even the identifier.

When another program wrote the bibtex since papers read it, the save is
refused (#119); the file operations of the command are then put back
(`journal.rollback`).

## Git

papers writes `.papers/.gitignore` with `*`: the folder holds papers'
internals, which a library under git does not track by default (a
`.gitignore` the user wrote is kept; the `backup/` of earlier versions is
replaced).

## Commands

- `papers undo [-n N]`, `papers redo [-n N]`.
- `papers restore N`: the state N of this project (`--ref N` kept);
  `papers restore` without N: the head (drops the changes made outside
  papers since).
- `papers history`: the states of this folder's line (number, time,
  command, the head marked), the size of the store, and the old git backups
  that are no longer used (`.papers/backup`, the folders of
  `~/.local/share/papers/backups`), with their size and the command that
  deletes them (papers does not delete them).
- `papers history --all`: the projects of the store (identifier, last
  folders, number of states, space used by it only).
- `papers history --remove`: the head of this folder; and the states of
  the project when no other folder uses it.
- `papers history --remove ID`: the history of that project.

## What goes away

The git backup and `papers git`; the `git` and `git-lfs` settings (ignored,
with a message); `init --git`, `--git-lfs`, `export --git`;
`--restore-files`; `backup_clean.bib` and the `.gitattributes` handling;
`trash-days` and `trash-size` (replaced by `history-size`); the trash of
the library (`.papers/backup/trash`); `previous.bib` and the undo without
git; `adopt_central_backup`. `papers backup` is a deprecated name of
`papers history`; `papers uninstall` is deprecated (`rm -r .papers` and
`papers history --remove`).

No migration: the old backups stay where they are, listed as stale by
`papers history` until the user deletes them.

## Code

`papers/history.py`: the store, states, heads, retention. Standard library
only (hashlib, zlib, json), and no import from the rest of papers: it
stores and reads states and objects. `papers/journal.py` keeps the file
operations and `restore`; `papers/backup.py` is replaced by the glue
between the library and the history.
