"""
Key and file name formatting
"""
import os
import re
from slugify import slugify
from papers.encoding import family_names
from papers.entries import get_entry_val

def title_words(words, maxlength=30, minwordlen=3, n=100, sep='-'):
    """the first `n` words of at least `minwordlen` characters, without the
    last words that make them longer than `maxlength` once joined with `sep`:
    a hard limit. At least one word is kept, cut to `maxlength` if needed."""
    words = [word for word in words if len(word) >= minwordlen][:n]
    while len(words) > 1 and len(sep.join(words)) > maxlength:
        words.pop()
    if words and len(words[0]) > maxlength:
        words[0] = words[0][:maxlength]
    return words

def listtag(words, maxlength=30, minwordlen=3, n=100, sep='-'):
    "the words of title_words joined with `sep`"
    return sep.join(title_words(words, maxlength, minwordlen, n, sep))

def _cite_author(names):
    if len(names) >= 3:
        return names[0] + ' et al'
    elif len(names) == 2:
        return ' and '.join(names)
    else:
        return names[0]

UNKNOWN_AUTHOR = 'unknown'
UNKNOWN_YEAR = '0000'
UNKNOWN_JOURNAL = None
UNKNOWN_TITLE = ""

def path_safe(value):
    """`value` without path separators (and not '.' or '..'), so that a field
    of an entry cannot make a file name point outside the files directory"""
    if value is None:
        return value
    value = str(value)
    for sep in ('/', '\\', '\0'):
        value = value.replace(sep, '-')
    if value and not value.strip('.'):
        value = '-' * len(value)
    return value

# the longest name (in bytes, as UTF-8) of a file or folder that papers names
# after an entry: 255 is the limit of most file systems, minus room for the
# -2, -3... suffix of a name already taken
MAX_NAME_BYTES = 250
# characters that Windows does not accept in a file name ('/' separates the
# folders of the template, '\\' is replaced in the values, see path_safe)
_FORBIDDEN = re.compile(r'[<>:"|?*\x00-\x1f]')
_RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}


def cut_bytes(text, size):
    "the start of `text` that is at most `size` bytes as UTF-8"
    return text.encode('utf-8')[:size].decode('utf-8', errors='ignore')


def safe_file_name(name):
    """a file name made from a template, valid on every system: in each
    folder of it, the characters that Windows forbids replaced with '-', no
    trailing dot or space, '-' after a reserved name of Windows (CON, NUL...),
    and at most MAX_NAME_BYTES bytes"""
    parts = []
    for part in name.split('/'):
        if part not in ('', '.', '..'):
            part = cut_bytes(_FORBIDDEN.sub('-', part), MAX_NAME_BYTES).rstrip('. ') or '-'
            first, dot, rest = part.partition('.')
            if first.upper() in _RESERVED:
                part = cut_bytes(first + '-' + dot + rest, MAX_NAME_BYTES)
        parts.append(part)
    return '/'.join(parts)


def fit_name(path):
    """`path` with its file name (extension included) cut to MAX_NAME_BYTES
    bytes, keeping the extension"""
    head, name = os.path.split(path)
    stem, ext = os.path.splitext(name)
    if len(name.encode('utf-8')) <= MAX_NAME_BYTES:
        return path
    stem = cut_bytes(stem, MAX_NAME_BYTES - len(ext.encode('utf-8'))).rstrip('. ') or '-'
    return os.path.join(head, stem + ext)


def make_template_fields(
    entry,
    author_num=2,
    title_word_num=100,
    title_word_size=1,
    title_length=100,
    author_sep="_",
    title_sep="-",
    **ignore,
):
    """
    Available fields in output are explicitly listed here, and this is the single source of truth for these.
    - author : slugified author names (lower case) separated by {author_sep} ('_' by default), with max {author_num} authors
    - Author : same as author but title case (first letter capitalized)
    - AUTHOR : same as author but upper case
    - authorX: first; first and second; first et al
    - journal: journal name
    (the values of journal, year, key, ID and doi have their path separators
    replaced with '-': see path_safe)
    - title : normalized title in lower case, separated by {title_sep} ('-' by default) with max {title_word_num} words
    - Title: same as title by with capitalized words
    - year
    - key, ID : bibtex key
    - doi : bibtex DOI
    - doi- : slugified doi (for use in filenames)
    Each one of these needs a specific, explicit assignment below.
    """
    _names = family_names(get_entry_val(entry, "author", UNKNOWN_AUTHOR).lower())
    _names = [slugify(nm) for nm in _names]
    author = author_sep.join([nm for nm in _names[:author_num]])
    Author = author_sep.join([nm.capitalize() for nm in _names[:author_num]])
    AuthorX = _cite_author([nm.capitalize() for nm in _names]).replace(" ", author_sep)
    authorX = AuthorX.lower()

    # a thing that's not a bibtex article won't have a journal
    journal = path_safe(get_entry_val(entry, "journal", UNKNOWN_JOURNAL))

    year = path_safe(get_entry_val(entry, "year", UNKNOWN_YEAR))

    if not title_word_num or not get_entry_val(entry, "title", ""):
        title = UNKNOWN_TITLE
        Title = UNKNOWN_TITLE
    else:
        titlewords = slugify(entry["title"]).split('-')
        _titles = title_words(
            titlewords,
            n=title_word_num,
            minwordlen=title_word_size,
            maxlength=title_length,
            sep=title_sep,
        )
        title = title_sep.join(_titles)
        Title = title_sep.join(w.capitalize() for w in _titles)

    return {
        "author": author,
        "Author": Author,
        "AUTHOR": author.upper(),
        "authorX": authorX,
        "AuthorX": AuthorX,
        "journal" : journal,
        "year": year,
        "title": title,
        "Title": Title,
        "key": path_safe(get_entry_val(entry, "ID", "")),
        "ID": path_safe(get_entry_val(entry, "ID", "")),
        "doi": path_safe(get_entry_val(entry, "doi", "")),
        "doi_": slugify(get_entry_val(entry, "doi", "")),
        "doi_or_id": slugify(get_entry_val(entry, "doi", get_entry_val(entry, "ID", ""))),
    }


