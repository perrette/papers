# Export

## `papers export`

```
papers export DIR [KEY...|-] [--files copy|link|none]
```

writes the entries (all without KEY) as a new library in `DIR`, which must
not exist or be empty, to hand over: its bibtex, its files directory, and
its configuration (a self-contained library, with the name and key
templates that the library sets). File links are relative to the new
bibtex.

- `--files copy` (default) copies the files into `DIR/files` (hard links
  when possible), named with the name template;
- `--files link` links to the files where they are;
- `--files none` leaves the file links out.

```
$ papers export ~/export-test perrette_landerer2013
create the library ~/export-test
exported 1 entries to ~/export-test (files: copy)
$ ls ~/export-test ~/export-test/files
~/export-test:
files
papers.bib

~/export-test/files:
perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf
```

`papers add DIR --recursive` adds an exported library to another one, and
`papers config pool DIR` makes it the pool of the library (the export has
copies of its PDFs). `papers sync --pool DIR` exchanges entries with it
later (see [Exchanges with any library](pools.md#exchanges-with-any-library)).

## Other formats

`papers export` writes a papers library only. Other formats are not
supported yet.
