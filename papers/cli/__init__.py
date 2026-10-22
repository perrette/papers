"""The command line of papers (see papers/__main__.py for the entry point)"""
import logging
import os
import sys

import papers.config
import papers.utils
from papers import __version__, logger
from papers.config import CONFIG_FILE
from papers.library import check_legacy_global_config, find_config
from papers.utils import PapersExit, file_uri_to_path, find_masked_viewer, set_directory, open_with_system
from papers.cli.common import check_install
from papers.cli.parser import get_parser


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
    papers.utils.use_color(papers.utils.color_enabled())
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
            open_with_system(f)
        return

    o, args = parser.parse_known_args(argv)
    if args:
        # the error of the command given (`papers rm: error: ...`), before anything runs
        (getattr(o, 'command_parser', None) or subparsers.choices.get(o.cmd) or parser).error(f'unrecognized arguments: {" ".join(args)}')

    if o.version:
        print(__version__)
        return

    handle_logging(o)
    papers.utils.use_color(papers.utils.color_enabled(getattr(o, 'color', 'auto')))

    if os.path.exists(CONFIG_FILE) and o.cmd != 'migrate' and not (o.cmd == 'install' and o.local is False):
        logger.warning(f"found the global configuration of papers v2 ({CONFIG_FILE}): it still applies "
                       "outside of libraries; `papers migrate` turns it into a library and the global pool")

    # modify disk state?
    if hasattr(o,'dry_run'):
        papers.config.DRYRUN = o.dry_run

    try:
        subp = subparsers.choices[o.cmd]
    except KeyError:
        parser.print_help()
        raise PapersExit()

    if o.func is None:  # papers file without subcommand
        subp.print_help()
        raise PapersExit()
    if o.library:
        config = check_install(o.command_parser, o, config, bibtex_must_exist=o.bibtex_must_exist)
    # the editor setting wins over $VISUAL and $EDITOR
    papers.utils.EDITOR = config.editor
    o.func(o.command_parser, o, config)


def main_clean_exit(args=None):
    logging.basicConfig()
    try:
        main(args)
    except PapersExit as error:
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
                     '(e.g. --on-duplicate for duplicates, -y/--yes)')
        sys.exit(1)
