# Git integration

## Git-tracked library

By default (when a git binary is available), a fresh `papers install`
git-tracks any change to the bibtex file. Pass `--no-git` to opt out, and
`--git-lfs` to also back up the attached files (see below):

```
$> papers install --bibtex papers.bib --filesdir files [ --no-git | --git-lfs ]
```

Installs made by older papers versions keep their saved setting; re-run
`papers install` (or `papers install --edit --git`) to enable git-tracking
on an existing install.

From now on, every change to the library will result in an automatic git
commit. And the `papers git ...` command will work just as `git ...` executed
from the backup directory. E.g. `papers git remote add origin *REMOTE URL*`;
`papers git lfs track files`; `papers git add files`; `papers git push`.

Under the hood, every save commits a copy of the bibtex file to the backup
repository. If `--git-lfs` is passed, the attached files are backed up along
with the bibtex: they are hard-linked into the backup directory and tracked
with git-lfs, together with a copy of the bibtex whose file paths point into
the backup (so the backup is self-contained). Background in
[issue 51](https://github.com/perrette/papers/issues/51).

Backup occurs in a subfolder of `~/.local/share/papers/backups` regardless of
the type of installation. Type `papers status -v` to find out, or
`papers backup list` to see every backup directory papers knows of and which
library each belongs to. Orphaned directories (e.g. whose library was
deleted) can be cleaned up with `papers backup remove NAME` (glob patterns
allowed; asks before deleting unless `--force` is passed).

Backup directories are named after the bibtex file plus a hash of its full
path (e.g. `papers-3f9a1c2b`), so two libraries can never share a directory.
Each directory also contains a `manifest.json` recording the bibtex file it
backs up; if a backup operation finds a directory that belongs to another
library (which could happen with directories created by papers versions that
used the bibtex name alone), it moves the current library to a fresh
directory instead of mixing the two histories. Directories created by older
versions keep their name and are adopted as-is.

For local installs that are already git-tracked, the feature remains useful as
it is the basis for `papers undo` and `papers redo` (see
[Undo and redo](undo-redo.md)).
