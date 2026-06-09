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
pip install papers-cli
papers add mypaper.pdf --rename --copy --bibtex papers.bib --filesdir files
```

- **[Installation](installation.md)** — pip install and external dependencies.
- **[Quickstart](quickstart.md)** — extract metadata, add a PDF, list entries.
- **[Adding entries](adding-entries.md)** — from PDFs, DOIs, bibtex, or whole directories.
- **[Configuration and install](configuration.md)** — make your bibtex and files directory persistent.

## Guides

- [Adding entries](adding-entries.md)
- [Listing and searching](listing.md)
- [Renaming files and keys](renaming.md)
- [Configuration and install](configuration.md)
- [Managing your library](library-management.md)
- [Git integration](git.md)
- [Undo and redo](undo-redo.md)

## About

- [Features](features.md)
- [Comparison with other tools](comparison.md)
