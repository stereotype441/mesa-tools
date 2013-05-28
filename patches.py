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
CACHE_VERSION = 2

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

            summary = (timestamp, key, subject, in_reply_to, message_id)

        stuff.append(summary)
        new_cache['msgs'][key] = summary

    stuff.sort()

    print '  Creating patch files'.format(folder_name)
    for timestamp, key, subject, in_reply_to, message_id in stuff:
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
            timestamp, key, subject, in_reply_to, message_id = cache['msgs'][key]
            msg_to_reply_map[in_reply_to].append((timestamp, message_id, subject))
        already_printed_message_ids = set()
        def dump_tree(prefix, message_id):
            for timestamp, reply_id, subject in sorted(msg_to_reply_map[message_id]):
                f.write(prefix + '- ' + subject.encode('unicode_escape') + '\n')
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
