# TODO: for patches that are candidates for updates:
# - Use "git show" of "git format-patch" to generate a patch based on the commit
# - Strip out innocuous headers
# - Diff the mailing list patch against the true patch using "diff -u -w -I'^\(@\|index\)'"

import collections
import argparse
import re
import subprocess

PW_SUBJECT_REGEXP = re.compile(r'[^[]*\[[^]]*\](.*)')
PW_INFO_REGEXP = re.compile(r'\- ([a-z_]+) +: (.*)')

parser = argparse.ArgumentParser(description='Find patchwork patches that probably should be in "Accepted" state')
parser.add_argument('sha_range', help='Range of SHAs to examine')
parser.add_argument('--hash', dest='use_hash', action='store_true', help='Match patches by hash')
args = parser.parse_args()

def pwrun_list(args):
    for i in range(5):
        try:
            result = subprocess.check_output(args).decode('Latin-1').splitlines()
            return result
        except:
            pass

def pwrun_info(args):
    for i in range(5):
        p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdoutdata, stderrdata = p.communicate('')
        if p.returncode != 0:
            if stderrdata.decode('Latin-1').strip() == 'No patch has the hash provided':
                return []
            continue
        return stdoutdata.decode('Latin-1').splitlines()
    print('# Failed to run pwclient: {0}'.format(args))
    return []

commits = []
for line in subprocess.check_output(['git', 'log', '--format=format:%H:%s', args.sha_range]).decode('Latin-1').splitlines():
    sha, subject = line.split(':', 1)
    commits.append((sha, subject.strip()))

for sha, subject in commits:
    print('# {0}'.format(subject))
    pw_command = ['/home/pberry/bin/pwclient']
    if args.use_hash:
        commit_body = subprocess.check_output(['git', 'show', sha])
        p = subprocess.Popen(['python2', '/home/pberry/patchwork/apps/patchwork/parser.py', '--hash'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        stdoutdata, stderrdata = p.communicate(commit_body)
        if p.returncode != 0:
            print('# Could not hash this patch')
            continue
        patch_hash = stdoutdata.strip()
        pw_command.extend(['info', '-h', patch_hash.decode('utf-8')])
        patch_id = None
        state = None
        for line in pwrun_info(pw_command):
            m = PW_INFO_REGEXP.match(line)
            if m is None:
                continue
            key = m.group(1)
            value = m.group(2)
            if key == 'id':
                patch_id = value
            elif key == 'state':
                state = value
        if patch_id is None:
            continue
        print('pwclient update -s Accepted -c {0} {1} # was: {2}'.format(sha, patch_id, state))
    else:
        pw_command.extend(['search', subject])
        for line in pwrun_list(pw_command):
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
