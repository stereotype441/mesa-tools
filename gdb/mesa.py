import traceback
import sys
import re
import collections


# Helper functions

def TODO(*detail):
    raise Exception("TODO({0})".format(', '.join(repr(s) for s in detail)))

class label(object):
    def __init__(self, value):
        assert isinstance(value, gdb.Value)
        self.__value = value

    @property
    def value(self):
        return self.__value

class newline(object):
    pass

NEWLINE = newline()

def shorten(s, prefix, discard = None):
    """Shorten string s by removing prefix (if present).  Then, if s
    == discard, shorten to None.

    Paramter discard is optional."""
    if s.startswith(prefix):
        s = s[len(prefix):]
    if s == discard:
        return None
    return s

def fully_deref(value):
    while value.type.code == gdb.TYPE_CODE_PTR:
        value = value.dereference()
    return value



# Pretty printing: general code

class PrinterBase(object):
    """Base class for dealing with printers.

    A printer is a function that takes a gdb.Value and returns an
    output representation of it (which it forms by calling methods on
    an output factory).

    This class defines some low-level printers and combinators for
    creating them."""

    def __init__(self, output_factory, history = None):
        self._output_factory = output_factory
        self._history = history

    def label(self, context):
        """Printer that creates a label of the form "$ir(999):", so
        the user may refer back to this context later."""
        addr = context.address
        if addr and self._history:
            return self._output_factory.atom(
                "$%s(%s):" % (self._history.label, self._history.add(addr)))
        else:
            return self._output_factory.none()

    def printer(self, decoding_fn):
        """Create a printer based on a decoding function."""
        def traverse(sexp):
            while isinstance(sexp, gdb.Value):
                try:
                    sexp = decode(sexp)
                except Exception, e:
                    accumulator = self._output_factory.open()
                    self._output_factory.extend(accumulator, self.label(sexp))
                    self._output_factory.extend(
                        accumulator,
                        self._output_factory.error(sys.exc_info(), e))
                    return self._output_factory.close(accumulator)
            if isinstance(sexp, basestring):
                return self._output_factory.atom(sexp)
            if isinstance(sexp, label):
                return self.label(sexp.value)
            if sexp is None:
                return self._output_factory.none()
            if isinstance(sexp, newline):
                return self._output_factory.newline()
            if isinstance(sexp, collections.Iterable):
                accumulator = self._output_factory.open()
                for item in sexp:
                    self._output_factory.extend(accumulator, traverse(item))
                return self._output_factory.close(accumulator)
            TODO(sexp)
        return lambda context: traverse(decoding_fn(context))

def iter_exec_list(exec_list):
    p = exec_list['head'] # exec_node *
    while p.dereference()['next'] != 0:
        yield p
        p = p.dereference()['next']



# History (used to output labels)

class History(object):
    def __init__(self, label):
        self._values = []
        self._reverse = {}
        self._label = label

    @property
    def label(self):
        return self._label

    def add(self, addr):
        key = (str(addr.type), str(addr))
        if key not in self._reverse:
            self._reverse[key] = len(self._values)
            self._values.append(addr)
        return self._reverse[key]

    def get(self, index):
        return self._values[index]



# Output factory for generating a simple sexp view.
class SimpleOutputFactory(object):
    def error(self, exc_info, s):
        traceback.print_exception(*exc_info) # TODO: make optional
        return ["...%s..." % s]

    def concat(self, values):
        result = []
        for value in values:
            result.extend(value)
        return result

    def open(self):
        return []

    def extend(self, items, item):
        items.extend(item)

    def close(self, items):
        return [items]

    def atom(self, s):
        return [s]

    def newline(self):
        return [None]

    def none(self):
        return []

    def pretty_print(self, items, prefix = ''):
        results = []
        space_needed = False
        for item in items:
            if item is None:
                results.append('\n' + prefix)
                space_needed = False
            else:
                if space_needed:
                    results.append(' ')
                if isinstance(item, list):
                    results.append(
                        '(%s)' % self.pretty_print(item, prefix + ' '))
                else:
                    results.append(item)
                space_needed = True
        return ''.join(results)



