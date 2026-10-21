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
import fnmatch   # unix-like match

import papers
from papers import logger
from papers.extract import extract_pdf_doi, isvaliddoi, extract_pdf_metadata, prefetch_pdf_metadata
from papers.extract import fetch_bibtex_by_doi, fetch_bibtex_by_fulltext_crossref, fetch_bibtex_by_fulltext_scholar
from papers.encoding import parse_file, format_file, family_names, format_entries, standard_name, format_entry, parse_keywords, format_key
from papers.config import (Config, CONFIG_FILE, CONFIG_FILE_LOCAL, LIBRARY_CONFIG_FILES,
                           SETTINGS, LIBRARY_ONLY, parse_value, format_value, is_pool_path, short_home)
from papers.duplicate import edit_entries, duplicate_groups, fuzzy_pairs, FUZZY_RATIO
from papers.merge import Resolver, DuplicateError, ON_DUPLICATE
from papers.entries import get_entry_val, entry_content_equal, entry_from_dict
from papers.bib import (backupfile as backupfile_func, isvalidkey, DuplicateKeyError, clean_filesdir,
                        download_url, scan_dir_items, hidden_bibtex)
from papers.install import (resolve_install, apply_install, _ask_path, RESET_WORDS,
                            InputAsker, DefaultAsker)
from papers.utils import bcolors, search_config, view_pdf, open_folder, PapersExit, file_uri_to_path, find_masked_viewer, set_directory
from papers.identifiers import read_selection, select_entries, ACCEPTED as ENTRY_IDS
from papers.files import (FilesPolicy, realpath, is_download, plan_moves, link_snapshot,
                          moved_links, execute_moves, files_to_delete, describe_file, delete_files,
                          check_entry_files)
from papers.pools import (Pools, Exchange, PoolLookup, use_pool_files, report_lines,
                          export, status_lines, machine_pool_lines, pool_path_setting, library_config_file)
from papers.library import (check_legacy_global_config, check_legacy_config, find_config,
                            config_for_bibtex, get_biblio, savebib, convert_file_links, snapshot_backup)
from papers.migrate import migrate_v2_global, migrate_folders
from papers.backup import (init_backup, restore_from_backupdir,
                           git_undo, git_redo, git_restore_state, list_backup_dirs)
from papers import __version__


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
                         "links and the files too: use `papers migrate --light` or `papers migrate --full`")
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


def init_hint(config):
    "how to create a library, here or for the default pool"
    pool = short_home(config.machine.pool_path('default'))
    return f"Create a library with `papers init` (here) or `papers init {pool}` (the default pool)"


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


def files_mode(o, config):
    """the files mode of the command line (--move or -r/--rename, --copy,
    --link), else the `files` setting. Without files directory, files can
    only be linked where they are."""
    if getattr(o, 'link', False) and (getattr(o, 'move', False) or getattr(o, 'rename', False)
                                      or getattr(o, 'copy', False)):
        raise PapersExit('--link excludes --move, -r/--rename and --copy')
    if getattr(o, 'copy', False):
        mode = 'copy'
    elif getattr(o, 'link', False):
        mode = 'link'
    elif getattr(o, 'move', False) or getattr(o, 'rename', False):
        mode = 'move'
    else:
        mode = config.files or 'move'
        if config.filesdir is None:
            return 'link'
    if config.filesdir is None and mode != 'link':
        raise PapersExit(f'--{mode}: the library has no files directory (pass --filesdir, '
                         'or set it with `papers config filesdir DIR`)')
    return mode


def files_policy(config, mode, keep=()):
    "what to do with each file, see papers.files.FilesPolicy"
    pool_dirs = Pools(config).files_dirs()
    # files placed in the pool by a light library (see papers.pools.use_pool_files)
    light = config.light and any(realpath(config.filesdir or '') == realpath(d) for d in pool_dirs)
    return FilesPolicy(mode, config.filesdir, current_config=config.file, machine=config.machine, keep=keep,
                       pool_dirs=pool_dirs, light=light)


# v2 letters of -m/--mode, and the --on-duplicate word they map to
ADD_MODES = {'i': 'ask', 'u': 'keep', 'U': 'update', 'o': 'update', 's': 'skip', 'r': 'error'}
CHECK_MODES = {'i': 'ask', 'm': 'keep', 's': 'skip'}


def on_duplicate_mode(o, cmd):
    """the --on-duplicate word of the command line: the option, else the
    deprecated -m/--mode letter, else ask in a terminal and error otherwise
    (check --force: skip)"""
    mode = o.on_duplicate
    if o.mode is not None:
        if cmd == 'add' and o.mode == 'a':
            logger.warning('-m/--mode a is deprecated: use --no-check-duplicate')
            o.no_check_duplicate = True
        else:
            new = (ADD_MODES if cmd == 'add' else CHECK_MODES)[o.mode]
            note = {'o': ' (the key and the fields only in the library are now kept)',
                    's': ' (the file of the added entry is no longer attached; keep does that)'}.get(o.mode, '') \
                if cmd == 'add' else ''
            logger.warning(f'-m/--mode {o.mode} is deprecated: use --on-duplicate {new}{note}')
            if mode is None:
                mode = new
    if mode is None:
        if cmd == 'check' and o.force:
            mode = 'skip'
        else:
            mode = 'ask' if stdin_is_terminal() else 'error'
    return mode


def duplicate_resolver(o, cmd):
    return Resolver(on_duplicate_mode(o, cmd), color=sys.stdout.isatty())


