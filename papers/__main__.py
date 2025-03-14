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
from papers.extract import extract_pdf_doi, isvaliddoi, extract_pdf_metadata
from papers.extract import fetch_bibtex_by_doi, fetch_bibtex_by_fulltext_crossref, fetch_bibtex_by_fulltext_scholar
from papers.encoding import parse_file, format_file, family_names, format_entries, standard_name, format_entry, parse_keywords, format_key
from papers.config import bcolors, Config, search_config, CONFIG_FILE, CONFIG_FILE_LOCAL, DATA_DIR, CONFIG_FILE_LEGACY, BACKUP_DIR
from papers.duplicate import list_duplicates, list_uniques, edit_entries
from papers.bib import (Biblio, FUZZY_RATIO, DEFAULT_SIMILARITY, entry_filecheck,
                        backupfile as backupfile_func, isvalidkey, DuplicateKeyError, clean_filesdir)
from papers.utils import move, checksum, view_pdf, open_folder
from papers import __version__


if os.path.exists(CONFIG_FILE_LEGACY):
    # move config file from ~/.local/.share/papers/ to ~/.config/papersconfig.json .papers/config.json to .papersconfig.json"
    if not os.path.exists(CONFIG_FILE):
        logger.warning(f"Move legacy config file {CONFIG_FILE_LEGACY} to {CONFIG_FILE}'")
        shutil.move(CONFIG_FILE_LEGACY, CONFIG_FILE)
    else:
        logger.warning(f"Legacy config file found: {CONFIG_FILE_LEGACY}. Delete to remove this warning:  rm -f '{CONFIG_FILE_LEGACY}'")

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


def get_biblio(config):
    """
    This function initializes a Biblio object based on the bibtex file specified as command line argument or in config file.
    If no bibtex file is specified, it raises a ValueError().
    """
    if config.bibtex is None:
        raise ValueError('bibtex is not initialized')
    relative_to = os.path.sep if config.absolute_paths else (os.path.dirname(config.bibtex) if config.bibtex else None)
    if config.bibtex and os.path.exists(config.bibtex):
        biblio = Biblio.load(config.bibtex, config.filesdir, nameformat=config.nameformat, keyformat=config.keyformat)
        if biblio.relative_to != relative_to:
            biblio.update_file_path(relative_to)
    else:
        biblio = Biblio.newbib(config.bibtex, config.filesdir, relative_to=relative_to, nameformat=config.nameformat, keyformat=config.keyformat)
    return biblio


def _backup_bib(biblio, config, message=None):
    if not config.git:
        raise PapersExit('cannot backup without --git enabled')
    # backupdir = Path(config.file).parent
    backupdir = Path(config.gitdir)
    backupdir.mkdir(exist_ok=True)

    # remove if exists
    config.backupfile.unlink(missing_ok=True)
    config.backupfile_clean.unlink(missing_ok=True)

    ## Here we could create a copy of biblio since it is modified in place
    ## For now, we exit the program after saving, so don't bother
    logger.debug(f'BACKUP: cp {config.bibtex} {config.backupfile}')
    shutil.copy(config.bibtex, config.backupfile)
    config.gitcmd(f"add {config.backupfile.name}")

    biblio = copy.deepcopy(biblio)

    if config.backup_files:
        logger.info('backup bibliography with files')
        backupfilesdir = backupdir/"files"
        backupfilesdir.mkdir(exist_ok=True)
        biblio.filesdir = str(backupfilesdir)
        biblio.rename_entries_files(copy=True, relative_to=backupdir, hardlink=True)
        biblio.save(config.backupfile_clean)
        config.gitcmd(f"add {config.backupfile_clean.name}")

        # Remove unlink files
        clean_filesdir(biblio, interactive=False, ignore_files=[config.backupfile, config.backupfile_clean])
        config.gitcmd(f"add files")

    else:
        logger.info('backup bibliography only (without files)')
        biblio.update_file_path(relative_to=backupdir)
        biblio.save(config.backupfile_clean)
        config.gitcmd(f"add {config.backupfile_clean.name}")

    message = message or f'papers ' +' '.join(sys.argv[1:])
    res = config.gitcmd(f"commit -m '{message}'", check=False)
    # work on "main" branch for comitting (out of history branch)
    config.gitcmd(f"checkout -B main")
    config.gitcmd(f"clean -f")

def _silent_backup_bib(biblio, config, level=logging.WARNING, *args, **kwargs):
    " this is useful when passing --info to avoid having too many outputs"
    level0 = logger.getEffectiveLevel()
    if level0 > logging.DEBUG: # if DEBUG, also show back debug logs
        logger.setLevel(level)
    _backup_bib(biblio, config, *args, **kwargs)
    logger.setLevel(level0)


def _restore_from_backupdir(config, restore_files=False):
    restore_cmd = f"papers add {config.backupfile_clean} --rename --copy" if config.backup_files else f"cp {config.backupfile} {config.bibtex}"
    repair_message = f"papers backup broken :: cannot repair file links :: try to recover manually with `{restore_cmd}`"
    try:
        return _restore_from_backupdir_wrapped(config, restore_files=restore_files)
    except Exception as error:
        raise
        logger.error(str(error))
        raise PapersExit(repair_message)


