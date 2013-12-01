import collections
import re
import subprocess
import sys

sha_range = sys.argv[1]

def pwrun(args):
    for i in range(5):
        try:
            result = subprocess.check_output(args).decode('Latin-1').splitlines()
            return result
        except:
            pass

commits = []
for line in subprocess.check_output(['git', 'log', '--format=format:%H:%s', sha_range]).decode('Latin-1').splitlines():
    sha, subject = line.split(':', 1)
    commits.append((sha, subject))

for sha, subject in commits:
    print('# {0}'.format(subject))
    for line in pwrun(['/home/pberry/bin/pwclient', 'search', subject]):
        patch_id, state, rest = line.split(None, 2)
        if patch_id.isdigit() and state != 'Accepted':
            print('pwclient update -s Accepted -c {0} {1} # was: {2}'.format(sha, patch_id, state))
