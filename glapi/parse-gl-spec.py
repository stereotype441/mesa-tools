import json
import os
import re


PROCEDURE_NAME_REGEXP = re.compile('[a-zA-Z_]([a-zA-Z0-9_]|{[a-z0-9, ]+})*')
EXPANDO_REGEXP = re.compile('{[a-z0-9, ]+}')


EXPANDO_EXPRESSIONS = {
    '{i,f,d}': 'ifd',
    '{fd}': 'fd',
    '{ubusui}': ('ub', 'us', 'ui'),
    '{1234}': '1234',
    '{bsifd}': 'bsifd',
    '{if}': 'if',
    '{d,dv,f,fv}': ('d', 'dv', 'f', 'fv'),
    '{dv,fv}': ('dv', 'fv'),
    '{bdfis}': 'bdfis',
    '{234}': '234',
    '{34}': '34',
    '{12}': '12',
    '{sifd}': 'sifd',
    '{bsifd ubusui}': ('b', 's', 'i', 'f', 'd', 'ub', 'us', 'ui'),
    }


RECOGNIZED_SECTIONS = ('', 'Name', 'Name Strings', 'Version', 'Number', 'Dependencies', 'Overview',
                       'New Procedures and Functions', 'New Tokens', 'Errors', 'New State',
                       'New Implementation Dependent State', 'Issues',
                       'XXX - Not complete yet!!!', 'Contact', 'IP Status',
                       'Status', 'Revision History', 'Notice', 'New Implementation State', 'Contributors',
                       'Sample Code', 'Implementation Notes', 'Intended Usage', 'New Types', 'Appendix',
                       'New Implementation Dependent state', 'Usage Example', 'NV3x Implementation Details',
                       'NV10 Implementation Details', 'NV20 Implementation Details', 'Support', 'Examples',
                       'New Procedures, Functions and Structures:', 'Usage examples', 'Revision history',
                       'NVIDIA Implementation Details', 'ATI Implementation Details', 'Usage Examples',
                       'Revision History:', 'New Implementation Dependent State:', 'Name String', 'Glossary',
                       'Version History', 'Issues:', 'Implementation Details', 'Example Usage',
                       'Addition to the GL specification', 'Sample Usage', 'Conformance Test', 'Conformance Testing',
                       'Contacts', 'Glossary of Helpful Terms', 'Issues and Notes', 'GLX Errors', 'Conformance Tests',
                       'Implementation Note', '2.1 Specification Updates',
                       'OpenGL Shading Language Spec v1.20.8 Updates', 'Backwards Compatibility',
                       'Change end of first sentence in section, p. 42', '2.11.7 Uniform Variables',
                       'New Procedure and Functions', 'Deprecated Functionality', 'New Functions and Procedures',
                       'XXX - Almost complete; needs GLX protocol.',
                       'An example of using the calls to test the extension:', 'XXX - Not complete.',
                       'XXX - not complete yet',
                       "XXX - Dead -- couldn't convince the ARB.  Use fragment_lighting & XXX   separate_specular_color instead. XXX - Not complete yet!!!",
                       'XXX - Not complete yet!!!  But pretty close.', 'XXX - incomplete', 'XXX - not complete yet!',
                       'Reasoning', 'PRELIMINARY - NOT COMPLETE --------------------------',
                       'New Procedures And Functions', 'Notes',
                       'In 4.3.3 (Copying Pixels), add to the section describing BlitFramebuffer that was added by EXT_framebuffer_blit.',
                       'Patent Note', 'OpenGL ES interactions', 'Compatibility', 'Usage ExampleS', 'Usage Examples:',
                       'GeForce Implementation Details', 'Sample Code (from framebuffer_blit)',
                       'Usage Examples (from packed_depth_stencil)', 'Example Use Cases',
                       'Addendum: Using this extension.', 'Issue', 'Proposal:', 'NVIDIA Implementation Note')


