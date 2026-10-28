"""The history of the libraries of a machine: a store of states, for undo,
redo and restore (see design/history.md).

The store is a folder of the machine (papers.config.HISTORY_DIR):

    objects/ab/ab12…          pieces of text, compressed (zlib), named by their sha256
    file-objects/ab/ab12….pdf the files deleted by the commands, named by their sha256
    projects/<id>/states/     one state per command, named by its identifier (see state_id), in a tree
    projects/<id>/heads.json  the current state of each place that uses the project
    numbers.json              the identifiers of the numbered states of earlier versions (see Store.upgrade)

A project is the history of a library, named by its identifier; a place is
where the library is (the real path of its bibtex): a copy of a library is
another place of the same project, whose states branch from the copy on.

A state is a dict: `parent` (the identifier of a state, or None), `time`, `message`,
`kind` ('command', 'outside': changed outside papers, 'start': the
library before its first recorded command), `bibtex` ({'pieces': [...],
'sha': ...}), `files` ({name: [pieces]}, the other text files of the
library), `ops` (the file operations of the command, see papers.journal)
and `deleted` (the file objects it refers to). The store only reads
`parent`, `time`, the pieces and `deleted`; the rest belongs to the caller.

This module uses the standard library only, and nothing else of papers.
"""
import hashlib
import json
import os
import re
import shutil
import time
import uuid
import zlib

# an object or a file object younger than this is not removed (a command
# writes its objects before its state)
GRACE = 3600

# the identifier of a state: the sha256 of these lines (see state_id); SHORT
# characters of it name the state in the messages, and any unique prefix of
# at least PREFIX characters is accepted (see Project.resolve)
STATE_VERSION = 'papers-state 1'
SHORT = 8
PREFIX = 4
_STATE_ID = re.compile(r'[0-9a-f]{64}')

# the bibtex is cut before each line that starts with @ (an entry), and the
# entries are grouped in pieces of about PIECE_ENTRIES: a piece ends after an
# entry whose checksum says so, so that adding or removing an entry changes
# the piece it is in only (the other pieces are those of the earlier states)
_ENTRY = re.compile(r'(?m)^(?=@)')
PIECE_ENTRIES = 32
PIECE_MAX = 256


def new_id():
    "the identifier of a new project"
    return uuid.uuid4().hex


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _write(path, data):
    "write bytes through a temporary file (a reader never sees half a file)"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f'{path}.{os.getpid()}.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)


def _read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


