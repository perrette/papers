# Formats: RIS, CSL-JSON, BibJSON, export layout, machine-readable output

This file specifies:

- the bibliography formats other than bibtex (RIS, CSL-JSON, BibJSON):
  which commands read and write them, and how entries are converted in
  both directions;
- the layout that `papers export` writes;
- the machine-readable outputs: `--porcelain`, `papers list --format`,
  `-K`, `--field`, exit codes.

The bibtex format itself (parsing, writing, the `file` field syntax, the
LaTeX decoding of values) is in [bibtex.md](bibtex.md). Libraries,
configuration and file placement are in [library.md](library.md).

## Conventions

- **Contract** marks behaviour that both implementations must produce
  identically (byte for byte for files and standard output).
- **Free** marks behaviour an implementation may choose (wording of human
  messages, prompts, internal strategy).
- "Entry" is a bibtex entry: an entry type, a key, and an ordered list of
  fields (name, value). Values are the raw bibtex text, LaTeX included.
- Field names are compared in lower case unless stated otherwise.
- A value is "empty" when it is missing or the empty string. Empty values
  are never written, in any format, in either direction.

## 1. Formats and where they are used

| format id | label in messages | extension (read) | file written by export |
|---|---|---|---|
| `bibtex` | bibtex | `.bib`, and any other extension | `<name of the library's bibtex>` (usually `papers.bib`) |
| `ris` | RIS | `.ris` | `papers.ris` |
| `csl-json` | CSL-JSON | `.json` | `papers.json` |
| `bibjson` | BibJSON | `.bib.json` | `papers.bib.json` |

The format ids, file names and the order `bibtex, ris, csl-json, bibjson`
are **contract**.

### 1.1 Format of a file from its name

Used by `papers add FILE` and `papers edit --from FILE`.

1. If `--format FMT` is given, the format is `FMT`.
2. Else take the base name of the path, in lower case. Test the
   extensions longest first: `.bib.json` → `bibjson`, then `.json` →
   `csl-json`, `.ris` → `ris`, `.bib` → `bibtex`.
3. Else `bibtex`.

**Contract.**

### 1.2 Commands

| command | reads | writes |
|---|---|---|
| `papers add FILE...` | each FILE that is not a directory and whose name does not end in `.pdf` (case-insensitive): in the format of 1.1. `--format FMT` (one of `bibtex ris csl-json bibjson`) applies to all such files of the call. | — |
| `papers add DIR --recursive` | only `*.pdf` and `*.bib` files in DIR (not RIS, CSL-JSON or BibJSON) | — |
| `papers edit KEY --from FILE [--format FMT]` | FILE in the format of 1.1; `--from -` (standard input) is bibtex unless `--format` is given. Exactly one entry is accepted. | — |
| `papers list --format FMT` | — | the listed entries on standard output (section 6) |
| `papers export DIR --format F[,F...]` | — | files in DIR (section 9) |
| `papers list ... --export DIR --export-format F` | — | same as `papers export DIR KEY...` with the listed entries |

`papers edit --format` without `--from` is a usage error (exit 2):
`--format is the format of --from FILE`.

### 1.3 Text encoding

- Reading: the file is decoded as UTF-8; a leading byte-order mark is
  dropped. For RIS, `\r\n` is also replaced by `\n` before parsing (a lone
  `\r` is not). **Contract.**
- Writing: UTF-8, no byte-order mark, `\n` line ends. **Contract.**

### 1.4 RIS dependency (Python only)

The Python code reads and writes RIS with an optional package (the `ris`
extra). An implementation that has RIS built in does not need any of this
(**Free**). The Python behaviour, for reference:

- The package is loaded only when RIS is needed: `papers export` with
  `ris` among its formats, before anything is written; `papers add` when
  any of its files is RIS, before anything is added; `papers list
  --format ris`; `papers edit --from` with a RIS file.
- Not installed, no terminal on standard input: exit 1 with
  `papers: error: RIS needs the rispy package, which is not installed: install it with one of: `pip install rispy`, `pipx inject papers-cli rispy`, `pip install 'papers-cli[ris]'` (with uv: `uv tool install papers-cli --with rispy`)`.
- Not installed, in a terminal: a question on standard error
  `RIS needs the rispy package: install it now (`<python> -m pip install rispy`)? [y/N] `;
  `y` or `yes` runs pip (its output on standard error), anything else
  exits 1 (`rispy not installed: ...`).
- With `edit --from`, the error is reported as a rejected edit
  (`the text could not be read as ris (...) -- keeping original entries`).

## 2. Shared conversion rules

These rules are used by RIS and CSL-JSON (not by BibJSON, which keeps
values as they are). **Contract** unless stated.

### 2.1 Values as text (export)

Each field value is converted from LaTeX to unicode text, except the
fields `url`, `doi`, `file`, `eprint`, `isbn`, `issn`, which are taken as
they are.

- A value that contains none of the characters `\ { } $ ~ % &` is only
  trimmed of surrounding white space.
- Otherwise it is decoded as LaTeX text and trimmed. Observed rules of the
  current decoder:

