# Undo and redo

Did a `papers add` and are unhappy with the result?

```
papers undo
```

puts the library back as it was before the command: the bibtex, and the
files that the command moved, renamed, copied or deleted. `papers redo`
does the command's changes again. Both take `-n N` to go several steps at
once.

```
$ papers add ~/Downloads/esd-4-11-2013.pdf --move
$ papers undo
undo: papers.bib restored to 12 papers add ~/Downloads/esd-4-11-2013.pdf --move (2026-10-22 14:03)
    files/perrette_2013_a-scaling-approach.pdf --> moved back to ~/Downloads/esd-4-11-2013.pdf
```

There is nothing to set up: every command that changes a library records a
step in its history.

## The history

`papers history` lists the steps of the library, the latest first. `>`
marks where the library is now, and the steps that `papers redo` can bring
back are marked as undone:

```
$ papers history
  13 papers rm smith2020 --delete-files (2026-10-22 14:10)  (undone: `papers redo`)
> 12 papers add ~/Downloads/esd-4-11-2013.pdf --move (2026-10-22 14:03)
  11 papers tag smith2020 --add climate (2026-10-21 09:12)
  ...
history: ~/.local/share/papers/history, 3.2 MB (up to 500 MB: the history-size setting; deleted files kept)
```

`papers restore N` brings the library to step N. Making a change after an
undo starts a new line of history; the undone steps are not lost, and
`papers restore N` still reaches them.

## Deleted files

A file that a command deletes (`papers rm --delete-files`, `papers file
rm`, `papers file clean`...) is kept by the history, and `papers undo` puts
it back, also when no entry linked to it, or when the command was stopped
(an error, Ctrl-C) after deleting it:

```
undo: papers.bib restored to 12 papers add paper.pdf (2026-10-22 14:03)
    files/perrette_2013_a-scaling-approach.pdf: restored from the history
```

The history keeps up to 500 MB (the `history-size` setting). Beyond that,
the oldest steps are dropped first, and the deleted files that only they
needed go to the trash of the system. Before a command that deletes more
than the history keeps, or so much that recent steps would be dropped,
papers asks first (`-y` answers yes; without a terminal, the files are
kept):

```
3 files to delete, 812 MB: more than the history keeps (history-size: 500 MB).
- This command cannot be undone: the files go to the trash of the system, not to the history.
- The history of the libraries is dropped: no undo before this point.
Proceed? [y/N]
```

If you would rather not keep deleted files at all (you have your own
backups, or no space to spare): `papers config --global keep-deleted-files
false`. Deleted files then go straight to the trash of the system, and undo
says it cannot bring them back.

## Changes made outside papers

When you edit the bibtex yourself (in an editor, JabRef, another program,
or on another computer that syncs the library), papers notices it at its
next command and records your change as a step of its own, "changed outside
papers". `papers undo` never drops it silently: undoing a papers command
goes back to what was on disk just before it, your change included.

Running `papers undo` right after your own edit undoes that edit (`papers
redo` brings it back). `papers restore` without a step number does the
same: it puts the library back to its last step, as papers left it.

## Where the history is

The history is kept on your computer, not in the library:
`~/.local/share/papers/history` on Linux (the `history-dir` setting). It is
not synced or shared with the library: a library you copy to another
computer, or receive from someone, starts with an empty history there.

The history follows the library: moving or renaming the library folder
keeps it (each library has an identifier, `id` in `.papers/config.json`).
A copy of a library shares the history up to the copy, then each folder
has its own steps. `papers export` makes a new library, with a history of
its own.

`papers history --all` lists the histories on the computer, with the space
each one uses; `papers history --remove` removes that of the library
(`--remove ID`: another one, e.g. of a library you deleted).

All libraries share one store, so that a file kept by several of them is
stored once. `papers config history-separate true` gives a library a store
of its own, with its own `history-size`.

## Undo in a library that has a pool

A pool is a library with its own history. A command that exchanges entries
with the pool (`add` in a shallow library, a command that changes entries
with auto-push; `push`, `pull`, `sync`) writes both, and each records a
step in its own history.

- `papers undo` and `papers redo` in the library change the library only.
  The pool keeps what the undone command wrote to it.
- `papers -C POOL undo` and `papers -C POOL redo` change the pool only.

The library also restores its origin copies (`.papers/origin/`, see
[Pools](pools.md#origin-copies)) and `.papers/distinct.json` to the step it
goes back to, and removes those that did not exist at that step. The next
exchange then compares the library and the pool to the origin copies of
that step:

- After undoing a `push` or a `pull` in the library, the pool shows as
  changed in `papers status`: what the pool has beyond the restored state
  comes again with the next `pull`, and the next `push` does not send the
  undone state back to the pool. To undo the change in the pool too, undo
  there as well (`papers -C POOL undo`).
- After an undo in the pool, the origin copies of the library still have the
  newer version, so the pool shows as changed, and a `pull` takes the pool's
  older values for the fields the library did not change since. A field
  that the pool undo removes is a removal in the pool: the `pull` removes it
  from the library too, unless the library changed it since (a conflict, see
  [`papers pull`](pools.md#papers-pull)).

## Details

### How undo finds the files

Each step records the files its command moved, renamed, copied or deleted,
with their checksum. Undo compares the files that the entries link to now
with those of the step it goes back to, and finds each missing file:

- where the commands in between moved or copied it;
- by its checksum (`.papers/files.json`, see [Checksums](#checksums)): a
  file that no entry links to any more is moved, a file that an entry links
  to, or a file of the pool, is copied;
- among the deleted files kept by the history.

The rules:

- A file is never overwritten: if its former place is taken, papers says so
  and leaves it where it is.
- A file whose content changed since the command (e.g. a PDF annotated
  since) is left as it is, with a message.
- A file outside the library that a command only unlinked (e.g.
  `papers file detach`) is never deleted by undo or redo, and the files
  that no command touched are left alone.
- In a shallow library, a file that `add` moved into the files directory of
  the pool is copied back: the pool entry keeps it.

A file outside the library (`~/Downloads`, a folder of the project) is
recorded with its full path; a file inside it, relative to the library
(with the `paths absolute` setting, with its full path), so that undo in a
copy of the library acts on the copy's files.

When another program writes the bibtex while a papers command runs, papers
does not overwrite it, and puts back the files that the command had
already moved, copied or deleted.

### Checksums

`.papers/files.json` holds the checksum (sha256) of the files that the
entries link to. With the `checksums` setting (true by default), a command
writes the checksum of the files it moves, copies, adds or links.
`papers file checksum` writes the checksums of all the files (or of the
entries given), `--check` reports the files whose content changed since
their checksum (e.g. annotated PDFs) and writes nothing. With `papers
config checksums false`, the commands write no checksum, and undo finds
the files through the steps of the commands only.

### What a step holds

The bibtex, byte for byte (stored in pieces of about 32 entries: a step that
changes one entry adds one piece, a few KB), the files of `.papers/` that belong to the library
(origin copies, `distinct.json`, `files.json`; not `config.json`), the
command and its time, and the files it moved, copied or deleted. The
history keeps older contents of the bibtex, but not of the PDFs: an
annotated PDF replaces the previous one.
