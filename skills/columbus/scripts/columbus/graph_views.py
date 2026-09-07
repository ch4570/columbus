"""Bounded graph selection and dependency projections for exported views."""
from __future__ import annotations

import json


def graph_view(index, limit: int = 1000, *, path: str | None = None, language: str | None = None,
               kinds: list[str] | None = None, focus: str | None = None, hops: int = 2,
               direction: str = 'both', level: str = 'symbol') -> dict:
    if not 1 <= limit <= 5000:
        raise ValueError('graph limit must be 1–5000')
    if level not in {'symbol', 'file'}:
        raise ValueError('level must be symbol or file')
    if kinds is not None and (not kinds or any(k not in {'contains', 'calls', 'imports', 'inherits'} for k in kinds)):
        raise ValueError('kinds must use contains/calls/imports/inherits')
    where, values = index._filter_sql(path, language)
    focused = index.neighbors(focus, direction=direction, hops=hops, limit=min(limit, 200), kinds=kinds) if focus else None
    with index._read() as conn:
        meta = index._meta(conn)
        if focused and focused['revision'] != meta['revision']:
            raise ValueError('Index changed during retrieval; retry graph')
        if focused:
            nodes = [n for n in focused['nodes'] if index._matches(n, path, language)]
            ids = {n['id'] for n in nodes}
            edges = [e for e in focused['edges'] if e['source'] in ids and e['target'] in ids]
            truncated = focused['truncated']
        else:
            # Select files directly for file-level views so a large first file's
            # declarations cannot starve the rest of the repository.
            condition = where + (" AND s.id=s.path || '::module'" if level == 'file' else '')
            rows = conn.execute('SELECT s.data FROM symbols s WHERE ' + condition + ' ORDER BY s.path,s.id LIMIT ?', [*values, limit + 1]).fetchall()
            nodes = [json.loads(row[0]) for row in rows[:limit]]
            conn.execute('CREATE TEMP TABLE selected(id TEXT PRIMARY KEY)')
            if level == 'file':
                conn.execute('CREATE TEMP TABLE selected_paths(path TEXT PRIMARY KEY)')
                conn.executemany('INSERT INTO selected_paths VALUES(?)', [(n['path'],) for n in nodes])
                conn.execute('INSERT INTO selected SELECT id FROM symbols JOIN selected_paths USING(path)')
            else:
                conn.executemany('INSERT INTO selected VALUES(?)', [(n['id'],) for n in nodes])
            edge_filter = '' if not kinds else ' WHERE e.kind IN (' + ','.join('?' for _ in kinds) + ')'
            edge_rows = conn.execute('''SELECT e.*, a.path AS source_path,b.path AS target_path FROM edges e
                JOIN selected x ON e.source=x.id JOIN selected y ON e.target=y.id
                JOIN symbols a ON a.id=e.source JOIN symbols b ON b.id=e.target''' + edge_filter +
                ' ORDER BY e.source,e.target,e.kind,e.line LIMIT 20001', kinds or []).fetchall()
            edges = [dict(row) for row in edge_rows[:20000]]
            truncated = len(rows) > limit or len(edge_rows) > 20000
        if level == 'file':
            paths = {n['path'] for n in nodes}
            file_nodes = []
            for file in sorted(paths):
                file_nodes.append(index._find(conn, file + '::module'))
            projected = {}
            symbol_paths = {n['id']: n['path'] for n in nodes}
            for edge in edges:
                source = edge.get('source_path') or symbol_paths[edge['source']]
                target = edge.get('target_path') or symbol_paths[edge['target']]
                if source == target:
                    continue
                key = source, target, edge['kind']
                if key in projected:
                    projected[key]['count'] += 1
                else:
                    projected[key] = {**edge, 'source': source + '::module', 'target': target + '::module', 'count': 1}
            nodes, edges = file_nodes, list(projected.values())
        for edge in edges:
            edge.pop('source_path', None)
            edge.pop('target_path', None)
        result = {'nodes': nodes, 'edges': edges, 'revision': meta['revision'],
                  'freshness': 'index_snapshot', 'truncated': truncated}
        if focused:
            center = focused['center']
            if level == 'file':
                center = index._find(conn, center)['path'] + '::module'
            result.update(center=center, hops=hops, direction=direction)
        if level != 'symbol' or path or language or kinds:
            result['selection'] = {'level': level, 'path': path, 'language': language, 'kinds': kinds}
        return result
