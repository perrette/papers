"""papers add, check, list, edit, rm, tag, open"""
import argparse
import fnmatch
import os
import re
import sys

import papers.config
import papers.files
import papers.utils
from papers import logger
from papers.bib import isvalidkey
from papers.duplicate import FUZZY_RATIO, duplicate_groups, fuzzy_pairs, normalize_text
from papers.encoding import family_names, format_entries, format_entry, format_key, parse_keywords, standard_name
from papers.formats import FORMATS, dumps, file_format, load_rispy
from papers.entries import entry_from_dict, get_entry_val, format_file, parse_file, set_entry_key
from papers.extract import isvaliddoi, prefetch_pdf_metadata
from papers.fetch import DOIRequestError
from papers.files import delete_files, describe_file, download_url, files_policy, scan_dir_items
from papers.identifiers import normalize_doi, read_selection, select_entries
from papers.library import get_biblio, savebib
from papers.merge import DuplicateError
from papers.pools import Exchange, PoolLookup, Pools
from papers.utils import PapersExit, file_uri_to_path, open_with_system, read_entry_text
from papers.cli.file_cmds import (attach_entry_files, fetch_entry_pdfs, check_entries_files, detach_entries, file_check_pools,
                                  rename_entries)
from papers.cli.pool_cmds import exchange_pools, export_entries, pull_entries, push_entries, sync_entries
from papers.cli.common import (view_entry_files, set_format_config_from_cmd, _print_biblio_diff, files_mode,
                               duplicate_resolver, save_exchange, stdin_is_terminal, edit_entries, edit_selected,
                               EditRejected, parse_edited, replace_entries, set_fields,
                               print_kept_files, _delete_files_option, library_pools, push_notes, push_changed,
                               save_entries, print_push_notes)


def _author_short_option(o):
    """-a NAME is --author NAME; the other values of -a are files to add
    (`-a NAME FILE`). The v2 form -a FILE... (attach): when every value is an
    existing file or a URL, they are attached as with --attach, with a warning."""
    values = [file_uri_to_path(v) for v in o.author_short]
    if all(os.path.isfile(v) or v.startswith(('http://', 'https://')) for v in values):
        one = len(values) == 1
        logger.warning(f"-a now means --author; {' '.join(values)} {'exists' if one else 'exist'}, so "
                       f"{'it is' if one else 'they are'} attached as with --attach (this fallback is removed in v4)")
        o.attachment = (o.attachment or []) + values
        return
    name, files = o.author_short[0], values[1:]
    if values[0] != name or os.path.exists(name):
        raise PapersExit(f'-a {name}: a file, but -a now means --author: use --attach FILE to attach it, '
                         'or --author NAME')
    if o.author:
        raise PapersExit('-a is the same as --author: give one of them')
    o.author = name
    o.file = o.file + files


def _nothing_to_add(o, biblio, what):
    "the error of `add --key KEY` when the pool does not have KEY"
    lookup = biblio.pool_lookup
    if o.no_pool:
        where = 'the library (--no-pool)'
    elif lookup:
        where = lookup.pool.label
    else:
        where = 'the library (it has no pool)'
    return f'nothing to add: no file, identifier or bibtex given, and {what}{where}'


