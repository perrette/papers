import atexit
import os
import shutil
import tempfile

# Keep the tests away from the user's configuration, backups and default
# library: papers.config derives its locations from platformdirs, which
# honors the XDG variables on Linux. HOME and the XDG variables are set before papers is
# imported, and are inherited by the `python3 -m papers` subprocesses of
# some tests. The cache is shared on purpose (it spares network queries): it
# stays where it was before HOME changes.
_TEST_HOME = tempfile.mkdtemp(prefix='papers-tests-')
atexit.register(shutil.rmtree, _TEST_HOME, ignore_errors=True)
os.environ.setdefault('XDG_CACHE_HOME', os.path.join(os.path.expanduser('~'), '.cache'))

os.environ['HOME'] = os.path.join(_TEST_HOME, 'home')
os.makedirs(os.environ['HOME'])
os.environ['XDG_CONFIG_HOME'] = os.path.join(_TEST_HOME, 'config')
os.environ['XDG_DATA_HOME'] = os.path.join(_TEST_HOME, 'data')

# The global configuration sets no default library: the tests of the
# default library register one, e.g. TEST_DEFAULT_LIBRARY, under the
# temporary HOME (tests.common.ConfigTest restores the global configuration
# and removes that directory after each test).
import json
import papers.config
TEST_DEFAULT_LIBRARY = os.path.join(os.environ['HOME'], 'Documents', 'papers')
# The files mode is `link` (the default is `move`): `papers add` then leaves
# the PDFs where they are, as in v2, so that the cached PDFs of
# tests/downloadedpapers are never moved. The tests of the files modes set
# the mode they test.
os.makedirs(os.path.dirname(papers.config.MACHINE_CONFIG_FILE))
with open(papers.config.MACHINE_CONFIG_FILE, 'w') as f:
    json.dump({'files': 'link'}, f)
