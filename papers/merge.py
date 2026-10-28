"""Merge of entries that are the same paper, and the dialogue that decides it.

A merge combines a target entry (entries[0], it keeps its key) with other
entries:

- fields present in the target only are kept, fields missing in the target
  are added (`+`);
- `file` links are the union of all links (a file linked under two paths,
  or two files with the same content, once);
- values equal after normalization are not conflicts (case, braces,
  whitespace, DOI case; author initials and full first names): the target's
  spelling is kept, except for names, where the fuller form is kept;
- the remaining differences are conflicts (`!`), decided by the user or by
  the --on-duplicate option;
- with keys_to_ids (check), the keys of the other entries go to the `ids`
  field of the target (biblatex key aliases).

The model (Merge), the screen and the reading of an answer (Dialogue) do no
input or output; `ask` runs the dialogue in a terminal.

Exchange mode (`pull`, `push`: Merge with exchange=True): the fields of
EXCHANGE_OWN are not merged, each side keeps its own (see there). With a
`base` (the origin copy of the entry, the entry as last exchanged), the
merge is three-way: whatever one side changed since the base wins, and a
field changed on both sides is a conflict. An equivalent change (case,
braces) of the other entry wins only when the target has the base exactly. A removal is a change: a field
removed in the other entry, that the target has as in the base, is removed
(`+`, shown as `(removed)`); removed on one side and changed on the other
is a conflict; removed on both sides, it is removed. Without a base (first
exchange, or a one-time exchange), a field present on one side only is an
addition.
"""
import builtins
import os
import re

from bibtexparser.model import Entry, Field

from papers import logger
from papers.duplicate import normalize_text, split_names, parse_name, ASK
from papers.entries import (get_entry_val, parse_string, format_library, library_from_entries, parse_file,
                            format_file)
from papers.identifiers import normalize_doi
from papers.utils import bcolors, checksum, edit_text, PapersExit


SAME = ' '
ADDED = '+'
CONFLICT = '!'

# fields with their own merge rule
SPECIAL_FIELDS = ('ID', 'file', 'ids')

# the fields that an exchange (pull, push) does not merge: each side keeps
# its own. The key: each library names its entries (the pool key comes from
# the pool's key template when the entry first reaches the pool). ids: the
# former keys of each side. file: the links of each side; the files have
# their own handling (a file new on the other side is linked or copied).
EXCHANGE_OWN = ('ID', 'ids', 'file')

# how the dialogue shows a field that a side removed (three-way mode)
REMOVED = '(removed)'


# EQUIVALENT VALUES
# =================

def _given_tokens(given):
    return [t for t in re.split(r'[\s.\-~]+', normalize_text(given)) if t]


def _given_compatible(g1, g2):
    """John / J. / J. D. / John David: each word equal, or an initial of the
    other; words beyond the shorter name are not compared (J. and John Quincy)"""
    for x, y in zip(_given_tokens(g1), _given_tokens(g2)):
        if x == y:
            continue
        if len(x) == 1 and y.startswith(x) or len(y) == 1 and x.startswith(y):
            continue
        return False
    return True


def names_compatible(field1, field2):
    "two author lists that only differ by initials versus full first names, or by name order"
    n1, n2 = split_names(field1), split_names(field2)
    if len(n1) != len(n2):
        return False
    for a, b in zip(n1, n2):
        (fa, ga), (fb, gb) = parse_name(a), parse_name(b)
        if normalize_text(fa) != normalize_text(fb) or not _given_compatible(ga, gb):
            return False
    return True


def _fullness(field):
    return sum(len(t) for n in split_names(field) for t in _given_tokens(parse_name(n)[1]))


def equivalent(name, v1, v2):
    if name in ('author', 'editor'):
        return names_compatible(v1, v2)
    if name == 'doi':
        d1, d2 = normalize_doi(v1), normalize_doi(v2)
        if d1 and d2:
            return d1 == d2
    return normalize_text(v1) == normalize_text(v2)