def addcmd(parser, o, config):
    """
    Given an options set and a config, sets up the function call to add the file or all files in the directory to the bibtex, and executes it.
    """

    set_format_config_from_cmd(o, config, 'name')
    set_format_config_from_cmd(o, config, 'key')

    if o.pool and o.no_pool:
        raise PapersExit('--pool PATH and --no-pool exclude each other')
    pools = library_pools(config)  # in a shallow library, files go to the pool
    biblio = get_biblio(config)
    exchange = Exchange(config, biblio, pools)
    source_dirs = []  # the files directory of the library of --pool PATH
    if not o.no_pool:
        lookup = PoolLookup(exchange, pools.get(o.pool) if o.pool else None)
        biblio.pool_lookup = lookup if lookup else None
        if o.pool and lookup.pool.filesdir:
            source_dirs = [lookup.pool.filesdir]

    entries = []

    if o.attachment_deprecated:
        logger.warning("--attachment is deprecated: use --attach")
        o.attachment = (o.attachment or []) + o.attachment_deprecated
    if o.author_short:
        _author_short_option(o)

    if o.fetch_pdf and (o.file or not o.doi):
        raise PapersExit('--fetch-pdf goes with --doi DOI, without FILE (`papers file fetch KEY` fetches the PDF '
                         'of an entry of the library)')
    if o.fetch_pdf and config.filesdir is None:
        raise PapersExit('--fetch-pdf: the library has no files directory, where the downloaded PDF goes '
                         '(pass --filesdir, or set it with `papers config filesdir DIR`)')

    # what to do with the files: see papers.files.FilesPolicy
    mode = files_mode(o, config)
    policy = files_policy(config, mode, pools.files_dirs() + source_dirs)
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

    if metadata and (len(o.file) > 1 or any(os.path.isdir(f) for f in o.file)):
        raise PapersExit('--doi, --metadata, --key, --attach and the other metadata options are only valid '
                         'for one PDF / BIBTEX entry')

    if o.no_merge_files:
        logger.warning('--no-merge-files is deprecated and ignored: the file links of duplicates are always merged')
    resolver = duplicate_resolver(o, 'add')
    kw = {'on_duplicate':resolver, 'check_duplicate':not o.no_check_duplicate,
            'update_key':o.update_key, 'metadata':metadata}

    if len(o.file) == 0 and o.doi and not o.no_query_doi:
        try:
            entries.extend( biblio.fetch_doi(o.doi, attachments=o.attachment, rename=rename, copy=policy, **kw) )
        except DOIRequestError as error:  # its message names the DOI
            raise PapersExit(str(error)) from error
        except OSError as error:  # network error
            raise PapersExit(f'{o.doi}: {error}') from error

    elif len(o.file) == 0 and o.key and not (o.edit or o.metadata or o.doi or o.title or o.author
                                             or o.journal or o.year):
        # --key alone: the entry of that key in the library or a pool
        added = biblio.add_key(o.key, attachments=o.attachment, rename=rename, copy=policy, **kw)
        if added is None:
            raise PapersExit(_nothing_to_add(o, biblio, f'no entry {o.key} in '))
        entries.extend(added)

    elif len(o.file) == 0:
        if not o.edit and not o.metadata and not o.key and not o.doi and not o.attachment and not o.title and not o.author and not o.journal and not o.year:
            raise PapersExit("No entry added: use --doi, --metadata, --key, --attachment, --title, --author, "
                             "--journal, --year to add a new entry")

        metadata.setdefault('ID', biblio.keyformat(metadata) or biblio.generate_key(metadata, new=True))
        metadata.setdefault('ENTRYTYPE', 'article')
        entry = entry_from_dict(metadata)
        if o.edit:
            edited = edit_entries([entry])
            if len(edited) != 1:
                raise PapersExit(f'the edited text has {len(edited)} entries: add one entry at a time')
            entry = edited[0]
            o.edit = False
        if not any(k != 'file' for k in entry.fields_dict) or not entry.key:
            raise PapersExit('nothing to add: the entry has no fields or no key' + (
                '' if o.key else ' (use --title, --author... or --edit)'))

        # the entry is made of the metadata (and edited): not applied again
        entries.extend( biblio.insert_entry(entry, rename=rename, copy=policy, **{**kw, 'metadata': {}}) )


    # several PDFs: fetch their metadata concurrently first
    if not o.doi and not o.scholar and not o.openalex and not (o.no_query_doi and o.no_query_fulltext):
        pdfs = []
        for file in o.file:
            if os.path.isdir(file) and o.recursive:
                pdfs.extend(path for kind, path, _ in scan_dir_items(file, quiet=True) if kind == 'file' and path.lower().endswith('.pdf'))
            elif os.path.isfile(file) and file.lower().endswith('.pdf'):
                pdfs.append(file)
        # those of the library and the pools are not looked up online
        if not o.no_check_duplicate and not o.no_query_doi:
            pdfs = [pdf for pdf in pdfs if biblio.find_pdf(pdf) is None]
        if biblio.pool_lookup:
            pdfs = [pdf for pdf in pdfs if not biblio.pool_lookup.has_file(pdf)]
        if len(pdfs) > 1:
            prefetch_pdf_metadata(pdfs, search_doi=not o.no_query_doi, search_fulltext=not o.no_query_fulltext)

    # RIS needs rispy: asked about (or the command stops) before anything is added
    if any(not os.path.isdir(f) and not f.lower().endswith('.pdf') and file_format(f, o.format) == 'ris'
           for f in o.file):
        load_rispy()

    for file in o.file:
        try:
            if os.path.isdir(file):
                if o.recursive:
                    entries.extend( biblio.scan_dir(file, rename=rename, copy=policy,
                                search_doi=not o.no_query_doi,
                                search_fulltext=not o.no_query_fulltext,
                                scholar=o.scholar, openalex=o.openalex,
                                **kw) )
                else:
                    raise ValueError(file+' is a directory, requires -R/--recursive to explore')

            elif file.lower().endswith('.pdf'):
                entries.extend( biblio.add_pdf(file, attachments=o.attachment, rename=rename, copy=policy,
                           search_doi=not o.no_query_doi,
                           search_fulltext=not o.no_query_fulltext,
                           scholar=o.scholar, openalex=o.openalex, doi=o.doi,
                           **kw) )

            elif file_format(file, o.format) == 'bibtex':
                entries.extend( biblio.add_bibtex_file(file, attachments=o.attachment, rename=rename, copy=policy, **kw) )

            else:  # RIS, CSL-JSON
                entries.extend( biblio.add_file_of_format(file, file_format(file, o.format),
                                attachments=o.attachment, rename=rename, copy=policy, **kw) )

        except (EOFError, DuplicateError):
            raise  # a question without answer, or --on-duplicate error, stops the command (see main_clean_exit)
        except Exception as error:
            if o.ignore_errors:
                logger.error(str(error))
            elif len(o.file) > 1 or (os.path.isdir(file) and o.recursive):
                raise PapersExit(f'{error}\nuse --ignore-errors to add other files anyway') from error
            else:
                raise PapersExit(str(error)) from error

    # --fetch-pdf: the PDF of the entry, attached before the save
    pdf_failed = 0
    if o.fetch_pdf:
        pdf_failed = fetch_entry_pdfs(biblio, config, pools, [e for e in biblio.entries
                                                              if any(e is x for x in entries)], mode)

    # The list of new entries potentially contains duplicates if more than one file is added sequentially
    # If action is required on the added entry, we need to make sure we're consistent with the biblio.
    if len(entries) > 1 and (o.edit or o.open):
        unique_keys = set(biblio.key(e) for e in entries)
        entries = [e for e in biblio.entries if biblio.key(e) in unique_keys]

    if o.edit:
        others = [e for e in biblio.entries if not any(e is x for x in entries)]

        try:
            entries = edit_entries(entries)
        except Exception as error:
            # the entries (and their files) are added already: save them unedited
            logger.error(f'failed to edit the added entries, saved without the edits: {error}')

        for e in entries:  # fields emptied in the editor are removed
            for k in [k for k, v in e.items() if v == "" and k not in ('ID', 'ENTRYTYPE')]:
                del e[k]
        biblio.entries = others + entries

    # auto-push, or the new entries of a shallow library: also in its pool
    # (never in the library of --pool PATH)
    lookup = biblio.pool_lookup
    notes = {key: f'from {pool.label}' for key, pool in (lookup.taken_from.items() if lookup else [])}
    push_notes(push_changed(exchange), notes)
    pool = lookup.pool if lookup else None
    if pool is not None and not any(pool is p for p in exchange.changed_pools + exchange.pushed_pools):
        exchange.after_take(pool)
    save_exchange(exchange)

    # compare entries to inform user
    # this is not very efficient but I have yet to hear a complaint about speed
    # (with the entries a skipped duplicate was of: `existing`)
    _print_biblio_diff(biblio, entries + biblio.skipped, show_existing=True, notes=notes)

    if o.open:
        for e in entries:
            view_entry_files(biblio, e)
    if pdf_failed:
        raise PapersExit()  # the entry is added, the error about its PDF reported: exit 1


