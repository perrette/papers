# Managing your library

## Move library to a new location

Moving a library can be tricky. Simple cases are:

- files are stored in a central repository, and the bibtex contains absolute
  paths. Then moving the bibtex by hand is fine.
- files are stored alongside the bibtex, and the bibtex contains relative
  paths. Just move around the folder containing bibtex and files.

In any other cases, you risk breaking the file links.

Papers tries to be as little opinionated as possible about how files are
organized, and so it relies on your own judgement and use case. When loading a
bibtex, it always interprets relative file links as being relative to the
bibtex file. When saving a bibtex, it will save file links according to the
`paths` setting of the library (relative to the bibtex by default, see
[Configuration](configuration.md#relative-versus-absolute-paths)).

To move the files directory, or some of its files, use `papers file mv`: it
updates the links of the entries, and the `filesdir` setting when the files
directory itself moves (see [Files](files.md#moving-files)):

```
papers file mv files ../shared/files
```

The following set of commands also works, provided the initial file links are
valid (optional parameters in brackets):

```
touch new.bib
papers add /path/to/old.bib --bib new.bib [ --copy | --link ] [ --filesdir newfilesdir ]
rm -f /path/to/old.bib
```

By default the files of `old.bib` are moved into the files directory
(`--copy` keeps them in place too, `--link` links to them where they are),
except the files inside the files directory of another library, which are
copied.

## Duplicates

It's easy to end up with duplicates in your bibtex. After adding PDFs, or every
once in a while, do:

```
papers check --duplicates
```

It groups the entries that are the same paper, by the rule of `papers add`
(same DOI, arXiv id, ISBN of two books, or else same authors and title; see
[Adding entries](adding-entries.md#same-paper)), and merges each group into
one entry. A group never holds two entries with different DOIs: a copy
without DOI that matches both goes with one of them, and the other comes up
on the next check if it is still a match.

Entry 1 of a group, the target, is the entry with most fields. The merge
works as in `papers add`: the target keeps its key, fields missing in it
are added, the file links are kept. The other entries are removed, and
their keys are added to the biblatex `ids` field of the target, so that
`\cite` commands with the old keys keep working with biblatex (BibTeX
ignores the field). Commands that take a KEY also accept a key of the `ids`
field.

```
$> papers check --duplicates
Same paper: 2 entries (same title and authors)
  1  smith2020climate  article  doi 10.1000/abc123  files/smith.pdf
  2  Smith_2020        article  no doi              other/smith-preprint.pdf

@article{smith2020climate,
!  key      = smith2020climate
!             2: Smith_2020 (kept in ids)
   author   = {Smith, John and Doe, Jane}
   doi      = {10.1000/abc123}
+  file     = {files/smith.pdf;other/smith-preprint.pdf}
+  ids      = {Smith_2020}
!  journal  = {Nature}
!             2: {Nature Climate Change}
   keywords = {climate, mine}
   title    = {Climate sensitivity revisited}
   year     = {2020}
}
1 conflict. Entry 2 is removed after the merge; its key goes to ids.
  1 keep values of 1   2 take values of 2   f field by field   e edit
  t N make entry N the target   n not the same paper   s skip   q quit   ? help
>>> 1
merged into smith2020climate: Smith_2020 (kept in ids)
```

The answers are those of the dialogue of `papers add` (see
[Adding entries](adding-entries.md#the-dialogue)), with one more: `t N`
makes entry N the target, so that its key is kept. `n` (not the same paper)
leaves the entries as they are and records them in `.papers/distinct.json`,
so that the next check does not ask again. A group whose entries differ
only by key and file links is merged without a question.

`--on-duplicate` sets what to do with each group without asking:

| Value | What happens |
|---|---|
| `ask` | the dialogue (default when the standard input is a terminal) |
| `keep` | merge; conflicts keep the value of entry 1 |
| `skip` | leave the groups as they are (the default with `-y/--yes`) |
| `error` | exit with status 1 if there is any group, and list them (default without a terminal) |

Groups that the title guard asks about (same DOI, but different entry types
and titles) are never merged with `keep`.

To only see the groups, use `papers list --duplicates` (see
[Listing](listing.md#duplicates)).

The `-m/--mode` option of earlier versions still works, with a warning:
`-m i` is `--on-duplicate ask`, `-m m` is `keep`, `-m s` is `skip`. To
remove entries, use `papers rm`.

## Checking and fixing files

`papers file check` reports broken links, files linked twice, identical
files and, with `--metadata`, DOIs of PDFs that differ from their entry's
DOI. It changes nothing. `papers file fix` applies the safe repairs
only. Broken links are removed with `papers file detach --broken`:

```
papers file check
papers file fix
papers file detach --broken
```

`papers file rename` places the files in the files directory under their
template name (see [Renaming files and keys](renaming.md)).

`papers file clean` removes the files of the files directory (and its
subfolders) that no entry links to:

```
papers file clean
```

It asks before removing anything, unless `-y/--yes` is passed. It ignores
hidden files and folders and `.bib` files; a folder with a `.{folder}.bib`
file inside, which is how versions before 2.19 stored entries with several
files (see
[Renaming files and keys](renaming.md#entries-with-several-files)), is removed
as a whole when no entry links to its files. That command works best when the
files are in their own folder, and not mixed up with other things, obviously.

`papers file clean --dry-run --yes` lists the files that no entry links to, without
removing them: a way to check what is actually tracked and what is not.

See [Files](files.md) for all the `papers file` commands. `papers filecheck`
is the deprecated form of these commands (it still works, with a warning).

## Two commands at the same time

A command that changes a library locks it while it runs: the file
`.papers/lock` says which command holds it (process and computer). A
command that changes a library and its pool (`add` in a shallow library,
`push`, `sync`, an undo that also undoes the pool's step) locks the library
first, then the pool. Another command that wants to change the same
library waits, with a line that names the command holding it, and stops
after 30 seconds with an error; nothing is written. Commands that only read
(`list` without an action, `status`, `export`, `file check`, `history`) do
not wait.

The holder touches the lock every 2 seconds. A lock that nobody touched
for 10 seconds, or that names a process of this computer that no longer
exists (e.g. after a crash), is stale: the next command takes it over. A
command that lost its lock (e.g. the computer was asleep) stops before it
writes.

The lock works for a library on a network drive, used from several
computers. It does not work for a folder kept in sync by a service
(Dropbox, Nextcloud, Syncthing...), where a file reaches the other
computers seconds or minutes later. There, papers notices a bibtex changed
outside papers since it read it, and does not write over it.
