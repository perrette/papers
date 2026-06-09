# Listing and searching

`papers list` is a powerful command, inspired by unix's `find` and `grep`. It
lets you search your bibtex, output the result in a number of formats, or
perform actions on the matched entries.

## Basic listing

Pretty listing by default (otherwise pass `--plain` for plain bibtex):

```
$> papers list
Perrette2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1)
```

## Search with keywords

Search with any number of keywords:

```
$> papers list perrette scaling approach sea level
... (short list)
$> papers list perrette scaling approach sea level --any
... (long list)
$> papers list --key perrette2013 --author perrette --year 2013 --title scaling approach sea level
... (precise list)
```

## Tags

Add tags to view papers by topic:

```
$> papers list perrette2013 --add-tag sea-level projections
...
$> papers list --tag sea-level projections
Perrette2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1, sea-level | projections )
```

## Output formats and actions

`papers list` supports a number of special flags such as `--duplicates`,
`--review-required`, `--broken-file`. You can then output the result in a
number of formats (one-liner, raw bibtex, keys-only, selected fields) or
perform actions on it (currently `--edit`, `--delete`, `--add-tag`, `--fetch`,
`--rename`).

For instance, it is possible to manually merge duplicates with:

```
$> papers list --duplicates --edit
```
