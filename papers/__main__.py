import os
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
from papers.extract import fetch_bibtex_by_doi
from papers.encoding import parse_file, format_file, family_names, format_entries
from papers.config import config, bcolors, search_config, CONFIG_FILE, DATA_DIR
from papers.duplicate import list_duplicates, list_uniques, edit_entries
from papers.bib import Biblio, FUZZY_RATIO, DEFAULT_SIMILARITY, entry_filecheck, backupfile, isvalidkey
from papers import __version__


def savebib(my_bib, config):
    """
    Given a Biblio object and its configuration, save them to disk.  If you're using the git bib tracker, will trigger a git commit there.
    """
    logger.info('Saving '+config.bibtex)
    if papers.config.DRYRUN:
        return
    if my_bib is not None:
        my_bib.save(config.bibtex)
    if config.git:
        config.gitcommit()


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
    return o, config

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
    return o, config

def installcmd(o, config):
    """
    Given options and a config state, installs the expected config files.
    """
    o, config = set_nameformat_config_from_cmd(o, config)
    o, config = set_keyformat_config_from_cmd(o, config)

    checkdirs = ["files", "pdfs", "pdf", "papers", "bibliography"]
    default_bibtex = "papers.bib"
    default_filesdir = "files"

    if o.local:
        datadir = gitdir = ".papers"
        papersconfig = ".papers/config.json"
        workdir = Path('.')
        biblios = list(workdir.glob("*.bib"))
        
        if o.absolute_paths is None:
            o.absolute_paths = False

    else:
        datadir = config.data
        gitdir = config.gitdir
        papersconfig = CONFIG_FILE
        workdir = Path(DATA_DIR)
        biblios = list(Path('.').glob("*.bib")) + list(workdir.glob("*.bib"))
        checkdirs = [os.path.join(papers.config.DATA_DIR, "files")] + checkdirs
        
        if o.absolute_paths is None:
            o.absolute_paths = True

    biblios = [default_bibtex] + [f for f in biblios if Path(f) != Path(default_bibtex)]

    if config.filesdir:
        checkdirs = [config.filesdir] + checkdirs

    for d in checkdirs:
        if os.path.exists(str(d)):
            default_filesdir = d
            break

    RESET_DEFAULT = ('none', 'null', 'unset', 'undefined', 'reset', 'delete', 'no', 'n')
    ACCEPT_DEFAULT = ('yes', 'y')

    if not o.bibtex:
        if len(biblios) > 1:
            logger.warn("Several bibtex files found: "+" ".join([str(b) for b in biblios]))
        if biblios:
            default_bibtex = biblios[0]
        if o.prompt:
            if os.path.exists(default_bibtex):
                user_input = input(f"Bibtex file name [default to existing: {default_bibtex}] [Enter/Yes/No]: ")
            else:
                user_input = input(f"Bibtex file name [default to new: {default_bibtex}] [Enter/Yes/No]: ")
            if user_input:
                if user_input.lower() in RESET_DEFAULT:
                    default_bibtex = None
                elif user_input.lower() in ACCEPT_DEFAULT:
                    pass
                else:
                    default_bibtex = Path(user_input)
        o.bibtex = default_bibtex

    if not o.filesdir:
        if o.prompt:
            if Path(default_filesdir).exists():
                user_input = input(f"Files folder [default to existing: {default_filesdir}] [Enter/Yes/No]: ")
            else:
                user_input = input(f"Files folder [default to new: {default_filesdir}] [Enter/Yes/No]: ")
            if user_input:
                if user_input.lower() in RESET_DEFAULT:
                    default_filesdir = None
                elif user_input.lower() in ACCEPT_DEFAULT:
                    pass
                else:
                    default_filesdir = user_input
        o.filesdir = default_filesdir


    config.bibtex = o.bibtex
    config.filesdir = o.filesdir
    config.gitdir = gitdir
    config.data = datadir
    config.file = papersconfig
    config.local = o.local
    config.absolute_paths = o.absolute_paths


    if config.git and not o.git and o.bibtex == config.bibtex:
        ans = input('stop git tracking (this will not affect actual git directory)? [Y/n] ')
        if ans.lower() != 'y':
            o.git = True

    if o.reset_paths:
        config.reset()

    config.git = o.git

    # create bibtex file if not existing
    bibtex = Path(o.bibtex) if o.bibtex else None
    
    if bibtex and not bibtex.exists():
        logger.info('create empty bibliography database: '+o.bibtex)
        bibtex.parent.mkdir(parents=True, exist_ok=True)
        bibtex.open('w', encoding="utf-8").write('')

    # create bibtex file if not existing
    filesdir = Path(o.filesdir) if o.filesdir else None
    if filesdir and not filesdir.exists():
        logger.info('create empty files directory: '+o.filesdir)
        filesdir.mkdir(parents=True)

    if o.git and not os.path.exists(config._gitdir):
        config.gitinit()

    logger.info('save config file: '+config.file)
    if o.local:
        os.makedirs(".papers", exist_ok=True)
    else:
        from papers.config import CONFIG_HOME
        os.makedirs(CONFIG_HOME, exist_ok=True)
    config.save()

    print(config.status(check_files=not o.no_check_files, verbose=True))

