import subprocess as sp
# setup user name and user email if not set (otherwise commit will fail)
sp.check_call('git config --list | grep user.name || git config --global user.name "Papers Tests"', shell=True)
sp.check_call('git config --list | grep user.email || git config --global user.email "papers.tests@github.com"', shell=True)
del sp