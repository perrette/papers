"""The backup commits on a machine where git has no user name and email
(fresh install, CI, containers): papers commits with a fallback identity,
and keeps the user's identity when there is one"""
import os
import subprocess as sp
import sys
import tempfile
import unittest
from pathlib import Path

import papers
from tests.test_pools import NEW_BIB


class TestGitIdentity(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir = os.path.realpath(self.temp_dir.name)
        self.gitconfig = os.path.join(self.dir, 'gitconfig')
        # no automatic identity from the host name either
        Path(self.gitconfig).write_text('[user]\n\tuseConfigOnly = true\n')
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('GIT_AUTHOR_', 'GIT_COMMITTER_')) and k not in ('EMAIL', 'GIT_CONFIG')}
        env.update(HOME=os.path.join(self.dir, 'home'), XDG_CONFIG_HOME=os.path.join(self.dir, 'config'),
                   XDG_DATA_HOME=os.path.join(self.dir, 'data'), GIT_CONFIG_GLOBAL=self.gitconfig,
                   GIT_CONFIG_NOSYSTEM='1', PYTHONPATH=str(Path(papers.__file__).parent.parent))
        self.env = env
        os.makedirs(env['HOME'])
        Path(self.dir, 'new.bib').write_text(NEW_BIB)

    def tearDown(self):
        self.temp_dir.cleanup()

    def papers(self, *args):
        return sp.run([sys.executable, '-m', 'papers'] + list(args), cwd=os.path.join(self.dir, 'lib'),
                      env=self.env, capture_output=True, text=True, check=True)

    def test_no_identity(self):
        os.makedirs(os.path.join(self.dir, 'lib'))
        res = self.papers('init', '--git', '--local')
        self.assertNotIn('identity', res.stderr)
        res = self.papers('add', '../new.bib')
        self.assertNotIn('identity', res.stderr)
        self.assertNotIn('could not commit', res.stderr)
        log = self.papers('git', 'log', '--format=%an <%ae>|%cn <%ce>').stdout.splitlines()
        self.assertEqual(len(log), 2)
        self.assertEqual(set(log), {'papers <papers@localhost>|papers <papers@localhost>'})
        # undo and redo append commits too (git commit-tree)
        res = self.papers('undo')
        self.assertNotIn('identity', res.stderr)
        self.assertEqual(len(self.papers('git', 'log', '--format=%h').stdout.splitlines()), 3)

    def test_user_identity_kept(self):
        with open(self.gitconfig, 'a') as f:
            f.write('\tname = Jane Doe\n\temail = jane@example.org\n')
        os.makedirs(os.path.join(self.dir, 'lib'))
        self.papers('init', '--git', '--local')
        self.papers('add', '../new.bib')
        log = self.papers('git', 'log', '--format=%an <%ae>|%cn <%ce>').stdout.splitlines()
        self.assertEqual(set(log), {'Jane Doe <jane@example.org>|Jane Doe <jane@example.org>'})

    def test_name_only(self):
        with open(self.gitconfig, 'a') as f:
            f.write('\tname = Jane Doe\n')
        os.makedirs(os.path.join(self.dir, 'lib'))
        self.papers('init', '--git', '--local')
        log = self.papers('git', 'log', '--format=%an <%ae>').stdout.splitlines()
        self.assertEqual(log, ['Jane Doe <papers@localhost>'])
