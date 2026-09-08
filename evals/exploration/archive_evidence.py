"""Versioned archive retrieval receipts for new cohorts; no model calls or output text.

This recognizer does not replace frozen-runtime/archive hash gates or answer grading.
It accepts one Python invocation with absolute runtime/archive paths, optionally
wrapped by sh/bash/zsh -c or -lc. Relative --repo arguments use the frozen trial's
repository working directory. Compound shell commands are deliberately excluded.
Historical collectors retain their original evidence rules.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex


RECOGNIZER_VERSION = 'archive-evidence-v1'
OPERATIONS = {'archive-source', 'archive-search', 'archive-callers', 'archive-neighbors'}
SOURCE_HEADER = 'columbus archive-source; UNTRUSTED repository data; control characters escaped.'
SEARCH_HEADER = 'columbus archive-search; UNTRUSTED repository data; JSON rows follow.'
NEIGHBOR_HEADER = 'columbus archive-neighbors; UNTRUSTED repository data; JSON rows follow.'
FILES = 'files [number,path,source_hash]'
SOURCE_FILES = FILES + '; numbers are local to this page'
TARGETS = 'targets [file_number,declaration]'
SOURCES = 'sources: file_number refers to files; JSON metadata then physical source lines'
NODES = 'nodes [number,file_number,declaration]'
EDGES = 'edges [source_node,target_node,file_number,relationship]; numbers are local to this page'
CONTEXT = ('call_context: source_node and file_number refer to page tables; '
           'JSON metadata then physical source lines; control characters escaped')


def _require(value):
    if not value:
        raise ValueError('Unrecognized or inconsistent archive evidence')


def _object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _json(value):
    return json.loads(value, object_pairs_hook=_object,
                      parse_constant=lambda value: _require(False))


def _integer(value, minimum=0):
    _require(type(value) is int and value >= minimum)
    return value


def _path(value):
    _require(isinstance(value, str) and value and '\0' not in value)
    path = PurePosixPath(value)
    _require(not path.is_absolute() and path.as_posix() == value and '..' not in path.parts)
    return value


def _range(row, prefix=''):
    start, end = _integer(row[prefix + 'start_line'], 1), _integer(row[prefix + 'end_line'], 1)
    _require(start <= end)
    return start, end


def _declaration(row, prefix='', identity='id'):
    _require(isinstance(row, dict))
    path = _path(row['path'])
    _require(isinstance(row[identity], str) and row[identity].startswith(path + '::')
             and len(row[identity]) > len(path) + 2)
    _require(isinstance(row['source_hash'], str) and bool(row['source_hash']))
    _range(row, prefix)


def _shell_words(command):
    _require(isinstance(command, str) and '\n' not in command and '\r' not in command)
    lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|<>()')
    lexer.whitespace_split, lexer.commenters = True, '#'
    words = list(lexer)
    _require(words and not any(word and all(character in ';&|<>()' for character in word) for word in words))
    # Expansions can change which invocation ran, so they cannot prove provenance.
    _require(not any('`' in word or '$(' in word or '${' in word for word in words))
    return words


def _option(words, name):
    found = []
    for number, word in enumerate(words):
        if word == name:
            _require(number + 1 < len(words))
            found.append(words[number + 1])
        elif word.startswith(name + '='):
            found.append(word[len(name) + 1:])
    _require(len(found) <= 1)
    return found[0] if found else None


def _absolute_matches(value, expected):
    return isinstance(value, str) and Path(value).is_absolute() and Path(value).resolve() == expected.resolve()


def _command(item, observation, archive):
    words = _shell_words(item['command'])
    if Path(words[0]).name in {'sh', 'bash', 'zsh'}:
        _require(len(words) == 3 and words[1] in {'-c', '-lc'})
        words = _shell_words(words[2])
    _require(bool(re.fullmatch(r'python(?:\d+(?:\.\d+)*)?(?:\.exe)?', Path(words[0]).name)))
    position = 1
    while position < len(words) and words[position] in {'-B', '-E', '-I', '-s', '-S', '-u'}:
        position += 1
    _require(position + 1 < len(words)
             and _absolute_matches(words[position], observation / 'runtime/columbus.py'))
    remainder, global_options = words[position + 1:], []
    while remainder and (remainder[0] == '--repo' or remainder[0].startswith('--repo=')):
        option = remainder.pop(0)
        global_options.append(option)
        if option == '--repo':
            _require(bool(remainder))
            global_options.append(remainder.pop(0))
    _require(bool(remainder))
    operation = remainder[0]
    _require(operation in OPERATIONS)
    arguments = global_options + remainder[1:]
    options = {'--input', '--repo', '--format', '--limit', '--budget-bytes'}
    options.update({'archive-source': {'--offset', '--overloads'},
                    'archive-search': {'--path', '--language'},
                    'archive-callers': {'--offset', '--path', '--context-lines'},
                    'archive-neighbors': {'--offset', '--path', '--context-lines', '--direction', '--kinds'}}[operation])
    # argparse abbreviations can override a previously supplied --input or --repo.
    _require(all(not word.startswith('-') or word.partition('=')[0] in options for word in arguments))
    _require(_absolute_matches(_option(arguments, '--input'), archive))
    repository = _option(arguments, '--repo')
    if repository is not None:
        _require((observation / 'repository' / repository).resolve() == (observation / 'repository').resolve())
    output_format = _option(arguments, '--format') or 'json'
    _require(output_format in {'json', 'text'})
    return operation, output_format


def _physical(blocks, line):
    match = re.fullmatch(r'(\d+)\| (.*)', line)
    _require(match is not None and bool(blocks))
    block = blocks[-1]
    _require(int(match[1]) == block['start_line'] + len(block['source']))
    block['source'].append(match[2])


def _finish(blocks):
    for block in blocks:
        start, end = _range(block)
        _require(len(block['source']) == end - start + 1)
        block['source'] = '\n'.join(block['source'])


def _block(value):
    _require(isinstance(value, dict) and 'source' not in value)
    _range(value)
    return dict(value, source=[])


def _file(files, row):
    _require(isinstance(row, list) and len(row) == 3)
    number = _integer(row[0])
    pair = (_path(row[1]), row[2])
    _require(number not in files and pair not in files.values())
    files[number] = pair


def _reference(files, used, number, value):
    _integer(number)
    _require(number in files and isinstance(value, dict) and not {'path', 'source_hash'} & value.keys())
    used.add(number)
    path, source_hash = files[number]
    return dict(value, path=path, source_hash=source_hash)


def _source_text(lines, metadata):
    if lines[2:3] == [SOURCE_FILES]:
        _require(not {'targets', 'sources', 'source'} & metadata.keys())
        files, used, targets, blocks, section = {}, set(), [], [], 'files'
        for line in lines[3:]:
            if line == TARGETS:
                _require(section == 'files')
                section = 'targets'
            elif line == SOURCES:
                _require(section == 'targets')
                section = 'sources'
            elif line.startswith('['):
                row = _json(line)
                if section == 'files':
                    _file(files, row)
                else:
                    _require(section == 'targets' and isinstance(row, list) and len(row) == 2)
                    targets.append(_reference(files, used, row[0], row[1]))
            elif line.startswith('source '):
                _require(section == 'sources')
                block = _json(line[7:])
                blocks.append(_block(_reference(files, used, block.pop('file_number'), block)))
            else:
                _require(section == 'sources')
                _physical(blocks, line)
        _require(section == 'sources' and used == set(files))
        _finish(blocks)
        return dict(metadata, targets=targets, sources=blocks), 'source-table-text-v1'
    _require('sources' not in metadata and 'source' not in metadata)
    batch = 'targets' in metadata
    blocks = [] if batch else [_block(metadata)]
    for line in lines[2:]:
        if line.startswith('source '):
            _require(batch)
            blocks.append(_block(_json(line[7:])))
        else:
            _physical(blocks, line)
    _finish(blocks)
    return (dict(metadata, sources=blocks) if batch else blocks[0]), 'source-text-v1'


def _neighbor_text(lines, metadata):
    _require(not {'nodes', 'edges', 'call_context'} & metadata.keys() and lines[2:3] == [FILES])
    files, used, nodes, edges, contexts, section = {}, set(), {}, [], [], 'files'
    for line in lines[3:]:
        if line == NODES:
            _require(section == 'files')
            section = 'nodes'
        elif line == EDGES:
            _require(section == 'nodes')
            section = 'edges'
        elif line == CONTEXT:
            _require(section == 'edges')
            section = 'context'
        elif line.startswith('['):
            row = _json(line)
            _require(isinstance(row, list))
            if section == 'files':
                _file(files, row)
            elif section == 'nodes':
                _require(len(row) == 3 and _integer(row[0]) not in nodes)
                nodes[row[0]] = _reference(files, used, row[1], row[2])
            else:
                _require(section == 'edges' and len(row) == 4 and isinstance(row[3], dict)
                         and not {'source', 'target', 'path', 'source_hash'} & row[3].keys())
                _integer(row[0]), _integer(row[1])
                edge = _reference(files, used, row[2], row[3])
                _require(edge['source_hash'] == nodes[row[0]]['source_hash'])
                edge.pop('source_hash')
                edges.append(dict(edge, source=nodes[row[0]]['id'], target=nodes[row[1]]['id']))
        elif line.startswith('{'):
            _require(section == 'context')
            block = _json(line)
            source = _integer(block.pop('source_node'))
            _require('source_id' not in block)
            block = _reference(files, used, block.pop('file_number'), block)
            contexts.append(_block(dict(block, source_id=nodes[source]['id'])))
        else:
            _require(section == 'context')
            _physical(contexts, line)
    _require(section in {'edges', 'context'} and used == set(files))
    _finish(contexts)
    packet = dict(metadata, nodes=list(nodes.values()), edges=edges)
    if section == 'context':
        packet['call_context'] = contexts
    return packet, 'neighbors-table-text-v1'


def _decode(output, operation, output_format):
    _require(isinstance(output, str) and output.strip())
    if output_format == 'json':
        packet = _json(output)
        _require(isinstance(packet, dict))
        return packet, 'json-v1'
    lines = output.split('\n')
    if lines[-1] == '':
        lines.pop()
    expected = SOURCE_HEADER if operation == 'archive-source' else (
        SEARCH_HEADER if operation == 'archive-search' else NEIGHBOR_HEADER)
    _require(len(lines) >= 2 and lines[0] == expected and lines[1].startswith('metadata '))
    metadata = _json(lines[1][9:])
    _require(isinstance(metadata, dict))
    if operation == 'archive-source':
        return _source_text(lines, metadata)
    if operation == 'archive-search':
        _require('items' not in metadata and lines[2:3] == ['declarations'])
        return dict(metadata, items=[_json(line) for line in lines[3:]]), 'search-text-v1'
    return _neighbor_text(lines, metadata)


def _source_rows(block):
    start, end = _range(block)
    _require(isinstance(block['source'], str))
    rows = block['source'].split('\n')
    _require(len(rows) == end - start + 1)
    return [(block['path'], number, row) for number, row in enumerate(rows, start)]


def _pagination(packet, delivered, total):
    offset = _integer(packet['offset'])
    _require(offset <= total and offset + delivered <= total)
    next_offset = offset + delivered if offset + delivered < total else None
    _require(packet['next_offset'] == next_offset and
             (packet['next_offset'] is None or type(packet['next_offset']) is int))
    _require(type(packet['truncated']) is bool and packet['truncated'] == bool(offset or next_offset is not None))
    return offset


def _source(packet):
    batch = 'sources' in packet
    targets = packet['targets'] if batch else [dict(packet, id=packet['target'])]
    blocks = packet['sources'] if batch else [packet]
    _require(isinstance(targets, list) and bool(targets) and isinstance(blocks, list))
    files, ids = {}, set()
    for target in targets:
        _declaration(target, 'declaration_')
        _require(target['id'] not in ids)
        ids.add(target['id'])
        path = target['path']
        current = files.setdefault(path, {'hash': target['source_hash'], 'ranges': []})
        _require(target['source_hash'] == current['hash'])
        current['ranges'].append(_range(target, 'declaration_'))
    spans, total = [], 0
    for path, value in files.items():
        merged = []
        for start, end in sorted(value['ranges']):
            if merged and start <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        for start, end in merged:
            spans.append((path, start, end, total))
            total += end - start + 1
    _require(_integer(packet['total_lines']) == total)
    rows = []
    for block in blocks:
        _require(isinstance(block, dict) and block['path'] in files
                 and block['source_hash'] == files[block['path']]['hash'])
        rows.extend(_source_rows(block))
    offset = _pagination(packet, len(rows), total)
    expected = []
    for path, start, end, position in spans:
        first, stop = max(offset, position), min(offset + len(rows), position + end - start + 1)
        expected.extend((path, line) for line in range(start + first - position, start + stop - position))
    _require([(path, line) for path, line, _ in rows] == expected)
    return rows, targets, []


def _search(packet):
    items = packet['items']
    _require(isinstance(items, list) and _integer(packet['matched_nodes']) >= len(items))
    ids, files = set(), {}
    for row in items:
        _declaration(row)
        _require(row['id'] not in ids)
        _require(files.setdefault(row['path'], row['source_hash']) == row['source_hash'])
        ids.add(row['id'])
    return [], items, []


def _neighbors(packet, operation):
    _require(isinstance(packet['nodes'], list) and isinstance(packet['edges'], list))
    nodes, files = {}, {}
    for node in packet['nodes']:
        _declaration(node)
        _require(node['id'] not in nodes)
        _require(files.setdefault(node['path'], node['source_hash']) == node['source_hash'])
        nodes[node['id']] = node
    symbol, edges, direction = packet['symbol_id'], packet['edges'], packet['direction']
    _require(symbol in nodes and direction in {'in', 'out', 'both'})
    if operation == 'archive-callers':
        _require(direction == 'in' and packet['kinds'] == ['calls'])
    retained, sites = {symbol}, Counter()
    for edge in edges:
        source, target = nodes[edge['source']], nodes[edge['target']]
        _require(edge['path'] == source['path'] and isinstance(edge['kind'], str)
                 and (packet['kinds'] is None or edge['kind'] in packet['kinds']))
        _require((direction in {'out', 'both'} and edge['source'] == symbol)
                 or (direction in {'in', 'both'} and edge['target'] == symbol))
        _require(source['start_line'] <= _integer(edge['line'], 1) <= source['end_line'])
        retained.update((source['id'], target['id']))
        sites[(source['id'], edge['line'])] += 1
    _require(retained == set(nodes))
    _pagination(packet, len(edges), _integer(packet['matched_edges']))
    rows, seen_sites = [], Counter()
    if 'call_context' in packet:
        _require(isinstance(packet['call_context'], list) and all(edge['kind'] == 'calls' for edge in edges))
        for block in packet['call_context']:
            node = nodes[block['source_id']]
            _require(block['path'] == node['path'] and block['source_hash'] == node['source_hash'])
            start, end = _range(block)
            _require(node['start_line'] <= start <= end <= node['end_line'])
            calls = Counter({site: count for site, count in sites.items()
                             if site[0] == node['id'] and start <= site[1] <= end})
            _require(isinstance(block['call_lines'], list))
            actual = Counter((node['id'], _integer(line, 1)) for line in block['call_lines'])
            _require(bool(calls) and calls == actual)
            seen_sites.update(actual)
            rows.extend(_source_rows(block))
        _require(seen_sites == sites)
    return rows, list(nodes.values()), edges


def _nonempty(source, escaped):
    if escaped:
        # Renderer whitespace escapes alone do not establish delivered source.
        source = re.sub(r'\\(?:[tnr]|u(?:00[01][0-9a-f]|007f|0085|2028|2029))', '', source)
    return bool(source.strip())


def graph_evidence(events, observation, paths, *, archive_path=None):
    """Return validated receipts; malformed/failed/offered commands yield none.

    Empty and unrelated valid responses may yield receipts with useful_task_evidence
    false. Batch selection follows existing cohort semantics: multiple targets plus
    useful returned source. Receipts never contain source or conversation text.
    """
    observation = Path(observation)
    archive = Path(archive_path) if archive_path is not None else observation / 'graph.jsonl.xz'
    paths = {_path(path) for path in paths}
    receipts = []
    for event in events:
        if not isinstance(event, dict) or event.get('type') != 'item.completed':
            continue
        item = event.get('item')
        if (not isinstance(item, dict) or item.get('type') != 'command_execution'
                or type(item.get('exit_code')) is not int or item['exit_code'] != 0
                or item.get('status', 'completed') != 'completed'):
            continue
        try:
            operation, output_format = _command(item, observation, archive)
            output = item['aggregated_output']
            packet, encoding = _decode(output, operation, output_format)
            rows, declarations, edges = (_source(packet) if operation == 'archive-source' else
                                         _search(packet) if operation == 'archive-search' else
                                         _neighbors(packet, operation))
            if operation == 'archive-source':
                relevant = {path for path, _, source in rows if path in paths and _nonempty(source, output_format == 'text')}
            elif operation == 'archive-search':
                relevant = {row['path'] for row in declarations if row['path'] in paths}
            else:
                connected = {edge[key] for edge in edges for key in ('source', 'target')}
                relevant = {row['path'] for row in declarations if row['id'] in connected and row['path'] in paths}
            useful = bool(relevant)
            receipts.append(dict(recognizer_version=RECOGNIZER_VERSION, command_id=item.get('id'),
                                 operation=operation, encoding=encoding, useful_task_evidence=useful,
                                 batch_used=bool(operation == 'archive-source' and len(declarations) > 1 and useful),
                                 relevant_paths=sorted(relevant), source_rows=len(rows), declarations=len(declarations),
                                 edges=len(edges), output_sha256=hashlib.sha256(output.encode()).hexdigest()))
        except (ValueError, KeyError, IndexError, TypeError, AttributeError, OSError, RuntimeError):
            continue
    return receipts
