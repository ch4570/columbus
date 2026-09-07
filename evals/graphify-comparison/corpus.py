"""Graphify's code-only extraction/build census; run in its isolated environment."""
import argparse
from collections import Counter
import json
from pathlib import Path
import time
from graphify.extract import extract
from graphify.build import build_from_json

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--repo',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
root=a.repo.resolve();paths=sorted([*root.rglob('*.java'),*root.rglob('*.kt')])
t=time.perf_counter()
r=extract(paths,cache_root=a.output/'cache',root=root,parallel=False)
elapsed=time.perf_counter()-t
raw=json.dumps(r).encode();(a.output/'extraction.json').write_bytes(raw)
ids={n['id'] for n in r['nodes']}
summary=dict(seconds=elapsed,files=len(paths),nodes=len(r['nodes']),edges=len(r['edges']),
             relations=dict(Counter(e.get('relation') for e in r['edges'])),
             dangling=sum(e['source'] not in ids or e['target'] not in ids for e in r['edges']),
             failed=r.get('failed_sources'),graph_bytes=len(raw))
g=build_from_json(r,directed=True,root=str(root))
summary['built']=dict(nodes=g.number_of_nodes(),edges=g.number_of_edges(),directed=g.is_directed(),
                      multigraph=g.is_multigraph(),relations=dict(Counter(e.get('relation') for _,_,e in g.edges(data=True))))
(a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
