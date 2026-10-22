"""Helpers shared by the commands: the library of the command line
(check_install), the format and files options, the duplicate resolver,
entry selection and the report of the changes."""
import os
import re
import sys

import papers.config
import papers.utils
from papers import logger
from papers.config import SETTINGS, short_home
from papers.encoding import format_entry
from papers.entries import entry_content_equal, get_entry_val, parse_string, format_library, library_from_entries
from papers.files import hidden_bibtex
from papers.identifiers import read_selection, select_entries
from papers.library import config_for_bibtex, savebib
from papers.merge import Resolver
from papers.pools import Pools, report_counts, use_pool_files
from papers.utils import PapersExit, edit_text, open_with_system


def view_entry_files(biblio, entry):
    files = biblio.get_files(entry)

    # several files in a directory of previous versions' layout (<name>/ with
    # a hidden .<name>.bib): open the directory instead of the single files
    if len(files) > 1:
        parent = os.path.commonpath(files)
        if os.path.isfile(hidden_bibtex(parent)):
            open_with_system(parent)
            return

    for f in biblio.get_files(entry):
        logger.info(f"opening {f} ...")
        open_with_system(f)


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


def set_format_config_from_cmd(o, config, kind):
    """apply the name or key format options of the command line (kind: name
    or key) to the configuration of the run"""
    fmt = config.nameformat if kind == 'name' else config.keyformat
    for name, value in format_options(o, [kind]).items():
        setattr(fmt, name.split('.')[1].replace('-', '_'), value)


def init_hint(config):
    "how to create a library, here or for the global pool"
    pool = config.machine.pool_path()
    if pool is None:
        return "Create a library with `papers init`"
    return f"Create a library with `papers init` (here) or `papers init {short_home(pool)}` (the global pool)"


def no_library_message(config):
    pool = config.machine.pool_path()
    where = f", and the global pool ({pool}) is not a library" if pool else ""
    return f"no library found in this directory or above{where}. {init_hint(config)}"


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
        raise PapersExit(f"{no_library_message(config)}, or pass --bibtex")

    if bibtex_must_exist and not os.path.exists(config.bibtex):
        raise PapersExit(f'no bibtex file found, do `touch {config.bibtex}` or `papers init --bibtex {config.bibtex}`')
    logger.info(f'bibtex: {config.bibtex!r}')
    logger.info(f'filesdir: {config.filesdir!r}')
    return config


def _print_biblio_diff(biblio_init, biblio, touched_entries, show_existing=False, notes=None):
    """Emit Added/Modified/Removed (and optionally Existing) lines for
    entries that differ between the pre-command snapshot and the
    post-command state.

    `touched_entries` scopes the Modified/Existing check to entries the
    command actually considered (matches addcmd's original semantics).
    `notes`: {lower-case key: text} added to the line of an entry, in
    brackets (where else it went, or where it came from).
    """
    notes = notes or {}
    note = lambda ID: f' [{notes[ID.lower()]}]' if ID.lower() in notes else ''
    old_set = set(get_entry_val(e, 'ID', '') for e in biblio_init.entries)
    old_entries_by_key = {get_entry_val(e, 'ID', ''): e for e in biblio_init.db.entries}
    new_set = set(get_entry_val(e, 'ID', '') for e in biblio.entries)
    new_entries_by_key = {get_entry_val(e, 'ID', ''): e for e in biblio.db.entries}
    modified_set = set(get_entry_val(e, 'ID', '') for e in touched_entries).intersection(set.intersection(old_set, new_set))

    for ID in sorted(old_set - new_set):
        print(format_entry(biblio_init, old_entries_by_key[ID], prefix="Removed"))

    for ID in sorted(new_set - old_set):
        print(format_entry(biblio, new_entries_by_key[ID], prefix="Added") + note(ID))

    for ID in sorted(modified_set):
        before = old_entries_by_key[ID]
        after = new_entries_by_key[ID]
        if not entry_content_equal(before, after):
            print(format_entry(biblio, after, prefix="Modified") + note(ID))
        elif show_existing:
            print(format_entry(biblio, after, prefix="Existing") + note(ID))


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


# v2 letters of -m/--mode, and the --on-duplicate word they map to
ADD_MODES = {'i': 'ask', 'u': 'keep', 'U': 'update', 'o': 'update', 's': 'skip', 'r': 'error'}


CHECK_MODES = {'i': 'ask', 'm': 'keep', 's': 'skip'}


def on_duplicate_mode(o, cmd):
    """the --on-duplicate word of the command line: the option, else the
    deprecated -m/--mode letter, else ask in a terminal and error otherwise
    (check --yes: skip)"""
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
        if cmd == 'check' and o.yes:
            mode = 'skip'
        else:
            mode = 'ask' if stdin_is_terminal() else 'error'
    return mode


def duplicate_resolver(o, cmd):
    return Resolver(on_duplicate_mode(o, cmd), color=papers.utils.COLOR)


def _entries_or_all(biblio, args):
    "the entries named on the command line (keys, DOIs, -), or all entries without argument"
    return select_entries(biblio, args) if args else list(biblio.entries)


# extensions of the files a --key value is likely to be (see _key_option_entries)
_FILE_EXTENSIONS = ('.pdf', '.djvu', '.epub', '.ps', '.txt', '.zip', '.doc', '.docx', '.html')


def _key_option_entries(biblio, keys):
    """the entries of the -k/--key option of `papers file detach` and
    `papers file rm` (None without the option). As the option takes several
    values, it swallows the files written after it: a value that is not an
    entry but a path is an error that says so."""
    if not keys:
        return None
    keys = read_selection(keys)
    for key in keys:
        if os.path.lexists(key) or key.lower().endswith(_FILE_EXTENSIONS):
            try:
                select_entries(biblio, [key])
            except PapersExit:
                raise PapersExit(f'{key} is not an entry: put the files before --key (nothing was changed)')
    return select_entries(biblio, keys)


