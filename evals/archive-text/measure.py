"""Diagnostic rendering comparison on a retained artifact; no model calls."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from columbus.archive import neighbors_archive
from columbus.presentation import render

p=argparse.ArgumentParser();p.add_argument('artifact',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
before=hashlib.sha256(a.artifact.read_bytes()).hexdigest()
target='django/utils/text.py::capfirst:function'
result={'archive_sha256':before,'target':target,'model_trial':False,'formats':{}}
packets={}
for fmt in ['json','text']:
    started=time.monotonic();offset=0;edges=[];pages=[]
    while offset is not None:
        packet=neighbors_archive(a.artifact,target,'in',['calls'],budget_bytes=6000,offset=offset,output_format=fmt)
        output=render(packet,fmt,'archive-neighbors')+('\n' if fmt=='json' else '')
        assert len(output.encode())<=6000
        pages.append({'offset':offset,'edges':len(packet['edges']),'bytes':len(output.encode()),'next_offset':packet['next_offset']})
        edges.extend(packet['edges']);offset=packet['next_offset']
    packets[fmt]=edges
    result['formats'][fmt]={'pages':pages,'total_bytes':sum(p['bytes'] for p in pages),'elapsed_seconds':round(time.monotonic()-started,4)}
assert packets['json']==packets['text']
assert hashlib.sha256(a.artifact.read_bytes()).hexdigest()==before
result.update(edge_parity=True,edges=len(packets['json']),archive_unchanged=True,timing_limitation='One fixed-order warm-cache diagnostic, not a latency benchmark or token measurement.')
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
