"""Compare two resolvers on identical fresh Spring syntax facts; no Spring build."""
import argparse
import ast
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import time
from columbus.index import RepositoryIndex, decode_parse

ROOT=Path(__file__).resolve().parents[2]
PIN='4c8c6409a27a62ab163d3b6196ad862b7c835440'

def module(path,name):
    spec=importlib.util.spec_from_file_location('columbus.'+name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    root=args.repo.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    assert subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()==PIN
    assert not subprocess.check_output(['git','-C',str(root),'diff','HEAD','--','.'])
    old=out/'before.py';old.write_bytes(subprocess.check_output(['git','show','f6a7530:skills/columbus/scripts/columbus/jvm.py'],cwd=ROOT))
    new=out/'after.py';new.write_bytes((ROOT/'skills/columbus/scripts/columbus/jvm.py').read_bytes())
    def syntax(path):
        return [ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text()).body
                if getattr(n,'name',None) not in {'_Resolver','resolve_jvm'}]
    assert syntax(old)==syntax(new), 'Syntax extraction changed; isolate resolver comparison first'
    started=time.perf_counter();index=RepositoryIndex(out/'index.sqlite');status=index.refresh(root)
    with sqlite3.connect(out/'index.sqlite') as conn:
        facts=[decode_parse(r[0]) for r in conn.execute('SELECT parsed FROM files ORDER BY path')]
        manifest={r[0]:r[1] for r in conn.execute('SELECT path,hash FROM files ORDER BY path')}
    tracked=set(subprocess.check_output(['git','-C',str(root),'ls-files','-z']).decode().split('\0'))
    assert set(manifest)<=tracked, 'Untracked sources would change the frozen corpus'
    assert len(facts)==1166, 'Unexpected frozen source inventory'
    symbols={s['id']:s for f in facts for s in f['symbols']}
    def edges(resolver):
        return {(e['source'],e['target'],e['path'],e['line']):e for e in resolver.resolve_jvm(facts) if e['kind']=='calls'}
    before=edges(module(old,'review_before'));after=edges(module(new,'review_after'))
    refs={(r['source'],r['path'],r['line'],r.get('evidence')):r for f in facts for r in f['references']}
    def records(keys,source):
        rows=[]
        for key in sorted(keys):
            edge=source[key];ref=refs.get((edge['source'],edge['path'],edge['line'],edge['evidence']),{})
            rows.append({'edge':edge,'source':symbols[edge['source']], 'target':symbols[edge['target']], 'current_reference':ref})
        return rows
    added=records(after.keys()-before.keys(),after);removed=records(before.keys()-after.keys(),before)
    for label,rows in [('added',added),('removed',removed)]:
        (out/(label+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    assert all(hashlib.sha256((root/path).read_bytes()).hexdigest()==value for path,value in manifest.items())
    result={'source_revision':PIN,'source_unchanged':True,'syntax_extraction_identical':True,'files':len(facts),'source_manifest':manifest,
            'parsed_java_files':sum(f.get('language')=='java' for f in facts),
            'partial_java_files':sum(f.get('language')=='java' and f.get('partial',False) for f in facts),
            'analyzer_hashes':{name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in [('before',old),('after',new)]},
            'analyzer_fingerprint':status['analyzer_fingerprint'],
            'before_calls':len(before),'after_calls':len(after),'added':len(added),'removed':len(removed),
            'removed_reasons':dict(Counter(r['current_reference'].get('reason','missing') for r in removed)),
            'added_target_kinds':dict(Counter(r['target']['kind'] for r in added)),
            'elapsed_seconds':time.perf_counter()-started,
            'scope':'Same fresh syntax facts under candidate grammar; edge changes are not precision/recall proof.'}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in {'source_manifest','analyzer_fingerprint'}},indent=2))

if __name__=='__main__':main()
