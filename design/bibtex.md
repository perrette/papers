# The bibtex: reading, writing, identity and merge

This file describes how papers reads and writes its bibtex file, the fields
it gives a meaning to (`file`, `keywords`, `ids`, `crossref`), when two
entries are the same paper, and how two such entries are merged. Other
files: the key and file name templates, the settings and the `.papers/`
folder are in library.md; RIS, CSL-JSON and BibJSON are in formats.md; the
history and its storage of the bibtex are in history.md; the exchange with
pools (pull, push, three-way merge) is in exchange.md.

Two labels are used below:

- **Contract**: two implementations must behave identically (same bytes
  written, same parse of a field, same verdict). A library written by one
  is read and rewritten unchanged by the other.
- **Free**: an implementation may do it differently, as long as the
  contracts hold.

The reference conformance test for reading and writing is the pair
`tests/sortformat/varied.bib` (input) and
`tests/sortformat/varied.expected.bib` (what papers writes for it).

## 1. Text encoding and line endings

- **Contract.** The bibtex is read and written as UTF-8, on every
  platform and whatever the locale. Line endings are read as `\n`, `\r\n`
  or `\r` (all three become `\n`), and written as `\n` on every platform.
  A file written by papers always uses `\n`.
- A byte order mark at the start of the file (written by some editors) is
  dropped at reading; papers never writes one. This holds for the library
  bibtex, for a bibtex file given to `papers add`, and for the text that
  comes back from the editor of `papers edit`.
- A file that is not valid UTF-8 cannot be loaded: the command stops with
  an error.
- `.papers/distinct.json` (section 9.4) is also written as UTF-8 with `\n`
  line endings.

## 2. Reading

### 2.1 Blocks

A bibtex text is a sequence of blocks:

| Block | Starts with | Kept as |
|---|---|---|
| entry | `@type{` or `@type(` | type, key, ordered list of fields |
| string | `@string{` | name and value |
| preamble | `@preamble{` | its text, as written |
| explicit comment | `@comment{` | its text, trimmed |
| implicit comment | any text outside a block | its text, trimmed |
| failed block | an `@` block that could not be read | its raw text |

The `@` keyword is matched without regard to case (`@ARTICLE`, `@String`,
`@Comment` all work). A block can be delimited by `{...}` or `(...)`.
Whitespace (spaces, tabs) is allowed between `@type` and the delimiter.

### 2.2 Entries

`@type{key, name = value, name = value, ...}`

- **Entry type**: lower-cased (`@ARTICLE` is read as `article`). Any word
  is accepted.
- **Key**: the text between the opening delimiter and the first comma,
  with surrounding whitespace removed. Its case is kept.
  An entry with no comma and no fields (`@misc{K0}`) is accepted, with no
  fields.
- **Field name**: the text before `=`, trimmed, then lower-cased by papers
  (`Title`, `TITLE` are read as `title`; older JabRef files write
  capitalized names).
- **Field value**: the text after `=` up to the next comma or closing
  delimiter that is outside braces and quotes, trimmed of surrounding
  whitespace. A trailing comma after the last field is allowed.
- **Value enclosing**: if the whole value is one `{...}` group or one
  `"..."` string, that outer pair is removed and the inside is kept
  exactly (inner braces, LaTeX commands, newlines and inner whitespace
  are kept). `{a} # {b}` starts and ends with braces but is not one group:
  it is kept as written.
- **Bare values**: a value that is not enclosed is kept as written.
  - digits only (`year = 2000`): read as the value `2000`, written back in
    braces (`year = {2000}`);
  - a single word that is the name of an `@string` of the file (any
    case; see 2.3): replaced by the value of that string;
  - anything else (an undefined macro such as `month = jan`, or a
    concatenation such as `note = jgr # " extra"` or `pages = 1--10`):
    kept as written, and marked "bare", so that it is written back
    without braces (section 3.3).
- The values are not decoded: LaTeX (`{\"u}`, `\&`) stays as written.

### 2.3 `@string` and `@preamble`

- `@string{name = value}`: the name keeps its case; the value is read as
  a field value (enclosing removed).
- References to strings are resolved at reading time: a field whose whole
  value is a bare word equal to a string name, compared without case,
  takes the value of the string. A string defined anywhere in the file
  is used (before or after the entry). Of two strings whose names differ
  only by case, the later one wins.
- Once resolved, the reference is lost: the field is written with the
  value (`journal = jgr` is written `journal = {Journal of Geophysical
  Research}`). The `@string` block itself is kept and written.
- Concatenations (`jgr # " extra"`) are not resolved: they stay bare.
- `@preamble{...}`: the text between the delimiters is kept as written,
  without trimming.

### 2.4 Comments

- An explicit comment `@comment{text}`: the text is kept, trimmed of
  surrounding whitespace.
- An implicit comment is any text between blocks (lines starting with
  `%`, free text). The text between two blocks is one implicit comment:
  leading blank lines and leading whitespace are removed, and trailing
  whitespace; empty text gives no block. Several comment lines separated
  by blank lines between the same two blocks are one block.