# User-accessible commands and convenience functions.

class ReadHistory(gdb.Function):
    def __init__(self, history):
        gdb.Function.__init__(self, history.label)
        self._history = history

    def invoke(self, i):
        if i.type.code != gdb.TYPE_CODE_INT:
            raise Exception("Need an int")
        return self._history.get(int(i))

class ViewCmd(gdb.Command):
    def __init__(self):
        self._history = History('v')
        ReadHistory(self._history)
        gdb.Command.__init__(self, "view",
                             gdb.COMMAND_DATA, # display in help for data cmds
                             gdb.COMPLETE_SYMBOL # autocomplete with symbols
                             )

    def invoke(self, argument, from_tty):
        value = gdb.parse_and_eval(argument)
        value = fully_deref(value)
        factory = SimpleOutputFactory()
        s = factory.pretty_print(
                PrinterBase(factory, self._history).printer(decode)(value))
        if not s.endswith('\n'):
            s += '\n'
        gdb.write(s)

ViewCmd()


def decode(x):
    typ = x.type
    if typ.code == gdb.TYPE_CODE_PTR and \
            typ.target().code == gdb.TYPE_CODE_INT and \
            typ.target().sizeof == 1: # char *
        return str(x)
    x = generic_downcast(fully_deref(x))
    tag = x.type.tag
    if tag:
        decoder_name = 'decode_{0}'.format(tag)
        if decoder_name in globals():
            return globals()[decoder_name](x)
    if x.type.code == gdb.TYPE_CODE_STRUCT:
        return (label(x), str(x))
    return str(x)

def decode_glsl_type(x):
    if str(x['base_type']) == 'GLSL_TYPE_ARRAY':
        return ('array', x['fields']['array'], x['length'])
    else:
        return x['name'].string()

def decode_ir_variable(x):
    # TODO: uniquify name
    return (
        label(x), 'declare', (
            ('centroid' if x['centroid'] else None),
            ('invariant' if x['invariant'] else None),
            shorten(
                str(x['mode'].cast(gdb.lookup_type('ir_variable_mode'))),
                'ir_var_', 'auto'),
            shorten(
                str(x['interpolation'].cast(
                        gdb.lookup_type('ir_variable_interpolation'))),
                'ir_var_', 'smooth')),
        x['type'], x['name'])

def decode_ir_function_signature(x):
    param_list = ['parameters', NEWLINE]
    for param in iter_exec_list(x['parameters']):
        param_list.extend(
            [x.dereference().cast(gdb.lookup_type('ir_variable')), NEWLINE])
    return (
        label(x), 'signature', x['return_type'], NEWLINE,
        param_list, NEWLINE,
        x['body'])

def decode_ir_assignment(x):
    write_mask = int(x['write_mask'])
    write_mask_str = ""
    for i in xrange(4):
        if (write_mask & (1 << i)) != 0:
            write_mask_str += "xyzw"[i]
    return (
        label(x), 'assign', x['condition'] or None, (write_mask_str or None,),
        x['lhs'], x['rhs'])

def decode_ir_dereference_variable(x):
    # TODO: uniquify name
    return (label(x), 'var_ref', x['var']['name'].string())

OP_TYPE_TABLE = { 'unop': 1, 'binop': 2, 'quadop': 4 }
OP_TABLE = {
    'bit_not': "~",
    'logic_not': "!",
    'add': "+",
    'sub': "-",
    'mul': "*",
    'div': "/",
    'mod': "%",
    'less': "<",
    'greater': ">",
    'lequal': "<=",
    'gequal': ">=",
    'equal': "==",
    'nequal': "!=",
    'lshift': "<<",
    'rshift': ">>",
    'bit_and': "&",
    'bit_xor': "^",
    'bit_or': "|",
    'logic_and': "&&",
    'logic_xor': "^^",
    'logic_or': "||",
    }