| input | output |
|---|---|
| `G{\"o}ttingen`, `{\'e}t{\'e}`, `{\o}`, `\ss{}` | `Göttingen`, `été`, `ø`, `ß` |
| `{S}ea`, `\{x\}` | `Sea`, `{x}` |
| `\textit{Ice}`, `\emph{x}`, `\unknownmacro{z}` | `Ice`, `x`, `z` (macro dropped, argument kept) |
| `\&`, `\%` | `&`, `%` |
| `a~b` | `a` U+00A0 `b` |
| `$x^2$`, `$\alpha$` | unchanged (math kept verbatim, with the `$`) |
| `a -- b`, ` ``q'' ` | unchanged (no ligature conversion) |
| `\cite{x}` | `<cit.>` |
| `a\\b` | `a` newline `b` |
| newlines inside a value | kept |

The full decoding table is that of the decoder used by bibtex.md for
LaTeX-to-unicode conversion; see Open questions.

### 2.2 Names: bibtex to parts

An `author`, `editor` or `translator` value (raw, with LaTeX) is split
into names, then each name into parts. The parts are the CSL name keys:
`family`, `given`, `non-dropping-particle`, `suffix`, or `literal`.

Splitting into names: split on the regular expression `\s+and\s+`
(lower-case `and` only) at brace depth 0. Empty names are dropped.

One name (trimmed):

1. If the whole name is one braced group (`{World Health Organization}`):
   `{literal: <inside, decoded>}`.
2. Split on `,` at brace depth 0 into parts, each trimmed.
3. One part (no comma): split on white space at depth 0 into tokens.
   - One token: `{family: token}`.
   - A token is a *particle* when, after removing leading `{` and `\`
     characters, its first character is a lower-case letter.
   - Look at the tokens except the last. If some are particles, let `i` be
     the index of the first and `j` of the last: given = tokens before `i`,
     particle = tokens `i..j`, family = tokens after `j`. Otherwise given =
     all tokens but the last, family = the last.
4. Two or more parts: last = part 1; suffix = part 2 only if there are
   exactly 3 parts; given = the last part. Leading tokens of `last` that
   are particles go to the particle, as long as more than one token
   remains. family = the remaining tokens.
5. Tokens are joined with one space. Each part is decoded (2.1); parts
   that are empty are left out.

Examples:

| bibtex name | parts |
|---|---|
| `Perrette, M.` | `family: Perrette, given: M.` |
| `van der Berg, Jan` | `family: Berg, given: Jan, non-dropping-particle: van der` |
| `Ludwig van Beethoven` | `family: Beethoven, given: Ludwig, non-dropping-particle: van` |
| `Smith, Jr, John` | `family: Smith, given: John, suffix: Jr` |
| `{World Health Organization}` | `literal: World Health Organization` |
| `jean de la fontaine` | `family: fontaine, non-dropping-particle: jean de la` |
| `Doe, Jr, Jane, X` | `family: Doe, given: X` (parts 2 and 3 lost) |
| `A AND B` | `family: B, given: A AND` (one name) |

### 2.3 Names: parts to bibtex

A name given as a plain string is treated as `{literal: string}`.

- `literal` and no `family`: `{` + literal + `}`.
- Else family' = `non-dropping-particle` + space + `family` (or `family`
  alone); given' = `given` and `dropping-particle` joined by a space
  (empty ones left out).
- With `suffix`: `family', suffix, given'` (written even when given' is
  empty, giving a trailing `, `).
- Else `family', given'` when given' is not empty, else `family'`.

Names are joined with ` and `. Imported values are not converted from
unicode to LaTeX: `&`, `%`, `#` etc. are written as they are into the
bibtex (see Open questions).

### 2.4 Dates

**Date text** to numbers: match at the start (after white space)
`YYYY` then optionally `[-/]M{1,2}` then optionally `[-/]D{1,2}`. The
result is the list of the numbers found, without those equal to 0.
`2013`, `2013-05`, `2013/05/02/`, `2013-05-02T00:00` all work; `13-05`
gives nothing.

**Date of an entry** (export):

1. `year` trimmed and with braces stripped at both ends. If it is all
   digits: `[year]`, plus the month if the `month` field parses.
2. Else the numbers of the `date` field (biblatex), as date text.

Month parsing: the value trimmed, braces stripped, lower-cased. Digits
1–12 give that number; else if the first three letters are one of
`jan feb mar apr may jun jul aug sep oct nov dec`, its number; else none.

When `year` is all digits, the day of the `date` field is never used.

**Date to fields** (import): `year` = the first number as decimal text;
`month` = the second number as decimal text (`5`, not `may`). The day is
dropped.

### 2.5 Pages

- To bibtex: split on `--`, `-`, `–` (U+2013) or `—` (U+2014), with any
  white space around. If exactly two non-empty parts: `first--second`.
  Otherwise the value, trimmed, unchanged (`1-2-3` stays).
- First and last page of a bibtex value: the same split; first = part 1,
  last = part 2 (or empty).

### 2.6 DOI

A DOI is cleaned by trimming and removing, case-insensitively, a leading
`http://doi.org/`, `https://doi.org/`, `http(s)://dx.doi.org/` or `doi:`
followed by optional white space.

### 2.7 Keys of imported entries

An imported key is kept when, trimmed, it matches `^[A-Za-z][\w:.+\-]*$`
(`\w`: Unicode letters, digits, underscore) and is not `ITEM-<digits>`.
Otherwise the key is empty and `papers add` gives the entry a key from
the key template (library.md). Zotero item URLs and EndNote record numbers
are not kept. With `edit --from`, the entry keeps the key of the edited
entry whatever the file says.

### 2.8 File links of imported entries

The input is a list of strings, or a string split on `;`. Each item,
trimmed, empty ones skipped:

1. `file://...`: the path of the URL, percent-decoded (the host part is
   dropped).
