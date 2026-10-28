"""papers pull, push, sync, export"""
import os
from papers.identifiers import read_selection, select_entries, select_some
from papers.library import get_biblio, savebib
from papers.formats import FILENAMES, FORMATS, dumps, load_rispy
from papers.pools import Exchange, PoolError, NO_POOL_MESSAGE, export, report_counts, removed_note
from papers.utils import PapersExit
from papers.cli.common import (duplicate_resolver, _entries_or_all, exchange_lines, print_exchange, save_exchange,
                               library_pools, push_changed, push_notes, print_push_notes)


def exchange_pools(config, o):
    """the pools of an exchange (pull, push, sync), made before the library
    is loaded: an error if there is no --pool PATH and the library has no
    pool. A shallow library that exchanges with another library than its
    pool places the files it takes in its pool, as `add` does (see
    papers.pools.use_pool_files): its pools then, else None (the default
    pools of Exchange)."""
    if not getattr(o, 'pool', None) and not config.has_pool():
        raise PapersExit(NO_POOL_MESSAGE)
    pools = None
    if getattr(o, 'pool', None) and config.shallow:
        try:
            pools = library_pools(config)
        except PoolError as error:
            raise PapersExit(f'{error} (nothing was changed)')
    return pools


def _exchange(config, o):
    """the library of an exchange (pull, push, sync): the library given with
    --pool PATH or the pool of the library (see exchange_pools), and the
    Exchange."""
    pools = exchange_pools(config, o)
    biblio = get_biblio(config)
    exchange = Exchange(config, biblio, pools)
    return biblio, exchange


def _source(exchange, o):
    """the pool of the command: --pool PATH, else the library's; an error
    if it is not a library"""
    try:
        if getattr(o, 'pool', None):
            return exchange.pools.get(o.pool)
        return exchange.pools.target()
    except PoolError as error:
        raise PapersExit(f'{error} (nothing was changed)')


def _forward(exchange, pool):
    """a shallow library that took entries from another library than its
    pool: they go to its pool too, as with `add` (see
    papers.cli.common.push_changed); return the notes of that push"""
    if not exchange.config.shallow or exchange.is_own(pool):
        return {}
    return push_notes(push_changed(exchange))


def _pull_selection(exchange, pool, args, take_all=False):
    """the library entries to update, the pool entries to add and the
    library entries named, for `pull KEY... [--all]`: each identifier is
    looked up in the library first, then in the pool; one found in neither
    is an error (raised before anything changes). A pool entry that is in
    the library (see Exchange.library_entry) is an update of that entry."""
    biblio = exchange.biblio
    selection = read_selection(args)
    entries, missing = select_some(biblio, selection) if selection else (list(biblio.entries), [])
    named = list(entries) if selection else []
    new = []
    if missing:
        for pe in select_entries(pool.biblio, missing):
            e = exchange.library_entry(pe, pool)
            if e is not None:
                if not any(e is x for x in entries):
                    entries.append(e)
                    named.append(e)
            elif not any(pe is x for x in new):
                new.append(pe)
    if take_all:
        new.extend(pe for pe in exchange.missing(pool) if not any(pe is x for x in new))
    return entries, new, named


def _nothing_shared(o, selected=None):
    """without KEY or --all, pull, push and sync only exchange the entries
    shared with the pool. selected: the entries of `papers list --push`
    (--pull, --sync), as KEY... names them"""
    return not o.entries and not o.all and selected is None


def _shared(exchange, entries, pool, o):
    """the entries shared with the pool among `entries` (see
    Exchange.sharing), for an exchange without KEY or --all. The entries
    removed from the pool are left out: their note is printed, and their
    origin records are dropped (they are no longer shared, and the note
    comes once)."""
    shared, removed = exchange.sharing(entries, pool)
    for e in removed:
        print(removed_note(e, pool, _options(o)))
    exchange.forget(removed, pool)
    return shared


def _pull(o, exchange, resolver, pool, selected=None):
    """the pull of `pull` and `sync`: (report, notes of the push to the pool
    of a shallow library, see _forward). Without KEY or --all, only the
    entries shared with the pool (see _shared)."""
    if selected is not None:
        entries, new, named = list(selected), [], list(selected)
    else:
        entries, new, named = _pull_selection(exchange, pool, o.entries, take_all=o.all)
    if _nothing_shared(o, selected):
        entries = _shared(exchange, entries, pool, o)
    report = exchange.pull(entries, pool, resolver, new=new, named=named,
                           record_pull=not o.entries and selected is None)
    notes = _forward(exchange, pool)
    save_exchange(exchange)
    return report, notes


def pullcmd(parser, o, config):
    biblio, exchange = _exchange(config, o)
    pull_entries(o, biblio, exchange)


def pull_entries(o, biblio, exchange, selected=None):
    """`papers pull` (also `papers list --pull`, with the listed entries
    as `selected`): o has the options of pull"""
    pool = _source(exchange, o)
    if o.check:
        entries = _entries_or_all(biblio, o.entries)
        if _nothing_shared(o):
            shared, removed = exchange.sharing(entries, pool)
            listed = {id(e) for e in shared + removed}
            entries = [e for e in entries if id(e) in listed]
        lines = exchange.check(entries, pool, all_entries=not o.entries, options=_options(o))
        print('\n'.join(lines) or 'nothing to pull')
        return
    report, notes = _pull(o, exchange, duplicate_resolver(o, 'pull'), pool, selected)
    print_exchange(report, 'pull', biblio, pool)
    print_push_notes(biblio, notes)


