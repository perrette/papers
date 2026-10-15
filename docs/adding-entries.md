# Adding entries

The `papers add` command adds entries to your library, with or without a PDF
attachment.

## Add a PDF (extract metadata automatically)

```
$> papers add esd-4-11-2013.pdf --rename --copy --bibtex papers.bib --filesdir files --info
INFO:papers:found doi:10.5194/esd-4-11-2013
INFO:papers:new entry: perrette_landerer2013
INFO:papers:mv /home/perrette/playground/papers/esd-4-11-2013.pdf files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf
INFO:papers:renamed file(s): 1
```

That is equivalent to doing:

```
papers extract esd-4-11-2013.pdf > entry.bib
papers add entry.bib --bibtex papers.bib --attachment esd-4-11-2013.pdf --rename --copy
```

Without `--rename` (`-r`) the PDF is linked where it is: the `file` field
points to its current location and nothing is moved or copied into the files
directory. `--rename` moves the file into `--filesdir` under a name made from
the name template, and `--copy` (`-c`) makes a copy there instead of moving
the original (it has no effect without `--rename`). The same applies to the
files linked from the entries of a bibtex file added with `papers add
other.bib`: their paths are read relative to that bibtex and stored so that
they remain valid from your own bibtex (absolute, or relative to it, according
to `--absolute-paths`/`--relative-paths` or the installed setting); with
`--rename` they are moved (or copied with `--copy`) into the files directory.

See [Renaming files and keys](renaming.md) for how to specify file naming
patterns.

## Add a whole directory of PDFs

It is possible to do this on a full directory of files, recursively:

```
papers add --rename --recursive /home/perette/playground/papers/papers_test
```

where, above, the `papers_test` directory contains a few PDF files. For each
PDF, `papers` will attempt to extract the metadata and add the relevant file to
the bibliography, and rename files into the files directory.

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
papers add entry.bib --attachment esd-4-11-2013.pdf
```

## Duplicates and keys

Before inserting an entry, `papers add` looks for a duplicate in the library
(same DOI, or same authors and title). The `-m/--mode` option says what to do
when one is found: `i` (interactive, the default), `u` (update the existing
entry with the new entry's missing fields, existing values win), `U` (update
the existing entry with the new entry's values, new values win), `o`
(overwrite), `s` (skip the new entry), `a` (append it anyway), `r` (raise an
error).

Entries added from a bibtex file keep their own key, unless `-u/--update-key`
is passed, in which case the key is regenerated from the key template (see
[Renaming files and keys](renaming.md)). Entries extracted from a PDF or
fetched from a DOI always get a generated key.

With `-u/--update-key`, a duplicate is always merged under the key of the entry
already in the library, in every mode (`u`, `U`, `o`; with `a` the existing
entry keeps its key and the appended entry gets a fresh one). Without `-u`,
modes `u` and `s` keep the existing entry's key, while `U` and `o` take over
the new entry's key.
