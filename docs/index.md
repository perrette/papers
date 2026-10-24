<!--
  Home page. The feature bullets are pulled straight from README.md (single
  source of truth) via the include-markdown plugin; everything else links into
  the guide.
-->
# papers

Command-line tool to manage your bibliography (PDFs + BibTeX).

{%
  include-markdown "../README.md"
  start="<!-- intro-start -->"
  end="<!-- intro-end -->"
%}

## Get started

```bash
pip install --pre papers-cli    # the 3.0 beta
cd ~/projects/my-paper
papers init                     # a library: papers.bib and files/ here
papers add ~/Downloads/paper.pdf
papers list
```

- **[Installation](installation.md)** — pip install and external dependencies.
- **[Quickstart](quickstart.md)** — a self-contained project, and a shallow project that uses it as pool.
- **[Upgrading from papers 2](upgrading.md)** — what becomes of a papers 2 library, and `papers migrate`.
- **[Adding entries](adding-entries.md)** — from PDFs, DOIs, bibtex, or whole directories.
- **[Configuration](configuration.md)** — libraries, settings and pools.

## Guides

- [Adding entries](adding-entries.md)
- [Listing and searching](listing.md)
- [Renaming files and keys](renaming.md)
- [Files](files.md)
- [Configuration](configuration.md)
- [Pools](pools.md)
- [Shallow libraries](shallow-libraries.md)
- [Export](export.md)
- [A global shared library](global-library.md)
- [Managing your library](library-management.md)
- [Git integration](git.md)
- [Undo and redo](undo-redo.md)

## From the same author

A few other open-source tools I maintain.

**Scientific writing & data**

- [**texmark**](https://perrette.github.io/texmark/) — write scientific articles in Markdown and convert them to journal-ready LaTeX/PDF.
- [**datamanifest**](https://perrette.github.io/datamanifest/) — declarative, reproducible dataset management. *(See also the [datamanifest.toml](https://perrette.github.io/datamanifest.toml/) format spec and the [DataManifest.jl](https://awi-esc.github.io/DataManifest.jl/) Julia port.)*

**Speech to Text (dictate) and Text to Speech (read-aloud) tools**

- [**scribe**](https://perrette.github.io/scribe/) — speech-to-text dictation.
- [**bard**](https://perrette.github.io/bard/) — text-to-speech reader.
