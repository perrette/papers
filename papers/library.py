"""Opening and saving a library: find its configuration (from the current
directory, or for a bibtex given on the command line), load its bibtex, and
save it with its git backup.
"""
import copy
import os
import shutil
from pathlib import Path

import papers.config
from papers import logger
from papers.backup import backup_bib, silent_backup_bib, resolve_gitdir
from papers.bib import Biblio
from papers.entries import get_entry_val
from papers.config import (Config, MachineConfig, CONFIG_FILE, CONFIG_FILE_LOCAL, LIBRARY_CONFIG_FILES,
                           CONFIG_FILE_LEGACY, CONFIG_FILE_LEGACY_XDG)
from papers.utils import search_config


def check_legacy_global_config():
    """move the global config file from locations used by previous versions
    (~/.local/share/papers/config.json on every platform, and the XDG-style
    location on macOS/Windows where platformdirs now differs)"""
    for legacy in [CONFIG_FILE_LEGACY, CONFIG_FILE_LEGACY_XDG]:
        if os.path.realpath(legacy) == os.path.realpath(CONFIG_FILE) or not os.path.exists(legacy):
            continue
        if not os.path.exists(CONFIG_FILE):
            logger.warning(f"Move legacy config file {legacy} to {CONFIG_FILE}")
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            shutil.move(legacy, CONFIG_FILE)
        else:
            logger.warning(f"Legacy config file found: {legacy}. Delete to remove this warning:  rm -f '{legacy}'")


def check_legacy_config(configfile):
    " move config file from ~/.local/.share/papers/ to ~/.config/papersconfig.json and .papers/config.json to .papersconfig.json"
    if os.path.exists(configfile):
        p = Path(configfile)
        if configfile == CONFIG_FILE_LEGACY:
            shutil.move(configfile, CONFIG_FILE)
            configfile = CONFIG_FILE
        elif p.name == "config.json" and p.parent.name == ".papers":
            newname = str(p.parent.parent/CONFIG_FILE_LOCAL)
            shutil.move(configfile, newname)
            configfile = newname

    return configfile


def find_config(start_dir='.', machine=None):
    """The configuration that commands act on, with `origin` telling where it
    was found:
    - 'library': a library configuration in start_dir or above;
    - 'v2-global': the global configuration of papers v2, until `papers migrate`;
    - 'global-pool': the library of the global pool;
    - None: no library (a Config with the inherited settings only).
    """
    machine = machine or MachineConfig.load()
    configfile = search_config(LIBRARY_CONFIG_FILES, start_dir=start_dir, default=None)
    origin = 'library'
    if configfile is None and os.path.exists(CONFIG_FILE):
        configfile, origin = CONFIG_FILE, 'v2-global'
    if configfile is None:
        pool = machine.pool_path()
        if pool and os.path.exists(os.path.join(pool, CONFIG_FILE_LOCAL)):
            configfile, origin = os.path.join(pool, CONFIG_FILE_LOCAL), 'global-pool'
    if configfile is None:
        return Config(machine=machine)
    config = Config.load(check_legacy_config(configfile), machine=machine,
                         is_library=False if origin == 'v2-global' else None)
    config.origin = origin
    return config


def config_for_bibtex(bibtex, config):
    """The configuration to use when --bibtex is passed on the command line.

    If it is another library than the configured one, the local configuration
    of that library (searched from the bibtex's directory upwards, as for the
    current directory) applies: its files directory, git backup and formats.
    Without one, the current configuration applies to the bibtex, except that
    it is never written back to disk and the backup goes to a directory of
    the bibtex's own.
    """
    if config.bibtex and os.path.realpath(bibtex) == os.path.realpath(config.bibtex):
        return config

    configfile = search_config(LIBRARY_CONFIG_FILES,
                               start_dir=os.path.dirname(os.path.abspath(bibtex)), default=None)
    if configfile is not None:
        other = Config.load(check_legacy_config(configfile), machine=config.machine)
        if other.bibtex and os.path.realpath(other.bibtex) == os.path.realpath(bibtex):
            logger.info(f'configuration of {bibtex}: {configfile}')
            other.origin = 'library'
            return other

    logger.debug(f'{bibtex} has no configuration of its own: use {config.file} without saving it')
    config = copy.copy(config)
    config.file = None
    if config.git:
        config.gitdir = resolve_gitdir(bibtex)
    return config


def get_biblio(config):
    """the bibliography of a library (its bibtex is created if it does not
    exist), with the file links as the `paths` setting says; raise
    ValueError if the configuration has no bibtex"""
    if config.bibtex is None:
        raise ValueError('bibtex is not initialized')
    relative_to = os.path.sep if config.absolute_paths else os.path.dirname(config.bibtex)
    if os.path.exists(config.bibtex):
        biblio = Biblio.load(config.bibtex, config.filesdir, nameformat=config.nameformat, keyformat=config.keyformat)
        if biblio.relative_to != relative_to:
            biblio.update_file_path(relative_to)
    else:
        biblio = Biblio.newbib(config.bibtex, config.filesdir, relative_to=relative_to, nameformat=config.nameformat, keyformat=config.keyformat)
    if config.file and not config.local:
        _repair_pool_links(biblio, config)
    return biblio


_REPAIRING = set()


def _repair_pool_links(biblio, config):
    """a non-local library links to the files of its pool: links broken because
    the pool renamed a file are repaired by looking the entry up in the pools
    (saved on the next write)"""
    from papers.pools import Exchange  # papers.pools imports this module
    key = os.path.realpath(config.bibtex)
    if key in _REPAIRING:  # two non-local libraries that are each other's pool
        return
    _REPAIRING.add(key)
    try:
        biblio.repaired_links = Exchange(config, biblio).repair_links()
        for e, old, new in biblio.repaired_links:
            logger.info(f'{get_entry_val(e, "ID", "")}: broken link to a pool file repaired: {new}')
    except Exception as error:
        logger.warning(f'could not repair the links to the pool files: {error}')
    finally:
        _REPAIRING.discard(key)


def savebib(biblio, config):
    """
    Given a Biblio object and its configuration, save them to disk.  If you're using the git bib tracker, will trigger a git commit there.
    """
    if papers.config.DRYRUN:
        logger.info(f'DRYRUN: NOT saving {config.bibtex}')
        return
    logger.info(f'Saving {config.bibtex}')
    if biblio is not None:
        biblio.save(config.bibtex)
    if config.git:
        # the backup comes last: a failure must not undo the work done above
        try:
            silent_backup_bib(biblio, config)
        except Exception as error:
            logger.error(f'the bibliography was saved, but its git backup failed: {error}')
    else:
        logger.debug('do not backup bib: git is off')


def convert_file_links(config):
    "write the file links of the bibtex as the `paths` setting says (relative or absolute)"
    biblio = get_biblio(config)  # converts to absolute links if needed
    biblio.update_file_path(biblio.relative_to)  # converts to relative links if needed
    savebib(biblio, config)


def snapshot_backup(config):
    "commit the current bibtex to the backup directory"
    backup_bib(get_biblio(config), config)
