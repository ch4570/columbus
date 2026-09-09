"""Future-only aggregation of four unchanged, independently bound verifiers.

``evidence(events, *, binding, relationships)`` keeps full-ID source/calls, text
tables, JSON tables and batch discovery distinct. Adoption is accepted delivery,
not task relevance, semantic understanding, cost savings or an execution-policy
verdict. Search never supplies source or reviewed-edge credit. Inner receipts
retain their standalone schemas and values; each list follows event chronology.

The exact seven-key binding and reviewed relationships must be frozen externally.
All terminal command IDs are globally unique, including failed/unsupported ones.
Events must be plain JSON transport values, captured before any lane runs. Full
pre/post byte validation also runs for empty streams and iterator/verifier errors.
This materializes the whole stream and performs four offline verifier scans; it
is not a bounded-memory service or a model/production efficiency optimization.

No production code, historical cohort adapter, subprocess or model is invoked.
Each unchanged verifier owns its command grammar: the older full-ID lane retains
its historical shell syntax, without broadening newer table/search allowlists.
Whole-log execution, citation/semantic review and frozen study gates stay separate.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import math
from pathlib import Path
import sys


def _load(stem):
    path = Path(__file__).resolve().with_name(stem + '.py')
    key = '_compact_delivery_' + hashlib.sha256(str(path).encode()).hexdigest()
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(key, None)
            raise
    return sys.modules[key]


FULL_ID = _load('source_call_evidence')
TEXT_TABLE = _load('call_table_evidence')
JSON_TABLE = _load('json_call_table_evidence')
SEARCH_BATCH = _load('search_batch_evidence')
VERSION = 'compact-delivery-adapter-v1'
_ERRORS = FULL_ID._ERRORS + (RecursionError, OverflowError)
_COMMON = ('recognizer_version', 'command_id', 'operation', 'delivery_mode',
           'encoding', 'binding_sha256', 'event_json_sha256', 'command_sha256',
           'output_sha256')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _event_copy(event):
    """Preserve types/order and detach reused dictionaries; never normalize JSON."""
    _require(type(event) is dict, 'Event must be a JSON object')
    pending, visited = [event], set()
    while pending:
        value = pending.pop()
        kind = type(value)
        _require(kind in (dict, list, str, int, float, bool, type(None)),
                 'Event contains a non-JSON transport value')
        if kind is float:
            _require(math.isfinite(value), 'Event contains a non-finite number')
        elif kind in (dict, list):
            if id(value) in visited:
                continue  # The exact serializer below rejects cycles, not aliases.
            visited.add(id(value))
            if kind is dict:
                _require(all(type(key) is str for key in value), 'Event JSON keys must be strings')
                pending.extend(value.values())
            else:
                pending.extend(value)
    captured = deepcopy(event)
    # Reject cycles, unencodable Unicode and serialization failures for the
    # whole stream, rather than silently losing one lane's delivery receipts.
    raw = FULL_ID._compact(captured).encode('utf-8')
    return captured, FULL_ID._sha(raw)


def _materialize(events):
    captured, ledger = [], {}
    try:
        for event in events:
            event, digest = _event_copy(event)
            position = len(captured)
            captured.append(event)
            item = event.get('item')
            if (event.get('type') != 'item.completed' or type(item) is not dict
                    or item.get('type') != 'command_execution'):
                continue
            identity = item.get('id')
            if type(identity) is not str or not identity:
                continue
            _require(identity not in ledger, 'Duplicate terminal command ID: ' + identity)
            ledger[identity] = (position, digest, item)
    except _ERRORS as exc:
        raise ValueError('Invalid compact-delivery event stream') from exc
    return captured, ledger


def _postflight(snapshot, binding, captured, relationships, reviewed):
    try:
        snapshot.check()
        FULL_ID._inventory(snapshot.root, snapshot.sources)
        FULL_ID._inventory(snapshot.runtime, snapshot.runtime_manifest)
        raw, stamp = FULL_ID._read(snapshot.archive)
        _require(stamp == snapshot.archive_stamp and FULL_ID._sha(raw) == snapshot.archive_hash,
                 'Frozen archive changed during adapter verification')
        snapshot.check()
        # These original caller-object checks follow ALL final I/O. Revalidate
        # relationship types too: Python equality alone treats 1 == True == 1.0.
        FULL_ID._relationships(relationships)
        _require(relationships == reviewed, 'Frozen reviewed relationships changed')
        _require(binding == captured, 'Frozen binding object changed')
    except _ERRORS as exc:
        raise ValueError('Frozen compact-delivery inputs changed during recognition') from exc


def _receipt(receipt, ledger, snapshot, verifier, encodings, *, source):
    _require(type(receipt) is dict, 'Malformed standalone receipt')
    identity = receipt.get('command_id')
    _require(type(identity) is str and identity in ledger, 'Receipt has no terminal command')
    _, digest, item = ledger[identity]
    _require(item.get('status') == 'completed' and type(item.get('exit_code')) is int
             and item['exit_code'] == 0, 'Receipt belongs to an unsuccessful command')
    _require(receipt.get('recognizer_version') == verifier.VERSION
             and receipt.get('binding_sha256') == snapshot.binding_hash
             and receipt.get('event_json_sha256') == digest
             and receipt.get('encoding') in encodings
             and receipt.get('operation') == ('archive-source' if source else 'archive-search')
             and receipt.get('delivery_mode') == ('source-call-sites' if source else 'batch-discovery'),
             'Standalone receipt provenance differs')
    for key, field in (('command_sha256', 'command'), ('output_sha256', 'aggregated_output')):
        _require(type(item.get(field)) is str
                 and receipt.get(key) == FULL_ID._sha(item[field].encode('utf-8')),
                 'Standalone receipt bytes differ')
    return identity


def _merge(results, ledger, snapshot):
    sources, relations, discovery, deliveries, graph_ids = [], [], [], set(), set()
    lanes = (
        (FULL_ID, {'source-calls-json-v1', 'source-calls-text-v1'}, 'full_id_source_calls_used'),
        (TEXT_TABLE, {'columbus-call-table/v1'}, 'call_table_used'),
        (JSON_TABLE, {'columbus-call-table-json/v1'}, 'json_call_table_used'),
        (SEARCH_BATCH, {'search-batch-json-v1', 'search-batch-text-v1'}, 'search_batch_used'),
    )
    flags = {}
    for result, (verifier, encodings, flag) in zip(results, lanes):
        source = verifier is not SEARCH_BATCH
        _require(type(result) is dict and result.get('recognizer_version') == verifier.VERSION,
                 'Malformed standalone result')
        rows = result.get('source_call_receipts' if source else 'search_batch_receipts')
        _require(type(rows) is list, 'Missing standalone delivery list')
        flags[flag] = bool(rows)
        own_sources = {}
        for original in rows:
            receipt = deepcopy(original)
            identity = _receipt(receipt, ledger, snapshot, verifier, encodings, source=source)
            _require(identity not in deliveries, 'Overlapping standalone delivery lanes')
            deliveries.add(identity)
            (sources if source else discovery).append(receipt)
            own_sources[identity] = receipt
        if not source:
            continue
        rows = result.get('relationship_receipts')
        _require(type(rows) is list, 'Missing standalone relationship list')
        for original in rows:
            receipt = deepcopy(original)
            identity = _receipt(receipt, ledger, snapshot, verifier, encodings, source=True)
            backing = own_sources.get(identity)
            _require(backing is not None and identity not in graph_ids
                     and all(receipt.get(key) == backing.get(key) for key in _COMMON)
                     and bool(receipt.get('relationships')),
                     'Relationship receipt has no unique matching source delivery')
            graph_ids.add(identity)
            relations.append(receipt)
    for rows in (sources, relations, discovery):
        rows.sort(key=lambda receipt: ledger[receipt['command_id']][0])
    return dict(recognizer_version=VERSION, source_calls_used=bool(sources), **flags,
                source_call_receipts=sources, relationship_receipts=relations,
                relationship_used=bool(relations), search_batch_receipts=discovery)


def evidence(events, *, binding, relationships):
    """Verify the entire stream or raise; do not deduplicate terminal attempts."""
    try:
        _require(type(binding) is dict and type(binding.get('source_manifest')) is dict
                 and type(binding.get('runtime_inventory')) is dict, 'Invalid frozen binding')
        captured, reviewed = deepcopy(binding), deepcopy(relationships)
        FULL_ID._relationships(reviewed)
        snapshot = FULL_ID._Snapshot(captured)
    except _ERRORS as exc:
        raise ValueError('Invalid frozen compact-delivery inputs') from exc
    try:
        captured_events, ledger = _materialize(events)
        results = [verifier.evidence(captured_events, binding=captured, relationships=reviewed)
                   for verifier in (FULL_ID, TEXT_TABLE, JSON_TABLE)]
        results.append(SEARCH_BATCH.evidence(captured_events, binding=captured))
        return _merge(results, ledger, snapshot)
    finally:
        _postflight(snapshot, binding, captured, relationships, reviewed)
