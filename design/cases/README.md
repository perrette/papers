# Conformance cases

What an implementation of papers does, as cases: a library before, a command, and what it
prints and leaves after. They are the language-neutral side of the tests of papers-cli
([../tests.md](../tests.md) lists those): the specification (`design/*.md`) says what an
implementation must do, the cases check it by running the program.

papers-cli (Python) is the reference: the expected results are recorded by running it, and
its CI runs the cases (`python design/cases/run.py --papers papers`). Another implementation
(papers-rs, the Rust one; Papers Desktop, which works on the same libraries) runs the same
cases with `--papers CMD`, with nothing from Python.

Each case says which sections of the specification it exercises (`sections`), which of the
tests of papers-cli check the same thing (`tests`: those that `design/tests.md` lists for a section, mostly),
and which of the outputs of each step the specification makes Contract and which Free (see
"Contract and Free"). The coverage table at the end says which contract each case checks.

Shared by the implementations, so part of the contract: the bibtex written,
`.papers/config.json` and the global configuration, the history and the pool's
steps, the lock, the `--porcelain` lines, the keys and file names, and the two tables
of `design/data/` (characters of LaTeX, ASCII transliteration: the cases check them by
what they give). Private to each: caches (the parse cache).

The cases are plain files, and the two tools are Python 3 scripts with the
standard library only (`conformance.py` is shared by both). The paths below are
from the root of the repository:

```
python design/cases/run.py --papers papers                        # an implementation on all the cases
python design/cases/run.py --papers path/to/other 'list/*'        # on the cases that match
python design/cases/run.py --papers papers --contract-only        # only what the specification makes Contract
python design/cases/run.py --papers papers --section 'formats.md#7'  # the cases of a section
python design/cases/run.py --papers papers --test test_undo.py    # the cases that list a test of design/tests.md
python design/cases/record.py --papers papers [CASE...]           # (re)record the expected results
```

Add `-j N` to run N cases at once (they are independent). Running papers needs
`pip install ".[ris]"` (the RIS cases need `rispy`). The expected output is recorded with
Python 3.14: the usage messages of argparse (Free, but compared in a full run) differ between
versions of Python in how they wrap lines and quote choices, so run papers itself with 3.14
for a full comparison, or use `--contract-only`, which passes with any version.
The cases that need the network (`requires`) are skipped unless `--with network` says it is there.

`run.py` prints `PASS`/`FAIL` per case, and for a failure the unified diff of
the first difference (`-a`: all of them), then a summary; the exit status is 0
when all pass. By default everything is compared byte for byte. With
`--contract-only` only the Contract parts are (exit codes, the files after, the
outputs of the steps that are Contract); a difference in a Free output is
reported as a note (`PASS name (Free differences: step 1 stdout)`; `-a` shows
them) and the summary counts the cases that have some. `--section PATTERN`
(repeatable) keeps the cases that exercise a section (see "Sections"), `--test
PATTERN` the cases that list a test of `design/tests.md` (a part of its id).
`record.py` runs each case twice and writes the results only if the two runs
agree. `CASE` is a glob on the name of the case (`group/name`). `--list` lists
the cases with their sections, `--sections` the sections with their cases,
`--tests` the tests with their cases, `--keep` keeps the sandboxes of the run.

## A case

`design/cases/<group>/<name>/` (the groups are the commands: `init`, `config`,
`status`, `list`, `add`, `edit`, `rm`, `tag`, `file`, `export`, `history` (undo,
redo, restore), `exchange` (pull, push, auto-push), `errors`; and the topics of
the specification that no single command owns: `porcelain` (the `--porcelain`
lines of the writing commands), `bibtex` (the format of the file), `lock`; `config` has the
cases of the library configuration and of the place of `.papers/`):

```
case.json        what to run (written by hand)
before/          the working folder before: a tree of files (optional, empty by default)
before-home/     the HOME of the user before: config/, data/, home/ (optional)
stdin/NN.txt     the standard input of step NN, when a step has one
expected/        what the reference did (written by record.py)
    NN.stdout        standard output of step NN (absent: empty)
    NN.stderr        standard error of step NN (absent: empty)
    exit.json        the exit codes of the steps: [0, 1, ...]
    work/            the working folder after: all the files, with their contents
    home/            the HOME after (config/, data/, home/, see below)
```