2. Any other `scheme://...` (`http`, EndNote `internal-pdf`): left out,
   with the warning `file link left out (not a local file): <value>`.
3. Two or more `:` and not a drive path (`C:\` or `C:/`): the form
   `description:path:type`; the path is everything between the first and
   the last `:`.
4. Else the value is the path.

The paths become the `file` field of the entry. With `papers add`,
relative paths are relative to the directory of the imported file; they
are then written as the library writes file links (library.md). With
`papers edit --from`, the paths are stored as given and read relative to
the library's bibtex (see Open questions).

## 3. CSL-JSON

CSL-JSON is the item format of citeproc processors: a JSON array of item
objects.

### 3.1 Entry types

Export (bibtex → CSL), entry type in lower case:

| bibtex | CSL |
|---|---|
| `article` | `article-journal` |
| `book`, `proceedings` | `book` |
| `booklet` | `pamphlet` |
| `inbook`, `incollection` | `chapter` |
| `inproceedings`, `conference` | `paper-conference` |
| `phdthesis`, `mastersthesis`, `thesis` | `thesis` |
| `techreport`, `report`, `manual` | `report` |
| `misc` | `document`, or `article` when the entry has an `eprint` |
| `online`, `electronic`, `www` | `webpage` |
| `dataset` | `dataset` |
| `software` | `software` |
| `unpublished` | `manuscript` |
| `patent` | `patent` |
| any other | `document` |

Import (CSL → bibtex); a missing `type` is `document`:

| CSL | bibtex |
|---|---|
| `article-journal`, `article-magazine`, `article-newspaper` | `article` |
| `article` (preprint) | `misc` |
| `book` | `book` |
| `pamphlet` | `booklet` |
| `chapter`, `entry-encyclopedia`, `entry-dictionary` | `incollection` |
| `paper-conference` | `inproceedings` |
| `thesis` | `phdthesis`; `mastersthesis` when `genre` contains `master` (any case) |
| `report` | `techreport` |
| `webpage`, `post`, `post-weblog` | `online` |
| `dataset`, `software`, `patent` | same |
| `manuscript` | `unpublished` |
| `document` | `misc` |
| any other | `misc` |

### 3.2 Fields, export

Fields are taken as text (2.1). The item's keys are written in exactly
this order, each only when its value is not empty (**contract**: the key
order is part of the output):

| # | CSL key | value |
|---|---|---|
| 1 | `id` | entry key |
| 2 | `citation-key` | entry key |
| 3 | `type` | 3.1 |
| 4 | `author` | names of `author` (2.2), array of name objects |
| 5 | `editor` | names of `editor` |
| 6 | `translator` | names of `translator` |
| 7 | `title` | `title` |
| 8 | `volume` | `volume` |
| 9 | `DOI` | `doi`, cleaned (2.6) |
| 10 | `URL` | `url` |
| 11 | `ISBN` | `isbn` |
| 12 | `ISSN` | `issn` |
| 13 | `publisher` | `publisher` |
| 14 | `publisher-place` | `address` |
| 15 | `abstract` | `abstract` |
| 16 | `note` | `note` |
| 17 | `edition` | `edition` |
| 18 | `language` | `language` |
| 19 | `collection-title` | `series` |
| 20 | `PMID` | `pmid` |
| 21 | `PMCID` | `pmcid` |
| 22 | `container-title` | `journal`, else `booktitle` |
| 23 | `issue` or `number` | `issue`, else `number`. Key `issue` when the CSL type is `article-journal` or the entry has `issue`; else `number` |
| 24 | `page` | `pages` normalised (2.5), then `--` replaced by `-` |
| 25 | `publisher` | only when the entry has no `publisher`: `school`, else `institution`, else `organization`. This key comes here, after `page`, not at position 13 |
| 26 | `genre` | `PhD thesis` for `phdthesis`; `Master's thesis` for `mastersthesis`; else the `type` field when the CSL type is `thesis` or `report` |
| 27 | `keyword` | `keywords` split on `,`, each trimmed, empty ones dropped, joined with `, ` (a string, not an array) |
| 28 | `issued` | `{"date-parts": [[Y, M?, D?]]}` from the date of the entry (2.4); if none and `year` is not empty: `{"literal": "<year as text>"}` |
| 29 | `accessed` | `{"date-parts": [[...]]}` from `urldate` as date text, when it gives numbers |
| 30 | `custom` | `{"file": [path, ...]}` when the entry has file links (paths as given by the caller, sections 6 and 9) |

A name object has its keys in the order `family`, `given`,
`non-dropping-particle`, `suffix`, or only `literal`. Date numbers are
JSON integers. All other values are JSON strings.

All other bibtex fields are left out (e.g. `month` as such, `eprint`,
`urldate` when not a date, `crossref`, `ids`, `papers-*` fields).

### 3.3 Fields, import

| bibtex | from CSL |
|---|---|
| `author`, `editor`, `translator` | name arrays (2.3) |
| `title`, `volume`, `doi`, `url`, `isbn`, `issn`, `publisher`, `address`, `abstract`, `note`, `edition`, `language`, `series`, `pmid`, `pmcid` | the keys of 3.2 rows 7–21. A value that is an array gives its first element; numbers become their decimal text. `doi` is cleaned (2.6). |
| `journal` (types `article`, `misc`, `online`) or `booktitle` (other types) | `container-title` |
| `number` | `issue`, else `number` |
| `pages` | `page`, normalised (2.5) |
| `school` (phdthesis, mastersthesis) or `institution` (techreport) | `publisher` moves there; other types keep `publisher` |
| `type` | `genre`, for `techreport` only |
| `keywords` | `keyword` (array joined with `, ` first), split on `,` or `;`, trimmed, joined with `, ` |
| `year`, `month` | `issued` (2.4): `date-parts` (first array; its elements as integers), else `raw`, else `literal` as date text; a string value is read as date text |
| `urldate` | `accessed`, as its numbers zero-padded to 2 digits joined with `-` (`2020-03-04`) |
| `file` | the item's `file` key, then `custom.file` (2.8) |
| key | `citation-key`, else `id` (2.7) |

Everything else is ignored.

### 3.4 Document layout

Reading: the text must be JSON. An object is read as `{"items": [...]}`
when it has `items`, else as one item. The result must be an array of
objects. Errors: `not a CSL-JSON file: <JSON error>` and
`not a CSL-JSON file: a list of items is expected` (exit 1 from `add`;
the JSON error text is **free**).

Writing: a JSON array of items, see 8 for the JSON text format.

```
$ papers list rep2020 --format csl-json
[
  {
    "id": "rep2020",
    "citation-key": "rep2020",
    "type": "report",
    "author": [
      {
        "family": "Doe",
        "given": "Jane"
      }
    ],
    "title": "Report",
    "publisher-place": "Potsdam",
    "publisher": "PIK",
    "genre": "Working paper",
    "issued": {
      "date-parts": [
        [
          2020
        ]
      ]
    }
  }
]
```

### 3.5 What is lost

Export: LaTeX markup (decoded); `month` names (become numbers); the day
of a `date` when `year` is set; any field not in 3.2; the bibtex type
distinctions that share a CSL type (`inbook`/`incollection`,
`book`/`proceedings`, `techreport`/`report`/`manual`, ...).

A round trip export → import gives: `month = {5}` instead of `may`;
`journal`/`booktitle` chosen by type; `school`/`institution` only for
the types above (a `manual` or `report` with `organization` comes back
as `techreport` with `institution`); `issue` comes back as `number`.

## 4. RIS

RIS is a line format: one record per reference, one tag per line.

### 4.1 Line syntax

- A tag line: two characters, the first an ASCII letter, both upper case
  (`[A-Z][A-Z0-9]`), then exactly `  -` (two spaces, hyphen), then one
  separator character, then the value. The value is the line from
  character 7 on, trimmed. `ER  -` with nothing after it is a valid tag
  line.
- Any other line is a continuation line (value = the line, trimmed).

### 4.2 Reading

**Contract** (it determines which entries are imported):

1. Lines are separated by `\n`.
2. Skip lines until one that starts with `TY`; its value is the record
   type. This starts a record.
3. In a record, for each line:
   - tag line `ER`: the record is complete; go to 2.
   - other tag line: add the value to the tag (below), remember the tag.
   - continuation line: add its text to the last tag line seen before it
     (`ER` and `TY` lines do not count): for a list tag, as a new item; for
     a single tag, appended to the value with one space between. In the
     first record, a continuation line before any tag line is ignored. In
     a later record, the "last tag" is still the last tag of an earlier
     record: if it is a single tag the current record does not have, the
     read fails (see Open questions); if it is a list tag, the text
     becomes a value of that tag in the current record.
4. At the end of the text, a record without `ER` is dropped.
5. Unknown tags are ignored.
6. Single tags keep their first value; later values of the same tag are
   ignored. List tags collect every value: `A1 A2 A3 A4 AU KW N1 UR ED L1
   SN`. The value of `UR` is also split on `;` (each item trimmed).
7. If the text is not blank and no record was found: error
   `not a RIS file: no record found (a record starts with TY  - )`.

### 4.3 Writing

**Contract.** For each entry, a record:

```
TY  - <type>
<tag>  - <value>
...
ER  - 
```

Each line is `TAG` + two spaces + `-` + one space + value. The `ER`
line is `ER  - ` (with the trailing space). Records are separated by one
empty line. The text ends with `\n` after the last `ER  - `. No entries:
the empty text. A value that contains newlines is written as it is (the
next lines become continuation lines). Tags are written in this order,
each when its value is not empty:

| tag | value (fields as text, 2.1) |
|---|---|
| `TY` | type (4.4) |
| `ID` | entry key |
| `AU` | one line per author (name format below) |
| `ED` | one line per editor |
| `TI` | `title` |
| `T2` | `journal`, else `booktitle` |
| `T3` | `series` |
| `PY` | first number of the entry date (2.4); if no date and `year` is not empty: `year` as text |
| `DA` | only when the date has a month: `YYYY/MM/` or `YYYY/MM/DD/` (month and day zero-padded, trailing `/`) |
| `VL` | `volume` |
| `IS` | `issue`, else `number` |
| `SP` | first page (2.5) |
| `EP` | last page |
| `DO` | `doi`, cleaned |
| `UR` | `url` |
| `SN` | `isbn` then `issn`, one line each |
| `PB` | `publisher`, else `school`, else `institution`, else `organization` |
| `CY` | `address` |
| `AB` | `abstract` |
| `KW` | `keywords` split on `,`, trimmed, one line each |
| `N1` | `note` |
| `ET` | `edition` |
| `LA` | `language` |
| `M3` | `type`, for entry types `techreport`, `report`, `phdthesis`, `mastersthesis`, `thesis` |
| `L1` | one line per file link |

Name format: `literal` (no family) as it is; else `Family, Given` or
`Family, Given, Suffix`, where Family includes the particle
(`van der Berg, Jan`); `Family` alone when there is no given name and no
suffix.

Example (from `papers export DIR --format ris`):

```
TY  - JOUR
ID  - perrette2013
AU  - Perrette, M.
AU  - van der Berg, Jan
AU  - World Health Organization
AU  - Smith, John, Jr
TI  - A scaling approach to Sea level in Göttingen & $\alpha$ 50%  x
T2  - Earth System Dynamics
PY  - 2013
DA  - 2013/05/
VL  - 4
IS  - 1
SP  - 11
EP  - 29
DO  - 10.5194/esd-4-11-2013
UR  - https://esd.copernicus.org/x
SN  - 2190-4979
AB  - Sea level
 rise.
KW  - sea level
KW  - ice; amoc
N1  - A note
L1  - files/perrette_et_al_2013_a-scaling-approach.pdf
ER  - 

TY  - RPRT
ID  - rep2020
AU  - Doe, Jane
TI  - Report
PY  - 2020
PB  - PIK
CY  - Potsdam
M3  - Working paper
ER  - 
```

(`50%  x`: the space before `~` is kept and `~` is U+00A0.)

### 4.4 Entry types

Export:

| bibtex | RIS |
|---|---|
| `article` | `JOUR` |
| `book` | `BOOK` |
| `booklet` | `PAMP` |
| `inbook`, `incollection` | `CHAP` |
| `inproceedings`, `conference` | `CPAPER` |
| `proceedings` | `CONF` |
| `phdthesis`, `mastersthesis`, `thesis` | `THES` |
| `techreport`, `report`, `manual` | `RPRT` |
| `misc` | `GEN` |
| `online`, `electronic`, `www` | `ELEC` |
| `dataset` | `DATA` |
| `software` | `COMP` |
| `unpublished` | `UNPB` |
| `patent` | `PAT` |
| any other | `GEN` |

Import (type trimmed, upper-cased; missing is `GEN`):

| RIS | bibtex |
|---|---|
| `JOUR`, `JFULL`, `EJOUR`, `MGZN`, `NEWS`, `INPR` | `article` |
| `BOOK`, `EBOOK`, `EDBOOK` | `book` |
| `PAMP` | `booklet` |
| `CHAP`, `ECHAP`, `ENCYC`, `DICT` | `incollection` |
| `CPAPER`, `CONF` | `inproceedings` |
| `THES` | `phdthesis` |
| `RPRT`, `GOVDOC` | `techreport` |
| `GEN` | `misc` |
| `ELEC`, `BLOG` | `online` |
| `DATA`, `DBASE` | `dataset` |
| `COMP` | `software` |
| `UNPB`, `MANSCPT` | `unpublished` |
| `PAT` | `patent` |
| any other | `misc` |

### 4.5 Fields, import

"First of T1, T2" means: the first non-blank value, trimmed, looking at
the tags in that order (all values of a list tag).

| bibtex | from RIS |
|---|---|
| `author` | all `AU` then all `A1`, each converted (below), joined with ` and ` |
| `editor` | all `ED`; if none and the type is `CHAP ECHAP CPAPER CONF BOOK EDBOOK ENCYC DICT`: all `A2` |
| `title` | first of `TI`, `T1` |
| `journal` (types `article`, `misc`, `online`) or `booktitle` | first of `T2`, `JF`, `JO`, `JA`, `J2` |
| `series` | `T3` |
| `year`, `month` | date numbers (2.4) of the first of `PY`, `Y1`, `DA`; if `DA` (else `Y1`) gives a year and a month and its year equals that year, its numbers are used instead |
| `volume` | `VL` |
| `number` | `IS` |
| `pages` | `SP` and `EP` both set and different: `SP--EP`; else `SP` normalised (2.5); `EP` alone is dropped |
| `doi` | `DO`, cleaned |
| `url` | the first `UR` value that is not a DOI URL (2.6 prefixes). If there is none and `doi` is empty, `doi` = the first `UR` value, cleaned |
| `issn`, `isbn` | each `SN`: take its first white-space-separated word, keep only digits and `X`/`x`; 8 characters → `issn`, else `isbn`. The first value of each kind is kept, as written (trimmed) |
| `publisher`; `school` (phdthesis); `institution` (techreport) | first `PB` |
| `address` | `CY` |
| `abstract` | first of `AB`, `N2` |
| `keywords` | every `KW` value split on `;` or `,`, trimmed, joined with `, ` |
| `note` | all `N1`, trimmed, non-empty, joined with `; ` |
| `edition` | `ET` |
| `language` | `LA` |
| `type` | `M3`, for techreport and phdthesis only |
| `file` | all `L1` (2.8) |
| key | `ID` (2.7) |

RIS name to bibtex name:

- No comma: the name as it is when it has no space, else in braces (an
  organization): `John Smith` → `{John Smith}`.
- With commas: split on `,` (not brace-aware), trim. With 3 or more parts
  and a non-empty third: `p1, p3, p2` (bibtex `Last, Jr, First`). Else
  `p1, p2`, or `p1` when `p2` is empty.

### 4.6 What is lost

Export: LaTeX markup; `translator`; `urldate` (no tag is written);
`month` as a name (written as `DA` digits); `pmid`, `pmcid`, `eprint` and
any field not in 4.3; the day of a `date` when `year` is set.

Import: every tag not in 4.5 (`Y2`, `N2` when `AB` is present, `A3`,
`A4`, `L2`, `C1`–`C8`, ...); line breaks inside values; `mastersthesis`
(always `phdthesis`); a final record without `ER`.

A keyword with `;` exported as one `KW` line comes back as two keywords.

## 5. BibJSON

BibJSON (Open Knowledge Foundation convention) keeps the bibtex fields as
they are, LaTeX included.

### 5.1 Writing

A JSON object:

```
{
  "metadata": {
    "records": <number of records>
  },
  "records": [ <record>, ... ]
}
```

A record is built in this key order (**contract**):

1. `"type"`: the entry type as stored (case kept);
2. `"id"`: the key;
3. each field of the entry, in the order of the entry (for entries read
   from a library bibtex, the order of the file, which papers writes
   sorted, see bibtex.md), except a field named exactly `file`:
   - `author`, `editor` (exact lower-case names): an array of
     `{"name": <name>}`, the names split as in 2.2 (raw, braces kept);
   - `journal`: `{"name": <value>}`;
   - any other: the raw value as a string. A field whose name is `type`
     or `id` replaces the value of step 1 or 2 in place (see Open
     questions);
4. `"file"`: array of the file link paths, when there are any.

A month macro (`month = may`) is written as `"may"`, like a braced value.

### 5.2 Reading

The text must be JSON. An object with `records` gives that array; any
other object is one record. The result must be an array of objects.
Errors: `not a BibJSON file: <JSON error>`, `not a BibJSON file: a
collection {"records": [...]} or a list of records is expected`.

For each record:

- entry type: `type` as text, lower-cased; `misc` when missing or empty;
- key: `id`, else `cid` (2.7);
- skipped keys: names starting with `_`, and `type`, `id`, `cid`,
  `collection`, `file`, `identifier`, `link`, `license`;
- `author` or `editor` given as an array: each element as text (below),
  joined with ` and `;
- any other key: the value as text: an object gives the text of its
  `name` (empty if none); an array gives its elements as text joined with
  `, `; other values their JSON-to-string text (`2013` → `2013`, `true` →
  `True`, `null` → `None`, see Open questions);
- `doi`: when there is no `doi` key, the `id` of the first element of
  `identifier` whose `type` is `doi` (any case), cleaned;
- `file`: the `file` key (2.8).

### 5.3 What is lost

Nothing for ordinary fields. A bibtex field named `type`, `id`, `cid`,
`collection`, `identifier`, `link`, `license`, or starting with `_`, does
not survive a round trip. The distinction between a month macro and a
braced value is lost (`may` comes back as `{may}`).

## 6. `papers list` output

Options of the formatting group, mutually exclusive: `--format
line|bibtex|ris|csl-json|bibjson|key`, `--plain` (= `bibtex`), `-l`,
`-1`, `--one-liner` (= `line`), `-K`, `--key-only` (= `key`),
`--field FIELD...`. Plus `--no-key`. The deprecated `-f` is `--field`
with a warning. Entries are listed in the order of the library.

The output goes to standard output, except with `--porcelain` (section
7), where it goes to standard error.

| option | output | status |
|---|---|---|
| `--format key`, `-K` | the key of each entry, one per line, nothing else. No entry: no output | **contract** |
| `--field F1 F2...` | per entry: `KEY: v1 v2 ...`, the raw values joined by single spaces, a missing field as the empty string (`arx2021:  Preprint`). With `--no-key`, the line starts with a space (` 2013`). Colours (below) apply to `KEY:` | **contract** without colours |
| `--format bibtex` | the entries as the library writes them (bibtex.md), file links as stored (relative), then one `\n`. No entry: a single `\n` | **contract** |
| `--format ris` | 4.3; file links as absolute normalised paths (resolved against the library's bibtex directory, `.` and `..` removed, symlinks not resolved). No entry: empty | **contract** |
| `--format csl-json` | 3.4, same file paths. No entry: `[]\n` | **contract** |
| `--format bibjson` | 5.1, same file paths. No entry: `metadata.records` 0 and `"records": []` | **contract** |
| `--format line` (default) | below | human output; should match |

Line format: `KEY: TITLE INFO`

- `KEY:` the key and a colon; with `--no-key`, empty (the line starts
  with a space);
- `TITLE`: the first 60 characters of the raw title, then `...` if it is
  longer;
- `INFO`: `(` + items joined with `, ` + `)`, or empty (the line then
  ends with a space). Items, in order: `doi:<doi>`; `file:1` or
  `files:<n>`; the keywords (split on `,`, trimmed) joined with ` | `.

```
arx2021: Preprint 
perrette2013: A scaling approach to {S}ea level in G{\"o}ttingen \& $\alph... (doi:10.5194/esd-4-11-2013, file:1, sea level | ice; amoc)
```

Colours (`--color always`, or `auto` with a terminal and no `NO_COLOR`):
the key in blue (bold repeated once per file link), file count green,
keywords yellow, and terminal hyperlinks (OSC 8) on `doi:` and the file
count. Exact escape codes are **free**; without colours the text is as
above.

`papers status` has no machine-readable output (only `--no-check-files`
and `-v`); its text is human output (**free**).

`papers extract` and `papers fetch` print bibtex (or DOIs with `extract
--doi-only`) on standard output; see bibtex.md for the entry text.

## 7. `--porcelain`

`--porcelain` is an option of every command that takes the common
logging options (it comes after the command name: `papers tag X --add y
--porcelain`).

### 7.1 Streams

With `--porcelain`, for the whole command:

- everything the command would print on standard output goes to standard
  error instead (messages, listings, questions, `papers list` output,
  `papers export` messages);
- standard output receives only the porcelain lines (7.2). A command that
  does not produce porcelain lines writes nothing to standard output.

**Contract.**

### 7.2 Porcelain lines

The commands that print porcelain lines are those that report the entries
they changed:

| command | lines |
|---|---|
| `papers add` | `added`, `modified`, `existing`, `removed`, `renamed` |
| `papers check` (fixes, `--fix-key`...) | `modified`, `renamed`, `removed`, `added` |
| `papers edit` (editor, `--from`, `--set/--unset`, `--key`) | `modified`, `renamed`, ... |
| `papers rm` | `removed` |
| `papers tag` | `modified` |
| `papers file rename`, `papers file attach` | `modified` |
| `papers config pool PATH`, `none`, `--unset pool` | `modified` (relinked entries) |
| `papers list` with `--add-tag`, `--rm-tag`, `--attach`, `-e/--edit`, `--fetch`, `--rename`, `--delete` | as the command each stands for |

Other commands (`list` without those actions, `pull`, `push`, `sync`,
`export`, `file detach/mv/rm/check/fix/clean/checksum`, `undo`, `redo`,
`status`, `config` other than pool, ...) print no porcelain lines.

Line formats (**contract**), one per line, `\n`-terminated:

```
removed KEY
renamed OLD NEW
added KEY
modified KEY
existing KEY
```

Algorithm, comparing the entries as loaded at the start of the command
(before) with the entries after it:

1. `renamed`: the key changes recorded by the command (old key → new key,
   e.g. `edit --key`, `check --fix-key`).
2. `removed`: keys before, not after, and not an old key of a rename.
3. `added`: keys after, not before, and not a new key of a rename.
4. For the entries the command considered (the touched entries) whose key
   is both before and after: `modified` if their content differs, else
   `existing` — `existing` only for `papers add`. Content equality: the
   same set of field names with the same values, field order ignored.
5. Output order: all `removed` sorted by key; all `renamed` sorted by
   new key; all `added` sorted by key; then the step 4 lines sorted by
   key. Sorting is by Unicode code points, case-sensitive. Keys are
   compared exactly (case-sensitive).

Without `--porcelain`, the same diff is printed for humans as `Removed ->
...`, `Renamed -> ... (was OLD)`, `Added -> ...`, `Modified -> ...`,
`Existing -> ...` lines in the line format of section 6, followed by
notes and file moves (**free**).

Example:

```
$ papers tag rep2020 th2019 --add x --porcelain
modified rep2020
modified th2019
$ papers edit rep2020 --key rep2020b --porcelain
renamed rep2020 rep2020b
$ papers add refs.bib --on-duplicate keep --porcelain 2>/dev/null
existing arx2021
existing perrette2013
```

### 7.3 Exit codes and standard error

| situation | exit code |
|---|---|
| success | 0 |
| an error papers reports (`papers: error: <message>` on standard error) | 1 |
| a question with closed standard input | 1 |
| the output closed early (`papers list | head`) | 1 |
| Ctrl-C | 130 |
| command-line usage error (`papers <cmd>: error: ...` with usage, on standard error) | 2 |

Exit codes are **contract**. Warnings and errors on standard error have
the form `papers: <level>: <message>` (`warning`, `error`); the message
texts are **free**.

## 8. JSON text format

For CSL-JSON and BibJSON (**contract**, so that files compare byte for
byte):

- two-space indentation, every array element and object member on its
  own line, `": "` between key and value, `,` at the end of the line
  between elements, no trailing white space;
- empty array `[]`, empty object `{}`;
- strings: non-ASCII characters written as UTF-8 (not escaped); escapes
  `\"`, `\\`, `\n`, `\r`, `\t`, `\b`, `\f`, and `\u00XX` (lower-case hex)
  for the other characters below U+0020; `/` is not escaped;
- the document ends with `\n`.

## 9. `papers export` layout

```
papers export DIR [KEY...|-] [--files copy|link|none] [--format F[,F...]]
```

Brief; library.md covers libraries.

- DIR must not exist or be an empty directory, else exit 1
  `DIR: exists and is not an empty directory`. `--dry-run` is refused
  (exit 1, `export does not support --dry-run`).
- `--format` values: comma-separated, case-insensitive, trimmed; the
  option can be repeated. Names: `bib`, `bibtex`, `ris`, `csl-json`,
  `json` (= csl-json), `bibjson`, `bib.json` (= bibjson), `all`. An
  unknown name is a usage error (exit 2). Duplicates are removed and the
  formats are written in the order bibtex, ris, csl-json, bibjson.
  Default: bibtex.
- Entries: all of the library, or those named.

With bibtex among the formats, DIR becomes a self-contained library:

```
DIR/
  .papers/config.json     bibtex, filesdir "files", pool "none", a new id (library.md)
  .papers/.gitignore
  <bibtex name>           same base name as the source library's bibtex, else papers.bib
  files/                  copies of the files (--files copy)
  papers.ris              with --format ris
  papers.json             with --format csl-json
  papers.bib.json         with --format bibjson
```

The name and key template settings that the source library sets itself
are copied into the new configuration. The records of pairs marked
distinct are copied too (`.papers/distinct.json`, bibtex.md section 9.4).

Without bibtex, DIR gets only the format files and `files/`; it is not a
library.

`--files`:

- `copy` (default): each linked file is copied into `DIR/files` (a hard
  link when possible), named with the name template (of the new library,
  or of the source library when DIR is not a library). The links point
  to the copies.
- `link`: no copy; the links point to the original files.
- `none`: the entries have no file links.

File link paths: in the bibtex, as the new library writes them (relative
to its directory by default); in RIS, CSL-JSON and BibJSON, relative to
DIR (with `link`, e.g. `../lib/files/x.pdf`). **Contract.**

Messages (standard output, or standard error with `--porcelain`):

```
create the library DIR                                   (only with bibtex)
exported N entries to DIR (papers.bib, papers.ris; files: copy)
DIR is not a papers library (no papers.bib): --format bib or all makes one   (only without bibtex)
```

DIR is the absolute path; N is the number of selected entries; the
names are those written, in order. The wording is **free**.

## Open questions

1. **BibJSON: a `type` or `id` field overwrites the entry type or key.**
   papers/formats.py:833–842. A `techreport` with `type = {Working paper}`
   is exported as `"type": "Working paper"`; read back it becomes the
   entry type `working paper`, written as `@working paper{...}`
   (invalid bibtex). Same for a field `id` and the key.
2. **BibJSON import writes `None`, `True`, `1.0` for JSON null, booleans,
   floats.** papers/formats.py:848–854, 865: the text of a value is the
   Python string of it; `"note": null` becomes `note = {None}`. Only the
   empty string and missing values are dropped (formats.py:351).
3. **Imported values are not escaped for LaTeX.** formats.py:350–354
   (CSL and RIS): unicode text with `&`, `%`, `#`, `_` goes into the bibtex
   as it is (`title = {... & ... 50% ...}`), which LaTeX rejects. Export
   decodes LaTeX, import does not encode it back.
4. **The LaTeX-to-unicode conversion is that of a third-party decoder.**
   formats.py:123–140. Its full table (which macros, how unknown macros,
   `\cite` → `<cit.>`, `~` → U+00A0 next to a kept space) is not specified
   here; bibtex.md may define a shared table. Byte-identical exports
   depend on it.
5. **RIS: a final record without `ER` is dropped silently.** Behaviour of
   the RIS reader used by formats.py:812; no warning, and the "no record
   found" error only triggers when no record at all was found.
6. **RIS: a continuation line right after `TY` reuses the last tag of the
   previous record.** Reader behaviour behind formats.py:812. With a single
   tag (`TI`) it fails with an internal error (`papers add` reports
   `papers: error: 'title'`); with a list tag (`KW`) the text is added as a
   keyword of the new record. Blank lines between `TY` and the first tag
   in a later record trigger it too.
7. **RIS: the DOI is lost when `UR` has both a DOI URL and another URL and
   there is no `DO`.** formats.py:766–770: the DOI URL is only used when
   no other URL exists.
8. **RIS: `urldate` and `translator` are not exported** (formats.py:654–716),
   although CSL exports both (`accessed`, `translator`). `Y2` (access
   date) is not read either.
9. **Keywords: export splits on `,` only, import splits on `,` and `;`.**
   formats.py:472, 538, 705, 783. `ice; amoc` exported as one keyword
   comes back as two.
10. **Date text drops zeros before assigning positions.** formats.py:267:
   `2013-00-05` gives year 2013, month 5 (the day becomes the month).
11. **Names with 4 or more comma parts lose the middle parts.**
    formats.py:206–208: `Doe, Jr, Jane, X` → family Doe, given X.
12. **`family, suffix, ` with an empty given name.** formats.py:240–241
    writes a trailing `, ` when a CSL name has a suffix and no given.
13. **CSL import: `container-title` becomes `booktitle` for `book`,
    `dataset`, `software`, `patent`, `unpublished`, ...**
    formats.py:521: only `article`, `misc`, `online` get `journal`.
14. **CSL export: `publisher` from school/institution/organization is
    placed after `page`, not at the `publisher` position.** formats.py:447–464.
    Harmless for JSON readers, but part of the byte-level contract.
15. **`edit --from FILE` (RIS/CSL/BibJSON) keeps relative file paths as
    given, relative to the library**, while `add FILE` resolves them
    against the directory of FILE. papers/cli/entry_cmds.py:425–444 versus
    papers/bib.py:573–577.
16. **`papers list --porcelain` sends the listing to standard error.**
    papers/utils.py:302–313 redirects all of standard output; `papers list
    -K --porcelain` prints the keys on standard error and nothing on
    standard output. The option help (parser.py:238) says the standard
    output has "only the entries that the command added, modified...",
    which is consistent but makes `--porcelain` unusable with `list`.
17. **Export message names `papers.bib` even when the library's bibtex has
    another name.** papers/cli/pool_cmds.py:277 uses the fixed name, while
    the bibtex written is named after the source library
    (papers/pools.py:1475).
18. **`papers add DIR --recursive` ignores `.ris`, `.json` and `.bib.json`
    files** (papers/bib.py:727–730), although the export help says
    `papers add DIR --recursive` adds an exported library back; an export
    without bibtex cannot be added back that way.
19. **RIS `mastersthesis` round trip**: export writes `THES`, import always
    gives `phdthesis` (formats.py:609); CSL keeps it through `genre`.
20. **`--field` output keeps colour codes on `KEY:`** when colours are on
    (papers/encoding.py:36–42), and prints a leading space with
    `--no-key`; not clearly meant as a machine format.
