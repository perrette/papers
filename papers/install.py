"""Resolution and application of `papers init` and `papers install`.

The decision logic lives in :func:`resolve_install`: it combines a
pre-existing configuration, the command-line options, a filesystem probe and
an :class:`Asker` into an :class:`InstallPlan` -- the final configuration
plus the actions to perform. :func:`apply_install` executes the plan.

Prompting goes through the Asker interface, so the whole precedence matrix
(command-line flag vs. prompt vs. pre-existing value vs. discovered default)
is testable without scripting stdin. `papers init` never prompts.

Semantics: installing over an existing library configuration *updates* it --
options you pass change, everything else is kept (this is the deprecated
`papers install`; `papers config` changes settings in v3). Pass ``--reset``
to discard it and start over from defaults.
"""
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from papers import logger
from papers.backup import init_backup, resolve_gitdir
from papers.config import Config, CONFIG_FILE_LOCAL
from papers.library import snapshot_backup

# words that clear a value at a prompt or on the command line
RESET_WORDS = ('none', 'null', 'unset', 'undefined', 'reset', 'delete')
# words that accept the proposed default at a prompt
ACCEPT_WORDS = ('yes', 'y', '')
# words that decline the proposed default (keep the configured value, if any)
DECLINE_WORDS = ('no', 'n')


class Asker:
    """Interface for interactive questions during install."""
    def ask(self, question, default=''):
        raise NotImplementedError


class InputAsker(Asker):
    def ask(self, question, default=''):
        return input(question)


class DefaultAsker(Asker):
    "non-interactive: always accept the default"
    def ask(self, question, default=''):
        return ''


@dataclass
class FsProbe:
    """What the filesystem offers as defaults, gathered up front."""
    bibtex_files: list = field(default_factory=list)
    existing_dirs: list = field(default_factory=list)


CHECKDIRS = ["files", "pdfs", "pdf", "papers", "bibliography"]


def probe_filesystem():
    "bibtex files and files folders of the current directory"
    bibs = [str(f) for f in sorted(Path('.').glob('*.bib'))]
    return FsProbe(bibtex_files=bibs,
                   existing_dirs=[d for d in CHECKDIRS if os.path.exists(str(d))])


@dataclass
class InstallPlan:
    config: Config
    create_bibtex: bool = False
    create_filesdir: bool = False
    remove_config_files: list = field(default_factory=list)
    init_git: bool = False
    snapshot: bool = False


def _ask_path(asker, what, default, current=None):
    status = 'existing' if (default and os.path.exists(str(default))) else 'new'
    ans = asker.ask(f"{what} [default to {status}: {default}] [Enter/path/'unset']: ",
                    default=default).strip()
    low = ans.lower()
    if low in ACCEPT_WORDS:
        return default
    if low in DECLINE_WORDS:
        return current
    if low in RESET_WORDS:
        return None
    return ans


def _ask_bool(asker, question, default):
    ans = asker.ask(f"{question} [Enter: {default}/Yes/No]: ", default=default).strip()
    if ans == '':
        return default
    return ans.lower() in ('y', 'yes')


