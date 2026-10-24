# Git integration

papers can keep the history of a library in a git repository of its own,
the backup directory. Every command that writes the bibtex then commits a
snapshot there. This history is what `papers undo`, `papers redo` and
`papers restore` use (see [Undo and redo](undo-redo.md)).

## Turning the backup on and off

`papers init` turns the backup on when the `git` program is installed
(unless the global configuration sets `git`, see
[Global configuration](configuration.md#global-configuration)).
`--git` and `--no-git` choose explicitly, and `--git-lfs` also backs up the
attached files (see [git-lfs](#git-lfs)):

```
$> papers init --bibtex papers.bib --filesdir files [ --no-git | --git-lfs ]
created the library ~/projects/sealevel
* bibtex:  papers.bib
* files:   files (the files directory of the library)
* backup:  git and git-lfs
`papers status -v` shows all settings
```

The `* backup:` line says `git`, `git and git-lfs`, or `off`. With `--git`
or `--git-lfs`, `papers init` stops with an error before creating the
library when git (or git-lfs) is not installed; so does
`papers config git true`.

The setting can be changed at any time:

```
papers config git true        # start the backup (first snapshot: the current bibtex)
papers config git false       # stop committing (the backup directory stays)
papers config git-lfs true    # also back up the files (sets git true)
```

`papers config git false` also sets `git-lfs` to false. Libraries made by
older papers versions keep their saved setting. The `--no-git` option of a
command skips the commit of that command.

## What is backed up

Each save commits, in the backup directory:

- a copy of the bibtex, under its own name (e.g. `papers.bib`);
- the origin copies of the entries exchanged with a pool,
  `.papers/origin/*.bib` (one file per pool, see
  [Pools](pools.md#origin-copies));
- `.papers/distinct.json`, the pairs recorded as not the same paper;
- with git-lfs only: the attached files and `backup_clean.bib` (see
  [git-lfs](#git-lfs)).

A command that changes no entry and no file of `.papers/` (e.g. `papers
check` that finds nothing, `papers add` of a duplicate that is skipped, a
`pull` with nothing to take) does not write the bibtex and commits
nothing.

The commit message is the command, e.g. `papers add paper.pdf`. A library
file of `.papers/` that was removed from the library is removed from the
next snapshot. The library configuration, `.papers/config.json`, is not
backed up: `papers restore`, `undo` and `redo` leave it as it is.

`papers restore`, `undo` and `redo` restore the bibtex and the files of
`.papers/` together. `undo`, `redo` and `restore --ref COMMIT` also remove
the files of `.papers/` that the restored snapshot does not have. Without
the backup, `papers undo` only swaps the bibtex with its previous version
(`.papers.bib.backup`, next to the bibtex), and `papers restore` is an
error.

A commit that fails (e.g. refused by a git hook) prints a warning: the
bibtex is saved anyway.

Each commit stores the whole bibtex; once the backup directory has 150
such objects (about 50 commits), the command that commits packs them with
`git repack`, which keeps only the differences between versions (about 2 s
for a library of 10000 entries, 9 s for 30000).

## Where

The backup directory is a subfolder of the backup folder of the machine,
whatever the location of the library: `~/.local/share/papers/backups` on
Linux (`$XDG_DATA_HOME/papers/backups` when `XDG_DATA_HOME` is set), the
platform's user data directory elsewhere (on macOS,
`~/Library/Application Support/papers/backups`). `papers status -v` shows
the backup directory of the library:

```
* backup (git):       True
* backup files (git-lfs): False
* backup directory:   /home/me/.local/share/papers/backups/sealevel-papers-3f9a1c2b
```

The directory is named after the parent folder of the bibtex and the
bibtex, plus a hash of the full path of the bibtex (e.g.
`sealevel-papers-3f9a1c2b` for `~/projects/sealevel/papers.bib`), so that
two libraries never share a directory. The library configuration stores
this name (`"gitdir"`), which each machine looks up in its own backup
folder; a backup directory outside that folder is stored as an absolute
path. Each backup directory also has a `manifest.json` (not committed) that
records the bibtex it backs up.

`papers backup list` lists the backup directories papers knows of (those of
the backup folder, those of `~/.local/share/papers/backups` on other
platforms than Linux, and the one of the current library), with the bibtex
each backs up, whether that bibtex still exists, and the number of
snapshots. `papers backup remove NAME...` removes backup directories, e.g.
those whose library was deleted. `NAME` can be a glob pattern
(`papers backup remove 'old-*'`). It asks before removing each directory,
unless `-y/--yes` is passed (`-f/--force` is the deprecated form of
`-y`). `papers uninstall --remove-backup` removes the backup directory of
the library with its configuration.

## `papers git`

`papers git ARGS...` runs `git ARGS...` in the backup directory of the
library, e.g.

```
papers git log --oneline
papers git remote add origin REMOTE-URL
papers git push -u origin main
```

The branch of the backup is `main`. When git fails, it prints its own error
message, and papers exits with git's exit code. `papers git` needs a
library whose backup directory exists.

The backup is separate from any git repository the library is in: papers
never commits to the repository of a project, and `papers git` does not run
in it. The backup history is still the basis of `papers undo` and
`papers redo` in such a library. To commit only the configuration of a
library to the repository of a project, see
[Configuration](configuration.md#relative-versus-absolute-paths) for the
`.gitignore` lines.

## git-lfs

With `git-lfs` set, the attached files are also backed up. They are
hard-linked into the `files/` folder of the backup directory, which git-lfs
tracks, and `backup_clean.bib`, a copy of the bibtex whose file links point
into `files/`, is committed with them, so that the backup is
self-contained. Background in
[issue 51](https://github.com/perrette/papers/issues/51).

- Since the file in the backup directory is a hard link, a file edited in
  place in the library is also edited there, until the next save commits
  it. The git store of the backup (`.git/lfs`) keeps its own copy of each
  committed version of a file.
- `papers restore`, `undo` and `redo` first reset the backup directory to
  the committed snapshot, so they restore the committed version of the
  files. A link of the restored bibtex to a file that no longer exists
  points to the copy in the backup directory, unless `--restore-files` is
  passed: then the file is copied back to where the bibtex links to it.

## Pools and shallow libraries

A pool is a library, with its own backup. A command that writes both a
library and its pool (`add` in a shallow library, `push`, `pull`, `sync`,
a command with auto-push) commits a snapshot in each backup, each with its
own setting: the pool's commit is in the pool's backup directory.
`papers undo` in the library undoes the change of the library only;
`papers -C POOL undo` undoes the change of the pool (see
[Undo in a pool](pools.md#undo-in-a-pool) and
[Undo in a library that has a pool](undo-redo.md#undo-in-a-library-that-has-a-pool)).

A shallow library links to the files of its pool. With `git-lfs` set in
the shallow library, its backup hard-links and commits the pool files that
its entries link to, the same way as the files of a self-contained library:
a file shared with the pool is then in both backups if the pool also has
`git-lfs`.

## Backups of earlier versions

- Backup directories created by older papers versions, named after the
  bibtex alone, keep their name and are used as they are. If a backup
  finds that its directory belongs to another library (its `manifest.json`
  names another bibtex), the library moves to a new backup directory
  instead of mixing the two histories, with an error message.
- The libraries of papers 2.2 to 2.4 kept their backup in `.papers/` next
  to the bibtex, the folder of `config.json`, `origin/` and
  `distinct.json` since papers 3. The first backup moves that repository
  (its history and the files it tracks) to a new subfolder of the backup
  folder, with a warning, and the library configuration records it.
- Backups made with git-lfs by earlier papers versions tracked `files/`, a
  pattern that git-lfs does not apply to the files in that folder (they were stored as
  plain git files). The next save adds `files/**` to `.gitattributes`
  and stores the files with git-lfs from then on.
