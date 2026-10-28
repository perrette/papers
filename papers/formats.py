"""Bibliography formats other than bibtex: RIS and CSL-JSON.

- `entry_to_csl` / `csl_to_entry`: a bibtex entry and a CSL-JSON item
  (https://citeproc-js.readthedocs.io/en/latest/csl-json/markup.html), our
  own mapping, no dependency;
- `entry_to_ris` / `ris_to_entry`: a bibtex entry and a RIS record as the
  rispy package reads and writes it (a dict of rispy field names). rispy is
  an optional dependency (the `ris` extra), loaded by `load_rispy` when a
  RIS file is read or written;
- `dumps(entries, format, files)` and `loads(text, format)`: a list of
  entries to a text in a format, and back.

Fields without an equivalent are left out. On export, the values are
converted from LaTeX to unicode. The file links are given by the caller
(`files`: entry -> list of paths, written as given). In CSL-JSON, which
has no field for files, they are written in the `custom` object
(`"custom": {"file": [...]}`); on import, a `file` key of the item (a
string separated by `;`, or a list) is read too.
"""
import functools
import importlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from urllib.parse import unquote, urlparse

from bibtexparser.model import Entry, Field

from papers import logger
from papers.entries import get_entry_val, format_file
from papers.utils import PapersExit, stdin_is_terminal

FORMATS = ('bibtex', 'ris', 'csl-json', 'bibjson')

# the name of each format in the messages
LABELS = {'bibtex': 'bibtex', 'ris': 'RIS', 'csl-json': 'CSL-JSON', 'bibjson': 'BibJSON'}

# the format of an added file, from its extension (other files are bibtex)
EXTENSIONS = {'.bib': 'bibtex', '.ris': 'ris', '.json': 'csl-json', '.bib.json': 'bibjson'}

# the name of the file of each format that `papers export` writes
FILENAMES = {'bibtex': 'papers.bib', 'ris': 'papers.ris', 'csl-json': 'papers.json', 'bibjson': 'papers.bib.json'}


def file_format(path, forced=None):
    "the format of an added file: `forced` if given, else from its extension (bibtex by default)"
    if forced:
        return forced
    name = os.path.basename(path).lower()
    # the longest extension first: .bib.json before .json
    for extension in sorted(EXTENSIONS, key=len, reverse=True):
        if name.endswith(extension):
            return EXTENSIONS[extension]
    return 'bibtex'


def extensions_help():
    "the formats of the extensions, for the help of the options: .ris is RIS, ..."
    known = ', '.join(f'{ext} is {LABELS[fmt]}' for ext, fmt in EXTENSIONS.items() if fmt != 'bibtex')
    return f'{known}, other files are bibtex'


# rispy, optional
# ===============

RISPY_COMMANDS = ['pip install rispy', 'pipx inject papers-cli rispy', "pip install 'papers-cli[ris]'"]


def _rispy_help():
    return ('install it with one of: ' + ', '.join(f'`{c}`' for c in RISPY_COMMANDS)
            + ' (with uv: `uv tool install papers-cli --with rispy`)')




def load_rispy(interactive=None, input=input):
    """the rispy module. If it is not installed: in a terminal, offer to
    install it with pip (in the Python environment of papers), else stop
    with the commands that install it. Nothing else is changed."""
    try:
        import rispy
        return rispy
    except ImportError:
        pass
    if interactive is None:
        interactive = stdin_is_terminal()
    if importlib.util.find_spec('pip') is None:
        raise PapersExit(f'RIS needs the rispy package, which is not installed, and pip is not available in the '
                         f'Python environment of papers ({sys.executable}): {_rispy_help()}')
    if not interactive:
        raise PapersExit(f'RIS needs the rispy package, which is not installed: {_rispy_help()}')
    command = [sys.executable, '-m', 'pip', 'install', 'rispy']
    # the question and the pip output go to stderr: the standard output may be the RIS of `papers list`
    print(f'RIS needs the rispy package: install it now (`{" ".join(command)}`)? [y/N] ', end='',
          file=sys.stderr, flush=True)
    try:
        answer = input('')
    except EOFError:
        answer = ''
    if answer.strip().lower() not in ('y', 'yes'):
        raise PapersExit(f'rispy not installed: {_rispy_help()}')
    result = subprocess.run(command, stdout=sys.stderr, stderr=sys.stderr)
    if result.returncode != 0:
        raise PapersExit(f'`{" ".join(command)}` failed: {_rispy_help()}')
    importlib.invalidate_caches()
    try:
        import rispy
    except ImportError as error:
        raise PapersExit(f'rispy was installed but cannot be imported ({error}): {_rispy_help()}')
    return rispy


