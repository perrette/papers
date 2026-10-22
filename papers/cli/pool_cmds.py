"""papers pull, push, sync, export"""
import os

from papers.identifiers import read_selection, select_entries, select_some
from papers.library import get_biblio, savebib
from papers.pools import Exchange, GLOBAL_POOL_ID, PoolError, export
from papers.utils import PapersExit
from papers.cli.common import duplicate_resolver, _entries_or_all, print_exchange, save_exchange


def _source(exchange, o, create=False):
    """the pool of the command: --pool PATH, else the library's (None if it
    has none, or the global pool does not exist yet)"""
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
    path = exchange.config.pool_path()
    if path is None or pools._is_self(path):
        return
    if pools._is_global(path) and not os.path.exists(path) and not exchange.origin.records(GLOBAL_POOL_ID):
        return
    try:
        pools.resolve(path)
    except PoolError as error:
        raise PapersExit(f'{error} (nothing was changed)')


def _pull_selection(exchange, pool, args, take_all=False):
    """the library entries to update and the pool entries to add for
    `pull KEY... [--all]`: each identifier is looked up in the library
    first, then in the pool; one found in neither is an error (raised
    before anything changes). A pool entry that is in the library (see
    Exchange.library_entry) is an update of that entry."""
    biblio = exchange.biblio
    selection = read_selection(args)
    entries, missing = select_some(biblio, selection) if selection else (list(biblio.entries), [])
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
            elif not any(pe is x for x in new):
                new.append(pe)
    if take_all:
        if pool is None:
            raise PapersExit('--all: the library has no pool')
        new.extend(pe for pe in exchange.missing(pool) if not any(pe is x for x in new))
    return entries, new


def _pull(o, exchange, resolver):
    "the pull of `pull` and `sync`: print and return its report"
    pool = _source(exchange, o)
    entries, new = _pull_selection(exchange, pool, o.entries, take_all=o.all)
    report = exchange.pull(entries, resolver, pool=pool, new=new, record_pull=not o.entries)
    save_exchange(exchange)
    print_exchange(report, 'pull', exchange.biblio, pool)
    return report


def pullcmd(parser, o, config):
    biblio = get_biblio(config)
    exchange = Exchange(config, biblio)
    if o.check:
        _source(exchange, o)
        entries = _entries_or_all(biblio, o.entries)
        print('\n'.join(exchange.check(entries, all_entries=not o.entries)) or 'nothing to pull')
        return
    _pull(o, exchange, duplicate_resolver(o, 'pull'))


def _push(o, exchange, resolver, entries):
    pool = _source(exchange, o, create=True)
    report = exchange.push(entries, pool, resolver)
    save_exchange(exchange)
    print_exchange(report, 'push', exchange.biblio, pool)


def pushcmd(parser, o, config):
    biblio = get_biblio(config)
    exchange = Exchange(config, biblio)
    _push(o, exchange, duplicate_resolver(o, 'push'), _entries_or_all(biblio, o.entries))


def synccmd(parser, o, config):
    """pull, then push the same entries; stop before pushing if the pull
    left conflicts undecided"""
    biblio = get_biblio(config)
    exchange = Exchange(config, biblio)
    o.all = False
    o.entries = read_selection(o.entries)  # read once, for the pull and the push
    resolver = duplicate_resolver(o, 'pull')
    report = _pull(o, exchange, resolver)
    skipped = [e.key for e, _, what in report if what == 'skipped']
    if skipped or resolver.quit:
        raise PapersExit(f'not pushed: the pull left conflicts undecided ({", ".join(skipped) or "quit"}). '
                         'Decide them with `papers pull`, then run `papers sync` again')
    entries = _entries_or_all(biblio, o.entries)  # the entries pulled from the pool are in the library now
    exchange = Exchange(config, biblio, exchange.pools, exchange.origin)
    _push(o, exchange, duplicate_resolver(o, 'push'), entries)


def exportcmd(parser, o, config):
    biblio = get_biblio(config)
    entries = _entries_or_all(biblio, o.entries)
    new, target = export(biblio, config, entries, o.dir, files=o.files, git=o.git)
    savebib(target, new)
    print(f'exported {len(entries)} entries to {new.configdir} (files: {o.files})')