def preferred(name, values):
    "the value kept among equivalent values: the first, or the fuller names"
    if name in ('author', 'editor'):
        best = values[0]
        for v in values[1:]:
            if _fullness(v) > _fullness(best):
                best = v
        return best
    return values[0]


# THE MERGE
# =========

def _no_empty(v):
    return v if v is not None and str(v).strip() else None


# where a field changed since the base (three-way mode)
CHANGED_TARGET = 'target'
CHANGED_OTHER = 'other'
CHANGED_BOTH = 'both'


class FieldMerge:
    """one field of a merge: `values` holds the value of each entry (None if
    absent), `status` is SAME, ADDED or CONFLICT, `choice` the entry whose
    value is used (for SAME and ADDED, `value` is set directly).

    In three-way mode (`three_way`, with `base` the value of the origin
    copy), `changed` says which side changed the field since the base:
    CHANGED_TARGET, CHANGED_OTHER, CHANGED_BOTH, or None. Equivalent values
    are the same, except when the target has the base exactly and the
    other entry another (equivalent) value: that change (case, braces,
    fuller names) is offered."""

    def __init__(self, name, values, base=None, three_way=False):
        self.name = name
        original = values
        # an empty value is no value
        values = [_no_empty(v) for v in values]
        self.values = values
        self.base = _no_empty(base)
        self.three_way = three_way
        self.changed = None
        present = [v for v in values if v is not None]
        target = values[0]
        self._value = None
        if not present:
            self.choice = 0
            self._value = original[0]  # an empty field of the target is kept, of another entry not added
            self.status = SAME
            return
        self.choice = 0 if target is not None else next(i for i, v in enumerate(values) if v is not None)
        if three_way and self.base is not None and target == self.base and values[1] != target \
                and values[1] is not None and equivalent(name, target, values[1]):
            # an equivalent change of the other side only (case, braces): offered
            self.status = ADDED
            self._value = values[1]
            self.choice = 1
            self.changed = CHANGED_OTHER
        elif all(equivalent(name, present[0], v) for v in present[1:]) and not (three_way and None in values):
            self._value = preferred(name, present)
            self.status = SAME if target is not None else ADDED
        elif three_way:
            self._three_way(name, values[0], values[1])
        else:
            self.status = CONFLICT

    def _three_way(self, name, target, other):
        "target and other differ (one of them may be absent: added, or removed since the base)"
        base = self.base
        same = lambda a, b: a is not None and b is not None and equivalent(name, a, b)
        self.choice = 0
        if base is None and other is None:
            # added in the target: kept
            self.status = SAME
            self.changed = CHANGED_TARGET
        elif base is None and target is None:
            # added in the other entry: offered
            self.status = ADDED
            self.choice = 1
            self.changed = CHANGED_OTHER
        elif same(other, base):
            # changed or removed in the target only: kept
            self.status = SAME
            self.changed = CHANGED_TARGET
        elif same(target, base):
            # changed or removed in the other entry only: offered
            self.status = ADDED
            self._value = other
            self.choice = 1
            self.changed = CHANGED_OTHER
        else:
            # changed on both sides, or removed on one side and changed on the other
            self.status = CONFLICT
            self.changed = CHANGED_BOTH

    @property
    def removal(self):
        "the change offered is the removal of the field (three-way mode)"
        return self.status == ADDED and self.values[self.choice] is None

    def decline(self):
        "do not take an addition: keep the value of the target (none if it has none)"
        if self.status == ADDED:
            self.status = SAME
            self._value = None
            self.choice = 0

    @property
    def value(self):
        if self._value is not None:
            return self._value
        return self.values[self.choice]

    def choose(self, i):
        """use the value of entry i (ignored when entry i does not have the
        field, except in three-way mode, where entry i removed it)"""
        if self.status == CONFLICT and 0 <= i < len(self.values) and (self.values[i] is not None or self.three_way):
            self.choice = i

    def alternatives(self):
        """[(entries, value)] of the values not used, grouped by value, in
        entry order (value None: the field removed, in three-way mode)"""
        groups = []
        for i, v in enumerate(self.values):
            if i == self.choice:
                continue
            if v is None:
                if not self.three_way or self.value is None:
                    continue
            elif self.value is not None and equivalent(self.name, v, self.value):
                continue
            for g in groups:
                if (g[1] is None) == (v is None) and (v is None or equivalent(self.name, g[1], v)):
                    g[0].append(i)
                    break
            else:
                groups.append(([i], v))
        return groups


