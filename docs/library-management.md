# Managing your library

## Move library to a new location

Moving a library can be tricky. Simple cases are:

- files are stored in a central repository, and the bibtex contains absolute
  paths. Then moving the bibtex by hand is fine.
- files are stored alongside the bibtex, and the bibtex contains relative
  paths. Just move around the folder containing bibtex and files.

In any other cases, you risk breaking the file links.

Papers tries to be as little opinionated as possible about how files are
organized, and so it relies on your own judgement and use case. When loading a
bibtex, it always interprets relative file links as being relative to the
bibtex file. When saving a bibtex, it will save file links according to the
`paths` setting of the library (relative to the bibtex by default, see
[Configuration](configuration.md#relative-versus-absolute-paths)).

To move the files directory, or some of its files, use `papers file mv`: it
updates the links of the entries, and the `filesdir` setting when the files
directory itself moves (see [Files](files.md#moving-files)):

```
papers file mv files ../shared/files
```

The following set of commands also works, provided the initial file links are
valid (optional parameters in brackets):

```
touch new.bib
papers add /path/to/old.bib --bib new.bib [ --copy | --link ] [ --filesdir newfilesdir ]
rm -f /path/to/old.bib
```

By default the files of `old.bib` are moved into the files directory
(`--copy` keeps them in place too, `--link` links to them where they are),
except the files inside the files directory of another library, which are
copied.

## check

It's easy to end up with duplicates in your bibtex. After adding PDFs, or every
once in a while, do:

```
papers check --duplicates
```

## Checking and fixing files

`papers file check` reports broken links, files linked twice, identical
files and, with `--metadata`, DOIs of PDFs that differ from their entry's
DOI. It changes nothing unless `--fix` is passed, which applies the safe
repairs only. Broken links are removed with `papers file detach --broken`:

```
papers file check
papers file check --fix
papers file detach --broken
```

`papers file rename` places the files in the files directory under their
template name (see [Renaming files and keys](renaming.md)).

`papers file clean` removes the files of the files directory (and its
subfolders) that no entry links to:

```
papers file clean
```

It asks before removing anything, unless `-y/--yes` is passed. It ignores
hidden files and folders and `.bib` files; a folder with a `.{folder}.bib`
file inside, which is how versions before 2.19 stored entries with several
files (see
[Renaming files and keys](renaming.md#entries-with-several-files)), is removed
as a whole when no entry links to its files. That command works best when the
files are in their own folder, and not mixed up with other things, obviously.

`papers file clean --dry-run --yes` lists the files that no entry links to, without
removing them: a way to check what is actually tracked and what is not.

See [Files](files.md) for all the `papers file` commands. `papers filecheck`
is the deprecated form of these commands (it still works, with a warning).
