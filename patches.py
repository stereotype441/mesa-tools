# This script generates a ~/patches dir containing all patches from
# the mailing lists.
#
# It assumes that offlineimap has been used to download the mailing
# list messages to ~/gmail.

import collections
import cStringIO
import datetime
import email.utils
import mailbox
import os.path
import json
import re

SAFE_SUBJECT_CHARS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz'
PATCH_REGEXP = re.compile(r'\[[A-Z ]*PATCH')
CACHE_VERSION = 5

PATCHES_DIR = os.path.expanduser('~/patches')

try:
    os.makedirs(PATCHES_DIR)
except OSError:
    pass

def decode_rfc2047_part(s, encoding):
    if encoding is None or encoding in ['y', 'n', 'a', 'j']:
        return s
    return s.decode(encoding)

def safe_subject(subject):
    while True:
        for prefix in ['[Piglit] ', '[Mesa-dev] ']:
            if subject.startswith(prefix):
                subject = subject[len(prefix):]
                break
        else:
            break
    result = ''
    for c in subject:
        if c in SAFE_SUBJECT_CHARS:
            result += c
        elif len(result) > 0 and result[-1] != '-':
            result += '-'
    return result

def nice_time(timestamp):
    dt = datetime.datetime.utcfromtimestamp(timestamp)
    return dt.strftime('%Y%m%d-%H%M%S')


def guess_if_patch(subject, data):
    # TODO: debug [Piglit] [PATCH 1/3] piglit util: new functions piglit_program_pipeline_check_status/quiet
    # TODO: handle multipart messages, e.g. [Piglit] [PATCH] Check for glsl before compiling a shader.
    # TODO: handle renames, e.g. [Piglit] [PATCH 4/8] move variable-index-read.sh and variable-index-write.sh to generated_tests
    # TODO: handle mode changes, e.g. [Mesa-dev] [PATCH 1/6] intel: remove executable bit from C file
    # TODO: handle multipart base64 messages, e.g. [Mesa-dev] [PATCH] Fix glXChooseFBConfig with GLX_DRAWABLE_TYPE GLX_DONT_CARE
    print('Interpreting message {0!r}'.format(subject))
    m = email.message_from_string(data)
    if m.is_multipart():
        print('Multipart message: {0!r}'.format(subject))
        return False
    data = m.get_payload(None, True)
    state = 0
    diffs_found = False
    for line in data.split('\n'):
        if state == 0:
            if line == '---':
                state = 1
        elif state == 1:
            if line.startswith('diff '):
                state = 2
            elif line == '-- ':
                state = 0
        elif state == 2:
            if line.startswith('index '):
                state = 1
                diffs_found = True
            elif line.startswith('new file mode '):
                pass
            else:
                state = 1
    return diffs_found


def make_patches_from_mail_folder(folder_name, summary_data, old_cache, new_cache):
    print 'Making patches from mail folder {0}'.format(folder_name)
    mbox_dir = os.path.join(os.path.expanduser('~/gmail'), folder_name)
    mbox = mailbox.Maildir(mbox_dir, create = False)

    stuff = []

    print '  Gathering data from mailbox'.format(folder_name)
    for key in mbox.keys():
        if key in old_cache['msgs']:
            summary = old_cache['msgs'][key]
        else:
            msg = mbox[key]
            decoded_subj = email.header.decode_header(msg['Subject'].replace('\n', ''))
            subject = ' '.join(decode_rfc2047_part(s, e) for s, e in decoded_subj)

            # TODO: email.utils.mktime_tz makes slight errors around daylight savings time.
            timestamp = email.utils.mktime_tz(email.utils.parsedate_tz(msg['Date']))

            message_id = msg['Message-Id']
            in_reply_to = msg['In-Reply-To'].split()[0] if 'In-Reply-To' in msg else None

            looks_like_patch = guess_if_patch(subject, mbox.get_string(key))

            summary = (timestamp, key, subject, in_reply_to, message_id, looks_like_patch)

        stuff.append(summary)
        new_cache['msgs'][key] = summary

    stuff.sort()

    print '  Creating patch files'.format(folder_name)
    for timestamp, key, subject, in_reply_to, message_id, looks_like_patch in stuff:
        if not PATCH_REGEXP.search(subject) or subject.lower().startswith('re'):
            continue

        filename = '{0}-{1}.patch'.format(nice_time(timestamp), safe_subject(subject)[:40])
        path = os.path.join(PATCHES_DIR, filename)
        summary_data.append((timestamp, subject, path, key))
        if not os.path.exists(path):
            msg_str = mbox.get_string(key)
            with open(path, 'w') as f:
                f.write(msg_str)
            print path


def output_reply_tree(cache):
    with open(os.path.join(PATCHES_DIR, 'replies.txt'), 'w') as f:
        msg_to_reply_map = collections.defaultdict(list)
        for key in cache['msgs']:
            timestamp, key, subject, in_reply_to, message_id, looks_like_patch = cache['msgs'][key]
            msg_to_reply_map[in_reply_to].append((timestamp, message_id, subject, looks_like_patch))
        already_printed_message_ids = set()
        def dump_tree(prefix, message_id):
            for timestamp, reply_id, subject, looks_like_patch in sorted(msg_to_reply_map[message_id]):
                if looks_like_patch:
                    tickmark = '*'
                elif not PATCH_REGEXP.search(subject) or subject.lower().startswith('re'):
                    tickmark = 'x'
                else:
                    tickmark = '-'
                f.write(prefix + tickmark + ' ' + subject.encode('unicode_escape') + '\n')
                if reply_id in already_printed_message_ids:
                    f.write(prefix + '  ...\n')
                else:
                    already_printed_message_ids.add(reply_id)
                    dump_tree(prefix + '  ', reply_id)
        dump_tree('', None)


old_cache = {'cache_version': CACHE_VERSION, 'msgs': {}}
try:
    with open(os.path.join(PATCHES_DIR, 'cache.json'), 'r') as f:
        cache = json.load(f)
    if 'cache_version' in cache and cache['cache_version'] == CACHE_VERSION:
        old_cache = cache
    else:
        print 'cache.json is out of date.  Rebuilding.'
except Exception, e:
    print 'Non-fatal error loading old cache.json: {0}'.format(e)

new_cache = {'cache_version': CACHE_VERSION, 'msgs': {}}
summary_data = []
for folder_name in ['Mesa-dev', 'Piglit']:
    make_patches_from_mail_folder(folder_name, summary_data, old_cache, new_cache)


summary_data.sort()
with open(os.path.join(PATCHES_DIR, 'summary.txt'), 'w') as f:
    f.write(''.join('git am -3 {2!r} # {0} {1!r}\n'.format(nice_time(timestamp), subject, path)
                    for timestamp, subject, path, _ in summary_data))

output_reply_tree(new_cache)

with open(os.path.join(PATCHES_DIR, 'cache.json'), 'w') as f:
    json.dump(new_cache, f)