def checkcmd(parser, o, config):
    """
    Loops over the entire bib file that the Papers install sees, and checks each entry for formatting and for the existance of duplicates.  Then writes the Biblio object back to your Bibtex file.
    """
    set_format_config_from_cmd(o, config, 'key')

    biblio = get_biblio(config)

    selection = list(o.entries) + list(o.keys or [])
    entries = select_entries(biblio, selection) if selection else list(biblio.entries)
    for e in entries:
        biblio.fix_entry(e, fix_doi=o.fix_doi, fetch=o.fetch, fetch_all=o.fetch_all, fix_key=o.fix_key,
                     auto_key=o.auto_key, format_name=o.format_name, encoding=o.encoding,
                     key_ascii=o.key_ascii, interactive=not o.yes)


    if o.duplicates:
        biblio.check_duplicates(on_duplicate=duplicate_resolver(o, 'check'))
    elif o.on_duplicate or o.mode:
        logger.warning('--on-duplicate and -m/--mode only apply with --duplicates')

    notes = save_entries(config, biblio)
    _print_biblio_diff(biblio, biblio.entries, notes=notes)


def remove_entries(biblio, entries, config, delete_files=None, ask=True):
    """remove entries from the bibliography, and return the files to delete
    once the bibliography is saved.

    Candidates are the files of the removed entries that no remaining entry
    links to. delete_files=True deletes them all; False keeps them; None
    asks, in a terminal (ask=True), whether to delete those inside the files
    directory, and keeps them without a terminal. A file outside the files
    directory is only deleted with delete_files=True. In a shallow library,
    the files that the pool entries link to are kept (rmcmd refuses
    --delete-files there).
    """
    pools = Pools(config)
    inside, outside, kept, in_pool = papers.files.remove_entries(biblio, entries, config.filesdir,
                                                                 pool_dirs=pools.files_dirs())
    pool = pools.pool(quiet=True) if config.shallow else None
    if pool is not None:
        # a shallow library: the files that the pool entries link to, wherever they are, are the pool's
        linked = {os.path.realpath(f) for e in pool.biblio.entries for f in pool.biblio.get_files(e)}
        in_pool += [f for f in inside + outside if os.path.realpath(f) in linked]
        inside = [f for f in inside if os.path.realpath(f) not in linked]
        outside = [f for f in outside if os.path.realpath(f) not in linked]
    if delete_files is False:
        return []
    print_kept_files(kept, in_pool)
    if delete_files:
        return inside + outside
    if outside:
        note = '' if config.shallow else ' (`--delete-files` deletes them)'
        print(f"kept {len(outside)} file(s) outside the files directory{note}:")
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
    print("delete them with `papers file clean`"
          + ("" if config.shallow else ", or remove the entries with `--delete-files`"))
    return []


