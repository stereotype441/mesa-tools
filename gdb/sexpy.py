import unittest
import re

def finishme(*detail):
    raise Exception("finishme({0})".format(', '.join(repr(s) for s in detail)))

def parse_template(template):
    """Convert a sexp template into a convenient internal
    representation for execution.

    The internal representation looks like lisp code which calls the
    following functions:
    - 'quote' outputs its argument, without evaluating it.
    - 'list' evaluates each of its arguments and creates a string
      containing the results
    - 'eval' evaluates its argument in Python
    - 'concat' evaluates each of its arguments (which must eval to
      lists) and concatenates the results together.

    For example:
    (a b c) => ('quote', ('a', 'b', 'c'))
    (a ,b c) => ('list', ('quote', 'a'), ('eval', 'b'), ('quote', 'c'))
    (a ,@b c) => ('concat', ('quote', ('a',)), ('eval', 'b'), ('quote', ('c',))

    The "," and ",@" operators match until the next space that occurs
    outside of (), {}, or []."""
    parsed = list(_Parser(template).parse_all())
    if len(parsed) != 1:
        raise Exception("parse_template must be passed exactly one sexp")
    return _optimize_template(_make_template(parsed[0]))

class _Parser(object):
    """Parse a sexp that may contain "," or ",@" operators."""
    def __init__(self, s):
        self._s = s
        self._i = 0
        self._len = len(s)
        prefixes = (',@', ',')
        self._prefixes = tuple(
            (re.compile(re.escape(prefix)), prefix) for prefix in prefixes)
        self._symbol_regex = re.compile('[a-zA-Z_][a-zA-Z0-9_]*')

    def parse_all(self):
        while True:
            item = self.parse_sexp()
            if item is not None:
                yield item
            else:
                if self._i < self._len:
                    assert self._s[self._i] == ')'
                    raise Exception("Unmatched )")
                break

    def parse_sexp(self):
        while self._i < self._len:
            if self._s[self._i].isspace():
                self._i += 1
            else:
                break
        else:
            return # No sexp found
        for prefix_regex, prefix in self._prefixes:
            m = prefix_regex.match(self._s, self._i)
            if m:
                self._i = m.end()
                rhs = self.parse_python()
                return (prefix, rhs)
        c = self._s[self._i]
        if c == ')':
            return
        if c == '(':
            self._i += 1
            items = []
            while True:
                item = self.parse_sexp()
                if item is not None:
                    items.append(item)
                else:
                    break
            if self._i >= self._len:
                raise Exception("Unmatched (")
            assert self._s[self._i] == ')'
            self._i += 1
            return tuple(items)
        m = self._symbol_regex.match(self._s, self._i)
        if m:
            self._i = m.end()
            return m.group()
        raise Exception(
            "Unrecognized input: %s" % (self._s[self._i:self._i+20]))

    def parse_python(self):
        start_pos = self._i
        nesting_level = 0
        while self._i < self._len:
            c = self._s[self._i]
            if c.isspace():
                if nesting_level == 0:
                    break
            elif c in "([{":
                nesting_level += 1
            elif c in ")]}":
                if nesting_level > 0:
                    nesting_level -= 1
                else:
                    break
            self._i += 1
        expr = self._s[start_pos:self._i]
        if nesting_level != 0:
            raise Exception("Unterminated python expression %s" % expr)
        return expr

class _TestParse(unittest.TestCase):
    def test_basic(self):
        for s, expected_parse in (
            ('', []),
            ('a', ['a']),
            ('a b', ['a', 'b']),
            ('foo_bar123 x', ['foo_bar123', 'x']),
            (',x', [(',', 'x')]),
            (',@x', [(',@', 'x')]),
            (',(a b) c', [(',', '(a b)'), 'c']),
            ('(a b c)', [('a', 'b', 'c')]),
            ('(a ,b c)', [('a', (',', 'b'), 'c')]),
            ('(a ,@b c)', [('a', (',@', 'b'), 'c')]),
            (',[a b] c', [(',', '[a b]'), 'c']),
            (',{a b} c', [(',', '{a b}'), 'c']),
            ('()', [()]),
            ('( ) ', [()]),
            ('(())', [((),)]),
            ):
            actual_parse = list(_Parser(s).parse_all())
            if actual_parse != expected_parse:
                self.fail(
                    "{0!r} parsed to {1!r}, expected {2!r}".format(
                        s, actual_parse, expected_parse))

def _make_template(sexp):
    """Convert a sexp (as produced by _Parser) into a substitution
    template of the form output by parse_template.  Do not attempt to
    optimize the template."""
    tmp = _make_partial_template(sexp)
    if tmp[0] == 'eval':
        raise Exception(',@ only allowed inside lists')
    elif tmp[0] == 'quote':
        assert isinstance(tmp[1], tuple)
        assert len(tmp[1]) == 1
        return ('quote', tmp[1][0])
    else:
        assert tmp[0] == 'list'
        assert len(tmp) == 2
        return tmp[1]

