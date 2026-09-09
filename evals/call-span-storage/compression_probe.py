"""Compare stdlib codecs on identical complete JSONL bytes, streaming throughout."""
import argparse
import gzip
import hashlib
import lzma
from pathlib import Path
import json
import tempfile
import time
from columbus.archive import archive
from columbus.index import RepositoryIndex

p=argparse.ArgumentParser();p.add_argument('database',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
def verify(path,opener):
    digest=hashlib.sha256();size=0;started=time.perf_counter()
    with opener(path,'rb') as stream:
        while chunk:=stream.read(1024*1024):digest.update(chunk);size+=len(chunk)
    return {'decoded_sha256':digest.hexdigest(),'decoded_bytes':size,'read_hash_seconds':time.perf_counter()-started}
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);original=root/'graph.gz'
    started=time.perf_counter();receipt=archive(RepositoryIndex(a.database),original)
    export_seconds=time.perf_counter()-started
    reference=verify(original,gzip.open)
    results={'gzip':{'bytes':receipt['bytes'],**reference},'export_seconds':export_seconds}
    for preset in [3,6]:
        path=root/f'graph-{preset}.xz';started=time.perf_counter()
        with gzip.open(original,'rb') as source,lzma.open(path,'wb',preset=preset) as output:
            while chunk:=source.read(1024*1024):output.write(chunk)
        elapsed=time.perf_counter()-started
        checked=verify(path,lzma.open)
        assert checked['decoded_sha256']==reference['decoded_sha256'] and checked['decoded_bytes']==reference['decoded_bytes']
        results[f'xz-{preset}']={'bytes':path.stat().st_size,'transcode_seconds':elapsed,**checked}
    results['scope']='Single host, warm/unflushed caches, fixed order; transcode includes gzip decoding; read timing includes SHA-256. Production format unchanged.'
    a.output.write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
