"""
Key and file name formatting
"""
from normality import slugify, normalize
from papers.encoding import family_names

def listtag(words, maxlength=30, minwordlen=3, n=100, sep='-'):
    # preformat & filter words
    words = [word for word in words if len(word) >= minwordlen]
    while True:
        tag = sep.join(words[:n])
        n -= 1
        if len(tag) <= maxlength or n < 2:
            break
    return tag

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
    - title : normalized title in lower case, separated by {title_sep} ('-' by default) with max {title_word_num} words
    - Title: same as title by with capitalized words
    - year
    - ID : bibtex key
    - doi : bibtex DOI
    - doi- : slugified doi (for use in filenames)
    Each one of these needs a specific, explicit assignment below.
    """
    # names = bibtexparser.customization.getnames(entry.get('author','unknown').lower().split(' and '))
    _names = family_names(entry.get("author", UNKNOWN_AUTHOR).lower())
    _names = [slugify(nm) for nm in _names]
    author = author_sep.join([nm for nm in _names[:author_num]])
    Author = author_sep.join([nm.capitalize() for nm in _names[:author_num]])
    AuthorX = _cite_author([nm.capitalize() for nm in _names]).replace(" ", author_sep)
    authorX = AuthorX.lower()

    # a thing that's not a bibtex article won't have a journal
    journal = entry.get("journal", UNKNOWN_JOURNAL)

    year = str(entry.get("year", UNKNOWN_YEAR))

    if not title_word_num or not entry.get("title", ""):
        title = UNKNOWN_TITLE
        Title = UNKNOWN_TITLE
    else:
        titlewords = normalize(entry["title"]).lower().split()
        _titles = listtag(
            titlewords,
            n=title_word_num,
            minwordlen=title_word_size,
            maxlength=title_length,
            sep="*",
        ).split("*")
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
        "ID": entry.get("ID"),
        "doi": entry.get("doi"),
        "doi_": slugify(entry.get("doi", "")),
        "doi_or_id": slugify(entry.get("doi", entry.get("ID", ""))),
    }


class Format:
    """
    Store formatting info as python template formatted with str.format() method. See make_template_fields for available fields.


    Example
    -------
    To rename esd-4-11-2013.pdf as perrette_2013.pdf, template should be '{author}_{year}' with --name-nauthor 1.
    If that happens to be the entry ID, 'ID' also works.
    To rename esd-4-11-2013.pdf as
    2013/Perrette2013-AScalingApproachToProjectRegionalSeaLevelRiseAndItsUncertainties.pdf,
    template should be '{year}/{Author}{year}-{Title}' with --name-nauthor 1 (note the case).
    Entries are case-sensitive, so that:
        'author' generates 'perrette'
        'Author' generates 'Perrette'
        'AUTHOR' generates 'PERRETTE'
    any other case, like 'AuTHoR', will retrieve the field from 'e' with unaltered case.

    """
    # def __init__(self, template="{author}{year}{title}", author_num=2, title_word_num=5, author_sep="_", title_sep="-")
    def __init__(self, template, author_num=2, title_word_num=100, title_word_size=1, title_length=100,
                 author_sep="_", title_sep="-", unknown_strict=False, unknown_template=None):
        self.template = template
        self.author_num = author_num
        self.author_sep = author_sep
        self.title_length = title_length
        self.title_sep = title_sep
        self.title_word_num = title_word_num
        self.title_word_size = title_word_size
        self.unknown_strict = unknown_strict
        self.unknown_template = unknown_template

    def todict(self):
        return vars(self)

    def is_unknown(self, entry):
        conditions = ( entry.get("author", UNKNOWN_AUTHOR) == UNKNOWN_AUTHOR, entry.get("year", UNKNOWN_YEAR) == UNKNOWN_YEAR, entry.get("title", UNKNOWN_TITLE) == UNKNOWN_TITLE)
        if self.unknown_strict:
            return all(conditions)
        else:
            return any(conditions)

    def render(self, **entry):
        fields = make_template_fields(entry, **vars(self))

        if self.unknown_template and self.is_unknown(entry):
            return self.unknown_template.format(**fields)

        return self.template.format(**fields)

    def __call__(self, entry):
        return self.render(**entry)


KEYFORMAT = Format(template='{author}{year}', author_num=2, author_sep="_", unknown_template="{doi}")
NAMEFORMAT = Format(template='{authorX}_{year}_{title}', author_sep="_", title_sep="-", unknown_template="unknown_{doi_or_id}")