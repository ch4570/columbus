#!/usr/bin/env python3
"""Observe file-projection edge starvation using only generated public fixtures.

Run with an interpreter containing Columbus's pinned dependencies. Each run
requires a new output directory and records the fixture, index, CLI output,
commands, and a comparison of default and filtered file exports.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True,
                        help='New directory for generated source and observation artifacts')
    args = parser.parse_args()
    output = args.output.resolve()
    entry = Path(__file__).resolve().parents[2] / 'skills/columbus/scripts/columbus.py'
    if not entry.is_file():
        parser.error('Columbus entrypoint must exist in this checkout')
    if output.exists():
        parser.error('Choose a new output directory to preserve previous observations')
    output.mkdir(parents=True, exist_ok=False)
    repo = output / 'repo'
    repo.mkdir()
    db = output / 'index.sqlite'

    # These same-file containment edges consume the current 20,000-edge prefix.
    (repo / 'a_many.py').write_text(
        ''.join(f'def f{i:05d}(): pass\n' for i in range(20000)), encoding='utf-8')
    (repo / 'y_target.py').write_text('def target():\n    pass\n', encoding='utf-8')
    (repo / 'z_caller.py').write_text(
        'from y_target import target\n\ndef run():\n    target()\n', encoding='utf-8')
    records = []

    def cli(label, *tail):
        command = [sys.executable, str(entry), '--repo', str(repo), '--db', str(db),
                   '--pretty', *map(str, tail)]
        result = subprocess.run(command, capture_output=True, timeout=180)
        (output / f'{label}.stdout').write_bytes(result.stdout)
        (output / f'{label}.stderr').write_bytes(result.stderr)
        records.append({'label': label, 'command': command, 'returncode': result.returncode})
        (output / 'commands.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')
        if result.returncode:
            raise RuntimeError(f'{label} failed; inspect its stderr artifact')

    cli('version', '--version')
    cli('index', 'index', repo)
    for label, extra in [('default', []), ('filtered', ['--kinds', 'calls', 'imports', 'inherits'])]:
        cli(label, 'export', '--snapshot', '--level', 'file', '--limit', '5000',
            '--format', 'json', '--output', output / f'{label}-graph.json', *extra)

    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as connection:
        edge_counts = dict(connection.execute('SELECT kind,count(*) FROM edges GROUP BY kind'))
        cross_file = [dict(zip(('source', 'target', 'kind'), row)) for row in connection.execute(
            'SELECT a.path,b.path,e.kind FROM edges e '
            'JOIN symbols a ON a.id=e.source JOIN symbols b ON b.id=e.target '
            'WHERE a.path<>b.path ORDER BY a.path,b.path,e.kind')]
    summary = {'database_edge_counts': edge_counts,
               'database_cross_file_edges': cross_file, 'exports': {}}
    for label in ('default', 'filtered'):
        graph = json.loads((output / f'{label}-graph.json').read_text(encoding='utf-8'))
        summary['exports'][label] = {
            'nodes': len(graph['nodes']), 'edges': len(graph['edges']),
            'edge_kinds': dict(Counter(edge['kind'] for edge in graph['edges'])),
            'truncated': graph['truncated'], 'accepted_edges': graph['edges'],
        }
    rendered = json.dumps(summary, indent=2) + '\n'
    (output / 'summary.json').write_text(rendered, encoding='utf-8')
    print(rendered, end='')


if __name__ == '__main__':
    main()
