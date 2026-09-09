"""Compare complete parse facts and time with the preceding Python adapter."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import time
from columbus.parser import parse_source

root=Path('/tmp/columbus-django-evaluation')
paths=sorted({c['path'] for c in json.loads(Path('evals/django-callers/oracle.json').read_text())['targets']['iri_to_uri']['calls']})
with tempfile.TemporaryDirectory() as directory:
    old=Path(directory)/'before.py';old.write_bytes(subprocess.check_output(['git','show','e2a7c63:skills/columbus/scripts/columbus/parser.py']))
    spec=importlib.util.spec_from_file_location('baseline_parser',old);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    rows=[]
    for path in paths:
        data=(root/path).read_bytes();source=data.decode();timings=[];facts=[]
        for fn in [module.parse_source,parse_source]:
            start=time.perf_counter();facts.append(fn(path,source,path[:-3].replace('/','.')));timings.append(time.perf_counter()-start)
        assert facts[0]==facts[1],path
        rows.append({'path':path,'source_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'before_seconds':timings[0],'after_seconds':timings[1],
                     'facts_equal':True,'facts_sha256':hashlib.sha256(json.dumps(facts[1],sort_keys=True).encode()).hexdigest()})
    print(json.dumps({'baseline_commit':'e2a7c63','rows':rows,'before_total_seconds':sum(r['before_seconds'] for r in rows),'after_total_seconds':sum(r['after_seconds'] for r in rows),
                      'limitations':'Single parse per file; baseline first; unflushed caches/shared host. Not full-index latency.','model_trials':0},indent=2))
