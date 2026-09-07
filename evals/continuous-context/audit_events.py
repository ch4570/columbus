"""Validate continued Codex event captures without guessing usage semantics."""
import argparse
import hashlib
import json
from pathlib import Path
import uuid


def audit(paths: list[Path]) -> dict:
    if not paths:
        raise ValueError('At least one complete event capture is required')
    thread_id = None
    seen_hashes = set()
    turns = []
    for path in paths:
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest in seen_hashes:
            raise ValueError('Duplicate event capture would count a turn twice')
        seen_hashes.add(digest)
        events = [json.loads(line) for line in raw.splitlines() if line.strip()]
        if any(not isinstance(e, dict) for e in events):
            raise ValueError('Events must be JSON objects')
        starts = [(i, e) for i, e in enumerate(events) if e.get('type') == 'thread.started']
        begins = [i for i, e in enumerate(events) if e.get('type') == 'turn.started']
        finishes = [(i, e) for i, e in enumerate(events) if e.get('type') == 'turn.completed']
        if (len(starts) != 1 or len(begins) != 1 or len(finishes) != 1
                or any(e.get('type') in {'turn.failed', 'error'} for e in events)):
            raise ValueError('Capture must contain one successful complete turn')
        current = starts[0][1].get('thread_id')
        if not isinstance(current, str) or str(uuid.UUID(current)) != current:
            raise ValueError('A canonical recorded thread UUID is required')
        if thread_id is not None and current != thread_id:
            raise ValueError('Different threads cannot represent retained agent memory')
        thread_id = current
        if not starts[0][0] < begins[0] < finishes[0][0] == len(events) - 1:
            raise ValueError('Unexpected event order or data after terminal completion')
        usage = finishes[0][1].get('usage')
        if not isinstance(usage, dict):
            raise ValueError('Completed turn has no runtime usage')
        for key in ['input_tokens', 'cached_input_tokens', 'output_tokens']:
            if type(usage.get(key)) is not int or usage[key] < 0:
                raise ValueError('Invalid runtime usage counter')
        if usage['cached_input_tokens'] > usage['input_tokens']:
            raise ValueError('Cached tokens must be a subset of input')
        turns.append({'capture': str(path), 'sha256': digest, 'reported_usage': usage})
    return {'thread_id': thread_id, 'captures': turns, 'same_thread': True,
            'usage_aggregation': 'unproven; raw counters retained without summing',
            'limitations': ['Thread identity does not prove source retention after compaction.',
                            'Quality, source immutability and usage counter semantics need separate gates.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('captures', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.captures)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
