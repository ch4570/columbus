"""Compare public source-free CLI pages on full Django gzip/XZ archives."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from columbus.archive import archive
from columbus.index import RepositoryIndex

p=argparse.ArgumentParser();p.add_argument('database',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
wrapper=Path(__file__).resolve().parents[2]/'skills/columbus/scripts/columbus.py'
results={};responses={}
with tempfile.TemporaryDirectory() as temporary:
    consumer=Path(temporary)
    for codec in ['gzip','xz']:
        artifact=consumer/f'graph.{codec}'
        receipt=archive(RepositoryIndex(a.database),artifact,compression=codec)
        before=hashlib.sha256(artifact.read_bytes()).hexdigest()
        def query(*args):
            raw=subprocess.check_output([sys.executable,str(wrapper),*args,'--repo',str(consumer),'--input',str(artifact)],cwd=consumer)
            return json.loads(raw)
        started=time.perf_counter()
        found=query('archive-search','conditional_escape','--budget-bytes','6000')
        target=next(x['id'] for x in found['items'] if x['path']=='django/utils/html.py' and x['name']=='conditional_escape')
        pages=[];offset=0
        while True:
            page=query('archive-neighbors',target,'--direction','in','--kinds','calls','--budget-bytes','6000','--offset',str(offset))
            pages.append(page)
            if page['next_offset'] is None:break
            assert page['next_offset']>offset
            offset=page['next_offset']
        elapsed=time.perf_counter()-started
        assert before==hashlib.sha256(artifact.read_bytes()).hexdigest()
        assert not (consumer/'.columbus').exists()
        responses[codec]={'search':found,'pages':pages}
        results[codec]={'bytes':receipt['bytes'],'sha256':before,'cli_query_seconds':elapsed,'pages':len(pages),'edges':sum(len(x['edges']) for x in pages)}
    assert responses['gzip']==responses['xz']
    assert results['xz']['edges']==17
    assert sorted(x.name for x in consumer.iterdir())==['graph.gzip','graph.xz']
results.update(all_query_packets_equal=True,source_free_consumer_unchanged=True,
               scope='Single full-Django stored target, includes same-line calls; fixed order, unflushed caches. No token result.')
a.output.write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