def _restore_from_backupdir_wrapped(config, restore_files=False):
    # current = sp.check_output(f"git rev-parse --short HEAD", shell=True, cwd=config.gitdir).strip().decode()
    current = sp.check_output(f"git rev-parse HEAD", shell=True, cwd=config.gitdir).strip().decode()
    message = sp.check_output(f"git log {current} --pretty='format:%C(auto)%h %s (%ad)' -1", shell=True, cwd=config.gitdir).strip().decode()
    logger.info(f'restore bibliography to {message}')

    if os.path.exists(config.bibtex):
        os.remove(config.bibtex)
    shutil.copy(config.backupfile, config.bibtex)

    # Re-name the file according to back-up bibtex
    if not config.backup_files:
        return

    biblio = Biblio.load(config.bibtex, config.filesdir)
    biblio_clean = Biblio.load(config.backupfile_clean, config.filesdir)

    assert len(biblio.entries) == len(biblio_clean.entries)

    for e, e_clean in zip(biblio.entries, biblio_clean.entries):
        assert e['ID'] == e_clean['ID'], f"{e['ID']} != {e_clean['ID']})"
        files = biblio.get_files(e)
        files_clean = biblio_clean.get_files(e_clean)
        assert len(files) == len(files_clean), f"{e['ID']} :: files {len(files)} != {len(files_clean)})"

        new_files = []

        for f, f_clean in zip(files, files_clean):
            # broken link in the backup
            if not os.path.exists(f_clean):
                logger.debug(f"BACKUP FILE DOES NOT EXISTS: {f_clean} ")
                logger.debug(f"BACKUP ENTRY: {e_clean['file']} ")
                logger.debug(f"BROKEN ENTRY: {e['file']} ")
                logger.warning(f"{e['ID']} :: file link broken => {f} ")
                new_files.append(f)
                continue

            # backup file is fine

            # original bibtex link matches something on disk
            if os.path.exists(f):

                # same file: nothing to do
                if os.path.samefile(f, f_clean) or checksum(f_clean) == checksum(f):
                    new_files.append(f)

                else:
                    logger.warning(f"{e['ID']} :: file found but does not match backup (keep pointer to backup): {f} != {f_clean}")
                    new_files.append(f_clean)

            # original bibtex link is broken, --restore-file is active
            elif restore_files:
                try:
                    move(f_clean, f, copy=True, interactive=False)
                    new_files.append(f)

                except Exception as error:
                    logger.error(f"{error}")
                    logger.error(f"{e['ID']} :: failed to restore file (keep pointer to backup)")
                    new_files.append(f_clean)
                    pass

            # original bibtex link is broken, default without --restore-file : do not do anything
            else:
                new_files.append(f_clean)

        biblio.set_files(e, new_files)

    biblio.save(config.bibtex)


def _git_reset_to_commit(config, commit, restore_files=False):
    config.gitcmd(f"reset --hard {commit}")
    _restore_from_backupdir(config, restore_files=restore_files)


def _git_undo(config, restore_files=False, steps=1):
    sp.check_call(f"git checkout -B history", shell=True, cwd=config.gitdir)
    _git_reset_to_commit(config, 'HEAD'+'^'*steps, restore_files=restore_files)
    # _git_reset_to_commit(config, 'HEAD^', restore_files=o.restore_files)


def _git_redo(config, restore_files=False, steps=1):
    current = sp.check_output(f"git rev-parse HEAD", shell=True, cwd=config.gitdir).strip().decode()
    futures = sp.check_output(f"git rev-list {current}..main", shell=True, cwd=config.gitdir).strip().decode().splitlines()[::-1]
    try:
        future = futures[steps-1]
    except Exception as error:
        raise PapersExit("nothing to redo")
    _git_reset_to_commit(config, future, restore_files=restore_files)


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
    if config.file and config.git:
        _silent_backup_bib(biblio, config)
    else:
        logger.debug(f'do not backup bib: {config.file}, {config.git}')
    # if config.git:
        # config.gitcommit()



def is_subdirectory(parent, child):
    # Resolve paths to absolute paths
    parent = Path(parent).resolve()
    child = Path(child).resolve()

    # Check if the child path is relative to the parent path
    return parent in child.parents


def view_entry_files(biblio, entry):
    files = biblio.get_files(entry)

    # in case several attachments are present and the files are ordered under filesdir,
    # open the subfolder instead of the single files
    if len(files) > 1:
        parent = os.path.commonpath(files)
        if is_subdirectory(biblio.filesdir, parent):
            open_folder(parent)
            return

    for f in biblio.get_files(entry):
        logger.info(f"opening {f} ...")
        view_pdf(f)


