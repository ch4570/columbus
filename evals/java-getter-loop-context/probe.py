"""Check producer/consumer type namespaces before getter-loop inference."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import sys
import importlib.metadata
import columbus.jvm as jvm

p=argparse.ArgumentParser();p.add_argument('--jdk',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--require-getters',action='store_true');a=p.parse_args()
report={'scope':'Three compiler-backed cross-package getter cases; unresolved valid calls are gaps. No runtime dispatch proof.','analyzer_sha256':hashlib.sha256(Path(jvm.__file__).read_bytes()).hexdigest(),'cases':[]}
version=subprocess.run([str(a.jdk/'javac'),'-version'],capture_output=True,text=True,check=True)
report.update(compiler=(version.stdout+version.stderr).strip(),python=sys.version,versions={name:importlib.metadata.version(name) for name in ('tree-sitter','tree-sitter-java')})
for declared,valid in [('a.Item',True),('var',True),('Item',False)]:
 sources={'a/Item.java':'package a; public class Item { public void hit() {} }',
  'a/Source.java':'package a; public class Source { public java.util.Collection<Item> items() { return null; } }',
  'b/Item.java':'package b; public class Item { public void hit() {} }',
  'b/C.java':'package b; public class C { void run(a.Source source) { for('+declared+' item : source.items()) item.hit(); } }'}
 with tempfile.TemporaryDirectory() as d:
  root=Path(d)
  for name,source in sources.items():
   dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(source,encoding='utf-8')
  compile_result=subprocess.run([str(a.jdk/'javac'),'-proc:none','-d',str(root),*[str(root/n) for n in sources]],capture_output=True,text=True)
  assert (compile_result.returncode==0)==valid,compile_result.stderr
  bytecode=subprocess.run([str(a.jdk/'javap'),'-classpath',str(root),'-c','-p','b.C'],capture_output=True,text=True,check=True).stdout if valid else None
  if valid:assert 'Method a/Item.hit:()V' in bytecode and 'Method b/Item.hit:()V' not in bytecode
  parsed=[jvm.parse_jvm(name,source) for name,source in sources.items()];jvm.resolve_jvm(parsed)
  ref=next(r for f in parsed for r in f['references'] if r['kind']=='calls' and r['member']=='hit')
  expected='a/Item.java::a.Item.hit:method()' if valid else None
  assert not ref['resolved'] or ref.get('target')==expected,ref
  if a.require_getters and valid:assert ref.get('target')==expected,ref
  report['cases'].append({'declared_loop_type':declared,'sources':sources,'source_sha256':{n:hashlib.sha256(s.encode()).hexdigest() for n,s in sources.items()},'javac_return_code':compile_result.returncode,'javac_stderr':compile_result.stderr,'javap':bytecode,'expected_static_target':expected,'actual':ref})
a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('Cross-package cases:',len(report['cases']),'resolved:',sum(c['actual']['resolved'] for c in report['cases']))
