"""papers status, init, install, uninstall, config, migrate"""
import copy
import os
from pathlib import Path
import shutil

import papers.config
from papers import logger
from papers.backup import init_backup
from papers.config import (CONFIG_FILE_LOCAL, Config, LIBRARY_CONFIG_FILES, LIBRARY_ONLY, NO_POOL,
                           SETTINGS, format_value, parse_value, pool_setting, short_home)
from papers.files import broken_links, delete_files, is_inside
from papers.install import DefaultAsker, InputAsker, RESET_WORDS, _ask_path, apply_install, resolve_install
from papers.library import convert_file_links, find_config, get_biblio, snapshot_backup
from papers.migrate import migrate_folders, migrate_v2_global
from papers.pools import Exchange, Pools
from papers.utils import PapersExit, set_directory
from papers.cli.common import (format_options, init_hint, check_install, _print_biblio_diff, no_library_message,
                               save_exchange, stdin_is_terminal)


def _install(o, config, asker, target=None):
    "resolve and apply an install of a library, with the format options of the command line"
    plan = resolve_install(config, o, asker=asker, target=target)
    for name, value in format_options(o).items():
        plan.config.set(name, value)
    if papers.config.DRYRUN:
        print(f"DRYRUN: {plan.config.file} not saved")
        return plan.config
    return apply_install(plan)


def initcmd(parser, o, config):
    """create a library in the current directory, or in DIR (created if missing)"""
    if o.dir is None:
        return _initcmd(parser, o, config)
    os.makedirs(o.dir, exist_ok=True)
    with set_directory(o.dir):
        _initcmd(parser, o, find_config(machine=config.machine))


def _initcmd(parser, o, config):
    for name in LIBRARY_CONFIG_FILES:
        if os.path.exists(name):
            raise PapersExit(f"a library already exists here ({name}): "
                             "change its settings with `papers config`")
    if config.origin == 'library':
        logger.info(f"the new library is inside the library of {config.file}")
    o.reset = False
    if o.local_setting and o.pool is None:
        o.pool = NO_POOL  # --local without --pool: a library of its own, without pool
    config = _install(o, Config(machine=config.machine), DefaultAsker(), target=CONFIG_FILE_LOCAL)
    print('\n'.join(init_summary(config)))


def init_summary(config):
    """what `papers init` prints: the library created, its bibtex, where its
    files go, its pool and its backup"""
    if config.local or not config.has_pool():
        files = f'{_show(config.filesdir)} (the files directory of the library)' if config.filesdir \
            else 'linked where they are (no files directory)'
    else:
        files = f'in the pool {config.pool_label()}'
    lines = [f'created the library {short_home(str(config.configdir))}',
             f'* bibtex:  {_show(config.bibtex) if config.bibtex else "none"}',
             f'* files:   {files}']
    if not config.has_pool():
        lines.append('* pool:    none')
    elif config.local:  # otherwise the files line names the pool
        lines.append(f'* pool:    {config.pool_label()} (shared entries; the PDFs stay in this library)')
    return lines + ['* backup:  ' + ('git' + (' and git-lfs' if config.gitlfs else '') if config.git else 'off'),
                    '`papers status -v` shows all settings']


def installcmd(parser, o, config):
    """
    Given options and a config state, installs the expected config files.

    The decision logic lives in papers.install (resolve_install); this
    function only wires up prompting and applies the resulting plan.
    """
    if o.edit and o.reset:
        parser.error('--edit and --reset are mutually exclusive')
    if o.edit:
        # historical behavior: --edit means "apply my flags, ask nothing"
        o.yes = True
    asker = DefaultAsker() if o.yes else InputAsker()

    if o.local is True:
        logger.warning("--local is ignored: a library configuration is always local (see `papers init`)")
    if o.local is False:
        return install_global(parser, o, config, asker)

    if config.origin == 'library':
        logger.warning(f"`papers install` on an existing library is deprecated: "
                       f"change its settings with `papers config` (updating {config.file})")
        target = None
    else:
        # behave like `papers init`: a new library in the current directory
        config = Config(machine=config.machine)
        target = CONFIG_FILE_LOCAL

    config = _install(o, config, asker, target=target)
    print(config.status(check_files=not o.no_check_files, verbose=True))


