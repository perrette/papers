"""The command-line parser of papers"""
import argparse
import logging
from papers import logger

import papers.config
from papers.config import SETTINGS
from papers.duplicate import FUZZY_RATIO
from papers.identifiers import ACCEPTED as ENTRY_IDS
from papers.merge import ON_DUPLICATE
from papers.utils import file_uri_to_path
from papers.cli.backup_cmds import undocmd, redocmd, restorecmd, backupcmd, gitcmd
from papers.cli.entry_cmds import addcmd, checkcmd, listcmd, editcmd, rmcmd, tagcmd, opencmd
from papers.cli.fetch_cmds import doicmd, fetchcmd, extractcmd
from papers.cli.file_cmds import (filecheckcmd, file_renamecmd, file_mvcmd, file_attachcmd, file_detachcmd, file_rmcmd,
                                  file_checkcmd, file_cleancmd)
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
    """a deprecated form of an option (removed in v4): warns with the new
    form, and sets the option's destination (the values given, or `const`
    for a flag). The warning is printed once per parser, though the option
    is repeated or the arguments parsed again (papers.cli._main does)"""

    def __init__(self, option_strings, dest, new, nargs=0, const=True, help=None, **kw):
        super().__init__(option_strings, dest, nargs=nargs, const=const,
                         help=help or f'deprecated: use {new}', **kw)
        self.new = new

    def __call__(self, parser, namespace, values, option_string=None):
        warned = parser.__dict__.setdefault('_deprecated_warned', set())
        if option_string not in warned:
            warned.add(option_string)
            logger.warning(f'{option_string} is deprecated: use {self.new}')
        setattr(namespace, self.dest, self.const if self.nargs == 0 else values)


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

    def _command(p, func, library=False, bibtex_must_exist=True):
        """the function of a command, called as func(p, o, config) by
        papers.cli.main; with library=True, config is the library of the
        command line (see papers.cli.common.check_install)"""
        p.set_defaults(func=func, library=library, bibtex_must_exist=bibtex_must_exist, command_parser=p)

    def _files_mode_options(grp, add=False):
        "the files mode options of add (with its aliases -r/--rename and -c) and file attach"
        grp.add_argument('--move', action='store_true', help='files mode move, whatever the setting')
        if add:
            grp.add_argument('-r','--rename', action='store_true', help='same as --move')
        grp.add_argument(*(['-c'] if add else []), '--copy', action='store_true',
            help='files mode copy, whatever the setting')
        grp.add_argument('--link', action='store_true', help='files mode link, whatever the setting')

    # configuration (re-used everywhere)
    # =============
    loggingp = argparse.ArgumentParser(add_help=False)
    grp = loggingp.add_argument_group('logging level (default warn)')
    egrp = grp.add_mutually_exclusive_group()
    egrp.add_argument('--debug', action='store_const', dest='logging_level', const=logging.DEBUG)
    egrp.add_argument('--info', action='store_const', dest='logging_level', const=logging.INFO)
    egrp.add_argument('--warn', action='store_const', dest='logging_level', const=logging.WARN)
    egrp.add_argument('--error', action='store_const', dest='logging_level', const=logging.ERROR)
    loggingp.add_argument('--color', choices=['auto', 'always', 'never'], default='auto',
        help='colours and hyperlinks in the output: auto (default) when the output is a terminal and the '
             'NO_COLOR environment variable is not set')

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
    keyfmt = _format_parser('key', 'bibtex key format', 'key', config.keyformat,
        '''python template for generating keys (default: {default}). The template applies to entries
        generated from a PDF or a DOI; entries added from a bibtex file keep their original key
        unless -u/--update-key is passed.''')
    namefmt = _format_parser('name', 'filename format', 'filename', config.nameformat,
        'python template for renaming files (default: {default})')


    # status
    # ======
    statusp = subparsers.add_parser('status',
        description='show the library, its pool and its settings',
        parents=[cfg])
    statusp.add_argument('--no-check-files', action='store_true', help='faster, less info')
    statusp.add_argument('-v','--verbose', action='store_true', help='also show where each setting comes from')
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
        help='directory of the library (default: the current directory); --bibtex and '
             '--filesdir are relative to it')
    initp.add_argument('--bibtex', type=file_uri_to_path,
        help='bibtex file (default: papers.bib, or the first .bib file of the directory)')
    initp.add_argument('--filesdir', type=file_uri_to_path,
        help='files directory (default: files, or an existing pdfs/, papers/... folder)')
    initp.add_argument('--pool', metavar='PATH',
        help='a shallow library that uses the library PATH as pool (a path relative to the library; '
             'PATH must be a library without pool): `papers add` looks in PATH first and adds the new '
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
    initp.add_argument('--git', action='store_true', default=None,
        help='back up the bibtex with git (default: true when git is installed)')
    initp.add_argument('--no-git', action='store_false', dest='git', default=None, help='no git backup')
    initp.add_argument('--git-lfs', action='store_true', default=None, help='also back up the files with git-lfs (implies --git)')
    initp.add_argument('--editor', help='command to open a text editor; it must wait until the editor is closed, e.g. vim or "subl -w"')
    _command(initp, initcmd)

    # config
    # ======
    configp = subparsers.add_parser('config', parents=[loggingp],
        description='get or set the settings of the library (git style): without KEY, list the '
                    'settings and where each comes from (library, global or default); with KEY, '
                    'print its value; with KEY VALUE..., set it in the library configuration',
        epilog='settings: ' + ', '.join(SETTINGS) + '; with --global, also default (the default library: '
               'PATH or none). pool PATH (a library without pool) makes the library shallow: it links to the '
               'pool\'s copies of its PDFs, and its own copies are deleted; each PDF must be in the pool entry '
               'already, otherwise nothing changes and papers names the entries to push first (`papers push '
               '--pool PATH KEY...`). pool none makes a shallow library self-contained: the pool files that it '
               'links to are copied into its files directory. papers lists what it will do and asks to continue.')
    configp.add_argument('key', nargs='?', metavar='KEY')
    configp.add_argument('values', nargs='*', metavar='VALUE')
    configp.add_argument('--unset', metavar='KEY', help='remove the setting: the global or default value applies again (pool: none)')
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
        help="""ignored (a library configuration is always local)""")
    installp.add_argument('--global', action="store_false", dest='local', default=None,
        help="no longer supported: an error that changes nothing (`papers init PATH --global` creates the "
             "default library, `papers config --global default PATH` registers an existing one)")

    installp.add_argument('--git', action='store_true', default=None, help='back up the bibtex with git')
    installp.add_argument('--backup', action=_Deprecated, dest='git', new='--git (or `papers config git true`)')
    installp.add_argument('--git-lfs', action='store_true', default=None, help='also back up the files with git-lfs (implies --git)')
    installp.add_argument('--backup-files', action=_Deprecated, dest='git_lfs',
                          new='--git-lfs (or `papers config git-lfs true`)')
    installp.add_argument('--gitdir', default=None, help=argparse.SUPPRESS)
    installp.add_argument('--editor', help="""Set command to open text editor. Need to wait until closing ! E.g. vim or subl -w""")
    installp.add_argument('--pool', metavar='PATH|none', help=argparse.SUPPRESS)

    grp = installp.add_argument_group('status')
    grp.add_argument('--no-check-files', action='store_true', help='faster, less info')
    _command(installp, installcmd)


    # uninstall
    # =======
    uninstallp = subparsers.add_parser('uninstall', description='remove the library configuration',
        parents=[loggingp])
    uninstallp.add_argument("--recursive", action="store_true", help="deprecated and ignored: only the configuration of the library is removed")
    uninstallp.add_argument("--remove-backup", action="store_true", help="also remove the backup directory of the uninstalled configuration(s)")
    _command(uninstallp, uninstallcmd)


    # add
    # ===
    addp = subparsers.add_parser('add', description='''add PDF(s) or bibtex(s) to library. In a
        shallow library, the files go to the files directory of the pool (files mode
        move or copy; with link, they stay where they are), and the entries to the pool too. Adding a bibtex file (`papers add other.bib`) copies its entries once, with no
        memory of where they came from; `papers pull` instead keeps the entries linked to the pool,
        and later pulls bring its corrections.''',
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
        help='''do not look in the pool first (by default, a PDF, DOI or bibtex entry that is
        the same paper as a pool entry is taken from the pool, with its files, without fetching)''')
    grp.add_argument('--pool', metavar='PATH',
        help='''look in the library PATH first, instead of the pool (PATH must be a library without
        pool): a paper that PATH has is taken from it, with its files (copied as the files mode
        says; in a shallow library, into the files directory of its pool), and later
        `papers pull --pool PATH` brings its corrections. Nothing is added to PATH. Not the same as
        `papers -C PATH add`, which adds to the library PATH.''')
    grp.add_argument('--no-merge-files', action='store_true',
        help='deprecated and ignored: file links are always merged')
    grp.add_argument('-u', '--update-key', action='store_true',
        help='''regenerate the key of the entries new to the library from the key template
        (see "bibtex key format" options). A duplicate always keeps the key of the library.''')
    grp.add_argument('-m', '--mode', choices=['u', 'U', 'o', 's', 'r', 'i', 'a'],
        help='''deprecated: use --on-duplicate (i: ask, u: keep, U and o: update, s: skip,
        r: error, a: --no-check-duplicate)''')

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
    grp.add_argument('--metadata', nargs="+", metavar="KEY=VALUE", type=lambda meta: meta.split('=', 1),
        help='any fields')
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
        its files directory) is never moved: it is copied instead. In a library that is
        shallow, the file links are those of the pool entry: move and copy place the files in
        the files directory of the pool, link leaves them where they are and the pool entry
        links to them there too.''')
    grp.add_argument('--attach', nargs='+', type=file_uri_to_path, dest='attachment', metavar='FILE',
        help='attach these files to the entry (e.g. supplementary material)')
    grp.add_argument('--attachment', nargs='+', type=file_uri_to_path, dest='attachment_deprecated',
        help='deprecated: use --attach')
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
    grp.add_argument('-m', '--mode', choices=list('ims'), help='deprecated: use --on-duplicate (i: ask, m: keep, s: skip)')
    _command(checkp, checkcmd, library=True)


    # file
    # ====
    filep = subparsers.add_parser('file', description='the files of the entries: rename, move, attach, '
        'detach, remove, check them, and clean the files directory')
    filesub = filep.add_subparsers(dest='file_cmd', metavar="{rename,mv,attach,detach,rm,check,clean}")
    _command(filep, None)  # without subcommand: the help of papers file

    p = filesub.add_parser('rename', parents=[cfg, namefmt],
        help='place the files in the files directory under their template name',
        description='place the files of the entries (all entries without KEY) in the files directory, '
                    'under the name made from the name template. A file that belongs to another library '
                    '(inside its files directory) is copied, not moved.')
    p.add_argument('entries', nargs='*', metavar='KEY', help=_selection_help)
    p.add_argument('--keep-source', action='store_true',
        help='keep the files where they are too (a hard link when possible, otherwise a copy)')
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

    _key_help = (f'only the links of these entries ({ENTRY_IDS}; - reads them from the standard input); '
                 'write the files before --key, which takes several values')
    p = filesub.add_parser('detach', parents=[cfg],
        help='remove file links from the entries (the files are kept)',
        description='remove the links to FILE from every entry that links to it (only from the entries of '
                    '--key with --key); with --key and no FILE, remove all the links of these entries; with '
                    '--broken, remove the broken links. The files are never deleted (`papers file rm` does that).')
    p.add_argument('files', nargs='*', metavar='FILE', type=file_uri_to_path)
    p.add_argument('-k', '--key', nargs='+', action='extend', metavar='KEY', help=_key_help)
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

    p = filesub.add_parser('check', parents=[cfg],
        help='report broken links, identical files, DOI mismatches',
        description='report broken links and the files found for them, links that can be repaired (paths '
                    'saved by Mendeley), files linked twice and identical files (same checksum) of an entry, and '
                    'with --metadata a DOI of the PDF that differs from the entry\'s. Nothing changes without --fix.')
    p.add_argument('entries', nargs='*', metavar='KEY', help=_selection_help + ' (default: all entries)')
    p.add_argument('--metadata', action='store_true', help='also compare the DOI of the PDFs with the entry (parses the PDFs)')
    p.add_argument('--fix', action='store_true',
        help='apply the safe repairs: repair the paths, remove the second link of a file linked twice or of '
             'identical files (the files are kept), and relink the broken links to the files found in the pool '
             '(same paper) or in the --search folders, placed as `papers file attach` does')
    p.add_argument('--search', action='append', metavar='DIR',
        help='also look for the files of the broken links in DIR (recursively), by file name, else by the '
             'template name of the entry (can be repeated)')
    _command(p, file_checkcmd, library=True)

    p = filesub.add_parser('clean', parents=[cfg],
        help='remove the files of the files directory that no entry links to',
        description='remove the files of the files directory (and its subfolders) that no entry links to, '
                    'asking for each one. Hidden files and folders, and .bib files, are skipped.')
    p.add_argument('-y', '--yes', action='store_true', help='do not ask')
    _command(p, file_cleancmd, library=True)

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
    listp.add_argument('--similarity', help='deprecated and ignored')
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
    grp.add_argument('--keywords', '--tag', nargs='+', help='keywords (tags)')


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
    mgrp.add_argument('--format', choices=['line', 'bibtex', 'key'],
        help='line: one line per entry (the default); bibtex: the entries as bibtex; key: the keys only, '
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
        description='shortcuts of `papers edit`, `papers rm` and `papers tag`; the other commands that act '
                    'on entries read the keys of `papers list -K` with -, e.g. `papers list smith -K | papers file rename -`')
    grp.add_argument('--delete', action='store_true',
        help='remove the listed entries, as `papers rm` (asks whether to delete their files, in a terminal)')
    grp.add_argument('--delete-files', action='store_true', help='with --delete: also delete their files, as `papers rm --delete-files`')
    grp.add_argument('--keep-files', action='store_true', help='with --delete: keep their files, without asking')
    grp.add_argument('-e', '--edit', action='store_true', help='edit the listed entries in a text editor, as `papers edit`')
    grp.add_argument('--fetch', action='store_true', help='deprecated: `papers check --fetch --fetch-all --fix-doi --fix-key --format-name -`')
    grp.add_argument('--add-keywords', '--add-tag', nargs='+', help='add keywords (tags) to the listed entries, as `papers tag --add`')
    grp.add_argument('--add-files', nargs='+', type=file_uri_to_path, help='deprecated: `papers file attach KEY FILE...`')
    grp.add_argument('--rename', action='store_true', help='deprecated: `papers file rename -`')
    grp.add_argument('--copy', action='store_true', help='deprecated: `papers file rename --keep-source -`')
    grp.add_argument('-o', '--open', action='store_true', help='deprecated: `papers open -`')
    _command(listp, listcmd, library=True)

    # edit, rm, tag
    # =============
    editp = subparsers.add_parser('edit', parents=[cfg],
        description='edit entries in a text editor (the editor setting, else $VISUAL, else $EDITOR)')
    editp.add_argument('entries', nargs='+', metavar='KEY',
        help=_selection_help)
    _command(editp, editcmd, library=True)

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
    _command(rmp, rmcmd, library=True)

    tagp = subparsers.add_parser('tag', parents=[cfg],
        description='tags are the keywords field of the entries (comma-separated). Without option, list '
                    'the tags of the library (or of the entries KEY...) with the number of entries.')
    tagp.add_argument('entries', nargs='*', metavar='KEY',
        help=_selection_help)
    tagp.add_argument('--add', nargs='+', metavar='TAG', help='add tags to the entries')
    tagp.add_argument('--rm', nargs='+', metavar='TAG', help='remove tags from the entries')
    tagp.add_argument('--rename', nargs=2, metavar=('OLD', 'NEW'), help='rename a tag in the whole library')
    _command(tagp, tagcmd, library=True)

    # pull, push, sync, export
    # ========================
    _exchange_help = '''what to do with an entry changed on both
        sides since the last pull or push: ask (dialogue; the default in a terminal), keep (the
        {receiving} values are kept), update (the {incoming} values are taken), skip (the entry is
        left as it is, and comes again next time), error (stop before saving; the default
        without a terminal). Fields changed on one side only need no decision.'''
    _pool_help = ('another library to {what} (a library without pool), e.g. a folder shared with someone '
                  '(default: the pool of the library). The origin copies are recorded, as with the pool: '
                  'without KEY or --all, the entries exchanged with PATH before. The files are copied (in a '
                  'shallow library, the entries and files taken from PATH also go to its pool).')
    pullp = subparsers.add_parser('pull', parents=[cfg],
        description='''update the entries of the library from their entries in the pool, or the
        library --pool PATH (three-way
        merge with the origin copy of the entry, in .papers/origin/): a field changed in the pool
        only is taken, a field changed in the library only is kept, a field changed on both sides
        is a conflict. Without KEY, only the entries shared with the pool (with an origin copy) are
        updated; an entry named, or all entries with --all, is matched by the same-paper rule when
        it has no origin copy. The keys of the library never change. KEY may also be an entry of
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
        help='all entries: the entries of the library not shared yet are matched by the same-paper rule in '
             'the pool, and every entry of the pool that the library does not have is added')
    pullp.add_argument('--on-duplicate', choices=ON_DUPLICATE,
        help=_exchange_help.format(receiving='library', incoming='pool'))
    pullp.add_argument('--check', action='store_true',
        help='only report: whether the pool changed since the last pull, and the entries changed in it')
    pullp.set_defaults(mode=None, yes=False)
    _command(pullp, pullcmd, library=True)

    pushp = subparsers.add_parser('push', parents=[cfg],
        description='''merge the changes of the entries of the library into their pool entries
        (three-way merge with the origin copy, as pull does in the other direction), in the pool
        of the library or the library --pool PATH. Without KEY, only the entries shared with the pool (those
        with an origin copy from it) are pushed; KEY... pushes those entries, and adds them to the pool if
        it does not have them; --all pushes every entry. Entries new to the pool get a key from
        the pool's key template; their files are copied (a hard link when possible) into the
        pool's files directory, named with the pool's name template. The pool must be a library
        (`papers init PATH` creates one).''')
    pushp.add_argument('entries', nargs='*', metavar='KEY',
        help=_selection_help + ' (default: the entries shared with the pool)')
    pushp.add_argument('--all', action='store_true',
        help='push every entry of the library, adding to the pool those it does not have')
    pushp.add_argument('--pool', metavar='PATH', help=_pool_help.format(what='push to'))
    pushp.add_argument('--on-duplicate', choices=ON_DUPLICATE,
        help=_exchange_help.format(receiving='pool', incoming='library'))
    pushp.set_defaults(mode=None, yes=False)
    _command(pushp, pushcmd, library=True)

    syncp = subparsers.add_parser('sync', parents=[cfg],
        description='''`papers pull`, then `papers push` of the same entries, with the pool of the
        library or the library --pool PATH. Without KEY, only the entries shared with it (those with an origin
        copy) are exchanged; KEY... exchanges those entries; --all is `pull --all`
        and `push --all`: each side gets the entries it does not have. If the pull leaves
        conflicts undecided (skipped, or the dialogue quit), nothing is pushed.''')
    syncp.add_argument('entries', nargs='*', metavar='KEY',
        help=_selection_help + ' (default: the entries shared with the pool)')
    syncp.add_argument('--all', action='store_true',
        help='also add to each side the entries it does not have (pull --all, push --all)')
    syncp.add_argument('--pool', metavar='PATH', help=_pool_help.format(what='sync with'))
    syncp.add_argument('--on-duplicate', choices=ON_DUPLICATE,
        help=_exchange_help.format(receiving='receiving side', incoming='other side'))
    syncp.set_defaults(mode=None, yes=False)
    _command(syncp, synccmd, library=True)

    exportp = subparsers.add_parser('export', parents=[cfg],
        description='''write entries as a new library in DIR, to hand over: bibtex, files,
        configuration (a self-contained library: its own files, no pool), with file links relative to
        the bibtex. `papers add DIR --recursive` adds it back; `papers config pool DIR` makes it the
        pool of the library.''')
    exportp.add_argument('dir', metavar='DIR', help='directory of the new library (must not exist, or be empty)')
    exportp.add_argument('entries', nargs='*', metavar='KEY', help=_selection_help + ' (default: all entries)')
    exportp.add_argument('--files', choices=['copy', 'link', 'none'], default='copy',
        help='copy the files into DIR/files (a hard link when possible; default), link to them where '
             'they are, or leave the file links out')
    _command(exportp, exportcmd, library=True)

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
    fetchp = subparsers.add_parser('fetch', description='fetch bibtex from DOI or full-text', parents=[loggingp])
    fetchp.add_argument('doi_or_text', nargs='+', help='DOI or full text.')
    fetchp.add_argument('--scholar', action='store_true', help='use google scholar instead of default crossref for fulltext search')
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
    extractp.add_argument('--scholar', action='store_true', help='use google scholar instead of default crossref for fulltext search')
    extractp.add_argument('--image', action='store_true', help='convert to image and use tesseract instead of pdftotext')
    _command(extractp, extractcmd)

    # undo
    # ====
    _restorep = argparse.ArgumentParser(add_help=False)
    _restorep.add_argument('--restore-files', action='store_true',
        help='with the git-lfs setting: copy back from the backup the files that no longer exist where the '
             'restored bibtex links to them (by default, these links point to the copy in the backup '
             'directory). No effect without git-lfs.')

    _stepsp = argparse.ArgumentParser(add_help=False)
    _stepsp.add_argument('-n', '--steps', type=int, default=1, help='number of steps to undo or redo')

    _undo_help = ('undo the last change of the bibtex. With the git setting (`papers config git true`), '
                  'each change is a step of the backup history; without it, undo swaps the bibtex with its '
                  'previous version (one step back and forth). With git-lfs, a link to a file that no '
                  'longer exists points to its copy in the backup, unless --restore-files.')
    undop = subparsers.add_parser('undo', parents=[cfg, _restorep, _stepsp], help=_undo_help, description=_undo_help)
    _command(undop, undocmd, library=True)
    _redo_help = ('redo a change undone by `papers undo` (without the git setting, the same as papers undo: '
                  'it swaps the bibtex with its previous version)')
    redop = subparsers.add_parser('redo', parents=[cfg, _restorep, _stepsp], help=_redo_help, description=_redo_help)
    _command(redop, redocmd, library=True)
    _restore_help = ('restore the bibtex from the git backup (the git setting: `papers config git true`): its '
                     'last version, or the version of --ref (see --restore-files for the files)')
    for name in ('restore', 'restore-backup'):
        restorep = subparsers.add_parser(name, parents=[cfg, _restorep],
            help=_restore_help if name == 'restore' else 'deprecated: use `papers restore`',
            description=_restore_help if name == 'restore' else 'deprecated: use `papers restore`')
        restorep.add_argument('--ref', help='restore this commit of the backup (see `papers git log`)')
        _command(restorep, restorecmd, library=True, bibtex_must_exist=False)

    # git
    # ===
    gitp = subparsers.add_parser('git', description='git subcommand')
    gitp.add_argument('gitargs', nargs=argparse.REMAINDER)
    _command(gitp, gitcmd)

    # backup
    # ======
    backupp = subparsers.add_parser('backup', description='manage backup directories', parents=[loggingp])
    backupp.add_argument('action', nargs='?', choices=['list', 'remove'], default='list',
        help='list (default) known backup directories and the library each belongs to, or remove them')
    backupp.add_argument('patterns', nargs='*', metavar='name',
        help='directory name(s), glob patterns allowed (filter for list, required for remove)')
    backupp.add_argument('-y', '--yes', action='store_true', help='remove without confirmation')
    backupp.add_argument('-f', '--force', action=_Deprecated, dest='yes', new='-y/--yes')
    _command(backupp, backupcmd)

    return parser, subparsers
