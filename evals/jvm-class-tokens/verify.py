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
]:
    gate.CASES.append((name,valid,valid,{'C.java':prefix+'class C { void run() { Factory.hit('+token+', '+value+'); } }'}))
if __name__=='__main__':gate.main()
