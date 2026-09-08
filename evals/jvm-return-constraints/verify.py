"""Compiler gate for type variables appearing only in method return types."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'jvm-class-tokens'))
import verify_varargs as corpus

gate=corpus.gate
for name,declaration,context,valid,resolved in [
 ('bounded_return_invalid','static <T extends Number> T','String',False,False),
 ('bounded_return_valid_unresolved','static <T extends Number> T','Number',True,False),
 ('unbounded_return_valid','static <T> T','String',True,True),
 ('unbounded_array_return_valid','static <T> T[]','String[]',True,True),
 ('unbounded_array_return_invalid','static <T> T[]','String',False,False),
]:
 gate.CASES.append((name,valid,resolved,{'C.java':'class C { '+declaration+' hit() { return null; } void run() { '+context+' result=hit(); } }'}))
for name,context,valid in [('declaring_return_invalid','String',False),('declaring_return_valid_unresolved','T',True)]:
 gate.CASES.append((name,valid,False,{'C.java':'class C<T> { T hit() { return null; } void run() { '+context+' result=hit(); } }'}))
assert len({c[0] for c in gate.CASES})==len(gate.CASES)
if __name__=='__main__':gate.main()
