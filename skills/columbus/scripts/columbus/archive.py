"""Complete, deterministic JSONL gzip/XZ graph archives without source/FTS copies."""
from __future__ import annotations

import gzip
from fnmatch import fnmatchcase
import io
import lzma
import hashlib
import json
import os
import re
from pathlib import Path
import tempfile

from .index import compact, decode_parse


def _compressed_reader(raw):
    raw.seek(0)
    magic = raw.read(6)
    raw.seek(0)
    if magic.startswith(b'\x1f\x8b'):
        return gzip.GzipFile(fileobj=raw, mode='rb')
    if magic == b'\xfd7zXZ\x00':
        return lzma.LZMAFile(raw, mode='rb')
    raise ValueError('Unsupported archive compression; expected gzip or XZ')


def archive(index, destination: str | Path, compression: str = 'gzip') -> dict:
    if compression not in {'gzip', 'xz'}:
        raise ValueError('compression must be gzip or xz')
    output = Path(destination).expanduser().resolve()
    if output == index.db:
        raise ValueError('Archive destination cannot overwrite the index')
    output.parent.mkdir(parents=True, exist_ok=True)
    counts = dict(files=0, nodes=0, scopes=0, edges=0, references=0, imports=0, diagnostics=0)
    temporary = None
    try:
        with index._read() as conn, tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as raw:
            temporary = Path(raw.name)
            meta = index._meta(conn)
            compressor = (gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0)
                          if compression == 'gzip' else lzma.LZMAFile(raw, mode='wb', preset=3))
            with compressor as stream:
                def emit(kind, data):
                    stream.write((compact({'record': kind, 'data': data}) + '\n').encode('utf-8'))
                emit('manifest', {'format': 'columbus-graph', 'version': 1,
                    'revision': meta['revision'], 'analyzer_version': meta['analyzer_version'],
                    'analyzer_fingerprint': meta['analyzer_fingerprint'],
                    'freshness': 'index_snapshot', 'semantic_complete': False,
                    'truncated': False, 'source_bodies_included': False})
                for row in conn.execute('SELECT path,hash,size,parsed FROM files ORDER BY path'):
                    emit('file', {key: row[key] for key in ('path', 'hash', 'size')})
                    counts['files'] += 1
                    parsed = decode_parse(row['parsed'])
                    for key, scope in sorted(parsed.get('_scopes', {}).items()):
                        emit('scope', {'path': row['path'], 'id': key, **scope})
                        counts['scopes'] += 1
                    for imported in parsed.get('imports', []):
                        emit('import', imported)
                        counts['imports'] += 1
                    for reference in parsed.get('references', []):
                        emit('reference', reference)
                        counts['references'] += 1
                for row in conn.execute('SELECT data FROM symbols ORDER BY path,id'):
                    emit('node', json.loads(row[0]))
                    counts['nodes'] += 1
                for row in conn.execute('SELECT * FROM edges ORDER BY source,target,kind,path,line,confidence,evidence'):
                    emit('edge', dict(row))
                    counts['edges'] += 1
                for diagnostic in meta.get('diagnostics', []):
                    emit('diagnostic', diagnostic)
                    counts['diagnostics'] += 1
                emit('end', counts)
            raw.flush()
            os.fsync(raw.fileno())
        # Publish only a complete artifact, and never replace existing destinations.
        os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    checksum = hashlib.sha256()
    with output.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(chunk)
    return {'output': str(output), 'format': f'columbus-graph-jsonl-{compression}-v1',
            'bytes': output.stat().st_size, 'sha256': checksum.hexdigest(),
            'revision': meta['revision'], 'truncated': False, 'semantic_complete': False, **counts}


