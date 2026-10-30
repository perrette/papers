# Proposal: fetching the free PDF of an entry

Status: proposal, for discussion (issue to be linked here). Not implemented.
When it is agreed, the rules move into the specification (library.md for
the files, formats.md for the output) and this file is removed.

## What it does

papers finds a free PDF of a paper from its identifiers (DOI, arXiv id),
downloads it, checks that it is a PDF, and attaches it to the entry as
`papers file attach` does (the `files` setting decides move, copy or link;
the name template names it). Only open-access sources are used: nothing
that gets around a paywall.

## Commands

- `papers file fetch KEY...`: fetch and attach the PDF of each entry.
  `--missing`: every entry that has no file. `--dry-run`: say which PDF
  would be downloaded, from where, and which version it is.
- `papers add --doi DOI --fetch-pdf`: add the entry and fetch its PDF.
- `papers fetch --pdf DOI`: download the PDF of a DOI into the current
  directory (or `-o FILE`), without a library, as `papers fetch DOI` prints
  the bibtex without a library.

Each command says where the PDF came from and which version it is:
`smith2020: files/smith_2020_ocean.pdf (published version, from
journals.example.org)`.

## Where the PDF comes from

1. **OpenAlex** (`GET https://api.openalex.org/works/doi:<DOI>`, one
   request): the open-access locations of the work (publisher, repositories,
   PubMed Central, arXiv). Each location says its version: published,
   accepted (the author's final manuscript) or submitted (preprint). It is
   the data of Unpaywall, which OpenAlex now runs.
2. **The publisher's page** (`https://doi.org/<DOI>`, then the article
   page): the `citation_pdf_url` tag that many publishers put on the page
   of an article (the tag Google Scholar reads). The PDF the publisher
   itself links is the published version.
3. **arXiv**: an entry with an arXiv id has its PDF at
   `https://arxiv.org/pdf/<id>` (a preprint, unless the journal is arXiv).

## Which PDF

The aim is the version of record, the one a reader cites:

1. a published version, from the publisher's page (2), or from an OpenAlex
   location of version published (1);
2. else an accepted manuscript;
3. else a submitted version or the arXiv preprint (3).

A PDF that is not the published version is attached with its version in
the message (`accepted manuscript, from repository.example.edu`), so that
the user knows. `--version published` refuses the others.

What is downloaded must be a PDF (the first bytes `%PDF`, as papers already
checks for downloads): a publisher that answers with a login page or a
challenge gives no file, and the command says so and prints the link to open
in a browser.

## Supplements

A supplement is attached only when a source names it as such: some
publishers list supplementary PDFs on the article page (as links to
`...-supplement.pdf`, Copernicus for example, or with a
`citation_supplementary_material` tag). With `--supplements`, those PDFs are
attached too, named as other files of the entry (`<name>--<label>.pdf`).
Only PDFs; data sets and other files are left out. Off by default: the
detection depends on the publisher.

## No duplicate downloads

A second pass (`papers file fetch KEY --supplements` after `papers file fetch
KEY`) must not download or attach the same PDF again:

1. The main PDF is not fetched for an entry that already has a PDF, unless
   `--again` is given (`KEY: has a PDF already (--again to fetch it anyway)`).
   The supplements are still fetched.
2. A downloaded file is compared by checksum (sha256) with the files of the
   entry before it is attached; the same content is not attached twice (as
   `file attach` already refuses it).
3. A cache of the downloads, on the machine (papers' cache, next to the
   answers of crossref and OpenAlex; nothing in the library): each URL with
   the checksum and size of the file it gave. Before a URL in the cache is
   downloaded again:
   - the entry has a file with that checksum: nothing is done;
   - a file of the library has it (the checksums of `.papers/files.json`,
     the files of other entries): that file is attached, without a
     download, and the message says which entry has it too;
   - otherwise: the URL is downloaded.

Websites do not give a checksum before the download, so the cache is what
lets papers know what a URL gives without fetching it.

## Network and settings

- At most one request a second to each site; the answers of OpenAlex are
  cached as those of the search (`papers.cache`).
- The OpenAlex key and the email address are those of `--openalex`
  (`OPENALEX_API_KEY`, `PAPERS_MAILTO`).
- Publishers answer programs less than browsers: papers says what it is in
  its user agent, and gives the link when a download is refused.

## Open questions

1. Command names: `papers file fetch`, `add --fetch-pdf`, `papers fetch
   --pdf`?
2. Supplements: detect only the publishers that tag them, or also links
   whose name says supplement?
3. `--missing` on a large library: one request to OpenAlex per entry (about
   100 a day without a key): ask before more than, say, 50?

## Related

- Papers Desktop (papers-rs) already finds a free PDF with OpenAlex when a
  paper is added from a journal page (`openalex_free_pdf`, the
  `best_oa_location`, then any open location), and opens the link in the
  browser when the download fails.
