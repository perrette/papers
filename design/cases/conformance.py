"""Shared by record.py and run.py: the case format, the sandbox, the normalization.

Python standard library only. See README.md for the format.
"""
import difflib
import fnmatch
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = HERE                     # the groups of cases are the folders next to this file

EMPTY_DIR = '.emptydir'          # marker file of an empty directory in a stored tree
STORED = {'.gitignore': '.gitignore.spec'}   # files git would act on, stored under another name
TIMEOUT = 120

# a section of the specification: <file>.md#<number> (formats, bibtex, exchange, history: "7", "7.2")
# or <file>.md#<slug>[/<slug>] (library.md, which has no numbers)
SECTION_REF = re.compile(r'^(library|bibtex|formats|exchange|history)\.md#[a-z0-9][a-z0-9./-]*$')
# a test of papers-cli, as design/tests.md lists it
TEST_REF = re.compile(r'^tests/[A-Za-z0-9_]+\.py(::[A-Za-z0-9_]+)*$')

# a time in brackets, alone or before more (`(2026-10-28 16:49, from $WORK/lib)`)
TIME_IN_TEXT = re.compile(r'\(\d{4}-\d\d-\d\d \d\d:\d\d(?=[),])')
TIME_IN_JSON = re.compile(r'("time":\s*)[0-9.eE+-]+')
LIBRARY_ID = re.compile(r'("id":\s*)"[0-9a-f]{32}"')
ORIGIN_TIME = re.compile(r'papers-time = \{[^}]*\}')
ORIGIN_PULLED = re.compile(r'papers-pulled \d+')
PLACEHOLDERS = ('$WORK', '$HOME', '$CONFIG', '$DATA', '$CACHE')

# the identifier of a state of the history is a sha256 that depends on its time (history.md#2.5)
STATE_ID = re.compile(r'(?<![0-9a-zA-Z])[0-9a-f]{64}(?![0-9a-zA-Z])')
STATE_SHORT = re.compile(r'(?<![0-9a-zA-Z])[0-9a-f]{8}(?![0-9a-zA-Z])')   # what papers history shows
STATE_FILE = re.compile(r'(?:^|/)projects/[^/]+/states/([0-9a-f]{64})\.json$')
STATE_PLACEHOLDER = re.compile(r'\$STATE(\d+)(?::(\d+))?')            # $STATE2, $STATE2:4 (4 characters)


# platform directories (what platformdirs gives papers-cli)
# ===========================================================

def platform_dirs(home):
    "{'config', 'data', 'cache'}: the papers directories of the user, for HOME=home"
    if sys.platform == 'darwin':
        support = os.path.join(home, 'Library', 'Application Support', 'papers')
        return {'config': support, 'data': support,
                'cache': os.path.join(home, 'Library', 'Caches', 'papers')}
    if sys.platform.startswith('linux'):
        return {'config': os.path.join(home, '.config', 'papers'),
                'data': os.path.join(home, '.local', 'share', 'papers'),
                'cache': os.path.join(home, '.cache', 'papers')}
    raise SystemExit(f'unsupported platform: {sys.platform}')


# cases
# =====

class Case:
    def __init__(self, path):
        self.path = path
        self.name = os.path.relpath(path, CASES).replace(os.sep, '/')
        with open(os.path.join(path, 'case.json'), encoding='utf-8') as f:
            spec = json.load(f)
        self.description = spec.get('description', '')
        self.sections = spec.get('sections', [])
        self.tests = spec.get('tests', [])
        self.ignore = spec.get('ignore', [])
        self.requires = spec.get('requires', [])
        self.steps = spec['steps']
        for ref in self.sections:
            if not SECTION_REF.match(ref):
                raise SystemExit(f'{self.name}: {ref}: not a section reference (see README.md, "Sections")')
        if not self.sections:
            raise SystemExit(f'{self.name}: case.json has no "sections"')
        for ref in self.tests:
            if not TEST_REF.match(ref):
                raise SystemExit(f'{self.name}: {ref}: not a test of design/tests.md (tests/FILE.py::Class::test)')
        for step in self.steps:
            bad = set(step.get('contract', [])) - {'stdout', 'stderr'}
            if bad:
                raise SystemExit(f'{self.name}: "contract" of a step: stdout and stderr only, not {sorted(bad)}')
        self.before = os.path.join(path, 'before')
        self.before_home = os.path.join(path, 'before-home')
        self.expected = os.path.join(path, 'expected')