def _search_archive(source: str | Path, query: str, limit: int = 5, budget_bytes: int = 6000,
                    output_format: str = 'json') -> dict:
    """Scan a portable artifact and return bounded declaration evidence only."""
    if output_format not in {'json', 'text'}:
        raise ValueError('output_format must be json or text')
    if not 1 <= len(query) <= 512 or not 1 <= limit <= 50 or not 2048 <= budget_bytes <= 64000:
        raise ValueError('query length 1–512, limit 1–50, budget-bytes 2048–64000 required')
    selected, hashes, manifest, end = [], {}, None, None
    counts = dict(files=0, nodes=0, scopes=0, edges=0, references=0, imports=0, diagnostics=0)
    names = {'file': 'files', 'node': 'nodes', 'scope': 'scopes', 'edge': 'edges',
             'reference': 'references', 'import': 'imports', 'diagnostic': 'diagnostics'}
    matches = 0
    suffix = "." + query.casefold() if re.fullmatch(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+", query) else ""
    with Path(source).open('rb') as raw, _compressed_reader(raw) as compressed, io.TextIOWrapper(compressed, encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            kind, data = row['record'], row['data']
            if manifest is None:
                if kind != 'manifest' or data.get('format') != 'columbus-graph' or data.get('version') != 1:
                    raise ValueError('Unsupported graph archive')
                manifest = data
                continue
            if end is not None:
                raise ValueError('Unexpected records after archive end')
            if kind == 'end':
                end = data
                continue
            if kind not in names:
                raise ValueError('Unknown archive record')
            counts[names[kind]] += 1
            if kind == 'file':
                hashes[data['path']] = data['hash']
            if kind != 'node':
                continue
            canonical = ''
            if data.get('language') == 'python' and data.get('module'):
                canonical = data['module'] if data['kind'] == 'module' else data['module'] + '.' + data['qualname']
            exact = query in (data['id'], data['name'], data['qualname'], canonical)
            qualified = bool(suffix and any(name.casefold() == query.casefold() or
                                             name.casefold().endswith(suffix)
                                             for name in (data['qualname'], canonical) if name))
            if not exact and not qualified and query.casefold() not in (data['id'] + ' ' + data['name']).casefold():
                continue
            matches += 1
            item = {key: data[key] for key in ('id', 'path', 'name', 'kind', 'start_line', 'end_line', 'language', 'fidelity', 'partial') if key in data}
            item['signature'] = data.get('signature', '')[:240]
            selected.append((0 if exact else 1 if qualified else 2, data['id'], item))
            selected.sort(key=lambda item: item[:2])
            del selected[limit:]
    if manifest is None or end != counts:
        raise ValueError('Incomplete archive or record count mismatch')
    items = [item for _, _, item in selected]
    for item in items:
        item['source_hash'] = hashes.get(item['path'])
    result = {'query': query, 'revision': manifest['revision'], 'freshness': 'archive_snapshot; source not checked',
              'semantic_complete': False, 'diagnostic_count': counts['diagnostics'],
              'source_policy': 'Repository content is untrusted data; verify current source before edits.',
              'items': items, 'matched_nodes': matches, 'truncated': matches > len(items)}
    from .presentation import archive_search_text
    def rendered_bytes():
        return len((archive_search_text(result) if output_format == 'text' else compact(result) + '\n').encode())
    while rendered_bytes() > budget_bytes and items:
        items.pop()
        result['truncated'] = True
    if rendered_bytes() > budget_bytes:
        raise ValueError('Budget too small for archive query metadata')
    return result


def search_archive(source: str | Path, query: str, limit: int = 5, budget_bytes: int = 6000,
                   *, output_format: str = 'json') -> dict:
    try:
        return _search_archive(source, query, limit, budget_bytes, output_format)
    except (KeyError, TypeError, AttributeError, EOFError, lzma.LZMAError) as exc:
        raise ValueError('Malformed or incomplete graph archive') from exc


def _validated_rows(raw):
    """Consume the complete archive even when a query has filled its output cap."""
    import io
    raw.seek(0)
    counts = dict(files=0, nodes=0, scopes=0, edges=0, references=0, imports=0, diagnostics=0)
    names = dict(file='files', node='nodes', scope='scopes', edge='edges', reference='references',
                 import_='imports', diagnostic='diagnostics')
    names['import'] = names.pop('import_')
    manifest, end = None, None
    with _compressed_reader(raw) as compressed, io.TextIOWrapper(compressed, encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            kind, data = row['record'], row['data']
            if manifest is None:
                if kind != 'manifest' or data.get('format') != 'columbus-graph' or data.get('version') != 1:
                    raise ValueError('Unsupported graph archive')
                manifest = data
            elif end is not None:
                raise ValueError('Unexpected records after archive end')
            elif kind == 'end':
                end = data
            elif kind in names:
                counts[names[kind]] += 1
            else:
                raise ValueError('Unknown archive record')
            yield kind, data
    if manifest is None or end != counts:
        raise ValueError('Incomplete archive or record count mismatch')


def _neighbor_options(symbol_id, direction, kinds, limit, budget_bytes, offset, output_format, repo, context_lines, path):
    if output_format not in {'json', 'text'}:
        raise ValueError('output_format must be json or text')
    if path is not None and (not isinstance(path, str) or not 1 <= len(path) <= 2048 or '\0' in path):
        raise ValueError('path must be a nonempty glob of at most 2048 characters')
    if context_lines is not None and (type(context_lines) is not int or not 0 <= context_lines <= 40
                                     or repo is None or kinds != ['calls']):
        raise ValueError('context-lines requires repo, kinds=calls and an integer from 0 to 40')
    if not isinstance(symbol_id, str) or not 1 <= len(symbol_id) <= 2048:
        raise ValueError('An exact symbol ID of 1–2048 characters is required')
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError('offset must be a nonnegative integer')
    if direction not in {'in', 'out', 'both'} or not 1 <= limit <= 50 or not 2048 <= budget_bytes <= 64000:
        raise ValueError('direction in/out/both, limit 1–50 and budget 2048–64000 required')
    if kinds is not None and (not kinds or any(not isinstance(k, str) or not 1 <= len(k) <= 64 for k in kinds)):
        raise ValueError('kinds must contain nonempty edge kinds')


def _declaration_rank(data, query):
    """Exact identity, exact name, then qualified suffix; never fuzzy ownership."""
    if query == data['id']:
        return 0
    canonical = ''
    if data.get('language') == 'python' and data.get('module'):
        canonical = (data['module'] if data.get('kind') == 'module'
                     else data['module'] + '.' + data.get('qualname', data['name']))
    if query in (data['name'], data.get('qualname'), canonical):
        return 1
    if '.' in query and '::' not in query and any(name.endswith('.' + query) for name in
                                                (data.get('qualname', ''), canonical) if name):
        return 2
    return 3


def callers_archive(source: str | Path, query: str, limit: int = 50, budget_bytes: int = 6000,
                    offset: int = 0, *, output_format: str = 'json', repo: str | Path | None = None,
                    context_lines: int | None = None, path: str | None = None) -> dict:
    """Resolve an exact declaration or unique qualified suffix and its calls."""
    if not isinstance(query, str) or not 1 <= len(query) <= 2048:
        raise ValueError('An exact declaration name or ID of 1–2048 characters is required')
    _neighbor_options(query, 'in', ['calls'], limit, budget_bytes, offset, output_format, repo, context_lines, path)
    source = Path(source)
    def stamp():
        stat = source.stat()
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns
    before = stamp()
    selected, count, exact_id = None, 0, None
    suffix_selected, suffix_count = None, 0
    edge_phase, ordered = False, True
    edges, matched, diagnostics, references, unresolved = [], 0, 0, 0, 0
    try:
        with source.open('rb') as raw:
            for kind, data in _validated_rows(raw):
                if kind == 'manifest':
                    manifest = data
                elif kind == 'diagnostic':
                    diagnostics += 1
                elif kind == 'reference':
                    references += 1
                    unresolved += not data.get('resolved', False)
                elif kind == 'edge':
                    edge_phase = True
                    target = exact_id or (selected if count == 1 else
                                          suffix_selected if count == 0 and suffix_count == 1 else None)
                    if (target is not None and data['kind'] == 'calls' and data['target'] == target
                            and (path is None or fnmatchcase(data['path'], path))):
                        matched += 1
                        if matched > offset and len(edges) < limit:
                            edges.append(data)
                if kind != 'node':
                    continue
                if edge_phase:
                    ordered = False
                rank = _declaration_rank(data, query)
                if rank == 0:
                    exact_id = data['id']
                if rank <= 1:
                    selected = data['id']
                    count += 1
                elif rank == 2:
                    suffix_selected = data['id']
                    suffix_count += 1
        if stamp() != before:
            raise ValueError('Archive changed during query; retry')
        if count == 0 and suffix_count == 1:
            selected, count = suffix_selected, 1
        if exact_id is None and count != 1:
            raise ValueError('Declaration is ambiguous or absent; use archive-search and an exact ID')
        # Exported archives place all nodes before edges. Arbitrary valid record
        # order remains supported by falling back to the complete edge scan.
        initial = (manifest, edges, matched, diagnostics, references, unresolved) if ordered else None
        result = _neighbors_archive(source, exact_id or selected, 'in', ['calls'], limit, budget_bytes,
                                    offset, output_format=output_format, repo=repo,
                                    context_lines=context_lines, path=path, _initial_scan=initial)
        if stamp() != before:
            raise ValueError('Archive changed during query; retry')
        return result
    except (KeyError, TypeError, AttributeError, EOFError, lzma.LZMAError) as exc:
        raise ValueError('Malformed or incomplete graph archive') from exc


def neighbors_archive(source: str | Path, symbol_id: str, direction: str = 'out',
                      kinds: list[str] | None = None, limit: int = 50, budget_bytes: int = 6000, offset: int = 0,
                      *, output_format: str = 'json', repo: str | Path | None = None,
                      context_lines: int | None = None, path: str | None = None) -> dict:
    return _neighbors_archive(source, symbol_id, direction, kinds, limit, budget_bytes, offset,
                              output_format=output_format, repo=repo, context_lines=context_lines, path=path)


def _neighbors_archive(source: str | Path, symbol_id: str, direction: str = 'out',
                      kinds: list[str] | None = None, limit: int = 50, budget_bytes: int = 6000, offset: int = 0,
                      *, output_format: str = 'json', repo: str | Path | None = None,
                      context_lines: int | None = None, path: str | None = None, _initial_scan=None) -> dict:
    """Two streaming passes; bounded stored one-hop evidence, never runtime reachability."""
    _neighbor_options(symbol_id, direction, kinds, limit, budget_bytes, offset, output_format, repo, context_lines, path)
    selected, nodes, hashes = [], {}, {}
    matched, diagnostics, target_exists = 0, 0, False
    references = unresolved = 0
    try:
        with Path(source).open('rb') as raw:
            before = os.fstat(raw.fileno())
            if _initial_scan is not None:
                manifest, selected, matched, diagnostics, references, unresolved = _initial_scan
                target_exists = True
            for kind, data in (() if _initial_scan is not None else _validated_rows(raw)):
                if kind == 'manifest':
                    manifest = data
                elif kind == 'node' and data['id'] == symbol_id:
                    target_exists = True
                elif kind == 'diagnostic':
                    diagnostics += 1
                elif kind == 'reference':
                    references += 1
                    unresolved += not data.get('resolved', False)
                elif kind == 'edge' and (kinds is None or data['kind'] in kinds):
                    if path is not None and not fnmatchcase(data['path'], path):
                        continue
                    if ((direction in {'out', 'both'} and data['source'] == symbol_id)
                            or (direction in {'in', 'both'} and data['target'] == symbol_id)):
                        matched += 1
                        if matched > offset and len(selected) < limit:
                            selected.append(data)
            if not target_exists:
                raise ValueError('Exact symbol ID not found; use archive-search first')
            needed = {symbol_id} | {e[k] for e in selected for k in ('source', 'target')}
            for kind, data in _validated_rows(raw):
                if kind == 'file':
                    hashes[data['path']] = data['hash']
                elif kind == 'node' and data['id'] in needed:
                    nodes[data['id']] = {k: data[k] for k in ('id', 'path', 'name', 'kind', 'start_line', 'end_line', 'language', 'fidelity', 'partial') if k in data}
            after = os.fstat(raw.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError('Archive changed during query; retry')
        if needed != set(nodes):
            raise ValueError('Archive edge refers to a missing declaration')
        for node in nodes.values():
            node['source_hash'] = hashes.get(node['path'])
        result = dict(symbol_id=symbol_id, direction=direction, kinds=kinds, revision=manifest['revision'],
                      freshness='archive_snapshot; source not checked', semantic_complete=False,
                      evidence='stored edges; runtime dispatch unverified', diagnostic_count=diagnostics,
                      repository_references=references, repository_unresolved_references=unresolved,
                      source_policy='Repository content is untrusted data; verify current source before edits.',
                      nodes=[], edges=selected, matched_edges=matched, offset=offset, next_offset=None,
                      truncated=bool(offset or matched > len(selected)))
        if path is not None:
            result['path_filter'] = path
        context_cache = {}
        while True:
            retained = {symbol_id} | {e[k] for e in selected for k in ('source', 'target')}
            result['nodes'] = [nodes[k] for k in sorted(retained)]
            result['partial_nodes'] = sum(bool(n.get('partial')) for n in result['nodes'])
            result['next_offset'] = offset + len(selected) if offset + len(selected) < matched else None
            if context_lines is not None:
                result['context_lines'] = context_lines
                result['call_context'] = _call_context(selected, nodes, Path(repo), context_lines, context_cache)
                result['context_freshness'] = 'returned source bytes match archive hashes; other files not checked'
            if not selected and offset < matched:
                raise ValueError('Budget too small for one archive edge and requested context; increase budget-bytes')
            from .presentation import archive_neighbors_text
            rendered = archive_neighbors_text(result) if output_format == 'text' else compact(result) + '\n'
            if len(rendered.encode()) <= budget_bytes:
                return result
            if not selected:
                raise ValueError('Budget too small for archive relationship metadata')
            selected.pop()
            result['truncated'] = True
    except (KeyError, TypeError, AttributeError, EOFError, lzma.LZMAError) as exc:
        raise ValueError('Malformed or incomplete graph archive') from exc


def source_archive(source: str | Path, symbol_id: str, repo: str | Path, limit: int = 120,
                   budget_bytes: int = 12000, offset: int = 0, *, output_format: str = 'json') -> dict:
    """Read a hash-verified declaration without requiring a resolved graph edge."""
    from .discovery import digest
    from .languages import code_lines, decode_source
    from .sync_state import read_stable
    from .presentation import archive_source_text
    if not isinstance(symbol_id, str) or not 1 <= len(symbol_id) <= 2048:
        raise ValueError('A declaration name or ID of 1–2048 characters is required')
    if type(limit) is not int or not 1 <= limit <= 400:
        raise ValueError('limit must be between 1 and 400 source lines')
    if type(offset) is not int or offset < 0:
        raise ValueError('offset must be a nonnegative source-line offset')
    if type(budget_bytes) is not int or not 2048 <= budget_bytes <= 64000:
        raise ValueError('budget-bytes must be between 2048 and 64000')
    if output_format not in {'json', 'text'}:
        raise ValueError('format must be json or text')
    try:
        node, hashes = None, {}
        best_rank, matches = 3, 0
        with Path(source).open('rb') as raw:
            for kind, data in _validated_rows(raw):
                if kind == 'manifest':
                    manifest = data
                elif kind == 'file':
                    hashes[data['path']] = data['hash']
                elif kind == 'node':
                    rank = _declaration_rank(data, symbol_id)
                    if rank < best_rank:
                        node, best_rank, matches = data, rank, 1
                    elif rank == best_rank and rank < 3:
                        matches += 1
        if node is None or matches != 1:
            raise ValueError('Declaration is ambiguous or absent; use archive-search and an exact ID')
        data, _ = read_stable(Path(repo).resolve(), node['path'])
        source_hash = hashes.get(node['path'])
        if digest(data) != source_hash:
            raise ValueError(f"Stale source: {node['path']}; regenerate the archive before reading source")
        lines = code_lines(decode_source(node['path'], data, language=node.get('language')), node.get('language'))
        start, end = node['start_line'], node['end_line']
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
            raise ValueError('Declaration range outside verified source')
        total = end - start + 1
        if offset >= total:
            raise ValueError('offset is outside the declaration')
        size = min(limit, total - offset)
        result = dict(target=node['id'], path=node['path'], source_hash=source_hash,
                      revision=manifest['revision'], partial=bool(node.get('partial')),
                      fidelity=node.get('fidelity'), semantic_complete=False,
                      freshness='returned file bytes match archive hash; other files not checked',
                      declaration_start_line=start, declaration_end_line=end,
                      total_lines=total, offset=offset, source='')
        while size:
            result.update(start_line=start + offset, end_line=start + offset + size - 1,
                          next_offset=offset + size if offset + size < total else None,
                          truncated=bool(offset or offset + size < total),
                          source='\n'.join(lines[start + offset - 1:start + offset + size - 1]))
            rendered = archive_source_text(result) if output_format == 'text' else compact(result) + '\n'
            if len(rendered.encode()) <= budget_bytes:
                return result
            size -= 1
        raise ValueError('Budget too small for one source line and declaration metadata; increase budget-bytes')
    except (KeyError, TypeError, AttributeError, EOFError, lzma.LZMAError) as exc:
        raise ValueError('Malformed or incomplete graph archive') from exc


def _call_context(edges, nodes, repo, radius, cache):
    """Merge nearby sites within their lexical owner; never execute repository code."""
    from .discovery import digest
    from .languages import code_lines, decode_source
    from .sync_state import read_stable
    grouped = {}
    for edge in edges:
        node = nodes[edge['source']]
        path = node['path']
        if edge['path'] != path:
            raise ValueError('Call path differs from its source declaration')
        if path not in cache:
            data, _ = read_stable(repo.resolve(), path)
            if digest(data) != node['source_hash']:
                raise ValueError(f'Stale source: {path}; regenerate the archive before reading call context')
            cache[path] = code_lines(decode_source(path, data, language=node.get('language')), node.get('language'))
        lines = cache[path]
        line = edge['line']
        if type(line) is not int or not node['start_line'] <= line <= min(node['end_line'], len(lines)):
            raise ValueError('Call site outside its archived source declaration')
        grouped.setdefault(edge['source'], []).append(line)
    result = []
    for source_id, sites in sorted(grouped.items()):
        node = nodes[source_id]
        ranges = []
        for line in sorted(sites):
            start, end = max(node['start_line'], line - radius), min(node['end_line'], len(cache[node['path']]), line + radius)
            if ranges and start <= ranges[-1][1] + 1:
                ranges[-1][1] = max(ranges[-1][1], end)
                ranges[-1][2].append(line)
            else:
                ranges.append([start, end, [line]])
        for start, end, call_lines in ranges:
            result.append(dict(source_id=source_id, path=node['path'], source_hash=node['source_hash'],
                               start_line=start, end_line=end, call_lines=call_lines,
                               source='\n'.join(cache[node['path']][start - 1:end])))
    return result
