# Shallow libraries

## What a shallow library is

A shallow library has a pool: the path of another library, in its `pool`
setting. It takes its entries from the pool and links to the pool's PDFs.
Its file links are those of the pool entries. The entries and PDFs that it
adds go to the pool too. The library decides which entries it has: the
pool usually has more.

A library without pool is self-contained: it has its own entries and its
own PDFs. See [Pools](pools.md) for the exchanges between a library and
its pool (`pull`, `push`, `sync`).

## `papers init --pool`

```
papers init [DIR] --pool PATH
```

creates a shallow library that uses the library PATH as pool. PATH must be
an existing library without pool of its own (a self-contained library):
`papers init --pool PATH` and `papers config pool PATH` stop with an error
otherwise, and nothing is created or changed:

```
$ papers init ~/projects/x --pool ~/projects/thesis
papers: error: --pool ~/projects/thesis: ~/projects/thesis has a pool itself (~/Documents/papers/sealevel): give a library without pool (nothing was changed)
```

The pool path is written in the configuration relative to the library when
it is given relative, or when it is under the library (e.g.
`../sealevel`); another path is written with `~` for the home directory,
or absolute. `papers init --shallow` uses the default library as pool (see
[A global shared library](global-library.md)).

A shallow library has no files directory of its own: `papers init --pool
PATH` does not create one.

## Files

In a shallow library, the file links are the pool entry's. The `files`
setting says how a new file gets to the pool:

- `move` (the default) and `copy`: the file is placed in the pool's files
  directory (moved, or copied: a hard link when possible), named with the
  pool's name template (a name template set on the library is not used);
  the library entry and the pool entry link to it there;
- `link`: the file stays where it is, and the library entry and the pool
  entry both link to it there. This works on one machine; on another
  machine that uses the pool (a pool in a synchronized folder), such links
  are broken.

What the commands do in a shallow library:

