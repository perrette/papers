# Git integration

## Setup git-tracked library (optional)

Install comes with the option to git-track any change to the bibtex file
(`--git`):

```
$> papers install --bibtex papers.bib --filesdir files --git  [ --git-lfs ]
```

From now on, every change to the library will result in an automatic git
commit. And the `papers git ...` command will work just as `git ...` executed
from the bibtex directory. E.g. `papers git add origin *REMOTE URL*`;
`papers git lfs track files`; `papers git add files`; `papers git push`.

If `--git-lfs` is passed, the files will be backed up along with the bibtex.
Under the hood, bibtex and files (if applicable) are copied (hard-linked) to a
back-up directory. Details are described in
[issue 51](https://github.com/perrette/papers/issues/51).

Backup occurs in a subfolder of `~/.local/.share/papers` regardless of the type
of installation. Type `papers status -v` to find out.

For local installs that are already git-tracked, the feature remains useful as
it is the basis for `papers undo` and `papers redo` (see
[Undo and redo](undo-redo.md)).