class Store:
    def __init__(self, root):
        self.root = root
        self.objects = os.path.join(root, 'objects')
        self.file_objects = os.path.join(root, 'file-objects')
        self.projects = os.path.join(root, 'projects')

    # pieces of text
    # ==============

    def _object(self, digest):
        return os.path.join(self.objects, digest[:2], digest)

    def put_text(self, text):
        "store a text by pieces; return the list of their checksums"
        pieces = []
        for piece in _pieces(text):
            data = piece.encode('utf-8')
            digest = sha256(data)
            path = self._object(digest)
            if os.path.exists(path):
                os.utime(path)  # recent again: not removed before the state that refers to it is written
            else:
                _write(path, zlib.compress(data))
            pieces.append(digest)
        return pieces

    def text(self, pieces):
        "the text of a list of pieces; raise KeyError for a missing piece"
        parts = []
        for digest in pieces:
            try:
                with open(self._object(digest), 'rb') as f:
                    parts.append(zlib.decompress(f.read()))
            except (OSError, zlib.error):
                raise KeyError(f'piece {digest} is missing from the history')
        return b''.join(parts).decode('utf-8')

    # files deleted by the commands
    # =============================

    def file_object(self, digest):
        "the stored file of this checksum, or None"
        if not digest:
            return None
        folder = os.path.join(self.file_objects, digest[:2])
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                if name.split('.', 1)[0] == digest:
                    return os.path.join(folder, name)
        return None

    def put_file(self, path, digest):
        "move a file into the store (named by its checksum `digest`); return its path in the store"
        found = self.file_object(digest)
        if found:
            os.remove(path)  # the store has this content already
            os.utime(found)
            return found
        target = os.path.join(self.file_objects, digest[:2], digest + os.path.splitext(path)[1])
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.move(path, target)
        os.utime(target)
        return target

    # projects
    # ========

    def project(self, id):
        return Project(self, id)

    def project_ids(self):
        if not os.path.isdir(self.projects):
            return []
        return sorted(name for name in os.listdir(self.projects)
                      if os.path.isdir(os.path.join(self.projects, name)))

    def upgrade(self):
        """the states of papers up to 3.0.0b5, numbered (000001.json, ...):
        named by their identifier (see state_id), and the references to them
        rewritten (parent, the current state and the redo list of each
        place, reverts, and the steps of the pools that a step links to, in
        other projects). All projects at once (a step names the steps of its
        pools); the result does not depend on who does it, so two commands
        doing it at the same time agree. The numbers and their identifiers
        are kept in numbers.json: a link from another store (history-separate)
        names a pool's state by its number (see Project.upgraded)."""
        numbered, maps = {}, {}
        for id in self.project_ids():
            folder = os.path.join(self.projects, id, 'states')
            names = [n for n in os.listdir(folder) if n.endswith('.json') and n[:-5].isdigit()] \
                if os.path.isdir(folder) else []
            if names:
                numbered[id] = {int(n[:-5]): _read_json(os.path.join(folder, n)) for n in names}
        if not numbered:
            return
        for id, states in numbered.items():
            maps[id] = {}
            for n in sorted(states):  # a parent has a smaller number than its states
                state = states[n]
                if not isinstance(state, dict):
                    continue
                state['parent'] = maps[id].get(state.get('parent'))
                if state.get('reverts'):
                    state['reverts'] = [maps[id][r] for r in state['reverts'] if r in maps[id]]
                maps[id][n] = state_id(state)
        known = self.numbers()
        for id, ids in maps.items():
            known.setdefault(id, {}).update({str(n): i for n, i in ids.items()})
        _write(os.path.join(self.root, 'numbers.json'), json.dumps(known, indent=1).encode())
        for id, states in numbered.items():
            project = self.project(id)
            for n, state in states.items():
                if not isinstance(state, dict):
                    continue
                links = {}
                for pool, link in (state.get('pools') or {}).items():
                    target = maps.get(pool, {}).get(link.get('state'), link.get('state'))
                    links[pool] = dict(link, state=target)
                if links:
                    state['pools'] = links
                _write(project._path(maps[id][n]), json.dumps(state, indent=1).encode())
            heads = _read_json(os.path.join(project.dir, 'heads.json'), {})  # as written (not through states())
            heads = heads if isinstance(heads, dict) else {}
            for head in heads.values():
                head['state'] = maps[id].get(head.get('state'), head.get('state'))
                head['redo'] = [maps[id].get(r, r) for r in head.get('redo') or []]
            _write(os.path.join(project.dir, 'heads.json'), json.dumps(heads, indent=1).encode())
            for n in states:
                try:
                    os.remove(os.path.join(project.states_dir, f'{n:06d}.json'))
                except FileNotFoundError:
                    pass

    def numbers(self):
        "{project id: {number: identifier}} of the numbered states upgraded (see upgrade)"
        known = _read_json(os.path.join(self.root, 'numbers.json'), {})
        return known if isinstance(known, dict) else {}

    # size and retention
    # ==================

    def _sizes(self):
        "{('piece' | 'file', digest): (path, size, mtime)} of everything stored"
        found = {}
        for kind, root in (('piece', self.objects), ('file', self.file_objects)):
            if not os.path.isdir(root):
                continue
            for sub in os.scandir(root):
                if not sub.is_dir():
                    continue
                for entry in os.scandir(sub.path):
                    if entry.name.endswith('.tmp'):
                        continue
                    st = entry.stat()
                    found[(kind, entry.name.split('.', 1)[0])] = (entry.path, st.st_size, st.st_mtime)
        return found

    def size(self):
        "bytes stored (pieces and files)"
        return sum(size for _, size, _ in self._sizes().values())

    def prune(self, limit, extra=0, dry=False, discard=os.remove, now=None):
        """drop the oldest states of all projects until the store holds no
        more than `limit` bytes (counting `extra` bytes about to be stored),
        then remove the pieces and files that no state refers to (not those
        younger than GRACE). The current states of the places are kept.
        A removed file goes through `discard` (e.g. the system trash).
        dry: change nothing. Return the dropped states: [(project id, number, state)]."""
        now = time.time() if now is None else now
        sizes = self._sizes()
        refs = {}
        states = []
        for id in self.project_ids():
            project = self.project(id)
            heads = {h['state'] for h in project.heads().values()}
            for n, state in project.states().items():
                for ref in _refs(state):
                    refs[ref] = refs.get(ref, 0) + 1
                if n not in heads:
                    states.append((state.get('time', 0), id, n, state))
        states.sort(key=lambda s: (s[0], s[2]))

        def removable(ref):
            item = sizes.get(ref)
            return item is not None and refs.get(ref, 0) == 0 and now - item[2] >= GRACE

        total = sum(size for _, size, _ in sizes.values()) + extra
        freed = {ref for ref in sizes if removable(ref)}
        total -= sum(sizes[ref][1] for ref in freed)
        dropped = []
        for _, id, n, state in states:
            if not limit or total <= limit:
                break
            dropped.append((id, n, state))
            for ref in _refs(state):
                refs[ref] -= 1
                if ref not in freed and removable(ref):
                    freed.add(ref)
                    total -= sizes[ref][1]
        if dry:
            return dropped
        for id, n, _ in dropped:
            self.project(id).drop(n)
        for ref in freed:
            path = sizes[ref][0]
            try:
                discard(path) if ref[0] == 'file' else os.remove(path)
            except OSError:
                pass
        return dropped