INDENT_FIXUPS = {
    'NV_texture_shader2': (
        ('     Table 3.A:', 'start indent'),
        ('     3.8.13.1.22  3D Projective Texturing', 'stop indent'),
        ('New State', 'start indent after'),
        ('New Implementation State', 'stop indent')
        ),
    'NV_occlusion_query': (
        ('(table 6.18, p. 226)', 'indent'),
        ('(table 6.29, p. 237) Add the following entry:', 'indent')
        ),
    'NV_copy_image': (
        ('************************************************************************', 'ignore'),
        ('Issues', 'start indent after'),
        ('Revision History', 'stop indent')
        ),
    'NV_vertex_program2': (
        ('Vertex', 'start indent'),
        ('parameters.', 'stop indent after'),
        ('New State', 'start indent after'),
        ('Revision History', 'stop indent')
        ),
    'NV_fragment_program': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'outdent'),
        ('Revision History', 'stop indent')
        ),
    'NV_texture_shader3': (
        ('     Add two more rows to table 3.16:', 'start indent after'),
        ('     Update this paragraph inserted by NV_texture_shader before the last', 'stop indent'),
        ('     Table 3.A:', 'start indent after'),
        ('     3.8.13.1.14  Dot Product', 'stop indent'),
        ('New State', 'start indent after'),
        ('New Implementation State', 'stop indent'),
        ),
    'NV_vertex_array_range': (
        ('Vertex', 'start indent'),
        ('        For the validity check to be TRUE, the following must all be', 'stop indent'),
        ),
    'NV_texture_expand_normal': (
        ('(add to table 6.15, p. 230)', 'start indent'),
        ('Revision History', 'outdent'),
        ),
    'NV_point_sprite': (
        ('(table 6.12, p. 220)', 'start indent'),
        ('NVIDIA Implementation Details', 'stop indent'),
        ),
    'NV_blend_square': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'NV_evaluators': (
        ('Vertex', 'start indent'),
        ('parameters.', 'stop indent after'),
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'outdent'),
        ('Revision History', 'stop indent'),
        ),
    'NV_register_combiners': (
        (' --  (NEW table 6.29, after p217)', 'start indent after'),
        ('New Implementation Dependent State', 'outdent'),
        ('NVIDIA Implementation Details', 'stop indent'),
        ),
    'NV_register_combiners2': (
        ('New State', 'start indent after'),
        ('New Implementation State', 'stop indent'),
        ),
    'NV_texture_shader': (
        ('     Add a new row to table 3.8:', 'start indent after'),
        ('     Replace the fifth paragraph in the subsection titled "Unpacking"', 'stop indent'),
        ('     these column entries blank.  Add the following rows to the table:', 'start indent after'),
        ('     Add to the caption for table 3.16:', 'stop indent'),
        ('     Also amend tables 3.18 and 3.19 based on the following updated columns:', 'start indent after'),
        ('     Also augment table 3.18 or 3.19 with the following column:', 'stop indent'),
        ('     describes each possible texture shader operation in detail.', 'start indent after'),
        ('     3.8.13.1.1  None', 'stop indent'),
        ('New State', 'start indent after'),
        ('New Implementation State', 'stop indent'),
        ),
    'NV_video_capture': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'outdent'),
        ('Usage Examples:', 'stop indent'),
        ),
    'NV_texgen_reflection': (
        ('New State', 'start indent after'),
        ('New Implementation State', 'stop indent'),
        ),
    'NV_fence': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'NV_vertex_program': (
        ('    Table X.1 and further discussed below.', 'start indent after'),
        ('    Table X.1:  Vertex Result Registers.', 'stop indent'),
        ('Vertex', 'start indent'),
        ('parameters.', 'stop indent after'),
        ('    number and what the mnemonic abbreviates.', 'start indent after'),
        ('mnemonics, and meanings.', 'stop indent after'),
        ('    respective input and output parameters are summarized in Table X.4.', 'start indent after'),
        ('a scalar output replicated across a 4-component vector.', 'stop indent after'),
        ('New State', 'start indent after'),
        ('Revision History', 'stop indent'),
        ),
    'NV_texture_rectangle': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'outdent'),
        ('Revision History', 'stop indent'),
        ),
    'NV_framebuffer_multisample_coverage': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'NV_fog_distance': (
        ('New State', 'start indent after'),
        ('New Implementation State', 'stop indent'),
        ),
    'NV_vertex_program1_1': (
        ('    respective input and output parameters are summarized in Table X.4."', 'start indent after'),
        ('a scalar output replicated across a 4-component vector.', 'stop indent after'),
        ),
    'NV_vdpau_interop': (
        ('New State', 'start indent after'),
        ('New Implementation State', 'stop indent'),
        ),
    'NV_light_max_exponent': (
        ('New Implementation Dependent State', 'start indent after'),
        ('NVIDIA Implementation Details', 'stop indent'),
        ),
    'NV_depth_clamp': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'NV_multisample_filter_hint': (
        ('New State', 'start indent after'),
        ('Revision History', 'stop indent'),
        ),
    'NV_texgen_emboss': (
        ('--  Section 2.10.4 "Generating Texture Coordinates"', 'indent'),
        ('New State', 'start indent after'),
        ('New Implementation State', 'stop indent'),
        ),
    'APPLE_row_bytes': (
        ('Version History', 'start indent after'),
        ),
    'APPLE_float_pixels': (
        ('New State', 'start indent after'),
        ('Revision History', 'stop indent'),
        ),
    'APPLE_aux_depth_stencil': (
        ('New Implementation Dependent State', 'start indent after'),
        ),
    'APPLE_vertex_program_evaluators': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'APPLE_object_purgeable': (
        ('state:', 'indent'),
        ),
    'INTEL_texture_scissor': (
        ('Overview', 'start indent after'),
        ('New Procedures and Functions', 'outdent'),
        ('New Tokens', 'outdent'),
        ('Additions to Chapter 2 of the GL 1.1 Specification', 'outdent'),
        ('Additions to Chapter 3 of the GL 1.1 Specification (Rasterization)', 'outdent'),
        ('Additions to Chapter 4 of the GL 1.1 Specification (Per Fragment Operations', 'outdent'),
        ('and the Framebuffer)', 'outdent'),
        ('Additions to Chapter 5 of the GL 1.1 Specification (Special Functions)', 'outdent'),
        ('Additions to Chapter 6 of the GL 1.1 Specification (State and State Requests)', 'outdent'),
        ('Additions to GLX Specification', 'outdent'),
        ('GLX Protocol', 'outdent'),
        ('Dependencies on EXT_texture3D', 'outdent'),
        ('Errors', 'outdent'),
        ('New State', 'outdent'),
        ('New Implementation Dependent State', 'outdent'),
        ),
    'INTEL_parallel_arrays': (
        ('Overview', 'start indent after'),
        ('Issues', 'stop indent'),
        ),
    'AMD_depth_clamp_separate': (
        ('Add to table 6.9, Transformation State - p.350', 'indent'),
        ),
    'AMD_glx_gpu_association': (
        ('Issues', 'start indent after'),
        ('Revision History', 'stop indent'),
        ),
    'AMD_vertex_shader_tessellator': (
        ('4.3.4 Attribute, Change third sentence:', 'indent'),
        ('(Built-in Variables)', 'start indent after'),
        ('Additions to Chapter 8 of the OpenGL Shading Language 1.20 Specification', 'outdent'),
        ('(Built-in Functions)', 'outdent'),
        ('Additions to Chapter 9 of the OpenGL Shading Language 1.20 Specification', 'stop indent'),
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ('Sample Code', 'start indent after'),
        ('Issues', 'outdent'),
        ('Revision History', 'stop indent'),
        ),
    'AMD_wgl_gpu_association': (
        ('Issues', 'start indent after'),
        ('Revision History', 'stop indent'),
        ),
    'ARB_map_buffer_range': (
        ('Usage Examples', 'start indent after'),
        ('Revision History', 'stop indent'),
        ),
    'ARB_occlusion_query': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'outdent'),
        ('Revision History', 'stop indent'),
        ),
    'ARB_viewport_array': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'outdent'),
        ('Interactions with NV_depth_buffer_float', 'stop indent'),
        ('       FEEDBACK FROM PAT:', 'start indent after'),
        ('    7) What is the VIEWPORT_SUBPIXEL_BITS implementation defined value for?', 'stop indent'),
        ),
    'ARB_framebuffer_object': (
        ('Move the following existing state from "Implementation Dependent', 'start indent'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'ARB_sync': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'outdent'),
        ('Sample Code', 'stop indent'),
        ),
    'ARB_texture_cube_map': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'outdent'),
        ('Backwards Compatibility', 'stop indent'),
        ),
    'ARB_point_sprite': (
        ('New State', 'start indent after'),
        ('Revision History', 'stop indent'),
        ),
    'ARB_shading_language_include': (
        ('*** (compatibility profile only)', 'indent'),
        ),
    'ARB_vertex_buffer_object': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ('Usage Examples', 'start indent after'),
        ),
    'ARB_multitexture': (
        ('NOTE: This extension no longer has its own specification document, since', 'indent'),
        ),
    'ARB_provoking_vertex': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'outdent'),
        ('NVIDIA Implementation Details', 'stop indent'),
        ),
    'ARB_shader_precision': (
        ('Issues', 'start indent after'),
        ('Revision History', 'stop indent'),
        ),
    'ARB_blend_func_extended': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'ARB_instanced_arrays': (
        ('************************************************************************', 'ignore'),
        ),
    'ARB_shader_texture_lod': (
        ('Revision History:', 'start indent after'),
        ),
    'ARB_point_parameters': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'ARB_vertex_array_bgra': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'ARB_vertex_program': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'outdent'),
        ('Revision History', 'stop indent'),
        ),
    'ARB_wgl_render_texture': (
        ('Issues', 'start indent after'),
        ('Implementation Notes', 'outdent'),
        ('Intended Usage', 'stop indent'),
        ),
    'ARB_pixel_buffer_object': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'ARB_vertex_blend': (
        ('New State', 'start indent after'),
        ('Additions to Appendix A:', 'stop indent'),
        ),
    'ARB_occlusion_query2': (
        ('(OpenGL Operation)', 'start indent after'),
        ('Additions to Chapter 4 of the OpenGL 3.2 Specification', 'outdent'),
        ('(Per-Fragment Operations and the Frame Buffer)', 'outdent'),
        ('Additions to Chapter 6 of the OpenGL 3.2 Specification', 'outdent'),
        ('(State and State Requests)', 'outdent'),
        ('Dependencies', 'outdent'),
        ('New State', 'outdent'),
        ('Usage Examples', 'stop indent'),
        ),
    'ARB_matrix_palette': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'outdent'),
        ('Additions to Appendix A:', 'stop indent'),
        ),
    'ARB_wgl_create_context': (
        ('Issues', 'start indent after'),
        ('Revision History', 'stop indent'),
        ),
    'ARB_depth_clamp': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'ARB_shader_atomic_counters': (
        ('2.11.7 Uniform Variables', 'start indent after'),
        ('New State', 'outdent'),
        ('New Implementation Dependent State', 'outdent'),
        ('Additions to the OpenGL Shading Langauge 4.10.6 Specification', 'stop indent'),
        ('(Built-in Variables)', 'start indent after'),
        ('Additions to Chapter 8 of the OpenGL Shading Language 1.50 Specification', 'outdent'),
        ('(Built-in Functions)', 'outdent'),
        ('Sample Code', 'stop indent'),
        ('Issues', 'start indent after'),
        ),
    'ARB_wgl_extensions_string': (
        ('Advertising WGL Extensions', 'indent'),
        ),
    'ARB_sampler_objects': (
        ('** This error applies only to 3.2 core profile / 3.1 w/o ARB_compatibility /', 'indent'),
        ('** 3.0 deprecated contexts.', 'indent'),
        ),
    'SUNX_constant_data': (
        ('Additions to Chapter 2 of the GL Specification (OpenGL Operation)', 'start indent after'),
        ('Additions to the GLX / WGL / AGL Specifications', 'stop indent'),
        ),
    'SUN_vertex': (
        ('New Procedures and Functions', 'start indent after'),
        ('New Tokens', 'stop indent'),
        ('Additions to Chapter 2 of the 1.2 Specification (OpenGL Operation)', 'start indent after'),
        ('Additions to Chapter 3 of the 1.2 Specification (Rasterization)', 'stop indent'),
        ),
    'SUN_triangle_list': (
        ('Where i is sizeof(UNSIGNED_INT) rounded up to the nearest multiple of', 'start indent'),
        ('interleaved array pointer.', 'stop indent after'),
        ),
    'ATI_pn_triangles': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'ATI_text_fragment_shader': (
        ('Sample Usage', 'start indent after'),
        ('Revision History', 'stop indent'),
        ),
    'SGIX_instruments': (
        ('    An example of using the calls to test the extension:', 'outdent'),
        ('{', 'start indent'),
        ('New Tokens', 'stop indent'),
        ),
    'SGIX_shadow_ambient': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'SGIX_clipmap': (
        ('Additions to Chapter 3 of the 1.0 Specification (Rasterization)', 'start indent after'),
        ('Additions to Chapter 4 of the 1.0 Specification (Per-Fragment Operations', 'stop indent'),
        ),
    'SGIX_shadow': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'OML_resample': (
        ('XXX Note that the "last pixel" case is only needed for readbacks where', 'indent'),
        ('XXX <width> is not even, so may be removable.', 'indent'),
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'OML_glx_swap_method': (
        ('New Tokens', 'start indent after'),
        ('Additions to the OpenGL 1.2.1 Specification', 'stop indent'),
        ),
    'SGIS_texture_color_mask': (
        ('New State', 'start indent after'),
        ('Revision History', 'stop indent'),
        ),
    'HP_occlusion_test': (
        ('GL_HP_occlusion_test - PRELIMINARY', 'indent'),
        ('----------------------------------', 'indent'),
        ('Overview', 'start indent after'),
        ('New Procedures and Functions', 'stop indent'),
        ('--------------64E073B876D--', 'ignore'),
        ),
    'EXT_stencil_two_side': (
        ('New State', 'start indent after'),
        ('Revision History', 'stop indent'),
        ),
    'EXT_framebuffer_object': (
        ('XXX [from jon leech] describe derivation of red green and blue size', 'indent'),
        ('Move the following existing state from "Implementation Dependent', 'start indent'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'EXT_draw_range_elements': (
        ('Proposal:', 'start indent after'),
        ),
    'EXT_fog_coord': (
        ('New State', 'start indent after'),
        ('Revision History', 'stop indent'),
        ),
    'EXT_paletted_texture': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ('Revision History', 'start indent after'),
        ),
    'EXT_stencil_wrap': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'EXT_texture_sRGB_decode': (
        ('Additions to Chapter 3 of the 2.1 Specification (Rasterization)', 'start indent after'),
        ('Dependencies on ARB_sampler_objects or OpenGL 3.3 or later', 'stop indent'),
        ),
    'EXT_provoking_vertex': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'EXT_clip_volume_hint': (
        ('Revision History', 'start indent after'),
        ),
    'EXT_framebuffer_multisample': (
        ('New State', 'start indent after'),
        ('Usage Examples', 'stop indent'),
        ),
    'EXT_vertex_weighting': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'EXT_scene_marker': (
        ('Revision History', 'start indent after'),
        ),
    'EXT_separate_specular_color': (
        ('Issues', 'start indent after'),
        ('New Procedures and Functions', 'stop indent'),
        ),
    'EXT_vertex_array_bgra': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'EXT_texture_lod_bias': (
        ('New State', 'start indent after'),
        ('New Implementation State', 'outdent'),
        ('Revision History', 'stop indent'),
        ),
    'EXT_stencil_clear_tag': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'EXT_pixel_buffer_object': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'EXT_misc_attribute': (
        ('(Table 6.1 (Attribute Groups).)', 'indent'),
        ('(In the glXCopyContext description)', 'indent'),
        ),
    'EXT_shared_texture_palette': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'EXT_packed_depth_stencil': (
        ('Revision History', 'start indent after'),
        ),
    'EXT_depth_bounds_test': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'EXT_secondary_color': (
        ('New State', 'start indent after'),
        ),
    'EXT_vertex_shader': (
        ('    Table of operations', 'start indent after'),
        ('        A special operation is OP_INDEX_EXT. It is special in that it', 'stop indent'),
        ('Errors', 'start indent after'),
        ('New State', 'outdent'),
        ('New Implementation Dependent State', 'stop indent'),
        ),
    'EXT_texture_filter_anisotropic': (
        ('New State', 'start indent after'),
        ('New Implementation State', 'outdent'),
        ('Revision History', 'stop indent'),
        ),
    'EXT_texture_shared_exponent': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ('Appendix', 'start indent after'),
        ('Issues', 'stop indent'),
        ),
    'OES_OES_byte_coordinates': (
        ('New State', 'start indent after'),
        ('New Implementation Dependent State', 'stop indent'),
        ('Revision History', 'start indent after'),
        ),
    'OES_OES_query_matrix': (
        ('Revision History', 'start indent after'),
        ),
    'OES_OES_fixed_point': (
        ('Issues', 'start indent after'),
        ('New Procedures and Functions', 'stop indent'),
        ),
    'OES_OES_read_format': (
        ('Issues', 'start indent after'),
        ('New Procedures and Functions', 'stop indent'),
        ('New Implementation Dependent State', 'start indent after'),
        ('Revision History', 'stop indent'),
        ),
    'OES_OES_single_precision': (
        ('Issues', 'start indent after'),
        ('New Procedures and Functions', 'stop indent'),
        ),
    }


