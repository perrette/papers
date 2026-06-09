# Renaming files and keys

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
