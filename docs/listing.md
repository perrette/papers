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

Tags are the `keywords` field of the entries (comma-separated). `papers tag`
lists them with the number of entries, adds and removes them:

```
$> papers tag perrette2013 --add sea-level projections
$> papers tag
sea-level (12)
projections (3)
$> papers tag perrette2013 --rm projections
$> papers tag --rename sea-level sea-level-rise     # in the whole library
$> papers list --tag sea-level projections
Perrette2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1, sea-level | projections )
```

`papers list ... --add-tag TAG...` adds tags to the listed entries.

## Output formats

`papers list` supports a number of special flags such as `--duplicates`,
`--review-required`, `--broken-file`. You can then output the result in a
number of formats: one-liner (`-l`), raw bibtex (`--plain`), keys only
(`-K/--key-only`), selected fields (`-f/--field`).

## Piping

The commands that act on entries take keys or DOIs (a DOI starts with `10.`),
and `-` reads them from the standard input, one per line. `papers list -K`
prints the keys of the listed entries, one per line:

```
papers list smith 2020 -K | papers file rename -
papers list --tag to-read -K | papers open -
papers list --no-file -K | papers check --fetch -
papers list --review-required -K | papers edit -
```

An unknown key or DOI is an error, reported before anything changes. These
commands take `-`: `edit`, `rm`, `tag`, `open`, `check`, and the
`papers file` commands that act on entries (`rename`, `detach`, `check`).

## Actions on the listed entries

`papers list` can also act on the entries it lists, as shortcuts of other
commands:

- `-e/--edit`: edit them in a text editor, as `papers edit`;
- `--delete`: remove them, as `papers rm` (in a terminal, papers asks
  whether to delete their files too; `--delete-files` and `--keep-files`
  answer without asking, see [Files](files.md#removing-entries-and-their-files));
- `--add-tag TAG...`: add tags, as `papers tag --add`.

For instance, it is possible to manually merge duplicates with:

```
$> papers list --duplicates --edit
```

The file actions of `papers list` are deprecated, and print a warning that
shows the new form; they will be removed in v4:

| Deprecated | New form |
|---|---|
| `papers list ... --rename` (`--copy`) | `papers list ... -K | papers file rename -` (`--keep-source`) |
| `papers list ... --add-files FILE...` | `papers file attach KEY FILE...` |
| `papers list ... -o/--open` | `papers list ... -K | papers open -` |
| `papers list ... --fetch` | `papers list ... -K | papers check --fetch -` |
