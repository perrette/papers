"""papers file rename, mv, attach, fetch, detach, rm, check, fix, clean, checksum, and filecheck (deprecated)"""
import os
import shutil

import papers.checksums
import papers.config
import papers.history
import papers.utils
from papers import backup, freepdf, journal, logger, openalex
from papers.entries import get_entry_val
from papers.identifiers import entry_arxiv, strip_doi
from papers.filename import fit_name
from papers.config import short_home
from papers.files import (SearchFolders, attach_files, broken_links, check_entry_files, clean_filesdir,
                          delete_files, detach_links, execute_moves, files_to_delete, link_snapshot, linked_files,
                          links_to_paths, moved_links, plan_moves, realpath, remove_empty_folders, rename_files)
from papers.library import get_biblio, savebib
from papers.otherlibs import Lookup, Source, is_own_unlinked
from papers.pools import Exchange, Pools
from papers.utils import PapersExit, checksum, stdin_is_terminal
from papers.cli.common import (set_format_config_from_cmd, _print_biblio_diff, files_mode,
                               _entries_or_all, _one_entry, _key_option_entries, print_kept_files, library_pools,
                               save_entries, print_push_notes)


def filecheckcmd(parser, o, config):
    """deprecated: the options of filecheck run the `papers file` subcommands"""
    check = o.fix_mendeley or o.hash_check or o.metadata_check or not (o.delete_broken or o.rename or o.clean_filesdir)
    new = []
    if check:
        if o.fix_mendeley or o.hash_check:
            new.append('papers file fix')
        if o.metadata_check or not (o.fix_mendeley or o.hash_check):
            new.append('papers file check' + (' --metadata' if o.metadata_check else ''))
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
        # deprecated: moves the files, as before the files setting applied to the renames
        rename_files(biblio, biblio.entries, config, Pools(config).files_dirs(), keep_source=o.copy, mode='move')

    if o.clean_filesdir:
        print("Check files directory for unlinked files")
        clean_filesdir(biblio, interactive=not o.force, ignore_files=[config.bibtex])

    print_push_notes(biblio, save_entries(config, biblio))


def rename_entries(biblio, config, pools, entries, keep_source=False, mode=None):
    """`papers file rename` (also `papers list --rename`): place the files of
    the entries under their template name, and save the library. pools: the
    library_pools of the configuration, made before the library is loaded
    (in a shallow library, they set the files directory and name template
    of the run). Return the notes of save_entries, and the number of entries
    whose files could not be placed."""
    failed = rename_files(biblio, entries, config, pools.files_dirs(), keep_source=keep_source, mode=mode)
    return save_entries(config, biblio, Exchange(config, biblio, pools)), failed


def file_renamecmd(parser, o, config):
    set_format_config_from_cmd(o, config, 'name')
    pools = library_pools(config)
    biblio = get_biblio(config)
    entries = _entries_or_all(biblio, o.entries)
    mode = files_mode(o, config) if o.move or o.copy or o.link else None
    notes, failed = rename_entries(biblio, config, pools, entries, keep_source=o.keep_source, mode=mode)
    _print_biblio_diff(biblio, entries, notes=notes)
    if failed:
        raise PapersExit()  # the errors are reported: exit 1


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


def attach_entry_files(biblio, config, pools, e, files, o):
    """`papers file attach` (also `papers list --attach`): attach the files to
    the entry e, as the files mode options of o (--move, --copy, --link, see
    files_mode) or else the files setting say, and save the library. pools:
    as for rename_entries. Return the notes of save_entries, and whether the
    files could be placed (False: the name points outside the files
    directory; the links are saved, the files left where they are)."""
    placed = attach_files(biblio, e, files, config, files_mode(o, config), pools.files_dirs())
    return save_entries(config, biblio, Exchange(config, biblio, pools)), placed


