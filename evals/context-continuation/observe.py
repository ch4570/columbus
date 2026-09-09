#!/usr/bin/env python3
"""Compare bounded receipt continuation without invoking any model or service."""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = Path('skills/columbus/scripts/columbus')
BASELINE = '7f4bb077c38eb5b64b8ef06448d36a2f1c399c98'
BUDGET = 2048


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*arguments):
    return subprocess.run(['git', '-C', str(ROOT), *arguments], check=True, capture_output=True).stdout


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def freeze(destination, revision=None):
    """Copy a complete Python package, retaining the exact bytes used by workers."""
    destination.mkdir(parents=True)
    commit = git('rev-parse', revision or 'HEAD').decode().strip()
    if revision:
        names = [Path(name) for name in git('ls-tree', '-r', '--name-only', commit, '--', PACKAGE.as_posix()).decode().splitlines()
                 if name.endswith('.py')]
        contents = {name.relative_to(PACKAGE).as_posix(): git('show', f'{commit}:{name.as_posix()}') for name in names}
    else:
        contents = {name.relative_to(ROOT / PACKAGE).as_posix(): name.read_bytes()
                    for name in (ROOT / PACKAGE).rglob('*.py')}
    if '__init__.py' not in contents or 'index.py' not in contents:
        raise ValueError('Selected revision does not contain the Columbus engine')
    for name, data in contents.items():
        target = destination / 'columbus' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    hashes = {name: sha(data) for name, data in sorted(contents.items())}
    result = {'selection': 'commit' if revision else 'working_tree_snapshot',
              'commit': commit if revision else None, 'base_commit': commit,
              'package_sha256': sha(canonical(hashes)), 'files': hashes}
    if not revision:
        result['package_git_status'] = git('status', '--porcelain', '--', PACKAGE.as_posix()).decode().splitlines()
        result['source_unchanged_during_freeze'] = all((ROOT / PACKAGE / name).read_bytes() == data for name, data in contents.items())
        if not result['source_unchanged_during_freeze']:
            raise ValueError('Candidate package changed while it was being frozen; retry after edits finish')
    return result


