# This script generates a ~/patches dir containing all patches from
# the mailing lists.
#
# It assumes that offlineimap has been used to download the mailing
# list messages to ~/gmail.

import cStringIO
import datetime
import email.utils
import mailbox
import os.path
import json

SAFE_SUBJECT_CHARS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz'

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
        if key in old_cache:
            summary = old_cache[key]
        else:
            msg = mbox[key]
            decoded_subj = email.header.decode_header(msg['Subject'].replace('\n', ''))
            subject = ' '.join(decode_rfc2047_part(s, e) for s, e in decoded_subj)

            # TODO: email.utils.mktime_tz makes slight errors around daylight savings time.
            timestamp = email.utils.mktime_tz(email.utils.parsedate_tz(msg['Date']))

            message_id = msg['Message-Id']
            in_reply_to = msg['In-Reply-To'].split()[0] if 'In-Reply-To' in msg else None

            summary = (timestamp, key, subject, in_reply_to)

        stuff.append(summary)
        new_cache[key] = summary

    stuff.sort()

    print '  Creating patch files'.format(folder_name)
    for timestamp, key, subject, in_reply_to in stuff:
        if subject.find('[PATCH') == -1 or subject.lower().startswith('re'):
            continue

        filename = '{0}-{1}.patch'.format(nice_time(timestamp), safe_subject(subject)[:40])
        path = os.path.join(PATCHES_DIR, filename)
        summary_data.append((timestamp, subject, path, key))
        if not os.path.exists(path):
            msg_str = mbox.get_string(key)
            with open(path, 'w') as f:
                f.write(msg_str)
            print path


old_cache = {}
try:
    with open(os.path.join(PATCHES_DIR, 'cache.json'), 'r') as f:
        old_cache = json.load(f)
except Exception, e:
    print 'Non-fatal error loading old cache.json: {0}'.format(e)

new_cache = {}
summary_data = []
for folder_name in ['Mesa-dev', 'Piglit']:
    make_patches_from_mail_folder(folder_name, summary_data, old_cache, new_cache)


summary_data.sort()
with open(os.path.join(PATCHES_DIR, 'summary.txt'), 'w') as f:
    f.write(''.join('{0} {1!r}: {2!r}\n'.format(nice_time(timestamp), subject, path)
                    for timestamp, subject, path, _ in summary_data))

with open(os.path.join(PATCHES_DIR, 'cache.json'), 'w') as f:
    json.dump(new_cache, f)
