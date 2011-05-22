import traceback
import sys
import re


# Helper functions

def fully_deref(value):
    while value.type.code == gdb.TYPE_CODE_PTR:
        value = value.dereference()
    return value

def get_base_types(t):
    """Given a gdb.Type, return a list of the types of the base classes."""
    if t.code != gdb.TYPE_CODE_STRUCT:
        return []
    return [field.type for field in t.fields() if field.is_base_class]

class InsnDowncaster(object):
    """An instance of this class can be called to downcast an
    instruction to its derived type.  The instruction is automatically
    dereferenced fully.

    This is a class rather than a simple function to allow caching,
    and to expose the is_allowed_starting_type() method."""
    def __init__(self):
        self.__allowed_starting_types = {"ir_instruction": True}
        self.__found_types = {}

    def is_allowed_starting_type(self, t):
        if t.code != gdb.TYPE_CODE_STRUCT:
            return False
        if t.tag not in self.__allowed_starting_types:
            if any(self.is_allowed_starting_type(base)
                   for base in get_base_types(t)):
                self.__allowed_starting_types[t.tag] = True
            else:
                self.__allowed_starting_types[t.tag] = False
        return self.__allowed_starting_types[t.tag]

    def __call__(self, value):
        value = fully_deref(value)
        if not self.is_allowed_starting_type(value.type):
            raise Exception("Not an instruction: %s" % value)
        ir_type = value['ir_type']
        ir_type_str = str(ir_type)
        ir_class_name = ir_type_str.replace('ir_type_', 'ir_')
        if ir_class_name not in self.__found_types:
            self.__found_types[ir_class_name] = gdb.lookup_type(ir_class_name)
        ir_class = self.__found_types[ir_class_name]
        return value.cast(ir_class)

