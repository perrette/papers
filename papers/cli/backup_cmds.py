"""papers undo, redo, restore (restore-backup: deprecated), backup, git"""
import fnmatch
import os
import shutil
import subprocess as sp

import papers.config
from papers import logger
from papers.backup import git_redo, git_restore_state, git_undo, list_backup_dirs, restore_from_backupdir, run_git
from papers.bib import Biblio, backupfile as backupfile_func
from papers.files import is_inside
from papers.utils import PapersExit, bcolors


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
    target = func(config, restore_files=o.restore_files, steps=o.steps)
    if target is None:  # --dry-run
        return
    info = run_git(config.gitdir, ["log", "-1", "--date=format:%Y-%m-%d %H:%M", "--pretty=%h %s (%ad)",
                                   target]).stdout.strip()
    print(f'{kind}: {os.path.basename(config.bibtex)} restored to {info}')
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
    back = backupfile_func(config.bibtex)
    if papers.config.DRYRUN:
        print(f'DRYRUN: {config.bibtex} not swapped with {back}')
        return
    tmp = config.bibtex + '.tmp'
    logger.info(config.bibtex+' <==> '+back)
    shutil.copy(config.bibtex, tmp)
    shutil.move(back, config.bibtex)
    shutil.move(tmp, back)
    print(f'{o.cmd}: {os.path.basename(config.bibtex)} swapped with its previous version ({back})')


def restorecmd(parser, o, config):
    if o.cmd == 'restore-backup':
        logger.warning('`papers restore-backup` is deprecated: use `papers restore`')
    if not config.git:
        raise PapersExit('restore needs the git backup: enable it with `papers config git true`')
    if o.ref:
        git_restore_state(config, o.ref, restore_files=o.restore_files)
    else:
        restore_from_backupdir(config, restore_files=o.restore_files)


def _print_backup_info(info):
    owner = info['bibtex'] or 'unknown library (no manifest)'
    status = ''
    if info['bibtex'] and not os.path.exists(info['bibtex']):
        status = bcolors.WARNING + ' (bibtex missing)' + bcolors.ENDC
    current = ' [current]' if info['current'] else ''
    snapshots = f"{info['snapshots']} snapshots" if info['snapshots'] is not None else 'no snapshot'
    last = f", last {info['last']}" if info['last'] else ''
    size = f"{info['size']/(1024*1024):.1f} MB"
    print(f"* {os.path.basename(info['gitdir'])}: {owner}{status} ({snapshots}{last}, {size}){current}")
    print(f"    {info['gitdir']}")


def backupcmd(parser, o, config):
    infos = list_backup_dirs(config)
    if o.patterns:
        infos = [info for info in infos
                 if any(fnmatch.fnmatch(os.path.basename(info['gitdir']), p) for p in o.patterns)]

    if o.action == 'remove':
        if not o.patterns:
            parser.error('backup remove requires directory name(s) -- see `papers backup list`')
        if not infos:
            print('no matching backup directory')
            return
        for info in infos:
            _print_backup_info(info)
            if info['current']:
                logger.warning("this is the current library's backup directory; "
                               "removing it discards its history (a fresh one is created on the next save)")
            if not o.yes:
                ans = input(f"remove {info['gitdir']} ? [y/N] ")
                if ans.lower() != 'y':
                    continue
            shutil.rmtree(info['gitdir'])
            print(f"removed {info['gitdir']}")
        return

    if not infos:
        print('no matching backup directory' if o.patterns else 'no backup directory found')
    for info in infos:
        _print_backup_info(info)

    # always say where the current library stands
    if not o.patterns and config.bibtex:
        if not config.git:
            print(f"current library: {config.bibtex} :: git-tracking is off "
                  f"(enable with `papers config git true`)")
        elif not any(info['current'] for info in infos):
            print(f"current library: {config.bibtex} :: no snapshot recorded yet")


def gitcmd(parser, o, config):
    """run git in the backup directory. git prints its own errors (on the
    standard error), and papers exits with git's exit code"""
    if config.file is None:
        raise PapersExit('papers git runs git in the backup directory of a library, and no library was found')
    if not config.gitdir or not os.path.isdir(config.gitdir):
        raise PapersExit('the library has no git backup: enable it with `papers config git true`')
    try:
        result = sp.run(['git']+o.gitargs, cwd=config.gitdir, stdout=sp.PIPE)
    except OSError as error:
        raise PapersExit(f'failed to run git: {error}')
    print(result.stdout.decode(), end='')
    if result.returncode != 0:
        raise SystemExit(result.returncode)