def state_id(state):
    """the identifier of a state: what the state is (its parent, its time to
    the microsecond, the checksum of its bibtex, the pieces of the other
    files), and nothing that a later command may change (the file
    operations, the deleted files, the labels)"""
    lines = [STATE_VERSION, f'parent {state.get("parent") or "-"}', f'time {float(state.get("time") or 0):.6f}',
             f'bibtex {(state.get("bibtex") or {}).get("sha", "")}']
    for name, digests in sorted((state.get('files') or {}).items()):
        lines.append(f'file {name} {",".join(digests)}')
    return sha256(('\n'.join(lines) + '\n').encode('utf-8'))


def short(n):
    "the identifier of a state as the messages show it"
    return n[:SHORT] if isinstance(n, str) else n


def pieces(text):
    "{checksum: piece} of a text cut as the store cuts it (see put_text), nothing stored"
    return {sha256(p.encode('utf-8')): p for p in _pieces(text)}


def _pieces(text):
    "the text cut in pieces of about PIECE_ENTRIES entries (see _ENTRY)"
    piece, count = [], 0
    for entry in _ENTRY.split(text):
        if not entry:
            continue
        piece.append(entry)
        count += 1
        if count >= PIECE_MAX or zlib.crc32(entry.encode('utf-8')) % PIECE_ENTRIES == 0:
            yield ''.join(piece)
            piece, count = [], 0
    if piece:
        yield ''.join(piece)


def _refs(state):
    "the pieces and files a state refers to"
    refs = [('piece', d) for d in (state.get('bibtex') or {}).get('pieces', [])]
    for pieces in (state.get('files') or {}).values():
        refs.extend(('piece', d) for d in pieces)
    refs.extend(('file', d) for d in state.get('deleted') or [])
    return refs


