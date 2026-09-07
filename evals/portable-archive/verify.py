"""Verify every archive node and edge against one complete SQLite snapshot."""
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from columbus.archive import search_archive

archive = Path(sys.argv[1])
db = Path(sys.argv[2])
nodes, edges, counts = {}, [], {}
with gzip.open(archive, 'rt', encoding='utf-8') as stream:
    for line in stream:
        row = json.loads(line)
        if row['record'] == 'node':
            nodes[row['data']['id']] = row['data']
        elif row['record'] == 'edge':
            edges.append(row['data'])
        elif row['record'] == 'end':
            counts = row['data']
with sqlite3.connect(db) as conn:
    conn.row_factory = sqlite3.Row
    expected_nodes = {row[0]: json.loads(row[1]) for row in conn.execute('SELECT id,data FROM symbols')}
    expected_edges = [dict(row) for row in conn.execute('SELECT * FROM edges ORDER BY source,target,kind,path,line,confidence,evidence')]
    source_bytes = conn.execute('SELECT sum(size) FROM files').fetchone()[0]
assert nodes == expected_nodes
assert edges == expected_edges
query = search_archive(archive, 'DefaultResourceLoader', budget_bytes=2048)
assert any(item['name'] == 'DefaultResourceLoader' for item in query['items'])
response_bytes = len((json.dumps(query, ensure_ascii=False, separators=(',', ':'))+'\n').encode())
assert response_bytes <= 2048
print(json.dumps({'archive_bytes': archive.stat().st_size, 'source_bytes': source_bytes,
                  'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'counts': counts,
                  'all_node_records_equal': True, 'all_edge_records_equal': True,
                  'query_response_bytes': response_bytes, 'query': query}, indent=2))