`case.json`:

```json
{
  "description": "what the case shows",
  "sections": ["formats.md#7.2", "library.md#the-library-configuration/keys"],
  "tests": ["tests/test_spec_formats.py::TestPorcelainLines::test_order"],
  "ignore": ["home/data/history/*"],
  "requires": ["network"],
  "steps": [
    {"argv": ["init", "lib"]},
    {"argv": ["list", "-K"], "cwd": "lib"},
    {"argv": ["edit", "perrette2013", "--from", "-"], "stdin_file": "stdin/03.txt"},
    {"argv": ["restore", "$STATE2"]},
    {"argv": ["tag", "-", "--add", "x"], "stdin": "doe2019\n"},
    {"argv": ["list", "--porcelain"], "contract": ["stderr"], "wait": 1.1}
  ]
}
```

- `steps`: the commands, run in order, each in a fresh process. `argv` is the
  arguments after the program (the program itself is not part of it),
  `cwd` the working folder of the step relative to `before/` (default `.`),
  `stdin_file` (a file of the case) or `stdin` (a string) the standard input;
  without either, the standard input is empty and not a terminal (`/dev/null`). A step
  can name a state of the history by `$STATEn` in its arguments (see "States").
  All the steps run, whatever their exit code: the standard output, standard
  error and exit code of each are compared, then the trees after the last one.
- `requires`: capabilities the case needs (e.g. `network`, `pdf`). `run.py` and
  `record.py` skip the case unless `--with network,pdf` says they are there.
  The first set of cases needs none: it is offline, with no PDF.
- `description`: free text.
- `sections`: required, a non-empty list of the sections of the specification that the
  case exercises (see "Sections").
- `tests`: optional, the tests of papers-cli that `design/tests.md` lists for these sections
  and that check what the case checks (`tests/FILE.py::Class::test`: where the match is
  obvious, not all of them). The suite so refers to the specification's own tests: an
  implementation that has the same rule can read there what papers-cli does about it.
- `contract` (of a step): which of `"stdout"`, `"stderr"` the specification makes
  Contract for that step, replacing the default rules (see "Contract and Free"). `[]`:
  neither.
- `ignore`: globs on the files after (`work/...`, `home/...`, as in `expected/`) that the
  case does not compare. Used by the `exchange` cases, and `porcelain/config-pool`, for
  `home/data/history/*`: the origin records they leave hold times (`papers-time`), and
  the history cuts the bibtex into pieces by its content, so the pieces differ from one run
  to the next (and the objects that hold them, and the states that name them). The
  identifiers of the states in the outputs are replaced as everywhere (`$STATEn`).
- `wait` (of a step): seconds to wait before the step. The exchanges compare times with a
  resolution of one second (without it a pull right after a push in the same second can
  miss a change; the cases of `exchange` wait 1.1 s).

Folders that are empty are kept as an empty file `.emptydir` (git does not
track folders), and `.gitignore` is stored as `.gitignore.spec` (the
`.papers/.gitignore` of a library contains `*`, which would hide its
neighbours). Both are only about storing: the tools restore the real names.

## Sections

`sections` refer to the files of the specification (`design/*.md`) by a stable
reference, `FILE.md#REF`:

- `formats.md`, `bibtex.md`, `history.md`, `exchange.md` number their sections: `REF` is
  the number of the heading, `formats.md#7`, `formats.md#7.2`, `bibtex.md#8`,
  `history.md#6.2`, `exchange.md#12`.
- `library.md` has no numbers: `REF` is the heading of the `##` section up to its colon, in
  lower case with hyphens for the spaces (`library.md#the-library-configuration`,
  `library.md#finding-the-library-of-a-command`, `library.md#the-lock`), and, for a `###`
  heading under it, `/` and the same form of that heading
  (`library.md#the-library-configuration/which-keys-papers-writes`,
  `library.md#settings/precedence`, `library.md#layout/papersgitignore`: the characters
  that are not letters, digits or spaces are dropped, as in a GitHub anchor).