class TemplateError(ValueError):
    "a name or key template that cannot be formatted"


PLACEHOLDERS = list(make_template_fields({}))


def format_template(template, fields, kind='name'):
    """`template` formatted with `fields` (see make_template_fields); an
    unknown placeholder is a TemplateError that lists the available ones"""
    try:
        return template.format(**fields)
    except (KeyError, IndexError) as error:
        name = error.args[0] if isinstance(error, KeyError) else ''
        available = ', '.join('{' + f + '}' for f in PLACEHOLDERS)
        raise TemplateError(f'unknown placeholder {{{name}}} in the {kind} template {template!r}; '
                            f'available: {available}') from None
    except ValueError as error:
        raise TemplateError(f'invalid {kind} template {template!r}: {error}') from None


class Format:
    """
    Store formatting info as python template formatted with str.format() method. See make_template_fields for available fields.


    Example
    -------
    To rename esd-4-11-2013.pdf as perrette_2013.pdf, template should be '{author}_{year}' with --name-author-num 1.
    If that happens to be the entry ID, 'ID' also works.
    To rename esd-4-11-2013.pdf as
    2013/Perrette2013-AScalingApproachToProjectRegionalSeaLevelRiseAndItsUncertainties.pdf,
    template should be '{year}/{Author}{year}-{Title}' with --name-author-num 1 (note the case).
    Entries are case-sensitive, so that:
        'author' generates 'perrette'
        'Author' generates 'Perrette'
        'AUTHOR' generates 'PERRETTE'
    any other case, like 'AuTHoR', will retrieve the field from 'e' with unaltered case.

    """
    def __init__(self, template, author_num=2, title_word_num=100, title_word_size=1, title_length=100,
                 author_sep="_", title_sep="-", unknown_strict=False, unknown_template=None, kind='name'):
        self.kind = kind  # name or key: for the errors
        self.template = template
        self.author_num = author_num
        self.author_sep = author_sep
        self.title_length = title_length
        self.title_sep = title_sep
        self.title_word_num = title_word_num
        self.title_word_size = title_word_size
        self.unknown_strict = unknown_strict
        self.unknown_template = unknown_template

    def is_unknown(self, entry):
        conditions = ( get_entry_val(entry, "author", UNKNOWN_AUTHOR) == UNKNOWN_AUTHOR, get_entry_val(entry, "year", UNKNOWN_YEAR) == UNKNOWN_YEAR, get_entry_val(entry, "title", UNKNOWN_TITLE) == UNKNOWN_TITLE)
        if self.unknown_strict:
            return all(conditions)
        else:
            return any(conditions)

    def render(self, **entry):
        fields = make_template_fields(entry, **vars(self))

        if self.unknown_template and self.is_unknown(entry):
            name = format_template(self.unknown_template, fields, self.kind + ' unknown')
        else:
            name = format_template(self.template, fields, self.kind)
        return safe_file_name(name) if self.kind == 'name' else name

    def __call__(self, entry):
        # Support both dict and bibtexparser v2 Entry (convert to dict for ** unpacking)
        entry = dict(entry.items()) if hasattr(entry, 'items') and not isinstance(entry, dict) else entry
        return self.render(**entry)


# the unknown-key fallback uses the slugified doi: a raw doi (slashes,
# parentheses, unicode...) makes for an invalid or unwieldy bibtex key
KEYFORMAT = Format(template='{author}{year}', author_num=2, author_sep="_", unknown_template="{doi_}", kind='key')
NAMEFORMAT = Format(template='{authorX}_{year}_{title}', author_sep="_", title_sep="-", unknown_template="unknown_{doi_or_id}")