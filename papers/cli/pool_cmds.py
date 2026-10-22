"""papers pull, push, sync, export"""
import os

from papers.identifiers import read_selection, select_entries, select_some
from papers.library import get_biblio, savebib
from papers.pools import Exchange, GLOBAL_POOL_ID, PoolError, export
from papers.utils import PapersExit
from papers.cli.common import duplicate_resolver, _entries_or_all, exchange_lines, print_exchange, save_exchange


def _source(exchange, o, create=False):
    """the pool of the command: --pool PATH, else the library's (None if it
    has none, or the global pool does not exist yet and not create)"""
    if getattr(o, 'pool', None):
        return exchange.pools.get(o.pool, create=create)
    if create:
        return exchange.pools.target()
    pool = exchange.pools.pool(quiet=True)
    if pool is None:
        _check_pool(exchange)
    return pool


def _check_pool(exchange):
    """the pool of the library is missing or cannot be read: an error (once,
    rather than `not found` for each entry), unless the library has no
    pool, or the global pool was not created yet and nothing came from it"""
    pools = exchange.pools
    path = pools.path()
    if path is None:
        return
    if pools._is_global(path) and not os.path.exists(path) and not exchange.origin.records(GLOBAL_POOL_ID):
        return
    try:
        pools.resolve(path)
    except PoolError as error:
        raise PapersExit(f'{error} (nothing was changed)')


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
        if pool is None:
            raise PapersExit('\n'.join(f'{arg}: no entry found' for arg in missing)
                             + '\n(the library has no pool to look in; nothing was changed)')
        for pe in select_entries(pool.biblio, missing):
            e = exchange.library_entry(pe, pool)
            if e is not None:
                if not any(e is x for x in entries):
                    entries.append(e)
                    named.append(e)
            elif not any(pe is x for x in new):
                new.append(pe)
    if take_all:
        if pool is None:
            raise PapersExit('--all: the library has no pool')
        new.extend(pe for pe in exchange.missing(pool) if not any(pe is x for x in new))
    return entries, new, named


def _nothing_shared(o):
    "without KEY or --all, pull, push and sync only exchange the entries shared with the pool"
    return not o.entries and not o.all


def _one_time(exchange, o, pool):
    "--pool PATH that is not the pool of the library: a one-time exchange, without origin records"
    return bool(getattr(o, 'pool', None)) and not exchange.is_own(pool)


def _one_time_note(kind, pool):
    "the message of pull, push or sync --pool PATH without KEY or --all, PATH not being the library's pool"
    verb = {'pull': 'takes entries from it', 'push': 'sends entries to it', 'sync': 'exchanges entries with it'}[kind]
    prep = {'pull': 'from', 'push': 'to', 'sync': 'with'}[kind]
    return (f'{kind} {prep} {pool.label}: not the pool of the library, so no entries are shared with it '
            f'(`papers {kind} --pool PATH KEY...` or `--all` {verb} once)')


def _pull(o, exchange, resolver, pool):
    """the pull of `pull` and `sync`: return its report. Without KEY or
    --all, only the entries shared with the pool (origin record)."""
    entries, new, named = _pull_selection(exchange, pool, o.entries, take_all=o.all)
    if _nothing_shared(o):
        entries = exchange.shared(entries, pool)
    report = exchange.pull(entries, pool, resolver, new=new, named=named, record_pull=not o.entries)
    save_exchange(exchange)
    return report


def pullcmd(parser, o, config):
    biblio = get_biblio(config)
    exchange = Exchange(config, biblio)
    pool = _source(exchange, o)
    if _one_time(exchange, o, pool) and _nothing_shared(o):
        print(_one_time_note('pull', pool))
        return
    if o.check:
        entries = _entries_or_all(biblio, o.entries)
        if _nothing_shared(o):
            entries = exchange.shared(entries, pool)
        lines = exchange.check(entries, pool, all_entries=not o.entries) if pool is not None else []
        print('\n'.join(lines) or 'nothing to pull')
        return
    report = _pull(o, exchange, duplicate_resolver(o, 'pull'), pool)
    print_exchange(report, 'pull', biblio, pool)


def _push_entries(exchange, o, pool):
    """the entries to push: those named, all of them with --all, else the
    entries shared with the pool (origin record)"""
    biblio = exchange.biblio
    if o.entries:
        return _entries_or_all(biblio, o.entries)
    if o.all:
        return list(biblio.entries)
    return exchange.shared(biblio.entries, pool) if pool is not None else []


def _push(o, exchange, resolver):
    """the push of `push` and `sync`: (report, pool). Without KEY or --all,
    only the entries shared with the pool are pushed: nothing is created or
    written when there are none."""
    nothing_shared = _nothing_shared(o)
    if nothing_shared and not getattr(o, 'pool', None) and exchange.pools.path() is None:
        exchange.pools.target()  # the error: no pool
    pool = _source(exchange, o, create=not nothing_shared)
    entries = _push_entries(exchange, o, pool)
    if not entries and nothing_shared:
        return [], pool
    report = exchange.push(entries, pool, resolver)
    save_exchange(exchange)
    return report, pool


def _pool_label(exchange, pool):
    "how the messages name the pool of a push (it may not exist yet)"
    return pool.label if pool is not None else f'pool {exchange.config.pool_label()}'


def pushcmd(parser, o, config):
    biblio = get_biblio(config)
    exchange = Exchange(config, biblio)
    report, pool = _push(o, exchange, duplicate_resolver(o, 'push'))
    if not report and _nothing_shared(o):
        if _one_time(exchange, o, pool):
            print(_one_time_note('push', pool))
        else:
            print(f'push to {_pool_label(exchange, pool)}: no entries shared with it '
                  '(`papers push KEY` or `papers push --all` adds entries to it)')
        return
    print_exchange(report, 'push', biblio, pool)


def synccmd(parser, o, config):
    """pull, then push the same entries (without KEY or --all, the entries
    shared with the pool); stop before pushing if the pull left conflicts
    undecided. One line when nothing changed."""
    biblio = get_biblio(config)
    exchange = Exchange(config, biblio)
    o.entries = read_selection(o.entries)  # read once, for the pull and the push
    pool = _source(exchange, o)
    if _one_time(exchange, o, pool) and _nothing_shared(o):
        print('nothing to ' + _one_time_note('sync', pool))
        return
    resolver = duplicate_resolver(o, 'pull')
    pull_report = _pull(o, exchange, resolver, pool)
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
    if pull_lines or push_lines:
        if not pull_lines and pull_report:
            print(pull_summary)
        print('\n'.join(push_lines + ([push_summary] if push_summary else [])))
        return
    involved = {e.key.lower() for e, _, _ in pull_report + push_report}
    label = _pool_label(exchange, pool)
    if not involved and _nothing_shared(o):
        print(f'nothing to sync with {label}: no entries shared with it '
              '(`papers sync --all` adds the entries missing on each side)')
    else:
        n = len(involved)
        print(f'nothing to sync with {label}' + (f' ({n} entr{"y" if n == 1 else "ies"} unchanged)' if n else ''))


def exportcmd(parser, o, config):
    biblio = get_biblio(config)
    entries = _entries_or_all(biblio, o.entries)
    new, target = export(biblio, config, entries, o.dir, files=o.files, git=o.git)
    savebib(target, new)
    print(f'exported {len(entries)} entries to {new.configdir} (files: {o.files})')