# Contract and Free outputs of a step
# ====================================
# Exit codes and every file written are Contract. What a step prints is Free (messages), except:
#   - with --porcelain: the standard output (the porcelain lines, formats.md#7)
#   - `list` with --format key|bibtex|ris|csl-json|bibjson, --plain, -K, --key-only, --field: the standard output
#     (formats.md#6). The default line format (-l, -1, --format line) is human output: Free.
# A step can say otherwise: "contract": ["stdout", "stderr"] (any subset, [] for none) replaces the default.

LIST_CONTRACT_FORMATS = {'key', 'bibtex', 'ris', 'csl-json', 'bibjson'}
LIST_CONTRACT_FLAGS = {'--plain', '-K', '--key-only', '--field', '-f'}


def command_args(argv):
    "the arguments after the global options (-C DIR): the command name first"
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '-C':
            i += 2
        elif a.startswith('-'):
            i += 1
        else:
            break
    return argv[i:]


def default_contract(argv):
    "the streams of a step that are Contract by default: a subset of {'stdout', 'stderr'}"
    args = command_args(argv)
    if '--porcelain' in args:
        return {'stdout'}
    if args and args[0] == 'list':
        fmt = None
        for i, a in enumerate(args):
            if a == '--format' and i + 1 < len(args):
                fmt = args[i + 1]
            elif a.startswith('--format='):
                fmt = a[len('--format='):]
        if fmt in LIST_CONTRACT_FORMATS or LIST_CONTRACT_FLAGS & set(args):
            return {'stdout'}
    return set()


# Keys of JSON files that are Free (the file is Contract, the key is not).
FREE_JSON_KEYS = [('home/data/history/projects/*/states/*.json', ('message',))]   # history.md#3.2


def section_matches(ref, pattern):
    "a section reference matches a pattern: a glob, or a section above it (formats.md#7 matches formats.md#7.2)"
    return fnmatch.fnmatch(ref, pattern) or ref.startswith(pattern + '.') or ref.startswith(pattern + '/')


def step_contract(case, n):
    "the streams of step n that are Contract: the step's own \"contract\", else the default rules"
    step = case.steps[n]
    if 'contract' in step:
        return set(step['contract'])
    return default_contract(step['argv'])


def find_cases(selectors=(), sections=(), tests=()):
    "the cases (the folders next to this file) whose name (group/name) matches one of the glob selectors (all by default), that exercise\n    a section or list a test of the specification (a glob, or a part of the test id)"
    found = []
    for root, dirs, files in os.walk(CASES):
        dirs.sort()
        if 'case.json' in files:
            dirs[:] = []
            found.append(Case(root))
    found.sort(key=lambda c: c.name)
    if selectors:
        found = [c for c in found
                 if any(fnmatch.fnmatch(c.name, s) or c.name.startswith(s.rstrip('/') + '/') for s in selectors)]
    if sections:
        found = [c for c in found if any(section_matches(ref, pat) for ref in c.sections for pat in sections)]
    if tests:
        found = [c for c in found if any(fnmatch.fnmatch(t, pat) or pat in t for t in c.tests for pat in tests)]
    return found


# trees
# =====

def _read_tree(root):
    "{path: bytes} of the files under root ('/' separators); an empty directory is its EMPTY_DIR marker"
    tree = {}
    if not os.path.isdir(root):
        return tree
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        rel = os.path.relpath(dirpath, root)
        rel = '' if rel == '.' else rel.replace(os.sep, '/') + '/'
        if not dirnames and not filenames and rel:
            tree[rel + EMPTY_DIR] = b''
        for name in filenames:
            if name == '.DS_Store':
                continue
            with open(os.path.join(dirpath, name), 'rb') as f:
                tree[rel + name] = f.read()
    return tree


def _stored_name(path):
    head, _, name = path.rpartition('/')
    name = STORED.get(name, name)
    return head + '/' + name if head else name


def _logical_name(path):
    head, _, name = path.rpartition('/')
    name = {v: k for k, v in STORED.items()}.get(name, name)
    return head + '/' + name if head else name


