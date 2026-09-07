"""Check existing saved false edges are invalidated by the analyzer upgrade."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
SOURCES={'a/T.java':'package a; public class T { void hit() {} }',
         'b/C.java':'package b; import a.T; class C { void run(T t) { t.hit(); } }'}
CODE='''import json,sys
sys.path.insert(0,sys.argv[1])
from columbus.index import RepositoryIndex
index=RepositoryIndex(sys.argv[3]);status=index.refresh(sys.argv[2],fast=True)
print(json.dumps({'refresh':status['refresh'],'fingerprint':status['analyzer_fingerprint'],'revision':status['revision'],
                  'calls':sum(e['kind']=='calls' for e in index.graph()['edges'])}))
'''
with tempfile.TemporaryDirectory(prefix='columbus package cache ') as temp:
    temp=Path(temp); source=temp/'repo';source.mkdir()
    for relative, text in SOURCES.items():
        p=source/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    current=ROOT/'skills/columbus/scripts'
    old=temp/'old';shutil.copytree(current/'columbus',old/'columbus',ignore=shutil.ignore_patterns('__pycache__'))
    (old/'columbus/jvm.py').write_bytes(subprocess.check_output(['git','show','1b27ecf:skills/columbus/scripts/columbus/jvm.py'],cwd=ROOT))
    rows=[json.loads(subprocess.check_output([sys.executable,'-c',CODE,str(runtime),str(source),str(temp/'index.sqlite')],text=True))
          for runtime in [old,current,current]]
    assert [r['calls'] for r in rows]==[1,0,0]
    assert [r['refresh']['parsed_files'] for r in rows]==[2,2,0]
    assert all((source/k).read_text()==v for k,v in SOURCES.items())
    result={'baseline_commit':'1b27ecf','source_unchanged':True,
            'source_hashes':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in SOURCES.items()},'runs':rows}
    output=ROOT/'evals/jvm-guardrails/results/package-access/cache-upgrade.json'
    output.write_text(json.dumps(result,indent=2)+'\n')
print('Existing false call removed on analyzer change; warm unchanged sync preserves corrected graph.')
