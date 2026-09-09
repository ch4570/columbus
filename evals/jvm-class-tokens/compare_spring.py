"""Compare full indexes using git-frozen runtimes differing only in jvm.py."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import zlib

p=argparse.ArgumentParser();p.add_argument('repo',type=Path);p.add_argument('output',type=Path);p.add_argument('--before',default='9ebf60ec97cfa5eac2d22cb8a8182e75292964f9');p.add_argument('--after',default='98c2eed4909becb6c561a8ede64d6b11577968d6');a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
source_revision=subprocess.check_output(['git','-C',str(a.repo),'rev-parse','HEAD'],text=True).strip()
versions={name:subprocess.check_output(['git','rev-parse',revision+'^{commit}'],text=True).strip() for name,revision in [('before',a.before),('after',a.after)]}
records={};runtimes={}
for name,revision in versions.items():
    runtime=a.output/name;runtime.mkdir();files={}
    paths=subprocess.check_output(['git','ls-tree','-r','--name-only',revision,'skills/columbus/scripts'],text=True).splitlines()
    for path in paths:
        relative=path.removeprefix('skills/columbus/scripts/')
        if relative!='columbus.py' and not (relative.startswith('columbus/') and relative.endswith('.py')):continue
        data=subprocess.check_output(['git','show',revision+':'+path]);dest=runtime/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        files[relative]=hashlib.sha256(data).hexdigest()
    runtimes[name]=files
    database=a.output/(name+'.sqlite')
    status=json.loads(subprocess.check_output([sys.executable,str(runtime/'columbus.py'),'sync','--repo',str(a.repo),'--db',str(database)],text=True))
    with sqlite3.connect(database) as conn:
        hashes=dict(conn.execute('SELECT path,hash FROM files'))
        facts={path:json.loads(zlib.decompress(data) if isinstance(data,bytes) else data) for path,data in conn.execute('SELECT path,parsed FROM files')}
        edges={tuple(row) for row in conn.execute('SELECT source,target,kind,path,line,confidence,evidence FROM edges')}
    assert all(hashlib.sha256((a.repo/path).read_bytes()).hexdigest()==digest for path,digest in hashes.items())
    records[name]=(hashes,facts,edges,status)
assert {p for p in runtimes['before'] if runtimes['before'][p]!=runtimes['after'][p]}=={'columbus/jvm.py'}
old,new=records['before'],records['after'];assert old[0]==new[0]
def syntax(f):
    f=copy.deepcopy(f)
    for ref in f['references']:
        for key in ['argument_facts','resolved','target','reason','confidence','retrieval_candidates']:ref.pop(key,None)
    for entry in f['imports']:
        for key in ['resolved','target','confidence']:entry.pop(key,None)
    return f
assert all(syntax(old[1][path])==syntax(new[1][path]) for path in old[1])
keys=['source','target','kind','path','line','confidence','evidence']
assert subprocess.check_output(['git','-C',str(a.repo),'rev-parse','HEAD'],text=True).strip()==source_revision
result={'source_revision':source_revision,'source_manifest_sha256':hashlib.sha256(json.dumps(old[0],sort_keys=True,separators=(',',':')).encode()).hexdigest(),'revisions':versions,'runtime_changes':['columbus/jvm.py'],'source_files':len(old[0]),'source_hashes_equal':True,
        'base_syntax_equal':True,'before_edges':len(old[2]),'after_edges':len(new[2]),
        'added':[dict(zip(keys,row)) for row in sorted(new[2]-old[2])],
        'removed':[dict(zip(keys,row)) for row in sorted(old[2]-new[2])],
        'runtime_manifests':runtimes,'fingerprints':{k:v[3]['analyzer_fingerprint'] for k,v in records.items()},
        'compiler_accuracy_claimed':False,'model_trial':False}
(a.output/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
print({k:v for k,v in result.items() if k not in {'runtime_manifests','fingerprints','added','removed'}},'added',len(result['added']),'removed',len(result['removed']))
