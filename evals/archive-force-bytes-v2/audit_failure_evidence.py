"""Locate predeclared semantic evidence in verified ranges and complete tool outputs."""
import argparse
import hashlib
import json
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('observation',type=Path);p.add_argument('reads',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
reads=json.loads(a.reads.read_text());manifest=json.loads((a.observation/'manifest.json').read_text())['source_manifest']
checks=[('uid_override','django/contrib/auth/forms.py',497,497),('delivery_catch','django/contrib/auth/forms.py',433,438),('oracle_preprocessing','django/db/backends/oracle/base.py',423,438),('request_override','django/test/client.py',667,667),('multipart_none_rejection','django/test/client.py',299,303),('vsi_delete_flag','django/contrib/gis/gdal/raster/const.py',105,105)]
result={'scope':'Verified physical source delivery and exact flag-definition occurrence; no claim about model attention or equivalent unrecognized evidence.','conditions':{}}
for condition,record in reads['conditions'].items():
 trial=a.observation/'trials'/f'archive-force-bytes-v2-{condition}-1';raw=(trial/'events.jsonl').read_bytes();assert hashlib.sha256(raw).hexdigest()==record['events_sha256']
 commands=[e['item'] for e in map(json.loads,raw.splitlines()) if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='command_execution']
 rows=[]
 for label,path,start,end in checks:
  data=(a.observation/'repository'/path).read_bytes();assert hashlib.sha256(data).hexdigest()==manifest[path]
  text='\n'.join(data.decode().splitlines()[start-1:end]);covered=set();witness=[]
  for r in record['reads']:
   if r['path']==path and r['start']<=end and r['end']>=start:
    covered.update(range(max(start,r['start']),min(end,r['end'])+1));witness.append(r)
  row={'evidence':label,'path':path,'start_line':start,'end_line':end,'source_sha256':manifest[path],'source':text,'all_lines_in_verified_reads':set(range(start,end+1))<=covered,'read_witnesses':witness}
  if label=='vsi_delete_flag':row['exact_definition_in_any_command_output']=[c['id'] for c in commands if text.strip() in c.get('aggregated_output','')]
  rows.append(row)
 result['conditions'][condition]={'events_sha256':record['events_sha256'],'evidence':rows}
a.output.write_text(json.dumps(result,indent=2)+'\n')
print({c:{r['evidence']:r['all_lines_in_verified_reads'] for r in d['evidence']} for c,d in result['conditions'].items()})
