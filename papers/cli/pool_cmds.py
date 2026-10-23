"""papers pull, push, sync, export"""
from papers.identifiers import read_selection, select_entries, select_some
from papers.library import get_biblio, savebib
from papers.pools import Exchange, PoolError, NO_POOL_MESSAGE, export, report_counts
from papers.utils import PapersExit
from papers.cli.common import (duplicate_resolver, _entries_or_all, exchange_lines, print_exchange, save_exchange,
                               library_pools, push_changed, push_notes, print_push_notes)


def _exchange(config, o):
    """the library of an exchange (pull, push, sync): the library given with
    --pool PATH or the pool of the library (an error if the library has
    none), and the Exchange. A shallow library that exchanges with another
    library than its pool places the files it takes in its pool, as `add`
    does (see papers.pools.use_pool_files)."""
    if not getattr(o, 'pool', None) and not config.has_pool():
        raise PapersExit(NO_POOL_MESSAGE)
    pools = None
    if getattr(o, 'pool', None) and config.shallow:
        try:
            pools = library_pools(config)
        except PoolError as error:
            raise PapersExit(f'{error} (nothing was changed)')
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


def _nothing_shared(o):
    "without KEY or --all, pull, push and sync only exchange the entries shared with the pool"
    return not o.entries and not o.all


def _pull(o, exchange, resolver, pool):
    """the pull of `pull` and `sync`: (report, notes of the push to the pool
    of a shallow library, see _forward). Without KEY or --all, only the
    entries shared with the pool (origin record)."""
    entries, new, named = _pull_selection(exchange, pool, o.entries, take_all=o.all)
    if _nothing_shared(o):
        entries = exchange.shared(entries, pool)
    report = exchange.pull(entries, pool, resolver, new=new, named=named, record_pull=not o.entries)
    notes = _forward(exchange, pool)
    save_exchange(exchange)
    return report, notes


def pullcmd(parser, o, config):
    biblio, exchange = _exchange(config, o)
    pool = _source(exchange, o)
    if o.check:
        entries = _entries_or_all(biblio, o.entries)
        if _nothing_shared(o):
            entries = exchange.shared(entries, pool)
        lines = exchange.check(entries, pool, all_entries=not o.entries)
        print('\n'.join(lines) or 'nothing to pull')
        return
    report, notes = _pull(o, exchange, duplicate_resolver(o, 'pull'), pool)
    print_exchange(report, 'pull', biblio, pool)
    print_push_notes(biblio, notes)


def _push_entries(exchange, o, pool):
    """the entries to push: those named, all of them with --all, else the
    entries shared with the pool (origin record)"""
    biblio = exchange.biblio
    if o.entries:
        return _entries_or_all(biblio, o.entries)
    if o.all:
        return list(biblio.entries)
    return exchange.shared(biblio.entries, pool)


def _push(o, exchange, resolver):
    """the push of `push` and `sync`: (report, pool). Without KEY or --all,
    only the entries shared with the pool are pushed: nothing is written
    when there are none."""
    nothing_shared = _nothing_shared(o)
    pool = _source(exchange, o)
    entries = _push_entries(exchange, o, pool)
    if not entries and nothing_shared:
        return [], pool
    report = exchange.push(entries, pool, resolver)
    save_exchange(exchange)
    return report, pool


def _options(o):
    "the --pool option of the command, to repeat in a message"
    return f' --pool {o.pool}' if getattr(o, 'pool', None) else ''


def pushcmd(parser, o, config):
    biblio, exchange = _exchange(config, o)
    report, pool = _push(o, exchange, duplicate_resolver(o, 'push'))
    if not report and _nothing_shared(o):
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
    pool = _source(exchange, o)
    resolver = duplicate_resolver(o, 'pull')
    pull_report, notes = _pull(o, exchange, resolver, pool)
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
    push_report, pool = _push(o, exchange, duplicate_resolver(o, 'push'))
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
    if not involved and _nothing_shared(o):
        print(f'nothing to sync with {label}: no entries shared with it '
              f'(`papers sync{_options(o)} --all` adds the entries missing on each side)')
    else:
        print(f'nothing to sync with {label}')


def exportcmd(parser, o, config):
    biblio = get_biblio(config)
    entries = _entries_or_all(biblio, o.entries)
    new, target = export(biblio, config, entries, o.dir, files=o.files, git=o.git)
    savebib(target, new)
    print(f'exported {len(entries)} entries to {new.configdir} (files: {o.files})')