# helpers
# =======

# the characters of LaTeX markup: a value without them is text already
_LATEX_CHARS = set('\\{}$~%&')


@functools.lru_cache(maxsize=None)
def _latex_converter():
    # built once: building one rebuilds the table of LaTeX macros (most of the time of a CSL export)
    from pylatexenc.latex2text import LatexNodes2Text
    return LatexNodes2Text(math_mode='verbatim')


def _latex_to_unicode(value):
    "a bibtex value as unicode text: LaTeX commands decoded, braces removed"
    if not value:
        return value
    if _LATEX_CHARS.isdisjoint(value):
        return value.strip()
    try:
        return _latex_converter().latex_to_text(value).strip()
    except Exception as error:  # pragma: no cover - pylatexenc is a dependency of bibtexparser
        logger.debug(f'latex to unicode: {error}: {value!r}')
        return value.replace('{', '').replace('}', '')


def _split_depth0(value, sep_regex):
    "split a bibtex value on a separator outside braces"
    parts, depth, start = [], 0, 0
    pattern = re.compile(sep_regex)
    i = 0
    while i < len(value):
        c = value[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        elif depth == 0:
            m = pattern.match(value, i)
            if m:
                parts.append(value[start:i])
                start = i = m.end()
                continue
        i += 1
    parts.append(value[start:])
    return [p.strip() for p in parts]


def _is_braced(s):
    "whether the whole string is one braced group, e.g. {World Health Organization}"
    if not (s.startswith('{') and s.endswith('}')):
        return False
    depth = 0
    for i, c in enumerate(s):
        depth += c == '{'
        depth -= c == '}'
        if depth == 0 and i < len(s) - 1:
            return False
    return True


def _is_particle(token):
    "von, van der, de la...: a token that starts with a lowercase letter"
    t = token.lstrip('{\\')
    return bool(t) and t[0].islower()


def parse_bibtex_name(name):
    """a bibtex name as a dict of CSL name parts: family, given,
    non-dropping-particle, suffix; or literal for a name in braces
    (an organization)"""
    name = name.strip()
    if _is_braced(name):
        return {'literal': _latex_to_unicode(name[1:-1])}
    parts = _split_depth0(name, r',')
    if len(parts) == 1:
        tokens = _split_depth0(name, r'\s+')
        if len(tokens) == 1:
            return {'family': _latex_to_unicode(tokens[0])}
        # First von Last: von is from the first to the last lowercase word before the last word
        lower = [i for i, t in enumerate(tokens[:-1]) if _is_particle(t)]
        if lower:
            given, particle, family = tokens[:lower[0]], tokens[lower[0]:lower[-1] + 1], tokens[lower[-1] + 1:]
        else:
            given, particle, family = tokens[:-1], [], tokens[-1:]
        d = {'family': ' '.join(family), 'given': ' '.join(given)}
        if particle:
            d['non-dropping-particle'] = ' '.join(particle)
    else:
        last = parts[0]
        suffix = parts[1] if len(parts) == 3 else ''
        given = parts[-1]
        tokens = _split_depth0(last, r'\s+')
        particle = []
        while len(tokens) > 1 and _is_particle(tokens[0]):
            particle.append(tokens.pop(0))
        d = {'family': ' '.join(tokens), 'given': given}
        if particle:
            d['non-dropping-particle'] = ' '.join(particle)
        if suffix:
            d['suffix'] = suffix
    return {k: _latex_to_unicode(v) for k, v in d.items() if v}


def parse_bibtex_names(value):
    "the names of a bibtex author or editor field, as CSL name dicts"
    if not value or not value.strip():
        return []
    return [parse_bibtex_name(n) for n in _split_depth0(value.strip(), r'\s+and\s+') if n]


def format_bibtex_name(name):
    "a CSL name dict as a bibtex name: von Family, Suffix, Given (an organization in braces)"
    if isinstance(name, str):
        name = {'literal': name}
    if name.get('literal') and not name.get('family'):
        return '{' + name['literal'] + '}'
    family = name.get('family', '')
    particle = name.get('non-dropping-particle', '')
    if particle:
        family = particle + ' ' + family
    given = ' '.join(x for x in [name.get('given', ''), name.get('dropping-particle', '')] if x)
    suffix = name.get('suffix', '')
    if suffix:
        return f'{family}, {suffix}, {given}'
    return f'{family}, {given}' if given else family


def format_bibtex_names(names):
    return ' and '.join(format_bibtex_name(n) for n in names or [] if n)


_MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']


def parse_month(value):
    "a bibtex month (jan, January, 5, 05) as a number, or None"
    v = str(value or '').strip().strip('{}').lower()
    if v.isdigit() and 1 <= int(v) <= 12:
        return int(v)
    if v[:3] in _MONTHS:
        return _MONTHS.index(v[:3]) + 1
    return None


def _date_parts(text):
    "the year, month, day numbers of a date text: 2013, 2013-05, 2013/05/02/, 2013-05-02T00:00"
    m = re.match(r'\s*(\d{4})(?:[-/](\d{1,2}))?(?:[-/](\d{1,2}))?', str(text or ''))
    if not m:
        return []
    return [int(x) for x in m.groups() if x and int(x) > 0]


def _entry_date_parts(e):
    "year, month, day of an entry (its year and month fields, else its biblatex date field)"
    year = get_entry_val(e, 'year', '').strip().strip('{}')
    if year.isdigit():
        parts = [int(year)]
        month = parse_month(get_entry_val(e, 'month', ''))
        if month:
            parts.append(month)
        return parts
    return _date_parts(get_entry_val(e, 'date', ''))


def _fields_from_parts(parts):
    fields = {}
    if parts:
        fields['year'] = str(parts[0])
    if len(parts) > 1:
        fields['month'] = str(parts[1])
    return fields


def _pages_to_bibtex(page):
    "123-130 (CSL, RIS) as 123--130 (bibtex)"
    page = str(page or '').strip()
    parts = [p for p in re.split(r'\s*(?:--|-|–|—)\s*', page) if p]
    if len(parts) == 2:
        return '--'.join(parts)
    return page


def _split_pages(pages):
    "the first and last pages of a bibtex pages field"
    parts = [p for p in re.split(r'\s*(?:--|-|–|—)\s*', pages.strip()) if p]
    if not parts:
        return '', ''
    return parts[0], (parts[1] if len(parts) > 1 else '')


_DOI_PREFIX = re.compile(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', re.I)


def _clean_doi(doi):
    return _DOI_PREFIX.sub('', str(doi or '').strip())


# the bibtex key of an imported entry: kept if it looks like a key (not a
# URL, as the item ids of Zotero, not a number, as the record numbers of EndNote)
_KEY_RE = re.compile(r'^[A-Za-z][\w:.+\-]*$')


def usable_key(key):
    key = str(key or '').strip()
    return key if _KEY_RE.match(key) and not re.match(r'^ITEM-\d+$', key) else ''


def _file_paths(value):
    """the paths of the file links of an imported item: a list, or a text
    separated by ; (bibtex-like description:path:type is accepted).
    file:// URIs are converted; links that are not files (http, EndNote
    internal-pdf://) are left out"""
    if not value:
        return []
    if isinstance(value, str):
        value = [v for v in value.split(';')]
    paths = []
    for v in value:
        v = str(v).strip()
        if not v:
            continue
        if v.startswith('file://'):
            v = unquote(urlparse(v).path)
        elif re.match(r'^[a-z][a-z0-9+.\-]*://', v, re.I):
            logger.warning(f'file link left out (not a local file): {v}')
            continue
        elif v.count(':') >= 2 and not re.match(r'^[A-Za-z]:[\\/]', v):
            v = ':'.join(v.split(':')[1:-1])  # description:path:type
        paths.append(v)
    return paths


def _entry(entry_type, key, fields, files=()):
    fields = {k: v for k, v in fields.items() if v not in (None, '')}
    if files:
        fields['file'] = format_file(list(files))
    return Entry(entry_type=entry_type, key=key, fields=[Field(k, str(v)) for k, v in fields.items()])


def _unicode_fields(e):
    "the fields of an entry, as unicode text (urls, DOIs and files as they are)"
    raw = ('url', 'doi', 'file', 'eprint', 'isbn', 'issn')
    return {f.key.lower(): (f.value if f.key.lower() in raw else _latex_to_unicode(f.value))
            for f in e.fields if f.value not in (None, '')}


# CSL-JSON
# ========

BIBTEX_TO_CSL_TYPE = {
    'article': 'article-journal',
    'book': 'book',
    'booklet': 'pamphlet',
    'inbook': 'chapter',
    'incollection': 'chapter',
    'inproceedings': 'paper-conference',
    'conference': 'paper-conference',
    'proceedings': 'book',
    'phdthesis': 'thesis',
    'mastersthesis': 'thesis',
    'thesis': 'thesis',
    'techreport': 'report',
    'report': 'report',
    'manual': 'report',
    'misc': 'document',
    'online': 'webpage',
    'electronic': 'webpage',
    'www': 'webpage',
    'dataset': 'dataset',
    'software': 'software',
    'unpublished': 'manuscript',
    'patent': 'patent',
}

CSL_TO_BIBTEX_TYPE = {
    'article-journal': 'article',
    'article-magazine': 'article',
    'article-newspaper': 'article',
    'article': 'misc',  # a preprint, working paper
    'book': 'book',
    'pamphlet': 'booklet',
    'chapter': 'incollection',
    'entry-encyclopedia': 'incollection',
    'entry-dictionary': 'incollection',
    'paper-conference': 'inproceedings',
    'thesis': 'phdthesis',
    'report': 'techreport',
    'webpage': 'online',
    'post': 'online',
    'post-weblog': 'online',
    'dataset': 'dataset',
    'software': 'software',
    'manuscript': 'unpublished',
    'patent': 'patent',
    'document': 'misc',
}

# fields with the same meaning, no conversion (bibtex name: CSL name)
_CSL_SIMPLE = {
    'title': 'title',
    'volume': 'volume',
    'doi': 'DOI',
    'url': 'URL',
    'isbn': 'ISBN',
    'issn': 'ISSN',
    'publisher': 'publisher',
    'address': 'publisher-place',
    'abstract': 'abstract',
    'note': 'note',
    'edition': 'edition',
    'language': 'language',
    'series': 'collection-title',
    'pmid': 'PMID',
    'pmcid': 'PMCID',
}


def entry_to_csl(e, files=()):
    "a CSL-JSON item (a dict) of a bibtex entry; `files`: the paths of its file links, as written"
    f = _unicode_fields(e)
    entry_type = e.entry_type.lower()
    csl_type = BIBTEX_TO_CSL_TYPE.get(entry_type, 'document')
    if entry_type == 'misc' and f.get('eprint'):
        csl_type = 'article'
    item = {'id': e.key, 'citation-key': e.key, 'type': csl_type}
    for name in ('author', 'editor', 'translator'):
        names = parse_bibtex_names(get_entry_val(e, name, ''))
        if names:
            item[name] = names
    for bib, csl in _CSL_SIMPLE.items():
        if f.get(bib):
            item[csl] = f[bib]
    if 'doi' in f:
        item['DOI'] = _clean_doi(f['doi'])
    container = f.get('journal') or f.get('booktitle')
    if container:
        item['container-title'] = container
    number = f.get('issue') or f.get('number')
    if number:
        item['issue' if csl_type == 'article-journal' or f.get('issue') else 'number'] = number
    if f.get('pages'):
        item['page'] = _pages_to_bibtex(f['pages']).replace('--', '-')
    if not f.get('publisher'):
        for name in ('school', 'institution', 'organization'):
            if f.get(name):
                item['publisher'] = f[name]
                break
    if entry_type == 'phdthesis':
        item['genre'] = 'PhD thesis'
    elif entry_type == 'mastersthesis':
        item['genre'] = "Master's thesis"
    elif f.get('type') and csl_type in ('thesis', 'report'):
        item['genre'] = f['type']
    if f.get('keywords'):
        item['keyword'] = ', '.join(w.strip() for w in f['keywords'].split(',') if w.strip())
    parts = _entry_date_parts(e)
    if parts:
        item['issued'] = {'date-parts': [parts]}
    elif f.get('year'):
        item['issued'] = {'literal': f['year']}
    if f.get('urldate') and _date_parts(f['urldate']):
        item['accessed'] = {'date-parts': [_date_parts(f['urldate'])]}
    if files:
        item['custom'] = {'file': list(files)}
    return item


def _csl_date(value):
    "the year, month... of a CSL date: {date-parts: [[y, m, d]]}, {raw: ...}, {literal: ...} or an EDTF text"
    if isinstance(value, dict):
        dp = value.get('date-parts')
        if dp and dp[0]:
            try:
                return [int(x) for x in dp[0] if str(x).strip()]
            except (TypeError, ValueError):
                pass
        return _date_parts(value.get('raw') or value.get('literal') or '')
    return _date_parts(value)


def _csl_text(v):
    if isinstance(v, list):  # some exports (Crossref) give titles as lists
        v = v[0] if v else ''
    return '' if v is None else str(v)


def csl_to_entry(item):
    "a bibtex entry of a CSL-JSON item (its key is empty if the item has none usable)"
    csl_type = item.get('type', 'document')
    entry_type = CSL_TO_BIBTEX_TYPE.get(csl_type, 'misc')
    if csl_type == 'thesis' and 'master' in str(item.get('genre', '')).lower():
        entry_type = 'mastersthesis'
    fields = {}
    for name in ('author', 'editor', 'translator'):
        if item.get(name):
            fields[name] = format_bibtex_names(item[name])
    for bib, csl in _CSL_SIMPLE.items():
        if item.get(csl) not in (None, ''):
            fields[bib] = _csl_text(item[csl])
    if 'doi' in fields:
        fields['doi'] = _clean_doi(fields['doi'])
    container = _csl_text(item.get('container-title'))
    if container:
        fields['journal' if entry_type in ('article', 'misc', 'online') else 'booktitle'] = container
    number = item.get('issue') or item.get('number')
    if number not in (None, ''):
        fields['number'] = _csl_text(number)
    if item.get('page'):
        fields['pages'] = _pages_to_bibtex(item['page'])
    if fields.get('publisher'):
        if entry_type in ('phdthesis', 'mastersthesis'):
            fields['school'] = fields.pop('publisher')
        elif entry_type == 'techreport':
            fields['institution'] = fields.pop('publisher')
    if item.get('genre') and entry_type in ('techreport',):
        fields['type'] = _csl_text(item['genre'])
    keywords = item.get('keyword')
    if keywords:
        if isinstance(keywords, list):
            keywords = ', '.join(keywords)
        fields['keywords'] = ', '.join(w.strip() for w in re.split(r'[,;]', str(keywords)) if w.strip())
    fields.update(_fields_from_parts(_csl_date(item.get('issued'))))
    accessed = _csl_date(item.get('accessed'))
    if accessed:
        fields['urldate'] = '-'.join(f'{x:02d}' for x in accessed)
    files = _file_paths(item.get('file')) + _file_paths((item.get('custom') or {}).get('file'))
    key = usable_key(item.get('citation-key')) or usable_key(item.get('id'))
    return _entry(entry_type, key, fields, files)


def dumps_csl(entries, files=lambda e: ()):
    return json.dumps([entry_to_csl(e, files(e)) for e in entries], indent=2, ensure_ascii=False) + '\n'


def loads_csl(text):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f'not a CSL-JSON file: {error}')
    if isinstance(data, dict):
        data = data.get('items', [data])  # one item, or {"items": [...]}
    if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
        raise ValueError('not a CSL-JSON file: a list of items is expected')
    return [csl_to_entry(item) for item in data]


# RIS
# ===

BIBTEX_TO_RIS_TYPE = {
    'article': 'JOUR',
    'book': 'BOOK',
    'booklet': 'PAMP',
    'inbook': 'CHAP',
    'incollection': 'CHAP',
    'inproceedings': 'CPAPER',
    'conference': 'CPAPER',
    'proceedings': 'CONF',
    'phdthesis': 'THES',
    'mastersthesis': 'THES',
    'thesis': 'THES',
    'techreport': 'RPRT',
    'report': 'RPRT',
    'manual': 'RPRT',
    'misc': 'GEN',
    'online': 'ELEC',
    'electronic': 'ELEC',
    'www': 'ELEC',
    'dataset': 'DATA',
    'software': 'COMP',
    'unpublished': 'UNPB',
    'patent': 'PAT',
}

RIS_TO_BIBTEX_TYPE = {
    'JOUR': 'article',
    'JFULL': 'article',
    'EJOUR': 'article',
    'MGZN': 'article',
    'NEWS': 'article',
    'INPR': 'article',
    'BOOK': 'book',
    'EBOOK': 'book',
    'EDBOOK': 'book',
    'PAMP': 'booklet',
    'CHAP': 'incollection',
    'ECHAP': 'incollection',
    'ENCYC': 'incollection',
    'DICT': 'incollection',
    'CPAPER': 'inproceedings',
    'CONF': 'inproceedings',
    'THES': 'phdthesis',
    'RPRT': 'techreport',
    'GOVDOC': 'techreport',
    'GEN': 'misc',
    'ELEC': 'online',
    'BLOG': 'online',
    'DATA': 'dataset',
    'DBASE': 'dataset',
    'COMP': 'software',
    'UNPB': 'unpublished',
    'MANSCPT': 'unpublished',
    'PAT': 'patent',
}

# rispy has no field for the editors (ED): it is added to its mapping, and
# the tags that can repeat are read as lists
def _ris_options(rispy):
    mapping = dict(rispy.TAG_KEY_MAPPING)
    mapping['ED'] = 'editors'
    list_tags = list(rispy.LIST_TYPE_TAGS) + ['ED', 'L1', 'SN']
    return {'mapping': mapping, 'list_tags': list_tags}


def _ris_name(name):
    "a CSL name dict as a RIS name: Family, Given, Suffix (an organization as it is)"
    if name.get('literal') and not name.get('family'):
        return name['literal']
    family = ' '.join(x for x in [name.get('non-dropping-particle', ''), name.get('family', '')] if x)
    parts = [family, name.get('given', '')]
    if name.get('suffix'):
        parts.append(name['suffix'])
    return ', '.join(p for p in parts if p) if parts[1] or len(parts) > 2 else family


def _bibtex_name_of_ris(name):
    "a RIS name (Family, Given, Suffix) as a bibtex name; a name without comma is an organization"
    name = name.strip()
    if ',' not in name:
        return name if ' ' not in name else '{' + name + '}'
    parts = [p.strip() for p in name.split(',')]
    if len(parts) >= 3 and parts[2]:
        return f'{parts[0]}, {parts[2]}, {parts[1]}'
    return f'{parts[0]}, {parts[1]}' if parts[1] else parts[0]


def entry_to_ris(e, files=()):
    "a RIS record (a dict of rispy field names) of a bibtex entry; `files`: the paths of its file links"
    f = _unicode_fields(e)
    entry_type = e.entry_type.lower()
    ref = {'type_of_reference': BIBTEX_TO_RIS_TYPE.get(entry_type, 'GEN'), 'id': e.key}
    authors = parse_bibtex_names(get_entry_val(e, 'author', ''))
    if authors:
        ref['authors'] = [_ris_name(n) for n in authors]
    editors = parse_bibtex_names(get_entry_val(e, 'editor', ''))
    if editors:
        ref['editors'] = [_ris_name(n) for n in editors]
    if f.get('title'):
        ref['title'] = f['title']
    container = f.get('journal') or f.get('booktitle')
    if container:
        ref['secondary_title'] = container
    if f.get('series'):
        ref['tertiary_title'] = f['series']
    parts = _entry_date_parts(e)
    if parts:
        ref['year'] = str(parts[0])
        if len(parts) > 1:
            ref['date'] = '/'.join(f'{x:02d}' if i else str(x) for i, x in enumerate(parts)) + '/'
    elif f.get('year'):
        ref['year'] = f['year']
    if f.get('volume'):
        ref['volume'] = f['volume']
    number = f.get('issue') or f.get('number')
    if number:
        ref['number'] = number
    if f.get('pages'):
        start, end = _split_pages(f['pages'])
        if start:
            ref['start_page'] = start
        if end:
            ref['end_page'] = end
    if f.get('doi'):
        ref['doi'] = _clean_doi(f['doi'])
    if f.get('url'):
        ref['urls'] = [f['url']]
    numbers = [f[k] for k in ('isbn', 'issn') if f.get(k)]
    if numbers:
        ref['issn'] = numbers
    publisher = f.get('publisher') or f.get('school') or f.get('institution') or f.get('organization')
    if publisher:
        ref['publisher'] = publisher
    if f.get('address'):
        ref['place_published'] = f['address']
    if f.get('abstract'):
        ref['abstract'] = f['abstract']
    if f.get('keywords'):
        ref['keywords'] = [w.strip() for w in f['keywords'].split(',') if w.strip()]
    if f.get('note'):
        ref['notes'] = [f['note']]
    if f.get('edition'):
        ref['edition'] = f['edition']
    if f.get('language'):
        ref['language'] = f['language']
    if f.get('type') and entry_type in ('techreport', 'report', 'phdthesis', 'mastersthesis', 'thesis'):
        ref['type_of_work'] = f['type']
    if files:
        ref['file_attachments1'] = list(files)
    return ref


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _first(ref, *names):
    for name in names:
        for v in _as_list(ref.get(name)):
            if str(v).strip():
                return str(v).strip()
    return ''


def ris_to_entry(ref):
    "a bibtex entry of a RIS record (as rispy reads it, see _ris_options)"
    ris_type = str(ref.get('type_of_reference', 'GEN')).strip().upper()
    entry_type = RIS_TO_BIBTEX_TYPE.get(ris_type, 'misc')
    fields = {}
    authors = _as_list(ref.get('authors')) + _as_list(ref.get('first_authors'))
    if authors:
        fields['author'] = ' and '.join(_bibtex_name_of_ris(a) for a in authors if a.strip())
    editors = _as_list(ref.get('editors'))
    if not editors and ris_type in ('CHAP', 'ECHAP', 'CPAPER', 'CONF', 'BOOK', 'EDBOOK', 'ENCYC', 'DICT'):
        editors = _as_list(ref.get('secondary_authors'))  # A2: the editors, in EndNote exports
    if editors:
        fields['editor'] = ' and '.join(_bibtex_name_of_ris(a) for a in editors if a.strip())
    fields['title'] = _first(ref, 'title', 'primary_title')
    container = _first(ref, 'secondary_title', 'alternate_title3', 'journal_name', 'alternate_title2',
                       'alternate_title1')
    if container:
        fields['journal' if entry_type in ('article', 'misc', 'online') else 'booktitle'] = container
    if ref.get('tertiary_title'):
        fields['series'] = _first(ref, 'tertiary_title')
    parts = _date_parts(_first(ref, 'year', 'publication_year', 'date'))
    date = _date_parts(_first(ref, 'date', 'publication_year'))
    if parts and len(date) > 1 and date[0] == parts[0]:
        parts = date
    fields.update(_fields_from_parts(parts))
    fields['volume'] = _first(ref, 'volume')
    fields['number'] = _first(ref, 'number')
    start, end = _first(ref, 'start_page'), _first(ref, 'end_page')
    if start and end and start != end:
        fields['pages'] = f'{start}--{end}'
    elif start:
        fields['pages'] = _pages_to_bibtex(start)
    fields['doi'] = _clean_doi(_first(ref, 'doi'))
    urls = [u for u in _as_list(ref.get('urls')) if u.strip() and not _DOI_PREFIX.match(u.strip())]
    if urls:
        fields['url'] = urls[0].strip()
    elif not fields['doi'] and _as_list(ref.get('urls')):
        fields['doi'] = _clean_doi(_as_list(ref.get('urls'))[0])
    for sn in _as_list(ref.get('issn')):
        digits = re.sub(r'[^0-9Xx]', '', sn.split()[0] if sn.split() else '')
        name = 'issn' if len(digits) == 8 else 'isbn'
        if name not in fields:
            fields[name] = sn.strip()
    publisher = _first(ref, 'publisher')
    if publisher:
        fields[{'phdthesis': 'school', 'techreport': 'institution'}.get(entry_type, 'publisher')] = publisher
    fields['address'] = _first(ref, 'place_published')
    fields['abstract'] = _first(ref, 'abstract', 'notes_abstract')
    keywords = []
    for k in _as_list(ref.get('keywords')):
        keywords.extend(w.strip() for w in re.split(r'[;,]', k) if w.strip())
    if keywords:
        fields['keywords'] = ', '.join(keywords)
    notes = [n.strip() for n in _as_list(ref.get('notes')) if n.strip()]
    if notes:
        fields['note'] = '; '.join(notes)
    fields['edition'] = _first(ref, 'edition')
    fields['language'] = _first(ref, 'language')
    if entry_type in ('techreport', 'phdthesis'):
        fields['type'] = _first(ref, 'type_of_work')
    files = _file_paths(_as_list(ref.get('file_attachments1')))
    return _entry(entry_type, usable_key(_first(ref, 'id')), fields, files)


def dumps_ris(entries, files=lambda e: (), rispy=None):
    rispy = rispy or load_rispy()

    class Writer(rispy.RisWriter):
        "standard RIS: no record number line before each record"
        def set_header(self, count):
            return ''

    refs = [entry_to_ris(e, files(e)) for e in entries]
    return rispy.dumps(refs, implementation=Writer, **_ris_options(rispy))


def loads_ris(text, rispy=None):
    rispy = rispy or load_rispy()
    text = text.lstrip('﻿').replace('\r\n', '\n')
    refs = rispy.loads(text, skip_unknown_tags=True, **_ris_options(rispy))
    if not refs and text.strip():
        raise ValueError('not a RIS file: no record found (a record starts with TY  - )')
    return [ris_to_entry(ref) for ref in refs]


# BibJSON
# =======
# the convention of the Open Knowledge Foundation for bibtex records in JSON
# (https://github.com/rufuspollock-okfn/bibjson): a collection
# {"metadata": {...}, "records": [...]}; a record has the bibtex fields as
# they are (LaTeX included: nothing is lost), with "type" and "id" for the
# entry type and key, and the structures BibJSON gives some of them: author
# and editor are lists of {"name": ...}, journal is {"name": ...}. The file
# links are a list of paths, "file".

_BIBJSON_NAMES = ('author', 'editor')
_BIBJSON_SKIPPED = ('type', 'id', 'cid', 'collection', 'file', 'identifier', 'link', 'license')
# a bibtex field with the name of a key of BibJSON (e.g. the type of a techreport, `type = {Working
# paper}`) goes in a namespaced key, `bibtex:type`, declared in the metadata of the collection (as the
# BibJSON convention says for additional keys): the record's own type and id stay the entry type and key
_BIBJSON_NAMESPACE = 'bibtex'
_BIBJSON_NAMESPACE_URL = 'https://www.bibtex.org/Format/'


def entry_to_bibjson(e, files=()):
    record = {'type': e.entry_type, 'id': e.key}
    for field in e.fields:
        if field.key == 'file':
            continue
        if field.key in _BIBJSON_NAMES:
            record[field.key] = [{'name': name} for name in _split_depth0(field.value, r'\s+and\s+')]
        elif field.key == 'journal':
            record['journal'] = {'name': field.value}
        elif field.key in _BIBJSON_SKIPPED:
            record[f'{_BIBJSON_NAMESPACE}:{field.key}'] = field.value
        else:
            record[field.key] = field.value
    if files:
        record['file'] = list(files)
    return record


def _bibjson_text(value):
    "a value of a record as a bibtex value: the names of objects, lists joined"
    if isinstance(value, dict):
        return _bibjson_text(value.get('name', ''))
    if isinstance(value, list):
        return ', '.join(_bibjson_text(v) for v in value)
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def bibjson_to_entry(record):
    fields = {}
    for name, value in record.items():
        if name.startswith(_BIBJSON_NAMESPACE + ':'):
            name = name[len(_BIBJSON_NAMESPACE) + 1:]  # a bibtex field with the name of a BibJSON key
        elif name.startswith('_') or name in _BIBJSON_SKIPPED:
            continue
        if value is None:
            continue
        if name in _BIBJSON_NAMES and isinstance(value, list):
            fields[name] = ' and '.join(_bibjson_text(v) for v in value)
        else:
            fields[name] = _bibjson_text(value)
    if 'doi' not in fields:  # the DOI of BibJSON identifiers: [{"type": "doi", "id": ...}]
        doi = next((i.get('id') for i in record.get('identifier') or []
                    if isinstance(i, dict) and str(i.get('type', '')).lower() == 'doi'), None)
        if doi:
            fields['doi'] = _clean_doi(doi)
    key = usable_key(record.get('id')) or usable_key(record.get('cid'))
    return _entry(str(record.get('type') or 'misc').lower(), key, fields, _file_paths(record.get('file')))


def dumps_bibjson(entries, files=lambda e: ()):
    records = [entry_to_bibjson(e, files(e)) for e in entries]
    metadata = {'records': len(records)}
    prefix = _BIBJSON_NAMESPACE + ':'
    if any(name.startswith(prefix) for record in records for name in record):
        metadata['namespace'] = {_BIBJSON_NAMESPACE: _BIBJSON_NAMESPACE_URL}
    collection = {'metadata': metadata, 'records': records}
    return json.dumps(collection, indent=2, ensure_ascii=False) + '\n'


def loads_bibjson(text):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f'not a BibJSON file: {error}')
    if isinstance(data, dict):
        data = data.get('records', [data])  # a collection, or one record
    if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
        raise ValueError('not a BibJSON file: a collection {"records": [...]} or a list of records is expected')
    return [bibjson_to_entry(record) for record in data]


# any format
# ==========

_DUMPS = {'ris': dumps_ris, 'csl-json': dumps_csl, 'bibjson': dumps_bibjson}
_LOADS = {'ris': loads_ris, 'csl-json': loads_csl, 'bibjson': loads_bibjson}


def dumps(entries, fmt, files=lambda e: ()):
    """the entries as a text in format `fmt` (other than bibtex; `files`:
    entry -> paths of its file links, as written)"""
    if fmt not in _DUMPS:
        raise ValueError(f'unknown format: {fmt}')
    return _DUMPS[fmt](entries, files)


def loads(text, fmt):
    "the entries of a text in format `fmt` (other than bibtex), as bibtex entries"
    if fmt not in _LOADS:
        raise ValueError(f'unknown format: {fmt}')
    return _LOADS[fmt](text)


def read_file(path, fmt):
    with open(path, encoding='utf-8-sig') as f:
        return loads(f.read(), fmt)