def resolve_install(config, o, probe=None, asker=None, target=None):
    """Combine pre-existing config, options, filesystem and answers into an InstallPlan.

    `config` is the library configuration to update, or a fresh Config
    (`config.file is None`); `o` the argparse namespace of the init or
    install command; `target` the configuration file to write (default: the
    one of `config`, else .papersconfig.json in the current directory).
    """
    asker = asker or DefaultAsker()

    old_file = None
    if config.file is not None and getattr(o, 'reset', False):
        logger.info(f"reset pre-existing configuration: {config.file}")
        old_file = config.file
        config = Config(machine=config.machine)
    # else: update the existing configuration (default)

    fresh = config.file is None

    # target configuration file
    papersconfig = target or config.file or CONFIG_FILE_LOCAL

    remove_config_files = []
    if old_file and Path(old_file).resolve() != Path(papersconfig).resolve():
        remove_config_files.append(old_file)

    if probe is None:
        probe = probe_filesystem()

    # --- bibtex ---
    default_bibtex = config.bibtex or 'papers.bib'
    # deduplicate by resolved path: the same file may appear both as the
    # configured (absolute) bibtex and as a relative directory-scan result
    seen = {Path(default_bibtex).resolve()}
    candidates = [default_bibtex]
    for f in probe.bibtex_files:
        resolved = Path(f).resolve()
        if resolved not in seen:
            seen.add(resolved)
            candidates.append(f)
    candidates = [f for f in candidates if os.path.exists(f)]

    bibtex = o.bibtex
    if not bibtex:
        if len(candidates) > 1:
            logger.warning("Several bibtex files found: " + " ".join(candidates))
        if candidates:
            default_bibtex = candidates[0]
        bibtex = _ask_path(asker, "Bibtex file name", default_bibtex, current=config.bibtex)
    elif bibtex.lower() in RESET_WORDS:
        bibtex = None

    # --- files directory ---
    default_filesdir = config.filesdir or 'files'
    for d in ([config.filesdir] if config.filesdir else []) + probe.existing_dirs:
        if os.path.exists(str(d)):
            default_filesdir = d
            break

    filesdir = o.filesdir
    if not filesdir:
        filesdir = _ask_path(asker, "Files folder", default_filesdir, current=config.filesdir)
    elif filesdir.lower() in RESET_WORDS:
        filesdir = None

    config.bibtex = str(bibtex) if bibtex else None
    config.filesdir = str(filesdir) if filesdir else None
    config.file = papersconfig
    config.local = True

    # a new library stores these settings rather than inheriting them later:
    # they determine its content (the file links) and where it looks for entries
    if getattr(o, 'paths', None) is not None:
        config.set('paths', o.paths)
    elif getattr(o, 'absolute_paths', None) is not None:
        config.set('paths', 'absolute' if o.absolute_paths else 'relative')
    elif fresh:
        config.set('paths', config.get('paths'))

    if getattr(o, 'pool', None):
        config.set('pools', list(o.pool))
    elif fresh:
        config.set('pools', config.get('pools'))

    # Unless otherwise specified (option not advertized -- help suppressed)
    # the git directory is centralized in the backup dir.
    if getattr(o, 'gitdir', None):
        config.gitdir = o.gitdir
    elif config.gitdir and os.path.exists(config.gitdir):
        pass  # keep the pre-existing backup directory and its history
    elif config.bibtex is not None:
        config.gitdir = resolve_gitdir(config.bibtex)

    if o.editor:
        config.set('editor', o.editor)

    # --- git tracking ---
    git = True if o.git_lfs else o.git
    if git is None:
        if fresh and config.source('git') == 'default':
            # fresh installs default to git-tracking when git is available
            default_git = shutil.which('git') is not None
        else:
            default_git = bool(config.git)
        git = _ask_bool(asker, "Use git to back-up the bibtex file ?", default_git)
    config.set('git', bool(git))

    gitlfs = o.git_lfs
    if not config.git:
        gitlfs = False
    if gitlfs is None:
        gitlfs = _ask_bool(asker, "Use git-lfs to back-up associated files ?", bool(config.gitlfs))
    config.set('git-lfs', bool(gitlfs))

    return InstallPlan(
        config=config,
        create_bibtex=bool(config.bibtex) and not os.path.exists(config.bibtex),
        create_filesdir=bool(config.filesdir) and not os.path.exists(config.filesdir),
        remove_config_files=remove_config_files,
        init_git=config.git,
        snapshot=config.git and bool(config.bibtex),
    )


def apply_install(plan):
    """Execute an InstallPlan and return the installed Config."""
    config = plan.config

    if plan.create_bibtex:
        logger.info(f'create empty bibliography database: {config.bibtex}')
        Path(config.bibtex).parent.mkdir(parents=True, exist_ok=True)
        Path(config.bibtex).write_text('', encoding='utf-8')

    if plan.create_filesdir:
        logger.info(f'create empty files directory: {config.filesdir}')
        Path(config.filesdir).mkdir(parents=True)

    for f in plan.remove_config_files:
        logger.warning(f'remove pre-existing configuration file: {f}')
        os.remove(f)

    logger.info('save config file: ' + config.file)
    if os.path.dirname(config.file):
        # typically is current dir = ""
        os.makedirs(os.path.dirname(config.file), exist_ok=True)
    config.save()

    if plan.init_git:
        init_backup(config)

    if plan.snapshot:
        snapshot_backup(config)

    return config
