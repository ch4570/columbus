"""Opt-in, fail-closed admission for named CLI snippet sessions, not model billing."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

from .receipts import MAX_BYTES, ReceiptFile, repository_key

SCHEMA = 'columbus.session-budget/v1'
FILES = ('budget-policy.json', 'budget.json', '.budget.lock')
LIMITS = ('max_queries', 'max_session_bytes', 'max_no_progress')


class BudgetExceeded(ValueError):
    """Admission refused without reading source or producing a query payload."""


def _regular(path: Path) -> None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError('Session budget files must be regular files, never symlinks')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate session budget field')
        result[key] = value
    return result


def _read(path: Path) -> dict:
    _regular(path)
    if not path.exists() or path.stat().st_size > 8192:
        raise ValueError('Session budget state missing or oversized; usage was not reset')
    try:
        value = json.loads(path.read_bytes(), object_pairs_hook=_pairs)
    except (ValueError, UnicodeError) as exc:
        raise ValueError('Invalid session budget state; usage was not reset') from exc
    if not isinstance(value, dict):
        raise ValueError('Invalid session budget state; usage was not reset')
    return value


def _write(path: Path, value: dict, *, create=False) -> None:
    data = (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    _regular(path)
    if create:
        with path.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.budget-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _receipt_hash(directory: Path) -> str | None:
    path = directory / 'receipt.json'
    _regular(path)
    if not path.exists():
        return None
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Session receipt exceeds 1 MiB')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(directory: Path, root: Path):
    policy_path, state_path = (directory / name for name in FILES[:2])
    for path in (policy_path, state_path):
        _regular(path)
    if not policy_path.exists() and not state_path.exists():
        return None, None
    policy, state = _read(policy_path), _read(state_path)
    identity = {'schema', 'repository', 'generation', *LIMITS}
    if (set(policy) != identity or policy.get('schema') != SCHEMA
            or policy.get('repository') != repository_key(str(root))
            or not isinstance(policy.get('generation'), str) or len(policy['generation']) != 32
            or not any(policy.get(key) is not None for key in LIMITS)
            or any(policy.get(key) is not None and (type(policy[key]) is not int or not 1 <= policy[key] <= 2**63 - 1)
                   for key in LIMITS)):
        raise ValueError('Invalid session budget policy or repository ownership')
    fields = {'schema', 'repository', 'generation', 'policy_hash', 'queries', 'output_bytes',
              'no_progress', 'revision', 'receipt_hash', 'phase', 'reserved_bytes'}
    expected_hash = hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()
    if (set(state) != fields or any(state.get(key) != policy[key] for key in ('schema', 'repository', 'generation'))
            or state.get('policy_hash') != expected_hash
            or any(type(state.get(key)) is not int or state[key] < 0
                   for key in ('queries', 'output_bytes', 'no_progress', 'reserved_bytes'))
            or state.get('phase') not in ('idle', 'pending')
            or not isinstance(state.get('revision'), str) or len(state['revision']) > 128
            or (state.get('receipt_hash') is not None and (not isinstance(state['receipt_hash'], str)
                or len(state['receipt_hash']) != 64))
            or state['no_progress'] > state['queries']
            or (state['phase'] == 'idle' and state['reserved_bytes'] != 0)
            or (state['phase'] == 'pending' and (state['queries'] == 0 or not 1 <= state['reserved_bytes'] <= 64000))
            or (policy['max_queries'] is not None and state['queries'] > policy['max_queries'])
            or (policy['max_session_bytes'] is not None
                and state['output_bytes'] + state['reserved_bytes'] > policy['max_session_bytes'])):
        raise ValueError('Invalid or inconsistent session budget usage; usage was not reset')
    return policy, state


def _check_receipt(directory: Path, root: Path, state: dict) -> None:
    if state['receipt_hash'] != _receipt_hash(directory):
        raise ValueError('Session receipt changed outside budget accounting; usage was not reset')
    if state['receipt_hash'] is None:
        if state['revision'] or state['output_bytes']:
            raise ValueError('Session usage has no matching receipt revision; usage was not reset')
    else:
        receipt = ReceiptFile(str(directory / 'receipt.json'), {'root': str(root), 'revision': state['revision']})
        if receipt.data['revision'] != state['revision'] or not state['queries'] or not state['output_bytes']:
            raise ValueError('Session receipt revision differs from accounted delivery; usage was not reset')


def summary(directory: Path, root: Path) -> dict | None:
    """Read only; pending usage is deliberately not treated as completed or zero."""
    policy, state = _load(directory, root)
    if policy is None:
        return None
    if state['phase'] == 'idle':
        _check_receipt(directory, root, state)
    return {**state, 'policy': {key: policy[key] for key in LIMITS},
            'remaining_bytes': None if policy['max_session_bytes'] is None else
                policy['max_session_bytes'] - state['output_bytes'] - state['reserved_bytes'],
            'note': 'Only named CLI snippet admission and UTF-8 stdout payloads. Pending bytes are held, '
                    'not confirmed delivery. Diagnostics, stats, other tools and model billing are excluded.'}


class SessionBudget:
    """Exclusive lease across admission, retrieval, output and receipt accounting.

    Even unbudgeted sessions take the lease so enabling a policy cannot race a
    legacy caller. A stale lease is never stolen automatically.
    """

    def __init__(self, directory: Path, root: Path):
        self.directory, self.root = directory, root
        self.lock = directory / FILES[2]
        self.identity = None
        self.state = self.policy = None
        self.admitted = self.output_started = False
        directory.mkdir(parents=True, exist_ok=True)
        _regular(self.lock)
        try:
            with self.lock.open('xb') as stream:
                stream.write(uuid.uuid4().hex.encode('ascii'))
                stream.flush()
                stat = os.fstat(stream.fileno())
                self.identity = stat.st_dev, stat.st_ino
        except FileExistsError as exc:
            raise ValueError('Session is locked by another or interrupted caller; do not retry concurrently') from exc

    def admit(self, requested: dict, response_bytes: int) -> int:
        self.policy, self.state = _load(self.directory, self.root)
        if self.policy is None and any(value is not None for value in requested.values()):
            if any((self.directory / name).exists() for name in ('receipt.json', 'queries.jsonl')):
                raise ValueError('Cannot add a budget to an already used unbudgeted session')
            self.policy = {'schema': SCHEMA, 'repository': repository_key(str(self.root)),
                           'generation': uuid.uuid4().hex, **requested}
            self.state = {key: self.policy[key] for key in ('schema', 'repository', 'generation')}
            self.state.update(policy_hash=hashlib.sha256(json.dumps(self.policy, sort_keys=True).encode()).hexdigest(),
                              queries=0, output_bytes=0, no_progress=0, revision='', receipt_hash=None,
                              phase='idle', reserved_bytes=0)
            _write(self.directory / FILES[0], self.policy, create=True)
            _write(self.directory / FILES[1], self.state, create=True)
        if self.policy is None:
            return response_bytes
        if any(value is not None and value != self.policy[key] for key, value in requested.items()):
            raise ValueError('Stored session budget is immutable; limits cannot be changed implicitly')
        if self.state['phase'] != 'idle':
            raise ValueError('Session has interrupted delivery with reserved usage; inspect stats, do not reset usage')
        _check_receipt(self.directory, self.root, self.state)
        reason = None
        if self.policy['max_queries'] is not None and self.state['queries'] >= self.policy['max_queries']:
            reason = 'max_queries'
        elif self.policy['max_no_progress'] is not None and self.state['no_progress'] >= self.policy['max_no_progress']:
            reason = 'max_no_progress'
        if self.policy['max_session_bytes'] is not None:
            response_bytes = min(response_bytes, self.policy['max_session_bytes'] - self.state['output_bytes'])
            if response_bytes < 2048:
                reason = reason or 'remaining_bytes_below_2048'
        if reason:
            detail = {'reason': reason, 'queries': self.state['queries'], 'output_bytes': self.state['output_bytes'],
                      'no_progress': self.state['no_progress'], 'policy': {key: self.policy[key] for key in LIMITS},
                      'remaining_bytes': None if self.policy['max_session_bytes'] is None else
                          self.policy['max_session_bytes'] - self.state['output_bytes']}
            raise BudgetExceeded('session budget exhausted ' + json.dumps(detail, separators=(',', ':'))
                                 + '; not task completion. Inspect prior evidence/stats and narrow or change entry point.')
        self.state.update(queries=self.state['queries'] + 1, phase='pending', reserved_bytes=response_bytes)
        _write(self.directory / FILES[1], self.state)
        self.admitted = True
        return response_bytes

    def before_output(self, rendered: str) -> None:
        if not self.admitted:
            return
        size = len(rendered.encode('utf-8'))
        if size > self.state['reserved_bytes']:
            raise ValueError('Query output exceeds reserved session budget')
        self.state['reserved_bytes'] = size
        _write(self.directory / FILES[1], self.state)
        self.output_started = True

    def complete(self, packet: dict, receipt) -> None:
        if not self.admitted:
            return
        progress = any(item.get('source') for item in packet['items'])
        pending = receipt.data.pending
        if packet.get('receipt', {}).get('has_more') and pending is not None:
            _, scope, cursor = pending
            old = receipt.data.get('continuations', {}).get(scope) if receipt.data['revision'] == packet['revision'] else None
            progress = progress or (cursor is not None and cursor != old)
        self.state.update(output_bytes=self.state['output_bytes'] + self.state['reserved_bytes'],
                          no_progress=0 if progress else self.state['no_progress'] + 1,
                          revision=packet['revision'], receipt_hash=_receipt_hash(self.directory),
                          phase='idle', reserved_bytes=0)
        _write(self.directory / FILES[1], self.state)
        self.admitted = False

    def fail_before_output(self) -> None:
        if self.admitted and not self.output_started:
            self.state.update(no_progress=self.state['no_progress'] + 1, phase='idle', reserved_bytes=0)
            _write(self.directory / FILES[1], self.state)
            self.admitted = False

    def close(self) -> None:
        if self.identity is not None and not self.lock.is_symlink():
            try:
                stat = self.lock.stat()
                if (stat.st_dev, stat.st_ino) == self.identity:
                    self.lock.unlink()
            except FileNotFoundError:
                pass
