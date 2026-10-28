"""Opening and saving a library: find its configuration (from the current
directory, or for a bibtex given on the command line), load its bibtex, and
save it, with its state in the history (see papers.backup).
"""
import copy
import os
import shutil

import papers.checksums
import papers.config
from papers import journal, lock, logger
import papers.backup
from papers.bib import Biblio, BibtexChanged
from papers.entries import get_entry_val
from papers.config import (Config, MachineConfig, CONFIG_FILE, CONFIG_FILE_LEGACY, CONFIG_FILE_LEGACY_XDG,
                           find_library_config, library_config_file)


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


def find_config(start_dir='.', machine=None):
    """The configuration that commands act on, with `origin` telling where it
    was found:
    - 'library': a library configuration in start_dir or above;
    - 'v2-global': the global configuration of papers v2, until `papers migrate`;
    - 'default': the default library of the global configuration;
    - None: no library (a Config with the inherited settings only).
    """
    machine = machine or MachineConfig.load()
    configfile = find_library_config(start_dir)
    origin = 'library'
    if configfile is None and os.path.exists(CONFIG_FILE):
        configfile, origin = CONFIG_FILE, 'v2-global'
    if configfile is None:
        default = machine.default_path()
        if default and os.path.isdir(default):
            configfile, origin = library_config_file(default), 'default'
    if configfile is None:
        return Config(machine=machine)
    config = Config.load(configfile, machine=machine,
                         is_library=False if origin == 'v2-global' else None)
    config.origin = origin
    return config


def config_for_bibtex(bibtex, config):
    """The configuration to use when --bibtex is passed on the command line.

    If it is another library than the configured one, the local configuration
    of that library (searched from the bibtex's directory upwards, as for the
    current directory) applies: its files directory, history and formats.
    Without one, the current configuration applies to the bibtex, except that
    it is never written back to disk and the history is that of the bibtex
    (named by its path).
    """
    if config.bibtex and os.path.realpath(bibtex) == os.path.realpath(config.bibtex):
        return config

    configfile = find_library_config(os.path.dirname(os.path.abspath(bibtex)))
    if configfile is not None:
        other = Config.load(configfile, machine=config.machine)
        if other.bibtex and os.path.realpath(other.bibtex) == os.path.realpath(bibtex):
            logger.debug(f'configuration of {bibtex}: {configfile}')
            other.origin = 'library'
            return other

    logger.debug(f'{bibtex} has no configuration of its own: use {config.file} without saving it')
    config = copy.copy(config)
    config.file = None
    config.id = None
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
        if biblio.relative_to != relative_to and biblio.update_file_path(relative_to):
            biblio.load_changes = True
    else:
        biblio = Biblio.newbib(config.bibtex, config.filesdir, relative_to=relative_to, nameformat=config.nameformat, keyformat=config.keyformat)
    if config.shallow:
        _repair_pool_links(biblio, config)
        if getattr(biblio, 'repaired_links', None):
            biblio.load_changes = True
    # for the auto-push (papers.cli.common.save_entries), the report of the
    # changes, and savebib, which does not write a library that did not change
    biblio.mark_loaded()
    return biblio


_REPAIRING = set()


def _repair_pool_links(biblio, config):
    """a shallow library links to the files of its pool: links broken because
    the pool renamed a file are repaired by looking the entry up in the pools
    (saved on the next write)"""
    from papers.pools import Exchange  # papers.pools imports this module
    key = os.path.realpath(config.bibtex)
    if key in _REPAIRING:  # two shallow libraries that are each other's pool
        return
    _REPAIRING.add(key)
    try:
        biblio.repaired_links = Exchange(config, biblio).repair_links()
        for e, found in biblio.repaired_links:
            new = [f for files in found.values() for f in files]
            logger.info(f'{get_entry_val(e, "ID", "")}: broken link to a pool file repaired: {new}')
    except Exception as error:
        logger.warning(f'could not repair the links to the pool files: {error}')
    finally:
        _REPAIRING.discard(key)


def savebib(biblio, config, other_changes=False):
    """
    Given a Biblio object and its configuration, save them to disk, and
    record the state in the history (see papers.backup).

    A library loaded by get_biblio that did not change since (see
    Biblio.unchanged) is not written, and has no new state, unless
    `other_changes` (e.g. the origin records of the library changed,
    which the history has too).
    """
    if papers.config.DRYRUN:
        print(f'DRYRUN: {config.bibtex} not saved')
        return
    if isinstance(biblio, Biblio) and not other_changes and biblio.unchanged():
        logger.info(f'{config.bibtex}: nothing changed, not saved')
        return
    logger.info(f'Saving {config.bibtex}')
    # a library written by a command that did not lock it beforehand (e.g. links repaired by papers list)
    lock.acquire(config)
    lock.check(config)
    if isinstance(biblio, Biblio):
        follow_renamed_keys(biblio, config)
    # the bibtex as it was before the command, if papers did not write it (see papers.backup.sync_head)
    try:
        papers.backup.sync_head(config)
    except Exception as error:
        logger.error(f'the history of the library could not record its state before the command: {error}')
    if biblio is not None:
        if isinstance(biblio, Biblio):
            papers.checksums.update(config, biblio)
        try:
            biblio.save(config.bibtex)
        except BibtexChanged:
            # the bibtex does not record what the command did to the files: put them back
            lines = journal.rollback(config.bibtex, papers.backup.Deleted(config).store.file_object)
            if lines:
                print('the files of the command are put back:')
                print('\n'.join(lines))
            raise
    # the history comes last: a failure must not undo the work done above
    try:
        papers.backup.record(config)
    except Exception as error:
        logger.error(f'the bibliography was saved, but its history failed: {error}')


def follow_renamed_keys(biblio, config):
    """what names the entries whose key changed in the command (see
    Biblio.renamed_keys): the crossref fields of the other entries, and the
    records of the exchanges with pools (.papers/origin/)"""
    renamed = biblio.renamed_keys()
    if not renamed:
        return
    from papers.pools import Origin  # papers.pools imports this module
    origin = Origin.for_bibtex(config.bibtex)
    for old, new in renamed:
        biblio.rekey_references(old, new)
        origin.rekey(old, new)
    origin.save()


def finish_journal(config=None):
    """at the end of a command (also one stopped by an error or Ctrl-C):
    the file operations done after the last state of its library (e.g. the
    files deleted by papers rm, once the library is saved) join that state;
    those of a command that did not save the library (e.g. papers file
    clean) make a state of their own, so that undo brings the files back
    (see papers.journal)"""
    ops, where = journal.leftover()
    if not ops or papers.config.DRYRUN:
        return
    if where is not None:
        saved, n = where
        papers.backup.add_operations(saved, n, ops)
    elif config is not None and journal.is_owner(config.bibtex):
        try:
            papers.backup.sync_head(config)
            papers.backup.record(config, ops=ops)
        except Exception as error:
            logger.error(f'{len(ops)} file operation(s) not recorded for undo: {error}')


def convert_file_links(config):
    "write the file links of the bibtex as the `paths` setting says (relative or absolute)"
    biblio = get_biblio(config)  # converts to absolute links if needed
    biblio.update_file_path(biblio.relative_to)  # converts to relative links if needed
    savebib(biblio, config)
