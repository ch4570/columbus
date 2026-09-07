"""Focused AST oracle for a frozen multi-hop task; never imports Columbus."""
import ast
from collections import deque
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'evals/exploration/fixtures/columbus-source-c67b20a.zip'
PREFIX = 'skills/columbus/scripts/columbus/'


def build():
    with zipfile.ZipFile(FIXTURE) as archive:
        sources = {name.removeprefix('columbus-source/'): archive.read(name)
                   for name in archive.namelist() if name.endswith('.py')}
    trees = {path: ast.parse(data, filename=path) for path, data in sources.items()}
    index = trees[PREFIX + 'index.py']
    cls = next(n for n in index.body if isinstance(n, ast.ClassDef) and n.name == 'RepositoryIndex')
    assert not cls.bases and not cls.decorator_list and not cls.keywords
    methods = {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert len(methods) == len([n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))])
    for path, module, name in [(PREFIX+'index.py', 'sync_state', 'read_stable'),
                               (PREFIX+'sync_state.py', 'discovery', 'safe_source')]:
        imports = [a for n in trees[path].body if isinstance(n, ast.ImportFrom)
                   and n.level == 1 and n.module == module for a in n.names if a.name == name]
        assert len(imports) == 1 and imports[0].asname is None
        assert not any((isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, (ast.Store, ast.Del)))
                       or (isinstance(n, ast.arg) and n.arg == name) for n in ast.walk(trees[path]))
    records = []
    class Calls(ast.NodeVisitor):
        def __init__(self, path): self.path, self.stack = path, []
        def visit_ClassDef(self, node):
            self.stack.append(node.name)
            for item in node.body: self.visit(item)
            self.stack.pop()
        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            for item in node.body: self.visit(item)
            self.stack.pop()
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_Lambda(self, node): pass
        def visit_Call(self, node):
            records.append({'path': self.path, 'owner': '.'.join(self.stack), 'line': node.lineno,
                            'callee': ast.unparse(node.func)})
            self.generic_visit(node)
    for path, tree in trees.items(): Calls(path).visit(tree)
    direct = [r for r in records if r['callee'] == 'read_stable']
    assert all(r['path'] == PREFIX+'index.py' and r['owner'] in {'RepositoryIndex.'+m for m in methods} for r in direct)
    assert not any(r['callee'].endswith('.read_stable') for r in records)
    edges = []
    for r in records:
        if r['path'] == PREFIX+'index.py' and r['owner'] in {'RepositoryIndex.'+m for m in methods}:
            member = r['callee'].removeprefix('self.')
            target = ('RepositoryIndex.'+member if r['callee'].startswith('self.') and member in methods
                      else 'read_stable' if r['callee'] == 'read_stable' else None)
            if target:
                if r['callee'].startswith('self.'):
                    fn = methods[r['owner'].split('.')[-1]]
                    assert fn.args.args[0].arg == 'self'
                    assert not any(isinstance(n, ast.Name) and n.id == 'self' and isinstance(n.ctx, (ast.Store, ast.Del)) for n in ast.walk(fn))
                edges.append({**r, 'target': target})
        elif r['path'] == PREFIX+'sync_state.py' and r['owner'] == 'read_stable' and r['callee'] == 'safe_source':
            edges.append({**r, 'target': 'safe_source'})
    findings = []
    for method in sorted(methods):
        start = 'RepositoryIndex.'+method
        queue = deque([(start, [])]); seen = {start}
        while queue:
            node, chain = queue.popleft()
            if node == 'safe_source':
                assert any(e['target'] == 'read_stable' for e in chain)
                findings.append({'id': start, 'hops': len(chain), 'shortest_path': chain})
                break
            if len(chain) == 3: continue
            for edge in sorted((e for e in edges if e['owner'] == node), key=lambda e:(e['target'],e['line'])):
                if edge['target'] not in seen:
                    seen.add(edge['target']); queue.append((edge['target'], chain+[edge]))
    assert [f['id'] for f in findings] == ['RepositoryIndex._source', 'RepositoryIndex.refresh', 'RepositoryIndex.status', 'RepositoryIndex.symbol']
    return {'fixture_sha256': hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            'source_hashes': {p:hashlib.sha256(d).hexdigest() for p,d in sorted(sources.items())},
            'rule': 'Within three hops: direct imported read_stable calls, lexical self member calls within RepositoryIndex, and the direct read_stable to safe_source handoff. Shortest paths only. No runtime reachability claim.',
            'method_universe': sorted('RepositoryIndex.'+m for m in methods), 'findings': findings,
            'direct_read_stable_sites': direct, 'focused_edges': edges}

if __name__ == '__main__':
    result = build()
    (Path(__file__).with_name('oracle.json')).write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps([(f['id'], f['hops']) for f in result['findings']]))
