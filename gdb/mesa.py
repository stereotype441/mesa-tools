import traceback
import sys
import re
import collections


# --------------------------------------------------
# User-accessible commands and convenience functions.
# --------------------------------------------------

class ReadHistory(gdb.Function):
    def __init__(self):
        gdb.Function.__init__(self, 'v')

    def invoke(self, i):
        if i.type.code != gdb.TYPE_CODE_INT:
            raise Exception("Need an int")
        return VIEW_HISTORY.get(int(i))

ReadHistory()



class ViewCmd(gdb.Command):
    def __init__(self):
        gdb.Command.__init__(self, "view",
                             gdb.COMMAND_DATA, # display in help for data cmds
                             gdb.COMPLETE_SYMBOL # autocomplete with symbols
                             )

    def invoke(self, argument, from_tty):
        pretty_print(gdb.parse_and_eval(argument))

ViewCmd()



class StringPrettyPrinter(object):
    """GDB-compliant pretty-printer object that simply returns the
    string it was initialized with.
    """
    def __init__(self, s):
        self.__s = s

    def to_string(self):
        return self.__s

def pretty_printer_lookup_function(value):
    try:
        if value.type.code != gdb.TYPE_CODE_PTR:
            return None
        deref_value = value.dereference()
        if deref_value.type.code != gdb.TYPE_CODE_STRUCT:
            return None
        if long(value) == 0:
            return None
        deref_value = generic_downcast(deref_value)
        tag = deref_value.type.tag
        if tag:
            decoder_name = 'decode_{0}'.format(tag)
            if decoder_name in globals():
                return StringPrettyPrinter(
                    '({0}) 0x{1:x} {2}'.format(
                        value.type, long(value),
                        pretty_print_short(deref_value)))
    except:
        pass
    return None

if pretty_printer_lookup_function not in gdb.pretty_printers:
    gdb.pretty_printers.append(pretty_printer_lookup_function)



# ------------------------
# Generic helper functions
# ------------------------

def TODO(*detail):
    raise Exception("TODO({0})".format(', '.join(repr(s) for s in detail)))

class History(object):
    def __init__(self):
        self._values = []
        self._reverse = {}

    def add(self, addr):
        key = (str(addr.type), long(addr))
        if key not in self._reverse:
            self._reverse[key] = len(self._values)
            self._values.append(addr)
        return self._reverse[key]

    def get(self, index):
        return self._values[index]

VIEW_HISTORY = History()

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

def eval_for_pretty_print(sexp, exceptions = None):
    while isinstance(sexp, gdb.Value):
        try:
            sexp = decode(sexp)
        except Exception, e:
            if exceptions is not None:
                exceptions.append(sys.exc_info())
            error_string = '...{0}...'.format(e)
            if sexp.address != None:
                sexp = (label(sexp), error_string)
            else:
                sexp = error_string
    return sexp

def format_label(value):
    if value.address is None:
        return '...No address...'
    else:
        return '$v({0})'.format(VIEW_HISTORY.add(value.address))

def pretty_print(sexp, writer = gdb.write):
    exceptions = []
    def traverse(sexp, prefix):
        sexp = eval_for_pretty_print(sexp, exceptions)
        if isinstance(sexp, basestring):
            writer(sexp)
        elif isinstance(sexp, label):
            writer('{0}:'.format(format_label(sexp.value)))
        elif isinstance(sexp, collections.Iterable):
            prefix = prefix + ' '
            writer('(')
            try:
                space_needed = False
                for item in sexp:
                    if item is None:
                        continue
                    elif isinstance(item, newline):
                        writer('\n' + prefix)
                        space_needed = False
                    else:
                        if space_needed: writer(' ')
                        traverse(item, prefix)
                        space_needed = True
            except Exception, e:
                exceptions.append(sys.exc_info())
                if space_needed: writer(' ')
                writer('...{0}...'.format(e))
            finally:
                gdb.write(')')
    traverse(sexp, '')
    writer('\n')
    if exceptions:
        writer('First exception:\n')
        for line in traceback.format_exception(*exceptions[0]):
            writer(line)