def install_global(parser, o, config, asker):
    """`papers install --global` (deprecated): create or update the library
    configuration next to the bibtex, and register the library's directory
    as the `default` pool of the global configuration"""
    logger.warning("`papers install --global` is deprecated: the global library of papers v2 is now the "
                   "global pool, used outside of any library. Use `papers config --global pool DIR` and "
                   "`papers init DIR` (DIR: the library). This command does both: the library configuration is "
                   "written next to the bibtex, and its directory becomes the global pool.")
    machine = config.machine
    bibtex = o.bibtex
    if not bibtex:
        default = config.bibtex if config.origin in ('v2-global', 'global-pool') and config.bibtex else 'papers.bib'
        bibtex = _ask_path(asker, "Bibtex file name", default)
    if not bibtex:
        raise PapersExit("install --global needs a bibtex file")
    bibtex = os.path.abspath(bibtex)

    # the global configuration of v2 becomes a library and the global pool,
    # as with `papers migrate` (the library below then updates or replaces it)
    migrate_v2_global(machine, dryrun=papers.config.DRYRUN)

    libdir = os.path.dirname(bibtex)
    target = os.path.join(libdir, CONFIG_FILE_LOCAL)
    existing = Config.load(target, machine=machine) if os.path.exists(target) else Config(machine=machine)

    o.bibtex = bibtex
    o.pool = NO_POOL  # the global pool itself
    o.local_setting = True
    if o.filesdir and o.filesdir.lower() not in RESET_WORDS:
        o.filesdir = os.path.abspath(o.filesdir)
    if papers.config.DRYRUN and not os.path.isdir(libdir):
        print(f"DRYRUN: {libdir} not created, {target} not saved")
        return
    os.makedirs(libdir, exist_ok=True)
    with set_directory(libdir):
        config = _install(o, existing, asker, target=target)

    if papers.config.DRYRUN:
        print(f"DRYRUN: {libdir} not registered as the global pool in {machine.file}")
        return
    machine.set('pool', short_home(libdir))
    machine.save()
    print(f"registered {libdir} as the global pool in {machine.file}")
    print(config.status(check_files=not o.no_check_files, verbose=True))


def uninstallcmd(parser, o, config):
    if config.file is None:
        parser.error('no library configuration was found')
    if o.recursive:
        logger.warning("uninstall --recursive is deprecated and ignored: there is no global configuration to "
                       "remove in v3, only the configuration of this library is removed")
    _uninstall(parser, o, config)
    print(config.status(verbose=True))


def _uninstall(parser, o, config):
    if config.origin == 'global-pool':
        raise PapersExit(f"no library in this directory or above. The global pool ({config.configdir}) "
                         f"is used outside of libraries: remove its configuration with "
                         f"`papers -C {config.configdir} uninstall`")
    if Path(config.file).exists():
        print(f"remove configuration file: {config.file}")
        os.remove(config.file)
    else:
        logger.info("The uninstaller found no config file to remove.")
        return

    # be transparent about what is left behind
    if config.bibtex and os.path.exists(config.bibtex):
        print(f"the bibliography remains: {config.bibtex}")
    if config.filesdir and os.path.exists(config.filesdir):
        print(f"the files directory remains: {config.filesdir}")
    if config.gitdir and os.path.isdir(config.gitdir):
        if o.remove_backup:
            shutil.rmtree(config.gitdir)
            print(f"removed backup directory: {config.gitdir}")
        else:
            print(f"the backup directory remains: {config.gitdir}")
            print(f"  remove it with `papers backup remove {os.path.basename(config.gitdir)}`")


