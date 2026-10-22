"""papers file rename, mv, attach, detach, rm, check, clean, and filecheck (deprecated)"""
import copy
import os

import papers.config
from papers import logger
from papers.entries import get_entry_val
from papers.files import (attach_files, check_entry_files, clean_filesdir, delete_files, detach_links,
                          execute_moves, files_to_delete, link_snapshot, linked_files, links_to_paths, moved_links,
                          plan_moves, realpath, remove_empty_folders, rename_files)
from papers.library import get_biblio, savebib
from papers.pools import Exchange, Pools
from papers.utils import PapersExit
from papers.cli.common import (set_format_config_from_cmd, _print_biblio_diff, files_mode,
                               _entries_or_all, _one_entry, _key_option_entries, print_kept_files, library_pools,
                               push_to_pool)


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

    set_format_config_from_cmd(o, config, 'name')
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
    set_format_config_from_cmd(o, config, 'name')
    pools = library_pools(config)
    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)
    entries = _entries_or_all(biblio, o.entries)
    rename_files(biblio, entries, config, pools.files_dirs(), keep_source=o.keep_source)
    push_to_pool(Exchange(config, biblio, pools), entries)
    _print_biblio_diff(biblio_init, biblio, entries)


def file_mvcmd(parser, o, config):
    if len(o.paths) < 2:
        parser.error('papers file mv SRC... DEST')
    *sources, dest = o.paths
    biblio = get_biblio(config)
    moves = plan_moves(biblio, sources, dest, force=o.force, protected=[config.bibtex, config.file])
    snapshot = link_snapshot(biblio)

    # -f: a replaced destination that entries link to
    links = linked_files(biblio)
    for m in moves:
        replaced = links.get(realpath(m.target)) if not m.isdir and os.path.isfile(m.target) else None
        if replaced:
            logger.warning(f"-f replaces {m.target}, which {', '.join(e.key for e in replaced)} "
                           f"link{'s' if len(replaced) == 1 else ''} to: "
                           f"{'that link leads' if len(replaced) == 1 else 'these links lead'} to the moved file")

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
    set_format_config_from_cmd(o, config, 'name')
    pools = library_pools(config)
    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)
    e = _one_entry(biblio, o.key)
    attach_files(biblio, e, o.files, config, files_mode(o, config), pools.files_dirs())
    push_to_pool(Exchange(config, biblio, pools), [e])
    _print_biblio_diff(biblio_init, biblio, [e])


def _detach(biblio, links):
    "remove the links [(entry, files)], and say which entries lost a link"
    prefix = 'DRYRUN: ' if papers.config.DRYRUN else ''
    for e, files in links:
        detach_links(biblio, e, files)
        for f in files:
            print(f"{prefix}{e.key}: removed the link to {f}")


def file_detachcmd(parser, o, config):
    biblio = get_biblio(config)
    entries = _key_option_entries(biblio, o.key)
    if o.broken:
        if o.files:
            parser.error('--broken takes no FILE (--key limits it to entries)')
        links = [(e, [f for f in biblio.get_files(e) if not os.path.exists(f)])
                 for e in (biblio.entries if entries is None else entries)]
    elif o.files:
        links = links_to_paths(biblio, o.files, entries, recursive=o.recursive)
    elif entries is not None:
        links = [(e, biblio.get_files(e)) for e in entries]
    else:
        parser.error('papers file detach FILE... [--key KEY...], --key KEY... or --broken [--key KEY...]')
    links = [(e, files) for e, files in links if files]
    _detach(biblio, links)
    savebib(biblio, config)
    if not links:
        print('no link removed')


def file_rmcmd(parser, o, config):
    biblio = get_biblio(config)
    entries = _key_option_entries(biblio, o.key)
    if not o.files:
        parser.error('papers file rm FILE... [-r] [--key KEY...]')
    links = links_to_paths(biblio, o.files, entries, recursive=o.recursive)
    _detach(biblio, links)
    inside, outside, kept, in_pool = files_to_delete(biblio, [f for _, files in links for f in files],
                                                     config.filesdir, pool_dirs=Pools(config).files_dirs())
    savebib(biblio, config)
    print_kept_files(kept, in_pool)
    deleted = inside + outside
    delete_files(deleted, dryrun=papers.config.DRYRUN)
    for path in o.files:
        if os.path.isdir(path):
            remove_empty_folders(deleted, path, keep=[config.filesdir], dryrun=papers.config.DRYRUN)


def file_checkcmd(parser, o, config):
    biblio = get_biblio(config)
    entries = _entries_or_all(biblio, o.entries)
    issues = []
    # broken links to pool files (repaired on load in a non-local library)
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
