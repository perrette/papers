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

With `--invert`, `papers list` lists the entries that the same command
without `--invert` does not list.

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
`--review-required`, `--broken-file`. `--format` chooses the output:

- `--format line` (the default): one line per entry (also `-l`, `-1`,
  `--one-liner`);
- `--format bibtex`: the entries as bibtex (also `--plain`);
- `--format key`: the keys only, one per line (also `-K`, `--key-only`),
  to pipe into other commands (below).

`--field FIELD...` prints the key and the given fields of each entry
(`--no-key` leaves the key out). `-f` is a deprecated alias of `--field`: in
v4, `-f` is no longer `--field` (it means `--force` in other commands).

## Duplicates

`papers list --duplicates` lists the entries that are the same paper, by the
rule of `papers add` (see [Adding entries](adding-entries.md#same-paper)):
the groups that `papers check --duplicates` would merge or ask about, and
not the pairs recorded as distinct in `.papers/distinct.json`. With
`--invert`, it lists the other entries.

With `--fuzzy`, it also lists the entries whose authors and title are
similar (rapidfuzz token set ratio of at least `--fuzzy-ratio`, default 80).
This is for looking only: papers never merges entries on this score.

With `--by key`, `--by doi` or `--by title`, it lists instead the entries
that share that field: the same key (ignoring case), the same DOI, or the
same title (ignoring case and punctuation), whether or not they are the same
paper by the rule above (`--by` implies `--duplicates`).

`--duplicates-key`, `--duplicates-doi` and `--duplicates-tit` are deprecated
forms of `--duplicates --by key`, `--by doi` and `--by title`;
`--similarity` is deprecated and has no effect.

## Naming entries

The commands that act on entries take KEY arguments, where KEY is any of:

- the key of the entry (case-insensitive), or a former key listed in its
  biblatex `ids` field (comma-separated);
- a DOI: `10.1000/xyz`, also written `doi:10.1000/xyz` or
  `https://doi.org/10.1000/xyz` (case-insensitive);
- an arXiv identifier: `2101.01234`, `2101.01234v2`, `arXiv:2101.01234`, or
  of the old style `hep-th/9901001`; it matches the `eprint` field (when
  `archivePrefix` is arXiv or absent) and arXiv DOIs (`10.48550/arXiv.<id>`),
  whatever the version;
- an ISBN, 10 or 13 digits, with hyphens or spaces (the ISBN-10 and ISBN-13
  forms of a book are the same), matched against the `isbn` field.

A key cannot start with a digit, so an argument that starts with a digit is
never a key. An identifier that matches no entry, or several entries (e.g.
an ISBN shared by the chapters of a book), is an error, reported before
anything changes.

## Piping

`-` reads the identifiers from the standard input, one per line (blank lines
are ignored). `papers list -K` prints the keys of the listed entries, one per
line:

```
papers list smith 2020 -K | papers file rename -
papers list --tag to-read -K | papers open -
papers list --no-file -K | papers check --fetch -
papers list --review-required -K | papers edit -
```

These commands take `-`: `edit`, `rm`, `tag`, `open`, `check`, and the
`papers file` commands that act on entries (`rename`, `check`, and the
`--key` option of `detach` and `rm`).

## Actions on the listed entries

`papers list` can also act on the entries it lists, as shortcuts of other
commands:

- `-e/--edit`: edit them in a text editor, as `papers edit`;
- `--delete`: remove them, as `papers rm` (in a terminal, papers asks
  whether to delete their files too; `--delete-files` and `--keep-files`
  answer without asking, see [Files](files.md#removing-entries-and-their-files));
- `--add-tag TAG...`: add tags, as `papers tag --add`.

For instance, the duplicates can be edited by hand with (`papers check
--duplicates` merges them, see [Managing your library](library-management.md#duplicates)):

```
$> papers list --duplicates --edit
```

The file actions of `papers list` are deprecated, and print a warning that
shows the new form; they will be removed in v4:

| Deprecated | New form |
|---|---|
| `papers list ... --rename` (`--copy`) | `papers list ... -K \| papers file rename -` (`--keep-source`) |
| `papers list ... --add-files FILE...` | `papers file attach KEY FILE...` |
| `papers list ... -o/--open` | `papers list ... -K \| papers open -` |
| `papers list ... --fetch` | `papers list ... -K \| papers check --fetch --fetch-all --fix-doi --fix-key --format-name -` |
