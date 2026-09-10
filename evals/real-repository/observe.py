#!/usr/bin/env python3
"""Observe real-repository navigation without building or modifying target source.

Output contains private paths and source. Keep it outside version control.
Run with the dedicated interpreter containing Columbus's pinned dependencies.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import time
import tokenize


def source_view(path, language):
    """Decode the documented source view independently of the retrieval engine."""
    data = path.read_bytes()
    encoding = tokenize.detect_encoding(io.BytesIO(data).readline)[0] if language == 'python' else 'utf-8-sig'
    text = data.decode(encoding).replace('\r\n', '\n')
    if language not in {'java', 'kotlin'}:
        text = text.replace('\r', '\n')
    return text.removesuffix('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--query', action='append', required=True,
                        help='Exact qualified entry symbol; repeat for each question')
    args = parser.parse_args()
    root, db, output = args.repo.resolve(), args.db.resolve(), args.output.resolve()
    engine = Path(__file__).resolve().parents[2]
    entry = engine / 'skills/columbus/scripts/columbus.py'
    if not root.is_dir() or not entry.is_file():
        parser.error('Repository and Columbus entrypoint must exist')
    if output.exists():
        parser.error('Choose a new output directory to preserve previous observations')
    if output.is_relative_to(root) or db.is_relative_to(root):
        parser.error('Keep the observation and index outside the source repository')
    output.mkdir(parents=True)
    records, checks = [], []

    def git(path, *tail):
        return subprocess.check_output(['git', '-C', str(path), *tail]).decode().strip()

    head, before = git(root, 'rev-parse', 'HEAD'), git(root, 'status', '--porcelain=v1')
    engine_head = git(engine, 'rev-parse', 'HEAD')

    def cli(label, *tail):
        command = [sys.executable, str(entry), '--repo', str(root), '--db', str(db), *tail]
        started = time.perf_counter()
        result = subprocess.run(command, capture_output=True, timeout=300)
        elapsed = time.perf_counter() - started
        (output / f'{label}.stdout').write_bytes(result.stdout)
        (output / f'{label}.stderr').write_bytes(result.stderr)
        records.append({'label': label, 'command': command, 'returncode': result.returncode,
                        'seconds': round(elapsed, 6), 'stdout_bytes': len(result.stdout),
                        'stdout_sha256': hashlib.sha256(result.stdout).hexdigest()})
        (output / 'commands.json').write_text(json.dumps(records, indent=2) + '\n')
        if result.returncode:
            raise RuntimeError(f'{label} failed; inspect its local stderr artifact')
        return json.loads(result.stdout)

    def check(name, passed, evidence):
        checks.append({'name': name, 'passed': bool(passed), 'evidence': evidence})

    cli('doctor', 'doctor')
    cold = None if db.exists() else cli('cold', 'sync')
    warm = [cli(f'warm-{n}', 'sync')['refresh'] for n in range(3)]
    check('unchanged sync hashes and parses zero files',
          all(r['hashed_files'] == r['parsed_files'] == 0 for r in warm), 'warm-{0,1,2}.stdout')
    cli('verified-status', 'status', '--verify-content')
    cli('bounded-map', 'map', '--snapshot', '--budget-tokens', '2000')
    navigation = []
    for number, query in enumerate(args.query):
        prefix = f'question-{number + 1}'
        search = cli(f'{prefix}-search', 'search', query, '--snapshot', '--limit', '3')
        exact = [hit for hit in search['hits'] if hit['qualname'] == query or hit['id'] == query]
        check(f'{prefix}: exact entry ranks first', bool(exact) and search['hits'][0] == exact[0], query)
        if not exact:
            navigation.append({'query': query, 'found': False})
            continue
        symbol = exact[0]
        result = cli(f'{prefix}-source', 'symbol', symbol['id'], '--snapshot', '--max-lines', '160')
        text = source_view(root / symbol['path'], symbol['language'])
        start, end = result['source_start_offset'], result['source_end_offset']
        check(f'{prefix}: source matches reported span and physical start line',
              result['source'] == text[start:end] and text[:start].count('\n') + 1 == result['start_line'],
              f'{prefix}-source.stdout')
        neighbors = cli(f'{prefix}-calls', 'neighbors', symbol['id'], '--snapshot', '--direction', 'out',
                        '--kinds', 'calls', '--hops', '2', '--limit', '100', '--budget-tokens', '2000')
        cli(f'{prefix}-impact', 'impact', symbol['id'], '--snapshot', '--hops', '2',
            '--limit', '100', '--budget-tokens', '2000')
        receipt = output / f'{prefix}-receipt.json'
        delivered = {}
        receipt_valid = True
        for n in range(3):
            packet = cli(f'{prefix}-context-{n}', 'context', symbol['id'], '--snapshot', '--receipt', str(receipt),
                         '--budget-tokens', '2000')
            for item in packet['items']:
                start, end = item['source_start_offset'], item['source_end_offset']
                current = source_view(root / item['path'], item['language'])
                spans = delivered.setdefault(item['path'], [])
                receipt_valid &= current[start:end] == item['source']
                receipt_valid &= all(end <= a or start >= b for a, b in spans)
                spans.append((start, end))
        check(f'{prefix}: receipt source is exact and non-overlapping', receipt_valid,
              f'{prefix}-context-{{0,1,2}}.stdout')
        cli(f'{prefix}-graph', 'graph', '--snapshot', '--focus', symbol['id'], '--hops', '2',
            '--limit', '120', '--format', 'html', '--output', str(output / f'{prefix}.html'))
        navigation.append({'query': query, 'found': True, 'id': symbol['id'],
                           'calls_response_fields': list(neighbors), 'path': symbol['path']})
    for format_ in ['html', 'json', 'mermaid', 'graphml']:
        extension = {'mermaid': 'mmd'}.get(format_, format_)
        cli(f'files-{format_}', 'graph', '--snapshot', '--level', 'file', '--limit', '5000',
            '--format', format_, '--output', str(output / f'files.{extension}'))
    for format_ in ['html', 'json']:
        cli(f'dependencies-{format_}', 'graph', '--snapshot', '--level', 'file', '--limit', '5000',
            '--kinds', 'calls', 'imports', 'inherits', '--format', format_,
            '--output', str(output / f'dependencies.{format_}'))
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as connection:
        integrity = connection.execute('pragma integrity_check').fetchall()
        foreign_keys = connection.execute('pragma foreign_key_check').fetchall()
        check('SQLite integrity', integrity == [('ok',)] and not foreign_keys, 'PRAGMA integrity_check/foreign_key_check')
        metadata = {k: json.loads(v) for k, v in connection.execute('select key,value from metadata')}
        languages, diagnostic_files = Counter(), Counter()
        for (parsed,) in connection.execute('select parsed from files'):
            parsed = json.loads(parsed)
            languages[parsed['language']] += 1
            if parsed.get('diagnostics'):
                diagnostic_files[parsed['language']] += 1
        edge_kinds = dict(connection.execute('select kind,count(*) from edges group by kind'))
        cross_file = set(connection.execute('select a.path,b.path,e.kind from edges e '
                         'join symbols a on a.id=e.source join symbols b on b.id=e.target where a.path<>b.path'))
    graph = json.loads((output / 'files.json').read_text())
    ids = [node['id'] for node in graph['nodes']]
    id_set = set(ids)
    check('file graph has unique nodes and no dangling edges', len(ids) == len(id_set) and
          all(e['source'] in id_set and e['target'] in id_set for e in graph['edges']), 'files.json')
    projections = {}
    for name in ['files', 'dependencies']:
        selected = json.loads((output / f'{name}.json').read_text())
        actual = {(e['source'].removesuffix('::module'), e['target'].removesuffix('::module'), e['kind'])
                  for e in selected['edges']}
        projections[name] = {'nodes': len(selected['nodes']), 'edges': len(actual),
                             'expected_cross_file_edges': len(cross_file), 'missing': len(cross_file - actual),
                             'truncated': selected['truncated']}
    check('bounded query payloads fit 6000 UTF-8 bytes', all(r['stdout_bytes'] <= 6000 for r in records
          if r['label'] == 'bounded-map' or '-calls' in r['label'] or '-impact' in r['label'] or '-context-' in r['label']),
          'commands.json; ceil(bytes / 3) is not model usage')
    check('source HEAD and porcelain status unchanged', head == git(root, 'rev-parse', 'HEAD') and
          before == git(root, 'status', '--porcelain=v1'), 'git before/after')
    summary = {'source_head': head, 'source_dirty_at_start': bool(before), 'engine_head': engine_head,
               'python': sys.version, 'platform': platform.platform(), 'cold': cold, 'warm': warm,
               'index_bytes': db.stat().st_size, 'languages': dict(languages),
               'diagnostic_files': dict(diagnostic_files), 'edge_kinds': edge_kinds,
               'metadata': metadata, 'questions': navigation, 'checks': checks, 'commands': records,
               'file_projections': projections,
               'limits': ['Not a runtime or compiler correctness test', 'No model token/cost comparison',
                          'Warm OS caches not cleared', 'Queries do not establish complete graph recall',
                          'HEAD/status equality does not prove byte invariance of already-dirty or ignored files']}
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'output': str(output), 'passed': sum(c['passed'] for c in checks),
                      'checks': len(checks), 'failures': [c for c in checks if not c['passed']]}, indent=2))
    return 0 if all(c['passed'] for c in checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