class Merge:
    """merge of entries[0] (the target) with the other entries (see the
    module documentation). `relative_to` is the directory the file links of
    the entries are relative to.

    exchange: a merge of a library entry and a pool entry (pull, push):
    the fields of EXCHANGE_OWN are the target's (the file links are the
    union, see Merge.new_files).
    base: the origin copy of the entry, for a three-way merge of two
    entries (pull, push: an exchange); its key and file links are not used."""

    def __init__(self, entries, relative_to=None, keys_to_ids=False, base=None, exchange=False):
        self.entries = list(entries)
        self.relative_to = relative_to
        self.keys_to_ids = keys_to_ids
        self.base = base
        self.exchange = exchange or base is not None
        if base is not None and len(self.entries) != 2:
            raise ValueError('a three-way merge combines two entries')
        self.fields = []
        names = []
        for e in self.entries:
            for k, _ in e.items():
                if k not in SPECIAL_FIELDS and k not in names:
                    names.append(k)
        for name in names:
            values = [_value(e, name) for e in self.entries]
            if base is not None:
                self.fields.append(FieldMerge(name, values, base=_value(base, name), three_way=True))
            else:
                self.fields.append(FieldMerge(name, values))
        self._merge_files()
        self._merge_ids()

    @property
    def three_way(self):
        return self.base is not None

    @property
    def target(self):
        return self.entries[0]

    @property
    def key(self):
        return get_entry_val(self.target, 'ID', '')

    @property
    def others(self):
        return self.entries[1:]

    def _files(self, e):
        return parse_file(get_entry_val(e, 'file', ''), relative_to=self.relative_to)

    def _merge_files(self):
        "union of the file links: the same file (real path, or content) once"
        self.files = []
        seen = set()
        for e in self.entries:
            for f in self._files(e):
                ids = {os.path.realpath(f)}
                if os.path.isfile(f):
                    ids.add(checksum(f))
                if not ids & seen:
                    self.files.append(f)
                seen |= ids
        own = {os.path.realpath(f) for f in self._files(self.target)}
        self.new_files = [f for f in self.files if os.path.realpath(f) not in own]

    def _merge_ids(self):
        key = self.key.lower()
        ids = []
        # the key aliases of a pool mean nothing in a library, and conversely (EXCHANGE_OWN)
        sources = [get_entry_val(e, 'ids', '') for e in (self.entries[:1] if self.exchange else self.entries)]
        if self.keys_to_ids:
            sources += [get_entry_val(e, 'ID', '') for e in self.others]
        for source in sources:
            for i in source.split(','):
                i = i.strip()
                if i and i.lower() != key and i.lower() not in {x.lower() for x in ids}:
                    ids.append(i)
        self.ids = ids
        self.ids_added = [i for i in ids if i.lower() not in
                          {x.strip().lower() for x in get_entry_val(self.target, 'ids', '').split(',')}]

    @property
    def conflicts(self):
        return [f for f in self.fields if f.status == CONFLICT]

    @property
    def additions(self):
        return [f for f in self.fields if f.status == ADDED]

    def is_exact(self):
        "nothing to decide: no conflict, and no field to add (files and key aliases aside)"
        return not self.conflicts and not self.additions

    def choose_all(self, i):
        "resolve every conflict with the value of entry i, where it has one"
        for f in self.conflicts:
            f.choose(i)

    def with_target(self, i):
        "the same merge with entry i as target"
        entries = [self.entries[i]] + [e for j, e in enumerate(self.entries) if j != i]
        return Merge(entries, relative_to=self.relative_to, keys_to_ids=self.keys_to_ids, base=self.base,
                     exchange=self.exchange)

    def _field(self, f):
        """the Field of the merged value of f: a bare value (month = jan, a
        @string name) stays bare when it is the value of one of the entries"""
        field = Field(f.name, f.value)
        for e in [self.entries[f.choice]] + self.entries:
            same = e.fields_dict.get(f.name)
            if same is not None and same.value == f.value:
                if getattr(same, 'enclosing', None) is not None:
                    field.enclosing = same.enclosing
                break
        return field

    def result(self):
        "the merged entry, with the key of the target"
        fields = [self._field(f) for f in self.fields if f.name != 'ENTRYTYPE' and f.value is not None]
        if self.files:
            fields.append(Field('file', format_file(self.files, relative_to=self.relative_to)))
        if self.ids:
            fields.append(Field('ids', ', '.join(self.ids)))
        etype = next((f.value for f in self.fields if f.name == 'ENTRYTYPE'), self.target.entry_type)
        return Entry(entry_type=etype, key=self.key, fields=fields)

    def edit_text(self):
        "the merged entry as plain bibtex, and the alternatives as % comment lines below it"
        text = format_library(library_from_entries([self.result()]))
        lines = []
        for f in self.conflicts:
            for idx, v in f.alternatives():
                value = f'{{{_oneline(v)}}}' if v is not None else REMOVED
                lines.append(f'% {f.name} = {value}   ({", ".join(str(i+1) for i in idx)})')
        if lines:
            text = text.rstrip('\n') + '\n\n% values of the other entries (lines starting with % are ignored):\n' + '\n'.join(lines) + '\n'
        return text

    def parse_edit(self, text):
        """the entry of an edited text (see edit_text), with the key of the
        target; None if it is not exactly one valid bibtex entry"""
        text = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('%'))
        try:
            lib = parse_string(text)
        except Exception as error:
            logger.error(f'the edited entry could not be parsed: {error}')
            return None
        if getattr(lib, 'failed_blocks', None) or len(lib.entries) != 1:
            logger.error('the edited text is not one bibtex entry')
            return None
        e = lib.entries[0]
        fieldname = re.compile(r'^[A-Za-z][\w-]*$')
        bad = [k for k in _field_names(e) if not fieldname.match(k)]
        if bad:
            logger.error(f'malformed field name(s) in the edited entry: {bad}')
            return None
        if e.key != self.key:
            logger.warning(f'the key {self.key} is kept (edited key {e.key} ignored)')
            e.key = self.key
        return e


