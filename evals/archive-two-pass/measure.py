"""Fixed-order source-free query timings using runtimes differing only in archive.py."""
import argparse
import gzip
import hashlib
import json
import lzma
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('output',type=Path);p.add_argument('--worker',type=Path);a=p.parse_args()
if a.worker:
 sys.path.insert(0,str(a.worker))
 from columbus.archive import callers_archive
 timings=[];packets=[]
 for _ in range(3):
  start=time.perf_counter();packet=callers_archive(a.archive,'django.utils.encoding.force_bytes',path='django/*',budget_bytes=64000,output_format='text');timings.append(time.perf_counter()-start);packets.append(packet)
 assert all(p==packets[0] for p in packets)
 value={'seconds':timings,'median_seconds':statistics.median(timings),'packet_sha256':hashlib.sha256(json.dumps(packet,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'edges':len(packet['edges']),'next_offset':packet['next_offset']}
 a.output.write_text(json.dumps(value,indent=2)+'\n');sys.exit()
root=Path(__file__).resolve().parents[2];source=root/'skills/columbus/scripts';results={};manifests={};original=hashlib.sha256(a.archive.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix='columbus two pass ') as directory:
 temp=Path(directory)
 for name in ('before','after'):
  runtime=temp/name;shutil.copytree(source/'columbus',runtime/'columbus',ignore=shutil.ignore_patterns('__pycache__'))
  if name=='before':(runtime/'columbus/archive.py').write_bytes(subprocess.check_output(['git','show','1ad68b9:skills/columbus/scripts/columbus/archive.py'],cwd=root))
  manifests[name]={str(p.relative_to(runtime)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(runtime.rglob('*.py'))}
 assert {p for p in manifests['before'] if manifests['before'][p]!=manifests['after'][p]}=={'columbus/archive.py'}
 gzip_path=temp/'graph.gz'
 with lzma.open(a.archive,'rb') as src,gzip.open(gzip_path,'wb') as dest:shutil.copyfileobj(src,dest)
 for codec,artifact in [('gzip',gzip_path),('xz',a.archive)]:
  results[codec]={}
  for name in ('before','after'):
   output=temp/(codec+'-'+name+'.json')
   subprocess.run([sys.executable,str(Path(__file__).resolve()),str(artifact),str(output),'--worker',str(temp/name)],check=True)
   results[codec][name]=json.loads(output.read_text())
  assert results[codec]['before']['packet_sha256']==results[codec]['after']['packet_sha256']
 assert len({r['packet_sha256'] for pair in results.values() for r in pair.values()})==1
assert hashlib.sha256(a.archive.read_bytes()).hexdigest()==original
value={'archive_sha256':original,'runtimes':manifests,'results':results,'all_packets_equal':True,'archive_unchanged':True,'scope':'One full Django target, three samples per condition, fixed gzip then XZ and before then after order; unflushed OS caches. No model or isolated causal timing claim.'}
a.output.write_text(json.dumps(value,indent=2)+'\n');print(results)
