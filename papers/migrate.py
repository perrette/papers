"""One-time upgrades from papers v2 (`papers migrate`).

The global configuration of v2 defined a library for the whole user account.
In v3 it becomes an ordinary library: its settings are written to a library
configuration next to its bibtex, its directory is registered as the
`default` pool of the global configuration (used outside of any
library), and the old file is renamed to <name>.v2.bak.
"""
import os

from papers import logger
from papers.config import (Config, CONFIG_FILE, CONFIG_FILE_LOCAL, CONFIG_FILE_LEGACY,
                           CONFIG_FILE_LEGACY_XDG, INHERITED, short_home)
from papers.files import hidden_bibtex
from papers.library import get_biblio, savebib, convert_file_links


def v2_global_configs():
    "existing global configuration files of v2, current location first"
    files, seen = [], set()
    for file in [CONFIG_FILE, CONFIG_FILE_LEGACY, CONFIG_FILE_LEGACY_XDG]:
        if os.path.isfile(file) and os.path.realpath(file) not in seen:
            seen.add(os.path.realpath(file))
            files.append(file)
    return files


def _same_path(a, b):
    return os.path.realpath(os.path.expanduser(a)) == os.path.realpath(os.path.expanduser(b))


def migrate_v2_global(machine, relative=False, dryrun=False):
    """Migrate the global configuration(s) of v2. Return the number of files
    migrated (0: nothing to do).

    relative: store the file links relative to the bibtex (by default the
        library keeps its previous setting, absolute in most cases); the
        file links of the bibtex are converted.
    """
    files = v2_global_configs()
    prefix = 'DRYRUN: ' if dryrun else ''
    for file in files:
        old = Config.load(file, machine=machine, local=False)
        print(f"global configuration of papers v2: {file}")
        if not old.bibtex:
            print(f"  {prefix}it defines no bibtex: no library to create")
        else:
            libdir = os.path.dirname(old.bibtex)
            target = os.path.join(libdir, CONFIG_FILE_LOCAL)
            if os.path.exists(target):
                print(f"  a library configuration already exists: {target} (kept as is)")
            else:
                new = Config(file=target, local=True, machine=machine,
                             bibtex=old.bibtex, filesdir=old.filesdir, gitdir=old.gitdir)
                for name in INHERITED:
                    if name in old.explicit:
                        new.set(name, old.get(name))
                new.set('pools', old.get('pools'))
                new.set('git', old.get('git'))
                new.set('git-lfs', old.get('git-lfs'))
                new.set('paths', 'relative' if relative else old.get('paths'))
                print(f"  {prefix}create the library configuration {target} (paths: {new.get('paths')})")
                if not dryrun:
                    new.save()
                    if relative and old.absolute_paths and os.path.exists(new.bibtex):
                        convert_file_links(new)
                        print(f"  the file links of {new.bibtex} are now relative to its directory")

            current = machine.data.get('pools', {}).get('default')
            if current is None or _same_path(current, libdir):
                print(f"  {prefix}register {libdir} as the default pool in {machine.file}")
                if not dryrun:
                    machine.set_pool('default', short_home(libdir))
                    machine.save()
            else:
                print(f"  the default pool is already {current}: not changed "
                      f"(change it with `papers config --global pools.default PATH`)")

        backup = file + '.v2.bak'
        print(f"  {prefix}rename {file} to {backup}")
        if not dryrun:
            os.replace(file, backup)
    if files:
        logger.info(f"migrated {len(files)} global configuration file(s)")
    return len(files)


def migrate_folders(config):
    """move the files of the entries kept in folders of papers < 2.19
    (<name>/ with a hidden .<name>.bib) to the flat layout of the files directory"""
    biblio = get_biblio(config)
    count = 0
    for e in biblio.entries:
        files = biblio.get_files(e)
        if any(os.path.isfile(hidden_bibtex(os.path.dirname(f))) for f in files):
            logger.info(f"{biblio.key(e)}: move files out of {os.path.dirname(files[0])}")
            biblio.rename_entry_files(e)
            count += 1
    if count:
        savebib(biblio, config)
    print(f"{count} entries moved out of the folders of papers < 2.19")
