"""Check frozen archive call multiplicity against the independently reviewed oracle."""
import argparse
import hashlib
import json
import lzma
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('observation', type=Path)
p.add_argument('output', type=Path)
a = p.parse_args()
oracle = json.loads(Path(__file__).with_name('oracle.json').read_text())
manifest = oracle['production_source_manifest']
repo = a.observation / 'repository'
assert set(manifest) == {f.relative_to(repo).as_posix() for f in (repo / 'django').rglob('*.py')}
for name, digest in manifest.items():
    assert hashlib.sha256((repo / name).read_bytes()).hexdigest() == digest, name
nodes, edges = {}, []
target = 'django/utils/http.py::url_has_allowed_host_and_scheme:function'
with lzma.open(a.observation / 'graph.jsonl.xz', 'rt', encoding='utf-8') as stream:
    for line in stream:
        row = json.loads(line)
        data = row['data']
        if row['record'] == 'node':
            nodes[data['id']] = data
        elif row['record'] == 'edge' and data['kind'] == 'calls' and data['target'] == target:
            edges.append(data)
actual = sorted((e['path'], nodes[e['source']]['qualname'], e['line']) for e in edges if e['path'].startswith('django/'))
expected = sorted((e['path'], e['qualname'], e['line']) for e in oracle['targets']['url_has_allowed_host_and_scheme']['calls'])
assert actual == expected, (actual, expected)
result = {'production_files_verified': len(manifest), 'production_call_sites': len(actual),
          'production_callers': len({e[:2] for e in actual}), 'archive_all_call_edges': len(edges),
          'missing': [], 'extra': [], 'multiplicity_preserved': True}
a.output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
