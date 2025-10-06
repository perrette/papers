# compat
from slugify import slugify
from unidecode import unidecode

def normalize(text):
    if text is None:
        return None
    return unidecode(text).strip()