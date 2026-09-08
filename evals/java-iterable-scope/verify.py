"""Compile isolated loop-scope controls and retain static-target evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from columbus.jvm import parse_jvm, resolve_jvm

p=argparse.ArgumentParser();p.add_argument('--jdk',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
cases=[
 ('implicit', 'for(C item : items()) { item.hit(); }', True, [True]),
 ('parameter_receiver', 'for(C item : other.items()) { item.hit(); }', True, [True]),
 ('wrong_argument', 'for(C item : items(1)) { item.hit(); }', False, [False]),
 ('nested', 'for(C item : items()) { for(C inner : items()) { inner.hit(); } }', True, [True,False]),
]
report={'compiler':subprocess.run([str(a.jdk/'javac'),'-version'],capture_output=True,text=True,check=True).stdout.strip(),'cases':[]}
for name,body,valid,expected in cases:
 source='class C { C[] items() { return new C[0]; } void hit() {} void run(C other) { '+body+' } }'
 with tempfile.TemporaryDirectory() as d:
  root=Path(d);(root/'C.java').write_text(source,encoding='utf-8')
  compile_result=subprocess.run([str(a.jdk/'javac'),'-proc:none','-d',str(root),str(root/'C.java')],capture_output=True,text=True)
  assert (compile_result.returncode==0)==valid,name
  javap=subprocess.run([str(a.jdk/'javap'),'-classpath',str(root),'-c','-p','C'],capture_output=True,text=True,check=True).stdout if valid else None
  parsed=parse_jvm('C.java',source);resolve_jvm([parsed])
  items=[r for r in parsed['references'] if r['member']=='items' and r['kind']=='calls']
  assert [r['resolved'] for r in items]==expected,(name,items)
  assert all(r.get('target')=='C.java::C.items:method()' for r in items if r['resolved'])
  assert all(not r['resolved'] for r in parsed['references'] if r['member']=='hit' and r['kind']=='calls')
  if valid:assert 'Method items:()[LC;' in javap
  report['cases'].append({'name':name,'source':source,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'javac_return_code':compile_result.returncode,'javac_stderr':compile_result.stderr,'javap':javap,'iterable_calls':items,'loop_body_still_unresolved':True})
a.output.write_text(json.dumps(report,indent=2)+'\n');print('Passed',len(cases),'compiler controls')
