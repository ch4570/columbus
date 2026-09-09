"""Conditional result context, including branch and condition negative controls."""
from pathlib import Path
import runpy
corpus=runpy.run_path(str(Path(__file__).parents[1]/'jvm-return-constraints/verify.py'))
gate=corpus['gate']
for name,body,valid in [
 ('conditional_assignment_bad','void run(boolean b) { String s=b ? hit(1) : null; }',False),
 ('conditional_assignment_good','void run(boolean b) { Integer s=b ? hit(1) : null; }',True),
 ('conditional_return_bad','String run(boolean b) { return b ? null : hit(1); }',False),
 ('conditional_return_good','Integer run(boolean b) { return b ? null : hit(1); }',True),
 ('nested_conditional_bad','void run(boolean b) { String s=(b ? null : (b ? hit(1) : null)); }',False),
 ('conditional_condition_good','void run() { String s=hit(true) ? "a" : "b"; }',True),
]:
 gate.CASES.append((name,valid,valid,{'C.java':'class C { static <T> T hit(T value) { return value; } '+body+' }'}))
if __name__=='__main__':gate.main()
