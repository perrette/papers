"""The command-line parser of papers"""
import argparse
import logging
from papers import logger

import papers.config
from papers.config import SETTINGS
from papers.duplicate import FUZZY_RATIO
from papers.formats import FILENAMES, FORMATS, extensions_help
from papers.identifiers import ACCEPTED as ENTRY_IDS
from papers.merge import ON_DUPLICATE
from papers.utils import file_uri_to_path
from papers.cli.backup_cmds import undocmd, redocmd, restorecmd, historycmd, gitcmd
from papers.cli.entry_cmds import addcmd, checkcmd, listcmd, editcmd, rmcmd, tagcmd, opencmd
from papers.cli.fetch_cmds import doicmd, fetchcmd, extractcmd
from papers.cli.file_cmds import (filecheckcmd, file_renamecmd, file_mvcmd, file_attachcmd, file_detachcmd, file_rmcmd,
                                  file_checkcmd, file_fixcmd, file_cleancmd, file_checksumcmd)
from papers.cli.file_cmds import OPENALEX_ASK, file_fetchcmd
from papers.freepdf import LEAST_VERSIONS
from papers.openalex import API_KEY_ENV, MAILTO_ENV
from papers.cli.library_cmds import statuscmd, initcmd, configcmd, migratecmd, installcmd, uninstallcmd
from papers.cli.pool_cmds import pullcmd, pushcmd, synccmd, exportcmd


# help of the name.* and key.* settings on the command line (`what` is key or
# filename; the template has its own help)
_FORMAT_HELP = {
    'author-num': 'number of authors in the {what} (not for {{authorX}})',
    'author-sep': 'separator of the authors in the {what}',
    'title-word-num': 'maximum number of title words in the {what}',
    'title-word-size': 'minimum length of a title word: shorter words are left out of the {what}',
    'title-length': 'maximum length of the title in the {what} (the last words are dropped until it fits; a longer first word is cut)',
    'title-sep': 'separator of the title words in the {what}',
    'unknown-template': 'template of the {what} of an entry without author, year or title',
    'unknown-strict': 'the unknown template applies when the author, the year or the title is missing; '
                      'with this option, only when all three are missing',
}


class _Deprecated(argparse.Action):
    """a deprecated form of an option (removed in v4), hidden from the help:
    warns with the new form, and sets the option's destination (the values given, or `const`
    for a flag). The warning is printed once per parser, though the option
    is repeated or the arguments parsed again (papers.cli._main does)"""

    def __init__(self, option_strings, dest, new, nargs=0, const=True, help=None, **kw):
        super().__init__(option_strings, dest, nargs=nargs, const=const, help=argparse.SUPPRESS, **kw)
        self.new = new

    def __call__(self, parser, namespace, values, option_string=None):
        warned = parser.__dict__.setdefault('_deprecated_warned', set())
        if option_string not in warned:
            warned.add(option_string)
            logger.warning(f'{option_string} is deprecated: use {self.new}')
        setattr(namespace, self.dest, self.const if self.nargs == 0 else values)


class _Ignored(argparse.Action):
    """an option of papers before the history (see design/history.md): it
    does nothing, and says so once per parser"""

    def __init__(self, option_strings, dest, why, nargs=0, help=None, **kw):
        super().__init__(option_strings, argparse.SUPPRESS, nargs=nargs, default=argparse.SUPPRESS,
                         help=argparse.SUPPRESS, **kw)
        self.why = why

    def __call__(self, parser, namespace, values, option_string=None):
        warned = parser.__dict__.setdefault('_deprecated_warned', set())
        if option_string not in warned:
            warned.add(option_string)
            logger.warning(f'{option_string} is ignored: {self.why}')


_NO_GIT = 'papers keeps the history of the libraries without git (see `papers history`)'
_NO_GIT_LFS = 'papers keeps the files that its commands delete in its history (see `papers history`)'


# the deprecated commands (removed in v4): they work, with a warning, and the help does not show them
DEPRECATED_COMMANDS = ('install', 'uninstall', 'filecheck', 'doi', 'restore-backup', 'backup', 'git')


# the actions of papers list that write the library (the others list, open or export)
_LIST_ACTIONS = ('delete', 'edit', 'add_keywords', 'rename', 'attach', 'rm_tag', 'detach', 'detach_broken',
                 'fix_files', 'push', 'pull', 'sync', 'fetch', 'add_files')

def _hide_commands(subparsers, names):
    """leave the commands `names` out of the usage, the list of commands of
    the help, and the error of an unknown command (see _Parser)"""
    subparsers.visible = [n for n in subparsers.choices if n not in names]
    subparsers.metavar = '{' + ','.join(subparsers.visible) + '}'
    subparsers._choices_actions = [a for a in subparsers._choices_actions if a.dest not in names]


class _Parser(argparse.ArgumentParser):
    "an unknown command is an error that names the commands of the help only (see _hide_commands)"

    def _check_value(self, action, value):
        visible = getattr(action, 'visible', None)
        if visible is not None and value not in action.choices:
            raise argparse.ArgumentError(None, f'unknown command {value!r} (commands: {", ".join(visible)})')
        super()._check_value(action, value)


def _default(value):
    "a configured value shown in a help text (argparse formats help with %)"
    return str(value).replace('%', '%%')


def _format_parser(kind, title, what, fmt, template_help):
    """parent parser of the options --<kind>-template, --<kind>-author-num...
    of the name or key format settings (kind: name or key), defaulting to
    None: the configured values (`fmt`, a papers.filename.Format) apply"""
    parser = argparse.ArgumentParser(add_help=False)
    grp = parser.add_argument_group(title)
    for name, type_ in SETTINGS.items():
        if not name.startswith(kind + '.'):
            continue
        field = name[len(kind) + 1:]
        default = _default(getattr(fmt, field.replace('-', '_')))
        if field == 'template':
            help = template_help.format(default=default)
        else:
            help = _FORMAT_HELP[field].format(what=what) + f' (default: {default})'
        if type_ == 'bool':
            # --no-...: the configured value can be turned off too
            grp.add_argument(f'--{kind}-{field}', action=argparse.BooleanOptionalAction, default=None, help=help)
        else:
            grp.add_argument(f'--{kind}-{field}', type=int if type_ == 'int' else None, help=help)
    return parser


def _field_value(text):
    "FIELD=VALUE of add --metadata and edit --set: (field, value)"
    name, sep, value = text.partition('=')
    if not sep or not name.strip():
        raise argparse.ArgumentTypeError(f'{text!r}: FIELD=VALUE expected')
    return name.strip(), value


def _steps(text):
    "-n of undo and redo: a number of steps, 1 or more"
    try:
        n = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f'{text!r}: a number of steps expected')
    if n < 1:
        raise argparse.ArgumentTypeError(f'{text!r}: 1 step or more')
    return n


# the names of the formats in `papers export --format` (bib, json, bib.json: other forms)
_EXPORT_NAMES = {'bib': 'bibtex', 'json': 'csl-json', 'bib.json': 'bibjson', **{fmt: fmt for fmt in FORMATS}}


def _export_formats(value):
    "the formats of `papers export --format`: names of FORMATS (or bib, json), all, separated by commas"
    formats = []
    for name in (v.strip().lower() for v in value.split(',') if v.strip()):
        if name == 'all':
            formats.extend(FORMATS)
        elif name in _EXPORT_NAMES:
            formats.append(_EXPORT_NAMES[name])
        else:
            raise argparse.ArgumentTypeError(f'unknown format {name!r} (choose from bib, {", ".join(FORMATS[1:])}, all)')
    return formats


# the options shared by a command and the action of `papers list` that stands for it
# =============================================================================

_EXCHANGE_HELP = '''what to do with an entry changed on both
    sides since the last pull or push: ask (dialogue; the default in a terminal), keep (the values
    of the side that receives the changes are kept: {keep}), update (the values of the side they
    come from are taken: {update}), skip (the entry is
    left as it is, and comes again next time), error (stop before saving; the default
    without a terminal). Fields changed on one side only need no decision.'''
