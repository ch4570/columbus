"""Hash-verified source pages with every stored call on the returned lines.

Archive scans are complete and repeatable, not single-pass. Retained call data
is bounded by at most 400 line bins, each capped by the requested output budget;
the cap includes fixed-field endpoint descriptors as well as edge records.
One decoded archive record and bounded declaration-query candidates are extra.
No repository configuration or target-only source bodies are opened.
"""
from __future__ import annotations

import json
import lzma
import os
from pathlib import Path
import re
import stat
import zlib

from .archive import (_declaration_rank, _overload_group, _overload_receiver_hint,
                      _validated_rows)
from .discovery import MAX_FILE_BYTES, digest, safe_source
from .index import compact
from .languages import code_lines, decode_source
from .presentation import archive_source_text
from .sync_state import read_stable


WINDOWS = os.name == 'nt'
_LANGUAGE = re.compile(r'[a-z][a-z0-9_-]{0,39}')
_HASH = re.compile(r'[0-9a-f]{64}')
_NODE_FIELDS = ('id', 'path', 'name', 'kind', 'start_line', 'end_line',
                'language', 'fidelity', 'partial')
_QUERY_FIELDS = _NODE_FIELDS + ('qualname', 'module', 'parent_id', 'receiver_type',
                               'local', 'parameter_types')
_TEXT_ESCAPES = {number: f'\\u{number:04x}'
                 for number in (*range(0x7f, 0xa0), 0x2028, 0x2029)}


def source_calls_json(packet: dict) -> str:
    """Serialize one faithful JSON packet with terminal/line controls escaped."""
    return (compact(packet) + '\n').translate(_TEXT_ESCAPES)


def source_calls_text(packet: dict) -> str:
    """Render each source line once and exact endpoint/edge JSON records.

Full-ID graph records (not shortened endpoint indexes) deliberately preserve
the serialized lower bounds used by the streaming line-flood guard.
"""
    source = {key: value for key, value in packet.items() if key != 'call_sites'}
    calls = packet['call_sites']
    rows = [archive_source_text(source).rstrip('\n')]
    rows.append('call_sites ' + compact({key: value for key, value in calls.items()
                                         if key not in {'nodes', 'edges'}}))
    rows.extend('call_node ' + compact(node) for node in calls['nodes'])
    rows.extend('call_edge ' + compact(edge) for edge in calls['edges'])
    # compact already escapes C0 in graph data; archive_source_text escapes C0
    # in numbered source. Escape remaining terminal/Unicode line controls too.
    return ('\n'.join(rows) + '\n').translate(_TEXT_ESCAPES)


def _bytes(value: dict) -> int:
    return len(compact(value).encode('utf-8'))


def _portable_path(path):
    if (not isinstance(path, str) or not 1 <= len(path) <= 2048
            or any(character in path for character in ('\\', '\0', ':'))
            or any(part in {'', '.', '..'} for part in path.split('/'))):
        raise ValueError('Archived source path must be canonical repository-relative POSIX text')
    return path


def _node(data):
    node = {key: data[key] for key in _NODE_FIELDS if key != 'partial'}
    # Older heuristic exporters omit partial. Preserve that absence as unknown
    # rather than claiming complete parsing or rejecting a valid saved graph.
    node['partial'] = data.get('partial')
    path = _portable_path(node['path'])
    if (any(not isinstance(node[key], str) or not node[key]
            for key in ('id', 'name', 'kind', 'fidelity'))
            or not node['id'].startswith(path + '::')
            or not isinstance(node['language'], str)
            or not _LANGUAGE.fullmatch(node['language'])
            or ('partial' in data and type(data['partial']) is not bool)
            or type(node['start_line']) is not int or type(node['end_line']) is not int
            or not 1 <= node['start_line'] <= node['end_line']):
        raise ValueError('Invalid archived declaration identity, range or metadata')
    return node