def set_keyformat_config_from_cmd(o, config):
    """
    Given options and a config state, applies the desired key options to the config.
    """
    config.keyformat.template = o.key_template
    config.keyformat.author_num = o.key_author_num
    config.keyformat.author_sep = o.key_author_sep
    config.keyformat.title_word_num = o.key_title_word_num
    config.keyformat.title_word_size = o.key_title_word_size
    config.keyformat.title_sep = o.key_title_sep

def set_nameformat_config_from_cmd(o, config):
    """
    Given options and a config state, applies the desired name options to the config.
    """
    config.nameformat.template = o.name_template
    config.nameformat.author_num = o.name_author_num
    config.nameformat.author_sep = o.name_author_sep
    config.nameformat.title_length = o.name_title_length
    config.nameformat.title_word_num = o.name_title_word_num
    config.nameformat.title_word_size = o.name_title_word_size
    config.nameformat.title_sep = o.name_title_sep

def installcmd(parser, o, config):
    """
    Given options and a config state, installs the expected config files.
    """
    prompt = o.prompt and not o.edit
    # installed = config.file is not None
    # WARNING if pre-existing config file
    if config.file is not None and prompt:
        if ((o.local and config.local) or ((not o.local and not config.local))):
            while True:
                ans = input(f'An existing {"local" if config.local else "global"} install was found: {config.file}. Overwrite (O) or Edit (E) ? [o / e]')
                if ans.lower() in ('o', 'e'):
                    break
                else:
                    print('Use the --edit option to selectively edit existing configuration, or --force to ignore pre-existing configuration.')
            o.edit = ans.lower() == 'e'

        elif not o.local and config.local:
            print(f"A local configuration file was found that will have precedence over the global install: {config.file}. Delete (D) or Ignore (any other key) ?")
            ans = input()
            if ans.lower() == "d":
                logger.info(f"Removing pre-existing local configuration file {config.file}")
                os.remove(config.file)
                config = Config()

        elif o.local and not config.local:
            logger.warning(f"A global configuration file was found, but the local install will have precedence: {config.file}. Delete the global configuration file (D) or Ignore (any other key) ?")
            ans = input()
            if ans.lower() == "d":
                logger.info(f"Removing pre-existing global configuration file {config.file}")
                os.remove(config.file)
                config = Config()

        else:
            raise PapersExit("Unexpected configuration state")


    if not o.edit:
        if config.file and os.path.exists(config.file) and ((o.local and config.local) or ((not o.local and not config.local))):
            # if we don't do that the local install will take precedence over global install
            logger.warning(f"remove pre-existing configuration file: {config.file}")
            os.remove(config.file)
        config = Config()

    if o.local is None:
        if config.local is not None:
            logger.debug(f'keep config to pre-existing: {config.local}')
            o.local = config.local
        else:
            logger.debug(f'default to global config')
            # default ?
            o.local = False

    set_nameformat_config_from_cmd(o, config)
    set_keyformat_config_from_cmd(o, config)

    checkdirs = ["files", "pdfs", "pdf", "papers", "bibliography"]
    default_bibtex = config.bibtex or "papers.bib"
    default_filesdir = config.filesdir or "files"

    if o.local:
        papersconfig = config.file or CONFIG_FILE_LOCAL
        workdir = Path('.')
        bibtex_files = [str(f) for f in sorted(workdir.glob("*.bib"))]

        if o.absolute_paths is None:
            o.absolute_paths = False

    else:
        papersconfig = CONFIG_FILE
        workdir = Path(DATA_DIR)
        bibtex_files = [str(f) for f in sorted(Path('.').glob("*.bib"))] + [str(f) for f in sorted(workdir.glob("*.bib"))]
        checkdirs = [os.path.join(DATA_DIR, "files")] + checkdirs

        if o.absolute_paths is None:
            o.absolute_paths = True

    bibtex_files = [default_bibtex] + [f for f in bibtex_files if Path(f) != Path(default_bibtex)]
    bibtex_files = [f for f in bibtex_files if os.path.exists(f)]

    if config.filesdir:
        checkdirs = [config.filesdir] + checkdirs

    for d in checkdirs:
        if os.path.exists(str(d)):
            default_filesdir = d
            break

    RESET_DEFAULT = ('none', 'null', 'unset', 'undefined', 'reset', 'delete', 'no', 'n')
    ACCEPT_DEFAULT = ('yes', 'y', '')

    if not o.bibtex:
        if len(bibtex_files) > 1:
            logger.warning("Several bibtex files found: "+" ".join([str(b) for b in bibtex_files]))
        if bibtex_files:
            default_bibtex = bibtex_files[0]
        if prompt:
            if os.path.exists(default_bibtex):
                user_input = input(f"Bibtex file name [default to existing: {default_bibtex}] [Enter/Yes/No]: ")
            else:
                user_input = input(f"Bibtex file name [default to new: {default_bibtex}] [Enter/Yes/No]: ")
            if user_input in ACCEPT_DEFAULT:
                pass
            elif user_input:
                default_bibtex = user_input
        o.bibtex = default_bibtex

    if o.bibtex and o.bibtex.lower() in RESET_DEFAULT:
        o.bibtex = None

    if not o.filesdir:
        if prompt:
            if Path(default_filesdir).exists():
                user_input = input(f"Files folder [default to existing: {default_filesdir}] [Enter/Yes/No]: ")
            else:
                user_input = input(f"Files folder [default to new: {default_filesdir}] [Enter/Yes/No]: ")
            if user_input in ACCEPT_DEFAULT:
                pass
            elif user_input:
                default_filesdir = user_input
        o.filesdir = default_filesdir

    if o.filesdir and o.filesdir.lower() in RESET_DEFAULT:
        o.filesdir = None

    config.bibtex = o.bibtex
    config.filesdir = o.filesdir
    config.file = papersconfig
    config.local = o.local
    config.absolute_paths = o.absolute_paths

    # Unless otherwise specified (option not advertized -- help suppressed)
    # the git directory is centralized in the back up dir.
    if o.gitdir:
        config.gitdir = o.gitdir

    elif config.bibtex is not None:
        from normality import slugify
        bibi = config.bibtex[:-len(".bib")] if config.bibtex.endswith(".bib") else config.bibtex
        config.gitdir = os.path.join(BACKUP_DIR, slugify(bibi))

    if o.editor:
        config.editor = o.editor

    # create bibtex file if not existing
    bibtex = Path(o.bibtex) if o.bibtex else None

    if bibtex and not bibtex.exists():
        logger.info(f'create empty bibliography database: {bibtex}')
        bibtex.parent.mkdir(parents=True, exist_ok=True)
        bibtex.open('w', encoding="utf-8").write('')

    # create bibtex file if not existing
    filesdir = Path(o.filesdir) if o.filesdir else None
    if filesdir and not filesdir.exists():
        logger.info(f'create empty files directory: {filesdir}')
        filesdir.mkdir(parents=True)

    if o.git_lfs:
        o.git = True

    default_git = config.git if config.git is not None else False
    if o.git is None:
        if prompt:
            ans = input(f"Use git to back-up the bibtex file ? [Enter: {default_git}/Yes/No]: ")
            if ans.strip() == '':
                o.git = default_git
            else:
                o.git = ans.strip() in ACCEPT_DEFAULT
        else:
            o.git = default_git
    config.git = o.git

    if not config.git:
        o.git_lfs = False

    default_git_lfs = config.gitlfs if config.gitlfs is not None else False
    if o.git_lfs is None:
        if prompt:
            ans = input(f"Use git-lfs to back-up associated files ? [Enter: {default_git_lfs}/Yes/No]: ")
            if ans.strip() == '':
                o.git_lfs = default_git_lfs
            else:
                o.git_lfs = ans.strip() in ACCEPT_DEFAULT
        else:
            o.git_lfs = default_git_lfs
    config.gitlfs = o.git_lfs

    config.backup_files = config.gitlfs

    logger.info('save config file: '+config.file)
    if os.path.dirname(config.file):
        # typically is current dir = ""
        os.makedirs(os.path.dirname(config.file), exist_ok=True)

    config.git = o.git

    config.save()

    if config.git:
        # add a gitignore file to skip gitdir
        if (Path(config.gitdir)/'.git').exists():
            logger.warning(f'{config.gitdir} is already initialized')
        else:
            os.makedirs(config.gitdir, exist_ok=True)
            config.gitcmd('init')

        if config.gitlfs:
            config.gitcmd('lfs track "files/"')
            config.gitcmd('add .gitattributes')
            config.gitcmd(f'commit -m "papers install: .gitattribute"', check=False)

        biblio = get_biblio(config)
        _backup_bib(biblio, config)

    print(config.status(check_files=not o.no_check_files, verbose=True))

