"""papers history --revert N: take back the changes of step N of the
history of a library alone, as a new step (see docs/undo-redo.md).

Step N goes from the state of its parent P to the state N. For each entry
that step N changed (matched by key, or by a former key of the ids field
for a key that step N changed), the three versions are compared: the entry
at P, at N, and now.

- added by N: removed, unless it changed since (kept, with a line);
- removed by N: added back as it was at P, unless its key is taken (a line);
- modified by N: a three-way merge, as pull does (papers.merge): base the
  entry at N, other side the entry at P, target the entry now. A field that
  N changed and that did not change since goes back to its value at P; a
  field changed since N too is a conflict, decided as in pull
  (--on-duplicate). The key goes back to that of P if N changed it and it
  did not change since. The file links and the tags (keywords) are taken
  one by one: those added by N are removed, those removed by N come back.
  The tags added since stay, without conflict.

Then the files go back as undo moves them (papers.journal.restore), with
the file operations of step N only. The pairs of distinct.json that N
added are removed, those it removed come back. The origin records are left
as they are: the next pull or push compares with them.
"""
import json
import os

from bibtexparser import parse_string

import papers.config
from papers import backup, journal
from papers.history import short
from papers.duplicate import DISTINCT_FILE, Verdict, SAME
from papers.encoding import parse_keywords
from papers.entries import entry_content_equal, get_entry_val, entry_copy
from papers.merge import Merge, apply_entry
from papers.utils import PapersExit


def _state_entries(project, n):
    "the entries of the bibtex of the state n"
    try:
        return parse_string(project.store.text(project.state(n)['bibtex']['pieces'])).entries
    except KeyError as error:
        raise PapersExit(f'the history of the library is damaged: {error}')


def _distinct_pairs(project, n):
    "the pairs of distinct.json of the state n"
    pieces = backup.state_files(project.state(n)).get(DISTINCT_FILE)
    if not pieces:
        return []
    try:
        return [p for p in json.loads(project.store.text(pieces)).get('distinct', [])
                if isinstance(p, list) and len(p) == 2]
    except (KeyError, ValueError):
        return []


def _ids(e):
    return [i.strip().lower() for i in get_entry_val(e, 'ids', '').split(',') if i.strip()]


def changes(before, after):
    """the entries that a step changed: [(entry before, entry after)], None
    for an entry added or removed; an entry whose key the step changed is
    matched by the ids field of the entry after (papers keeps former keys there)"""
    old = {e.key.lower(): e for e in before}
    new = {e.key.lower(): e for e in after}
    pairs, seen = [], set()
    for key, e in new.items():
        if key in old:
            p = old[key]
        else:
            p = next((old[k] for k in _ids(e) if k in old and k not in new), None)
        if p is not None:
            seen.add(p.key.lower())
            if not entry_content_equal(p, e):
                pairs.append((p, e))
        else:
            pairs.append((None, e))
    pairs += [(p, None) for key, p in old.items() if key not in seen]
    return pairs


def _current(biblio, e):
    "the entry of the library now for the entry `e` of a state: same key, or e's key among its former keys"
    key = e.key.lower()
    found = next((x for x in biblio.entries if x.key.lower() == key), None)
    return found or next((x for x in biblio.entries if key in _ids(x)), None)


def _revert_links(biblio, now, before, after, libdir):
    """the file links of `now` (absolute paths) without those that step N
    added, with those it removed; before, after: entries of states, whose
    links are relative to the folder of the bibtex (libdir)"""
    real = lambda files: {os.path.realpath(f) for f in files}
    old, new = biblio.get_files(before, relative_to=libdir), biblio.get_files(after, relative_to=libdir)
    added = real(new) - real(old)
    files = [f for f in biblio.get_files(now) if os.path.realpath(f) not in added]
    return files + [f for f in old if os.path.realpath(f) not in real(new) | real(files)]


def _revert_tags(now, before, after):
    "the tags of `now` without those that step N added, with those it removed (case-insensitive)"
    lower = lambda tags: {t.lower() for t in tags}
    old, new = parse_keywords(before), parse_keywords(after)
    tags = [t for t in parse_keywords(now) if t.lower() not in lower(new) - lower(old)]
    return tags + [t for t in old if t.lower() not in lower(new) | lower(tags)]


def _without_tags(e):
    "a copy of the entry without its tags (merged one by one, see _revert_tags)"
    e = entry_copy(e)
    if 'keywords' in e.fields_dict:
        del e['keywords']
    return e