def fixup_indent(extension_name, lines):
    fixups = list(INDENT_FIXUPS.get(extension_name, ()))
    additional_indent = ''
    for line in lines:
        line = line.rstrip()
        if len(fixups) != 0 and fixups[0][0] == line:
            cmd = fixups[0][1]
            del fixups[0]
        else:
            cmd = ''
        if cmd == 'start indent':
            additional_indent = '    '
            yield additional_indent + line
        elif cmd == 'stop indent':
            additional_indent = ''
            yield additional_indent + line
        elif cmd == 'start indent after':
            yield additional_indent + line
            additional_indent = '    '
        elif cmd == 'stop indent after':
            yield additional_indent + line
            additional_indent = ''
        elif cmd == 'indent':
            yield '    ' + line
        elif cmd == 'outdent':
            yield line.strip()
        elif cmd == '':
            yield additional_indent + line
        elif cmd == 'ignore':
            pass
        else:
            print 'Unrecognized indent fixup: {0!r}'.format(cmd)
    if len(fixups) != 0:
        print 'Unfinished fixups in {0}'.format(extension_name)


# Assign each line a boolean (True if it is indented, False if not),
# and then group consecutive lines whose boolean value is the same.
# Return a list of pairs (indented, grouped_lines).  Blank lines are
# considered indented.
def group_sections(lines):
    groups = []
    for line in lines:
        indented = (line == '' or line[0].isspace())
        if len(groups) > 0 and groups[-1][0] == indented:
            groups[-1][1].append(line)
        else:
            groups.append((indented, [line]))
    return groups


