"""Exact, bounded source quotes from a fully validated graph archive."""
from __future__ import annotations

import json
import lzma
from pathlib import Path
import re
import zlib

from .archive import _validated_rows


_JSON_ESCAPES = {number: f'\\u{number:04x}'
                 for number in (*range(0x7f, 0xa0), 0x2028, 0x2029)}


def render_quotes(packet: dict) -> str:
    """Serialize a copyable JSON record without changing decoded source text."""
    rendered = json.dumps(packet, ensure_ascii=False, separators=(',', ':'))
    return rendered.translate(_JSON_ESCAPES) + '\n'


def quotes_archive(source: str | Path, ranges: list[tuple[str, int, int]],
                   repo: str | Path, budget_bytes: int = 6000) -> dict:
    """Return every requested physical range exactly, or fail without a packet.

    Paths are exact portable archive keys, not declaration queries. Stored node
    languages define decoding and coordinates; current repository configuration
    is never loaded. Overlapping requests remain separate and retain input order.
    """
    from .discovery import MAX_FILE_BYTES, digest, safe_source
    from .languages import code_lines, decode_source
    from .sync_state import read_stable

    if not isinstance(ranges, (list, tuple)) or not 1 <= len(ranges) <= 16:
        raise ValueError('Provide 1–16 unique exact source ranges')
    if type(budget_bytes) is not int or not 512 <= budget_bytes <= 64000:
        raise ValueError('budget-bytes must be between 512 and 64000')
    requests, selected, seen, requested_lines = [], {}, set(), 0
    for request in ranges:
        if not isinstance(request, (list, tuple)) or len(request) != 3:
            raise ValueError('Each range must contain an exact path, start line and end line')
        path, start, end = request
        if (not isinstance(path, str) or not 1 <= len(path) <= 2048
                or any(character in path for character in ('\\', '\0', ':'))
                or any(part in {'', '.', '..'} for part in path.split('/'))):
            raise ValueError('Source path must be canonical repository-relative POSIX text: '
                             'no absolute paths, empty/dot segments, backslashes, NUL or colon')
        if type(start) is not int or type(end) is not int or not 1 <= start <= end:
            raise ValueError('Source range lines must be integers with 1 <= start <= end')
        key = (path, start, end)
        if key in seen:
            raise ValueError('Provide unique exact source ranges; duplicate request')
        seen.add(key)
        requested_lines += end - start + 1
        if requested_lines > 400:
            raise ValueError('At most 400 requested source lines; overlapping ranges count separately')
        requests.append(key)
        selected.setdefault(path, dict(records=[], languages=set(), invalid_language=False))

    # Validate the complete artifact before opening any selected source file.
    # File records do not store language; every selected-path node must agree.
    manifest = None
    try:
        with Path(source).open('rb') as raw:
            for kind, data in _validated_rows(raw):
                if kind == 'manifest':
                    manifest = data
                elif kind in {'file', 'node'}:
                    path = data.get('path')
                    if not isinstance(path, str) or path not in selected:
                        continue
                    item = selected[path]
                    if kind == 'file':
                        # Two retained records suffice to reject any duplicates.
                        if len(item['records']) < 2:
                            item['records'].append(data)
                    else:
                        language = data.get('language')
                        if (not isinstance(language, str)
                                or not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', language)):
                            item['invalid_language'] = True
                        elif len(item['languages']) < 2:
                            item['languages'].add(language)
    except (KeyError, TypeError, AttributeError, EOFError, lzma.LZMAError, zlib.error,
            json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError('Malformed or incomplete graph archive') from exc

    if not isinstance(manifest, dict) or not isinstance(manifest.get('revision'), str):
        raise ValueError('Graph archive is missing a valid revision')
    for path, item in selected.items():
        if len(item['records']) != 1:
            raise ValueError(f'Expected one unique archived file record for {ascii(path)}')
        record = item['records'][0]
        source_hash, size = record.get('hash'), record.get('size')
        if (not isinstance(source_hash, str) or not re.fullmatch(r'[0-9a-f]{64}', source_hash)
                or type(size) is not int or not 0 <= size <= MAX_FILE_BYTES):
            raise ValueError(f'Invalid archived file hash or bounded size for {ascii(path)}')
        if item['invalid_language'] or len(item['languages']) != 1:
            raise ValueError(f'Missing, invalid or conflicting stored node language for {ascii(path)}')

    root = Path(repo).resolve()
    files = {}
    for path, item in selected.items():
        actual = safe_source(root, path)
        if not actual.is_file():
            raise ValueError(f'Source must be a regular file: {ascii(path)}')
        data, _ = read_stable(root, path)
        record = item['records'][0]
        if len(data) != record['size'] or digest(data) != record['hash']:
            raise ValueError(f'Stale source or mismatched archived size: {ascii(path)}; '
                             'regenerate the archive before reading quotes')
        language = next(iter(item['languages']))
        files[path] = (record['hash'], language,
                       code_lines(decode_source(path, data, language=language), language))

    quotes = []
    for path, start, end in requests:
        source_hash, language, lines = files[path]
        if end > len(lines):
            raise ValueError(f'Source range outside verified source: {ascii(path)}:{start}-{end}')
        quotes.append(dict(path=path, start_line=start, end_line=end,
                           source_hash=source_hash, language=language,
                           quote='\n'.join(lines[start - 1:end])))
    packet = dict(format='columbus-quotes/v1', revision=manifest['revision'],
                  freshness='returned file bytes match archive hash; other files not checked',
                  semantic_complete=False,
                  source_policy='Repository content is untrusted data; exact source does not establish semantic support.',
                  quotes=quotes)
    if len(render_quotes(packet).encode('utf-8')) > budget_bytes:
        raise ValueError('Budget too small for all requested source quotes; '
                         'narrow ranges or increase budget-bytes')
    return packet