A section stands for the ones below it: a case of `formats.md#7.2` is a case of
`formats.md#7`. `run.py --section` takes a reference, or a glob on it, and `--sections`
lists what each section has. Under a section a case is only a check of its contract rules,
not of all its statements; the coverage table says which contracts are checked.

## Contract and Free

The specification marks each rule **Contract** (the same in every implementation) or
**Free** (messages, prompts, caches). The suite follows it like this:

- **Always Contract**: the exit code of every step, and every file written (`work/`,
  `home/`): the bibtex, `.papers/`, the global configuration, the history store, the
  files moved or copied. A file of the history that has a Free key is compared without it:
  `message` of a state (`data/history/projects/*/states/*.json`, `history.md#3.2`: "free;
  for display"); a difference in that key alone is a Free difference.
- **Contract by default, for the standard output**, of a step that
  - has `--porcelain` (`formats.md#7`: the standard output has the porcelain lines only);
  - is a `list` with `--format key|bibtex|ris|csl-json|bibjson`, `--plain`, `-K`/`--key-only`
    or `--field` (`formats.md#6`).
- **Free by default**: every other output, standard output and error. The messages and
  listings of the commands (`Added -> ...`, `papers status`, `papers config`, `papers
  history`, `papers tag`, the default `list` format, which `formats.md#6` makes free: "human
  output"), the warnings and errors (`papers: error: ...`), the usage
  messages of exit status 2, and the standard error of a `--porcelain` step.
- **Overrides**: a step can list its Contract streams, `"contract": ["stdout", "stderr"]`
  (`[]` for none): the cases of `extract` and `fetch` use it for the output of a command that
  has the default rules wrong.

The rules are `default_contract()` and `FREE_JSON_KEYS` in `conformance.py`.

## The sandbox

Each case runs in a fresh temporary folder with two parts: `work/`, a copy of
`before/`, where the steps run, and `home/`, the HOME of the user. Nothing
else of the machine is seen: the global configuration of papers and its
history are those of this `home/` (platform directories: on macOS
`~/Library/Application Support/papers` and `~/Library/Caches/papers`, on Linux
`~/.config/papers`, `~/.local/share/papers` and `~/.cache/papers`; the XDG
variables are unset). The environment of a step is `PATH` and:

```
HOME=<sandbox>/home  LANG=C.UTF-8  LC_ALL=C.UTF-8  TZ=UTC  COLUMNS=80  LINES=24  NO_COLOR=1  TERM=dumb
```

`COLUMNS` fixes how argparse wraps the usage messages of errors.

## Placeholders and normalization

What is machine-specific is replaced by a placeholder in everything that is
recorded and compared (standard output and error, text files of the trees);
the same placeholders can be written in `before/`, `before-home/`, `argv` and
`stdin` and are replaced by the real paths when the case runs.

| placeholder | what |
|---|---|
| `$WORK` | the working folder (`<sandbox>/work`), as an absolute path |
| `$HOME` | the HOME of the sandbox |
| `$CONFIG` | the folder of the global configuration of papers (`config.json` is in it) |
| `$DATA/history` | the history store of the machine (`$DATA`: the data folder of papers) |
| `$CACHE` | the cache folder (`~/Library/Caches/papers`, `~/.cache/papers`) |
| `$TMP` | the sandbox itself (a path that leaves `$WORK`, e.g. `../x`) |
| `$VERSION` | the version of the implementation: what `--version` prints |
| `$TIME` | a time: `(2026-10-22 14:03)` in `papers history` and `undo`/`redo` lines becomes `($TIME)`, and the `time` of the history files |
| `$PROJECT1`, `$PROJECT2`... | the identifiers of libraries (see below) |
| `$STATE1`, `$STATE2`... | the identifier of a state of the history (see "States"); in an argument, the first 8 characters of it; `$STATE2:4`: the first 4 |
| `$ID` | the `id` of a library configuration that no step of the history names (`papers export` makes one): 32 hexadecimal characters |
| `$MTIME` | in an origin record (`.papers/origin/*.bib`), the number of `@comment{papers-pulled ...}`; `papers-time = {...}` becomes `{$TIME}` |

The paths are replaced in both forms papers prints them: absolute, and with
`~` for the HOME (`~/Library/Application Support/papers/history`). The
unresolved name of a temporary folder (`/var/...` for `/private/var/...` on
macOS) is replaced too.

**Library identifiers.** The first command that records a step of the history
gives the library an identifier, a random uuid, written as `"id"` in
`.papers/config.json`; it names the project of the library in the history
store and is shown by `papers history --all`. The identifiers are replaced by
`$PROJECT1`, `$PROJECT2`... in the order of the places of the libraries (the
paths of their bibtex files). An implementation can use any identifier.

The same identifier names a pool in the origin records of the libraries that exchange with
it (`exchange.md#2.3`): `papers-pool` holds it, and the file is `<name>-<first 6 digits of
the sha1 of the identifier>.bib` (`exchange.md#3.1`). The identifier is replaced as above,
and so is the hash in the file name: `.papers/origin/pool-$PROJECT2.bib` (in the files, and
in the names that the states of the history keep). A pool whose library has no identifier is
named by its path (`pool-615fe0.bib` for `../pool`, no placeholder). A case can give a pool
a fixed identifier in its configuration (`exchange/pool-identifier`): nothing replaces it
(the pool records no step, so it is no project of the history), and the file name is the
one the specification gives.

**States.** The identifier of a state of the history is a sha256 that includes its time
(`history.md#2.5`), so it differs at each run. The harness gives the states that a run writes
numbers, in the order of their times, over the whole history store (all libraries): the
first state written is `$STATE1`, which is, for the first library that a command records,
its start state. The identifier is replaced by `$STATEn` in everything compared: the
outputs (the 8 characters `papers history` and `undo` show, the 64 of the other
messages), `heads.json`, the file names `states/$STATEn.json` and the keys inside them
(`parent`, `reverts`, `pools`, the `redo` list). The numbering is kept for the whole run: a
state that the history drops later (`history/retention`) keeps its number in the outputs
that named it. The same placeholder in the arguments of a step names a state that exists
when the step runs: `restore $STATE2`, `history --revert $STATE3`, `history --drop-files
$STATE2`; `$STATE2:4` is its first 4 characters, as a short name is. The cases that write
two libraries (a library and its pool) count the states of both in the order they were
written (`history/revert-pool-line`: the pool's start state and push step come before the
start state of the library).

A state that the case starts with (a history converted from papers 3.0.0b5 in `before-home`:
`history/convert-numbered`, `history/state-prefix`) has a time that is not of the run and is
not replaced: its identifier, its file name and its `time` stay as they are, so the cases check
the computation of the identifier (`history.md#2.5`) and a prefix shared by two of them.

## What is compared

- **Per step:** the standard output, the standard error and the exit code,
  byte for byte (after the placeholders).
- **The working folder after:** every file, byte for byte, and the empty
  folders. This includes the files the case started with (nothing may change
  that should not), and `.papers/` (`config.json`, `.gitignore`...).
- **The HOME after**, as three roots: `config/` (the global configuration:
  `config.json`), `data/` (the history store: `data/history/projects/$PROJECTn/heads.json`,
  `.../states/$STATEn.json`, `data/history/objects/...`, `numbers.json` when a history of
  papers 3.0.0b5 was converted), and `home/` (anything
  else written under HOME). On macOS the configuration and the data folder
  are the same folder, and what is under `history/` is `data/`, the rest
  `config/`.
- **The history objects** (`objects/ab/ab12...`, the pieces of the bibtex named
  by their sha256) are zlib-compressed on disk: they are compared
  decompressed, because the bytes of a compressed stream depend on the zlib
  that made it. An implementation must write objects that papers-cli reads.
  An object whose text has a placeholder in it (a path, the times of an origin
  record) is named by the sha256 of its normalized text, and the states, and
  the `sha` of their bibtex, follow: the real names depend on the sandbox.

`--contract-only` leaves out of this what the specification makes Free (see
"Contract and Free"): the outputs of the steps that are not Contract, and the
`message` of the states.

Not compared:

- The parse cache (`$CACHE`, `Library/Caches/papers`): private to each
  implementation.
- File times and permissions.
- `.DS_Store`.

Not (yet) part of the format: symbolic links, binary files other than
history file objects (PDFs), the network.

## Things in the reference that are not deterministic, or surprising

- The random identifier of the libraries and the identifier of a state, which includes its
  time (above). `papers history --all` lists the projects of a store in the order of the
  place of their last use (`history.md#12`), so its output is reproducible whatever the
  identifiers (`history/all-sorted-by-place`).
- The history messages (`papers history`) are the arguments joined with
  spaces, without quoting, with `papers` as the program name whatever was run
  (`papers edit x --set journal=Earth System Dynamics (ESD)`).
- Errors of the command line (an option that does not exist, a missing
  argument, a bad value of `-n`, `history --revert` without a step) print the usage message of argparse, exit
  status 2: `errors/bad-option` and `history/undo-steps-below-one` (`-n 0`: a usage error, `history.md#6.2`)
  are the only cases that have them, so that they
  can be dealt with apart. An implementation must print `papers`, not its own
  name, as the program in these messages.
- The bibtex parser's own warnings (`bibtexparser.splitter: warning: ...`) go
  to standard error, once, for a bibtex that does not parse (`list/unreadable-bibtex`).
- `papers add` has no `-` argument for the standard input; the bibtex from
  stdin is `papers add /dev/stdin` (`add/from-stdin`). `papers edit --from -`
  and the `-` of `tag`, `rm` and `edit` (keys, one per line) do read it.
- The one-line listing keeps a trailing space for an entry with neither DOI,
  file nor tag (`plain2019: An entry without file `).
- A command that changes nothing (`edit --unset nosuchfield`, `tag --rm
  notthere`) records no step in the history. An `undo`, `redo` or `restore` with nothing to
  do leaves no trace either: no `id` in `.papers/config.json`, no start state, no store
  folder (`history/nothing-to-undo`, `history.md#6`).
- `--format ris` needs the optional `rispy` package: `list/ris` and `export/ris` fail
  without it in the reference (`pip install papers-cli[ris]`).
- A step that names a state of the history takes its identifier or the start of it, 4
  characters or more (`history.md#2.5`); the step numbers of papers 3.0.0b5 (`restore 3`) are
  errors (`no step 3 in the history`) and the usage error of `restore last` is gone: a
  value of `restore` is a text. `errors/bad-option` uses `history --revert` for the usage
  error.
- The files and `.papers/origin/` records of a pool that has an identifier are named after its
  folder and the hash of the identifier (`pool-569371.bib`), so a case that wants a name that is
  the same at every run gives the pool library an `id` of its own (`exchange/pool-identifier`),
  or has none (the pool then has a path id).
- `papers config` of a global configuration of papers 2 (`papersconfig.json`) depends on the
  platform for its location: no case has it.
- A pull right after another change in the same second can miss a change; the cases of
  `exchange` use `wait` (above).
- The identifier of a library is replaced by `$PROJECTn` in the outputs only when its project is
  in the history store at the end of the run (a command that leaves no trace, or a removed
  history, leaves none): a case that names a library by an `id` of its own and removes its
  history ends with a command that records a step again (`history/remove`,
  `history/separate-store`).

## Adding a case

Make the folder with `case.json` and `before/` (a library fixture is easiest
made by running `papers init` and `papers add` in a scratch folder with a
temporary `HOME`, and copying the library; remove the `id` from its
`.papers/config.json`), give it its `sections`, the `tests` of `design/tests.md` it matches,
and, where a step's output is Contract although the default rules say Free (or the other way
round), its `contract`, then `python design/cases/record.py --papers papers group/name`. A step that
takes a step of the history names it `$STATEn` (see "States"). A history of papers 3.0.0b5
(numbered states, `heads.json` with numbers) as a fixture is made by hand: `history/convert-numbered`
has one (the identifiers that the conversion computes are in `history.md#2.5`).
Read the recorded `expected/` before committing it: it is what papers does,
including its mistakes. The recording refuses what is not reproducible (it runs twice).

**Never run the reference on the real machine to record**: `record.py` and
`run.py` always run in a sandbox with a temporary `HOME`; do the same when
running papers by hand to explore (`HOME=$(mktemp -d)`, in a temporary
working folder), so the global configuration and the history of the user are
not touched.

## Coverage of the specification

The rows are those of the compatibility table of `design/README.md` (what
two implementations must share), with the cases that check them. "none yet" says why. RIS
needs the `rispy` package: the recording has it, so RIS is covered for the output
(`list/ris`, `export/ris`) and not for the import.

| Contract | Cases | Not covered |
|---|---|---|
| Library layout: the library directory and `.papers/` (`library.md`, Layout) | `init/default`, `init/new-directory`, `init/existing-bibtex-and-files-folder`, `init/bibtex-filesdir-paths`, `export/library`, `status/library`, `config/papers-folder-moved`, `config/papers-folder-not-moved` (`.papers/` of the library directory when the bibtex is in a subfolder: `distinct.json`, `origin/`, `origin.bib` of earlier builds move there), `config/papers-folder-not-moved-dry-run` (not moved by `--dry-run`, an abbreviation of it, `file mv -n`, nor by a usage error) | `.papers/` of a bibtex without library |
| `.papers/.gitignore` | `init/default`, `config/gitignore` | |
| `.papers/config.json`: format, keys, which keys are written, reading, `id`, relative paths | `init/*`, `config/set-and-unset`, `config/prune`, `config/set-invalid`, `config/read-library-config`, `config/pool-path-forms`, `config/legacy-papersconfig`, `config/invalid-value` (a wrong value is an error), `config/invalid-utf8` (a configuration that is not UTF-8: an error that names the file), `config/unknown-keys-kept`, `config/explicit-default-saved` (a setting given is saved at its default; `init` writes `paths`), `config/paths-from-current-folder`, `init/paths-from-current-folder` (paths of the command line are read from the current folder), `export/library` | the format of an `id` created by a command is only checked as 32 hexadecimal characters (`$ID`, `$PROJECTn`) |
| Legacy `.papersconfig.json` and `papersconfig.json` | `config/legacy-papersconfig` | `papersconfig.json` of papers 2 (global, `migrate` of it): none yet, its location differs by platform |
| Machine configuration: location and keys | `config/global`, `config/global-default`, `config/global-invalid` (not valid JSON: an error), `config/global-invalid-utf8`, `config/global-too-new`, `init/global-default-library`, `init/shallow-global` | the Linux locations (the suite runs on one platform at a time) |
| Settings: names, types, defaults, precedence | `config/get`, `config/show`, `config/set-and-unset`, `config/set-invalid`, `config/precedence`, `init/format-options` | the display of `papers config` is Free: only the files are Contract |
| Finding the library of a command (`-C`, search upwards, `--bibtex`) | `config/find-library`, `config/other-directory`, `status/subdirectory`, `status/bibtex-option`, `status/bibtex-missing` (a missing FILE is an error), `list/bibtex-option`, `errors/bad-directory`, `errors/no-library`, `config/global-default` | `--bibtex FILE` of a bibtex that has no library and its history (`history.md#5.1`): `history/bibtex-option` has the undo and restore of one |
| The `pool` setting and the states self-contained and shallow | `init/pool-relative`, `init/pool-missing`, `init/shallow-global`, `config/pool-path-forms` (also: a library is not its own pool), `status/shallow-library`, `porcelain/config-pool` | |
| File names of the files directory, name and key templates, slugify, path safety | `file/name-template`, `file/name-suffix` (the `-2` suffix: a file of another entry is never replaced), `file/name-slugify` (HTML references, transliteration, `{doi_or_id}`), `file/extension-rule`, `file/template-invalid`, `file/attach-refused`, `list/file-actions-refused` (refused placements: exit status 1), `add/file-links`, `add/update-key`, `add/key-suffix`, `add/key-empty-template`, `add/key-transliteration`, `add/csl-json` (keys from the template) | `{journal}` of an entry without journal, `--name-*` with Python format specifications (not part of the contract), the cut at 250 bytes (and an extension longer than 249) |
| The lock file `.papers/lock` and its protocol | `lock/stale` | refresh every 2 s, takeover during a command, the pid check of a lock on this host (it depends on the host name): none yet |
| Bibtex reading and output format (blocks, order, layout, values) | `bibtex/save-format` (`tests/sortformat/varied.bib` of papers), `bibtex/bom-crlf` (a byte order mark and CRLF are read, UTF-8 and LF written), `add/bibtex-file`, `add/odd-bibtex-syntax`, `list/unreadable-bibtex`, `list/bibtex-option`, `add/dry-run` | encodings other than UTF-8 |
| `file` field syntax | `bibtex/file-field-read`, `bibtex/file-field-write`, `add/file-links`, `list/file-filters` | `paths = absolute` rewriting at load (`config/set-and-unset` only sets it) |
| `keywords` field syntax (tags) | `tag/syntax`, `tag/add-remove`, `tag/rename`, `tag/rename-nested`, `tag/list`, `tag/list-order`, `list/tags`, `list/tags-nested`, `list/tag-pattern-slashes` | |
| `ids` field syntax, `crossref` on renames | `edit/key`, `edit/key-validity-crossref`, `edit/key-case-only` (a change of case is a rename), `edit/key-numerals`, `edit/set-key-refused`, `errors/unknown-key`, `rm/by-identifier`, `porcelain/check` | `--keep-old-key` repeating a former key |
| Key suffix rule, keys never empty | `add/key-suffix`, `add/update-key`, `add/key-empty-template`, `check/auto-key` (an entry whose key is right keeps it), `check/fix-key-empty-template`, `list/action-fetch` (a rekey keeps the key, with a warning) | |
| Same-paper rule and text normalization | `list/duplicates-rules`, `list/duplicates-ascii-numerals` (ASCII digits, the ISBN prefix, whitespace in names), `list/duplicates`, `list/search-normalized` (`norm` in the search), `add/on-duplicate`, `add/no-check-duplicate` | the dialogue (`ask`): needs a terminal |
| The character table and the ASCII transliteration table (`design/data/`) | `check/encoding` (Unicode to LaTeX), `add/key-transliteration`, `file/name-slugify`, `list/search-normalized` (a sample: other scripts) | the tables themselves: `tests/test_spec_tables.py` of papers compares them with its code |
| `.papers/distinct.json` | `list/distinct-json` (reading, matching, the file not rewritten), `list/distinct-json-bad-values`, `config/papers-folder-moved` | writing it: only the dialogue adds pairs (needs a terminal) |
| Origin records `.papers/origin/<name>-<hash>.bib`, pool ids (library identifiers, path ids), `papers-pool-path`, legacy `.papers/origin.bib` | `exchange/pull-merge`, `exchange/push`, `exchange/auto-push`, `exchange/one-time` (the id of a library given by `--pool PATH`), `exchange/legacy-origin` (the legacy `.papers/origin.bib`), `exchange/rename-key`, `exchange/pull-check`, `porcelain/config-pool`, `exchange/pool-identifier` (the file named after the pool folder and the sha1 of its identifier, `papers-pool-path`, records of a path id moving to the identifier, a pool that moved) | records under several path ids moving together; a pool setting rewritten, a record with `~`: none yet |
| Matching entries (`exchange.md#4`) | `exchange/pull-merge`, `exchange/push`, `exchange/pull-check` (removed from the pool), `exchange/one-time`, `exchange/add-from-pool` | the finer rules (a pool key reused, the same paper twice, `distinct.json` of both): none yet |
| Three-way merge and its outcomes | `exchange/pull-merge`, `exchange/push`, `exchange/sync` (`keep`, `update`, `skip`, `error`, the pull that leaves conflicts), `exchange/one-time`; two-way merge: `add/on-duplicate`, `porcelain/check` | a link removed in the pool (`exchange.md#15.2`) |
| `pull`, `push`, `sync`, automatic pushes, `add` from a pool | `exchange/*`, `history/undo-pool-moved-on` (undo with a pool), `exchange/undo-auto-push`, `history/undo-redo-several-pool` (`undo -n 2` and `redo -n 2` with a pool that moved on) | the dialogue of a conflict (`ask`: needs a terminal) |
| Shallow library: files and links of the pool | `exchange/shallow-files`, `exchange/auto-push-links`, `exchange/config-pool-files`, `file/fix-pool`, `exchange/auto-push` (`rm`) | |
| `exchanges.json` (if written, exactly that content) | none: it holds the checksums of the texts of the library, the pool and the origin file, and the origin file has times (the `exchange` cases ignore the history store). | |
| History store: location, layout | `history/*`, every case that writes a step (`home/data/history`), `history/all-sorted-by-place` (`history --all`: the order), `history/convert-numbered` (`numbers.json`) | `history-dir` (the store is not under the data folder, so it is not decompressed for the comparison): `history/history-dir` has it |
| Objects (pieces of text, the cutting rule, zlib) | `history/workflow`, `history/undo-redo`, `history/restore`, `history/nothing-to-undo` (no trace), `history/undo-steps-below-one` (small bibtex: one piece) | the rule for libraries of more than one piece: none yet |
| File objects (deleted files) | `history/undo-deleted-files`, `rm/keep-files`, `file/fix-history` | |
| States: identifiers, keys, kinds, kept `.papers/` files, file operations | `history/convert-numbered` (the identifier computed by the conversion of a numbered state), `history/state-prefix` (naming a state by its start), `history/undo-redo`, `history/workflow`, `history/restore`, `history/undo-deleted-files`, `file/fix-history`, `add/file-links`, `config/legacy-papersconfig` | `outside` states (a change made between two commands: a step cannot edit a file yet); the identifier of a state written by a command (it includes the time: `$STATEn`) |
| `heads.json` | `history/two-libraries`, `history/undo-redo`, `history/convert-numbered` | |
| Writing order and retention (what may be removed) | `history/retention` (`history-size` of 1 MB), `history/remove`, `history/remove-dry-run`, `history/drop-files`, `history/drop-files-dry-run` | the writing order; the objects younger than one hour |
| Separate stores | `history/separate-store` | |
| Project id of a library and of a bibtex without library | `history/two-libraries`, `history/workflow`, `history/bibtex-option` | |
| `.papers/files.json` | `file/checksum`, `add/file-links` | |
| Parse cache | not compared (private to each implementation) | |
| Export formats: CSL-JSON, RIS, BibJSON, JSON text, `papers export` layout | `list/csl-json-types`, `list/bibjson-fields`, `list/json-text`, `list/ris`, `list/formats`, `list/empty-library`, `list/no-match-formats`, `export/library`, `export/formats`, `export/ris` | the import of RIS: none yet; import: `add/csl-json`, `add/csl-json-one-name` (an author that is one string or one object), `add/bibjson`, `add/json-errors`, `edit/from-json`, `edit/from-file` |
| `papers list --format`, `-K`, `--field` | `list/formats`, `list/line-format`, `list/no-match-formats`, `list/empty-library`, `list/bibjson-fields`, `bibtex/file-field-read` | colours (`--color always`): Free |
| `--porcelain` lines and exit codes | `edit/key-case-only`, `add/on-duplicate-skip-porcelain` (`existing`), `file/attach-refused`, `list/file-actions-refused`, `history/undo-steps-below-one` (exit status 2), `porcelain/order`, `porcelain/streams` (the listing of `list` on the standard output, the messages on the standard error), `porcelain/file-commands`, `porcelain/check`, `porcelain/config-pool`, `add/porcelain`, `add/from-stdin`, `add/no-check-duplicate`, `add/on-duplicate`, `edit/key`, `edit/from-stdin`, `edit/set-several-entries`, `rm/remove`, `tag/add-remove`, `tag/rename`, `errors/*`, `config/read-library-config`, `edit/key-validity-crossref`, `config/invalid-value` | `papers add` of a PDF or a DOI, `pull` lines: none (offline, no PDF) |

Not in the table, checked by cases too: the files that `file check` and `file fix` bring back from
the history (`history.md#6.6`, `file/fix-history`), and the search of `papers list`
(`formats.md#6.1`: `list/search-accents`, `list/search-normalized`, `list/search-fields`,
`list/search-words`; `--fuzzy` is Free: `list/fuzzy`).

Not covered by the specification: fetching, `papers extract`, PDF metadata, the
interactive dialogues.
