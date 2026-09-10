#!/usr/bin/env python3
"""Compare two local Columbus checkouts on one unchanged repository; no builds.

Raw output contains private paths and source metadata. Use an ignored output path.
New databases measure construction; OS caches are not flushed. Never compare
these complete-index timings directly with another tool's extraction-only stage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import sqlite3
import statistics
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True, help='Frozen Columbus checkout')
    parser.add_argument('--candidate', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--query', required=True, help='Same exact symbol query in both engines')
    parser.add_argument('--samples', type=int, default=3)
    args = parser.parse_args()
    root, output = args.repo.resolve(), args.output.resolve()
    engines = {'before': args.baseline.resolve(), 'after': args.candidate.resolve()}
    if not 1 <= args.samples <= 5:
        parser.error('samples must be 1–5')
    if output.exists() or output.is_relative_to(root):
        parser.error('Use a new output directory outside the source repository')
    for engine in engines.values():
        if not (engine / 'skills/columbus/scripts/columbus.py').is_file():
            parser.error('Both engine entrypoints must exist')
    output.mkdir(parents=True)
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD']).decode().strip()
    state = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain=v1'])
    runs = []
    def engine_fingerprints():
        return {name: {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted((engine / 'skills/columbus/scripts/columbus').glob('*.py'))}
                for name, engine in engines.items()}

    fingerprints = engine_fingerprints()

    def invoke(engine, db, directory, label, *tail):
        command = [sys.executable, str(engine / 'skills/columbus/scripts/columbus.py'),
                   '--repo', str(root), '--db', str(db), *tail]
        measured = ['/usr/bin/time', '-l', *command] if platform.system() == 'Darwin' else command
        started = time.perf_counter()
        result = subprocess.run(measured, capture_output=True, timeout=300)
        elapsed = time.perf_counter() - started
        (directory / f'{label}.stdout').write_bytes(result.stdout)
        (directory / f'{label}.stderr').write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError(f'{label} failed; inspect {directory}')
        memory = re.search(rb'(\d+)\s+maximum resident set size', result.stderr)
        record = {'seconds': round(elapsed, 6), 'stdout_bytes': len(result.stdout),
                  'peak_rss_bytes': int(memory[1]) if memory else None, 'command': command}
        return json.loads(result.stdout), record

    for sample in range(args.samples):
        for name in (['before', 'after'] if sample % 2 == 0 else ['after', 'before']):
            engine, directory = engines[name], output / f'{sample}-{name}'
            directory.mkdir()
            db = directory / 'index.sqlite'
            cold, cold_record = invoke(engine, db, directory, 'cold', 'sync')
            warm, warm_record = invoke(engine, db, directory, 'warm', 'sync')
            search, auto_record = invoke(engine, db, directory, 'auto-search', 'search', args.query, '--limit', '3')
            snapshot, snapshot_record = invoke(engine, db, directory, 'snapshot-search', 'search', args.query,
                                               '--limit', '3', '--snapshot')
            assert [h['id'] for h in search['hits']] == [h['id'] for h in snapshot['hits']]
            assert warm['refresh']['parsed_files'] == warm['refresh']['hashed_files'] == 0
            assert not warm['refresh']['global_relink']
            with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as c:
                assert c.execute('pragma integrity_check').fetchall() == [('ok',)]
                assert not c.execute('pragma foreign_key_check').fetchall()
                files = c.execute('select path,hash from files order by path').fetchall()
                parse_bytes = c.execute('select sum(length(cast(parsed as blob))) from files').fetchone()[0]
                raw_cache_bytes = c.execute("select count(*) from files where typeof(parsed)='blob'").fetchone()[0]
                cross_file = c.execute('select count(*) from (select a.path,b.path,e.kind from edges e '
                                      'join symbols a on a.id=e.source join symbols b on b.id=e.target '
                                      'where a.path<>b.path group by a.path,b.path,e.kind)').fetchone()[0]
            run = {'engine': name, 'sample': sample, 'cold': cold_record, 'warm': warm_record,
                   'auto_search': auto_record, 'snapshot_search': snapshot_record,
                   'database_bytes': db.stat().st_size, 'parse_cache_bytes': parse_bytes,
                   'compressed_files': raw_cache_bytes, 'file_manifest_sha256': hashlib.sha256(json.dumps(files).encode()).hexdigest(),
                   'files': cold['files'], 'symbols': cold['symbols'], 'edges': cold['edges'],
                   'cross_file_edges': cross_file, 'references': cold['references'],
                   'resolved_references': cold['resolved_references'],
                   'unresolved_references': cold['unresolved_references'], 'revision': cold['revision']}
            runs.append(run)
            (output / 'runs.json').write_text(json.dumps(runs, indent=2) + '\n')
            print(json.dumps({k: run[k] for k in ['engine', 'sample', 'database_bytes', 'parse_cache_bytes']},
                             ensure_ascii=False), flush=True)
    assert len({r['file_manifest_sha256'] for r in runs}) == 1
    assert engine_fingerprints() == fingerprints, 'Engine source changed during measurement'
    assert subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD']).decode().strip() == head
    assert subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain=v1']) == state
    summary = {'source_head': head, 'engine_fingerprints': fingerprints, 'python': sys.version,
               'platform': platform.platform(), 'runs': runs, 'medians': {},
               'limits': ['OS caches not cleared; first build means new database, not cold disk.',
                          'Timings include process startup and full output serialization.',
                          'Git status parity does not prove byte invariance of already dirty/ignored files.',
                          'No model usage or billing measured.']}
    for name in engines:
        selected = [r for r in runs if r['engine'] == name]
        summary['medians'][name] = {key + '_seconds': statistics.median(r[key]['seconds'] for r in selected)
                                    for key in ['cold', 'warm', 'auto_search', 'snapshot_search']}
        summary['medians'][name].update({key: statistics.median(r[key] for r in selected)
                                        for key in ['database_bytes', 'parse_cache_bytes']})
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary['medians'], indent=2))


if __name__ == '__main__':
    main()
