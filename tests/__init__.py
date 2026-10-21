import atexit
import os
import shutil
import tempfile
import subprocess as sp
# setup user name and user email if not set (otherwise commit will fail)
sp.check_call('git config --list | grep user.name || git config --global user.name "Papers Tests"', shell=True)
sp.check_call('git config --list | grep user.email || git config --global user.email "papers.tests@github.com"', shell=True)
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
os.makedirs(os.path.dirname(papers.config.MACHINE_CONFIG_FILE))
with open(papers.config.MACHINE_CONFIG_FILE, 'w') as f:
    json.dump({'pools': {'default': TEST_DEFAULT_POOL}}, f)
