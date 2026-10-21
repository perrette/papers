# Duplicate detection and merge: review and v3 proposal

Reviewed: `master` at 44e9756 (`papers/duplicate.py`, `papers/bib.py`,
`papers/__main__.py`) and `v3:design/v3.md`. All examples below were run in
a scratch directory
with `--no-git`, an isolated `HOME`, and answers fed on stdin
(not kept). Fixtures:

- `lib0.bib`: `smith2020climate` (Smith, John and Doe, Jane; *Climate sensitivity
  revisited*; Nature; doi 10.1000/abc123; keywords `climate, mine`; file `files/smith.pdf`).
- `new.bib`: `Smith_2020`, the same paper (Smith, J. and Doe, J.; title in title case;
  Nature Climate Change; volume 10; DOI in upper case; file `other/smith-preprint.pdf`).
- `grp.bib`: the two entries above, plus `smith2019preprint` (@misc, same authors and
  title, *different* DOI 10.5194/egusphere-2019-1), plus an unrelated `brown2021`.

---

## 1. Current state

### 1.1 Identity: similarity levels (`bib.py: compare_entries`, `are_duplicates`)

`entry_id(e)` = (lower-case DOI, family names of authors + lower-case title).

| Level | Score | Condition | Used by |
|---|---|---|---|
| EXACT | 104 | all fields equal (`entry_content_equal`) | nothing in the CLI |
| GOOD | 103 | DOI and author+title both equal | nothing |
| FAIR | 102 | both have a DOI and the raw DOIs are equal (case-sensitive) | nothing |
| PARTIAL (default) | 101 | DOI equal **or** author+title equal, each compared only when both sides have it | `add`, `check --duplicates`, `list --duplicates` |
| FUZZY | 0-100 | `token_set_ratio(author+title)` >= 100 (the target is the constant 100) | nothing reachable |

`Biblio.similarity` is always PARTIAL: no configuration or command-line option changes it.
`list --similarity` is parsed but never read (`list --duplicates` hard-codes PARTIAL and
also groups entries with the same key).

### 1.2 Options

| Command | Option | What it does |
|---|---|---|
| `add` | `-m/--mode {i,u,U,o,s,r,a}` (default `i`) | what to do when the added entry is a duplicate; letters as in table 1.3 |
| `add` | `--no-check-duplicate` | no duplicate search; files are not merged; a key collision still raises, except when the titles are equal, then the new entry is dropped silently |
| `add` | `--no-merge-files` | do not union the `file` fields before comparing; a different `file` then counts as a conflict |
| `add` | `-u/--update-key` | regenerate the key of every added entry from the template; on a duplicate, give the new entry the existing key first. **Also decides whether `U`/`o` keep the library key** (see problem 2) |
| `check` | `--duplicates` | group the library by the PARTIAL rule and resolve each group |
| `check` | `-m/--mode {i,m,s}` (default `i`) | (i)nteractive, (m)erge every group, (s)kip |
| `check` | `--force` | turns `-m i` into `-m s` |
| `list` | `--duplicates` | entries that share a key or are PARTIAL duplicates |
| `list` | `--duplicates-key`, `--duplicates-doi`, `--duplicates-tit` | group by key, by valid DOI, by title only |
| `list` | `--similarity` | no effect |
| `list` | `--fuzzy`, `--fuzzy-ratio` | fuzzy matching of search words (not of duplicates) |

Total: 11 options and 3 letter vocabularies for one concept.

### 1.3 Add-time menu (`conflict_resolution_on_insert`)

Appears when an added entry is a PARTIAL duplicate of a library entry and is not
equal to it after the files were unioned (and, with `-u`, after the key was copied).
Only the most similar library entry is offered, even if several match.
The view is a `difflib.ndiff` of the two formatted entries (`-` existing, `+` new, `?`
character markers).

