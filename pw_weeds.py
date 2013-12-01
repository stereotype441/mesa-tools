import collections
import re
import subprocess
import sys

PW_SUBJECT_REGEXP = re.compile(r'[^[]*\[[^]]*\](.*)')

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
    commits.append((sha, subject.strip()))

for sha, subject in commits:
    print('# {0}'.format(subject))
    for line in pwrun(['/home/pberry/bin/pwclient', 'search', subject]):
        patch_id, state, rest = line.split(None, 2)
        if not patch_id.isdigit():
            # print('# Rejecting patch {0!r} because this is not a patch ID'.format(patch_id))
            continue
        if state == 'Accepted':
            print('# Rejecting patch {0} because state is accepted'.format(patch_id))
            continue
        m = PW_SUBJECT_REGEXP.match(rest)
        if m is None:
            print("# Rejecting patch {0} because its subject couldn't be found in the string {1!r}".format(patch_id, rest))
            continue
        patch_subject = m.group(1).strip()
        if subject != patch_subject:
            print('# Rejecting patch {0} because its subject ({1!r}) does not match'.format(patch_id, patch_subject))
            continue
        print('pwclient update -s Accepted -c {0} {1} # was: {2}'.format(sha, patch_id, state))
