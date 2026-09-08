"""Verify every exported record category against SQLite, then compare codecs."""
import argparse
import collections
import gzip
import hashlib
from importlib.metadata import version
import json
import lzma
from pathlib import Path
import sqlite3
import tempfile
import time
import zlib
from columbus.archive import archive
from columbus.index import RepositoryIndex

p=argparse.ArgumentParser();p.add_argument('database',type=Path);p.add_argument('repo',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def accumulator():return collections.defaultdict(hashlib.sha256),collections.Counter()
def add(state,kind,data):
 state[0][kind].update((json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode());state[1][kind]+=1
def summary(state):return {k:{'count':state[1][k],'sha256':h.hexdigest()} for k,h in sorted(state[0].items())}
expected=accumulator();source_bytes=0;source_hashes={};db_hash=digest(a.database)
with sqlite3.connect(a.database.resolve().as_uri()+'?mode=ro',uri=True) as conn:
 conn.row_factory=sqlite3.Row
 for row in conn.execute('SELECT path,hash,size,parsed FROM files ORDER BY path'):
  source_hashes[row['path']]=row['hash'];assert digest(a.repo/row['path'])==row['hash']
  source_bytes+=row['size'];add(expected,'file',{k:row[k] for k in ('path','hash','size')})
  parsed=json.loads(zlib.decompress(row['parsed']) if isinstance(row['parsed'],bytes) else row['parsed'])
  for key,scope in sorted(parsed.get('_scopes',{}).items()):add(expected,'scope',{'path':row['path'],'id':key,**scope})
  for item in parsed.get('imports',[]):add(expected,'import',item)
  for item in parsed.get('references',[]):add(expected,'reference',item)
 for row in conn.execute('SELECT data FROM symbols ORDER BY path,id'):add(expected,'node',json.loads(row[0]))
 for row in conn.execute('SELECT * FROM edges ORDER BY source,target,kind,path,line,confidence,evidence'):add(expected,'edge',dict(row))
 metadata={r[0]:json.loads(r[1]) for r in conn.execute('SELECT key,value FROM metadata')}
 for item in metadata.get('diagnostics',[]):add(expected,'diagnostic',item)
results={};streams={};manifests={}
with tempfile.TemporaryDirectory(prefix='columbus archive parity ') as directory:
 for codec,opener in [('gzip',gzip.open),('xz',lzma.open)]:
  target=Path(directory)/codec;started=time.perf_counter();receipt=archive(RepositoryIndex(a.database),target,codec);elapsed=time.perf_counter()-started
  actual=accumulator();stream_hash=hashlib.sha256();uncompressed=0;ending=None
  with opener(target,'rb') as stream:
   for line in stream:
    stream_hash.update(line);uncompressed+=len(line);row=json.loads(line);kind=row['record'];data=row['data']
    assert ending is None
    if kind=='manifest':assert codec not in manifests;manifests[codec]=data
    elif kind=='end':ending=data
    else:add(actual,kind,data)
  assert ending=={plural:actual[1][singular] for singular,plural in [('file','files'),('node','nodes'),('scope','scopes'),('edge','edges'),('reference','references'),('import','imports'),('diagnostic','diagnostics')]}
  assert summary(actual)==summary(expected)
  streams[codec]=stream_hash.hexdigest()
  results[codec]={'bytes':receipt['bytes'],'sha256':receipt['sha256'],'export_seconds':elapsed,'uncompressed_bytes':uncompressed,'uncompressed_sha256':streams[codec],'all_record_categories_equal_sqlite':True}
assert streams['gzip']==streams['xz'] and manifests['gzip']==manifests['xz']
assert digest(a.database)==db_hash
assert all(digest(a.repo/path)==h for path,h in source_hashes.items())
result={'database_bytes':a.database.stat().st_size,'database_sha256':db_hash,'indexed_source_bytes':source_bytes,'source_files':len(source_hashes),'source_manifest_sha256':hashlib.sha256(json.dumps(source_hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'parser_versions':{n:version(n) for n in ('tree-sitter','tree-sitter-java','tree-sitter-kotlin')},'archive_manifest':manifests['xz'],'categories':summary(expected),'codecs':results,'database_and_source_unchanged':True,'all_decompressed_bytes_equal':True,'scope':'Full exported graph facts; excludes SQLite FTS/source bodies and does not prove compiler accuracy or model savings. Fixed codec order, unflushed caches, single timing observation.'}
a.output.write_text(json.dumps(result,indent=2)+'\n');print({k:result[k] for k in ('source_files','indexed_source_bytes','database_bytes','codecs')})
