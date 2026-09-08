"""Check the first complete archive-callers page chain in actual model tool output."""
import argparse
import hashlib
import json
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('trial',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
oracle=json.loads(Path(__file__).with_name('oracle.json').read_text())
expected=sorted((c['path'],c['qualname'],c['line']) for c in oracle['targets']['force_bytes']['calls'])
text=(a.trial/'events.jsonl').read_text();events=text.splitlines()
if not text.endswith('\n'):events=events[:-1]
chain=[];sites=[];offset=0
for line in events:
 event=json.loads(line);item=event.get('item',{})
 if event.get('type')!='item.completed' or item.get('type')!='command_execution' or ' archive-callers ' not in item.get('command',''):continue
 output=item['aggregated_output'];files={};nodes={};edges=[];metadata=None;section=None
 for row in output.splitlines():
  if row.startswith('metadata '):metadata=json.loads(row[9:])
  elif row.startswith('files ['):section='files'
  elif row.startswith('nodes ['):section='nodes'
  elif row.startswith('edges ['):section='edges'
  elif row.startswith('call_context:'):break
  elif row.startswith('['):
   value=json.loads(row)
   if section=='files':files[value[0]]=value[1:]
   elif section=='nodes':nodes[value[0]]=value[2]
   elif section=='edges':edges.append(value)
 assert metadata and metadata['symbol_id']=='django/utils/encoding.py::force_bytes:function'
 assert metadata['offset']==offset and metadata['matched_edges']==46
 assert metadata['context_lines']==12
 assert len(output.encode())<=30000
 for source,target,file,edge in edges:
  assert nodes[target]['id']==metadata['symbol_id'] and edge['kind']=='calls'
  sites.append((files[file][0],nodes[source]['id'].split('::',1)[1].rsplit(':',1)[0],edge['line']))
 chain.append({'command':item['command'],'offset':offset,'next_offset':metadata['next_offset'],'edges':len(edges),'bytes':len(output.encode()),'output_sha256':hashlib.sha256(output.encode()).hexdigest()})
 offset=metadata['next_offset']
 if offset is None:break
assert chain and offset is None and sorted(sites)==expected
result={'scope':'First complete actual tool-output page chain only; not final model answer or usage.', 'pages':chain,'call_sites':len(sites),'owners':len({s[:2] for s in sites}),'oracle_parity':True,'source_context_radius':12,'byte_budget_per_page':30000,'token_savings_claimed':False}
a.output.write_text(json.dumps(result,indent=2)+'\n');print({'pages':len(chain),'sites':len(sites),'owners':result['owners'],'bytes':sum(x['bytes'] for x in chain)})
