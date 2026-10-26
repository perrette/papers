"""Git-based backup of the bibliography, and the undo/redo machinery built on it.

With the git setting (`papers config git true`), every save of the bibtex file is
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
``restore --ref`` append a *restore commit* whose tree is the older
state, marked with a ``Papers-Restores: <commit>`` trailer naming the state
it represents. That trailer doubles as the cursor: a consecutive undo walks
back from the restored state rather than from the tip, and redo walks the
first-parent chain forward again, skipping restore commits. Making a new
change while undone simply appends on top; the states that were still
redoable remain in history and can be recovered with further undos or
``restore --ref``.

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

from slugify import slugify

import papers.config
from papers import journal, logger, __version__
from papers.bib import Biblio
from papers.config import BACKUP_DIR, BACKUP_DIR_LEGACY
from papers.duplicate import DISTINCT_FILE
from papers.entries import get_entry_val
from papers.files import clean_filesdir
from papers.utils import checksum, move, PapersExit

MANIFEST_NAME = "manifest.json"
# version of the backup directory layout, recorded in the manifest
# (2: verbatim copy tracked under the bibtex's own name, clean copy only with --git-lfs)
LAYOUT_VERSION = 2


def git_env(gitdir, env=None):
    """the environment of a git command in the backup repository `gitdir`:
    git does not look for a repository above `gitdir`, so that a backup
    directory without .git never reaches an enclosing repository (e.g. a
    home directory under git)"""
    env = dict(os.environ if env is None else env)
    env['GIT_CEILING_DIRECTORIES'] = os.path.dirname(os.path.abspath(gitdir))
    return env


def run_git(gitdir, cmd, check=True):
    """Run a git command in the backup repository.

    ``cmd`` may be a string (split into arguments like a shell would,
    but without going through a shell) or a list of arguments.
    Output is captured; on failure git's stderr is logged, and a
    ``CalledProcessError`` is raised if ``check`` is true.
    """
    args = shlex.split(cmd) if isinstance(cmd, str) else [str(a) for a in cmd]
    logger.debug(f"git -C {gitdir} {' '.join(args)}")
    env = _identity_env(gitdir) if args[:1] in (['commit'], ['commit-tree']) else None
    res = sp.run(['git'] + args, cwd=gitdir, capture_output=True, text=True, env=git_env(gitdir, env))
    if res.returncode != 0:
        message = f"Command failed: 'git {' '.join(args)}': {res.stderr.strip()}"
        if check:
            logger.error(message)
            raise sp.CalledProcessError(res.returncode, ['git'] + args, res.stdout, res.stderr)
        logger.debug(message)
    return res


# the author of the backup commits when git has no user name and email
# (fresh install, CI, containers): the backup repositories are private to papers
FALLBACK_IDENTITY = ('papers', 'papers@localhost')


def _identity_env(gitdir):
    """the environment of a commit in a backup repository: unchanged (None)
    if git knows who commits (user.name and user.email, or the GIT_AUTHOR_*
    and GIT_COMMITTER_* variables), else with the fallback identity for what
    is missing"""
    def git(*args):
        return sp.run(['git'] + list(args), cwd=gitdir, capture_output=True, text=True, env=git_env(gitdir))

    env = None
    for role in ('AUTHOR', 'COMMITTER'):
        if git('var', f'GIT_{role}_IDENT').returncode == 0:
            continue
        env = env or dict(os.environ)
        for var, key, value in zip(('NAME', 'EMAIL'), ('user.name', 'user.email'), FALLBACK_IDENTITY):
            if not git('config', key).stdout.strip():
                env.setdefault(f'GIT_{role}_{var}', value)
    return env


def check_git_available(gitlfs=False):
    "raise PapersExit if git (or with gitlfs, git-lfs) is not installed"
    if shutil.which('git') is None:
        raise PapersExit('the git backup needs git, which is not installed (nothing was changed; '
                         '--no-git or `papers config git false` turns the backup off)')
    if gitlfs and sp.run(['git', 'lfs', 'version'], capture_output=True).returncode != 0:
        raise PapersExit('the git-lfs setting needs git-lfs, which is not installed (nothing was changed)')


def git_init(gitdir):
    "create a backup repository whose branch is main, whatever git's init.defaultBranch"
    run_git(gitdir, ["init"])
    run_git(gitdir, ["symbolic-ref", "HEAD", "refs/heads/main"])

def default_gitdir(bibtex):
    """Allocate a backup directory name for a bibtex file.

    A human-readable slug (parent folder + file name, since libraries are
    often named alike: references.bib, papers.bib...) plus a hash of the
    resolved absolute path, so that two libraries can never map to the same
    directory (a bare slug of the bibtex name used to collide).
    """
    path = Path(bibtex).resolve()
    stem = path.stem or "library"
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:8]
    label = slugify(f"{path.parent.name} {stem}") if path.parent.name else slugify(stem)
    return os.path.join(BACKUP_DIR, f"{label}-{digest}")


def legacy_gitdir(bibtex):
    """The backup directory name older versions derived from the bibtex path."""
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


def move_gitdir_out_of_library(config):
    """The backup directory of the libraries of papers v2.2 to v2.4 is
    <library>/.papers, the folder where papers 3 keeps the files of the
    library (config.json, origin/, distinct.json): the backup would copy them into
    itself, and `git clean` would remove them. Move the repository (its
    .git and the files it tracks) to a new directory of the backup folder,
    and record it in the library configuration."""
    if not config.gitdir or not config.bibtex:
        return
    gitdir = Path(config.gitdir)
    if os.path.realpath(gitdir) != os.path.realpath(Path(config.bibtex).resolve().parent / '.papers'):
        return
    new = default_gitdir(config.bibtex)
    n = 2
    while os.path.exists(new):
        new = default_gitdir(config.bibtex) + f"-{n}"
        n += 1
    os.makedirs(new)
    if (gitdir / ".git").exists():
        tracked = [f for f in run_git(gitdir, ["ls-files", "-z"]).stdout.split("\0") if f]
        shutil.move(str(gitdir / ".git"), os.path.join(new, ".git"))
        for name in tracked + [MANIFEST_NAME]:
            if (gitdir / name).is_file():
                os.makedirs(os.path.dirname(os.path.join(new, name)), exist_ok=True)
                # .papers/config.json is the configuration of the library: it stays
                move = shutil.copy if os.path.normpath(name) == 'config.json' else shutil.move
                move(str(gitdir / name), os.path.join(new, name))
    logger.warning(f"the backup directory {gitdir} is the folder of the library's own files since papers 3 "
                   f"(config.json, origin/, distinct.json): the backup moved to {new}")
    config.gitdir = new
    if config.file and config.is_library and os.path.exists(config.file):
        config.save()


def init_backup(config):
    """Set up the git backup of a library: initialize its backup directory
    (an existing one is kept, otherwise one is allocated) and take ownership
    of it. Used by install and by `papers config git true`, followed by a
    first snapshot (papers.library.snapshot_backup)."""
    move_gitdir_out_of_library(config)
    if not (config.gitdir and os.path.exists(config.gitdir)) and config.bibtex:
        config.gitdir = resolve_gitdir(config.bibtex)
    if (Path(config.gitdir)/'.git').exists():
        logger.warning(f'{config.gitdir} is already initialized')
    else:
        os.makedirs(config.gitdir, exist_ok=True)
        git_init(config.gitdir)

    # an explicit install takes ownership of the backup directory
    claim_gitdir(config)

    if config.gitlfs:
        # staged only: the first snapshot commits it with the bibtex, so that
        # no state of the history is without the bibtex (undo would remove it)
        # files/** (not files/: a directory pattern does not apply to its content)
        run_git(config.gitdir, 'lfs track "files/**"')
        run_git(config.gitdir, 'add .gitattributes')


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
        git_init(newdir)
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
    roots = [BACKUP_DIR]
    if Path(BACKUP_DIR_LEGACY) != Path(BACKUP_DIR):
        roots.append(BACKUP_DIR_LEGACY)
    dirs = []
    for root in roots:
        if os.path.isdir(root):
            dirs += [os.path.join(root, d) for d in sorted(os.listdir(root))
                     if os.path.isdir(os.path.join(root, d))]
    if config is not None and config.gitdir and os.path.isdir(config.gitdir):
        if not any(Path(d) == Path(config.gitdir) for d in dirs):
            dirs.append(config.gitdir)
    return [backup_info(d, config=config) for d in dirs]


def backup_bib(biblio, config, message=None):
    if not config.git:
        raise PapersExit('cannot backup without --git enabled')
    if not config.gitdir:
        config.gitdir = resolve_gitdir(config.bibtex)
    move_gitdir_out_of_library(config)
    backupdir = Path(config.gitdir)
    backupdir.mkdir(parents=True, exist_ok=True)

    # never mix the histories of two libraries in one backup directory
    check_gitdir_ownership(config)
    backupdir = Path(config.gitdir)  # may have been re-allocated

    # a backup directory that was never initialized (or removed since the install)
    if not (backupdir / ".git").exists():
        logger.info(f"initialize backup repository: {backupdir}")
        git_init(config.gitdir)
        write_manifest(config.gitdir, config.bibtex)

    # a snapshot made while undone must append to the full history
    adopt_legacy_undone_state(config.gitdir)

    # stop tracking files under their pre-layout-2 names; restore still
    # understands them when materializing old snapshots
    legacy_names = ["backup_copy.bib"] + ([] if config.gitlfs else ["backup_clean.bib"])
    for legacy in legacy_names:
        if legacy != config.backupfile.name and (backupdir/legacy).exists():
            (backupdir/legacy).unlink()
            run_git(config.gitdir, ["rm", "--cached", "--ignore-unmatch", "--quiet", legacy], check=False)

    # remove if exists
    config.backupfile.unlink(missing_ok=True)

    logger.debug(f'BACKUP: cp {config.bibtex} {config.backupfile}')
    shutil.copy(config.bibtex, config.backupfile)
    run_git(config.gitdir, ["add", config.backupfile.name])

    # the files of the library next to its bibtex: the origin copies of the
    # entries exchanged with pools (one file per pool), and the pairs that
    # are not the same paper; a file removed from the library leaves the backup
    from papers.pools import ORIGIN_DIR, LEGACY_ORIGIN_FILE  # papers.pools imports this module
    libdir = Path(config.bibtex).parent
    names = {DISTINCT_FILE, LEGACY_ORIGIN_FILE}
    for d in (libdir / ORIGIN_DIR, backupdir / ORIGIN_DIR):
        if d.is_dir():
            names.update(os.path.join(ORIGIN_DIR, f.name) for f in d.iterdir() if f.suffix == '.bib')
    for name in sorted(names):
        source = libdir / name
        if source.exists():
            (backupdir / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, backupdir / name)
            run_git(config.gitdir, ["add", name])
        elif (backupdir / name).exists():
            (backupdir / name).unlink()
            run_git(config.gitdir, ["rm", "--cached", "--ignore-unmatch", "--quiet", name], check=False)

    # the file operations of the command, reversed by undo (see papers.journal)
    ops = journal.take(config.bibtex)
    journal_path = backupdir / journal.JOURNAL_FILE
    if ops:
        journal_path.write_text(json.dumps(ops, indent=1))
        run_git(config.gitdir, ["add", journal.JOURNAL_FILE])
    elif journal_path.exists():
        journal_path.unlink()
        run_git(config.gitdir, ["rm", "--cached", "--ignore-unmatch", "--quiet", journal.JOURNAL_FILE], check=False)

    if config.gitlfs:
        logger.info('backup bibliography with files')
        config.backupfile_clean.unlink(missing_ok=True)
        biblio = copy.deepcopy(biblio)
        backupfilesdir = backupdir/"files"
        backupfilesdir.mkdir(exist_ok=True)
        biblio.filesdir = str(backupfilesdir)
        with journal.paused():  # the copies of the backup are not the command's
            biblio.rename_entries_files(copy=True, relative_to=backupdir, hardlink=True)
        biblio.save(config.backupfile_clean)
        run_git(config.gitdir, ["add", config.backupfile_clean.name])

        # Remove unlinked files
        with journal.paused():
            clean_filesdir(biblio, interactive=False, ignore_files=[config.backupfile, config.backupfile_clean])
        run_git(config.gitdir, ["add", "files"])
        attributes = backupdir / ".gitattributes"
        text = attributes.read_text() if attributes.exists() else ""
        if "files/**" not in text:
            # backups made before papers 3 tracked "files/", which git-lfs
            # does not apply to the files in it: store them with git-lfs now
            attributes.write_text(text + ("" if not text or text.endswith("\n") else "\n")
                                  + "files/** filter=lfs diff=lfs merge=lfs -text\n")
            run_git(config.gitdir, ["add", ".gitattributes"])
            run_git(config.gitdir, ["add", "--renormalize", "files"])

    else:
        logger.info('backup bibliography only (without files)')

    message = message or 'papers ' + ' '.join(sys.argv[1:])
    res = run_git(config.gitdir, ["commit", "-m", message], check=False)
    if res.returncode != 0 and 'nothing to commit' not in res.stdout + res.stderr \
            and 'nothing added to commit' not in res.stdout + res.stderr:
        logger.warning(f"the git backup could not commit in {config.gitdir}: "
                       f"{(res.stderr or res.stdout).strip()}")
    compact_backup(config.gitdir)
    # work on "main" branch for comitting (out of history branch)
    run_git(config.gitdir, ["checkout", "-B", "main"])
    run_git(config.gitdir, ["clean", "-f"])


# the number of loose objects of a backup repository from which they are packed (see compact_backup)
LOOSE_OBJECTS_LIMIT = 150


def compact_backup(gitdir):
    """pack the loose objects of a backup repository once it has
    LOOSE_OBJECTS_LIMIT of them (about 50 commits). Each commit stores the
    whole bibtex, compressed (1.6 MB for 10000 entries), and git's automatic
    gc waits for about 6700 loose objects; a pack stores the differences
    between versions (50 commits of 10000 entries: 82 MB loose, 4 MB packed;
    `git repack` takes 2 s, 9 s for 30000 entries). git count-objects, run
    after each commit, takes a few milliseconds."""
    res = run_git(gitdir, ["count-objects", "-v"], check=False)
    count = next((int(line.split(':')[1]) for line in res.stdout.splitlines() if line.startswith('count:')), 0)
    if count < LOOSE_OBJECTS_LIMIT:
        return
    logger.info(f"pack the {count} loose objects of the backup repository {gitdir}")
    run_git(gitdir, ["repack", "-d", "-q"], check=False)


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


def _dryrun_restore(config, target, kind):
    "with --dry-run: print the state that undo, redo or restore would bring back, and return True"
    if not papers.config.DRYRUN:
        return False
    info = run_git(config.gitdir, ["log", "-1", "--pretty=%h %s", target]).stdout.strip()
    print(f"DRYRUN: {kind}: {config.bibtex} not restored to {info}")
    return True


def restore_from_backupdir(config, restore_files=False, previous=None):
    """Restore the library from the backup worktree (HEAD): the bibtex and
    the library files of .papers/ (origin records, distinct.json). previous:
    the commit of the state left (undo, redo, restore --ref); the library
    files it tracked that HEAD does not are removed."""
    if _dryrun_restore(config, "HEAD", "restore"):
        return
    check_gitdir_ownership(config)
    restore_cmd = f"papers add {config.backupfile_clean} --rename --copy" if config.gitlfs else f"cp {_tracked_backupfile(config)} {config.bibtex}"
    repair_message = f"papers backup broken :: cannot repair file links :: try to recover manually with `{restore_cmd}`"
    try:
        return _restore_from_backupdir(config, restore_files=restore_files, previous=previous)
    except Exception as error:
        raise PapersExit(f'{error}\n{repair_message}') from error


def _library_files(gitdir, rev):
    """the library files of .papers/ that the backup commit `rev` tracks
    (see backup_bib): the origin records and distinct.json"""
    from papers.pools import ORIGIN_DIR, LEGACY_ORIGIN_FILE  # papers.pools imports this module
    out = run_git(gitdir, ["ls-tree", "-r", "-z", "--name-only", rev, "--", ".papers"]).stdout
    names = set()
    for name in out.split("\0"):
        name = os.path.normpath(name) if name else ""
        if name in (DISTINCT_FILE, LEGACY_ORIGIN_FILE) or (
                os.path.dirname(name) == ORIGIN_DIR and name.endswith(".bib")):
            names.add(name)
    return names


def _restore_library_files(config, previous=None):
    """copy the library files of .papers/ of the backup worktree (HEAD) to
    the library, and remove those that `previous` tracked and HEAD does not
    (a file the backup never had is left alone)"""
    libdir = Path(config.bibtex).parent
    backupdir = Path(config.gitdir)
    names = _library_files(config.gitdir, "HEAD")
    for name in sorted(names):
        (libdir / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(backupdir / name, libdir / name)
    if previous is not None:
        for name in sorted(_library_files(config.gitdir, previous) - names):
            if (libdir / name).exists():
                logger.info(f"remove {libdir / name}: not in the restored state")
                (libdir / name).unlink()


def _restore_from_backupdir(config, restore_files=False, previous=None):
    current = run_git(config.gitdir, ["rev-parse", "HEAD"]).stdout.strip()
    message = run_git(config.gitdir, ["log", current, "--pretty=format:%C(auto)%h %s (%ad)", "-1"]).stdout.strip()
    logger.info(f'restore bibliography to {message}')

    # read the snapshot, not the work tree: with git-lfs, the files of the
    # work tree are hard links of the library files, so a library file
    # edited in place is edited there too (git replaces the files it
    # restores, which breaks the link and leaves the library file as it is)
    run_git(config.gitdir, ["reset", "--hard", "--quiet", "HEAD"])

    tracked = _tracked_backupfile(config)
    if not tracked.exists():
        raise PapersExit(f"the backup state {message} has no copy of the bibtex: {config.bibtex} is left as it is")
    if os.path.exists(config.bibtex):
        os.remove(config.bibtex)
    shutil.copy(tracked, config.bibtex)
    _restore_library_files(config, previous=previous)

    # Re-name the file according to back-up bibtex
    if not config.gitlfs:
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
    """Append a commit on HEAD with `target`'s tree and move branch + worktree
    to it; return the former HEAD"""
    gitdir = config.gitdir
    previous = run_git(gitdir, ["rev-parse", "HEAD"]).stdout.strip()
    target_info = run_git(gitdir, ["log", "-1", "--pretty=%h %s", target]).stdout.strip()
    message = f"papers {kind}: back to {target_info}\n\n{RESTORES_TRAILER}: {target}"
    tree = run_git(gitdir, ["rev-parse", f"{target}^{{tree}}"]).stdout.strip()
    new = run_git(gitdir, ["commit-tree", tree, "-p", "HEAD", "-m", message]).stdout.strip()
    # the new commit has HEAD as parent, so this discards nothing;
    # it moves the branch forward and updates the working tree
    run_git(gitdir, ["reset", "--hard", new])
    return previous


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
    if not papers.config.DRYRUN:
        check_gitdir_ownership(config)
    _require_history(config.gitdir)
    res = run_git(config.gitdir, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], check=False)
    if res.returncode != 0:
        raise PapersExit(f"unknown git reference: {ref}")
    target = res.stdout.strip()
    if _dryrun_restore(config, target, "restore"):
        return
    previous = _append_restore_commit(config, target, kind=kind)
    restore_from_backupdir(config, restore_files=restore_files, previous=previous)


def _journal_of(gitdir, commit):
    "the file operations of the command of a commit (see papers.journal)"
    res = run_git(gitdir, ["show", f"{commit}:{journal.JOURNAL_FILE}"], check=False)
    if res.returncode != 0:
        return []
    try:
        return json.loads(res.stdout)
    except ValueError:
        return []


def _pool_dirs(config):
    "the files directory of the pool of a shallow library: a file moved there is copied back by undo"
    if not config.shallow:
        return []
    from papers.pools import pool_files_dir  # papers.pools imports this module
    return [pool_files_dir(config)]


def _files_of_steps(config, commits, kind, file_lines, apply):
    """the files of the commands of the states that undo or redo goes over:
    one step, its file operations are reversed or replayed (apply); several,
    the files stay where they are"""
    if len(commits) == 1:
        file_lines.extend(apply(_journal_of(config.gitdir, commits[0]), _pool_dirs(config)))
    elif any(_journal_of(config.gitdir, c) for c in commits):
        file_lines.append(f'    the files that these commands moved, copied or removed stay as they are '
                          f'({kind} of one step moves them too)')


def git_undo(config, restore_files=False, steps=1, file_lines=None):
    """go back `steps` states; return the commit of the state restored (None
    with --dry-run). One step: the file operations of the command undone are
    reversed (see papers.journal), their report goes to file_lines."""
    if not papers.config.DRYRUN:
        check_gitdir_ownership(config)
    _require_history(config.gitdir)
    if not papers.config.DRYRUN:
        adopt_legacy_undone_state(config.gitdir)
    cur = cursor_commit(config.gitdir)
    res = run_git(config.gitdir, ["rev-parse", "--verify", "--quiet", f"{cur}~{steps}"], check=False)
    if res.returncode != 0:
        raise PapersExit("nothing to undo")
    if _dryrun_restore(config, res.stdout.strip(), "undo"):
        return None
    undone = run_git(config.gitdir, ["rev-list", "--first-parent", f"{res.stdout.strip()}..{cur}"]).stdout.split()
    previous = _append_restore_commit(config, res.stdout.strip(), kind="undo")
    # the files first: the links of the restored bibtex find them
    _files_of_steps(config, undone, 'undo', file_lines if file_lines is not None else [], journal.reverse)
    restore_from_backupdir(config, restore_files=restore_files, previous=previous)
    return res.stdout.strip()


def git_redo(config, restore_files=False, steps=1, file_lines=None):
    """go forward `steps` states; return the commit of the state restored
    (None with --dry-run). One step: the file operations of the command
    redone are replayed (see papers.journal), their report goes to file_lines."""
    if not papers.config.DRYRUN:
        check_gitdir_ownership(config)
    _require_history(config.gitdir)
    if not papers.config.DRYRUN:
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
    if _dryrun_restore(config, futures[steps-1], "redo"):
        return None
    previous = _append_restore_commit(config, futures[steps-1], kind="redo")
    _files_of_steps(config, futures[:steps], 'redo', file_lines if file_lines is not None else [], journal.replay)
    restore_from_backupdir(config, restore_files=restore_files, previous=previous)
    return futures[steps-1]
