"""Compare reviewed direct-call sites with graph edges on a frozen package.

This oracle is deliberately limited to one module-level function and two
explicit relative imports, without aliases, rebinding or dynamic attributes.
It does not call Columbus parsing or resolution to construct expected sites.
"""
import ast
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

root, db, output = map(Path, sys.argv[1:])
base = 'skills/columbus/scripts/columbus/'
reviewed = {
    'index.py': {'encode_parse', 'byte_size', 'RepositoryIndex.refresh', 'RepositoryIndex.neighbors'},
    'archive.py': {'archive.emit', '_search_archive'},
    'cli.py': {'main'},
}
expected = set()
files = {}
for path in sorted(root.rglob('*.py')):
    relative = path.relative_to(root).as_posix()
    raw = path.read_bytes()
    files[relative] = hashlib.sha256(raw).hexdigest()
    tree = ast.parse(raw)
    owners = []
    sites = []
    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            owners.append(node.name)
            self.generic_visit(node)
            owners.pop()
        visit_AsyncFunctionDef = visit_FunctionDef
        visit_ClassDef = visit_FunctionDef
        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id == 'compact':
                sites.append(('.'.join(owners), node.lineno))
            self.generic_visit(node)
    Visitor().visit(tree)
    if not sites:
        continue
    assert path.name in reviewed and relative == base + path.name, relative
    assert {owner for owner, _ in sites} == reviewed[path.name], sites
    if path.name != 'index.py':
        assert any(isinstance(n, ast.ImportFrom) and n.level == 1 and n.module == 'index'
                   and any(a.name == 'compact' and a.asname is None for a in n.names)
                   for n in tree.body)
    for owner, line in sites:
        expected.add((relative, owner, line))
pinned = json.loads((Path(__file__).resolve().parents[1] / 'exploration/results/relational-pilot/preparation.json').read_text())
assert files == pinned['source_manifest'], 'Source differs from frozen c67b20a fixture'
with closing(sqlite3.connect(db)) as conn:
    metadata = {key: json.loads(value) for key, value in conn.execute('SELECT key,value FROM metadata')}
    symbols = {r[0]: json.loads(r[1]) for r in conn.execute('SELECT id,data FROM symbols')}
    targets = [s['id'] for s in symbols.values() if s['path'] == base + 'index.py' and s['qualname'] == 'compact']
    assert len(targets) == 1
    actual = {(path, symbols[source]['qualname'], line) for source, path, line in
              conn.execute("SELECT source,path,line FROM edges WHERE target=? AND kind='calls'", (targets[0],))}
report = {'target': targets[0], 'graph_revision': metadata['revision'],
          'analyzer_fingerprint': metadata['analyzer_fingerprint'], 'source_sha256': files,
          'scope': 'reviewed direct Name calls to compact in one module and two explicitly imported modules',
          'expected_sites': sorted(expected), 'graph_sites': sorted(actual),
          'missing': sorted(expected - actual), 'false_sites': sorted(actual - expected),
          'site_precision': len(actual & expected) / len(actual) if actual else None,
          'site_recall': len(actual & expected) / len(expected),
          'reviewed_callers': sum(map(len, reviewed.values()))}
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k:v for k,v in report.items() if k not in {'source_sha256','expected_sites','graph_sites'}}))
assert expected == actual, 'Graph differs from reviewed call-site inventory'
