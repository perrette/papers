from distutils.core import setup
import versioneer

version = versioneer.get_version()

setup(name='papers-cli',
      version=version,
      cmdclass = versioneer.get_cmdclass(),
      author='Mahe Perrette',
      author_email='mahe.perrette@gmail.com',
      description='utilities to keep your PDF library organized',
      url='https://github.com/perrette/papers',
      download_url=f'https://github.com/perrette/papers/archive/{version}.tar.gz',
      packages=['papers'],
      scripts=['scripts/papers'],
      license = "MIT",
      requires = ["bibtexparser","crossrefapi","rapidfuzz", "unidecode", "scholarly", "six"],
      )
