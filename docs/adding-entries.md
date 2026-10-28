# Adding entries

The `papers add` command adds entries to your library, with or without a PDF
attachment.

## Add a PDF (extract metadata automatically)

```
$> papers add esd-4-11-2013.pdf --bibtex papers.bib --filesdir files -v
papers: info: found doi:10.5194/esd-4-11-2013
papers: info: new entry: perrette_landerer2013
papers: info: mv /home/perrette/playground/papers/esd-4-11-2013.pdf files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf
papers: info: renamed file(s): 1
```

That is equivalent to doing:

```
papers extract esd-4-11-2013.pdf > entry.bib
papers add entry.bib --attach esd-4-11-2013.pdf --bibtex papers.bib --filesdir files
```

### How the DOI is found

`papers add` looks for the DOI of a PDF in this order:

1. The PDF metadata: the `subject`, `keywords` and `title` fields of the
   document information, then the XMP tags `prism:doi`, `dc:identifier`
   (`doi:...`), `pdfx:doi` and `crossmark:DOI`. A DOI found there is used
   as is.
2. The text of the first pages: pages are read one at a time until there
   are 200 words (at most 10 pages). A DOI is `10.`, 4 to 9 digits, `/`,
   then letters, digits and `-._;()/:`, not glued to a preceding word
   (case is ignored). A DOI broken over two lines after `10.` or after a
   dash is joined, and trailing text such as `.pdf`, `supplement` or an
   unbalanced `)` is cut. If the PDF has more than one page, the DOIs of
   the last page that follow `doi:` or `doi.org/` are added after those of
   the first pages (some publishers append a cover page).
3. The candidates are ordered: a DOI written in a `doi.org` URL first, then
   the others in order of appearance; the DOIs of data repositories
   (Zenodo, Dryad, figshare, PANGAEA...) come last, and a supplement DOI
   (ending in `.s1`) after the DOI of the article. Each candidate is
   fetched (from crossref), and the first one whose title appears in the
   first pages (ignoring case, accents and punctuation) is used. This skips
   the DOIs of cited papers.
4. If the text has no DOI, an arXiv identifier written `arXiv:2101.01234`
   gives the DOI `10.48550/arXiv.2101.01234`, whose metadata come from
   arXiv and are checked as in step 3.