def addcmd(parser, o, config):
    """
    Given an options set and a config, sets up the function call to add the file or all files in the directory to the bibtex, and executes it.
    """

    set_nameformat_config_from_cmd(o, config)
    set_keyformat_config_from_cmd(o, config)

    pools = Pools(config)
    if config.light:
        use_pool_files(config, pools)  # files go to the first pool
    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)
    exchange = Exchange(config, biblio, pools)
    if not o.no_pool:
        lookup = PoolLookup(exchange)
        biblio.pool_lookup = lookup if lookup else None

    entries = []

    if o.attachment_deprecated:
        logger.warning("--attachment is deprecated: use --attach")
        o.attachment = (o.attachment or []) + o.attachment_deprecated

    # what to do with the files: see papers.files.FilesPolicy
    mode = files_mode(o, config)
    policy = files_policy(config, mode)
    rename = mode != 'link'

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
            # downloaded attachments live in a tempdir: they are moved into
            # the files directory whatever the mode (see FilesPolicy)
            rename = True
        metadata['file'] = format_file(biblio.get_files(metadata) + o.attachment, relative_to=biblio.relative_to)

    if len(o.file) > 1:
        if metadata:
            logger.error('--doi, --metadata, --key, --attachment and other metadata keys are only valid for one PDF / BIBTEX entry')
            raise PapersExit()

    if o.no_merge_files:
        logger.warning('--no-merge-files is deprecated and ignored: the file links of duplicates are always merged')
    resolver = duplicate_resolver(o, 'add')
    kw = {'on_duplicate':resolver, 'check_duplicate':not o.no_check_duplicate,
            'update_key':o.update_key, 'metadata':metadata}

    if len(o.file) == 0 and o.doi and not o.no_query_doi:
        entries.extend( biblio.fetch_doi(o.doi, attachments=o.attachment, rename=rename, copy=policy, **kw) )

    elif len(o.file) == 0:
        if not o.edit and not o.metadata and not o.key and not o.doi and not o.attachment and not o.title and not o.author and not o.journal and not o.year:
            logger.error("No entry added: use --doi, --metadata, --key, --attachment, --title, --author, --journal, --year to add a new entry")
            raise PapersExit()

        metadata.setdefault('ID', biblio.keyformat(metadata))
        metadata.setdefault('ENTRYTYPE', 'article')
        if o.edit:
            metadata = edit_entries(metadata)
            o.edit = False

        entries.extend( biblio.insert_entry(entry_from_dict(metadata), rename=rename, copy=policy, **kw) )


    # several PDFs: fetch their metadata concurrently first
    if not o.doi and not o.scholar and not (o.no_query_doi and o.no_query_fulltext):
        pdfs = []
        for file in o.file:
            if os.path.isdir(file) and o.recursive:
                pdfs.extend(path for kind, path, _ in scan_dir_items(file, quiet=True) if kind == 'file' and path.lower().endswith('.pdf'))
            elif os.path.isfile(file) and file.lower().endswith('.pdf'):
                pdfs.append(file)
        if biblio.pool_lookup:
            pdfs = [pdf for pdf in pdfs if not biblio.pool_lookup.has_file(pdf)]
        if len(pdfs) > 1:
            prefetch_pdf_metadata(pdfs, search_doi=not o.no_query_doi, search_fulltext=not o.no_query_fulltext)

    for file in o.file:
        try:
            if os.path.isdir(file):
                if o.recursive:
                    entries.extend( biblio.scan_dir(file, rename=rename, copy=policy,
                                search_doi=not o.no_query_doi,
                                search_fulltext=not o.no_query_fulltext,
                                **kw) )
                else:
                    raise ValueError(file+' is a directory, requires --recursive to explore')

            elif file.lower().endswith('.pdf'):
                entries.extend( biblio.add_pdf(file, attachments=o.attachment, rename=rename, copy=policy,
                           search_doi=not o.no_query_doi,
                           search_fulltext=not o.no_query_fulltext,
                           scholar=o.scholar, doi=o.doi,
                           **kw) )

            else: # file.endswith('.bib'):
                entries.extend( biblio.add_bibtex_file(file, attachments=o.attachment, rename=rename, copy=policy, **kw) )

        except (EOFError, DuplicateError):
            raise  # a question without answer, or --on-duplicate error, stops the command (see main_clean_exit)
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

    # light library or sync push: also in the first pool
    before = {biblio.key(e) for e in biblio_init.entries}
    added = {get_entry_val(e, 'ID', '').lower() for e in entries}
    pushed = exchange.push_added([e for e in biblio.entries if biblio.key(e) in added],
                                 [e for e in biblio.entries if biblio.key(e) not in before], resolver)
    if pushed:
        print('\n'.join(report_lines(pushed, f'push to {pushed[0][1].label}')))
    save_exchange(exchange)

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

    selection = list(o.entries) + list(o.keys or [])
    entries = select_entries(biblio, selection) if selection else list(biblio.entries)
    for e in entries:
        biblio.fix_entry(e, fix_doi=o.fix_doi, fetch=o.fetch, fetch_all=o.fetch_all, fix_key=o.fix_key,
                     auto_key=o.auto_key, format_name=o.format_name, encoding=o.encoding,
                     key_ascii=o.key_ascii, interactive=not o.force)


    if o.duplicates:
        biblio.check_duplicates(on_duplicate=duplicate_resolver(o, 'check'))
    elif o.on_duplicate or o.mode:
        logger.warning('--on-duplicate and -m/--mode only apply with --duplicates')

    savebib(biblio, config)

def filecheckcmd(parser, o, config):
    """deprecated: the options of filecheck run the `papers file` subcommands"""
    check = o.fix_mendeley or o.hash_check or o.metadata_check or not (o.delete_broken or o.rename or o.clean_filesdir)
    new = []
    if check:
        new.append('papers file check' + (' --metadata' if o.metadata_check else '')
                   + (' --fix' if o.fix_mendeley or o.hash_check else ''))
    if o.delete_broken:
        new.append('papers file detach --broken')
    if o.rename:
        new.append('papers file rename' + (' --keep-source' if o.copy else ''))
    if o.clean_filesdir:
        new.append('papers file clean' + (' --yes' if o.force else ''))
    logger.warning(f"`papers filecheck` is deprecated: use {' and '.join('`'+cmd+'`' for cmd in new)}")

    set_nameformat_config_from_cmd(o, config)
    biblio = get_biblio(config)

    if check:
        for e in biblio.entries:
            for line in check_entry_files(biblio, e, metadata=o.metadata_check, fix=o.fix_mendeley or o.hash_check):
                print(line)

    if o.delete_broken:
        for e in biblio.entries:
            detach_links(biblio, e, [f for f in biblio.get_files(e) if not os.path.exists(f)])

    if o.rename:
        rename_files(biblio, biblio.entries, config, keep_source=o.copy)

    if o.clean_filesdir:
        print("Check files directory for unlinked files")
        clean_filesdir(biblio, interactive=not o.force, ignore_files=[config.bibtex])

    savebib(biblio, config)


# papers file
# ===========

def _entries_or_all(biblio, args):
    "the entries named on the command line (keys, DOIs, -), or all entries without argument"
    return select_entries(biblio, args) if args else list(biblio.entries)


def _one_entry(biblio, key):
    entries = select_entries(biblio, [key])
    if len(entries) != 1:
        raise PapersExit(f"{key}: give one entry ({len(entries)} given)")
    return entries[0]


def rename_files(biblio, entries, config, keep_source=False):
    """place the files of the entries in the files directory, under their
    template name (a file that belongs to another library is copied, see
    FilesPolicy)"""
    if config.filesdir is None:
        raise PapersExit('the library has no files directory: pass --filesdir, '
                         'or set it with `papers config filesdir DIR`')
    policy = files_policy(config, 'copy' if keep_source else 'move')
    for e in entries:
        try:
            biblio.rename_entry_files(e, copy=policy)
        except Exception as error:
            logger.error(f"{get_entry_val(e, 'ID', '')}: {error}")


