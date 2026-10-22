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
attach`), papers lists them: `papers file clean` removes them.

See [Git integration](git.md) for how to enable git-tracking.