_SYNC_KEEP = "the library's in a pull, the pool's in a push"
_SYNC_UPDATE = "the pool's in a pull, the library's in a push"


def _on_duplicate_option(p, keep, update):
    "--on-duplicate of pull, push and sync (and of their list actions)"
    p.add_argument('--on-duplicate', choices=ON_DUPLICATE,
        help=_EXCHANGE_HELP.format(keep=keep, update=update))


def _export_options(p, format='--format', files='--files'):
    "the --format and --files options of export (in list: --export-format and --export-files)"
    p.add_argument(files, choices=['copy', 'link', 'none'], default='copy',
        help='copy the files into DIR/files (a hard link when possible; default), link to them where '
             'they are, or leave the file links out')
    p.add_argument(format, action='append', type=_export_formats, metavar='FORMAT',
        help=f'''the files of entries written in DIR: bib ({FILENAMES['bibtex']}, the default: DIR is a papers
        library), {', '.join(f'{fmt} ({FILENAMES[fmt]})' for fmt in FORMATS[1:])}, or all (RIS needs the
        rispy package); repeat the option or separate the formats with commas, e.g. {format} bib,ris''')


def _fix_move_option(p, search='--search', rename=False):
    "--move of file fix (and of list --fix-files and --rename)"
    p.add_argument('--move', action='store_true',
                   help=f'move the files found in the {search} folders instead of copying them (a file in the '
                        'files directory of another library is still copied)'
                        + ('; with --rename: files mode move, whatever the setting' if rename else ''))


