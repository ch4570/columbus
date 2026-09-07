"""Opt-in local query measurements. Never store queries, paths, or source text."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path

SCHEMA = 'repoatlas.query-telemetry/v1'
COMMANDS = {'map', 'search', 'context', 'symbol', 'neighbors', 'impact'}
FIELDS = {'schema', 'timestamp', 'command', 'format', 'revision', 'output_bytes',
          'estimated_tokens', 'duration_ms', 'returned_items', 'returned_edges',
          'source_bytes', 'omitted_candidates', 'seen_candidates', 'truncated'}


def _validate(row: dict) -> dict:
    if (not isinstance(row, dict) or set(row) != FIELDS or row.get('schema') != SCHEMA
            or row.get('command') not in COMMANDS or row.get('format') not in {'json', 'text'}
            or not isinstance(row.get('revision'), str) or len(row['revision']) > 128
            or not isinstance(row.get('timestamp'), str) or len(row['timestamp']) > 64
            or type(row.get('truncated')) is not bool):
        raise ValueError('File is not a RepoAtlas query telemetry log; existing content was preserved')
    for field in ('output_bytes', 'estimated_tokens', 'duration_ms', 'returned_items', 'returned_edges',
                  'source_bytes', 'omitted_candidates', 'seen_candidates'):
        if type(row[field]) not in (int, float) or not math.isfinite(row[field]) or row[field] < 0:
            raise ValueError('Invalid RepoAtlas telemetry measurement; existing content was preserved')
    return row


def _read(path: Path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Telemetry must be a regular, non-symlink file')
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('Telemetry log exceeds 32 MiB; choose a new log file')
    with path.open(encoding='utf-8') as stream:
        for number, line in enumerate(stream, 1):
            try:
                if len(line) > 8192 or not line.endswith('\n'):
                    raise ValueError('incomplete or oversized line')
                yield _validate(json.loads(line))
            except (UnicodeError, ValueError) as exc:
                raise ValueError(f'Invalid RepoAtlas telemetry at line {number}; existing content was preserved') from exc


class TelemetryLog:
    def __init__(self, path: str):
        self.path = Path(path).expanduser().absolute()
        if self.path.is_symlink():
            raise ValueError('Telemetry must be a regular, non-symlink file')
        self.existed = self.path.exists()
        if self.existed:
            rows = sum(1 for _ in _read(self.path))
            if not rows:
                raise ValueError('Existing empty telemetry file has no RepoAtlas ownership marker; preserved')

    def append(self, command: str, output_format: str, packet: dict, rendered: str, duration: float) -> None:
        output_bytes = len(rendered.encode('utf-8'))
        items = packet.get('items', packet.get('hits', packet.get('nodes', [packet] if 'id' in packet else [])))
        row = _validate({'schema': SCHEMA, 'timestamp': datetime.now(timezone.utc).isoformat(),
                         'command': command, 'format': output_format, 'revision': packet['revision'],
                         'output_bytes': output_bytes, 'estimated_tokens': math.ceil(output_bytes / 3),
                         'duration_ms': round(duration * 1000, 3), 'returned_items': len(items),
                         'returned_edges': len(packet.get('edges', [])),
                         'source_bytes': sum(len(item.get('source', '').encode('utf-8')) for item in items),
                         'omitted_candidates': packet.get('omitted_candidates', 0),
                         'seen_candidates': packet.get('seen_candidates', 0),
                         'truncated': bool(packet.get('truncated'))})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.existed:
            # Revalidate after retrieval so a replaced non-telemetry file is
            # never appended to. Concurrent writers should use separate logs.
            list(_read(self.path))
        with self.path.open('a' if self.existed else 'x', encoding='utf-8') as stream:
            stream.write(json.dumps(row, separators=(',', ':')) + '\n')


def summarize(path: str) -> dict:
    count, totals, commands, formats = 0, Counter(), Counter(), Counter()
    for row in _read(Path(path).expanduser().absolute()):
        count += 1
        commands[row['command']] += 1
        formats[row['format']] += 1
        for key in ('output_bytes', 'estimated_tokens', 'duration_ms', 'returned_items', 'returned_edges',
                    'source_bytes', 'omitted_candidates', 'seen_candidates'):
            totals[key] += row[key]
    return {'schema': SCHEMA, 'queries': count, 'commands': dict(commands), 'formats': dict(formats),
            **totals, 'duration_ms': round(totals['duration_ms'], 3),
            'note': 'Local response measurements. Estimated tokens = ceil(UTF-8 output bytes/3) per query; '
                    'not measured model input, cached tokens, billing, or savings versus a baseline.'}


def summary_text(summary: dict) -> str:
    return (f"RepoAtlas local telemetry: {summary['queries']} queries\n"
            f"commands={json.dumps(summary['commands'], separators=(',', ':'))} "
            f"formats={json.dumps(summary['formats'], separators=(',', ':'))}\n"
            f"output_bytes={summary.get('output_bytes', 0)} estimated_tokens={summary.get('estimated_tokens', 0)} "
            f"source_bytes={summary.get('source_bytes', 0)} duration_ms={summary['duration_ms']}\n"
            f"returned_items={summary.get('returned_items', 0)} omitted={summary.get('omitted_candidates', 0)} "
            f"seen={summary.get('seen_candidates', 0)}\n{summary['note']}\n")