| Letter | Menu text | What it really does (tested) |
|---|---|---|
| `u` | update existing with the new entry's missing fields | library values kept, missing fields added (`volume`), key kept. Files already unioned. |
| `U` | update existing with the new entry's values | new values win **including the key**: `smith2020climate` became `Smith_2020` (reported as Removed + Added). With `-u` the key is kept. |
| `o` | overwrite: replace the existing entry entirely | new entry replaces the old one: key changes to `Smith_2020` (without `-u`), `keywords = {climate, mine}` is lost. Files unioned. |
| `s` | skip the new entry (keep the existing one unchanged) | the existing entry **is changed**: the new file is added to it (reported "Modified"). |
| `a` | append the new entry anyway | both entries kept, **both** get the union of the two files. If the new entry has the same key as the existing one, the whole `add` aborts with `Key conflict. Try update_key is True ...` after the user chose `a`, and nothing is saved. With `-u` the new entry gets key `smith_doe2020`. |
| `e` | edit the merged diff in an editor | opens the raw ndiff text, with `-`/`+`/`?` markers. Saved as is, it fails to parse, and the fallback keeps `[old, new]`: the new entry is **appended** (tested with `EDITOR=cat`). |
| `E` | edit both entries separately | editor with both entries as bibtex |
| `r` | raise an error (abort) | `ERROR: conflicting entries`, whole `add` aborted, nothing saved |

No quit letter. End of input gives `ERROR: EOF when reading a line`.

### 1.4 `check --duplicates` group menu (`DuplicateHandler.interactive_loop`)

Appears for every group of 2 or more entries linked by the PARTIAL rule (grouping is
transitive: A~B by DOI and B~C by title make one group). Default view is a split view
of all entries, numbered, with `*` on the "most complete" entry (`score`: valid DOI,
title, author, file, number of fields).

| Choice | Menu text | What it really does (tested) |
|---|---|---|
| `N` | keep only entry N, delete the others | others removed **with their file links** (`other/smith-preprint.pdf` no longer linked; files stay on disk) |
| `N M` | keep entries N and M | idem |
| `-N` | keep all entries but entry N | **off by one**: `-1` removes entry 2, `-2` removes entry 1, `-3` is "invalid choice" (`entries[int('-1')-1]`) |
| `m` | merge the group into one entry | files unioned into every entry; conflicting fields (here also `ID` and `ENTRYTYPE`) taken from `*`; the merged entry is appended as (4) and the loop asks again; one more answer (`4`) is needed. Result key `Smith_2020`: the library key `smith2020climate` is gone, and the preprint with another DOI is folded in, its DOI dropped. |
| `f` | fetch metadata for `*` and add to the group | needs network (not tested) |
| `e` | edit the group in an editor | **crash** `KeyError: 'ENTRYTYPE_FIELD{REPLACE_ID'` when both type and key differ (grp.bib) |
| `d` | delete the whole group | asks `[y/N]`, removes entries, files kept |
| `n` | not duplicates: keep all, stop asking | kept; not remembered, the next `check --duplicates` asks again |
| `s` / `S` | skip this group / all remaining | group(s) untouched |
| `v` / `V` | view toggles (split, merged diff, line diff) | `v` **crashes** with the same KeyError on grp.bib; on a 2-entry group it shows a merged view with `⌄⌄⌄ --- ⌃⌃⌃` blocks that do not say which value is from which entry |
| `q` | quit | same as `S` |

End of input gives a Python traceback (`EOFError`) rather than an error message.
`check -m m` merges every group the same way as `m`, without review (tested:
`smith2020climate` and `smith2019preprint` disappear, `Smith_2020` stays).

### 1.5 Silent paths (no menu)

| Situation | Behaviour |
|---|---|
| added entry equal to a library entry | files unioned into the library entry |
| equal after copying the key (`-u`) or after the file union | idem |
| key collision with a non-duplicate, no `-u` | `Key conflict. Try update_key is True or specify --key KEY explicitly` (API wording) |
| key collision, same title, `--no-check-duplicate` | new entry dropped silently, with its file link ("Existing ->") |

---

## 2. Problems

1. **Three vocabularies for one decision.** `add -m` has 7 letters, the add menu 8, `check
   -m` 3, the check menu 16 choices. `s` means "skip the new entry" in add and "skip the
   group" in check; `e` means "edit the diff" in add and "edit the group" in check; `m`
   exists only in check, `u/U/o/a/r` only in add. No sentence describes both menus.

2. **The library key changes on `U` and `o`** unless `-u` is passed. Run: `printf 'U\n' |
   papers add new.bib --bibtex lib.bib` → `smith2020climate` becomes `Smith_2020`; any
   `\cite{smith2020climate}` breaks. With `-u` the key is kept. The option whose name says
   "update the key" is the one that preserves it.