def pretty_print_short(sexp):
    sexp = eval_for_pretty_print(sexp)
    if isinstance(sexp, basestring):
        return sexp
    elif isinstance(sexp, collections.Iterable):
        elements = []
        try:
            for item in sexp:
                if item is None:
                    continue
                elif isinstance(item, newline):
                    continue
                elif isinstance(item, label):
                    continue
                elif isinstance(item, gdb.Value):
                    x = fully_deref(item)
                    if is_char_ptr(item.type) or \
                            x.type.code != gdb.TYPE_CODE_STRUCT:
                        elements.append(str(item))
                    else:
                        elements.append(format_label(x))
                else:
                    elements.append(pretty_print_short(item))
        except Exception, e:
            elements.append('...{0}...'.format(e))
        return '({0})'.format(' '.join(elements))
    else:
        TODO(sexp)

def is_char_ptr(typ):
    return typ.code == gdb.TYPE_CODE_PTR and \
        typ.target().code == gdb.TYPE_CODE_INT and \
        typ.target().sizeof == 1

def decode(x):
    if is_char_ptr(x.type):
        return str(x)
    x = generic_downcast(fully_deref(x))
    tag = x.type.tag
    if tag:
        decoder_name = 'decode_{0}'.format(tag)
        if decoder_name in globals():
            return globals()[decoder_name](x)
    if x.type.code == gdb.TYPE_CODE_STRUCT:
        return (label(x), '{0}{1}'.format(x.type, x))
    return str(x)

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



# ----------------------
# MESA-specific decoders
# ----------------------
#
# Note: any function whose name is of the form decode_<typename> will
# automatically be called to decode values of that type.

def iter_exec_list(exec_list):
    p = exec_list['head'] # exec_node *
    while p.dereference()['next'] != 0:
        yield p
        p = p.dereference()['next']

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
    def decode_param_list(params):
        yield 'parameters'
        yield NEWLINE
        for param in iter_exec_list(params):
            yield param
            yield NEWLINE
    yield label(x)
    yield 'signature'
    yield x['return_type']
    yield NEWLINE
    yield decode_param_list(x['parameters'])
    yield NEWLINE
    yield x['body']

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

def decode_ir_call(x):
    yield label(x)
    yield 'call'
    yield x['callee']['_function']['name'].string()
    yield x['actual_parameters']

def decode_ir_dereference_array(x):
    yield label(x)
    yield 'array_ref'
    yield x['array']
    yield x['array_index']

def decode_ir_return(x):
    yield label(x)
    yield 'return'
    if x['value']:
        yield x['value']

def decode_exec_list(x):
    for item in iter_exec_list(x):
        yield downcast_exec_node(item)
        yield NEWLINE

def decode_exec_node(x):
    return downcast_exec_node(x)

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
    raise Exception(
        "Could not downcast exec_node at 0x{0:x}".format(long(x.address)))

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
        yield x['subexpressions'][0]
    elif op == 'conditional':
        yield x['subexpressions'][0]
        yield x['subexpressions'][1]
        yield x['subexpressions'][2]
    elif op == 'function_call':
        yield x['subexpressions'][0]
        yield x['expressions']
    elif op == 'identifier':
        yield x['primary_expression']['identifier'].string()
    elif op in CONSTANT_TYPES:
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
        return x['structure']
    else:
        return x['type_name'].string()

def decode_ast_fully_specified_type(x):
    return (label(x), 'type', x['qualifier'], x['specifier'])

def decode_s_list(x):
    yield label(x)
    for item in iter_exec_list(x['subexpressions']):
        yield downcast_exec_node(item)

def decode_s_symbol(x):
    return x['str'].string()

def decode_s_float(x):
    return str(x['val'])

def decode_ast_struct_specifier(x):
    yield label(x)
    yield 'struct'
    yield x['name'].string()
    yield x['declarations']

