"""Blocking generic argument constraints, with explicit unsupported cases."""
import observe_generic_constraints as corpus

gate=corpus.gate
factory='class Factory { static <T> void hit(Class<T> type, T value) {} } '
gate.CASES += [
    ('nested_type_mimics_java_lang',False,False,{'C.java':'class java { static class lang { static class String {} } } class C { static <T> void hit(Class<T> type,T value) {} void run() { hit(java.lang.String.class, \"text\"); } }'}),
    ('generic_source_identity_valid',True,True,{'C.java':'class Value {} class C { static <T> void hit(Class<T> type,T value) {} void run() { hit(Value.class, new Value()); } }'}),
    ('declaring_type_invalid',False,False,{'C.java':'class C<T> { void hit(T value) {} void run() { hit(Integer.valueOf(1)); } }'}),
    ('number_anchor',True,True,{'C.java':factory+'class C { void run() { Factory.hit(Number.class, 1); } }'}),
    ('typed_local_valid',True,True,{'C.java':factory+'class C { void run(String value) { Factory.hit(String.class, value); } }'}),
    ('typed_local_invalid',False,False,{'C.java':factory+'class C { void run(Integer value) { Factory.hit(String.class, value); } }'}),
    ('typed_class_token',True,True,{'C.java':factory+'class C { void run(Class<String> type) { Factory.hit(type, "ok"); } }'}),
    ('conflicting_tokens',False,False,{'C.java':'class C { static <T> void hit(Class<T> a, Class<T> b, T value) {} void run() { hit(String.class, Integer.class, "text"); } }'}),
    ('bounded_valid_unresolved',True,False,{'C.java':'class C { static <T extends Number> void hit(T value) {} void run() { hit(1); } }'}),
    ('bounded_invalid',False,False,{'C.java':'class C { static <T extends Number> void hit(T value) {} void run() { hit("bad"); } }'}),
    ('explicit_valid_unresolved',True,False,{'C.java':'class C { static <T> void hit(T value) {} void run() { C.<String>hit("ok"); } }'}),
    ('explicit_invalid',False,False,{'C.java':'class C { static <T> void hit(T value) {} void run() { C.<String>hit(1); } }'}),
    ('array_wrong_assignment',False,False,{'C.java':'class C { static <T> T[] hit(T... values) { return values; } void run() { String[] a = hit(1); } }'}),
    ('array_wrong_return',False,False,{'C.java':'class C { static <T> T[] hit(T... values) { return values; } String[] run() { return hit(1); } }'}),
    ('array_mixed_valid',True,True,{'C.java':'class C { static <T> T[] hit(T... values) { return values; } void run() { Object[] a = hit(1, "text"); } }'}),
    ('shadowed_value_factory',False,False,{'C.java':factory+'class String { static Integer valueOf(int value) { return value; } } class C { void run() { Factory.hit(java.lang.String.class, String.valueOf(1)); } }'}),
    ('type_variable_class_token',False,False,{'C.java':factory+'class C<String> { void run() { Factory.hit(String.class, "text"); } }'}),
]

if __name__=='__main__':gate.main()
