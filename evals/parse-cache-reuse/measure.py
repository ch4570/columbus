"""Full Django parse-cache reuse comparison, including cross-file rename invalidation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import statistics
import subprocess
import sys
import time
import zlib


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def worker(source, output):
    from columbus.index import RepositoryIndex
    root = output / 'source'
    shutil.copytree(source, root, ignore=shutil.ignore_patterns('.git', '.columbus', '__pycache__'))
    index = RepositoryIndex(output / 'index.sqlite')

    def refresh(fast):
        start = time.perf_counter()
        result = index.refresh(root, fast=fast)
        return {'seconds': time.perf_counter() - start, 'refresh': result['refresh']}

    def snapshot():
        with sqlite3.connect(index.db) as conn:
            files = dict(conn.execute('SELECT path,hash FROM files'))
            facts = {p: json.loads(zlib.decompress(v) if isinstance(v, bytes) else v)
                     for p, v in conn.execute('SELECT path,parsed FROM files')}
            tables = {table: sorted(conn.execute('SELECT * FROM ' + table).fetchall())
                      for table in ('symbols', 'edges')}
            # rowid is a physical FTS address, reassigned when an edited file is reinserted.
            tables['search_documents'] = sorted(conn.execute('SELECT id,name,path,body FROM search_documents').fetchall())
            # Compressed search bodies are compared byte-for-byte as hex strings.
            tables = {t: [[v.hex() if isinstance(v, bytes) else v for v in row] for row in rows]
                      for t, rows in tables.items()}
        assert all(hashlib.sha256((root / p).read_bytes()).hexdigest() == h for p, h in files.items())
        return {'source_hashes': files, 'facts_sha256': digest(facts),
                'table_sha256': {t: digest(rows) for t, rows in tables.items()},
                'table_counts': {t: len(rows) for t, rows in tables.items()},
                'search_hits': {q: index.search(q, limit=50)['hits'] for q in
                                ('iri_to_uri', 'force_bytes', 'RequestFactory', 'QueryDict', 'urlencode', 'conditional_escape')}}

    cold = refresh(False)
    warm = [refresh(True) for _ in range(5)]
    initial = snapshot()
    target = root / 'django/utils/encoding.py'
    original = target.read_bytes()
    target.write_bytes(original + b'\n# prefix cache sync measurement\n')
    edit = refresh(True)
    edited_snapshot = snapshot()
    target.write_bytes(original)
    restoration = refresh(True)
    restored = snapshot()
    renamed = original.replace(b'def iri_to_uri(iri):', b'def renamed_iri_to_uri(iri):')
    assert renamed != original
    target.write_bytes(renamed)
    rename = refresh(True)
    renamed_snapshot = snapshot()
    target.write_bytes(original)
    refresh(True)
    assert snapshot() == initial
    (output / 'initial-snapshot.json').write_text(json.dumps(initial, indent=2) + '\n')
    (output / 'restored-snapshot.json').write_text(json.dumps(restored, indent=2) + '\n')
    assert restored == initial, [key for key in initial if initial[key] != restored[key]]
    result = {'cold': cold, 'warm': warm, 'warm_median_seconds': statistics.median(r['seconds'] for r in warm),
              'one_file_edit': edit, 'edited_snapshot': edited_snapshot, 'rename': rename, 'renamed_snapshot': renamed_snapshot, 'restoration': restoration,
              'database_bytes': index.db.stat().st_size, 'snapshot': initial, 'restored_snapshot_equal': True}
    (output / 'measurement.json').write_text(json.dumps(result, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    if args.worker:
        worker(args.source, args.output)
        return
    args.output.mkdir(parents=True, exist_ok=False)
    records, manifests, revisions = {}, {}, {}
    source_revision = subprocess.check_output(['git', '-C', str(args.source), 'rev-parse', 'HEAD'], text=True).strip()
    for name, ref in [('before', '279416c'), ('after', '279416c')]:
        revision = subprocess.check_output(['git', 'rev-parse', ref], text=True).strip()
        revisions[name] = revision
        directory = args.output / name
        runtime = directory / 'runtime'
        runtime.mkdir(parents=True)
        manifest = {}
        paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', revision,
                                         'skills/columbus/scripts/columbus'], text=True).splitlines()
        for path in paths:
            if not path.endswith('.py'):
                continue
            relative = path.removeprefix('skills/columbus/scripts/')
            data = (Path(path).read_bytes() if name == 'after' and path.endswith('/index.py')
                    else subprocess.check_output(['git', 'show', revision + ':' + path]))
            dest = runtime / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            manifest[relative] = hashlib.sha256(data).hexdigest()
        manifests[name] = manifest
        # Candidate grammar remains available after the frozen Columbus package.
        env = dict(os.environ, PYTHONPATH=str(runtime.resolve()) + os.pathsep + os.environ.get('PYTHONPATH', ''))
        subprocess.run([sys.executable, str(Path(__file__).resolve()), str(args.source.resolve()),
                        str(directory.resolve()), '--worker'], env=env, check=True)
        records[name] = json.loads((directory / 'measurement.json').read_text())
    assert manifests['before'].keys() == manifests['after'].keys()
    assert [p for p in manifests['before'] if manifests['before'][p] != manifests['after'][p]] == ['columbus/index.py']
    assert records['before']['snapshot'] == records['after']['snapshot']
    assert records['before']['edited_snapshot'] == records['after']['edited_snapshot']
    assert records['before']['renamed_snapshot'] == records['after']['renamed_snapshot']
    assert subprocess.check_output(['git', '-C', str(args.source), 'rev-parse', 'HEAD'], text=True).strip() == source_revision
    result = {'source_revision': source_revision, 'base_revisions': revisions, 'after_override': 'Working index.py frozen by runtime manifest', 'runtime_manifests': manifests,
              'measurements': records, 'full_snapshot_equal': True,
              'cache_conditions': 'Same host, before then after; OS caches not flushed; five warm samples per runtime.',
              'model_trial': False}
    (args.output / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    print({name: {'warm_median_seconds': r['warm_median_seconds'], 'database_bytes': r['database_bytes'],
                  'edit_seconds': r['one_file_edit']['seconds']} for name, r in records.items()})


if __name__ == '__main__':
    main()