def decode_ir_expression(x):
    operation = str(x['operation'])
    op_type = operation.split('_')[1]
    num_operands = OP_TYPE_TABLE[op_type]
    operation = operation[(4+len(op_type)):]
    if operation in OP_TABLE:
        operation = OP_TABLE[operation]
    return [label(x), 'expression', x['type'], operation] + \
        [x['operands'][i] for i in xrange(num_operands)]

def decode_ir_swizzle(x):
    swizzle_mask = ""
    for i in xrange(int(x['mask']['num_components'])):
        swizzle_mask += "xyzw"[int(x['mask']["xyzw"[i]])]
    return (label(x), 'swiz', swizzle_mask, x['val'])

BASE_TYPE_TO_UNION_SELECTOR = {
    'GLSL_TYPE_UINT': 'u',
    'GLSL_TYPE_INT': 'i',
    'GLSL_TYPE_FLOAT': 'f',
    'GLSL_TYPE_BOOL': 'b',
    }

def decode_ir_constant(x):
    ir_type = x['type']
    glsl_base_type = str(ir_type['base_type'])
    if glsl_base_type == 'GLSL_TYPE_ARRAY':
        TODO("test me")
        constant_value = tuple(
            x['array_elements'][i] for i in xrange(int(ir_type['length'])))
    elif glsl_base_type == 'GLSL_TYPE_STRUCT':
        TODO("test me")
        components = list(iter_exec_list(x['components']))
        constant_value = tuple(
            (ir_type['fields']['structure'][i]['name'].string(), components[i])
            for i in xrange(int(ir_type['length'])))
    else:
        num_components = int(ir_type['vector_elements']) \
            * int(ir_type['matrix_columns'])
        union_selector = BASE_TYPE_TO_UNION_SELECTOR[glsl_base_type]
        matrix = x['value'][union_selector]
        constant_value = tuple(matrix[i] for i in xrange(num_components))
    return (label(x), 'constant', x['type'], constant_value)

def decode_ir_loop(x):
    return (
        label(x), 'loop', (x['counter'] or None,), (x['from'] or None,),
        (x['to'] or None,), (x['increment'] or None,), NEWLINE,
        x['body_instructions'])

def decode_ir_if(x):
    return (
        label(x), 'if', x['condition'], NEWLINE,
        x['then_instructions'], NEWLINE,
        x['else_instructions'])

def decode_ir_loop_jump(x):
    return shorten(str(x['mode']), 'ir_loop_jump::jump_')

def decode_ir_function(x):
    return (
        label(x), 'function', x['name'].string(), NEWLINE,
        [signature.dereference().cast(gdb.lookup_type('ir_function_signature'))
         for signature in iter_exec_list(x['signatures'])])

def decode_exec_list(x):
    for item in iter_exec_list(x):
        yield downcast_exec_node(item)
        yield NEWLINE

def compute_offset(master_type, field):
    """Compute the offest (as an integer number of bytes) of field
    within master_type."""
    for f in master_type.fields():
        if f.name == field:
            assert f.bitpos % 8 == 0
            return f.bitpos / 8
    raise Exception(
        'Field {0} not found in type {1}'.format(field, master_type))

def field_de_accessor(master_type, field_name):
    """Return a function that undoes the effects of accesing the
    field_name'th element of master_type."""
    def f(x):
        char_ptr = gdb.lookup_type('char').pointer()
        master_ptr_type = gdb.lookup_type(master_type).pointer()
        p_master_type_null = gdb.Value(0).cast(master_ptr_type)
        offset = long(p_master_type_null.dereference()[field_name].address)
        return (x.address.cast(char_ptr) - offset).cast(
            master_ptr_type).dereference()
    return f

def iter_type_and_bases(typ):
    # Walk the class hierarchy returning typ and everything it
    # inherits from
    types_to_search = [typ]
    while types_to_search:
        typ = types_to_search.pop()
        yield typ
        for f in typ.fields():
            if f.is_base_class:
                types_to_search.append(f.type)

