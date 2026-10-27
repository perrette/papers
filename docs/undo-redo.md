# Undo and redo

Did a `papers add` and are unhappy with the result?

```
papers undo
```

will revert to the previous version. Without git-tracking, repeating it only
jumps back and forth between the latest and before-latest version.

With git-tracking (the default of `papers init` when git is installed), `papers undo` and
`papers redo` step through the whole history of the library (`-n N` steps at
once).
History is append-only: undo and redo record *restore commits* in the backup
repository instead of rewriting it, so no state is ever lost. In particular,
making a new change while undone starts a new line of history on top, and the
states that were still redoable remain reachable with further `papers undo`
or with `papers restore --ref COMMIT` (use `papers git log` to find
`COMMIT`). `papers restore` without `--ref` restores the last version of the
backup. `papers restore-backup` is the deprecated name of `papers restore`.

`papers undo` and `papers redo` print the state they restore, with the
command that made it, e.g.

```
undo: papers.bib restored to 3f2a1c9 papers add paper.pdf (2026-10-22 14:03)
```

## Files

`papers undo`, `papers redo` (of any number of steps, `-n N`) and
`papers restore --ref COMMIT` bring the files back with the bibtex: a
moved or renamed file is moved back where it was, even outside the library
(e.g. a folder of the project that `papers file rename` moved it from, or
`~/Downloads` for `papers add --move`), a copy placed in the files directory
is removed, a deleted file comes back from the trash; redo does the same
again. Each file is listed:

```
undo: papers.bib restored to 3f2a1c9 papers add paper.pdf (2026-10-22 14:03)
    files/perrette_2013_a-scaling-approach.pdf --> moved back to ~/Downloads/esd-4-11-2013.pdf
```

papers compares the files that the entries link to now with those of the
restored state, and finds each missing file:

- where the commands in between moved or copied it: each command records
  the files it moves, renames, copies or deletes, with their checksum (with
  the git backup, in the snapshot of the command, `files-journal.json`;
  without it, in the backup folder, `.papers/backup/previous-files.json`);
- by its checksum (`.papers/files.json`, see [Checksums](#checksums)): a
  file that no entry links to any more is moved, a file that an entry links
  to, or a file of the pool, is copied;
- in the trash (see [The trash](#the-trash));
- in the git-lfs copies of the backup.

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

The commands made before papers recorded the files (3.0.0b3) have no
journal: their files are found by checksum only, if `papers file checksum`
wrote them.

### Checksums

`.papers/files.json` holds the checksum (sha256) of the files that the
entries link to. With the `checksums` setting (true by default), a command
writes the checksum of the files it moves, copies, adds or links; the git
backup commits the file with the bibtex. `papers file checksum` writes the
checksums of all the files (or of the entries given), `--check` reports
the files whose content changed since their checksum (e.g. annotated PDFs)
and writes nothing. With `papers config checksums false`, the commands
write no checksum, and undo finds the files through the journal of the
commands only.

### The trash

A file that a command deletes (`papers rm --delete-files`, `papers file
rm`, `papers file clean`, the library's copies replaced by those of the
pool with `papers config pool PATH`) goes to the trash of the library, in
its backup folder, `.papers/backup/trash`, and `papers undo` puts it
back:

```
undo: papers.bib restored to 3f2a1c9 papers add paper.pdf (2026-10-22 14:03)
    files/perrette_2013_a-scaling-approach.pdf: restored from the trash
```

A file stays in the trash for 30 days at most (the `trash-days` setting),
and the trash holds 100 MB at most (`trash-size`): beyond that, the oldest
files leave it first, to the trash of the system (where there is one,
otherwise they are deleted). A command that would delete more than the trash
holds asks first, and then deletes the files for good; without a terminal
to ask, it keeps them. A file that has an identical copy that stays (e.g.
in the pool) is not put in the trash: undo copies it back from that copy.
A file that is no longer in the trash is not restored: undo says so, and
the restored link is broken (with git-lfs, `--restore-files` takes the
files of the files directory from the backup).

## Undo in a library that has a pool

A pool is a library with its own backup and its own history. A command that
exchanges entries with the pool (`add` in a shallow library, a command
that changes entries with auto-push; `push`, `pull`, `sync`) writes both, and each records a
step in its own history.

- `papers undo` and `papers redo` in the library change the library only.
  The pool keeps what the undone command wrote to it.
- `papers -C POOL undo` and `papers -C POOL redo` change the pool only.

The library also restores its origin copies (`.papers/origin/`, see
[Pools](pools.md#origin-copies)) and `.papers/distinct.json` to the state of
the step it goes back to, and removes those that did not exist at that step.
The next exchange then compares the library and the pool to the origin
copies of that step:

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

Without git-tracking, undo swaps the bibtex only: the origin copies stay as
the last exchange left them. The undone change then counts as a change of
the library: after undoing a `pull`, the next `push` sends the library's
older values to the pool (it lists the entries it modifies).

See [Git integration](git.md) for how to enable git-tracking.
