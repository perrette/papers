"""The command line of papers (see papers/__main__.py for the entry point)"""
import logging
import os
import sys

import papers.config
from papers import __version__, logger
from papers.bib import DuplicateKeyError
from papers.config import CONFIG_FILE
from papers.library import check_legacy_global_config, find_config
from papers.utils import PapersExit, file_uri_to_path, find_masked_viewer, set_directory, view_pdf
from papers.cli.backup_cmds import redocmd, undocmd, restorecmd, backupcmd, gitcmd
from papers.cli.common import check_install
from papers.cli.entry_cmds import addcmd, checkcmd, editcmd, rmcmd, tagcmd, listcmd, opencmd
from papers.cli.fetch_cmds import doicmd, fetchcmd, extractcmd
from papers.cli.file_cmds import filecheckcmd, FILE_COMMANDS
from papers.cli.library_cmds import initcmd, installcmd, uninstallcmd, configcmd, migratecmd, statuscmd
from papers.cli.parser import get_parser
from papers.cli.pool_cmds import pullcmd, pushcmd, exportcmd, poolcmd


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
