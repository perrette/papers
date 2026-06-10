# Undo and redo

Did a `papers add` and are unhappy with the result?

```
papers undo
```

will revert to the previous version. Without git-tracking, repeating it only
jumps back and forth between the latest and before-latest version.

If papers is installed with the `--git` option, `papers undo` and `papers
redo` step through the whole history of the library (`-n N` steps at once).
History is append-only: undo and redo record *restore commits* in the backup
repository instead of rewriting it, so no state is ever lost. In particular,
making a new change while undone starts a new line of history on top, and the
states that were still redoable remain reachable with further `papers undo`
or with `papers restore-backup --ref COMMIT` (use `papers git log` to find
`COMMIT`).

See [Git integration](git.md) for how to enable git-tracking.