def attach_files(biblio, e, files, config, mode):
    """add files to the links of an entry, and place them as the files mode
    says (the files the entry had stay where they are)"""
    old = biblio.get_files(e)
    new = []
    for f in files:
        if str(f).startswith("http://") or str(f).startswith("https://"):
            new.append(download_url(f, expect_pdf=False))  # moved into the files directory
        elif not os.path.exists(f):
            raise PapersExit(f"file {f} does not exist")
        else:
            new.append(os.path.abspath(f))
    biblio.set_files(e, old + new)
    if mode != 'link' or any(is_download(f) for f in new):
        biblio.rename_entry_files(e, copy=files_policy(config, mode, keep=old))


def detach_links(biblio, e, files):
    "remove links from an entry (files are compared by real path)"
    remove = {realpath(f) for f in files}
    biblio.set_files(e, [f for f in biblio.get_files(e) if realpath(f) not in remove])


def file_renamecmd(parser, o, config):
    set_nameformat_config_from_cmd(o, config)
    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)
    entries = _entries_or_all(biblio, o.entries)
    rename_files(biblio, entries, config, keep_source=o.keep_source)
    savebib(biblio, config)
    _print_biblio_diff(biblio_init, biblio, entries)


def file_mvcmd(parser, o, config):
    if len(o.paths) < 2:
        parser.error('papers file mv SRC... DEST')
    *sources, dest = o.paths
    biblio = get_biblio(config)
    moves = plan_moves(biblio, sources, dest, force=o.force, protected=[config.bibtex, config.file])
    snapshot = link_snapshot(biblio)

    def _filesdir(moves):
        "the new files directory, if it moves"
        if config.filesdir is None or o.filesdir is not None:
            return None
        return next(filter(None, (m.new_path(realpath(config.filesdir)) for m in moves)), None)

    if papers.config.DRYRUN:
        for m in moves:
            print(f"DRYRUN: mv {m.src} {m.target}")
        for e, old, new in moved_links(snapshot, moves):
            for a, b in zip(old, new):
                if a != b:
                    print(f"DRYRUN: {get_entry_val(e, 'ID', '')}: {a} -> {b}")
        if _filesdir(moves):
            print(f"DRYRUN: filesdir = {_filesdir(moves)}")
        return

    done, error = execute_moves(moves, force=o.force)
    changes = moved_links(snapshot, done)
    for e, old, new in changes:
        biblio.set_files(e, new)
    savebib(biblio, config)
    filesdir = _filesdir(done)
    if filesdir:
        config.filesdir = filesdir
        if config.file:
            config.save()
            print(f"filesdir = {config._relpath(filesdir)} (in {config.file})")
    print(f"moved {len(done)} of {len(moves)} file(s) or folder(s), {len(changes)} entries updated")
    if error:
        raise PapersExit(f"{error}: the links of the files moved before were saved")


def file_attachcmd(parser, o, config):
    set_nameformat_config_from_cmd(o, config)
    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)
    e = _one_entry(biblio, o.key)
    attach_files(biblio, e, o.files, config, files_mode(o, config))
    savebib(biblio, config)
    _print_biblio_diff(biblio_init, biblio, [e])


def file_detachcmd(parser, o, config):
    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)
    if o.broken:
        entries = _entries_or_all(biblio, o.args)
        detached = {id(e): [f for f in biblio.get_files(e) if not os.path.exists(f)] for e in entries}
    else:
        if not o.args:
            parser.error('papers file detach KEY [FILE...] (or --broken [KEY...])')
        key, *files = o.args
        e = _one_entry(biblio, key)
        linked = biblio.get_files(e)
        if files:
            by_real = {realpath(f): f for f in linked}
            unknown = [f for f in files if realpath(f) not in by_real]
            if unknown:
                raise PapersExit(f"not linked from {key}: {', '.join(unknown)} (nothing was changed)")
            files = [by_real[realpath(f)] for f in files]
        else:
            files = linked
        entries = [e]
        detached = {id(e): files}

    for e in entries:
        detach_links(biblio, e, detached[id(e)])

    alldetached = [f for e in entries for f in detached[id(e)]]
    if o.delete_files:
        inside, outside, kept, in_pool = files_to_delete(biblio, alldetached, config.filesdir,
                                                         pool_dirs=Pools(config).files_dirs())
    savebib(biblio, config)
    _print_biblio_diff(biblio_init, biblio, entries)
    if o.delete_files:
        print_kept_files(kept, in_pool)
        delete_files(inside + outside, dryrun=papers.config.DRYRUN)


def file_checkcmd(parser, o, config):
    biblio = get_biblio(config)
    entries = _entries_or_all(biblio, o.entries)
    issues = []
    # broken links to pool files (repaired on load in a light library)
    selected = {id(e) for e in entries}
    repaired = [r for r in getattr(biblio, 'repaired_links', []) + Exchange(config, biblio).repair_links(entries)
                if id(r[0]) in selected]
    for e, old, new in repaired:
        gone = [f for f in old if f not in new]
        issues.append(f"{e.key}: broken link to a pool file: {';'.join(gone)} -> the pool's file "
                      f"{';'.join(f for f in new if f not in old)} ({'fixed' if o.fix else 'fix with --fix'})")
    for e in entries:
        issues.extend(check_entry_files(biblio, e, metadata=o.metadata, fix=o.fix))
    for line in issues:
        print(line)
    if issues:
        print(f"{len(issues)} issue(s) in the files of {len(entries)} entries")
    else:
        print(f"no issue found in the files of {len(entries)} entries")
    if o.fix and issues:
        savebib(biblio, config)


def file_cleancmd(parser, o, config):
    biblio = get_biblio(config)
    if config.filesdir is None:
        raise PapersExit('the library has no files directory')
    removed = clean_filesdir(biblio, interactive=not o.yes, ignore_files=[config.bibtex])
    print(f"{'DRYRUN: ' if papers.config.DRYRUN else ''}removed {len(removed)} unlinked file(s) "
          f"from {config.filesdir}")


# papers pull, push, export, pool
# ===============================

