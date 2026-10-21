"""That is the script called by the papers cli command
"""
import os
import copy
import sys
from pathlib import Path
import logging
import argparse
import subprocess as sp
import shutil
import itertools
import fnmatch   # unix-like match

import papers
from papers import logger
from papers.extract import extract_pdf_doi, isvaliddoi, extract_pdf_metadata, prefetch_pdf_metadata
from papers.extract import fetch_bibtex_by_doi, fetch_bibtex_by_fulltext_crossref, fetch_bibtex_by_fulltext_scholar
from papers.encoding import parse_file, format_file, family_names, format_entries, standard_name, format_entry, parse_keywords, format_key
from papers.config import (bcolors, Config, MachineConfig, search_config, CONFIG_FILE, CONFIG_FILE_LOCAL,
                           DATA_DIR, CONFIG_FILE_LEGACY, CONFIG_FILE_LEGACY_XDG,
                           SETTINGS, LIBRARY_ONLY, parse_value, format_value, is_pool_path, short_home)
from papers.duplicate import list_duplicates, list_uniques, edit_entries, title_id
from papers.entries import get_entry_val, entry_content_equal, entry_from_dict
from papers.bib import (Biblio, FUZZY_RATIO, DEFAULT_SIMILARITY, entry_filecheck,
                        backupfile as backupfile_func, isvalidkey, DuplicateKeyError, clean_filesdir,
                        are_duplicates, download_url, get_biblio, scan_dir_items, hidden_bibtex)
from papers.install import resolve_install, apply_install, init_backup, _ask_path, InputAsker, DefaultAsker
from papers.utils import view_pdf, open_folder, PapersExit, file_uri_to_path, find_masked_viewer, set_directory
from papers.backup import (silent_backup_bib, restore_from_backupdir,
                           git_undo, git_redo, git_restore_state, list_backup_dirs)
from papers import __version__


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


LIBRARY_CONFIG_FILES = [CONFIG_FILE_LOCAL, os.path.join(".papers", "config.json")]


def find_config(start_dir='.', machine=None):
    """The configuration that commands act on, with `origin` telling where it
    was found:
    - 'library': a library configuration in start_dir or above;
    - 'v2-global': the global configuration of papers v2, until `papers migrate`;
    - 'default-pool': the library of the default pool;
    - None: no library (a Config with the inherited settings only).
    """
    machine = machine or MachineConfig.load()
    configfile = search_config(LIBRARY_CONFIG_FILES, start_dir=start_dir, default=None)
    origin = 'library'
    if configfile is None and os.path.exists(CONFIG_FILE):
        configfile, origin = CONFIG_FILE, 'v2-global'
    if configfile is None:
        pool = machine.pool_path('default')
        if pool and os.path.exists(os.path.join(pool, CONFIG_FILE_LOCAL)):
            configfile, origin = os.path.join(pool, CONFIG_FILE_LOCAL), 'default-pool'
    if configfile is None:
        return Config(machine=machine)
    config = Config.load(check_legacy_config(configfile), machine=machine,
                         local=False if origin == 'v2-global' else None)
    config.origin = origin
    return config


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
        logger.debug(f'do not backup bib: git is off')
    # if config.git:
        # config.gitcommit()



def view_entry_files(biblio, entry):
    files = biblio.get_files(entry)

    # several files in a directory of previous versions' layout (<name>/ with
    # a hidden .<name>.bib): open the directory instead of the single files
    if len(files) > 1:
        parent = os.path.commonpath(files)
        if os.path.isfile(hidden_bibtex(parent)):
            open_folder(parent)
            return

    for f in biblio.get_files(entry):
        logger.info(f"opening {f} ...")
        view_pdf(f)


def format_options(o, kind=('name', 'key')):
    """the name and key format settings passed on the command line, by
    setting name (`--name-author-num 1` -> {'name.author-num': 1})"""
    options = {}
    for name in SETTINGS:
        if name.startswith(tuple(k + '.' for k in kind)):
            value = getattr(o, name.replace('.', '_').replace('-', '_'), None)
            if value is not None:
                options[name] = value
    return options


def set_keyformat_config_from_cmd(o, config):
    """
    Given options and a config state, applies the desired key options to the config.
    """
    for name, value in format_options(o, ['key']).items():
        setattr(config.keyformat, name.split('.')[1].replace('-', '_'), value)

def set_nameformat_config_from_cmd(o, config):
    """
    Given options and a config state, applies the desired name options to the config.
    """
    for name, value in format_options(o, ['name']).items():
        setattr(config.nameformat, name.split('.')[1].replace('-', '_'), value)


def check_pools(config, pools):
    "warn about pool names that the per-machine configuration does not define"
    for pool in pools:
        if not is_pool_path(pool) and config.machine.pool_path(pool) is None:
            logger.warning(f"unknown pool name: {pool} (define it with `papers config --machine pools.{pool} PATH`, "
                           "or write a path with a / to use a folder)")


def _install(o, config, asker, target=None):
    "resolve and apply an install of a library, with the format options of the command line"
    plan = resolve_install(config, o, asker=asker, target=target)
    for name, value in format_options(o).items():
        plan.config.set(name, value)
    check_pools(plan.config, plan.config.pools)
    return apply_install(plan)


