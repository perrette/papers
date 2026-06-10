# Git integration

## Setup git-tracked library (optional)

Install comes with the option to git-track any change to the bibtex file
(`--git`):

```
$> papers install --bibtex papers.bib --filesdir files --git  [ --git-lfs ]
```

From now on, every change to the library will result in an automatic git
commit. And the `papers git ...` command will work just as `git ...` executed
from the backup directory. E.g. `papers git remote add origin *REMOTE URL*`;
`papers git lfs track files`; `papers git add files`; `papers git push`.

If `--git-lfs` is passed, the files will be backed up along with the bibtex.
Under the hood, bibtex and files (if applicable) are copied (hard-linked) to a
back-up directory. Details are described in
[issue 51](https://github.com/perrette/papers/issues/51).

Backup occurs in a subfolder of `~/.local/share/papers/backups` regardless of
the type of installation. Type `papers status -v` to find out, or
`papers backup list` to see every backup directory papers knows of and which
library each belongs to.

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
