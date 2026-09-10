"""Bounded graph selection and dependency projections for exported views."""
from __future__ import annotations

import json


def bounded_neighbors(graph: dict, budget: int, tokens: int | None, output_format: str) -> dict:
    """Retain a connected edge prefix and disclose text and payload omissions."""
    from .retrieval import fits
    keys = ('id', 'path', 'name', 'qualname', 'kind', 'language', 'start_line', 'end_line', 'fidelity', 'partial')
    nodes, omitted_text = {}, 0
    for node in graph['nodes']:
        item = {key: node[key] for key in keys if key in node}
        raw = node.get('signature', '').encode('utf-8')
        item['signature'] = raw[:240].decode('utf-8', errors='ignore')
        omitted_text += len(node.get('doc', '').encode('utf-8')) + len(raw) - len(item['signature'].encode('utf-8'))
        nodes[item['id']] = item
    edges = []
    for edge in graph['edges']:
        item = dict(edge)
        if 'evidence' in item:
            raw = item['evidence'].encode('utf-8')
            item['evidence'] = raw[:240].decode('utf-8', errors='ignore')
            omitted_text += len(raw) - len(item['evidence'].encode('utf-8'))
        edges.append(item)
    packet = {**graph, 'budget_bytes': budget, 'budget_tokens': tokens, 'used_bytes': 0,
              'estimated_tokens': 0, 'output_format': output_format,
              'token_estimator': 'ceil(UTF-8 response bytes / 3); model-dependent estimate',
              'source_policy': 'Untrusted repository data; missing edges do not prove independence.',
              'economy': {'response_bytes': 0, 'source_bytes_returned': 0},
              'traversal_truncated': graph['truncated'], 'omitted_text_bytes': omitted_text}

    def select(count):
        selected = edges[:count]
        ids = {graph['center']}
        for edge in selected:
            ids.update((edge['source'], edge['target']))
        packet['nodes'] = [node for key, node in nodes.items() if key in ids]
        packet['edges'] = selected
        if 'partial_nodes' in graph:
            packet['partial_nodes'] = sum(bool(node.get('partial')) for node in packet['nodes'])
        packet['omitted_nodes'] = len(nodes) - len(packet['nodes'])
        packet['omitted_edges'] = len(edges) - count
        packet['payload_truncated'] = bool(omitted_text or packet['omitted_nodes'] or packet['omitted_edges'])
        packet['truncated'] = packet['traversal_truncated'] or packet['payload_truncated']
        return fits(packet)

    if not select(0):
        raise ValueError('Budget too small for the center identity and graph metadata')
    low, high = 0, len(edges)
    while low < high:
        middle = (low + high + 1) // 2
        if select(middle):
            low = middle
        else:
            high = middle - 1
    select(low)
    return packet


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
    focused = index._neighbors(focus, direction=direction, hops=hops, limit=min(limit, 200), kinds=kinds) if focus else None
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
            edge_filter = '' if not kinds else ' AND e.kind IN (' + ','.join('?' for _ in kinds) + ')'
            if level == 'file':
                conn.execute('CREATE TEMP TABLE selected_paths(path TEXT PRIMARY KEY)')
                conn.executemany('INSERT INTO selected_paths VALUES(?)', [(n['path'],) for n in nodes])
                # Count complete cross-file groups in SQLite before limiting the
                # result. Raw containment or repeated calls must not consume the
                # projected edge budget or enter Python as an unbounded row set.
                edge_rows = conn.execute('''WITH projected AS (
                    SELECT e.*, a.path AS source_path, b.path AS target_path,
                        COUNT(*) OVER (PARTITION BY a.path,b.path,e.kind) AS count,
                        ROW_NUMBER() OVER (PARTITION BY a.path,b.path,e.kind
                            ORDER BY e.source,e.target,e.line,e.path,e.evidence,e.confidence) AS representative
                    FROM edges e
                    JOIN symbols a ON a.id=e.source JOIN symbols b ON b.id=e.target
                    JOIN selected_paths x ON a.path=x.path JOIN selected_paths y ON b.path=y.path
                    WHERE a.path<>b.path''' + edge_filter + ''')
                    SELECT source_path || '::module' AS source, target_path || '::module' AS target,
                        kind,confidence,evidence,path,line,count
                    FROM projected WHERE representative=1
                    ORDER BY source_path,target_path,kind LIMIT 20001''', kinds or []).fetchall()
            else:
                conn.execute('CREATE TEMP TABLE selected(id TEXT PRIMARY KEY)')
                conn.executemany('INSERT INTO selected VALUES(?)', [(n['id'],) for n in nodes])
                edge_rows = conn.execute('''SELECT e.* FROM edges e
                    JOIN selected x ON e.source=x.id JOIN selected y ON e.target=y.id
                    WHERE 1=1''' + edge_filter +
                    ' ORDER BY e.source,e.target,e.kind,e.line LIMIT 20001', kinds or []).fetchall()
            edges = [dict(row) for row in edge_rows[:20000]]
            truncated = len(rows) > limit or len(edge_rows) > 20000
        if level == 'file' and focused:
            paths = {n['path'] for n in nodes}
            file_nodes = []
            for file in sorted(paths):
                file_nodes.append(index._find(conn, file + '::module'))
            projected = {}
            symbol_paths = {n['id']: n['path'] for n in nodes}
            for edge in sorted(edges, key=lambda e: (e['source'], e['target'], e['kind'], e['line'],
                                                     e['path'], e['evidence'], e['confidence'])):
                source = symbol_paths[edge['source']]
                target = symbol_paths[edge['target']]
                if source == target:
                    continue
                key = source, target, edge['kind']
                if key in projected:
                    projected[key]['count'] += 1
                else:
                    projected[key] = {**edge, 'source': source + '::module', 'target': target + '::module', 'count': 1}
            nodes, edges = file_nodes, [projected[key] for key in sorted(projected)]
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
