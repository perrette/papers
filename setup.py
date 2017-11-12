from distutils.core import setup
import versioneer

setup(name='myref',
      version=versioneer.get_version(),
      cmdclass = versioneer.get_cmdclass(),
      author='Mahe Perrette',
      author_email='mahe.perrette@gmail.com',
      description='utilities to keep your PDF library organized',
      url='https://github.com/perrette/myref',
      packages=['myref'],
      scripts=['scripts/myref'],
      license = "MIT",
      requires = ["bibtexparser","crossrefapi","fuzzywuzzy", "six"],
      )