def worker(args):
    sys.path.insert(0, str(Path(args.engine).resolve()))
    from columbus import __version__
    from columbus.cli import main
    from columbus.index import RepositoryIndex
    from columbus.presentation import render
    from columbus.receipts import ReceiptFile

    with tempfile.TemporaryDirectory(prefix='columbus-context-fixture-') as directory:
        root = Path(directory)
        contents = {f'entry_{number:03d}.py': f'def target():\n    return "TARGET_{number:03d}"\n'
                    for number in range(args.count)}
        for name, source in contents.items():
            (root / name).write_text(source, encoding='utf-8', newline='\n')
        subprocess.run(['git', 'init', '-q', str(root)], check=True, capture_output=True)
        hashes = {name: sha(source.encode()) for name, source in contents.items()}
        index = RepositoryIndex(root / '.columbus/index.sqlite')
        started = time.perf_counter()
        status = index.refresh(root)
        preparation_seconds = time.perf_counter() - started
        if status['files'] != args.count:
            raise ValueError('Fixture index does not cover every requested source file')
        receipt_path = root / '.columbus/receipt.json'
        delivered = {name: set() for name in contents}
        expected = {name: {position for position, character in enumerate(source) if character != '\n'}
                    for name, source in contents.items()}
        records, source_errors, overlap = [], [], 0
        first_output, stalled = None, 0
        terminal = 'iteration_limit'
        for attempt in range(1, args.count * 6 + 31):
            receipt = ReceiptFile(str(receipt_path), index.status())
            before = dict(receipt.data.get('continuations', {}))
            packet = index.context('target', budget_bytes=BUDGET, output_format=args.output_format, receipt=receipt.data)
            output = render(packet, args.output_format)
            if first_output is None:
                first_output = output
            size = len(output.encode('utf-8'))
            if size > BUDGET or packet['used_bytes'] != size:
                raise ValueError('Serialized response violates its complete output budget/accounting')
            for item in packet['items']:
                name = item['path']
                start, stop = item['source_start_offset'], item['source_end_offset']
                if (name not in contents or item['source_hash'] != hashes[name]
                        or not 0 <= start < stop <= len(contents[name])
                        or contents[name][start:stop] != item['source']):
                    source_errors.append({'path': name, 'start': start, 'stop': stop})
                    continue
                positions = set(range(start, stop))
                overlap += len(delivered[name] & positions)
                delivered[name].update(positions)
            receipt.save(packet)
            after = json.loads(receipt_path.read_text(encoding='utf-8')).get('continuations', {})
            complete = [name for name in contents if expected[name] <= delivered[name]]
            records.append({'attempt': attempt, 'items': len(packet['items']), 'response_bytes': size,
                            'response_sha256': sha(output.encode('utf-8')),
                            'source_bytes': packet['economy']['source_bytes_returned'],
                            'complete_files': len(complete), 'omitted_candidates': packet['omitted_candidates'],
                            'seen_candidates': packet.get('seen_candidates', 0),
                            'stale_candidates': packet['stale_candidates'], 'truncated': packet['truncated'],
                            'receipt_has_more': packet.get('receipt', {}).get('has_more'),
                            'cursor_changed': before != after})
            if not packet['items']:
                if len(complete) == args.count and not packet['truncated']:
                    terminal = 'exhausted_complete_source'
                    break
                stalled = 0 if before != after else stalled + 1
                if stalled >= 2:
                    terminal = 'stalled_with_unread_source'
                    break
            else:
                stalled = 0
        # Verify the API packet matches the installed CLI's first, snapshot
        # receipt call. This separate validation probe is not part of totals.
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(['--repo', str(root), '--db', str(index.db), 'context', 'target', '--snapshot',
                         '--format', args.output_format, '--budget-bytes', str(BUDGET),
                         '--receipt', str(root / '.columbus/cli-probe.json')])
        unchanged = all(sha((root / name).read_bytes()) == digest for name, digest in hashes.items())
        complete = [name for name in contents if expected[name] <= delivered[name]]
        checks = {'source_offsets_and_hashes_match': not source_errors, 'no_repeated_source_characters': overlap == 0,
                  'all_responses_within_budget': all(row['response_bytes'] <= BUDGET for row in records),
                  'source_unchanged': unchanged, 'cli_first_response_matches_api': code == 0 and stdout.getvalue() == first_output}
        result = {'engine_version': __version__, 'format': args.output_format, 'declarations': args.count,
                  'budget_bytes': BUDGET, 'query': 'target', 'fixture_sha256': sha(canonical(hashes)),
                  'fixture_files': hashes, 'index_files': status['files'], 'index_symbols': status['symbols'],
                  'revision': status['revision'], 'preparation_seconds': round(preparation_seconds, 6),
                  'terminal': terminal, 'context_calls': len(records),
                  'response_bytes_total': sum(row['response_bytes'] for row in records),
                  'source_bytes_total': sum(row['source_bytes'] for row in records),
                  'complete_source_files': len(complete), 'missing_source_files': sorted(set(contents) - set(complete)),
                  'expected_nonnewline_characters': sum(map(len, expected.values())),
                  'covered_nonnewline_characters': sum(len(expected[name] & delivered[name]) for name in contents),
                  'repeated_source_characters': overlap, 'checks': checks,
                  'cli_validation_probe': {'count': 1, 'status': code, 'stderr': stderr.getvalue()}, 'calls': records}
        print(json.dumps(result, ensure_ascii=False))
        return 0 if all(checks.values()) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', default=BASELINE)
    parser.add_argument('--candidate-ref', help='Freeze a committed candidate; default freezes current package bytes')
    parser.add_argument('--large', action='store_true', help='Also cover 175 independent declarations, beyond the former 150 cap')
    parser.add_argument('--output', type=Path, help='Write a new JSON evidence file; existing files are preserved')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--engine', help=argparse.SUPPRESS)
    parser.add_argument('--count', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--output-format', choices=('json', 'text'), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    if args.output and args.output.exists():
        parser.error('Output already exists; choose a new evidence path')
    result = {'schema': 'columbus.context-continuation-observation/v1',
              'generated_utc': datetime.now(timezone.utc).isoformat(),
              'harness_sha256': sha(Path(__file__).read_bytes()), 'python': platform.python_version(),
              'platform': platform.platform(), 'model_calls': 0,
              'protocol': 'Repeated API context calls with the same saved receipt; one separate first-call CLI parity probe per condition.',
              'measurement_limit': 'Serialized payloads and source coverage only; no actual model tokens, billing or task-answer quality measured.',
              'conditions': {}}
    with tempfile.TemporaryDirectory(prefix='columbus-context-engines-') as directory:
        scratch = Path(directory)
        for condition, revision in [('baseline', args.baseline_ref), ('candidate', args.candidate_ref)]:
            engine = scratch / condition
            provenance = freeze(engine, revision)
            measurements = []
            for count in ([30, 175] if args.large else [30]):
                for output_format in ('json', 'text'):
                    invocation = [sys.executable, str(Path(__file__).resolve()), '--worker', '--engine', str(engine),
                                  '--count', str(count), '--output-format', output_format]
                    completed = subprocess.run(invocation, check=True, capture_output=True, text=True)
                    measurements.append(json.loads(completed.stdout))
            result['conditions'][condition] = {'engine': provenance, 'measurements': measurements}
    baseline = result['conditions']['baseline']['measurements']
    candidate = result['conditions']['candidate']['measurements']
    result['verified'] = (all(row['terminal'] == 'stalled_with_unread_source' and row['complete_source_files'] == 20 for row in baseline)
                          and all(row['terminal'] == 'exhausted_complete_source' and row['complete_source_files'] == row['declarations'] for row in candidate)
                          and all(all(row['checks'].values()) for row in baseline + candidate))
    output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(output)
        print(json.dumps({'output': str(args.output), 'verified': result['verified'], 'model_calls': 0}))
    else:
        print(output, end='')
    return 0 if result['verified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
