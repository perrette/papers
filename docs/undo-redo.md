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
undo: papers.bib restored to 4f1c9a2e papers add ~/Downloads/esd-4-11-2013.pdf --move (2026-10-22 14:03)
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
  b7e30d51 papers rm smith2020 --delete-files (2026-10-22 14:10)  (undone: `papers redo`)
> 4f1c9a2e papers add ~/Downloads/esd-4-11-2013.pdf --move (2026-10-22 14:03)
  92ad6c07 papers tag smith2020 --add climate (2026-10-21 09:12)
  ...
history: ~/.local/share/papers/history, 3.2 MB (up to 500 MB: the history-size setting; deleted files kept)
```

A step is named by its identifier, the first column: 8 characters of the
sha256 of the step (of its bibtex, its other files, its parent and its
time), which never changes. A command that takes a step accepts the start
of it, 4 characters or more, as long as no other step starts the same way.

`papers restore STEP` brings the library to that step. Making a change after an
undo starts a new line of history; the undone steps are not lost, and
`papers restore STEP` still reaches them.

## Taking back an older step

`papers undo -n 3` goes back over the last three steps. To take back one
step alone and keep the steps made after it, give its identifier (or the
start of it, see [The history](#the-history)):

```
$ papers history --revert 92ad
Modified -> smith2020: Sea level rise... (later)
```

The revert is a new step of the history (`papers undo` takes it back). For
each entry that the step changed, papers compares the entry before the step,
after it, and now:

- an entry that the step added is removed, unless it changed since (it is
  kept, and a line says so);
- an entry that the step removed comes back as it was;
- a field that the step changed goes back to its value before the step,
  unless it changed since: then it is a conflict, decided as for
  [`papers pull`](pools.md#papers-pull), with `--on-duplicate` (`keep`: the
  value now, `update`: the value before the step; in a terminal, papers asks);
- the tags and the file links are taken one by one: those that the step added
  are removed, those it removed come back, those added since stay;
- a key that the step changed (with `--keep-old-key`, which keeps the former
  key in `ids`) goes back to the former key.

The files go back as undo moves them, for the files of the step only: a file
that the step moved or renamed is moved back, a file it deleted comes back
from the history. The pairs that the step recorded in `.papers/distinct.json`
(entries that are not the same paper) are removed. The origin copies
(`.papers/origin/`) are not changed: the next `pull` or `push` compares
with them, and with auto-push the revert is pushed like any command.

A step that also changed the pool is reverted in the library only; a line
gives the command that reverts the pool's step:
`papers -C ../pool history --revert 3c5e0b7a`.

## Deleted files

A file that a command deletes (`papers rm --delete-files`, `papers file
rm`, `papers file clean`...) is kept by the history, and `papers undo` puts
it back, also when no entry linked to it, or when the command was stopped
(an error, Ctrl-C) after deleting it:

```
undo: papers.bib restored to 4f1c9a2e papers add paper.pdf (2026-10-22 14:03)
    files/perrette_2013_a-scaling-approach.pdf: restored from the history
```

The history keeps up to 500 MB (the `history-size` setting). Beyond that,
the oldest steps are dropped first, and the deleted files that only they
needed go to the trash of the system (a step that brought a file back from
the history, `papers file fix` or `papers history --revert`, needs it too). Before a command that deletes more
than the history keeps, or so much that recent steps would be dropped,
papers asks first (`-y` answers yes; without a terminal, the files are
kept):

```
3 files to delete, 812 MB: more than the history keeps (history-size: 500 MB).
- This command cannot be undone: the files go to the trash of the system, not to the history (the history keeps its steps).
Proceed? [y/N]
```

`papers history` shows the size of the files each step keeps
(`[3.2 MB of deleted files]`). `papers history --drop-files STEP` removes from
the history the files that the step deleted, and `--drop-files PATH` the file
deleted from PATH (by any step): they go to the trash of the system, the
steps stay, and undo says the files are no longer in the history. `papers
history --remove` removes the whole history of the library. Both ask
first (`-y` does not).

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
step in its own history. When the command wrote the pool, the step of the
library also records the step of the pool.

- `papers undo` and `papers redo` in the library undo and redo the pool's
  step too, as long as the pool is still where the command left it (for
  redo: where the undo left it). The files that the command moved to the
  files directory of the pool are moved back.
- If the pool changed since (another command in the pool or in another
  library that shares it), papers reverts the pool's step there instead (a
  new step of the pool, see [Taking back an older step](#taking-back-an-older-step)).
  An entry that changed in the pool since stays; in a terminal, papers asks
  about a field changed on both sides. `papers redo` then reverts that
  revert. If the undo took the pool's step back and the pool changed
  after it, `papers redo` does the step again there (a new step of the
  pool, with the same rules).
- If the pool changed outside papers since its last step, the library only
  is undone, and a line says so.
- With auto-push, the shared entries that differ from their origin copy are
  pushed after the undo or redo, as after any command. In general there is
  nothing to push: the undo restores the origin copies with the bibtex.
  There is something when a step was made with auto-push off; that push is
  then a new step, after which there is nothing to redo, as after any
  command (`papers restore STEP` still goes to the steps undone).
- `papers undo --library-only` (and `redo --library-only`) leave the pool
  as it is: the files that the command moved to the pool are copied back.
- The pool does not know which libraries use its entries. If another
  library pulled an entry since the `add` that undo takes back, that
  library's link to the PDF breaks: the PDF goes back where it came from,
  and `papers file fix --search FOLDER` there finds it.
- `papers -C POOL undo` and `papers -C POOL redo` change the pool only:
  they undo the last change of the pool, whichever library made it. In the
  history of the pool, a step made from a library names it:
  `31 papers add ../new.bib (2026-10-28 10:09, from ~/papers/paper2)`.
- The library and the pool are locked during the undo (see
  [Two commands at the same time](library-management.md#two-commands-at-the-same-time)):
  no other command changes the pool between the moment undo looks where the
  pool is and the moment it writes it.

```
$ papers add ~/Downloads/esd-4-11-2013.pdf --move
$ papers undo
undo: papers.bib restored to 0e8d41f3 papers pull (2026-10-28 10:12)
    ~/sealevel/files/perrette_2013_a-scaling-approach.pdf --> moved back to ~/Downloads/esd-4-11-2013.pdf
pool ../sealevel: also undone, restored to 3c5e0b7a papers push (2026-10-28 10:09)
```

The library also restores its origin copies (`.papers/origin/`, see
[Pools](pools.md#origin-copies)) and `.papers/distinct.json` to the step it
goes back to, and removes those that did not exist at that step. The next
exchange then compares the library and the pool to the origin copies of
that step:

- After undoing a `pull`, or a `push` whose step the pool did not undo or
  revert (`--library-only`, a conflict in the pool), the pool shows as
  changed in `papers status`: what the pool has beyond the restored state
  comes again with the next `pull`, and the next `push` does not send the
  undone state back to the pool.
- After an undo in the pool, the origin copies of the library still have the
  newer version, so the pool shows as changed, and a `pull` takes the pool's
  older values for the fields the library did not change since. A field
  that the pool undo removes is a removal in the pool: the `pull` removes it
  from the library too, unless the library changed it since (a conflict, see
  [`papers pull`](pools.md#papers-pull)).

`papers restore STEP` restores the library only.

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
