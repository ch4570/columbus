"""Isolated compressed external-content FTS experiment; no production migration."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import zlib

p = argparse.ArgumentParser()
p.add_argument('--baseline', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
args = p.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
db = args.output / 'candidate.sqlite'
queries = ['DefaultResourceLoader', 'getResource', 'ResolvableType', 'Nullable',
           'protocolResolver', 'class loader', 'getClassLoader', 'paramTypes',
           'ReflectionUtils', 'MethodInvoker', 'ObjectUtils', 'ClassUtils']
with sqlite3.connect(args.baseline) as old, sqlite3.connect(db) as c:
    old.backup(c)
    control_db = args.output / 'vacuum-control.sqlite'
    with sqlite3.connect(control_db) as control:
        old.backup(control)
        control.execute('VACUUM')
    original = c.execute('SELECT rowid,id,name,path,body FROM symbol_fts ORDER BY rowid').fetchall()
    c.create_function('inflate', 1, lambda b: zlib.decompress(b).decode())
    c.executescript('''DROP TABLE symbol_fts;
      CREATE TABLE search_documents(rowid INTEGER PRIMARY KEY, id TEXT, name TEXT, path TEXT, body BLOB);
      CREATE VIEW search_content AS SELECT rowid,id,name,path,inflate(body) AS body FROM search_documents;
      CREATE VIRTUAL TABLE symbol_fts USING fts5(id UNINDEXED,name,path,body,content='search_content',content_rowid='rowid');''')
    c.executemany('INSERT INTO search_documents VALUES(?,?,?,?,?)',
                  [(r,n,name,path,zlib.compress(body.encode())) for r,n,name,path,body in original])
    c.execute("INSERT INTO symbol_fts(symbol_fts) VALUES('rebuild')")
    c.commit()
    c.execute('VACUUM')
    def search(conn, query):
        from columbus.index import terms
        expression = ' OR '.join('"' + word + '"' for word in terms(query))
        return conn.execute('''SELECT s.id,bm25(symbol_fts,0,8,3,1) AS rank
          FROM symbol_fts JOIN symbols s ON s.id=symbol_fts.id
          WHERE symbol_fts MATCH ? ORDER BY rank LIMIT 150''', (expression,)).fetchall()
    before = {q: search(old,q) for q in queries}
    after = {q: search(c,q) for q in queries}
    assert before == after
    assert c.execute('SELECT rowid,id,name,path,body FROM symbol_fts ORDER BY rowid').fetchall() == original
    # Explicit FTS deletion needs the prior text. Rollback must preserve both stores.
    row = next(r for r in original if 'DefaultResourceLoader' in r[1])
    c.execute('BEGIN')
    c.execute("INSERT INTO symbol_fts(symbol_fts,rowid,id,name,path,body) VALUES('delete',?,?,?,?,?)", row)
    c.execute('DELETE FROM search_documents WHERE rowid=?', (row[0],))
    assert all(item[0] != row[1] for item in search(c,'DefaultResourceLoader'))
    c.rollback()
    assert search(c,'DefaultResourceLoader') == before['DefaultResourceLoader']
    c.execute("INSERT INTO symbol_fts(symbol_fts,rank) VALUES('integrity-check',1)")
    c.commit()
    tables = dict(c.execute('SELECT name,sum(pgsize) FROM dbstat GROUP BY name'))
    result = {'sqlite_version':sqlite3.sqlite_version,'baseline_bytes':args.baseline.stat().st_size,
              'vacuum_control_bytes':control_db.stat().st_size,
              'candidate_bytes':db.stat().st_size,'documents':len(original),'queries':queries,
              'exact_fts_ids_and_scores_equal':True,'all_document_text_equal':True,
              'delete_and_rollback_passed':True,'fts_integrity_passed':True,'tables':tables,
              'baseline_path':str(args.baseline),'production_changed':False,
              'query_results_sha256':hashlib.sha256(json.dumps(before).encode()).hexdigest()}
(args.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