class GenericDowncaster(object):
    """An instance of this class can be called to downcast an object
    with a vtable to its derived type.  The object is automatically
    dereferenced fully.

    This is a class rather than a simple function to allow caching,
    and to expose the is_allowed_starting_type() method."""
    def __init__(self, base_class):
        self.__base_class = base_class
        self.__allowed_starting_types = {base_class: True}
        self.__found_types = {}
        self.__vtable_entry_regexp = re.compile('<([a-zA-Z0-9_]+)::')

    def is_allowed_starting_type(self, t):
        if t.code != gdb.TYPE_CODE_STRUCT:
            return False
        if t.tag not in self.__allowed_starting_types:
            if any(self.is_allowed_starting_type(base)
                   for base in get_base_types(t)):
                self.__allowed_starting_types[t.tag] = True
            else:
                self.__allowed_starting_types[t.tag] = False
        return self.__allowed_starting_types[t.tag]

    def __call__(self, value):
        value = fully_deref(value)
        if not self.is_allowed_starting_type(value.type):
            raise Exception("Not derived from %s: %s" %
                            (self.__base_class, value))
        vtable_entry = str(value['_vptr.%s' % self.__base_class][0])
        print vtable_entry
        m = self.__vtable_entry_regexp.search(vtable_entry)
        derived_class_name = m.group(1)
        if derived_class_name not in self.__found_types:
            self.__found_types[derived_class_name] = gdb.lookup_type(
                derived_class_name)
        derived_class = self.__found_types[derived_class_name]
        return value.cast(derived_class)



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
        self._registered_printers = {}

    def sexp(self, *printers):
        """Create a printer that outputs the result of running its
        arguments, enclosed in parentheses."""
        def f(context):
            items = self._output_factory.open()
            for printer in printers:
                try:
                    self._output_factory.extend(items, printer(context))
                except Exception, e:
                    self._output_factory.extend(
                        items, self._output_factory.error(sys.exc_info(), e))
            return self._output_factory.close(items)
        return f

    def literal(self, s):
        """Create a printer that outputs the given literal atom."""
        return lambda context: self._output_factory.atom(s)

    def maybe(self, field, printer = None):
        """Create a printer that checks if the given field is nonzero,
        and if it is, executes its second argument on the value of
        that field.

        If there is no second argument, it simply executes
        dispatch."""
        if printer is None:
            printer = self.dispatch
        def f(context):
            value = context[field]
            if value:
                return printer(value)
            else:
                return self._output_factory.none()
        return f

    def field(self, field, printer = None):
        """Create a printer that executes its second argument on the
        value of the given field.

        If no second argument is given, it defaults to
        self.dispatch."""
        if not printer:
            printer = self.dispatch
        return lambda context: printer(context[field])

    def deref(self, printer):
        """Create a printer that executes its second argument after
        dereferencing the value."""
        return lambda context: printer(context.dereference())

    def cast(self, cast_type, printer):
        """Create a printer that casts the value to the new type and
        then runs the given printer on the result."""
        cast_type = gdb.lookup_type(cast_type)
        def f(context):
            return printer(context.cast(cast_type))
        return f

    def string(self, context):
        """Printer that uses the raw string value."""
        return self._output_factory.atom(context.string())

    def value(self, prefix=None, default=None):
        """Create a printer that converts the context to a string and
        outputs it as an atom.  If a prefix is given, it is stripped
        from the beginning of the string.  If a default is given, and
        it matches the string (after stripping the prefix), then
        nothing is output."""
        def f(context):
            s = str(context)
            if prefix and s.startswith(prefix):
                s = s[len(prefix):]
            if default and s == default:
                return self._output_factory.none()
            return self._output_factory.atom(s)
        return f

    def unique(self, context):
        """Printer that evaluates the value as a string and outputs a
        uniquified version of it."""
        return self._output_factory.unique_atom(context.string())

    def newline(self, context):
        """Printer that forces a newline to be output."""
        return self._output_factory.newline()

    def cast_adjuster(self, cast_type):
        """Create an adjuster that adjusts by casting to the given
        type."""
        cast_type = gdb.lookup_type(cast_type)
        return lambda value: value.cast(cast_type)

    def offset_adjuster(self, final_type, field_name):
        """Create an adjuster that adjusts by assuming the input value
        is a field of final_type, and locates the final_type."""
        final_type = gdb.lookup_type(final_type)
        final_ptr = final_type.pointer()
        char_ptr = gdb.lookup_type('char').pointer()
        field_info = None
        for field in final_type.fields():
            if field.name == field_name:
                field_info = field
        offset = field_info.bitpos / 8
        def f(value):
            return value.address.cast(char_ptr)[-offset].address.cast(final_ptr).dereference()
        return f

    def iterate(self, adjuster, *printers):
        """Printer that iterates over the current context (which
        should be an exec_list), adjusts the results using adjuster,
        and executes each argument on the results."""
        def f(context):
            result = []
            for p in iter_exec_list(context):
                item = adjuster(p.dereference())
                for printer in printers:
                    try:
                        result.append(printer(item))
                    except Exception, e:
                        result.append(
                            self._output_factory.error(sys.exc_info(), e))
            return self._output_factory.concat(result)
        return f

    def label(self, context):
        """Printer that creates a label of the form "$ir(999):", so
        the user may refer back to this context later."""
        addr = context.address
        if addr and self._history:
            return self._output_factory.atom(
                "$%s(%s):" % (self._history.label, self._history.add(addr)))
        else:
            return self._output_factory.none()

    def register(self, tag, printer):
        """Record that the given printer can be used to print the
        given type."""
        self._registered_printers[tag] = printer

    def fallback(self, context):
        """Printer that is used as a fallback if the type to be
        printed was not registered.  May be overridden."""
        atom = self._output_factory.atom(str(context))
        if context.type.code == gdb.TYPE_CODE_STRUCT:
            s = self._output_factory.open()
            self._output_factory.extend(s, self.label(context))
            self._output_factory.extend(s, atom)
            return self._output_factory.close(s)
        else:
            return atom

    def dispatch(self, context):
        """Dispatch to a registered printer based on type."""
        typ = context.type
        if typ.code == gdb.TYPE_CODE_PTR and \
                typ.target().code == gdb.TYPE_CODE_INT and \
                typ.target().sizeof == 1: # char *
            return self._output_factory.atom(str(context))
        context = fully_deref(context)
        tag = context.type.tag
        if tag and tag in self._registered_printers:
            return self._registered_printers[tag](context)
        return self.fallback(context)

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

    def unique_atom(self, s):
        return [s] # TODO: uniquify

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



