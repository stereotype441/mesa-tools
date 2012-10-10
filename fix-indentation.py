# Fix indentation in a python file to use 4 spaces.

import re
import sys

INDENTATION_REGEXP = re.compile('[ \t]*')
PARSE_POINT = re.compile('[\n\'"()\\[\\]{}#\\\\]')

def test():
    """foo
    bar
    baz"""
    TEST1 = ('foo',
             'bar',
             'baz')
    TEST2 = ['foo',
             'bar',
             'baz']
    TEST3 = {'foo': 'bar',
             'baz': 'bar'}
    TEST4 = """foo
bar
baz"""

def test2():
	   	 "tab space space space tab space"
                 pass

def test3():
        if foo \
           and bar \
           and baz:
                return 1

def find_string_end(text, delimiter, pos):
    while pos < len(text):
        next_backslash_pos = text.find('\\', pos)
        next_delimiter_pos = text.find(delimiter, pos)
        if next_delimiter_pos == -1:
            return len(text)
        if next_backslash_pos == -1:
            return next_delimiter_pos + len(delimiter)
        if next_delimiter_pos < next_backslash_pos:
            return next_delimiter_pos + len(delimiter)
        pos = next_backslash_pos + 2
    return len(text)


def pre_parse(text):
    # Break the input into tokens and yield (token_type, text)
    # Token types are:
    # 'string'
    # 'comment'
    # 'newline'
    # 'open' (any of '(', '[', or '{')
    # 'close' (any of ')', ']', or '}')
    # 'text' (anything else)
    pos = 0
    while True:
        m = PARSE_POINT.search(text, pos)
        if not m:
            if pos < len(text):
                yield 'text', text[pos:]
            break
        if m.start() > pos:
            yield 'text', text[pos:m.start()]
        if m.group()[0] in '\'"':
            if m.end() + 2 <= len(text) \
                    and text[m.end()] == m.group() \
                    and text[m.end()+1] == m.group():
                delimiter = m.group() * 3
            else:
                delimiter = m.group()
            string_end = find_string_end(text,
                                         delimiter,
                                         m.start() + len(delimiter))
            yield 'string', text[m.start():string_end]
            pos = string_end
            continue
        if m.group() == '\n':
            yield 'newline', m.group()
        elif m.group() in '([{':
            yield 'open', m.group()
        elif m.group() in ')]}':
            yield 'close', m.group()
        elif m.group() == '#':
            comment_end = text.find('\n', m.end())
            if comment_end == -1:
                comment_end = len(text)
            yield 'comment', text[m.start():comment_end]
            pos = comment_end
            continue
        elif m.group() == '\\':
            if m.end() < len(text) and text[m.end()] == '\n':
                yield 'text', '\\\n'
                pos = m.end() + 1
                continue
            else:
                yield 'text', m.group()
        else:
            raise Exception(m.group())
        pos = m.end()


def measure_indent(str):
    amount = 0
    indent_str = INDENTATION_REGEXP.match(str).group()
    for c in indent_str:
        amount += 1
        if c == '\t':
            amount += (-amount) % 8
    return amount, indent_str

class LogicalLine(object):
    def __init__(self, str):
        self.physical_lines = str.split('\n')
        self.indent_amount, self.indent_str = measure_indent(
            self.physical_lines[0])
        self.normal_indent = all(
            len(p) == 0 or p.isspace() or p.startswith(self.indent_str)
            for p in self.physical_lines)
        self.is_empty = len(self.physical_lines) == 1 \
            and self.indent_str == self.physical_lines[0]

    def reindent(self, new_amount):
        delta = new_amount - self.indent_amount
        def reindent_phys_line(phys_line):
            old_amount, old_indent_str = measure_indent(phys_line)
            if old_indent_str == phys_line:
                return ''
            return ' '*(old_amount + delta) + phys_line[len(old_indent_str):]
        if self.indent_amount == 0 and new_amount == 0:
            return '\n'.join(self.physical_lines)
        elif self.normal_indent:
            return '\n'.join(reindent_phys_line(phys_line)
                             for phys_line in self.physical_lines)
        else:
            return reindent_phys_line('\n'.join(self.physical_lines))


def parse_logical_lines(text):
    logical_line = ''
    nesting = 0
    for token_type, str in pre_parse(text):
        if token_type == 'newline' and nesting == 0:
            yield LogicalLine(logical_line)
            logical_line = ''
            continue
        elif token_type == 'open':
            nesting += 1
        elif token_type == 'close' and nesting > 0:
            nesting -= 1
        logical_line += str
    yield LogicalLine(logical_line)


def fix_tabs(text, new_indent = 4):
    old_indents = [0]
    new_indents = [0]
    for line in parse_logical_lines(text):
        if line.is_empty:
            yield ''
            continue
        while line.indent_amount < old_indents[-1]:
            old_indents.pop()
            new_indents.pop()
        if line.indent_amount > old_indents[-1]:
            old_indents.append(line.indent_amount)
            new_indents.append(new_indents[-1] + new_indent)
        yield line.reindent(new_indents[-1])


with open(sys.argv[1], 'r') as f:
    new_contents = '\n'.join(fix_tabs(f.read()))

with open(sys.argv[1], 'w') as f:
    f.write(new_contents)