def _write_tree(root, tree, stored=True):
    "write {path: bytes} under root; the markers make empty directories"
    os.makedirs(root, exist_ok=True)
    for path, data in sorted(tree.items()):
        target = os.path.join(root, *(_stored_name(path) if stored else path).split('/'))
        if path.rsplit('/', 1)[-1] == EMPTY_DIR:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if stored:
                with open(target, 'wb') as f:   # the marker is kept: git cannot track a directory
                    pass
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'wb') as f:
            f.write(data)


def _load_stored(root):
    "the logical tree of a stored tree (before/, expected/work/...)"
    return {_logical_name(p): d for p, d in _read_tree(root).items()}


def _remove_dir_contents(path):
    if os.path.isdir(path):
        shutil.rmtree(path)


# the sandbox
# ===========

class Sandbox:
    """a temporary directory with `work/` (the case's before/) and `home/` (HOME of the run)"""

    def __init__(self, case, keep=False):
        self.case = case
        self.keep = keep
        self.tmp = tempfile.mkdtemp(prefix='papers-cases-')
        self.root = os.path.realpath(self.tmp)
        self.work = os.path.join(self.root, 'work')
        self.home = os.path.join(self.root, 'home')
        self.dirs = platform_dirs(self.home)
        self.version = None
        os.makedirs(self.work)
        os.makedirs(self.home)
        self._subs = self._build_subs()
        self.projects = {}
        self.t0 = time.time()      # the states of the run are younger than this; those of before-home are not
        self.seen = {}             # id -> time of the states the run has written, also those the history dropped since
        self.states = {}           # id of a state of the run -> $STATEn (after the run)
        self.named = {}            # text given for a $STATEn in an argument -> that placeholder as written
        self.hashes = {}           # first 6 digits of the sha1 of a library identifier -> $PROJECTn

    def close(self):
        if not self.keep:
            shutil.rmtree(self.tmp, ignore_errors=True)

    # placeholders
    # ------------

    def _build_subs(self):
        d = self.dirs
        pairs = []   # (needle, placeholder), the first wins for equal needles
        named = [(os.path.join(d['data'], 'history'), '$DATA/history'),
                 (d['config'], '$CONFIG'), (d['data'], '$DATA'), (d['cache'], '$CACHE'),
                 (self.work, '$WORK'), (self.home, '$HOME')]
        for path, ph in named:
            pairs.append((path, ph))
            if path.startswith(self.home + os.sep):   # as papers shows it
                pairs.append(('~' + path[len(self.home):], ph))
        # the working folder written without its leading slash, as Mendeley writes file links
        pairs.append((self.work.lstrip(os.sep), '$NOSLASH_WORK'))
        pairs.append((self.root, '$TMP'))
        # the same with the unresolved name of the temporary directory
        if self.tmp != self.root:
            for needle, ph in list(pairs):
                if needle.startswith(self.root):
                    pairs.append((self.tmp + needle[len(self.root):], ph))
        subs = {}
        for needle, ph in pairs:
            subs.setdefault(needle, ph)
        return sorted(subs.items(), key=lambda kv: -len(kv[0]))

    def normalize(self, text):
        for needle, ph in self._subs:
            text = text.replace(needle, ph)
        if self.version:
            text = text.replace(self.version, '$VERSION')
        return text

    def expand(self, text):
        "the placeholders of a case file or argument, as paths of this sandbox"
        d = self.dirs
        for ph, path in (('$NOSLASH_WORK', self.work.lstrip(os.sep)), ('$WORK', self.work), ('$HOME', self.home), ('$CONFIG', d['config']),
                         ('$DATA', d['data']), ('$CACHE', d['cache'])):
            text = text.replace(ph, path)
        return STATE_PLACEHOLDER.sub(self._state_text, text)

    def see_states(self):
        "note the states the run has written so far (not those of before-home): one the history drops is kept in `seen`"
        for dirpath, dirnames, filenames in os.walk(self.home):
            if os.path.basename(dirpath) != 'states':
                continue
            for name in filenames:
                m = STATE_FILE.search(os.path.relpath(os.path.join(dirpath, name), self.home).replace(os.sep, '/'))
                if not m or m.group(1) in self.seen:
                    continue
                try:
                    with open(os.path.join(dirpath, name), encoding='utf-8') as f:
                        when = json.load(f)['time']
                except (OSError, ValueError, KeyError, TypeError):
                    continue
                if isinstance(when, (int, float)) and when >= self.t0:
                    self.seen[m.group(1)] = when

    def _recent_states(self):
        "[(time, id)] of the states the run has written, oldest first: the number of a state is its place here"
        self.see_states()
        return sorted((when, i) for i, when in self.seen.items())

    def _state_text(self, m):
        "$STATEn of a step: the identifier (8 characters, or $STATEn:K: K) of the n-th state the run has written so far"
        n, size = int(m.group(1)), int(m.group(2) or 8)
        states = self._recent_states()
        if not 1 <= n <= len(states):
            return m.group(0)
        text = states[n - 1][1][:size]
        self.named[text] = m.group(0)
        return text

    def _rename(self, text):
        "the machine-specific names of the library identifiers and states of the run replaced by placeholders"
        for pid, name in self.projects.items():
            text = text.replace(pid, name)
        for h, name in self.hashes.items():
            text = text.replace(f'-{h}.bib', f'-{name}.bib')
        text = STATE_ID.sub(lambda m: self.states.get(m.group(0), m.group(0)), text)
        short = {i[:8]: ph for i, ph in self.states.items()}
        text = STATE_SHORT.sub(lambda m: short.get(m.group(0), m.group(0)), text)
        for given, ph in self.named.items():
            text = re.sub(rf'(?<![0-9a-zA-Z]){given}(?![0-9a-zA-Z])', lambda m, ph=ph: ph, text)
        return text

    def _normalize_bytes(self, data, time_json=False, path='', origin=False):
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            return data
        text = self._rename(self.normalize(text))
        if time_json:
            text = TIME_IN_JSON.sub(r'\1"$TIME"', text)
        if path.endswith('.papers/config.json'):   # the id of a library no history step has named (export)
            text = LIBRARY_ID.sub(r'\1"$ID"', text)
        if origin or '.papers/origin/' in path:   # origin records: the times of the exchanges
            text = ORIGIN_TIME.sub('papers-time = {$TIME}', ORIGIN_PULLED.sub('papers-pulled $MTIME', text))
        return text.encode('utf-8')

    def _expand_bytes(self, data):
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            return data
        return self.expand(text).encode('utf-8')

    # before
    # ------

    def populate(self):
        "write before/ to work/ and before-home/ to home/"
        tree = {p: self._expand_bytes(d) for p, d in _load_stored(self.case.before).items()}
        _write_tree(self.work, tree, stored=False)
        d = self.dirs
        roots = {'config': d['config'], 'data': d['data'], 'home': self.home}
        for path, data in _load_stored(self.case.before_home).items():
            top, _, rest = path.partition('/')
            if top not in roots:
                raise SystemExit(f'{self.case.name}: before-home/{path}: the top folders are config, data and home')
            target = os.path.join(roots[top], *rest.split('/'))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if rest.rsplit('/', 1)[-1] != EMPTY_DIR:
                with open(target, 'wb') as f:
                    f.write(self._expand_bytes(data))

    # running
    # -------

    def env(self):
        return {'PATH': os.environ.get('PATH', ''), 'HOME': self.home, 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
                'TZ': 'UTC', 'COLUMNS': '80', 'LINES': '24', 'NO_COLOR': '1', 'TERM': 'dumb'}

    def run_step(self, papers, step):
        if step.get('wait'):
            time.sleep(step['wait'])   # exchanges compare times with a resolution of one second
        cwd = os.path.normpath(os.path.join(self.work, step.get('cwd', '.')))
        argv = [self.expand(a) for a in step['argv']]
        if 'stdin_file' in step:
            with open(os.path.join(self.case.path, step['stdin_file']), 'rb') as f:
                stdin = self._expand_bytes(f.read())
        elif 'stdin' in step:
            stdin = self.expand(step['stdin']).encode('utf-8')
        else:
            stdin = None
        if not os.path.isdir(cwd):
            return {'stdout': '', 'stderr': f'cases: the directory {step.get("cwd")} of the step does not exist\n', 'exit': 125}
        try:
            p = subprocess.run(papers + argv, cwd=cwd, env=self.env(), input=stdin, capture_output=True,
                               stdin=None if stdin is not None else subprocess.DEVNULL, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return {'stdout': '', 'stderr': f'cases: timeout after {TIMEOUT} s\n', 'exit': 124}
        # the first stdin, the encoding of the text: utf-8, undecodable bytes kept
        return {'stdout': p.stdout.decode('utf-8', 'surrogateescape'),
                'stderr': p.stderr.decode('utf-8', 'surrogateescape'), 'exit': p.returncode}

    def normalize_steps(self, steps):
        "the outputs of the steps, normalized (after snapshot(): it knows the identifiers of the projects)"
        for step in steps:
            for stream in ('stdout', 'stderr'):
                text = self._rename(self.normalize(step[stream]))
                step[stream] = TIME_IN_TEXT.sub('($TIME', text)

    def detect_version(self, papers):
        "the version the implementation reports: its output is replaced by $VERSION (asked in an empty HOME)"
        env = self.env()
        env['HOME'] = tempfile.mkdtemp(prefix='papers-cases-version-')
        try:
            p = subprocess.run(papers + ['--version'], cwd=self.work, env=env, capture_output=True,
                               stdin=subprocess.DEVNULL, timeout=TIMEOUT)
        except (OSError, subprocess.SubprocessError):
            return
        finally:
            shutil.rmtree(env['HOME'], ignore_errors=True)
        text = p.stdout.decode('utf-8', 'replace').strip()
        if p.returncode == 0 and text:
            self.version = text

    # after
    # -----

    def snapshot(self):
        "the normalized trees after the run: {'work': {...}, 'home': {...}}"
        raw = _read_tree(self.home)
        d = self.dirs
        history = os.path.relpath(d['data'], self.home).replace(os.sep, '/') + '/history/'
        self.projects = self._project_names(raw, history)
        self.hashes = {hashlib.sha1(pid.encode()).hexdigest()[:6]: name for pid, name in self.projects.items()}
        self.states = {i: f'$STATE{n + 1}' for n, (_, i) in enumerate(self._recent_states())}
        work = {self._rename(p): self._normalize_bytes(data, path=p) for p, data in _read_tree(self.work).items()}
        return {'work': work, 'home': self._snapshot_home(raw)}

    def _snapshot_home(self, raw):
        d = self.dirs
        cache = os.path.relpath(d['cache'], self.home).replace(os.sep, '/') + '/'
        config = os.path.relpath(d['config'], self.home).replace(os.sep, '/') + '/'
        data = os.path.relpath(d['data'], self.home).replace(os.sep, '/') + '/'
        history = data + 'history/'
        projects = self.projects
        tree = {}
        renamed = {}
        texts = {}   # the objects: sha256 (of the normalized text) -> normalized text
        for path, content in raw.items():
            if path.startswith(cache):
                continue   # the parse cache: private to each implementation
            if path.startswith('.local/share/Trash/'):
                continue   # the trash of the system (Linux: in HOME; macOS: elsewhere): not papers'
            if path.startswith(history):
                rel = 'data/history/' + path[len(history):]
                parts = rel.split('/')
                if len(parts) > 3 and parts[2] == 'projects':
                    parts[3] = projects.get(parts[3], parts[3])
                    time_json = True
                    if len(parts) == 6 and parts[4] == 'states' and parts[5].endswith('.json'):
                        # a state of the run is named by a hash of its time: $STATEn. A state of before-home
                        # (a history converted from papers 3.0.0b5) keeps its name and its time.
                        stem = parts[5][:-len('.json')]
                        if stem in self.states:
                            parts[5] = self.states[stem] + '.json'
                        else:
                            time_json = False
                    rel = '/'.join(parts)
                    content = self._normalize_bytes(content, time_json=time_json)
                elif len(parts) > 3 and parts[2] == 'objects':
                    try:
                        content = zlib.decompress(content)   # the compressor is private; the text is shared
                    except zlib.error:
                        pass
                    normalized = self._normalize_bytes(content, origin=True)
                    if normalized != content:
                        # an object is named by the sha256 of its text: a text with a machine-specific part
                        # (a path, the time of an origin record) is named by the sha256 of its normalized text
                        new = hashlib.sha256(normalized).hexdigest()
                        renamed[parts[-1]] = new
                        parts[-1] = new
                        parts[-2] = new[:2]
                        rel = '/'.join(parts)
                    content = normalized
                    texts[parts[-1]] = normalized
                else:
                    content = self._normalize_bytes(content)
            elif path.startswith(config):
                rel = 'config/' + path[len(config):]
                content = self._normalize_bytes(content)
            elif path.startswith(data):
                rel = 'data/' + path[len(data):]
                content = self._normalize_bytes(content)
            else:
                rel = 'home/' + path
                content = self._normalize_bytes(content)
            tree[rel] = content
        if renamed:   # the states name the objects they use
            for rel, content in tree.items():
                if rel.startswith('data/history/projects/') and rel.endswith('.json'):
                    text = content.decode('utf-8')
                    for old, new in renamed.items():
                        text = text.replace(old, new)
                    tree[rel] = self._renew_bibtex_sha(text, renamed, texts).encode('utf-8')
        return tree

    @staticmethod
    def _renew_bibtex_sha(text, renamed, texts):
        "a state whose bibtex has a renamed piece: its `sha` (of the whole text) follows the normalized text"
        try:
            bibtex = json.loads(text)['bibtex']
            pieces, old = bibtex['pieces'], bibtex['sha']
        except (ValueError, KeyError, TypeError):
            return text
        if not set(pieces) & set(renamed.values()) or any(p not in texts for p in pieces):
            return text
        new = hashlib.sha256(b''.join(texts[p] for p in pieces)).hexdigest()
        return text.replace(old, new)

    def _project_names(self, raw, history):
        "the random identifiers of the projects of the history, numbered by the places of their libraries"
        prefix = history + 'projects/'
        ids = sorted({p[len(prefix):].split('/')[0] for p in raw if p.startswith(prefix)})
        keyed = []
        for pid in ids:
            heads = raw.get(prefix + pid + '/heads.json', b'')
            try:
                places = sorted(self.normalize(k) for k in json.loads(heads.decode('utf-8')))
            except ValueError:
                places = []
            keyed.append((places, pid))
        keyed.sort()
        return {pid: f'$PROJECT{i + 1}' for i, (_, pid) in enumerate(keyed)}


# running a case
# ==============

def resolve_papers(command):
    "the command to run (a list), its program as an absolute path"
    argv = shlex.split(command)
    if not argv:
        raise SystemExit('--papers: empty command')
    prog = argv[0]
    if os.sep in prog:
        prog = os.path.abspath(prog)
    else:
        prog = shutil.which(prog)
    if not prog or not os.path.exists(prog):
        raise SystemExit(f'--papers: {argv[0]}: command not found')
    return [prog] + argv[1:]


def run_case(case, papers, keep=False):
    "run the steps of a case: {'steps': [{stdout, stderr, exit}], 'work': {...}, 'home': {...}}"
    box = Sandbox(case, keep=keep)
    try:
        box.populate()
        box.detect_version(papers)
        steps = []
        for step in case.steps:
            steps.append(box.run_step(papers, step))
            box.see_states()   # a later step can drop the history of this one: its identifiers are still named
        result = box.snapshot()
        for tree in ('work', 'home'):   # the files the case does not compare ("ignore")
            for path in [p for p in result[tree] if any(fnmatch.fnmatch(f'{tree}/{p}', g) for g in case.ignore)]:
                del result[tree][path]
        box.normalize_steps(steps)
        result['steps'] = steps
        if keep:
            print(f'{case.name}: sandbox kept in {box.root}', file=sys.stderr)
        return result
    finally:
        box.close()


# expected results
# ================

def _step_file(n):
    return f'{n + 1:02d}'


def write_expected(case, result):
    "write expected/ of the case: <NN>.stdout, <NN>.stderr (when not empty), exit.json, work/, home/"
    _remove_dir_contents(case.expected)
    os.makedirs(case.expected)
    for n, step in enumerate(result['steps']):
        for stream in ('stdout', 'stderr'):
            if step[stream]:
                with open(os.path.join(case.expected, f'{_step_file(n)}.{stream}'), 'wb') as f:
                    f.write(step[stream].encode('utf-8', 'surrogateescape'))
    with open(os.path.join(case.expected, 'exit.json'), 'w', encoding='utf-8') as f:
        json.dump([s['exit'] for s in result['steps']], f)
        f.write('\n')
    for tree in ('work', 'home'):
        _write_tree(os.path.join(case.expected, tree), result[tree])


def read_expected(case):
    if not os.path.isfile(os.path.join(case.expected, 'exit.json')):
        return None
    with open(os.path.join(case.expected, 'exit.json'), encoding='utf-8') as f:
        exits = json.load(f)
    steps = []
    for n, code in enumerate(exits):
        step = {'exit': code}
        for stream in ('stdout', 'stderr'):
            path = os.path.join(case.expected, f'{_step_file(n)}.{stream}')
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    step[stream] = f.read().decode('utf-8', 'surrogateescape')
            else:
                step[stream] = ''
        steps.append(step)
    result = {'steps': steps}
    for tree in ('work', 'home'):
        result[tree] = _load_stored(os.path.join(case.expected, tree))
    return result


# comparison
# ==========

def _text_diff(label, expected, actual, limit=40):
    if isinstance(expected, bytes) or isinstance(actual, bytes):
        try:
            expected = expected.decode('utf-8') if isinstance(expected, bytes) else expected
            actual = actual.decode('utf-8') if isinstance(actual, bytes) else actual
        except UnicodeDecodeError:
            return f'{label}: binary content differs ({len(expected)} bytes expected, {len(actual)} found)'
    lines = list(difflib.unified_diff(expected.splitlines(True), actual.splitlines(True),
                                      f'expected {label}', f'actual {label}'))
    lines = [l if l.endswith('\n') else l + '\n\\ no newline at end of text\n' for l in lines]
    if len(lines) > limit:
        lines = lines[:limit] + [f'... ({len(lines) - limit} more lines)\n']
    if not lines:
        return f'{label}: differs'
    return ''.join(lines)


def _without_keys(data, keys):
    "the JSON object of the text without the given top-level keys, or None when it is not a JSON object"
    try:
        obj = json.loads(data.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    return {k: v for k, v in obj.items() if k not in keys}


def _free_keys(tree, path):
    for pattern, keys in FREE_JSON_KEYS:
        if fnmatch.fnmatch(f'{tree}/{path}', pattern):
            return keys
    return ()


def differences(expected, actual, case=None, first_only=True, contract_only=False):
    """list of (label, unified diff, free) of what differs in the results, in the order of the run.

    `free` is True for a difference in something that is Free (the output of a step that is not Contract,
    a Free key of a file: see "Contract and Free" above); `case` says which. Without `case`, everything
    is Contract. All differences are listed; first_only stops at the first one (with contract_only: at the
    first Contract one, the Free ones before it are kept)."""
    found = []

    def add(label, text, free=False):
        found.append((label, text, free))

    if len(expected['steps']) != len(actual['steps']):
        add('steps', _text_diff('steps', f'{len(expected["steps"])} steps\n', f'{len(actual["steps"])} steps\n'))
        return found
    for n, (e, a) in enumerate(zip(expected['steps'], actual['steps'])):
        streams = step_contract(case, n) if case else {'stdout', 'stderr'}
        for key in ('exit', 'stdout', 'stderr'):
            if e[key] != a[key]:
                label = f'step {n + 1} {key}'
                if key == 'exit':
                    add(label, f'expected exit code {e[key]}, found {a[key]}\n')
                else:
                    add(label, _text_diff(label, e[key], a[key]), free=key not in streams)
    for tree in ('work', 'home'):
        for path in sorted(set(expected[tree]) | set(actual[tree])):
            e, a = expected[tree].get(path), actual[tree].get(path)
            if e == a:
                continue
            label = f'{tree}/{path}'
            if e is None:
                add(label, 'file not expected, but written\n')
            elif a is None:
                add(label, 'file expected, but not written\n')
            else:
                keys = _free_keys(tree, path)
                ke, ka = (_without_keys(e, keys), _without_keys(a, keys)) if keys else (None, None)
                add(label, _text_diff(label, e, a), free=ke is not None and ke == ka)
    if first_only:
        shown = []
        for item in found:
            shown.append(item)
            if not item[2] or not contract_only:
                break
        return shown
    return found