def _check_setting_name(name, is_global):
    if name not in SETTINGS:
        raise PapersExit(f"unknown setting: {name}. Settings: {', '.join(SETTINGS)}")
    if is_global and name in LIBRARY_ONLY:
        raise PapersExit(f"{name} is a setting of a library: the global configuration holds the global pool and "
                         "the default settings of the libraries, and defines no library (the global library of "
                         "papers v2 is now the global pool, see `papers config --global pool`)")


def _parse_setting(name, values):
    try:
        return parse_value(name, values)
    except ValueError as error:
        raise PapersExit(str(error))


def configcmd(parser, o, config):
    """get and set the settings of the library (or with --global, of the
    global configuration)"""
    if o.unset and o.key:
        parser.error('--unset takes the setting name: papers config --unset KEY')
    name = o.unset or o.key
    if name:
        _check_setting_name(name, o.is_global)
    if o.is_global:
        return machine_configcmd(parser, o, config.machine, name)

    if config.file is None:
        raise PapersExit(f"{no_library_message(config)}, or use `papers config --global`")

    if not name:
        print(f"# {config.file}")
        print('\n'.join(config.settings_lines()))
        return

    if not o.unset and not o.values:
        print(format_value(config.get(name)))
        return

    if config.origin == 'v2-global':
        raise PapersExit(f"{config.file} is the global configuration of papers v2: "
                         "run `papers migrate` first, to turn it into a library")

    if name in ('pool', 'local'):
        return _set_pool_or_local(o, config, name)

    if o.unset:
        config.unset(name)
        if name == 'git' and not config.git:
            config.set('git-lfs', False)
    else:
        value = _parse_setting(name, o.values)
        if name in ('bibtex', 'filesdir'):
            if not os.path.exists(value):
                logger.warning(f"{value} does not exist")
            value = os.path.abspath(value)
        config.set(name, value)
        if name == 'git-lfs' and value:
            config.set('git', True)
        if name == 'git' and not value and config.gitlfs:
            config.set('git-lfs', False)

    if papers.config.DRYRUN:
        print(f"DRYRUN: {name} = {format_value(config.get(name))} not saved to {config.file}")
        return
    config.save()

    if name in ('git', 'git-lfs') and config.git:
        init_backup(config)
        if config.bibtex and os.path.exists(config.bibtex):
            snapshot_backup(config)
    if name == 'paths' and config.bibtex and os.path.exists(config.bibtex):
        convert_file_links(config)


# papers config local / pool: the files follow
# ============================================

def _confirm(o, lines, what, details=()):
    """print what a change does to the files, and ask to continue: -y
    answers yes, --dry-run stops here (and lists `details`, each file), and
    without a terminal it is an error"""
    print('\n'.join(lines))
    if papers.config.DRYRUN:
        if details:
            print('\n'.join(details))
        print('DRYRUN: nothing was changed')
        return False
    if o.yes:
        return True
    if not stdin_is_terminal():
        raise PapersExit(f'{what}: confirm in a terminal, or pass -y to proceed (nothing was changed)')
    if details:
        print(f'(`papers config {what} --dry-run` lists each file)')
    if input('Continue? [y/N] ').strip().lower() in ('y', 'yes'):
        return True
    print('nothing was changed')
    return False


def _show(path):
    "a path in the plan of a change: relative to the current directory if under it, else with ~"
    if is_inside(path, os.getcwd()):
        return os.path.relpath(path)
    return short_home(path)


def _files(n):
    return f'{n} file{"s" if n != 1 else ""}'


def _local_lines(plan, config):
    "the summary and the details (each file) of `papers config local true`"
    n = sum(len(files) for _, files in plan)
    summary = [f'copy {_files(n)} of the pool into {_show(config.filesdir)} (hard links when possible); '
               'the library will link to the copies, and the pool keeps its files.']
    details = [f'  {e.key}: {_show(f)}' for e, files in plan for f in files]
    return summary, details


