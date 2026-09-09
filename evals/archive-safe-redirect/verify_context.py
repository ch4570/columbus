"""Verify saved-graph context against frozen source and the independent call oracle."""
import argparse
import hashlib
import json
from pathlib import Path
from columbus.archive import neighbors_archive
from columbus.presentation import render
from columbus.languages import code_lines, decode_source

p=argparse.ArgumentParser();p.add_argument('observation',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
repo=a.observation/'repository';artifact=a.observation/'graph.jsonl.xz'
before=hashlib.sha256(artifact.read_bytes()).hexdigest();offset=0;pages=[];sites=[];sources=set()
while offset is not None:
    packet=neighbors_archive(artifact,'django/utils/http.py::url_has_allowed_host_and_scheme:function','in',['calls'],budget_bytes=12000,offset=offset,output_format='text',repo=repo,context_lines=20,path="django/*")
    rendered=render(packet,'text','archive-neighbors');assert len(rendered.encode())<=12000
    pages.append({'offset':offset,'edges':len(packet['edges']),'contexts':len(packet['call_context']),'bytes':len(rendered.encode()),'next_offset':packet['next_offset']})
    actual=[]
    for c in packet['call_context']:
        data=(repo/c['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==c['source_hash']
        lines=code_lines(decode_source(c['path'],data,language='python'),'python')
        assert c['source']=='\n'.join(lines[c['start_line']-1:c['end_line']])
        sources.add(c['path'])
        actual.extend((c['source_id'],n) for n in c['call_lines'])
    assert sorted(actual)==sorted((e['source'],e['line']) for e in packet['edges'])
    sites.extend((e['path'],e['source'].split('::',1)[1].rsplit(':',1)[0],e['line']) for e in packet['edges'] if e['path'].startswith('django/'))
    offset=packet['next_offset']
oracle=json.loads(Path(__file__).parents[1].joinpath('archive-safe-redirect/oracle.json').read_text())
expected=sorted((c['path'],c['qualname'],c['line']) for c in oracle['targets']['url_has_allowed_host_and_scheme']['calls'])
assert sorted(sites)==expected
assert not (repo/'.columbus').exists()
assert hashlib.sha256(artifact.read_bytes()).hexdigest()==before
result={'archive_sha256':before,'pages':pages,'total_bytes':sum(p['bytes'] for p in pages),'source_files_checked':len(sources),'production_call_sites':len(sites),'production_callers':len({x[:2] for x in sites}),'exact_excerpt_parity':True,'oracle_parity':True,'archive_unchanged':True,'consumer_index_absent':True,'path_filter':'django/*','model_trial':False,'token_savings_claimed':False}
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
