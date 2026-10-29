"""papers status, init, install, uninstall, config, migrate"""
import copy
import json
import os
from pathlib import Path

import papers.config
from papers import logger
from papers.config import (CONFIG_FILE_LOCAL, Config, DEFAULT_LIBRARY, LIBRARY_ONLY, MACHINE_ONLY, NO_POOL,
                           REMOVED_SETTINGS, library_config_file,
                           SETTINGS, format_value, json_get, parse_value, pool_setting, short_home)
from papers.files import broken_links, delete_files, is_inside
from papers.install import RESET_WORDS, DefaultAsker, InputAsker, apply_install, resolve_install
from papers.library import convert_file_links, find_config, get_biblio
from papers.migrate import migrate_folders, migrate_library_config, migrate_v2_global
from papers.pools import Exchange, Pools, library_without_pool
from papers.utils import PapersExit, set_directory
from papers.cli.common import (format_options, check_install, _print_biblio_diff, no_library_message,
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


NO_DEFAULT = "no default library: `papers init PATH --global` or `papers config --global default PATH`"


def initcmd(parser, o, config):
    """create a library in the current directory, or in DIR (created if
    missing): self-contained, or shallow with --pool PATH (an existing
    library without pool) or --shallow (the default library); with
    --global, also registered as the default library. Nothing is created
    if a check fails."""
    machine = config.machine
    if o.is_global and o.dir is None:
        raise PapersExit('--global needs the directory of the library: `papers init PATH --global` '
                         '(`papers init . --global` for the current directory)')
    if o.shallow:
        if o.pool is not None:
            raise PapersExit('--shallow is --pool with the default library: give one of them')
        if machine.default is None:
            raise PapersExit(NO_DEFAULT)
        o.pool = machine.default_path()
    if o.is_global and o.pool not in (None, NO_POOL):
        raise PapersExit('--global: the default library has no pool (no --pool or --shallow)')
    libdir = os.path.abspath(o.dir or '.')
    # the paths of the command line are relative to the current directory, not to DIR
    for name in ('bibtex', 'filesdir'):
        value = getattr(o, name)
        if value and value.lower() not in RESET_WORDS:
            setattr(o, name, os.path.abspath(value))
    if o.pool not in (None, NO_POOL):
        given = machine.default if o.shallow else o.pool
        path = os.path.abspath(os.path.expanduser(o.pool))
        if os.path.realpath(path) == os.path.realpath(libdir):
            raise PapersExit(f'--pool {given}: this is the library itself (nothing was changed)')
        library_without_pool(path, machine, f'--pool {given}:')
        o.pool = pool_setting(o.pool, libdir, base=os.getcwd())  # as the pool setting writes it
    if o.dir is None:
        _initcmd(parser, o, config)
    else:
        created = _missing_dirs(libdir)
        os.makedirs(o.dir, exist_ok=True)
        try:
            with set_directory(o.dir):
                _initcmd(parser, o, find_config(machine=machine))
        except BaseException:
            # a check of _initcmd failed: remove the directories created above, if still empty
            for d in created:
                if os.path.isdir(d) and not os.listdir(d):
                    os.rmdir(d)
            raise
    if o.is_global:
        machine.set(DEFAULT_LIBRARY, short_home(libdir))
        machine.save()
        print(f'registered {short_home(libdir)} as the default library in {short_home(machine.file)}')


def _missing_dirs(path):
    "the directories that os.makedirs(path) would create, deepest first"
    missing = []
    while not os.path.exists(path):
        missing.append(path)
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return missing


def _initcmd(parser, o, config):
    existing = library_config_file('.')
    if existing:
        hint = (' (`papers config --global default PATH` registers an existing library as the default one)'
                if o.is_global else '')
        raise PapersExit(f"a library already exists here ({existing}): "
                         f"change its settings with `papers config`{hint}")
    if config.origin == 'library':
        logger.warning(f"the new library is inside the library of {config.file}")
    o.reset = False
    config = _install(o, Config(machine=config.machine), DefaultAsker(), target=CONFIG_FILE_LOCAL)
    print('\n'.join(init_summary(config)))


def init_summary(config):
    """what `papers init` prints: the library created, its bibtex, where its
    files go and its pool"""
    lines = [f'created the library {short_home(str(config.configdir))}',
             f'* bibtex:  {_show(config.bibtex) if config.bibtex else "none"}']
    if not config.has_pool():
        files = f'{_show(config.filesdir)} (the files directory of the library)' if config.filesdir \
            else 'linked where they are (no files directory)'
        lines.append(f'* files:   {files}')
    else:
        lines.extend(['* files:   in the pool (shallow library)',
                      f'* pool:    {config.pool_label()}'])
    return lines + ['`papers config` lists and sets the settings']


def installcmd(parser, o, config):
    """
    Given options and a config state, installs the expected config files.

    The decision logic lives in papers.install (resolve_install); this
    function only wires up prompting and applies the resulting plan.
    """
    if o.local is False:
        raise PapersExit(INSTALL_GLOBAL_REMOVED)
    if o.edit and o.reset:
        parser.error('--edit and --reset are mutually exclusive')
    if o.edit:
        # historical behavior: --edit means "apply my flags, ask nothing"
        o.yes = True
    asker = DefaultAsker() if o.yes else InputAsker()

    if o.local is True:
        logger.warning("--local is ignored: a library configuration is always in the library (see `papers init`)")

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


INSTALL_GLOBAL_REMOVED = ("`papers install --global` is no longer supported (nothing was changed): create the "
                          "default library with `papers init PATH --global` (e.g. `papers init "
                          "~/Documents/papers/default --global`), or register an existing library with "
                          "`papers config --global default PATH`")


def uninstallcmd(parser, o, config):
    if config.file is None:
        parser.error('no library configuration was found')
    logger.warning('`papers uninstall` is deprecated: `rm -r .papers` removes the configuration of the library, '
                   '`papers history --remove` its history')
    if o.recursive:
        logger.warning("uninstall --recursive is deprecated and ignored: there is no global configuration to "
                       "remove in v3, only the configuration of this library is removed")
    _uninstall(parser, o, config)
    print(config.status(verbose=True))


def _uninstall(parser, o, config):
    if config.origin == 'default':
        raise PapersExit(f"no library in this directory or above. The default library ({config.configdir}) "
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
    if o.remove_history:
        from papers.cli.backup_cmds import remove_history
        remove_history(config, yes=True)
    else:
        print("the history of the library remains: `papers history --remove` removes it")


def _check_setting_name(name, is_global):
    if name == DEFAULT_LIBRARY:
        if not is_global:
            raise PapersExit(f"{DEFAULT_LIBRARY} is a setting of the global configuration: "
                             f"`papers config --global {DEFAULT_LIBRARY} PATH|none`")
        return
    if name in REMOVED_SETTINGS:
        raise PapersExit(f"the {name} setting is no longer used: {REMOVED_SETTINGS[name]}")
    if name not in SETTINGS:
        raise PapersExit(f"unknown setting: {name}. Settings: {', '.join(SETTINGS)}"
                         + (f" (and with --global: {DEFAULT_LIBRARY})" if is_global else ""))
    if is_global and name == 'pool':
        raise PapersExit("the global configuration has no pool: `papers config pool PATH` sets the pool of a "
                         "library, and `papers config --global default PATH` the default library "
                         "(`papers init --shallow` uses it as pool)")
    if not is_global and name in MACHINE_ONLY:
        raise PapersExit(f"{name} is a setting of the machine, not of a library (a library received from "
                         f"someone cannot set it): `papers config --global {name} VALUE`")
    if is_global and name in LIBRARY_ONLY:
        raise PapersExit(f"{name} is a setting of a library: the global configuration holds the default library "
                         "and the default settings of the libraries (the global library of papers v2 is now the "
                         "default library, see `papers config --global default`)")


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

    if o.prune:
        if name:
            parser.error('--prune takes no setting: papers config --prune')
        return _prune(config)

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

    if name == 'pool':
        return _set_pool(o, config)

    if o.unset:
        config.unset(name)
    else:
        value = _parse_setting(name, o.values)
        if name in ('bibtex', 'filesdir'):
            if not os.path.exists(value):
                logger.warning(f"{value} does not exist")
            value = os.path.abspath(value)
        config.set(name, value)

    if papers.config.DRYRUN:
        print(f"DRYRUN: {name} = {format_value(config.get(name))} not saved to {config.file}")
        return
    config.save()

    if name == 'paths' and config.bibtex and os.path.exists(config.bibtex):
        convert_file_links(config)
    if name == 'checksums':
        print('the files get a checksum when a command moves, copies, adds or links them: '
              '`papers file checksum` writes those of all the files' if config.checksums else
              'the commands write no checksum (undo finds the files through the journal of the commands)')


# papers config pool: the files follow
# ====================================

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


def _own_files_lines(plan, config):
    "the summary and the details (each file) of `papers config pool none` in a shallow library"
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
    """the error of `config pool PATH` when entries link to PDFs that the
    pool entry does not have"""
    keys = [e.key for e in missing]
    shown = ', '.join(keys[:MAX_KEYS]) + (f' and {len(keys) - MAX_KEYS} more' if len(keys) > MAX_KEYS else '')
    n = len(keys)
    lines = [f'{what}: {n} entr{"ies link" if n != 1 else "y links"} to PDFs that {pool_label} does not have '
             f'(nothing was changed): {shown}']
    lines += commands
    lines.append(f'Then run `papers config {what}` again.')
    return PapersExit('\n'.join(lines))


def _prune(config):
    "`papers config --prune`: save the library configuration without the settings equal to their inherited value"
    if config.origin == 'v2-global':
        raise PapersExit(f"{config.file} is the global configuration of papers v2: run `papers migrate` first")
    before = json.load(open(config.file))
    removed = [name for name in SETTINGS if name not in ('bibtex', 'filesdir', 'pool')
               and json_get(before, name) is not None and config.get(name) == config.inherited(name)]
    for name in removed:
        config.unset(name)
    # the settings of papers before the history (git, git-lfs, trash-days...), no longer used
    removed += [name for name in ('git', 'gitlfs', 'backup_files', 'gitdir', 'trash-days', 'trash-size')
                if name in before]
    if not removed:
        print(f'nothing to remove from {short_home(config.file)}')
        return
    if papers.config.DRYRUN:
        print(f'DRYRUN: {", ".join(removed)} not removed from {short_home(config.file)}')
        return
    config.save()
    print(f'removed from {short_home(config.file)} (equal to the global or default value): {", ".join(removed)}')


def _save_setting(config, changes):
    for name, value in changes.items():
        if value is None:
            config.unset(name)
        else:
            config.set(name, value)
    config.save()
    print(', '.join(f'{name} = {format_value(config.get(name))}' for name in changes)
          + f' (in {short_home(config.file)})')


def _set_pool(o, config):
    """`papers config pool PATH|none` and `--unset pool`. In a shallow
    library, pool none (the library becomes self-contained) copies the pool
    files that it links to into its files directory. A pool PATH (an
    existing library without pool) needs each PDF of the library in the
    pool entry of the same paper (same file or same content): the library
    then links to the pool's copies, and its own copies are deleted;
    otherwise it is an error that names the entries. The changes of the
    files are confirmed first."""
    name = 'pool'
    was_shallow = config.shallow
    new = copy.copy(config)
    new.explicit = set(config.explicit)
    if o.unset:
        changes = {'pool': None}
    else:
        value = _parse_setting('pool', o.values)
        changes = {'pool': pool_setting(value, str(config.configdir), base=os.getcwd())}
    for key, value in changes.items():
        new.unset(key) if value is None else new.set(key, value)
    if new.is_pool_library():
        raise PapersExit(f'pool {o.values[0]}: this is the library itself (nothing was changed)')
    if new.has_pool():
        library_without_pool(new.pool_path(), config.machine, f'pool {o.values[0]}:')

    def done():
        if papers.config.DRYRUN:
            print('DRYRUN: ' + ', '.join(f'{k} = {format_value(new.get(k))}' for k in changes)
                  + f' not saved to {short_home(config.file)}')
            return
        _save_setting(config, changes)
        if to_pool and not was_shallow:
            print('the library is now shallow: it links to the PDFs of the pool entries, and `papers add` '
                  'adds its new entries to the pool')
        elif to_self:
            print('the library is now self-contained: its own entries and files')

    old_pools = Pools(config)
    old_pool = old_pools.pool(quiet=True) if config.shallow else None
    old_dirs = [old_pool.filesdir] if old_pool is not None and old_pool.filesdir else []
    to_self = config.shallow and not new.has_pool()
    to_pool = new.has_pool() and (not config.shallow or os.path.realpath(config.pool_path())
                                  != os.path.realpath(new.pool_path()))
    if not to_self and not to_pool:
        return done()

    biblio = get_biblio(config)
    exchange = Exchange(config, biblio, old_pools)
    hint = None
    if to_self:
        if config.filesdir is None:
            raise PapersExit('the library has no files directory: set it with `papers config filesdir DIR` first')
        plan = exchange.plan_own_files(dirs=old_dirs)
        intro = ['pool none: the library becomes self-contained, with its own files']
        summary, details = _own_files_lines(plan, config) if plan else ([], [])
        if plan and not _confirm(o, intro + summary, f'{name} {NO_POOL}', details):
            return
        if not plan and intro:
            print('\n'.join(intro))
        if papers.config.DRYRUN:
            return done()
        exchange.own_files(plan, old_dirs)
        delete = []
    else:
        # the library links to the files of the pool: each PDF must be in the pool already
        new_pools = Pools(new)
        new_pools.set_known_ids(set(exchange.origin.entries) | set(exchange.origin.pulls))
        pool = new_pools.pool(quiet=True)
        what = f'{name} {o.values[0]}'
        pool_label = f'the pool {new.pool_label()}'
        plan, missing = exchange.plan_relink(pool)
        if missing:
            selection = ' '.join(e.key for e in missing) if len(missing) <= MAX_KEYS else '--all'
            commands = [f'Copy them to the pool first: `papers push --pool {o.values[0]} {selection}`']
            raise _missing_error(what, missing, pool_label, commands)
        summary, details = _relink_lines(plan, config, pool_label) if plan else ([], [])
        if plan and not _confirm(o, summary, what, details):
            return
        if papers.config.DRYRUN:
            return done()
        # the broken links are not changed: file fix relinks those that the pool has
        broken = sum(len(broken_links(biblio, e)) for e in biblio.entries)
        hint = (f'{broken} link{"s were" if broken > 1 else " was"} already broken: '
                '`papers file fix` relinks those that the pool has') if broken else None
        if not plan:
            done()
            if hint:
                print(hint)
            return
        delete = exchange.relink(plan, pool, keep_dirs=old_dirs + [pool.filesdir])
        exchange.pools = new_pools
    save_exchange(exchange)
    _print_biblio_diff(biblio, biblio.entries)
    done()
    delete_files(delete, same=exchange.same)
    if hint:
        print(hint)


def machine_configcmd(parser, o, machine, name):
    if not name:
        print(f"# {machine.file}" + ("" if machine.exists() else " (does not exist)"))
        for setting in [DEFAULT_LIBRARY] + list(SETTINGS):
            value = machine.get(setting)
            if value is not None:
                print(f"{setting} = {format_value(value)}")
        return

    if not o.unset and not o.values:
        value = machine.get(name)
        if value is not None:
            print(format_value(value))
        return

    if o.unset:
        value = None
    elif name == DEFAULT_LIBRARY:
        if len(o.values) != 1:
            raise PapersExit(f'{DEFAULT_LIBRARY} takes one value: PATH or none')
        value = o.values[0]
        if value == NO_POOL:
            value = None
        else:
            path = os.path.abspath(os.path.expanduser(value))
            library_without_pool(path, machine, 'the default library')
            value = short_home(path)
    else:
        value = _parse_setting(name, o.values)
        if name == 'history-dir':
            value = short_home(os.path.abspath(os.path.expanduser(value)))  # relative to the current directory
    machine.set(name, value)
    if papers.config.DRYRUN:
        print(f"DRYRUN: {machine.file} not saved")
        return
    machine.save()


def migratecmd(parser, o, config):
    """one-time upgrades from papers v2"""
    if o.folders:
        return migrate_folders(check_install(parser, o, config))
    dryrun = papers.config.DRYRUN
    moved = config.origin in ('library', 'default') and migrate_library_config(config, dryrun=dryrun)
    if not migrate_v2_global(config.machine, relative=o.relative, dryrun=dryrun) and not moved:
        print("nothing to migrate: no global configuration of papers v2 was found"
              + (f", and the library configuration is already {CONFIG_FILE_LOCAL}"
                 if config.origin in ('library', 'default') else ''))


def statuscmd(parser, o, config):
    if o.bibtex is not None or o.filesdir is not None:
        config = check_install(parser, o, config)  # the library of --bibtex FILE, as for the other commands
    print(config.status(check_files=not o.no_check_files, verbose=o.verbose))
    if config.file is None:
        default = config.machine.default_path()
        print(f"* default library: {short_home(default) + ' (not a library)' if default else 'none'}")
