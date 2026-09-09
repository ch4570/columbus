"""Observe reduced generic constraints motivated by the Spring source review."""
import verify_packages as gate

prefix='class Factory { static <T> void hit(Class<T> type, T value) {} } '
gate.CASES=[]
for name, value, valid, expected in [
    ('literal_valid','"text"',True,True),
    ('literal_invalid','1',False,False),
    ('expression_valid','String.valueOf(1)',True,True),
    ('expression_invalid','Integer.valueOf(1)',False,False),
]:
    source=prefix+'class C { void run() { Factory.hit(String.class, '+value+'); } }'
    gate.CASES.append((name,valid,expected,{'C.java':source}))
gate.CASES += [
    ('literal_charsequence_valid',True,True,{'C.java':prefix+'class C { void run() { Factory.hit(CharSequence.class, \"text\"); } }'}),
    ('generic_filter_valid_literal',True,True,{'C.java':'class Filter<T> {} class C { static <T> void hit(Filter<T> filter, T value) {} void run() { hit(new Filter<String>(), \"text\"); } }'}),
    ('generic_array_valid',True,True,{'C.java':'class C { static <T> T[] hit(T... values) { return values; } void run() { String[] values = hit("text"); } }'}),
    ('generic_filter_invalid_expression',False,False,{'C.java':'class Filter<T> {} class C { static <T> void hit(Filter<T> filter, T value) {} void run() { hit(new Filter<String>(), Integer.valueOf(1)); } }'}),
]

if __name__=='__main__':gate.main()