def _field_names(e):
    return [k for k, _ in e.items() if k not in ('ID', 'ENTRYTYPE')]


def _value(e, name):
    "value of a field of an entry for the merge (the entry type in lower case), None if absent"
    if name == 'ENTRYTYPE':
        return get_entry_val(e, name, '').lower()
    return get_entry_val(e, name, None) if name in _field_names(e) else None


def _oneline(value, width=None):
    s = ' '.join(str(value).split())
    if width and len(s) > width:
        s = s[:width-3] + '...'
    return s


def apply_entry(target, entry):
    "make the target entry (in the library) equal to `entry`, in place (a bare value stays bare)"
    target.entry_type = entry.entry_type
    target.key = entry.key
    fields = []
    for f in entry.fields:
        field = Field(f.key, f.value)
        if getattr(f, 'enclosing', None) is not None:
            field.enclosing = f.enclosing
        fields.append(field)
    target.fields = fields


# THE DIALOGUE
# ============

class Answer:
    "a parsed answer: kind is one of take, fields, edit, target, distinct, skip, quit, help, invalid"

    def __init__(self, kind, index=None, text=''):
        self.kind = kind
        self.index = index
        self.text = text

    def __repr__(self):
        return f'Answer({self.kind!r}, {self.index!r})'


class Dialogue:
    """screen and answers for one merge decision; no input or output.

    context: 'add' (entry 1 is the library entry, entry 2 the added entry),
    'check' (a group of library entries), 'pull' (entry 1 is the library
    entry, entry 2 the pool entry) or 'push' (entry 1 is the pool entry,
    entry 2 the library entry).
    reason: why the entries are the same paper (from same_paper); for pull
    and push, the pool."""

    LABELS = {'add': ('library', 'new'), 'pull': ('library', 'pool'), 'push': ('pool', 'library')}

    def __init__(self, merge, context, reason='', color=False):
        self.merge = merge
        self.context = context
        self.reason = reason
        self.color = color

    @property
    def exchange(self):
        "pull or push"
        return self.context in ('pull', 'push')

    # labels

    def label(self, i):
        if self.context in self.LABELS:
            return self.LABELS[self.context][i]
        return get_entry_val(self.merge.entries[i], 'ID', '')

    def change_note(self, f):
        "where a field changed, in three-way mode"
        if f.changed == CHANGED_TARGET:
            return f'changed in {self.label(0)}, kept'
        if f.changed == CHANGED_OTHER:
            if f.values[1] is None:
                return f'removed in {self.label(1)}'
            return f'{"added" if f.values[0] is None else "changed"} in {self.label(1)}'
        if f.changed == CHANGED_BOTH:
            for i in (0, 1):
                if f.values[i] is None:
                    return f'removed in {self.label(i)}, changed in {self.label(1 - i)}'
            return 'changed on both sides'
        return ''

    def _c(self, s, color):
        return (color + s + bcolors.ENDC) if self.color else s

    # screen

    def header(self):
        m = self.merge
        if self.context == 'add':
            line = f'Already in library: {m.key}' + (f' ({self.reason})' if self.reason else '')
        elif self.context == 'pull':
            line = f'{m.key}  <-  {self.reason or "pool"} ({get_entry_val(m.others[0], "ID", "")})'
        elif self.context == 'push':
            line = f'{get_entry_val(m.others[0], "ID", "")}  ->  {self.reason or "pool"} ({m.key})'
        else:
            line = f'Same paper: {len(m.entries)} entries' + (f' ({self.reason})' if self.reason else '')
        lines = [self._c(line, bcolors.OKBLUE)]
        rows = []
        for i, e in enumerate(m.entries):
            files = [os.path.relpath(f) if os.path.isabs(f) else f for f in m._files(e)]
            doi = get_entry_val(e, 'doi', '')
            rows.append([str(i+1), self.label(i) if self.context in self.LABELS else '',
                         get_entry_val(e, 'ID', ''), get_entry_val(e, 'ENTRYTYPE', '').lower(),
                         f'doi {doi}' if doi else 'no doi', ' '.join(files)])
        widths = [max(len(r[j]) for r in rows) for j in range(len(rows[0]))]
        for r in rows:
            lines.append('  ' + '  '.join(c.ljust(w) for c, w in zip(r, widths) if w).rstrip())
        if m.three_way:
            lines.append('     origin = the entry as last exchanged (add, pull or push)')
        return '\n'.join(lines)

    def entry_lines(self):
        m = self.merge
        etype = next(f for f in m.fields if f.name == 'ENTRYTYPE')
        names = [f.name for f in m.fields if f.name != 'ENTRYTYPE'] + ['file', 'ids']
        width = max([len(n) for n in names] + [4])
        out = [f'@{etype.value}{{{m.key},']

        def line(mark, name, value, alternatives=(), note=''):
            text = f'{mark}  {name.ljust(width)} = {value}'
            if note:
                text = text.ljust(50) + '   ' + note
            color = {ADDED: bcolors.OKGREEN, CONFLICT: bcolors.WARNING}.get(mark)
            out.append(self._c(text, color) if color else text)
            for idx, v in alternatives:
                which = ",".join(str(i+1) if isinstance(i, int) else i for i in idx)
                alt = f'{CONFLICT}  {" " * width}   {which}: {v}'
                out.append(self._c(alt, bcolors.WARNING))

        def origin(f):
            return [] if f.base is None or not m.three_way else [(['origin'], '{' + _oneline(f.base) + '}')]

        if etype.status == CONFLICT:
            line(CONFLICT, 'type', etype.value, etype.alternatives() + origin(etype), self.change_note(etype))
        others = [get_entry_val(e, 'ID', '') for e in m.others]
        if self.context == 'check' and any(k != m.key for k in others):
            alts = [([i+1], f'{k} (kept in ids)') for i, k in enumerate(others) if k != m.key]
            line(CONFLICT, 'key', m.key, alts)
        def shown(v, width=None):
            return REMOVED if v is None else '{' + _oneline(v, width) + '}'

        rows = []
        for f in m.fields:
            if f.name == 'ENTRYTYPE' or f.value is None and f.status == SAME:
                continue
            if f.status == CONFLICT:
                rows.append((CONFLICT, f.name, shown(f.value),
                             [(idx, shown(v)) for idx, v in f.alternatives()] + origin(f),
                             self.change_note(f)))
            else:
                rows.append((f.status, f.name, shown(f.value, None if f.status == ADDED else 70), (),
                             self.change_note(f)))
        if m.files:
            files = ';'.join(os.path.relpath(f) if os.path.isabs(f) else f for f in m.files)
            rows.append((ADDED if m.new_files else SAME, 'file', '{' + files + '}', ()))
        if m.ids:
            rows.append((ADDED if m.ids_added else SAME, 'ids', '{' + ', '.join(m.ids) + '}', ()))
        for row in sorted(rows, key=lambda r: r[1]):
            line(*row)
        out.append('}')
        return out

    def summary(self):
        m = self.merge
        n = len(m.conflicts)
        conflicts = 'No conflict' if n == 0 else f'{n} conflict' + ('s' if n > 1 else '')
        if self.context == 'add':
            return f'{conflicts}. The key {m.key} is kept; + lines are added.'
        if self.exchange:
            n = len(m.additions)
            return (f'{conflicts}, {n} change{"s" if n != 1 else ""} from the {self.label(1)}. '
                    f'The key {m.key} is kept.')
        others =', '.join(str(i+2) for i in range(len(m.others)))
        if len(m.others) == 1:
            return f'{conflicts}. Entry {others} is removed after the merge; its key goes to ids.'
        return f'{conflicts}. Entries {others} are removed after the merge; their keys go to ids.'

    def menu(self):
        m = self.merge
        n = len(m.entries)
        first = []
        if m.conflicts:
            if self.context in self.LABELS:
                first += [f'1 keep {self.label(0)} values', f'2 take {self.label(1)} values']
            else:
                first += [f'{i+1} {"keep" if i == 0 else "take"} values of {i+1}' for i in range(n)]
            first += ['f field by field']
        else:
            first += ['1 merge']
            if m.three_way and m.additions:
                first += ['f field by field']
        first += ['e edit']
        second = []
        if self.context == 'check':
            second.append('t N make entry N the target')
        if self.context == 'add':
            second.append(f'n not the same paper (add {get_entry_val(m.others[0], "ID", "")} separately)')
        elif not self.exchange:
            second.append('n not the same paper')
        second += [f's skip ({self.context} again later)' if self.exchange else 's skip', 'q quit', '? help']
        return '  ' + '   '.join(first) + '\n  ' + '   '.join(second)

    def screen(self):
        return '\n'.join([self.header(), ''] + self.entry_lines() + [self.summary(), self.menu()])

    def help(self):
        n = len(self.merge.entries)
        lines = [
            f'  1..{n}  resolve all remaining conflicts with the values of that entry, and merge',
            '  f      go through the conflicts one at a time'
            + (' (and the changes from the other side)' if self.merge.three_way else ''),
            '  e      edit the merged entry in the editor (the other values are % comment lines)',
        ]
        if self.context == 'check':
            lines.append('  t N    make entry N the target: its key is kept, the other keys go to ids')
            lines.append('  n      not the same paper: keep the entries separate, and do not ask again')
        elif not self.exchange:
            lines.append('  n      not the same paper: add the new entry separately, and do not ask again')
        lines += [
            '  s      skip: change nothing for this one (asked again next time)',
            '  q      quit: skip this one and all remaining duplicates',
            '  ?      this help',
            'Lines: unmarked = same on all sides, + = added from another entry, ! = conflict '
            '(the value used, then the other values, numbered by entry).',
        ]
        return '\n'.join(lines)

    def field_question(self, f):
        """the question for one conflicting field, or in three-way mode an
        addition (answer with parse_field)"""
        absent = REMOVED if f.base is not None else '(none)'
        rows = [(str(i+1), _oneline(v) if v is not None else absent, self.label(i))
                for i, v in enumerate(f.values) if v is not None or f.status == ADDED or f.three_way]
        width = max(len(r[1]) for r in rows)
        lines = [f'{f.name if f.name != "ENTRYTYPE" else "type"}:']
        lines += [f'  {n}  {v.ljust(width)}  {label}' for n, v, label in rows]
        choices = '/'.join(r[0] for r in rows)
        return '\n'.join(lines) + f'\n  [{choices}/e] >>> '

    # answers

    def parse(self, text):
        s = text.strip()
        n = len(self.merge.entries)
        if s.isdigit():
            i = int(s)
            if 1 <= i <= n:
                return Answer('take', i - 1, s)
            return Answer('invalid', text=s)
        if s in ('f', 'e', 'n', 's', 'q', '?'):
            if s == 'f' and not self.field_questions():
                return Answer('invalid', text=s)
            if s == 'n' and self.exchange:
                return Answer('invalid', text=s)
            return Answer({'f': 'fields', 'e': 'edit', 'n': 'distinct', 's': 'skip',
                           'q': 'quit', '?': 'help'}[s], text=s)
        m = re.fullmatch(r't\s*(\d+)', s)
        if m and self.context == 'check':
            i = int(m.group(1))
            if 1 <= i <= n:
                return Answer('target', i - 1, s)
        return Answer('invalid', text=s)

    def parse_field(self, f, text):
        "answer to field_question: Answer take (entry index) or edit, or invalid"
        s = text.strip()
        if s == 'e':
            return Answer('edit', text=s)
        if s.isdigit() and 1 <= int(s) <= len(f.values) and (f.values[int(s)-1] is not None or f.status == ADDED
                                                              or f.three_way):
            return Answer('take', int(s) - 1, s)
        return Answer('invalid', text=s)

    def field_questions(self):
        "the fields that `f` asks about: the conflicts, and in three-way mode the additions"
        return self.merge.conflicts + (self.merge.additions if self.merge.three_way else [])