def _one_entry(biblio, key):
    entries = select_entries(biblio, [key])
    if len(entries) != 1:
        raise PapersExit(f"{key}: give one entry ({len(entries)} given)")
    return entries[0]


def library_pools(config):
    """the pools of the library. In a non-local library, the files that the
    command places go to the pool, as with `add` (see
    papers.pools.use_pool_files): call push_to_pool after."""
    pools = Pools(config)
    if config.file and not config.local:
        use_pool_files(config, pools)
    return pools


def push_to_pool(exchange, entries):
    """save the library; in a non-local library, first push the entries to
    the pool, which holds their files (as `add` does). Return the notes of
    the push for _print_biblio_diff."""
    resolver = Resolver('ask' if stdin_is_terminal() else 'error', color=papers.utils.COLOR)
    pushed = exchange.push_added(entries, [], resolver) if not exchange.config.local else []
    save_exchange(exchange)
    return push_notes(pushed)


# the notes of the entries pushed as a side effect (add, file attach...)
_PUSH_NOTES = {'added': 'also added to {}', 'updated': 'also modified in {}',
               'skipped': 'not pushed to {}: conflict skipped', 'empty': 'not pushed to {}: no fields or no key'}


def push_notes(pushed, notes=None):
    """{lower-case key: note} of the entries that a push following another
    command changed in the pool (see _print_biblio_diff); the push itself
    is reported at --info level"""
    notes = {} if notes is None else notes
    if not pushed:
        return notes
    logger.info(f'push to {pushed[0][1].label}: {report_counts(pushed)}')
    for e, pool, what in pushed:
        if what in _PUSH_NOTES:
            text = _PUSH_NOTES[what].format(pool.label)
            key = e.key.lower()
            notes[key] = f'{notes[key]}; {text}' if key in notes else text
    return notes


# pull and push: one line per entry that changed, or that was not exchanged
_EXCHANGE_LINES = {
    'pull': {'added': ('Added', 'from {}'), 'updated': ('Modified', 'from {}'),
             'skipped': ('Conflict', 'skipped, not taken from {}'), 'not found': ('Not found', 'not in {}')},
    'push': {'added': ('Added', 'to {}'), 'updated': ('Modified', 'in {}'),
             'skipped': ('Conflict', 'skipped, not pushed to {}'),
             'empty': ('Not pushed', 'no fields or no key, not pushed to {}')},
}


def exchange_lines(report, kind, biblio, pool):
    """the report of pull or push (see papers.pools.Exchange.pull, push):
    (one line per entry added, modified, skipped or not found, the line of
    the counts or None). The counts are given when more than one entry was
    involved, or when there is no entry line. pool: the pool of the
    exchange, or None."""
    label = pool.label if pool is not None else None
    lines = []
    for e, p, what in report:
        if what in _EXCHANGE_LINES[kind]:
            prefix, note = _EXCHANGE_LINES[kind][what]
            where = p.label if p is not None else (label or 'the pool')
            lines.append(format_entry(biblio, e, prefix=prefix) + f' [{note.format(where)}]')
    summary = None
    if len(report) > 1 or not lines:
        verb = kind if label is None else f'{kind} {"from" if kind == "pull" else "to"} {label}'
        summary = f'{verb}: {report_counts(report)}'
    return lines, summary


def print_exchange(report, kind, biblio, pool):
    "print the report of pull or push (see exchange_lines)"
    lines, summary = exchange_lines(report, kind, biblio, pool)
    print('\n'.join(lines + ([summary] if summary else [])))


def save_exchange(exchange):
    """save what an exchange with a pool changed: the pools pushed to,
    the pairs that are not the same paper of the pool, the origin
    records, and the library"""
    for pool in exchange.changed_pools:
        savebib(pool.biblio, pool.config)
        exchange.after_push(pool)
    if not papers.config.DRYRUN:
        for pool in exchange.pools.loaded():
            if pool._biblio is not None and not any(pool is p for p in exchange.changed_pools):
                pool.biblio.distinct.save()
    exchange.origin.save()
    savebib(exchange.biblio, exchange.config)


def stdin_is_terminal():
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError, OSError):
        return False


def edit_entries(entries, editor=None):
    """edit entries in a text editor; returns the edited entries, or the
    original entries if the edit failed or does not parse as bibtex"""
    text = edit_text(format_library(library_from_entries(entries)), editor=editor)
    if text is None:
        logger.error('failed to edit file -- keeping original entries')
        return entries

    db_updated = parse_string(text)
    new_entries = db_updated.entries

    failed = getattr(db_updated, 'failed_blocks', None)
    if failed:
        logger.error('some edited blocks could not be parsed as bibtex -- keeping original entries')
        return entries
    if entries and not new_entries:
        logger.error('edited file contains no bibtex entry -- keeping original entries')
        return entries
    fieldname = re.compile(r'^[A-Za-z][\w-]*$')
    for e in new_entries:
        bad = [k for k, _ in e.items() if not fieldname.match(k)]
        if bad:
            logger.error(f'edited entry {get_entry_val(e, "ID", "")!r} has malformed field name(s) {bad} '
                         '-- keeping original entries')
            return entries

    logger.info('successfully edited file, insert edited entries')
    return new_entries


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


def print_kept_files(kept, in_pool):
    for f in kept:
        print(f"kept {f}: another entry links to it")
    for f in in_pool:
        print(f"kept {f}: it is a file of a pool")


def _delete_files_option(parser, o):
    if o.delete_files and o.keep_files:
        parser.error('--delete-files and --keep-files are mutually exclusive')
    return True if o.delete_files else (False if o.keep_files else None)
