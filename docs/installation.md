# Installation

## Install papers

papers 3 (beta) is published on PyPI as a pre-release: `--pre` installs it.

```bash
pip install --pre papers-cli
```

The development version, from the `v3` branch:

```bash
pip install git+https://github.com/perrette/papers.git@v3
```

papers 2, the current release:

```bash
pip install papers-cli
```

Note there is another project registered on PyPI as `papers`, hence
`papers-cli` for command-line-interface. The installed command is still
`papers`. To upgrade a papers 2 setup, see
[Upgrading from papers 2](upgrading.md).

## Name clash with GNOME Papers

The [GNOME Papers](https://gitlab.gnome.org/GNOME/papers) document viewer
(the default viewer on recent GNOME desktops) also installs a `papers`
command; with both installed, whichever comes first in `$PATH` wins. Two
mitigations are built in:

- The package also installs the command under the unambiguous name
  `papers-cli` — call that, or set a shell alias (e.g.
  `alias papers=papers-cli`), on systems where the names collide.
- Because this command may mask GNOME Papers, a call whose arguments are all
  existing files (paths or `file://` URIs, as passed by file managers through
  the viewer's desktop entry) is handed over unchanged to the next `papers`
  executable in `$PATH` that is not this tool, i.e. GNOME Papers itself.
  Double-clicking a PDF and `papers somefile.pdf` therefore keep opening the
  viewer. If no other `papers` is found, the files are opened with the
  system's default viewer (`xdg-open`) instead; should that lead back to
  this command, it stops with an error rather than looping. Subcommand names
  always take precedence (`papers ./list` opens a file named `list`;
  `papers list` lists your library), and any flag disables the hand-over —
  call the viewer's binary directly for viewer-specific flags.

## Dependencies

- python 3.11+
- [PyMuPDF](https://github.com/pymupdf/PyMuPDF) (preferred) or
  [poppler-utils](https://en.wikipedia.org/wiki/Poppler_(software))
  (only `pdftotext` and `pdfinfo`; deprecated): convert PDF to text for parsing
- [bibtexparser](https://bibtexparser.readthedocs.io): parse bibtex files
- [scholarly](https://github.com/OrganicIrradiation/scholarly): interface for
  google scholar
- [rapidfuzz](https://github.com/rhasspy/rapidfuzz): calculate score to sort
  crossref requests
- [unidecode](https://github.com/avian2/unidecode): replace unicode with ascii
  equivalent

The Python dependencies are installed automatically with `pip`.

## Optional: RIS support

Reading and writing RIS files (`papers add refs.ris`,
`papers export --format ris`, `papers list --format ris`) needs the
[rispy](https://pypi.org/project/rispy/) package, which is not installed
by default. Install it in the environment of papers:

```bash
pip install 'papers-cli[ris]'       # with papers
pip install rispy                    # or afterwards
pipx inject papers-cli rispy         # papers installed with pipx
uv tool install papers-cli --with rispy   # papers installed with uv
```

When a command needs rispy and it is missing, papers asks in a terminal
whether to install it with `pip` (`python -m pip install rispy`, with the
Python of papers); otherwise, or on no, it stops without changing anything
and prints these commands. CSL-JSON needs no extra package.
