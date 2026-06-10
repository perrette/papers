"""Git-based backup of the bibliography, and the undo/redo machinery built on it.

When papers is installed with --git, every save of the bibtex file is
mirrored to a dedicated git repository (``config.gitdir``, under
``~/.local/share/papers/backups`` by default):

- a verbatim copy of the bibtex file, tracked under its own name
  (e.g. ``papers.bib``)
- with --git-lfs only: ``backup_clean.bib``, a derived copy with file paths
  expressed relative to the backup directory, plus the attached files
  hard-linked into a ``files/`` subdirectory so they are backed up too

(Older versions tracked the verbatim copy as ``backup_copy.bib`` and wrote
``backup_clean.bib`` unconditionally; the next snapshot drops the legacy
names, and restore still understands them when materializing old snapshots.)

Each save is committed on a single ``main`` branch, and history is
append-only: nothing is ever reset away. Undo, redo and
``restore-backup --ref`` append a *restore commit* whose tree is the older
state, marked with a ``Papers-Restores: <commit>`` trailer naming the state
it represents. That trailer doubles as the cursor: a consecutive undo walks
back from the restored state rather than from the tip, and redo walks the
first-parent chain forward again, skipping restore commits. Making a new
change while undone simply appends on top; the states that were still
redoable remain in history and can be recovered with further undos or
``restore-backup --ref``.

Repositories last written by the pre-append-only model (which moved a
``history`` branch around with ``git reset --hard``) are adopted on first
use: their checked-out state is recorded onto ``main`` as a restore commit.

Each backup repository carries an (untracked, git-excluded) ``manifest.json``
naming the bibtex file it backs up. Backup directories are allocated under
``BACKUP_DIR`` as ``<slug>-<sha256(absolute bibtex path)[:8]>``, so two
libraries can never share a directory by name; the manifest is the safety
net for directories allocated by older versions (or set by hand): any backup
operation that finds a manifest belonging to another library moves the
current library to a fresh directory instead of mixing histories, whereas an
explicit ``papers install`` claims the directory for its bibtex.
"""
import copy
import hashlib
import json
import logging
import os
import shlex
import shutil
import subprocess as sp
import sys
from datetime import datetime, timezone
from pathlib import Path

from papers import logger, __version__
from papers.entries import get_entry_val
from papers.utils import checksum, move, PapersExit

MANIFEST_NAME = "manifest.json"
# version of the backup directory layout, recorded in the manifest
# (2: verbatim copy tracked under the bibtex's own name, clean copy only with --git-lfs)
LAYOUT_VERSION = 2


def run_git(gitdir, cmd, check=True):
    """Run a git command in the backup repository.

    ``cmd`` may be a string (split into arguments like a shell would,
    but without going through a shell) or a list of arguments.
    Output is captured; on failure git's stderr is logged, and a
    ``CalledProcessError`` is raised if ``check`` is true.
    """
    args = shlex.split(cmd) if isinstance(cmd, str) else [str(a) for a in cmd]
    logger.debug(f"git -C {gitdir} {' '.join(args)}")
    res = sp.run(['git'] + args, cwd=gitdir, capture_output=True, text=True)
    if res.returncode != 0:
        message = f"Command failed: 'git {' '.join(args)}': {res.stderr.strip()}"
        if check:
            logger.error(message)
            raise sp.CalledProcessError(res.returncode, ['git'] + args, res.stdout, res.stderr)
        logger.debug(message)
    return res


def default_gitdir(bibtex):
    """Allocate a backup directory name for a bibtex file.

    A human-readable slug plus a hash of the resolved absolute path, so that
    two libraries can never map to the same directory (a bare slug of the
    bibtex name used to collide, e.g. any local 'papers.bib').
    """
    from slugify import slugify
    from papers.config import BACKUP_DIR
    path = Path(bibtex).resolve()
    stem = path.stem or "library"
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:8]
    return os.path.join(BACKUP_DIR, f"{slugify(stem)}-{digest}")


def legacy_gitdir(bibtex):
    """The backup directory name older versions derived from the bibtex path."""
    from slugify import slugify
    from papers.config import BACKUP_DIR
    bibtex = str(bibtex)
    stem = bibtex[:-len(".bib")] if bibtex.endswith(".bib") else bibtex
    return os.path.join(BACKUP_DIR, slugify(stem))


