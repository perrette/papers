# Renaming files and keys

## Entries with several files

The first file of an entry (the PDF) is named after the name template, and
any other file (attachments, e.g. supplementary material added with `-a`) is
placed next to it, under the same name followed by `--` and the file's
original name:

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
renamed. Renaming (`papers filecheck --rename`, or `papers list ... --rename`)
moves the files out of the folder into the layout above, and removes the
folder if nothing but the hidden bibtex is left in it (a folder with other
files is kept, and the files left in it are reported).

## Control fields when renaming files

```
$> papers add --rename --info --name-template "{AuthorX}{year}-{Title}" --name-title-sep '' --name-author-sep '' esd-4-11-2013
INFO:papers:found doi:10.5194/esd-4-11-2013
INFO:papers:new entry: perrette2013scaling
INFO:papers:create directory: files/2013
INFO:papers:mv /home/perrette/playground/papers/esd-4-11-2013.pdf files/PerretteEtAl2013-AScalingApproachToProjectRegionalSeaLevelRiseAndItsUncertainties.pdf
INFO:papers:renamed file(s): 1
```

where `--name-template` is a python template (formatted via the `.format()`
method) with valid fields being any field available in the bibtex. Fields not
in the bibtex will remain untouched.

To rename `esd-4-11-2013.pdf` as `perrette_2013.pdf`, the template should be
`--name-template {author}_{year} --name-author-num 1`. If that happens to be
the entry ID, `ID` also works.

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
- `--name-title-length`: max title length
- `--name-title-word-size`: min size to be considered a word
- `--name-title-word-num`: max number of title words

and similarly:

- `--name-author-sep`: separator for authors
- `--name-author-num`: number of authors (not relevant for `{authorX}`)

The same template and modifiers system applies to the bibtex key generation by
replacing the prefix `--name-` with `--key-`, e.g. `--key-template`.

In the common case where the bibtex (`--bibtex`), files directory
(`--filesdir`), and name and key formats (e.g. `--name-template`) do not
change, it is convenient to [install](configuration.md) `papers`.
