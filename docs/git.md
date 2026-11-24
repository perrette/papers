# Using git

papers does not use git: it keeps its own history of each library for undo
and redo (see [Undo and redo](undo-redo.md)), on your computer, outside the
library. That history is a way to repair mistakes, not a record of your
work: it is not synced, and it keeps a limited size.

If you want the history of your bibliography and PDFs, or to share them,
put the library folder under git yourself, like any other project:

```
cd ~/projects/sealevel
git init
git add papers.bib files .papers
git commit -m "my library"
```

papers never commits to that repository, and leaves it alone.

## The folder `.papers/`

The bibtex and the PDFs are your work. The folder `.papers/` holds the
internals of papers: what it keeps to manage them, which may change from
one version to the next. papers writes `.papers/.gitignore` (with `*`), so
that git leaves the folder out. A colleague who clones the repository runs
`papers init` to make it a library on their side.

As git does with its own `.git/config`, each copy of a library has its own
settings. To commit the configuration nonetheless (so that a clone is a
library right away), make `.papers/.gitignore`:

```
*
!.gitignore
!config.json
```

papers does not rewrite a `.gitignore` you changed. What is in the folder:

| file | what it is | without it |
|---|---|---|
| `config.json` | the settings of the library: where its bibtex and files are, its pool, the name formats, its identifier | set them again (`papers init`, `papers config`) |
| `origin/` | with a pool only: each entry as it was at the last `pull` or `push`, to tell who changed what since | the next `pull` asks about more differences |
| `distinct.json` | the pairs of entries you said are not the same paper | papers asks about them again |
| `files.json` | the checksums of the files, for undo | nothing: `papers file checksum` writes them again |

## Backups of earlier versions

Earlier versions of papers kept a git backup of each library: in the
library, `.papers/backup` (the v3 branch before 3.0.0b4), or in a folder of
the computer, `~/.local/share/papers/backups` (papers 3.0.0b2 and earlier).
papers no longer uses them, and does not delete them: `papers history`
lists those it finds, with their size, and the command that deletes them:

```
stale: ~/projects/sealevel/.papers/backup (backup of an earlier papers, 641 MB, no longer used) — delete with: rm -rf ~/projects/sealevel/.papers/backup
```

Their history does not carry over: undo starts with the first command made
with this version. The settings `git` and `git-lfs`, `papers init --git`,
`--git-lfs` and `papers git` are no longer used.
