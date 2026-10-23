# Export

## `papers export`

```
papers export DIR [KEY...|-] [--files copy|link|none] [--format FORMAT]
```

writes the entries (all without KEY) as a new library in `DIR`, which must
not exist or be empty, to hand over: its bibtex, its files directory, and
its configuration (a self-contained library, with the name and key
templates that the library sets). File links are relative to the new
bibtex. `--format` writes RIS or CSL-JSON as well, or instead (see
[Other formats](#other-formats-ris-and-csl-json)).

- `--files copy` (default) copies the files into `DIR/files` (hard links
  when possible), named with the name template;
- `--files link` links to the files where they are;
- `--files none` leaves the file links out.

```
$ papers export ~/export-test perrette_landerer2013
create the library ~/export-test
exported 1 entries to ~/export-test (papers.bib; files: copy)
$ ls ~/export-test ~/export-test/files
~/export-test:
files
papers.bib

~/export-test/files:
perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf
```

`papers add DIR --recursive` adds an exported library to another one, and
`papers config pool DIR` makes it the pool of the library (the export has
copies of its PDFs). `papers sync --pool DIR` exchanges entries with it
later (see [Exchanges with any library](pools.md#exchanges-with-any-library)).

## Other formats: RIS and CSL-JSON

```
papers export DIR [KEY...|-] --format bib|ris|csl-json|all
```

`--format` chooses the files of entries written in `DIR`, next to
`DIR/files`:

| format | file | |
|---|---|---|
| `bib` (default) | `papers.bib` | bibtex; `DIR` is a papers library, as above |
| `ris` | `papers.ris` | RIS, read by Zotero, EndNote, Mendeley...; needs the [rispy](https://pypi.org/project/rispy/) package (see [Installation](installation.md#optional-ris-support)) |
| `csl-json` | `papers.json` | CSL-JSON, read by Zotero, pandoc and citeproc processors |
| `all` | the three files | |

Repeat the option or separate the formats with commas
(`--format bib,ris`). The file links of each file point to the copies in
`DIR/files`, relative to `DIR` (with `--files link`, to the files where
they are). Without `bib`, `DIR` is not a papers library (it has no
`.papers/config.json`), and papers says so:

```
$ papers export ~/export-test --format all
create the library ~/export-test
exported 1 entries to ~/export-test (papers.bib, papers.ris, papers.json; files: copy)
$ papers export ~/for-zotero --format ris
exported 1 entries to ~/for-zotero (papers.ris; files: copy)
~/for-zotero is not a papers library (no papers.bib): --format bib or all makes one
$ cat ~/for-zotero/papers.ris
TY  - JOUR
ID  - perrette_landerer2013
AU  - Perrette, M.
AU  - Landerer, F.
AU  - Riva, R.
AU  - Frieler, K.
AU  - Meinshausen, M.
TI  - A scaling approach to project regional sea level rise and its uncertainties
T2  - Earth System Dynamics
PY  - 2013
VL  - 4
IS  - 1
SP  - 11
EP  - 29
DO  - 10.5194/esd-4-11-2013
L1  - files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf
ER  - 
```

`papers list --format ris` and `--format csl-json` write the entries to the
standard output instead, without copying files (see
[Output formats](listing.md#output-formats)). `papers add refs.ris` and
`papers add refs.json` read these formats (see
[Add RIS and CSL-JSON files](adding-entries.md#add-ris-and-csl-json-files)).

### How the fields are converted

The values are written as unicode (LaTeX accents and commands are
converted, braces removed). Fields without an equivalent in the format are
left out.

| bibtex | CSL-JSON | RIS |
|---|---|---|
| key | `id`, `citation-key` | `ID` |
| entry type | `type` (below) | `TY` (below) |
| `author`, `editor` | `author`, `editor` (`family`, `given`, `non-dropping-particle`, `suffix`; a name in braces is a `literal`) | `AU`, `ED` (`Family, Given, Suffix`) |
| `title` | `title` | `TI` |
| `journal`, `booktitle` | `container-title` | `T2` |
| `series` | `collection-title` | `T3` |
| `year`, `month` | `issued` (`date-parts`) | `PY`, `DA` |
| `volume` | `volume` | `VL` |
| `number`, `issue` | `issue` (articles), else `number` | `IS` |
| `pages` | `page` (`11-29`) | `SP`, `EP` |
| `doi`, `url` | `DOI`, `URL` | `DO`, `UR` |
| `isbn`, `issn` | `ISBN`, `ISSN` | `SN` |
| `publisher` (or `school`, `institution`) | `publisher` | `PB` |
| `address` | `publisher-place` | `CY` |
| `abstract`, `keywords`, `note` | `abstract`, `keyword`, `note` | `AB`, `KW`, `N1` |
| `edition`, `language` | `edition`, `language` | `ET`, `LA` |
| `file` | `custom.file` (a list) | `L1` (one line per file) |

CSL-JSON has no field for files: the links are written in its `custom`
object, `"custom": {"file": [...]}`, which other programs ignore.

| bibtex | CSL-JSON | RIS |
|---|---|---|
| `article` | `article-journal` | `JOUR` |
| `book` | `book` | `BOOK` |
| `inbook`, `incollection` | `chapter` | `CHAP` |
| `inproceedings`, `conference` | `paper-conference` | `CPAPER` |
| `proceedings` | `book` | `CONF` |
| `phdthesis`, `mastersthesis` | `thesis` | `THES` |
| `techreport` | `report` | `RPRT` |
| `misc` | `document` | `GEN` |
| `online` | `webpage` | `ELEC` |
| `dataset`, `software` | `dataset`, `software` | `DATA`, `COMP` |
| `unpublished` | `manuscript` | `UNPB` |
