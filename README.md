# papers

[![pypi](https://img.shields.io/pypi/v/papers-cli)](https://pypi.org/project/papers-cli)
[![python](https://img.shields.io/badge/python-3.11-blue.svg)]()
[![python](https://img.shields.io/badge/python-3.15-blue.svg)]()
[![test](https://github.com/perrette/papers/workflows/CI/badge.svg?query=branch%3Amaster)](https://github.com/perrette/papers/actions)
[![docs](https://img.shields.io/badge/docs-perrette.github.io%2Fpapers-blue)](https://perrette.github.io/papers/)

Command-line tool to manage your bibliography (PDFs + BibTeX).

<!-- intro-start -->
`papers` keeps a BibTeX file for each of your projects, and the PDFs that
go with it. Give it a PDF: it reads the DOI, fetches the entry from
crossref, renames the PDF after the entry and adds both to your project.
A project can use another library as its pool, and take its entries and
PDFs from there, so that each PDF is stored and fetched once.

It works like `git`: one `papers` command with subcommands, run inside a
project folder.

- **Add papers** from PDFs, DOIs, bibtex, RIS, CSL-JSON or BibJSON files, or whole folders. The DOI is
  read from the PDF, and the metadata comes from
  [crossref](https://github.com/CrossRef/rest-api-doc) (by DOI or full-text
  search), doi.org, google scholar or
  [OpenAlex](https://openalex.org).
- **Name the PDFs** with a template (`{authorX}_{year}_{title}` by default),
  and attach supplements to an entry.
- **Share entries and PDFs between projects**: a shallow project uses
  another library as its pool, takes its entries from there and links to
  its PDFs; any library can also exchange entries with another one
  (`--pool PATH`). `papers pull`, `push` and `sync` exchange the entries
  with a field-by-field three-way merge; each project keeps its own keys.
- **Search and act on a library** with `papers list` (tag, edit, delete,
  rename, fetch, deduplicate), in the style of `find` and `grep`.
- **Detect duplicates** by DOI, arXiv identifier, ISBN, or authors and
  title, and merge them.
- **Export** a selection as a library with copies of its PDFs, or as RIS
  and CSL-JSON (for Zotero, EndNote, pandoc) or BibJSON (for programs).
- **Plain files**: the bibtex is the database, the PDFs stay in folders you
  see, and the library can be edited with any tool.
- **Undo anything**: every command is a step of the library's history,
  kept on your computer; `papers undo` / `papers redo` take back any
  command, with the files it moved, renamed or deleted, and a change made
  outside papers is never lost.
- **Fast on large libraries**: the parsed bibtex is cached piece by piece,
  and `papers status` compares a project with its pool only where they
  changed.
<!-- intro-end -->

## Example

A project with its own PDFs, and a second project that uses it as pool:

```
$ cd ~/projects/sealevel
$ papers init
created the library ~/projects/sealevel
* bibtex:  papers.bib
* files:   files (the files directory of the library)
`papers config` lists and sets the settings
$ papers add ~/Downloads/esd-4-11-2013.pdf
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1)

$ cd ~/projects/tides
$ papers init --pool ../sealevel
created the library ~/projects/tides
* bibtex:  papers.bib
* files:   in the pool (shallow library)
* pool:    ../sealevel
`papers config` lists and sets the settings
$ papers add --doi 10.5194/esd-4-11-2013
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1) [from pool ../sealevel]
$ papers add ~/Downloads/bg-8-515-2011.pdf
Added -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, file:1) [also added to pool ../sealevel]
$ grep "file =" papers.bib
 file = {:../sealevel/files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf:pdf},
 file = {:../sealevel/files/perrette_et_al_2011_near-ubiquity-of-ice-edge-blooms-in-the-arctic.pdf:pdf},
```

The second project took the first entry and its PDF from the pool: no
request to crossref, and no second copy of the PDF. The paper it added is
in the pool too. `papers sync` later exchanges the changes made in either
project. A library kept for sharing, such as `~/Documents/papers`, can be
the pool of all projects (`papers init --shallow`, see
[A global shared library](https://perrette.github.io/papers/global-library/)).

## Documentation

Full documentation: **<https://perrette.github.io/papers/>**

- [Installation](https://perrette.github.io/papers/installation/) (incl. external dependencies)
- [Quickstart](https://perrette.github.io/papers/quickstart/): a self-contained project, and a shallow project that uses it
- [Upgrading from papers 2](https://perrette.github.io/papers/upgrading/)
- [Adding entries](https://perrette.github.io/papers/adding-entries/)
- [Listing and searching](https://perrette.github.io/papers/listing/)
- [Pools](https://perrette.github.io/papers/pools/), [shallow libraries](https://perrette.github.io/papers/shallow-libraries/), [a global shared library](https://perrette.github.io/papers/global-library/)
- [Configuration](https://perrette.github.io/papers/configuration/)
- Also: [files](https://perrette.github.io/papers/files/),
  [renaming files and keys](https://perrette.github.io/papers/renaming/),
  [managing your library](https://perrette.github.io/papers/library-management/),
  [export](https://perrette.github.io/papers/export/),
  [git integration](https://perrette.github.io/papers/git/),
  [undo/redo](https://perrette.github.io/papers/undo-redo/)

`papers --help` and `papers <command> --help` describe every command and
option.

## Install

papers 3 (beta), published on PyPI as a pre-release:

```bash
pip install --pre papers-cli
```

papers 2, the current release:

```bash
pip install papers-cli
```

The package is called `papers-cli` because another project is registered
on PyPI as `papers`; the command is `papers`. Python 3.11 or later is
needed. See the
[installation page](https://perrette.github.io/papers/installation/) for
external dependencies.

The project is developed by one person and is still evolving: bug reports
and contributions are welcome.

## From the same author

A few other open-source tools I maintain.

**Scientific writing & data**

- [**texmark**](https://perrette.github.io/texmark/) — write scientific articles in Markdown and convert them to journal-ready LaTeX/PDF.
- [**datamanifest**](https://perrette.github.io/datamanifest/) — declarative, reproducible dataset management. *(See also the [datamanifest.toml](https://perrette.github.io/datamanifest.toml/) format spec and the [DataManifest.jl](https://awi-esc.github.io/DataManifest.jl/) Julia port.)*

**Speech to Text (dictate) and Text to Speech (read-aloud) tools**

- [**scribe**](https://perrette.github.io/scribe/) — speech-to-text dictation.
- [**bard**](https://perrette.github.io/bard/) — text-to-speech reader.