def tag_parents(tag):
    "the tags above a nested tag: climate/amoc/tipping -> climate, climate/amoc"
    parts = tag.split('/')
    return ['/'.join(parts[:i]) for i in range(1, len(parts)) if parts[i-1]]


def tag_matches(tag, pattern):
    """`--tag PATTERN`: the whole tag, whatever its case, with * patterns;
    a tag also finds the tags under it (climate: climate/amoc)"""
    tag, pattern = tag.lower(), pattern.lower().rstrip('/')
    return fnmatch.fnmatchcase(tag, pattern) or fnmatch.fnmatchcase(tag, pattern + '/*')


def tag_counts(entries):
    "the number of entries of each tag; a tag above nested tags counts the entries under it"
    counts = {}
    for e in entries:
        tags = set()
        for tag in parse_keywords(e):
            tags.add(tag)
            tags.update(tag_parents(tag))
        for tag in tags:
            counts[tag] = counts.get(tag, 0) + 1
    return counts


def print_tag_tree(counts):
    "the tags with their number of entries, the nested tags indented under their parent"
    children = {}
    for tag in counts:
        parents = tag_parents(tag)
        children.setdefault(parents[-1] if parents else None, []).append(tag)

    def show(parent, depth):
        for tag in sorted(children.get(parent, []), key=lambda t: (-counts[t], t.lower(), t)):
            name = tag[len(parent)+1:] if parent else tag
            print(f"{'  '*depth}{name} ({counts[tag]})")
            show(tag, depth+1)
    show(None, 0)


