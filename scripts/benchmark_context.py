#!/usr/bin/env python3
"""Measure deterministic payload reduction, without making model-cost claims."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/columbus/scripts'))
from columbus.index import RepositoryIndex, byte_size


def benchmark(root: Path, query: str, budget_tokens: int) -> dict:
    with tempfile.TemporaryDirectory(prefix='columbus-benchmark-') as temporary:
        index = RepositoryIndex(Path(temporary) / 'index.sqlite')
        cold = index.refresh(root)
        warm = index.refresh(root, fast=True)
        packets = {'map': index.repo_map(query, budget_tokens=budget_tokens),
                   'signatures': index.context(query, budget_tokens=budget_tokens, mode='signatures'),
                   'snippets': index.context(query, budget_tokens=budget_tokens)}
        measurements = {}
        for name, packet in packets.items():
            size = byte_size(packet)
            assert size == packet['used_bytes'] and size <= packet['budget_bytes']
            measurements[name] = {'response_bytes': size, 'estimated_tokens': packet['estimated_tokens'],
                                  'items': len(packet['items']), 'truncated': packet['truncated'],
                                  'fraction_of_source_bytes': round(size / max(1, cold['indexed_bytes']), 6)}
        return {'fixture': str(root), 'query': query, 'indexed_files': cold['files'],
                'indexed_source_bytes': cold['indexed_bytes'], 'languages': cold['analyzer_fingerprint']['languages'],
                'warm_sync': warm['refresh'], 'packets': measurements,
                'measurement': 'Complete compact JSON UTF-8 bytes versus all indexed source bytes. '
                               'Tokens are estimated as ceil(bytes/3); not observed agent billing or task success.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, help='Omit to use a deterministic 101-file Python fixture')
    parser.add_argument('--query', default='refund_payment')
    parser.add_argument('--budget-tokens', type=int, default=2000)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='columbus-fixture-') as temporary:
        root = args.repo.expanduser().resolve() if args.repo else Path(temporary)
        if not args.repo:
            (root / 'payments.py').write_text('def refund_payment(amount):\n    return amount\n', encoding='utf-8')
            for number in range(100):
                (root / f'unrelated_{number:03d}.py').write_text(
                    f'def unrelated_{number}():\n' + '    # unrelated implementation detail\n' * 100 + '    return 0\n', encoding='utf-8')
        print(json.dumps(benchmark(root, args.query, args.budget_tokens), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