def expando(text):
    m = EXPANDO_REGEXP.search(text)
    if not m:
        yield text
        return
    expando_expression = m.group(0)
    if expando_expression not in EXPANDO_EXPRESSIONS:
        print 'Unknown expando expression: {0}'.format(expando_expression)
        return
    for expansion in EXPANDO_EXPRESSIONS[expando_expression]:
        for item in expando(text[:m.start(0)] + expansion + text[m.end(0):]):
            yield item


def extract_tokens(extension_name, text):
    if extension_name in ('EXT_secondary_color', 'EXT_fog_coord'):
        text = text.replace('[', '{')
        text = text.replace(']', '}')
    tokens = set()
    for m in PROCEDURE_NAME_REGEXP.finditer(text):
        for item in expando(m.group(0)):
            if item.startswith('gl'):
                item = item[2:]
            if extension_name == 'ATI_vertex_streams' and not item.endswith('ATI'):
                item = item + 'ATI'
            tokens.add(item)
    return tokens


def handle_file(extension_name, f):
    sections = []
    section_name = ''
    for indented, lines in group_sections(fixup_indent(extension_name, f)):
        if indented:
            sections.append((section_name, lines))
        else:
            section_name = ' '.join(lines)
    procedure_data = []
    for section_name, section_contents in sections:
        if section_name.lower().find('procedure') != -1:
            procedure_data.extend(section_contents)
        if section_name.startswith('Additions to '):
            continue
        if section_name.startswith('Addition to '):
            continue
        if section_name.startswith('additions to '):
            continue
        if section_name.startswith('Interactions with '):
            continue
        if section_name.startswith('Interaction with '):
            continue
        if section_name.startswith('Dependencies on '):
            continue
        if section_name.startswith('Dependencies with '):
            continue
        if section_name.startswith('Modifications to '):
            continue
        if section_name.startswith('Modification to '):
            continue
        if section_name.startswith('Modify '):
            continue
        if section_name.startswith('Appendix'):
            continue
        if section_name.startswith('GLX Protocol'):
            continue
        if section_name.startswith('GLX protocol'):
            continue
        if section_name.startswith('Add a new subsection after '):
            continue
        if section_name.startswith('Changes from '):
            continue
        if section_name.startswith('Changes to '):
            continue
        if section_name.startswith('Add to '):
            continue
        if section_name.startswith('Issues from '):
            continue
        if section_name.startswith('Insert Section '):
            continue
        if section_name.startswith('Add Section '):
            continue
        if section_name in RECOGNIZED_SECTIONS:
            continue
        print 'Unrecognized section in {0}: {1!r}'.format(extension_name, section_name)
    return extract_tokens(extension_name, '\n'.join(procedure_data))