def _dir_is_empty(dir):
    # TODO this is actually never tested.
    with os.scandir(dir) as it:
        return not any(it)

def uninstallcmd(o, config):
    # TODO this is actually never tested.    
    if Path(config.file).exists():
        logger.info(f"The uninstaller will now remove {config.file}")
        os.remove(config.file)
        parent = os.path.dirname(config.file)
        if _dir_is_empty(parent):
            logger.info(f"The config dir {parent} is empty and the uninstaller will now remove it.")
            os.rmdir(parent)
        papers.config.config = papers.config.Config()
    else:
        logger.info(f"The uninstaller found no config file to remove.")
        return

    if o.recursive:
        config.file = search_config([os.path.join(".papers", "config.json")], start_dir=".", default=CONFIG_FILE)
        uninstallcmd(o, config)

def check_install(parser, o, config):
    """
    Given an option and config, checks to see if the install is done correctly on this filesystem.
    """
    if getattr(o, "bibtex", None) is not None:
        config.bibtex = o.bibtex
    if getattr(o, "filesdir", None) is not None:
        config.filesdir = o.filesdir
    if getattr(o, "absolute_paths", None) is not None:
        config.absolute_paths = o.absolute_paths

    install_doc = f"first execute `papers install --bibtex {config.bibtex or '...'} [ --local ]`"
    if not config.bibtex:
        print(f"--bibtex must be specified, or {install_doc}")
        parser.exit(1)
    elif not os.path.exists(config.bibtex):
        print(f'papers: error: no bibtex file found, do `touch {config.bibtex}` or {install_doc}')
        parser.exit(1)
    logger.info(f'bibtex: {config.bibtex!r}')
    logger.info(f'filesdir: {config.filesdir!r}')
    return True

