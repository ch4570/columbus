"""Assignment result contexts checked against javac, with conditional and shadow controls."""
from pathlib import Path
import runpy
corpus=runpy.run_path(str(Path(__file__).parents[1]/'jvm-conditional-context/verify.py'))
gate=corpus['gate']
for name,body,valid in [
 ('assignment_bad','void run() { String value; value=hit(1); }',False),
 ('assignment_good','void run() { Integer value; value=hit(1); }',True),
 ('parameter_assignment_bad','void run(String value) { value=hit(1); }',False),
 ('parameter_assignment_good','void run(Integer value) { value=hit(1); }',True),
 ('assignment_conditional_bad','void run(boolean b) { String value; value=b ? hit(1) : null; }',False),
 ('assignment_conditional_good','void run(boolean b) { Integer value; value=b ? hit(1) : null; }',True),
 ('assignment_condition_good','void run() { String value; value=hit(true) ? "a" : "b"; }',True),
 ('assignment_field_shadow_good','String value; void run() { Integer value; value=hit(1); }',True),
 ('assignment_field_shadow_bad','Integer value; void run() { String value; value=hit(1); }',False),
 ('parameter_trailing_array_bad','void run(Integer value[]) { value=hit(1); }',False),
 ('parameter_varargs_bad','void run(Integer... value) { value=hit(1); }',False),
 ('sibling_block_good','void run() { { String value; } { Integer value; value=hit(1); } }',True),
 ('compound_assignment_good','void run() { String value=""; value+=hit(1); }',True),
]:
 gate.CASES.append((name,valid,valid,{'C.java':'class C { static <T> T hit(T value) { return value; } '+body+' }'}))
if __name__=='__main__':gate.main()
