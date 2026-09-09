"""Compare complete saved Spring facts and every edge, not just counts."""
import argparse
from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import zlib

p = argparse.ArgumentParser()
p.add_argument('repo', type=Path)
p.add_argument('before', type=Path)
p.add_argument('after', type=Path)
p.add_argument('output', type=Path)
p.add_argument('--before-runtime', type=Path, required=True)
a = p.parse_args()
current = Path(__file__).resolve().parents[2] / 'skills/columbus/scripts'
runtime_hashes = {'before': {}, 'after': {}}
for file in sorted(a.before_runtime.rglob('*.py')):
    relative = file.relative_to(a.before_runtime)
    for name, source in [('before', file), ('after', current / relative)]:
        runtime_hashes[name][str(relative)] = hashlib.sha256(source.read_bytes()).hexdigest()
assert [p for p in runtime_hashes['before'] if runtime_hashes['before'][p] != runtime_hashes['after'][p]] == ['columbus/jvm.py']
records = []
for db in [a.before, a.after]:
    with closing(sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True)) as c:
        hashes = dict(c.execute('SELECT path,hash FROM files'))
        facts = {p: json.loads(zlib.decompress(data)) for p, data in c.execute('SELECT path,parsed FROM files')}
        edges = set(c.execute('SELECT source,target,kind,path,line,confidence,evidence FROM edges'))
        symbols = set(c.execute('SELECT * FROM symbols'))
        fts = set(c.execute('SELECT id,name,path,body FROM search_documents'))
    assert all(hashlib.sha256((a.repo / path).read_bytes()).hexdigest() == h for path, h in hashes.items())
    records.append((hashes, facts, edges, symbols, fts))
old, new = records
assert old[0] == new[0]
assert old[3:] == new[3:]
changes = []
for path in old[1]:
    before, after = old[1][path], copy.deepcopy(new[1][path])
    assert len(before['references']) == len(after['references'])
    for b, n in zip(before['references'], after['references']):
        if b != n:
            assert b['kind'] == 'calls' and not b['resolved']
            assert b['reason'] == 'inherited candidate set and argument applicability required'
            changes.append({'before': b, 'after': copy.deepcopy(n)})
            for key in ['resolved', 'target', 'reason', 'confidence']:
                n.pop(key, None)
                if key in b:
                    n[key] = b[key]
    assert before == after, path
added = new[2] - old[2]
assert not old[2] - new[2]
assert all(row[2] == 'calls' for row in added)
resolved = [change['after'] for change in changes if change['after']['resolved']]
reference_rows = {tuple(r[k] for k in ['source', 'target', 'kind', 'path', 'line', 'confidence', 'evidence']) for r in resolved}
# The persisted edge schema collapses repeated same-source/target/kind/line
# references. Each retained edge must still match a complete source reference.
assert added <= reference_rows
assert {row[:5] for row in added} == {row[:5] for row in reference_rows}
result = {
    'runtime_sha256': runtime_hashes,
    'source_files': len(old[0]),
    'source_manifest_sha256': hashlib.sha256(json.dumps(old[0], sort_keys=True).encode()).hexdigest(),
    'databases_sha256': [hashlib.sha256(db.read_bytes()).hexdigest() for db in [a.before, a.after]],
    'symbols_and_logical_fts_equal': True,
    'all_other_parsed_fields_equal': True,
    'removed_edges': 0,
    'added_calls': len(added),
    'newly_resolved_references': len(resolved),
    'still_unresolved_with_more_specific_reason': len(changes) - len(resolved),
    'changes': changes,
    'all_added_calls_independently_reviewed': False,
    'compiler_accuracy_claimed_for_full_spring': False,
}
a.output.write_text(json.dumps(result, indent=2) + '\n')
print({k: v for k, v in result.items() if k not in {'changes', 'runtime_sha256'}})
