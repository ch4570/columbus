"""Validate frozen inputs and citation-gate controls before either model trial."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('observation',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
spec=importlib.util.spec_from_file_location('observe',Path(__file__).parents[1]/'exploration/observe.py')
o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o)
m=json.loads((a.observation/'manifest.json').read_text());e=json.loads((a.observation/'engine.json').read_text())
assert o.manifest(a.observation/'repository')==m['source_manifest']
assert o.manifest(a.observation/'runtime')==e['files']
case=o.case_catalog(a.observation,m)['cases'][0]
findings=[]
for f in case['findings']:
    line=f['call_lines'][0]
    text=(a.observation/'repository'/f['path']).read_text().splitlines()[line-1]
    assert f['marker'] in text, f['id']
    findings.append({'id':f['id'],'path':f['path'],'start_line':line,'end_line':line,'quote':text.strip(),
                     'explanation':'Citation gate control only; not a semantic answer.'})
assert o.grade({'findings':findings},case,a.observation/'repository')['passed']
for i in range(len(findings)):
    altered=copy.deepcopy(findings);altered[i]['start_line']=1;altered[i]['end_line']=1;altered[i]['quote']='not source'
    assert not o.grade({'findings':altered},case,a.observation/'repository')['passed']
result={'source_manifest_equal':True,'runtime_manifest_equal':True,'positive_citation_control':True,
        'negative_citation_controls':len(findings),'index':o.live_index_preflight(a.observation,e),
        'semantic_grading':'Manual review against all PLAN.md criteria remains mandatory for both answers.',
        'model_trial_started':any((a.observation/'trials').glob('*/process.json'))}
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