When no DOI is accepted, papers searches crossref with the first 200 words
of the text (`--scholar`: Google Scholar), and accepts the result only if
its title appears in the text. Otherwise the PDF is not added, and papers
stops with an error: pass the DOI with `--doi`, or describe the entry (see
[below](#add-a-whole-directory-of-pdfs)). `--no-query-doi` skips the DOI
search, and `--no-query-fulltext` the text search.

`papers extract --doi-only FILE` prints the DOI that steps 1 to 4 find,
without adding anything:

```
$ papers extract --doi-only bg-8-515-2011.pdf
10.5194/bg-8-515-2011
```

## What happens to the files

By default, `papers add` moves the PDF into the files directory of the
library, under a name made from the name template: in a shallow library
(a library with a pool), the files directory and the name template of its
pool (see [Shallow libraries](shallow-libraries.md#files)). The
`files` setting of the library changes what happens to the original (see
[Files](files.md#what-add-does-with-a-file)):

- `move` (default): place the file in the files directory and remove the
  original;
- `copy`: place it in the files directory and keep the original (a hard link
  when possible, otherwise a copy);
- `link`: leave it where it is; the entry links to it there;
- `ask`: ask for each file, `m` (move), `c` (copy) or `l` (link, also
  Enter); `M`, `C` or `L` answers for all the next files; without a
  terminal, the file is linked where it is.

`--move`, `--copy` and `--link` override the setting for one command
(`-r/--rename` is the same as `--move`, `-c` as `--copy`):

```
papers config files copy           # this library keeps the originals
papers add esd-4-11-2013.pdf --link
```

A file that belongs to another library (inside its files directory) is
never moved: it is copied instead, so that the other library keeps its link.

The same applies to the files linked from the entries of a bibtex file added
with `papers add other.bib`: their paths are read relative to that bibtex,
and when they are linked where they are (`link`), they are stored so that
they remain valid from your own bibtex (relative to it, or absolute,
according to the `paths` setting of the library).

See [Renaming files and keys](renaming.md) for how to specify file naming
patterns, and how the files of an entry with attachments are named.

## Attach files

`--attach FILE...` attaches other files to the added entry (e.g.
supplementary material), placed as the `files` setting says. They are named
after the main file (see
[Renaming files and keys](renaming.md#entries-with-several-files)). To
attach files to an entry already in the library, use
`papers file attach KEY FILE...`. `--attachment` is a deprecated name of
`--attach`.

`-a` is the short form of `--author` (as in `papers list`). In papers v2, `-a
FILE...` attached files: until v4, when every value given to `-a` is an
existing file (or a URL), papers attaches them as with `--attach` and warns.
Otherwise the first value is the author, and the next values are files to
add (`papers add -a "Smith, John" paper.pdf`); a first value that is an
existing file, followed by other values, is an error.

## Add a whole directory of PDFs

It is possible to do this on a full directory of files, recursively, with
`-R/--recursive`:

```
papers add -R /home/perette/playground/papers/papers_test
```

where, above, the `papers_test` directory contains a few PDF files. For each
PDF, `papers` will attempt to extract the metadata and add the relevant file to
the bibliography, and place the files as the `files` setting says (by
default, moved into the files directory).

Files named after a PDF of the same directory, as papers names
attachments (`<name>--<label>.<ext>` next to `<name>.pdf`, see
[Renaming files and keys](renaming.md#entries-with-several-files)), are added
as attachments of that PDF's entry, whatever their type, instead of being
scanned as papers of their own. Bibtex files found in the directory are added
too, before the PDFs, and the files they link to are not scanned: their entry
comes from the bibtex, so a folder that holds a bibtex and its files is added
without looking anything up online. Folders of the pre-2.19 layout (with a
hidden `.<name>.bib`) are read from their hidden bibtex.

The metadata of each PDF are found as for a single PDF (see
[How the DOI is found](#how-the-doi-is-found)). If none matches, the PDF is
not added: pass its DOI with `--doi` (see below),
or, for a reference without DOI (older papers, books, reports...), describe it
and attach the PDF:

```
papers add --title "Self-consistent equilibrium ocean tides" --author "Agnew, Duncan C. and Farrell, W. E." \
    --year 1978 --journal "Geophysical Journal International" --attach agnew1978.pdf
```

## Entries already in the library

When the DOI of the added paper is already in the library (given with
`--doi`, or found in the PDF metadata, or printed in the text of the PDF
with the title of the library entry), `papers add` uses that entry: nothing
is fetched online and there is no duplicate dialogue. The PDF (and the files
of `--attach`) are attached to the entry and placed as the `files` setting
says, as `papers file attach KEY FILE...` does; the key, the fields and the
other files of the entry are not touched. A file with the content of a file
of the entry is not attached again, and stays where it is. An arXiv DOI
(`10.48550/arXiv.<id>`) matches an entry whose `eprint` is that arXiv
identifier. `--no-check-duplicate` skips this, and adds a new entry.

The order is: the library, then the pool (below), then online.

## Entries already in the pool

Before querying crossref, `papers add` looks in the pool of the library
(see [Pools](pools.md#add-looks-in-the-pool-first)): a PDF with the same
content as a pool file, or whose DOI is in the pool, a DOI that a pool entry
has, or a bibtex entry that is the same paper as a pool entry, is taken from
the pool, with its files. `--no-pool` skips this. `--pool PATH` looks in
the library PATH instead, in any library: the entry is taken from PATH with
its files, its origin is recorded for PATH, and nothing is added to PATH
(`papers -C PATH add` is what adds to PATH).

`papers add --key KEY`, with no file, DOI or other field, takes the pool
entry of key `KEY` (ignoring case). When the library already has an entry of
that key, the files of `--attach` are attached to it. When neither has it,
papers stops with an error and changes nothing:

```
papers add --key yool2011
```

In a shallow library, the files of the added entries go to the files
directory of the pool, and the entries to the pool too (see
[Shallow libraries](shallow-libraries.md#files)).

`papers add other.bib` copies the entries of `other.bib` once, with no
memory of the source. To take entries from the pool so that they stay
linked to it (later pulls bring the corrections made there), use
`papers pull KEY` (see [`papers pull`](pools.md#papers-pull)).

## Add RIS, CSL-JSON and BibJSON files

`papers add` reads RIS (`.ris`, as exported by Zotero, EndNote, Web of
Science, Scopus...), CSL-JSON (`.json`, as exported by Zotero or pandoc)
and BibJSON (`.bib.json`, see [BibJSON](export.md#bibjson)) files,
recognized by their extension; `--format ris|csl-json|bibjson|bibtex` sets
the format of a file of another extension. Other files are read as bibtex.
RIS needs the [rispy](https://pypi.org/project/rispy/) package (see
[Installation](installation.md#optional-ris-support)).

```
$ papers add ~/refs.ris --on-duplicate keep
Added -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011)
Modified -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1)
```

The entries are added as those of a bibtex file:

- the [duplicate check](#duplicates) and `--on-duplicate` apply;
- the key is the `ID` of a RIS record, or the `citation-key` or `id` of a
  CSL-JSON item, when it is a valid bibtex key; otherwise (the item URIs of
  Zotero, the record numbers of EndNote) it is made from the key template;
- the file links (RIS `L1`; in CSL-JSON, a `file` key or `custom.file`,
  which papers writes, since CSL-JSON has no standard field for files) are
  read relative to the added file and attached as for a bibtex file; links
  that are not local files (`http://`, EndNote's `internal-pdf://`) are left
  out with a warning;
- RIS and CSL-JSON hold plain text: `&`, `%`, `#` and `_` are escaped for
  LaTeX (`\&`...), except in `url`, `doi`, `file`, `eprint`, `isbn`,
  `issn`, `keywords` and `urldate`; BibJSON values are read as they are,
  since they are bibtex values;
- keywords (RIS `KW`, CSL-JSON `keyword`) are split on `,` and `;` and
  joined with `, ` (export splits the `keywords` field on `,` only);
- the CSL-JSON `container-title` (RIS `T2`, `JO`...) is the `booktitle` of a chapter or a
  conference paper (`incollection`, `inproceedings`), the `journal` of any
  other type;
- a date part that is zero or missing ends the date: `2013-00-05` is the
  year 2013 only;
- in a shallow library, the new entries go to the pool too;
- a directory scan (`-R`) reads PDFs and bibtex files only.

The fields are converted as `papers export --format` writes them (see
[How the fields are converted](export.md#how-the-fields-are-converted)); a
few more are read: `T1`, `JO`, `JF` (title, journal), `A2` (editors of a
chapter, in EndNote exports), `N2` (abstract), `M3` (type of a report); and
in CSL-JSON, `genre` (the type of a report or thesis). A thesis whose type
(RIS `M3`, CSL-JSON `genre`) contains `master` is a `mastersthesis`, any
other a `phdthesis`. Other fields are ignored.

## Add an entry from its DOI

If you already know the DOI of a PDF, and don't want to gamble the fulltext
search and match, you can indicate it via `--doi`:

```
papers add esd-4-11-2013.pdf --doi 10.5194/esd-4-11-2013 --bibtex papers.bib
```

The `add` command above also works without any PDF (create a bibtex entry
without file attachment):

```
papers add --doi 10.5194/esd-4-11-2013 --bibtex papers.bib
```

## Add an entry without DOI from bibtex + PDF

Some old files don't have a DOI. The best approach is to add the entry from its
bibtex:

```
papers add entry.bib --attach esd-4-11-2013.pdf --bibtex papers.bib --filesdir files
```

## Set fields on the command line

`--title`, `--author`, `--year`, `--journal`, `--type` (the entry type, e.g.
`book`), `--key` and `--metadata KEY=VALUE...` (any field) set these fields of
the added entry. They replace the values found in the PDF, fetched from the
DOI or read from the added bibtex; the other fields are kept:

```
papers add paper.pdf --year 1999 --journal "Journal of Glaciology"
```

- `--key KEY` sets the key, which is then not generated from the key
  template; without `--key`, the generated key uses the fields given (here
  the year 1999);
- the files of `--attach` (and of a `file` field given with `--metadata`)
  are added to the files of the entry;
- these options apply to one entry: they are an error with several files, a
  directory (`-R`), or a bibtex file of several entries;
- an entry taken from a pool gets the fields given too (in the library; the
  pool entry changes only if you push);
- when the added paper is already in the library (same DOI, see below), the
  fields of the library entry are not changed: papers warns that the options
  are ignored; use `papers edit KEY` to change them;
- when the added entry is merged into a library entry by the duplicate check
  (below), the fields given are those of the added entry: a value that
  differs from the library's is a conflict, resolved as `--on-duplicate`
  says, and the library key is kept.

## Duplicates

Before inserting an entry, `papers add` looks for the same paper in the
library. `papers check --duplicates` and `papers list --duplicates` use the
same rule (see [Managing your library](library-management.md#duplicates)).

### Same paper

Two entries are the same paper when they have the same identifier, checked
in this order:

1. the DOI (case-insensitive; `doi:` and `https://doi.org/` prefixes are
   ignored);
2. the arXiv identifier: the `eprint` field when `archivePrefix` is arXiv
   or absent, and arXiv DOIs (`10.48550/arXiv.<id>`), whatever the version;
3. the ISBN, for two `@book` entries only (a chapter carries the ISBN of its
   book, and each edition has its own ISBN);
4. otherwise the family names of the authors and the title, compared without
   case, braces, accents and extra spaces. Both entries need authors and a
   title: two entries titled "Editorial" without authors are not the same
   paper.

The first identifier that both entries have decides: equal values make the
same paper, different values two papers. A preprint and the published
article with different DOIs are two entries, even with the same authors and
title.

Equal identifiers make the same paper, except in one case: when the entry
types differ (e.g. `@book` and `@incollection`) and the titles differ
(after ignoring case, braces, accents and spacing), papers asks instead of
merging. This happens with a chapter exported with the DOI of its book, or a
dataset "Data for: X" deposited under the DOI of the article "X". Without a
terminal, such a pair is never merged.

When you answer that two entries are not the same paper (`n`, below), papers
records it in `.papers/distinct.json` of the library, and does not ask
about them again. The file records the identifiers of both entries (DOI,
arXiv id, ISBN, authors and title), not their keys.

### What a merge does

The entry already in the library (entry 1) is the target:

- it keeps its key;
- fields that only the added entry has are added;
- the file links of both entries are kept (a file linked twice, or two
  copies with the same content, once);
- values that differ only by case, braces, spaces, or the case of a DOI are
  not conflicts, and the library's spelling is kept. Author names with
  initials and with full first names (`Smith, J.` and `Smith, John`) are not
  a conflict either: the fuller form is kept, whichever entry it comes
  from. Different first names (`Smith, John` and `Smith, Jane`) are a
  conflict;
- the remaining differences are conflicts.

An added entry that brings nothing new (no conflict, no field to add) is
merged without a question: its files are added, and papers prints
`already in library: smith2020climate (+1 file)`.

### --on-duplicate

`--on-duplicate` says what to do when the added entry has conflicts or
fields to add:

| Value | What happens |
|---|---|
| `ask` | the dialogue below (default when the standard input is a terminal) |
| `keep` | merge; conflicts keep the library value |
| `update` | merge; conflicts take the value of the added entry |
| `skip` | the entry is not added; the library entry, its files and the added file are left as they are |
| `error` | stop before saving, and exit with status 1 (default without a terminal, e.g. in a script) |

`--no-check-duplicate` adds the entries without looking for duplicates.

### The dialogue

```
$> papers add new.bib
Already in library: smith2020climate (same DOI 10.1000/abc123)
  1  library  smith2020climate  article  doi 10.1000/abc123  files/smith.pdf
  2  new      Smith_2020        article  doi 10.1000/ABC123  other/smith-preprint.pdf

@article{smith2020climate,
   author   = {Smith, John and Doe, Jane}
   doi      = {10.1000/abc123}
+  file     = {files/smith.pdf;other/smith-preprint.pdf}
!  journal  = {Nature}
!             2: {Nature Climate Change}
   keywords = {climate, mine}
   title    = {Climate sensitivity revisited}
+  volume   = {10}
   year     = {2020}
}
1 conflict. The key smith2020climate is kept; + lines are added.
  1 keep library values   2 take new values   f field by field   e edit
  n not the same paper (add Smith_2020 separately)   s skip   q quit   ? help
>>>
```

Unmarked lines are the same in both entries (here the title and the author
names, which differ only by case and initials), `+` lines are added from the
other entry, and `!` lines are conflicts: the value that will be used, then
the other values, numbered by entry.

| Answer | Meaning |
|---|---|
| `1`, `2` | resolve all conflicts with the values of that entry, and merge |
| `f` | go through the conflicts one at a time |
| `e` | edit the merged entry in the editor, as plain bibtex; the values of the other entry are `%` comment lines below it. If the editor fails or the text is not one bibtex entry, papers comes back to this menu |
| `n` | not the same paper: add the entry separately (with a free key if its key is taken), and remember it |
| `s` | skip: change nothing for this entry; it is asked again next time |
| `q` | quit: skip this entry and all the remaining duplicates of this command; the other entries are added |
| `?` | help |

`f` asks for each conflict:

```
journal:
  1  Nature                 library
  2  Nature Climate Change  new
  [1/2/e] >>>
```

To stop without saving anything, use Ctrl-C.

### Keys

Entries added from a bibtex file keep their own key, unless `-u/--update-key`
is passed, in which case the key is regenerated from the key template (see
[Renaming files and keys](renaming.md)). Entries extracted from a PDF or
fetched from a DOI always get a generated key. `--key KEY` sets the key
instead, in both cases. Either way, this only
concerns entries new to the library: an entry merged into a duplicate takes
the key of the library entry.

### Options of earlier versions

These options still work, with a warning, and will be removed:

| Old | New |
|---|---|
| `-m i` | `--on-duplicate ask` |
| `-m u` | `--on-duplicate keep` |
| `-m U` | `--on-duplicate update` (the library key is kept) |
| `-m o` | `--on-duplicate update` (the library key and the fields only in the library are kept) |
| `-m s` | `--on-duplicate skip` (the file of the added entry is not attached; `keep` does that) |
| `-m r` | `--on-duplicate error` |
| `-m a` | `--no-check-duplicate` |
| `--no-merge-files` | ignored: file links are always merged |
