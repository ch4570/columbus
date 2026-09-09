"""Count byte-identical resolved cache blobs after edits, using an isolated source copy."""
import argparse,hashlib,json,shutil,sqlite3,tempfile
from pathlib import Path
from columbus.index import RepositoryIndex
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
def state(index):
 with sqlite3.connect(index.db) as c:return {p:{'source_hash':h,'parse_sha256':hashlib.sha256(v).hexdigest(),'parse_bytes':len(v)} for p,h,v in c.execute('SELECT path,hash,parsed FROM files')}
with tempfile.TemporaryDirectory(prefix='columbus parse reuse ') as directory:
 root=Path(directory)/'source';shutil.copytree(a.source,root,ignore=shutil.ignore_patterns('.git','.columbus','__pycache__'))
 index=RepositoryIndex(Path(directory)/'index.sqlite');index.refresh(root);initial=state(index)
 target=root/'django/utils/encoding.py';original=target.read_bytes();results={}
 cases={'comment':original+b'\n# cache equality probe\n','rename':original.replace(b'def iri_to_uri(iri):',b'def renamed_iri_to_uri(iri):')}
 assert cases['rename']!=original
 try:
  for name,content in cases.items():
   target.write_bytes(content);refresh=index.refresh(root,fast=True);after=state(index)
   assert initial.keys()==after.keys()
   changed=[p for p in initial if initial[p]['parse_sha256']!=after[p]['parse_sha256']]
   results[name]={'refresh':refresh['refresh'],'files':len(initial),'identical_cache_blobs':len(initial)-len(changed),'changed_cache_paths':changed,'changed_cache_bytes_before':sum(initial[p]['parse_bytes'] for p in changed),'all_cache_bytes_before':sum(v['parse_bytes'] for v in initial.values()),'changed_source_paths':[p for p in initial if initial[p]['source_hash']!=after[p]['source_hash']]}
   target.write_bytes(original);index.refresh(root,fast=True);assert state(index)==initial
 finally:target.write_bytes(original)
result={'cases':results,'all_restored_cache_blobs_equal':True,'scope':'Byte-identical compressed resolved parse caches, not just unchanged source; full relinking still ran. Isolated copy, unflushed caches; timings are diagnostic only.'}
a.output.write_text(json.dumps(result,indent=2)+'\n');print({k:{f:v for f,v in d.items() if f!='refresh'} for k,d in results.items()})
