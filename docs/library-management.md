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
default setting path (usually absolute, unless local install or unless you
specify otherwise).

In any case, the following set of commands will always work provided the
initial file links are valid (optional parameters in brackets):

```
touch new.bib
papers add /path/to/old.bib --bib new.bib [ --rename ] [ --relative-paths ] [ --filesdir newfilesdir ]
rm -f /path/to/old.bib
```

## check

It's easy to end up with duplicates in your bibtex. After adding PDFs, or every
once in a while, do:

```
papers check --duplicates
```

## filecheck

Check for broken links, rename files etc. Example:

```
papers filecheck --rename
```

The command can be used to move around the file directory:

```
papers filecheck --rename --filesdir newfilesdir
```

That command is also convenient to check what's actually tracked and what is
not. Example workflow:

```
papers filecheck --rename --filesdir tmp
# check what's left over in your initial files directory, e.g.
# papers extract files/leftover1.pdf
# papers add files/leftover1.pdf
# ...
papers filecheck --rename --filesdir files
```

There is also a command specifically designed to clean up zombie files and
folders:

```
papers filecheck --clean-filesdir
```

That command will ask before removing anything, unless `--force` is passed.
Currently it ignores hidden files and folders, and will only consider folders
that have a `.{folder}.bib` file inside, which is the convention `papers`
follows to store multiple attachments. That command works best when the files
are in their own folder, and not mixed up with other things, obviously.