def set_tags(e, tags):
    "write the tags in the keywords field (comma-separated), removing it when empty"
    if tags:
        e['keywords'] = ", ".join(tags)
    elif get_entry_val(e, 'keywords', None) is not None:
        del e['keywords']


# tags are compared without case, as --tag finds them (Climate and climate are one tag): the
# spelling of a tag already there is kept


def add_tags(entries, tags):
    for e in entries:
        old = parse_keywords(e)
        new = list(old)
        for t in tags:
            if t.lower() not in {x.lower() for x in new}:
                new.append(t)
        if new != old:
            set_tags(e, new)


def remove_tags(entries, tags):
    removed = {t.lower() for t in tags}
    for e in entries:
        old = parse_keywords(e)
        new = [t for t in old if t.lower() not in removed]
        if new != old:
            set_tags(e, new)


def rename_tag(entries, old, new):
    """rename a tag in all entries, and the tags under it (climate/amoc ->
    ocean/amoc), whatever their case; return the number of entries changed"""
    def rename(t):
        if t.lower() == old.lower():
            return new
        if t.lower().startswith(old.lower() + '/'):
            return new + t[len(old):]
        return t
    count = 0
    for e in entries:
        tags = parse_keywords(e)
        if all(rename(t) == t for t in tags):
            continue
        renamed = []
        for t in map(rename, tags):
            if t.lower() not in {x.lower() for x in renamed}:
                renamed.append(t)
        set_tags(e, renamed)
        count += 1
    return count


def _entry_from(biblio, path, fmt, entry):
    """the entry of `path` (- : the standard input) in place of `entry`: with
    its key, and its file and keywords fields when the new one has none. Its
    file links are relative to the directory of `path`, as with `papers add`"""
    if path == '-':
        text = read_entry_text()
    else:
        try:
            with open(path, encoding='utf-8-sig') as f:
                text = f.read()
        except OSError as error:
            raise PapersExit(f'--from {path}: {error.strerror}')
    new = parse_edited(text, file_format(path, fmt) if path != '-' else (fmt or 'bibtex'))
    if len(new) != 1:
        raise EditRejected(f'--from {path}: {len(new)} entries, --from takes one -- keeping original entries')
    new = new[0]
    set_entry_key(new, get_entry_val(entry, 'ID', ''))
    if path != '-' and 'file' in new:
        biblio.set_files(new, biblio.get_files(new, os.path.dirname(os.path.abspath(path))))
    for name in ('file', 'keywords'):
        if get_entry_val(new, name, None) is None and get_entry_val(entry, name, None) is not None:
            new[name] = get_entry_val(entry, name)
    return new


def editcmd(parser, o, config):
    ways = [name for name, given in (('--from', o.from_file), ('--set/--unset', o.set or o.unset),
                                     ('--key', o.new_key is not None)) if given]
    if len(ways) > 1:
        parser.error(f'{" and ".join(ways)}: one at a time')
    if o.keep_old_key and o.new_key is None:
        parser.error('--keep-old-key goes with --key NEW')
    if o.from_file == '-' and '-' in o.entries:
        parser.error('--from - and the keys from the standard input (-): only one of them can read it')
    if o.format and not o.from_file:
        parser.error('--format is the format of --from FILE')
    biblio = get_biblio(config)
    entries = select_entries(biblio, o.entries)
    if not entries:
        return
    if o.from_file:
        if len(entries) != 1:
            raise PapersExit(f'--from replaces one entry: {len(entries)} selected')
        replace_entries(biblio, entries, [_entry_from(biblio, o.from_file, o.format, entries[0])])
    elif o.set or o.unset:
        set_fields(entries, o.set or [], o.unset or [])
    elif o.new_key is not None:
        if len(entries) != 1:
            raise PapersExit(f'--key changes the key of one entry: {len(entries)} selected')
        biblio.set_key(entries[0], o.new_key, keep_old=o.keep_old_key)
    else:
        if '-' in o.entries and not stdin_is_terminal():
            # the keys came from a pipe: the editor reads the terminal
            try:
                fd = os.open('/dev/tty', os.O_RDONLY)
                os.dup2(fd, 0)
                os.close(fd)
            except OSError:
                pass
        edit_selected(biblio, entries)
    notes = save_entries(config, biblio)
    _print_biblio_diff(biblio, biblio.entries, notes=notes)