def file_attachcmd(parser, o, config):
    set_format_config_from_cmd(o, config, 'name')
    pools = library_pools(config)
    biblio = get_biblio(config)
    e = _one_entry(biblio, o.key)
    notes, placed = attach_entry_files(biblio, config, pools, e, o.files, o)
    _print_biblio_diff(biblio, [e], notes=notes)
    if not placed:
        raise PapersExit()  # the error is reported: exit 1


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
    if o.broken and o.files:
        parser.error('--broken takes no FILE (--key limits it to entries)')
    if not o.broken and not o.files and entries is None:
        parser.error('papers file detach FILE... [--key KEY...], --key KEY... or --broken [--key KEY...]')
    detach_entries(biblio, config, entries, o.files, broken=o.broken, recursive=o.recursive)


def detach_entries(biblio, config, entries, files=(), broken=False, recursive=False):
    """`papers file detach` (also `papers list --detach`): remove the links
    of the entries (None: all entries) to the files (all their links
    without files; only the broken links with broken=True), and save the
    library"""
    if broken:
        links = [(e, [f for f in biblio.get_files(e) if not os.path.exists(f)])
                 for e in (biblio.entries if entries is None else entries)]
    elif files:
        links = links_to_paths(biblio, files, entries, recursive=recursive)
    else:
        links = [(e, biblio.get_files(e)) for e in entries]
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
    removed = [f for _, files in links for f in files]
    keep_dirs = [config.filesdir]
    if config.shallow:
        # a shallow library: the links of the pool entries were removed too
        # (save_entries); a pool file that no entry of the pool or of the
        # library links to any more is deleted
        exchange = Exchange(config, biblio)
        notes = save_entries(config, biblio, exchange)
        pool = exchange.pools.pool(quiet=True)
        if pool is None:  # the pool cannot be read: its files are kept
            inside, outside, kept, in_pool = files_to_delete(biblio, removed, config.filesdir,
                                                             pool_dirs=exchange.pools.files_dirs())
            pool_linked = set()
        else:
            inside, outside, kept, in_pool = files_to_delete(biblio, removed, config.filesdir)
            pool_linked = {realpath(f) for e in pool.biblio.entries for f in pool.biblio.get_files(e)}
            keep_dirs.append(pool.filesdir)
        pool_kept = [f for f in inside + outside if realpath(f) in pool_linked]
        inside = [f for f in inside if realpath(f) not in pool_linked]
        outside = [f for f in outside if realpath(f) not in pool_linked]
        print_push_notes(biblio, notes)
        print_kept_files(kept, in_pool)
        for f in pool_kept:
            print(f"kept {f}: an entry of the pool links to it")
    else:
        inside, outside, kept, in_pool = files_to_delete(biblio, removed, config.filesdir,
                                                         pool_dirs=Pools(config).files_dirs())
        print_push_notes(biblio, save_entries(config, biblio))
        print_kept_files(kept, in_pool)
    deleted = inside + outside
    delete_files(deleted, dryrun=papers.config.DRYRUN)
    for path in o.files:
        if os.path.isdir(path):
            remove_empty_folders(deleted, path, keep=keep_dirs, dryrun=papers.config.DRYRUN)


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
            names.append(os.path.basename(fit_name(nameformat(e) + ext)))
        except Exception as error:
            logger.debug(f'{e.key}: no template name: {error}')
    return names


