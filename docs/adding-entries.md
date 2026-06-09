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
