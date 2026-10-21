"""papers file rename, mv, attach, detach, check, clean, and filecheck (deprecated)"""
import copy
import os

import papers.config
from papers import logger
from papers.entries import get_entry_val
from papers.files import (attach_files, check_entry_files, clean_filesdir, delete_files, detach_links,
                          execute_moves, files_to_delete, link_snapshot, moved_links, plan_moves, realpath,
                          rename_files)
from papers.library import get_biblio, savebib
from papers.pools import Exchange, Pools
from papers.utils import PapersExit
from papers.cli.common import (set_nameformat_config_from_cmd, _print_biblio_diff, files_mode,
                               _entries_or_all, _one_entry, print_kept_files)


def filecheckcmd(parser, o, config):
    """deprecated: the options of filecheck run the `papers file` subcommands"""
    check = o.fix_mendeley or o.hash_check or o.metadata_check or not (o.delete_broken or o.rename or o.clean_filesdir)
    new = []
    if check:
        new.append('papers file check' + (' --metadata' if o.metadata_check else '')
                   + (' --fix' if o.fix_mendeley or o.hash_check else ''))
    if o.delete_broken:
        new.append('papers file detach --broken')
    if o.rename:
        new.append('papers file rename' + (' --keep-source' if o.copy else ''))
    if o.clean_filesdir:
        new.append('papers file clean' + (' --yes' if o.force else ''))
    logger.warning(f"`papers filecheck` is deprecated: use {' and '.join('`'+cmd+'`' for cmd in new)}")

    set_nameformat_config_from_cmd(o, config)
    biblio = get_biblio(config)

    if check:
        for e in biblio.entries:
            for line in check_entry_files(biblio, e, metadata=o.metadata_check, fix=o.fix_mendeley or o.hash_check):
                print(line)

    if o.delete_broken:
        for e in biblio.entries:
            detach_links(biblio, e, [f for f in biblio.get_files(e) if not os.path.exists(f)])

    if o.rename:
        rename_files(biblio, biblio.entries, config, Pools(config).files_dirs(), keep_source=o.copy)

    if o.clean_filesdir:
        print("Check files directory for unlinked files")
        clean_filesdir(biblio, interactive=not o.force, ignore_files=[config.bibtex])

    savebib(biblio, config)


def file_renamecmd(parser, o, config):
    set_nameformat_config_from_cmd(o, config)
    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)
    entries = _entries_or_all(biblio, o.entries)
    rename_files(biblio, entries, config, Pools(config).files_dirs(), keep_source=o.keep_source)
    savebib(biblio, config)
    _print_biblio_diff(biblio_init, biblio, entries)


def file_mvcmd(parser, o, config):
    if len(o.paths) < 2:
        parser.error('papers file mv SRC... DEST')
    *sources, dest = o.paths
    biblio = get_biblio(config)
    moves = plan_moves(biblio, sources, dest, force=o.force, protected=[config.bibtex, config.file])
    snapshot = link_snapshot(biblio)

    def _filesdir(moves):
        "the new files directory, if it moves"
        if config.filesdir is None or o.filesdir is not None:
            return None
        return next(filter(None, (m.new_path(realpath(config.filesdir)) for m in moves)), None)

    if papers.config.DRYRUN:
        for m in moves:
            print(f"DRYRUN: mv {m.src} {m.target}")
        for e, old, new in moved_links(snapshot, moves):
            for a, b in zip(old, new):
                if a != b:
                    print(f"DRYRUN: {get_entry_val(e, 'ID', '')}: {a} -> {b}")
        if _filesdir(moves):
            print(f"DRYRUN: filesdir = {_filesdir(moves)}")
        return

    done, error = execute_moves(moves, force=o.force)
    changes = moved_links(snapshot, done)
    for e, old, new in changes:
        biblio.set_files(e, new)
    savebib(biblio, config)
    filesdir = _filesdir(done)
    if filesdir:
        config.filesdir = filesdir
        if config.file:
            config.save()
            print(f"filesdir = {config._relpath(filesdir)} (in {config.file})")
    print(f"moved {len(done)} of {len(moves)} file(s) or folder(s), {len(changes)} entries updated")
    if error:
        raise PapersExit(f"{error}: the links of the files moved before were saved")


def file_attachcmd(parser, o, config):
    set_nameformat_config_from_cmd(o, config)
    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)
    e = _one_entry(biblio, o.key)
    attach_files(biblio, e, o.files, config, files_mode(o, config), Pools(config).files_dirs())
    savebib(biblio, config)
    _print_biblio_diff(biblio_init, biblio, [e])


def file_detachcmd(parser, o, config):
    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)
    if o.broken:
        entries = _entries_or_all(biblio, o.args)
        detached = {id(e): [f for f in biblio.get_files(e) if not os.path.exists(f)] for e in entries}
    else:
        if not o.args:
            parser.error('papers file detach KEY [FILE...] (or --broken [KEY...])')
        key, *files = o.args
        e = _one_entry(biblio, key)
        linked = biblio.get_files(e)
        if files:
            by_real = {realpath(f): f for f in linked}
            unknown = [f for f in files if realpath(f) not in by_real]
            if unknown:
                raise PapersExit(f"not linked from {key}: {', '.join(unknown)} (nothing was changed)")
            files = [by_real[realpath(f)] for f in files]
        else:
            files = linked
        entries = [e]
        detached = {id(e): files}

    for e in entries:
        detach_links(biblio, e, detached[id(e)])

    alldetached = [f for e in entries for f in detached[id(e)]]
    if o.delete_files:
        inside, outside, kept, in_pool = files_to_delete(biblio, alldetached, config.filesdir,
                                                         pool_dirs=Pools(config).files_dirs())
    savebib(biblio, config)
    _print_biblio_diff(biblio_init, biblio, entries)
    if o.delete_files:
        print_kept_files(kept, in_pool)
        delete_files(inside + outside, dryrun=papers.config.DRYRUN)


def file_checkcmd(parser, o, config):
    biblio = get_biblio(config)
    entries = _entries_or_all(biblio, o.entries)
    issues = []
    # broken links to pool files (repaired on load in a light library)
    selected = {id(e) for e in entries}
    repaired = [r for r in getattr(biblio, 'repaired_links', []) + Exchange(config, biblio).repair_links(entries)
                if id(r[0]) in selected]
    for e, old, new in repaired:
        gone = [f for f in old if f not in new]
        issues.append(f"{e.key}: broken link to a pool file: {';'.join(gone)} -> the pool's file "
                      f"{';'.join(f for f in new if f not in old)} ({'fixed' if o.fix else 'fix with --fix'})")
    for e in entries:
        issues.extend(check_entry_files(biblio, e, metadata=o.metadata, fix=o.fix))
    for line in issues:
        print(line)
    if issues:
        print(f"{len(issues)} issue(s) in the files of {len(entries)} entries")
    else:
        print(f"no issue found in the files of {len(entries)} entries")
    if o.fix and issues:
        savebib(biblio, config)


def file_cleancmd(parser, o, config):
    biblio = get_biblio(config)
    if config.filesdir is None:
        raise PapersExit('the library has no files directory')
    removed = clean_filesdir(biblio, interactive=not o.yes, ignore_files=[config.bibtex])
    print(f"{'DRYRUN: ' if papers.config.DRYRUN else ''}removed {len(removed)} unlinked file(s) "
          f"from {config.filesdir}")


FILE_COMMANDS = {
    'rename': file_renamecmd,
    'mv': file_mvcmd,
    'attach': file_attachcmd,
    'detach': file_detachcmd,
    'check': file_checkcmd,
    'clean': file_cleancmd,
}
