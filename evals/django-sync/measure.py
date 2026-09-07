"""Measure current Django sync work, preserving original source and model inputs."""
import argparse
import cProfile
import hashlib
import json
from pathlib import Path
import pstats
import shutil
import statistics
import tempfile
import time
from columbus.index import RepositoryIndex

p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
with tempfile.TemporaryDirectory(prefix='columbus-django-sync-') as directory:
    root=Path(directory)/'source'
    shutil.copytree(a.source,root,ignore=shutil.ignore_patterns('.git','.columbus','__pycache__'))
    index=RepositoryIndex(Path(directory)/'index.sqlite')
    def run(fast):
        start=time.perf_counter();r=index.refresh(root,fast=fast)
        return {'seconds':time.perf_counter()-start,'refresh':r['refresh'],
                'probe_files':r['inventory']['probe_files'],'probe_bytes':r['inventory']['probe_bytes'],
                'files':r['files'],'symbols':r['symbols'],'edges':r['edges']}
    cold=run(False)
    warm=[run(True) for _ in range(3)]
    profile=cProfile.Profile();profile.enable();profiled=run(True);profile.disable()
    stats=pstats.Stats(profile)
    top=[]
    for (filename,line,name),(cc,nc,tt,ct,callers) in sorted(stats.stats.items(),key=lambda x:x[1][3],reverse=True)[:20]:
        top.append({'file':Path(filename).name,'line':line,'name':name,'calls':nc,'own_seconds':tt,'cumulative_seconds':ct})
    target=root/'django/utils/encoding.py';original=target.read_bytes()
    before=index.search('iri_to_uri')
    target.write_bytes(original+b'\n# sync measurement\n')
    edited=run(True)
    after=index.search('iri_to_uri')
    assert [x['id'] for x in before['hits']]==[x['id'] for x in after['hits']]
    target.write_bytes(original);restored=run(True)
    assert cold['symbols']==edited['symbols']==restored['symbols']
    assert cold['edges']==edited['edges']==restored['edges']
    result={'cold':cold,'warm':warm,'warm_median_seconds':statistics.median(x['seconds'] for x in warm),
            'one_file_edit':edited,'restoration':restored,'database_bytes':index.db.stat().st_size,
            'profiled_warm':profiled,'profile_top_cumulative':top,
            'limited_search_ids_equal':True,'graph_counts_equal':True,
            'os_caches':'Not flushed; same host, sequential observations. Profile timing excluded from median.',
            'scope':'Current implementation diagnosis, not a controlled before/after or full graph parity proof.'}
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['warm_median_seconds','database_bytes','scope']},indent=2))