class _Snapshot:
    """Bind every EOF-validated pass and source read to one opened artifact.

On Windows, path stat and fstat can expose different ctime meanings. Compare
identity/size/mtime across APIs and each API's ctime against its own baseline;
retain the stronger cross-API ctime check on POSIX.
"""
    def __init__(self, path, raw, before):
        self.path, self.raw = path, raw
        self.before_path, self.before_fd = before, os.fstat(raw.fileno())
        self.check()

    @staticmethod
    def common(value):
        return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)

    def check(self):
        path_now, fd_now = self.path.stat(), os.fstat(self.raw.fileno())
        if (not stat.S_ISREG(path_now.st_mode) or not stat.S_ISREG(fd_now.st_mode)
                or not (self.common(self.before_path) == self.common(self.before_fd)
                        == self.common(path_now) == self.common(fd_now))
                or self.before_path.st_ctime_ns != path_now.st_ctime_ns
                or self.before_fd.st_ctime_ns != fd_now.st_ctime_ns
                or (not WINDOWS and path_now.st_ctime_ns != fd_now.st_ctime_ns)):
            raise ValueError('Archive changed during query; retry with a stable snapshot')

    def rows(self):
        self.check()
        yield from _validated_rows(self.raw)
        self.check()


def _select(snapshot, queries, overloads):
    selected, ranks, matches = [[] for _ in queries], [3] * len(queries), [0] * len(queries)
    manifest = None
    oversized_manifest = False
    for kind, data in snapshot.rows():
        if kind == 'manifest':
            manifest = {'revision': data.get('revision')}
            if _bytes(manifest) > 64000:
                manifest, oversized_manifest = None, True
        elif kind == 'node':
            candidate = None
            prepared = False
            for number, query in enumerate(queries):
                rank = _declaration_rank(data, query)
                if rank > ranks[number] or rank == 3:
                    continue
                if rank < ranks[number]:
                    selected[number], ranks[number], matches[number] = [], rank, 0
                matches[number] += 1
                if len(selected[number]) >= (64 if overloads else 1):
                    continue
                if not prepared:
                    candidate = {key: data[key] for key in _QUERY_FIELDS if key in data}
                    # At most 16 x 64 candidates, each <=64 KiB; aliases share
                    # this projection. Never retain arbitrary node extra fields.
                    if _bytes(candidate) > 64000:
                        candidate = None
                    prepared = True
                selected[number].append(candidate)
    if oversized_manifest:
        raise ValueError('Archive revision exceeds bounded metadata capacity')
    if not isinstance(manifest, dict) or not isinstance(manifest.get('revision'), str):
        raise ValueError('Graph archive is missing a valid revision')
    failed, receiver_conflict = [], False
    for query, nodes, count in zip(queries, selected, matches):
        if any(node is None for node in nodes):
            raise ValueError('Selected declaration metadata exceeds bounded query capacity')
        if nodes and (count == 1 or (overloads and count <= 64 and _overload_group(nodes))):
            continue
        label = ascii(query[:80]) + ('...' if len(query) > 80 else '')
        hint = _overload_receiver_hint(nodes) if overloads and count <= 64 else None
        if hint is not None:
            label += ' (different Kotlin receiver identities, untrusted labels: ' + hint + ')'
            receiver_conflict = True
        failed.append(label)
    if failed:
        guidance = ('; --overloads requires the same owner and receiver; use archive-search, '
                    'then batch selected exact IDs without --overloads' if receiver_conflict
                    else '; use archive-search and an exact ID')
        raise ValueError('Declaration is ambiguous or absent for queries: ' + ', '.join(failed) + guidance)
    chosen = {}
    for group in selected:
        for node in sorted(group, key=lambda item:
                           (item['path'], item['start_line'], item['end_line'], item['id'])):
            chosen.setdefault(node['id'], _node(node))
    if len(chosen) > 64:
        raise ValueError('At most 64 declarations per batch; narrow queries or use exact IDs')
    return manifest, chosen


def _spans(chosen):
    files = {}
    for node in chosen.values():
        files.setdefault(node['path'], []).append((node['start_line'], node['end_line']))
    spans, total = [], 0
    for path, ranges in files.items():
        merged = []
        for start, end in sorted(ranges):
            if merged and start <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        for start, end in merged:
            spans.append((path, start, end, total))
            total += end - start + 1
    return files, spans, total