def revert(config, biblio, n, resolver, forward=False, anywhere=False, parent=None):
    """take back step n in `biblio` (the library, loaded): the entries, the
    files and distinct.json; not saved. forward: do step n again instead
    (the same rules, from the state of step n to its parent swapped: redo
    in a pool that changed since the undo of its step). anywhere: step n
    need not be in the current history (a pool, whose step n was undone or
    done again by another step). parent: the state that step n is
    compared with, instead of its parent (a pool saved several times by
    one command: its state before the first save). Return the lines of the report (the
    entries left as they are and why, the files)."""
    project, place = backup.project_of(config)
    head = backup.sync_head(config, project, place) if not papers.config.DRYRUN else \
        (project.head(place) or {}).get('state')
    n = backup.resolve(project, n)
    state = project.state(n)
    if not anywhere and (head is None or n not in project.line(head)):
        raise PapersExit(f'step {short(n)} is not in the current history of the library: '
                         f'`papers restore {short(n)}` goes there')
    parent = parent if parent is not None else state.get('parent')
    if parent is None or project.state(parent) is None:
        raise PapersExit(f'step {short(n)} is the first step of the history: nothing before it to go back to')
    before, after = _state_entries(project, parent), _state_entries(project, n)
    # what step n did, as the lines say it (done again: an entry added by n is taken as removed, and so on)
    added, removed = ('removed', 'added') if forward else ('added', 'removed')
    if forward:
        before, after = after, before
    libdir = os.path.dirname(os.path.abspath(config.bibtex))
    links = lambda: {os.path.normpath(f) for x in biblio.entries for f in biblio.get_files(x)}
    current_links = links()
    lines = []
    for p, e in changes(before, after):
        if p is None:  # added by N
            now = _current(biblio, e)
            if now is None:
                continue
            if entry_content_equal(now, e, skip_keys=('file',)):
                biblio.db.remove(now)
            else:
                lines.append(f'{now.key}: {added} by step {short(n)} and changed since: kept (`papers rm {now.key}` '
                             'removes it)')
        elif e is None:  # removed by N
            now = _current(biblio, p)
            if now is not None:  # back already, or another entry has its key now
                if not entry_content_equal(now, p, skip_keys=('file',)):
                    lines.append(f'{p.key}: {removed} by step {short(n)}; the entry {now.key} has its key now: '
                                 'not added')
                continue
            back = entry_copy(p)
            files = biblio.get_files(p, relative_to=libdir)
            biblio.db.add(back)
            biblio.set_files(back, files)
        else:
            now = _current(biblio, e)
            if now is None:
                lines.append(f'{e.key}: changed by step {short(n)} and removed since: not added')
                continue
            merge = Merge([_without_tags(now), _without_tags(p)], relative_to=biblio.relative_to,
                          exchange=True, base=_without_tags(e))
            if merge.conflicts:
                decision = resolver.decide(merge, 'revert', Verdict(SAME, f'step {short(n)}'))
                if decision.kind != 'merge':
                    lines.append(f'{now.key}: changed since step {short(n)} too: left as it is')
                    continue
                new = decision.entry
            else:
                new = merge.result()
            files, tags = _revert_links(biblio, now, p, e, libdir), _revert_tags(now, p, e)
            apply_entry(now, new)
            biblio.set_files(now, files)
            if tags:
                now['keywords'] = ', '.join(tags)
            elif 'keywords' in now.fields_dict:
                del now['keywords']
            if p.key != e.key and now.key == e.key:
                if any(x is not now and x.key.lower() == p.key.lower() for x in biblio.entries):
                    lines.append(f'{now.key}: renamed by step {short(n)} (key {p.key} before), now another entry\'s key: '
                                 'the key stays')
                else:
                    biblio.set_key(now, p.key)
                    ids = [i for i in get_entry_val(now, 'ids', '').split(',')
                           if i.strip() and i.strip().lower() != p.key.lower()]
                    if ids:
                        now['ids'] = ', '.join(i.strip() for i in ids)
                    elif 'ids' in now.fields_dict:
                        del now['ids']
    pairs = _distinct_pairs(project, parent), _distinct_pairs(project, n)
    _revert_distinct(biblio, *(reversed(pairs) if forward else pairs))
    if papers.config.DRYRUN:
        return lines
    ops = backup._absolute_ops(state.get('ops') or [], config)
    hashes = backup.state_hashes(config, project, n if forward else parent)
    lines += journal.restore(current_links, links(), ops, not forward, hashes=hashes,
                             pool_dirs=backup._pool_dirs(config), find_deleted=project.store.file_object)
    return lines


def _revert_distinct(biblio, before, after):
    "the pairs that step N added to distinct.json are removed, those it removed come back"
    same = lambda a, b: a == b or [a[1], a[0]] == b
    added = [p for p in after if not any(same(p, q) for q in before)]
    removed = [p for p in before if not any(same(p, q) for q in after)]
    distinct = biblio.distinct
    kept = [p for p in distinct.pairs if not any(same(p, q) for q in added)]
    kept += [p for p in removed if not any(same(p, q) for q in kept)]
    if kept != distinct.pairs:
        distinct.pairs = kept
        distinct.changed = True


def pool_lines(config, project, n):
    "the lines of the pools that step n also changed: the command that takes back their step"
    lines = []
    for id, link in (project.state(n).get('pools') or {}).items():
        file = link.get('config')
        if not file or not os.path.isfile(file):
            continue
        pool_config = papers.config.Config.load(file, machine=config.machine)
        shown = backup._shown(config, pool_config)
        state = link['state']
        if isinstance(state, int):  # a link of an earlier version to another store (see history.Store.upgrade)
            pool_project, _ = backup.project_of(pool_config, create=False)
            state = pool_project.upgraded(state) if pool_project else state
        lines.append(f'step {short(n)} also changed pool {shown} (its step {short(state)}): '
                     f'`papers -C {shown} history --revert {short(state)}` takes it back there')
    return lines
