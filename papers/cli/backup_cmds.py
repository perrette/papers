"""papers undo, redo, restore (restore-backup: deprecated), history (backup: deprecated), git (removed)"""
import os
import time

import papers.config
import papers.history
import papers.lock
from papers import backup, logger
from papers.bib import Biblio
from papers.files import is_inside
from papers.utils import PapersExit, stdin_is_terminal

MB = backup.MB


def _linked_files(config):
    "the real paths of the files that the entries of the bibtex link to"
    if not config.bibtex or not os.path.exists(config.bibtex):
        return set()
    biblio = Biblio.load(config.bibtex, config.filesdir)
    return {os.path.realpath(f) for e in biblio.entries for f in biblio.get_files(e)}


def _auto_push(config):
    """after undo or redo in a shallow library with auto-push: the shared
    entries that differ from their origin copy are pushed, as after any
    command (an entry changed in the pool too is left to `papers sync`).
    Nothing to push in general: undo and redo restore the origin copies
    with the bibtex. A push is a new step of the library (its origin
    copies), after which there is nothing to redo, as after any command."""
    from papers.cli.common import print_push_notes, push_notes, save_exchange
    from papers.library import get_biblio
    from papers.merge import Resolver
    from papers.pools import Exchange, PoolError
    if not config.shallow or not config.auto_push or papers.config.DRYRUN:
        return
    biblio = get_biblio(config)
    exchange = Exchange(config, biblio)
    try:
        pool = exchange.pools.target()
    except PoolError as error:
        logger.warning(f'not pushed to the pool: {error}')
        return
    shared, _ = exchange.sharing(biblio.entries, pool)
    report = exchange.push(shared, pool, Resolver('skip'), include_new=False)
    if any(what == 'updated' for _, _, what in report):
        project, place = backup.project_of(config)
        undone = project.head(place)['redo']
        save_exchange(exchange)
        if undone:
            print(f'the push is a new step: nothing to redo now (`papers restore {papers.history.short(undone[0])}` '
                  f'goes back to the steps undone)')
    print_push_notes(biblio, push_notes(report))


def _time_travel(config, kind, func, *args):
    """undo, redo or restore: say which state is restored, the files that
    moved, the pools that followed, and which files of the files directory no entry links to any more"""
    before = _linked_files(config)
    project, target, file_lines, pool_lines = func(config, *args)
    if file_lines is None:  # --dry-run
        print(f'DRYRUN: {kind}: {config.bibtex} not restored to {backup.describe(project, target)}')
        return
    print(f'{kind}: {os.path.basename(config.bibtex)} restored to {backup.describe(project, target)}')
    if file_lines:
        print('\n'.join(file_lines))
    if pool_lines:
        print('\n'.join(pool_lines))
    after = _linked_files(config)
    unlinked = sorted(f for f in before - after
                      if os.path.isfile(f) and config.filesdir and is_inside(f, config.filesdir))
    if unlinked:
        print(f'{len(unlinked)} file(s) of the files directory are linked by no entry now '
              f'(`papers file clean` removes them):')
        for f in unlinked:
            print(f'  {f}')


def undocmd(parser, o, config):
    _time_travel(config, 'undo', backup.undo, o.steps, o.library_only)
    if not o.library_only:
        _auto_push(config)


def redocmd(parser, o, config):
    _time_travel(config, 'redo', backup.redo, o.steps, o.library_only)
    if not o.library_only:
        _auto_push(config)


def restorecmd(parser, o, config):
    if o.cmd == 'restore-backup':
        logger.warning('`papers restore-backup` is deprecated: use `papers restore`')
    n = o.state if o.state is not None else o.ref
    _time_travel(config, 'restore', backup.restore, n)


# papers history
# ==============

def _when(t):
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(t or 0))


def _mb(size):
    return f'{size / MB:.1f} MB'


def remove_history(config, yes=False, id=None):
    """remove the history of this place (and of the library, when no other
    place uses it), or of the library `id`"""
    if id:
        found = [st for st in backup.all_stores(config) if id in st.project_ids()]
        if not found:
            raise PapersExit(f'no history of a library {id} (see `papers history --all`)')
        project = found[0].project(id)
        what = f'the history of the library {id} ({len(project.states())} steps)'
        if not yes and not _confirm(f'remove {what}?'):
            return
        project.remove()
        print(f'removed {what}')
        backup.prune(config, found[0])
        return
    project, place = backup.project_of(config, create=False)
    if project is None or not project.exists():
        print('the library has no history')
        return
    others = [p for p in project.heads() if p != place]
    if others:
        project.remove_head(place)
        print(f'removed the history of {papers.config.short_home(place)}; the history of the library stays '
              f'for the other folder(s) that use it: {", ".join(papers.config.short_home(p) for p in others)}')
        return
    what = f'the history of the library ({len(project.states())} steps)'
    if not yes and not _confirm(f'remove {what}?'):
        return
    project.remove()
    print(f'removed {what}')
    backup.prune(config, project.store)  # its pieces and files, unless another library keeps them


def _size(size):
    return f'{size / 1024:.0f} KB' if size < MB else f'{size / MB:.1f} MB'