def _line_bins(spans, offset, size):
    bins = []
    for path, start, end, position in spans:
        first, stop = max(offset, position), min(offset + size, position + end - start + 1)
        for index in range(first, stop):
            bins.append(dict(path=path, line=start + index - position, edges=[], cost=0,
                             overflow=False, resolved=0, unresolved=0))
    return bins


def _collect_calls(snapshot, bins, budget):
    lookup = {(item['path'], item['line']): item for item in bins}
    paths = {item['path'] for item in bins}
    for kind, data in snapshot.rows():
        if kind not in {'edge', 'reference'} or data.get('kind') != 'calls':
            continue
        path, line = data.get('path'), data.get('line')
        # A bool line aliases integer dictionary keys; reject it, not silently
        # treat it as physical line one. Irrelevant paths need no graph hydration.
        if not isinstance(path, str) or path not in paths:
            continue
        if type(line) is not int or line < 1:
            raise ValueError('Invalid stored call-site physical line')
        item = lookup.get((path, line))
        if item is None:
            continue
        source_id = data.get('source')
        if not isinstance(source_id, str) or not source_id.startswith(path + '::'):
            raise ValueError('Call path differs from its source declaration identity')
        if kind == 'reference':
            # Scalar reference counts do not fabricate an edge/target. Their
            # physical coordinates and owner-ID path prefix are checked here;
            # full owner-node hydration/range checks apply to emitted edges.
            if type(data.get('resolved')) is not bool:
                raise ValueError('Stored CALL reference resolved flag must be boolean')
            item['resolved' if data['resolved'] else 'unresolved'] += 1
            continue
        edge = {key: data[key] for key in ('source', 'target', 'path', 'line',
                                          'kind', 'confidence', 'evidence')}
        if (any(not isinstance(edge[key], str) or not edge[key]
                for key in ('target', 'confidence')) or not isinstance(edge['evidence'], str)):
            raise ValueError('Invalid stored call edge endpoints, confidence or evidence')
        if item['overflow']:
            continue
        item['cost'] += _bytes(edge)
        if item['cost'] > budget:
            item['overflow'] = True
            item['edges'].clear()
        else:
            item['edges'].append(edge)
    # Flooding is decided only after complete validation and independently of
    # archive record order. The cursor never skips the overflowing source line.
    return next((index for index, item in enumerate(bins) if item['overflow']), len(bins))


def _hydrate(snapshot, chosen, bins, cap, selected_paths, budget):
    positions = {}
    for index, item in enumerate(bins[:cap]):
        for edge in item['edges']:
            for key in ('source', 'target'):
                positions.setdefault(edge[key], set()).add(index)
    needed = set(chosen) | positions.keys()
    seen, nodes, oversized_selection = set(), {}, False
    for kind, data in snapshot.rows():
        if kind != 'node' or data.get('id') not in needed:
            continue
        identity = data['id']
        if identity in seen:
            raise ValueError('Duplicate archived declaration endpoint')
        seen.add(identity)
        node = _node(data)
        relevant = [index for index in positions.get(identity, ()) if index < cap]
        if not relevant and identity not in chosen:
            continue
        if identity in chosen and node != chosen[identity]:
            raise ValueError('Archive declaration changed between passes')
        node.update(source_hash='0' * 64,
                    source_status=('selected_file_hash_verified' if node['path'] in selected_paths
                                   else 'archive_only'))
        cost = _bytes(node)
        failed = [index for index in relevant if bins[index]['cost'] + cost > budget]
        if failed:
            cap = min(cap, min(failed))
            # Release orphan descriptors promptly; shared nodes stay only while
            # at least one retained line references them (or they are selected).
            nodes = {key: value for key, value in nodes.items()
                     if key in chosen or any(index < cap for index in positions.get(key, ()))}
            relevant = [index for index in relevant if index < cap]
        if relevant or identity in chosen:
            if cost > 64000:
                oversized_selection = True
            else:
                nodes[identity] = node
                for index in relevant:
                    bins[index]['cost'] += cost
    if oversized_selection:
        raise ValueError('Selected declaration endpoint metadata exceeds bounded capacity')
    retained = set(chosen) | {edge[key] for item in bins[:cap] for edge in item['edges']
                              for key in ('source', 'target')}
    if not retained <= seen or not retained <= nodes.keys():
        raise ValueError('Archive edge refers to a missing declaration endpoint')
    for item in bins[:cap]:
        for edge in item['edges']:
            owner = nodes[edge['source']]
            if owner['path'] != edge['path']:
                raise ValueError('Call path differs from its source declaration')
            if not owner['start_line'] <= edge['line'] <= owner['end_line']:
                raise ValueError('Call site outside its archived source declaration')
    return {key: value for key, value in nodes.items() if key in retained}, cap