def _dir_is_empty(dir):
    # TODO this is actually never tested.
    with os.scandir(dir) as it:
        return not any(it)

def uninstallcmd(parser, o, config):
    # TODO this is actually never tested.
    if Path(config.file).exists():
        logger.info(f"The uninstaller will now remove {config.file}")
        os.remove(config.file)
        parent = os.path.dirname(config.file)
        if _dir_is_empty(parent):
            logger.info(f"The config dir {parent} is empty and the uninstaller will now remove it.")
            os.rmdir(parent)
        config = Config()
    else:
        logger.info(f"The uninstaller found no config file to remove.")
        return

    if o.recursive:
        config.file = search_config([CONFIG_FILE_LOCAL, os.path.join(".papers", "config.json")], start_dir=".", default=CONFIG_FILE)
        config.file = check_legacy_config(config.file)
        uninstallcmd(parser, o, config)

def check_install(parser, o, config, bibtex_must_exist=True):
    """
    Given an option and config, checks to see if the install is done correctly on this filesystem.
    """
    if getattr(o, "bibtex", None) is not None:
        config.bibtex = o.bibtex
    if getattr(o, "filesdir", None) is not None:
        config.filesdir = o.filesdir
    if getattr(o, "absolute_paths", None) is not None:
        config.absolute_paths = o.absolute_paths
    if getattr(o, "git", None) is not None:
        config.git = o.git

    install_doc = f"first execute `papers install --bibtex {config.bibtex or '...'} [ --local ]`"
    if not config.bibtex:
        parser.print_help()
        print(f"--bibtex must be specified, or {install_doc}")
        raise PapersExit()

    if bibtex_must_exist and not os.path.exists(config.bibtex):
        print(f'papers: error: no bibtex file found, do `touch {config.bibtex}` or {install_doc}')
        raise PapersExit()
    logger.info(f'bibtex: {config.bibtex!r}')
    logger.info(f'filesdir: {config.filesdir!r}')
    return True


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

        entries.extend( biblio.insert_entry(metadata, **kw) )


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

            elif file.endswith('.pdf'):
                entries.extend( biblio.add_pdf(file, attachments=o.attachment, rename=o.rename, copy=o.copy,
                           search_doi=not o.no_query_doi,
                           search_fulltext=not o.no_query_fulltext,
                           scholar=o.scholar, doi=o.doi,
                           **kw) )

            else: # file.endswith('.bib'):
                entries.extend( biblio.add_bibtex_file(file, attachments=o.attachment, rename=o.rename, copy=o.copy, **kw) )

        except Exception as error:
            # print(error)
            # addp.error(str(error))
            raise
            logger.error(str(error))
            if not o.ignore_errors:
                if len(o.file) or (os.isdir(file) and o.recursive)> 1:
                    logger.error('use --ignore to add other files anyway')
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

    old_set = set(e["ID"] for e in biblio_init.entries)
    old_entries_by_key = {e["ID"]:e for e in biblio_init.db.entries}
    new_set = set(e["ID"] for e in biblio.entries)
    new_entries_by_key = {e["ID"]:e for e in biblio.db.entries}
    modified_set = set(e["ID"] for e in entries ).intersection(set.intersection(old_set, new_set))

    for ID in sorted(old_set - new_set):
        print(format_entry(biblio_init, old_entries_by_key[ID], prefix="Removed"))

    for ID in sorted(new_set - old_set):
        print(format_entry(biblio, new_entries_by_key[ID], prefix="Added"))

    for ID in sorted(modified_set):
        before = old_entries_by_key[ID]
        after = new_entries_by_key[ID]
        if before != after:
            print(format_entry(biblio, after, prefix="Modified"))
        else:
            print(format_entry(biblio, after, prefix="Existing"))

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
        if o.keys and e.get('ID','') not in o.keys:
            continue
        biblio.fix_entry(e, fix_doi=o.fix_doi, fetch=o.fetch, fetch_all=o.fetch_all, fix_key=o.fix_key,
                     auto_key=o.auto_key, format_name=o.format_name, encoding=o.encoding,
                     key_ascii=o.key_ascii, interactive=not o.force)


    if o.duplicates:
        biblio.check_duplicates(mode=o.mode)

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
        return _git_redo(config, restore_files=o.restore_files, steps=o.steps)
    else:
        undocmd(parser, o, config)