def plan_relinks(exchange, entries, search, nameformat, others=(), lookup=None):
    """the files found for the broken links of the entries (see
    `papers file fix`), without parsing any file, in this order: the
    library itself (a file with the checksum that .papers/files.json has
    for the link), the pool of the library (the files of the pool entry,
    see Exchange.pool_relinks, then by checksum), the libraries of --pool
    PATH (`others`), the other libraries of the machine by checksum (see
    papers.otherlibs), then the --search folders (by the link's file
    name, else by the template name of the entry). lookup: the
    papers.otherlibs.Lookup of the library (made here by default). Return
    (plans, unclear, count): plans [(entry, {link: [files]}, {link:
    source})] where source is 'pool' (the pool of the library, by name),
    the Pool of a --pool PATH, a papers.otherlibs.Source, or the --search
    folder; unclear [(entry, link, reason)] for the links that several
    files match; count, the number of broken links."""
    biblio = exchange.biblio
    own = exchange.pools.pool(quiet=True)
    pools = [(own, 'pool')] if own is not None else []
    pools += [(p, p) for p in others if p is not own]
    if lookup is None:
        lookup = Lookup(exchange.config, biblio, own, [p.config.bibtex for p, _ in pools])
    plans, unclear, count = [], [], 0
    claims = {}  # real path of a file found in a --search folder: [(plan, link)]
    for e in entries:
        broken = broken_links(biblio, e)
        if not broken:
            continue
        count += len(broken)
        found, sources = {}, {}

        def taken():
            return {realpath(f) for f in biblio.get_files(e) + [g for fs in found.values() for g in fs]
                    if os.path.exists(f)}

        def by_checksum(where):
            for link in [f for f in broken if f not in found]:
                hit = where(link, taken())
                if hit:
                    found[link], sources[link] = [hit[0]], hit[1]

        by_checksum(lookup.own.find)
        for pool, source in pools:
            more = exchange.pool_relinks(e, pool, [f for f in broken if f not in found])
            found.update(more)
            sources.update(dict.fromkeys(more, source))
            if source == 'pool':
                by_checksum(lookup.in_pool)
        by_checksum(lookup.in_others)
        plan = (e, found, sources)
        linked = taken()
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
    if isinstance(source, Source):
        return source.describe()
    if source == 'pool':
        return 'from the pool'
    if isinstance(source, str):
        return f'found in {short_home(source)}'
    return f'from the library {source.shown}'


def file_checkcmd(parser, o, config):
    "papers file check: report the problems of the file links, change nothing"
    _file_check(o, config, fix=False)


def file_fixcmd(parser, o, config):
    "papers file fix: the repairs that `papers file check` reports"
    _file_check(o, config, fix=True)


def _fix_command(o):
    """the `papers file fix` command for the options of `papers file check`:
    -C DIR, --bibtex FILE, the selection, --pool and --search"""
    directory = getattr(o, 'directory', None)
    return ' '.join(['papers'] + ([f'-C {directory}'] if directory else []) + ['file fix']
                    + ([f'--bibtex {o.bibtex}'] if o.bibtex else [])
                    + list(o.entries)
                    + [f'--pool {short_home(os.path.abspath(os.path.expanduser(p)))}' for p in o.pool or []]
                    + [f'--search {short_home(os.path.abspath(d))}' for d in o.search or []])


def _file_check(o, config, fix):
    """papers file check (fix=False) and papers file fix (fix=True): with
    fix, apply the safe repairs (repaired paths, the second link of a file
    linked twice or of identical files removed, broken links relinked to the
    files found in the pool, the libraries of --pool PATH or the --search
    folders); --dry-run lists them. A file found is copied (a hard link when
    possible) into the files directory, never moved, except with --move a
    file of a --search folder (see FilesPolicy for the files of other
    libraries); in link mode, or without files directory, it is linked where
    it is."""
    nameformat = config.nameformat  # the library's own (a shallow library places files with the pool's)
    pools = file_check_pools(config, fix)
    biblio = get_biblio(config)
    entries = _entries_or_all(biblio, o.entries)
    check_entries_files(o, config, fix, pools, biblio, entries, nameformat)


def file_check_pools(config, fix):
    """the pools of `papers file check` and `papers file fix`, made before
    the library is loaded (see rename_entries)"""
    return library_pools(config) if fix and not papers.config.DRYRUN else Pools(config)