def _push_entries(exchange, o, pool, selected=None):
    """the entries to push: those named (or selected), all of them with
    --all, else the entries shared with the pool (see _shared)"""
    biblio = exchange.biblio
    if selected is not None:
        return list(selected)
    if o.entries:
        return _entries_or_all(biblio, o.entries)
    if o.all:
        return list(biblio.entries)
    return _shared(exchange, biblio.entries, pool, o)


def _push(o, exchange, resolver, selected=None):
    """the push of `push` and `sync`: (report, pool). Without KEY or --all,
    only the entries shared with the pool are pushed: only the origin
    records of the entries removed from the pool are written when there
    are none."""
    nothing_shared = _nothing_shared(o, selected)
    pool = _source(exchange, o)
    entries = _push_entries(exchange, o, pool, selected)
    if not entries and nothing_shared:
        if exchange.origin.changed:
            save_exchange(exchange)
        return [], pool
    report = exchange.push(entries, pool, resolver)
    save_exchange(exchange)
    return report, pool


def _options(o):
    "the --pool option of the command, to repeat in a message"
    return f' --pool {o.pool}' if getattr(o, 'pool', None) else ''


def pushcmd(parser, o, config):
    biblio, exchange = _exchange(config, o)
    push_entries(o, biblio, exchange)


def push_entries(o, biblio, exchange, selected=None):
    """`papers push` (also `papers list --push`, with the listed entries
    as `selected`): o has the options of push"""
    report, pool = _push(o, exchange, duplicate_resolver(o, 'push'), selected)
    if not report and _nothing_shared(o, selected):
        print(f'push to {pool.label}: no entries shared with it '
              f'(`papers push{_options(o)} KEY` or `papers push{_options(o)} --all` adds entries to it)')
        return
    print_exchange(report, 'push', biblio, pool)


def synccmd(parser, o, config):
    """pull, then push the same entries (without KEY or --all, the entries
    shared with the pool); stop before pushing if the pull left conflicts
    undecided. One line when nothing changed."""
    biblio, exchange = _exchange(config, o)
    o.entries = read_selection(o.entries)  # read once, for the pull and the push
    sync_entries(o, biblio, exchange)


def sync_entries(o, biblio, exchange, selected=None):
    """`papers sync` (also `papers list --sync`, with the listed entries
    as `selected`): o has the options of sync"""
    config = exchange.config
    pool = _source(exchange, o)
    resolver = duplicate_resolver(o, 'pull')
    pull_report, notes = _pull(o, exchange, resolver, pool, selected)
    print_push_notes(biblio, notes)
    pull_report = [r for r in pull_report if r[2] != 'not found']  # the push adds them
    pull_lines, pull_summary = exchange_lines(pull_report, 'pull', biblio, pool)
    if pull_lines:
        print('\n'.join(pull_lines + ([pull_summary] if pull_summary else [])))
    skipped = [e.key for e, _, what in pull_report if what == 'skipped']
    if skipped or resolver.quit:
        raise PapersExit(f'not pushed: the pull left conflicts undecided ({", ".join(skipped) or "quit"}). '
                         'Decide them with `papers pull`, then run `papers sync` again')
    exchange = Exchange(config, biblio, exchange.pools, exchange.origin)
    push_report, pool = _push(o, exchange, duplicate_resolver(o, 'push'), selected)
    push_lines, push_summary = exchange_lines(push_report, 'push', biblio, pool)
    pull_counted = report_counts(pull_report)
    push_counted = report_counts(push_report)
    if pull_lines or push_lines or pull_counted or push_counted:
        if not pull_lines and pull_counted:
            print(pull_summary)
        if push_lines or push_counted:
            print('\n'.join(push_lines + ([push_summary] if push_summary else [])))
        return
    involved = pull_report or push_report
    label = pool.label
    if not involved and _nothing_shared(o, selected):
        print(f'nothing to sync with {label}: no entries shared with it '
              f'(`papers sync{_options(o)} --all` adds the entries missing on each side)')
    else:
        print(f'nothing to sync with {label}')


def exportcmd(parser, o, config):
    biblio = get_biblio(config)
    entries = _entries_or_all(biblio, o.entries)
    export_entries(o, config, biblio, entries)


def _export_formats(o):
    "the formats of --format, once each, in the order of FORMATS"
    formats = [f for fmts in (o.format or [['bibtex']]) for f in fmts]
    return [f for f in FORMATS if f in formats]


def export_entries(o, config, biblio, entries):
    """`papers export` (also `papers list --export`): write the entries in
    the directory o.dir, with the options of export (o.format, o.files)"""
    formats = _export_formats(o)
    if 'ris' in formats:
        load_rispy()  # before anything is written
    library = 'bibtex' in formats
    new, target = export(biblio, config, entries, o.dir, files=o.files, library=library)
    dest = new.configdir if library else os.path.abspath(o.dir)
    written = []
    if library:
        savebib(target, new)
        written.append(os.path.basename(new.bibtex))
    for fmt in formats:
        if fmt == 'bibtex':
            continue
        path = os.path.join(dest, FILENAMES[fmt])
        text = dumps(target.entries, fmt,
                     files=lambda e: [os.path.relpath(f, dest) for f in target.get_files(e)])
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        written.append(FILENAMES[fmt])
    print(f'exported {len(entries)} entries to {dest} ({", ".join(written)}; files: {o.files})')
    if not library:
        print(f'{dest} is not a papers library (no {FILENAMES["bibtex"]}): --format bib or all makes one')
