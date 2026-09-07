"""Source-reviewed navigation evidence, independent of graph target resolution."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--repo', type=Path, required=True)
p.add_argument('--db', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
revision = subprocess.check_output(['git','-C',str(a.repo),'rev-parse','HEAD'],text=True).strip()
assert revision == '4c8c6409a27a62ab163d3b6196ad862b7c835440'
base = 'src/main/java/org/springframework/core/io/'
# Reviewed source ranges; no graph-derived expected answer or call target.
ranges = [('DefaultResourceLoader.java',155,184),('DefaultResourceLoader.java',198,200),
          ('DefaultResourceLoader.java',242,267),('DefaultResourceLoader.java',297,302),
          ('ClassPathResource.java',200,216),('UrlResource.java',244,257),
          ('FileUrlResource.java',51,51),('ResourceLoader.java',48,68)]
expected = ['DefaultResourceLoader.getResource','DefaultResourceLoader.getResourceByPath',
            'DefaultResourceLoader.ClassPathAllResource.getInputStream',
            'ClassPathResource.getInputStream','UrlResource.getInputStream']
source = []
for filename,start,end in ranges:
    path = base + filename
    data = (a.repo/path).read_bytes()
    source.append({'path':path,'sha256':hashlib.sha256(data).hexdigest(),'start_line':start,'end_line':end,
                   'text':'\n'.join(data.decode().splitlines()[start-1:end])})
with sqlite3.connect(a.db) as c:
    hashes = dict(c.execute('SELECT path,hash FROM files'))
    assert all(hashes[r['path']]==r['sha256'] for r in source)
    nodes = []
    for suffix in expected:
        rows = c.execute('SELECT id,data FROM symbols WHERE qualname=?',('org.springframework.core.io.'+suffix,)).fetchall()
        assert len(rows)==1, (suffix,len(rows))
        node=json.loads(rows[0][1]);assert not node.get('partial')
        calls=c.execute("SELECT target,line,evidence FROM edges WHERE source=? AND kind='calls'",(rows[0][0],)).fetchall()
        nodes.append({'id':rows[0][0],'start_line':node['start_line'],'end_line':node['end_line'],'stored_calls':calls})
result={'spring_revision':revision,'source_ranges':source,'graph_nodes':nodes,'source_hashes_match_index':True,
        'all_requested_declarations_present':True,'runtime_executed':False,'model_trial_started':False}
a.output.parent.mkdir(parents=True,exist_ok=True)
a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'declarations':len(nodes),'source_ranges':len(source),'stored_call_counts':[len(n['stored_calls']) for n in nodes]}))