def rmcmd(parser, o, config):
    delete = _delete_files_option(parser, o, config)
    biblio = get_biblio(config)
    entries = select_entries(biblio, o.entries)
    todelete = remove_entries(biblio, entries, config, delete_files=delete,
                              ask='-' not in o.entries)
    savebib(biblio, config)
    _print_biblio_diff(biblio, entries)
    delete_files(todelete, dryrun=papers.config.DRYRUN)


def tagcmd(parser, o, config):
    biblio = get_biblio(config)
    if o.rename:
        if o.entries or o.add or o.rm:
            parser.error('--rename OLD NEW applies to the whole library: no KEY, --add or --rm')
        old, new = o.rename
        count = rename_tag(biblio.entries, old, new)
        notes = save_entries(config, biblio)
        if papers.utils.PORCELAIN is not None:
            _print_biblio_diff(biblio, biblio.entries, notes=notes)
        print(f"renamed tag {old} to {new} in {count} entries")
        print_push_notes(biblio, notes)
        return

    if o.add or o.rm:
        if not o.entries:
            parser.error('--add and --rm need the entries: KEY..., or - to read them from the standard input. '
                         '--add and --rm take all the words after them: put the keys first '
                         '(papers tag KEY... --add TAG...)')
        entries = select_entries(biblio, o.entries)
        add_tags(entries, o.add or [])
        remove_tags(entries, o.rm or [])
        notes = save_entries(config, biblio)
        _print_biblio_diff(biblio, entries, notes=notes)
        return

    entries = select_entries(biblio, o.entries) if o.entries else biblio.entries
    print_tag_tree(tag_counts(entries))


def groups_by_field(entries, field):
    """`list --duplicates --by key|doi|title`: the groups of entries that share
    the key (ignoring case), the DOI, or the title (ignoring case and
    punctuation), in the order of the entries"""
    def value(e):
        if field == 'key':
            return get_entry_val(e, 'ID', '').lower()
        if field == 'doi':
            return normalize_doi(get_entry_val(e, 'doi', ''))
        return re.sub(r'[\W_]', '', get_entry_val(e, 'title', '').lower())
    groups = {}
    for e in entries:
        v = value(e)
        if v:
            groups.setdefault(v, []).append(e)
    return [g for g in groups.values() if len(g) > 1]


def _fullsearch_string(e):
    return " ".join([v for k,v in sorted(e.items(), key=lambda kv:kv[0]) if v is not None])