def drop_files(config, target, yes=False):
    """papers history --drop-files N|PATH: the files that step N deleted, or
    the file deleted from PATH, leave the history (to the trash of the system)"""
    project, place = backup.project_of(config, create=False)
    if project is None or not project.exists():
        raise PapersExit('the library has no history')
    found = backup.files_to_drop(config, project, target)
    if not found:
        print(f'the history keeps no file deleted {"from " + target if backup.is_path(target) else "by step " + target}')
        return
    total = sum(size for _, size in found.values())
    for path, size in sorted(found.values()):
        print(f'  {papers.config.short_home(path)} ({_size(size)})')
    question = (f'drop {len(found)} file{"s" if len(found) > 1 else ""} ({_size(total)}) from the history? '
                'Undo will not bring them back; they go to the trash of the system')
    if not yes and not _confirm(question):
        return
    backup.drop_files(project, set(found))
    print(f'dropped {len(found)} file{"s" if len(found) > 1 else ""} ({_size(total)}) from the history')


def revert(o, config):
    """papers history --revert N: take back step N alone (see papers.revert),
    saved as a new step; the report of the entries, and of the pools that
    step N also changed"""
    from papers.cli.common import _print_biblio_diff, duplicate_resolver, save_entries
    from papers.library import get_biblio
    import papers.revert
    if not config.bibtex or not os.path.exists(config.bibtex):
        raise PapersExit('no library: --revert takes back a step of the history of a library')
    papers.lock.acquire(config)
    biblio = get_biblio(config)
    project, _ = backup.project_of(config)
    step = backup.resolve(project, o.revert)
    lines = papers.revert.revert(config, biblio, step, duplicate_resolver(o, 'revert'))
    backup.mark(config, reverts=[step])
    notes = save_entries(config, biblio)
    _print_biblio_diff(biblio, biblio.entries, notes=notes)
    if lines:
        print('\n'.join(lines))
    project, _ = backup.project_of(config)
    for line in papers.revert.pool_lines(config, project, step):
        print(line)


def _confirm(question):
    if not stdin_is_terminal():
        raise PapersExit(f'{question} no terminal to confirm: -y/--yes removes without asking')
    return input(f'{question} [y/N] ').strip().lower() in ('y', 'yes')


def _show_all(config):
    for st in backup.all_stores(config):
        ids = st.project_ids()
        if not ids:
            continue
        sizes = st._sizes()
        refs = {}
        for id in ids:
            for state in st.project(id).states().values():
                for ref in papers.history._refs(state):
                    refs.setdefault(ref, set()).add(id)
        print(f'{papers.config.short_home(st.root)}: {_mb(st.size())}')
        projects = []
        for id in ids:
            heads = st.project(id).heads()
            last = max(heads.items(), key=lambda h: h[1].get('time', 0))[0] if heads else None
            projects.append((last, id))
        # by the bibtex of the place last used (the ids are random), those without place last
        for last, id in sorted(projects, key=lambda p: (p[0] is None, p[0] or '', p[1])):
            project = st.project(id)
            own = sum(sizes[r][1] for r, users in refs.items() if users == {id} and r in sizes)
            print(f'* {id}: {len(project.states())} steps, {_mb(own)} of its own'
                  + (f', last used at {papers.config.short_home(last)}' if last else ''))


def historycmd(parser, o, config):
    if o.cmd == 'backup':
        logger.warning('`papers backup` is deprecated: use `papers history`')
    if getattr(o, 'bibtex', None) is not None:  # a bibtex given (also without library), as for undo
        from papers.cli.common import check_install
        config = check_install(parser, o, config, bibtex_must_exist=False)
    if o.remove is not None:
        return remove_history(config, yes=o.yes, id=o.remove or None)
    if o.all:
        return _show_all(config)
    if o.drop_files:
        return drop_files(config, o.drop_files, yes=o.yes)
    if o.revert is not None:
        return revert(o, config)
    project, place = backup.project_of(config, create=False) if config.bibtex else (None, None)
    head = project.head(place) if project else None
    if head is None:
        print('no history yet: each command that changes the library records a step'
              if config.bibtex else 'no library: `papers history --all` lists the histories of the machine')
    else:
        line = project.line(head['state'])
        shown = line if not o.n else line[:o.n]
        def kept(n):
            size = backup.kept_size(project, n)
            return f'  [{_size(size)} of deleted files]' if size else ''
        for n in reversed(head['redo']):
            print(f'  {backup.describe(project, n)}  (undone: `papers redo`){kept(n)}')
        for n in shown:
            print(f'{">" if n == head["state"] else " "} {backup.describe(project, n)}{kept(n)}')
        if len(line) > len(shown):
            print(f'  ... {len(line) - len(shown)} older step(s) (-n 0 shows them all)')
    st = project.store if project else backup.store(config)
    size = backup.history_size(config, st)
    limit = f'up to {size} MB' if size else 'no limit'
    print(f'history: {papers.config.short_home(st.root)}, {_mb(st.size())} ({limit}: the history-size setting; '
          f'deleted files {"kept" if config.keep_deleted_files else "not kept: keep-deleted-files false"})')
    for path, size in backup.stale_backups(config):
        print(f'stale: {papers.config.short_home(path)} (backup of an earlier papers, {_mb(size)}, '
              f'no longer used) — delete with: rm -rf {papers.config.short_home(path)}')


def gitcmd(parser, o, config):
    raise PapersExit('`papers git` is removed: papers keeps the history of the libraries without git '
                     '(`papers history`); to keep a library under git, run git in its folder')
