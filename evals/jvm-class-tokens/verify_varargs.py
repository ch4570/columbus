"""Check fixed-arity array invocation before target-type generic inference."""
import verify as corpus

gate=corpus.gate
for name,context,valid in [('array_argument_flat_result','String[]',True),('array_argument_nested_result','String[][]',False),('array_argument_object_result','Object[]',True)]:
    source='class C { static <T> T[] hit(T... values) { return values; } void run() { '+context+' result=hit(new String[0]); } }'
    gate.CASES.append((name,valid,valid,{'C.java':source}))
for name,token,value,valid in [
    ('anchored_flat_array','String.class','new String[0]',True),
    ('anchored_array_as_value','String[].class','new String[0]',True),
    ('anchored_primitive_array_as_value','Object.class','new int[0]',True),
    ('anchored_wrong_array','String.class','new Object[0]',False),
]:
    gate.CASES.append((name,valid,valid,{'C.java':'class C { static <T> void hit(Class<T> type,T... values) {} void run() { hit('+token+','+value+'); } }'}))
assert len({c[0] for c in gate.CASES}) == len(gate.CASES)
if __name__=='__main__':gate.main()
