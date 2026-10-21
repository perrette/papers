import atexit
import os
import shutil
import tempfile
import subprocess as sp
# git commits of the backups need a user name and email: when git has none,
# give them through the environment (inherited by every git call), instead of
# writing to the developer's ~/.gitconfig
for _key, _var, _value in [('user.name', 'NAME', 'Papers Tests'), ('user.email', 'EMAIL', 'papers.tests@github.com')]:
    if sp.run(['git', 'config', _key], capture_output=True).returncode != 0:
        os.environ.setdefault(f'GIT_AUTHOR_{_var}', _value)
        os.environ.setdefault(f'GIT_COMMITTER_{_var}', _value)
del sp

# Keep the tests away from the user's configuration and backups: papers.config
# derives its locations from platformdirs, which honors the XDG variables on
# Linux. They are set before papers is imported, and are inherited by the
# `python3 -m papers` subprocesses of some tests. The cache is shared on
# purpose (it spares network queries).
_TEST_HOME = tempfile.mkdtemp(prefix='papers-tests-')
os.environ['XDG_CONFIG_HOME'] = os.path.join(_TEST_HOME, 'config')
os.environ['XDG_DATA_HOME'] = os.path.join(_TEST_HOME, 'data')
atexit.register(shutil.rmtree, _TEST_HOME, ignore_errors=True)

# The default pool (~/Documents/papers without per-machine configuration) is
# used outside of any library: point it to the temporary directory too, both
# as built-in default (in this process) and in the per-machine configuration
# (also read by the subprocesses).
import json
import papers.config
TEST_DEFAULT_POOL = os.path.join(_TEST_HOME, 'Documents', 'papers')
papers.config.DEFAULT_POOLS['default'] = TEST_DEFAULT_POOL
# The files mode is `link` (the default is `move`): `papers add` then leaves
# the PDFs where they are, as in v2, so that the cached PDFs of
# tests/downloadedpapers are never moved. The tests of the files modes set
# the mode they test.
os.makedirs(os.path.dirname(papers.config.MACHINE_CONFIG_FILE))
with open(papers.config.MACHINE_CONFIG_FILE, 'w') as f:
    json.dump({'pools': {'default': TEST_DEFAULT_POOL}, 'files': 'link'}, f)
