# papers: specification

These files specify what papers does with a library on disk: the files it
reads and writes, their formats, and the rules that decide their content.
They describe papers 3. They are language agnostic: they say what happens
to the files and on the command line, not how a program does it.

Their purpose: a second implementation (in Rust) and a desktop
application (Papers Desktop) will work on the same libraries and the same
history store as the Python version, at the same time. Each must read
what the other writes, write what the other reads, and undo what the
other did. The files say which rules this requires and which ones an
implementation may choose.

## Files

- [library.md](library.md): the library on disk, `.papers/config.json`,
  the machine configuration, the settings, how a command finds its
  library, pools and shallow libraries (the setting), the files directory,
  the name and key templates, path safety, the lock.
- [bibtex.md](bibtex.md): reading and writing the bibtex, the `file`,
  `keywords`, `ids` and `crossref` fields, LaTeX and Unicode, key
  collisions, the same-paper rule, `distinct.json`, the two-way merge.
- [formats.md](formats.md): RIS, CSL-JSON and BibJSON, the layout of
  `papers export`, `papers list` output, `--porcelain`, exit codes.
- [exchange.md](exchange.md): the exchanges with a pool: origin records,
  the three-way merge, `pull`, `push`, `sync`, automatic pushes, `add`
  from a pool, `papers status`, `exchanges.json`, the files of a shallow
  library.
- [history.md](history.md): the history store, states, recording, undo,
  redo, restore, `history --revert`, the links with a pool's history,
  retention, `.papers/files.json`, the parse cache.

Other documents:

- [tests.md](tests.md): the tests of each section.
- [data/](data/): the two data tables that rules refer to, each with its
  origin and license in its header lines:
  - [latex-characters.tsv](data/latex-characters.tsv): LaTeX text of
    characters (bibtex.md 4.1, 4.2), from the W3C table of MathML
    characters, by way of python-bibtexparser 1.x;
  - [ascii-transliteration.tsv](data/ascii-transliteration.tsv): ASCII
    transliteration of about 41,000 characters, all scripts, Chinese
    included (bibtex.md 9.1, library.md Slugify), from Unidecode (GNU
    GPL v2 or later, unlike the rest of papers).

  `scripts/spec_tables.py` writes them from the code, and a test checks
  that they are the same.
- [v3.md](v3.md) is the older design document of papers 3. It is kept for
  its rationale. Where it differs from these files, these files are
  right.
- The user documentation (`docs/*.md`) describes the commands and their
  options.

Not covered: fetching metadata from the network, the extraction of
metadata from PDF files (its DOI parser is described, as information, in
bibtex.md section 3.6), the screens of the interactive dialogues.

## How to read Contract and Free

Each file marks its rules with one of two labels:

- **Contract**: file names, JSON keys, value formats, and the rules that
  decide what is written or what a stored value means. Two
  implementations must read and write them identically.
- **Free**: messages, prompts, the order of internal steps that leaves the
  same result on disk, caches, thresholds marked as such. An
  implementation may do it differently, as long as the contracts hold.

A rule that is not labelled is contract.

## The compatibility contract

Every on-disk format and name that two implementations must share:

| What | Defined in |
|---|---|
| Library layout: the library directory and `.papers/` | library.md, Layout |
| `.papers/.gitignore` | library.md, Layout |
| `.papers/config.json`: format, keys, which keys are written, reading, the `id` field, relative paths | library.md, The library configuration |
| Legacy `.papersconfig.json` and `papersconfig.json` | library.md, Legacy configuration files |
| Machine configuration: location and keys | library.md, The machine configuration |
| Settings: names, types, defaults, precedence | library.md, Settings |
| Finding the library of a command (`-C`, search upwards, `--bibtex`) | library.md, Finding the library of a command |
| The `pool` setting and the states self-contained and shallow | library.md, Pools and shallow libraries |
| File names of the files directory, name and key templates, slugify, path safety | library.md, The files directory; Name and key templates; Path safety |
| The lock file `.papers/lock` and its protocol | library.md, The lock |
| Bibtex reading and output format (blocks, order, layout, values) | bibtex.md, sections 1 to 3 |
| `file` field syntax | bibtex.md, section 5 |
| `keywords` field syntax (tags) | bibtex.md, section 6 |
| `ids` field syntax, `crossref` on renames | bibtex.md, section 7 |
| Key suffix rule | bibtex.md, section 8 |
| Same-paper rule and text normalization (they decide `distinct.json` matches) | bibtex.md, section 9 |
| `.papers/distinct.json` | bibtex.md, section 9.4 |
| The character table and the ASCII transliteration table | `data/latex-characters.tsv`, `data/ascii-transliteration.tsv` |
| Origin records `.papers/origin/<name>-<hash>.bib`, pool ids (library identifiers, path ids), `papers-pool-path`, legacy `.papers/origin.bib` | exchange.md, sections 2.3 and 3 |
| Three-way merge and its outcomes | exchange.md, section 5 |
| `exchanges.json` (if written, exactly that content) | exchange.md, section 14.4 |
| History store location and layout | history.md, sections 2.1 and 2.2 |
| Objects (pieces of text, the cutting rule, zlib) | history.md, section 2.3 |
| File objects (deleted files) | history.md, section 2.4 |
| States: identifiers, keys, kinds, kept `.papers/` files, file operations | history.md, sections 2.5, 3 and 4 |
| `heads.json` | history.md, section 2.7 |
| Writing order and retention (what may be removed) | history.md, sections 2.8 and 9.2 |
| Separate stores | history.md, section 2.6 |
| Project id of a library and of a bibtex without library | history.md, section 5.1 |
| `.papers/files.json` | history.md, section 10 |
| Parse cache: another implementation must not write into `<cache dir>/parsed/` | history.md, section 11 |
| Export formats: CSL-JSON, RIS, BibJSON, the JSON text format, `papers export` layout | formats.md, sections 3, 4, 5, 8 and 9 |
| `papers list --format`, `-K`, `--field` | formats.md, section 6 |
| `--porcelain` lines and exit codes | formats.md, section 7 |

## Tests

[tests.md](tests.md) lists, for each section, the test cases of the Python
version that check its rules. A second implementation can be checked
against the same cases: they say what is on disk and on the command line
after each command. The bibtex output format has a reference pair of
files, `tests/sortformat/varied.bib` and the expected output
`varied.expected.bib`.

## Open questions

Each file keeps its list of open questions, with how each one was
resolved (the pull request or the decision). They came in four groups:
likely bugs (fixed), inconsistencies (fixed, or kept and documented),
rules to pin for compatibility (pinned in the rule text) and minor items
(fixed, or kept as correct behaviour).

None is open.
