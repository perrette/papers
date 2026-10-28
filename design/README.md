# papers: specification

These files specify what papers does with a library on disk: the files it
reads and writes, their formats, and the rules that decide their content.
They are written from the code of the Python version (papers 3).

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

- [v3.md](v3.md) is the older design document of papers 3. It is kept for
  its rationale. Where it differs from these files, these files describe
  the code.
- The user documentation (`docs/*.md`) describes the commands and their
  options.

Not covered: fetching metadata from the network, the extraction of
metadata from PDF files (including the DOI parser, see the open
questions), the screens of the interactive dialogues.

## How to read Contract and Free

Each file marks its rules with one of two labels:

- **Contract**: file names, JSON keys, value formats, and the rules that
  decide what is written or what a stored value means. Two
  implementations must read and write them identically.
- **Free**: messages, prompts, the order of internal steps that leaves the
  same result on disk, caches, thresholds marked as such. An
  implementation may do it differently, as long as the contracts hold.

A rule that is not labelled is contract. Each open question names the
code (file and line) that the rule was taken from.

## The compatibility contract

Every on-disk format and name that two implementations must share:

| What | Defined in |
|---|---|
| Library layout: the library directory, `.papers/` and which files are in the `.papers/` of the library directory or of the bibtex directory | library.md, Layout |
| `.papers/.gitignore` | library.md, Layout |
| `.papers/config.json`: format, keys, which keys are written, reading, the `id` field, relative paths | library.md, The library configuration |
| Legacy `.papersconfig.json` and `papersconfig.json` | library.md, Legacy configuration files |
| Machine configuration: location and keys | library.md, The machine configuration |
| Settings: names, types, defaults, precedence | library.md, Settings |
| Finding the library of a command (`-C`, search upwards, `--bibtex`) | library.md, Finding the library of a command |
| The `pool` setting and the states self-contained and shallow | library.md, Pools and shallow libraries |
| File names of the files directory, name and key templates, slugify, path safety | library.md, The files directory; Name and key templates; Path safety |
| The lock file `.papers/lock` and its protocol | library.md, The lock |
| Bibtex reading and output format (blocks, order, layout, values) | bibtex.md, sections 1 to 3; reference test `tests/sortformat/varied.bib` and `varied.expected.bib` |
| `file` field syntax | bibtex.md, section 5 |
| `keywords` field syntax (tags) | bibtex.md, section 6 |
| `ids` field syntax, `crossref` on renames | bibtex.md, section 7 |
| Key suffix rule | bibtex.md, section 8 |
| Same-paper rule and text normalization (they decide `distinct.json` matches) | bibtex.md, section 9 |
| `.papers/distinct.json` | bibtex.md, section 9.4 |
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

## Open questions

The open questions of the five files, grouped. Each file keeps its own
list; the numbers below are those of that list. An item found in several
files is listed once.

### (a) Likely bugs

Behaviour that loses data, breaks a link, or contradicts the docs.

