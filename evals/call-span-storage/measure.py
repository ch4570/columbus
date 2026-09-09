"""Compare retained Django snapshots without rewriting either database."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
from columbus.archive import archive
from columbus.index import RepositoryIndex

p=argparse.ArgumentParser();p.add_argument('before',type=Path);p.add_argument('after',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
results={}
with tempfile.TemporaryDirectory() as tmp:
    for label,db in [('before',a.before),('after',a.after)]:
        artifact=Path(tmp)/(label+'.jsonl.gz');receipt=archive(RepositoryIndex(db),artifact)
        sizes={};counts={};manifest={}
        with gzip.open(artifact,'rb') as stream:
            for line in stream:
                row=json.loads(line);kind=row['record']
                sizes[kind]=sizes.get(kind,0)+len(line);counts[kind]=counts.get(kind,0)+1
                if kind=='file':manifest[row['data']['path']]=row['data']['hash']
        results[label]={'archive_bytes':receipt['bytes'],'database_bytes':db.stat().st_size,
                        'archive_sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),
                        'uncompressed_bytes_by_record':sizes,'records':counts,
                        'file_manifest_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()}
assert results['before']['file_manifest_sha256']==results['after']['file_manifest_sha256']
results['same_indexed_source_hashes']=True
results['archive_change_percent']=(results['after']['archive_bytes']/results['before']['archive_bytes']-1)*100
results['scope']='Storage cost of corrected Python call evidence on matching retained snapshots; no speed or model token claim.'
a.output.write_text(json.dumps(results,indent=2)+'\n');print(results['archive_change_percent'])
