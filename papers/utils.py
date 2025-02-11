import os
import re
import shutil
import hashlib
import subprocess, platform
from contextlib import contextmanager
from pathlib import Path

from papers import logger


class bcolors:
    # https://stackoverflow.com/a/287944/2192272
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def strip_colors(s):
    for name, c in vars(bcolors).items():
        if name.startswith("_"):
            continue
        s = s.replace(c, '')
    return s


def ansi_link(uri, label=None):
    """https://stackoverflow.com/a/71309268/2192272
    """
    if label is None:
        label = uri
    parameters = ''

    # OSC 8 ; params ; URI ST <name> OSC 8 ;; ST
    escape_mask = '\033]8;{};{}\033\\{}\033]8;;\033\\'

    return escape_mask.format(parameters, uri, label)


ANSI_LINK_RE = re.compile(r'(?P<ansi_sequence>\033]8;(?P<parameter>.*?);(?P<uri>.*?)\033\\(?P<label>.*?)\033]8;;\033\\)')

def strip_ansi_link(s):
    for m in ANSI_LINK_RE.findall(s):
        s = s.replace(m[0], m[3])
    return s


def strip_all(s):
    s = strip_colors(s)
    s = strip_ansi_link(s)
    return s


def check_filesdir(folder):
    folder_size = 0
    file_count = 0
    for (path, dirs, files) in os.walk(folder):
      for file in files:
        filename = os.path.join(path, file)
        if filename.endswith('.pdf'):
            folder_size += os.path.getsize(filename)
            file_count += 1
    return file_count, folder_size


def search_config(filenames, start_dir, default=None):
    """Thanks Chat GPT !"""
    current_dir = os.path.abspath(start_dir)
    root_dir = os.path.abspath(os.sep)
    while True:
        for filename in filenames:
            file_path = os.path.join(current_dir, filename)
            if os.path.exists(file_path):
                return file_path

        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:
            return default

        # root
        if parent_dir == root_dir:
            return default
        current_dir = parent_dir

    return default


def hash_bytestr_iter(bytesiter, hasher, ashexstr=False):
    for block in bytesiter:
        hasher.update(block)
    return (hasher.hexdigest() if ashexstr else hasher.digest())

def file_as_blockiter(afile, blocksize=65536):
    with afile:
        block = afile.read(blocksize)
        while len(block) > 0:
            yield block
            block = afile.read(blocksize)

def checksum(fname):
    """memory-efficient check sum (sha256)

    source: https://stackoverflow.com/a/3431835/2192272
    """
    return hash_bytestr_iter(file_as_blockiter(open(fname, 'rb')), hashlib.sha256())



# move / copy
def move(f1, f2, copy=False, interactive=True, dryrun=False, hardlink=False):
    maybe = 'dry-run:: ' if dryrun else ''
    if f1 == f2:
        logger.info('dest is identical to src: '+f1)
        return
    dirname = os.path.dirname(f2)
    if dirname and not os.path.exists(dirname):
        logger.info(f'{maybe}create directory: {dirname}')
        if not dryrun: os.makedirs(dirname)

    if os.path.exists(f2):
        # if identical file, pretend nothing happened, skip copying
        if os.path.samefile(f1, f2) or checksum(f2) == checksum(f1):
            if not copy and not dryrun:
                logger.info(f'{maybe}rm {f1}')
                os.remove(f1)
            return

        elif interactive:
            ans = input(f'dest file already exists: {f2}. Replace? (y/n) ')
            if ans.lower() != 'y':
                return
        else:
            logger.info(f'{maybe}rm {f2}')
            if not dryrun:
                os.remove(f2)

    if copy:
        # If we can do a hard-link instead of copy-ing, let's do:
        def _hardlink(f1, f2):
            cmd = f'{maybe}ln {f1} {f2}'
            logger.info(cmd)
            if not dryrun:
                os.link(f1, f2)

        def _copy(f1, f2):
            logger.info(f'{maybe}cp {f1} {f2}')
            if not dryrun:
                shutil.copy(f1, f2)

        if hardlink:
            try:
                _hardlink(f1, f2)
            except:
                _copy(f1, f2)
        else:
            _copy(f1, f2)

    else:
        cmd = f'{maybe}mv {f1} {f2}'
        logger.info(cmd)
        if not dryrun:
            shutil.move(f1, f2)




@contextmanager
def set_directory(path: Path):
    """Sets the cwd within the context

    Args:
        path (Path): The path to the cwd

    Yields:
        None
    """

    origin = Path().absolute()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(origin)


def view_pdf(filepath):
    """
    https://stackoverflow.com/questions/434597/open-document-with-default-os-application-in-python-both-in-windows-and-mac-os
    """
    if platform.system() == 'Darwin':       # macOS
        subprocess.call(('open', filepath))
    elif platform.system() == 'Windows':    # Windows
        os.startfile(filepath)
    else:                                   # linux variants
        subprocess.call(('xdg-open', filepath))


def open_folder(path):
    system_platform = platform.system()

    if system_platform == "Windows":
        os.startfile(path)
    elif system_platform == "Darwin":  # macOS
        os.system(f'open "{path}"')
    elif system_platform == "Linux":
        os.system(f'xdg-open "{path}"')
    else:
        print("Unsupported operating system.")