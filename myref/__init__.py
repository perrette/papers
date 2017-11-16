

from ._version import get_versions
__version__ = get_versions()['version']
del get_versions

import logging
logging.basicConfig()
logger = logging.getLogger(__name__)