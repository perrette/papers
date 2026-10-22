"""papers pull, push, sync, export"""
import os

from papers.identifiers import read_selection, select_some
from papers.library import get_biblio, savebib
from papers.pools import Exchange, GLOBAL_POOL_ID, PoolError, export
from papers.utils import PapersExit
from papers.cli.common import (duplicate_resolver, _entries_or_all, exchange_lines, pools_label, print_exchange,
                               save_exchange)


def _pull_pools(exchange, o):
    """the pools that pull and sync read: --pool PATH, else those of the
    library that can be used (a pool that cannot be used is a warning, if
    another one can). Return (pools, own): own is True for the library's."""
    if getattr(o, 'pool', None):
        return [exchange.pools.get(o.pool)], False
    pools = exchange.pools.all(quiet=True)
    if not pools:
        _check_pools(exchange)
    else:
        exchange.pools.all()  # the warnings
    return pools, True


def _check_pools(exchange, paths=None):
    """the pools of the library (or `paths`) that cannot be used: an error
    (once, rather than `not found` for each entry), unless the library has
    no pool, or the global pool was not created yet and nothing came from
    it"""
    pools = exchange.pools
    for path in (pools.paths() if paths is None else paths):
        if pools._is_global(path) and not os.path.exists(path) and not exchange.origin.records(GLOBAL_POOL_ID):
            continue
        try:
            pools.resolve(path)
        except PoolError as error:
            raise PapersExit(f'{error} (nothing was changed)')


def _pull_selection(exchange, pools, args, take_all=False):
    """the library entries to update, the pool entries to add (as (pool,
    pool entry)) and the library entries named, for `pull KEY... [--all]`:
    each identifier is looked up in the library first, then in the pools
    in order; one found nowhere is an error (raised before anything
    changes). A pool entry that is in the library (see
    Exchange.library_entry) is an update of that entry."""
    biblio = exchange.biblio
    selection = read_selection(args)
    entries, missing = select_some(biblio, selection) if selection else (list(biblio.entries), [])
    named = list(entries) if selection else []
    new = []
    if missing:
        if not pools:
            raise PapersExit('\n'.join(f'{arg}: no entry found' for arg in missing)
                             + '\n(the library has no pool to look in; nothing was changed)')
        for pool in pools:
            if not missing:
                break
            found, missing = select_some(pool.biblio, missing)
            for pe in found:
                e = exchange.library_entry(pe, pool)
                if e is not None:
                    if not any(e is x for x in entries):
                        entries.append(e)
                        named.append(e)
                elif not any(pe is x for _, x in new):
                    new.append((pool, pe))
        if missing:
            raise PapersExit('\n'.join(f'{arg}: no entry found' for arg in missing) + '\n(nothing was changed)')
    if take_all:
        if not pools:
            raise PapersExit('--all: the library has no pool')
        new.extend((pool, pe) for pool, pe in exchange.missing_all(pools) if not any(pe is x for _, x in new))
    return entries, new, named


def _pull(o, exchange, resolver, pools, own, shared_only=False):
    """the pull of `pull` and `sync`: return its report. shared_only:
    without KEY, only the entries shared with the pools (origin record)"""
    entries, new, named = _pull_selection(exchange, pools, o.entries, take_all=o.all)
    if shared_only and not o.entries and not o.all:
        entries = exchange.shared(entries, pools)
    report = exchange.pull(entries, resolver, pools=None if own else pools, new=new, named=named,
                           record_pull=not o.entries)
    save_exchange(exchange)
    return report


def pullcmd(parser, o, config):
    biblio = get_biblio(config)
    exchange = Exchange(config, biblio)
    pools, own = _pull_pools(exchange, o)
    if o.check:
        entries = _entries_or_all(biblio, o.entries)
        if not o.entries and not o.all:
            entries = exchange.shared(entries, pools)
        print('\n'.join(exchange.check(entries, all_entries=not o.entries, pools=None if own else pools))
              or 'nothing to pull')
        return
    report = _pull(o, exchange, duplicate_resolver(o, 'pull'), pools, own, shared_only=True)
    print_exchange(report, 'pull', biblio, pools)


def _push_pool(exchange, o, create):
    """the pool that push writes to: --pool PATH, else the first pool of the
    library (None if it does not exist yet and not create)"""
    if getattr(o, 'pool', None):
        return exchange.pools.get(o.pool, create=create)
    if create:
        return exchange.pools.target()
    pool = exchange.pools.pool(quiet=True)
    if pool is None:
        paths = exchange.pools.paths()
        if not paths:
            exchange.pools.target()  # the error: no pool
        _check_pools(exchange, paths[:1])
    return pool


def _push_entries(exchange, o, pool):
    """the entries to push: those named, all of them with --all, else the
    entries shared with the pool (origin record)"""
    biblio = exchange.biblio
    if o.entries:
        return _entries_or_all(biblio, o.entries)
    if o.all:
        return list(biblio.entries)
    return exchange.shared(biblio.entries, [pool]) if pool is not None else []


def _nothing_shared(o):
    "without KEY or --all, push and sync only exchange the entries shared with the pool"
    return not o.entries and not o.all


def _push(o, exchange, resolver):
    """the push of `push` and `sync`: (report, pool). Without KEY or --all,
    only the entries shared with the pool are pushed: nothing is created or
    written when there are none."""
    pool = _push_pool(exchange, o, create=not _nothing_shared(o))
    entries = _push_entries(exchange, o, pool)
    if not entries and _nothing_shared(o):
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
        print(f'push to {_pool_label(exchange, pool)}: no entries shared with it '
              '(`papers push KEY` or `papers push --all` adds entries to it)')
        return
    print_exchange(report, 'push', biblio, [pool])


def synccmd(parser, o, config):
    """pull, then push the same entries (without KEY or --all, the entries
    shared with the pools); stop before pushing if the pull left conflicts
    undecided. One line when nothing changed."""
    biblio = get_biblio(config)
    exchange = Exchange(config, biblio)
    o.entries = read_selection(o.entries)  # read once, for the pull and the push
    if not getattr(o, 'pool', None):
        _check_pools(exchange, exchange.pools.paths()[:1])  # the pool written to
    pools, own = _pull_pools(exchange, o)
    resolver = duplicate_resolver(o, 'pull')
    pull_report = _pull(o, exchange, resolver, pools, own, shared_only=True)
    pull_lines, pull_summary = exchange_lines(pull_report, 'pull', biblio, pools)
    if pull_lines:
        print('\n'.join(pull_lines + ([pull_summary] if pull_summary else [])))
    skipped = [e.key for e, _, what in pull_report if what == 'skipped']
    if skipped or resolver.quit:
        raise PapersExit(f'not pushed: the pull left conflicts undecided ({", ".join(skipped) or "quit"}). '
                         'Decide them with `papers pull`, then run `papers sync` again')
    exchange = Exchange(config, biblio, exchange.pools, exchange.origin)
    push_report, pool = _push(o, exchange, duplicate_resolver(o, 'push'))
    push_lines, push_summary = exchange_lines(push_report, 'push', biblio, [pool])
    if pull_lines or push_lines:
        if not pull_lines and pull_report:
            print(pull_summary)
        print('\n'.join(push_lines + ([push_summary] if push_summary else [])))
        return
    involved = {e.key.lower() for e, _, _ in pull_report + push_report}
    others = [p for p in [pool] if p is not None and not any(p is x for x in pools)]
    label = pools_label(pools + others) or _pool_label(exchange, pool)
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