def _input(prompt):
    return builtins.input(prompt)


def _output(text):
    print(text)


class Decision:
    """outcome of a duplicate decision: kind is 'merge' (entry: the merged
    entry, merge: the Merge decided, whose target may have changed with t N),
    'distinct', 'skip' or 'quit'"""

    def __init__(self, kind, merge=None, entry=None):
        self.kind = kind
        self.merge = merge
        self.entry = entry

    def __repr__(self):
        return f'Decision({self.kind!r})'


def ask(merge, context, reason='', input=None, output=None, editor=None, color=True):
    """run the dialogue in a terminal, and return a Decision"""
    input = input or _input
    output = output or _output
    show = True
    while True:
        dialogue = Dialogue(merge, context, reason, color=color)
        if show:
            output(dialogue.screen())
        show = True
        answer = dialogue.parse(input('>>> '))

        if answer.kind == 'take':
            merge.choose_all(answer.index)
            return Decision('merge', merge, merge.result())

        elif answer.kind == 'fields':
            decision = _ask_fields(dialogue, input, output, editor)
            if decision is not None:
                return decision

        elif answer.kind == 'edit':
            decision = _edit(merge, editor)
            if decision is not None:
                return decision

        elif answer.kind == 'target':
            merge = merge.with_target(answer.index)

        elif answer.kind in ('distinct', 'skip', 'quit'):
            return Decision(answer.kind, merge)

        elif answer.kind == 'help':
            output(dialogue.help())
            show = False

        else:
            output(f'invalid answer: {answer.text!r} (? for help)')
            show = False