def _relink_lines(plan, config, pool_label):
    "the summary and the details (each file) of linking the library to the files of a pool"
    n = sum(len(actions) for _, actions in plan)
    own = config.filesdir
    deleted = [f for _, actions in plan for f, _ in actions if own and is_inside(f, own)]
    summary = [f'link to the copies in {pool_label} for {_files(n)} (same content)'
               + (f'; the library\'s copies in {_show(own)} ({_files(len(deleted))}) are deleted' if deleted else '')]
    details = [f'  {e.key}: {_show(f)} -> {_show(target)}' + (' (deleted)' if own and is_inside(f, own) else '')
               for e, actions in plan for f, target in actions]
    return summary, details


MAX_KEYS = 10


def _missing_error(what, missing, pool_label, commands):
    """the error of `config local false` or `config pool PATH` when entries
    link to PDFs that the pool entry does not have"""
    keys = [e.key for e in missing]
    shown = ', '.join(keys[:MAX_KEYS]) + (f' and {len(keys) - MAX_KEYS} more' if len(keys) > MAX_KEYS else '')
    n = len(keys)
    lines = [f'{what}: {n} entr{"ies link" if n != 1 else "y links"} to PDFs that {pool_label} does not have '
             f'(nothing was changed): {shown}']
    lines += commands
    lines.append(f'Then run `papers config {what}` again.')
    return PapersExit('\n'.join(lines))


def _save_setting(config, changes):
    for name, value in changes.items():
        if value is None:
            config.unset(name)
        else:
            config.set(name, value)
    config.save()
    print(', '.join(f'{name} = {format_value(config.get(name))}' for name in changes)
          + f' (in {short_home(config.file)})')


