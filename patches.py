# coding=utf8
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
CACHE_VERSION = 9
KNOWN_EMAILS = {
    'maraeo@gmail.com': u'Marek Olšák',
    'sroland@vmware.com': 'Roland Scheidegger',
    'ville.syrjala@linux.intel.com': u'Ville Syrjälä',
    'bugzilla-daemon@freedesktop.org': '(bugzilla)',
    'jfonseca@vmware.com': u'José Fonseca',
    'alexdeucher@gmail.com': 'Alex Deucher',
    'junyan.he@linux.intel.com': 'Junyan He',
    'j.glisse@gmail.com': 'Jerome Glisse',
    'chad.versace@linux.intel.com': 'Chad Versace',
    'groleo@gmail.com': 'Adrian Marius Negreanu',
    'Ritvik_Sharma@Dell.com': 'Ritvik Sharma',
    'piglit-bounces@lists.freedesktop.org': '(bounce)',
    'Dmitry@freedesktop.org': 'Dmitry Cherkassov',
    'tom@stellard.net': 'Tom Stellard',
    'tstellar@gmail.com': 'Tom Stellard',
    'oliver.mcfadden@linux.intel.com': 'Oliver McFadden',
    'anuj.phogat@gmail.com': 'Anuj Phogat',
    'jbenton@vmware.com': 'James Benton',
    'zhiwen.wu@linux.intel.com': 'Alex Wu',
    'mandeep.baines@gmail.com': 'Mandeep Singh Baines',
    'jose.r.fonseca@gmail.com': u'José Fonseca',
    'zhigang.gong@linux.intel.com': 'Zhigang Gong',
    'juan.j.zhao@linux.intel.com': 'Juan Zhao',
    'kallisti5@unixzen.com': 'Alexander von Gluck IV',
    'christoph@bumiller.com': 'Christoph Bumiller',
    'tfogal@sci.utah.edu': 'Tom Fogal',
    'deathsimple@vodafone.de': u'Christian König',
    'younes.m@gmail.com': 'Younes Manton',
    'tapani.palli@intel.com': u'Tapani Pälli',
}

PATCHES_DIR = os.path.expanduser('~/patches')

try:
    os.makedirs(PATCHES_DIR)
except OSError:
    pass


MessageInfo = collections.namedtuple('MessageInfo', (
    'timestamp', 'key', 'subject', 'in_reply_to', 'message_id', 'analysis', 'sender'))


PatchAnalysis = collections.namedtuple('PatchAnalysis', (
    'diffs_found',))


def decode_rfc2047_part(s, encoding):
    if encoding is None or encoding in ['y', 'n', 'a', 'j']:
        return s
    return s.decode(encoding)

def decode_header(header):
    parts = email.header.decode_header(header.replace('\n', ''))
    return ' '.join(decode_rfc2047_part(s, e) for s, e in parts)

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


def analyze_patch(subject, data):
    # TODO: debug [Piglit] [PATCH 1/3] piglit util: new functions piglit_program_pipeline_check_status/quiet
    # TODO: handle multipart messages, e.g. [Piglit] [PATCH] Check for glsl before compiling a shader.
    # TODO: handle renames, e.g. [Piglit] [PATCH 4/8] move variable-index-read.sh and variable-index-write.sh to generated_tests
    # TODO: handle mode changes, e.g. [Mesa-dev] [PATCH 1/6] intel: remove executable bit from C file
    # TODO: handle multipart base64 messages, e.g. [Mesa-dev] [PATCH] Fix glXChooseFBConfig with GLX_DRAWABLE_TYPE GLX_DONT_CARE
    print('Interpreting message {0!r}'.format(subject))
    m = email.message_from_string(data)
    if m.is_multipart():
        print('Multipart message: {0!r}'.format(subject))
        return PatchAnalysis(False)
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
    return PatchAnalysis(diffs_found)


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
            subject = decode_header(msg['Subject'])

            # TODO: email.utils.mktime_tz makes slight errors around daylight savings time.
            timestamp = email.utils.mktime_tz(email.utils.parsedate_tz(msg['Date']))

            message_id = decode_header(msg['Message-Id'])
            in_reply_to = decode_header(msg['In-Reply-To']).split()[0] if 'In-Reply-To' in msg else None

            analysis = analyze_patch(subject, mbox.get_string(key))
            sender = decode_header(msg['From'])

            summary = MessageInfo(timestamp, key, subject, in_reply_to, message_id, analysis, sender)

        stuff.append(summary)
        new_cache['msgs'][key] = summary

    stuff.sort()

    print '  Creating patch files'.format(folder_name)
    for msg_info in stuff:
        if msg_info.subject.lower().startswith('re'):
            continue
        if not (PATCH_REGEXP.search(msg_info.subject) or msg_info.analysis.diffs_found):
            continue

        filename = '{0}-{1}.patch'.format(nice_time(msg_info.timestamp), safe_subject(msg_info.subject)[:40])
        path = os.path.join(PATCHES_DIR, filename)
        summary_data.append((msg_info.timestamp, msg_info.subject, path, msg_info.key))
        if not os.path.exists(path):
            msg_str = mbox.get_string(msg_info.key)
            with open(path, 'w') as f:
                f.write(msg_str)
            print path


def short_sender(sender):
    NAME_WIDTH = 16
    real, addr = email.utils.parseaddr(sender)
    if addr in KNOWN_EMAILS:
        name = KNOWN_EMAILS[addr]
    elif real:
        name = real
    else:
        name = addr
    name += ' ' * NAME_WIDTH
    return name[0:NAME_WIDTH]


def output_reply_tree(cache):
    with open(os.path.join(PATCHES_DIR, 'replies.txt'), 'w') as f:
        msg_to_reply_map = collections.defaultdict(list)
        for key in cache['msgs']:
            msg_info = cache['msgs'][key]
            msg_to_reply_map[msg_info.in_reply_to].append((msg_info.timestamp, msg_info.message_id, msg_info.subject, msg_info.analysis, msg_info.sender))
        already_printed_message_ids = set()
        def dump_tree(prefix, message_id):
            for timestamp, reply_id, subject, analysis, sender in sorted(msg_to_reply_map[message_id]):
                if analysis.diffs_found:
                    tickmark = '*'
                elif not PATCH_REGEXP.search(subject) or subject.lower().startswith('re'):
                    tickmark = 'x'
                else:
                    tickmark = '-'
                f.write(nice_time(timestamp) + ' ' + short_sender(sender).encode('utf8') + prefix + tickmark + ' ' +
                        subject.encode('unicode_escape') + '\n')
                if reply_id in already_printed_message_ids:
                    f.write(prefix + '  ...\n')
                else:
                    already_printed_message_ids.add(reply_id)
                    dump_tree(prefix + '  ', reply_id)
        dump_tree(' ', None)


def reconstitute_cache(cache):
    msgs = cache['msgs']
    for key in msgs:
        timestamp, key, subject, in_reply_to, message_id, analysis, sender = msgs[key]
        analysis = PatchAnalysis(*analysis)
        msgs[key] = MessageInfo(timestamp, key, subject, in_reply_to, message_id, analysis, sender)


old_cache = {'cache_version': CACHE_VERSION, 'msgs': {}}
try:
    with open(os.path.join(PATCHES_DIR, 'cache.json'), 'r') as f:
        cache = json.load(f)
    if 'cache_version' in cache and cache['cache_version'] == CACHE_VERSION:
        old_cache = cache
        reconstitute_cache(old_cache)
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
    json.dump(new_cache, f, indent=2)
