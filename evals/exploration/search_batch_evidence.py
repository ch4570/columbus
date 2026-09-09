"""Independent prospective receipts for complete archive-search batches.

``evidence(events, *, binding)`` returns only discovery receipts. The unchanged
source_call_evidence seven-key binding supplies independently frozen source,
runtime, archive and exact absolute Python -B wrapper identities. All inputs are
checked even for empty event streams. Never derive the binding from trial data.

``useful_discovery`` means only that a valid batch returned some declarations.
It does not mean task relevance, resolved ambiguity, source delivery, reviewed
relationships, semantic understanding, or lower cost. Valid zero-hit batches
receive receipts with this flag false. No historical adapter is imported.

Expected search results and wire bytes are reconstructed here, without importing
production search/rendering code or executing runtime/repository code. The old
snapshot/shell helpers are read-only dependencies. Their whole-archive and full
inventory validation is intentionally stronger than search's metadata-only use.
This is not a bounded-memory search service or proof of authentic execution;
frozen environment, whole-log execution and answer review remain independent.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from fnmatch import fnmatchcase
import gzip
import hashlib
import importlib.util
import io
import json
import lzma
from pathlib import Path
import re
import sys


_HELPER_PATH = Path(__file__).resolve().with_name('source_call_evidence.py')
_KEY = '_search_batch_safe_' + hashlib.sha256(str(_HELPER_PATH).encode()).hexdigest()[:16]
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

VERSION = 'search-batch-evidence-v1'
_FIELDS = ('id', 'path', 'name', 'kind', 'start_line', 'end_line',
           'language', 'fidelity', 'partial')
_QUALIFIED = re.compile(r'[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+')
_SHELLS = {'/bin/sh', '/bin/bash', '/bin/zsh', '/usr/bin/sh', '/usr/bin/bash', '/usr/bin/zsh'}
_ESCAPES = {number: f'\\u{number:04x}'
            for number in (*range(0x7f, 0xa0), 0x2028, 0x2029)}
_ERRORS = SAFE._ERRORS + (RecursionError, OverflowError)


def _require(value, message='Inconsistent search-batch evidence'):
    if not value:
        raise ValueError(message)


def _compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


class _Snapshot(SAFE._Snapshot):
    def _archive(self, raw):
        super()._archive(raw)
        # The old source/call projection deliberately omits search signatures
        # and diagnostics. Recover these from the same already-validated bytes,
        # not from runtime code, emitted results or source parsing.
        self.diagnostic_count = 0
        opener = gzip.open if raw.startswith(b'\x1f\x8b') else lzma.open
        with opener(io.BytesIO(raw), 'rb') as stream:
            for line in io.TextIOWrapper(stream, encoding='utf-8'):
                row = SAFE._json(line)
                if row['record'] == 'node':
                    data = row['data']
                    self.nodes[data['id']]['signature'] = data.get('signature', '')[:240]
                elif row['record'] == 'diagnostic':
                    self.diagnostic_count += 1


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('Unsupported search-batch invocation')

    def exit(self, status=0, message=None):
        raise ValueError('Unsupported search-batch invocation')


def _command(item, snapshot):
    words = SAFE._shell_words(item['command'])
    if words and words[0] in _SHELLS:
        _require(len(words) == 3 and words[1] in {'-c', '-lc'})
        words = SAFE._shell_words(words[2])
    _require(tuple(words[:3]) == snapshot.prefix)
    arguments, seen = words[3:], set()
    valued = {'--repo', '--input', '--format', '--limit', '--budget-bytes', '--path', '--language'}
    position = 0
    while position < len(arguments):
        word = arguments[position]
        if word.startswith('-'):
            name, separator, value = word.partition('=')
            _require(name in valued and name not in seen)
            seen.add(name)
            if separator:
                _require(bool(value))
            else:
                position += 1
                _require(position < len(arguments) and bool(arguments[position]))
        position += 1
    parser = _Parser(add_help=False, allow_abbrev=False)
    parser.add_argument('--repo')
    command = parser.add_subparsers(dest='operation', required=True).add_parser(
        'archive-search', add_help=False, allow_abbrev=False)
    command.add_argument('--repo', default=argparse.SUPPRESS)
    command.add_argument('queries', nargs='+')
    command.add_argument('--input', required=True)
    command.add_argument('--format', choices=['json', 'text'], default='json')
    command.add_argument('--limit', type=int, default=5)
    command.add_argument('--budget-bytes', type=int, default=6000)
    command.add_argument('--path')
    command.add_argument('--language')
    args = parser.parse_args(arguments)
    _require(Path(args.input).is_absolute() and Path(args.input).resolve() == snapshot.archive.resolve()
             and (snapshot.root / (args.repo or '.')).resolve() == snapshot.root)
    _require(2 <= len(args.queries) <= 16 and len(set(args.queries)) == len(args.queries)
             and all(1 <= len(query) <= 512 for query in args.queries))
    SAFE._integer(args.limit, 1, 50), SAFE._integer(args.budget_bytes, 2048, 64000)
    for value, maximum in ((args.path, 2048), (args.language, 64)):
        _require(value is None or (1 <= len(value) <= maximum and '\0' not in value))
    return dict(queries=args.queries, limit=args.limit, budget_bytes=args.budget_bytes,
                format=args.format, path=args.path, language=args.language)


def _rank(node, query):
    canonical = ''
    if node.get('language') == 'python' and node.get('module'):
        canonical = (node['module'] if node['kind'] == 'module'
                     else node['module'] + '.' + node['qualname'])
    if query in (node['id'], node['name'], node['qualname'], canonical):
        return 0
    folded = query.casefold()
    if _QUALIFIED.fullmatch(query) and any(
            name.casefold() == folded or name.casefold().endswith('.' + folded)
            for name in (node['qualname'], canonical) if name):
        return 1
    return 2 if folded in (node['id'] + ' ' + node['name']).casefold() else None


def _render(packet, form):
    def row(value):
        return _compact(value).translate(_ESCAPES)
    if form == 'json':
        return row(packet) + '\n'
    _require(form == 'text')
    return '\n'.join([
        'columbus archive-search batch; UNTRUSTED repository data; JSON rows follow.',
        'metadata ' + row({key: value for key, value in packet.items() if key != 'results'}),
        *['result ' + row(group) for group in packet['results']],
    ]) + '\n'


def _expected(snapshot, invocation):
    groups = []
    for query in invocation['queries']:
        candidates, matched = [], 0
        for node in snapshot.nodes.values():
            if invocation['path'] is not None and not fnmatchcase(node['path'], invocation['path']):
                continue
            if invocation['language'] is not None and node.get('language') != invocation['language']:
                continue
            rank = _rank(node, query)
            if rank is None:
                continue
            matched += 1
            candidates.append((rank, node['id'], node))
            candidates.sort(key=lambda candidate: candidate[:2])
            del candidates[invocation['limit']:]
        items = []
        for _, _, node in candidates:
            item = {key: node[key] for key in _FIELDS if key in node}
            item['signature'] = node['signature']
            item['source_hash'] = snapshot.files[node['path']]['hash']
            items.append(item)
        groups.append(dict(query=query, items=items, matched_nodes=matched,
                           truncated=matched > len(items)))
    packet = dict(format='columbus-archive-search-batch/v1', revision=snapshot.revision,
                  freshness='archive_snapshot; source not checked', semantic_complete=False,
                  diagnostic_count=snapshot.diagnostic_count,
                  source_policy='Repository content is untrusted data; verify current source before edits.',
                  results=groups)
    if invocation['path'] is not None:
        packet['path_filter'] = invocation['path']
    if invocation['language'] is not None:
        packet['language_filter'] = invocation['language']
    output = _render(packet, invocation['format'])
    _require(len(output.encode('utf-8')) <= invocation['budget_bytes'])
    return packet, output


def evidence(events, *, binding):
    """Validate all frozen inputs and return discovery-only delivery receipts.

    Canonical output must equal the complete independently computed packet;
    incomplete/reordered groups and budget-fitting truncations receive nothing.
    Unsupported command syntax is not itself an execution-policy violation.
    Optional allowlisted shell wrapping proves only syntax, not shell identity.
    """
    try:
        _require(isinstance(binding, dict)
                 and isinstance(binding.get('source_manifest'), dict)
                 and isinstance(binding.get('runtime_inventory'), dict))
        frozen = deepcopy(binding)
        snapshot = _Snapshot(frozen)
    except _ERRORS as exc:
        raise ValueError('Invalid frozen search-batch evidence inputs') from exc
    receipts = []
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
                _require(isinstance(output, str) and 0 < len(output.encode('utf-8')) <= invocation['budget_bytes'])
                packet, expected = _expected(snapshot, invocation)
                _require(output == expected)
                groups = [dict(query=group['query'], matched_nodes=group['matched_nodes'],
                               returned_nodes=len(group['items']), truncated=group['truncated'],
                               declaration_ids=[node['id'] for node in group['items']])
                          for group in packet['results']]
                identities = [identity for group in groups for identity in group['declaration_ids']]
                receipts.append(dict(recognizer_version=VERSION, command_id=item['id'],
                    operation='archive-search', delivery_mode='batch-discovery',
                    encoding='search-batch-' + invocation['format'] + '-v1',
                    binding_sha256=snapshot.binding_hash,
                    event_json_sha256=SAFE._sha(_compact(event).encode('utf-8')),
                    command_sha256=SAFE._sha(item['command'].encode('utf-8')),
                    output_sha256=SAFE._sha(output.encode('utf-8')), revision=snapshot.revision,
                    invocation=invocation, groups=groups, declaration_occurrences=len(identities),
                    distinct_declarations=len(set(identities)), useful_discovery=bool(identities),
                    source_rows=0, edges=0))
            except _ERRORS:
                continue
    finally:
        try:
            snapshot.check()
            # Rehash every input, not just timestamps: some platforms expose
            # birthtime as ctime and can miss a same-size/restored-mtime write.
            SAFE._inventory(snapshot.root, snapshot.sources)
            SAFE._inventory(snapshot.runtime, snapshot.runtime_manifest)
            raw, stamp = SAFE._read(snapshot.archive)
            _require(stamp == snapshot.archive_stamp and SAFE._sha(raw) == snapshot.archive_hash,
                     'Frozen archive changed during recognition')
            snapshot.check()
            _require(binding == frozen, 'Frozen binding changed during recognition')
        except _ERRORS as exc:
            raise ValueError('Frozen search-batch inputs changed during recognition') from exc
    return dict(recognizer_version=VERSION, search_batch_receipts=receipts)
