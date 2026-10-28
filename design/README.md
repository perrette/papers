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
| Origin records `.papers/origin/<name>-<hash>.bib`, pool ids, legacy `.papers/origin.bib` | exchange.md, sections 2.3 and 3 |
| Three-way merge and its outcomes | exchange.md, section 5 |
| `exchanges.json` (if written, exactly that content) | exchange.md, section 14.4 |
| History store location and layout | history.md, sections 2.1 and 2.2 |
| Objects (pieces of text, the cutting rule, zlib) | history.md, section 2.3 |
| File objects (deleted files) | history.md, section 2.4 |
| States: numbers, keys, kinds, kept `.papers/` files, file operations | history.md, sections 2.5, 3 and 4 |
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

1. `check --auto-key` renames an entry whose key is already the template key (`smith2000` becomes `smith2000b`): [library.md](library.md#open-questions) 4, [bibtex.md](bibtex.md#open-questions) 10.
2. `papers init` does not store `paths`, although v3.md and `docs/configuration.md` say it does: [library.md](library.md#open-questions) 2.
3. Two entries with the same file name: the file is replaced after a prompt; answering no leaves a link to the other entry's file: [library.md](library.md#open-questions) 3.
4. Stale-lock takeover race: two waiters can both remove the lock and both write: [library.md](library.md#open-questions) 16.
5. The machine configuration is written in place, and drops the legacy `pools` names that unsaved earlier-v3 libraries still need: [library.md](library.md#open-questions) 19.
6. A failed block followed by another failed block grows by one warning line at each save: [bibtex.md](bibtex.md#open-questions) 1.
7. A byte order mark becomes a comment and moves into the middle of the file: [bibtex.md](bibtex.md#open-questions) 3.
8. Encoding and line endings follow the platform (bibtex writes, restored history texts): not UTF-8 and `\n` on Windows or with a non-UTF-8 locale: [bibtex.md](bibtex.md#open-questions) 4, [history.md](history.md#open-questions) 9.
9. A merge drops the bare mark of values: `month = jan` (a macro) becomes `month = {jan}`: [bibtex.md](bibtex.md#open-questions) 5.
10. `check --format-name` ignores braces: `John {van der Berg}` becomes `Berg}, John {van der`: [bibtex.md](bibtex.md#open-questions) 19.
11. BibJSON: a `type` or `id` field overwrites the entry type or key (invalid bibtex on the way back): [formats.md](formats.md#open-questions) 1.
12. RIS: a continuation line right after `TY` uses the last tag of the previous record (internal error, or a wrong keyword): [formats.md](formats.md#open-questions) 6.
13. RIS import loses the DOI when `UR` has a DOI URL and another URL and there is no `DO`: [formats.md](formats.md#open-questions) 7.
14. `papers add DIR --recursive` ignores `.ris`, `.json`, `.bib.json`, although the export help says it adds an export back: [formats.md](formats.md#open-questions) 18.
15. A link removed in the pool is added back by a `push` without a pull before it (and `status` says `both changed`): [exchange.md](exchange.md#open-questions) 3.
16. Pool ids of other libraries are relative paths: moving the library loses the match of their records: [exchange.md](exchange.md#open-questions) 12.
17. A state number can be given again after the retention drops the highest one; redo lists, `pools` and `reverts` then name an unrelated state: [history.md](history.md#open-questions) 1.
18. The question before deleting more than `history-size` says the history is dropped; it is not: [history.md](history.md#open-questions) 2.
19. A pool step reverted by undo or redo records no file operations, so undoing that revert in the pool brings no file back: [history.md](history.md#open-questions) 3.
20. When a save adds no state, the operations after the save join the previous command's state: [history.md](history.md#open-questions) 6.
21. Auto-push after undo and redo: the push state is in no redo list, and it records a pending pool link of the undo: [history.md](history.md#open-questions) 8.

### (b) Inconsistencies to decide

1. `.papers/` of the bibtex directory versus of the library directory: `distinct.json` and `origin/` are next to the bibtex, `config.json`, `lock`, `files.json` in the library directory; the history keeps `.papers/` files relative to the bibtex directory, so `files.json` is not kept when they differ; pool ids and `from` use the other directory: [library.md](library.md#open-questions) 1, [history.md](history.md#open-questions) 14 and 17, [exchange.md](exchange.md#open-questions) 12.
2. No file-name length limit; path-safe values keep characters invalid on Windows: [library.md](library.md#open-questions) 8.
3. Values in `config.json` are not type-checked; an invalid library configuration is an unhandled error, an invalid machine configuration is ignored: [library.md](library.md#open-questions) 9.
4. `~` is not expanded in `bibtex` and `filesdir`, but is in `pool` and `default`: [library.md](library.md#open-questions) 11.
5. Relative `default` and `history-dir` are resolved against the current directory: [library.md](library.md#open-questions) 12.
6. The configured pool is not checked again for a pool of its own: [library.md](library.md#open-questions) 13.
7. `papers config pool .` is accepted, `papers init --pool .` is refused: [library.md](library.md#open-questions) 14.
8. The base of a relative pool path differs between `init --pool` and `config pool`: [library.md](library.md#open-questions) 15.
9. Two commands that lock two libraries in opposite orders wait for each other until one fails: [library.md](library.md#open-questions) 17.
10. Field names that differ by case give two fields: [bibtex.md](bibtex.md#open-questions) 2.
11. `@string` references are inlined at the first save: [bibtex.md](bibtex.md#open-questions) 6.
12. Given-name compatibility ignores extra words (`J.` and `John Quincy` are equivalent): [bibtex.md](bibtex.md#open-questions) 8.
13. Tag add, remove and rename are case-sensitive; matching (and `history --revert`) are not: [bibtex.md](bibtex.md#open-questions) 9.
14. A `crossref` to a key removed by a merge is not updated: [bibtex.md](bibtex.md#open-questions) 13.
15. Absolute links in a relative library are not converted at load: [bibtex.md](bibtex.md#open-questions) 14.
16. Keys that differ only by case are both read: [bibtex.md](bibtex.md#open-questions) 20.
17. BibJSON import writes `None`, `True`, `1.0` for JSON null, booleans, floats: [formats.md](formats.md#open-questions) 2.
18. Imported values are not escaped for LaTeX (`&`, `%`, `#`, `_`): [formats.md](formats.md#open-questions) 3.
19. RIS: a final record without `ER` is dropped without a warning: [formats.md](formats.md#open-questions) 5.
20. RIS does not export `urldate` and `translator`, CSL does: [formats.md](formats.md#open-questions) 8.
21. Keywords: export splits on `,`, import on `,` and `;`: [formats.md](formats.md#open-questions) 9.
22. CSL import puts `container-title` in `booktitle` for most types: [formats.md](formats.md#open-questions) 13.
23. `edit --from FILE` keeps relative file paths relative to the library, `add FILE` to the directory of FILE: [formats.md](formats.md#open-questions) 15.
24. `papers list --porcelain` sends the listing to standard error: [formats.md](formats.md#open-questions) 16.
25. `status` ignores a change of entry type: [exchange.md](exchange.md#open-questions) 1.
26. `status` reads the library without repairing pool links, `pull` repairs them: [exchange.md](exchange.md#open-questions) 2.
27. The base of a push of a new entry is the pool entry as inserted, unlike other pushes: [exchange.md](exchange.md#open-questions) 6.
28. The piece cache of `status` can miss an entry removed from the pool: [exchange.md](exchange.md#open-questions) 7.
29. `status` writes the origin file and `exchanges.json` without lock or history step: [exchange.md](exchange.md#open-questions) 8.
30. `status` ignores shared entries without record: [exchange.md](exchange.md#open-questions) 9.
31. Two origin ids for one pool: the records of the second are ignored: [exchange.md](exchange.md#open-questions) 13.
32. Step 4 of the record lookup matches another paper put under a reused pool key: [exchange.md](exchange.md#open-questions) 14.
33. Equivalent changes are not sent; a later rewrite takes the fuller form of either side: [exchange.md](exchange.md#open-questions) 15.
34. `keep` and `update` mean opposite sides in pull and push: [exchange.md](exchange.md#open-questions) 18.
35. The `outside` state does not read `.papers/`: outside edits of `distinct.json` or origin records join the next command's state: [history.md](history.md#open-questions) 5.
36. Several saves of one pool in one command: undo takes back the last pool step only: [history.md](history.md#open-questions) 7.
37. `history-size 0` never removes anything, and `--remove` of the last place does not prune: [history.md](history.md#open-questions) 11.
38. Recent unreferenced objects count in the size but cannot be freed: [history.md](history.md#open-questions) 12.
39. `papers history` ignores a bibtex without library, `papers undo` does not: [history.md](history.md#open-questions) 13.
40. A separate store is recognised by the name of its parent folder: [history.md](history.md#open-questions) 16.

### (c) Rules to pin for compatibility

1. Transliteration to ASCII is a third-party table, chosen at run time for slugify (text-unidecode or Unidecode) and Unidecode for the identity normalization; file names, origin file names, identities and `distinct.json` depend on it: [library.md](library.md#open-questions) 7, [bibtex.md](bibtex.md#open-questions) 17.
2. LaTeX-to-text conversion (`check --encoding unicode`, `add` of a PDF, RIS and CSL-JSON export) is a third-party converter: [bibtex.md](bibtex.md#open-questions) 18, [formats.md](formats.md#open-questions) 4.
3. The table LaTeX decoder defines identity and is wrong for some input; it must be copied exactly: [bibtex.md](bibtex.md#open-questions) 16.
4. Template syntax is Python's format syntax: restrict the contract to `{name}`, `{{`, `}}`?: [library.md](library.md#open-questions) 6.
5. Unknown keys of `config.json` are dropped when papers saves it; a newer implementation's keys are lost: [library.md](library.md#open-questions) 10.
6. No escaping in the `file` field (`;`, JabRef `\:` and `\;`, `C:\x.pdf`): [bibtex.md](bibtex.md#open-questions) 15.
7. CSL export places `publisher` (from school, institution, organization) after `page`: part of the byte-level output: [formats.md](formats.md#open-questions) 14.
8. Origin files under another name are read but never rewritten; their records can win: [exchange.md](exchange.md#open-questions) 11.
9. Separators in stored history paths are those of the operating system: should the store use `/`?: [history.md](history.md#open-questions) 15.
10. `kind` of a state is written but never read: keep it in the contract?: [history.md](history.md#open-questions) 18.
11. The DOI parser of `check --fix-doi` (and of PDF text) is specified nowhere: [bibtex.md](bibtex.md) section 3.5.

### (d) Minor

1. `{journal}` of an entry without journal gives the text `None`: [library.md](library.md#open-questions) 5.
2. `.papers/.gitignore` is written only when the configuration is saved: [library.md](library.md#open-questions) 18.
3. Legacy global location: the code comment and the path disagree: [library.md](library.md#open-questions) 20.
4. The `id` is written into a legacy `.papersconfig.json` in place: [library.md](library.md#open-questions) 21.
5. Install docstring names `.papersconfig.json` as the default target: [library.md](library.md#open-questions) 22.
6. A merge adds fields that are empty in the added entry: [bibtex.md](bibtex.md#open-questions) 7.
7. Key suffix after an upper-case letter or `z`: [bibtex.md](bibtex.md#open-questions) 11.
8. `--keep-old-key` can repeat a former key in `ids`: [bibtex.md](bibtex.md#open-questions) 12.
9. On a key collision, the exact-duplicate check compares raw titles: [bibtex.md](bibtex.md#open-questions) 21.
10. Date text drops zeros before assigning positions (`2013-00-05`): [formats.md](formats.md#open-questions) 10.
11. Names with 4 or more comma parts lose the middle parts: [formats.md](formats.md#open-questions) 11.
12. A CSL name with a suffix and no given name gets a trailing `, `: [formats.md](formats.md#open-questions) 12.
13. The export message names `papers.bib` whatever the bibtex name: [formats.md](formats.md#open-questions) 17.
14. RIS `mastersthesis` comes back as `phdthesis`: [formats.md](formats.md#open-questions) 19.
15. `--field` output keeps colour codes and a leading space with `--no-key`: [formats.md](formats.md#open-questions) 20.
16. Empty `file = {}` fields in records and after a pull: [exchange.md](exchange.md#open-questions) 4.
17. The base of a pull keeps the pool's `ids`: [exchange.md](exchange.md#open-questions) 5.
18. `never pulled` and `not pulled from yet` do not say their difference: [exchange.md](exchange.md#open-questions) 10.
19. `add` from a pool sets the exchange time on the first exchange only: [exchange.md](exchange.md#open-questions) 16.
20. The dialogue calls the base "the pool version", also after a push: [exchange.md](exchange.md#open-questions) 17.
21. A rename onto a key with a leftover record replaces that record: [exchange.md](exchange.md#open-questions) 19.
22. An unreachable line in revert: [history.md](history.md#open-questions) 4.
23. "deleted again (kept in the history)" is printed with `keep-deleted-files` false: [history.md](history.md#open-questions) 10.
