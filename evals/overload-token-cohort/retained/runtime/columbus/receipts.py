"""Caller-owned source ledgers and bounded query-scoped discovery cursors."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

SCHEMA = 'columbus.context-receipt/v2'
LEGACY_SCHEMA = 'columbus.context-receipt/v1'
MAX_BYTES = 1_048_576


class ReceiptState(dict):
    """Keep an uncommitted cursor beside the source ledger until delivery is saved.

    The cursor is not response evidence and need not consume the model's source
    budget. Ordinary dictionaries remain supported with explicit packet fields.
    """

    def __init__(self, data):
        super().__init__(data)
        self.pending = None

    def stage(self, packet, scope, cursor):
        self.pending = (packet_key(packet), scope, cursor)


def packet_key(packet: dict) -> str:
    return hashlib.sha256(json.dumps(packet, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def repository_key(root: str) -> str:
    return hashlib.sha256(root.encode('utf-8')).hexdigest()


def merge_spans(spans: list[list[int]]) -> list[list[int]]:
    merged: list[list[int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return merged


def validate(value: dict) -> dict:
    fields = {'schema', 'repository', 'revision', 'files'}
    if not isinstance(value, dict):
        raise ValueError('Invalid Columbus context receipt; existing file was preserved')
    expected = fields | {'continuations'} if value.get('schema') == SCHEMA else fields
    if set(value) != expected:
        raise ValueError('Invalid Columbus context receipt; existing file was preserved')
    if (value['schema'] not in (SCHEMA, LEGACY_SCHEMA) or not isinstance(value['repository'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', value['repository'])
            or not isinstance(value['revision'], str) or len(value['revision']) > 128
            or not isinstance(value['files'], dict) or len(value['files']) > 2000):
        raise ValueError('Invalid Columbus context receipt header; existing file was preserved')
    for path, item in value['files'].items():
        if (not isinstance(path, str) or len(path) > 4096 or not path
                or not isinstance(item, dict) or set(item) not in ({'source_hash', 'spans'}, {'source_hash', 'source_view_hash', 'spans'})
                or not isinstance(item['source_hash'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', item['source_hash'])
                or not isinstance(item['spans'], list) or len(item['spans']) > 10000):
            raise ValueError('Invalid Columbus context receipt file entry; existing file was preserved')
        if 'source_view_hash' in item and (not isinstance(item['source_view_hash'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', item['source_view_hash'])):
            raise ValueError('Invalid Columbus decoded source fingerprint; existing file was preserved')
        for span in item['spans']:
            if (not isinstance(span, list) or len(span) != 2
                    or any(type(n) is not int for n in span) or not 0 <= span[0] < span[1] <= 10_000_000):
                raise ValueError('Invalid Columbus context receipt span; existing file was preserved')
    continuations = value.get('continuations', {})
    if not isinstance(continuations, dict) or len(continuations) > 128:
        raise ValueError('Invalid Columbus receipt continuation table; existing file was preserved')
    for scope, cursor in continuations.items():
        if (not isinstance(scope, str) or not re.fullmatch('[0-9a-f]{64}', scope)
                or not isinstance(cursor, str) or not 1 <= len(cursor) <= 32768
                or not re.fullmatch('[A-Za-z0-9_-]+', cursor)):
            raise ValueError('Invalid Columbus receipt continuation; existing file was preserved')
    return value


class ReceiptFile:
    """Validate before use; replace only the exact receipt read by this caller."""

    def __init__(self, path: str, meta: dict):
        self.path = Path(path).expanduser().absolute()
        if self.path.is_symlink() or (self.path.exists() and not self.path.is_file()):
            raise ValueError('Receipt must be a regular, non-symlink file')
        self.original = None
        if self.path.exists():
            if self.path.stat().st_size > MAX_BYTES:
                raise ValueError('Receipt exceeds 1 MiB; existing file was preserved')
            self.original = self.path.read_bytes()
            try:
                self.data = validate(json.loads(self.original))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError('Invalid Columbus context receipt JSON; existing file was preserved') from exc
        else:
            self.data = {'schema': SCHEMA, 'repository': repository_key(meta['root']),
                         'revision': meta['revision'], 'files': {}, 'continuations': {}}
        if self.data['repository'] != repository_key(meta['root']):
            raise ValueError('Receipt belongs to another repository; existing file was preserved')
        self.data = ReceiptState(self.data)

    def save(self, packet: dict) -> None:
        updated = json.loads(json.dumps(self.data))
        updated['schema'] = SCHEMA
        if updated['revision'] != packet['revision']:
            updated['continuations'] = {}
        else:
            updated.setdefault('continuations', {})
        updated['revision'] = packet['revision']
        continuation = packet.get('receipt', {})
        scope = continuation.get('continuation_scope')
        cursor = continuation.get('next_cursor')
        if 'has_more' in continuation and scope is None and self.data.pending is None:
            raise ValueError('Context continuation belongs to another receipt state; retry retrieval')
        if self.data.pending is not None:
            expected, scope, cursor = self.data.pending
            if expected != packet_key(packet):
                raise ValueError('Context response changed before receipt save; retry retrieval')
        if scope is not None:
            updated['continuations'].pop(scope, None)
            if cursor is not None:
                updated['continuations'][scope] = cursor
                # Eviction restarts only candidate discovery; source receipts remain intact.
                while len(updated['continuations']) > 128:
                    updated['continuations'].pop(next(iter(updated['continuations'])))
        for item in packet['items']:
            if not item.get('source'):
                continue
            previous = updated['files'].get(item['path'], {})
            compatible = (previous.get('source_hash') == item['source_hash']
                          and previous.get('source_view_hash') == item['source_view_hash'])
            spans = previous.get('spans', []) if compatible else []
            updated['files'][item['path']] = {
                'source_hash': item['source_hash'],
                'source_view_hash': item['source_view_hash'],
                'spans': merge_spans([*spans, [item['source_start_offset'], item['source_end_offset']]])}
        validate(updated)
        data = (json.dumps(updated, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
        if len(data) > MAX_BYTES:
            raise ValueError('Receipt exceeds 1 MiB; use a new receipt file')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.original is None:
            with self.path.open('xb') as stream:
                stream.write(data)
            return
        if self.path.is_symlink() or self.path.read_bytes() != self.original:
            raise ValueError('Receipt changed during retrieval; retry with the current file')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix='.columbus-receipt-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
