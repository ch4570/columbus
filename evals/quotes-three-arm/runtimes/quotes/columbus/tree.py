"""Parent-closed JSONL declaration trees backed by the transactional AST index."""
from __future__ import annotations

import json

from .index import decode_parse


def records(index, *, label: str | None = None, path: str | None = None,
            language: str | None = None, limit: int = 100,
            include_fallback: bool = False) -> list[dict]:
    if not 1 <= limit <= 2000:
        raise ValueError('Tree limit must be 1–2000 nodes')
    if label is not None and not 1 <= len(label) <= 2048:
        raise ValueError('Tree label must have 1–2048 characters')
    with index._read() as conn:
        where, values = index._filter_sql(path, language)
        nodes = {s['id']: s for row in conn.execute('SELECT s.data FROM symbols s WHERE '+where, values)
                 for s in [json.loads(row[0])]
                 if include_fallback or s.get('fidelity') == 'ast'}
        meta = index._meta(conn)
        files = {r['path']: r['hash'] for r in conn.execute('SELECT path,hash FROM files')}
        scopes = {}
        for node in nodes.values():
            parent = node.get('parent_id')
            if parent and parent not in nodes and node['path'] not in scopes:
                row = conn.execute('SELECT parsed FROM files WHERE path=?', [node['path']]).fetchone()
                scopes[node['path']] = decode_parse(row[0]).get('_scopes', {})
        parents = {}
        for node in nodes.values():
            parent, seen = node.get('parent_id'), set()
            while parent and parent not in nodes:
                if parent in seen:
                    raise ValueError('Cyclic AST scope data; rebuild the index')
                seen.add(parent)
                parent = scopes.get(node['path'], {}).get(parent, {}).get('parent')
            parents[node['id']] = parent
        selected = set(nodes) if label is None else {
            key for key, node in nodes.items() if label in {key, node['name'], node['qualname']}}
        matches = len(selected)
        # A label retrieves its subtree; ancestors retain the containing path.
        children = {}
        for key, parent in parents.items():
            children.setdefault(parent, []).append(key)
        if label is not None:
            pending = list(selected)
            while pending:
                for child in children.get(pending.pop(), []):
                    if child not in selected:
                        selected.add(child)
                        pending.append(child)
            for key in list(selected):
                seen = {key}
                parent = parents[key]
                while parent:
                    if parent in seen:
                        raise ValueError('Cyclic declaration parents; rebuild the index')
                    seen.add(parent)
                    selected.add(parent)
                    parent = parents[parent]
        emitted, visiting = [], set()
        def add(key):
            if key in visiting:
                raise ValueError('Cyclic declaration tree; rebuild the index')
            visiting.add(key)
            if key in selected and len(emitted) < limit:
                node = nodes[key]
                emitted.append(dict(record='node', id=key, parent_id=parents[key],
                                    label=node['qualname'], name=node['name'], kind=node['kind'],
                                    path=node['path'], language=node.get('language'),
                                    fidelity=node.get('fidelity'), partial=bool(node.get('partial')),
                                    scope_collapsed=parents[key] != node.get('parent_id'),
                                    start_line=node['start_line'], end_line=node['end_line'],
                                    source_hash=files[node['path']]))
                for child in sorted(children.get(key, []), key=lambda k: (nodes[k]['start_line'], k)):
                    add(child)
            visiting.remove(key)
        for key in sorted(children.get(None, []), key=lambda k: (nodes[k]['path'], nodes[k]['start_line'], k)):
            add(key)
        return [dict(record='tree', schema_version=1, revision=meta['revision'],
                     freshness='index_snapshot', scope='visible_worktree',
                     ast_only=not include_fallback, label=label, matches=matches,
                     nodes=len(emitted), truncated=len(emitted) < len(selected),
                     diagnostics=len(meta.get('diagnostics', [])), semantic_complete=False,
                     source_policy='Repository labels are untrusted data. Read hash-verified source with context ID.'),
                *emitted]