def save_exchange(exchange):
    """save what an exchange with the pools changed: the pools pushed to,
    the pairs that are not the same paper of the other pools, the origin
    records, and the library"""
    for pool in exchange.changed_pools:
        savebib(pool.biblio, pool.config)
        exchange.after_push(pool)
    if not papers.config.DRYRUN:
        for pool in exchange.pools.all(quiet=True):
            if pool._biblio is not None and not any(pool is p for p in exchange.changed_pools):
                pool.biblio.distinct.save()
    exchange.origin.save()
    savebib(exchange.biblio, exchange.config)


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
    """the pools of the per-machine configuration (as `papers config
    --machine pools.NAME`), and the pools of the library"""
    machine = config.machine
    if o.pool_cmd in (None, 'list'):
        print(f'pools of this machine ({machine.file}):')
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


# papers edit, rm, tag
# ====================

def stdin_is_terminal():
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError, OSError):
        return False


def edit_selected(biblio, entries):
    "edit entries in a text editor, and put them back in the bibliography; False on failure"
    others = [e for e in biblio.db.entries if not any(e is x for x in entries)]
    try:
        edited = edit_entries(entries)
    except Exception as error:
        logger.error(str(error))
        return False
    biblio.entries = others + edited
    return True


def remove_entries(biblio, entries, config, delete_files=None, ask=True):
    """remove entries from the bibliography, and return the files to delete
    once the bibliography is saved.

    Candidates are the files of the removed entries that no remaining entry
    links to. delete_files=True deletes them all; False keeps them; None
    asks, in a terminal (ask=True), whether to delete those inside the files
    directory, and keeps them without a terminal. A file outside the files
    directory is only deleted with delete_files=True.
    """
    files = [f for e in entries for f in biblio.get_files(e)]
    for e in entries:
        biblio.db.remove(e)
    inside, outside, kept, in_pool = files_to_delete(biblio, files, config.filesdir,
                                                     pool_dirs=Pools(config).files_dirs())
    if delete_files is False:
        return []
    print_kept_files(kept, in_pool)
    if delete_files:
        return inside + outside
    if outside:
        print(f"kept {len(outside)} file(s) outside the files directory (`--delete-files` deletes them):")
        for f in outside:
            print(f"  {f}")
    if not inside:
        return []
    if ask and stdin_is_terminal():
        print("files of the removed entries that no other entry links to:")
        for f in inside:
            print(f"  {describe_file(f)}")
        if input(f"also delete {len(inside)} file(s)? [y/N] ").lower() in ('y', 'yes'):
            return inside
        return []
    print(f"kept {len(inside)} file(s) of the removed entries in the files directory:")
    for f in inside:
        print(f"  {f}")
    print("delete them with `papers file clean`, or remove the entries with `--delete-files`")
    return []


def print_kept_files(kept, in_pool):
    for f in kept:
        print(f"kept {f}: another entry links to it")
    for f in in_pool:
        print(f"kept {f}: it is a file of a pool")


def _delete_files_option(parser, o):
    if o.delete_files and o.keep_files:
        parser.error('--delete-files and --keep-files are mutually exclusive')
    return True if o.delete_files else (False if o.keep_files else None)


def tag_counts(entries):
    counts = {}
    for e in entries:
        for tag in parse_keywords(e):
            counts[tag] = counts.get(tag, 0) + 1
    return counts


def set_tags(e, tags):
    "write the tags in the keywords field (comma-separated), removing it when empty"
    if tags:
        e['keywords'] = ", ".join(tags)
    elif get_entry_val(e, 'keywords', None) is not None:
        del e['keywords']


def add_tags(entries, tags):
    for e in entries:
        old = parse_keywords(e)
        new = old + [t for i, t in enumerate(tags) if t not in old and t not in tags[:i]]
        if new != old:
            set_tags(e, new)


def remove_tags(entries, tags):
    for e in entries:
        old = parse_keywords(e)
        new = [t for t in old if t not in tags]
        if new != old:
            set_tags(e, new)


def rename_tag(entries, old, new):
    "rename a tag in all entries; return the number of entries changed"
    count = 0
    for e in entries:
        tags = parse_keywords(e)
        if old not in tags:
            continue
        renamed = []
        for t in tags:
            t = new if t == old else t
            if t not in renamed:
                renamed.append(t)
        set_tags(e, renamed)
        count += 1
    return count


def editcmd(parser, o, config):
    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)
    entries = select_entries(biblio, o.entries)
    if not entries:
        return
    if '-' in o.entries and not stdin_is_terminal():
        # the keys came from a pipe: the editor reads the terminal
        try:
            fd = os.open('/dev/tty', os.O_RDONLY)
            os.dup2(fd, 0)
            os.close(fd)
        except OSError:
            pass
    if edit_selected(biblio, entries):
        savebib(biblio, config)
        _print_biblio_diff(biblio_init, biblio, biblio.entries)


def rmcmd(parser, o, config):
    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)
    entries = select_entries(biblio, o.entries)
    todelete = remove_entries(biblio, entries, config, delete_files=_delete_files_option(parser, o),
                              ask='-' not in o.entries)
    savebib(biblio, config)
    _print_biblio_diff(biblio_init, biblio, entries)
    delete_files(todelete, dryrun=papers.config.DRYRUN)


def tagcmd(parser, o, config):
    biblio = get_biblio(config)
    biblio_init = copy.deepcopy(biblio)
    if o.rename:
        if o.entries or o.add or o.rm:
            parser.error('--rename OLD NEW applies to the whole library: no KEY, --add or --rm')
        old, new = o.rename
        count = rename_tag(biblio.entries, old, new)
        savebib(biblio, config)
        print(f"renamed tag {old} to {new} in {count} entries")
        return

    if o.add or o.rm:
        if not o.entries:
            parser.error('--add and --rm need the entries: KEY..., or - to read them from the standard input')
        entries = select_entries(biblio, o.entries)
        add_tags(entries, o.add or [])
        remove_tags(entries, o.rm or [])
        savebib(biblio, config)
        _print_biblio_diff(biblio_init, biblio, entries)
        return

    entries = select_entries(biblio, o.entries) if o.entries else biblio.entries
    counts = tag_counts(entries)
    for tag, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower())):
        print(f"{tag} ({count})")


