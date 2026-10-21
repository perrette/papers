# Adding entries

The `papers add` command adds entries to your library, with or without a PDF
attachment.

## Add a PDF (extract metadata automatically)

```
$> papers add esd-4-11-2013.pdf --bibtex papers.bib --filesdir files --info
INFO:papers:found doi:10.5194/esd-4-11-2013
INFO:papers:new entry: perrette_landerer2013
INFO:papers:mv /home/perrette/playground/papers/esd-4-11-2013.pdf files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf
INFO:papers:renamed file(s): 1
```

That is equivalent to doing:

```
papers extract esd-4-11-2013.pdf > entry.bib
papers add entry.bib --attach esd-4-11-2013.pdf --bibtex papers.bib --filesdir files
```

## What happens to the files

By default, `papers add` moves the PDF into the files directory of the
library, under a name made from the name template. The `files` setting of
the library changes that (see [Files](files.md#what-add-does-with-a-file)):

- `move` (default): place the file in the files directory and remove the
  original;
- `copy`: place it in the files directory and keep the original (a hard link
  when possible, otherwise a copy);
- `link`: leave it where it is; the entry links to it there.

`--move`, `--copy` and `--link` override the setting for one command
(`-r/--rename` is the same as `--move`, `-c` as `--copy`):

```
papers config files copy           # this library keeps the originals
papers add esd-4-11-2013.pdf --link
```

A file that belongs to another library (inside its files directory) is
never moved: it is copied instead, so that the other library keeps its link.

The same applies to the files linked from the entries of a bibtex file added
with `papers add other.bib`: their paths are read relative to that bibtex,
and when they are linked where they are (`link`), they are stored so that
they remain valid from your own bibtex (relative to it, or absolute,
according to the `paths` setting of the library).

See [Renaming files and keys](renaming.md) for how to specify file naming
patterns, and how the files of an entry with attachments are named.

## Attach files

`--attach FILE...` attaches other files to the added entry (e.g.
supplementary material), placed as the `files` setting says. They are named
after the main file (see
[Renaming files and keys](renaming.md#entries-with-several-files)). To
attach files to an entry already in the library, use
`papers file attach KEY FILE...`. `--attachment` is the deprecated name of
`--attach`.

## Add a whole directory of PDFs

It is possible to do this on a full directory of files, recursively:

```
papers add --recursive /home/perette/playground/papers/papers_test
```

where, above, the `papers_test` directory contains a few PDF files. For each
PDF, `papers` will attempt to extract the metadata and add the relevant file to
the bibliography, and place the files as the `files` setting says (by
default, moved into the files directory).

Files named after a PDF of the same directory, as papers names
attachments (`<name>--<label>.<ext>` next to `<name>.pdf`, see
[Renaming files and keys](renaming.md#entries-with-several-files)), are added
as attachments of that PDF's entry, whatever their type, instead of being
scanned as papers of their own. Bibtex files found in the directory are added
too, before the PDFs, and the files they link to are not scanned: their entry
comes from the bibtex, so a folder that holds a bibtex and its files is added
without looking anything up online. Folders of the pre-2.19 layout (with a
hidden `.<name>.bib`) are read from their hidden bibtex.

The metadata of a PDF are found as follows:

1. a DOI in the PDF metadata is used as is;
2. otherwise, the DOIs printed in the text (first pages, and the last page,
   where some publishers add a cover page) are looked up in turn, and the
   first one whose title appears in the first pages is used: this skips the
   DOIs of cited papers;
3. otherwise, a crossref search on the text of the first pages, whose result
   is also accepted only if its title appears in the text.

If none matches, the PDF is not added: pass its DOI with `--doi` (see below),
or, for a reference without DOI (older papers, books, reports...), describe it
and attach the PDF:

```
papers add --title "Self-consistent equilibrium ocean tides" --author "Agnew, Duncan C. and Farrell, W. E." \
    --year 1978 --journal "Geophysical Journal International" --attach agnew1978.pdf
```

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
papers add entry.bib --attach esd-4-11-2013.pdf --bibtex papers.bib --filesdir files
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