def relink_broken_links(config, biblio, exchange, entries, search_dirs, nameformat, others=(), mode=None,
                        place=False, move=False, lookup=None):
    """the repair of the broken links of the entries by `papers file fix`
    (also `papers file fetch`, before it downloads): the links to pool files
    repaired when a shallow library was loaded, the files found by
    plan_relinks (the library by checksum, the pool, the libraries
    `others` of --pool PATH, the other libraries of the machine, the
    folders `search_dirs` of --search; lookup: see plan_relinks), then the files that a command
    deleted from the place of the link, kept by the history. With place,
    the files found are placed as `papers file attach` does (with the files
    mode `mode`; move: the files of the --search folders are moved), and
    those of the history copied back. Return (relinks, unclear, restores,
    count): relinks [(entry, {link: [files]}, {link: source})] (the new
    links once placed), unclear as for plan_relinks, restores [(entry,
    link, when)], and count, the number of broken links."""
    selected = {id(e) for e in entries}
    search = SearchFolders(search_dirs)

    # the links to pool files repaired when a shallow library is loaded (already linked), then the others
    loaded = [(e, found, dict.fromkeys(found, 'pool')) for e, found in getattr(biblio, 'repaired_links', [])
              if id(e) in selected]
    plans, unclear, count = plan_relinks(exchange, entries, search, nameformat, others, lookup=lookup)
    count += sum(len(found) for _, found, _ in loaded)

    relinks = []
    for (e, found, sources), linked in [(p, True) for p in loaded] + [(p, False) for p in plans]:
        if place and not linked:
            # placed as `papers file attach` does, in place of the broken links
            positions, i = {}, 0
            for f in biblio.get_files(e):
                n = len(found.get(f, [f]))
                positions[f] = range(i, i + n)
                i += n
            pool_files, kept, copied = _placement(found, sources, config.filesdir, move)
            attach_files(biblio, e, [], config, mode, exchange.pools.files_dirs(), replace=found,
                         pool_files=pool_files, copied=copied, keep=kept)
            newfiles = biblio.get_files(e)
            found = {link: [newfiles[j] for j in positions[link]] for link in found}
        relinks.append((e, found, sources))

    # last, the history: a file that a command deleted from the place of the link comes back there
    found_links = {link for _, found, _ in relinks for link in found} | {link for _, link, _ in unclear}
    restores = []
    for e in entries:
        for link in broken_links(biblio, e):
            kept = None if link in found_links else backup.deleted_file(config, link)
            if kept is None:
                continue
            stored, step = kept
            when = f'deleted by step {papers.history.short(step)}' if step else 'deleted, its checksum known'
            if place:
                os.makedirs(os.path.dirname(link), exist_ok=True)
                shutil.copy2(stored, link)
                journal.record('copied', stored, link)  # undo removes it again
            restores.append((e, link, when))
    return relinks, unclear, restores, count


def _placement(found, sources, filesdir, move=False):
    """how the files found for broken links are placed (see FilesPolicy):
    (pool_files, kept, copied). The files of the pool are pool files; a
    file of another entry of the library (found by checksum) is linked
    where it is; an unlinked file of the files directory is placed as the
    files setting says (renamed in place); the files of other libraries,
    of --pool PATH and of the --search folders (unless `move`) are
    copied."""
    pool_files, kept, copied = [], [], []
    for link, files in found.items():
        source = sources[link]
        for f in files:
            if source == 'pool' or (isinstance(source, Source) and source.kind == 'pool'):
                pool_files.append(f)
            elif isinstance(source, Source) and source.kind == 'own' and source.key:
                kept.append(f)
            elif isinstance(source, Source) and is_own_unlinked(source, f, filesdir):
                pass
            elif not (move and isinstance(source, str)):
                copied.append(f)
    return pool_files, kept, copied


