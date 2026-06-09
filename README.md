# papers

[![pypi](https://img.shields.io/pypi/v/papers-cli)](https://pypi.org/project/papers-cli)
[![python](https://img.shields.io/badge/python-3.9-blue.svg)]()
[![python](https://img.shields.io/badge/python-3.14t-blue.svg)]()
[![test](https://github.com/perrette/papers/workflows/CI/badge.svg?query=branch%3Amaster)](https://github.com/perrette/papers/actions)
[![docs](https://img.shields.io/badge/docs-perrette.github.io%2Fpapers-blue)](https://perrette.github.io/papers/)

Command-line tool to manage your bibliography (PDFs + BibTeX).

Disclaimer: This tool requires further development and testing, and might never
be fully production-ready (contributors welcome). \
That said, it is becoming useful :)

<!-- intro-start -->
A light-weight, command-line bibliography management tool built like `git`,
with a main command `papers` and a range of subcommands. It lets you:

- **Maintain a PDF library** with appropriate, customisable file naming.
- **Maintain one or several BibTeX collections**, linked to their PDFs.
- **Fetch metadata from the internet** — enough PDF-parsing capability to pull
  metadata from [crossref](https://github.com/CrossRef/rest-api-doc) (by DOI or
  fulltext search) or google scholar.
- **Search and act on your library** with a `find`/`grep`-inspired
  `papers list` (tag, edit, delete, rename, fetch, deduplicate).
- **Stay in control** — plain BibTeX files, optional git tracking, and
  undo/redo for every change.
<!-- intro-end -->

## 📖 Documentation

Full documentation lives at **<https://perrette.github.io/papers/>**:

- [Installation](https://perrette.github.io/papers/installation/) (incl. external dependencies)
- [Quickstart](https://perrette.github.io/papers/quickstart/)
- [Adding entries](https://perrette.github.io/papers/adding-entries/)
- [Listing and searching](https://perrette.github.io/papers/listing/)
- [Renaming files and keys](https://perrette.github.io/papers/renaming/)
- [Configuration and install](https://perrette.github.io/papers/configuration/)
- Also: [managing your library](https://perrette.github.io/papers/library-management/),
  [git integration](https://perrette.github.io/papers/git/),
  [undo/redo](https://perrette.github.io/papers/undo-redo/),
  [features](https://perrette.github.io/papers/features/)

## Install

```bash
pip install papers-cli
```

Note there is another project registered on PyPI as `papers`, hence
`papers-cli` for command-line-interface. See the
[installation page](https://perrette.github.io/papers/installation/) for
external dependencies.

## Quickstart

```bash
# extract metadata from a PDF and add it to your library
papers add esd-4-11-2013.pdf --rename --copy --bibtex papers.bib --filesdir files

# list and search your library
papers list perrette scaling approach sea level
```

See the [quickstart](https://perrette.github.io/papers/quickstart/) for a full
walkthrough.

Consult inline help (`papers --help`, `papers <command> --help`) for more
detailed documentation.

## From the same author

A few related tools I maintain, useful in a Markdown-based scientific workflow.

**Scientific writing & data**

- [**texmark**](https://perrette.github.io/texmark/) — write scientific articles in Markdown and convert them to journal-ready LaTeX/PDF.
- [**papers**](https://perrette.github.io/papers/) — command-line BibTeX bibliography and PDF library manager.
- [**datamanifest**](https://perrette.github.io/datamanifest/) — declarative, reproducible dataset management. *(See also the [datamanifest.toml](https://perrette.github.io/datamanifest.toml/) format spec and the [DataManifest.jl](https://awi-esc.github.io/DataManifest.jl/) Julia port.)*

**Voice helpers** — handy for dictating and proofreading drafts by ear

- [**scribe**](https://perrette.github.io/scribe/) — speech-to-text dictation (Whisper).
- [**bard**](https://perrette.github.io/bard/) — text-to-speech reader (Kokoro / Piper).
