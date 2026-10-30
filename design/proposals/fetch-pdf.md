# Proposal: fetching the free PDF of an entry

Status: implemented in #212 (issue #211). The rules are in the
specification: library.md, "The free PDF of an entry" (which entries, the
order of the links, the supplements, the cache of the downloads), and
formats.md (the porcelain lines of `papers file fetch`, `papers fetch
--pdf`). The user documentation is in docs/files.md.

## Decisions

1. Commands: `papers file fetch KEY...` (`--missing`, `--dry-run`,
   `--version published|accepted|any`, `--supplements`, `--again`,
   `-y/--yes`), `papers add --doi DOI --fetch-pdf`, `papers fetch --pdf
   DOI... [-o FILE]` (`-o` takes one DOI; an existing file is not
   replaced). An arXiv id works as well as a DOI.
2. Order: the `citation_pdf_url` of the publisher's page, then the
   open-access locations of OpenAlex by version (published, accepted,
   submitted), then arXiv. The publisher's page is read first, and
   OpenAlex only when the publisher gives no PDF. `--version` is the least
   final version accepted.
3. Supplements (only with `--supplements`): the PDF links of the article
   page whose URL or text contains "suppl" (case-insensitive), and the
   `citation_supplementary_material` tags. PDFs only, attached as
   `<name>--<label>.pdf`.
4. `--missing` asks before more than 50 entries with a DOI when
   `OPENALEX_API_KEY` is not set (`-y/--yes` does not ask); without a
   terminal it stops and says how to proceed.
5. An entry that got no PDF is an error (the links to open in a browser);
   the others are attached and saved, and the command exits with 1. `add
   --fetch-pdf` adds the entry all the same.
6. No duplicates, as below. Nothing about the source is written in the
   library (no field): the URLs are only in the cache of the machine.

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