def addcmd(o, config):
    """
    Given an options set and a config, sets up the function call to add the file or dir to the bibtex, and executes it.
    """

    o, config = set_nameformat_config_from_cmd(o, config)
    o, config = set_keyformat_config_from_cmd(o, config)

    if os.path.exists(config.bibtex):
        my = Biblio.load(config.bibtex, config.filesdir)
    else:
        my = Biblio.newbib(config.bibtex, config.filesdir)

    kw = {'on_conflict':o.mode, 'check_duplicate':not o.no_check_duplicate,
            'mergefiles':not o.no_merge_files, 'update_key':o.update_key}

    if len(o.file) > 1:
        if o.attachment:
            logger.error('--attachment is only valid for one PDF / BIBTEX entry')
            addp.exit(1)
        if o.doi:
            logger.error('--doi is only valid for one added file')
            addp.exit(1)

    if len(o.file) == 0:
        if not o.doi:
            logger.error('Please provide either a PDF file or BIBTEX entry or specify `--doi DOI`')
            addp.exit(1)
        elif o.no_query_doi:
            logger.error('If no file is present, --no-query-doi is not compatible with --doi')
            addp.exit(1)
        else:
            my.fetch_doi(o.doi, attachments=o.attachment, rename=o.rename, copy=o.copy, **kw)

    for file in o.file:
        try:
            if os.path.isdir(file):
                if o.recursive:
                    my.scan_dir(file, rename=o.rename, copy=o.copy,
                                search_doi=not o.no_query_doi,
                                search_fulltext=not o.no_query_fulltext,
                                **kw)
                else:
                    raise ValueError(file+' is a directory, requires --recursive to explore')
                
            elif file.endswith('.pdf'):
                my.add_pdf(file, attachments=o.attachment, rename=o.rename, copy=o.copy,
                           search_doi=not o.no_query_doi,
                           search_fulltext=not o.no_query_fulltext,
                           scholar=o.scholar, doi=o.doi,
                           **kw)

            else: # file.endswith('.bib'):
                my.add_bibtex_file(file, **kw)

        except Exception as error:
            # print(error)
            # addp.error(str(error))
            raise
            logger.error(str(error))
            if not o.ignore_errors:
                if len(o.file) or (os.isdir(file) and o.recursive)> 1:
                    logger.error('use --ignore to add other files anyway')
                addp.exit(1)

    savebib(my, config)

def checkcmd(o, config):
    o, config = set_keyformat_config_from_cmd(o, config)
    my = Biblio.load(config.bibtex, config.filesdir)
    
    # if o.fix_all:
    #     o.fix_doi = True
    #     o.fetch_all = True
    #     o.fix_key = True

    for e in my.entries:
        if o.keys and e.get('ID','') not in o.keys:
            continue
        my.fix_entry(e, fix_doi=o.fix_doi, fetch=o.fetch, fetch_all=o.fetch_all, fix_key=o.fix_key,
                     auto_key=o.auto_key, format_name=o.format_name, encoding=o.encoding,
                     key_ascii=o.key_ascii, interactive=not o.force)


    if o.duplicates:
        my.check_duplicates(mode=o.mode)

    savebib(my, config)

def filecheckcmd(o, config):
    o, config = set_nameformat_config_from_cmd(o, config)

    my = Biblio.load(config.bibtex, config.filesdir)

    # fix ':home' entry as saved by Mendeley
    for e in my.entries:
        entry_filecheck(e, delete_broken=o.delete_broken, fix_mendeley=o.fix_mendeley,
                        check_hash=o.hash_check, check_metadata=o.metadata_check, interactive=not o.force, relative_to=my.relative_to)

    if o.rename:
        my.rename_entries_files(o.copy)
        
    savebib(my, config)

def undocmd(o, config):
    back = backupfile(config.bibtex)
    tmp = config.bibtex + '.tmp'
    # my = :config.bibtex, config.filesdir)
    logger.info(config.bibtex+' <==> '+back)
    shutil.copy(config.bibtex, tmp)
    shutil.move(back, config.bibtex)
    shutil.move(tmp, back)
    # o.savebib()

def gitcmd(o):
    try:
        out = sp.check_output(['git']+o.gitargs, cwd=config.gitdir)
        print(out.decode())
    except:
        gitp.error('papers failed to execute git command -- you should check your system git install.')

def doicmd(o):
    print(extract_pdf_doi(o.pdf, image=o.image))    

def fetchcmd(o):
    print(fetch_bibtex_by_doi(o.doi))

def extractcmd(o):
    print(extract_pdf_metadata(o.pdf, search_doi=not o.fulltext, search_fulltext=True, scholar=o.scholar, minwords=o.word_count, max_query_words=o.word_count, image=o.image))
    # print(fetch_bibtex_by_doi(o.doi))

