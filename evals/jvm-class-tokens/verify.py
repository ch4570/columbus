"""Compiler checks for primitive and array Class<T> argument correlations."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]/'jvm-guardrails'))
import verify_generic_array_context as corpus

gate=corpus.gate
prefix='class Factory { static <T> void hit(Class<T> type, T value) {} } '
for name, token, value, valid in [
    ('primitive_int_valid','int.class','1',True),
    ('primitive_int_wrong_boolean','int.class','true',False),
    ('primitive_boolean_valid','boolean.class','true',True),
    ('primitive_boolean_wrong_int','boolean.class','1',False),
    ('primitive_array_valid','int[].class','new int[0]',True),
    ('primitive_array_wrong_component','int[].class','new long[0]',False),
    ('reference_array_valid','String[].class','new String[0]',True),
    ('reference_array_wrong_component','String[].class','new Object[0]',False),
    ('primitive_array_not_boxed','int[].class','new Integer[0]',False),
    ('boxed_array_not_primitive','Integer[].class','new int[0]',False),
    ('array_dimensions_valid','int[][].class','new int[1][]',True),
    ('array_dimensions_invalid','int[][].class','new int[1]',False),
    ('reference_array_covariant','Object[].class','new String[0]',True),
    ('primitive_array_not_object_array','Object[].class','new int[0]',False),
    ('nested_primitive_array_is_object_array','Object[].class','new int[0][]',True),
    ('array_initializer','String[].class','new String[]{"x"}',True),
    ('class_token_array_cloneable','Cloneable.class','new int[0]',True),
    ('class_token_array_serializable','java.io.Serializable.class','new int[0]',True),
]:
    gate.CASES.append((name,valid,valid,{'C.java':prefix+'class C { void run() { Factory.hit('+token+', '+value+'); } }'}))
for name, token, value, valid in [
    ('shadowed_reference_array_valid','String[].class','new String[0]',True),
    ('shadowed_reference_array_mismatch','java.lang.String[].class','new String[0]',False),
]:
    gate.CASES.append((name,valid,valid,{'C.java':'class String {} '+prefix+'class C { void run() { Factory.hit('+token+', '+value+'); } }'}))
assert len({case[0] for case in gate.CASES}) == len(gate.CASES)
if __name__=='__main__':gate.main()
