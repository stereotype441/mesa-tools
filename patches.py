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

MBOX_DIR = os.path.expanduser('~/gmail/Mesa-dev')
mbox = mailbox.Maildir(MBOX_DIR, create = False)

stuff = []
by_id = {}

SAFE_SUBJECT_CHARS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz'

PATCHES_DIR = os.path.expanduser('~/patches')

try:
    os.makedirs(PATCHES_DIR)
except OSError:
    pass

def decode_rfc2047_part(s, encoding):
    if encoding is None or encoding in ['y', 'n', 'a']:
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

for key in mbox.keys():
    msg = mbox[key]
    decoded_subj = email.header.decode_header(msg['Subject'].replace('\n', ''))
    subject = ' '.join(decode_rfc2047_part(s, e) for s, e in decoded_subj)

    # TODO: email.utils.mktime_tz makes slight errors around daylight savings time.
    timestamp = email.utils.mktime_tz(email.utils.parsedate_tz(msg['Date']))

    message_id = msg['Message-Id']
    in_reply_to = msg['In-Reply-To'].split()[0] if 'In-Reply-To' in msg else None

    summary = (timestamp, key, subject, in_reply_to)

    stuff.append(summary)
    by_id[message_id] = summary

stuff.sort()

for timestamp, key, subject, in_reply_to in stuff:
    if subject.find('[PATCH') == -1 or subject.lower().startswith('re'):
        continue

    filename = '{0}-{1}.patch'.format(nice_time(timestamp), safe_subject(subject)[:40])
    path = os.path.join(PATCHES_DIR, filename)
    if not os.path.exists(path):
        msg_str = mbox.get_string(key)
        with open(path, 'w') as f:
            f.write(msg_str)
        print path