def resolve_gitdir(bibtex):
    """Pick the backup directory for a bibtex: an existing one if any, else a new name."""
    new = default_gitdir(bibtex)
    if os.path.exists(new):
        return new
    for legacy in {legacy_gitdir(bibtex), legacy_gitdir(Path(bibtex).resolve())}:
        if os.path.exists(legacy):
            return legacy
    return new


def read_manifest(gitdir):
    f = Path(gitdir) / MANIFEST_NAME
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError) as error:
        logger.warning(f"unreadable backup manifest {f}: {error}")
        return None


def write_manifest(gitdir, bibtex, created=None):
    manifest = {
        "bibtex": str(Path(bibtex).resolve()),
        "created": created or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "layout": LAYOUT_VERSION,
        "papers_version": __version__,
    }
    _exclude_from_git(gitdir, MANIFEST_NAME)
    (Path(gitdir) / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def _exclude_from_git(gitdir, name):
    """Exclude `name` via .git/info/exclude: the manifest describes the directory
    itself and must not be tracked (restore commits would revert it) nor swept
    by `git clean -f` (a .gitignore would itself be untracked)."""
    exclude = Path(gitdir) / ".git" / "info" / "exclude"
    if not exclude.parent.is_dir():
        return
    lines = exclude.read_text().splitlines() if exclude.exists() else []
    if name not in lines:
        exclude.write_text("\n".join(lines + [name]) + "\n")


def claim_gitdir(config):
    """Mark config.gitdir as backing up config.bibtex (explicit install)."""
    manifest = read_manifest(config.gitdir)
    if manifest is not None and Path(manifest.get("bibtex", "")) != Path(config.bibtex).resolve():
        logger.warning(f"backup directory {config.gitdir} previously backed up {manifest.get('bibtex')}; "
                       f"it now backs up {config.bibtex} (history of both remains in `papers git log`)")
    write_manifest(config.gitdir, config.bibtex, created=manifest.get("created") if manifest else None)


def check_gitdir_ownership(config):
    """Ensure config.gitdir backs up config.bibtex before any backup operation.

    Pre-manifest directories are adopted for the current library. A directory
    whose manifest names another library is left untouched: the current
    library moves to a freshly allocated directory instead of mixing
    histories (collision healing).
    """
    gitdir = Path(config.gitdir)
    if not (gitdir / ".git").exists():
        return
    manifest = read_manifest(gitdir)
    bibtex = Path(config.bibtex).resolve()
    if manifest is None:
        logger.info(f"write backup manifest for {bibtex} in {gitdir}")
        write_manifest(gitdir, bibtex)
        return
    if Path(manifest.get("bibtex", "")) == bibtex:
        return

    # collision: this directory belongs to another library
    newdir = default_gitdir(bibtex)
    n = 2
    while Path(newdir) == gitdir or (
            read_manifest(newdir) is not None
            and Path(read_manifest(newdir).get("bibtex", "")) != bibtex):
        newdir = default_gitdir(bibtex) + f"-{n}"
        n += 1
    logger.error(f"backup directory {gitdir} belongs to another library ({manifest.get('bibtex')}) "
                 f"-- the present library moves to a fresh backup directory: {newdir}")
    config.gitdir = newdir
    os.makedirs(newdir, exist_ok=True)
    if not (Path(newdir) / ".git").exists():
        run_git(newdir, ["init"])
    write_manifest(newdir, bibtex)
    if config.file:
        config.save()


def backup_info(gitdir, config=None):
    """Collect display information about one backup directory."""
    gitdir = Path(gitdir)
    manifest = read_manifest(gitdir) or {}
    info = {
        "gitdir": str(gitdir),
        "bibtex": manifest.get("bibtex"),
        "snapshots": None,
        "last": None,
        "size": sum(f.stat().st_size for f in gitdir.glob("**/*") if f.is_file()),
        "current": config is not None and config.gitdir and Path(config.gitdir) == gitdir,
    }
    if (gitdir / ".git").exists():
        res = run_git(gitdir, ["rev-list", "--count", "HEAD"], check=False)
        if res.returncode == 0:
            info["snapshots"] = int(res.stdout.strip())
        res = run_git(gitdir, ["log", "-1", "--pretty=%ad", "--date=short"], check=False)
        if res.returncode == 0:
            info["last"] = res.stdout.strip() or None
    return info


def list_backup_dirs(config=None):
    """Return information about every backup directory papers knows of."""
    from papers.config import BACKUP_DIR
    dirs = []
    if os.path.isdir(BACKUP_DIR):
        dirs += [os.path.join(BACKUP_DIR, d) for d in sorted(os.listdir(BACKUP_DIR))
                 if os.path.isdir(os.path.join(BACKUP_DIR, d))]
    if config is not None and config.gitdir and os.path.isdir(config.gitdir):
        if not any(Path(d) == Path(config.gitdir) for d in dirs):
            dirs.append(config.gitdir)
    return [backup_info(d, config=config) for d in dirs]


def backup_bib(biblio, config, message=None):
    from papers.bib import clean_filesdir

    if not config.git:
        raise PapersExit('cannot backup without --git enabled')
    backupdir = Path(config.gitdir)
    backupdir.mkdir(exist_ok=True)

    # never mix the histories of two libraries in one backup directory
    check_gitdir_ownership(config)
    backupdir = Path(config.gitdir)  # may have been re-allocated

    # a snapshot made while undone must append to the full history
    adopt_legacy_undone_state(config.gitdir)

    # stop tracking files under their pre-layout-2 names; restore still
    # understands them when materializing old snapshots
    legacy_names = ["backup_copy.bib"] + ([] if config.backup_files else ["backup_clean.bib"])
    for legacy in legacy_names:
        if legacy != config.backupfile.name and (backupdir/legacy).exists():
            (backupdir/legacy).unlink()
            run_git(config.gitdir, ["rm", "--cached", "--ignore-unmatch", "--quiet", legacy], check=False)

    # remove if exists
    config.backupfile.unlink(missing_ok=True)

    logger.debug(f'BACKUP: cp {config.bibtex} {config.backupfile}')
    shutil.copy(config.bibtex, config.backupfile)
    run_git(config.gitdir, ["add", config.backupfile.name])

    if config.backup_files:
        logger.info('backup bibliography with files')
        config.backupfile_clean.unlink(missing_ok=True)
        biblio = copy.deepcopy(biblio)
        backupfilesdir = backupdir/"files"
        backupfilesdir.mkdir(exist_ok=True)
        biblio.filesdir = str(backupfilesdir)
        biblio.rename_entries_files(copy=True, relative_to=backupdir, hardlink=True)
        biblio.save(config.backupfile_clean)
        run_git(config.gitdir, ["add", config.backupfile_clean.name])

        # Remove unlinked files
        clean_filesdir(biblio, interactive=False, ignore_files=[config.backupfile, config.backupfile_clean])
        run_git(config.gitdir, ["add", "files"])

    else:
        logger.info('backup bibliography only (without files)')

    message = message or 'papers ' + ' '.join(sys.argv[1:])
    run_git(config.gitdir, ["commit", "-m", message], check=False)
    # work on "main" branch for comitting (out of history branch)
    run_git(config.gitdir, ["checkout", "-B", "main"])
    run_git(config.gitdir, ["clean", "-f"])


def silent_backup_bib(biblio, config, level=logging.WARNING, *args, **kwargs):
    " this is useful when passing --info to avoid having too many outputs"
    level0 = logger.getEffectiveLevel()
    if level0 > logging.DEBUG: # if DEBUG, also show back debug logs
        logger.setLevel(level)
    try:
        backup_bib(biblio, config, *args, **kwargs)
    finally:
        logger.setLevel(level0)


def _tracked_backupfile(config):
    """The verbatim bibtex copy in the backup worktree.

    Named after the bibtex itself; falls back to the pre-layout-2 name
    'backup_copy.bib' when materializing snapshots recorded by older versions.
    """
    if not config.backupfile.exists():
        legacy = Path(config.gitdir) / "backup_copy.bib"
        if legacy.exists():
            return legacy
    return config.backupfile


def restore_from_backupdir(config, restore_files=False):
    check_gitdir_ownership(config)
    restore_cmd = f"papers add {config.backupfile_clean} --rename --copy" if config.backup_files else f"cp {_tracked_backupfile(config)} {config.bibtex}"
    repair_message = f"papers backup broken :: cannot repair file links :: try to recover manually with `{restore_cmd}`"
    try:
        return _restore_from_backupdir(config, restore_files=restore_files)
    except Exception as error:
        logger.error(str(error))
        raise PapersExit(repair_message)


def _restore_from_backupdir(config, restore_files=False):
    from papers.bib import Biblio

    current = run_git(config.gitdir, ["rev-parse", "HEAD"]).stdout.strip()
    message = run_git(config.gitdir, ["log", current, "--pretty=format:%C(auto)%h %s (%ad)", "-1"]).stdout.strip()
    logger.info(f'restore bibliography to {message}')

    if os.path.exists(config.bibtex):
        os.remove(config.bibtex)
    shutil.copy(_tracked_backupfile(config), config.bibtex)

    # Re-name the file according to back-up bibtex
    if not config.backup_files:
        return

    biblio = Biblio.load(config.bibtex, config.filesdir)
    biblio_clean = Biblio.load(config.backupfile_clean, config.filesdir)

    assert len(biblio.entries) == len(biblio_clean.entries)

    for e, e_clean in zip(biblio.entries, biblio_clean.entries):
        assert get_entry_val(e, 'ID', '') == get_entry_val(e_clean, 'ID', ''), f"{get_entry_val(e, 'ID', '')} != {get_entry_val(e_clean, 'ID', '')})"
        files = biblio.get_files(e)
        files_clean = biblio_clean.get_files(e_clean)
        assert len(files) == len(files_clean), f"{get_entry_val(e, 'ID', '')} :: files {len(files)} != {len(files_clean)})"

        new_files = []

        for f, f_clean in zip(files, files_clean):
            # broken link in the backup
            if not os.path.exists(f_clean):
                logger.debug(f"BACKUP FILE DOES NOT EXISTS: {f_clean} ")
                logger.debug(f"BACKUP ENTRY: {e_clean['file']} ")
                logger.debug(f"BROKEN ENTRY: {e['file']} ")
                logger.warning(f"{get_entry_val(e, 'ID', '')} :: file link broken => {f} ")
                new_files.append(f)
                continue

            # backup file is fine

            # original bibtex link matches something on disk
            if os.path.exists(f):

                # same file: nothing to do
                if os.path.samefile(f, f_clean) or checksum(f_clean) == checksum(f):
                    new_files.append(f)

                else:
                    logger.warning(f"{get_entry_val(e, 'ID', '')} :: file found but does not match backup (keep pointer to backup): {f} != {f_clean}")
                    new_files.append(f_clean)

            # original bibtex link is broken, --restore-file is active
            elif restore_files:
                try:
                    move(f_clean, f, copy=True, interactive=False)
                    new_files.append(f)

                except Exception as error:
                    logger.error(f"{error}")
                    logger.error(f"{get_entry_val(e, 'ID', '')} :: failed to restore file (keep pointer to backup)")
                    new_files.append(f_clean)

            # original bibtex link is broken, default without --restore-file : do not do anything
            else:
                new_files.append(f_clean)

        biblio.set_files(e, new_files)

    biblio.save(config.bibtex)


RESTORES_TRAILER = "Papers-Restores"


def _restores_target(message_body):
    """Return the commit named by the Papers-Restores trailer, or None."""
    for line in reversed(message_body.strip().splitlines()):
        if line.startswith(RESTORES_TRAILER + ":"):
            return line.split(":", 1)[1].strip()
    return None


def cursor_commit(gitdir):
    """The commit representing the current library state.

    The tip itself, unless the tip is a restore commit, in which case the
    commit its Papers-Restores trailer points to.
    """
    body = run_git(gitdir, ["log", "-1", "--pretty=%B"]).stdout
    return _restores_target(body) or run_git(gitdir, ["rev-parse", "HEAD"]).stdout.strip()


def _append_restore_commit(config, target, kind):
    """Append a commit on HEAD with `target`'s tree and move branch + worktree to it."""
    gitdir = config.gitdir
    target_info = run_git(gitdir, ["log", "-1", "--pretty=%h %s", target]).stdout.strip()
    message = f"papers {kind}: back to {target_info}\n\n{RESTORES_TRAILER}: {target}"
    tree = run_git(gitdir, ["rev-parse", f"{target}^{{tree}}"]).stdout.strip()
    new = run_git(gitdir, ["commit-tree", tree, "-p", "HEAD", "-m", message]).stdout.strip()
    # the new commit has HEAD as parent, so this discards nothing;
    # it moves the branch forward and updates the working tree
    run_git(gitdir, ["reset", "--hard", new])


def adopt_legacy_undone_state(gitdir):
    """Linearize an old-model undone state (HEAD on 'history' behind 'main') onto main."""
    res = run_git(gitdir, ["rev-parse", "--abbrev-ref", "HEAD"], check=False)
    if res.returncode != 0 or res.stdout.strip() != "history":
        return
    if run_git(gitdir, ["rev-parse", "--verify", "--quiet", "main"], check=False).returncode != 0:
        return
    head = run_git(gitdir, ["rev-parse", "HEAD"]).stdout.strip()
    main = run_git(gitdir, ["rev-parse", "main"]).stdout.strip()
    if head == main:
        run_git(gitdir, ["checkout", "main"])
        run_git(gitdir, ["branch", "-D", "history"], check=False)
        return
    logger.info("adopt pre-append-only undone state into linear history")
    head_info = run_git(gitdir, ["log", "-1", "--pretty=%h %s", head]).stdout.strip()
    message = f"papers: adopt undone state {head_info}\n\n{RESTORES_TRAILER}: {head}"
    tree = run_git(gitdir, ["rev-parse", f"{head}^{{tree}}"]).stdout.strip()
    new = run_git(gitdir, ["commit-tree", tree, "-p", main, "-m", message]).stdout.strip()
    run_git(gitdir, ["checkout", "-B", "main", new])
    run_git(gitdir, ["branch", "-D", "history"], check=False)


def _require_history(gitdir):
    if run_git(gitdir, ["rev-parse", "--verify", "--quiet", "HEAD"], check=False).returncode != 0:
        raise PapersExit("no backup history (no snapshot recorded yet)")


def git_restore_state(config, ref, restore_files=False, kind="restore-backup"):
    """Append a restore commit for `ref` and restore the bibtex from it."""
    check_gitdir_ownership(config)
    _require_history(config.gitdir)
    res = run_git(config.gitdir, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], check=False)
    if res.returncode != 0:
        raise PapersExit(f"unknown git reference: {ref}")
    target = res.stdout.strip()
    _append_restore_commit(config, target, kind=kind)
    restore_from_backupdir(config, restore_files=restore_files)