def decode_ir_texture(x):
    yield label(x)
    op_str = str(x['op'])
    yield shorten(op_str, 'ir_')
    yield x['type']
    yield x['sampler']
    yield x['coordinate']
    yield x['offset'] or '0'
    if op_str != 'ir_txf':
        yield x['projector'] or '1'
        yield x['shadow_comparitor'] or '()'
    if op_str == 'ir_tex':
        pass
    elif op_str == 'ir_txb':
        yield x['lod_info']['bias']
    elif op_str in ('ir_txl', 'ir_txf'):
        yield x['lod_info']['lod']
    elif op_str == 'ir_txd':
        yield [x['lod_info']['grad']['dPdx'], x['lod_info']['grad']['dPdy']]

def decode_ir_dereference_record(x):
    yield label(x)
    yield 'record_ref'
    yield x['record']
    yield x['field'].string()

def decode_ast_function_expression(x):
    # ast_function_expression derives from ast_expression, and uses
    # its print routine.
    return decode_ast_expression(x)

def mesa_num_inst_src_regs(opcode):
    return int(gdb.parse_and_eval('InstInfo')[opcode]['NumSrcRegs'])

def GET_SWZ(swz, idx):
    # Based on GET_SWZ in prog_instruction.h
    return (int(swz) >> int(idx)*3) & 7

def mesa_swizzle_string(swizzle, negateMask, extended):
    # Based on _mesa_swizzle_string() in prog_print.c
    negateMask = int(negateMask)
    swizzle = int(swizzle)
    swz = 'xyzw01!?'
    SWIZZLE_NOOP = 03210
    if not extended and swizzle == SWIZZLE_NOOP and negateMask == 0:
        return ''
    parts = [
        '{0}{1}'.format(
            '-' if negateMask & (1 << idx) else '', swz[GET_SWZ(swizzle, idx)])
        for idx, name in enumerate('xyzw')]
    if extended:
        return ','.join(parts)
    else:
        return '.' + ''.join(parts)

def decode_prog_src_register(srcReg):
    # Based on fprint_src_reg() in prog_print.c
    abs_str = '|' if srcReg['Abs'] else ''
    return '{0}{1}{2}{0}'.format(
        abs_str,
        reg_string(
            srcReg['File'].cast(gdb.lookup_type('gl_register_file')),
            srcReg['Index'], srcReg['RelAddr'], srcReg['HasIndex2'],
            srcReg['RelAddr2'], srcReg['Index2']),
        mesa_swizzle_string(srcReg['Swizzle'], srcReg['Negate'], False))

def fprint_comment(inst):
    # Based on fprint_comment() in prog_print.c
    if inst['Comment']:
        return ';  # {0}'.format(inst['Comment'].string())
    else:
        return ';'

def mesa_fprint_alu_instruction(inst, opcode_string, numRegs):
    # Based on _mesa_fprint_alu_instruction() in prog_print.c
    result = opcode_string
    if inst['CondUpdate']:
        result += '.C'
    if inst['SaturateMode']:
        result += '_SAT'
    result += ' '
    if inst['DstReg']['File'] != gdb.parse_and_eval('PROGRAM_UNDEFINED'):
        result += decode_prog_dst_register(inst['DstReg'])
    else:
        result += ' ???'
    if numRegs > 0:
        result += ', '
    result += ', '.join(
        decode_prog_src_register(inst['SrcReg'][j]) for j in xrange(numRegs))
    result += fprint_comment(inst)
    return result

COND_TR = 8

def decode_gl_register_file(f):
    # Based on _mesa_register_file_name() in prog_print.c
    table = {
        'PROGRAM_TEMPORARY': 'TEMP',
        'PROGRAM_LOCAL_PARAM': 'LOCAL',
        'PROGRAM_ENV_PARAM': 'ENV',
        'PROGRAM_STATE_VAR': 'STATE',
        'PROGRAM_INPUT': 'INPUT',
        'PROGRAM_OUTPUT': 'OUTPUT',
        'PROGRAM_NAMED_PARAM': 'NAMED',
        'PROGRAM_CONSTANT': 'CONST',
        'PROGRAM_UNIFORM': 'UNIFORM',
        'PROGRAM_VARYING': 'VARYING',
        'PROGRAM_WRITE_ONLY': 'WRITE_ONLY',
        'PROGRAM_ADDRESS': 'ADDR',
        'PROGRAM_SAMPLER': 'SAMPLER',
        'PROGRAM_SYSTEM_VALUE': 'SYSVAL',
        'PROGRAM_UNDEFINED': 'UNDEFINED',
        }
    f_str = str(f)
    if f_str in table:
        return table[f_str]
    else:
        return 'FILE{0}'.format(int(f))