def match(word, target, fuzzy=False, substring=False):
    if isinstance(target, list):
        return any([match(word, t, fuzzy, substring) for t in target])

    if fuzzy:
        res = fuzz.token_set_ratio(word, target, score_cutoff=o.fuzzy_ratio) > o.fuzzy_ratio
    elif substring:
        res = target.lower() in word.lower()
    else:
        res = fnmatch.fnmatch(word.lower(), target.lower())

    return res if not o.invert else not res


def longmatch(word, target):
    return match(word, target, fuzzy=o.fuzzy, substring=not o.strict)

def nfiles(e):
    return len(parse_file(e.get('file',''), relative_to=my.relative_to))


def requiresreview(e):
    if not isvalidkey(e.get('ID','')): return True
    if 'doi' in e and not isvaliddoi(e['doi']): return True
    if 'author' not in e: return True
    if 'title' not in e: return True
    if 'year' not in e: return True
    return False


def listcmd(o, config):

    my = Biblio.load(config.bibtex, config.filesdir)
    entries = my.db.entries

    if o.fuzzy:
        from rapidfuzz import fuzz


    if o.review_required:
        if o.invert:
            entries = [e for e in entries if not requiresreview(e)]
        else:
            entries = [e for e in entries if requiresreview(e)]
            for e in entries:
                if 'doi' in e and not isvaliddoi(e['doi']):
                    e['doi'] = bcolors.FAIL + e['doi'] + bcolors.ENDC
    if o.has_file:
        entries = [e for e in entries if e.get('file','')]
    if o.no_file:
        entries = [e for e in entries if not e.get('file','')]
    if o.broken_file:
        entries = [e for e in entries if e.get('file','') and any([not os.path.exists(f) for f in parse_file(e['file'], relative_to=my.relative_to)])]


    if o.doi:
        entries = [e for e in entries if 'doi' in e and match(e['doi'], o.doi)]
    if o.key:
        entries = [e for e in entries if 'ID' in e and match(e['ID'], o.key)]
    if o.year:
        entries = [e for e in entries if 'year' in e and match(e['year'], o.year)]
    if o.first_author:
        first_author = lambda field : family_names(field)[0]
        entries = [e for e in entries if 'author' in e and match(firstauthor(e['author']), o.author)]
    if o.author:
        author = lambda field : ' '.join(family_names(field))
        entries = [e for e in entries if 'author' in e and longmatch(author(e['author']), o.author)]
    if o.title:
        entries = [e for e in entries if 'title' in e and longmatch(e['title'], o.title)]
    if o.abstract:
        entries = [e for e in entries if 'abstract' in e and longmatch(e['abstract'], o.abstract)]

    _check_duplicates = lambda uniques, groups: uniques if o.invert else list(itertools.chain(*groups))

    # if o.duplicates_key or o.duplicates_doi or o.duplicates_tit or o.duplicates or o.duplicates_fuzzy:
    list_dup = list_uniques if o.invert else list_duplicates

    if o.duplicates_key:
        entries = list_dup(entries, key=my.key, issorted=True)
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

    if o.no_key:
        key = lambda e: ''
    else:
        # key = lambda e: bcolors.OKBLUE+e['ID']+filetag(e)+':'+bcolors.ENDC
        key = lambda e: nfiles(e)*(bcolors.BOLD)+bcolors.OKBLUE+e['ID']+':'+bcolors.ENDC

    if o.edit:
        otherentries = [e for e in my.db.entries if e not in entries]
        try:
            entries = edit_entries(entries)
            my.db.entries = otherentries + entries
        except Exception as error:
            logger.error(str(error))
            return

        savebib(my, config)
        
    elif o.fetch:
        for e in entries:
            my.fix_entry(e, fix_doi=True, fix_key=True, fetch_all=True, interactive=True)
        savebib(my, config)

    elif o.delete:
        for e in entries:
            my.db.entries.remove(e)
        savebib(my, config)

    elif o.field:
        # entries = [{k:e[k] for k in e if k in o.field+['ID','ENTRYTYPE']} for e in entries]
        for e in entries:
            print(key(e),*[e.get(k, "") for k in o.field])
    elif o.key_only:
        for e in entries:
            print(e['ID'].encode('utf-8'))
    elif o.one_liner:
        for e in entries:
            tit = e.get('title', '')[:60]+ ('...' if len(e.get('title', ''))>60 else '')
            info = []
            if e.get('doi',''):
                info.append('doi:'+e['doi'])
            n = nfiles(e)
            if n:
                info.append(bcolors.OKGREEN+'file:'+str(n)+bcolors.ENDC)
            infotag = '('+', '.join(info)+')' if info else ''
            print(key(e), tit, infotag)
    else:
        print(format_entries(entries))

