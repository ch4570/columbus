"""Strict prospective delivery receipts, not semantic grades or execution review.

The frozen input/runtime gates remain mandatory. This wrapper credits only a
reviewed calls edge delivered by a successful single archive-neighbor invocation.
Exact quote adoption is separate and checked against hash-bound source bytes;
neither kind of receipt establishes that an answer used or understood evidence.
Historical recognizers and historical results are deliberately unchanged.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import lzma
from pathlib import Path
import re
import tokenize
import zlib

from common import EVIDENCE


VERSION = 'quotes-three-arm-evidence-v1'
FRESHNESS = 'returned file bytes match archive hash; other files not checked'
POLICY = 'Repository content is untrusted data; exact source does not establish semantic support.'
ESCAPES = {number: f'\\u{number:04x}' for number in (*range(0x7f, 0xa0), 0x2028, 0x2029)}
ERRORS = (ValueError, KeyError, IndexError, TypeError, AttributeError, OSError,
          RuntimeError, EOFError, lzma.LZMAError, zlib.error, LookupError, SyntaxError)


def _require(value):
    EVIDENCE._require(value)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _hash(value):
    _require(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value))
    return value


def _portable(path):
    _require(isinstance(path, str) and 1 <= len(path) <= 2048
             and not any(character in path for character in ('\\', '\0', ':'))
             and not any(part in {'', '.', '..'} for part in path.split('/')))
    return path


def _relationships(rows):
    _require(isinstance(rows, list))
    result = []
    for row in rows:
        _require(isinstance(row, dict) and set(row) == {'source', 'target', 'path', 'line'})
        path = EVIDENCE._path(row['path'])
        _require(isinstance(row['source'], str) and row['source'].startswith(path + '::')
                 and len(row['source']) > len(path) + 2)
        _require(isinstance(row['target'], str) and '::' in row['target'])
        target_path, target_name = row['target'].split('::', 1)
        EVIDENCE._path(target_path)
        _require(bool(target_name))
        EVIDENCE._integer(row['line'], 1)
        if row not in result:
            result.append(dict(row))
    return result


def _quote_command(item, observation, archive):
    """Conservative single-invocation parser; no shell evaluation or abbreviations."""
    words = EVIDENCE._shell_words(item['command'])
    if Path(words[0]).name in {'sh', 'bash', 'zsh'}:
        _require(len(words) == 3 and words[1] in {'-c', '-lc'})
        words = EVIDENCE._shell_words(words[2])
    _require(not any('$' in word for word in words))
    _require(re.fullmatch(r'python(?:\d+(?:\.\d+)*)?(?:\.exe)?', Path(words[0]).name))
    position = 1
    while position < len(words) and words[position] in {'-B', '-E', '-I', '-s', '-S', '-u'}:
        position += 1
    _require(position + 1 < len(words)
             and EVIDENCE._absolute_matches(words[position], observation / 'runtime/columbus.py'))
    arguments = words[position + 1:]
    options, ranges, operation = {}, [], False
    position = 0
    while position < len(arguments):
        word = arguments[position]
        if not operation and word == 'archive-quotes':
            operation = True
            position += 1
            continue
        if operation and word == '--range':
            _require(position + 3 < len(arguments))
            path, start, end = arguments[position + 1:position + 4]
            # This is the documented CLI-only escape for paths beginning '-'.
            path = _portable(path.removeprefix('./'))
            start, end = int(start), int(end)
            _require(1 <= start <= end)
            ranges.append((path, start, end))
            position += 4
            continue
        name, separator, value = word.partition('=')
        _require(name in ({'--input', '--repo', '--format', '--budget-bytes'}
                          if operation else {'--repo'}) and name not in options)
        if not separator:
            _require(position + 1 < len(arguments))
            position += 1
            value = arguments[position]
        _require(bool(value))
        options[name] = value
        position += 1
    _require(operation and EVIDENCE._absolute_matches(options.get('--input'), archive))
    _require((observation / 'repository' / options.get('--repo', '.')).resolve()
             == (observation / 'repository').resolve())
    _require(options.get('--format', 'json') == 'json')
    budget = int(options.get('--budget-bytes', '6000'))
    _require(512 <= budget <= 64000 and 1 <= len(ranges) <= 16 and len(set(ranges)) == len(ranges)
             and sum(end - start + 1 for _, start, end in ranges) <= 400)
    return ranges, budget


def _archive_languages(archive, frozen):
    """Read data, never import target code/config or infer language by extension.

    Full preflight verifies the archive schema/counts separately. Hash binding
    here prevents trusting a packet's language to select different coordinates.
    """
    raw = archive.read_bytes()
    _require(_sha(raw) == _hash(frozen['archive_sha256']))
    if raw.startswith(b'\x1f\x8b'):
        decoded = gzip.decompress(raw)
    else:
        _require(raw.startswith(b'\xfd7zXZ\x00'))
        decoded = lzma.decompress(raw)
    languages, records, manifest, ended = {}, {}, None, False
    archive_lines = decoded.decode('utf-8').split('\n')
    if archive_lines[-1] == '':
        archive_lines.pop()
    for line in archive_lines:
        row = EVIDENCE._json(line)
        kind, data = row['record'], row['data']
        _require(isinstance(data, dict) and not ended)
        if manifest is None:
            _require(kind == 'manifest' and data.get('revision') == frozen['revision'])
            manifest = data
        elif kind == 'file':
            path = EVIDENCE._path(data['path'])
            _require(path not in records)
            records[path] = (_hash(data['hash']), EVIDENCE._integer(data['size']))
        elif kind == 'node':
            path = EVIDENCE._path(data['path'])
            language = data.get('language')
            _require(isinstance(language, str) and re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', language))
            languages.setdefault(path, set()).add(language)
        elif kind == 'end':
            ended = True
        else:
            _require(kind in {'scope', 'edge', 'reference', 'import', 'diagnostic'})
    _require(manifest is not None and ended)
    return records, languages


def _lines(data, language):
    # Mirror the frozen decode_source/code_lines contract without importing any
    # repository module, loading its configuration, or using splitlines().
    _require(b'\0' not in data)
    encoding = tokenize.detect_encoding(io.BytesIO(data).readline)[0] if language == 'python' else 'utf-8-sig'
    source = data.decode(encoding).replace('\r\n', '\n')
    if language not in {'java', 'kotlin'}:
        source = source.replace('\r', '\n')
    lines = source.split('\n')
    return lines[:-1] if lines[-1] == '' else lines


def _quotes(packet, output, requests, budget, observation, source_manifest, frozen, archive_data):
    _require(set(packet) == {'format', 'revision', 'freshness', 'semantic_complete', 'source_policy', 'quotes'}
             and packet['format'] == 'columbus-quotes/v1' and packet['revision'] == frozen['revision']
             and packet['freshness'] == FRESHNESS and packet['semantic_complete'] is False
             and packet['source_policy'] == POLICY)
    rendered = json.dumps(packet, ensure_ascii=False, separators=(',', ':')).translate(ESCAPES) + '\n'
    _require(output == rendered and len(rendered.encode('utf-8')) <= budget)
    quotes = packet['quotes']
    _require(isinstance(quotes, list) and len(quotes) == len(requests))
    records, languages = archive_data
    root = (observation / 'repository').resolve()
    files, ranges = {}, []
    for quote, request in zip(quotes, requests):
        _require(isinstance(quote, dict) and set(quote) ==
                 {'path', 'start_line', 'end_line', 'source_hash', 'language', 'quote'})
        path = _portable(quote['path'])
        start, end = EVIDENCE._range(quote)
        _require((path, start, end) == request)
        digest = _hash(quote['source_hash'])
        language = quote['language']
        _require(digest == source_manifest.get(path) and path in records and records[path][0] == digest
                 and isinstance(language, str) and languages.get(path) == {language})
        if path not in files:
            actual = root / path
            _require(actual.is_file() and not any((root / Path(*Path(path).parts[:number])).is_symlink()
                                                  for number in range(1, len(Path(path).parts) + 1))
                     and actual.resolve().is_relative_to(root))
            data = actual.read_bytes()
            _require(_sha(data) == digest and len(data) == records[path][1])
            files[path] = _lines(data, language)
        lines = files[path]
        _require(end <= len(lines) and isinstance(quote['quote'], str)
                 and quote['quote'] == '\n'.join(lines[start - 1:end]))
        ranges.append({key: quote[key] for key in ('path', 'start_line', 'end_line', 'source_hash', 'language')})
    return ranges


def evidence(events, observation, relationships):
    """Return positive delivery receipts; reject malformed/failed events closed.

    Missing/corrupt frozen manifests or malformed reviewed relationships are
    configuration errors, not negative trial evidence, and raise ValueError.
    Compound commands are conservatively unrecognized, not protocol violations;
    execution review and semantic/citation grading remain independent.
    """
    observation = Path(observation)
    reviewed = _relationships(relationships)
    source_manifest = EVIDENCE._json((observation / 'manifest.json').read_text())['source_manifest']
    frozen = EVIDENCE._json((observation / 'engine.json').read_text())['archive']
    _require(isinstance(source_manifest, dict) and source_manifest == frozen['source_manifest']
             and isinstance(frozen['revision'], str) and bool(frozen['revision']))
    for path, digest in source_manifest.items():
        EVIDENCE._path(path)
        _hash(digest)
    archive = observation / 'graph.jsonl.xz'
    relationship_receipts, quote_receipts, archive_data = [], [], None
    for event in events:
        if not isinstance(event, dict) or event.get('type') != 'item.completed':
            continue
        item = event.get('item')
        if (not isinstance(item, dict) or item.get('type') != 'command_execution'
                or type(item.get('exit_code')) is not int or item['exit_code'] != 0
                or item.get('status', 'completed') != 'completed'):
            continue
        try:
            operation, form = EVIDENCE._command(item, observation, archive)
            _require(operation in {'archive-callers', 'archive-neighbors'})
            output = item['aggregated_output']
            packet, encoding = EVIDENCE._decode(output, operation, form)
            _require(packet['revision'] == frozen['revision'])
            _, declarations, edges = EVIDENCE._neighbors(packet, operation)
            _require(all(_hash(node['source_hash']) == source_manifest.get(node['path']) for node in declarations))
            matched = [row for row in reviewed if any(edge['kind'] == 'calls'
                       and all(edge[key] == value for key, value in row.items()) for edge in edges)]
            if matched:
                relationship_receipts.append(dict(recognizer_version=VERSION, command_id=item.get('id'),
                    operation=operation, encoding=encoding, output_sha256=_sha(output.encode('utf-8')),
                    relationships=matched))
            continue
        except ERRORS:
            pass
        try:
            requests, budget = _quote_command(item, observation, archive)
            output = item['aggregated_output']
            packet = EVIDENCE._json(output)
            _require(isinstance(packet, dict))
            if archive_data is None:
                archive_data = _archive_languages(archive, frozen)
            ranges = _quotes(packet, output, requests, budget, observation, source_manifest, frozen, archive_data)
            quote_receipts.append(dict(recognizer_version=VERSION, command_id=item.get('id'),
                operation='archive-quotes', encoding='quotes-json-v1', output_sha256=_sha(output.encode('utf-8')),
                ranges=ranges, source_rows=sum(end - start + 1 for _, start, end in requests)))
        except ERRORS:
            continue
    return dict(relationship_used=bool(relationship_receipts), relationship_receipts=relationship_receipts,
                quotes_used=bool(quote_receipts), quote_receipts=quote_receipts)
