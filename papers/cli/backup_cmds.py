"""papers undo, redo, restore (restore-backup: deprecated), backup, git"""
import fnmatch
import os
import shutil
import subprocess as sp

from papers import logger
from papers.backup import git_redo, git_restore_state, git_undo, list_backup_dirs, restore_from_backupdir
from papers.bib import backupfile as backupfile_func
from papers.utils import PapersExit, bcolors


def redocmd(parser, o, config):
    if config.git:
        return git_redo(config, restore_files=o.restore_files, steps=o.steps)
    else:
        undocmd(parser, o, config)


def undocmd(parser, o, config):
    if config.git:
        return git_undo(config, restore_files=o.restore_files, steps=o.steps)

    logger.warning("the git backup is off (`papers config git true` enables it): "
                   "undo / redo is limited to 1 step back and forth")
    back = backupfile_func(config.bibtex)
    tmp = config.bibtex + '.tmp'
    logger.info(config.bibtex+' <==> '+back)
    shutil.copy(config.bibtex, tmp)
    shutil.move(back, config.bibtex)
    shutil.move(tmp, back)


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
    if config.file is None:
        parser.error('papers must be installed to use git command')
    try:
        out = sp.check_output(['git']+o.gitargs, cwd=config.gitdir)
        print(out.decode())
    except Exception as error:
        print(f"Error message: {error}")
        parser.error('papers failed to execute git command -- you should check your system git install.')