def _files(snapshot, paths):
    files = {path: dict(count=0, hash=None, size=None, language=None, invalid=False)
             for path in paths}
    for kind, data in snapshot.rows():
        if kind not in {'file', 'node'} or not isinstance(data.get('path'), str):
            continue
        item = files.get(data['path'])
        if item is None:
            continue
        if kind == 'file':
            item['count'] = min(2, item['count'] + 1)
            source_hash, size = data.get('hash'), data.get('size')
            if (not isinstance(source_hash, str) or not _HASH.fullmatch(source_hash)
                    or type(size) is not int or not 0 <= size <= MAX_FILE_BYTES):
                item['invalid'] = True
            else:
                item.update(hash=source_hash, size=size)
        else:
            language = data.get('language')
            if (not isinstance(language, str) or not _LANGUAGE.fullmatch(language)
                    or item['language'] not in (None, language)):
                item['invalid'] = True
            else:
                item['language'] = language
    for path, item in files.items():
        if item['count'] != 1:
            raise ValueError('Expected one unique archived file record for ' + ascii(path))
        if item['invalid'] or item['language'] is None:
            raise ValueError('Invalid file hash/size or missing/conflicting stored language for ' + ascii(path))
    return files


def _page_sources(bins, files):
    blocks = []
    for item in bins:
        path, line = item['path'], item['line']
        if blocks and blocks[-1]['path'] == path and blocks[-1]['end_line'] + 1 == line:
            blocks[-1]['end_line'] = line
        else:
            blocks.append(dict(path=path, source_hash=files[path]['hash'],
                               start_line=line, end_line=line))
    for block in blocks:
        block['source'] = '\n'.join(files[block['path']]['lines'][block['start_line'] - 1:block['end_line']])
    return blocks


