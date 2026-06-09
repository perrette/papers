# Quickstart

This tool's interface is built like `git`, with a main command `papers` and a
range of subcommands. This page walks through the most common first steps.

## Extract PDF metadata and add to library

Start with a PDF of your choice (modern enough to have a DOI, e.g. anything
from the Copernicus publications). For the sake of the example, one of mine:
<https://www.earth-syst-dynam.net/4/11/2013/esd-4-11-2013.pdf>

Extract the PDF metadata (DOI-based if available, otherwise crossref, or google
scholar if so specified):

```
$> papers extract esd-4-11-2013.pdf
@article{Perrette_2013,
doi = {10.5194/esd-4-11-2013},
url = {https://doi.org/10.5194%2Fesd-4-11-2013},
year = 2013,
month = {jan},
publisher = {Copernicus {GmbH}},
volume = {4},
number = {1},
pages = {11--29},
author = {M. Perrette and F. Landerer and R. Riva and K. Frieler and M. Meinshausen},
title = {A scaling approach to project regional sea level rise and its uncertainties},
journal = {Earth System Dynamics}
}
```

Add the PDF to your `papers.bib` library, and rename a copy of it in a files
directory `files`:

```
$> papers add esd-4-11-2013.pdf --rename --copy --bibtex papers.bib --filesdir files --info
INFO:papers:found doi:10.5194/esd-4-11-2013
INFO:papers:new entry: perrette_landerer2013
INFO:papers:mv /home/perrette/playground/papers/esd-4-11-2013.pdf files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf
INFO:papers:renamed file(s): 1
```

(the `--info` argument asks for the above output information to be printed out
to the terminal)

See [Adding entries](adding-entries.md) for the full range of ways to add
entries, and [Renaming files and keys](renaming.md) for how to specify file
naming patterns.

## List entries

Pretty listing by default (otherwise pass `--plain` for plain bibtex):

```
$> papers list
Perrette2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1)
```

See [Listing and searching](listing.md) for the full power of `papers list`.

## Make settings persistent

In the common case where the bibtex, files directory and naming formats do not
change, install `papers` so that you don't need to pass them every time:

```
papers install --bibtex papers.bib --filesdir files
```

See [Configuration and install](configuration.md) for details.

!!! tip
    Consult the inline help (`papers --help`, `papers <command> --help`) for
    more detailed documentation of every option.