def find_vptr(value):
    for typ in iter_type_and_bases(value.type):
        try:
            type_name = str(typ)
            return value['_vptr.{0}'.format(type_name)]
        except:
            pass
    return None

def generic_downcast(value):
    vptr = find_vptr(value)
    if vptr is None:
        return value
    vtable_entry = str(vptr[-1])
    derived_class_name = TYPEINFO_REGEXP.search(vtable_entry).group(1)
    derived_class = gdb.lookup_type(derived_class_name)
    return value.cast(derived_class)

TYPEINFO_REGEXP = re.compile('<typeinfo for (.*)>')
AST_NODE_LINK_DE_ACCESSOR = None
EXEC_NODE_DOWNCASTERS = (
    lambda x: x.cast(gdb.lookup_type('ir_instruction')),
    field_de_accessor('ast_node', 'link'),
    )

def downcast_exec_node(x):
    x = fully_deref(x)
    for downcaster in EXEC_NODE_DOWNCASTERS:
        try:
            return generic_downcast(downcaster(x))
        except:
            # If anything went wrong, then presumably the value we
            # were looking at wasn't of the expected type.  Go on and
            # try the next one.
            pass
    raise Exception("Could not downcast exec_node at {0}".format(x.address))

def decode_ast_declarator_list(x):
    return (
        label(x), 'declarator_list', x['type'] or None,
        'invariant' if x['invariant'] else None, NEWLINE, x['declarations'])

def decode_ast_declaration(x):
    return (
        label(x), 'declaration', x['identifier'].string(),
        '[{0}]'.format(x['array_size']) if x['array_size'] else None,
        x['initializer'] or None)

def decode_ast_function_definition(x):
    return (
        label(x), 'function_definition', x['prototype'], NEWLINE, x['body'])

def decode_ast_function(x):
    return (
        label(x), 'function', x['return_type'], x['identifier'].string(),
        x['parameters'])

def decode_ast_compound_statement(x):
    return (label(x), 'compound_statement', NEWLINE, x['statements'])

def decode_ast_expression_statement(x):
    return (
        label(x), 'expression_statement',
        x['expression'] if x['expression'] else None)

UNARY_OPS = ('plus', 'neg', 'bit_not', 'logic_not', 'pre_inc', 'pre_dec',
             'post_inc', 'post_dec')

CONSTANT_TYPES = ('int_constant', 'uint_constant',
                  'float_constant', 'bool_constant')

def decode_ast_expression(x):
    yield label(x)
    op = shorten(str(x['oper']), 'ast_')
    yield op
    if op == 'field_selection':
        TODO("test me")
        yield x['primary_expression']['identifier'].string()
    elif op in UNARY_OPS:
        TODO("test me")
        yield x['subexpressions'][0]
    elif op == 'conditional':
        TODO("test me")
        yield x['subexpressions'][0]
        yield x['subexpressions'][1]
        yield x['subexpressions'][2]
    elif op == 'function_call':
        TODO("test me")
        yield x['subexpressions'][0]
        yield x['expressions'][0]
    elif op == 'identifier':
        yield x['primary_expression']['identifier'].string()
    elif op in CONSTANT_TYPES:
        TODO("test me")
        yield x['primary_expression'][op]
    elif op == 'sequence':
        TODO("test me")
        yield x['expressions']
    else:
        yield x['subexpressions'][0]
        yield x['subexpressions'][1]

def decode_ast_type_qualifier(x):
    q = x['flags']['q']
    def do_words(*words):
        for word in words:
            if q[word]: yield word
    if q['constant']: yield 'const'
    do_words('invariant', 'attribute', 'varying')
    if q['in'] and q['out']:
        yield 'inout'
    else:
        do_words('in', 'out')
    do_words('centroid', 'uniform', 'smooth', 'flat', 'noperspective')

def decode_ast_type_specifier(x):
    if str(x['type_specifier']) == 'ast_struct':
        TODO("test me")
        return x['structure']
    else:
        return x['type_name'].string()

def decode_ast_fully_specified_type(x):
    return (label(x), 'type', x['qualifier'], x['specifier'])