def _set_pool_or_local(o, config, name):
    """`papers config local true|false`, `papers config pool PATH|none` and
    `--unset pool`. Local true (or pool none) copies the pool files that the
    library links to into its files directory. Local false, or a new pool
    of a library that is not local, needs each PDF of the library in the
    pool entry of the same paper (same file or same content): the library
    then links to the pool's copies, and its own copies are deleted;
    otherwise it is an error that names the entries. The changes of the
    files are confirmed first."""
    if name == 'local' and o.unset:
        raise PapersExit('local is set in each library: `papers config local true` or `false`')
    new = copy.copy(config)
    new.explicit = set(config.explicit)
    if name == 'local':
        changes = {'local': _parse_setting('local', o.values)}
    elif o.unset:
        changes = {'pool': None}
    else:
        value = _parse_setting('pool', o.values)
        changes = {'pool': pool_setting(value, str(config.configdir), base=os.getcwd())}
    for key, value in changes.items():
        new.unset(key) if value is None else new.set(key, value)
    if new.local is False and not new.has_pool():
        if name == 'local':
            raise PapersExit('local false needs a pool, and the library has none (pool none): '
                             'set one with `papers config pool PATH` first')
        changes['local'] = True  # pool none: the files are the library's own
        new.set('local', True)

    def done():
        if papers.config.DRYRUN:
            print('DRYRUN: ' + ', '.join(f'{k} = {format_value(new.get(k))}' for k in changes)
                  + f' not saved to {short_home(config.file)}')
            return
        _save_setting(config, changes)

    old_pools = Pools(config)
    old_pool = old_pools.pool(quiet=True) if not config.local else None
    old_dirs = [old_pool.filesdir] if old_pool is not None and old_pool.filesdir else []
    to_local = not config.local and changes.get('local', new.local)
    to_pool = (not new.local) and (config.local or old_pool is None
                                   or os.path.realpath(old_pool.path) != os.path.realpath(new.pool_path()))
    if not to_local and not to_pool:
        return done()

    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)
    exchange = Exchange(config, biblio, old_pools)
    hint = None
    if to_local:
        if config.filesdir is None:
            raise PapersExit('the library has no files directory: set it with `papers config filesdir DIR` first')
        plan = exchange.plan_to_local(dirs=old_dirs)
        intro = [] if name == 'local' else ['pool none: the library cannot link to the files of a pool, '
                                            'so it becomes local (local true)']
        summary, details = _local_lines(plan, config) if plan else ([], [])
        if plan and not _confirm(o, intro + summary, f'{name} {format_value(changes[name])}', details):
            return
        if not plan and intro:
            print('\n'.join(intro))
        if papers.config.DRYRUN:
            return done()
        exchange.to_local(plan, old_dirs)
        delete = []
    else:
        # the library links to the files of the pool: each PDF must be in the pool already
        new_pools = Pools(new)
        pool = new_pools.pool(quiet=True)
        what = f'{name} {format_value(changes.get(name, new.get(name)))}'
        pool_label = f'the pool {new.pool_label()}'
        plan, missing = exchange.plan_relink(pool)
        if missing:
            selection = ' '.join(e.key for e in missing) if len(missing) <= MAX_KEYS else '--all'
            if config.local:
                commands = [f'Share them with the pool first: `papers push {selection}`']
            else:
                new_arg = o.values[0] if o.values else _show(new.pool_path())
                commands = [f'Copy them to the new pool first: `papers push --pool {new_arg} {selection}` '
                            '(a one-time push, which copies the PDFs)']
            raise _missing_error(what, missing, pool_label, commands)
        summary, details = _relink_lines(plan, config, pool_label) if plan else ([], [])
        if plan and not _confirm(o, summary, what, details):
            return
        if papers.config.DRYRUN:
            return done()
        # the broken links are not changed: file check --fix relinks those that the pool has
        broken = sum(len(broken_links(biblio, e)) for e in biblio.entries)
        hint = (f'{broken} link{"s were" if broken > 1 else " was"} already broken: '
                '`papers file check --fix` relinks those that the pool has') if broken else None
        if not plan:
            done()
            if hint:
                print(hint)
            return
        delete = exchange.relink(plan, pool, keep_dirs=old_dirs + [pool.filesdir])
        exchange.pools = new_pools
    save_exchange(exchange)
    _print_biblio_diff(biblio_init, biblio, biblio.entries)
    done()
    delete_files(delete)
    if hint:
        print(hint)


def machine_configcmd(parser, o, machine, name):
    if not name:
        print(f"# {machine.file}" + ("" if machine.exists() else " (does not exist)"))
        if machine.get('pool') is None:
            print(f"pool = {machine.pool}  (default)")
        for setting in SETTINGS:
            value = machine.get(setting)
            if value is not None:
                print(f"{setting} = {format_value(value)}")
        return

    if not o.unset and not o.values:
        value = machine.get(name)
        if value is None and name == 'pool':
            value = machine.pool
        if value is not None:
            print(format_value(value))
        return

    if o.unset:
        value = None
    else:
        value = _parse_setting(name, o.values)
        if name == 'pool' and value != NO_POOL:
            value = short_home(os.path.abspath(os.path.expanduser(value)))
    machine.set(name, value)
    if papers.config.DRYRUN:
        print(f"DRYRUN: {machine.file} not saved")
        return
    machine.save()


def migratecmd(parser, o, config):
    """one-time upgrades from papers v2"""
    if o.folders:
        return migrate_folders(check_install(parser, o, config))
    if not migrate_v2_global(config.machine, relative=o.relative, dryrun=papers.config.DRYRUN):
        print("nothing to migrate: no global configuration of papers v2 was found")


def statuscmd(parser, o, config):
    print(config.status(check_files=not o.no_check_files, verbose=o.verbose))
    if config.file is None:
        pool = config.machine.pool_path()
        print(f"* global pool:        {short_home(pool) + ' (not a library)' if pool else 'none'}")
        print(init_hint(config))