# Specific printers for various types.

class InsnPrinter(PrinterBase):
    def __init__(self, output_factory, history = None):
        PrinterBase.__init__(self, output_factory, history)

        self.op_type_table = { 'unop': 1, 'binop': 2, 'quadop': 4 }
        self.op_table = {
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
        self.base_type_to_union_selector = {
            'GLSL_TYPE_UINT': 'u',
            'GLSL_TYPE_INT': 'i',
            'GLSL_TYPE_FLOAT': 'f',
            'GLSL_TYPE_BOOL': 'b',
            }

        self.insn_downcast = InsnDowncaster()
        print_insn = lambda v: self.dispatch(self.insn_downcast(v))
        self.register('ir_instruction', print_insn)
        self.register('ir_dereference', print_insn)
        self.register('ir_rvalue', print_insn)
        self.register('glsl_type', self.print_type)
        self.print_array_type = self.sexp(
            self.literal('array'),
            self.field('fields', self.field('array')),
            self.field('length'))
        self.register(
            'exec_list',
            self.iterate(self.cast_adjuster('ir_instruction'),
                         self.dispatch, self.newline))
        self.register('ir_variable', self.sexp(
                self.label,
                self.literal('declare'),
                self.sexp(
                    self.maybe('centroid', self.literal('centroid')),
                    self.maybe('invariant', self.literal('invariant')),
                    self.field(
                        'mode', self.cast('ir_variable_mode', self.value(
                                prefix='ir_var_', default='auto'))),
                    self.field(
                        'interpolation',
                        self.cast('ir_variable_interpolation', self.value(
                                prefix='ir_var_', default='smooth')))),
                self.field('type'),
                self.field('name', self.unique)))
        self.register('ir_function_signature', self.sexp(
                # _mesa_symbol_table_push_scope(symbols)
                self.label,
                self.literal('signature'),
                self.field('return_type'),
                self.newline,
                self.sexp(self.literal('parameters'),
                     self.field(
                        'parameters', self.iterate(
                            self.cast_adjuster('ir_variable'),
                            self.dispatch, self.newline))),
                self.newline,
                self.sexp(self.field('body'))))
        self.register('ir_function', self.sexp(
                self.label,
                self.literal('function'),
                self.field('name', self.string),
                self.newline,
                self.field(
                    'signatures',
                    self.iterate(self.cast_adjuster('ir_function_signature'),
                                 self.dispatch, self.newline))))
        self.register('ir_expression', self.sexp(
                self.label,
                self.literal('expression'),
                self.field('type'),
                self.print_expr_operator_and_operands))
        # TODO: ir_texture
        self.register('ir_swizzle', self.sexp(
                self.label,
                self.literal('swiz'),
                self.field('mask', self.print_swizzle_mask),
                self.field('val')))
        self.register('ir_dereference_variable', self.sexp(
                self.label,
                self.literal('var_ref'),
                self.field('var', self.deref(self.field('name', self.unique)))))
        # TODO: ir_dereference_array
        # TODO: ir_dereference_record
        self.register('ir_assignment', self.sexp(
                self.label,
                self.literal('assign'),
                self.maybe('condition'),
                self.sexp(self.field('write_mask', self.print_write_mask)),
                self.field('lhs'),
                self.field('rhs')))
        self.register('ir_constant', self.sexp(
                self.label,
                self.literal('constant'),
                self.field('type'),
                self.print_constant_value))
        # TODO: ir_call
        # TODO: ir_return
        # TODO: ir_discard
        self.register('ir_if', self.sexp(
                self.label,
                self.literal('if'),
                self.field('condition'),
                self.newline,
                self.sexp(self.field('then_instructions')),
                self.newline,
                self.sexp(self.field('else_instructions'))))
        self.register('ir_loop', self.sexp(
                self.label,
                self.literal('loop'),
                self.sexp(self.maybe('counter')),
                self.sexp(self.maybe('from')),
                self.sexp(self.maybe('to')),
                self.sexp(self.maybe('increment')),
                self.sexp(
                    self.newline,
                    self.field('body_instructions'))))
        self.register(
            'ir_loop_jump', self.field(
                'mode', self.value(prefix='ir_loop_jump::jump_')))

    def print_expr_operator_and_operands(self, context):
        operation = str(context['operation'])
        op_type = operation.split('_')[1]
        num_operands = self.op_type_table[op_type]
        operation = operation[(4+len(op_type)):]
        if operation in self.op_table:
            operation = self.op_table[operation]
        terms = [self._output_factory.atom(operation)]
        for i in xrange(num_operands):
            terms.append(self.dispatch(context['operands'][i]))
        return self._output_factory.concat(terms)

    def print_type(self, context):
        if context['base_type'] == gdb.parse_and_eval('GLSL_TYPE_ARRAY'):
            return self.print_array_type(context)
        else:
            return self._output_factory.atom(context['name'].string())

    def print_write_mask(self, context):
        write_mask = int(context)
        if write_mask == 0:
            return self._output_factory.none()
        mask = ""
        for i in xrange(4):
            if (write_mask & (1 << i)) != 0:
                mask += "xyzw"[i]
        return self._output_factory.atom(mask)

    def print_swizzle_mask(self, context):    
        mask = ""
        for i in xrange(int(context['num_components'])):
            mask += "xyzw"[int(context["xyzw"[i]])]
        return self._output_factory.atom(mask)

    def print_constant_value(self, context):
        ir_type = context['type']
        glsl_base_type = str(ir_type['base_type'])
        accumulator = self._output_factory.open()
        if glsl_base_type == 'GLSL_TYPE_ARRAY':
            for i in xrange(int(ir_type['length'])):
                self._output_factory.extend(
                    accumulator, self.dispatch(context['array_elements'][i]))
        elif glsl_base_type == 'GLSL_TYPE_STRUCT':
            components = list(iter_exec_list(context['components']))
            for i in xrange(int(ir_type['length'])):
                struct_elem = self._output_factory.open()
                self._output_factory.extend(
                    struct_elem, self._output_factory.atom(
                        ir_type['fields']['structure'][i]['name'].string()))
                self._output_factory.extend(
                    struct_elem, self.dispatch(components[i]))
                self._output_factory.extend(
                    accumulator, self._output_factory.close(struct_elem))
        else:
            num_components = int(ir_type['vector_elements']) \
                * int(ir_type['matrix_columns'])
            union_selector = self.base_type_to_union_selector[glsl_base_type]
            matrix = context['value'][union_selector]
            for i in xrange(num_components):
                self._output_factory.extend(
                    accumulator,
                    self._output_factory.atom(str(matrix[i])))
        return self._output_factory.close(accumulator)

class AstPrinter(PrinterBase):
    def __init__(self, output_factory, history = None):
        PrinterBase.__init__(self, output_factory, history)

        self.ast_downcast = GenericDowncaster('ast_node')
        print_ast = lambda v: self.dispatch(self.ast_downcast(v))
        self.register('ast_node', print_ast)
        self.register(
            'exec_list',
            self.iterate(self.offset_adjuster('ast_node', 'link'),
                         self.dispatch, self.newline))



# User-accessible commands and convenience functions.

class ReadHistory(gdb.Function):
    def __init__(self, history):
        gdb.Function.__init__(self, history.label)
        self._history = history

    def invoke(self, i):
        if i.type.code != gdb.TYPE_CODE_INT:
            raise Exception("Need an int")
        return self._history.get(int(i))

class DumpCmd(gdb.Command):
    def __init__(self, label, printer):
        self._history = History(label)
        self._printer = printer
        ReadHistory(self._history)
        gdb.Command.__init__(self, "dump_%s" % label,
                             gdb.COMMAND_DATA, # display in help for data cmds
                             gdb.COMPLETE_SYMBOL # autocomplete with symbols
                             )

    def invoke(self, argument, from_tty):
        value = gdb.parse_and_eval(argument)
        value = fully_deref(value)
        if value.type != gdb.lookup_type("exec_list"):
            raise Exception(
                "%s is not an exec_list (or a pointer/reference to one)" %
                (value,))
        factory = SimpleOutputFactory()
        gdb.write(
            factory.pretty_print(
                self._printer(factory, self._history).dispatch(value)))

DumpCmd('ir', InsnPrinter)
DumpCmd('ast', AstPrinter)
