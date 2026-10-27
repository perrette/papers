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

Each command records the files it moves, renames, copies or deletes (with
the git backup, in the snapshot of the command, `files-journal.json`;
without it, next to the backup of the bibtex, `.papers.bib.files.json`).
`papers undo` of one step puts them back: a moved or renamed file is moved
back where it was, even outside the library (e.g. a folder of the project
that `papers file rename` moved it from), a copy placed in the files
directory is removed; `papers redo` does the operations again. Each file
is listed:

```
undo: papers.bib restored to 3f2a1c9 papers add paper.pdf (2026-10-22 14:03)
    files/perrette_2013_a-scaling-approach.pdf --> moved back to ~/Downloads/esd-4-11-2013.pdf
```

A file is put back only if it is where the command left it, with the same
content, and its former place is free; otherwise papers says so and
leaves it as it is (e.g. a PDF annotated since). In a shallow library, a
file that `add` moved into the files directory of the pool is copied back:
the pool entry keeps it.

`papers undo -n N` (N > 1) and `papers restore` do not move files: they
say so when the commands they go over moved some, and the files that no
entry links to any more are listed (`papers file clean` removes them).
Undo one step at a time to put the files back with each command. The
commands made before papers recorded the files (3.0.0b3) are undone
without them.

### The trash

A file that a command deletes (`papers rm --delete-files`, `papers file
rm`, `papers file clean`, the library's copies replaced by those of the
pool with `papers config pool PATH`) goes to the trash of the library, in
its backup folder (`papers status -v` shows it), and `papers undo` puts it
back:

```
undo: papers.bib restored to 3f2a1c9 papers add paper.pdf (2026-10-22 14:03)
    files/perrette_2013_a-scaling-approach.pdf: restored from the trash
```

A file stays in the trash for 30 days at most (the `trash-days` setting),
and the trash holds 100 MB at most (`trash-size`): beyond that, the oldest
files leave it first. A command that would delete more than the trash
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
