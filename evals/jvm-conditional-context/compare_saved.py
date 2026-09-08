"""Audit completed frozen indexes, retaining every newly extracted context."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import zlib

p=argparse.ArgumentParser();p.add_argument('indexes',type=Path);p.add_argument('repo',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
records={}
for name in ['before','after']:
 with sqlite3.connect(a.indexes/(name+'.sqlite')) as c:
  hashes=dict(c.execute('SELECT path,hash FROM files'))
  facts={p:json.loads(zlib.decompress(d)) for p,d in c.execute('SELECT path,parsed FROM files')}
  edges=sorted(c.execute('SELECT source,target,kind,path,line,confidence,evidence FROM edges').fetchall())
 assert all(hashlib.sha256((a.repo/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
 records[name]=(hashes,facts,edges)
old,new=records['before'],records['after'];assert old[0]==new[0];assert old[1].keys()==new[1].keys();changes=[]
for path,before in old[1].items():
 after=copy.deepcopy(new[1][path]);assert len(before['references'])==len(after['references'])
 for previous,current in zip(before['references'],after['references']):
  if previous.get('expected_type')!=current.get('expected_type'):
   assert previous['expected_type']=='' and current['expected_type']
   changes.append({'path':path,'source':current['source'],'line':current['line'],'evidence':current['evidence'],'before':previous['expected_type'],'after':current['expected_type']})
   current['expected_type']=previous['expected_type']
 assert before==after,path
assert old[2]==new[2]
manifest={}
for name in records:
 manifest[name]={str(p.relative_to(a.indexes/name)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((a.indexes/name).rglob('*.py'))}
assert manifest['before'].keys()==manifest['after'].keys()
assert [k for k in manifest['before'] if manifest['before'][k]!=manifest['after'][k]]==['columbus/jvm.py']
for name,revision in [('before','6594992'),('after','cf635cf')]:
 for relative,digest in manifest[name].items():
  assert hashlib.sha256(subprocess.check_output(['git','show',revision+':skills/columbus/scripts/'+relative])).hexdigest()==digest

result={'before_revision':'6594992e9c0cee1180d08e771b1970d124a5dfb7','after_revision':'cf635cf970f1eab67f3063dc946fd07ec9df9436','source_manifest_sha256':hashlib.sha256(json.dumps(old[0],sort_keys=True,separators=(',',':')).encode()).hexdigest(),'files':len(old[0]),'edges':len(old[2]),'all_edge_tuples_equal':True,'all_other_parsed_fields_equal':True,'runtime_manifests':manifest,'context_changes':changes,'compiler_accuracy_claimed':False}
a.output.write_text(json.dumps(result,indent=2)+'\n');print({'files':len(old[0]),'edges':len(old[2]),'new_contexts':len(changes)})
