"""The shortcuts of the text normalization (bibtex.md 4.1 and 9.1) give the
same text as the step-by-step path: runs of plain characters copied in one
step by the LaTeX decoder, ASCII runs left out of the transliteration, and a
plain ASCII text only lower-cased and spaced."""
import random
import re
import unittest
from unittest.mock import patch

from anyascii import anyascii

from papers import ascii, latex
from papers.duplicate import normalize_text

NEVER = re.compile(r'(?!)')  # matches nothing: the decoder reads one character at a time

TEXTS = [
    '', ' ', 'Sea level', '  Sea   LEVEL\n rise ', 'a--b', 'a---b c-d', "``quoted'' `single' x'", 'a~b',
    '$CO_2$', '{CO$_2$} emissions', 'M{\\"u}ller', '\\"{u}ber \\c c \\v{S}', "Garc{\\'\\i}a", '\\ss\\o{} \\AA',
    '\\emph{Ocean} \\textit {model}', '\\unknown cmd', 'trailing \\', 'trailing \\\'', '{{nested} {braces}}',
    'stray } brace {', 'Müller Schrödinger Ã…ström', '中文 title', 'tab\tand\nnew line', 'path/to/file:pdf',
    '\\& \\% \\$ \\# \\_ \\{ \\}', 'hyphen\\-ation', 'x\\ y\\,z', 'É{\\\'e}\u0301', '\ufb01 ligature', '\x1f\x1c sep',
]


def _random_texts(n, seed=0):
    rng = random.Random(seed)
    pieces = ['a', 'Z', ' ', '  ', '\n', '\\', '{', '}', '$', '~', '-', '--', '`', "'", '"', 'ü', 'é', '中',
              '\\"', "\\'", '\\c', '\\ss', '\\emph', '\\i', 'text', '1', ',', '\u0301', '\t']
    return [''.join(rng.choice(pieces) for _ in range(rng.randint(0, 25))) for _ in range(n)]


def _slow_normalize(s):
    "norm(s) of bibtex.md 9.1, every step done, one character at a time"
    if not s:
        return ''
    if not (s.isascii() and not set(s) & set('\\{}')):  # step 2 leaves such a text unchanged
        with patch.object(latex, '_PLAIN_TEXT', NEVER):
            s = latex.latex_to_unicode(s)
    s = anyascii(s).replace('{', '').replace('}', '')
    return ' '.join(s.lower().split())


class CountingStr(str):
    "a text that counts the calls of its startswith (one per character in the decoder's loop)"
    calls = 0

    def startswith(self, *args):
        CountingStr.calls += 1
        return str.startswith(self, *args)


class TestFastNormalization(unittest.TestCase):

    def setUp(self):
        normalize_text.cache_clear()

    def test_decoder_runs_same_text(self):
        for text in [True, False]:
            pattern = '_PLAIN_TEXT' if text else '_PLAIN_PATH'
            for s in TEXTS + _random_texts(3000):
                with patch.object(latex, pattern, NEVER):
                    slow = latex.latex_to_unicode(s, text=text)
                self.assertEqual(latex.latex_to_unicode(s, text=text), slow, (s, text))

    def test_to_ascii_same_text(self):
        for s in TEXTS + _random_texts(3000, seed=1):
            self.assertEqual(ascii.to_ascii(s), anyascii(s), s)

    def test_normalize_same_text(self):
        for s in TEXTS + _random_texts(3000, seed=2):
            self.assertEqual(normalize_text(s), _slow_normalize(s), s)

    def test_decoder_copies_plain_runs(self):
        CountingStr.calls = 0
        s = CountingStr('Sea level rise and the ocean, ' * 100 + 'M{\\"u}ller -- 2020')
        self.assertEqual(latex.latex_to_unicode(s), 'Sea level rise and the ocean, ' * 100 + 'Müller – 2020')
        self.assertLess(CountingStr.calls, 10)

    def test_ascii_runs_not_transliterated(self):
        seen = []
        with patch.object(ascii, 'anyascii', lambda t: seen.append(t) or anyascii(t)):
            self.assertEqual(ascii.to_ascii('Müller and Schrödinger, sea level'), 'Muller and Schrodinger, sea level')
        self.assertEqual(seen, ['ü', 'ö'])

    def test_plain_ascii_not_decoded(self):
        with patch('papers.duplicate.latex_to_unicode') as decode, patch('papers.duplicate.to_ascii') as translit:
            self.assertEqual(normalize_text('  Sea   LEVEL -- rise~ '), 'sea level -- rise~')
        decode.assert_not_called()
        translit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
