"""The checksums of the files of a library: .papers/files.json, the sha256
of the files that its entries link to ({path: sha256}, the paths written as
the file links of the bibtex: relative to it, or absolute), and the version
of the PDFs that `papers file fetch` attached ({sha256: published, accepted
or submitted}; a file without version: unknown).

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
VERSIONS = ('published', 'accepted', 'submitted')  # the versions of a PDF, the final one first


def files_json(config):
    "the checksums file of the library, or None (a bibtex without library)"
    if not config.file or not config.is_library:
        return None
    return os.path.join(config.libdir, FILES_JSON)


def _base(config):
    return os.path.dirname(os.path.abspath(config.bibtex))


def parse(text, config):
    "{absolute path: sha256} of the content of a checksums file"
    return parse_text(text, _base(config))


def parse_text(text, base):
    "{absolute path: sha256} of the content of a checksums file, its paths relative to `base` (the bibtex folder)"
    try:
        stored = json.loads(text).get('files', {})
    except (ValueError, AttributeError):
        return {}
    # stored with / (with \\ by papers on Windows before 3.0.0b6)
    return {os.path.normpath(os.path.join(base, path.replace('\\', '/'))): digest
            for path, digest in stored.items()}


def parse_versions(text):
    "{sha256: version} of the content of a checksums file (a file without \"versions\": none)"
    try:
        stored = json.loads(text).get('versions', {})
    except (ValueError, AttributeError):
        return {}
    return {digest: version for digest, version in stored.items() if version in VERSIONS} \
        if isinstance(stored, dict) else {}


def _text(config):
    path = files_json(config)
    if path is None or not os.path.exists(path):
        return None
    return open(path, encoding='utf-8-sig').read()


def load(config):
    "{absolute path: sha256} of the library"
    text = _text(config)
    return {} if text is None else parse(text, config)


def load_versions(config):
    "{sha256: version} of the library"
    text = _text(config)
    return {} if text is None else parse_versions(text)


def file_versions(config):
    "{absolute path: version} of the linked files whose version is known"
    text = _text(config)
    if text is None:
        return {}
    versions = parse_versions(text)
    return {path: versions[digest] for path, digest in parse(text, config).items() if digest in versions}


def save(config, hashes, versions=None):
    """write the checksums of the library (no checksum: no file), and the
    versions (default: those of the file) of the checksums kept"""
    path = files_json(config)
    if path is None or papers.config.DRYRUN:
        return
    if versions is None:
        versions = load_versions(config)
    if not hashes:
        if os.path.exists(path):
            os.remove(path)
        return
    base = _base(config)
    stored = {(p if config.absolute_paths else os.path.relpath(p, base)).replace(os.sep, '/'): digest
              for p, digest in sorted(hashes.items())}  # the same keys on every system
    content = {'files': stored}
    linked = set(hashes.values())
    versions = {digest: version for digest, version in versions.items() if digest in linked}
    if versions:
        content['versions'] = versions
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_atomic(path, json.dumps(content, indent=1, sort_keys=True) + '\n')


def entry_links(entries, relative_to):
    "the absolute paths of the files that the entries link to"
    return {os.path.normpath(p) for e in entries if 'file' in e
            for p in parse_file(e['file'], relative_to)}


def bibtex_links(bibtex, relative_to, parse=None):
    """the absolute paths of the files that the entries of a bibtex file
    link to (parse: see papers.bib.Biblio.load)"""
    from papers.bib import Biblio  # papers.bib imports papers.journal
    if not os.path.exists(bibtex):
        return set()
    biblio = Biblio.load(bibtex, '', relative_to=relative_to, parse=parse)
    return {os.path.normpath(f) for e in biblio.entries for f in biblio.get_files(e)}


def update(config, biblio):
    """at the save of the library: the checksums of the files that the
    command moved, copied, added or linked; those of the files no entry links
    to any more are dropped. The PDFs that papers file fetch attached or
    replaced (biblio.pdf_versions: {path: version}) get their checksum
    (also with the checksums setting off) and their version; a version
    whose checksum is no longer in the file is dropped."""
    if files_json(config) is None:
        return
    links = {os.path.normpath(f) for e in biblio.entries for f in biblio.get_files(e)}
    hashes, versions = load(config), load_versions(config)
    kept = {p: digest for p, digest in hashes.items() if p in links}
    fetched = {os.path.normpath(p): v for p, v in biblio.pdf_versions.items()}
    touched = set()
    if config.checksums:
        touched = {os.path.normpath(op['dst']) for op in journal.pending(config.bibtex)
                   if op['op'] in ('moved', 'copied') and op.get('dst')}
        if biblio.loaded_entries is not None:
            touched |= links - entry_links(biblio.loaded_entries, biblio.loaded_relative_to)
        for path in sorted(touched & links):
            if os.path.isfile(path):
                kept[path] = checksum(path).hex()
    new_versions = dict(versions)
    for path, version in sorted(fetched.items()):
        if path in links and os.path.isfile(path):
            if path not in touched:
                kept[path] = checksum(path).hex()
            new_versions[kept[path]] = version
    linked = set(kept.values())
    new_versions = {digest: v for digest, v in new_versions.items() if digest in linked}
    if kept != hashes or new_versions != versions:
        save(config, kept, new_versions)