3. **`check` merge drops a library key and picks a key by completeness score.** `m` on
   grp.bib keeps `Smith_2020` (the `*` entry) and removes `smith2020climate`; there is no
   way to choose which key survives except editing.

4. **The identity rule is wider than the stated one.** PARTIAL matches on author+title
   even when both entries have different DOIs: the 2019 preprint (`10.5194/...`) is grouped
   with the 2020 article, and `check -m m` merges them, losing the preprint's DOI. The rule
   decided for v3 ("DOI equal, or author+title when one has no DOI") would not group them.
   Also, an entry without authors matches any other entry with the same title only
   ("Editorial", "Introduction"), because the empty author string is concatenated.

5. **"Skip" is not skip.** Add menu `s` says "keep the existing one unchanged"; the
   existing entry gets the new file link (reported Modified). Meanwhile check `N` ("keep
   only entry N") removes the file links of the other entries. Files are unioned in one
   place and dropped in the other.

6. **Field-level decisions are not possible.** Both menus work on whole entries: keep one,
   or merge with every conflict taken from one side (`u`, `U`, `m` from `*`). To take the
   journal from one entry and the title from the other, the only path is the editor.

7. **Noise conflicts.** `doi = {10.1000/abc123}` vs `{10.1000/ABC123}`, title case, and a
   different key alone are shown as conflicts. An entry that differs only by key
   (`same.bib`, key `otherkey`) opens the full 8-letter menu. The ndiff `?` lines add
   three lines per changed field.

8. **The editor paths lose or duplicate data.** Add `e` writes the raw diff with markers;
   saving it unchanged is rejected and the fallback appends the new entry. Check `e`/`v`
   crash on groups where the entry type and key differ.

9. **`-N` deletes the wrong entry** (`-1` removes entry 2). This is the most dangerous
   item in the list: it looks like a selection and silently deletes. (Not one of the June
   fixes; it is a current bug.)

10. **`a` (append) can abort the whole run after the user's choice** when the new entry has
    the same key (`samekey.bib`), and nothing from that `add` is saved.

11. **Non-interactive use is unclear.** Default is `i` in both commands; without a terminal,
    `add` prints `EOF when reading a line`, `check` prints a traceback. `check --force`
    means skip. There is no "fail if any duplicate" for `check`, no "merge" for `add`.

12. **Dead and overlapping options.** `list --similarity` has no effect; EXACT/GOOD/FAIR and
    FUZZY are unreachable; `--duplicates-doi` is a subset of `--duplicates`, `--duplicates-tit`
    a near-superset, `--duplicates-key` should never find anything in a valid bibtex.
    `--no-merge-files` turns a file difference into a conflict that the menus then resolve by
    dropping one side's links (`U` replaces the link).

13. **"Not duplicates" is forgotten.** `n` stops asking for this run only.

---

## 3. Proposal

### 3.1 Identity

- **Same paper**: DOIs equal (case-insensitive); or, when at least one entry has no DOI,
  author family names and title equal after normalisation (case, braces, accents,
  whitespace), both non-empty. Different DOIs are never the same paper.
- Used by `add`, `check --duplicates`, `list --duplicates`, `pull`, `push`.
- `list --duplicates --fuzzy [--fuzzy-ratio N]`: also lists pairs whose author+title score
  at least N; listing only, never used to merge.
- Removed: `--similarity` and the five levels, `--duplicates-key`, `--duplicates-doi`,
  `--duplicates-tit`.

### 3.2 What a merge is

A merge combines one **target** entry (it keeps its key and its place) with one or more
**other** entries:

- fields present on one side only are added;
- `file` links are the union (deduplicated by path and checksum); never a conflict;
- values equal after normalisation (case, braces, whitespace, DOI case) are not
  conflicts: the target's spelling is kept;
- the key is the target's. Keys of other entries that were in the library (check) are
  added to the target's `ids` field (biblatex key aliases), so existing `\cite` commands
  keep working with biblatex; papers prints them either way;
- the remaining differences are **conflicts**, decided by the user or by the option.

Target per context:

| Context | Target (entry 1) | Other(s) | Conflict = |
|---|---|---|---|
| `add` | the library entry | the added entry (2) | values differ |
| `check --duplicates` | the entry chosen as target; proposed: the entry with most fields, listed first | the other entries (2, 3...) | values differ |
| `pull` | the library entry | the pool entry (2), compared with the origin copy | changed on both sides since origin |
| `push` | the pool entry | the library entry (2), compared with the origin copy | changed on both sides since origin |

In three-way mode a field changed only in the pool is an addition offered like a missing
field; a field changed only in the library is kept and not shown as a change.

Deleting entries is not part of the dialogue: merging removes the other entries after
their fields, files and keys have been taken over. `papers rm` deletes; it deletes files
only with `--files`.

### 3.3 Option

```
--on-duplicate {ask,keep,update,skip,error}
```

| Word | add | check --duplicates | pull / push |
|---|---|---|---|
| `ask` | dialogue | dialogue | dialogue for entries with conflicts |
| `keep` | merge into the library entry; conflicts keep the library value | merge each group; conflicts keep entry 1's value | merge; conflicts keep the receiving side's value |
| `update` | merge; conflicts take the added value | not available (no "new" side) | merge; conflicts take the incoming value |
| `skip` | the added entry is not added; the library entry, its files and the source file are untouched | groups untouched | entries with conflicts are not merged, the origin copy is not updated (they come again next time) |
| `error` | stop before saving, list the duplicates, exit status 1 | exit status 1 if any group exists (for scripts) | stop before saving if any conflict |

Defaults: `ask` when standard input is a terminal; otherwise see open question 1.
Exact duplicates (no conflict, no field to add) never ask: the files are unioned and the
entry is reported as `already in library: smith2020climate (+1 file)`.

Dropped from the draft list, and why:

- `overwrite`: removes fields the user added (tags, notes) and the key; `update` covers
  the useful part (take the new values). To start over: `papers rm` then `add`.
- `update-new`: same as `update`.
- `merge`: `keep` and `update` are both merges; the word names which side wins.
- `append`: keeping two entries for the same paper is not a resolution. The
  dialogue keeps it as `n` ("not the same paper"); non-interactively,
  `--no-check-duplicate` already does it.

`--no-merge-files`: removed (file links are always unioned). `-u/--update-key`: only
regenerates keys of entries that are new to the library; it no longer affects duplicates,
whose key is always the library's.

### 3.4 The dialogue

One screen layout and one set of answers. Entry 1 is always the target. Lines:

- `   field = value` same on all sides, or kept from the library (three-way);
- `+  field = value` added from another entry (missing in 1, or changed only in the pool);
- `!  field = value` conflict: line shows the value that will be used, the alternatives
  follow, numbered by entry.

Answers (only the ones that apply are shown):

| Answer | Meaning |
|---|---|
| `1` ... `N` | resolve all remaining conflicts with entry N's values, then save |
| `f` | go through the conflicts one at a time (and the `+` changes in three-way mode) |
| `e` | edit the merged entry in the editor: plain bibtex, alternatives as `%` comment lines below it |
| `t N` | (check only) make entry N the target: its key is kept |
| `n` | not the same paper. add: add the entry separately; check: leave the group as separate entries and remember it; pull: not offered |
| `s` | skip: change nothing for this one; asked again next time |
| `q` | quit: skip this one and all remaining |
| `?` | help |

`1` is what `--on-duplicate keep` does; `2` in add and pull is `--on-duplicate update`;
`s` is `--on-duplicate skip`. Field-by-field (`f`) asks, per conflict:

```
title:
  1  Climate sensitivity revisited        library
  2  Climate Sensitivity Revisited        new
  [1/2/e] >>>
```

**Add conflict** (`papers add new.bib`):

```
Already in library: smith2020climate (same DOI 10.1000/abc123)
  1  library   smith2020climate   files/smith.pdf
  2  new       Smith_2020         other/smith-preprint.pdf

@article{smith2020climate,
   author   = {Smith, John and Doe, Jane}
!                2: {Smith, J. and Doe, J.}
   doi      = {10.1000/abc123}
+  file     = {files/smith.pdf;other/smith-preprint.pdf}
   journal  = {Nature}
!                2: {Nature Climate Change}
   keywords = {climate, mine}
   title    = {Climate sensitivity revisited}
+  volume   = {10}
   year     = {2020}
}
2 conflicts. The key smith2020climate is kept; + lines are added.
  1 keep library values   2 take new values   f field by field   e edit
  n not the same paper (add Smith_2020 separately)   s skip   q quit
>>>
```

(The title and DOI differ only in case and are not conflicts.)

**Check group** (`papers check --duplicates`; a group of an article and a copy without DOI):

```
Same paper (title and authors): 2 entries
  1  smith2020climate   article  Nature   doi 10.1000/abc123   files/smith.pdf
  2  Smith_2020         article  -        no doi               other/smith-preprint.pdf

@article{smith2020climate,
!  key      = smith2020climate        2: Smith_2020 (kept in ids)
   author   = {Smith, John and Doe, Jane}
+  doi      = {10.1000/abc123}
+  file     = {files/smith.pdf;other/smith-preprint.pdf}
   journal  = {Nature}
!                2: {Nature Climate Change}
   title    = {Climate sensitivity revisited}
}
1 conflict. Entry 2 is removed after the merge; its key goes to ids.
  1 keep values of 1   2 take values of 2   f field by field   e edit
  t N make entry N the target   n not the same paper   s skip   q quit
>>>
```

**Three-way pull** (`papers pull`):

```
smith2020climate  <-  default pool (Smith_2020), changed since last pull
  1  library
  2  pool
     origin = pool version at last pull (2026-03-02)

@article{smith2020climate,
   author   = {Smith, John and Doe, Jane}
   keywords = {climate, mine}                       changed here, kept
+  volume   = {10}                                  added in pool
+  pages    = {100--110}                            added in pool
!  journal  = {Nature}                              changed on both sides
!                2: {Nature Climate Change}   origin: {Nat.}
   title    = {Climate sensitivity revisited}
}
1 conflict, 2 changes from the pool.
  1 keep library values   2 take pool values   f field by field   e edit
  s skip (pull again later)   q quit
>>>
```

### 3.5 Behaviour summary

- No key in the library changes as a result of a duplicate decision, except in `check`,
  where all but one key of a group must go: the user sees which, and the removed keys are
  kept in `ids`.
- File links are always unioned on merge; no answer deletes a file; `skip` does not touch
  files (and does not move the source file of `add`).
- Under `--on-duplicate keep` no library value is ever overwritten.
- The same letter means the same thing in add, check and pull.

---

## 4. Migration

| Old | New |
|---|---|
| `add -m i` | `--on-duplicate ask` (default) |
| `add -m u` | `--on-duplicate keep` |
| `add -m U` | `--on-duplicate update` (key now always kept) |
| `add -m o` | `--on-duplicate update` (fields only in the library are no longer removed, key kept); warning |
| `add -m s` | `--on-duplicate skip` (the new file is no longer attached; use `keep` for that) |
| `add -m r` | `--on-duplicate error` |
| `add -m a` | `--no-check-duplicate` |
| `add --no-merge-files` | removed (warning, ignored) |
| `add -u` | unchanged for new entries; no effect on duplicates |
| `check --duplicates -m i` | `check --duplicates` (`--on-duplicate ask`) |
| `check --duplicates -m m` | `--on-duplicate keep` (target = entry with most fields, other keys to `ids`) |
| `check --duplicates -m s` / `--force` | `--on-duplicate skip`; to only see the groups, `list --duplicates` |
| `list --similarity X` | removed (it had no effect) |
| `list --duplicates-doi`, `--duplicates-tit`, `--duplicates-key` | `list --duplicates` (`--fuzzy` for near matches); warning |
| add menu `u` / `U` | `1` / `2` |
| add menu `o` | `2`, or `e` |
| add menu `s` | `s` |
| add menu `a`, `E` | `n` |
| add menu `e` | `e` (plain bibtex, no diff markers) |
| add menu `r` | `q` (skips this and the remaining duplicates; decisions already made and non-duplicate entries are saved). To abort without saving anything: Ctrl-C |
| check menu `N` | `t N` then `N` (merge, keeping N's key and values; others' files and keys kept) |
| check menu `N M`, `-N` | `n` on the group, then `check` again; or `rm` |
| check menu `m` | `1` (or `f`) |
| check menu `f` (fetch) | `papers check --fetch KEY` before or after; not in the dialogue |
| check menu `e` | `e` |
| check menu `d` | `papers rm KEY...` |
| check menu `n` | `n` (now remembered) |
| check menu `s`, `S`/`q` | `s`, `q` |
| check menu `v`, `V` | removed (one view) |

Old `-m` letters can stay accepted with a deprecation warning that prints the new word.

---

## 5. Open questions

1. **Default without a terminal**: `error` (safe, tells the user which word to pass) or
   `keep` (never overwrites a library value, but adds fields and files without asking)?
   Proposed: `error`.
2. **Removed keys in `check`**: store them in the biblatex `ids` field (works for biblatex
   users, ignored by BibTeX), or only print them?
3. **`skip` versus `keep`**: is a mode that leaves the library entry completely untouched
   (no new fields, no new file) needed, or should `skip` only exist as the dialogue's
   "decide later"? Keeping it gives five words; dropping it gives four.
4. **Normalised equality**: treat author initials versus full first names
   (`Smith, J.` / `Smith, John`) as equal, keeping the library spelling, or as a
   conflict? Case, braces and DOI case are proposed as equal in any case.
5. **Remembering "not the same paper"**: where to store it (a `.papers/` file next to
   `origin.bib`, or a field in both entries), so that `check` and `pull` do not ask again?

---

## Appendix: current bugs found (independent of the redesign)

- `-N` in the check menu removes entry N+1 (`-1` removes 2), and `-n` for the last entry is
  rejected (`duplicate.py:383`, `entries[int(i)-1]` with a negative `i`).
- Check menu `v` and `e` crash with `KeyError: 'ENTRYTYPE_FIELD{REPLACE_ID'` when entries
  differ in both type and key (`entry_ndiff`, the placeholder regex `REPLACE_(.*)_FIELD`
  is greedy on the `@type{key,` line).
- Add menu `e`: an unedited diff is rejected and the new entry is appended.
- Add menu `a` with a same-key entry aborts the whole `add` without saving.
- `check --duplicates` without a terminal: `EOFError` traceback.
- `add` without `-u`: `U` and `o` replace the library key.
- `--no-check-duplicate`: key collision with the same title drops the new entry and its file.

---

## Decisions (2026-10-21)

1. **No terminal**: default `--on-duplicate error`; the error names the option to pass.
2. **Keys removed by a merge in `check`** are kept in the biblatex `ids` field, and printed.
3. **`skip` stays** a mode of its own (the library entry is left completely untouched), separate from `keep`.
4. **Initials versus full first names** (`Smith, J.` / `Smith, John`) are not a conflict;
   the fuller form is kept, whichever side it comes from (citation styles can always
   abbreviate). Different first names (`Smith, John` / `Smith, Jane`) are a conflict.
5. **Identity, in order**: DOI (case-insensitive); arXiv identifier (`eprint` with
   `archivePrefix = arXiv`); ISBN for two `@book` entries only (a chapter carries its
   book's ISBN, and editions have their own); otherwise author family names + title. Two
   entries with different values of the first identifier both have are not the same
   paper. **Title guard** (narrow): equal DOIs (or arXiv ids, ISBNs) are not merged
   automatically only when the entry types differ AND the titles clearly differ: the
   answer is "ask" (e.g. a `@incollection` exported with its `@book`'s DOI, a `@misc`
   dataset deposited under the `@article`'s DOI); without a terminal this stops like any
   other conflict (`error`). Same type and same DOI is always the same paper, whatever the
   titles. Chapters normally have their own DOI, so book and
   chapter are already distinct. Documented in the user docs.
7. **One implementation**: a single function `same_paper(a, b)` returns *same*,
   *different*, or *ask* (with the reason), applies the identifiers, the title guard and
   `.papers/distinct.json`, and is the only duplicate rule used by `add` (including
   `add DIR` and the pool lookup), `check --duplicates`, `list --duplicates` (which also
   lists the "ask" pairs), `pull` and `push`.
8. **Tests** cover each identifier (DOI, arXiv id, ISBN for books, author+title), the
   order between them, the title guard (types differ and titles differ: ask; same type or
   similar titles: same), name equality (initials vs full names, fuller form kept),
   `distinct.json` (recorded, honoured, merged on push/pull), and each `--on-duplicate`
   mode in `add`, `check`, `pull`.
6. **"Not the same paper"** is remembered in `.papers/distinct.json` of the library, as pairs
   of identities (DOI, arXiv id, ISBN, or normalized author+title), not keys, so that the
   file means the same in every library: `push`/`pull` merge it (union) with the pool's.
   Mostly needed for entries without DOI, and to stop the title guard from asking again
   about entries that share a DOI but are distinct.
