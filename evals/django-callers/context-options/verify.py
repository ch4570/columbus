"""Reproduce bounded caller context checks without launching a model trial."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

p=argparse.ArgumentParser()
p.add_argument('repository',type=Path)
p.add_argument('output',type=Path)
a=p.parse_args()
here=Path(__file__).resolve().parent
root=here.parents[2]
wrapper=root/'skills/columbus/scripts/columbus.py'
oracle=json.loads((here.parent/'oracle.json').read_text())
for path,digest in oracle['production_source_manifest'].items():
    assert hashlib.sha256((a.repository/path).read_bytes()).hexdigest()==digest,path

def query(*args):
    return subprocess.check_output([sys.executable,str(wrapper),'callers','iri_to_uri',
                                   '--repo',str(a.repository),'--snapshot',*args])

# Exercise the public CLI used in the skill, not just its Python method.
args=['--path','django/*','--context-lines','30','--budget-bytes','24000']
packet=json.loads(query(*args))
text=query(*args,'--format','text')
expected=oracle['targets']['iri_to_uri']['calls']
assert packet['matched_callers']==12 and len(packet['items'])==12 and not packet['truncated']
assert {(x['path'],x['qualname']) for x in packet['items']}=={(x['path'],x['qualname']) for x in expected}
for call in expected:
    item=next(x for x in packet['items'] if x['path']==call['path'] and x['qualname']==call['qualname'])
    assert item['start_line']<=call['line']<=item['end_line']
    lines=(a.repository/item['path']).read_text().splitlines()
    assert item['source']=='\n'.join(lines[item['start_line']-1:item['end_line']])
small=query('--path','django/*','--context-lines','30','--budget-bytes','2048','--format','text')
assert len(small)<=2048 and b'truncated=true' in small
assert len(text)<=24000 and b'path_filter=django/* context_lines=30' in text
result={'production_hashes_verified':len(oracle['production_source_manifest']),
        'production_callers':12,'all_15_call_sites_in_excerpts':True,'excerpt_source_equal':True,
        'text_bytes':len(text),'text_sha256':hashlib.sha256(text).hexdigest(),
        'budget_bytes':24000,'context_lines':30,'path':'django/*','small_budget_bytes':2048,
        'small_budget_truncated':True,'public_cli_verified':True,'semantic_complete':False,'model_trial':False}
a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
