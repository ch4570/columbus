"""Compiler-backed collection loop inventory; unresolved calls stay visible as gaps."""
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

p=argparse.ArgumentParser();p.add_argument('--jdk',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--require-parameters',action='store_true');a=p.parse_args()
cases=json.loads(Path(__file__).with_name('cases.json').read_text())
report={'scope':'Isolated collection loop cases with manually specified declaration owners; no runtime-dispatch assertion. Missing targets count as gaps, not correct resolution.','cases':[]}
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
  if a.require_parameters and name in {'list_parameter','list_var'}:
   assert all(r['resolved_expected_target'] for r in rows),(name,rows)
  report['cases'].append({'name':name,'source':source,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'javac_return_code':compilation.returncode,'javac_stderr':compilation.stderr,'javap':bytecode,'calls':rows})
report['expected_valid_calls']=sum(x['expected_static_target'] is not None for c in report['cases'] for x in c['calls'])
report['resolved_expected_calls']=sum(x['resolved_expected_target'] for c in report['cases'] for x in c['calls'])
a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print({k:v for k,v in report.items() if k!='cases'})