def check_entries_files(o, config, fix, pools, biblio, entries, nameformat):
    """`papers file check` and `papers file fix` (also `papers list
    --fix-files`) on the entries: see _file_check. o has the options of
    file check or fix (search, pool, move, metadata); nameformat: the name
    format of the library, before file_check_pools."""
    dryrun = papers.config.DRYRUN
    metadata = getattr(o, 'metadata', False)
    place = fix and not dryrun
    exchange = Exchange(config, biblio, pools)
    others = [pools.get_library(p) for p in o.pool or []]
    mode = files_mode(o, config) if fix else None
    relinks, unclear, restores, count = relink_broken_links(
        config, biblio, exchange, entries, o.search or [], nameformat, others, mode=mode, place=place,
        move=getattr(o, 'move', False))

    lines = []
    for e, found, sources in relinks:
        found = {link: ', '.join(short_home(f) for f in files) for link, files in found.items() if files}
        if place:
            lines.append(f"{e.key}: relinked to "
                         + '; '.join(f'{files} ({_source(sources[link])})' for link, files in found.items()))
        elif fix:
            lines.extend(f"DRYRUN: {e.key}: relink {short_home(link)} -> {files} ({_source(sources[link])})"
                         for link, files in found.items())
        else:
            lines.extend(f"{e.key}: broken link: {short_home(link)} -> {files} ({_source(sources[link])})"
                         for link, files in found.items())
    for e, link, reason in unclear:
        lines.append(f"{e.key}: broken link: {short_home(link)}: {reason} (not relinked)")
    for e, link, when in restores:
        if place:
            lines.append(f"{e.key}: {short_home(link)}: restored from the history ({when})")
        elif fix:
            lines.append(f"DRYRUN: {e.key}: restore {short_home(link)} from the history ({when})")
        else:
            lines.append(f"{e.key}: broken link: {short_home(link)} -> in the history ({when})")
    restored = len(restores)
    restorable = {link for _, link, _ in restores}

    relinked = sum(len(found) for _, found, _ in relinks) + restored
    issues = list(lines)
    repairs = []
    skip = {link for _, link, _ in unclear}
    if not place:
        skip |= {link for _, found, _ in relinks for link in found} | restorable
    for e in entries:
        issues.extend(check_entry_files(biblio, e, metadata=metadata, fix=fix, skip=skip, repairs=repairs,
                                        dryrun=dryrun))
    for line in issues:
        print(line)
    if count:
        left = count - relinked
        detach = ' (papers file detach --broken removes them)' if left else ''
        if fix:
            print(f"{'DRYRUN: ' if not place else ''}{_links(relinked)} relinked, {left} still broken{detach}")
        else:
            print(f"{_links(relinked)} can be relinked, {left} without a file found{detach}")
    if place:
        # the issues left: neither relinked nor repaired
        left = len(issues) - (len(lines) - len(unclear)) - len(repairs)
        if left:
            print(f"{left} issue(s) left in the files of {len(entries)} entries")
        elif not issues:
            print(f"no issue found in the files of {len(entries)} entries")
    elif issues:
        print(f"{len(issues)} issue(s) in the files of {len(entries)} entries")
    else:
        print(f"no issue found in the files of {len(entries)} entries")
    if not fix and relinked + len(repairs):
        print(f"{_links(relinked + len(repairs))} can be repaired: `{_fix_command(o)}`")
    if fix and issues:
        print_push_notes(biblio, save_entries(config, biblio, exchange if place else None))


def file_cleancmd(parser, o, config):
    if config.shallow:
        # its filesdir setting is not used: the files are those of the pool, which other libraries link to too
        raise PapersExit(f'the files of a shallow library are in its pool: clean them there, with all the entries '
                         f'of the pool (`papers -C {config.pool_label()} file clean`)')
    biblio = get_biblio(config)
    if config.filesdir is None:
        raise PapersExit('the library has no files directory')
    removed = clean_filesdir(biblio, interactive=not o.yes, ignore_files=[config.bibtex])
    print(f"{'DRYRUN: ' if papers.config.DRYRUN else ''}removed {len(removed)} unlinked file(s) "
          f"from {config.filesdir}")


def file_checksumcmd(parser, o, config):
    """papers file checksum: write (or check) the checksums of the files of
    the entries in .papers/files.json (see papers.checksums)"""
    if papers.checksums.files_json(config) is None:
        raise PapersExit('the checksums are kept in a library (.papers/files.json): this bibtex has none')
    biblio = get_biblio(config)
    paths = sorted({os.path.normpath(f) for e in _entries_or_all(biblio, o.entries) for f in biblio.get_files(e)})
    hashes = papers.checksums.load(config)
    written, changed, missing = 0, [], []
    for p in paths:
        if not os.path.isfile(p):
            missing.append(p)
            continue
        digest = checksum(p).hex()
        if p in hashes and hashes[p] != digest:
            changed.append(p)
        if hashes.get(p) != digest:
            written += 1
            hashes[p] = digest
    for p in changed:
        print(f"{short_home(p)}: changed since its checksum{'' if o.check else ' (updated)'}")
    if missing:
        print(f"{len(missing)} broken link{'' if len(missing) == 1 else 's'} (`papers file check` reports them)")
    if o.check:
        print(f"{len(paths) - len(missing)} files checked, {len(changed)} changed, "
              f"{written - len(changed)} without checksum")
        return
    papers.checksums.save(config, hashes)
    print(f"{written} checksum{'' if written == 1 else 's'} written ({len(changed)} changed)")
    savebib(biblio, config, other_changes=True)  # the backup commits files.json


