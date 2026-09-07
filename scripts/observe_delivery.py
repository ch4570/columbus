#!/usr/bin/env python3
"""Measure real CLI output and receipt reuse on the bundled polyglot example."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
COLUMBUS = ROOT / 'skills/columbus/scripts/columbus.py'


def fixture_sources(fixture: Path) -> dict[str, bytes]:
    """Copy only fixture inputs, excluding both current and preview caches."""
    return {p.relative_to(fixture).as_posix(): p.read_bytes()
            for p in sorted(fixture.rglob('*')) if p.is_file()
            and not {'.columbus', '.repoatlas', '.git', '__pycache__'} & set(p.relative_to(fixture).parts)}


def observe() -> dict:
    sources = fixture_sources(ROOT / 'examples/polyglot-demo')
    with tempfile.TemporaryDirectory(prefix='columbus delivery ') as temporary:
        scratch = Path(temporary)
        repo = scratch / 'repository'
        for name, data in sources.items():
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        log = scratch / 'queries.jsonl'

        def run(*args: str) -> str:
            result = subprocess.run([sys.executable, str(COLUMBUS), '--repo', str(repo), *args],
                                    capture_output=True, text=True, encoding='utf-8', check=True)
            return result.stdout

        index = json.loads(run('sync'))
        if not index['files'] or not index['symbols']:
            raise ValueError('Empty fixture index cannot support a delivery comparison')
        rows = []

        def query(*args: str, **labels) -> str:
            output = run(*args, '--snapshot', '--telemetry', str(log))
            record = json.loads(log.read_text(encoding='utf-8').splitlines()[-1])
            if record['output_bytes'] != len(output.encode('utf-8')):
                raise ValueError('Telemetry does not match captured CLI bytes')
            rows.append({**labels, **{key: record[key] for key in
                         ('command', 'format', 'output_bytes', 'returned_items', 'source_bytes',
                          'seen_candidates', 'omitted_candidates', 'truncated')}})
            return output

        # A generous budget ensures the two renderers select the same map IDs.
        structured = json.loads(query('map', '--format', 'json', '--budget-bytes', '30000', '--budget-tokens', '10000',
                                      comparison='same_map'))
        plain = query('map', '--format', 'text', '--budget-bytes', '30000', '--budget-tokens', '10000', comparison='same_map')
        expected_ids = [item['id'] for item in structured['items']]
        actual_ids = [line.split(' | ', 1)[0] for line in plain.splitlines() if ' | ' in line]
        if structured['truncated'] or rows[-1]['truncated'] or expected_ids != actual_ids:
            raise ValueError('Format comparison did not preserve the complete ordered map IDs')
        for output_format in ('json', 'text'):
            query('map', '--format', output_format, '--budget-tokens', '2000', comparison='same_budget')
            if rows[-1]['output_bytes'] > 6000:
                raise ValueError('CLI map exceeded the complete response budget')
        for with_receipt in (False, True):
            for call in range(1, 4):
                receipt_args = ['--receipt', str(scratch / 'receipt.json')] if with_receipt else []
                query('context', 'checkout', '--format', 'text', '--budget-tokens', '2000',
                      *receipt_args, comparison='repeated_context', receipt=with_receipt, call=call)
                if rows[-1]['output_bytes'] > 6000:
                    raise ValueError('CLI context exceeded the complete response budget')
        if rows[-1]['source_bytes'] != 0:
            raise ValueError('The small checkout example did not exhaust its source receipt')
        warm = json.loads(run('sync'))['refresh']
        return {'schema': 'columbus.delivery-observation/v1',
                'fixture': 'examples/polyglot-demo',
                'fixture_files': {name: hashlib.sha256(data).hexdigest() for name, data in sources.items()},
                'engine_version': json.loads((ROOT / 'skills/columbus/bundle.json').read_text())['version'],
                'engine_files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted((COLUMBUS.parent / 'columbus').glob('*.py'))},
                'index': {key: index[key] for key in ('files', 'symbols', 'edges', 'indexed_bytes')},
                'same_map_ids': expected_ids, 'rows': rows,
                'warm_sync': {key: warm[key] for key in ('parsed_files', 'hashed_files', 'hashed_bytes')},
                'note': 'Captured UTF-8 CLI bytes, not model tokens or billing. Same-map renderers preserve '
                        'ordered IDs, not every JSON metadata field. Repeated context uses the same query '
                        'three times; receipt continuation can reveal additional source.'}


if __name__ == '__main__':
    print(json.dumps(observe(), ensure_ascii=False, indent=2))