def source_calls_archive(source: str | Path, queries: list[str], repo: str | Path,
                         limit: int = 120, budget_bytes: int = 12000, offset: int = 0,
                         *, output_format: str = 'json', overloads: bool = False) -> dict:
    """Page a declaration union and all stored calls on each returned line.

Only the source-page suffix can be removed to fit the shared rendered budget.
An unreturnable next line fails explicitly; it is never skipped. Stored CALL
reference counts are archive facts, not a claim that semantic calls are known.
"""
    if type(overloads) is not bool:
        raise ValueError('overloads must be a boolean')
    if (not isinstance(queries, (list, tuple)) or not 1 <= len(queries) <= 16
            or any(not isinstance(query, str) or not 1 <= len(query) <= 2048 for query in queries)
            or len(set(queries)) != len(queries)):
        raise ValueError('Provide 1–16 unique declaration names or IDs of 1–2048 characters')
    if type(limit) is not int or not 1 <= limit <= 400:
        raise ValueError('limit must be between 1 and 400 source lines')
    if type(offset) is not int or offset < 0:
        raise ValueError('offset must be a nonnegative source-line offset')
    if type(budget_bytes) is not int or not 2048 <= budget_bytes <= 64000:
        raise ValueError('budget-bytes must be between 2048 and 64000')
    if not isinstance(output_format, str) or output_format not in {'json', 'text'}:
        raise ValueError('format must be json or text')
    archive_path = Path(source)
    before = archive_path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('Graph archive must be a regular file')
    try:
        with archive_path.open('rb') as raw:
            snapshot = _Snapshot(archive_path, raw, before)
            manifest, chosen = _select(snapshot, queries, overloads)
            selected_paths, spans, total = _spans(chosen)
            if offset >= total:
                raise ValueError('offset is outside the selected declarations')
            bins = _line_bins(spans, offset, min(limit, total - offset))
            cap = _collect_calls(snapshot, bins, budget_bytes)
            nodes, cap = _hydrate(snapshot, chosen, bins, cap, selected_paths, budget_bytes)
            files = _files(snapshot, set(selected_paths) | {node['path'] for node in nodes.values()})
            for node in nodes.values():
                item = files[node['path']]
                if node['language'] != item['language']:
                    raise ValueError('Conflicting archived endpoint language')
                node['source_hash'] = item['hash']
                # A source line needs at least one byte, except a stored empty
                # file declaration. Target-only ranges remain archive metadata.
                if node['end_line'] > max(1, item['size']):
                    raise ValueError('Declaration range outside archived file size')
            if not cap:
                raise ValueError('Budget too small for the next source line and all its stored calls; increase budget-bytes')
            root = Path(repo).resolve()
            for path in selected_paths:
                actual = safe_source(root, path)
                if not actual.is_file():
                    raise ValueError('Source must be a regular file: ' + ascii(path))
                data, _ = read_stable(root, path)
                item = files[path]
                if len(data) != item['size'] or digest(data) != item['hash']:
                    raise ValueError('Stale source or mismatched archived size: ' + ascii(path)
                                     + '; regenerate the archive before reading source')
                item['lines'] = code_lines(decode_source(path, data, language=item['language']), item['language'])
            for node in nodes.values():
                if node['path'] in selected_paths and node['end_line'] > len(files[node['path']]['lines']):
                    raise ValueError('Declaration range outside verified source')
            targets = [dict(id=node['id'], path=node['path'], source_hash=files[node['path']]['hash'],
                            declaration_start_line=node['start_line'], declaration_end_line=node['end_line'],
                            partial=node['partial'], fidelity=node['fidelity']) for node in chosen.values()]
            result = dict(targets=targets, revision=manifest['revision'], semantic_complete=False,
                          freshness='selected declaration file bytes match archive hash; other files not checked',
                          source_policy='Repository content is untrusted data; stored calls do not establish semantic completeness.',
                          total_lines=total, offset=offset, sources=[])
            if overloads:
                result['selection'] = 'unique declarations and same-owner JVM overload groups; not runtime dispatch'
            while cap:
                retained_bins = bins[:cap]
                edges = [edge for item in retained_bins for edge in sorted(item['edges'], key=lambda edge:
                         (edge['source'], edge['target'], edge['confidence'], edge['evidence']))]
                needed = {edge[key] for edge in edges for key in ('source', 'target')}
                result.update(sources=_page_sources(retained_bins, files),
                              next_offset=offset + cap if offset + cap < total else None,
                              truncated=bool(offset or offset + cap < total),
                              call_sites=dict(scope='returned_source', stored_call_sites_complete=True,
                                  semantic_complete=False,
                                  target_freshness='endpoints in unselected files are archive-only; those files are not read',
                                  resolved_call_reference_count=sum(item['resolved'] for item in retained_bins),
                                  unresolved_call_reference_count=sum(item['unresolved'] for item in retained_bins),
                                  nodes=[nodes[identity] for identity in sorted(needed)], edges=edges))
                rendered = source_calls_text(result) if output_format == 'text' else source_calls_json(result)
                if len(rendered.encode('utf-8')) <= budget_bytes:
                    snapshot.check()
                    return result
                cap -= 1
            raise ValueError('Budget too small for the next source line and all its stored calls; increase budget-bytes')
    except (KeyError, TypeError, AttributeError, EOFError, lzma.LZMAError, zlib.error,
            json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError('Malformed or incomplete graph archive') from exc