def undocmd(parser, o, config):
    if config.git:
        return _git_undo(config, restore_files=o.restore_files, steps=o.steps)

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
        _git_reset_to_commit(config, o.ref, restore_files=o.restore_files)
    else:
        _restore_from_backupdir(config, restore_files=o.restore_files)


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

def extractcmd(parser, o):
    print(extract_pdf_metadata(o.pdf, search_doi=not o.fulltext, search_fulltext=True, scholar=o.scholar, minwords=o.word_count, max_query_words=o.word_count, image=o.image))
    # print(fetch_bibtex_by_doi(o.doi))


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
        return len(parse_file(e.get('file',''), relative_to=biblio.relative_to))


    def _requiresreview(e):
        if not isvalidkey(e.get('ID','')): return True
        if 'doi' in e and not isvaliddoi(e['doi']): return True
        if 'author' not in e: return True
        if 'title' not in e: return True
        if 'year' not in e: return True
        return False


    biblio = get_biblio(config)
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
        entries = [e for e in entries if e.get('file','')]
    if o.no_file:
        entries = [e for e in entries if not e.get('file','')]
    if o.broken_file:
        entries = [e for e in entries if e.get('file','') and any([not os.path.exists(f) for f in parse_file(e['file'], relative_to=biblio.relative_to)])]


    if o.doi:
        entries = [e for e in entries if 'doi' in e and _longmatch(e['doi'], o.doi)]
    if o.key:
        entries = [e for e in entries if 'ID' in e and _longmatch(e['ID'], o.key)]
    if o.year:
        entries = [e for e in entries if 'year' in e and _longmatch(e['year'], o.year)]
    if o.first_author:
        first_author = lambda field : family_names(field)[0]
        entries = [e for e in entries if 'author' in e and _longmatch(firstauthor(e['author']), o.author)]
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
        entries = list_dup(entries, key=lambda e:e.get('doi',''), filter_key=isvaliddoi)
    if o.duplicates_tit:
        entries = list_dup(entries, key=title_id)
    if o.duplicates:
        # QUESTION MARK: in latest HEAD before merge with @malfatti's PR, I used hard-coded "PARTIAL".
        # I think that's because we might need to be inclusive here, whereas the default is conservative (parameter used for several functions with possibly differing requirements).
        # (otherwise we'd have used the command-line option o.similarity, or possibly DEFAULT_SIMILARITY)
        # Might need to revise later (the question mark is from a review after a long time without use)
        eq = lambda a, b: a['ID'] == b['ID'] or are_duplicates(a, b, similarity="PARTIAL", fuzzy_ratio=o.fuzzy_ratio)
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
        for f in o.add_files:
            if not os.path.exists(f):
                raise PapersExit(f"file {f} does not exist")
        files.extend(o.add_files)
        biblio.set_files(e, files)
        if o.rename:
            biblio.rename_entry_files(e, copy=o.copy)
        savebib(biblio, config)

    elif o.edit:
        otherentries = [e for e in biblio.db.entries if e not in entries]
        try:
            entries = edit_entries(entries)
            biblio.db.entries = otherentries + entries
        except Exception as error:
            logger.error(str(error))
            return

        savebib(biblio, config)

    elif o.fetch:
        for e in entries:
            biblio.fix_entry(e, fix_doi=True, fix_key=True, fetch_all=True, interactive=True)
        savebib(biblio, config)

    elif o.delete:
        for e in entries:
            biblio.db.entries.remove(e)
        savebib(biblio, config)

    elif o.open:
        for e in entries:
            view_entry_files(biblio, e)

    elif o.field:
        # entries = [{k:e[k] for k in e if k in o.field+['ID','ENTRYTYPE']} for e in entries]
        for e in entries:
            print(format_key(e, no_key=o.no_key),*[e.get(k, "") for k in o.field])
    elif o.key_only:
        for e in entries:
            print(e['ID'])
    elif o.one_liner:
        for e in entries:
            print(format_entry(biblio, e, no_key=o.no_key))

    else:
        print(format_entries(entries))


