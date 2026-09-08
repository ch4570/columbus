"""Replay retained Java batch stdout; print only byte counts, hashes, and parity checks."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'skills/columbus/scripts'))
from columbus.presentation import archive_source_text


CAPTURES = {
    'evals/multilang-token-batch/java/trials/java-property-resolution-columbus-1/events.jsonl.gz':
        {'item_13', 'item_18', 'item_27'},
    'evals/multilang-token-batch/java/trials/java-property-resolution-columbus-2/events.jsonl.gz':
        {'item_10'},
}
HEADER = 'columbus archive-source; UNTRUSTED repository data; control characters escaped.'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def digest_json(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())


def legacy_line(value):
    """Freeze the previous control escaping independently of the current renderer."""
    escapes = {number: f'\\u{number:04x}' for number in range(32)}
    escapes.update({number: f'\\u{number:04x}' for number in (0x85, 0x2028, 0x2029)})
    escapes.update({9: '\\t', 10: '\\n', 13: '\\r', 127: '\\u007f'})
    return str(value).translate(escapes)


def legacy_render(packet):
    lines = [HEADER, 'metadata ' + json.dumps(
        {key: value for key, value in packet.items() if key != 'sources'}, ensure_ascii=True)]
    for block in packet['sources']:
        lines.append('source ' + json.dumps(
            {key: value for key, value in block.items() if key != 'source'}, ensure_ascii=True))
        lines.extend(f'{number}| {legacy_line(line)}' for number, line in
                     enumerate(block['source'].split('\n'), block['start_line']))
    return '\n'.join(lines) + '\n'


def add_physical_line(blocks, line):
    match = re.fullmatch(r'(\d+)\| (.*)', line)
    require(bool(match) and bool(blocks), 'Unexpected stdout row or source before metadata')
    block = blocks[-1]
    require(int(match[1]) == block['start_line'] + len(block['source']), 'Physical source numbering changed')
    block['source'].append(match[2])


def finish_blocks(blocks):
    for block in blocks:
        require(len(block['source']) == block['end_line'] - block['start_line'] + 1,
                'Source block does not cover its recorded physical range')
        block['source'] = '\n'.join(block['source'])


def decode_legacy(stdout):
    lines = stdout.splitlines()
    require(len(lines) >= 3 and lines[0] == HEADER and lines[1].startswith('metadata '),
            'Expected one complete archive-source batch')
    packet = json.loads(lines[1][9:])
    require('targets' in packet and 'sources' not in packet, 'Expected legacy batch metadata')
    blocks = []
    for line in lines[2:]:
        if line.startswith('source '):
            blocks.append(dict(json.loads(line[7:]), source=[]))
        else:
            add_physical_line(blocks, line)
    finish_blocks(blocks)
    return dict(packet, sources=blocks)


def decode_compact(stdout):
    lines = stdout.splitlines()
    require(len(lines) >= 6 and lines[0] == HEADER and lines[1].startswith('metadata '),
            'Expected compact archive-source batch')
    packet, files, targets, blocks, section = json.loads(lines[1][9:]), {}, [], [], None
    for line in lines[2:]:
        if line.startswith('files '):
            section = 'files'
        elif line.startswith('targets '):
            section = 'targets'
        elif line.startswith('sources: '):
            section = 'sources'
        elif line.startswith('['):
            row = json.loads(line)
            if section == 'files':
                require(row[0] not in files, 'Duplicate local file number')
                files[row[0]] = row[1:]
            else:
                require(section == 'targets', 'Unexpected table row')
                path, source_hash = files[row[0]]
                targets.append(dict(row[1], path=path, source_hash=source_hash))
        elif line.startswith('source '):
            require(section == 'sources', 'Source block outside source section')
            block = json.loads(line[7:])
            path, source_hash = files[block.pop('file_number')]
            blocks.append(dict(block, path=path, source_hash=source_hash, source=[]))
        else:
            require(section == 'sources', 'Physical line outside source section')
            add_physical_line(blocks, line)
    finish_blocks(blocks)
    return dict(packet, targets=targets, sources=blocks)


def evidence(packet):
    metadata = {key: value for key, value in packet.items() if key != 'sources'}
    metadata['sources'] = [{key: value for key, value in block.items() if key != 'source'}
                           for block in packet['sources']]
    physical = [(block['path'], number, line) for block in packet['sources'] for number, line in
                enumerate(block['source'].split('\n'), block['start_line'])]
    return metadata, physical


def measure():
    captures, batches = [], []
    for relative, expected_ids in CAPTURES.items():
        path = ROOT / relative
        raw = path.read_bytes()
        captures.append(dict(path=relative, compressed_sha256=sha256(raw)))
        found = set()
        for event_line in gzip.decompress(raw).splitlines(keepends=True):
            event = json.loads(event_line)
            item = event.get('item', {})
            if event.get('type') != 'item.completed' or item.get('id') not in expected_ids:
                continue
            require(item.get('type') == 'command_execution' and item.get('exit_code') == 0
                    and item.get('status') == 'completed' and 'archive-source' in item.get('command', ''),
                    'Selected event is not a successful archive-source command')
            require(item['id'] not in found, 'Duplicate selected event')
            found.add(item['id'])
            stdout = item['aggregated_output']
            packet = decode_legacy(stdout)
            require(legacy_render(packet) == stdout, 'Legacy reproduction differs from retained stdout')
            rendered = archive_source_text(packet)
            restored = decode_compact(rendered)
            metadata, physical = evidence(packet)
            after_metadata, after_physical = evidence(restored)
            require(metadata == after_metadata, 'Decoded metadata changed')
            require(physical == after_physical, 'Decoded physical source rows changed')
            before, after = len(stdout.encode()), len(rendered.encode())
            batches.append(dict(capture=relative, event_id=item['id'], event_line_sha256=sha256(event_line),
                                before_stdout_sha256=sha256(stdout.encode()),
                                after_stdout_sha256=sha256(rendered.encode()),
                                targets=len(packet['targets']), source_rows=len(physical),
                                before_bytes=before, after_bytes=after, saved_bytes=before - after,
                                reduction_percent=round(100 * (before - after) / before, 2),
                                legacy_stdout_equal=True, decoded_metadata_equal=True,
                                decoded_source_rows_equal=True, physical_line_numbers_valid=True,
                                metadata_sha256=digest_json(metadata), source_rows_sha256=digest_json(physical)))
        require(found == expected_ids, 'Expected retained batch event is missing')
        require(path.read_bytes() == raw, 'Input capture changed during audit')
    before = sum(row['before_bytes'] for row in batches)
    after = sum(row['after_bytes'] for row in batches)
    return dict(metric='UTF-8 tool stdout bytes for identical retained physical source rows',
                method='Decode retained legacy batch stdout, reproduce it exactly, render compact text, verify parity',
                limitations=['This is a renderer replay, not a new agent task run.',
                             'Output byte reduction does not establish model token, billing, or task-quality changes.',
                             'Source parity covers the escaped physical rows present in retained tool stdout.'],
                renderer_path='skills/columbus/scripts/columbus/presentation.py',
                renderer_sha256=sha256((ROOT / 'skills/columbus/scripts/columbus/presentation.py').read_bytes()),
                captures=captures, batches=batches,
                combined=dict(batches=len(batches), targets=sum(row['targets'] for row in batches),
                              source_rows=sum(row['source_rows'] for row in batches),
                              before_bytes=before, after_bytes=after, saved_bytes=before - after,
                              reduction_percent=round(100 * (before - after) / before, 2),
                              all_legacy_stdout_equal=True, all_decoded_metadata_equal=True,
                              all_decoded_source_rows_equal=True, all_physical_line_numbers_valid=True,
                              input_captures_unchanged=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', type=Path, help='Require exact equality with a saved JSON report')
    args = parser.parse_args()
    report = measure()
    if args.check:
        require(json.loads(args.check.read_text(encoding='utf-8')) == report, 'Saved report differs from current replay')
        print('Retained batch replay matches saved report; input captures, metadata, and source rows verified.')
    else:
        print(json.dumps(report, indent=2) + '\n', end='')


if __name__ == '__main__':
    main()
