"""Compiler-backed loop binding inventory; unresolved calls stay visible as gaps."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import sys
import importlib.metadata
import columbus.jvm as jvm
from columbus.jvm import parse_jvm, resolve_jvm

p=argparse.ArgumentParser();p.add_argument('--jdk',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
base='class Item { void hit() {} } class Wrong { void hit() {} Item[] values() { return new Item[0]; } } '
cases=[
 ('explicit_array',base+'class C { void run(Item[] values) { for(Item item : values) item.hit(); } }',True,['Item']),
 ('field_shadow_and_restore',base+'class C { Wrong item; void run(Item[] values) { for(Item item : values) item.hit(); item.hit(); } }',True,['Item','Wrong']),
 ('iterable_before_binding',base+'class C { Wrong item; void run() { for(Item item : item.values()) item.hit(); } }',True,['Item']),
 ('nested',base+'class C { void run(Item[][] values) { for(Item[] row : values) for(Item item : row) item.hit(); } }',True,['Item']),
 ('var_inference',base+'class C { void run(Item[] values) { for(var item : values) item.hit(); } }',True,['Item']),
 ('generic_shadow',base+'class T { void hit() {} } class C<T extends Item> { void run(T[] values) { for(T item : values) item.hit(); } }',True,['Item']),
 ('outside_scope',base+'class C { void run(Item[] values) { for(Item item : values) {} item.hit(); } }',False,[None]),
 ('incompatible_iterable',base+'class C { void run(Wrong[] values) { for(Item item : values) item.hit(); } }',False,[None]),
 ('local_name_conflict',base+'class C { void run(Item[] values) { Item item=null; for(Item item : values) item.hit(); } }',False,[None]),
 ('wrong_argument',base+'class C { void run(Item[] values) { for(Item item : values) item.hit(1); } }',False,[None]),
]
report={'scope':'Ten isolated loop cases with manually specified declaration owners; no runtime-dispatch assertion. Missing targets count as gaps, not correct resolution.','cases':[]}
version=subprocess.run([str(a.jdk/'javac'),'-version'],capture_output=True,text=True,check=True)
report.update(compiler=(version.stdout+version.stderr).strip(), python=sys.version, analyzer_sha256=hashlib.sha256(Path(jvm.__file__).read_bytes()).hexdigest(), versions={name:importlib.metadata.version(name) for name in ('tree-sitter','tree-sitter-java')})
for name,source,valid,owners in cases:
 with tempfile.TemporaryDirectory() as d:
  root=Path(d);(root/'C.java').write_text(source,encoding='utf-8')
  compilation=subprocess.run([str(a.jdk/'javac'),'-proc:none','-d',str(root),str(root/'C.java')],capture_output=True,text=True)
  assert (compilation.returncode==0)==valid,(name,compilation.stderr)
  bytecode=subprocess.run([str(a.jdk/'javap'),'-classpath',str(root),'-c','-p','C'],capture_output=True,text=True,check=True).stdout if valid else None
  if valid:
   for owner in owners:assert f'Method {owner}.hit:()V' in bytecode,(name,bytecode)
  parsed=parse_jvm('C.java',source);resolve_jvm([parsed])
  calls=[r for r in parsed['references'] if r['kind']=='calls' and r['member']=='hit']
  assert len(calls)==len(owners)
  rows=[]
  for ref,owner in zip(calls,owners):
   expected=f'C.java::{owner}.hit:method()' if owner else None
   assert not ref['resolved'] or ref['target']==expected,(name,ref,expected)
   rows.append({'expected_static_target':expected,'actual':ref,'resolved_expected_target':bool(expected and ref.get('target')==expected)})
  report['cases'].append({'name':name,'source':source,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'javac_return_code':compilation.returncode,'javac_stderr':compilation.stderr,'javap':bytecode,'calls':rows})
report['expected_valid_calls']=sum(x['expected_static_target'] is not None for c in report['cases'] for x in c['calls'])
report['resolved_expected_calls']=sum(x['resolved_expected_target'] for c in report['cases'] for x in c['calls'])
a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print({k:v for k,v in report.items() if k!='cases'})
