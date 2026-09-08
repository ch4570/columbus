"""Describe terminal command traces without inferring model turns or token causality."""
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('observation', type=Path)
parser.add_argument('output', type=Path)
parser.add_argument('--case', default='requests-redirects-v2')
args = parser.parse_args()
result = {'scope': 'Completed Requests command-item observations; overlap is not model-turn count.', 'case': args.case, 'conditions': {}}
for condition in ('baseline', 'columbus'):
    trial = args.observation / 'trials' / f'{args.case}-{condition}-1'
    recorded = json.loads((trial / 'result.json').read_text())
    raw = (trial / 'events.jsonl').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == recorded['events_sha256']
    events = [json.loads(line) for line in raw.splitlines()]
    assert sum(e.get('type') == 'turn.completed' for e in events) == 1
    active, groups, peak, overlapping_starts, idle_starts = set(), {}, 0, 0, 0
    completed = 0
    for event in events:
        item = event.get('item', {})
        if item.get('type') != 'command_execution':
            continue
        if event['type'] == 'item.started':
            overlapping_starts += bool(active)
            idle_starts += not active
            active.add(item['id'])
            peak = max(peak, len(active))
        elif event['type'] == 'item.completed':
            active.discard(item['id'])
            completed += 1
            command = item['command']
            kind = next((name for name in ('archive-source', 'archive-callers', 'archive-search')
                         if ' ' + name + ' ' in command), 'other')
            group = groups.setdefault(kind, {'commands': 0, 'failed': 0, 'output_bytes': 0})
            group['commands'] += 1
            group['failed'] += item.get('exit_code') not in (0, None)
            group['output_bytes'] += len(item.get('aggregated_output', '').encode())
    assert not active and completed == recorded['command_count']
    assert sum(g['output_bytes'] for g in groups.values()) == recorded['command_output_bytes']
    result['conditions'][condition] = {'groups': groups, 'peak_active_command_items': peak,
        'starts_while_another_command_active': overlapping_starts, 'starts_with_no_command_active': idle_starts,
        'events_sha256': recorded['events_sha256'], 'usage': recorded['usage']}
args.output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