def statuscmd(o):
    print(config.status(check_files=not o.no_check_files, verbose=o.verbose))
    
def main():

    configfile = search_config([os.path.join(".papers", "config.json")], start_dir=".", default=config.file)

    if os.path.exists(configfile):
        config.file = configfile
        config.load()

    else:
        config.bibtex = None
        config.filesdir = None

    parser = argparse.ArgumentParser(description='library management tool')
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
    grp.add_argument('--no-prompt', action='store_false', dest="prompt",
        help='no prompt, use default (useful for tests)')
    grp.add_argument('--relative-paths', action="store_false", dest="absolute_paths", default=None)
    grp.add_argument('--absolute-paths', action="store_true", default=None)

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
    installp.add_argument('--reset-paths', action='store_true', help=argparse.SUPPRESS)
    # egrp = installp.add_mutually_exclusive_group()
    installp.add_argument('--local', action="store_true",
        help="""setup papers locally in current directory (global install by default), exposing bibtex and filesdir,
        and having the rest under .papers (config options). Only keep the cache globally.
        This might not play out too well with git tracking (local install usuall have their own git) but might be OK.""")

    installp.add_argument('--git', action='store_true',
        help="""Track bibtex files with git.
        Each time the bibtex is modified, a copy of the file is saved in a git-tracked
        global directory (see papers status), and committed. Note the original bibtex name is
        kept, so that different files can be tracked simultaneously, as long as the names do
        not conflict. This option is mainly useful for backup purposes (local or remote).
        Use in combination with `papers git`'
        """)
    installp.add_argument('--gitdir', default=None, help=f'default: {config.gitdir} or local')

    grp = installp.add_argument_group('status')
    # grp.add_argument('-l','--status', action='store_true')
    # grp.add_argument('-v','--verbose', action='store_true')
    # grp.add_argument('-c','--check-files', action='store_true')
    grp.add_argument('--no-check-files', action='store_true', help='faster, less info')
    # grp.add_argument('-v','--verbose', action='store_true', help='app status info')


    # uninstall
    # =======
    uninstallp = subparsers.add_parser('uninstall', description='remove configuration file',
        parents=[cfg])
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

    grp = addp.add_argument_group('pdf metadata')
    grp.add_argument('--doi', help='provide DOI -- skip parsing PDF')
    grp.add_argument('--no-query-doi', action='store_true', help='do not attempt to parse and query doi')
    grp.add_argument('--no-query-fulltext', action='store_true', help='do not attempt to query fulltext in case doi query fails')
    grp.add_argument('--scholar', action='store_true', help='use google scholar instead of crossref')

    grp = addp.add_argument_group('attached files')
    grp.add_argument('-a','--attachment', nargs='+') #'supplementary material')
    grp.add_argument('-r','--rename', action='store_true',
        help='rename PDFs according to key')
    grp.add_argument('-c','--copy', action='store_true',
        help='copy file instead of moving them')

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
    listp = subparsers.add_parser('list', description='list (a subset of) entries',
        parents=[cfg])

    mgrp = listp.add_mutually_exclusive_group()
    mgrp.add_argument('--strict', action='store_true', help='exact matching - instead of substring (only (*): title, author, abstract)')
    mgrp.add_argument('--fuzzy', action='store_true', help='fuzzy matching - instead of substring (only (*): title, author, abstract)')
    listp.add_argument('--fuzzy-ratio', type=int, default=FUZZY_RATIO, help='threshold for fuzzy matching of title, author, abstract (default:%(default)s)')
    listp.add_argument('--similarity', choices=['EXACT','GOOD','FAIR','PARTIAL','FUZZY'], default=DEFAULT_SIMILARITY, help='duplicate testing (default:%(default)s)')
    listp.add_argument('--invert', action='store_true')

    grp = listp.add_argument_group('search')
    grp.add_argument('-a','--author', nargs='+', help='any of the authors (*)')
    grp.add_argument('--first-author', nargs='+')
    grp.add_argument('-y','--year', nargs='+')
    grp.add_argument('-t','--title', help='title (*)')
    grp.add_argument('--abstract', help='abstract (*)')
    grp.add_argument('--key', nargs='+')
    grp.add_argument('--doi', nargs='+')


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
    mgrp.add_argument('-k','--key-only', action='store_true')
    mgrp.add_argument('-l', '--one-liner', action='store_true', help='one liner')
    mgrp.add_argument('-f', '--field', nargs='+', help='specific field(s) only')
    grp.add_argument('--no-key', action='store_true')

    grp = listp.add_argument_group('action on listed results (pipe)')
    grp.add_argument('--delete', action='store_true')
    grp.add_argument('--edit', action='store_true', help='interactive edit text file with entries, and re-insert them')
    grp.add_argument('--fetch', action='store_true', help='fetch and fix metadata')
    # grp.add_argument('--merge-duplicates', action='store_true')


    # doi
    # ===
    doip = subparsers.add_parser('doi', description='parse DOI from PDF')
    doip.add_argument('pdf')
    doip.add_argument('--image', action='store_true', help='convert to image and use tesseract instead of pdftotext')

    # fetch
    # =====
    fetchp = subparsers.add_parser('fetch', description='fetch bibtex from DOI')
    fetchp.add_argument('doi')


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
    undop = subparsers.add_parser('undo', parents=[cfg])

    # git
    # ===
    gitp = subparsers.add_parser('git', description='git subcommand')
    gitp.add_argument('gitargs', nargs=argparse.REMAINDER)

    # All parser setup complete; below here, all we do is check parser options and run the relevant command.

    o = parser.parse_args()

    if o.version:
        print(__version__)
        parser.exit(0)

    # verbosity
    if getattr(o,'logging_level',None):
        logger.setLevel(o.logging_level)
    # modify disk state?
    if hasattr(o,'dry_run'):
        papers.config.DRYRUN = o.dry_run

    if o.cmd == 'status':
        return statuscmd(o)

    if o.cmd == 'install':
        installcmd(o, config)
    elif o.cmd == 'uninstall':
        uninstallcmd(o, config)
        print(config.status(verbose=True))
    elif o.cmd == 'add':
        check_install(parser, o, config) and addcmd(o, config)
    elif o.cmd == 'check':
        check_install(parser, o, config) and checkcmd(o, config)
    elif o.cmd == 'filecheck':
        check_install(parser, o, config) and filecheckcmd(o, config)
    elif o.cmd == 'list':
        check_install(parser, o, config) and listcmd(o, config)
    elif o.cmd == 'undo':
        check_install(parser, o, config) and undocmd(o, config)
    elif o.cmd == 'git':
        check_install(parser, o, config) and gitcmd(o, config)
    elif o.cmd == 'doi':
        doicmd(o)
    elif o.cmd == 'fetch':
        fetchcmd(o)
    elif o.cmd == 'extract':
        extractcmd(o)
    else:
        parser.print_help()
        parser.exit(1)
        # raise ValueError('this is a bug')


if __name__ == '__main__':
    main()
