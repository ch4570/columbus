"""Compare stored direct calls with an independent, source-hashed AST oracle."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from columbus.archive import archive, neighbors_archive
from columbus.index import RepositoryIndex

p = argparse.ArgumentParser()
p.add_argument('repo', type=Path)
p.add_argument('database', type=Path)
p.add_argument('output', type=Path)
a = p.parse_args()
oracle = json.loads(Path(__file__).with_name('oracle.json').read_text())
manifest = oracle['production_source_manifest']
assert set(manifest) == {f.relative_to(a.repo).as_posix() for f in (a.repo/'django').rglob('*.py')}
for path, digest in manifest.items():
    assert hashlib.sha256((a.repo/path).read_bytes()).hexdigest() == digest, path
key = lambda row: (row['path'], row['qualname'], row['line'])
expected = sorted(key(row) for row in oracle['targets']['iri_to_uri']['calls'])
with sqlite3.connect(a.database.resolve().as_uri()+'?mode=ro', uri=True) as conn:
    conn.row_factory = sqlite3.Row
    indexed_hashes = dict(conn.execute('SELECT path,hash FROM files'))
    assert all(indexed_hashes.get(path) == digest for path, digest in manifest.items())
    target, = conn.execute("SELECT id FROM symbols WHERE path='django/utils/encoding.py' AND name='iri_to_uri'").fetchall()
    target = target['id']
    rows = conn.execute("SELECT e.path,s.qualname,e.line FROM edges e JOIN symbols s ON s.id=e.source WHERE e.target=? AND e.kind='calls' AND e.path LIKE 'django/%'", (target,)).fetchall()
    actual = sorted(key(row) for row in rows)
    assert actual == expected, (actual, expected)
    all_edges = [dict(row) for row in conn.execute("SELECT * FROM edges WHERE target=? AND kind='calls'", (target,))]
with tempfile.TemporaryDirectory() as directory:
    artifact = Path(directory)/'graph.jsonl.gz'
    receipt = archive(RepositoryIndex(a.database), artifact)
    checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
    edges = []
    pages = []
    offset = 0
    while True:
        page = neighbors_archive(artifact, target, direction='in', kinds=['calls'], limit=50, budget_bytes=6000, offset=offset)
        edges.extend(page['edges'])
        pages.append({'offset':offset, 'edges':len(page['edges']), 'next_offset':page['next_offset']})
        if page['next_offset'] is None:
            break
        assert page['next_offset'] > offset
        offset = page['next_offset']
    edge_key = lambda row: tuple(row[k] for k in ('source','target','kind','confidence','evidence','path','line'))
    assert sorted(map(edge_key, edges)) == sorted(map(edge_key, all_edges))
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == checksum
    result = {'source_commit':oracle['revision'], 'production_files_hash_verified':len(manifest),
              'target':target, 'production_call_sites':len(actual), 'production_callers':len({x[:2] for x in actual}),
              'missing':[], 'extra':[], 'archive_all_call_edges':len(edges), 'archive_pages':pages,
              'archive_sqlite_edge_parity':True, 'archive_sha256':checksum, 'archive_bytes':receipt['bytes'],
              'sqlite_bytes':a.database.stat().st_size, 'runtime_completeness_claimed':False}
    a.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