# papers file fetch (also papers add --fetch-pdf)
# ===============================================

OPENALEX_ASK = 50  # entries of --missing that may query OpenAlex, above which papers asks (without API key)


def has_pdf(biblio, e):
    "the entry links to a PDF file that exists (a broken link counts as no PDF)"
    return any(f.lower().endswith('.pdf') and os.path.isfile(f) for f in biblio.get_files(e))


def _show(path):
    "a file in a message: relative to the current directory if under it, else with ~"
    relative = os.path.relpath(path)
    return relative if not relative.startswith('..') else short_home(path)


class LibraryChecksums:
    """the files of the library with the content of a PDF downloaded before
    (see papers.freepdf.get): of the entry, of another entry, or of the
    checksums of the library (.papers/files.json). A file is compared by
    size, then by checksum."""

    def __init__(self, biblio, config):
        self.biblio = biblio
        self.hashes = papers.checksums.load(config)
        self._sizes, self._digests = {}, {}

    def _matches(self, f, known):
        if f not in self._sizes:
            self._sizes[f] = os.path.getsize(f) if os.path.isfile(f) else None
        if self._sizes[f] != known['size']:
            return False
        if f not in self._digests:
            self._digests[f] = checksum(f).hex()
        return self._digests[f] == known['sha256']

    def local(self, e):
        "the `local` of papers.freepdf.get for the entry e"
        def local(link, known):
            for f in self.biblio.get_files(e):
                if self._matches(f, known):
                    return freepdf.Found(f, link, 'has')
            for other in self.biblio.entries:
                if other is not e:
                    for f in self.biblio.get_files(other):
                        if self._matches(f, known):
                            return freepdf.Found(f, link, 'linked', other.key)
            for f, digest in self.hashes.items():
                if digest == known['sha256'] and self._matches(f, known):
                    return freepdf.Found(f, link, 'known')
            return None
        return local


def _found_line(e, path, found):
    if found.how == 'linked':
        return f'{e.key}: {_show(path)} ({found.link.describe()}; same file as {found.other}, not downloaded)'
    if found.how == 'known':
        return f'{e.key}: {_show(path)} ({found.link.describe()}; a file of the library, not downloaded)'
    return f'{e.key}: {_show(path)} ({found.link.describe()})'


def _dry_run_lines(e, search, local, main, supplements):
    "the DRYRUN lines of an entry; False if no PDF would be found"
    lines, ok = [], True
    if main:
        links = list(search.links())
        for i, link in enumerate(links):
            known = freepdf.known_download(link.url)
            found = local(link, known) if known else None
            if found and found.how == 'has':
                what = f'already has {_show(found.path)} (from {link.host})'
            elif found:
                what = f'would attach {_show(found.path)} ({link.describe()}; ' + (
                    f'same file as {found.other}' if found.how == 'linked' else 'a file of the library') + ')'
            else:
                what = f'would download {link.url} ({link.describe()})'
            lines.append(f'DRYRUN: {e.key}: {"else " if i else ""}{what}')
        if not links:
            logger.error(f'{e.key}: {freepdf.no_pdf_message(search, [])}')
            ok = False
    if supplements:
        lines += [f'DRYRUN: {e.key}: would download {link.url} ({link.describe()})' for link in search.supplements()]
    for line in lines:
        print(line)
    return ok


