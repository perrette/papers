"""LaTeX to Unicode: the decoder of the same-paper rule and of Mendeley file links.

The text is read token by token, as LaTeX reads it (design/bibtex.md, 4.1):

- an accent command (`\\'e`, `\\'{e}`, `{\\'e}`, `\\c c`, `\\v{S}`) puts its
  accent on the first character of its argument (the next character or
  braced group, spaces before it skipped); on `\\i` and `\\j` the accent
  goes on `i` and `j`;
- a command that names a character (`\\o`, `\\ss`, `\\alpha`,
  `\\textendash`) gives that character; `\\&`, `\\%`, `\\$`, `\\#`, `\\_`,
  `\\{`, `\\}` give the character after the backslash;
- a formatting command (`\\textit`, `\\emph`, `\\url`...) is dropped and its
  argument kept;
- any other command is kept as written;
- `{`, `}` and `$` are dropped, `~` is a no-break space, `--` and `---`
  are en and em dashes, ``` `` ``` and `''` are double quotes;
- the result is in Unicode NFC form.
"""
import functools
import re
import unicodedata

__all__ = ['latex_to_unicode']

# accent commands: the combining character each one puts on its argument
ACCENTS = {
    '`': '̀', "'": '́', '^': '̂', '~': '̃', '=': '̄',
    'u': '̆', '.': '̇', '"': '̈', 'r': '̊', 'H': '̋',
    'v': '̌', 'd': '̣', 'c': '̧', 'k': '̨', 'b': '̱',
    't': '͡',
    # in math
    'grave': '̀', 'acute': '́', 'hat': '̂', 'tilde': '̃',
    'bar': '̄', 'breve': '̆', 'dot': '̇', 'ddot': '̈',
    'check': '̌', 'vec': '⃗',
}

# characters written with a backslash in front
ESCAPES = set('&%$#_{}')

# formatting commands: dropped, their argument kept
FORMATTING = {
    'emph', 'textit', 'textbf', 'textsc', 'textrm', 'textsf', 'texttt', 'textup',
    'textsl', 'textmd', 'textnormal', 'textsuperscript', 'textsubscript',
    'mathrm', 'mathit', 'mathbf', 'mathsf', 'mathtt', 'mathcal', 'mathnormal',
    'text', 'mbox', 'hbox', 'url', 'href', 'ensuremath', 'protect', 'relax',
    'cyrchar', 'it', 'bf', 'sc', 'rm', 'sf', 'tt', 'em', 'sl', 'up', 'normalfont', 'nocase',
}

# character names missing from the table of papers/latexenc.py
_MORE_CHARACTERS = {'dh': 'ð', 'j': 'ȷ', 'times': '×', 'ell': 'ℓ',
                    'copyright': '©', 'textregistered': '®'}

_NAMED = re.compile(r'^(?:\\cyrchar)?(?:\{\\([A-Za-z]+)\}|\\([A-Za-z]+)\{\}|\\([A-Za-z]+) ?|\$\\([A-Za-z]+)\$)$')


@functools.lru_cache(maxsize=None)
def characters():
    """{command name: character}: the commands of the to_latex table of
    papers/latexenc.py written as one command (`\\o`, `{\\o}`, `\\o{}`,
    `$\\alpha$`), the first one of each name, and a few the table lacks"""
    from papers.latexenc import unicode_to_latex, unicode_to_crappy_latex1
    names = {}
    for char, latex in unicode_to_latex + unicode_to_crappy_latex1:
        m = _NAMED.match(latex)
        if m and len(char) == 1:  # a few rows of the table hold text such as '≂-00338'
            name = next(g for g in m.groups() if g)
            if name not in ACCENTS:
                names.setdefault(name, char)
    for name, char in _MORE_CHARACTERS.items():
        names.setdefault(name, char)
    return names


def _group_end(s, i):
    "the index after the `}` that closes the `{` at s[i] (or the end of s)"
    depth = 0
    for j in range(i, len(s)):
        if s[j] == '{':
            depth += 1
        elif s[j] == '}':
            depth -= 1
            if depth == 0:
                return j + 1
    return len(s)


def _command(s, i):
    "(name, index after it) of the command at s[i] == '\\'"
    j = i + 1
    while j < len(s) and s[j].isascii() and s[j].isalpha():
        j += 1
    if j == i + 1:  # a control symbol: one character
        return s[i + 1:i + 2], min(i + 2, len(s))
    return s[i + 1:j], j


def _skip_spaces(s, i):
    while i < len(s) and s[i] in ' \t\n':
        i += 1
    return i


def _accent(s, i, mark, text):
    "(decoded text, index after it) of the argument of an accent at s[i], with the accent on"
    i = _skip_spaces(s, i)
    if i >= len(s):
        return '', i
    if s[i] == '{':
        end = _group_end(s, i)
        arg = _decode(s[i + 1:end - 1] if s[end - 1:end] == '}' else s[i + 1:end], text)
    elif s[i] == '\\':
        end = _command(s, i)[1]
        arg = _decode(s[i:end], text)
    else:
        end = i + 1
        arg = s[i]
    if not arg:
        return '', end
    first = {'ı': 'i', 'ȷ': 'j'}.get(arg[0], arg[0])
    k = 1  # after the accents the first character already has
    while k < len(arg) and unicodedata.combining(arg[k]):
        k += 1
    return first + arg[1:k] + mark + arg[k:], end


# a run of characters the decoder copies as they are
_PLAIN_TEXT = re.compile(r"[^\\{}$~\-`']+")
_PLAIN_PATH = re.compile(r"[^\\{}]+")


def _decode(s, text):
    out = []
    i = 0
    n = len(s)
    plain = _PLAIN_TEXT if text else _PLAIN_PATH
    while i < n:
        m = plain.match(s, i)
        if m:
            out.append(m.group())
            i = m.end()
            continue
        c = s[i]
        if c == '\\':
            name, j = _command(s, i)
            if name in ACCENTS:
                accented, i = _accent(s, j, ACCENTS[name], text)
                out.append(accented)
                continue
            if name.isalpha():
                after = _skip_spaces(s, j)  # spaces after a command word are not text
                if name in FORMATTING:
                    i = after
                elif name in characters():
                    out.append(characters()[name])
                    i = after
                else:
                    out.append(s[i:j])
                    i = j
            elif name in ESCAPES:
                out.append(name)
                i = j
            elif name in (' ', ',', ';', ':', '!', '\\', '\n', '\t'):
                out.append(' ')
                i = j
            elif name == '-':  # a hyphenation point
                i = j
            else:
                out.append(s[i:j])
                i = j
        elif c in '{}':
            i += 1
        elif not text:
            out.append(c)
            i += 1
        elif c == '$':
            i += 1
        elif c == '~':
            out.append(' ')
            i += 1
        elif s.startswith('---', i):
            out.append('—')
            i += 3
        elif s.startswith('--', i):
            out.append('–')
            i += 2
        elif s.startswith('``', i) or s.startswith("''", i):
            out.append('"')
            i += 2
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def latex_to_unicode(s, text=True):
    """the Unicode text of the LaTeX text `s` (see the module docstring);
    with text=False (a file path), only the commands and braces are decoded:
    `$`, `~`, dashes and quotes are kept"""
    if not s:
        return s
    return unicodedata.normalize('NFC', _decode(s, text))
