"""Future-only, independently bound receipts for explicit indexed call tables.

Public API: evidence(events, *, binding, relationships). Binding is the exact
source_call_evidence binding: independently frozen repository/runtime inventories,
archive hash/revision and absolute Python -B wrapper prefix. The unchanged older
verifier supplies read/snapshot/selection primitives, never production code.
This module owns command parsing, indexed serialization and format-aware fitting.

No runtime or repository code is imported/executed, no subprocess/model is called,
and no file is written. Bad frozen inputs raise, even for an empty event stream;
unsupported, failed or inconsistent deliveries receive no receipt. Callers still
own authoritative cohort pre/postflight, whole-log execution review, semantic
review, citation grading and cost accounting. This is not a cohort adapter.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import sys


_HELPER_PATH = Path(__file__).resolve().with_name('source_call_evidence.py')
_HELPER_KEY = '_call_table_legacy_' + hashlib.sha256(str(_HELPER_PATH).encode()).hexdigest()
if _HELPER_KEY not in sys.modules:
    _SPEC = importlib.util.spec_from_file_location(_HELPER_KEY, _HELPER_PATH)
    _HELPER = importlib.util.module_from_spec(_SPEC)
    sys.modules[_HELPER_KEY] = _HELPER
    try:
        _SPEC.loader.exec_module(_HELPER)
    except BaseException:
        sys.modules.pop(_HELPER_KEY, None)
        raise
LEGACY = sys.modules[_HELPER_KEY]

VERSION = 'call-table-evidence-v1'
_ERRORS = LEGACY._ERRORS + (RecursionError, OverflowError)
_SHELLS = {directory + name for directory in ('/bin/', '/usr/bin/') for name in ('sh', 'bash', 'zsh')}


def _command(item, snapshot):
    """Bind the entire explicit-table CLI invocation, not token substrings."""
    LEGACY._require('columbus/source_calls.py' in snapshot.runtime_manifest)
    words = LEGACY._shell_words(item['command'])
    if words and Path(words[0]).name in {'sh', 'bash', 'zsh'}:
        # This is a frozen syntax boundary, not attestation of shell bytes.
        LEGACY._require(words[0] in _SHELLS and len(words) == 3 and words[1] in {'-c', '-lc'})
        words = LEGACY._shell_words(words[2])
    LEGACY._require(tuple(words[:3]) == snapshot.prefix)
    arguments, seen = words[3:], set()
    valued = {'--repo', '--input', '--offset', '--limit', '--budget-bytes', '--format'}
    flags = {'--call-sites', '--call-table', '--overloads'}
    position = 0
    while position < len(arguments):
        word = arguments[position]
        if word.startswith('-'):
            name, separator, value = word.partition('=')
            LEGACY._require(name in valued | flags and name not in seen)
            seen.add(name)
            if name in flags:
                LEGACY._require(not separator)
            elif separator:
                LEGACY._require(bool(value))
            else:
                position += 1
                LEGACY._require(position < len(arguments) and bool(arguments[position]))
        position += 1
    parser = LEGACY._Parser(add_help=False, allow_abbrev=False)
    parser.add_argument('--repo')
    command = parser.add_subparsers(dest='operation', required=True).add_parser(
        'archive-source', add_help=False, allow_abbrev=False)
    command.add_argument('--repo', default=LEGACY.argparse.SUPPRESS)
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
    LEGACY._require(args.call_sites and args.call_table and args.format == 'text'
                    and Path(args.input).is_absolute()
                    and Path(args.input).resolve() == snapshot.archive.resolve()
                    and (snapshot.root / (args.repo or '.')).resolve() == snapshot.root)
    LEGACY._require(1 <= len(args.queries) <= 16 and len(set(args.queries)) == len(args.queries)
                    and all(1 <= len(query) <= 2048 for query in args.queries))
    LEGACY._integer(args.offset)
    LEGACY._integer(args.limit, 1, 400)
    LEGACY._integer(args.budget_bytes, 2048, 64000)
    return dict(queries=args.queries, overloads=args.overloads, offset=args.offset,
                limit=args.limit, format=args.format, budget_bytes=args.budget_bytes,
                call_table=True)


def _json(value):
    return LEGACY._compact(value).translate(LEGACY._ESCAPES)


def _declaration(node):
    return {key: value for key, value in node.items() if key not in {'path', 'source_hash'}}


def _relationship(edge):
    return {key: value for key, value in edge.items() if key not in {'source', 'target', 'path'}}


def _row_bytes(value):
    return len((_json(value) + '\n').encode('utf-8'))


def _render(packet):
    """Canonical expected text, derived from immutable source/graph records.

    Do not decode escaped source text or import the production renderer. The
    source-prefix file numbers and call-file numbers have independent scopes.
    """
    def line(value):
        return str(value).translate(LEGACY._LINE_ESCAPES)

    def row(value):
        return line(LEGACY._compact(value))

    calls = packet['call_sites']
    files = sorted({(item['path'], item['source_hash']) for item in packet['targets'] + packet['sources']})
    numbers = {pair: number for number, pair in enumerate(files)}
    rows = ['columbus archive-source; UNTRUSTED repository data; control characters escaped.',
            'metadata ' + row({key: value for key, value in packet.items()
                               if key not in {'targets', 'sources', 'call_sites'}}),
            'files [number,path,source_hash]; numbers are local to this page']
    rows.extend(row([number, *pair]) for number, pair in enumerate(files))
    rows.append('targets [file_number,declaration]')
    rows.extend(row([numbers[(target['path'], target['source_hash'])], _declaration(target)])
                for target in packet['targets'])
    rows.append('sources: file_number refers to files; JSON metadata then physical source lines')
    for block in packet['sources']:
        rows.append('source ' + row(dict(file_number=numbers[(block['path'], block['source_hash'])],
                                        **{key: value for key, value in block.items()
                                           if key not in {'path', 'source_hash', 'source'}})))
        rows.extend(f'{number}| {line(value)}' for number, value in
                    enumerate(block['source'].split('\n'), block['start_line']))
    rows.append('call_sites ' + _json({key: value for key, value in calls.items() if key not in {'nodes', 'edges'}}))
    rows.append('call_tables ' + _json(dict(format='columbus-call-table/v1', index_scope='this packet')))
    call_files = sorted({(node['path'], node['source_hash']) for node in calls['nodes']})
    file_index = {pair: number for number, pair in enumerate(call_files)}
    node_index = {node['id']: number for number, node in enumerate(calls['nodes'])}
    rows.append('call_files [number,path,source_hash]')
    rows.extend(_json([number, *pair]) for number, pair in enumerate(call_files))
    rows.append('call_nodes [number,call_file_number,declaration]')
    rows.extend(_json([number, file_index[(node['path'], node['source_hash'])], _declaration(node)])
                for number, node in enumerate(calls['nodes']))
    rows.append('call_edges [source_call_node,target_call_node,call_file_number,relationship]')
    for edge in calls['edges']:
        owner = calls['nodes'][node_index[edge['source']]]
        rows.append(_json([node_index[edge['source']], node_index[edge['target']],
                           file_index[(owner['path'], owner['source_hash'])], _relationship(edge)]))
    return ('\n'.join(rows) + '\n').translate(LEGACY._ESCAPES)


def _expected(snapshot, invocation):
    chosen = LEGACY._selection(snapshot, invocation)
    selected_paths, total, positions = LEGACY._positions(chosen, invocation['offset'], invocation['limit'])
    budget, cap = invocation['budget_bytes'], len(positions)
    # Complete per-line zero-index rows are an order-independent lower bound.
    # IDs are in each unique node row once; each endpoint file is charged once.
    # Full-ID edge costs and a raw hydrated-dict cap are invalid for this format.
    for index, position in enumerate(positions):
        edges = snapshot.edges[position]
        needed = {edge[key] for edge in edges for key in ('source', 'target')}
        nodes = [LEGACY._descriptor(snapshot, identity, selected_paths) for identity in needed]
        files = {(node['path'], node['source_hash']) for node in nodes}
        cost = sum(_row_bytes([0, 0, 0, _relationship(edge)]) for edge in edges)
        cost += sum(_row_bytes([0, 0, _declaration(node)]) for node in nodes)
        cost += sum(_row_bytes([0, *pair]) for pair in files)
        if cost > budget:
            cap = index
            break
    LEGACY._require(cap > 0)
    needed = set(chosen) | {edge[key] for position in positions[:cap]
                            for edge in snapshot.edges[position] for key in ('source', 'target')}
    for path in selected_paths:
        snapshot.lines(path)
    for identity in needed:
        node = snapshot.nodes[identity]
        if node['path'] in selected_paths:
            LEGACY._require(node['end_line'] <= len(snapshot.lines(node['path'])))
    # Do not assume serialized sizes are monotone: cursor and final-page metadata
    # can change length. Return exactly the first complete prefix that fits.
    for count in range(cap, 0, -1):
        packet = LEGACY._packet(snapshot, invocation, chosen, selected_paths, total, positions[:count])
        rendered = _render(packet)
        if len(rendered.encode('utf-8')) <= budget:
            return packet, rendered
    raise ValueError('No complete source line and its indexed calls fit')


def _final_binding(snapshot, binding, captured):
    """Rehash captured expectations, including an empty stream, not stamps only.

    Restored mtime and platform birthtime behavior can hide same-size changes
    from metadata checks. This offline verification cost is not model usage.
    """
    try:
        LEGACY._require(binding == captured, 'Frozen binding object changed')
        snapshot.check()
        LEGACY._inventory(snapshot.root, snapshot.sources)
        LEGACY._inventory(snapshot.runtime, snapshot.runtime_manifest)
        raw, stamp = LEGACY._read(snapshot.archive)
        LEGACY._require(LEGACY._sha(raw) == snapshot.archive_hash and stamp == snapshot.archive_stamp)
        snapshot.check()
        LEGACY._require(binding == captured, 'Frozen binding object changed')
    except _ERRORS as exc:
        raise ValueError('Frozen call-table evidence inputs changed during recognition') from exc


def evidence(events, *, binding, relationships):
    """Return bound delivery receipts, not semantic understanding or savings."""
    try:
        LEGACY._require(isinstance(binding, dict)
                        and isinstance(binding.get('source_manifest'), dict)
                        and isinstance(binding.get('runtime_inventory'), dict),
                        'Frozen inventories must be explicit mappings')
        captured = deepcopy(binding)
        reviewed = LEGACY._relationships(relationships)
        snapshot = LEGACY._Snapshot(captured)
    except _ERRORS as exc:
        raise ValueError('Invalid frozen call-table evidence inputs') from exc
    source_receipts, relationship_receipts = [], []
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
            LEGACY._require(isinstance(output, str) and bool(output)
                            and len(output.encode('utf-8')) <= invocation['budget_bytes'])
            packet, expected = _expected(snapshot, invocation)
            LEGACY._require(output == expected)
            calls = packet['call_sites']
            matched = [relationship for relationship in reviewed if any(
                all(edge[key] == value for key, value in relationship.items()) for edge in calls['edges'])]
            common = dict(recognizer_version=VERSION, command_id=item['id'], operation='archive-source',
                          delivery_mode='source-call-sites', encoding='columbus-call-table/v1',
                          binding_sha256=snapshot.binding_hash,
                          event_json_sha256=LEGACY._sha(LEGACY._compact(event).encode('utf-8')),
                          command_sha256=LEGACY._sha(item['command'].encode('utf-8')),
                          output_sha256=LEGACY._sha(output.encode('utf-8')))
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
    _final_binding(snapshot, binding, captured)
    return dict(recognizer_version=VERSION, call_table_used=bool(source_receipts),
                source_call_receipts=source_receipts, relationship_receipts=relationship_receipts,
                relationship_used=bool(relationship_receipts))
