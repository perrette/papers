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
