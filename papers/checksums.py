"""The checksums of the files of a library: .papers/files.json, the sha256
of the files that its entries link to ({path: sha256}, the paths written as
the file links of the bibtex: relative to it, or absolute).

With the checksums setting (true by default), a command writes the checksum
of the files it moves, copies, adds or links; `papers file checksum` writes
them for all the files. The git backup commits files.json with the bibtex:
undo, redo and restore find a file of the restored state by its checksum
(see papers.journal.restore).
"""
import json
import os

import papers.config
from papers import journal
from papers.entries import parse_file
from papers.utils import checksum, write_atomic

FILES_JSON = os.path.join('.papers', 'files.json')


def files_json(config):
    "the checksums file of the library, or None (a bibtex without library)"
    if not config.file or not config.is_library:
        return None
    return os.path.join(config.libdir, FILES_JSON)


def _base(config):
    return os.path.dirname(os.path.abspath(config.bibtex))


def parse(text, config):
    "{absolute path: sha256} of the content of a checksums file"
    try:
        stored = json.loads(text).get('files', {})
    except (ValueError, AttributeError):
        return {}
    # stored with / (with \\ by papers on Windows before 3.0.0b6)
    return {os.path.normpath(os.path.join(_base(config), path.replace('\\', '/'))): digest
            for path, digest in stored.items()}


def load(config):
    "{absolute path: sha256} of the library"
    path = files_json(config)
    if path is None or not os.path.exists(path):
        return {}
    return parse(open(path, encoding='utf-8-sig').read(), config)


def save(config, hashes):
    "write the checksums of the library (no checksum: no file)"
    path = files_json(config)
    if path is None or papers.config.DRYRUN:
        return
    if not hashes:
        if os.path.exists(path):
            os.remove(path)
        return
    base = _base(config)
    stored = {(p if config.absolute_paths else os.path.relpath(p, base)).replace(os.sep, '/'): digest
              for p, digest in sorted(hashes.items())}  # the same keys on every system
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_atomic(path, json.dumps({'files': stored}, indent=1, sort_keys=True) + '\n')


def entry_links(entries, relative_to):
    "the absolute paths of the files that the entries link to"
    return {os.path.normpath(p) for e in entries if 'file' in e
            for p in parse_file(e['file'], relative_to)}


def bibtex_links(bibtex, relative_to):
    "the absolute paths of the files that the entries of a bibtex file link to"
    from papers.bib import Biblio  # papers.bib imports papers.journal
    if not os.path.exists(bibtex):
        return set()
    biblio = Biblio.load(bibtex, '', relative_to=relative_to)
    return {os.path.normpath(f) for e in biblio.entries for f in biblio.get_files(e)}


def update(config, biblio):
    """at the save of the library: the checksums of the files that the
    command moved, copied, added or linked; those of the files no entry links
    to any more are dropped"""
    if files_json(config) is None:
        return
    links = {os.path.normpath(f) for e in biblio.entries for f in biblio.get_files(e)}
    hashes = load(config)
    kept = {p: digest for p, digest in hashes.items() if p in links}
    if config.checksums:
        touched = {os.path.normpath(op['dst']) for op in journal.pending(config.bibtex)
                   if op['op'] in ('moved', 'copied') and op.get('dst')}
        if biblio.loaded_entries is not None:
            touched |= links - entry_links(biblio.loaded_entries, biblio.loaded_relative_to)
        for path in sorted(touched & links):
            if os.path.isfile(path):
                kept[path] = checksum(path).hex()
    if kept != hashes:
        save(config, kept)