def get_parser(config=None):
    if config is None:
        config = papers.config.Config()

    parser = _Parser(prog='papers', description='library management tool')
    parser.add_argument('--version', action='store_true', help='Print version string and exit.')
    parser.add_argument('-C', metavar='DIR', dest='directory',
        help='run as if papers was started in DIR (before the command name)')

    subparsers = parser.add_subparsers(dest='cmd')

    # entries named on the command line (see papers.identifiers)
    _selection_help = (f'KEY: {ENTRY_IDS} (a former key in the ids field works too); '
                       '- reads them from the standard input, one per line')

    def _command(p, func, library=False, bibtex_must_exist=True, writes=True):
        """the function of a command, called as func(p, o, config) by
        papers.cli.main; with library=True, config is the library of the
        command line (see papers.cli.common.check_install), locked while
        the command runs (see papers.lock) unless writes is False, or a
        function of the parsed arguments that says False"""
        p.set_defaults(func=func, library=library, bibtex_must_exist=bibtex_must_exist, command_parser=p,
                       writes=writes)

    def _files_mode_options(grp, add=False):
        "the files mode options of add (with its aliases -r/--rename and -c), file attach and file rename"
        grp.add_argument('--move', action='store_true', help='files mode move, whatever the setting')
        if add:
            grp.add_argument('-r','--rename', action='store_true', help='same as --move')
        grp.add_argument(*(['-c'] if add else []), '--copy', action='store_true',
            help='files mode copy, whatever the setting')
        grp.add_argument('--link', action='store_true', help='files mode link, whatever the setting')

    # configuration (re-used everywhere)
    # =============
    loggingp = argparse.ArgumentParser(add_help=False)
    loggingp.add_argument('-v', '--verbose', action='store_true',
        help='say what papers does, step by step')
    loggingp.add_argument('--debug', action='store_const', dest='logging_level', const=logging.DEBUG,
        help='debugging messages, and the traceback of errors')
    loggingp.add_argument('--info', action=_Deprecated, dest='verbose', new='-v')
    # former logging levels: --warn is the default, --error hides the warnings
    loggingp.add_argument('--warn', action='store_const', dest='logging_level', const=logging.WARN,
        help=argparse.SUPPRESS)
    loggingp.add_argument('--error', action='store_const', dest='logging_level', const=logging.ERROR,
        help=argparse.SUPPRESS)
    loggingp.add_argument('--color', choices=['auto', 'always', 'never'], default='auto',
        help='colours and hyperlinks in the output: auto (default) when the output is a terminal and the '
             'NO_COLOR environment variable is not set')
    loggingp.add_argument('--porcelain', action='store_true',
        help='output for programs (as git\'s): the standard output has only the entries that the command '
             'added, modified, renamed or removed, or found already in the library, one per line: "added KEY", '
             '"modified KEY", "renamed OLD NEW", "removed KEY", "existing KEY"; every other message goes to the '
             'standard error (except the listing of papers list, which stays on the standard output)')

    cfg = argparse.ArgumentParser(add_help=False, parents=[loggingp])
    grp = cfg.add_argument_group('config')
    grp.add_argument('--filesdir', default=None, type=file_uri_to_path,
        help=f'files directory (default: {_default(config.filesdir)})')
    grp.add_argument('--bibtex', default=None, type=file_uri_to_path,
        help=f'bibtex database (default: {_default(config.bibtex)})')
    grp.add_argument('--dry-run', action='store_true',
        help='no PDF renaming/copying, no bibtex writing on disk (for testing)')
    grp.add_argument('--relative-paths', action="store_false", dest="absolute_paths", default=None,
        help=argparse.SUPPRESS)  # deprecated: `papers config paths relative`
    grp.add_argument('--absolute-paths', action="store_true", default=None,
        help=argparse.SUPPRESS)  # deprecated: `papers config paths absolute`
    grp.add_argument('--no-git', action=_Ignored, why=_NO_GIT)

    # the format options default to None: the configured values apply
    keyfmt = _format_parser('key', 'bibtex key format', 'key', config.keyformat,
        '''python template for generating keys (default: {default}). The template applies to entries
        generated from a PDF or a DOI; entries added from a bibtex file keep their original key
        unless -u/--update-key is passed.''')
    namefmt = _format_parser('name', 'filename format', 'filename', config.nameformat,
        'python template for renaming files (default: {default})')


    # status
    # ======
    statusp = subparsers.add_parser('status',
        description='show the library, its pool and its settings (with -v/--verbose: also where '
                    'each setting comes from)',
        parents=[cfg])
    statusp.add_argument('--no-check-files', action='store_true', help='faster, less info')
    _command(statusp, statuscmd)

    # init
    # ====
    initp = subparsers.add_parser('init', description='create a library in the current directory, '
        'or in DIR (created if missing): a self-contained library (its own entries and files, no pool), '
        'or with --pool PATH a shallow library, which takes its entries from the library PATH and links '
        'to its files. It asks no questions: every setting has a default (from the global configuration, '
        'or built in), the options below override them, and later changes go through `papers config`.',
        parents=[loggingp, namefmt, keyfmt])
    initp.add_argument('dir', nargs='?', metavar='DIR',
        help='directory of the library (default: the current directory); like DIR, the paths of '
             '--bibtex, --filesdir and --pool are relative to the current directory')
    initp.add_argument('--bibtex', type=file_uri_to_path,
        help='bibtex file (default: papers.bib, or the first .bib file of the directory)')
    initp.add_argument('--filesdir', type=file_uri_to_path,
        help='files directory (default: files, or an existing pdfs/, papers/... folder)')
    initp.add_argument('--pool', metavar='PATH',
        help='a shallow library that uses the library PATH as pool (PATH must be a library without '
             'pool; a relative PATH is stored relative to the library): `papers add` looks in PATH first and adds the new '
             'entries and their files to it, and the library links to the files of PATH. Default: no '
             'pool, a self-contained library')
    initp.add_argument('--shallow', action='store_true',
        help='same as --pool with the default library (`papers config --global default`)')
    initp.add_argument('--global', action='store_true', dest='is_global',
        help='also register the library as the default library (used outside of any library, and by '
             '--shallow); DIR is required (`papers init . --global` for the current directory)')
    initp.add_argument('--paths', choices=['relative', 'absolute'],
        help='file links in the bibtex relative to the bibtex directory, or absolute '
             f'(default: {config.inherited("paths")})')
    initp.add_argument('--git', '--no-git', action=_Ignored, why=_NO_GIT)
    initp.add_argument('--git-lfs', action=_Ignored, why=_NO_GIT_LFS)
    initp.add_argument('--editor', help='command to open a text editor; it must wait until the editor is closed, e.g. vim or "subl -w"')
    _command(initp, initcmd)

    # config
    # ======
    configp = subparsers.add_parser('config', parents=[loggingp],
        description='get or set the settings of the library (git style): without KEY, list the '
                    'settings and where each comes from (library, global or default); with KEY, '
                    'print its value; with KEY VALUE..., set it in the library configuration',
        epilog='settings: ' + ', '.join(SETTINGS) + '; with --global, also default (the default library: '
               'PATH or none). pool PATH (a library without pool, not the library itself) makes the library shallow: it links to the '
               'pool\'s copies of its PDFs, and its own copies are deleted; each PDF must be in the pool entry '
               'already, otherwise nothing changes and papers names the entries to push first (`papers push '
               '--pool PATH KEY...`). pool none makes a shallow library self-contained: the pool files that it '
               'links to are copied into its files directory. papers lists what it will do and asks to continue.')
    configp.add_argument('key', nargs='?', metavar='KEY')
    configp.add_argument('values', nargs='*', metavar='VALUE')
    configp.add_argument('--unset', metavar='KEY', help='remove the setting: the global or default value applies again (pool: none)')
    configp.add_argument('--prune', action='store_true',
        help='remove from the library configuration file the settings equal to their global or default value '
             '(they follow it from then on); a setting given explicitly (`papers init`, `papers config NAME '
             'VALUE`) is kept in the file, even with the default value')
    configp.add_argument('--global', action='store_true', dest='is_global',
        help=f'the global configuration, per user ({_default(papers.config.MACHINE_CONFIG_FILE)}), instead of '
             'the library\'s: the default library, and the default settings of the libraries')
    configp.add_argument('-y', '--yes', action='store_true', help='do not ask before copying or deleting the files (pool)')
    configp.add_argument('--dry-run', action='store_true', help='do not save (pool: only show what would be done)')
    _command(configp, configcmd)

    # migrate
    # =======
    migratep = subparsers.add_parser('migrate', parents=[cfg],
        description='one-time upgrades from papers v2. Without option: move the configuration of the '
                    'current library from .papersconfig.json (papers v2) to .papers/config.json, and turn the '
                    'global configuration of v2 into a library configuration in the directory of its bibtex '
                    '(a self-contained library: its own files, no pool), registered, where it is, as the '
                    'default library. The library configurations of v2 are read as self-contained libraries '
                    '(no pool), and moved to .papers/config.json when papers saves them.')
    migratep.add_argument('--relative', action='store_true',
        help='store the file links of the migrated library relative to its bibtex '
             '(default: keep the previous setting)')
    migratep.add_argument('--folders', action='store_true',
        help='move the files of entries kept in folders of papers < 2.19 (<name>/ with a hidden '
             '.<name>.bib) to the flat layout of the files directory')
    _command(migratep, migratecmd)

    # install
    # =======

    installp = subparsers.add_parser('install', description='deprecated alias of `papers init`; on an existing library, '
        'updates it (deprecated: use `papers config`)',
        parents=[cfg, namefmt, keyfmt])
    installp.add_argument('--edit', action='store_true',
        help=f'update existing install non-interactively (updating is the default; --edit also suppresses prompts) (found: {config.file})')
    installp.add_argument('--reset', action='store_true',
        help='discard the pre-existing configuration and start over from defaults (default: update it)')
    installp.add_argument('-y', '--yes', action='store_true', help='do not ask: accept the defaults')
    installp.add_argument('--no-prompt', '--force', action=_Deprecated, dest='yes', new='-y/--yes')

    installp.add_argument('--local', action="store_true", default=None,
        help=argparse.SUPPRESS)  # ignored: a library configuration is always local
    installp.add_argument('--global', action="store_false", dest='local', default=None,
        help="no longer supported: an error that changes nothing (`papers init PATH --global` creates the "
             "default library, `papers config --global default PATH` registers an existing one)")

    installp.add_argument('--git', '--backup', action=_Ignored, why=_NO_GIT)
    installp.add_argument('--git-lfs', '--backup-files', action=_Ignored, why=_NO_GIT_LFS)
    installp.add_argument('--editor', help="""Set command to open text editor. Need to wait until closing ! E.g. vim or subl -w""")
    installp.add_argument('--pool', metavar='PATH|none', help=argparse.SUPPRESS)

    grp = installp.add_argument_group('status')
    grp.add_argument('--no-check-files', action='store_true', help='faster, less info')
    _command(installp, installcmd)


    # uninstall
    # =======
    uninstallp = subparsers.add_parser('uninstall', description='deprecated: remove the library configuration '
        '(`rm -r .papers`); its history: `papers history --remove`',
        parents=[loggingp])
    uninstallp.add_argument("--recursive", action="store_true", help=argparse.SUPPRESS)  # deprecated and ignored
    uninstallp.add_argument("--remove-backup", "--remove-history", action="store_true", dest='remove_history',
        help="also remove the history of the library (`papers history --remove`)")
    _command(uninstallp, uninstallcmd)


    # add
    # ===
    addp = subparsers.add_parser('add', description='''add PDF(s), bibtex(s), RIS (.ris) or CSL-JSON (.json)
        file(s) to library. In a
        shallow library, the files go to the files directory of the pool (files mode
        move or copy; with link, they stay where they are), and the entries to the pool too. Adding a bibtex file (`papers add other.bib`) copies its entries once, with no
        memory of where they came from; `papers pull` instead keeps the entries linked to the pool,
        and later pulls bring its corrections.''',
        parents=[cfg, namefmt, keyfmt])
    addp.add_argument('file', nargs='*', default=[], type=file_uri_to_path)
    addp.add_argument('--format', choices=FORMATS,
        help=f'''the format of the added files that are not PDFs (default: from the extension:
        {extensions_help()}). RIS needs the rispy package.''')

    grp = addp.add_argument_group('duplicate check',
        description='''An added entry is the same paper as a library entry when they have
        the same DOI, arXiv id, ISBN (two books), or else the same authors and title.
        The library entry keeps its key; fields only in the added entry are added and
        the file links are merged. An entry that brings nothing new is not asked about.''')
    grp.add_argument('--on-duplicate', choices=ON_DUPLICATE,
        help='''what to do when the added entry is in the library, with conflicting
        values or fields to add: ask (dialogue; the default in a terminal), keep (merge,
        conflicts keep the library's value: the library receives the entry), update (merge,
        conflicts take the value of the added entry),
        skip (leave the library entry untouched, do not add), error (stop before saving;
        the default without a terminal)''')
    grp.add_argument('--no-check-duplicate', action='store_true',
        help='disable duplicate check (faster, create duplicates)')
    grp.add_argument('--no-pool', action='store_true',
        help='''do not look in the pool first (by default, a PDF, DOI or bibtex entry that is
        the same paper as a pool entry is taken from the pool, with its files, without fetching)''')
    grp.add_argument('--pool', metavar='PATH',
        help='''look in the library PATH first, instead of the pool (PATH must be a library without
        pool): a paper that PATH has is taken from it, with its files (copied as the files mode
        says; in a shallow library, into the files directory of its pool), and later
        `papers pull --pool PATH` brings its corrections. Nothing is added to PATH. Not the same as
        `papers -C PATH add`, which adds to the library PATH.''')
    grp.add_argument('--no-merge-files', action='store_true',
        help=argparse.SUPPRESS)  # deprecated and ignored: file links are always merged
    grp.add_argument('-u', '--update-key', action='store_true',
        help='''regenerate the key of the entries new to the library from the key template
        (see "bibtex key format" options). A duplicate always keeps the key of the library.''')
    grp.add_argument('-m', '--mode', choices=['u', 'U', 'o', 's', 'r', 'i', 'a'],
        help=argparse.SUPPRESS)  # deprecated: --on-duplicate (i: ask, u: keep, U and o: update, s: skip, r: error, a: --no-check-duplicate)

    grp = addp.add_argument_group('directory scan')
    grp.add_argument('-R', '--recursive', action='store_true',
        help='accept directory as argument, for recursive scan \
        of .pdf and .bib files; files named <name>--<label>.<ext> next to <name>.pdf \
        are added as attachments of its entry')
    grp.add_argument('--ignore-errors', action='store_true',
        help='ignore errors when adding multiple files')

    grp = addp.add_argument_group('metadata',
        description='''The fields given here replace those found in the PDF, fetched from the DOI,
        or read from the added bibtex (one entry only). They do not change an entry already in
        the library (same DOI): use `papers edit`.''')
    grp.add_argument('--doi', help='provide DOI -- skip parsing PDF')
    grp.add_argument('--key', help='the key of the entry (instead of a key made from the key template); '
                     'alone, the entry of that key is taken from the pool')
    grp.add_argument('--type', help='entry type (article, book...)')
    grp.add_argument('--title', help='the title')
    grp.add_argument('--author', help='the authors, e.g. "Smith, John and Doe, Jane"')
    grp.add_argument('-a', nargs='+', dest='author_short', metavar='NAME',
        help='''same as --author (the values after the name are files to add, as the FILE
        arguments). In papers v2, -a FILE... attached files: when every value
        of -a is an existing file (or a URL), they are attached as with --attach, with a
        warning (until v4)''')
    grp.add_argument('--journal', help='the journal')
    grp.add_argument('--year', help='the year')
    grp.add_argument('--metadata', nargs="+", metavar="FIELD=VALUE", type=_field_value,
        help='any fields')
    grp.add_argument('--no-query-doi', action='store_true', help='do not attempt to parse and query doi')
    grp.add_argument('--no-query-fulltext', action='store_true', help='do not attempt to query fulltext in case doi query fails')
    search = grp.add_mutually_exclusive_group()
    search.add_argument('--scholar', action='store_true', help='use google scholar instead of crossref')
    search.add_argument('--openalex', action='store_true',
        help='use OpenAlex (open API, CC0 data) instead of crossref; without a free API key (environment variable OPENALEX_API_KEY) OpenAlex allows about 100 searches a day')

    grp = addp.add_argument_group('files',
        description=f'''What happens to the added PDF, the files of an added bibtex, and the
        attached files, is the `files` setting of the library (found: {config.files}):
        move: place them in the files directory, under a name made from the name
        template, and remove the original; copy: place them there, and keep the original
        (a hard link when possible, otherwise a copy); link: leave them where they are,
        the entry links to them there. A file that belongs to another library (inside
        its files directory) is never moved: it is copied instead. In a library that is
        shallow, the file links are those of the pool entry: move and copy place the files in
        the files directory of the pool, link leaves them where they are and the pool entry
        links to them there too.''')
    grp.add_argument('--attach', nargs='+', type=file_uri_to_path, dest='attachment', metavar='FILE',
        help='attach these files to the entry (e.g. supplementary material)')
    grp.add_argument('--attachment', nargs='+', type=file_uri_to_path, dest='attachment_deprecated',
        help=argparse.SUPPRESS)  # deprecated: --attach
    grp.add_argument('--fetch-pdf', action='store_true',
        help='with --doi DOI (no FILE): also download the free PDF of the entry and attach it, '
             'as `papers file fetch KEY` does')
    _files_mode_options(grp, add=True)

    grp = addp.add_argument_group('actions')
    grp.add_argument('-e', '--edit', action='store_true', help='edit entry')
    grp.add_argument('-o', '--open', action='store_true', help='open files')
    _command(addp, addcmd, library=True)

    # check
    # =====
    checkp = subparsers.add_parser('check', description='check and fix entries',
        parents=[cfg, keyfmt])
    checkp.add_argument('entries', nargs='*', metavar='KEY',
        help='check these entries only (default: all): ' + _selection_help)
    checkp.add_argument('-k', '--keys', nargs='+', help='apply check on this key subset (same as the KEY arguments)')
    checkp.add_argument('-y', '--yes', action='store_true',
        help='do not ask: apply the changes of the fixes and fetches (and --on-duplicate skip by default)')
    checkp.add_argument('-f', '--force', action=_Deprecated, dest='yes', new='-y/--yes')

    grp = checkp.add_argument_group('entry key')
    grp.add_argument('--fix-key', action='store_true', help='fix key based on author name and date (in case missing or digit)')
    grp.add_argument('--key-ascii', action='store_true', help='replace keys unicode character with ascii')
    grp.add_argument('--auto-key', action='store_true', help='new, auto-generated key for all entries')

    grp = checkp.add_argument_group('crossref fetch and fix')
    grp.add_argument('--fix-doi', action='store_true', help='fix doi for some common issues (e.g. DOI: inside doi, .received at the end')
    grp.add_argument('--fetch', action='store_true', help='fetch metadata from doi and update entry')
    grp.add_argument('--fetch-all', action='store_true',
        help='''--fetch, and for entries without DOI, a crossref search by title and authors.
        The best result is taken only if its title is the same or nearly the same (after
        normalization) and it has an author family name in common with the entry; otherwise
        the entry is left unchanged and a warning is printed. The fetched fields replace or add
        to those of the entry; the key and the files are kept. Asks before each change unless -y.''')

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
        and skip with -y/--yes)''')
    grp.add_argument('-m', '--mode', choices=list('ims'), help=argparse.SUPPRESS)  # deprecated: --on-duplicate
    _command(checkp, checkcmd, library=True)


    # file
    # ====
    filep = subparsers.add_parser('file', description='the files of the entries: rename, move, attach, '
        'fetch, detach, remove, check them, and clean the files directory')
    filesub = filep.add_subparsers(dest='file_cmd',
                                   metavar="{rename,mv,attach,fetch,detach,rm,check,fix,clean,checksum}")
    _command(filep, None)  # without subcommand: the help of papers file

    p = filesub.add_parser('rename', parents=[cfg, namefmt],
        help='place the files in the files directory under their template name',
        description='place the files of the entries (all entries without KEY) in the files directory, '
                    'under the name made from the name template. The files already there are renamed; the '
                    'others are moved, copied or left where they are as the files setting says (ask: papers '
                    'asks for each one). A file that belongs to another library (inside its files directory) '
                    'is copied, not moved.')
    p.add_argument('entries', nargs='*', metavar='KEY', help=_selection_help)
    grp = p.add_argument_group('files mode')
    _files_mode_options(grp)
    grp.add_argument('--keep-source', action='store_true',
        help='keep the files where they are too (a hard link when possible, otherwise a copy): same as --copy')
    _command(p, file_renamecmd, library=True)

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
    _command(p, file_mvcmd, library=True)

    p = filesub.add_parser('attach', parents=[cfg, namefmt],
        help='attach files to an entry',
        description='attach files to an existing entry. What happens to the files is the files setting '
                    f'(found: {config.files}), as for `papers add`; the files the entry had are left as they are.')
    p.add_argument('key', metavar='KEY', help=f'{ENTRY_IDS} of the entry')
    p.add_argument('files', nargs='+', metavar='FILE', type=file_uri_to_path, help='files or URLs')
    _files_mode_options(p)
    _command(p, file_attachcmd, library=True)

    p = filesub.add_parser('fetch', parents=[cfg, namefmt],
        help='download the free PDF of entries and attach it',
        description='find a free (open-access) PDF of each entry from its DOI or arXiv id, download it and '
                    'attach it as `papers file attach` does (the downloaded file goes to the files directory, '
                    'under its template name). The links are tried in this order, until one gives a PDF: the '
                    'published version (the citation_pdf_url of the publisher\'s article page, then the '
                    'open-access locations of OpenAlex), the accepted manuscript, the submitted version '
                    '(preprint) and arXiv. Each line says which version was attached and where it came from. '
                    'An entry that links to a PDF already is skipped (--again fetches it anyway). An entry whose '
                    'PDF link is broken first gets the repair of `papers file fix` (the file found in the library '
                    'by checksum, the pool, the other libraries of the machine, the --search folders or the '
                    'history), and is downloaded only if that gives it no PDF. A PDF '
                    'with the content of a file of the entry is not attached; a URL downloaded before on this machine '
                    'whose file the library has is not downloaded again. OpenAlex reads the environment '
                    f'variables {API_KEY_ENV} (a free API key) and {MAILTO_ENV} (an email address, also given to '
                    'the publishers in the user agent). Exit 1 if an entry got no PDF (the others are attached); '
                    'the error gives the links to open in a browser.')
    p.add_argument('entries', nargs='*', metavar='KEY', help=_selection_help)
    p.add_argument('--missing', action='store_true',
        help='the entries without PDF (of KEY..., or of the whole library); papers asks before more than '
             f'{OPENALEX_ASK} entries with a DOI when {API_KEY_ENV} is not set')
    p.add_argument('--version', choices=LEAST_VERSIONS, default='any', dest='least_version',
        help='the least final version to attach: published (the version of record only), accepted (also the '
             'accepted manuscript), any (default: also the submitted version and the arXiv preprint)')
    p.add_argument('--supplements', action='store_true',
        help='also attach the supplementary PDFs that the article page links (a link with "suppl" in its URL '
             'or text, or a citation_supplementary_material tag), as other files of the entry '
             '(<name>--<label>.pdf); also for an entry that has its PDF')
    p.add_argument('--again', action='store_true', help='fetch the PDF of an entry that links to a PDF already')
    p.add_argument('--search', action='append', metavar='DIR',
        help='for an entry whose PDF link is broken, also look for its file in DIR (recursively), by file '
             'name, else by the template name of the entry, as `papers file fix --search` (can be repeated)')
    p.add_argument('-y', '--yes', action='store_true', help='do not ask before querying OpenAlex for many entries')
    _command(p, file_fetchcmd, library=True)

    _key_help = (f'only the links of these entries ({ENTRY_IDS}; - reads them from the standard input); '
                 'write the files before --key, which takes several values')
    p = filesub.add_parser('detach', parents=[cfg],
        help='remove file links from the entries (the files are kept)',
        description='remove the links to FILE from every entry that links to it (only from the entries of '
                    '--key with --key); with --key and no FILE, remove all the links of these entries; with '
                    '--broken, remove the broken links. The files are never deleted (`papers file rm` does that).')
    p.add_argument('files', nargs='*', metavar='FILE', type=file_uri_to_path)
    p.add_argument('-k', '--key', nargs='+', action='extend', metavar='KEY', help=_key_help)
    p.add_argument('-y', '--yes', action='store_true',
        help='do not ask before deleting more files than the history keeps (the history-size setting)')
    p.add_argument('-r', action='store_true', dest='recursive', help='FILE can be a folder: the links to the files inside it')
    p.add_argument('--broken', action='store_true', help='remove the broken links (of all entries without --key)')
    _command(p, file_detachcmd, library=True)

    p = filesub.add_parser('rm', parents=[cfg],
        help='remove file links from the entries and delete the files',
        description='like git rm: remove the links to FILE from every entry that links to it, then delete '
                    'the file. A file that no entry links to is an error, and nothing changes. With --key, only '
                    'the links of these entries are removed, and a file that another entry still links to is '
                    'kept. A file of a pool is not deleted, only the link, except in a shallow library: '
                    'there the link is removed from the pool entry too, and the file is deleted unless another '
                    'entry of the pool links to it. -r FOLDER: the linked files '
                    'inside FOLDER (the unlinked files stay, and the folders left empty are removed).')
    p.add_argument('files', nargs='*', metavar='FILE', type=file_uri_to_path)
    p.add_argument('-k', '--key', nargs='+', action='extend', metavar='KEY', help=_key_help)
    p.add_argument('-r', action='store_true', dest='recursive', help='FILE can be a folder: the linked files inside it')
    _command(p, file_rmcmd, library=True)

    _pool_help = ('also look for the files of the broken links in the library PATH, among the files of the '
                  'entry of the same paper, after the pool of the library and before the --search folders '
                  '(can be repeated)')
    _search_help = ('also look for the files of the broken links in DIR (recursively), by file name, else by '
                    'the template name of the entry (can be repeated)')
    p = filesub.add_parser('check', parents=[cfg],
        help='report broken links, identical files, DOI mismatches',
        description='report broken links and the files found for them, links that can be repaired (paths '
                    'saved by Mendeley), files linked twice and identical files (same checksum) of an entry, and '
                    'with --metadata a DOI of the PDF that differs from the entry\'s. Nothing changes: '
                    '`papers file fix` applies the repairs.')
    p.add_argument('entries', nargs='*', metavar='KEY', help=_selection_help + ' (default: all entries)')
    p.add_argument('--metadata', action='store_true', help='also compare the DOI of the PDFs with the entry (parses the PDFs)')
    p.add_argument('--pool', action='append', metavar='PATH', help=_pool_help)
    p.add_argument('--search', action='append', metavar='DIR', help=_search_help)
    _command(p, file_checkcmd, library=True, writes=False)

    p = filesub.add_parser('fix', parents=[cfg],
        help='repair the file links that `papers file check` reports',
        description='apply the safe repairs that `papers file check` reports: repair the paths saved by '
                    'Mendeley, remove the second link of a file linked twice or of identical files (the files '
                    'are kept), and relink the broken links to the files found in the library by checksum '
                    '(.papers/files.json), in the pool or the libraries of --pool PATH (same paper), in the other '
                    'libraries of the machine (those of `papers history --all`, by checksum), or '
                    'in the --search folders. A file found is never moved: it is '
                    'copied (a hard link when possible) into the files directory, named as `papers file '
                    'attach` names it (in a shallow library, into the files directory of its pool; a file of '
                    'its pool is linked where it is); in link mode or without files directory, it is linked '
                    'where it is. With --dry-run, list the repairs and change nothing.')
    p.add_argument('entries', nargs='*', metavar='KEY', help=_selection_help + ' (default: all entries)')
    p.add_argument('--pool', action='append', metavar='PATH', help=_pool_help)
    p.add_argument('--search', action='append', metavar='DIR', help=_search_help)
    _fix_move_option(p)
    _command(p, file_fixcmd, library=True)

    p = filesub.add_parser('clean', parents=[cfg],
        help='remove the files of the files directory that no entry links to',
        description='remove the files of the files directory (and its subfolders) that no entry links to, '
                    'asking for each one. Hidden files and folders, and .bib files, are skipped.')
    p.add_argument('-y', '--yes', action='store_true', help='do not ask')
    _command(p, file_cleancmd, library=True)

    p = filesub.add_parser('checksum', parents=[cfg],
        help='write the checksums of the files, for undo and to find changed files',
        description='write the checksums (sha256) of the files of the entries (all entries without KEY) in '
                    '.papers/files.json. Undo, redo and restore find a file by its checksum. With the checksums '
                    'setting (true by default), the commands write the checksums of the files they move, copy, '
                    'add or link; this command writes those of the other files. A file whose content changed '
                    'since its checksum (e.g. annotated) is reported.')
    p.add_argument('entries', nargs='*', metavar='KEY', help=_selection_help + ' (default: all entries)')
    p.add_argument('--check', action='store_true',
        help='report the files that changed since their checksum, and write nothing')
    _command(p, file_checksumcmd, library=True)

    # filecheck
    # =====
    filecheckp = subparsers.add_parser('filecheck', description='deprecated: use the subcommands of `papers file`',
        parents=[cfg, namefmt])
    _command(filecheckp, filecheckcmd, library=True)

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
    listp.add_argument('--similarity', help=argparse.SUPPRESS)  # deprecated and ignored
    listp.add_argument('--invert', action='store_true',
        help='list the entries that the same command without --invert does not list')
    listp.add_argument('--any', action='store_true', help='when several keywords: any of them')

    grp = listp.add_argument_group('search')
    grp.add_argument('-a','--author', nargs='+', help='any of the authors')
    grp.add_argument('--first-author', nargs='+', help='family name of the first author')
    grp.add_argument('-y','--year', nargs='+', help='year')
    grp.add_argument('-t','--title', help='title', nargs="+")
    grp.add_argument('--abstract', help='abstract', nargs="+")
    grp.add_argument('-k', '--key', '--id', nargs='+', help='entry key')
    grp.add_argument('--doi', nargs='+', help='DOI')
    grp.add_argument('--keywords', '--tag', nargs='+', help="keywords (tags): whole tags, case-insensitive, with * patterns (--tag 'ice*'); "
                          "a tag also finds the tags under it (--tag climate: climate/amoc)")


    grp = listp.add_argument_group('check')
    for field, word in [('key', 'key'), ('doi', 'doi'), ('tit', 'title')]:
        grp.add_argument(f'--duplicates-{field}', action=_Deprecated, dest='by', const=word,
                         new=f'--duplicates --by {word}')
    grp.add_argument('--by', choices=['key', 'doi', 'title'],
        help='with --duplicates (implied): the entries that share this field instead (the same key, DOI, or '
             'title ignoring case and punctuation), whether or not they are the same paper')
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
    mgrp.add_argument('--format', choices=['line', *FORMATS, 'key'],
        help=f'line: one line per entry (the default); {", ".join(FORMATS)}: the entries in that format '
             '(file links as absolute paths; RIS needs the rispy package); key: the keys only, '
             'one per line (to pipe into the commands that take -, e.g. `papers file rename -`)')
    mgrp.add_argument('--plain', action='store_const', dest='format', const='bibtex', help='same as --format bibtex')
    mgrp.add_argument('-l', '-1', '--one-liner', action='store_const', dest='format', const='line',
        help='same as --format line')
    mgrp.add_argument('-K', '--key-only', action='store_const', dest='format', const='key',
        help='same as --format key')
    mgrp.add_argument('--field', nargs='+', help='print these fields only (after the key)')
    # -f is --force elsewhere: in v4, -f is no longer --field
    mgrp.add_argument('-f', action=_Deprecated, dest='field', nargs='+', new='--field', metavar='FIELD')
    grp.add_argument('--no-key', action='store_true', help='do not print the keys')

    grp = listp.add_argument_group('action on listed results',
        description='run a command on the listed entries, in the same process (questions and the editor work, '
                    'the library is saved once); one action at a time. The other commands that act on entries '
                    'read the keys of `papers list -K` with -, e.g. `papers list smith -K | papers check -`')
    grp.add_argument('--delete', action='store_true',
        help='remove the listed entries, as `papers rm` (asks whether to delete their files, in a terminal)')
    grp.add_argument('--delete-files', action='store_true', help='with --delete: also delete their files, as `papers rm --delete-files` (an error in a shallow library)')
    grp.add_argument('--keep-files', action='store_true', help='with --delete: keep their files, without asking')
    grp.add_argument('-e', '--edit', action='store_true', help='edit the listed entries in a text editor, as `papers edit`')
    grp.add_argument('--add-keywords', '--add-tag', nargs='+', help='add keywords (tags) to the listed entries, as `papers tag --add`')
    grp.add_argument('--rename', action='store_true',
        help='place the files of the listed entries under their template name, as `papers file rename`')
    grp.add_argument('--keep-source', action='store_true',
        help='with --rename: keep the files where they are too, as `papers file rename --keep-source`')
    grp.add_argument('-o', '--open', action='store_true',
        help='open the files of the listed entries, as `papers open`')
    grp.add_argument('--attach', nargs='+', type=file_uri_to_path, metavar='FILE',
        help='attach files to the listed entry, as `papers file attach KEY FILE...` (the files setting '
             'applies); an error unless the listing gives exactly one entry')
    grp.add_argument('--rm-tag', nargs='+', metavar='TAG',
        help='remove tags from the listed entries, as `papers tag --rm`')
    grp.add_argument('--detach', nargs='*', type=file_uri_to_path, metavar='FILE',
        help='remove the links of the listed entries to these files (without FILE: all their links), '
             'as `papers file detach FILE... --key KEY...`')
    grp.add_argument('--detach-broken', action='store_true',
        help='remove the broken links of the listed entries, as `papers file detach --broken --key KEY...`')
    grp.add_argument('--fix-files', nargs='*', metavar='DIR',
        help='repair the file links of the listed entries, as `papers file fix KEY...`; the broken links are '
             'also looked for in the folders DIR, as `papers file fix --search DIR`')
    _fix_move_option(grp, search='--fix-files', rename=True)
    grp.add_argument('--push', action='store_true', help='push the listed entries, as `papers push KEY...`')
    grp.add_argument('--pull', action='store_true', help='pull the listed entries, as `papers pull KEY...`')
    grp.add_argument('--sync', action='store_true', help='sync the listed entries, as `papers sync KEY...`')
    grp.add_argument('--pool', action='append', metavar='PATH',
        help='with --push, --pull, --sync: the library to exchange with instead of the pool, as their --pool; '
             'with --fix-files: also look for the files of the broken links in the library PATH, as '
             '`papers file fix --pool PATH` (can be repeated)')
    _on_duplicate_option(grp, keep=_SYNC_KEEP, update=_SYNC_UPDATE)
    grp.add_argument('--export', metavar='DIR',
        help='write the listed entries as a new library in DIR, as `papers export DIR KEY...`')
    _export_options(grp, format='--export-format', files='--export-files')
    grp.add_argument('--fetch', action='store_true', help=argparse.SUPPRESS)  # deprecated: papers check --fetch --fetch-all --fix-doi --fix-key --format-name -
    grp.add_argument('--add-files', nargs='+', type=file_uri_to_path, metavar='FILE',
        help=argparse.SUPPRESS)  # deprecated: --attach
    grp.add_argument('--copy', action='store_true', help=argparse.SUPPRESS)  # deprecated: --rename --keep-source
    _command(listp, listcmd, library=True, writes=lambda o: any(
        getattr(o, action, None) not in (None, False) for action in _LIST_ACTIONS))

    # edit, rm, tag
    # =============
    editp = subparsers.add_parser('edit', parents=[cfg],
        description='edit entries in a text editor (the editor setting, else $VISUAL, else $EDITOR), or '
                    'without an editor: --from, --set and --unset, --key')
    editp.add_argument('entries', nargs='+', metavar='KEY',
        help=_selection_help)
    editp.add_argument('--from', dest='from_file', metavar='FILE',
        help='replace the entry by the entry in FILE, without an editor (- reads it from the standard input: '
             'a pipe, or a paste, ended by the closing brace of the entry). The entry keeps its key, and its '
             'file and keywords fields when FILE has none; its other fields are those of FILE. The file links '
             'of FILE are relative to its directory, as with papers add FILE')
    editp.add_argument('--format', choices=FORMATS,
        help=f'the format of --from FILE (default: from the extension: {extensions_help()}; - is bibtex)')
    editp.add_argument('--set', nargs='+', metavar='FIELD=VALUE', type=_field_value,
        help='set fields of the entries, e.g. --set journal="Earth System Dynamics" year=2013 (the value '
             'replaces the whole field, as written in bibtex: author="Smith, John and Doe, Jane"). '
             'Not the key (--key) or the file links (papers file attach, detach); tags: papers tag')
    editp.add_argument('--unset', nargs='+', metavar='FIELD', help='remove fields of the entries')
    editp.add_argument('--key', dest='new_key', metavar='NEW',
        help='change the key of the entry (one entry). The records of the exchanges with pools and the '
             'crossref fields of other entries follow; LaTeX documents that cite the old key do not')
    editp.add_argument('--keep-old-key', action='store_true',
        help='with --key: the old key goes to the ids field of the entry, where papers and biblatex '
             'still find it')
    _command(editp, editcmd, library=True)

    rmp = subparsers.add_parser('rm', parents=[cfg],
        description='remove entries. Their files that no other entry links to may be deleted too: in a '
                    'terminal, papers asks for those in the files directory; without a terminal, they are kept. '
                    'Files outside the files directory are only deleted with --delete-files. In a shallow '
                    'library, the files of the pool are kept: `papers file rm FILE` deletes them.')
    rmp.add_argument('entries', nargs='+', metavar='KEY',
        help=_selection_help)
    rmp.add_argument('--delete-files', action='store_true',
        help='also delete the files of the entries that no other entry links to, without asking '
             '(also those outside the files directory); an error in a shallow library')
    rmp.add_argument('--keep-files', action='store_true', help='keep the files, without asking')
    rmp.add_argument('-y', '--yes', action='store_true',
        help='do not ask before deleting more files than the history keeps (the history-size setting)')
    _command(rmp, rmcmd, library=True)

    tagp = subparsers.add_parser('tag', parents=[cfg],
        description='tags are the keywords field of the entries (comma-separated). A tag with / is under '
                    'another tag: climate/amoc is under climate. Without option, list the tags of the '
                    'library (or of the entries KEY...) with the number of entries, the nested tags '
                    'indented under their parent, which counts the entries under it.')
    tagp.add_argument('entries', nargs='*', metavar='KEY',
        help=_selection_help)
    tagp.add_argument('--add', nargs='+', metavar='TAG', help='add tags to the entries')
    tagp.add_argument('--rm', nargs='+', metavar='TAG', help='remove tags from the entries')
    tagp.add_argument('--rename', nargs=2, metavar=('OLD', 'NEW'), help='rename a tag in the whole library, and the tags under it (climate/amoc -> NEW/amoc)')
    _command(tagp, tagcmd, library=True)

    # pull, push, sync, export
    # ========================
    _pool_help = ('another library to {what} (a library without pool), e.g. a folder shared with someone '
                  '(default: the pool of the library). The origin copies are recorded, as with the pool: '
                  'without KEY or --all, the entries exchanged with PATH before. The files are copied (in a '
                  'shallow library, the entries and files taken from PATH also go to its pool).')
    pullp = subparsers.add_parser('pull', parents=[cfg],
        description='''update the entries of the library from their entries in the pool, or the
        library --pool PATH (three-way
        merge with the origin copy of the entry, in .papers/origin/): a field changed in the pool
        only is taken, a field changed in the library only is kept, a field changed on both sides
        is a conflict. Without KEY, only the entries shared with the pool (the pool has the same
        paper: the pool entry of the origin copy, else by the same-paper rule) are updated; an
        entry without origin copy has no base, and its differences are conflicts. The keys of the library never change. KEY may also be an entry of
        the pool only (its key, DOI, arXiv id or ISBN): it is added to the library, under the pool
        key (with a letter suffix if the library has that key already). New pool files are linked
        in a shallow library (its own pool), and otherwise copied (a hard link when possible) as the
        files setting says. Unlike `papers add other.bib`, which copies entries once, the entries
        pulled keep their link to the pool (origin copy): later pulls bring the corrections made
        in the pool.''')
    pullp.add_argument('entries', nargs='*', metavar='KEY',
        help=_selection_help + ' (default: the entries shared with the pool)')
    pullp.add_argument('--pool', metavar='PATH', help=_pool_help.format(what='pull from'))
    pullp.add_argument('--all', action='store_true',
        help='all entries of the library, and every entry of the pool that the library does not have is added')
    _on_duplicate_option(pullp, keep="the library's", update="the pool's")
    pullp.add_argument('--check', action='store_true',
        help='only report: whether the pool changed since the last pull, and the entries changed in it')
    pullp.set_defaults(mode=None, yes=False)
    _command(pullp, pullcmd, library=True)

    pushp = subparsers.add_parser('push', parents=[cfg],
        description='''merge the changes of the entries of the library into their pool entries
        (three-way merge with the origin copy, as pull does in the other direction), in the pool
        of the library or the library --pool PATH. Without KEY, only the entries shared with the pool (the
        pool has the same paper) are pushed, and an entry removed from the pool is not added back;
        KEY... pushes those entries, and adds them to the pool if
        it does not have them; --all pushes every entry. Entries new to the pool get a key from
        the pool's key template; their files are copied (a hard link when possible) into the
        pool's files directory, named with the pool's name template. The pool must be a library
        (`papers init PATH` creates one).''')
    pushp.add_argument('entries', nargs='*', metavar='KEY',
        help=_selection_help + ' (default: the entries shared with the pool)')
    pushp.add_argument('--all', action='store_true',
        help='push every entry of the library, adding to the pool those it does not have')
    pushp.add_argument('--pool', metavar='PATH', help=_pool_help.format(what='push to'))
    _on_duplicate_option(pushp, keep="the pool's", update="the library's")
    pushp.set_defaults(mode=None, yes=False)
    _command(pushp, pushcmd, library=True)

    syncp = subparsers.add_parser('sync', parents=[cfg],
        description='''`papers pull`, then `papers push` of the same entries, with the pool of the
        library or the library --pool PATH. Without KEY, only the entries shared with it (it has the same
        paper) are exchanged; KEY... exchanges those entries; --all is `pull --all`
        and `push --all`: each side gets the entries it does not have. If the pull leaves
        conflicts undecided (skipped, or the dialogue quit), nothing is pushed.''')
    syncp.add_argument('entries', nargs='*', metavar='KEY',
        help=_selection_help + ' (default: the entries shared with the pool)')
    syncp.add_argument('--all', action='store_true',
        help='also add to each side the entries it does not have (pull --all, push --all)')
    syncp.add_argument('--pool', metavar='PATH', help=_pool_help.format(what='sync with'))
    _on_duplicate_option(syncp, keep=_SYNC_KEEP, update=_SYNC_UPDATE)
    syncp.set_defaults(mode=None, yes=False)
    _command(syncp, synccmd, library=True)

    exportp = subparsers.add_parser('export', parents=[cfg],
        description='''write entries as a new library in DIR, to hand over: bibtex, files,
        configuration (a self-contained library: its own files, no pool), with file links relative to
        the bibtex. `papers add DIR --recursive` adds it back; `papers config pool DIR` makes it the
        pool of the library. With --format, the entries are also, or instead, written as RIS
        (DIR/papers.ris) or CSL-JSON (DIR/papers.json), with file links relative to DIR; without
        bibtex, DIR is not a papers library (`papers add DIR/papers.ris` adds the entries of a RIS
        file; `papers add DIR --recursive` adds the bibtex files of a folder, not the RIS or JSON
        files).''')
    exportp.add_argument('dir', metavar='DIR', help='directory of the new library (must not exist, or be empty)')
    exportp.add_argument('entries', nargs='*', metavar='KEY', help=_selection_help + ' (default: all entries)')
    _export_options(exportp)
    _command(exportp, exportcmd, library=True, writes=False)

    # open
    # ====
    openp = subparsers.add_parser('open', description='open entry attachments or files with the system viewer', parents=[cfg])
    openp.add_argument('key', nargs='+', type=file_uri_to_path, help='entries (' + _selection_help + '), or existing file path(s) to open directly')
    _command(openp, opencmd)

    # doi
    # ===
    doip = subparsers.add_parser('doi', description='deprecated: use `papers extract --doi-only`', parents=[loggingp])
    doip.add_argument('pdf', type=file_uri_to_path)
    doip.add_argument('--image', action='store_true', help='convert to image and use tesseract instead of pdftotext')
    _command(doip, doicmd)

    # fetch
    # =====
    fetchp = subparsers.add_parser('fetch', description='fetch bibtex from DOI or full-text; with --pdf, download '
        'the free PDF of DOIs or arXiv ids instead (as `papers file fetch` finds it)', parents=[loggingp])
    fetchp.add_argument('doi_or_text', nargs='+', help='DOI or full text.')
    fetchp.add_argument('--pdf', action='store_true',
        help='download the free PDF of each DOI or arXiv id into the current directory, under the name of its '
             'URL (or -o FILE), and say which version it is and where it came from; with --porcelain, one line per '
             'argument for programs: "downloaded ID VERSION URL FILE" (then "refused-published ID URL" for each '
             'published link refused before an accepted or submitted version), "exists ID FILE" when the file '
             'exists (not replaced), else "refused ID URL" for each link to open in a browser, or "failed ID"')
    fetchp.add_argument('-o', '--output', metavar='FILE', type=file_uri_to_path,
        help='with --pdf and one DOI: the file to write (an existing file is not replaced: nothing is downloaded)')
    fetchp.add_argument('--version', choices=LEAST_VERSIONS, default='any', dest='least_version',
        help='with --pdf: the least final version, as for `papers file fetch`')
    search = fetchp.add_mutually_exclusive_group()
    search.add_argument('--scholar', action='store_true', help='use google scholar instead of default crossref for fulltext search')
    search.add_argument('--openalex', action='store_true',
        help='use OpenAlex (open API, CC0 data) instead of crossref; without a free API key (environment variable OPENALEX_API_KEY) OpenAlex allows about 100 searches a day')
    _command(fetchp, fetchcmd)

    # extract
    # ========
    extractp = subparsers.add_parser('extract', description='print the bibtex of PDFs, from the DOI found in the '
        'PDF (metadata or text) or a full-text search; with --doi-only, the DOI only', parents=[loggingp])
    extractp.add_argument('pdf', nargs='+', type=file_uri_to_path, help='one or several PDF files')
    extractp.add_argument('--doi-only', action='store_true',
        help='print the DOI of the PDFs: the DOI of the PDF metadata, otherwise the first DOI of the text whose '
             'title (from crossref) appears in the text')
    extractp.add_argument('-R', '--recursive', action='store_true', help='accept directories and scan them for PDF files')
    extractp.add_argument('-n', '--word-count', type=int, default=200)
    extractp.add_argument('--fulltext', action='store_true', help='fulltext only (otherwise DOI-based)')
    search = extractp.add_mutually_exclusive_group()
    search.add_argument('--scholar', action='store_true', help='use google scholar instead of default crossref for fulltext search')
    search.add_argument('--openalex', action='store_true',
        help='use OpenAlex (open API, CC0 data) instead of crossref; without a free API key (environment variable OPENALEX_API_KEY) OpenAlex allows about 100 searches a day')
    extractp.add_argument('--image', action='store_true', help='convert to image and use tesseract instead of pdftotext')
    _command(extractp, extractcmd)

    # undo
    # ====
    _restorep = argparse.ArgumentParser(add_help=False)
    _restorep.add_argument('--restore-files', action=_Ignored,
        why='undo, redo and restore bring the files back (see `papers history`)')

    _stepsp = argparse.ArgumentParser(add_help=False)
    _stepsp.add_argument('-n', '--steps', type=_steps, default=1, help='number of steps to undo or redo (1 or more)')
    _stepsp.add_argument('--library-only', action='store_true',
        help='the library only: a step that also wrote the pool (add in a shallow library, auto-push, push, '
             'sync) is undone or redone in the pool too, unless the pool changed since')

    _undo_help = ('undo the last change of the library: the bibtex and the files (moved back, deleted files '
                  'restored from the history). Each command that changes the library is a step of its '
                  'history (`papers history`); a change made outside papers (an editor, another program) is '
                  'recorded as a step of its own when papers next writes the library. To take back an older '
                  'step alone: `papers history --revert N`')
    undop = subparsers.add_parser('undo', parents=[cfg, _restorep, _stepsp], help=_undo_help, description=_undo_help)
    _command(undop, undocmd, library=True)
    _redo_help = 'redo a change undone by `papers undo`'
    redop = subparsers.add_parser('redo', parents=[cfg, _restorep, _stepsp], help=_redo_help, description=_redo_help)
    _command(redop, redocmd, library=True)
    _restore_help = ('bring the library to the step STEP of its history (see `papers history`), with its files; '
                     'without STEP, to its last step: the changes made outside papers since are undone '
                     '(and recorded: `papers redo` brings them back)')
    for name in ('restore', 'restore-backup'):
        restorep = subparsers.add_parser(name, parents=[cfg, _restorep],
            help=_restore_help if name == 'restore' else 'deprecated: use `papers restore`',
            description=_restore_help if name == 'restore' else 'deprecated: use `papers restore`')
        restorep.add_argument('state', nargs='?', metavar='STEP',
            help='the step: its identifier in `papers history`, or the start of it (4 characters or more)')
        restorep.add_argument('--ref', metavar='STEP', help='same as STEP')
        _command(restorep, restorecmd, library=True, bibtex_must_exist=False)

    # git
    # ===
    gitp = subparsers.add_parser('git',
        description=f'removed: {_NO_GIT}; to keep the library under git, run git in its folder')
    gitp.add_argument('gitargs', nargs=argparse.REMAINDER)
    _command(gitp, gitcmd)

    # history
    # =======
    _history_help = ('the steps of the library (identifier, command, time; > marks where the library is; a step '
                     'is named by its identifier, or the start of it, 4 characters or more), '
                     'the history of the machine (where, its size: the history-size setting), and the backups '
                     'of earlier versions of papers that are no longer used. The history is in a folder of '
                     'the machine (the history-dir setting), not in the library: it is not synced or shared '
                     'with it')
    for name in ('history', 'backup'):
        historyp = subparsers.add_parser(name, parents=[cfg],
            help=_history_help if name == 'history' else 'deprecated: use `papers history`',
            description=_history_help if name == 'history' else 'deprecated: use `papers history`')
        historyp.add_argument('--all', action='store_true',
            help='the histories of all the libraries: identifier, last folder, steps, space used by it only')
        historyp.add_argument('--remove', nargs='?', const='', metavar='ID',
            help='remove the history of this library (of this folder; the history itself when no other '
                 'folder uses it), or of the library ID (see --all)')
        historyp.add_argument('--drop-files', metavar='STEP|PATH',
            help='remove from the history the files that step STEP deleted, or the file deleted from PATH '
                 '(by any step): they go to the trash of the system, and undo no longer brings them back')
        historyp.add_argument('--revert', metavar='STEP',
            help='take back the changes of step STEP alone, as a new step (`papers undo` takes the revert back); '
                 'unlike `papers undo -n N`, which goes back over the last N steps, the later steps are kept. '
                 'Per entry, a three-way merge: what the step changed goes back, unless it changed since '
                 '(a conflict, as in pull); the files of the step go back as undo moves them')
        historyp.add_argument('--on-duplicate', choices=ON_DUPLICATE,
            help='with --revert: what to do with an entry that changed since the step too: ask (dialogue; the '
                 'default in a terminal), keep (the values of the entry now are kept), update (the values '
                 'before the step are taken), skip (the entry is left as it is), error (stop before saving; the default '
                 'without a terminal)')
        historyp.set_defaults(mode=None)
        historyp.add_argument('-n', type=int, default=20, help='number of steps to show (default: 20; 0: all)')
        historyp.add_argument('-y', '--yes', action='store_true', help='remove or drop without confirmation')
        if name == 'backup':
            historyp.add_argument('action', nargs='?', help=argparse.SUPPRESS)
            historyp.add_argument('patterns', nargs='*', help=argparse.SUPPRESS)
        _command(historyp, historycmd)

    _hide_commands(subparsers, DEPRECATED_COMMANDS)
    _hide_commands(filesub, ())  # the same error for an unknown subcommand
    return parser, subparsers
