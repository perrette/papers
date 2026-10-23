# Undo and redo

Did a `papers add` and are unhappy with the result?

```
papers undo
```

will revert to the previous version. Without git-tracking, repeating it only
jumps back and forth between the latest and before-latest version.

With git-tracking (the default for fresh installs), `papers undo` and
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

Files that the undone command placed in the files directory stay there.
When no entry links to them any more (e.g. after undoing `papers file
attach`), papers lists them: `papers file clean` removes them. A file
deleted by `papers file rm` is not restored: undo restores the link, which
is then broken.

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