def statuscmd(parser, o, config):
    print(config.status(check_files=not o.no_check_files, verbose=o.verbose))


def get_parser(config=None):
    if config is None:
        config = papers.config.Config()

    parser = argparse.ArgumentParser(prog='papers', description='library management tool')
    parser.add_argument('--version', action='store_true', help='Print version string and exit.')

    subparsers = parser.add_subparsers(dest='cmd')

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
    grp.add_argument('--filesdir', default=None,
        help=f'files directory (default: {config.filesdir}')
    grp.add_argument('--bibtex', default=None,
        help=f'bibtex database (default: {config.bibtex}')
    grp.add_argument('--dry-run', action='store_true',
        help='no PDF renaming/copying, no bibtex writing on disk (for testing)')
    grp.add_argument('--relative-paths', action="store_false", dest="absolute_paths", default=None)
    grp.add_argument('--absolute-paths', action="store_true", default=None)
    grp.add_argument('--no-git', action='store_false', dest='git', default=None, help="""Do not commit the currrent action, whatever happens""")

    keyfmt = argparse.ArgumentParser(add_help=False)
    grp = keyfmt.add_argument_group('bibtex key format')
    grp.add_argument('--key-template', default=config.keyformat.template,
        help='python template for generating keys (default:%(default)s)')
    grp.add_argument('--key-author-num', type=int, default=config.keyformat.author_num,
        help='number of authors to include in key (default:%(default)s)')
    grp.add_argument('--key-author-sep', default=config.keyformat.author_sep,
        help='separator for authors in key (default:%(default)s)')
    grp.add_argument('--key-title-word-num', type=int, default=config.keyformat.title_word_num,
        help='number of title words to include in key (default:%(default)s)')
    grp.add_argument('--key-title-word-size', type=int, default=config.keyformat.title_word_size,
        help='number of title words to include in key (default:%(default)s)')
    grp.add_argument('--key-title-sep', default=config.keyformat.title_sep,
        help='separator for title words in key (default:%(default)s)')

    namefmt = argparse.ArgumentParser(add_help=False)
    grp = namefmt.add_argument_group('filename format')
    grp.add_argument('--name-template', default=config.nameformat.template,
        help='python template for renaming files (default:%(default)s)')
    grp.add_argument('--name-author-num', type=int, default=config.nameformat.author_num,
        help='number of authors to include in filename (default:%(default)s)')
    grp.add_argument('--name-author-sep', default=config.nameformat.author_sep,
        help='separator for authors in filename (default:%(default)s)')
    grp.add_argument('--name-title-word-num', type=int, default=config.nameformat.title_word_num,
        help='number of title words to include in filename (default:%(default)s)')
    grp.add_argument('--name-title-word-size', type=int, default=config.nameformat.title_word_size,
        help='min size of title words to include in filename (default:%(default)s)')
    grp.add_argument('--name-title-length', type=int, default=config.nameformat.title_length,
        help='title length to include in filename (default:%(default)s)')
    grp.add_argument('--name-title-sep', default=config.nameformat.title_sep,
        help='separator for title words in filename (default:%(default)s)')


    # status
    # ======
    statusp = subparsers.add_parser('status',
        description='view install status',
        parents=[cfg])
    statusp.add_argument('--no-check-files', action='store_true', help='faster, less info')
    statusp.add_argument('-v','--verbose', action='store_true', help='app status info')

    # install
    # =======

    installp = subparsers.add_parser('install', description='setup or update papers install',
        parents=[cfg, namefmt, keyfmt])
    installp.add_argument('--edit', action='store_true', help=f'edit existing install if any (found: {config.file})')
    installp.add_argument('--force', '--no-prompt', action='store_false', dest="prompt",
        help='no prompt, use default (useful for tests)')

    installp.add_argument('--local', action="store_true", default=None,
        help="""setup papers locally in current directory (global install by default), exposing bibtex and filesdir,
        and having the rest under .papers (config options). Only keep the cache globally.
        This might not play out too well with git tracking (local install usuall have their own git) but might be OK.""")

    installp.add_argument('--git', '--backup', action='store_true', default=None, help="""Track bibtex files with git.""")
    installp.add_argument('--git-lfs', '--backup-files', action='store_true', default=None, help="""Backup files with git-lfs (implies --git)""")
    installp.add_argument('--gitdir', default=None, help=argparse.SUPPRESS)
    installp.add_argument('--editor', help="""Set command to open text editor. Need to wait until closing ! E.g. vim or subl -w""")

    grp = installp.add_argument_group('status')
    # grp.add_argument('-l','--status', action='store_true')
    # grp.add_argument('-v','--verbose', action='store_true')
    # grp.add_argument('-c','--check-files', action='store_true')
    grp.add_argument('--no-check-files', action='store_true', help='faster, less info')
    # grp.add_argument('-v','--verbose', action='store_true', help='app status info')


    # uninstall
    # =======
    uninstallp = subparsers.add_parser('uninstall', description='remove configuration file',
        parents=[loggingp])
    uninstallp.add_argument("--recursive", action="store_true", help="if true, uninstall all papers configuration found on the path, recursively (config file only)")


    # add
    # ===
    addp = subparsers.add_parser('add', description='add PDF(s) or bibtex(s) to library',
        parents=[cfg, namefmt, keyfmt])
    addp.add_argument('file', nargs='*', default=[])
    # addp.add_argument('-f','--force', action='store_true', help='disable interactive')

    grp = addp.add_argument_group('duplicate check')
    grp.add_argument('--no-check-duplicate', action='store_true',
        help='disable duplicate check (faster, create duplicates)')
    grp.add_argument('--no-merge-files', action='store_true',
        help='distinct "file" field considered a conflict, all other things being equal')
    grp.add_argument('-u', '--update-key', action='store_true',
        help='update added key according to any existing duplicate (otherwise an error might be raised on identical insert key)')
    # grp.add_argument('-f', '--force', action='store_true', help='no interactive')
    grp.add_argument('-m', '--mode', default='i', choices=['u', 'U', 'o', 's', 'r', 'i','a'],
        help='''if duplicates are found, the default is to start an (i)nteractive dialogue,
        unless "mode" is set to (r)aise, (s)skip new, (u)pdate missing, (U)pdate with new, (o)verwrite completely.
        ''')

    grp = addp.add_argument_group('directory scan')
    grp.add_argument('--recursive', action='store_true',
        help='accept directory as argument, for recursive scan \
        of .pdf files (bibtex files are ignored in this mode')
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

    grp = addp.add_argument_group('attached files')
    grp.add_argument('-a','--attachment', nargs='+') #'supplementary material')
    grp.add_argument('-r','--rename', action='store_true',
        help='rename PDFs according to key')
    grp.add_argument('-c','--copy', action='store_true',
        help='copy file instead of moving them')

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
    grp.add_argument('--fix-key', action='store_true', help='fix key based on author name and date (in case misssing or digit)')
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
    grp.add_argument('-m', '--mode', default='i', choices=list('ims'), help='''(i)interactive mode by default, otherwise (m)erge or (s)kip failed''')
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
    listp.add_argument('--invert', action='store_true')
    listp.add_argument('--any', action='store_true', help='when several keywords: any of them')

    grp = listp.add_argument_group('search')
    grp.add_argument('-a','--author', nargs='+', help='any of the authors')
    grp.add_argument('--first-author', nargs='+')
    grp.add_argument('-y','--year', nargs='+')
    grp.add_argument('-t','--title', help='title', nargs="+")
    grp.add_argument('--abstract', help='abstract', nargs="+")
    grp.add_argument('-k', '--key', '--id', nargs='+')
    grp.add_argument('--doi', nargs='+')
    grp.add_argument('--keywords', '--tag', nargs='+')


    grp = listp.add_argument_group('check')
    grp.add_argument('--duplicates-key', action='store_true', help='list key duplicates only')
    grp.add_argument('--duplicates-doi', action='store_true', help='list doi duplicates only')
    grp.add_argument('--duplicates-tit', action='store_true', help='list tit duplicates only')
    grp.add_argument('--duplicates', action='store_true', help='list all duplicates (see --similarity)')
    grp.add_argument('--has-file', action='store_true')
    grp.add_argument('--no-file', action='store_true')
    grp.add_argument('--broken-file', action='store_true')
    grp.add_argument('--review-required', action='store_true', help='suspicious entry (invalid dois, missing field etc.)')

    grp = listp.add_argument_group('formatting')
    mgrp = grp.add_mutually_exclusive_group()
    mgrp.add_argument('--plain', action='store_false', dest="one_liner", help='print in bibtex format')
    mgrp.add_argument('-l', '-1', '--one-liner', action='store_true', help='one liner')
    mgrp.add_argument('--key-only', action='store_true')
    mgrp.add_argument('-f', '--field', nargs='+', help='specific field(s) only')
    grp.add_argument('--no-key', action='store_true')

    grp = listp.add_argument_group('action on listed results (pipe)')
    grp.add_argument('--delete', action='store_true')
    grp.add_argument('-e', '--edit', action='store_true', help='interactive edit text file with entries, and re-insert them')
    grp.add_argument('--fetch', action='store_true', help='fetch and fix metadata')
    grp.add_argument('--add-keywords', '--add-tag', nargs='+', help='add keywords to the selected entries')
    grp.add_argument('--add-files', nargs='+', help='add files to the selected entries (only one entry must be listed)')
    grp.add_argument('--rename', action='store_true', help='rename added file(s) into files folder. Used together with --add-files')
    grp.add_argument('--copy', action='store_true', help='copy added file(s) into files folder. Used together with --add-files --rename')
    grp.add_argument('-o', '--open', action='store_true', help='open attachments (if any)')

    # grp.add_argument('--merge-duplicates', action='store_true')


    # doi
    # ===
    doip = subparsers.add_parser('doi', description='parse DOI from PDF', parents=[loggingp])
    doip.add_argument('pdf')
    doip.add_argument('--image', action='store_true', help='convert to image and use tesseract instead of pdftotext')

    # fetch
    # =====
    fetchp = subparsers.add_parser('fetch', description='fetch bibtex from DOI or full-text', parents=[loggingp])
    fetchp.add_argument('doi_or_text', nargs='+', help='DOI or full text.')
    fetchp.add_argument('--scholar', action='store_true', help='use google scholar instead of default crossref for fulltext search')

    # extract
    # ========
    extractp = subparsers.add_parser('extract', description='extract pdf metadata', parents=[loggingp])
    extractp.add_argument('pdf')
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

    return parser, subparsers

