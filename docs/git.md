# Git integration

## Git-tracked library

By default (when a git binary is available), a library created with
`papers init` git-tracks any change to the bibtex file. Pass `--no-git` to
opt out, and `--git-lfs` to also back up the attached files (see below):

```
$> papers init --bibtex papers.bib --filesdir files [ --no-git | --git-lfs ]
```

Libraries made by older papers versions keep their saved setting; run
`papers config git true` (or `papers config git-lfs true`) to enable
git-tracking on an existing library.

From now on, every change to the library will result in an automatic git
commit. And the `papers git ...` command will work just as `git ...` executed
from the backup directory. E.g. `papers git remote add origin *REMOTE URL*`;
`papers git lfs track files`; `papers git add files`; `papers git push`.
When git fails, it prints its own error message, and papers exits with
git's exit code.

Under the hood, every save commits a copy of the bibtex file to the backup
repository, with the files of `.papers/origin/` (origin copies of the
entries exchanged with the pool, one file per pool, see
[Pools](pools.md#origin-copies)) and
`.papers/distinct.json` (pairs that are not the same paper) when they exist.
`papers restore`, `undo` and `redo` restore the bibtex and these files
together (a file that the restored snapshot does not have is removed).
The library configuration (`.papers/config.json`) is not in the backup:
`papers restore`, `undo` and `redo` leave it as it is.
If `--git-lfs` is passed, the attached files are backed up along
with the bibtex: they are hard-linked into the backup directory and tracked
with git-lfs, together with a copy of the bibtex whose file paths point into
the backup (so the backup is self-contained). Background in
[issue 51](https://github.com/perrette/papers/issues/51).
Since the copy in the backup directory is a hard link, a file edited in
place in the library is also edited there until the next save commits it.
`papers restore`, `undo` and `redo` first reset the backup directory to the
committed snapshot, so they restore the committed version of the files (git
writes a new file, and the library file is left as it is).

Backup occurs in a subfolder of `~/.local/share/papers/backups`, whatever the
location of the library. Type `papers status -v` to find out, or
`papers backup list` to see every backup directory papers knows of and which
library each belongs to. Orphaned directories (e.g. whose library was
deleted) can be cleaned up with `papers backup remove NAME` (glob patterns
allowed; asks before deleting unless `-y/--yes` is passed; `-f/--force` is the
deprecated form).

Backup directories are named after the bibtex file and its parent folder,
plus a hash of the full path (e.g. `myproject-references-3f9a1c2b`), so two
libraries can never share a directory and same-named libraries remain
recognizable. The library configuration stores the name of its backup
directory, which each machine looks up in its own backup folder; only a
backup directory outside that folder is stored as an absolute path.
Each directory also contains a `manifest.json` recording the bibtex file it
backs up; if a backup operation finds a directory that belongs to another
library (which could happen with directories created by papers versions that
used the bibtex name alone), it moves the current library to a fresh
directory instead of mixing the two histories. Directories created by older
versions keep their name and are adopted as-is.

The libraries of papers 2.2 to 2.4 kept their backup in `.papers/` next to
the bibtex, the folder of `config.json`, `origin/` and `distinct.json`
since papers 3:
the first backup moves that repository (its history and the files it
tracks) to a new subfolder of the backup folder, with a warning, and the
library configuration records it. A backup commit that fails (e.g. refused
by a git hook) is a warning; the bibliography is saved anyway.

For libraries that are already in a git repository, the feature remains useful as
it is the basis for `papers undo` and `papers redo` (see
[Undo and redo](undo-redo.md)).