class Project:
    def __init__(self, store, id):
        if not re.fullmatch(r'[0-9A-Za-z_-]+', id or ''):
            raise ValueError(f'invalid identifier of a library: {id!r}')
        self.store = store
        self.id = id
        self.dir = os.path.join(store.projects, id)
        self.states_dir = os.path.join(self.dir, 'states')
        self._states = None

    def exists(self):
        return os.path.isdir(self.dir)

    # states
    # ======

    def states(self):
        "{identifier: state}"
        if self._states is None:
            self._states = {}
            if os.path.isdir(self.states_dir):
                names = os.listdir(self.states_dir)
                if any(name.endswith('.json') and name[:-5].isdigit() for name in names):
                    self.store.upgrade()  # numbered states of an earlier version
                    names = os.listdir(self.states_dir)
                for name in names:
                    if name.endswith('.json') and _STATE_ID.fullmatch(name[:-5]):
                        state = _read_json(os.path.join(self.states_dir, name))
                        if isinstance(state, dict):
                            self._states[name[:-5]] = state
        return self._states

    def state(self, n):
        return self.states().get(n)

    def upgraded(self, n):
        """the identifier of the state that an earlier version numbered n (a
        link from a state of another store, see Store.upgrade); else n"""
        if not isinstance(n, int) or isinstance(n, bool):
            return n
        self.states()  # numbered states upgraded first
        return self.store.numbers().get(self.id, {}).get(str(n), n)

    def resolve(self, ref):
        """the identifier of the state that `ref` names: the identifier, or a
        unique prefix of at least PREFIX characters; None if no state has it;
        ValueError if several have it (the message lists them)"""
        ref = str(ref).strip().lower()
        if ref in self.states():
            return ref
        if len(ref) < PREFIX or not re.fullmatch(r'[0-9a-f]+', ref):
            return None
        found = sorted(n for n in self.states() if n.startswith(ref))
        if len(found) > 1:
            raise ValueError(f'{ref} names several steps: {", ".join(short(n) for n in found)}')
        return found[0] if found else None

    def _path(self, n):
        return os.path.join(self.states_dir, f'{n}.json')

    def add(self, state):
        "write a new state; return its identifier (see state_id)"
        os.makedirs(self.states_dir, exist_ok=True)
        n = state_id(state)
        try:
            fd = os.open(self._path(n), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:  # the same state (parent, time, content): written already
            pass
        else:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(state, f, indent=1)
        self.states()[n] = state
        return n

    def update(self, n, state):
        "rewrite the state n (e.g. the file operations done after its save)"
        _write(self._path(n), json.dumps(state, indent=1).encode())
        self.states()[n] = state

    def drop(self, n):
        try:
            os.remove(self._path(n))
        except FileNotFoundError:
            pass
        self.states().pop(n, None)

    def line(self, n):
        "the states from n back to the oldest one kept: [n, parent, …]"
        line = []
        while n is not None and n in self.states() and n not in line:
            line.append(n)
            n = self.states()[n].get('parent')
        return line

    def path(self, a, b):
        """from the state a to the state b: the states left going back (a
        first, down to before the common ancestor) and the states entered
        going forward (b last)"""
        up = self.line(a)
        down = self.line(b)
        common = next((n for n in up if n in set(down)), None)
        back = up[:up.index(common)] if common is not None else up
        forward = down[:down.index(common)] if common is not None else down
        return back, list(reversed(forward))

    # places
    # ======

    def heads(self):
        "{place: {'state': n, 'redo': [n, …]}}"
        self.states()  # the states of an earlier version are named by their identifier first (see Store.upgrade)
        heads = _read_json(os.path.join(self.dir, 'heads.json'), {})
        return heads if isinstance(heads, dict) else {}

    def head(self, place):
        "{'state': n, 'redo': [...]} of a place, or None"
        head = self.heads().get(place)
        if head and head.get('state') in self.states():
            head['redo'] = [n for n in head.get('redo') or [] if n in self.states()]
            return head
        return None

    def set_head(self, place, n, redo=()):
        heads = self.heads()
        heads[place] = {'state': n, 'redo': list(redo), 'time': time.time()}
        _write(os.path.join(self.dir, 'heads.json'), json.dumps(heads, indent=1).encode())

    def remove_head(self, place):
        "forget a place; return the number of places left"
        heads = self.heads()
        heads.pop(place, None)
        _write(os.path.join(self.dir, 'heads.json'), json.dumps(heads, indent=1).encode())
        return len(heads)

    def forget_missing_places(self, exists=os.path.exists):
        "forget the places that no longer exist (a library moved or deleted)"
        heads = self.heads()
        gone = [place for place in heads if not exists(place)]
        for place in gone:
            heads.pop(place)
        if gone:
            _write(os.path.join(self.dir, 'heads.json'), json.dumps(heads, indent=1).encode())
        return gone

    def start_state(self, sha):
        """the state a new place starts from: the most recent one whose
        bibtex has this checksum, or else the most recent one (None if
        there is none)"""
        states = self.states()
        if not states:
            return None
        same = [n for n, s in states.items() if (s.get('bibtex') or {}).get('sha') == sha]
        pool = same or list(states)
        return max(pool, key=lambda n: (states[n].get('time', 0), n))

    def remove(self):
        "delete the history of the project (the pieces and files go at the next prune)"
        shutil.rmtree(self.dir, ignore_errors=True)
        self._states = {}
