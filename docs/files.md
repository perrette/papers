# Files

An entry links to its files (the PDF, supplementary material...) in its
`file` field. The files usually live in the files directory of the library
(the `filesdir` setting), named after the name template (see
[Renaming files and keys](renaming.md)), but an entry can link to a file
anywhere.

## What `add` does with a file

The `files` setting says what `papers add` does with the PDF it adds, with
the files of the entries of an added bibtex (`papers add other.bib`), with
the files of an added folder (`papers add --recursive DIR`) and with the
files attached with `--attach`:

| `files` | the file is placed in the files directory | the original is removed |
|---|---|---|
| `move` (default) | yes, under its template name | yes |
| `copy` | yes, as a hard link when possible (same file system), otherwise a copy | no |
| `link` | no: the entry links to the file where it is | no |

Set it for a library with `papers config files copy`, or for all libraries
of the machine with `papers config --machine files copy`. The options
`--move`, `--copy` and `--link` of `papers add` override it for one command;
`-r/--rename` is the same as `--move`, and `-c` the same as `--copy`.

A file that belongs to another library, i.e. a file inside the files
directory of a library whose configuration (`.papersconfig.json`) is found
in the file's directory or above, is never moved: in `move` mode it is
copied instead (a hard link when possible), so that the other library keeps
its link. A file already in the files directory of the current library is
renamed in `copy` mode too, rather than copied next to itself. A file
downloaded by papers (a URL given to `add` or `--attach`) is always moved
into the files directory.

## `papers file`

The commands of `papers file` act on the files of the entries. Those that
take entries accept keys, DOIs, arXiv identifiers or ISBNs (see
[Naming entries](listing.md#naming-entries)), and `-` to read them from the
standard input, one per line:

| Command | Action |
|---|---|
| `papers file rename [KEY...]` | place the files of the entries (all without KEY) in the files directory, under their template name; `--keep-source` keeps the originals too (hard links when possible) |
| `papers file mv SRC... DEST` | move files or folders, and update the links of the entries (below) |
| `papers file attach KEY FILE...` | attach files to an existing entry, following the `files` setting (`--move`, `--copy`, `--link` override it); the files the entry already has are not touched |
| `papers file detach KEY [FILE...]` | remove links to files from the entry (all its links without FILE); `--broken [KEY...]` removes the broken links only, of all entries without KEY; `--delete-files` also deletes the detached files that no other entry links to |
| `papers file check [KEY...]` | report broken links, files linked twice, identical files (same checksum) of an entry, and with `--metadata` a DOI of the PDF that differs from the DOI of the entry (this parses the PDFs) |
| `papers file clean` | remove the files of the files directory and its subfolders that no entry links to, asking for each one (`-y/--yes` does not ask) |

`papers file check` changes nothing unless `--fix` is passed. `--fix` only
applies the repairs that cannot lose anything: paths saved by Mendeley
(missing leading `/`, latex symbols such as `{\_}`) are repaired when the
repaired path exists, and the second link to the same file, or to an
identical file, is removed from the entry (the file itself stays on disk;
`papers file clean` removes it). Broken links are reported, and removed
with `papers file detach --broken`.

`papers file clean` skips hidden files and folders (such as `.git`) and
`.bib` files. A folder of the layout of versions before 2.19 (with a hidden
`.<name>.bib`) is removed as a whole when no entry links to its files.

### Moving files

`papers file mv` works like `mv`, with the rules of `git mv`, and updates the
links of every entry that links to a moved file (links are compared by real
path, so a link through a symbolic link is found too):

1. a source file that no entry links to is an error;
2. a source folder must contain at least one linked file; the whole folder
   moves, files that no entry links to included;
3. with several sources, the destination must be an existing folder;
4. a destination that exists as a file is an error, unless `-f/--force`;
5. `-n/--dry-run` shows the moves and the links that change, and does
   nothing;
6. moving the files directory of the library (or a folder that contains it)
   also updates the `filesdir` setting.

All checks run before anything moves: if one fails, nothing is moved. If a
move fails midway (e.g. disk full), the bibtex is saved with the links of the
files already moved, and the error is reported. The parent folders of the
destination are created when needed. A folder that contains the bibtex or
the library configuration cannot be moved with `papers file mv`.

```
papers file mv files/2013 files/archive/2013
papers file mv files ~/Documents/library-files    # also sets filesdir
papers file mv -n files/a.pdf files/b.pdf files/new/
```

Links from other libraries to the moved files break: papers cannot know
about them.

## Removing entries and their files

`papers rm KEY...` (or `papers list ... --delete`) removes entries. Their
files that no remaining entry links to may be deleted too:

- in a terminal, papers lists those that are inside the files directory and
  asks once whether to delete them (default: no);
- `--delete-files` deletes them without asking, and also those outside the
  files directory; `--keep-files` keeps them without asking;
- without a terminal (e.g. the keys come from a pipe), the files are kept,
  and papers lists them: `papers file clean` deletes them later;
- a file outside the files directory is deleted only with `--delete-files`.

A file still linked from another entry is never deleted. A file that is a
hard link (e.g. to the file of another library) can be deleted: this only
removes this link, and papers says so.

## Deprecated forms

`papers filecheck` still works in v3, with a warning, and runs the
corresponding commands: `--rename` (`-c`) is `papers file rename`
(`--keep-source`), `--delete-broken` is `papers file detach --broken`,
`--hash-check` and `--fix-mendeley` are `papers file check --fix`,
`--metadata-check` is `papers file check --metadata`, and `--clean-filesdir`
(`--force`) is `papers file clean` (`--yes`). The file actions of
`papers list` are deprecated too (see [Listing and searching](listing.md)),
and so is `papers add --attachment` (now `--attach`).