def git_undo(config, restore_files=False, steps=1):
    check_gitdir_ownership(config)
    _require_history(config.gitdir)
    adopt_legacy_undone_state(config.gitdir)
    cur = cursor_commit(config.gitdir)
    res = run_git(config.gitdir, ["rev-parse", "--verify", "--quiet", f"{cur}~{steps}"], check=False)
    if res.returncode != 0:
        raise PapersExit("nothing to undo")
    _append_restore_commit(config, res.stdout.strip(), kind="undo")
    restore_from_backupdir(config, restore_files=restore_files)


def git_redo(config, restore_files=False, steps=1):
    check_gitdir_ownership(config)
    _require_history(config.gitdir)
    adopt_legacy_undone_state(config.gitdir)
    cur = cursor_commit(config.gitdir)
    out = run_git(config.gitdir, ["log", "--first-parent", "--reverse", "-z",
                                  "--pretty=format:%H %B", f"{cur}..HEAD"]).stdout
    # oldest first; skip restore commits, which do not introduce new states
    futures = []
    for record in out.split("\x00"):
        if not record.strip():
            continue
        sha, _, body = record.partition(" ")
        if _restores_target(body) is None:
            futures.append(sha)
    if len(futures) < steps:
        raise PapersExit("nothing to redo")
    _append_restore_commit(config, futures[steps-1], kind="redo")
    restore_from_backupdir(config, restore_files=restore_files)