FILE_COMMANDS = {
    'rename': file_renamecmd,
    'mv': file_mvcmd,
    'attach': file_attachcmd,
    'detach': file_detachcmd,
    'check': file_checkcmd,
    'clean': file_cleancmd,
}

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
    logger.info(config.bibtex+' <==> '+back)
    shutil.copy(config.bibtex, tmp)
    shutil.move(back, config.bibtex)
    shutil.move(tmp, back)

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
            ratio = o.fuzzy_ratio if o.fuzzy_ratio is not None else 50
            res = (target.lower() in word.lower() or fuzz.token_set_ratio(word.lower(), target.lower(), score_cutoff=ratio) > ratio)
        elif substring:
            res = target.lower() in word.lower()
        else:
            res = fnmatch.fnmatch(word.lower(), target.lower())

        return res if not o.invert else not res


    def _longmatch(word, target):
        return _match(word, target, fuzzy=o.fuzzy, substring=not o.strict)

    def _requiresreview(e):
        if not isvalidkey(get_entry_val(e, 'ID', '')): return True
        if 'doi' in e and not isvaliddoi(e['doi']): return True
        if 'author' not in e: return True
        if 'title' not in e: return True
        if 'year' not in e: return True
        return False


    # file actions moved to other commands (removed in v4)
    if o.add_files:
        logger.warning("`papers list --add-files` is deprecated: use `papers file attach KEY FILE...`"
                       + (" (--copy or --move)" if o.rename else ""))
    elif o.rename:
        logger.warning("`papers list --rename` is deprecated: use `papers list ... -K | papers file rename "
                       + ("--keep-source " if o.copy else "") + "-`")
    elif o.copy:
        logger.warning("`papers list --copy` is deprecated (and has no effect without --rename): "
                       "use `papers list ... -K | papers file rename --keep-source -`")
    if o.open:
        logger.warning("`papers list --open` is deprecated: use `papers list ... -K | papers open -`")
    if o.fetch:
        logger.warning("`papers list --fetch` is deprecated: use `papers list ... -K | papers check --fetch -`")

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

    for name in ('duplicates_key', 'duplicates_doi', 'duplicates_tit'):
        if getattr(o, name):
            logger.warning(f'--{name.replace("_", "-")} is deprecated: use --duplicates (--fuzzy for near matches)')
            o.duplicates = True
    if o.similarity is not None:
        logger.warning('--similarity is deprecated and ignored: entries are the same paper by identifier, '
                       'or by authors and title (see the documentation of papers add)')

    if o.duplicates:
        listed = []
        for g in duplicate_groups(entries, biblio.distinct):
            listed.extend(e for e in g.entries if not any(e is x for x in listed))
        if o.fuzzy:
            for a, b in fuzzy_pairs(entries, o.fuzzy_ratio if o.fuzzy_ratio is not None else FUZZY_RATIO):
                listed.extend(e for e in (a, b) if not any(e is x for x in listed))
        if o.invert:
            entries = [e for e in entries if not any(e is x for x in listed)]
        else:
            entries = listed

    if o.add_keywords:
        add_tags(entries, o.add_keywords)
        savebib(biblio, config)

    elif o.add_files:
        if len(entries) != 1:
            raise PapersExit("list only one entry to use --add-files")
        e = entries[0]
        attach_files(biblio, e, o.add_files, config,
                     ('copy' if o.copy else 'move') if o.rename else 'link')
        savebib(biblio, config)

    elif o.edit:
        if not edit_selected(biblio, entries):
            return
        entries = biblio.entries
        savebib(biblio, config)

    elif o.fetch:
        for e in entries:
            biblio.fix_entry(e, fix_doi=True, fix_key=True, fetch_all=True, interactive=True)
        savebib(biblio, config)

    elif o.rename:
        rename_files(biblio, entries, config, keep_source=o.copy)
        savebib(biblio, config)

    elif o.delete:
        todelete = remove_entries(biblio, entries, config, delete_files=_delete_files_option(parser, o))
        savebib(biblio, config)
        delete_files(todelete, dryrun=papers.config.DRYRUN)

    elif o.open:
        for e in entries:
            view_entry_files(biblio, e)

    elif o.field:
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
    for key in read_selection(o.key):
        # an existing file is opened directly with the system viewer; anything
        # else is looked up as an entry key (or DOI) in the bibliography
        if os.path.isfile(key):
            logger.info(f"opening {key} ...")
            view_pdf(key)
            continue
        if biblio is None:
            try:
                biblio = get_biblio(config)
            except ValueError:
                raise PapersExit(f"'{key}' is not an existing file, and no bibliography is configured to look it up as a key")
        try:
            e, = select_entries(biblio, [key])[:1]
        except PapersExit as error:
            logger.error(str(error))
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

    # entries named on the command line (see papers.identifiers)
    _selection_help = (f'KEY: {ENTRY_IDS} (a former key in the ids field works too); '
                       '- reads them from the standard input, one per line')

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
    initp = subparsers.add_parser('init', description='create a library in the current directory, '
        'or in DIR (created if missing)',
        parents=[loggingp, namefmt, keyfmt])
    initp.add_argument('dir', nargs='?', metavar='DIR',
        help='directory of the library (default: the current directory); --bibtex and '
             '--filesdir are relative to it')
    initp.add_argument('--bibtex', type=file_uri_to_path,
        help='bibtex file (default: papers.bib, or the first .bib file of the directory)')
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
    initp.add_argument('--light', action='store_true',
        help='a light library: its file links point to the files of its first pool (see `papers migrate --light`)')
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
    migratep.add_argument('--light', action='store_true',
        help='make the library light: each file that the first pool has for the same paper (same content) '
             'is replaced by a link to the pool\'s file, and the library\'s copy in its files directory is '
             'deleted. Files that are not in the pool are kept and listed (push them first).')
    migratep.add_argument('--full', action='store_true',
        help='make the library full again: copy (a hard link when possible) the pool files it links to '
             'into its files directory, named with its name template')

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
    grp.add_argument('--no-check-files', action='store_true', help='faster, less info')


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

    grp = addp.add_argument_group('duplicate check',
        description='''An added entry is the same paper as a library entry when they have
        the same DOI, arXiv id, ISBN (two books), or else the same authors and title.
        The library entry keeps its key; fields only in the added entry are added and
        the file links are merged. An entry that brings nothing new is not asked about.''')
    grp.add_argument('--on-duplicate', choices=ON_DUPLICATE,
        help='''what to do when the added entry is in the library, with conflicting
        values or fields to add: ask (dialogue; the default in a terminal), keep (merge,
        conflicts keep the library value), update (merge, conflicts take the added value),
        skip (leave the library entry untouched, do not add), error (stop before saving;
        the default without a terminal)''')
    grp.add_argument('--no-check-duplicate', action='store_true',
        help='disable duplicate check (faster, create duplicates)')
    grp.add_argument('--no-pool', action='store_true',
        help='''do not look in the pools first (by default, a PDF, DOI or bibtex entry that is
        the same paper as a pool entry is taken from the pool, with its files, without fetching)''')
    grp.add_argument('--no-merge-files', action='store_true',
        help='deprecated and ignored: file links are always merged')
    grp.add_argument('-u', '--update-key', action='store_true',
        help='''regenerate the key of the entries new to the library from the key template
        (see "bibtex key format" options). A duplicate always keeps the key of the library.''')
    grp.add_argument('-m', '--mode', choices=['u', 'U', 'o', 's', 'r', 'i', 'a'],
        help='''deprecated: use --on-duplicate (i: ask, u: keep, U and o: update, s: skip,
        r: error, a: --no-check-duplicate)''')

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

    grp = addp.add_argument_group('files',
        description=f'''What happens to the added PDF, the files of an added bibtex, and the
        attached files, is the `files` setting of the library (found: {config.files}):
        move: place them in the files directory, under a name made from the name
        template, and remove the original; copy: place them there, and keep the original
        (a hard link when possible, otherwise a copy); link: leave them where they are,
        the entry links to them there. A file that belongs to another library (inside
        its files directory) is never moved: it is copied instead.''')
    grp.add_argument('--attach', nargs='+', type=file_uri_to_path, dest='attachment', metavar='FILE',
        help='attach these files to the entry (e.g. supplementary material)')
    grp.add_argument('--attachment', nargs='+', type=file_uri_to_path, dest='attachment_deprecated',
        help='deprecated: use --attach')
    grp.add_argument('--move', action='store_true', help='files mode move, whatever the setting')
    grp.add_argument('-r','--rename', action='store_true', help='same as --move')
    grp.add_argument('-c','--copy', action='store_true', help='files mode copy, whatever the setting')
    grp.add_argument('--link', action='store_true', help='files mode link, whatever the setting')

    grp = addp.add_argument_group('actions')
    grp.add_argument('-e', '--edit', action='store_true', help='edit entry')
    grp.add_argument('-o', '--open', action='store_true', help='open files')

    # check
    # =====
    checkp = subparsers.add_parser('check', description='check and fix entries',
        parents=[cfg, keyfmt])
    checkp.add_argument('entries', nargs='*', metavar='KEY',
        help='check these entries only (default: all): ' + _selection_help)
    checkp.add_argument('-k', '--keys', nargs='+', help='apply check on this key subset (same as the KEY arguments)')
    checkp.add_argument('-f','--force', action='store_true', help='do not ask')

    grp = checkp.add_argument_group('entry key')
    grp.add_argument('--fix-key', action='store_true', help='fix key based on author name and date (in case missing or digit)')
    grp.add_argument('--key-ascii', action='store_true', help='replace keys unicode character with ascii')
    grp.add_argument('--auto-key', action='store_true', help='new, auto-generated key for all entries')

    grp = checkp.add_argument_group('crossref fetch and fix')
    grp.add_argument('--fix-doi', action='store_true', help='fix doi for some common issues (e.g. DOI: inside doi, .received at the end')
    grp.add_argument('--fetch', action='store_true', help='fetch metadata from doi and update entry')
    grp.add_argument('--fetch-all', action='store_true', help='fetch metadata from title and author field and update entry (only when doi is missing)')

    grp = checkp.add_argument_group('names')
    grp.add_argument('--format-name', action='store_true', help='author name as family, given, without brackets')
    grp.add_argument('--encoding', choices=['latex','unicode'], help='bibtex field encoding')

    grp = checkp.add_argument_group('duplicates')
    grp.add_argument('--duplicates',action='store_true',
        help='''merge the entries that are the same paper (same DOI, arXiv id, ISBN of two books,
        or else same authors and title). The entry with most fields is entry 1, the
        target: it keeps its key, and the keys of the others go to its ids field.''')
    grp.add_argument('--on-duplicate', choices=[m for m in ON_DUPLICATE if m != 'update'],
        help='''what to do with each group: ask (dialogue; the default in a terminal),
        keep (merge, conflicts keep the value of entry 1), skip (leave the group),
        error (exit with status 1 if there is any group; the default without a terminal,
        and skip with --force)''')
    grp.add_argument('-m', '--mode', choices=list('ims'), help='deprecated: use --on-duplicate (i: ask, m: keep, s: skip)')


    # file
    # ====
    filep = subparsers.add_parser('file', description='the files of the entries: rename, move, attach, '
        'detach, check them, and clean the files directory')
    filesub = filep.add_subparsers(dest='file_cmd', metavar='{rename,mv,attach,detach,check,clean}')
    filep.subcommands = filesub.choices

    p = filesub.add_parser('rename', parents=[cfg, namefmt],
        help='place the files in the files directory under their template name',
        description='place the files of the entries (all entries without KEY) in the files directory, '
                    'under the name made from the name template. A file that belongs to another library '
                    '(inside its files directory) is copied, not moved.')
    p.add_argument('entries', nargs='*', metavar='KEY', help=_selection_help)
    p.add_argument('--keep-source', action='store_true',
        help='keep the files where they are too (a hard link when possible, otherwise a copy)')

    p = filesub.add_parser('mv', parents=[cfg],
        help='move files or folders, and update the links of the entries',
        description='move files or folders like mv, with the rules of git mv, and update the links of the '
                    'entries to the moved files: a source file must be linked from an entry; a source folder '
                    'must contain a linked file, and moves as a whole; with several sources, DEST must be an '
                    'existing folder; an existing DEST file is an error unless -f. Moving the files directory '
                    'also updates the filesdir setting. Nothing moves if a check fails.')
    p.add_argument('paths', nargs='+', metavar='SRC... DEST', type=file_uri_to_path)
    p.add_argument('-f', '--force', action='store_true', help='replace an existing destination file')
    p.add_argument('-n', action='store_true', dest='dry_run', help='show the moves and the links that change (same as --dry-run)')

    p = filesub.add_parser('attach', parents=[cfg, namefmt],
        help='attach files to an entry',
        description='attach files to an existing entry. What happens to the files is the files setting '
                    f'(found: {config.files}), as for `papers add`; the files the entry had are left as they are.')
    p.add_argument('key', metavar='KEY', help=f'{ENTRY_IDS} of the entry')
    p.add_argument('files', nargs='+', metavar='FILE', type=file_uri_to_path, help='files or URLs')
    p.add_argument('--move', action='store_true', help='files mode move, whatever the setting')
    p.add_argument('--copy', action='store_true', help='files mode copy, whatever the setting')
    p.add_argument('--link', action='store_true', help='files mode link, whatever the setting')

    p = filesub.add_parser('detach', parents=[cfg],
        help='remove file links from an entry',
        description='remove the links to FILE (all its files without FILE) from the entry KEY. '
                    'The files are kept, unless --delete-files.')
    p.add_argument('args', nargs='*', metavar='KEY [FILE...]', type=file_uri_to_path,
        help=f'KEY: {ENTRY_IDS} of the entry; with --broken: KEY... (all entries without KEY)')
    p.add_argument('--broken', action='store_true', help='remove the broken links only')
    p.add_argument('--delete-files', action='store_true',
        help='also delete the detached files that no other entry links to')

    p = filesub.add_parser('check', parents=[cfg],
        help='report broken links, identical files, DOI mismatches',
        description='report broken links, links that can be repaired (paths saved by Mendeley), files linked '
                    'twice and identical files (same checksum) of an entry, and with --metadata a DOI of the PDF '
                    'that differs from the entry\'s. Nothing changes without --fix.')
    p.add_argument('entries', nargs='*', metavar='KEY', help=_selection_help + ' (default: all entries)')
    p.add_argument('--metadata', action='store_true', help='also compare the DOI of the PDFs with the entry (parses the PDFs)')
    p.add_argument('--fix', action='store_true',
        help='apply the safe repairs: repair the paths, remove the second link of a file linked twice or of '
             'identical files (the files are kept)')

    p = filesub.add_parser('clean', parents=[cfg],
        help='remove the files of the files directory that no entry links to',
        description='remove the files of the files directory (and its subfolders) that no entry links to, '
                    'asking for each one. Hidden files and folders, and .bib files, are skipped.')
    p.add_argument('-y', '--yes', action='store_true', help='do not ask')

    # filecheck
    # =====
    filecheckp = subparsers.add_parser('filecheck', description='deprecated: use the subcommands of `papers file`',
        parents=[cfg, namefmt])

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

    # list
    # ======
    listp = subparsers.add_parser('list', description='list (a subset of) entries in the existing bib file',
        parents=[cfg])

    listp.add_argument('fullsearch', nargs='*', help='''Search field. Usually no quotes required. See keywords to search specific fields. All words must find a match, unless --any is passed.''')

    mgrp = listp.add_mutually_exclusive_group()
    mgrp.add_argument('--strict', action='store_true', help='exact matching - instead of substring')
    mgrp.add_argument('--fuzzy', action='store_true', help='fuzzy matching - instead of substring')
    listp.add_argument('--fuzzy-ratio', type=int,
        help=f'threshold for fuzzy matching of title, author, abstract (default: 50), '
             f'and of authors and title with --duplicates --fuzzy (default: {FUZZY_RATIO})')
    listp.add_argument('--similarity', help='deprecated and ignored')
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
    grp.add_argument('--duplicates-key', action='store_true', help='deprecated: --duplicates')
    grp.add_argument('--duplicates-doi', action='store_true', help='deprecated: --duplicates')
    grp.add_argument('--duplicates-tit', action='store_true', help='deprecated: --duplicates')
    grp.add_argument('--duplicates', action='store_true',
        help='''entries that are the same paper, as `papers check --duplicates` finds them, and
        the entries it would ask about; with --fuzzy, also the entries with similar
        authors and title (see --fuzzy-ratio)''')
    grp.add_argument('--has-file', action='store_true', help='entries with at least one file')
    grp.add_argument('--no-file', action='store_true', help='entries without file')
    grp.add_argument('--broken-file', action='store_true', help='entries with a file link to a missing file')
    grp.add_argument('--review-required', action='store_true', help='suspicious entry (invalid dois, missing field etc.)')

    grp = listp.add_argument_group('formatting')
    mgrp = grp.add_mutually_exclusive_group()
    mgrp.add_argument('--plain', action='store_false', dest="one_liner", help='print in bibtex format')
    mgrp.add_argument('-l', '-1', '--one-liner', action='store_true', help='one liner')
    mgrp.add_argument('-K', '--key-only', action='store_true',
        help='print the keys only, one per line (to pipe into commands that take -, e.g. `papers file rename -`)')
    mgrp.add_argument('-f', '--field', nargs='+', help='specific field(s) only')
    grp.add_argument('--no-key', action='store_true', help='do not print the keys')

    grp = listp.add_argument_group('action on listed results',
        description='shortcuts of `papers edit`, `papers rm` and `papers tag`; the other commands that act '
                    'on entries read the keys of `papers list -K` with -, e.g. `papers list smith -K | papers file rename -`')
    grp.add_argument('--delete', action='store_true',
        help='remove the listed entries, as `papers rm` (asks whether to delete their files, in a terminal)')
    grp.add_argument('--delete-files', action='store_true', help='with --delete: also delete their files, as `papers rm --delete-files`')
    grp.add_argument('--keep-files', action='store_true', help='with --delete: keep their files, without asking')
    grp.add_argument('-e', '--edit', action='store_true', help='edit the listed entries in a text editor, as `papers edit`')
    grp.add_argument('--fetch', action='store_true', help='deprecated: `papers check --fetch -`')
    grp.add_argument('--add-keywords', '--add-tag', nargs='+', help='add keywords (tags) to the listed entries, as `papers tag --add`')
    grp.add_argument('--add-files', nargs='+', type=file_uri_to_path, help='deprecated: `papers file attach KEY FILE...`')
    grp.add_argument('--rename', action='store_true', help='deprecated: `papers file rename -`')
    grp.add_argument('--copy', action='store_true', help='deprecated: `papers file rename --keep-source -`')
    grp.add_argument('-o', '--open', action='store_true', help='deprecated: `papers open -`')

    # edit, rm, tag
    # =============
    editp = subparsers.add_parser('edit', parents=[cfg],
        description='edit entries in a text editor (the editor setting, or $EDITOR)')
    editp.add_argument('entries', nargs='+', metavar='KEY',
        help=_selection_help)

    rmp = subparsers.add_parser('rm', parents=[cfg],
        description='remove entries. Their files that no other entry links to may be deleted too: in a '
                    'terminal, papers asks for those in the files directory; without a terminal, they are kept. '
                    'Files outside the files directory are only deleted with --delete-files.')
    rmp.add_argument('entries', nargs='+', metavar='KEY',
        help=_selection_help)
    rmp.add_argument('--delete-files', action='store_true',
        help='also delete the files of the entries that no other entry links to, without asking '
             '(also those outside the files directory)')
    rmp.add_argument('--keep-files', action='store_true', help='keep the files, without asking')

    tagp = subparsers.add_parser('tag', parents=[cfg],
        description='tags are the keywords field of the entries (comma-separated). Without option, list '
                    'the tags of the library (or of the entries KEY...) with the number of entries.')
    tagp.add_argument('entries', nargs='*', metavar='KEY',
        help=_selection_help)
    tagp.add_argument('--add', nargs='+', metavar='TAG', help='add tags to the entries')
    tagp.add_argument('--rm', nargs='+', metavar='TAG', help='remove tags from the entries')
    tagp.add_argument('--rename', nargs=2, metavar=('OLD', 'NEW'), help='rename a tag in the whole library')

    # pull, push, export, pool
    # ========================
    _exchange_help = '''what to do with an entry changed on both
        sides since the last pull or push: ask (dialogue; the default in a terminal), keep (the
        {receiving} values are kept), update (the {incoming} values are taken), skip (the entry is
        left as it is, and comes again next time), error (stop before saving; the default
        without a terminal). Fields changed on one side only need no decision.'''
    pullp = subparsers.add_parser('pull', parents=[cfg],
        description='''update the entries of the library from their pool entries (three-way merge
        with the origin copy of the entry, .papers/origin.bib): a field changed in the pool only is
        taken, a field changed in the library only is kept, a field changed on both sides is a
        conflict. Entries without origin copy are matched to the pools by the same-paper rule.
        The keys of the library never change. New pool files are copied (or linked) as the files
        setting says; a light library links to them.''')
    pullp.add_argument('entries', nargs='*', metavar='KEY', help=_selection_help + ' (default: all entries)')
    pullp.add_argument('--on-duplicate', choices=ON_DUPLICATE,
        help=_exchange_help.format(receiving='library', incoming='pool'))
    pullp.add_argument('--check', action='store_true',
        help='only report: the pools that changed since the last pull, and the entries changed in the pools')
    pullp.set_defaults(mode=None, force=False)

    pushp = subparsers.add_parser('push', parents=[cfg],
        description='''add the entries of the library to the first pool, or merge their changes
        into the pool entries (three-way merge with the origin copy, as pull does in the other
        direction). Entries new to the pool get a key from the pool's key template; their files
        are copied (a hard link when possible) into the pool's files directory, named with the
        pool's name template. The default pool is created if it does not exist.''')
    pushp.add_argument('entries', nargs='*', metavar='KEY', help=_selection_help + ' (default: all entries)')
    pushp.add_argument('--pool', metavar='NAME|PATH', help='push to this pool (default: the first pool of the library)')
    pushp.add_argument('--on-duplicate', choices=ON_DUPLICATE,
        help=_exchange_help.format(receiving='pool', incoming='library'))
    pushp.set_defaults(mode=None, force=False)

    exportp = subparsers.add_parser('export', parents=[cfg],
        description='''write entries as a new library in DIR: bibtex, files, configuration, with
        file links relative to the bibtex. `papers add DIR --recursive` adds it back.''')
    exportp.add_argument('dir', metavar='DIR', help='directory of the new library (must not exist, or be empty)')
    exportp.add_argument('entries', nargs='*', metavar='KEY', help=_selection_help + ' (default: all entries)')
    exportp.add_argument('--files', choices=['copy', 'link', 'none'], default='copy',
        help='copy the files into DIR/files (a hard link when possible; default), link to them where '
             'they are, or leave the file links out')
    exportp.add_argument('--pool', action='store_true', help='also add DIR to the pools of the library')

    poolp = subparsers.add_parser('pool', parents=[loggingp],
        description='the pools of the per-machine configuration (the same as `papers config --machine '
                    'pools.NAME PATH`). Without subcommand: list them, and the pools of the library.')
    poolsub = poolp.add_subparsers(dest='pool_cmd')
    poolsub.add_parser('list', parents=[loggingp], help='list the pools of the machine and of the library')
    p = poolsub.add_parser('add', parents=[loggingp], help='name a pool of this machine')
    p.add_argument('name', metavar='NAME')
    p.add_argument('path', metavar='PATH')
    p.add_argument('--dry-run', action='store_true', help='do not save')
    p = poolsub.add_parser('remove', parents=[loggingp], help='remove a pool name of this machine (not the library)')
    p.add_argument('name', metavar='NAME')
    p.add_argument('--dry-run', action='store_true', help='do not save')

    # open
    # ====
    openp = subparsers.add_parser('open', description='open entry attachments or files with the system viewer', parents=[cfg])
    openp.add_argument('key', nargs='+', type=file_uri_to_path, help='entries (' + _selection_help + '), or existing file path(s) to open directly')

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

    # undo
    # ====
    _restorep = argparse.ArgumentParser(add_help=False)
    _restorep.add_argument('--restore-files', action='store_true', help='Use this option to restore files that have been renamed. By default the file link points to the back-up repository. This command has no effect without --git-lfs, and will result in broken file links.')

    _stepsp = argparse.ArgumentParser(add_help=False)
    _stepsp.add_argument('-n', '--steps', type=int, default=1, help='number of times undo/redo should be performed')

    subparsers.add_parser('undo', parents=[cfg, _restorep, _stepsp], help='Undo changes on bibtex (if --git is not enabled, only back and forth with last modification). If --git-lfs is enabled, the file entry may differ if it does not exist on disk any more, unless --restore-files was passed.')
    subparsers.add_parser('redo', parents=[cfg, _restorep, _stepsp], help='Redo changes on bibtex (if --git is not enabled, this has the same effect as papers undo)')
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

    if os.path.exists(CONFIG_FILE) and o.cmd != 'migrate' and not (o.cmd == 'install' and o.local is False):
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
    elif o.cmd == 'edit':
        editcmd(subp, o, check_install(subp, o, config))
    elif o.cmd == 'rm':
        rmcmd(subp, o, check_install(subp, o, config))
    elif o.cmd == 'pull':
        pullcmd(subp, o, check_install(subp, o, config))
    elif o.cmd == 'push':
        pushcmd(subp, o, check_install(subp, o, config))
    elif o.cmd == 'export':
        exportcmd(subp, o, check_install(subp, o, config))
    elif o.cmd == 'pool':
        poolcmd(subp, o, config)
    elif o.cmd == 'tag':
        tagcmd(subp, o, check_install(subp, o, config))
    elif o.cmd == 'file':
        if not o.file_cmd:
            subp.print_help()
            raise PapersExit()
        filesubp = subp.subcommands[o.file_cmd]
        FILE_COMMANDS[o.file_cmd](filesubp, o, check_install(filesubp, o, config))
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


def main_clean_exit(args=None):
    try:
        main(args)
    except (PapersExit, DuplicateKeyError) as error:
        if logger.getEffectiveLevel() == logging.DEBUG:
            raise
        if error.args:
            logger.error(str(error))
        sys.exit(1)
    except EOFError:
        # a question was asked, but the standard input is closed (script, pipe)
        if logger.getEffectiveLevel() == logging.DEBUG:
            raise
        logger.error('papers asked a question, but there is no input to answer it: '
                     'run the command in a terminal, or answer with its options '
                     '(e.g. --on-duplicate for duplicates, --force)')
        sys.exit(1)

if __name__ == "__main__":
    # we use try/except here to use a clean exit instead of trace
    # test and debugging may use main() directly for speed-up => better to avoid sys.exit there
    main_clean_exit()