def repair_pdf_links(config, biblio, exchange, entries, search_dirs, nameformat, mode, again=False, lookup=None):
    """`papers file fetch`, before it downloads: the entries whose PDF link
    is broken get the repair of `papers file fix` (see relink_broken_links;
    search_dirs: the folders of --search); --dry-run says what it would
    relink. Return the ids of the entries that have a PDF after the repair:
    their PDF is not downloaded (unless `again`). lookup: see plan_relinks."""
    dryrun = papers.config.DRYRUN
    broken = [e for e in entries if not has_pdf(biblio, e)
              and any(f.lower().endswith('.pdf') for f in broken_links(biblio, e))]
    if not broken:
        return set()
    relinks, unclear, restores, _ = relink_broken_links(config, biblio, exchange, broken, search_dirs, nameformat,
                                                        mode=mode, place=not dryrun, lookup=lookup)
    repaired = {id(e) for e, found, _ in relinks
                if any(f.lower().endswith('.pdf') for files in found.values() for f in files)}
    repaired |= {id(e) for e, link, _ in restores if link.lower().endswith('.pdf')}

    def end(e):
        return ', not downloaded' if id(e) in repaired and not again else ''
    for e, found, sources in relinks:
        found = {link: files for link, files in found.items() if files}
        if dryrun:
            for link, files in found.items():
                print(f"DRYRUN: {e.key}: would relink {_show(link)} -> {', '.join(_show(f) for f in files)} "
                      f"({_source(sources[link])})")
        elif found:
            print(f"{e.key}: relinked "
                  + '; '.join(f"{', '.join(_show(f) for f in files)} ({_source(sources[link])})"
                              for link, files in found.items()) + end(e))
    for e, link, reason in unclear:
        print(f"{e.key}: broken link: {_show(link)}: {reason} (not relinked)")
    for e, link, when in restores:
        if dryrun:
            print(f"DRYRUN: {e.key}: would restore {_show(link)} from the history ({when})")
        else:
            print(f"{e.key}: {_show(link)}: restored from the history ({when}){end(e)}")
    return repaired


def fetch_entry_pdfs(biblio, config, pools, entries, mode, least='any', supplements=False, again=False,
                     repaired=()):
    """`papers file fetch` (also `papers add --fetch-pdf`): find the free PDF
    of each entry (see papers.freepdf), and attach it as `papers file attach`
    does (with the files mode `mode`); the library is not saved. The main
    PDF of an entry that links to a PDF already is not fetched, unless
    `again`; with `supplements`, the supplements are fetched too. A PDF with
    the content of a file of the entry is not attached; one that this
    machine downloaded before (same URL) and that the library has is
    attached without downloading it. Return the number of entries whose PDF
    was not found (the errors are reported). repaired: the ids of the
    entries whose broken PDF link repair_pdf_links repaired (no main PDF
    fetched unless `again`, without message)."""
    from papers.bib import _same_content
    dryrun = papers.config.DRYRUN
    library = LibraryChecksums(biblio, config)
    failed = 0
    plans = []  # (entry, [Found])
    for e in entries:
        main = again or (not has_pdf(biblio, e) and id(e) not in repaired)
        if not main and id(e) not in repaired:
            print(f'{e.key}: has a PDF already (--again to fetch it anyway)')
            if not supplements:
                continue
        doi, arxiv = strip_doi(get_entry_val(e, 'doi', '')), entry_arxiv(e)
        if not doi and not arxiv:
            if main:
                logger.error(f'{e.key}: no DOI or arXiv id to look for a PDF')
                failed += 1
            continue
        search = freepdf.Search(doi, arxiv or None, least)
        local = library.local(e)
        if dryrun:
            failed += not _dry_run_lines(e, search, local, main, supplements)
            continue
        found = []
        if main:
            try:
                found.append(freepdf.fetch_pdf(search, local))
            except freepdf.NoPDF as error:
                logger.error(f'{e.key}: {error}')
                failed += 1
        if supplements:
            found += freepdf.fetch_supplements(search, local)
        plans.append((e, found))

    # the downloads are done: the files are attached
    for e, found in plans:
        new = []
        for f in found:
            if f.how == 'has':
                print(f'{e.key}: already has {_show(f.path)} (from {f.link.host})')
                continue
            if f.how == 'downloaded':
                same = _same_content(f.path, biblio.get_files(e) + [g.path for g in new])
                if same:
                    print(f'{e.key}: {f.link.url}: not attached, the entry has the same file: {_show(same)}')
                    freepdf.discard(f.path)
                    continue
            new.append(f)
        if not new:
            continue
        # a file of another entry is linked where it is (shared, as add does); the others are placed
        linked = [f for f in new if f.how == 'linked']
        placed = [f for f in new if f.how != 'linked']
        biblio.set_files(e, biblio.get_files(e) + [f.path for f in linked])
        if placed and not attach_files(biblio, e, [f.path for f in placed], config, mode, pools.files_dirs()):
            failed += 1
        for f in placed:  # the temporary folder of a download, now empty
            if f.how == 'downloaded' and not os.path.exists(f.path):
                shutil.rmtree(os.path.dirname(f.path), ignore_errors=True)
        paths = biblio.get_files(e)[-len(new):]
        for path, f in zip(paths, linked + placed):
            print(_found_line(e, path, f))
    return failed


