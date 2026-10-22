"""papers file rename, mv, attach, detach, rm, check, clean, and filecheck (deprecated)"""
import copy
import os

import papers.config
from papers import logger
from papers.entries import get_entry_val
from papers.config import short_home
from papers.files import (SearchFolders, attach_files, broken_links, check_entry_files, clean_filesdir,
                          delete_files, detach_links, execute_moves, files_to_delete, link_snapshot, linked_files,
                          links_to_paths, moved_links, plan_moves, realpath, remove_empty_folders, rename_files)
from papers.library import get_biblio
from papers.pools import Exchange, Pools
from papers.utils import PapersExit
from papers.cli.common import (set_format_config_from_cmd, _print_biblio_diff, files_mode,
                               _entries_or_all, _one_entry, _key_option_entries, print_kept_files, library_pools,
                               save_entries, print_push_notes)


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

    print_push_notes(biblio, save_entries(config, biblio))


def file_renamecmd(parser, o, config):
    set_format_config_from_cmd(o, config, 'name')
    pools = library_pools(config)
    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)
    entries = _entries_or_all(biblio, o.entries)
    rename_files(biblio, entries, config, pools.files_dirs(), keep_source=o.keep_source)
    notes = save_entries(config, biblio, Exchange(config, biblio, pools))
    _print_biblio_diff(biblio_init, biblio, entries, notes=notes)


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
    notes = save_entries(config, biblio)
    filesdir = _filesdir(done)
    if filesdir:
        config.filesdir = filesdir
        if config.file:
            config.save()
            print(f"filesdir = {config._relpath(filesdir)} (in {config.file})")
    print(f"moved {len(done)} of {len(moves)} file(s) or folder(s), {len(changes)} entries updated")
    print_push_notes(biblio, notes)
    if error:
        raise PapersExit(f"{error}: the links of the files moved before were saved")


def file_attachcmd(parser, o, config):
    set_format_config_from_cmd(o, config, 'name')
    pools = library_pools(config)
    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)
    e = _one_entry(biblio, o.key)
    attach_files(biblio, e, o.files, config, files_mode(o, config), pools.files_dirs())
    notes = save_entries(config, biblio, Exchange(config, biblio, pools))
    _print_biblio_diff(biblio_init, biblio, [e], notes=notes)


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
    print_push_notes(biblio, save_entries(config, biblio))
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
    print_push_notes(biblio, save_entries(config, biblio))
    print_kept_files(kept, in_pool)
    deleted = inside + outside
    delete_files(deleted, dryrun=papers.config.DRYRUN)
    for path in o.files:
        if os.path.isdir(path):
            remove_empty_folders(deleted, path, keep=[config.filesdir], dryrun=papers.config.DRYRUN)


def _search_names(e, link, rest, nameformat):
    """the names to look for in the --search folders for the broken link
    `link` of an entry (`rest`: its broken links not found in the pool): the
    link's file name, then the name that the library's name template gives
    the entry, with the link's extension (only when no other broken link
    has that extension: the template names one file)"""
    names = [os.path.basename(link)]
    ext = os.path.splitext(link)[1]
    if sum(os.path.splitext(f)[1].lower() == ext.lower() for f in rest) == 1:
        try:
            names.append(os.path.basename(nameformat(e)) + ext)
        except Exception as error:
            logger.debug(f'{e.key}: no template name: {error}')
    return names


def plan_relinks(exchange, entries, search, nameformat):
    """the files found for the broken links of the entries (see
    `papers file check --fix`), without parsing any file: the pool of the
    library first (Exchange.pool_relinks), then the --search folders (by the
    link's file name, else by the template name of the entry). Return
    (plans, unclear, count): plans [(entry, {link: [files]}, {link: source})]
    where source is 'pool' or the --search folder; unclear [(entry, link,
    reason)] for the links that several files match; count, the number of
    broken links."""
    biblio = exchange.biblio
    pool = exchange.pools.pool(quiet=True)
    plans, unclear, count = [], [], 0
    claims = {}  # real path of a file found in a --search folder: [(plan, link)]
    for e in entries:
        broken = broken_links(biblio, e)
        if not broken:
            continue
        count += len(broken)
        found = exchange.pool_relinks(e, pool, broken) if pool is not None else {}
        plan = (e, found, dict.fromkeys(found, 'pool'))
        linked = {realpath(f) for f in biblio.get_files(e) + [g for fs in found.values() for g in fs]
                  if os.path.exists(f)}
        rest = [f for f in broken if f not in found]
        for link in rest:
            for name in _search_names(e, link, rest, nameformat):
                candidates = [f for f in search.find(name) if realpath(f) not in linked]
                if candidates:
                    break
            if len(candidates) > 1:
                unclear.append((e, link, 'several files match in the --search folders: '
                                         + ', '.join(short_home(f) for f in candidates)))
            elif candidates:
                found[link] = candidates
                plan[2][link] = search.folder(candidates[0])
                claims.setdefault(realpath(candidates[0]), []).append((plan, link))
        plans.append(plan)
    # a file found for the broken links of several entries goes to none of them
    for real, links in claims.items():
        if len(links) > 1:
            keys = ', '.join(plan[0].key for plan, _ in links)
            for plan, link in links:
                unclear.append((plan[0], link, f'{short_home(real)} matches the broken links of {keys}'))
                del plan[1][link], plan[2][link]
    return [plan for plan in plans if plan[1]], unclear, count


