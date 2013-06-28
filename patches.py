import collections
CACHE_VERSION = 5

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


            looks_like_patch = guess_if_patch(subject, mbox.get_string(key))

            summary = (timestamp, key, subject, in_reply_to, message_id, looks_like_patch)
    for timestamp, key, subject, in_reply_to, message_id, looks_like_patch in stuff:
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


output_reply_tree(new_cache)
