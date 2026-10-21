"""Cache of the network queries (crossref, doi.org, arXiv, Google Scholar):
one json file per key under papers.config.CACHE_DIR, see `cached`.
"""
import contextlib
import hashlib
import json
import os
import tempfile
import time
from urllib.parse import quote

import papers.config
from papers import logger


def _cache_path(folder, key):
    """one json file per key: <folder>/<prefix>/<rest>.json, split at the first
    slash so that DOIs are grouped by registrant (10.1126/science.1166510 ->
    10.1126/science.1166510.json); characters unsafe in file names are quoted"""
    head, sep, tail = key.partition('/')
    if not sep:
        head, tail = key[:2], key
    name = quote(tail, safe='')
    if len(name) > 200:  # file name length limit
        name = hashlib.sha256(tail.encode('utf-8')).hexdigest()
    return os.path.join(folder, quote(head, safe=''), name + '.json')


def _read_cache_file(file):
    if os.path.exists(file):
        try:
            return json.load(open(file))
        except (json.JSONDecodeError, OSError) as error:
            # a corrupt cache file must not break every query
            logger.warning(f"unreadable cache file {file}: {error} -- ignored")
    return None


def _write_cache_file(data, file):
    """atomic replace, so an interrupted write cannot truncate the file"""
    os.makedirs(os.path.dirname(file), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(file),
                               prefix=os.path.basename(file) + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f)
        os.replace(tmp, file)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def _migrate_legacy_cache(legacy, folder, migrate):
    """split a cache of previous versions (one json file for all keys) into
    the per-key files; the legacy file is kept as <legacy>.bak"""
    data = _read_cache_file(legacy)
    if data:
        logger.info(f'migrate cache {legacy} to {folder}')
        for key, value in data.items():
            if migrate:
                value = migrate(value)
            if value is not None:
                # lower-case: DOIs are case-insensitive, and looked up in lower case
                _write_cache_file({'value': value}, _cache_path(folder, key.lower()))
    with contextlib.suppress(OSError):  # another process may have migrated it
        os.replace(legacy, legacy + '.bak')


NOT_FOUND_TTL = 24 * 3600  # seconds


def cached(name, hashed_key=False, legacy=None, migrate=None, trim=None, not_found=None):
    """cache the results of fun(key) as json files under papers.config.CACHE_DIR/name/

    legacy: cache file of previous versions, migrated on first use (with
        migrate(value) -> value, or None to drop it)
    trim: applied to results before they are stored
    not_found: exception class raised by fun when the key does not exist:
        it is remembered (and raised again) for NOT_FOUND_TTL seconds
    """
    def decorator(fun):
        def decorated(arg):
            key = arg
            # read at each call: the tests and --dry-run change them
            cache_dir = papers.config.CACHE_DIR
            folder = os.path.join(cache_dir, name)
            if legacy and not papers.config.DRYRUN and os.path.exists(os.path.join(cache_dir, legacy)):
                _migrate_legacy_cache(os.path.join(cache_dir, legacy), folder, migrate)
            if hashed_key: # use hashed parameter as key (for full text query)
                key = hashlib.sha256(arg.encode('utf-8')).hexdigest()[:16]
            file = _cache_path(folder, key)
            data = _read_cache_file(file)
            if data and 'value' in data:
                logger.debug('load from cache: '+repr((name, key)))
                return data['value']
            if data and not_found and time.time() - data.get('not_found', 0) < NOT_FOUND_TTL:
                raise not_found(f'{key}: not found (cached until {time.ctime(data["not_found"] + NOT_FOUND_TTL)})')
            try:
                res = fun(arg)
            except Exception as error:
                if not_found and isinstance(error, not_found) and not papers.config.DRYRUN:
                    _write_cache_file({'not_found': time.time()}, file)
                raise
            if trim:
                res = trim(res)
            if not papers.config.DRYRUN:
                _write_cache_file({'value': res}, file)
            return res
        return decorated
    return decorator