def _links(n):
    return f"{n} link{'' if n == 1 else 's'}"


def _source(source):
    return 'from the pool' if source == 'pool' else f'found in {short_home(source)}'


def file_checkcmd(parser, o, config):
    nameformat = config.nameformat  # the library's own (a non-local library places files with the pool's)
    place = o.fix and not papers.config.DRYRUN
    pools = library_pools(config) if place else Pools(config)
    biblio = get_biblio(config)
    entries = _entries_or_all(biblio, o.entries)
    selected = {id(e) for e in entries}
    exchange = Exchange(config, biblio, pools)
    search = SearchFolders(o.search or [])

    # the links to pool files repaired when a non-local library is loaded (already linked), then the others
    loaded = [(e, found, dict.fromkeys(found, 'pool')) for e, found in getattr(biblio, 'repaired_links', [])
              if id(e) in selected]
    plans, unclear, count = plan_relinks(exchange, entries, search, nameformat)
    count += sum(len(found) for _, found, _ in loaded)

    lines = []
    for (e, found, sources), linked in [(p, True) for p in loaded] + [(p, False) for p in plans]:
        if place and not linked:
            # placed as `papers file attach` does, in place of the broken links
            positions, i = {}, 0
            for f in biblio.get_files(e):
                n = len(found.get(f, [f]))
                positions[f] = range(i, i + n)
                i += n
            attach_files(biblio, e, [], config, files_mode(o, config), pools.files_dirs(), replace=found,
                         pool_files=[f for link in found if sources[link] == 'pool' for f in found[link]])
            newfiles = biblio.get_files(e)
            found = {link: [newfiles[j] for j in positions[link]] for link in found}
        found = {link: ', '.join(short_home(f) for f in files) for link, files in found.items() if files}
        if place:
            lines.append(f"{e.key}: relinked to "
                         + '; '.join(f'{files} ({_source(sources[link])})' for link, files in found.items()))
        elif o.fix:
            lines.extend(f"DRYRUN: {e.key}: relink {short_home(link)} -> {files} ({_source(sources[link])})"
                         for link, files in found.items())
        else:
            lines.extend(f"{e.key}: broken link: {short_home(link)} -> {files} "
                         f"({_source(sources[link])}; relink with --fix)" for link, files in found.items())
    for e, link, reason in unclear:
        lines.append(f"{e.key}: broken link: {short_home(link)}: {reason} (not relinked)")

    relinked = sum(len(found) for _, found, _ in loaded + plans)
    issues = list(lines)
    skip = {link for _, link, _ in unclear}
    if not place:
        skip |= {link for _, found, _ in plans for link in found}
    for e in entries:
        issues.extend(check_entry_files(biblio, e, metadata=o.metadata, fix=o.fix, skip=skip))
    for line in issues:
        print(line)
    if count:
        left = count - relinked
        detach = ' (papers file detach --broken removes them)' if left else ''
        if o.fix:
            print(f"{'DRYRUN: ' if not place else ''}{_links(relinked)} relinked, {left} still broken{detach}")
        else:
            print(f"{_links(relinked)} can be relinked{' (papers file check --fix)' if relinked else ''}, "
                  f"{left} without a file found{detach}")
    if issues:
        print(f"{len(issues)} issue(s) in the files of {len(entries)} entries")
    else:
        print(f"no issue found in the files of {len(entries)} entries")
    if o.fix and issues:
        print_push_notes(biblio, save_entries(config, biblio, exchange if place else None))


def file_cleancmd(parser, o, config):
    biblio = get_biblio(config)
    if config.filesdir is None:
        raise PapersExit('the library has no files directory')
    removed = clean_filesdir(biblio, interactive=not o.yes, ignore_files=[config.bibtex])
    print(f"{'DRYRUN: ' if papers.config.DRYRUN else ''}removed {len(removed)} unlinked file(s) "
          f"from {config.filesdir}")
