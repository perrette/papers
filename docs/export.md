# Export

## `papers export`

```
papers export DIR [KEY...|-] [--files copy|link|none] [--format FORMAT]
```

writes the entries (all without KEY) as a new library in `DIR`, which must
not exist or be empty, to hand over: its bibtex, its files directory, and
its configuration (a self-contained library, with the name and key
templates that the library sets). File links are relative to the new
bibtex. `--format` writes RIS, CSL-JSON or BibJSON as well, or instead (see
[Other formats](#other-formats-ris-csl-json-and-bibjson)).

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

`papers add DIR --recursive` adds an exported library to another one (its
bibtex and PDFs; the RIS and JSON files of a folder are left out: add one
with `papers add DIR/papers.ris`), and
`papers config pool DIR` makes it the pool of the library (the export has
copies of its PDFs). `papers sync --pool DIR` exchanges entries with it
later (see [Exchanges with any library](pools.md#exchanges-with-any-library)).

## Other formats: RIS, CSL-JSON and BibJSON

```
papers export DIR [KEY...|-] --format bib|ris|csl-json|bibjson|all
```

`--format` chooses the files of entries written in `DIR`, next to
`DIR/files`:

| format | file | |
|---|---|---|
| `bib` (default) | `papers.bib` | bibtex; `DIR` is a papers library, as above |
| `ris` | `papers.ris` | RIS, read by Zotero, EndNote, Mendeley...; needs the [rispy](https://pypi.org/project/rispy/) package (see [Installation](installation.md#optional-ris-support)) |
| `csl-json` | `papers.json` | CSL-JSON, read by Zotero, pandoc and citeproc processors |
| `bibjson` (or `bib.json`) | `papers.bib.json` | BibJSON: the bibtex fields as they are, in JSON, for programs (see [BibJSON](#bibjson)) |
| `all` | the four files | |

Repeat the option or separate the formats with commas
(`--format bib,ris`). The file links of each file point to the copies in
`DIR/files`, relative to `DIR` (with `--files link`, to the files where
they are). Without `bib`, `DIR` is not a papers library (it has no
`.papers/config.json`), and papers says so:

```
$ papers export ~/export-test --format all
create the library ~/export-test
exported 1 entries to ~/export-test (papers.bib, papers.ris, papers.json, papers.bib.json; files: copy)
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

`papers list --format ris`, `--format csl-json` and `--format bibjson`
write the entries to the standard output instead, without copying files
(see [Output formats](listing.md#output-formats)). `papers add refs.ris`,
`papers add refs.json` and `papers add refs.bib.json` read these formats
(see [Add RIS, CSL-JSON and BibJSON files](adding-entries.md#add-ris-csl-json-and-bibjson-files)).

### How the fields are converted

The values are written as unicode (LaTeX accents and commands are
converted, braces removed). Fields without an equivalent in the format are
left out.

| bibtex | CSL-JSON | RIS |
|---|---|---|
| key | `id`, `citation-key` | `ID` |
| entry type | `type` (below) | `TY` (below) |
| `author`, `editor`, `translator` | `author`, `editor`, `translator` (`family`, `given`, `non-dropping-particle`, `suffix`; a name in braces is a `literal`) | `AU`, `ED`, `A4` (`Family, Given, Suffix`) |
| `title` | `title` | `TI` |
| `journal`, `booktitle` | `container-title` | `T2` |
| `series` | `collection-title` | `T3` |
| `year`, `month` | `issued` (`date-parts`) | `PY`, `DA` |
| `volume` | `volume` | `VL` |
| `number`, `issue` | `issue` (articles), else `number` | `IS` |
| `pages` | `page` (`11-29`) | `SP`, `EP` |
| `doi`, `url` | `DOI`, `URL` | `DO`, `UR` |
| `urldate` | `accessed` | `Y2` |
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

### BibJSON

[BibJSON](https://github.com/rufuspollock-okfn/bibjson) is the convention of
the Open Knowledge Foundation for bibliographic records in JSON. RIS and
CSL-JSON convert the fields to those of other programs and lose some of
them; BibJSON keeps the bibtex fields as they are (LaTeX included), so that
a program can read the whole library:

```
$ papers list perrette --format bibjson
{
  "metadata": {
    "records": 1
  },
  "records": [
    {
      "type": "article",
      "id": "perrette_landerer2013",
      "author": [
        {
          "name": "Perrette, M."
        },
        ...
      ],
      "journal": {
        "name": "Earth System Dynamics"
      },
      "title": "A scaling approach to project regional sea level rise and its uncertainties",
      "year": "2013",
      "file": [
        "/home/me/papers/files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf"
      ]
    }
  ]
}
```

- `type` and `id` are the entry type and key;
- `author` and `editor` are lists of `{"name": ...}`, and `journal` is
  `{"name": ...}`, as BibJSON gives them;
- the other fields are strings, as in the bibtex;
- `file` is the list of the file links (absolute paths with `papers list`,
  relative to `DIR` with `papers export`);
- a bibtex field with the name of a BibJSON key (`type`, `id`, `cid`,
  `collection`, `identifier`, `link`, `license`), e.g. the `type` of a
  techreport (`type = {Working paper}`), is written as `bibtex:type`, and
  the collection's `metadata` declares the namespace
  (`"namespace": {"bibtex": ...}`), as BibJSON says for additional keys.
  papers reads it back as the bibtex field.

`papers add refs.bib.json` reads a collection (`{"records": [...]}`), a
list of records or one record. It also reads the DOI of BibJSON
identifiers (`"identifier": [{"type": "doi", "id": ...}]`), and joins the
lists of strings (e.g. keywords) with commas.