def _edit(merge, editor):
    text = edit_text(merge.edit_text(), editor=editor)
    entry = merge.parse_edit(text) if text is not None else None
    if entry is None:
        logger.error('edit failed: back to the menu (nothing was changed)')
        return None
    return Decision('merge', merge, entry)


def _ask_fields(dialogue, input, output, editor):
    "field by field; None when the user went back to the menu (failed edit)"
    merge = dialogue.merge
    for f in dialogue.field_questions():
        while True:
            question, prompt = dialogue.field_question(f).rsplit('\n', 1)
            output(question)
            answer = dialogue.parse_field(f, input(prompt))
            if answer.kind == 'take':
                if f.status == ADDED:
                    if answer.index == 0:
                        f.decline()
                else:
                    f.choose(answer.index)
                break
            elif answer.kind == 'edit':
                return _edit(merge, editor)
            output(f'invalid answer: {answer.text!r}')
    return Decision('merge', merge, merge.result())


# WHAT TO DO WITH A DUPLICATE
# ===========================

ON_DUPLICATE = ('ask', 'keep', 'update', 'skip', 'error')


class DuplicateError(PapersExit):
    "a duplicate with --on-duplicate error: stop before saving"


class Resolver:
    """the --on-duplicate mode of a command, and what was answered so far
    (after q, the remaining duplicates are skipped)

    ask: the dialogue; keep: merge, conflicts keep the value of entry 1;
    update: merge, conflicts take the value of entry 2 (add, pull, push); skip:
    change nothing; error: raise DuplicateError.
    """

    def __init__(self, mode='error', input=None, output=None, editor=None, color=False):
        if mode not in ON_DUPLICATE:
            raise ValueError(f'on_duplicate must be one of {", ".join(ON_DUPLICATE)}')
        self.mode = mode
        self.input = input
        self.output = output
        self.editor = editor
        self.color = color
        self.quit = False

    def decide(self, merge, context, verdict):
        "a Decision for this merge (see Decision); verdict: from same_paper"
        if self.quit:
            return Decision('skip', merge)

        if self.mode == 'error':
            raise DuplicateError(self.describe(merge, context, verdict)
                                 + '\n' + option_hint(context))

        if self.mode == 'skip':
            return Decision('skip', merge)

        if verdict.kind == ASK and self.mode != 'ask':
            logger.warning(f'{self.describe(merge, context, verdict)}: not merged, '
                           'decide in the dialogue (--on-duplicate ask)')
            return Decision('skip', merge)

        if self.mode == 'ask':
            decision = ask(merge, context, verdict.reason, input=self.input, output=self.output,
                           editor=self.editor, color=self.color)
            if decision.kind == 'quit':
                self.quit = True
                decision.kind = 'skip'
            return decision

        merge.choose_all(0 if self.mode == 'keep' else 1)
        return Decision('merge', merge, merge.result())

    @staticmethod
    def describe(merge, context, verdict):
        n = len(merge.conflicts)
        what = f'{n} conflict' + ('s' if n != 1 else '') if n or not merge.additions else 'fields to add'
        if context == 'add':
            new = get_entry_val(merge.others[0], 'ID', '')
            return f'{new}: already in library as {merge.key} ({verdict.reason}; {what})'
        if context == 'pull':
            pool = get_entry_val(merge.others[0], 'ID', '')
            return f'{merge.key}: changed in the library and in {verdict.reason} ({pool}; {what})'
        if context == 'revert':
            return f'{merge.key}: changed since {verdict.reason} too ({what})'
        if context == 'push':
            key = get_entry_val(merge.others[0], 'ID', '')
            return f'{key}: changed in the library and in {verdict.reason} ({merge.key}; {what})'
        keys = ', '.join(get_entry_val(e, 'ID', '') for e in merge.entries)
        return f'same paper: {keys} ({verdict.reason}; {what})'


def option_hint(context):
    words = 'ask, keep, skip' if context == 'check' else 'ask, keep, update, skip'
    command = 'history' if context == 'revert' else context
    return (f'Pass --on-duplicate with one of: {words} (ask is the default in a terminal), '
            f'see `papers {command} --help`.')
