"""Prospective, read-only receipts for archive-source --call-sites.

Public API: evidence(events, *, binding, relationships). ``binding`` contains
repository and archive Paths, an exact (absolute_python, '-B', absolute_wrapper)
invocation_prefix, archive_sha256, revision, and complete source_manifest and
runtime_inventory path/hash mappings. Runtime inventory paths are relative to
the wrapper's parent. Inventories have no implicit exclusions. The graph must
be outside both trees. Callers supply independently frozen expected values;
deriving a binding from the files being assessed defeats provenance.

No runtime/repository code is imported or executed. No subprocess, model call,
configuration read, or filesystem write occurs. Frozen-input errors raise
ValueError; failed, unsupported or inconsistent command events receive nothing.
The historical recognizers and their receipt semantics remain unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import io
import json
import lzma
import os
from pathlib import Path
import re
import shlex
import stat
import tokenize
import zlib


VERSION = 'source-call-evidence-v1'
_HASH = re.compile(r'[0-9a-f]{64}')
_LANGUAGE = re.compile(r'[a-z][a-z0-9_-]{0,39}')
_NODE_FIELDS = ('id', 'path', 'name', 'kind', 'start_line', 'end_line',
                'language', 'fidelity')
_QUERY_FIELDS = _NODE_FIELDS + ('partial', 'qualname', 'module', 'parent_id',
                               'receiver_type', 'local', 'parameter_types')
_EDGE_FIELDS = ('source', 'target', 'path', 'line', 'kind', 'confidence', 'evidence')
_ESCAPES = {number: f'\\u{number:04x}'
            for number in (*range(0x7f, 0xa0), 0x2028, 0x2029)}
_LINE_ESCAPES = {number: f'\\u{number:04x}' for number in range(32)}
_LINE_ESCAPES.update({number: f'\\u{number:04x}' for number in (127, 0x85, 0x2028, 0x2029)})
_LINE_ESCAPES.update({9: '\\t', 10: '\\n', 13: '\\r'})
_ERRORS = (ValueError, KeyError, TypeError, AttributeError, IndexError,
           OSError, EOFError, lzma.LZMAError, zlib.error, LookupError, SyntaxError)


def _require(condition, message='Inconsistent source-call evidence'):
    if not condition:
        raise ValueError(message)


def _compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _hash(value):
    _require(isinstance(value, str) and _HASH.fullmatch(value), 'Invalid frozen SHA256')
    return value


def _integer(value, minimum=0, maximum=None):
    _require(type(value) is int and value >= minimum and (maximum is None or value <= maximum))
    return value


def _portable(value):
    _require(isinstance(value, str) and 1 <= len(value) <= 2048
             and not any(char in value for char in ('\\', '\0', ':'))
             and not any(part in {'', '.', '..'} for part in value.split('/')))
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, 'Duplicate JSON key in frozen archive')
        result[key] = value
    return result


def _json(value):
    return json.loads(value, object_pairs_hook=_pairs,
                      parse_constant=lambda value: _require(False))


def _stamp(value):
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _read(path):
    before = path.lstat()
    _require(stat.S_ISREG(before.st_mode), 'Frozen input must be a regular non-symlink file')
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        data = stream.read()
        after_fd = os.fstat(stream.fileno())
    after = path.lstat()
    # Windows stat/fstat ctime can have different meanings; compare each API
    # to itself, and identity/size/mtime across APIs.
    _require(_stamp(before) == _stamp(after) and _stamp(opened) == _stamp(after_fd)
             and _stamp(before)[:4] == _stamp(opened)[:4], 'Frozen input changed during read')
    return data, _stamp(after)


def _tree(root):
    result = {}
    for path in root.rglob('*'):
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            continue
        _require(stat.S_ISREG(info.st_mode), 'Frozen tree contains a symlink or special file')
        result[_portable(path.relative_to(root).as_posix())] = _stamp(info)
    return result


def _inventory(root, expected):
    _require(isinstance(expected, dict) and bool(expected), 'Missing complete frozen inventory')
    for path, digest in expected.items():
        _portable(path), _hash(digest)
    found = _tree(root)
    _require(set(found) == set(expected), 'Frozen file inventory differs (addition or deletion)')
    for path, digest in expected.items():
        data, stamp = _read(root / path)
        _require(_sha(data) == digest and stamp == found[path], 'Frozen file bytes differ')
    return found


def _node(data):
    result = {key: data[key] for key in _NODE_FIELDS}
    result['partial'] = data.get('partial')
    path = _portable(result['path'])
    _require(all(isinstance(result[key], str) and result[key] for key in ('id', 'name', 'kind', 'fidelity'))
             and result['id'].startswith(path + '::')
             and isinstance(result['language'], str) and _LANGUAGE.fullmatch(result['language'])
             and ('partial' not in data or type(data['partial']) is bool))
    _require(1 <= _integer(result['start_line'], 1) <= _integer(result['end_line'], 1))
    return result


class _Snapshot:
    def __init__(self, binding):
        _require(isinstance(binding, dict) and set(binding) == {
            'repository', 'archive', 'invocation_prefix', 'archive_sha256',
            'runtime_inventory', 'source_manifest', 'revision'}, 'Invalid binding fields')
        prefix = binding['invocation_prefix']
        _require(isinstance(prefix, (list, tuple)) and len(prefix) == 3
                 and all(isinstance(word, str) for word in prefix) and prefix[1] == '-B'
                 and Path(prefix[0]).is_absolute() and Path(prefix[2]).is_absolute()
                 and re.fullmatch(r'python(?:\d+(?:\.\d+)*)?(?:\.exe)?', Path(prefix[0]).name),
                 'Expected an exact absolute Python -B wrapper prefix')
        self.prefix = tuple(prefix)
        self.root = Path(binding['repository'])
        self.archive = Path(binding['archive'])
        _require(self.root.is_absolute() and self.archive.is_absolute())
        self.root = self.root.resolve()
        self.runtime = Path(prefix[2]).parent.resolve()
        _require(self.root.is_dir() and self.runtime.is_dir()
                 and not self.root.is_relative_to(self.runtime)
                 and not self.runtime.is_relative_to(self.root)
                 and not self.archive.resolve().is_relative_to(self.root)
                 and not self.archive.resolve().is_relative_to(self.runtime),
                 'Repository, runtime and archive must be separate')
        self.sources = dict(binding['source_manifest'])
        self.runtime_manifest = dict(binding['runtime_inventory'])
        self.source_stamps = _inventory(self.root, self.sources)
        self.runtime_stamps = _inventory(self.runtime, self.runtime_manifest)
        _require(Path(prefix[2]).name in self.runtime_manifest, 'Wrapper missing from runtime inventory')
        self.revision = binding['revision']
        _require(isinstance(self.revision, str) and bool(self.revision)
                 and len(_compact({'revision': self.revision}).encode('utf-8')) <= 64000)
        raw, self.archive_stamp = _read(self.archive)
        self.archive_hash = _hash(binding['archive_sha256'])
        _require(_sha(raw) == self.archive_hash, 'Frozen archive hash differs')
        self.files, self.nodes, self.edges = {}, {}, defaultdict(list)
        self.references = defaultdict(Counter)
        self._archive(raw)
        self.lines_cache = {}
        self.binding_hash = _sha(json.dumps({
            'repository': str(self.root), 'archive': str(self.archive), 'prefix': self.prefix,
            'archive_sha256': self.archive_hash, 'revision': self.revision,
            'source_manifest': self.sources, 'runtime_inventory': self.runtime_manifest,
        }, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8'))
        self.check()

    def _archive(self, raw):
        _require(raw.startswith((b'\x1f\x8b', b'\xfd7zXZ\x00')), 'Expected gzip or XZ graph')
        opener = gzip.open if raw.startswith(b'\x1f\x8b') else lzma.open
        plurals = dict(file='files', node='nodes', scope='scopes', edge='edges',
                       reference='references', diagnostic='diagnostics', **{'import': 'imports'})
        counts, manifest, ended = dict.fromkeys(plurals.values(), 0), None, False
        call_edges, languages = [], defaultdict(set)
        with opener(io.BytesIO(raw), 'rb') as compressed, io.TextIOWrapper(compressed, encoding='utf-8') as stream:
            for line in stream:
                row = _json(line)
                _require(isinstance(row, dict) and set(row) == {'record', 'data'} and not ended)
                kind, data = row['record'], row['data']
                _require(isinstance(data, dict))
                if manifest is None:
                    _require(kind == 'manifest' and data.get('format') == 'columbus-graph'
                             and type(data.get('version')) is int and data['version'] == 1
                             and data.get('revision') == self.revision, 'Invalid frozen archive manifest')
                    manifest = data
                    continue
                if kind == 'end':
                    _require(set(data) == set(counts) and all(type(value) is int for value in data.values())
                             and data == counts, 'Invalid frozen archive footer counts')
                    ended = True
                    continue
                _require(kind in plurals, 'Unknown frozen archive record')
                counts[plurals[kind]] += 1
                if kind == 'file':
                    path = _portable(data['path'])
                    _require(path not in self.files, 'Duplicate archived file')
                    digest, size = _hash(data['hash']), _integer(data['size'], 0, 1_000_000)
                    _require(self.sources.get(path) == digest and self.source_stamps[path][2] == size,
                             'Archived file hash/size differs from frozen source')
                    self.files[path] = dict(hash=digest, size=size)
                elif kind == 'node':
                    node = _node(data)
                    _require(node['id'] not in self.nodes, 'Duplicate archived declaration')
                    self.nodes[node['id']] = {key: data[key] for key in _QUERY_FIELDS if key in data}
                    languages[node['path']].add(node['language'])
                elif kind in {'edge', 'reference'} and data.get('kind') == 'calls':
                    path, number, owner = _portable(data['path']), _integer(data['line'], 1), data['source']
                    _require(isinstance(owner, str) and owner.startswith(path + '::'))
                    if kind == 'reference':
                        _require(type(data.get('resolved')) is bool)
                        self.references[(path, number)][data['resolved']] += 1
                    else:
                        edge = {key: data[key] for key in _EDGE_FIELDS}
                        _require(isinstance(edge['target'], str) and bool(edge['target'])
                                 and isinstance(edge['confidence'], str) and bool(edge['confidence'])
                                 and isinstance(edge['evidence'], str))
                        call_edges.append(edge)
        _require(manifest is not None and ended, 'Incomplete frozen archive')
        for path, values in languages.items():
            _require(path in self.files and len(values) == 1, 'Missing file or conflicting archived language')
            self.files[path]['language'] = next(iter(values))
        for node in self.nodes.values():
            _require(node['end_line'] <= max(1, self.files[node['path']]['size']))
        for edge in call_edges:
            _require(edge['source'] in self.nodes and edge['target'] in self.nodes, 'Dangling archived call endpoint')
            owner = self.nodes[edge['source']]
            _require(owner['path'] == edge['path'] and owner['start_line'] <= edge['line'] <= owner['end_line'])
            self.edges[(edge['path'], edge['line'])].append(edge)

    def lines(self, path):
        if path not in self.lines_cache:
            item = self.files[path]
            language = item['language']
            data, stamp = _read(self.root / path)
            _require(stamp == self.source_stamps[path] and _sha(data) == item['hash']
                     and len(data) == item['size'] and b'\0' not in data)
            encoding = tokenize.detect_encoding(io.BytesIO(data).readline)[0] if language == 'python' else 'utf-8-sig'
            source = data.decode(encoding)
            _require(language in {'python', 'java', 'kotlin'} or '\r' not in source.replace('\r\n', ''),
                     'Ambiguous bare-CR heuristic coordinates')
            source = source.replace('\r\n', '\n')
            if language not in {'java', 'kotlin'}:
                source = source.replace('\r', '\n')
            lines = source.split('\n')
            self.lines_cache[path] = lines[:-1] if lines[-1] == '' else lines
        return self.lines_cache[path]

    def check(self):
        try:
            unchanged = (_tree(self.root) == self.source_stamps and _tree(self.runtime) == self.runtime_stamps
                         and _stamp(self.archive.lstat()) == self.archive_stamp)
        except OSError as exc:
            raise ValueError('Frozen inputs disappeared during recognition') from exc
        _require(unchanged, 'Frozen inputs changed during recognition')


def _shell_words(command):
    """A quoting-aware single-command subset, never shell evaluation.

    Unlike a blanket '$' check after shlex, single-quoted literal identifiers
    remain usable. Expansion, globbing and command separators are rejected only
    where the shell could interpret them; comments are not accepted.
    """
    _require(isinstance(command, str) and command and not any(char in command for char in '\r\n\0'))
    quote, escaped, word_start = None, False, True
    for char in command:
        if escaped:
            escaped, word_start = False, False
            continue
        if quote == "'":
            if char == "'":
                quote = None
            continue
        if char == '\\':
            escaped = True
            continue
        if char == '"':
            quote = None if quote == '"' else '"'
            word_start = False
            continue
        if quote is None and char == "'":
            quote, word_start = "'", False
            continue
        _require(char not in '$`')
        if quote is None:
            _require(char not in ';&|<>()*?[]{}~' and not (char == '#' and word_start))
            word_start = char.isspace()
    _require(quote is None and not escaped)
    return shlex.split(command, comments=False, posix=True)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('Unsupported source-call invocation')

    def exit(self, status=0, message=None):
        raise ValueError('Unsupported source-call invocation')


def _command(item, snapshot):
    # A correctly frozen pre-feature control runtime cannot emit this contract.
    # It may still be assessed by the adapter for its historical commands.
    _require('columbus/source_calls.py' in snapshot.runtime_manifest)
    words = _shell_words(item['command'])
    if words and Path(words[0]).name in {'sh', 'bash', 'zsh'}:
        _require(len(words) == 3 and words[1] in {'-c', '-lc'})
        words = _shell_words(words[2])
    _require(tuple(words[:3]) == snapshot.prefix)
    arguments, seen = words[3:], set()
    valued = {'--repo', '--input', '--offset', '--limit', '--budget-bytes', '--format'}
    flags = {'--call-sites', '--overloads'}
    position = 0
    while position < len(arguments):
        word = arguments[position]
        if word.startswith('-'):
            name, separator, value = word.partition('=')
            _require(name in valued | flags and name not in seen)
            seen.add(name)
            if name in flags:
                _require(not separator)
            elif separator:
                _require(bool(value))
            else:
                position += 1
                _require(position < len(arguments) and bool(arguments[position]))
        position += 1
    parser = _Parser(add_help=False, allow_abbrev=False)
    parser.add_argument('--repo')
    command = parser.add_subparsers(dest='operation', required=True).add_parser(
        'archive-source', add_help=False, allow_abbrev=False)
    command.add_argument('--repo', default=argparse.SUPPRESS)
    command.add_argument('queries', nargs='+')
    command.add_argument('--input', required=True)
    command.add_argument('--call-sites', action='store_true')
    command.add_argument('--overloads', action='store_true')
    command.add_argument('--offset', type=int, default=0)
    command.add_argument('--limit', type=int, default=120)
    command.add_argument('--budget-bytes', type=int, default=12000)
    command.add_argument('--format', choices=['json', 'text'], default='json')
    args = parser.parse_args(arguments)
    _require(args.call_sites and Path(args.input).is_absolute()
             and Path(args.input).resolve() == snapshot.archive.resolve()
             and (snapshot.root / (args.repo or '.')).resolve() == snapshot.root)
    _require(1 <= len(args.queries) <= 16 and len(set(args.queries)) == len(args.queries)
             and all(1 <= len(query) <= 2048 for query in args.queries))
    _integer(args.offset), _integer(args.limit, 1, 400), _integer(args.budget_bytes, 2048, 64000)
    return dict(queries=args.queries, overloads=args.overloads, offset=args.offset,
                limit=args.limit, format=args.format, budget_bytes=args.budget_bytes)


def _rank(node, query):
    if query == node['id']:
        return 0
    canonical = ''
    if node.get('language') == 'python' and node.get('module'):
        canonical = node['module'] if node['kind'] == 'module' else node['module'] + '.' + node.get('qualname', node['name'])
    if query in (node['name'], node.get('qualname'), canonical):
        return 1
    if '.' in query and '::' not in query and any(name.endswith('.' + query)
            for name in (node.get('qualname', ''), canonical) if name):
        return 2
    return 3


def _overload_group(nodes):
    keys = ('path', 'parent_id', 'qualname', 'kind', 'language', 'receiver_type')
    first = nodes[0]
    if (first.get('language') not in {'java', 'kotlin'}
            or first['kind'] not in {'method', 'function', 'constructor'}
            or any(not isinstance(first.get(key), str) or (key != 'receiver_type' and not first[key]) for key in keys)):
        return False
    signatures = set()
    for node in nodes:
        parameters = node.get('parameter_types')
        if (any(node.get(key) != first[key] for key in keys) or node.get('local') is not False
                or node['fidelity'] != 'ast' or not isinstance(parameters, list)
                or any(not isinstance(value, str) for value in parameters)):
            return False
        signature = tuple(parameters)
        if signature in signatures:
            return False
        signatures.add(signature)
    return True


def _selection(snapshot, invocation):
    chosen = {}
    for query in invocation['queries']:
        best, group = 3, []
        for node in snapshot.nodes.values():
            rank = _rank(node, query)
            if rank < best:
                best, group = rank, []
            if rank == best and rank < 3:
                group.append(node)
        _require(group and (len(group) == 1 or (invocation['overloads'] and len(group) <= 64 and _overload_group(group))))
        for node in sorted(group, key=lambda value: (value['path'], value['start_line'], value['end_line'], value['id'])):
            _require(len(_compact(node).encode('utf-8')) <= 64000)
            chosen.setdefault(node['id'], _node(node))
    _require(len(chosen) <= 64)
    return chosen


def _positions(chosen, offset, limit):
    files = {}
    for node in chosen.values():
        files.setdefault(node['path'], []).append((node['start_line'], node['end_line']))
    total, positions = 0, []
    for path, ranges in files.items():
        merged = []
        for start, end in sorted(ranges):
            if merged and start <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        for start, end in merged:
            count = end - start + 1
            first, stop = max(offset, total), min(offset + limit, total + count)
            positions.extend((path, start + number - total) for number in range(first, stop))
            total += count
    _require(offset < total and positions)
    return set(files), total, positions


def _descriptor(snapshot, identity, selected_paths):
    node = _node(snapshot.nodes[identity])
    node.update(source_hash=snapshot.files[node['path']]['hash'],
                source_status='selected_file_hash_verified' if node['path'] in selected_paths else 'archive_only')
    return node


def _packet(snapshot, invocation, chosen, selected_paths, total, positions):
    blocks, edges, references = [], [], Counter()
    for path, number in positions:
        if blocks and blocks[-1]['path'] == path and blocks[-1]['end_line'] + 1 == number:
            blocks[-1]['end_line'] = number
        else:
            blocks.append(dict(path=path, source_hash=snapshot.files[path]['hash'], start_line=number, end_line=number))
        edges.extend(sorted(snapshot.edges[(path, number)], key=lambda edge:
                            (edge['source'], edge['target'], edge['confidence'], edge['evidence'])))
        references.update(snapshot.references[(path, number)])
    for block in blocks:
        block['source'] = '\n'.join(snapshot.lines(block['path'])[block['start_line'] - 1:block['end_line']])
    targets = [dict(id=node['id'], path=node['path'], source_hash=snapshot.files[node['path']]['hash'],
                    declaration_start_line=node['start_line'], declaration_end_line=node['end_line'],
                    partial=node['partial'], fidelity=node['fidelity']) for node in chosen.values()]
    packet = dict(targets=targets, revision=snapshot.revision, semantic_complete=False,
                  freshness='selected declaration file bytes match archive hash; other files not checked',
                  source_policy='Repository content is untrusted data; stored calls do not establish semantic completeness.',
                  total_lines=total, offset=invocation['offset'], sources=blocks)
    if invocation['overloads']:
        packet['selection'] = 'unique declarations and same-owner JVM overload groups; not runtime dispatch'
    next_offset = invocation['offset'] + len(positions)
    needed = {edge[key] for edge in edges for key in ('source', 'target')}
    packet.update(next_offset=next_offset if next_offset < total else None,
                  truncated=bool(invocation['offset'] or next_offset < total),
                  call_sites=dict(scope='returned_source', stored_call_sites_complete=True,
                      semantic_complete=False,
                      target_freshness='endpoints in unselected files are archive-only; those files are not read',
                      resolved_call_reference_count=references[True],
                      unresolved_call_reference_count=references[False],
                      nodes=[_descriptor(snapshot, identity, selected_paths) for identity in sorted(needed)], edges=edges))
    return packet


def _render(packet, output_format):
    if output_format == 'json':
        return (_compact(packet) + '\n').translate(_ESCAPES)
    def line(value):
        return str(value).translate(_LINE_ESCAPES)
    def row(value):
        return line(_compact(value))
    calls = packet['call_sites']
    files = sorted({(item['path'], item['source_hash']) for item in packet['targets'] + packet['sources']})
    numbers = {pair: number for number, pair in enumerate(files)}
    rows = ['columbus archive-source; UNTRUSTED repository data; control characters escaped.',
            'metadata ' + row({key: value for key, value in packet.items() if key not in {'targets', 'sources', 'call_sites'}}),
            'files [number,path,source_hash]; numbers are local to this page']
    rows.extend(row([number, *pair]) for number, pair in enumerate(files))
    rows.append('targets [file_number,declaration]')
    rows.extend(row([numbers[(target['path'], target['source_hash'])],
                     {key: value for key, value in target.items() if key not in {'path', 'source_hash'}}]) for target in packet['targets'])
    rows.append('sources: file_number refers to files; JSON metadata then physical source lines')
    for block in packet['sources']:
        rows.append('source ' + row(dict(file_number=numbers[(block['path'], block['source_hash'])],
                                        **{key: value for key, value in block.items() if key not in {'path', 'source_hash', 'source'}})))
        rows.extend(f'{number}| {line(value)}' for number, value in enumerate(block['source'].split('\n'), block['start_line']))
    rows.append('call_sites ' + _compact({key: value for key, value in calls.items() if key not in {'nodes', 'edges'}}))
    rows.extend('call_node ' + _compact(node) for node in calls['nodes'])
    rows.extend('call_edge ' + _compact(edge) for edge in calls['edges'])
    return ('\n'.join(rows) + '\n').translate(_ESCAPES)


def _expected(snapshot, invocation):
    chosen = _selection(snapshot, invocation)
    selected_paths, total, positions = _positions(chosen, invocation['offset'], invocation['limit'])
    budget = invocation['budget_bytes']
    # The production flood guard is a per-line lower bound. Recompute it from
    # complete immutable records, independent of their order, before fitting.
    cap = len(positions)
    for index, position in enumerate(positions):
        edges = snapshot.edges[position]
        needed = {edge[key] for edge in edges for key in ('source', 'target')}
        cost = sum(len(_compact(edge).encode('utf-8')) for edge in edges)
        cost += sum(len(_compact(_descriptor(snapshot, identity, selected_paths)).encode('utf-8')) for identity in needed)
        if cost > budget:
            cap = index
            break
    _require(cap > 0)
    needed = set(chosen) | {edge[key] for position in positions[:cap]
                            for edge in snapshot.edges[position] for key in ('source', 'target')}
    for path in selected_paths:
        snapshot.lines(path)
    for identity in needed:
        node = _descriptor(snapshot, identity, selected_paths)
        _require(len(_compact(node).encode('utf-8')) <= 64000)
        if node['path'] in selected_paths:
            _require(node['end_line'] <= len(snapshot.lines(node['path'])))
    # Decreasing prefixes mirrors the contract without assuming monotonic
    # serialized sizes (cursor/final-page metadata can also change length).
    for count in range(cap, 0, -1):
        packet = _packet(snapshot, invocation, chosen, selected_paths, total, positions[:count])
        rendered = _render(packet, invocation['format'])
        if len(rendered.encode('utf-8')) <= budget:
            return packet, rendered
    raise ValueError('No complete source line and its calls fit')


def _relationships(values):
    _require(isinstance(values, list), 'Reviewed relationships must be a list')
    result = []
    for value in values:
        _require(isinstance(value, dict) and set(value) == {'source', 'target', 'path', 'line'})
        path = _portable(value['path'])
        _require(isinstance(value['source'], str) and value['source'].startswith(path + '::')
                 and len(value['source']) > len(path) + 2
                 and isinstance(value['target'], str) and '::' in value['target'])
        target_path, target_name = value['target'].split('::', 1)
        _portable(target_path), _integer(value['line'], 1)
        _require(bool(target_name))
        if value not in result:
            result.append(dict(value))
    return result


def evidence(events, *, binding, relationships):
    """Recognize actual complete deliveries, not semantic understanding or cost.

    All frozen inputs are verified even for an empty/failed event stream. The
    caller still owns whole-log execution review, semantic/citation grading and
    pre/post-run freezing; these receipts cannot replace those gates.
    """
    try:
        reviewed = _relationships(relationships)
        snapshot = _Snapshot(binding)
    except _ERRORS as exc:
        raise ValueError('Invalid frozen source-call evidence inputs') from exc
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
            _require(isinstance(output, str) and bool(output)
                     and len(output.encode('utf-8')) <= invocation['budget_bytes'])
            packet, expected = _expected(snapshot, invocation)
            _require(output == expected)
            calls = packet['call_sites']
            matched = [relationship for relationship in reviewed if any(
                all(edge[key] == value for key, value in relationship.items()) for edge in calls['edges'])]
            common = dict(recognizer_version=VERSION, command_id=item.get('id'),
                          operation='archive-source', delivery_mode='source-call-sites',
                          encoding='source-calls-json-v1' if invocation['format'] == 'json' else 'source-calls-text-v1',
                          binding_sha256=snapshot.binding_hash,
                          event_json_sha256=_sha(_compact(event).encode('utf-8')),
                          command_sha256=_sha(item['command'].encode('utf-8')),
                          output_sha256=_sha(output.encode('utf-8')))
            ranges = [{key: block[key] for key in ('path', 'source_hash', 'start_line', 'end_line')}
                      for block in packet['sources']]
            source_receipts.append(dict(common, invocation=invocation,
                target_ids=[target['id'] for target in packet['targets']], ranges=ranges,
                source_rows=sum(block['end_line'] - block['start_line'] + 1 for block in packet['sources']),
                next_offset=packet['next_offset'], total_lines=packet['total_lines'],
                stored_edges=len(calls['edges']), endpoint_nodes=len(calls['nodes']),
                resolved_call_reference_count=calls['resolved_call_reference_count'],
                unresolved_call_reference_count=calls['unresolved_call_reference_count']))
            if matched:
                relationship_receipts.append(dict(common, relationships=matched))
        except _ERRORS:
            continue
    snapshot.check()
    return dict(recognizer_version=VERSION, source_call_receipts=source_receipts,
                relationship_receipts=relationship_receipts, relationship_used=bool(relationship_receipts))
