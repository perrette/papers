"""papers pull, push, export, pool"""
import copy
import os

import papers.config
from papers import logger
from papers.config import short_home
from papers.library import get_biblio, savebib
from papers.pools import (Exchange, export, library_config_file, machine_pool_lines, pool_path_setting,
                          report_lines, status_lines)
from papers.utils import PapersExit
from papers.cli.common import _print_biblio_diff, duplicate_resolver, _entries_or_all, save_exchange


def pullcmd(parser, o, config):
    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)
    exchange = Exchange(config, biblio)
    entries = _entries_or_all(biblio, o.entries)
    if o.check:
        print('\n'.join(exchange.check(entries, all_entries=not o.entries)) or 'nothing to pull')
        return
    report = exchange.pull(entries, duplicate_resolver(o, 'pull'), record_pull=not o.entries)
    print('\n'.join(report_lines(report, 'pull')))
    save_exchange(exchange)
    _print_biblio_diff(biblio_init, biblio, entries)


def pushcmd(parser, o, config):
    biblio = get_biblio(config)
    exchange = Exchange(config, biblio)
    pool = exchange.pools.get(o.pool, create=True) if o.pool else exchange.pools.first(create=True)
    entries = _entries_or_all(biblio, o.entries)
    report = exchange.push(entries, pool, duplicate_resolver(o, 'push'))
    print('\n'.join(report_lines(report, f'push to {pool.label}')))
    save_exchange(exchange)


def exportcmd(parser, o, config):
    biblio = get_biblio(config)
    entries = _entries_or_all(biblio, o.entries)
    new, target = export(biblio, config, entries, o.dir, files=o.files, git=o.git)
    savebib(target, new)
    print(f'exported {len(entries)} entries to {new.configdir} (files: {o.files})')
    if o.pool:
        if config.file is None:
            raise PapersExit('--pool: no library to add the pool to')
        name = pool_path_setting(config, o.dir)
        config.set('pools', config.pools + [name])
        config.save()
        exchange = Exchange(config, biblio)
        pool = exchange.pools.resolve(name)
        for e in target.entries:
            exchange.origin.set(e.key, pool.id, e)
        exchange.origin.set_pulled(pool.id, pool.bibtex_mtime())
        exchange.origin.save()
        print(f'pools = {" ".join(config.pools)} (in {config.file})')


def poolcmd(parser, o, config):
    """the pools of the global configuration (as `papers config
    --global pools.NAME`), and the pools of the library"""
    machine = config.machine
    if o.pool_cmd in (None, 'list'):
        print(f'pools of the global configuration ({machine.file}):')
        print('\n'.join(machine_pool_lines(machine)))
        if config.file:
            print(f'pools of the library ({config.file}):' + ('' if config.pools else ' none'))
            print('\n'.join(status_lines(config)))
        return
    if o.pool_cmd == 'add':
        path = os.path.abspath(os.path.expanduser(o.path))
        if library_config_file(path) is None:
            logger.warning(f'{path} is not a library yet: create it with `papers init {short_home(path)}`')
        machine.set_pool(o.name, short_home(path))
    elif o.pool_cmd == 'remove':
        if o.name not in machine.data.get('pools', {}):
            raise PapersExit(f'{o.name} is not a pool of {machine.file}')
        machine.set_pool(o.name, None)
    if papers.config.DRYRUN:
        print(f'DRYRUN: {machine.file} not saved')
        return
    machine.save()