- The parser does not treat `%` specially: `@word{` or `@word(` starts a
  block wherever it is, so `% @article{x, ...}` is an entry. An `@` not
  followed by a word and a delimiter (an e-mail address) is text.
- Comments are kept and written back (section 3.1 says where).

### 2.5 Failed blocks

A block that cannot be read is kept as raw text and written back as it is,
under a warning line. papers does not see its content: it is not an entry
of the library (not listed, not searched, not merged). A warning names the
lines at each load: `<bibtex>: N entries could not be read (line L: a
field given twice; line M: syntax error): papers ignores them until they
are fixed`.

Kinds of failed blocks:

| Kind | Cause |
|---|---|
| syntax error | unbalanced braces or quotes, a missing `=` or `,`, end of file inside a block |
| field given twice | two fields with the same name *as written* (`title` twice) |
| duplicate key | an entry (or string) whose key, compared *with* case, is that of an earlier one |

Rules of the parser that decide where a failed block ends:

- Inside a block, an `@` that is the first non-blank character of a line
  starts a new block: the open block fails and ends just before that
  line. An `@` elsewhere in a value (`LeQua @ {CLEF}`) is text.
- The raw text of a failed block runs from its `@` to the point where the
  parser stopped. Before it is kept, papers removes from it every line
  that is a warning line of section 3.2 (after trimming), and the
  whitespace and blank lines at its end; the kept raw text ends with one
  `\n`. (Without this, a failed block that runs to the next `@` would
  take in the warning line and the blank line written after it, one more
  at each save.)
- The parser is a single pass and is tolerant: after a failure it goes on
  with the next `@` block. What it makes of malformed text beyond these
  rules (e.g. a `}` that closes an entry too early, after which the rest
  is read as an implicit comment) is **free**: a second implementation
  must keep the raw text of what it cannot read, and must read correctly
  what papers writes.

Two consequences of these rules:

- Two fields whose names differ only by case (`Title` and `title`) are
  *not* "given twice" (the check is made before papers lower-cases the
  names): the entry is read, with two `title` fields. A lookup of the
  field gives the last one; both are written (see the open questions).
- The warning line written above a failed block (section 3.2) is removed
  when the file is read again, whether it is read as an implicit comment
  or into the raw text of the failed block before it, so that it is not
  repeated at each save. A file written by papers is written back
  unchanged.

### 2.6 Duplicate keys

- Two entries with exactly the same key: the second is a failed block
  (kept raw, ignored).
- Two entries whose keys differ only by case (`Smith2000`, `smith2000`):
  both are read as entries. papers itself never creates this: it compares
  keys without case everywhere else (selection, new keys, renames).

### 2.7 Parse cache

papers keeps a cache of parsed pieces of the bibtex on the machine, so
that a large file is not parsed again in full at each command. **Contract**:
the cache never changes the result; a parse with the cache gives the same
blocks, values and failed blocks as a parse without it. Whether to have a
cache is **free**. Its format and the cutting into pieces are in
history.md.

## 3. Writing

### 3.1 Block order

**Contract.** At each save the blocks are put in this order:

1. The blocks are grouped into chunks: each comment block (explicit or
   implicit) joins the next non-comment block; a chunk is the comments
   above a block, then the block. Comments after the last non-comment
   block form a last chunk of comments only.
2. Chunks are sorted by the type of their last block, then by its key:

   | Rank | Type | Key used |
   |---|---|---|
   | 1 | `@string` | string name |
   | 2 | `@preamble` | none (empty) |
   | 3 | entry | entry key |
   | 4 | implicit comment (trailing chunk only) | none |
   | 5 | explicit comment (trailing chunk only) | none |
   | 6 | failed block | the key for a duplicate-key block, otherwise none |

3. Keys are compared as strings by Unicode code point, case-sensitive:
   `Beta2001` comes before `Zeta2020`, which comes before `alpha1999`
   (upper case before lower case).
4. The sort is stable: chunks with the same rank and key (preambles,
   failed blocks without key) keep their order in the file.

So a comment written above an entry stays above it when the entries are
reordered, and an explicit `@comment` above an entry moves with the
entry, not with the other comments.

### 3.2 Layout of each block

**Contract.** Byte for byte:

- **Entry**:

  ```
  @<type>{<key>,
   <name> = <value>,
   <name> = <value>
  }
  ```

  - `@`, the type as stored (lower case for entries read from a file),
    `{`, the key, `,` and a newline.
  - One line per field: one space of indentation, the field name, ` = `,
    the written value (section 3.3), a comma except after the last
    field, a newline. No alignment of the `=` signs.
  - Fields sorted by name, by Unicode code point (`a1` < `abstract` <
    `x-a` < `x_y`). The sort is stable: two fields with the same name
    keep their order.
  - `}` and a newline.
  - An entry without fields is written `@misc{K0,\n}\n`.
  - A value with newlines is written with them, unchanged (continuation
    lines keep their original indentation).
