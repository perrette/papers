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
of the user with `papers config --global files copy`. The options
`--move`, `--copy` and `--link` of `papers add` override it for one command;
`-r/--rename` is the same as `--move`, and `-c` the same as `--copy`.

A file that belongs to another library, i.e. a file inside the files
directory of a library whose configuration (`.papers/config.json`) is found
in the file's directory or above, is never moved: in `move` mode it is
copied instead (a hard link when possible), so that the other library keeps
its link. The same holds for a file in the files directory of the pool of
the library, or of the library of `--pool PATH` (see [Pools](pools.md)). A file already in the files directory of the current library is
renamed in `copy` mode too, rather than copied next to itself. A file
downloaded by papers (a URL given to `add` or `--attach`) is always moved
into the files directory.

In a shallow library (a library with a pool), the file links are the pool
entry's; the library decides which entries it has. The files directory
where `add`, `file attach` and `file rename` place the files is that of the
pool, and the name template is the pool's: `move` and `copy` place the
file in the pool's files directory, and the library entry and the pool
entry link to it there; with `link`, the file stays where it is, and both
link to it there. This works on one machine; on another machine that uses
the pool, such links are broken (see
[Shallow libraries](shallow-libraries.md#files)).

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
| `papers file detach FILE... [--key KEY...]` | remove the links to the files from every entry that links to them (only from the entries of `--key` with `--key`); the files are kept (below) |
| `papers file detach --key KEY...` | remove all the links of the entries |
| `papers file detach --broken [--key KEY...]` | remove the broken links (of all entries without `--key`) |
| `papers file rm FILE... [-r] [--key KEY...]` | remove the links to the files, then delete the files, like `git rm` (below) |
| `papers file check [KEY...]` | report broken links and the files found for them (in the pool, in the libraries of `--pool PATH`, and in the folders of `--search DIR`), files linked twice, identical files (same checksum) of an entry, and with `--metadata` a DOI of the PDF that differs from the DOI of the entry (this parses the PDFs) |
| `papers file fix [KEY...]` | apply the repairs that `papers file check` reports (below); `--pool PATH` and `--search DIR` as for `check`; the files found are copied, never moved (`--move` moves those of `--search`) |
| `papers file clean` | remove the files of the files directory and its subfolders that no entry links to, asking for each one (`-y/--yes` does not ask) |

`papers file attach KEY FILE...` is the low-level form of
`papers add FILE --doi DOI` for an entry already in the library: when the
DOI is that of a library entry, `add` attaches the file to it in the same
way, without fetching anything (see
[Adding entries](adding-entries.md#entries-already-in-the-library)).

`papers file check` changes nothing, and ends with the number of links that
`papers file fix` can repair. `papers file fix` only applies the repairs
that cannot lose anything: paths saved by Mendeley
(missing leading `/`, latex symbols such as `{\_}`) are repaired when the
repaired path exists, the second link to the same file, or to an
identical file, is removed from the entry (the file itself stays on disk;
`papers file clean` removes it), and broken links are relinked to the files
found for them (see [Reconnecting PDFs and a bibtex](#reconnecting-pdfs-and-a-bibtex)).
The other broken links are reported, and removed with
`papers file detach --broken`.

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
4. a destination that exists as a file is an error, unless `-f/--force`
   (papers warns when entries link to the replaced file: their links then
   lead to the moved file);
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

### Detaching and removing files

A file can be linked from several entries: the chapters of a book that
share the PDF of the volume, two papers that share a supplement.
`papers file detach FILE...` removes the links to FILE from all of them and
prints which entries lost a link. Links are compared by real path, so a
broken link can be named too. The files stay on disk: `papers file detach`
never deletes a file.

`papers file rm FILE...` works like `git rm`: it removes the links to FILE
from every entry that links to it, then deletes the file.

- A FILE that no entry links to is an error, and nothing changes (with
  `--key`: that none of the entries of `--key` links to).
- `-r FOLDER` removes the linked files inside FOLDER (and its subfolders).
  Files that no entry links to stay where they are; the folders left empty
  are removed, FOLDER included, except the files directory of the library.
  Without `-r`, a folder is an error. `papers file detach -r FOLDER` removes
  the links in the same way, without deleting anything.
- With `--key`, only the links of those entries are removed; a file that
  another entry still links to is kept on disk, and papers says so.
- In a shallow library, the link is removed from the pool entry too, and
  the file (in the pool's files directory or elsewhere) is deleted unless
  another entry of the pool or of the library still links to it.
- papers does not ask: the file was named on the command line. `--dry-run`
  shows the links that would be removed and the files and folders that
  would be deleted.

`-k/--key` takes one or more entries (keys, DOIs, arXiv identifiers or
ISBNs), and can be repeated: `--key K1 K2` is `--key K1 --key K2`; `-`
reads them from the standard input. As it takes several values, write the
files before it: in `papers file rm --key K1 file.pdf`, `file.pdf` would be
read as an entry, and papers stops with the error `file.pdf is not an
entry: put the files before --key`.

```
papers file detach files/volume.pdf                    # from all the chapters
papers file detach files/volume.pdf --key smith2020    # from one chapter
papers file detach --key smith2020                     # all its links
papers file rm files/old-version.pdf
papers file rm -r files/2013 --dry-run
papers list --tag draft -K | papers file detach --broken --key -
```

## Reconnecting PDFs and a bibtex

When the links of a library are broken because the PDFs moved (another
library that shared the files directory moved them into a library, a folder
was renamed, a backup was restored elsewhere...), `papers file fix`
looks for each missing file, without parsing any PDF:

1. in the pool of the library, among the files of the pool entry of the
   same paper (same DOI, arXiv identifier, ISBN, or same title and
   authors): the file with the same file name as the broken link; else
   the one file named `<name>--<file name of the link>` (the pool renamed
   it as an attachment, see
   [Renaming files and keys](renaming.md#entries-with-several-files));
   then, if one broken link of the entry and one file of the pool entry
   are left, that file. When more are left, nothing is guessed;
2. in the libraries given with `--pool PATH` (the option can be repeated),
   in the same way: the entry of PATH of the same paper, and its files.
   PATH must be a library (otherwise: `create it first with papers init`).
   Nothing changes in PATH, and no origin copy is recorded (see
   [Origin copies](pools.md#origin-copies)): only the file links of the
   library change;
3. in the folders given with `--search DIR` (searched recursively; the
   option can be repeated): a file with the same file name as the broken
   link, else a file named as the library's name template names the entry
   (with the extension of the link). When several files match, none is
   taken, and papers says which.

The file found replaces the broken link. It is never moved, whatever the
`files` setting:

- in a self-contained library, it is copied (a hard link when possible)
  into the files directory, named as `papers file attach KEY FILE` names
  it;
- in a shallow library, a file of its pool is linked where it is; a file of
  `--pool PATH` or of a `--search` folder is copied into the files
  directory of the pool, and the pool entry links to it (as for the other
  changes of file links, see
  [Shallow libraries](shallow-libraries.md#files));
- in `link` mode, or in a library without files directory, the file is
  linked where it is.

`papers file fix --move` moves the files found in the `--search` folders
instead of copying them. A file in the files directory of another library
is still copied (`... belongs to the library in ...: copied, not moved`),
and so are the files of the pool and of `--pool PATH`.

`papers config pool PATH` links the library to the copies in PATH of the
files that exist, and says how many links were already broken:
`papers file fix` relinks them afterwards.

`papers file check` takes `--pool PATH` and `--search DIR` too, reports the
files that `papers file fix` would relink and where they come from, and
ends with the `papers file fix` command to run, with the same `-C DIR`,
`--bibtex FILE`, KEYs, `--pool` and `--search`. `papers file fix --dry-run`
shows the links that it would change, and changes nothing. After
`papers file fix`, the last line counts the issues left, if any.

```
$ papers file check --pool ~/P --search ~/Downloads
perrette2013scaling: broken link: ~/old/esd-4-11-2013.pdf -> ~/P/files/perrette_2013_a-scaling-approach.pdf (from the library ~/P)
perrette2011: broken link: ~/old/bg-8-515-2011.pdf -> ~/Downloads/bg-8-515-2011.pdf (found in ~/Downloads)
2 links can be relinked, 0 without a file found
2 issue(s) in the files of 2 entries
2 links can be repaired: `papers file fix --pool ~/P --search ~/Downloads`
$ papers file fix --pool ~/P --search ~/Downloads
perrette2013scaling: relinked to ~/thesis/files/perrette_2013_a-scaling-approach-to-project-regional-sea-level-rise.pdf (from the library ~/P)
perrette2011: relinked to ~/thesis/files/perrette_2011_near-ubiquity-of-ice-edge-blooms-in-the-arctic.pdf (found in ~/Downloads)
2 links relinked, 0 still broken
```

`papers file fix` works on any bibtex, without `papers init`: there is no
files directory, and the files found are linked where they are.

```
$ papers file fix --bibtex refs.bib --search ~/Downloads
perrette2011: relinked to ~/Downloads/bg-8-515-2011.pdf (found in ~/Downloads)
1 link relinked, 0 still broken
```

For PDFs whose names say nothing about the paper, `papers add -R DIR` is
the fallback: it parses each PDF, and a PDF with the DOI of a library
entry is attached to that entry, without new entry and without duplicate
dialogue (a PDF with the content of a file of the entry is not attached
again; see
[Adding entries](adding-entries.md#entries-already-in-the-library)). The
broken links stay next to the new ones: remove them with
`papers file detach --broken`.

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

A file still linked from another entry is never deleted, nor a file in the
files directory of the pool of the library, nor, in a shallow library, a
file that an entry of the pool links to (see
[Shallow libraries](shallow-libraries.md#files)); `papers rm` does not
change the pool. In a shallow library, `--delete-files` is an error and
nothing is removed: the files are the pool's, and `papers file rm FILE`
deletes them. A file that is a
hard link (e.g. to the file of another library) can be deleted: this only
removes this link, and papers says so.

## Deprecated forms

`papers filecheck` still works in v3, with a warning, and runs the
corresponding commands: `--rename` (`-c`) is `papers file rename`
(`--keep-source`), `--delete-broken` is `papers file detach --broken`,
`--hash-check` and `--fix-mendeley` are `papers file fix`,
`--metadata-check` is `papers file check --metadata`, and `--clean-filesdir`
(`--force`) is `papers file clean` (`--yes`). The file actions of
`papers list` are deprecated too (see [Listing and searching](listing.md)),
and so is `papers add --attachment` (now `--attach`; `-a FILE` attaches the file
until v4, with a warning: `-a` is `--author`, see [Adding entries](adding-entries.md#attach-files)).
