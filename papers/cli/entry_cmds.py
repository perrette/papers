"""papers add, check, list, edit, rm, tag, open"""
import copy
import fnmatch
import os

import papers.config
import papers.files
from papers import logger
from papers.bib import isvalidkey
from papers.duplicate import FUZZY_RATIO, duplicate_groups, edit_entries, fuzzy_pairs
from papers.encoding import (family_names, format_entries, format_entry, format_file, format_key, parse_file,
                             parse_keywords, standard_name)
from papers.entries import entry_from_dict, get_entry_val
from papers.extract import isvaliddoi, prefetch_pdf_metadata
from papers.files import (attach_files, delete_files, describe_file, download_url, files_policy, rename_files,
                          scan_dir_items)
from papers.identifiers import read_selection, select_entries
from papers.library import get_biblio, savebib
from papers.merge import DuplicateError
from papers.pools import Exchange, PoolLookup, Pools, report_lines, use_pool_files
from papers.utils import PapersExit, view_pdf
from papers.cli.common import (view_entry_files, set_format_config_from_cmd, _print_biblio_diff, files_mode,
                               duplicate_resolver, save_exchange, stdin_is_terminal, edit_selected,
                               print_kept_files, _delete_files_option)


def addcmd(parser, o, config):
    """
    Given an options set and a config, sets up the function call to add the file or all files in the directory to the bibtex, and executes it.
    """

    set_format_config_from_cmd(o, config, 'name')
    set_format_config_from_cmd(o, config, 'key')

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
    policy = files_policy(config, mode, pools.files_dirs())
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
    set_format_config_from_cmd(o, config, 'key')

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


def remove_entries(biblio, entries, config, delete_files=None, ask=True):
    """remove entries from the bibliography, and return the files to delete
    once the bibliography is saved.

    Candidates are the files of the removed entries that no remaining entry
    links to. delete_files=True deletes them all; False keeps them; None
    asks, in a terminal (ask=True), whether to delete those inside the files
    directory, and keeps them without a terminal. A file outside the files
    directory is only deleted with delete_files=True.
    """
    inside, outside, kept, in_pool = papers.files.remove_entries(biblio, entries, config.filesdir,
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
                     ('copy' if o.copy else 'move') if o.rename else 'link', Pools(config).files_dirs())
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
        rename_files(biblio, entries, config, Pools(config).files_dirs(), keep_source=o.copy)
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
