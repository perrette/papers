"""Resolution and application of `papers install`.

The decision logic lives in :func:`resolve_install`: it combines a
pre-existing configuration, the command-line options, a filesystem probe and
an :class:`Asker` into an :class:`InstallPlan` -- the final configuration
plus the actions to perform. :func:`apply_install` executes the plan.

Prompting goes through the Asker interface, so the whole precedence matrix
(command-line flag vs. prompt vs. pre-existing value vs. discovered default)
is testable without scripting stdin.

Semantics: installing over an existing configuration of the same scope
*updates* it -- options you pass change, everything else is kept. Pass
``--reset`` to discard it and start over from defaults. An existing
configuration of the other scope (local vs. global) is left alone: a warning
states which one takes precedence.
"""
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from papers import logger
from papers.config import Config, CONFIG_FILE, CONFIG_FILE_LOCAL, DATA_DIR

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


class ScriptedAsker(Asker):
    "for tests: replay prepared answers, record the questions"
    def __init__(self, *answers):
        self.answers = list(answers)
        self.questions = []

    def ask(self, question, default=''):
        self.questions.append(question)
        return self.answers.pop(0) if self.answers else ''


@dataclass
class FsProbe:
    """What the filesystem offers as defaults, gathered up front."""
    bibtex_files: list = field(default_factory=list)
    existing_dirs: list = field(default_factory=list)


CHECKDIRS = ["files", "pdfs", "pdf", "papers", "bibliography"]


def probe_filesystem(local):
    bibs = [str(f) for f in sorted(Path('.').glob('*.bib'))]
    checkdirs = list(CHECKDIRS)
    if not local:
        bibs += [str(f) for f in sorted(Path(DATA_DIR).glob('*.bib'))]
        checkdirs = [os.path.join(DATA_DIR, 'files')] + checkdirs
    return FsProbe(bibtex_files=bibs,
                   existing_dirs=[d for d in checkdirs if os.path.exists(str(d))])


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


def resolve_install(config, o, probe=None, asker=None):
    """Combine pre-existing config, options, filesystem and answers into an InstallPlan.

    `config` is the pre-existing configuration (`config.file is None` when not
    installed); `o` the argparse namespace of the install command.
    """
    asker = asker or DefaultAsker()

    # scope: keep the existing install's scope unless specified
    if o.local is None:
        o.local = config.local if config.local is not None else False
    o.local = bool(o.local)

    same_scope = config.file is not None and bool(config.local) == o.local
    old_file = None

    if config.file is not None and not same_scope:
        # never delete the other scope's configuration; just state precedence
        if o.local:
            logger.warning(f"a global install exists ({config.file}); "
                           "the local install will take precedence in this directory")
        else:
            logger.warning(f"a local install exists ({config.file}) and will take "
                           "precedence over the global install in this directory")
        config = Config()
    elif same_scope and getattr(o, 'reset', False):
        logger.info(f"reset pre-existing configuration: {config.file}")
        old_file = config.file
        config = Config()
    # else: update the existing configuration (default)

    fresh = config.file is None

    # target configuration file
    if o.local:
        papersconfig = config.file or CONFIG_FILE_LOCAL
    else:
        papersconfig = CONFIG_FILE

    remove_config_files = []
    if old_file and Path(old_file).resolve() != Path(papersconfig).resolve():
        remove_config_files.append(old_file)

    if probe is None:
        probe = probe_filesystem(o.local)

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
    config.local = o.local

    if o.absolute_paths is not None:
        config.absolute_paths = o.absolute_paths
    elif fresh:
        config.absolute_paths = not o.local

    # Unless otherwise specified (option not advertized -- help suppressed)
    # the git directory is centralized in the backup dir.
    if o.gitdir:
        config.gitdir = o.gitdir
    elif config.gitdir and os.path.exists(config.gitdir):
        pass  # keep the pre-existing backup directory and its history
    elif config.bibtex is not None:
        from papers.backup import resolve_gitdir
        config.gitdir = resolve_gitdir(config.bibtex)

    if o.editor:
        config.editor = o.editor

    # --- git tracking ---
    git = True if o.git_lfs else o.git
    if git is None:
        if fresh:
            # fresh installs default to git-tracking when git is available
            default_git = shutil.which('git') is not None
        else:
            default_git = bool(config.git)
        git = _ask_bool(asker, "Use git to back-up the bibtex file ?", default_git)
    config.git = bool(git)

    gitlfs = o.git_lfs
    if not config.git:
        gitlfs = False
    if gitlfs is None:
        gitlfs = _ask_bool(asker, "Use git-lfs to back-up associated files ?", bool(config.gitlfs))
    config.gitlfs = bool(gitlfs)
    config.backup_files = config.gitlfs

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
        from papers.backup import claim_gitdir
        if (Path(config.gitdir)/'.git').exists():
            logger.warning(f'{config.gitdir} is already initialized')
        else:
            os.makedirs(config.gitdir, exist_ok=True)
            config.gitcmd('init')

        # an explicit install takes ownership of the backup directory
        claim_gitdir(config)

        if config.gitlfs:
            config.gitcmd('lfs track "files/"')
            config.gitcmd('add .gitattributes')
            config.gitcmd('commit -m "papers install: .gitattribute"', check=False)

    if plan.snapshot:
        from papers.bib import get_biblio
        from papers.backup import backup_bib
        biblio = get_biblio(config)
        backup_bib(biblio, config)

    return config
