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
Projects on the same topic share their entries and PDFs through a pool, so
each PDF is stored and fetched once.

It works like `git`: one `papers` command with subcommands, run inside a
project folder.

- **Add papers** from PDFs, DOIs, bibtex files or whole folders. The DOI is
  read from the PDF, and the metadata comes from
  [crossref](https://github.com/CrossRef/rest-api-doc) (by DOI or full-text
  search), doi.org or google scholar.
- **Name the PDFs** with a template (`{authorX}_{year}_{title}` by default),
  and attach supplements to an entry.
- **Share entries and PDFs between projects** through a pool: a library in
  a shared location, such as one per topic. `papers pull`, `push` and
  `sync` exchange the entries with a field-by-field three-way merge; each
  project keeps its own keys.
- **Search and act on a library** with `papers list` (tag, edit, delete,
  rename, fetch, deduplicate), in the style of `find` and `grep`.
- **Detect duplicates** by DOI, arXiv identifier, ISBN, or authors and
  title, and merge them.
- **Plain files**: the bibtex is the database. Every change is backed up
  with git (when it is installed), and `papers undo` / `papers redo` take it back or restore it.
<!-- intro-end -->

## Example

Two projects that use the pool `~/Documents/papers/sealevel`:

```
$ cd ~/projects/sealevel
$ papers init --pool ~/Documents/papers/sealevel
created the library ~/projects/sealevel
* bibtex:  papers.bib
* files:   in the pool ~/Documents/papers/sealevel
* backup:  git
`papers status -v` shows all settings
$ papers add ~/Downloads/esd-4-11-2013.pdf
create the library ~/Documents/papers/sealevel
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1) [also added to pool ~/Documents/papers/sealevel]
$ papers add --doi 10.5194/bg-8-515-2011
Added -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011) [also added to pool ~/Documents/papers/sealevel]

$ cd ~/projects/tides
$ papers init --pool ~/Documents/papers/sealevel
created the library ~/projects/tides
* bibtex:  papers.bib
* files:   in the pool ~/Documents/papers/sealevel
* backup:  git
`papers status -v` shows all settings
$ papers add --doi 10.5194/esd-4-11-2013
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1) [from pool ~/Documents/papers/sealevel]
$ grep "file =" papers.bib
 file = {:../../Documents/papers/sealevel/files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf:pdf},
```

The second project took the entry and the PDF from the pool: no request
to crossref, and no second copy of the PDF. `papers sync` later exchanges
the changes made in either project.

A project that keeps its own PDFs, such as a folder shared with coauthors,
is created with `papers init --local`. Plain `papers init` uses the global
pool, `~/Documents/papers`.

## Documentation

Full documentation: **<https://perrette.github.io/papers/>**

- [Installation](https://perrette.github.io/papers/installation/) (incl. external dependencies)
- [Quickstart](https://perrette.github.io/papers/quickstart/): a project, its pool, a second project
- [Upgrading from papers 2](https://perrette.github.io/papers/upgrading/)
- [Adding entries](https://perrette.github.io/papers/adding-entries/)
- [Listing and searching](https://perrette.github.io/papers/listing/)
- [Pools](https://perrette.github.io/papers/pools/)
- [Configuration](https://perrette.github.io/papers/configuration/)
- Also: [files](https://perrette.github.io/papers/files/),
  [renaming files and keys](https://perrette.github.io/papers/renaming/),
  [managing your library](https://perrette.github.io/papers/library-management/),
  [git integration](https://perrette.github.io/papers/git/),
  [undo/redo](https://perrette.github.io/papers/undo-redo/),
  [features](https://perrette.github.io/papers/features/)

`papers --help` and `papers <command> --help` describe every command and
option.

## Install

papers 3 (beta, this branch) is not on PyPI yet:

```bash
pip install git+https://github.com/perrette/papers.git@v3
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
