# Installation

## Install papers

```bash
pip install papers-cli
```

Note there is another project registered on PyPI as `papers`, hence
`papers-cli` for command-line-interface. The installed command is still
`papers`.

## Name clash with GNOME Papers

The [GNOME Papers](https://gitlab.gnome.org/GNOME/papers) document viewer
(the default viewer on recent GNOME desktops) also installs a `papers`
command; with both installed, whichever comes first in `$PATH` wins. The
package therefore also installs the command under the unambiguous name
`papers-cli` — call that, or set a shell alias (e.g.
`alias papers=papers-cli`), on systems where the names collide.

## Dependencies

- python 3.9+
- [PyMuPDF](https://github.com/pymupdf/PyMuPDF) (preferred) or
  [poppler-utils](https://en.wikipedia.org/wiki/Poppler_(software))
  (only `pdftotext`; deprecated): convert PDF to text for parsing
- [bibtexparser](https://bibtexparser.readthedocs.io): parse bibtex files
- [crossrefapi](https://github.com/fabiobatalha/crossrefapi): make polite
  requests to the crossref API
- [scholarly](https://github.com/OrganicIrradiation/scholarly): interface for
  google scholar
- [rapidfuzz](https://github.com/rhasspy/rapidfuzz): calculate score to sort
  crossref requests
- [unidecode](https://github.com/avian2/unidecode): replace unicode with ascii
  equivalent

The Python dependencies are installed automatically with `pip`.