with open(os.path.expanduser('~/.platform/piglit-mesa/piglit/build/glapi/glapi.json'), 'r') as f:
    api = json.load(f)


procedure_tokens = {}
for root, dirs, files in os.walk(os.path.expanduser('~/opengl-docs/www.opengl.org/registry/specs/')):
    dirroot, dirname = os.path.split(root)
    for filename in files:
        fileroot, fileext = os.path.splitext(filename)
        if fileext == '.txt':
            extension_name = '{0}_{1}'.format(dirname, fileroot)
            with open(os.path.join(root, filename), 'r') as f:
                procedure_tokens[extension_name] = handle_file(extension_name, f)


found_functions = {}
for ext, tokens in procedure_tokens.items():
    found_functions[ext] = set()
    for fname in api['functions'].keys():
        if fname in tokens:
            found_functions[ext].add(fname)


expected_functions = {}
for fname, fdata in api['functions'].items():
    category_name = fdata['category']
    category = api['categories'][category_name]
    if category['kind'] != 'extension':
        continue
    category_name_short = category['extension_name'][3:]
    if category_name_short not in expected_functions:
        expected_functions[category_name_short] = set()
    expected_functions[category_name_short].add(fname)


extra_extensions_found = set(found_functions.keys()) - set(expected_functions.keys())
if extra_extensions_found:
    print 'Extra extensions found: {0}'.format(', '.join(extra_extensions_found))

missing_extensions = set(expected_functions.keys()) - set(found_functions.keys())
if missing_extensions:
    print 'Missing extensions: {0}'.format(', '.join(missing_extensions))

common_extensions = set(found_functions.keys()) & set(expected_functions.keys())
for ext in common_extensions:
    functions_found = found_functions[ext]
    functions_expected = expected_functions[ext]
    extra_functions = functions_found - functions_expected
    if extra_functions:
        print 'In {0}, extra functions found: {1}'.format(ext, ', '.join(extra_functions))
    missing_functions = functions_expected - functions_found
    if missing_functions:
        print 'In {0}, missing functions: {1}'.format(ext, ', '.join(missing_functions))
