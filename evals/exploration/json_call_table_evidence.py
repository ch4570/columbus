"""Prospective, independently bound receipts for lossless JSON call tables.

API: evidence(events, *, binding, relationships). The exact seven-key binding
comes from independently frozen inputs, never from the files being assessed.
The unchanged source_call_evidence.py is an explicit dependency for inventory,
archive, source-decoding, declaration-selection and full-packet primitives.
This module owns JSON invocation parsing, table projection, rendering and fitting;
it never imports production selectors/renderers or uses text/full-ID byte bounds.

No runtime/repository code, subprocess, model, configuration or file write is
executed. Invalid frozen inputs raise even for empty streams. Receipts require
complete canonical output; they do not establish authentic execution, semantic
understanding, quotation quality or lower cost. Whole-log/environment/answer and
cohort pre/postflight gates remain the caller's independent responsibility.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import sys


_HELPER_PATH = Path(__file__).resolve().with_name('source_call_evidence.py')
_KEY = '_json_call_table_safe_' + hashlib.sha256(str(_HELPER_PATH).encode()).hexdigest()
if _KEY not in sys.modules:
    _SPEC = importlib.util.spec_from_file_location(_KEY, _HELPER_PATH)
    _MODULE = importlib.util.module_from_spec(_SPEC)
    sys.modules[_KEY] = _MODULE
    try:
        _SPEC.loader.exec_module(_MODULE)
    except BaseException:
        sys.modules.pop(_KEY, None)
        raise
SAFE = sys.modules[_KEY]

VERSION = 'json-call-table-evidence-v1'
WIRE_FORMAT = 'columbus-call-table-json/v1'
_ERRORS = SAFE._ERRORS + (RecursionError, OverflowError)
_SHELLS = {directory + name for directory in ('/bin/', '/usr/bin/')
           for name in ('sh', 'bash', 'zsh')}


def _command(item, snapshot):
    """An explicit JSON table, including default JSON, with exact bound paths."""
    SAFE._require('columbus/source_calls.py' in snapshot.runtime_manifest)
    words = SAFE._shell_words(item['command'])
    if words and words[0] in _SHELLS:
        SAFE._require(len(words) == 3 and words[1] in {'-c', '-lc'})
        words = SAFE._shell_words(words[2])
    SAFE._require(tuple(words[:3]) == snapshot.prefix)
    arguments, seen = words[3:], set()
    valued = {'--repo', '--input', '--offset', '--limit', '--budget-bytes', '--format'}
    flags = {'--call-sites', '--call-table', '--overloads'}
    position = 0
    while position < len(arguments):
        word = arguments[position]
        if word.startswith('-'):
            name, separator, value = word.partition('=')
            SAFE._require(name in valued | flags and name not in seen)
            seen.add(name)
            if name in flags:
                SAFE._require(not separator)
            elif separator:
                SAFE._require(bool(value))
            else:
                position += 1
                SAFE._require(position < len(arguments) and bool(arguments[position]))
        position += 1
    parser = SAFE._Parser(add_help=False, allow_abbrev=False)
    parser.add_argument('--repo')
    command = parser.add_subparsers(dest='operation', required=True).add_parser(
        'archive-source', add_help=False, allow_abbrev=False)
    command.add_argument('--repo', default=SAFE.argparse.SUPPRESS)
    command.add_argument('queries', nargs='+')
    command.add_argument('--input', required=True)
    command.add_argument('--call-sites', action='store_true')
    command.add_argument('--call-table', action='store_true')
    command.add_argument('--overloads', action='store_true')
    command.add_argument('--offset', type=int, default=0)
    command.add_argument('--limit', type=int, default=120)
    command.add_argument('--budget-bytes', type=int, default=12000)
    command.add_argument('--format', choices=['json', 'text'], default='json')
    args = parser.parse_args(arguments)
    SAFE._require(args.call_sites and args.call_table and args.format == 'json'
                  and Path(args.input).is_absolute()
                  and Path(args.input).resolve() == snapshot.archive.resolve()
                  and (snapshot.root / (args.repo or '.')).resolve() == snapshot.root)
    SAFE._require(1 <= len(args.queries) <= 16 and len(set(args.queries)) == len(args.queries)
                  and all(1 <= len(query) <= 2048 for query in args.queries))
    SAFE._integer(args.offset)
    SAFE._integer(args.limit, 1, 400)
    SAFE._integer(args.budget_bytes, 2048, 64000)
    return dict(queries=args.queries, overloads=args.overloads, offset=args.offset,
                limit=args.limit, format=args.format, budget_bytes=args.budget_bytes,
                call_table=True)


def _json(value):
    return SAFE._compact(value).translate(SAFE._ESCAPES)


def _declaration(node):
    return {key: value for key, value in node.items() if key not in {'path', 'source_hash'}}


def _relationship(edge):
    return {key: value for key, value in edge.items() if key not in {'source', 'target', 'path'}}


def _row_bytes(value):
    # JSON-only lower bound: neither text row numbers nor per-row LF/comma.
    return len(_json(value).encode('utf-8'))


def _wire_packet(packet):
    """Keep source exact; share only call paths/hashes and endpoint identities."""
    calls = packet['call_sites']
    SAFE._require(not {'format', 'index_scope', 'files'} & calls.keys(),
                  'Reserved JSON call-table metadata collision')
    nodes = calls['nodes']
    node_index = {node['id']: number for number, node in enumerate(nodes)}
    SAFE._require(len(node_index) == len(nodes))
    files = sorted({(node['path'], node['source_hash']) for node in nodes})
    file_index = {pair: number for number, pair in enumerate(files)}
    table = {key: value for key, value in calls.items() if key not in {'nodes', 'edges'}}
    table.update(format=WIRE_FORMAT, index_scope='this packet',
                 files=[list(pair) for pair in files],
                 nodes=[[file_index[(node['path'], node['source_hash'])], _declaration(node)]
                        for node in nodes], edges=[])
    for edge in calls['edges']:
        owner = nodes[node_index[edge['source']]]
        SAFE._require(owner['path'] == edge['path'])
        table['edges'].append([node_index[edge['source']], node_index[edge['target']],
                               file_index[(owner['path'], owner['source_hash'])], _relationship(edge)])
    return dict(packet, call_sites=table)


def _render(packet):
    return _json(_wire_packet(packet)) + '\n'


def _expected(snapshot, invocation):
    chosen = SAFE._selection(snapshot, invocation)
    selected_paths, total, positions = SAFE._positions(chosen, invocation['offset'], invocation['limit'])
    budget, cap = invocation['budget_bytes'], len(positions)
    # Every edge occurrence, unique endpoint and endpoint file for a line is
    # present in a complete output containing that line. Zero indexes cannot
    # be longer than real nonnegative indexes; omitted JSON punctuation is
    # nonnegative. This is independent of production interning/streaming code.
    for number, position in enumerate(positions):
        edges = snapshot.edges[position]
        identities = {edge[key] for edge in edges for key in ('source', 'target')}
        nodes = [SAFE._descriptor(snapshot, identity, selected_paths) for identity in identities]
        files = {(node['path'], node['source_hash']) for node in nodes}
        cost = sum(_row_bytes([0, 0, 0, _relationship(edge)]) for edge in edges)
        cost += sum(_row_bytes([0, _declaration(node)]) for node in nodes)
        cost += sum(_row_bytes(list(pair)) for pair in files)
        if cost > budget:
            cap = number
            break
    SAFE._require(cap > 0)
    identities = set(chosen) | {edge[key] for position in positions[:cap]
                               for edge in snapshot.edges[position] for key in ('source', 'target')}
    for path in selected_paths:
        snapshot.lines(path)
    for identity in identities:
        node = snapshot.nodes[identity]
        if node['path'] in selected_paths:
            SAFE._require(node['end_line'] <= len(snapshot.lines(node['path'])))
    # Full-source packets and exact final LF count. Never assume monotone byte
    # sizes, skip a next line, or remove a call from a retained physical line.
    for count in range(cap, 0, -1):
        packet = SAFE._packet(snapshot, invocation, chosen, selected_paths, total, positions[:count])
        output = _render(packet)
        if len(output.encode('utf-8')) <= budget:
            return packet, output
    raise ValueError('No complete source line and its JSON call table fit')


def _final_binding(snapshot, binding, captured):
    try:
        SAFE._require(binding == captured, 'Frozen binding object changed')
        snapshot.check()
        SAFE._inventory(snapshot.root, snapshot.sources)
        SAFE._inventory(snapshot.runtime, snapshot.runtime_manifest)
        raw, stamp = SAFE._read(snapshot.archive)
        SAFE._require(stamp == snapshot.archive_stamp and SAFE._sha(raw) == snapshot.archive_hash)
        snapshot.check()
        # This check follows the last I/O, including the closing tree scan.
        SAFE._require(binding == captured, 'Frozen binding object changed')
    except _ERRORS as exc:
        raise ValueError('Frozen JSON call-table inputs changed during recognition') from exc


def evidence(events, *, binding, relationships):
    """Complete JSON delivery and reviewed-edge utility are separate receipts.

    Exact canonical-byte equality checks schema, integer index types/ranges,
    order, multiplicity and decoded source; it cannot accept a partial table.
    Shell wrapping is supported syntax, not attestation of executable bytes.
    """
    try:
        SAFE._require(isinstance(binding, dict)
                      and isinstance(binding.get('source_manifest'), dict)
                      and isinstance(binding.get('runtime_inventory'), dict))
        captured = deepcopy(binding)
        reviewed = SAFE._relationships(relationships)
        snapshot = SAFE._Snapshot(captured)
    except _ERRORS as exc:
        raise ValueError('Invalid frozen JSON call-table evidence inputs') from exc
    source_receipts, relationship_receipts = [], []
    try:
        for event in events:
            if not isinstance(event, dict) or event.get('type') != 'item.completed':
                continue
            item = event.get('item')
            if (not isinstance(item, dict) or item.get('type') != 'command_execution'
                    or not isinstance(item.get('id'), str) or not item['id']
                    or item.get('status') != 'completed' or type(item.get('exit_code')) is not int
                    or item['exit_code'] != 0):
                continue
            try:
                invocation = _command(item, snapshot)
                output = item['aggregated_output']
                SAFE._require(isinstance(output, str)
                              and 0 < len(output.encode('utf-8')) <= invocation['budget_bytes'])
                packet, expected = _expected(snapshot, invocation)
                SAFE._require(output == expected)
                calls = packet['call_sites']
                matched = [relation for relation in reviewed if any(
                    all(edge[key] == value for key, value in relation.items()) for edge in calls['edges'])]
                common = dict(recognizer_version=VERSION, command_id=item['id'], operation='archive-source',
                              delivery_mode='source-call-sites', encoding=WIRE_FORMAT,
                              binding_sha256=snapshot.binding_hash,
                              event_json_sha256=SAFE._sha(SAFE._compact(event).encode('utf-8')),
                              command_sha256=SAFE._sha(item['command'].encode('utf-8')),
                              output_sha256=SAFE._sha(output.encode('utf-8')))
                source_receipts.append(dict(common, invocation=invocation,
                    target_ids=[target['id'] for target in packet['targets']],
                    ranges=[{key: block[key] for key in ('path', 'source_hash', 'start_line', 'end_line')}
                            for block in packet['sources']],
                    source_rows=sum(block['end_line'] - block['start_line'] + 1 for block in packet['sources']),
                    next_offset=packet['next_offset'], total_lines=packet['total_lines'],
                    stored_edges=len(calls['edges']), endpoint_nodes=len(calls['nodes']),
                    resolved_call_reference_count=calls['resolved_call_reference_count'],
                    unresolved_call_reference_count=calls['unresolved_call_reference_count']))
                if matched:
                    relationship_receipts.append(dict(common, relationships=matched))
            except _ERRORS:
                continue
    finally:
        _final_binding(snapshot, binding, captured)
    return dict(recognizer_version=VERSION, json_call_table_used=bool(source_receipts),
                source_call_receipts=source_receipts, relationship_receipts=relationship_receipts,
                relationship_used=bool(relationship_receipts))
