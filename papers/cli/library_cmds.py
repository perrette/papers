"""papers status, init, install, uninstall, config, migrate"""
import copy
import os
from pathlib import Path
import shutil

import papers.config
from papers import logger
from papers.backup import init_backup
from papers.config import (CONFIG_FILE, CONFIG_FILE_LOCAL, Config, LIBRARY_CONFIG_FILES, LIBRARY_ONLY,
                           SETTINGS, format_value, parse_value, short_home)
from papers.files import delete_files
from papers.install import DefaultAsker, InputAsker, RESET_WORDS, _ask_path, apply_install, resolve_install
from papers.library import (check_legacy_config, convert_file_links, find_config, get_biblio, savebib,
                            snapshot_backup)
from papers.migrate import migrate_folders, migrate_v2_global
from papers.pools import Exchange
from papers.utils import PapersExit, search_config, set_directory
from papers.cli.common import format_options, check_pools, init_hint, check_install, _print_biblio_diff


def _install(o, config, asker, target=None):
    "resolve and apply an install of a library, with the format options of the command line"
    plan = resolve_install(config, o, asker=asker, target=target)
    for name, value in format_options(o).items():
        plan.config.set(name, value)
    if getattr(o, 'light', False):
        plan.config.light = True  # a new library: no files to convert
    check_pools(plan.config, plan.config.pools)
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
    config = _install(o, Config(machine=config.machine), DefaultAsker(), target=CONFIG_FILE_LOCAL)
    print(config.status(check_files=not o.no_check_files, verbose=True))


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
                   "default pool, used outside of any library. Use `papers init DIR` (DIR: the library) and "
                   "`papers pool add default DIR`. This command does both: the library configuration is "
                   "written next to the bibtex, and its directory becomes the `default` pool.")
    machine = config.machine
    bibtex = o.bibtex
    if not bibtex:
        default = config.bibtex if config.origin in ('v2-global', 'default-pool') and config.bibtex else 'papers.bib'
        bibtex = _ask_path(asker, "Bibtex file name", default)
    if not bibtex:
        raise PapersExit("install --global needs a bibtex file")
    bibtex = os.path.abspath(bibtex)

    # the global configuration of v2 becomes a library and the default pool,
    # as with `papers migrate` (the library below then updates or replaces it)
    migrate_v2_global(machine, dryrun=papers.config.DRYRUN)

    libdir = os.path.dirname(bibtex)
    target = os.path.join(libdir, CONFIG_FILE_LOCAL)
    existing = Config.load(target, machine=machine) if os.path.exists(target) else Config(machine=machine)

    o.bibtex = bibtex
    if o.filesdir and o.filesdir.lower() not in RESET_WORDS:
        o.filesdir = os.path.abspath(o.filesdir)
    os.makedirs(libdir, exist_ok=True)
    with set_directory(libdir):
        config = _install(o, existing, asker, target=target)

    if not papers.config.DRYRUN:
        machine.set_pool('default', short_home(libdir))
        machine.save()
    print(f"registered {libdir} as the default pool in {machine.file}")
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
    if config.origin == 'default-pool':
        raise PapersExit(f"no library in this directory or above. The default pool ({config.configdir}) "
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
    if name == 'light':
        raise PapersExit("light is not changed with `papers config`, because it changes the file "
                         "links and the files too: use `papers migrate --light` or `papers migrate --full`")
    if is_global and name.startswith('pools.') and len(name) > len('pools.'):
        return
    if name not in SETTINGS:
        raise PapersExit(f"unknown setting: {name}. Settings: {', '.join(SETTINGS)}"
                         + (", pools.NAME (with --global)" if not is_global else ", pools.NAME"))
    if is_global and name in LIBRARY_ONLY:
        raise PapersExit(f"{name} is a setting of a library: the global configuration holds the default "
                         "settings of the libraries, and defines no library (the global library of papers v2 "
                         "is now the default pool, see `papers pool list`)"
                         + ("; it names the pools with pools.NAME PATH" if name == 'pools' else ''))


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
        raise PapersExit(f"no library found in this directory or above, and the default pool is not a library. "
                         f"{init_hint(config)}, or use `papers config --global`")

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
        if name == 'pools':
            check_pools(config, value)
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


def machine_configcmd(parser, o, machine, name):
    if not name:
        print(f"# {machine.file}" + ("" if machine.exists() else " (does not exist)"))
        for pool, path in machine.pools.items():
            source = "global" if pool in machine.data.get("pools", {}) else "default"
            print(f"pools.{pool} = {path}  ({source})")
        for setting in SETTINGS:
            value = machine.get(setting)
            if value is not None:
                print(f"{setting} = {format_value(value)}")
        return

    is_pool = name.startswith('pools.')
    if not o.unset and not o.values:
        value = machine.pools.get(name[len('pools.'):]) if is_pool else machine.get(name)
        if value is not None:
            print(format_value(value))
        return

    if o.unset:
        value = None
    elif is_pool:
        if len(o.values) != 1:
            raise PapersExit(f"{name} takes one path")
        value = o.values[0]
        if not value.startswith('~'):
            value = short_home(value)
    else:
        value = _parse_setting(name, o.values)

    if is_pool:
        machine.set_pool(name[len('pools.'):], value)
    else:
        machine.set(name, value)
    if papers.config.DRYRUN:
        print(f"DRYRUN: {machine.file} not saved")
        return
    machine.save()


def migratecmd(parser, o, config):
    """one-time upgrades from papers v2"""
    if o.light and o.full:
        parser.error('--light and --full are mutually exclusive')
    if o.light or o.full:
        config = check_install(parser, o, config)
        if config.file is None:
            raise PapersExit('migrate --light / --full: the library has no configuration file')
        return migrate_light(config, light=o.light)
    if o.folders:
        return migrate_folders(check_install(parser, o, config))
    if not migrate_v2_global(config.machine, relative=o.relative, dryrun=papers.config.DRYRUN):
        print("nothing to migrate: no global configuration of papers v2 was found")


def migrate_light(config, light):
    """papers migrate --light: link to the files of the first pool and
    delete the library's copies; --full: copy the pool files linked into
    the library's files directory"""
    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)
    exchange = Exchange(config, biblio)
    if light:
        relinked, missing, delete, kept = exchange.to_light()
        for e in missing:
            print(f'{e.key}: some of its files are not in the pool: kept as they are')
        if missing:
            print(f'{len(missing)} entries have files that are not in the pool: run `papers push` first, '
                  'then `papers migrate --light` again')
        for f in kept:
            print(f'kept {f}: the entry links to the pool file now, but this file is outside the files directory')
    else:
        relinked = exchange.to_full()
        delete = []
    config.light = light
    if papers.config.DRYRUN:
        print(f'DRYRUN: light = {"true" if light else "false"} not saved to {config.file}')
    else:
        config.save()
    exchange.origin.save()
    savebib(biblio, config)
    _print_biblio_diff(biblio_init, biblio, relinked)
    delete_files(delete, dryrun=papers.config.DRYRUN)
    print(f'{len(relinked)} entries relinked; the library is {"light" if light else "full"}')


def statuscmd(parser, o, config):
    print(config.status(check_files=not o.no_check_files, verbose=o.verbose))
    if config.file is None:
        print(f"* default pool:       {config.machine.pool_path('default')} (not a library)")
        print(init_hint(config))