def listcmd(parser, o, config):

    def _match(word, target, fuzzy=False, substring=False):
        if isinstance(target, list):
            return (any if o.any else all)([_match(word, t, fuzzy, substring) for t in target])

        if fuzzy:
            from rapidfuzz import fuzz
            ratio = o.fuzzy_ratio if o.fuzzy_ratio is not None else 50
            res = (target.lower() in word.lower() or fuzz.token_set_ratio(word.lower(), target.lower(), score_cutoff=ratio) >= ratio)
        elif substring:
            res = target.lower() in word.lower()
        else:
            res = fnmatch.fnmatch(word.lower(), target.lower())

        return res


    def _longmatch(word, target):
        # both sides as the same-paper rule compares text (LaTeX decoded, ASCII, no braces,
        # lower case, single spaces): Muller finds M{\"u}ller and Müller
        target = [normalize_text(t) for t in target] if isinstance(target, list) else normalize_text(target)
        return _match(normalize_text(word), target, fuzzy=o.fuzzy, substring=not o.strict)

    def _requiresreview(e):
        if not isvalidkey(get_entry_val(e, 'ID', '')): return True
        if 'doi' in e and not isvaliddoi(e['doi']): return True
        if 'author' not in e: return True
        if 'title' not in e: return True
        if 'year' not in e: return True
        return False


    # the deprecated forms (removed in v4): --add-files [--rename|--copy], --copy, --fetch
    attach, attach_mode = o.attach, argparse.Namespace()
    if o.add_files:
        mode = '--copy' if o.copy else ('--move' if o.rename else '--link')
        logger.warning(f"`papers list --add-files` is deprecated: use `papers list --attach` "
                       f"(`papers file attach KEY FILE... {mode}`)")
        attach = (attach or []) + o.add_files
        attach_mode = argparse.Namespace(copy=o.copy, move=o.rename and not o.copy,
                                         link=not (o.rename or o.copy))
        rename = keep_source = False
    else:
        if o.copy:
            logger.warning("`papers list --copy` is deprecated: use `papers list --rename --keep-source`")
        rename, keep_source = o.rename or o.copy, o.keep_source or o.copy
    if o.fetch:
        logger.warning("`papers list --fetch` is deprecated: use `papers list ... -K | "
                       "papers check --fetch --fetch-all --fix-doi --fix-key --format-name -`")
    detach, fix_files = o.detach is not None or o.detach_broken, o.fix_files is not None
    exchange = 'pull' if o.pull else 'push' if o.push else 'sync' if o.sync else None
    actions = [name for name, given in [('--delete', o.delete), ('--edit', o.edit), ('--fetch', o.fetch),
                                        ('--add-tag', o.add_keywords), ('--rm-tag', o.rm_tag),
                                        ('--attach', attach), ('--detach', detach), ('--rename', rename),
                                        ('--fix-files', fix_files), ('--open', o.open), ('--push', o.push),
                                        ('--pull', o.pull), ('--sync', o.sync), ('--export', o.export)] if given]
    if len(actions) > 1:
        parser.error(f"one action at a time: {' and '.join(actions)}")
    for option, given, needs, action in [
            ('--keep-source', o.keep_source, rename, '--rename'),
            ('--move', o.move, fix_files or rename, '--fix-files or --rename'),
            ('--pool', o.pool, fix_files or exchange, '--push, --pull, --sync or --fix-files'),
            ('--on-duplicate', o.on_duplicate, exchange, '--push, --pull or --sync'),
            ('--export-format', o.export_format, o.export, '--export')]:
        if given and not needs:
            parser.error(f'{option} goes with {action}')
    if o.detach_broken and o.detach:
        parser.error('--detach-broken takes no FILE')
    if exchange and len(o.pool or []) > 1:
        parser.error(f'--{exchange} takes one --pool')

    # the pools of the library for the actions that place files or exchange
    # entries, made before it is loaded (see papers.cli.file_cmds.rename_entries)
    pools = None
    if rename or attach:
        pools = library_pools(config)
    elif fix_files:
        nameformat = config.nameformat  # the library's own, as for papers file fix
        pools = file_check_pools(config, fix=True)
    elif exchange:
        # the options of papers pull, push, sync KEY...
        exchange_options = argparse.Namespace(entries=[], all=False, pool=(o.pool or [None])[0], check=False,
                                              on_duplicate=o.on_duplicate, mode=None, yes=False)
        pools = exchange_pools(config, exchange_options)
    biblio = get_biblio(config)
    entries = biblio.db.entries

    if o.review_required:
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
        if o.fuzzy:
            entries = [e for e in entries if 'keywords' in e and _longmatch(e['keywords'], o.keywords)]
        else:
            # whole tags, not part of the keywords field: --tag ice does not find ice-review (ice* does),
            # and the tags under it: --tag ice finds ice/sheet
            def _has_tag(e, target):
                return any(tag_matches(tag, target) for tag in parse_keywords(e))
            entries = [e for e in entries
                       if (any if o.any else all)(_has_tag(e, target) for target in o.keywords)]
    if o.fullsearch:
        o.strict = False
        entries = [e for e in entries if _longmatch(_fullsearch_string(e), o.fullsearch)]

    if o.similarity is not None:
        logger.warning('--similarity is deprecated and ignored: entries are the same paper by identifier, '
                       'or by authors and title (see the documentation of papers add)')

    if o.by:
        if o.fuzzy:
            parser.error('--by and --fuzzy are mutually exclusive')
        entries = [e for g in groups_by_field(entries, o.by) for e in g]

    elif o.duplicates:
        listed = []
        for g in duplicate_groups(entries, biblio.distinct):
            listed.extend(e for e in g.entries if not any(e is x for x in listed))
        if o.fuzzy:
            for a, b in fuzzy_pairs(entries, o.fuzzy_ratio if o.fuzzy_ratio is not None else FUZZY_RATIO):
                listed.extend(e for e in (a, b) if not any(e is x for x in listed))
        entries = listed

    # the entries that the same search without --invert does not list
    if o.invert:
        listed = {id(e) for e in entries}
        entries = [e for e in biblio.db.entries if id(e) not in listed]

    notes, failed = {}, 0
    if o.add_keywords:
        add_tags(entries, o.add_keywords)
        notes = save_entries(config, biblio)

    elif o.rm_tag:
        remove_tags(entries, o.rm_tag)
        notes = save_entries(config, biblio)

    elif detach:
        detach_entries(biblio, config, entries, o.detach or [], broken=o.detach_broken)
        return

    elif fix_files:
        fix_options = argparse.Namespace(search=o.fix_files, pool=o.pool, move=o.move)
        check_entries_files(fix_options, config, True, pools, biblio, entries, nameformat)
        return

    elif exchange:
        run = {'pull': pull_entries, 'push': push_entries, 'sync': sync_entries}[exchange]
        run(exchange_options, biblio, Exchange(config, biblio, pools), selected=entries)
        return

    elif o.export:
        export_options = argparse.Namespace(dir=o.export, format=o.export_format, files=o.export_files)
        export_entries(export_options, config, biblio, entries)
        return

    elif attach:
        if len(entries) != 1:
            raise PapersExit(f"list only one entry to use --attach ({len(entries)} listed): nothing was changed")
        notes, placed = attach_entry_files(biblio, config, pools, entries[0], attach, attach_mode)
        failed = 0 if placed else 1

    elif o.edit:
        edit_selected(biblio, entries)
        entries = biblio.entries
        notes = save_entries(config, biblio)

    elif o.fetch:
        for e in entries:
            biblio.fix_entry(e, fix_doi=True, fix_key=True, fetch_all=True, interactive=True)
        notes = save_entries(config, biblio)

    elif rename:
        notes, failed = rename_entries(biblio, config, pools, entries, keep_source=keep_source,
                                       mode='move' if o.move else None)

    elif o.delete:
        todelete = remove_entries(biblio, entries, config, delete_files=_delete_files_option(parser, o, config))
        savebib(biblio, config)
        delete_files(todelete, dryrun=papers.config.DRYRUN)

    elif o.open:
        open_entries(biblio, entries)
        return

    else:
        # the listing is the data: on the standard output, with --porcelain too
        out = papers.utils.PORCELAIN or sys.stdout
        if o.field:
            for e in entries:
                values = [get_entry_val(e, k, "") for k in o.field]
                print(*values if o.no_key else [format_key(e), *values], file=out)
        elif o.format == 'key':
            for e in entries:
                print(get_entry_val(e, 'ID', ''), file=out)
        elif o.format == 'bibtex':
            print(format_entries(entries), file=out)
        elif o.format in FORMATS:
            out.write(dumps(entries, o.format, files=biblio.get_files))
        else:
            for e in entries:
                print(format_entry(biblio, e, no_key=o.no_key), file=out)
        return  # nothing was changed: no Added/Modified/Removed lines to look for

    # report any entry mutations (--attach, --add-tag, --rm-tag, --edit, --fetch,
    # --rename, --delete) using the same Added/Modified/Removed convention as addcmd
    # (the other actions print their report, as their command does)
    _print_biblio_diff(biblio, entries, notes=notes)
    if failed:
        raise PapersExit()  # the errors are reported: exit 1


def opencmd(parser, o, config):
    biblio = None
    for key in read_selection(o.key):
        # an existing file is opened directly with the system viewer; anything
        # else is looked up as an entry key (or DOI) in the bibliography
        if os.path.isfile(key):
            logger.info(f"opening {key} ...")
            open_with_system(key)
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
        open_entries(biblio, [e])


def open_entries(biblio, entries):
    "`papers open` (also `papers list --open`): open the files of the entries with the system viewer"
    for e in entries:
        if not biblio.get_files(e):
            logger.warning(f'{get_entry_val(e, "ID", "")}: no attached file')
            continue
        view_entry_files(biblio, e)