#############
# Main script
#############

def handle_logging(o):
    # verbosity
    if getattr(o,'logging_level',None):
        logger.setLevel(o.logging_level)
    logger.debug("LOGGER LEVEL: "+logging.getLevelName(logger.getEffectiveLevel()))


def main(args=None):
    papers.config.DRYRUN = False  # reset in case main() if called directly
    if args is not None:
        # used in the commit message
        sys.argv = sys.argv[:1] + args

    configfile = search_config([CONFIG_FILE_LOCAL, os.path.join(".papers", "config.json")], start_dir=".", default=CONFIG_FILE)
    configfile = check_legacy_config(configfile)
    if not os.path.exists(configfile):
        config = Config()
    else:
        config = Config.load(configfile)

    installed = config.file is not None

    parser, subparsers = get_parser(config)

    o, args = parser.parse_known_args(args)

    if o.version:
        print(__version__)
        return

    handle_logging(o)

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

    if o.cmd == 'install':
        installcmd(subp, o, config)
    elif o.cmd == 'uninstall':
        if not installed:
            subp.error('no papers install was found')
        uninstallcmd(subp, o, config)
        print(config.status(verbose=True))
    elif o.cmd == 'add':
        check_install(subp, o, config) and addcmd(subp, o, config)
    elif o.cmd == 'check':
        check_install(subp, o, config) and checkcmd(subp, o, config)
    elif o.cmd == 'filecheck':
        check_install(subp, o, config) and filecheckcmd(subp, o, config)
    elif o.cmd == 'list':
        check_install(subp, o, config) and listcmd(subp, o, config)
    elif o.cmd == 'undo':
        check_install(subp, o, config) and undocmd(subp, o, config)
    elif o.cmd == 'redo':
        check_install(subp, o, config) and redocmd(subp, o, config)
    elif o.cmd == 'restore-backup':
        check_install(subp, o, config, bibtex_must_exist=False) and restorecmd(subp, o, config)
    elif o.cmd == 'git':
        if not installed:
            subp.error('papers must be installed to use git command')
        gitcmd(subp, o, config)
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


class PapersExit(Exception):
    pass


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