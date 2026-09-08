"""Validate frozen inputs and citation controls without running a model."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('trial', type=Path)
p.add_argument('output', type=Path)
a = p.parse_args()
here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('observe', here.parent / 'exploration/observe_saved_callers.py')
o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(o)
m = json.loads((a.trial / 'manifest.json').read_text())
e = json.loads((a.trial / 'engine.json').read_text())
assert o.manifest(a.trial / 'repository') == m['source_manifest']
assert o.manifest(a.trial / 'runtime') == e['files']
case = o.case_catalog(a.trial, m)['cases'][0]
findings = []
for expected in case['findings']:
    lines = (a.trial / 'repository' / expected['path']).read_text().splitlines()
    matches = [n for n, line in enumerate(lines, 1) if expected['marker'] in line]
    assert len(matches) == 1, expected['id']
    n = matches[0]
    findings.append(dict(id=expected['id'], path=expected['path'], start_line=n,
                         end_line=n, quote=lines[n-1], explanation='Citation control only.'))
assert o.grade({'findings': findings}, case, a.trial / 'repository')['passed']
for i in range(len(findings)):
    bad = copy.deepcopy(findings)
    bad[i].update(start_line=1, end_line=1, quote='not the source')
    assert not o.grade({'findings': bad}, case, a.trial / 'repository')['passed']
    assert not o.grade({'findings': findings[:i] + findings[i+1:]}, case, a.trial / 'repository')['passed']
result = {'source_manifest_equal': True, 'runtime_manifest_equal': True,
          'positive_citation_control': True, 'negative_citation_controls': len(findings),
          'missing_finding_controls': len(findings), 'archive': o.archive_gate(a.trial, e),
          'model_started': any((a.trial / 'trials').glob('*/process.json')),
          'semantic_review_pending': True}
a.output.write_text(json.dumps(result, indent=2) + '\n')
print({k: v for k, v in result.items() if k != 'archive'})
