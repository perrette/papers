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

`--tag` matches whole tags, whatever their case: `--tag ice` does not find
`ice-review`, `--tag 'ice*'` does. With several tags, an entry needs all of
them (`--any`: one of them).

A tag with `/` is under another tag: `climate/amoc` is under `climate`.
`--tag climate` also finds `climate/amoc` and `climate/amoc/tipping` (not
`climate-review`), `--tag climate/amoc` finds that tag and the ones under it.
`papers tag --rename climate ocean` also renames `climate/amoc` to
`ocean/amoc`. `papers tag` shows the nested tags indented under their
parent, which counts the entries that have it or a tag under it:

```
$> papers tag
climate (5)
  amoc (3)
    tipping (1)
  arctic (1)
to-read (2)
```

`papers list ... --add-tag TAG...` adds tags to the listed entries.

## Output formats

`papers list` supports a number of special flags such as `--duplicates`,
`--review-required`, `--broken-file`. `--format` chooses the output:

- `--format line` (the default): one line per entry (also `-l`, `-1`,
  `--one-liner`);
- `--format bibtex`: the entries as bibtex (also `--plain`);
- `--format ris`, `--format csl-json`, `--format bibjson`: the entries as
  RIS, CSL-JSON or BibJSON, with the file links as absolute paths (RIS
  needs the rispy package; see
  [Export](export.md#other-formats-ris-csl-json-and-bibjson) for the
  conversion). BibJSON keeps the bibtex fields as they are: it is the
  format for programs that read the library;
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
  biblatex `ids` field (comma-separated); the key of an entry names that
  entry even if it is also a former key of another entry;
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

## Editing without an editor

`papers edit KEY --from FILE` replaces the entry by the entry in FILE,
without opening an editor (for scripts and other programs). The entry keeps
its key, and its `file` and `keywords` fields when FILE has none; its other
fields are those of FILE (a field that FILE does not have is removed). FILE
is bibtex, or RIS (`.ris`), CSL-JSON (`.json`) or BibJSON (`.bib.json`),
or the format given with `--format`. `--from -` reads the entry from the standard input:

```
papers extract paper.pdf | papers edit perrette2013 --from -
papers fetch 10.5194/esd-4-11-2013 | papers edit perrette2013 --from -
```

In a terminal, `papers edit KEY --from -` waits for the entry: paste it, and
papers continues when the closing brace of the entry is read (Ctrl-D ends
the input too, Ctrl-C cancels).

`--set` and `--unset` change single fields, of one entry or several:

```
papers edit perrette2013 --set journal="Earth System Dynamics" year=2013
papers list --journal "Earth Syst. Dyn." -K | papers edit - --set journal="Earth System Dynamics"
papers edit smith2020 --unset note
```

The value replaces the whole field, written as in bibtex
(`--set author="Smith, John and Doe, Jane"`). The key and the file links
are not changed this way: `--key` (below) changes the key, and
`papers file attach` and `detach` the file links. `papers tag` adds and
removes single tags of the `keywords` field.

`--key NEW` changes the key of one entry:

```
papers edit perrette_landerer2013 --key perrette2013 [--keep-old-key]
```

The `crossref` fields of other entries that name the old key, and the
records of the exchanges with pools (see [Pools](pools.md)), follow the new
key; LaTeX documents that cite the old key do not. With `--keep-old-key`,
the old key goes to the `ids` field of the entry: papers (e.g.
`papers edit OLD`) and biblatex still find the entry by it. A key that
another entry has is refused. `papers check --fix-key` changes keys the
same way.

An edit that does not parse, has a malformed field name, or gives the entry
the key of another entry is not applied, and the command exits with status
1, with `--from`, `--set` and `--key` as with the editor.

## Output for programs

`--porcelain` (after git's option of that name) makes the output of a command
stable for programs: the standard output has only the entries that the
command added, modified, renamed or removed, or found already in the library
(`papers add` of an entry that is there), one per line, without colours:

```
$ papers add paper.pdf --porcelain
added perrette2013
$ papers tag perrette2013 smith2020 --add to-read --porcelain
modified perrette2013
modified smith2020
```

The lines are `added KEY`, `modified KEY`, `renamed OLD NEW`, `removed KEY`
and `existing KEY`. `renamed OLD NEW` is an entry whose key the command
changed (`papers edit OLD --key NEW`, `papers check --fix-key`). An entry
replaced in the editor with another key is `removed OLD` and `added NEW`,
and an entry merged into another one is `removed` (a program that follows an
entry across these can match it by DOI). Every other message
(questions, warnings, the files moved) goes to the standard error. An error
exits with status 1.

## Actions on the listed entries

`papers list` can run a command on the entries it lists: list the entries,
then act on them. Each action calls the same code as the command it stands
for, with the listed entries as KEY...:

| action | command | example |
|---|---|---|
| `-e/--edit` | `papers edit KEY...` | `papers list --duplicates --edit` |
| `--delete` (`--delete-files`, `--keep-files`) | `papers rm KEY...` (same options) | `papers list --tag draft --delete --keep-files` |
| `--add-tag TAG...` | `papers tag --add TAG... KEY...` | `papers list -a perrette --add-tag ocean` |
| `--rm-tag TAG...` | `papers tag --rm TAG... KEY...` | `papers list --tag to-read --rm-tag to-read` |
| `--rename` (`--keep-source`) | `papers file rename KEY...` (`--keep-source`) | `papers list smith 2020 --rename` |
| `--attach FILE...` | `papers file attach KEY FILE...` | `papers list --title "ice-edge blooms" --attach si.pdf` |
| `--detach [FILE...]` | `papers file detach [FILE...] --key KEY...` | `papers list --year 2010 --detach` |
| `--detach-broken` | `papers file detach --broken --key KEY...` | `papers list --broken-file --detach-broken` |
| `--fix-files [DIR...]` (`--pool PATH`, `--move`) | `papers file fix KEY... [--search DIR...]` (`--pool PATH`, `--move`) | `papers list --broken-file --fix-files ~/pdfs` |
| `-o/--open` | `papers open KEY...` | `papers list --tag to-read --open` |
| `--push` (`--pool PATH`, `--on-duplicate`) | `papers push KEY...` (same options) | `papers list --tag thesis --push` |
| `--pull` (`--pool PATH`, `--on-duplicate`) | `papers pull KEY...` (same options) | `papers list --tag thesis --pull` |
| `--sync` (`--pool PATH`, `--on-duplicate`) | `papers sync KEY...` (same options) | `papers list --tag thesis --sync` |
| `--export DIR` (`--export-format`, `--export-files`) | `papers export DIR KEY...` (`--format`, `--files`) | `papers list -a perrette --export out --export-format ris` |

Notes on the options:

- `--delete` asks, in a terminal, whether to delete the files of the
  entries too; `--delete-files` and `--keep-files` answer without asking
  (see [Files](files.md#removing-entries-and-their-files)).
- `--attach` needs exactly one listed entry: with none or several, it is an
  error and nothing changes. The files are moved, copied or linked as the
  `files` setting says.
- `--detach` without FILE removes all the links of the listed entries.
- The folders given to `--fix-files` are the `--search` folders of
  `papers file fix`: the broken links are also looked for there. `--move`
  moves the files found there instead of copying them.
- `--pool PATH` is the library to exchange with for `--push`, `--pull` and
  `--sync` (once), and a library to look for files in for `--fix-files`
  (can be repeated).
- `--export-format` and `--export-files` are the `--format` and `--files`
  options of `papers export` (`--format` of `papers list` is the format of
  its own output).
- `--detach` and `--fix-files` take any number of values: write them after
  the search words, or end their values with another option.
- An option of an action without the action (e.g. `--move` without
  `--fix-files`) is an error.

The action runs in the same process as the listing: papers can ask
questions and open the editor, and the library is saved once (one step of the history,
undone by one `papers undo`). One action at a time: two actions
in the same command are an error, and nothing changes.

(`papers check --duplicates` merges duplicates, see [Managing your
library](library-management.md#duplicates).) The other commands that act on
entries, e.g. `papers check`, read the keys of `papers list -K` with `-`
(see [Piping](#piping)).

These forms are deprecated, print a warning that shows the new form, and
will be removed in v4:

| Deprecated | New form |
|---|---|
| `papers list ... --copy` | `papers list ... --rename --keep-source` |
| `papers list ... --add-files FILE...` | `papers list ... --attach FILE...` |
| `papers list ... --fetch` | `papers list ... -K \| papers check --fetch --fetch-all --fix-doi --fix-key --format-name -` |

`--add-files` keeps its papers 2 behaviour: it links the files where they
are, or moves them with `--rename`, or copies them with `--copy`.
`--attach` follows the `files` setting.
