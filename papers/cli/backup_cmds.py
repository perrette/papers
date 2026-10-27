"""papers undo, redo, restore (restore-backup: deprecated), backup, git"""
import fnmatch
import os
import shutil
import subprocess as sp
import sys

import papers.config
from papers import journal, logger
from papers.backup import git_env, git_redo, git_restore_state, git_undo, restore_from_backupdir, run_git, _pool_dirs
from papers.bib import Biblio
from papers.config import BACKUP_DIR, BACKUP_DIR_LEGACY
from papers.files import is_inside
from papers.utils import PapersExit


def _linked_files(config):
    "the real paths of the files that the entries of the bibtex link to"
    if not config.bibtex or not os.path.exists(config.bibtex):
        return set()
    biblio = Biblio.load(config.bibtex, config.filesdir)
    return {os.path.realpath(f) for e in biblio.entries for f in biblio.get_files(e)}


def _time_travel(config, kind, func, o):
    """undo or redo with the git backup: say which state is restored, and
    which files of the files directory no entry links to any more"""
    before = _linked_files(config)
    file_lines = []
    target = func(config, restore_files=o.restore_files, steps=o.steps, file_lines=file_lines)
    if target is None:  # --dry-run
        return
    info = run_git(config.gitdir, ["log", "-1", "--date=format:%Y-%m-%d %H:%M", "--pretty=%h %s (%ad)",
                                   target]).stdout.strip()
    print(f'{kind}: {os.path.basename(config.bibtex)} restored to {info}')
    if file_lines:
        print('\n'.join(file_lines))
    after = _linked_files(config)
    unlinked = sorted(f for f in before - after
                      if os.path.isfile(f) and config.filesdir and is_inside(f, config.filesdir))
    if unlinked:
        print(f'{len(unlinked)} file(s) of the files directory are linked by no entry now '
              f'(`papers file clean` removes them):')
        for f in unlinked:
            print(f'  {f}')


def redocmd(parser, o, config):
    if config.git:
        return _time_travel(config, 'redo', git_redo, o)
    else:
        undocmd(parser, o, config)


def undocmd(parser, o, config):
    if config.git:
        return _time_travel(config, 'undo', git_undo, o)

    logger.warning("the git backup is off (`papers config git true` enables it): "
                   "undo / redo is limited to 1 step back and forth")
    back = config.previous_bibtex
    if not os.path.exists(back):
        raise PapersExit(f"nothing to {o.cmd}: no previous version of {os.path.basename(config.bibtex)} ({back})")
    if papers.config.DRYRUN:
        print(f'DRYRUN: {config.bibtex} not swapped with {back}')
        return
    # the files of the last command: moved back, or again (see papers.journal)
    file_lines, files_journal = journal.swap_last(config.bibtex, config.gitdir, _pool_dirs(config))
    tmp = config.bibtex + '.tmp'
    logger.info(config.bibtex+' <==> '+back)
    shutil.copy(config.bibtex, tmp)
    shutil.move(back, config.bibtex)
    shutil.move(tmp, back)
    if files_journal is not None:
        journal.save_swapped(config.bibtex, config.gitdir, files_journal)
    print(f'{o.cmd}: {os.path.basename(config.bibtex)} swapped with its previous version ({back})')
    if file_lines:
        print('\n'.join(file_lines))


def restorecmd(parser, o, config):
    if o.cmd == 'restore-backup':
        logger.warning('`papers restore-backup` is deprecated: use `papers restore`')
    if not config.git:
        raise PapersExit('restore needs the git backup: enable it with `papers config git true`')
    if o.ref:
        git_restore_state(config, o.ref, restore_files=o.restore_files)
    else:
        restore_from_backupdir(config, restore_files=o.restore_files)


def backupcmd(parser, o, config):
    """where the backup of the library is, and the backup folders of papers
    3.0.0b2 and earlier that no library took (see papers.backup.adopt_central_backup)"""
    if config.bibtex:
        state = 'git' if config.git else 'git off: previous bibtex only'
        print(f"backup of {papers.config.short_home(config.bibtex)}: "
              f"{papers.config.short_home(str(config.gitdir))} ({state})")
    left = []
    for root in dict.fromkeys([BACKUP_DIR, BACKUP_DIR_LEGACY]):
        if os.path.isdir(root):
            left += [os.path.join(root, d) for d in sorted(os.listdir(root)) if os.path.isdir(os.path.join(root, d))]
    if o.patterns:
        left = [d for d in left if any(fnmatch.fnmatch(os.path.basename(d), p) for p in o.patterns)]
    if o.action == 'remove' and not o.patterns:
        parser.error('backup remove requires folder name(s) -- see `papers backup list`')
    if not left:
        return
    if o.action == 'list':
        print("backups of papers 3.0.0b2 and earlier (each library moves its own to .papers/backup when papers "
              "uses it: these belong to libraries not used since; `papers backup remove NAME` removes one):")
    for d in left:
        print(f"* {os.path.basename(d)}: {papers.config.short_home(d)}")
        if o.action != 'remove':
            continue
        if not o.yes and input(f"remove {d} ? [y/N] ").lower() != 'y':
            continue
        shutil.rmtree(d)
        print(f"removed {d}")


def gitcmd(parser, o, config):
    """run git in the backup directory. git prints its own errors (on the
    standard error), and papers exits with git's exit code"""
    if config.file is None:
        raise PapersExit('papers git runs git in the backup directory of a library, and no library was found')
    if not config.gitdir or not os.path.isdir(config.gitdir):
        raise PapersExit('the library has no git backup: enable it with `papers config git true`')
    try:
        result = sp.run(['git']+o.gitargs, cwd=config.gitdir, stdout=sp.PIPE, env=git_env(config.gitdir))
    except OSError as error:
        raise PapersExit(f'failed to run git: {error}')
    # git's output as is: it may be binary (e.g. `papers git show HEAD:files/a.pdf`)
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout.flush()
        sys.stdout.buffer.write(result.stdout)
        sys.stdout.buffer.flush()
    else:
        print(result.stdout.decode(errors='replace'), end='')
    if result.returncode != 0:
        raise SystemExit(result.returncode)
