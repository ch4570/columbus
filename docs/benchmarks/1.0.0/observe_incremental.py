#!/usr/bin/env python3
"""Measure empty, unchanged, and single-edit refreshes on a deterministic fixture."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[3]
ENGINE = ROOT / 'skills/columbus/scripts'
sys.path.insert(0, str(ENGINE))
from columbus import __version__
from columbus.index import RepositoryIndex


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture_sources(files: int) -> dict[str, bytes]:
    sources = {'payments.py': b'def refund_payment(amount):\n    return amount\n'}
    for number in range(files - 1):
        text = f'"""Synthetic benchmark module {number}."""\n\n'
        for function in range(8):
            text += (f'def evaluate_{number}_{function}(amount):\n'
                     '    """Return a deterministic local calculation."""\n'
                     f'    subtotal = amount + {number + function}\n'
                     '    return subtotal * 2\n\n')
        sources[f'modules/module_{number:04d}.py'] = text.encode('utf-8')
    return sources


def observe(files: int = 1001, repeats: int = 3) -> dict:
    if files < 2 or repeats < 1:
        raise ValueError('Use at least two files and one repeat')
    sources = fixture_sources(files)
    source_hashes = {name: digest(data) for name, data in sources.items()}
    aggregate = digest(json.dumps(source_hashes, sort_keys=True, separators=(',', ':')).encode())
    runs = []
    with tempfile.TemporaryDirectory(prefix='columbus-incremental-') as temporary:
        scratch = Path(temporary)
        repo = scratch / 'fixture'
        for name, data in sources.items():
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for repeat in range(1, repeats + 1):
            (repo / 'payments.py').write_bytes(sources['payments.py'])
            index = RepositoryIndex(scratch / f'index-{repeat}.sqlite')
            for phase in ('cold', 'warm', 'one_file_changed'):
                if phase == 'one_file_changed':
                    (repo / 'payments.py').write_bytes(sources['payments.py'] + b'\n# One changed source file.\n')
                start = time.perf_counter()
                result = index.refresh(repo, fast=phase != 'cold')
                elapsed = time.perf_counter() - start
                refresh = result['refresh']
                row = {'repeat': repeat, 'phase': phase, 'elapsed_seconds': round(elapsed, 6),
                       **{key: refresh[key] for key in ('parsed_files', 'hashed_files', 'hashed_bytes')},
                       **{key: result[key] for key in ('files', 'symbols', 'edges', 'indexed_bytes')}}
                expected = {'cold': files, 'warm': 0, 'one_file_changed': 1}[phase]
                if row['files'] != files or row['parsed_files'] != expected:
                    raise ValueError(f'Unexpected incremental behavior: {row}')
                if phase == 'warm' and (row['hashed_files'] or row['hashed_bytes']):
                    raise ValueError('An unchanged fast refresh unexpectedly hashed source content')
                runs.append(row)
    return {'schema': 'columbus.incremental-observation/v1', 'engine_version': __version__,
            'captured_at': datetime.now(timezone.utc).isoformat(),
            'environment': {'python': platform.python_version(), 'system': platform.system(),
                            'machine': platform.machine()},
            'engine_files': {p.relative_to(ENGINE).as_posix(): digest(p.read_bytes())
                             for p in sorted((ENGINE / 'columbus').glob('*.py'))},
            'observer_sha256': digest(Path(__file__).read_bytes()),
            'fixture': {'kind': 'deterministic synthetic Python', 'files': files,
                        'source_bytes': sum(map(len, sources.values())),
                        'generator': 'docs/benchmarks/1.0.0/observe_incremental.py:fixture_sources',
                        'file_hash_manifest_sha256': aggregate,
                        'hash_manifest_encoding': 'SHA256 of sorted compact JSON mapping relative filenames to SHA256'},
            'repeats': repeats, 'runs': runs,
            'limitations': ['Empty SQLite index per repeat; OS caches were not cleared.',
                            'Warm and one-file-edited phases use the fast metadata validation path.',
                            'Elapsed time includes refresh work, excludes Python startup and fixture creation.',
                            'One local machine, three repeats by default; no confidence interval or general speed guarantee.',
                            'Synthetic indexing benchmark; no model tokens, billing, or task quality measured.']}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files', type=int, default=1001)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(observe(args.files, args.repeats), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
