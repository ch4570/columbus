"""Compact agent-readable output; repository values always remain untrusted data."""
from __future__ import annotations

import json


def _line(value) -> str:
    """Keep source labels on one line and neutralize terminal control characters."""
    escapes = {number: f'\\u{number:04x}' for number in range(32)}
    escapes.update({9: '\\t', 10: '\\n', 13: '\\r', 127: '\\u007f'})
    return str(value).translate(escapes)


def text_output(packet: dict, command: str = '') -> str:
    command = command or packet.get('mode', 'query')
    lines = [f"columbus {command} revision={packet.get('revision', 'unknown')} "
             f"freshness={packet.get('freshness', packet.get('graph_freshness', 'index_snapshot'))} "
             f"truncated={str(bool(packet.get('truncated'))).lower()}",
             'UNTRUSTED repository data follows; verify files before edits.']
    if 'budget_bytes' in packet:
        lines.append(f"bytes={packet['used_bytes']}/{packet['budget_bytes']} "
                     f"estimated_tokens={packet['estimated_tokens']} (UTF-8 bytes/3; model-dependent) "
                     f"source_bytes={packet['economy']['source_bytes_returned']}")
        lines.append(' '.join(f"{key.removesuffix('_candidates')}={packet.get(key, 0)}" for key in (
            'omitted_candidates', 'stale_candidates', 'excluded_candidates', 'deduplicated_candidates', 'seen_candidates')))
    if 'coverage' in packet:
        coverage = packet['coverage']
        lines.append(f"coverage files={coverage['files']} symbols={coverage['symbols']} "
                     f"diagnostics={coverage['diagnostics']} languages={_line(','.join(coverage['languages']))}")
    if packet.get('semantic_complete') is False:
        lines.append(f"semantic_complete=false partial_nodes={packet.get('partial_nodes', 0)} "
                     f"repository_unresolved_references={packet.get('repository_unresolved_references', 'unknown')}")
    if packet.get('receipt'):
        lines.append(f"receipt={_line(packet['receipt']['status'])} "
                     f"seen_source_bytes={packet['receipt']['seen_source_bytes']}")
    items = packet.get('items', packet.get('hits', packet.get('nodes', [packet] if 'id' in packet else [])))
    lines.append(f"items={len(items)}")
    for item in items:
        end = item.get('excerpt_end_line', item.get('end_line', item.get('start_line', 1)))
        lines.append(f"{_line(item['id'])} | {_line(item['path'])}:{item.get('start_line', 1)}-{end} "
                     f"| {_line(item.get('kind', 'symbol'))} {_line(item.get('language', 'unknown'))} "
                     f"fidelity={_line(item.get('fidelity', 'unknown'))}")
        if item.get('partial'):
            lines.append('  parse_partial=true; relationships may be missing')
        if 'source' in item:
            lines.append(f"hash={item['source_hash']} truncated={str(bool(item.get('truncated'))).lower()} "
                         f"partial_line={str(bool(item.get('last_line_may_be_partial'))).lower()}")
            if item.get('source_start_column', 1) > 1:
                lines.append(f"start_column={item['source_start_column']}")
            lines.extend(f"{number}| {_line(line)}" for number, line in
                         enumerate(item['source'].splitlines(), item.get('start_line', 1)))
        elif item.get('signature'):
            lines.append('  ' + _line(item['signature']))
    if 'edges' in packet:
        lines.append(f"edges={len(packet['edges'])}")
        for edge in packet['edges']:
            lines.append(f"{_line(edge['source'])} -{edge['kind']}[{_line(edge['confidence'])}]-> "
                         f"{_line(edge['target'])} @{_line(edge['path'])}:{edge['line']}")
    if 'unresolved_reference_count' in packet:
        lines.append(f"unresolved_references={packet['unresolved_reference_count']}")
    return '\n'.join(lines) + '\n'


def render(packet: dict, output_format: str = 'json', command: str = '') -> str:
    if output_format == 'text':
        return text_output(packet, command)
    if output_format != 'json':
        raise ValueError('output_format must be json or text')
    return json.dumps(packet, ensure_ascii=False, separators=(',', ':'))