1. The machine configuration drops the legacy `pools` names that unsaved earlier-v3 libraries still need: [library.md](library.md#open-questions) 15.
2. Files read in the platform's encoding (and without dropping a byte order mark), although papers writes them as UTF-8: configuration files, `distinct.json`, origin files and the pool's `config.json`; raw UTF-8 from another implementation is misread on Windows or with a non-UTF-8 locale: [library.md](library.md#open-questions) 19, [bibtex.md](bibtex.md#open-questions) 17, [exchange.md](exchange.md#open-questions) 20.
3. On a file system without hard links, a fresh lock renamed aside during a stale-lock takeover cannot be put back and is lost: [library.md](library.md#open-questions) 20.
4. `status` computes the origin file name from the pool id alone: for a file named after the pool folder it compares with an empty text and misses a change to the records alone: [exchange.md](exchange.md#open-questions) 19.
5. The upgrade of numbered states rewrites `pools` links within one store only: a library with `history-separate` keeps numbers in its links to a pool in the other store, and undo and redo then leave the pool alone: [history.md](history.md#open-questions) 13.
6. A file brought back by `file fix` from the history has a file object as source, not a `deleted` entry: retention or a change of `history-dir` can remove it, and undo then leaves the copy: [history.md](history.md#open-questions) 14.

### (b) Inconsistencies to decide

1. `.papers/` of the bibtex directory versus of the library directory: `distinct.json` and `origin/` are next to the bibtex, `config.json`, `lock`, `files.json` in the library directory; the history keeps `.papers/` files relative to the bibtex directory, so `files.json` is not kept when they differ; `from` uses the other directory: [library.md](library.md#open-questions) 1, [history.md](history.md#open-questions) 8 and 11.
2. No file-name length limit; path-safe values keep characters invalid on Windows: [library.md](library.md#open-questions) 5.
3. Values in `config.json` are not type-checked; an invalid library configuration is an unhandled error, an invalid machine configuration is ignored: [library.md](library.md#open-questions) 6.
4. `~` is not expanded in `bibtex` and `filesdir`, but is in `pool` and `default`: [library.md](library.md#open-questions) 8.
5. Relative `default` and `history-dir` are resolved against the current directory: [library.md](library.md#open-questions) 9.
6. The configured pool is not checked again for a pool of its own: [library.md](library.md#open-questions) 10.
7. `papers config pool .` is accepted, `papers init --pool .` is refused: [library.md](library.md#open-questions) 11.
8. The base of a relative pool path differs between `init --pool` and `config pool`: [library.md](library.md#open-questions) 12.
9. Two commands that lock two libraries in opposite orders wait for each other until one fails: [library.md](library.md#open-questions) 13.
10. Field names that differ by case give two fields: [bibtex.md](bibtex.md#open-questions) 1.
11. `@string` references are inlined at the first save: [bibtex.md](bibtex.md#open-questions) 2.
12. Given-name compatibility ignores extra words (`J.` and `John Quincy` are equivalent): [bibtex.md](bibtex.md#open-questions) 4.
13. Tag add, remove and rename are case-sensitive; matching (and `history --revert`) are not: [bibtex.md](bibtex.md#open-questions) 5.
14. A `crossref` to a key removed by a merge is not updated: [bibtex.md](bibtex.md#open-questions) 8.
15. Absolute links in a relative library are not converted at load: [bibtex.md](bibtex.md#open-questions) 9.
16. Keys that differ only by case are both read: [bibtex.md](bibtex.md#open-questions) 14.
17. `and` inside braces is split three ways: name formatting at brace depth 0, the identity and name equivalence also inside braces, the family names of the key and name templates again on ` and ` and the first comma: [bibtex.md](bibtex.md#open-questions) 16.
18. Imported values are not escaped for LaTeX (`&`, `%`, `#`, `_`): [formats.md](formats.md#open-questions) 1.
19. RIS: a final record without `ER` is dropped without a warning: [formats.md](formats.md#open-questions) 3.
20. RIS does not export `urldate` and `translator`, CSL does: [formats.md](formats.md#open-questions) 4.
21. Keywords: export splits on `,`, import on `,` and `;`: [formats.md](formats.md#open-questions) 5.
22. CSL import puts `container-title` in `booktitle` for most types: [formats.md](formats.md#open-questions) 9.
23. `edit --from FILE` keeps relative file paths relative to the library, `add FILE` to the directory of FILE: [formats.md](formats.md#open-questions) 11.
24. `papers list --porcelain` sends the listing to standard error: [formats.md](formats.md#open-questions) 12.
25. Export files other than bibtex (RIS, CSL-JSON, BibJSON) get the platform's line ends, the bibtex LF: [formats.md](formats.md#open-questions) 16.
26. `status` ignores a change of entry type: [exchange.md](exchange.md#open-questions) 1.
27. `status` reads the library without repairing pool links, `pull` repairs them: [exchange.md](exchange.md#open-questions) 2.
28. The base of a push of a new entry is the pool entry as inserted, unlike other pushes: [exchange.md](exchange.md#open-questions) 5.
29. The piece cache of `status` can miss an entry removed from the pool: [exchange.md](exchange.md#open-questions) 6.
30. `status` writes the origin file and `exchanges.json` without lock or history step: [exchange.md](exchange.md#open-questions) 7.
31. `status` ignores shared entries without record: [exchange.md](exchange.md#open-questions) 8.
32. Two path ids for one pool: one exchange moves only the first to the identifier; the records of the other wait for the next exchange: [exchange.md](exchange.md#open-questions) 11.
33. Step 4 of the record lookup matches another paper put under a reused pool key: [exchange.md](exchange.md#open-questions) 12.
34. Equivalent changes are not sent; a later rewrite takes the fuller form of either side: [exchange.md](exchange.md#open-questions) 13.
35. `keep` and `update` mean opposite sides in pull and push: [exchange.md](exchange.md#open-questions) 16.
36. `papers-pool-path` is written only when records move from a path id: a pool that has its identifier at the first exchange gets a file named `pool-<hash>.bib`, while `docs/pools.md` says it is named after the pool folder: [exchange.md](exchange.md#open-questions) 18.
37. The `outside` state does not read `.papers/`: outside edits of `distinct.json` or origin records join the next command's state: [history.md](history.md#open-questions) 2.
38. Several saves of one pool in one command: undo takes back the last pool step only: [history.md](history.md#open-questions) 3.
39. `history-size 0` never removes anything, and `--remove` of the last place does not prune: [history.md](history.md#open-questions) 5.
40. Recent unreferenced objects count in the size but cannot be freed: [history.md](history.md#open-questions) 6.
41. `papers history` ignores a bibtex without library, `papers undo` does not: [history.md](history.md#open-questions) 7.
42. A separate store is recognised by the name of its parent folder: [history.md](history.md#open-questions) 10.

### (c) Rules to pin for compatibility

1. Transliteration to ASCII is a third-party table, chosen at run time for slugify (text-unidecode or Unidecode) and Unidecode for the identity normalization; file names, origin file names, identities and `distinct.json` depend on it: [library.md](library.md#open-questions) 4, [bibtex.md](bibtex.md#open-questions) 12.
2. LaTeX-to-text conversion (`check --encoding unicode`, `add` of a PDF, RIS and CSL-JSON export) is a third-party converter: [bibtex.md](bibtex.md#open-questions) 13, [formats.md](formats.md#open-questions) 2.
3. The table LaTeX decoder defines identity and is wrong for some input; it must be copied exactly: [bibtex.md](bibtex.md#open-questions) 11.
4. Template syntax is Python's format syntax: restrict the contract to `{name}`, `{{`, `}}`?: [library.md](library.md#open-questions) 3.
5. Unknown keys of `config.json` are dropped when papers saves it; a newer implementation's keys are lost: [library.md](library.md#open-questions) 7.
6. No escaping in the `file` field (`;`, JabRef `\:` and `\;`, `C:\x.pdf`): [bibtex.md](bibtex.md#open-questions) 10.
7. CSL export places `publisher` (from school, institution, organization) after `page`: part of the byte-level output: [formats.md](formats.md#open-questions) 10.
8. BibJSON import: a `null` inside an array gives the text `None`, a number with a fraction the Python text of the number (`1e-07`): [formats.md](formats.md#open-questions) 17.
9. Origin files under another name are read; a second file of the same pool id is never rewritten nor removed, and a record dropped from the computed file comes back from it: [exchange.md](exchange.md#open-questions) 10.
10. Separators in stored history paths are those of the operating system, and they enter the state identifiers (another identifier on Windows): should the store use `/`?: [history.md](history.md#open-questions) 9.
11. `kind` of a state is written but never read: keep it in the contract?: [history.md](history.md#open-questions) 12.
12. The DOI parser of `check --fix-doi` (and of PDF text) is specified nowhere: [bibtex.md](bibtex.md) section 3.5.

### (d) Minor

1. `{journal}` of an entry without journal gives the text `None`: [library.md](library.md#open-questions) 2.
2. `.papers/.gitignore` is written only when the configuration is saved: [library.md](library.md#open-questions) 14.
3. Legacy global location: the code comment and the path disagree: [library.md](library.md#open-questions) 16.
4. The `id` is written into a legacy `.papersconfig.json` in place: [library.md](library.md#open-questions) 17.
5. Install docstring names `.papersconfig.json` as the default target: [library.md](library.md#open-questions) 18.
6. A merge adds fields that are empty in the added entry: [bibtex.md](bibtex.md#open-questions) 3.
7. Key suffix after an upper-case letter or `z`: [bibtex.md](bibtex.md#open-questions) 6.
8. `--keep-old-key` can repeat a former key in `ids`: [bibtex.md](bibtex.md#open-questions) 7.
9. On a key collision, the exact-duplicate check compares raw titles: [bibtex.md](bibtex.md#open-questions) 15.
10. Date text drops zeros before assigning positions (`2013-00-05`): [formats.md](formats.md#open-questions) 6.
11. Names with 4 or more comma parts lose the middle parts: [formats.md](formats.md#open-questions) 7.
12. A CSL name with a suffix and no given name gets a trailing `, `: [formats.md](formats.md#open-questions) 8.
13. The export message names `papers.bib` whatever the bibtex name: [formats.md](formats.md#open-questions) 13.
14. RIS `mastersthesis` comes back as `phdthesis`: [formats.md](formats.md#open-questions) 14.
15. `--field` output keeps colour codes and a leading space with `--no-key`: [formats.md](formats.md#open-questions) 15.
16. RIS: the stray-line step wants a space or end of line after `-`, the reader does not, so `TI  -x` right after `TY` is dropped: [formats.md](formats.md#open-questions) 18.
17. Empty `file = {}` fields in records and after a pull: [exchange.md](exchange.md#open-questions) 3.
18. The base of a pull keeps the pool's `ids`: [exchange.md](exchange.md#open-questions) 4.
19. `never pulled` and `not pulled from yet` do not say their difference: [exchange.md](exchange.md#open-questions) 9.
20. `add` from a pool sets the exchange time on the first exchange only: [exchange.md](exchange.md#open-questions) 14.
21. The dialogue calls the base "the pool version", also after a push: [exchange.md](exchange.md#open-questions) 15.
22. A rename onto a key with a leftover record replaces that record: [exchange.md](exchange.md#open-questions) 17.
23. An unreachable line in revert: [history.md](history.md#open-questions) 1.
24. "deleted again (kept in the history)" is printed with `keep-deleted-files` false: [history.md](history.md#open-questions) 4.