def reg_string(f, index, relAddr, hasIndex2, relAddr2, index2):
    # Based on reg_string() in prog_print.c
    addr = 'ADDR=' if relAddr else ''
    result = '{0}[{1}{2}]'.format(decode_gl_register_file(f), addr, index)
    if hasIndex2:
        addr2 = 'ADDR=' if relAddr2 else ''
        result += '[{0}{1}]'.format(addr2, index2)
    return result

def mesa_writemask_string(writeMask):
    # Based on _mesa_writemask_string() in prog_print.c
    writeMask = int(writeMask)
    if writeMask == 15:
        return ''
    else:
        return '.{0}'.format(
            ''.join(
                s for s, mask in (('x', 1), ('y', 2), ('z', 4), ('w', 8))
                if writeMask & mask))

def decode_prog_dst_register(dstReg):
    # Based on fprint_dst_reg() in prog_print.c
    result = '{0}{1}'.format(
        reg_string(
            dstReg['File'].cast(gdb.lookup_type('gl_register_file')),
            dstReg['Index'], dstReg['RelAddr'], False, False, 0),
        mesa_writemask_string(dstReg['WriteMask']))
    if dstReg['CondMask'] != COND_TR:
        result += ' ({0}.{1})'.format(
            mesa_condnode_string(dstReg['CondMask']),
            mesa_swizzle_string(dstReg['CondSwizzle'], False, False))
    return result

def decode_prog_instruction(inst):
    # Based on _mesa_fprint_instruction_opt() in prog_print.c
    opcode = inst['Opcode']
    opcode_str = shorten(str(opcode), 'OPCODE_')
    if opcode_str == 'OPCODE_PRINT':
        TODO()
    elif opcode_str == 'OPCODE_SWZ':
        TODO()
    elif any(opcode_str == 'OPCODE_' + x
             for x in ('TEX', 'TXP', 'TXL', 'TXB', 'TXD')):
        TODO()
    elif opcode_str == 'OPCODE_KIL':
        TODO()
    elif opcode_str == 'OPCODE_KIL_NV':
        TODO()
    elif opcode_str == 'OPCODE_ARL':
        TODO()
    elif opcode_str == 'OPCODE_BRA':
        TODO()
    elif opcode_str == 'OPCODE_IF':
        TODO()
    elif opcode_str == 'OPCODE_ELSE':
        TODO()
    elif opcode_str == 'OPCODE_ENDIF':
        TODO()
    elif opcode_str == 'OPCODE_BGNLOOP':
        TODO()
    elif opcode_str == 'OPCODE_ENDLOOP':
        TODO()
    elif opcode_str == 'OPCODE_BRK':
        TODO()
    elif opcode_str == 'OPCODE_CONT':
        TODO()
    elif opcode_str == 'OPCODE_BGNSUB':
        TODO()
    elif opcode_str == 'OPCODE_ENDSUB':
        TODO()
    elif opcode_str == 'OPCODE_CAL':
        TODO()
    elif opcode_str == 'OPCODE_RET':
        TODO()
    elif opcode_str == 'OPCODE_END':
        TODO()
    elif opcode_str == 'OPCODE_NOP':
        TODO()
    elif opcode_str == 'OPCODE_EMIT_VERTEX':
        TODO()
    elif opcode_str == 'OPCODE_END_PRIMITIVE':
        TODO()
    elif opcode < gdb.parse_and_eval('MAX_OPCODE'):
        return mesa_fprint_alu_instruction(
            inst, opcode_str, mesa_num_inst_src_regs(opcode))
        TODO()
    else:
        TODO()
