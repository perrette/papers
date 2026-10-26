# Renaming files and keys

## Entries with several files

The first file of an entry (the PDF) is named after the name template, and
any other file (attachments, e.g. supplementary material added with
`--attach` or `papers file attach`) is placed next to it, under the same
name followed by `--` and the file's original name:

```
files/perrette_et_al_2013_a-scaling-approach.pdf
files/perrette_et_al_2013_a-scaling-approach--esd-4-11-2013-supplement.pdf
```

The label after `--` is kept when the entry is renamed again (e.g. after its
title or year was fixed), so only the part before `--` changes. If two
attachments have the same original name, the second one gets a `-2` suffix.

Versions before 2.19 placed the files of an entry with several files in a
folder named after the entry, with a hidden copy of the entry
(`files/<name>/.<name>.bib`). Such folders keep working as they are: their
files are linked from the bibtex, and nothing is moved until the entry is
renamed. Renaming (`papers file rename`) moves the files out of the folder
into the layout above, and removes the folder if nothing but the hidden
bibtex is left in it (a folder with other files is kept, and the files left
in it are reported).

## Renaming the files of existing entries

`papers add` places new files in the files directory under their template
name (unless the `files` setting is `link`, see [Files](files.md)). To rename
the files of entries already in the library, e.g. after changing the name
template or fixing an entry's title:

```
papers file rename                      # all entries
papers file rename perrette2013         # some entries
papers list --year 2013 --rename       # the listed entries
```

A file already in the files directory is renamed. A file outside it (e.g.
in a folder of your project) is moved, copied or left where it is as the
`files` setting says (moved by default, see
[Files](files.md#what-add-does-with-a-file)). `--move`, `--copy` and
`--link` override the setting; `--keep-source` is the same as `--copy` (a
hard link when possible). A file that belongs to another library is copied,
not moved. `papers list ... --rename` runs this command (with `--move` or
`--keep-source`); the deprecated `papers filecheck --rename` moves the
files, whatever the setting.

## Control fields when renaming files

```
$> papers add --move --info --name-template "{AuthorX}{year}-{Title}" --name-title-sep '' --name-author-sep '' esd-4-11-2013
INFO:papers:found doi:10.5194/esd-4-11-2013
INFO:papers:new entry: perrette2013scaling
INFO:papers:create directory: files/2013
INFO:papers:mv /home/perrette/playground/papers/esd-4-11-2013.pdf files/PerretteEtAl2013-AScalingApproachToProjectRegionalSeaLevelRiseAndItsUncertainties.pdf
INFO:papers:renamed file(s): 1
```

where `--name-template` is a python template (formatted via the `.format()`
method). Its placeholders are:

- `{author}`, `{Author}`, `{AUTHOR}`, `{authorX}`, `{AuthorX}`: the authors
  (see below)
- `{year}`, `{journal}`
- `{title}`, `{Title}`: the title words (see the modifiers below)
- `{key}` (or `{ID}`): the bibtex key of the entry
- `{doi}`, `{doi_}` (the doi with `-` in place of `/`, `.` and the other
  characters that are not letters or digits, for a file name),
  `{doi_or_id}` (the same, or the key if the entry has no doi)

Another placeholder is an error that lists these.

To rename `esd-4-11-2013.pdf` as `perrette_2013.pdf`, the template should be
`--name-template {author}_{year} --name-author-num 1`. If that happens to be
the entry key, `{key}` also works.

To rename `esd-4-11-2013.pdf` as
`2013/Perrette2013-AScalingApproachToProjectRegionalSeaLevelRiseAndItsUncertainties.pdf`,
name-template should be
`--name-template {year}/{Author}{year}-{Title} --name-title-sep ''`
(note the case).

## Case-sensitive fields

Entries are case-sensitive, and a few more fields are added, so that:

- `author` generates `perrette`
- `Author` generates `Perrette`
- `AUTHOR` generates `PERRETTE`
- `authorX` generates `perrette`, `perrette_and_landerer` or `perrette_et_al`
  depending on the number of authors
- `AuthorX` same as `authorX` but capitalized

## Modifiers

The modifiers are:

- `--name-title-sep`: separator for title words
- `--name-title-length`: max title length, with its separators: the last
  words are dropped until the title fits, and a first word longer than that
  is cut
- `--name-title-word-size`: min size to be considered a word
- `--name-title-word-num`: max number of title words

and similarly:

- `--name-author-sep`: separator for authors
- `--name-author-num`: number of authors (not relevant for `{authorX}`)

and for entries without author, year or title:

- `--name-unknown-template`: the template used instead (default:
  `unknown_{doi_or_id}` for file names, `{doi_}` for keys)
- `--name-unknown-strict`: use it only when author, year and title are all
  missing (by default, when any of them is missing); `--no-name-unknown-strict`
  turns off the `name.unknown-strict` setting for one command

The same template and modifiers system applies to the bibtex key generation by
replacing the prefix `--name-` with `--key-`, e.g. `--key-template`.

In the common case where the bibtex (`--bibtex`), files directory
(`--filesdir`), and name and key formats (e.g. `--name-template`) do not
change, it is convenient to store them in a [library configuration](configuration.md)
(`papers init`, `papers config name.template ...`).