def _confirm_openalex(o, entries):
    """--missing: ask before more than OPENALEX_ASK entries with a DOI may
    query OpenAlex without API key (-y/--yes does not ask); without a
    terminal, stop"""
    count = sum(1 for e in entries if strip_doi(get_entry_val(e, 'doi', '')))
    if count <= OPENALEX_ASK or os.environ.get(openalex.API_KEY_ENV) or o.yes:
        return
    question = (f'{count} entries with a DOI: each may make a request to OpenAlex, which allows few '
                f'requests a day without an API key ({openalex.API_KEY_ENV}, free at '
                f'https://openalex.org/settings/api)')
    if not stdin_is_terminal():
        raise PapersExit(f'{question}: no terminal to confirm; set {openalex.API_KEY_ENV}, pass -y/--yes, '
                         f'or name the entries (nothing was changed)')
    if input(f'{question}. Continue? [y/N] ').strip().lower() not in ('y', 'yes'):
        raise PapersExit('nothing was changed')


def file_fetchcmd(parser, o, config):
    set_format_config_from_cmd(o, config, 'name')
    if not o.entries and not o.missing:
        parser.error('papers file fetch KEY... or --missing [KEY...]')
    dryrun = papers.config.DRYRUN
    nameformat = config.nameformat  # the library's own, as for `papers file fix`
    pools = Pools(config) if dryrun else library_pools(config)
    biblio = get_biblio(config)
    entries = _entries_or_all(biblio, o.entries)
    if o.missing:
        entries = [e for e in entries if not has_pdf(biblio, e)]
    if config.filesdir is None:
        raise PapersExit('the library has no files directory, where the downloaded PDFs go '
                         '(pass --filesdir, or set it with `papers config filesdir DIR`)')
    mode = files_mode(o, config)
    if o.missing:
        _confirm_openalex(o, entries)
    # the repair of `papers file fix` first: the download, only if it gives no PDF (one step for both)
    exchange = Exchange(config, biblio, pools)
    pool = exchange.pools.pool(quiet=True)
    lookup = Lookup(config, biblio, pool, [pool.config.bibtex] if pool is not None else [])
    repaired = repair_pdf_links(config, biblio, exchange, entries, o.search or [], nameformat, mode, again=o.again,
                                lookup=lookup)
    fetched = [e for e in entries if id(e) not in repaired or o.again or o.supplements]
    failed = fetch_entry_pdfs(biblio, config, pools, fetched, mode, least=o.least_version,
                              supplements=o.supplements, again=o.again, repaired=repaired)
    if not dryrun:
        notes = save_entries(config, biblio, exchange)
        if papers.utils.PORCELAIN is not None:
            _print_biblio_diff(biblio, entries, notes=notes)
        else:
            print_push_notes(biblio, notes)
    if o.missing and not entries:
        print('every entry has a PDF')
    if failed:
        raise PapersExit()  # the errors are reported: exit 1
