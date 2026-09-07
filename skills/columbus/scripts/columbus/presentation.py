"""Compact agent-readable output; repository values always remain untrusted data."""
from __future__ import annotations

import json


def _line(value) -> str:
    """Keep source labels on one line and neutralize terminal control characters."""
    escapes = {number: f'\\u{number:04x}' for number in range(32)}
    escapes.update({9: '\\t', 10: '\\n', 13: '\\r', 127: '\\u007f'})
    return str(value).translate(escapes)


def caller_text(packet: dict) -> str:
    lines = [f"columbus callers target={_line(packet['target'])}",
             f"revision={_line(packet['revision'])} freshness={_line(packet['freshness'])}",
             f"matched_callers={packet['matched_callers']} included={len(packet['items'])} "
             f"truncated={str(packet['truncated']).lower()} target_partial={str(packet['target_partial']).lower()}",
             f"semantic_complete=false repository_unresolved_references={packet['repository_unresolved_references']} "
             f"repository_diagnostic_count={packet['repository_diagnostic_count']}",
             'UNTRUSTED repository data; missing edges do not prove absence of callers. Control characters are escaped.']
    for item in packet['items']:
        lines.append(f"{_line(item['id'])} | {_line(item['path'])}:{item['start_line']}-{item['end_line']} "
                     f"qualname={_line(item['qualname'])} partial={str(item['partial']).lower()}")
        lines.append(f"call_line={item['call_line']} call_sites={item['call_sites']} "
                     f"confidence={_line(','.join(item['confidence']))} source_hash={item['source_hash']}")
        lines.extend(f"{number}| {_line(line)}" for number, line in
                     enumerate(item['source'].splitlines(), item['start_line']))
    return '\n'.join(lines) + '\n'


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
                     f"repository_unresolved_references={packet.get('repository_unresolved_references', 'unknown')} "
                     f"repository_diagnostic_count={packet.get('repository_diagnostic_count', 'unknown')}")
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
        return caller_text(packet) if command == 'callers' else text_output(packet, command)
    if output_format != 'json':
        raise ValueError('output_format must be json or text')
    return json.dumps(packet, ensure_ascii=False, separators=(',', ':'))


def sync_summary(status: dict) -> dict:
    """Constant-shape agent receipt; full status remains available on request."""
    keys = ('revision', 'schema_version', 'analyzer_version', 'freshness', 'last_sync_check',
            'files', 'symbols', 'edges', 'indexed_bytes', 'references',
            'resolved_references', 'unresolved_references')
    result = {key: status[key] for key in keys if key in status}
    result.update(summary=True, semantic_complete=False,
                  diagnostic_count=len(status.get('diagnostics', [])),
                  details_omitted=True)
    refresh = status.get('refresh', {})
    result['refresh'] = {key: refresh[key] for key in (
        'mode', 'check', 'parsed_files', 'cached_parses_loaded', 'reused_files',
        'metadata_reused_files', 'added_files', 'removed_files', 'hashed_files',
        'hashed_bytes', 'config_hashed_files', 'config_hashed_bytes',
        'global_relink', 'elapsed_seconds') if key in refresh}
    inventory = status.get('inventory', {})
    result['inventory'] = {key: inventory[key] for key in (
        'candidate_files', 'excluded_files', 'probe_files', 'probe_bytes') if key in inventory}
    result['inventory'].update(oversized_files=len(inventory.get('oversized_paths', [])),
                               binary_files=len(inventory.get('binary_paths', [])))
    if 'stale_paths' in status:
        result.update(stale_files=len(status['stale_paths']),
                      stale_config_files=len(status.get('stale_config_paths', [])),
                      stale_reasons=status.get('stale_reasons', []))
    return result