- `add` places new files as the `files` setting says, and adds the new
  entries to the pool too, whatever the `auto-push` setting (their origin
  is recorded, see [Origin copies](pools.md#origin-copies)). A change that
  `add` makes to the fields of an entry the library has already is pushed
  only with auto-push;
- `papers file attach` and `file rename` place the files they handle in
  the same way; `file fix` copies the files it finds outside the pool into
  the pool (hard links when possible) and never moves them, unless
  `--move` is given for the files of the `--search` folders;
- the file links are always pushed, whatever the `auto-push` setting: a
  command that changes the files of an entry (`file attach`, `file rename`,
  `file detach`, `file rm`, `file mv`, `file fix`, `edit`...) sets the
  links of the pool entry to match right away, and says so: `file links
  also updated in pool ...`. The pool entry gets the links that the
  command added, wherever they point, and the links of the library entry
  into the pool's files directory, and loses the links that the library
  entry no longer has. A link that the library entry had before the
  command, outside the pool's files directory, and that the pool entry
  does not have (for instance a file of the library's own `files/` from
  when it was self-contained) is not sent; `push` sends it with the other
  fields. Only the links change: the other fields are pushed only with
  auto-push. An entry not shared with the pool gets the links of the pool
  entry of the same paper updated; if the pool does not have it, the entry
  is added to the pool, as `add` does;
- removing a file and removing an entry are different:
  - `papers file detach KEY FILE` removes the link from the library entry
    and from the pool entry; the file stays;
  - `papers file rm FILE` removes the link from both and deletes the file,
    unless another entry of the pool or of the library still links to it
    (`kept FILE: an entry of the pool links to it`). The PDF is removed for
    every library that uses the pool;
  - `papers rm KEY` removes the entry from the library only. The pool entry
    and its files stay, and papers does not ask about them.
    `papers rm KEY --delete-files` (and `papers list ... --delete
    --delete-files`) is an error, and nothing is removed:

    ```
    $ papers rm perrette_yool2011 --delete-files
    papers: error: --delete-files: the files of a shallow library are the pool's: remove them with `papers file rm FILE`
    ```

- `pull` and `sync` with the pool link to the pool's files instead of
  copying them, and the library entry follows the pool entry's links: a
  link that the pool entry had at the last exchange and no longer has is
  removed from the library entry (the file is not deleted); `push` does
  not send it back to the pool, and the next `pull` removes it. A link that
  the pool entry never had stays. The origin copy records the pool entry's
  links for this, in its `file` field; an origin copy without it removes
  nothing until the next exchange;
- when the pool renames a file, the link breaks. It is repaired by looking
  the entry up in the pool when the library is loaded (saved on the next
  write), and by `papers file fix`. `papers file check` reports it
  meanwhile, with the new name `(from the pool)`. A broken link to a file
  outside the pool is relinked to the pool's file by `papers file fix`
  only, and `papers file fix --pool PATH` also takes the files of the same
  paper in another library PATH, copied into the pool (see
  [Reconnecting PDFs and a bibtex](files.md#reconnecting-pdfs-and-a-bibtex)).

Deleting a file of the pool, with `papers file rm` in a shallow library or
in the pool itself, breaks the links of the other libraries that use it,
until their next `pull` or `sync` removes the link. `papers file check`
shows the broken link meanwhile. The pool keeps no list of the libraries
that depend on it.

A project folder shared with coauthors (git, Dropbox...) should be a
self-contained library: the links of a shallow library point into your own
pool, which the others do not have. Such a project can still exchange
entries with your libraries through `--pool PATH` (see
[Exchanges with any library](pools.md#exchanges-with-any-library)).

A pool can be in a folder synchronized by a cloud client on the local disk
(e.g. `~/Dropbox/papers`): papers reads and writes the files there, and
the client synchronizes them.

## Changing the pool

`papers config pool PATH|none` changes the state of a library, and its
files follow. When a change copies files or deletes the library's copies,
papers lists what it will do and asks `Continue? [y/N]`; `-y` answers yes,
`--dry-run` only shows the list, and without a terminal the command stops
with the list (pass `-y`). The files of a pool are never deleted.

| Command | In a self-contained library | In a shallow library |
|---|---|---|
| `papers config pool PATH` | the library becomes shallow: it links to the copies of its PDFs in PATH, and its own copies are deleted (see below) | the library links to the copies of its PDFs in the new pool (see below); the files of the former pool stay where they are |
| `papers config pool none` (or `--unset pool`) | nothing to do | the library becomes self-contained: the pool files that it links to are copied into its files directory (hard links when possible), named with its name template, and the links rewritten; the pool keeps its files |

PATH must be an existing library without pool. Each PDF that the library
links to must already be linked by the entry of the same paper in PATH:
the same file, or a file of the same content. Entries without PDF need not
be in PATH, and broken links do not count (`papers file fix` relinks them
afterwards). If an entry has a PDF that PATH does not have, nothing is
changed, and the command lists the entries (the first ten, and the number
of the others) and the command that copies their PDFs there:
`papers push --pool PATH KEY...`, or `papers push --pool PATH --all` when
there are more than ten.

Otherwise the library links to the copies in PATH. The library's own
copies, in its files directory, are deleted, unless an entry of the
library or of PATH still links to them; nothing is copied or moved. These
commands do not push entries or merge fields: `papers push` does that. The
origin copies of the entries exchanged with PATH before (with `--pool
PATH`) are those of the new pool.

### From a self-contained project to a shallow one

To move the PDFs of a self-contained library into another library, and
make the library shallow:

```
papers init PATH                # if PATH is not a library yet
papers push --pool PATH --all   # copies the entries and their PDFs to PATH
papers config pool PATH         # links to the copies in PATH, deletes the library's own
```

For a project with one PDF and the library `~/Documents/papers/arctic`:

```
$ papers config pool ~/Documents/papers/arctic
papers: error: pool ~/Documents/papers/arctic: 1 entry links to PDFs that the pool ~/Documents/papers/arctic does not have (nothing was changed): perrette_landerer2013
Copy them to the pool first: `papers push --pool ~/Documents/papers/arctic perrette_landerer2013`
Then run `papers config pool ~/Documents/papers/arctic` again.
$ papers push --pool ~/Documents/papers/arctic --all
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1) [to pool ~/Documents/papers/arctic]
$ papers config pool ~/Documents/papers/arctic -y
link to the copies in the pool ~/Documents/papers/arctic for 1 file (same content); the library's copies in files (1 file) are deleted
Modified -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1)
pool = ~/Documents/papers/arctic (in ~/projects/old-paper/.papers/config.json)
the library is now shallow: it links to the PDFs of the pool entries, and `papers add` adds its new entries to the pool
delete ~/projects/old-paper/files/perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf (hard link: the other links remain)
```

## Auto-push

`papers config auto-push true` in a shallow library makes the commands that
change entries push them to the pool: `add`, `edit`, `tag`, `list
--add-tag` and the other actions of `list`, `check`, `file attach`, `file
rename`, `file detach`, `file rm`, `file mv` and `file fix`. After the
command, the entries it changed that are shared with the pool (the pool
has the same paper), and the entries new to the library, are pushed as
`papers push KEY...` would push them, files included. The other entries
are not pushed: an entry removed from the pool is noted once (see
[Removed entries](pools.md#removed-entries)). In a
self-contained library, the setting has no effect (it has no pool; the
libraries of `--pool PATH` only get what `push` and `sync` send).

```
$ papers config auto-push true
$ papers tag perrette_landerer2013 --add sealevel
Modified -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1, sealevel) [also modified in pool ~/Documents/papers/sealevel]
```

- `rm` is never pushed: removing an entry from the library does not
  remove it from the pool.
- A conflict (the same field changed in the pool since the last exchange)
  does not stop the command: the entry is saved in the library, is not
  pushed, and its line says so:

```
$ papers tag Smith_2020 --add bar
Modified -> Smith_2020: Climate sensitivity revisited (doi:10.1000/abc123, foo | bar) [not pushed: changed in the pool too; papers sync decides]
```

With `auto-push false` (the default), nothing is pushed automatically,
apart from the new entries of `add` and the file links (see
[Files](#files)): run `papers push` or `papers sync`.

## Use case: topic libraries

Two topic libraries, each self-contained, and two projects, each shallow
on one of them:

- `~/Documents/papers/sealevel` and `~/Documents/papers/arctic`: the topic
  libraries, with the PDFs;
- `~/projects/thesis`: a thesis, shallow on `sealevel`;
- `~/projects/arctic-paper`: a paper, shallow on `arctic`.

```
$ papers init ~/Documents/papers/sealevel
created the library ~/Documents/papers/sealevel
* bibtex:  papers.bib
* files:   files (the files directory of the library)
`papers config` lists and sets the settings
$ papers init ~/Documents/papers/arctic
created the library ~/Documents/papers/arctic
...
$ papers init ~/projects/thesis --pool ~/Documents/papers/sealevel
created the library ~/projects/thesis
* bibtex:  papers.bib
* files:   in the pool (shallow library)
* pool:    ~/Documents/papers/sealevel
`papers config` lists and sets the settings
$ papers init ~/projects/arctic-paper --pool ~/Documents/papers/arctic
created the library ~/projects/arctic-paper
...
```

Each project adds its papers. They go to its topic library:

```
$ cd ~/projects/thesis
$ papers add ~/Downloads/esd-4-11-2013.pdf
Added -> perrette_landerer2013: A scaling approach to project regional sea level rise and it... (doi:10.5194/esd-4-11-2013, file:1) [also added to pool ~/Documents/papers/sealevel]
$ cd ~/projects/arctic-paper
$ papers add ~/Downloads/bg-8-515-2011.pdf
Added -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, file:1) [also added to pool ~/Documents/papers/arctic]
$ ls ~/projects/arctic-paper ~/Documents/papers/arctic/files
~/Documents/papers/arctic/files:
perrette_et_al_2011_near-ubiquity-of-ice-edge-blooms-in-the-arctic.pdf

~/projects/arctic-paper:
papers.bib
```

### A paper relevant to both topics

A shallow library has one pool. The thesis also cites
`perrette_yool2011`, which is in `arctic`. `papers add --pool` takes it
from `arctic`, without a query to crossref:

```
$ cd ~/projects/thesis
$ papers add --pool ~/Documents/papers/arctic --doi 10.5194/bg-8-515-2011
Added -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, file:1) [from pool ~/Documents/papers/arctic; also added to pool ~/Documents/papers/sealevel]
$ ls ~/Documents/papers/sealevel/files
perrette_et_al_2011_near-ubiquity-of-ice-edge-blooms-in-the-arctic.pdf
perrette_et_al_2013_a-scaling-approach-to-project-regional-sea-level-rise-and-its-uncertainties.pdf
```

The entry is now in the thesis and in `sealevel`. Its PDF is copied into
the files directory of `sealevel`: a hard link when both libraries are on
the same disk. `papers pull --pool ~/Documents/papers/arctic
perrette_yool2011` does the same.

The thesis records an origin copy for `arctic`. A later change in `arctic`
comes with `papers pull --pool`, and goes to `sealevel` with `papers push`:

```
$ papers -C ~/Documents/papers/arctic tag perrette_yool2011 --add blooms
Modified -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, file:1, blooms)
$ papers pull --pool ~/Documents/papers/arctic
Modified -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, file:1, blooms) [from pool ~/Documents/papers/arctic]
$ papers push
Modified -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, file:1, blooms) [in pool ~/Documents/papers/sealevel]
```

The paper project gets the change from its own pool:

```
$ cd ~/projects/arctic-paper
$ papers status
...
* pool:    ~/Documents/papers/arctic (pool changed)
`papers pull --dry-run` shows the changes, `papers pull` takes them
$ papers pull
Modified -> perrette_yool2011: Near-ubiquity of ice-edge blooms in the Arctic (doi:10.5194/bg-8-515-2011, file:1, blooms) [from pool ~/Documents/papers/arctic]
```

`papers sync --pool ~/Documents/papers/arctic` in the thesis also sends
the changes made in the thesis to `arctic`. The two topic libraries can
also exchange entries directly, e.g. `papers -C ~/Documents/papers/sealevel
pull --pool ~/Documents/papers/arctic perrette_yool2011`; the thesis then
takes the entry from its pool with `papers add --doi`.

## Comparison

Three ways to use papers with several libraries:

- a **shared files folder** (papers 2): several self-contained libraries
  with a common files directory, and no pool;
- **shallow libraries**: projects with a pool;
- **self-contained libraries** that exchange entries with `--pool PATH`.

| | Shared files folder | Shallow libraries | Self-contained, `--pool PATH` |
|---|---|---|---|
| Setup | `papers init --filesdir FOLDER` in each project | `papers init POOL`, then `papers init --pool POOL` in each project | `papers init` in each library |
| Where the PDFs are | in the common folder, one copy | in the pool's files directory, one copy; the projects link there | in each library's files directory; a copy is a hard link when possible |
| Entries | each library has its own; a change in one does not reach the other | the project chooses which pool entries it has; new entries go to the pool; changes go with `push`, `pull` and `sync` (or auto-push); file links always follow | each library has its own; the entries exchanged are kept in step by `pull`, `push` and `sync` with `--pool PATH` |
| `add` of a paper another library has | reads the PDF again and fetches the entry from crossref (from the cache when the same DOI was fetched on this machine) | takes the pool entry, without query; links to the pool's PDF | `papers add --pool PATH` takes the entry and a copy of its files, without query; `papers add` alone fetches the entry |
| A file renamed | the link of the other libraries breaks | the links of the other shallow libraries are repaired from the pool, when loaded or by `papers file fix` | each library has its own copy: the others are not affected |
| A file removed | the other libraries keep a broken link | the PDF is removed for every library of the pool; their next `pull` or `sync` removes the link | each library removes its own copy only |

### Warnings for a shared files folder

A library configuration of papers 2 has no `pool` setting: it is read as a
self-contained library, as in papers 2. A shared files folder is enough
when the libraries are independent and you do not want a shared
bibliography. To set it up:

```
papers init --filesdir ~/Documents/pdfs   # a new library
papers config filesdir ~/Documents/pdfs   # an existing library
```

Each library only knows its own entries. What to watch for:

- `papers file clean` in one library lists the PDFs of the other
  libraries in the shared folder as unlinked, asks about each, and deletes
  them once confirmed (all of them with `-y`). `papers file clean
  --dry-run -y` shows the list and deletes nothing.
- `papers rm --delete-files` and `papers file rm` keep a PDF that another
  entry of the same library links to, but not one that another library
  links to.
- `papers file rename` in one library renames the shared PDF, and the
  link of the other library breaks. `papers file check` reports the broken
  link there. `papers file fix --pool OTHER` relinks it to the file of the
  same paper in the other library (copied, a hard link when possible), and
  `papers file fix --search FOLDER` if the new name
  is the one that the library's name template gives the entry (the two
  libraries use the same template); otherwise attach the renamed file with
  `papers file attach KEY FILE`, and remove the link with
  `papers file detach --broken --key KEY`.
- `papers push --pool PATH --all` then `papers config pool PATH` in one
  library deletes the shared PDFs once PATH has copies, and the links of
  the other library break. Once the other library uses the same pool
  (`papers config pool PATH`, which counts the broken links),
  `papers file fix` relinks them to the pool's files (see
  [Reconnecting PDFs and a bibtex](files.md#reconnecting-pdfs-and-a-bibtex)).
