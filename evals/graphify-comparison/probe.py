"""Run source-oracle Java probes against either engine, with isolated caches."""
import argparse
import json
from pathlib import Path
import tempfile
import time

CASES = {
 'this_call': {'files': {'C.java':'package demo; class C { void hit() {} void run() { this.hit(); } }'}, 'expected':'C.hit'},
 'generic_receiver': {'files': {'C.java':'package demo; class Box<T> { void hit() {} } class C { void run(Box<String> box) { box.hit(); } }'}, 'expected':'Box.hit'},
 'loop_receiver': {'files': {'C.java':'package demo; class Item { void hit() {} } class C { void run(Item[] items) { for (Item item : items) { item.hit(); } } }'}, 'expected':'Item.hit'},
 'parameter_receiver': {'files': {'C.java':'package demo; class Item { void hit() {} } class C { void run(Item item) { item.hit(); } }'}, 'expected':'Item.hit'},
 'wrong_package': {'files': {'unrelated/Item.java':'package unrelated; class Item { void hit() {} }', 'app/C.java':'package app; import external.Item; class C { void run(Item item) { item.hit(); } }'}, 'forbidden':'Item.hit', 'note':'External imported type is deliberately outside indexed scope; never bind unrelated.Item.'},
 'type_parameter_shadow': {'files': {'C.java':'package demo; class T { void hit() {} } interface API { void hit(); } class C<T extends API> { void run(T item) { item.hit(); } }'}, 'forbidden':'T.hit', 'expected':'API.hit'},
 'inherited_overload': {'files': {'C.java':'package demo; class Base { void hit(int n) {} } class C extends Base { void hit(String s) {} void run() { hit(1); } }'}, 'expected':'Base.hit', 'forbidden':'C.hit'},
 'parameter_shadows_field': {'files': {'C.java':'package demo; interface API { void hit(); } class Item { void hit() {} } class C { Item item; void run(API item) { item.hit(); } }'}, 'expected':'API.hit', 'forbidden':'Item.hit'},
 'partial_file': {'files': {'C.java':'package demo; @java.lang.annotation.Target(java.lang.annotation.ElementType.TYPE_USE) @interface Mark {} class C { void hit() {} void run() { hit(); } void other(int @Mark ... args) {} }'}, 'expected':'C.hit', 'note':'Legal annotated varargs causes pinned Java grammar recovery.'},
}

def main():
 p=argparse.ArgumentParser();p.add_argument('engine',choices=['columbus','graphify']);p.add_argument('--output',type=Path,required=True);p.add_argument('--require-safe',action='store_true',help='Exit 1 if a forbidden target is emitted');a=p.parse_args();results=[]
 with tempfile.TemporaryDirectory(prefix='columbus-guardrail-') as d:
  for name,case in CASES.items():
   root=Path(d)/name;root.mkdir();paths=[]
   for rel,source in case['files'].items():
    path=root/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(source);paths.append(path)
   t=time.perf_counter()
   if a.engine=='columbus':
    from columbus.jvm import parse_jvm,resolve_jvm
    files=[parse_jvm(str(p.relative_to(root)),p.read_text()) for p in paths];edges=resolve_jvm(files)
    nodes={s['id']:s for f in files for s in f['symbols']}
    calls=[dict(source=nodes[e['source']]['qualname'],target=nodes[e['target']]['qualname'],**{k:v for k,v in e.items() if k not in ['source','target']}) for e in edges if e['kind']=='calls']
    diagnostics=[dict(path=f['path'],partial=f['partial'],diagnostics=f['diagnostics']) for f in files]
   else:
    from graphify.extract import extract
    data=extract(paths,cache_root=root/'cache',root=root,parallel=False);nodes={n['id']:n for n in data['nodes']}
    owners={e['target']:nodes.get(e['source'],{}).get('label','') for e in data['edges'] if e.get('relation')=='method'}
    calls=[dict(source=nodes.get(e['source'],{}).get('label',e['source']),target=nodes.get(e['target'],{}).get('label',e['target']),source_node=nodes.get(e['source']),target_node=nodes.get(e['target']),target_owner=owners.get(e['target']),**{k:v for k,v in e.items() if k not in ['source','target']}) for e in data['edges'] if e.get('relation')=='calls']
    diagnostics={k:v for k,v in data.items() if k not in ['nodes','edges','hyperedges']}
   targets = [c['target'] if a.engine=='columbus' else (c.get('target_owner') or '')+'.'+c['target'].strip('.()') for c in calls]
   found = lambda key: any(target==case.get(key) or target.endswith('.'+case.get(key,'INVALID')) for target in targets)
   results.append(dict(name=name,case=case,calls=calls,diagnostics=diagnostics,seconds=time.perf_counter()-t,
                       expected_found=found('expected') if 'expected' in case else None,
                       forbidden_found=found('forbidden') if 'forbidden' in case else False))
 a.output.write_text(json.dumps(dict(engine=a.engine,results=results),indent=2)+'\n')
 print(json.dumps([dict(name=r['name'],calls=[(c['source'],c['target']) for c in r['calls']]) for r in results],indent=2))
 return 1 if a.require_safe and any(r['forbidden_found'] for r in results) else 0
if __name__=='__main__':raise SystemExit(main())
