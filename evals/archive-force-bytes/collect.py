"""Collect completed, unrepeated trial evidence without launching model calls."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

p=argparse.ArgumentParser();p.add_argument('observation',type=Path);a=p.parse_args()
here=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('observe',here.parent/'exploration/observe.py')
o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o)
manifest=json.loads((a.observation/'manifest.json').read_text())
engine=json.loads((a.observation/'engine.json').read_text())
pre=json.loads((here/'input-hashes.json').read_text())
assert o.manifest(a.observation/'repository')==manifest['source_manifest']
assert o.manifest(a.observation/'runtime')==engine['files']
for name,digest in pre.items():
    assert hashlib.sha256((here.parents[1]/name).read_bytes()).hexdigest()==digest, name
gate=o.archive_gate(a.observation,engine)
results={}
raw=here.parents[1]/'.omx/observations/archive-force-bytes'
raw.mkdir(parents=True,exist_ok=True)
for condition in ['baseline','columbus']:
    trial=a.observation/'trials'/f'archive-force-bytes-{condition}-1'
    result=json.loads((trial/'result.json').read_text())
    assert result['source_unchanged']
    assert hashlib.sha256((trial/'events.jsonl').read_bytes()).hexdigest()==result['events_sha256']
    results[condition]=result
    shutil.copytree(trial,raw/trial.name,dirs_exist_ok=True)
(here/'results.json').write_text(json.dumps(results,indent=2)+'\n')
(here/'post-run.json').write_text(json.dumps({'source_manifest_equal':True,'runtime_manifest_equal':True,'archive_postflight':gate,'harness_schema_case_review_hashes_equal':True,'both_trials_terminal':True,'semantic_review_pending':True},indent=2)+'\n')
print({condition:{k:r[k] for k in ['elapsed_seconds','return_code','timed_out','quality']} for condition,r in results.items()})
