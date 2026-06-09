# Installation

## Install papers

```bash
pip install papers-cli
```

Note there is another project registered on PyPI as `papers`, hence
`papers-cli` for command-line-interface. The installed command is still
`papers`.

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
