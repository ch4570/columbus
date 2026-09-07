"""Same-corpus storage, sync and exact search parity; run from repository root."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

from columbus.index import RepositoryIndex

root = Path(sys.argv[1]).resolve()
baseline_ref = sys.argv[2] if len(sys.argv) > 2 else '4d55a34'
queries = ['DefaultResourceLoader', 'getResource', 'ResolvableType', 'Nullable',
           'protocolResolver', 'class loader', 'getClassLoader', 'paramTypes',
           'ReflectionUtils', 'MethodInvoker', 'ObjectUtils', 'ClassUtils']


def measure(index):
    start = time.perf_counter()
    report = index.refresh(root, fast=True)
    return {'seconds': time.perf_counter() - start, 'refresh': report['refresh']}


def facts(db):
    with sqlite3.connect(db) as conn:
        result = {}
        for table, order in [('symbols', 'id'), ('edges', 'source,target,kind,evidence,path,line,confidence')]:
            rows = conn.execute(f'SELECT * FROM {table} ORDER BY {order}').fetchall()
            result[table] = {'count': len(rows), 'sha256': hashlib.sha256(
                json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()}
        return result


with tempfile.TemporaryDirectory() as directory:
    directory = Path(directory)
    baseline = directory / 'baseline.py'
    baseline.write_bytes(subprocess.check_output([
        'git', 'show', baseline_ref + ':skills/columbus/scripts/columbus/index.py']))
    spec = importlib.util.spec_from_file_location('columbus.baseline_index', baseline)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = {'baseline_commit': subprocess.check_output(['git', 'rev-parse', baseline_ref], text=True).strip(),
              'corpus_commit': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
              'engine_sha256': hashlib.sha256(Path('skills/columbus/scripts/columbus/index.py').read_bytes()).hexdigest(),
              'os_cache': 'not flushed; baseline first; shared host load uncontrolled', 'queries': queries}
    searches = {}
    target = root / 'src/main/java/org/springframework/core/io/DefaultResourceLoader.java'
    original = target.read_bytes()
    result['edited_source_sha256'] = hashlib.sha256(original).hexdigest()
    for label, cls in [('before', module.RepositoryIndex), ('after', RepositoryIndex)]:
        db = directory / (label + '.sqlite')
        index = cls(db)
        cold = measure(index)
        with sqlite3.connect(db) as conn:
            tables = dict(conn.execute('SELECT name,sum(pgsize) FROM dbstat GROUP BY name'))
        database_bytes = db.stat().st_size
        warm = [measure(index) for _ in range(5)]
        searches[label] = {query: index.search(query, limit=50)['hits'] for query in queries}
        snapshot = facts(db)
        try:
            target.write_bytes(original + b'\n// storage benchmark edit\n')
            edit = measure(index)
            edited_facts = facts(db)
        finally:
            target.write_bytes(original)
            restored = measure(index)
        result[label] = {'cold': cold, 'warm': warm, 'warm_median_seconds': statistics.median(r['seconds'] for r in warm),
                         'database_bytes': database_bytes, 'allocated_table_bytes': sum(tables.values()), 'tables': tables, 'facts': snapshot,
                         'edit': edit, 'edited_facts': edited_facts, 'restore': restored,
                         'restored_facts_equal': snapshot == facts(db),
                         'indexed_bytes': index.status()['indexed_bytes']}
    result['all_symbol_edge_rows_equal'] = result['before']['facts'] == result['after']['facts']
    result['edited_symbol_edge_rows_equal'] = result['before']['edited_facts'] == result['after']['edited_facts']
    result['search_hits_and_ranking_equal'] = searches['before'] == searches['after']
    print(json.dumps(result, indent=2))
    assert result['all_symbol_edge_rows_equal'] and result['edited_symbol_edge_rows_equal'] and result['search_hits_and_ranking_equal']
