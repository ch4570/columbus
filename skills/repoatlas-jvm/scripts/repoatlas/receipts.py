"""Caller-owned context receipts containing hashes and emitted character spans only."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

SCHEMA = 'repoatlas.context-receipt/v1'
MAX_BYTES = 1_048_576


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
    if not isinstance(value, dict) or set(value) != {'schema', 'repository', 'revision', 'files'}:
        raise ValueError('Invalid RepoAtlas context receipt; existing file was preserved')
    if (value['schema'] != SCHEMA or not isinstance(value['repository'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', value['repository'])
            or not isinstance(value['revision'], str) or len(value['revision']) > 128
            or not isinstance(value['files'], dict) or len(value['files']) > 2000):
        raise ValueError('Invalid RepoAtlas context receipt header; existing file was preserved')
    for path, item in value['files'].items():
        if (not isinstance(path, str) or len(path) > 4096 or not path
                or not isinstance(item, dict) or set(item) not in ({'source_hash', 'spans'}, {'source_hash', 'source_view_hash', 'spans'})
                or not isinstance(item['source_hash'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', item['source_hash'])
                or not isinstance(item['spans'], list) or len(item['spans']) > 10000):
            raise ValueError('Invalid RepoAtlas context receipt file entry; existing file was preserved')
        if 'source_view_hash' in item and (not isinstance(item['source_view_hash'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', item['source_view_hash'])):
            raise ValueError('Invalid RepoAtlas decoded source fingerprint; existing file was preserved')
        for span in item['spans']:
            if (not isinstance(span, list) or len(span) != 2
                    or any(type(n) is not int for n in span) or not 0 <= span[0] < span[1] <= 10_000_000):
                raise ValueError('Invalid RepoAtlas context receipt span; existing file was preserved')
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
                raise ValueError('Invalid RepoAtlas context receipt JSON; existing file was preserved') from exc
        else:
            self.data = {'schema': SCHEMA, 'repository': repository_key(meta['root']),
                         'revision': meta['revision'], 'files': {}}
        if self.data['repository'] != repository_key(meta['root']):
            raise ValueError('Receipt belongs to another repository; existing file was preserved')

    def save(self, packet: dict) -> None:
        updated = json.loads(json.dumps(self.data))
        updated['revision'] = packet['revision']
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
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix='.repoatlas-receipt-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
