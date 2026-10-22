"""papers pull, push, sync, export"""
import os

from papers.identifiers import read_selection, select_some
from papers.library import get_biblio, savebib
from papers.pools import Exchange, GLOBAL_POOL_ID, PoolError, export
from papers.utils import PapersExit
from papers.cli.common import (duplicate_resolver, _entries_or_all, exchange_lines, pools_label, print_exchange,
                               save_exchange)


def _pull_pools(exchange, o):
    """the pool that pull and sync exchange with, and the pools searched
    for `KEY...` and `--all`: --pool PATH for both; else the main pool, and
    the pools of the library that can be used, in order (a pool that
    cannot be used is a warning; the main pool must be usable, unless it is
    the global pool not created yet). The pool is None when there is none
    to exchange with."""
    if getattr(o, 'pool', None):
        pool = exchange.pools.get(o.pool)
        return pool, [pool]
    _check_pools(exchange, exchange.pools.paths()[:1])
    pool = exchange.pools.pool(quiet=True)
    return pool, exchange.pools.all()


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


def _nothing_shared(o):
    "without KEY or --all, pull, push and sync only exchange the entries shared with the main pool"
    return not o.entries and not o.all


def _one_time(exchange, o, pool):
    "--pool PATH that is not the main pool: a one-time exchange, without origin records"
    return bool(getattr(o, 'pool', None)) and not exchange.is_main(pool)


def _one_time_note(kind, pool):
    "the message of pull, push or sync --pool PATH without KEY or --all, PATH not being the main pool"
    verb = {'pull': 'takes entries from it', 'push': 'sends entries to it', 'sync': 'exchanges entries with it'}[kind]
    prep = {'pull': 'from', 'push': 'to', 'sync': 'with'}[kind]
    return (f'{kind} {prep} {pool.label}: not the main pool, so no entries are shared with it '
            f'(`papers {kind} --pool PATH KEY...` or `--all` {verb} once)')


def _pull(o, exchange, resolver, pool, searched):
    """the pull of `pull` and `sync`: return (report of the pull, report of
    the push to the main pool). Without KEY or --all, only the entries
    shared with the main pool (origin record). The entries added from a
    pool searched (not the main pool) also go to the main pool in a
    library that is not local, or with auto-push."""
    entries, new, named = _pull_selection(exchange, searched, o.entries, take_all=o.all)
    if _nothing_shared(o):
        entries = exchange.shared(entries, pool)
    report = exchange.pull(entries, pool, resolver, new=new, named=named, record_pull=not o.entries)
    pushed = []
    if not getattr(o, 'pool', None):
        others = [e for e, p, what in report if what == 'added' and not exchange.is_main(p)]
        if others:
            pushed = exchange.push_added(others, others, duplicate_resolver(o, 'push'))
    save_exchange(exchange)
    return report, pushed


def _pulled_from(report, pool, searched):
    "the pools that the messages of a pull name: the pool exchanged with, and the pools searched that entries came from"
    pools = [pool] if pool is not None else []
    for _, p, _ in report:
        if p is not None and not any(p is x for x in pools):
            pools.append(p)
    return pools or searched


def pullcmd(parser, o, config):
    biblio = get_biblio(config)
    exchange = Exchange(config, biblio)
    pool, searched = _pull_pools(exchange, o)
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
    report, pushed = _pull(o, exchange, duplicate_resolver(o, 'pull'), pool, searched)
    print_exchange(report, 'pull', biblio, _pulled_from(report, pool, searched))
    lines, _ = exchange_lines(pushed, 'push', biblio, [])
    if lines:
        print('\n'.join(lines))


def _push_pool(exchange, o, create):
    """the pool that push writes to: --pool PATH, else the main pool of the
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
    entries shared with the main pool (origin record)"""
    biblio = exchange.biblio
    if o.entries:
        return _entries_or_all(biblio, o.entries)
    if o.all:
        return list(biblio.entries)
    return exchange.shared(biblio.entries, pool) if pool is not None else []


def _push(o, exchange, resolver):
    """the push of `push` and `sync`: (report, pool). Without KEY or --all,
    only the entries shared with the main pool are pushed: nothing is
    created or written when there are none."""
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
        if _one_time(exchange, o, pool):
            print(_one_time_note('push', pool))
        else:
            print(f'push to {_pool_label(exchange, pool)}: no entries shared with it '
                  '(`papers push KEY` or `papers push --all` adds entries to it)')
        return
    print_exchange(report, 'push', biblio, [pool])


def synccmd(parser, o, config):
    """pull, then push the same entries (without KEY or --all, the entries
    shared with the main pool); stop before pushing if the pull left
    conflicts undecided. One line when nothing changed."""
    biblio = get_biblio(config)
    exchange = Exchange(config, biblio)
    o.entries = read_selection(o.entries)  # read once, for the pull and the push
    pool, searched = _pull_pools(exchange, o)
    if _one_time(exchange, o, pool) and _nothing_shared(o):
        print('nothing to ' + _one_time_note('sync', pool))
        return
    resolver = duplicate_resolver(o, 'pull')
    pull_report, pushed = _pull(o, exchange, resolver, pool, searched)
    pools = _pulled_from(pull_report, pool, searched)
    pull_lines, pull_summary = exchange_lines(pull_report, 'pull', biblio, pools)
    pull_lines += exchange_lines(pushed, 'push', biblio, [])[0]
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
    label = pools_label([p for p in [pool] if p is not None]) or _pool_label(exchange, pool)
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