- **String**: `@string{<name> = <value>}` and a newline. The value is
  written in braces unless it was bare (section 3.3). The keyword is
  always `@string` in lower case, with braces even if the file used
  parentheses.
- **Preamble**: `@preamble{` + the kept text + `}` and a newline.
- **Explicit comment**: `@comment{` + the trimmed text + `}` and a newline.
- **Implicit comment**: the kept text and a newline.
- **Failed block**: the line `% WARNING Parsing failed for the following
  N lines.`, a newline, the raw text (which ends with `\n`, section 2.5),
  a newline. N is the number of lines of the raw text. So a failed block
  ends with an empty line. On reading, an implicit comment line that is
  exactly such a warning line (after trimming) is removed, and the
  comment block is dropped if nothing else is left; such lines are also
  removed from the raw text of a failed block (2.5).

Blocks are separated by one empty line: each block ends with `\n`, and a
`\n` is written between two blocks. A failed block, which ends with an
empty line of its own, is thus followed by two empty lines. The file ends
with the `\n` of the last block and no blank line after it, except when
the last block is a failed block: then the file ends with one empty line.
A library with no blocks is written as an empty file. The reference test
`tests/sortformat/varied.expected.bib` shows both cases.

### 3.3 Values

**Contract.**

- A value is written as `{` + value + `}`. No escaping is done: the value
  must have balanced braces (papers does not check this for values it
  sets).
- Integers are written in braces too (`year = {2000}`, `number = {007}`).
- Quotes are never used for enclosing: `title = "A"` is written
  `title = {A}`.
- A bare value (an undefined macro or a concatenation read from the file,
  section 2.2) is written as it was read, without braces:
  `month = jan`, `note = "first" # " and second"`. A bare value that could
  not be read back the same way unenclosed (unbalanced braces, or a comma,
  `=` or newline outside braces and quotes) is written in braces.
- A value set or changed by papers is no longer bare: it is written in
  braces (`month = {feb}`).
- A merge (section 10.7, and the three-way merge of exchange.md) keeps a
  value bare when it is the value, as text, of one of the merged entries
  where it is bare: the entry whose value was chosen is looked at first,
  then the entries in order, and the first that has the field with that
  exact value decides. A value typed in the merge dialogue is written in
  braces.

Example. Input:

```bibtex
% my library
@String{ agu = "AGU" }

@ARTICLE{smith2000,
  Title    = "The {AMOC} and sea level",
  Author   = {Smith, John and Doe, Jane},
  journal  = agu,
  Year     = 2000,
  month    = jan,
  file     = {Full Text:files/smith2000.pdf:application/pdf},
}

@book{Brown1999, title={A book}, isbn={0-306-40615-2}}
```

Written by papers:

```bibtex
% my library

@string{agu = {AGU}}

@book{Brown1999,
 isbn = {0-306-40615-2},
 title = {A book}
}

@article{smith2000,
 author = {Smith, John and Doe, Jane},
 file = {Full Text:files/smith2000.pdf:application/pdf},
 journal = {AGU},
 month = jan,
 title = {The {AMOC} and sea level},
 year = {2000}
}
```

(The `file` field is kept as written until papers rewrites the links of
the entry, see section 5.)

### 3.4 When the file is written

- Every save sorts and formats the whole library as above.
- If the text on disk is already exactly the text to write, the file is
  not written (its modification time is kept).
- If the file on disk changed since papers read it (another program wrote
  it), papers does not write it and stops with an error. papers compares
  size and modification time first, then the text.
- The file is replaced in one step (written to a temporary file next to
  it, then renamed), keeping its permissions; a symbolic link is
  followed. These are **free** as to the method, but a reader must never
  see a partial file.

### 3.5 What is normalized

At every save, only:

- the order of blocks and fields (3.1, 3.2);
- the lower case of entry types and field names (2.2);
- the enclosing of values (3.3);
- resolved `@string` references (2.3).

Field values are otherwise written as read. papers changes the content of
fields only through commands:

- `file`: rewritten in papers' syntax when the links of an entry change,
  or for all entries when the `paths` setting asks for it (section 5).
- `keywords`: rewritten when tags are added, removed or renamed (6).
- `ids`, `crossref`: on key renames and merges (7, 10).
- `check --format-name` and `list --fetch`: author and editor names
  rewritten as `Family, Given` (see below).
- `check --fix-doi`: the DOI cleaned of prefixes and suffixes, with the
  DOI parser of the PDF text extraction (not specified in these files;
  see README.md, open questions).
- `check --encoding latex|unicode`: section 4.
- `check --key-ascii`: the key transliterated to ASCII.

Name formatting (`check --format-name`, also used for the family names of
the key template, library.md): all splits below are made only at brace
depth 0, so a `{...}` group is one word whatever it contains.

1. The field is split on `and` with one or more whitespace characters on
   each side (case-sensitive). Each part is trimmed; empty parts are
   dropped.