def initcmd(parser, o, config):
    """create a library in the current directory"""
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
        o.prompt = False
    asker = InputAsker() if o.prompt else DefaultAsker()

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
    as the `default` pool of the per-machine configuration"""
    logger.warning("`papers install --global` is deprecated: there is no global configuration in v3. "
                   "The library configuration is written next to the bibtex, and its directory "
                   "becomes the `default` pool, used outside of any library.")
    machine = config.machine
    bibtex = o.bibtex
    if not bibtex:
        default = config.bibtex if config.origin in ('v2-global', 'default-pool') and config.bibtex else 'papers.bib'
        bibtex = _ask_path(asker, "Bibtex file name", default)
    if not bibtex:
        raise PapersExit("install --global needs a bibtex file")
    bibtex = os.path.abspath(bibtex)
    libdir = os.path.dirname(bibtex)
    target = os.path.join(libdir, CONFIG_FILE_LOCAL)
    existing = Config.load(target, machine=machine) if os.path.exists(target) else Config(machine=machine)

    o.bibtex = bibtex
    if o.filesdir and o.filesdir.lower() not in ('none', 'null', 'unset', 'undefined', 'reset', 'delete'):
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
    if config.origin == 'default-pool':
        raise PapersExit(f"no library in this directory or above. The default pool ({config.configdir}) "
                         f"is used outside of libraries: remove its configuration with "
                         f"`papers -C {config.configdir} uninstall`")
    if Path(config.file).exists():
        print(f"remove configuration file: {config.file}")
        os.remove(config.file)
    else:
        logger.info(f"The uninstaller found no config file to remove.")
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

    if o.recursive:
        # library configurations above, then the global configuration of v2
        # (never the per-machine configuration)
        configfile = search_config(LIBRARY_CONFIG_FILES, start_dir=".", default=CONFIG_FILE)
        configfile = check_legacy_config(configfile)
        if os.path.exists(configfile):
            other = Config.load(configfile, machine=config.machine)
            other.origin = 'library'
            uninstallcmd(parser, o, other)


def _check_setting_name(name, machine):
    if name == 'light':
        raise PapersExit("light is not changed with `papers config`, because it changes the file "
                         "links and the files too: use `papers migrate --light` or `papers migrate --full` "
                         "(not implemented yet)")
    if machine and name.startswith('pools.') and len(name) > len('pools.'):
        return
    if name not in SETTINGS:
        raise PapersExit(f"unknown setting: {name}. Settings: {', '.join(SETTINGS)}"
                         + (", pools.NAME (with --machine)" if not machine else ", pools.NAME"))
    if machine and name in LIBRARY_ONLY:
        raise PapersExit(f"{name} is a setting of a library, not of the machine"
                         + (" (the per-machine configuration names pools: pools.NAME PATH)" if name == 'pools' else ''))


def _parse_setting(name, values):
    try:
        return parse_value(name, values)
    except ValueError as error:
        raise PapersExit(str(error))


def configcmd(parser, o, config):
    """get and set the settings of the library (or with --machine, of the
    per-machine configuration)"""
    if o.unset and o.key:
        parser.error('--unset takes the setting name: papers config --unset KEY')
    name = o.unset or o.key
    if name:
        _check_setting_name(name, o.machine)
    if o.machine:
        return machine_configcmd(parser, o, config.machine, name)

    if config.file is None:
        raise PapersExit(f"no library found in this directory or above, and the default pool is not a library. "
                         f"{init_hint(config)}, or use `papers config --machine`")

    if not name:
        print(f"# {config.file}")
        print('\n'.join(config.settings_lines()))
        return

    if not o.unset and not o.values:
        value = config.get(name)
        if name in ('bibtex', 'filesdir') and value is not None:
            value = config._relpath(value)
        print(format_value(value))
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
    if name == 'paths' and config.bibtex and os.path.exists(config.bibtex):
        convert_file_links(config)


def convert_file_links(config):
    "write the file links of the bibtex as the `paths` setting says (relative or absolute)"
    biblio = get_biblio(config)  # converts to absolute links if needed
    biblio.update_file_path(biblio.relative_to)  # converts to relative links if needed
    savebib(biblio, config)


def machine_configcmd(parser, o, machine, name):
    if not name:
        print(f"# {machine.file}" + ("" if machine.exists() else " (does not exist)"))
        for pool, path in machine.pools.items():
            source = 'machine' if pool in machine.data.get('pools', {}) else 'default'
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
    if o.light or o.full:
        raise PapersExit("migrate --light / --full: not implemented yet")
    if o.folders:
        return migrate_folders(check_install(parser, o, config))
    from papers.migrate import migrate_v2_global
    if not migrate_v2_global(config.machine, relative=o.relative, dryrun=papers.config.DRYRUN,
                             convert_links=convert_file_links):
        print("nothing to migrate: no global configuration of papers v2 was found")


def migrate_folders(config):
    """move the files of the entries kept in folders of papers < 2.19
    (<name>/ with a hidden .<name>.bib) to the flat layout of the files directory"""
    biblio = get_biblio(config)
    count = 0
    for e in biblio.entries:
        files = biblio.get_files(e)
        if any(os.path.isfile(hidden_bibtex(os.path.dirname(f))) for f in files):
            logger.info(f"{biblio.key(e)}: move files out of {os.path.dirname(files[0])}")
            biblio.rename_entry_files(e)
            count += 1
    if count:
        savebib(biblio, config)
    print(f"{count} entries moved out of the folders of papers < 2.19")


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
        from papers.backup import resolve_gitdir
        config.gitdir = resolve_gitdir(bibtex)
    return config


def init_hint(config):
    "how to create a library, here or for the default pool"
    pool = config.machine.pool_path('default')
    mkdir = '' if os.path.isdir(pool) else f"mkdir -p {pool} && "
    return f"Create a library with `papers init` (here) or `{mkdir}papers -C {pool} init` (the default pool)"


def check_install(parser, o, config, bibtex_must_exist=True):
    """
    Given an option and config, checks to see if the install is done correctly on this filesystem.
    Returns the configuration to use (see config_for_bibtex).
    """
    if getattr(o, "bibtex", None) is not None:
        config = config_for_bibtex(o.bibtex, config)
        config.bibtex = o.bibtex
    if getattr(o, "filesdir", None) is not None:
        config.filesdir = o.filesdir
    if getattr(o, "absolute_paths", None) is not None:
        option = '--absolute-paths' if o.absolute_paths else '--relative-paths'
        logger.warning(f"{option} is deprecated: file paths are a setting of the library, "
                       f"`papers config paths {'absolute' if o.absolute_paths else 'relative'}`")
        config.absolute_paths = o.absolute_paths
    if getattr(o, "git", None) is not None:
        config.git = o.git

    if not config.bibtex:
        print(f"papers: error: no library found in this directory or above, and the default pool "
              f"({config.machine.pool_path('default')}) is not a library. {init_hint(config)}, or pass --bibtex")
        raise PapersExit()

    if bibtex_must_exist and not os.path.exists(config.bibtex):
        print(f'papers: error: no bibtex file found, do `touch {config.bibtex}` or `papers init --bibtex {config.bibtex}`')
        raise PapersExit()
    logger.info(f'bibtex: {config.bibtex!r}')
    logger.info(f'filesdir: {config.filesdir!r}')
    return config


def _print_biblio_diff(biblio_init, biblio, touched_entries, show_existing=False):
    """Emit Added/Modified/Removed (and optionally Existing) lines for
    entries that differ between the pre-command snapshot and the
    post-command state.

    `touched_entries` scopes the Modified/Existing check to entries the
    command actually considered (matches addcmd's original semantics).
    """
    old_set = set(get_entry_val(e, 'ID', '') for e in biblio_init.entries)
    old_entries_by_key = {get_entry_val(e, 'ID', ''): e for e in biblio_init.db.entries}
    new_set = set(get_entry_val(e, 'ID', '') for e in biblio.entries)
    new_entries_by_key = {get_entry_val(e, 'ID', ''): e for e in biblio.db.entries}
    modified_set = set(get_entry_val(e, 'ID', '') for e in touched_entries).intersection(set.intersection(old_set, new_set))

    for ID in sorted(old_set - new_set):
        print(format_entry(biblio_init, old_entries_by_key[ID], prefix="Removed"))

    for ID in sorted(new_set - old_set):
        print(format_entry(biblio, new_entries_by_key[ID], prefix="Added"))

    for ID in sorted(modified_set):
        before = old_entries_by_key[ID]
        after = new_entries_by_key[ID]
        if not entry_content_equal(before, after):
            print(format_entry(biblio, after, prefix="Modified"))
        elif show_existing:
            print(format_entry(biblio, after, prefix="Existing"))


def addcmd(parser, o, config):
    """
    Given an options set and a config, sets up the function call to add the file or all files in the directory to the bibtex, and executes it.
    """

    set_nameformat_config_from_cmd(o, config)
    set_keyformat_config_from_cmd(o, config)

    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)

    entries = []

    metadata = {k: v for k, v in o.metadata or []}
    if o.doi: metadata['doi'] = o.doi
    if o.key: metadata['ID'] = o.key
    if o.title: metadata['title'] = o.title
    if o.author: metadata['author'] = o.author
    if o.journal: metadata['journal'] = o.journal
    if o.year: metadata['year'] = o.year
    if o.type: metadata['ENTRYTYPE'] = o.type
    if "author" in metadata:
        metadata["author"] = standard_name(metadata["author"])
    if o.attachment:
        resolved = []
        any_url = False
        for a in o.attachment:
            if str(a).startswith("http://") or str(a).startswith("https://"):
                resolved.append(download_url(a, expect_pdf=False))
                any_url = True
            else:
                resolved.append(a)
        o.attachment = resolved
        if any_url:
            # downloaded attachments live in a tempdir; rename so they land in filesdir
            o.rename = True
        metadata['file'] = format_file(biblio.get_files(metadata) + o.attachment, relative_to=biblio.relative_to)

    if len(o.file) > 1:
        if metadata:
            logger.error('--doi, --metadata, --key, --attachment and other metadata keys are only valid for one PDF / BIBTEX entry')
            raise PapersExit()

    kw = {'on_conflict':o.mode, 'check_duplicate':not o.no_check_duplicate,
            'mergefiles':not o.no_merge_files, 'update_key':o.update_key, 'metadata':metadata}

    if len(o.file) == 0 and o.doi and not o.no_query_doi:
        entries.extend( biblio.fetch_doi(o.doi, attachments=o.attachment, rename=o.rename, copy=o.copy, **kw) )

    elif len(o.file) == 0:
        if not o.edit and not o.metadata and not o.key and not o.doi and not o.attachment and not o.title and not o.author and not o.journal and not o.year:
            logger.error("No entry added: use --doi, --metadata, --key, --attachment, --title, --author, --journal, --year to add a new entry")
            raise PapersExit()

        metadata.setdefault('ID', biblio.keyformat(metadata))
        metadata.setdefault('ENTRYTYPE', 'article')
        if o.edit:
            metadata = edit_entries(metadata)
            o.edit = False

        entries.extend( biblio.insert_entry(entry_from_dict(metadata), rename=o.rename, copy=o.copy, **kw) )


    # several PDFs: fetch their metadata concurrently first
    if not o.doi and not o.scholar and not (o.no_query_doi and o.no_query_fulltext):
        pdfs = []
        for file in o.file:
            if os.path.isdir(file) and o.recursive:
                pdfs.extend(path for kind, path, _ in scan_dir_items(file, quiet=True) if kind == 'file' and path.lower().endswith('.pdf'))
            elif os.path.isfile(file) and file.lower().endswith('.pdf'):
                pdfs.append(file)
        if len(pdfs) > 1:
            prefetch_pdf_metadata(pdfs, search_doi=not o.no_query_doi, search_fulltext=not o.no_query_fulltext)

    for file in o.file:
        try:
            if os.path.isdir(file):
                if o.recursive:
                    entries.extend( biblio.scan_dir(file, rename=o.rename, copy=o.copy,
                                search_doi=not o.no_query_doi,
                                search_fulltext=not o.no_query_fulltext,
                                **kw) )
                else:
                    raise ValueError(file+' is a directory, requires --recursive to explore')

            elif file.lower().endswith('.pdf'):
                entries.extend( biblio.add_pdf(file, attachments=o.attachment, rename=o.rename, copy=o.copy,
                           search_doi=not o.no_query_doi,
                           search_fulltext=not o.no_query_fulltext,
                           scholar=o.scholar, doi=o.doi,
                           **kw) )

            else: # file.endswith('.bib'):
                entries.extend( biblio.add_bibtex_file(file, attachments=o.attachment, rename=o.rename, copy=o.copy, **kw) )

        except Exception as error:
            logger.error(str(error))
            if not o.ignore_errors:
                if len(o.file) > 1 or (os.path.isdir(file) and o.recursive):
                    logger.error('use --ignore-errors to add other files anyway')
                raise PapersExit()

    # The list of new entries potentially contains duplicates if more than one file is added sequentially
    # If action is required on the added entry, we need to make sure we're consistent with the biblio.
    if len(entries) > 1 and (o.edit or o.open):
        unique_keys = set(biblio.key(e) for e in entries)
        entries = [e for e in biblio.entries if biblio.key(e) in unique_keys]

    if o.edit:
        entry_keys = [biblio.key(e) for e in entries]
        otherentries = [e for e in biblio.entries if biblio.key(e) not in entry_keys]

        try:
            entries = edit_entries(entries)
        except Exception as error:
            logger.error(str(error))
            return

        entries = [{k:v for k,v in e.items() if v != ""} for e in entries]
        biblio.db.entries = sorted(otherentries + entries, key=lambda e: biblio.key(e))

    savebib(biblio, config)

    # compare entries to inform user
    # this is not very efficient but I have yet to hear a complaint about speed
    _print_biblio_diff(biblio_init, biblio, entries, show_existing=True)

    if o.open:
        for e in entries:
            view_entry_files(biblio, e)

def checkcmd(parser, o, config):
    """
    Loops over the entire bib file that the Papers install sees, and checks each entry for formatting and for the existance of duplicates.  Then writes the Biblio object back to your Bibtex file.
    """
    set_keyformat_config_from_cmd(o, config)

    biblio = get_biblio(config)

    # if o.fix_all:
    #     o.fix_doi = True
    #     o.fetch_all = True
    #     o.fix_key = True

    for e in biblio.entries:
        if o.keys and get_entry_val(e, 'ID', '') not in o.keys:
            continue
        biblio.fix_entry(e, fix_doi=o.fix_doi, fetch=o.fetch, fetch_all=o.fetch_all, fix_key=o.fix_key,
                     auto_key=o.auto_key, format_name=o.format_name, encoding=o.encoding,
                     key_ascii=o.key_ascii, interactive=not o.force)


    if o.duplicates:
        mode = o.mode
        if o.force and mode == 'i':
            mode = 's'  # --force means non-interactive: leave unresolved duplicates alone
        biblio.check_duplicates(mode=mode)

    savebib(biblio, config)

def filecheckcmd(parser, o, config):
    set_nameformat_config_from_cmd(o, config)

    biblio = get_biblio(config)

    # fix ':home' entry as saved by Mendeley
    for e in biblio.entries:
        entry_filecheck(e, delete_broken=o.delete_broken, fix_mendeley=o.fix_mendeley,
                        check_hash=o.hash_check, check_metadata=o.metadata_check, interactive=not o.force, relative_to=biblio.relative_to)

    if o.rename:
        biblio.rename_entries_files(o.copy)

    if o.clean_filesdir:
        print("Check files directory for unlinked files")
        clean_filesdir(biblio, interactive=not o.force, ignore_files=[config.bibtex])

    savebib(biblio, config)

def redocmd(parser, o, config):
    if config.git:
        return git_redo(config, restore_files=o.restore_files, steps=o.steps)
    else:
        undocmd(parser, o, config)

def undocmd(parser, o, config):
    if config.git:
        return git_undo(config, restore_files=o.restore_files, steps=o.steps)

    logger.warning("git-tracking is not installed: undo / redo is limited to 1 step back and forth")
    back = backupfile_func(config.bibtex)
    tmp = config.bibtex + '.tmp'
    # my = :config.bibtex, config.filesdir)
    logger.info(config.bibtex+' <==> '+back)
    shutil.copy(config.bibtex, tmp)
    shutil.move(back, config.bibtex)
    shutil.move(tmp, back)
    # o.savebib()

def restorecmd(parser, o, config):
    if not config.git:
        parser.print_help()
        raise PapersExit('only valid with --git enabled')
    if o.ref:
        git_restore_state(config, o.ref, restore_files=o.restore_files)
    else:
        restore_from_backupdir(config, restore_files=o.restore_files)


def _print_backup_info(info):
    owner = info['bibtex'] or 'unknown library (no manifest)'
    status = ''
    if info['bibtex'] and not os.path.exists(info['bibtex']):
        status = bcolors.WARNING + ' (bibtex missing)' + bcolors.ENDC
    current = ' [current]' if info['current'] else ''
    snapshots = f"{info['snapshots']} snapshots" if info['snapshots'] is not None else 'no snapshot'
    last = f", last {info['last']}" if info['last'] else ''
    size = f"{info['size']/(1024*1024):.1f} MB"
    print(f"* {os.path.basename(info['gitdir'])}: {owner}{status} ({snapshots}{last}, {size}){current}")
    print(f"    {info['gitdir']}")


def backupcmd(parser, o, config):
    infos = list_backup_dirs(config)
    if o.patterns:
        infos = [info for info in infos
                 if any(fnmatch.fnmatch(os.path.basename(info['gitdir']), p) for p in o.patterns)]

    if o.action == 'remove':
        if not o.patterns:
            parser.error('backup remove requires directory name(s) -- see `papers backup list`')
        if not infos:
            print('no matching backup directory')
            return
        for info in infos:
            _print_backup_info(info)
            if info['current']:
                logger.warning("this is the current library's backup directory; "
                               "removing it discards its history (a fresh one is created on the next save)")
            if not o.force:
                ans = input(f"remove {info['gitdir']} ? [y/N] ")
                if ans.lower() != 'y':
                    continue
            shutil.rmtree(info['gitdir'])
            print(f"removed {info['gitdir']}")
        return

    if not infos:
        print('no matching backup directory' if o.patterns else 'no backup directory found')
    for info in infos:
        _print_backup_info(info)

    # always say where the current library stands
    if not o.patterns and config.bibtex:
        if not config.git:
            print(f"current library: {config.bibtex} :: git-tracking is off "
                  f"(enable with `papers config git true`)")
        elif not any(info['current'] for info in infos):
            print(f"current library: {config.bibtex} :: no snapshot recorded yet")


def gitcmd(parser, o, config):
    try:
        out = sp.check_output(['git']+o.gitargs, cwd=config.gitdir)
        print(out.decode())
    except Exception as error:
        print(f"Error message: {error}")
        parser.error('papers failed to execute git command -- you should check your system git install.')

def doicmd(parser, o):
    print(extract_pdf_doi(o.pdf, image=o.image))

def fetchcmd(parser, o):
    # either one or several DOIs
    if all(isvaliddoi(field) for field in o.doi_or_text):
        if o.scholar:
            parser.error("Fetching from DOI does not support Google Scholar option")
        for doi in o.doi_or_text:
            print(fetch_bibtex_by_doi(doi))
        return

    # or one full text search
    field = " ".join(o.doi_or_text)
    if o.scholar:
        print(fetch_bibtex_by_fulltext_scholar(field))
    else:
        print(fetch_bibtex_by_fulltext_crossref(field))

def _collect_pdf_files(paths, recursive=False):
    """Expand the extract arguments into a list of PDF files.

    Plain files are taken as given; directories require `recursive` and are
    scanned for PDF files (case-insensitively).
    """
    files = []
    for path in paths:
        if os.path.isdir(path):
            if not recursive:
                raise ValueError(f'{path} is a directory, requires --recursive to scan')
            files.extend(sorted(str(p) for p in Path(path).rglob('*')
                                if p.is_file() and p.suffix.lower() == '.pdf'))
        else:
            files.append(path)
    return files


def extractcmd(parser, o):
    try:
        files = _collect_pdf_files(o.pdf, recursive=o.recursive)
    except ValueError as error:
        parser.error(str(error))
    if not files:
        logger.warning('no PDF file found')
        return
    for file in files:
        if len(files) > 1:
            print(f'% {file}')
        try:
            print(extract_pdf_metadata(file, search_doi=not o.fulltext, search_fulltext=True, scholar=o.scholar, minwords=o.word_count, max_query_words=o.word_count, image=o.image))
        except Exception as error:
            if len(files) == 1:
                raise
            logger.error(f'{file} :: {error}')


def _fullsearch_string(e):
    return " ".join([v for k,v in sorted(e.items(), key=lambda kv:kv[0]) if v is not None])


def listcmd(parser, o, config):

    def _match(word, target, fuzzy=False, substring=False):
        if isinstance(target, list):
            return (any if o.any else all)([_match(word, t, fuzzy, substring) for t in target])

        if fuzzy:
            res = (target.lower() in word.lower() or fuzz.token_set_ratio(word.lower(), target.lower(), score_cutoff=o.fuzzy_ratio) > o.fuzzy_ratio)
        elif substring:
            res = target.lower() in word.lower()
        else:
            res = fnmatch.fnmatch(word.lower(), target.lower())

        return res if not o.invert else not res


    def _longmatch(word, target):
        return _match(word, target, fuzzy=o.fuzzy, substring=not o.strict)

    def _nfiles(e):
        return len(parse_file(get_entry_val(e, 'file', ''), relative_to=biblio.relative_to))


    def _requiresreview(e):
        if not isvalidkey(get_entry_val(e, 'ID', '')): return True
        if 'doi' in e and not isvaliddoi(e['doi']): return True
        if 'author' not in e: return True
        if 'title' not in e: return True
        if 'year' not in e: return True
        return False


    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)
    entries = biblio.db.entries

    if o.fuzzy:
        from rapidfuzz import fuzz


    if o.review_required:
        if o.invert:
            entries = [e for e in entries if not _requiresreview(e)]
        else:
            entries = [e for e in entries if _requiresreview(e)]
            for e in entries:
                if 'doi' in e and not isvaliddoi(e['doi']):
                    e['doi'] = bcolors.FAIL + e['doi'] + bcolors.ENDC
    if o.has_file:
        entries = [e for e in entries if get_entry_val(e, 'file', '')]
    if o.no_file:
        entries = [e for e in entries if not get_entry_val(e, 'file', '')]
    if o.broken_file:
        entries = [e for e in entries if get_entry_val(e, 'file', '') and any([not os.path.exists(f) for f in parse_file(e['file'], relative_to=biblio.relative_to)])]


    if o.doi:
        entries = [e for e in entries if 'doi' in e and _longmatch(e['doi'], o.doi)]
    if o.key:
        entries = [e for e in entries if _longmatch(get_entry_val(e, 'ID', ''), o.key)]
    if o.year:
        entries = [e for e in entries if 'year' in e and _longmatch(e['year'], o.year)]
    if o.first_author:
        first_author = lambda field : family_names(field)[0]
        entries = [e for e in entries if 'author' in e and _longmatch(first_author(e['author']), o.first_author)]
    if o.author:
        author = lambda field : ' '.join(family_names(field))
        entries = [e for e in entries if 'author' in e and _longmatch(author(e['author']), o.author)]
    if o.title:
        entries = [e for e in entries if 'title' in e and _longmatch(e['title'], o.title)]
    if o.abstract:
        entries = [e for e in entries if 'abstract' in e and _longmatch(e['abstract'], o.abstract)]
    if o.keywords:
        entries = [e for e in entries if 'keywords' in e and _longmatch(e['keywords'], o.keywords)]
    if o.fullsearch:
        o.strict = False
        entries = [e for e in entries if _longmatch(_fullsearch_string(e), o.fullsearch)]

    _check_duplicates = lambda uniques, groups: uniques if o.invert else list(itertools.chain(*groups))

    # if o.duplicates_key or o.duplicates_doi or o.duplicates_tit or o.duplicates or o.duplicates_fuzzy:
    list_dup = list_uniques if o.invert else list_duplicates

    if o.duplicates_key:
        entries = list_dup(entries, key=biblio.key, issorted=True)
    if o.duplicates_doi:
        entries = list_dup(entries, key=lambda e: get_entry_val(e, 'doi', ''), filter_key=isvaliddoi)
    if o.duplicates_tit:
        entries = list_dup(entries, key=title_id)
    if o.duplicates:
        # QUESTION MARK: in latest HEAD before merge with @malfatti's PR, I used hard-coded "PARTIAL".
        # I think that's because we might need to be inclusive here, whereas the default is conservative (parameter used for several functions with possibly differing requirements).
        # (otherwise we'd have used the command-line option o.similarity, or possibly DEFAULT_SIMILARITY)
        # Might need to revise later (the question mark is from a review after a long time without use)
        eq = lambda a, b: get_entry_val(a, 'ID', '') == get_entry_val(b, 'ID', '') or are_duplicates(a, b, similarity="PARTIAL", fuzzy_ratio=o.fuzzy_ratio)
        entries = list_dup(entries, eq=eq)

    if o.add_keywords:
        for e in entries:
            keywords = parse_keywords(e)
            for w in o.add_keywords:
                if w not in keywords:
                    keywords.append(w)
            e['keywords'] = ", ".join(keywords)
        savebib(biblio, config)

    elif o.add_files:
        if len(entries) != 1:
            raise PapersExit("list only one entry to use --add-files")
        e = entries[0]
        files = biblio.get_files(e)
        resolved = []
        any_url = False
        for f in o.add_files:
            if str(f).startswith("http://") or str(f).startswith("https://"):
                resolved.append(download_url(f, expect_pdf=False))
                any_url = True
            elif not os.path.exists(f):
                raise PapersExit(f"file {f} does not exist")
            else:
                resolved.append(f)
        if any_url:
            # downloaded files live in a tempdir; rename so they land in filesdir
            o.rename = True
        files.extend(resolved)
        biblio.set_files(e, files)
        if o.rename:
            biblio.rename_entry_files(e, copy=o.copy)
        savebib(biblio, config)

    elif o.edit:
        otherentries = [e for e in biblio.db.entries if e not in entries]
        try:
            entries = edit_entries(entries)
            biblio.entries = otherentries + entries
        except Exception as error:
            logger.error(str(error))
            return

        savebib(biblio, config)

    elif o.fetch:
        for e in entries:
            biblio.fix_entry(e, fix_doi=True, fix_key=True, fetch_all=True, interactive=True)
        savebib(biblio, config)

    elif o.rename:
        for e in entries:
            biblio.rename_entry_files(e, copy=o.copy)
        savebib(biblio, config)

    elif o.delete:
        for e in entries:
            biblio.db.remove(e)
        savebib(biblio, config)

    elif o.open:
        for e in entries:
            view_entry_files(biblio, e)

    elif o.field:
        # entries = [{k:e[k] for k in e if k in o.field+['ID','ENTRYTYPE']} for e in entries]
        for e in entries:
            print(format_key(e, no_key=o.no_key),*[get_entry_val(e, k, "") for k in o.field])
    elif o.key_only:
        for e in entries:
            print(get_entry_val(e, 'ID', ''))
    elif o.one_liner:
        for e in entries:
            print(format_entry(biblio, e, no_key=o.no_key))

    else:
        print(format_entries(entries))

    # report any entry mutations (--add-files, --add-keywords, --edit, --fetch,
    # --rename, --delete) using the same Added/Modified/Removed convention as addcmd
    _print_biblio_diff(biblio_init, biblio, entries)


def opencmd(parser, o, config):
    biblio = None
    entries_by_key = {}
    for key in o.key:
        # an existing file is opened directly with the system viewer; anything
        # else is looked up as an entry key in the bibliography
        if os.path.isfile(key):
            logger.info(f"opening {key} ...")
            view_pdf(key)
            continue
        if biblio is None:
            try:
                biblio = get_biblio(config)
            except ValueError:
                raise PapersExit(f"'{key}' is not an existing file, and no bibliography is configured to look it up as a key")
            entries_by_key = {biblio.key(e): e for e in biblio.entries}
        e = entries_by_key.get(key.lower())
        if e is None:
            logger.error(f'no entry found with key: {key}')
            continue
        if not biblio.get_files(e):
            logger.warning(f'{get_entry_val(e, "ID", "")}: no attached file')
            continue
        view_entry_files(biblio, e)


def statuscmd(parser, o, config):
    print(config.status(check_files=not o.no_check_files, verbose=o.verbose))
    if config.file is None:
        print(f"* default pool:       {config.machine.pool_path('default')} (not a library)")
        print(init_hint(config))


def get_parser(config=None):
    if config is None:
        config = papers.config.Config()

    parser = argparse.ArgumentParser(prog='papers', description='library management tool')
    parser.add_argument('--version', action='store_true', help='Print version string and exit.')
    parser.add_argument('-C', metavar='DIR', dest='directory',
        help='run as if papers was started in DIR (before the command name)')

    subparsers = parser.add_subparsers(dest='cmd')

    def _default(value):
        "a configured value shown in a help text (argparse formats help with %)"
        return str(value).replace('%', '%%')

    # configuration (re-used everywhere)
    # =============
    loggingp = argparse.ArgumentParser(add_help=False)
    grp = loggingp.add_argument_group('logging level (default warn)')
    egrp = grp.add_mutually_exclusive_group()
    egrp.add_argument('--debug', action='store_const', dest='logging_level', const=logging.DEBUG)
    egrp.add_argument('--info', action='store_const', dest='logging_level', const=logging.INFO)
    egrp.add_argument('--warn', action='store_const', dest='logging_level', const=logging.WARN)
    egrp.add_argument('--error', action='store_const', dest='logging_level', const=logging.ERROR)

    cfg = argparse.ArgumentParser(add_help=False, parents=[loggingp])
    grp = cfg.add_argument_group('config')
    grp.add_argument('--filesdir', default=None, type=file_uri_to_path,
        help=f'files directory (default: {_default(config.filesdir)})')
    grp.add_argument('--bibtex', default=None, type=file_uri_to_path,
        help=f'bibtex database (default: {_default(config.bibtex)})')
    grp.add_argument('--dry-run', action='store_true',
        help='no PDF renaming/copying, no bibtex writing on disk (for testing)')
    grp.add_argument('--relative-paths', action="store_false", dest="absolute_paths", default=None,
        help='store file paths relative to the bibtex file (deprecated: `papers config paths relative`)')
    grp.add_argument('--absolute-paths', action="store_true", default=None,
        help='store absolute file paths (deprecated: `papers config paths absolute`)')
    grp.add_argument('--no-git', action='store_false', dest='git', default=None, help="""Do not commit the current action, whatever happens""")

    # the format options default to None: the configured values apply
    keyfmt = argparse.ArgumentParser(add_help=False)
    grp = keyfmt.add_argument_group('bibtex key format')
    grp.add_argument('--key-template',
        help=f'''python template for generating keys (default: {_default(config.keyformat.template)}).
        The template applies to entries generated from a PDF or a DOI;
        entries added from a bibtex file keep their original key unless
        -u/--update-key is passed.''')
    grp.add_argument('--key-author-num', type=int,
        help=f'number of authors to include in key (default: {config.keyformat.author_num})')
    grp.add_argument('--key-author-sep',
        help=f'separator for authors in key (default: {_default(config.keyformat.author_sep)})')
    grp.add_argument('--key-title-word-num', type=int,
        help=f'number of title words to include in key (default: {config.keyformat.title_word_num})')
    grp.add_argument('--key-title-word-size', type=int,
        help=f'min size of title words to include in key (default: {config.keyformat.title_word_size})')
    grp.add_argument('--key-title-sep',
        help=f'separator for title words in key (default: {_default(config.keyformat.title_sep)})')

    namefmt = argparse.ArgumentParser(add_help=False)
    grp = namefmt.add_argument_group('filename format')
    grp.add_argument('--name-template',
        help=f'python template for renaming files (default: {_default(config.nameformat.template)})')
    grp.add_argument('--name-author-num', type=int,
        help=f'number of authors to include in filename (default: {config.nameformat.author_num})')
    grp.add_argument('--name-author-sep',
        help=f'separator for authors in filename (default: {_default(config.nameformat.author_sep)})')
    grp.add_argument('--name-title-word-num', type=int,
        help=f'number of title words to include in filename (default: {config.nameformat.title_word_num})')
    grp.add_argument('--name-title-word-size', type=int,
        help=f'min size of title words to include in filename (default: {config.nameformat.title_word_size})')
    grp.add_argument('--name-title-length', type=int,
        help=f'title length to include in filename (default: {config.nameformat.title_length})')
    grp.add_argument('--name-title-sep',
        help=f'separator for title words in filename (default: {_default(config.nameformat.title_sep)})')


    # status
    # ======
    statusp = subparsers.add_parser('status',
        description='show the library, its pools and its settings',
        parents=[cfg])
    statusp.add_argument('--no-check-files', action='store_true', help='faster, less info')
    statusp.add_argument('-v','--verbose', action='store_true', help='also show where each setting comes from')

    # init
    # ====
    initp = subparsers.add_parser('init', description='create a library in the current directory',
        parents=[loggingp, namefmt, keyfmt])
    initp.add_argument('--bibtex', type=file_uri_to_path,
        help='bibtex file (default: papers.bib, or the only .bib file of the directory)')
    initp.add_argument('--filesdir', type=file_uri_to_path,
        help='files directory (default: files, or an existing pdfs/, papers/... folder)')
    initp.add_argument('--pool', nargs='+', action='extend', metavar='NAME|PATH',
        help='pools of the library: names of the per-machine configuration, or paths '
             '(containing a /, relative to the library) (default: default)')
    initp.add_argument('--paths', choices=['relative', 'absolute'],
        help='file links in the bibtex relative to the bibtex directory, or absolute '
             f'(default: {config.inherited("paths")})')
    initp.add_argument('--git', action='store_true', default=None,
        help='back up the bibtex with git (default: true when git is installed)')
    initp.add_argument('--no-git', action='store_false', dest='git', default=None, help='no git backup')
    initp.add_argument('--git-lfs', action='store_true', default=None, help='also back up the files with git-lfs (implies --git)')
    initp.add_argument('--editor', help='command to open a text editor; it must wait until the editor is closed, e.g. vim or "subl -w"')
    initp.add_argument('--no-check-files', action='store_true', help=argparse.SUPPRESS)

    # config
    # ======
    configp = subparsers.add_parser('config', parents=[loggingp],
        description='get or set the settings of the library (git style): without KEY, list the '
                    'settings and where each comes from (library, machine or default); with KEY, '
                    'print its value; with KEY VALUE..., set it in the library configuration',
        epilog='settings: ' + ', '.join(SETTINGS) + '; with --machine, also pools.NAME (path of a pool)')
    configp.add_argument('key', nargs='?', metavar='KEY')
    configp.add_argument('values', nargs='*', metavar='VALUE', help='several values for pools')
    configp.add_argument('--unset', metavar='KEY', help='remove the setting: the per-machine or default value applies again')
    configp.add_argument('--machine', '--global', action='store_true',
        help=f'the per-machine configuration ({papers.config.MACHINE_CONFIG_FILE}) instead of the library\'s')
    configp.add_argument('--dry-run', action='store_true', help='do not save')

    # migrate
    # =======
    migratep = subparsers.add_parser('migrate', parents=[cfg],
        description='one-time upgrades from papers v2. Without option: turn the global configuration '
                    'of v2 into a library configuration next to its bibtex, and register its directory '
                    'as the default pool.')
    migratep.add_argument('--relative', action='store_true',
        help='store the file links of the migrated library relative to its bibtex '
             '(default: keep the previous setting)')
    migratep.add_argument('--folders', action='store_true',
        help='move the files of entries kept in folders of papers < 2.19 (<name>/ with a hidden '
             '.<name>.bib) to the flat layout of the files directory')
    migratep.add_argument('--light', action='store_true', help='not implemented yet')
    migratep.add_argument('--full', action='store_true', help='not implemented yet')

    # install
    # =======

    installp = subparsers.add_parser('install', description='deprecated alias of `papers init`; on an existing library, '
        'updates it (deprecated: use `papers config`)',
        parents=[cfg, namefmt, keyfmt])
    installp.add_argument('--edit', action='store_true',
        help=f'update existing install non-interactively (updating is the default; --edit also suppresses prompts) (found: {config.file})')
    installp.add_argument('--reset', action='store_true',
        help='discard the pre-existing configuration and start over from defaults (default: update it)')
    installp.add_argument('--no-prompt', '--force', action='store_false', dest="prompt",
        help='non-interactive: accept defaults without asking')

    installp.add_argument('--local', action="store_true", default=None,
        help="""ignored (a library configuration is always local)""")
    installp.add_argument('--global', action="store_false", dest='local', default=None,
        help="deprecated: create or update the library configuration next to the bibtex, and register "
             "its directory as the default pool (used outside of any library)")

    installp.add_argument('--git', '--backup', action='store_true', default=None, help="""Track bibtex files with git.""")
    installp.add_argument('--git-lfs', '--backup-files', action='store_true', default=None, help="""Backup files with git-lfs (implies --git)""")
    installp.add_argument('--gitdir', default=None, help=argparse.SUPPRESS)
    installp.add_argument('--editor', help="""Set command to open text editor. Need to wait until closing ! E.g. vim or subl -w""")
    installp.add_argument('--pool', nargs='+', action='extend', metavar='NAME|PATH', help=argparse.SUPPRESS)

    grp = installp.add_argument_group('status')
    # grp.add_argument('-l','--status', action='store_true')
    # grp.add_argument('-v','--verbose', action='store_true')
    # grp.add_argument('-c','--check-files', action='store_true')
    grp.add_argument('--no-check-files', action='store_true', help='faster, less info')
    # grp.add_argument('-v','--verbose', action='store_true', help='app status info')


    # uninstall
    # =======
    uninstallp = subparsers.add_parser('uninstall', description='remove the library configuration',
        parents=[loggingp])
    uninstallp.add_argument("--recursive", action="store_true", help="deprecated: also remove the library configurations found in the parent directories, and the global configuration of papers v2 (config files only)")
    uninstallp.add_argument("--remove-backup", action="store_true", help="also remove the backup directory of the uninstalled configuration(s)")


    # add
    # ===
    addp = subparsers.add_parser('add', description='add PDF(s) or bibtex(s) to library',
        parents=[cfg, namefmt, keyfmt])
    addp.add_argument('file', nargs='*', default=[], type=file_uri_to_path)
    # addp.add_argument('-f','--force', action='store_true', help='disable interactive')

    grp = addp.add_argument_group('duplicate check')
    grp.add_argument('--no-check-duplicate', action='store_true',
        help='disable duplicate check (faster, create duplicates)')
    grp.add_argument('--no-merge-files', action='store_true',
        help='distinct "file" field considered a conflict, all other things being equal')
    grp.add_argument('-u', '--update-key', action='store_true',
        help='''regenerate the key of added entries from the key template
        (see "bibtex key format" options); if a duplicate is found, use the
        existing entry's key instead (otherwise an error might be raised on
        identical insert key)''')
    # grp.add_argument('-f', '--force', action='store_true', help='no interactive')
    grp.add_argument('-m', '--mode', default='i', choices=['u', 'U', 'o', 's', 'r', 'i', 'a'],
        help='''if duplicates are found, the default is to start an (i)nteractive dialogue,
        unless "mode" is set to (r)aise, (s)kip new, (u)pdate missing, (U)pdate with new,
        (o)verwrite completely, (a)ppend anyway.
        ''')

    grp = addp.add_argument_group('directory scan')
    grp.add_argument('--recursive', action='store_true',
        help='accept directory as argument, for recursive scan \
        of .pdf and .bib files; files named <name>--<label>.<ext> next to <name>.pdf \
        are added as attachments of its entry')
    grp.add_argument('--ignore-errors', action='store_true',
        help='ignore errors when adding multiple files')

    grp = addp.add_argument_group('metadata')
    grp.add_argument('--doi', help='provide DOI -- skip parsing PDF')
    grp.add_argument('--key', help='manually set the key')
    grp.add_argument('--type', help='document type')
    grp.add_argument('--title', help='manually set the title')
    grp.add_argument('--author', help='manually set the author')
    grp.add_argument('--journal', help='manually set the journal')
    grp.add_argument('--year', help='manually set the year')
    grp.add_argument('--metadata', nargs="+", metavar="KEY=VALUE", type=lambda meta: meta.split('=', 1), help='the metadata fields manually')
    grp.add_argument('--no-query-doi', action='store_true', help='do not attempt to parse and query doi')
    grp.add_argument('--no-query-fulltext', action='store_true', help='do not attempt to query fulltext in case doi query fails')
    grp.add_argument('--scholar', action='store_true', help='use google scholar instead of crossref')

    grp = addp.add_argument_group('attached files',
        description='''Without -r/--rename, the PDF (and the files of a bibtex entry) are linked
        where they are: the file field points to their current location and nothing is
        moved or copied into the files directory. -r moves them into the files directory
        (--filesdir) under a name made from the name template; with -c the original is
        kept and a copy is made instead (-c has no effect without -r).''')
    grp.add_argument('-a','--attachment', nargs='+', type=file_uri_to_path, help='attach these files to the entry (supplementary material)')
    grp.add_argument('-r','--rename', action='store_true',
        help='move the files into the files directory, renamed according to the name template')
    grp.add_argument('-c','--copy', action='store_true',
        help='with -r, copy the files instead of moving them')

    grp = addp.add_argument_group('actions')
    grp.add_argument('-e', '--edit', action='store_true', help='edit entry')
    grp.add_argument('-o', '--open', action='store_true', help='open files')

    # check
    # =====
    checkp = subparsers.add_parser('check', description='check and fix entries',
        parents=[cfg, keyfmt])
    checkp.add_argument('-k', '--keys', nargs='+', help='apply check on this key subset')
    checkp.add_argument('-f','--force', action='store_true', help='do not ask')

    grp = checkp.add_argument_group('entry key')
    grp.add_argument('--fix-key', action='store_true', help='fix key based on author name and date (in case missing or digit)')
    grp.add_argument('--key-ascii', action='store_true', help='replace keys unicode character with ascii')
    grp.add_argument('--auto-key', action='store_true', help='new, auto-generated key for all entries')
    #     grp.add_argument('--nauthor', type=int, default=config.nauthor, help='number of authors to include in key (default:%(default)s)')
    #     grp.add_argument('--ntitle', type=int, default=config.ntitle, help='number of title words to include in key (default:%(default)s)')
    # grp.add_argument('--ascii-key', action='store_true', help='replace unicode characters with closest ascii')

    grp = checkp.add_argument_group('crossref fetch and fix')
    grp.add_argument('--fix-doi', action='store_true', help='fix doi for some common issues (e.g. DOI: inside doi, .received at the end')
    grp.add_argument('--fetch', action='store_true', help='fetch metadata from doi and update entry')
    grp.add_argument('--fetch-all', action='store_true', help='fetch metadata from title and author field and update entry (only when doi is missing)')

    grp = checkp.add_argument_group('names')
    grp.add_argument('--format-name', action='store_true', help='author name as family, given, without brackets')
    grp.add_argument('--encoding', choices=['latex','unicode'], help='bibtex field encoding')

    grp = checkp.add_argument_group('merge/conflict')
    grp.add_argument('--duplicates',action='store_true', help='solve duplicates')
    grp.add_argument('-m', '--mode', default='i', choices=list('ims'), help='''(i)nteractive by default, otherwise (m)erge or (s)kip the duplicates''')
    # grp.add_argument('--ignore', action='store_true', help='ignore unresolved conflicts')
    # checkp.add_argument('--merge-keys', nargs='+', help='only merge remove / merge duplicates')
    # checkp.add_argument('--duplicates',action='store_true', help='remove / merge duplicates')


    # filecheck
    # =====
    filecheckp = subparsers.add_parser('filecheck', description='check attached file(s)',
        parents=[cfg, namefmt])
    # filecheckp.add_argument('-f','--force', action='store_true',
    #     help='do not ask before performing actions')

    # action on files
    filecheckp.add_argument('-r','--rename', action='store_true',
        help='rename files')
    filecheckp.add_argument('-c','--copy', action='store_true',
        help='in combination with --rename, keep a copy of the file in its original location')

    # various metadata and duplicate checks
    filecheckp.add_argument('--metadata-check', action='store_true',
        help='parse pdf metadata and check against metadata (currently doi only)')

    filecheckp.add_argument('--hash-check', action='store_true',
        help='check file hash sum to remove any duplicates')

    filecheckp.add_argument('-d', '--delete-broken', action='store_true',
        help='remove file entry if the file link is broken')

    filecheckp.add_argument('--clean-filesdir', action='store_true',
        help='remove files in filesdir if not referred to in any entry')

    filecheckp.add_argument('--fix-mendeley', action='store_true',
        help='fix a Mendeley bug where the leading "/" is omitted.')

    filecheckp.add_argument('--force', action='store_true', help='no interactive prompt, strictly follow options')
    # filecheckp.add_argument('--search-for-files', action='store_true',
    #     help='search for missing files')
    # filecheckp.add_argument('--searchdir', nargs='+',
    #     help='search missing file link for existing bibtex entries, based on doi')
    # filecheckp.add_argument('-D', '--delete-free', action='store_true',
        # help='delete file which is not associated with any entry')
    # filecheckp.add_argument('-a', '--all', action='store_true', help='--hash and --meta')

    # list
    # ======
    listp = subparsers.add_parser('list', description='list (a subset of) entries in the existing bib file',
        parents=[cfg])

    listp.add_argument('fullsearch', nargs='*', help='''Search field. Usually no quotes required. See keywords to search specific fields. All words must find a match, unless --any is passed.''')

    mgrp = listp.add_mutually_exclusive_group()
    mgrp.add_argument('--strict', action='store_true', help='exact matching - instead of substring')
    mgrp.add_argument('--fuzzy', action='store_true', help='fuzzy matching - instead of substring')
    listp.add_argument('--fuzzy-ratio', type=int, default=50, help='threshold for fuzzy matching of title, author, abstract (default:%(default)s)')
    listp.add_argument('--similarity', choices=['EXACT','GOOD','FAIR','PARTIAL','FUZZY'], default=DEFAULT_SIMILARITY, help='duplicate testing (default:%(default)s)')
    listp.add_argument('--invert', action='store_true', help='list the entries that do not match')
    listp.add_argument('--any', action='store_true', help='when several keywords: any of them')

    grp = listp.add_argument_group('search')
    grp.add_argument('-a','--author', nargs='+', help='any of the authors')
    grp.add_argument('--first-author', nargs='+', help='family name of the first author')
    grp.add_argument('-y','--year', nargs='+', help='year')
    grp.add_argument('-t','--title', help='title', nargs="+")
    grp.add_argument('--abstract', help='abstract', nargs="+")
    grp.add_argument('-k', '--key', '--id', nargs='+', help='entry key')
    grp.add_argument('--doi', nargs='+', help='DOI')
    grp.add_argument('--keywords', '--tag', nargs='+', help='keywords (tags)')


    grp = listp.add_argument_group('check')
    grp.add_argument('--duplicates-key', action='store_true', help='list key duplicates only')
    grp.add_argument('--duplicates-doi', action='store_true', help='list doi duplicates only')
    grp.add_argument('--duplicates-tit', action='store_true', help='list title duplicates only')
    grp.add_argument('--duplicates', action='store_true', help='list all duplicates (see --similarity)')
    grp.add_argument('--has-file', action='store_true', help='entries with at least one file')
    grp.add_argument('--no-file', action='store_true', help='entries without file')
    grp.add_argument('--broken-file', action='store_true', help='entries with a file link to a missing file')
    grp.add_argument('--review-required', action='store_true', help='suspicious entry (invalid dois, missing field etc.)')

    grp = listp.add_argument_group('formatting')
    mgrp = grp.add_mutually_exclusive_group()
    mgrp.add_argument('--plain', action='store_false', dest="one_liner", help='print in bibtex format')
    mgrp.add_argument('-l', '-1', '--one-liner', action='store_true', help='one liner')
    mgrp.add_argument('--key-only', action='store_true', help='print the keys only (one per line)')
    mgrp.add_argument('-f', '--field', nargs='+', help='specific field(s) only')
    grp.add_argument('--no-key', action='store_true', help='do not print the keys')

    grp = listp.add_argument_group('action on listed results (pipe)')
    grp.add_argument('--delete', action='store_true', help='delete the listed entries (their files are kept)')
    grp.add_argument('-e', '--edit', action='store_true', help='interactive edit text file with entries, and re-insert them')
    grp.add_argument('--fetch', action='store_true', help='fetch and fix metadata')
    grp.add_argument('--add-keywords', '--add-tag', nargs='+', help='add keywords to the selected entries')
    grp.add_argument('--add-files', nargs='+', type=file_uri_to_path, help='add files to the selected entries (only one entry must be listed)')
    grp.add_argument('--rename', action='store_true', help='rename file(s) of the listed entries into the files folder (also applies to files added via --add-files)')
    grp.add_argument('--copy', action='store_true', help='in combination with --rename, keep a copy of the file(s) in their original location')
    grp.add_argument('-o', '--open', action='store_true', help='open attachments (if any)')

    # grp.add_argument('--merge-duplicates', action='store_true')


    # open
    # ====
    openp = subparsers.add_parser('open', description='open entry attachments or files with the system viewer', parents=[cfg])
    openp.add_argument('key', nargs='+', type=file_uri_to_path, help='entry key(s) (case-insensitive), or existing file path(s) to open directly')

    # doi
    # ===
    doip = subparsers.add_parser('doi', description='parse DOI from PDF', parents=[loggingp])
    doip.add_argument('pdf', type=file_uri_to_path)
    doip.add_argument('--image', action='store_true', help='convert to image and use tesseract instead of pdftotext')

    # fetch
    # =====
    fetchp = subparsers.add_parser('fetch', description='fetch bibtex from DOI or full-text', parents=[loggingp])
    fetchp.add_argument('doi_or_text', nargs='+', help='DOI or full text.')
    fetchp.add_argument('--scholar', action='store_true', help='use google scholar instead of default crossref for fulltext search')

    # extract
    # ========
    extractp = subparsers.add_parser('extract', description='extract pdf metadata', parents=[loggingp])
    extractp.add_argument('pdf', nargs='+', type=file_uri_to_path, help='one or several PDF files')
    extractp.add_argument('--recursive', action='store_true', help='accept directories and scan them for PDF files')
    extractp.add_argument('-n', '--word-count', type=int, default=200)
    extractp.add_argument('--fulltext', action='store_true', help='fulltext only (otherwise DOI-based)')
    extractp.add_argument('--scholar', action='store_true', help='use google scholar instead of default crossref for fulltext search')
    extractp.add_argument('--image', action='store_true', help='convert to image and use tesseract instead of pdftotext')

    # *** Pure OS related file checks ***

    # undo
    # ====
    _restorep = argparse.ArgumentParser(add_help=False)
    _restorep.add_argument('--restore-files', action='store_true', help='Use this option to restore files that have been renamed. By default the file link points to the back-up repository. This command has no effect without --git-lfs, and will result in broken file links.')

    _stepsp = argparse.ArgumentParser(add_help=False)
    _stepsp.add_argument('-n', '--steps', type=int, default=1, help='number of times undo/redo should be performed')

    undop = subparsers.add_parser('undo', parents=[cfg, _restorep, _stepsp], help='Undo changes on bibtex (if --git is not enabled, only back and forth with last modification). If --git-lfs is enabled, the file entry may differ if it does not exist on disk any more, unless --restore-files was passed.')
    redop = subparsers.add_parser('redo', parents=[cfg, _restorep, _stepsp], help='Redo changes on bibtex (if --git is not enabled, this has the same effect as papers undo)')
    restorep = subparsers.add_parser('restore-backup', parents=[cfg, _restorep], help='Restore bibtex from backup. Also restore files if --restore-files if passed (--git-lfs only).')
    restorep.add_argument('--ref', help='Optional: restore specific commit (execute `papers git whatchanged` to obtain appropriate reference)')

    # git
    # ===
    gitp = subparsers.add_parser('git', description='git subcommand')
    gitp.add_argument('gitargs', nargs=argparse.REMAINDER)

    # backup
    # ======
    backupp = subparsers.add_parser('backup', description='manage backup directories', parents=[loggingp])
    backupp.add_argument('action', nargs='?', choices=['list', 'remove'], default='list',
        help='list (default) known backup directories and the library each belongs to, or remove them')
    backupp.add_argument('patterns', nargs='*', metavar='name',
        help='directory name(s), glob patterns allowed (filter for list, required for remove)')
    backupp.add_argument('-f', '--force', action='store_true', help='remove without confirmation')

    return parser, subparsers

#############
# Main script
#############

def handle_logging(o):
    # verbosity
    if getattr(o,'logging_level',None):
        logger.setLevel(o.logging_level)
    logger.debug("LOGGER LEVEL: "+logging.getLevelName(logger.getEffectiveLevel()))


# set while handing files to the system viewer, to detect a passthrough loop (#107)
VIEWER_PASSTHROUGH_ENV = 'PAPERS_CLI_VIEWER_PASSTHROUGH'


def _pop_directory_options(argv):
    """the directory of the -C DIR options before the command name (several
    -C combine as in git), and the remaining arguments"""
    directory = None
    while argv and argv[0].startswith('-C'):
        if argv[0] == '-C':
            if len(argv) < 2:
                raise PapersExit('-C requires a directory')
            d, argv = argv[1], argv[2:]
        else:
            d, argv = argv[0][2:], argv[1:]
        directory = os.path.join(directory, d) if directory else d
    return directory, argv


def main(args=None):
    papers.config.DRYRUN = False  # reset in case main() if called directly
    if args is not None:
        # used in the commit message
        sys.argv = sys.argv[:1] + args

    directory, argv = _pop_directory_options(sys.argv[1:])
    if directory is None:
        return _main(argv)
    if not os.path.isdir(directory):
        raise PapersExit(f'-C {directory}: not a directory')
    with set_directory(directory):
        return _main(argv)


def _main(argv):
    check_legacy_global_config()
    config = find_config()

    installed = config.file is not None

    parser, subparsers = get_parser(config)

    # viewer passthrough (#107): this command often masks the GNOME Papers
    # document viewer in $PATH. Its desktop entry runs `papers %U`, so file
    # managers and xdg-open land here with file paths or file:// URIs. When
    # every argument is an existing file, the call is handed over unchanged
    # to the masked viewer (the next `papers` on $PATH that is not this tool).
    # xdg-open is only a fallback when there is no such viewer: it resolves
    # the desktop entry, which may lead back to this command, hence the
    # environment guard against a loop. Subcommand names always take
    # precedence, and any flag disables the passthrough (it cannot be meant
    # for this tool).
    if argv and all(not a.startswith('-') for a in argv) \
            and argv[0] not in subparsers.choices \
            and all(os.path.isfile(file_uri_to_path(a)) for a in argv):
        viewer = find_masked_viewer()
        if viewer:
            print(f"papers-cli: passing {' '.join(map(repr, argv))} to {viewer} "
                  f"(see `papers --help` for the bibliography tool)", file=sys.stderr)
            os.execv(viewer, [viewer] + argv)
            return  # only reached when os.execv is mocked
        if os.environ.get(VIEWER_PASSTHROUGH_ENV):
            raise PapersExit("the system viewer for these files leads back to this "
                             "command, and no other `papers` viewer is in $PATH")
        os.environ[VIEWER_PASSTHROUGH_ENV] = '1'  # inherited by the viewer
        for a in argv:
            f = file_uri_to_path(a)
            print(f"papers-cli: opening {f!r} with the system viewer "
                  f"(see `papers --help` for the bibliography tool)", file=sys.stderr)
            view_pdf(f)
        return

    o, args = parser.parse_known_args(argv)

    if o.version:
        print(__version__)
        return

    handle_logging(o)

    if os.path.exists(CONFIG_FILE) and o.cmd != 'migrate':
        logger.warning(f"found the global configuration of papers v2 ({CONFIG_FILE}): it still applies "
                       "outside of libraries; `papers migrate` turns it into a library and the default pool")

    # modify disk state?
    if hasattr(o,'dry_run'):
        papers.config.DRYRUN = o.dry_run

    try:
        subp = subparsers.choices[o.cmd]
    except KeyError:
        parser.print_help()
        raise PapersExit()

    # arguments are already parsed, but we can now process error message
    # with subparser:
    if args:
        subp.parse_args(args)

    if o.cmd == 'status':
        return statuscmd(subp, o, config)

    if o.cmd == 'init':
        initcmd(subp, o, config)
    elif o.cmd == 'config':
        configcmd(subp, o, config)
    elif o.cmd == 'migrate':
        migratecmd(subp, o, config)
    elif o.cmd == 'install':
        installcmd(subp, o, config)
    elif o.cmd == 'uninstall':
        if not installed:
            subp.error('no library configuration was found')
        if o.recursive:
            logger.warning("uninstall --recursive is deprecated: remove the configuration of each library instead")
        uninstallcmd(subp, o, config)
        print(config.status(verbose=True))
    elif o.cmd == 'add':
        addcmd(subp, o, check_install(subp, o, config))
    elif o.cmd == 'check':
        checkcmd(subp, o, check_install(subp, o, config))
    elif o.cmd == 'filecheck':
        filecheckcmd(subp, o, check_install(subp, o, config))
    elif o.cmd == 'list':
        listcmd(subp, o, check_install(subp, o, config))
    elif o.cmd == 'open':
        # no install required when opening plain files; opencmd reports the
        # missing bibliography itself when an argument must be looked up as a key
        opencmd(subp, o, config)
    elif o.cmd == 'undo':
        undocmd(subp, o, check_install(subp, o, config))
    elif o.cmd == 'redo':
        redocmd(subp, o, check_install(subp, o, config))
    elif o.cmd == 'restore-backup':
        restorecmd(subp, o, check_install(subp, o, config, bibtex_must_exist=False))
    elif o.cmd == 'git':
        if not installed:
            subp.error('papers must be installed to use git command')
        gitcmd(subp, o, config)
    elif o.cmd == 'backup':
        backupcmd(subp, o, config)
    elif o.cmd == 'doi':
        doicmd(subp, o)
    elif o.cmd == 'fetch':
        fetchcmd(subp, o)
    elif o.cmd == 'extract':
        extractcmd(subp, o)
    else:
        parser.print_help()
        raise PapersExit()
        # parser.exit(1)


def main_clean_exit(args=None):
    try:
        main(args)
    except (PapersExit, DuplicateKeyError) as error:
        if logger.getEffectiveLevel() == logging.DEBUG:
            raise
        if error.args:
            logger.error(str(error))
        sys.exit(1)

if __name__ == "__main__":
    # we use try/except here to use a clean exit instead of trace
    # test and debugging may use main() directly for speed-up => better to avoid sys.exit there
    main_clean_exit()