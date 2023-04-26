import os
import shutil
import hashlib

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
def move(f1, f2, copy=False, interactive=True, dryrun=False):
    dirname = os.path.dirname(f2)
    if dirname and not os.path.exists(dirname):
        logger.info('create directory: '+dirname)
        os.makedirs(dirname)
    if f1 == f2:
        logger.info('dest is identical to src: '+f1)
        return

    if os.path.exists(f2):
        # if identical file, pretend nothing happened, skip copying
        if checksum(f2) == checksum(f1):
            if not copy:
                os.remove(f1)
            return

        elif interactive:
            ans = input('dest file already exists: '+f2+'. Replace? (y/n) ')
            if ans.lower() != 'y':
                return
        else:
            os.remove(f2)

    if copy:
        cmd = 'cp {} {}'.format(f1, f2)
        logger.info(cmd)
        if not dryrun:
            shutil.copy(f1, f2)
    else:
        cmd = 'mv {} {}'.format(f1, f2)
        logger.info(cmd)
        if not dryrun:
            shutil.move(f1, f2)