def _make_partial_template(sexp):
    if isinstance(sexp, tuple):
        if len(sexp) > 0:
            if sexp[0] == ',':
                assert len(sexp) == 2
                return ('list', ('eval', sexp[1]))
            if sexp[0] == ',@':
                assert len(sexp) == 2
                return ('eval', sexp[1])
        return (
            'list', ('concat',) + tuple(
                _make_partial_template(term) for term in sexp))
    else:
        return ('quote', (sexp,))

def _optimize_template(template):
    """Optimize a substitution template, simplifying concatenations
    and literal lists."""
    if isinstance(template, tuple):
        template = (template[0],) + tuple(
            _optimize_template(term) for term in template[1:])
        if template[0] == 'concat':
            if len(template) == 1:
                return ('quote', ())
            sublists = [list(template[1])]
            for term in template[2:]:
                if sublists[-1][0] == 'quote' and term[0] == 'quote':
                    sublists[-1][1] += term[1]
                elif sublists[-1][0] in ('quote', 'list') and \
                        term[0] in ('quote', 'list'):
                    if sublists[-1][0] == 'quote':
                        assert isinstance(sublists[-1][1], tuple)
                        sublists[-1] = ['list'] + [
                            ('quote', x[0]) for x in sublists[-1][1]]
                    if term[0] == 'quote':
                        assert isinstance(term[1], tuple)
                        term = ('list',) + tuple(
                            ('quote', x[0]) for x in term[1])
                    sublists[-1].extend(term[1:])
                else:
                    sublists.append(list(term))
            if len(sublists) == 1:
                return tuple(sublists[0])
            return ('concat',) + tuple(tuple(t) for t in sublists)
        elif template[0] == 'list' and all(
            term[0] == 'quote' for term in template[1:]):
            return ('quote', tuple(term[1] for term in template[1:]))
    return template

class _TestParseTemplate(unittest.TestCase):
    def test_basic(self):
        for s, expected_template in (
            ('a', ('quote', 'a')),
            ('()', ('quote', ())),
            ('(a)', ('quote', ('a',))),
            ('(a b)', ('quote', ('a', 'b'))),
            (',a', ('eval', 'a')),
            ('(,a)', ('list', ('eval', 'a'))),
            ('(,a b)', ('list', ('eval', 'a'), ('quote', 'b'))),
            ('(a ,b)', ('list', ('quote', 'a'), ('eval', 'b'))),
            ('(,a ,b)', ('list', ('eval', 'a'), ('eval', 'b'))),
            ('(,@a)', ('eval', 'a')),
            ('(,@a b)', ('concat', ('eval', 'a'), ('quote', ('b',)))),
            ('(a ,@b)', ('concat', ('quote', ('a',)), ('eval', 'b'))),
            ('(,@a ,@b)', ('concat', ('eval', 'a'), ('eval', 'b'))),
            ('(())', ('quote', ((),))),
            ('(a b ,c)', (
                    'list', ('quote', 'a'), ('quote', 'b'), ('eval', 'c'))),
            ):
            actual_template = parse_template(s)
            if actual_template != expected_template:
                self.fail(
                    "{0!r} parsed to {1!r}, expected {2!r}".format(
                        s, actual_template, expected_template))

def compile_template(template):
    """Make a function that executes a template.  This function will
    need to be passed two arguments: globals and locals, which are
    analogous to the globals and locals arguments of eval().

    For example:
    a = 5
    assert compile_template("(x ,a)")(globals(), locals()) == ('x', 5)
    """
    return lambda g, l: _eval_template(parse_template(template), g, l)

def _eval_template(template, globals_dict, locals_dict):
    def f(template):
        if template[0] == 'list':
            return tuple(f(term) for term in template[1:])
        elif template[0] == 'quote':
            return template[1]
        elif template[0] == 'eval':
            return eval(template[1], globals_dict, locals_dict)
        else:
            assert template[0] == 'concat'
            result = []
            for term in template[1:]:
                result.extend(f(term))
            return tuple(result)
    return f(template)

_TEST_GLOBAL = 100

class _TestCompileTemplate(unittest.TestCase):
    def test_basic(self):
        a = 5
        b = (1, 2, 3)
        g = globals()
        l = locals()
        self.assertEqual(compile_template("(x ,a)")(g, l), ('x', 5))
        self.assertEqual(
            compile_template("(x ,_TEST_GLOBAL)")(g, l), ('x', 100))
        self.assertEqual(compile_template("(x ,@b)")(g, l), ('x', 1, 2, 3))

if __name__ == '__main__':
    unittest.main()