2. A part that contains a comma at depth 0 is kept as it is.
3. Otherwise the part is split on whitespace runs into words. A part of
   one word is kept (`{World Health Organization}` stays whole). Otherwise
   it is written as the last word, `, `, and the other words joined by
   one space: `John {van der Berg}` gives `{van der Berg}, John`.
4. The parts are joined with ` and `.

## 4. LaTeX and Unicode

papers stores values as they are written in the file, LaTeX or Unicode.
Three conversions exist; none is applied at reading or writing.

### 4.1 LaTeX to Unicode, by table (identity and file names)

Used to normalize text for the same-paper rule (section 9.1) and to repair
file links saved by Mendeley. **Contract** (it decides whether two entries
are the same paper). It uses three tables of (Unicode character, LaTeX
text) pairs, given as data in `papers/latexenc.py`: `to_latex` (about
2340 pairs, e.g. `ü` / `{\"u}`, `%` / `\%`, space / `\space `),
`to_crappy1` (about 200 pairs, accented letters written as `\"{u}`,
`\'{e}`, `\AA `...), and `to_crappy2` (4 pairs: the combining grave,
acute, circumflex and cedilla, written `` \` ``, `\'`, `\^`, `\c`).

Steps, in order:

1. If the text contains `\` or `{`: for each pair of `to_crappy1`, then of
   `to_latex`, in table order, every occurrence of the LaTeX text is
   replaced by the character.
2. If the text still contains `\`: for each pair of `to_crappy2`, the text
   is split on the LaTeX text; for each piece but the last, if the next
   piece is not empty, its first character is moved to the end of this
   piece; the pieces are joined with the (combining) character.
3. Each combining character (Unicode combining class not 0) is swapped
   with the character after it; a combining character at the end is
   dropped.
4. Unicode NFC normalization.
5. All `{` and `}` are removed.

The result is not always right (`T\^ete` gives `Tet̂e`; `\url{x}` gives
`r̆lx`), but it is the reference: see the open questions.

### 4.2 Unicode to LaTeX (`check --encoding latex`)

**Contract** for the output of this command. Each character of the value
is replaced by its LaTeX text from the `to_latex` table; space, `{` and `}`
are kept; characters not in the table are kept. Example:
`Müller étoile_x ~ 50% & {GCM}` gives
`M{\"u}ller {\'e}toile\_x \textasciitilde  50\% \& {GCM}`.
It is applied to every field except `abstract`, `file`, `doi`, `url`,
`eprint`, `isbn`, `issn`, `ids`. It is not idempotent on a value already in
LaTeX (a backslash is encoded again).

### 4.3 LaTeX to text (`check --encoding unicode`, and `add` of a PDF)

A full LaTeX-to-text conversion of every field value: accent commands and
escapes become Unicode characters, braces are removed, `~` becomes a
no-break space, `--` and `---` become en and em dashes, `\url{x}` becomes
`x`, formatting commands are dropped (`\textit{x}` gives `x`), math
(`$...$`) is kept as written. Applied by `check --encoding unicode` and to
the bibtex of a paper added from a PDF (fetched or extracted metadata). The
exact output is that of a third-party converter; see the open questions.

## 5. The `file` field

### 5.1 Syntax

**Contract.** The field holds one or more links separated by `;`. Each
link has one of three forms:

| Form | Path read |
|---|---|
| `path` (no `:`) | the whole text |
| `path:type` (one `:`) | the text before the `:` |
| `description:path:type` (two or more `:`) | everything between the first and the last `:` |

So the path of the three-part form may contain `:` (`Desc:dir/a: b.pdf:pdf`
gives `dir/a: b.pdf`), while the description and the type cannot. This
reads the files of Mendeley and JabRef (`Full Text:files/x.pdf:application/pdf`).

- Empty links (`;;`, or text that is only whitespace) are skipped.
- A link whose path is empty (`::pdf`) is skipped with a warning.
- The path is not trimmed: whitespace around it is part of it.
- There is no escaping: a path with `;` cannot be stored, and `\:` or `\;`
  (JabRef escapes) are read literally. A two-part link `C:\x.pdf` is read
  as the path `C`.

**Contract.** papers writes each link as `:path:type`, where `type` is the
file extension without the dot, as written (`PDF` stays `PDF`; the part
after the last dot of the file name; empty if there is none), and joins
links with `;` without spaces:

```
file = {:files/smith2000.pdf:pdf;:../other/notes.txt:txt;:files/README:}
```

A file named `x.tar.gz` has type `gz`. A file whose name starts with a
dot and has no other dot has an empty type.

### 5.2 Relative and absolute paths

- A relative path is relative to the directory of the bibtex file. An
  absolute path is used as it is.
- When the links of an entry are written, they follow the `paths` setting
  of the library (library.md):
  - `relative`: the path relative to the bibtex directory, normalized
    (`..` used to reach files outside it: `../other/notes.txt`; `.` and
    redundant separators removed). Symbolic links are not resolved.
  - `absolute`: the absolute path, normalized (`..` resolved as text,
    symbolic links not resolved).
- When papers writes the links of an entry: on any change of its files
  (add, attach, detach, rename, merge), the whole field is rewritten from
  the parsed paths, so descriptions and MIME types are lost and the
  current `paths` setting applies to all its links.
- At load, with `paths` = `absolute`, the links of all entries are
  rewritten as absolute (and the bibtex is saved even if the command
  changes nothing else). With `paths` = `relative`, nothing is rewritten
  at load: absolute links stay until the entry's files change or `papers
  config paths relative` converts all links (see the open questions).
- Links are kept in their order. When papers sets the links of an entry,
  a path given twice (same absolute path as text) is kept once, at its
  first position. If no link is left, the field is removed.

## 6. The `keywords` field and tags

**Contract** for the syntax; the commands are described in the user
documentation (`docs/listing.md`).

- Tags are the `keywords` field split on `,`; each tag is trimmed; empty
  tags are dropped. `;` is not a separator in bibtex (it is in RIS and
  CSL-JSON imports, formats.md).
- A tag may contain `/`: `climate/amoc` is under `climate`. The parents of
  `a/b/c` are `a` and `a/b`.
- When papers sets tags it writes them joined by `, ` (comma and space).
  When no tag is left, the field is removed.
- Add: the new tags are appended after the existing ones, in the order
  given, skipping those already present and repeats; the existing tags
  keep their order. Comparison is exact (case-sensitive).
- Remove: the tags equal (case-sensitive) to a given tag are removed; the
  others keep their order.
- Rename `OLD` to `NEW` (whole library): a tag equal to `OLD` becomes
  `NEW`, a tag starting with `OLD/` gets `NEW/` in its place; then
  repeats are removed, keeping the first. Exact, case-sensitive.
- Matching (`list --tag PATTERN`): the tag and the pattern are compared in
  lower case; a trailing `/` of the pattern is dropped; the pattern is a
  shell-style pattern (`*`, `?`, `[...]`) matched against the whole tag;
  a tag also matches when it is under a tag that matches (`climate`
  matches `climate/amoc`).
- The field is written only when tags change: a field written as
  `a;b, c` by another program is read as the tags `a;b` and `c`, and
  stays as it is until then.
- Counting (`papers tag`): an entry counts once for each of its tags and
  for each parent of them.

The fields are not merged as sets in a two-way merge: two `keywords`
values that differ are a conflict (section 10).

## 7. Keys: `ids` and `crossref`

### 7.1 The `ids` field

The `ids` field holds former keys of the entry, comma-separated (the
biblatex key alias field). papers:

- reads it by splitting on `,` and trimming each part; empty parts are
  dropped;
- writes it joined by `, `;
- accepts a former key anywhere a key is accepted on the command line
  (comparison without case). The key of an entry wins over the former key
  of another;
- uses it to recognize an entry renamed in a command as the same entry
  (for the report of changes);
- fills it in two cases:
  - `edit KEY --key NEW --keep-old-key`: the former key is appended to
    `ids`, and a part equal to the new key (without case) is removed from
    it. Without `--keep-old-key`, `ids` is not changed.
  - `check --duplicates`: the keys of the merged entries go to the `ids`
    of the entry that is kept (section 10.5).
- does not send it to pools: each side of an exchange keeps its own
  `ids` (exchange.md).

### 7.2 Key validity on rename

`edit --key NEW` refuses a key that is empty, starts with a digit, or
contains whitespace or one of `, { } " # % ~ = ( ) \`, and a key that
another entry has (compared without case). (The key template is in
library.md.)

### 7.3 `crossref` follows renames

At save, for each entry whose key changed during the command (the same
entry, its old key no longer in the library, its new key not in the
library when it was loaded), every `crossref` field equal to the old key
(compared without case) is set to the new key. Other fields that name
keys (`xdata`, `related`, `xref`) are not followed. Keys removed by a merge
are not renames: a `crossref` to a merged-away key is not changed (see the
open questions).

## 8. Key collisions when entries are added

**Contract** for the suffix rule (it decides the keys written).

- A new key from the key template (library.md) that is already in the
  library (compared without case) gets a letter suffix.
- Suffix rule: if the key ends with a lower-case letter `a`-`z` right after
  a digit (`Author2000b`), that letter is taken as a previous suffix: it
  is removed and the next letters are tried (`c`, `d`, ...). Otherwise the
  letters `b` to `z` are tried, appended. The first key not in the library
  (without case) is taken. If none is free, the command fails.
  - `Author2000` with `author2000` taken: `Author2000b`.
  - `Author2000` with `author2000` and `author2000b` taken: `Author2000c`.
  - `Ab` with `ab` taken: `Abb` (no digit before the last letter).
- When the entry is in the library already (`check --auto-key`), its own
  key is not counted as taken: an entry whose key is already the template
  key keeps it (`smith2000` stays `smith2000`).
- Adding an entry whose key is given (not from the template) and already
  used:
  - if the existing entry has the same title (exact text) and is the same
    paper (section 9): the added entry is not inserted; its file links are
    added to the existing entry;
  - otherwise the command fails ("this key is already in the library").
- An added entry that the user declared a different paper from a library
  entry (answer "not the same paper") is inserted, and its key gets a
  suffix as above if it is taken.
- An added entry without key gets a key from the template.

## 9. Entry identity: the same-paper rule

**Contract.** The verdict for a pair of entries is `same`, `different` or
`ask`. It is used by `add`, `check --duplicates`, `list --duplicates` and
the exchanges with pools.

### 9.1 Text normalization

`norm(s)`:

1. empty text gives empty text;
2. LaTeX to Unicode by table (section 4.1) (a text that is ASCII without
   `\`, `{`, `}` is unchanged by this step);
3. transliteration to ASCII (`ü` to `u`, `ß` to `ss`, `Å` to `A`; the
   table is that of the Unidecode project, see the open questions);
4. remove `{` and `}`;
5. lower case; whitespace runs replaced by one space; trimmed.

### 9.2 Identifiers of an entry

- **DOI**: the `doi` field, trimmed, without a leading
  `http://doi.org/`, `https://doi.org/`, `http(s)://dx.doi.org/` or
  `doi:` (any case, spaces allowed after `doi:`), trimmed again. It is a
  DOI if it starts with `10.` and contains `/`. Compared in lower case.
- **arXiv id**:
  - from `eprint`, if `archiveprefix` is empty, absent, or `arXiv` (any
    case, trimmed);
  - else from a DOI of the form `10.48550/arXiv.<id>`.
  - Normalization: trimmed; a leading `arXiv:` (any case, spaces allowed
    after) or `http(s)://arxiv.org/abs/` or `/pdf/` removed; a trailing
    `.pdf` removed. Accepted forms: `NNNN.NNNN` or `NNNN.NNNNN` (new),
    `archive/NNNNNNN` or `archive.XX/NNNNNNN` (old, e.g. `hep-th/9901001`,
    `math.AG/0601001`), each with an optional version `vN`, which is
    dropped. Lower case. Anything else is no arXiv id.
- **ISBNs**: only for entries of type `book`. The `isbn` field is split on
  `,` and `;`. Each part: whitespace and hyphens removed, a leading `ISBN`
  (any case) and `:` removed, upper case. A 10-character ISBN
  (`NNNNNNNNN` + digit or `X`) with a valid check digit (weighted sum
  10..1 divisible by 11) is converted to ISBN-13 (`978` + first 9 digits +
  new check digit). A 13-digit ISBN with a valid check digit (weights
  1,3,1,3...; sum divisible by 10) is kept. Invalid ones are ignored. The
  identifier is the set of ISBN-13s.
- **Authors**: the `author` field split on `and` surrounded by whitespace
  (case-sensitive, any whitespace; also inside braces, unlike the name
  formatting of section 3.5: see the open questions). The family name of
  each name: if it
  contains a comma, the text before the first comma; otherwise its last
  word, where a `{...}` group without nested braces counts as one word
  (`Jane {van der Berg}` gives `{van der Berg}`). Each family name is
  normalized (9.1); the author identifier is the normalized family names
  joined by spaces. The `editor` field is not used.
- **Title**: `norm(title)`.
- **Author-title**: `authors|title` when both are non-empty, else none.

### 9.3 The rule

In this order; the first step that applies decides:

1. The pair is recorded in `distinct.json` (9.4): `different`.
2. Both have a DOI: different DOIs give `different`; equal DOIs give
   `same`, or `ask` under the title guard.
3. Both have an arXiv id: same as for the DOI.
4. Both have ISBNs (both are books): no ISBN in common gives `different`;
   one in common gives `same` (no title guard).
5. Both have an author-title and they are equal: `same`.
6. Otherwise: `different`.

Title guard: equal identifiers, with different entry types (lower case)
and both titles non-empty and different after normalization, give `ask`
(e.g. a chapter exported with the DOI of its book). An `ask` is decided by
the user in the dialogue; the other modes skip it (section 10.6).

Consequence: an entry with a DOI and one without are compared on the next
identifier they share, so an entry with no DOI matches by arXiv id or by
authors and title.

### 9.4 `distinct.json`

File `.papers/distinct.json` next to the bibtex. It records pairs of
entries that the user declared not the same paper, by identity, not by
key, so that the file means the same in every library.

**Contract** (format):

```json
{
 "distinct": [
  [
   {
    "authortitle": "smith doe|the title",
    "doi": "10.1/abc"
   },
   {
    "authortitle": "muller|unicode t"
   }
  ]
 ]
}
```

- Each side is an identity: an object with the keys an entry has among
  `doi` (normalized DOI), `arxiv` (normalized arXiv id), `isbn` (the
  ISBN-13s of a book, sorted, joined by `,`), and `authortitle`, or
  `title` when the entry has a title but no authors.
- Written with an indentation of one space, keys sorted, non-ASCII
  characters escaped as `\uXXXX`, and a final newline. Written only when a
  pair was added.
- Reading: a missing file is no pairs; a file that cannot be read is
  ignored with a warning; elements of `distinct` that are not lists of
  two are ignored.
- A recorded side matches an entry when `doi`, `arxiv` and `isbn` are
  equal (absent on both sides counts as equal), and `authortitle` and
  `title` are equal where both sides have them. A pair matches two
  entries in either order.
- A pair is added when the user answers "not the same paper" in `add` or
  `check --duplicates`; for a group of entries, every pair of the group is
  added. A pair is not added if an entry has no identity,
  or if the pair already matches.
- Exchanges with a pool take the union of the pairs of both sides (a pair
  equal, in either order, to a recorded one is not added again).
- An entry whose identifiers change later (e.g. it gains a DOI) no longer
  matches the recorded side.

### 9.5 Finding duplicates

- `add`: the added entry is compared with each library entry that shares
  an identifier with it (DOI, arXiv id, an ISBN, author-title, or title
  for entries without authors). Matches are ordered `same` first, then
  `ask`, each in library order; the first is used. How candidates are
  found (an index) is **free**; the result must be that of comparing with
  every entry.
- `check --duplicates`: entries linked by `same` or `ask` verdicts are
  joined into connected sets. Each set is sorted by number of fields,
  most first (the type and key count as fields; ties keep library order),
  then split into groups: each entry joins the first group where it is
  not `different` from any member, or starts a new group. Groups of one
  are dropped. A group is `ask` if any of its pairs is `ask`. So a group
  never holds two papers with contradicting identifiers: an entry without
  DOI that matches two entries with different DOIs by authors and title
  goes with the first of them. The order in which groups are presented is
  **free**.

## 10. Merging entries that are the same paper (two-way)

### 10.1 Target

The merge combines a target (entry 1, it keeps its key and its position
in the library) with the other entries.

- `add`: the library entry is the target, the added entry is entry 2.
- `check --duplicates`: the first entry of the group (most fields).
- In the dialogue, the user can make another entry the target (`t N`).

### 10.2 Fields

All field names of all entries, except `file` and `ids`, plus the entry
type, are merged one by one. For each field, the value of each entry, an
empty or whitespace-only value counting as absent:

| Case | Status | Value |
|---|---|---|
| no entry has a value | same | the target's value as written (possibly empty), or empty if absent |
| all values present are equivalent, target has one | same | the preferred value (10.3) |
| all values present are equivalent, target has none | added (`+`) | the preferred value |
| otherwise | conflict (`!`) | decided (10.6); by default the target's value, or the first entry having one |

The entry type is compared in lower case.

### 10.3 Equivalent values

- `author`, `editor`: same number of names; for each name, in order:
  equal normalized family names (9.1, 9.2), and compatible given names.
  Given names are normalized and split into words on whitespace, `.`, `-`
  and `~`; the words are compared pairwise up to the shorter list (extra
  words on one side are ignored); two words are compatible if equal, or
  if one is a single letter that starts the other (`J` and `John`).
  `Smith, J.` and `John Smith` are equivalent; `Smith, Jo` and
  `Smith, John` are not.
- `doi`: if both values are DOIs (9.2), equal normalized DOIs; otherwise
  as other fields.
- Other fields: equal after `norm` (case, braces, accents, LaTeX accents,
  whitespace).

Preferred value among equivalent values: for `author` and `editor`, the
one with the longest given names (sum of the lengths of the given-name
words), the first one on a tie; for other fields, the first present (the
target's when it has one).

### 10.4 `file`

The union of the links of all entries, target first, in order. A link is
skipped if it names a file already in the union, by real path (symbolic
links resolved) or, for an existing file, by content checksum. The links
are written with the `paths` setting of the library (section 5).

### 10.5 `ids`

The parts of the `ids` fields of all entries, in entry order; in
`check --duplicates`, followed by the keys of the other entries. A part
equal to the target's key, or to a part already taken, is dropped
(compared without case; the first spelling is kept). Written joined by
`, `; no field if empty. In `add`, the key of the added entry is not put
in `ids`.

### 10.6 Decision

- A `same` verdict with no conflict and no added field is merged without
  asking (new links and former keys may still be added).
- Otherwise, the `--on-duplicate` mode:
  - `ask`: the dialogue (per field, take all from one entry, edit, change
    target, not the same paper, skip, quit). Its screen is **free**.
  - `keep`: merge; each conflict takes the target's value (if it has one).
  - `update` (`add` only): merge; each conflict takes the value of
    entry 2 (if it has one).
  - `skip`: nothing is changed.
  - `error`: the command stops before saving.
  - An `ask` verdict is skipped with a warning in all modes but `ask`.
- "Not the same paper": the pair (or every pair of the group) goes to
  `distinct.json`; in `add` the entry is inserted (key suffix if needed).

### 10.7 Result

The merged entry has the target's key, the merged type, the merged fields
(those with a value, possibly empty), `file` and `ids`. The target in the
library is replaced by it in place; in `check --duplicates`, the other
entries of the group are removed. A bare value stays bare when it is the
value of one of the entries (section 3.3); the other values are written in
braces.

### 10.8 Three-way merge

The exchange with a pool (pull, push) uses a three-way merge against the
last exchanged copy, and keeps the key, `ids` and `file` of each side: see
exchange.md.

## Open questions

1. **Field names that differ by case give two fields.** `Title` and
   `title` in one entry are not "a field given twice" (the check runs
   before lower-casing): both are kept and written, a lookup gives the
   last one. papers/entries.py:104-111, 114-122.
2. **`@string` references are inlined.** A resolved reference is written
   as its value, so `journal = jgr` becomes `journal = {...}` at the first
   save, while the `@string` block is kept. Intended?
3. **Empty fields are added by a merge.** A field that is empty in the
   added entry and absent in the target is added to the target, empty
   (`pages = {}`). papers/merge.py:152-157.
4. **Given-name compatibility ignores extra words.** Words are compared
   with a pairwise zip, so `John` and `John David` are equivalent, and
   `J.` and `John Quincy` too. papers/merge.py:67-79.
5. **Tag add/remove/rename are case-sensitive, matching is not.**
   `--tag climate` finds `Climate`, but `--rm-tag climate` does not
   remove it, and `--add-tag climate` adds it next to `Climate`.
   papers/cli/entry_cmds.py:343-347 versus 385-421.
6. **Key suffix after an upper-case letter or `z`.** The suffix rule only
   knows lower-case letters, so `Author2000B` gets `Author2000Bb`; a
   template key that ends with a digit and `z` (`Author2000z`) has no
   next letter, and the command fails.
   papers/bib.py:80-102.
7. **`--keep-old-key` can repeat a former key.** The old key is appended
   to `ids` without checking whether it is there already; without
   `--keep-old-key`, a part of `ids` equal to the new key stays.
   papers/bib.py:308-310.
8. **`crossref` to a merged-away key is not updated.** After
   `check --duplicates`, a `crossref` that names a key that went to
   `ids` keeps naming it (biblatex may or may not resolve it through
   `ids`). Fields `xdata`, `related` are never followed.
   papers/bib.py:277-294, papers/library.py:179-190.
9. **Absolute links in a relative library are not converted at load.**
   With `paths` = `absolute` all links are rewritten at load; with
   `relative`, absolute links stay until the entry's files change.
   papers/library.py:93-97.
10. **No escaping in the `file` field.** A path with `;` cannot be
    stored; JabRef's `\:` and `\;` are read literally; a two-part link
    `C:\x.pdf` is read as `C`. Paths are not trimmed. papers/entries.py:246-290.
11. **The table LaTeX decoder is wrong for some input, and it defines
    identity.** `T\^ete` gives `Tet̂e` (the accent is moved twice), `\url{x}`
    gives `r̆lx`, `\'e` without braces is not decoded. A second
    implementation must copy the algorithm and its tables exactly to give
    the same verdicts. papers/latexenc.py:34-90.
12. **Transliteration is a third-party table.** Step 3 of the
    normalization (9.1) is the Unidecode table; a second implementation
    needs the same table, or identities (and `distinct.json`) differ.
    papers/duplicate.py:83-90.
13. **`check --encoding unicode` and `add` of a PDF use a third-party
    LaTeX-to-text converter** (not the table of 4.1), whose exact output
    is hard to reproduce. papers/encoding.py:21-30, papers/bib.py:698-700.
14. **Keys that differ by case are both read.** The parser rejects only
    exact duplicate keys; papers compares keys without case elsewhere, so
    a file with `Smith2000` and `smith2000` has two entries that the same
    selection cannot tell apart. papers/bib.py:261-262.
15. **"Exact duplicate" on key collision compares raw titles.** When an
    added entry has the key of a library entry, it is folded into it only
    if the titles are the same text (not normalized) and the same-paper
    rule says `same`. papers/bib.py:438-446.
16. **`and` inside braces: three different splits.** Name formatting
    (3.5) splits an author field only at brace depth 0, so
    `{Barnes and Noble}` is one name. The identity (9.2) and the
    equivalence of names (10.3) split on `and` inside braces too (two
    authors, family names `{Barnes` and `Noble}`). The family names of the
    key template split the formatted text again on ` and ` and on the
    first comma without regard to braces. Should all three split at depth
    0? Changing identity changes `distinct.json` matches.
    papers/duplicate.py:93-95; papers/encoding.py:91-93 versus
    papers/entries.py:221-241.
17. **`distinct.json` is read with the platform encoding.** It is written
    as UTF-8 with non-ASCII characters escaped, so papers' own files read
    the same everywhere; a file with raw UTF-8 characters (valid JSON,
    written by another implementation) is misread on Windows or with a
    non-UTF-8 locale. Should the contract require the `\uXXXX` escapes,
    or should reading be UTF-8? papers/duplicate.py:326.
