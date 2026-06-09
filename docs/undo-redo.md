# Undo and redo

Did a `papers add` and are unhappy with the result?

```
papers undo
```

will revert to the previous version. If repeated, it will jump back and forth
between the latest and before-latest version. Unless papers is installed with
the `--git` option, in which case `papers undo` and `papers redo` will have
essentially infinite memory (doing undos and making a new commit risks losing
history, unless you keep track of the commit).

See [Git integration](git.md) for how to enable git-tracking.
