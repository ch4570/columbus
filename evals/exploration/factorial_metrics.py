"""OpenAI CLI observations and all-attempt model-cost estimates for the new cohort.

Cached reads and reported cache writes are subsets of total input; reasoning is
a subset of output. Missing details stay unknown. A supplied price contract may
explicitly include unreported cache writes in ordinary input, otherwise their
absence prevents a monetary estimate. These estimates are not provider bills.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal
import math
import re


TOKEN_FIELDS = ('input_tokens', 'cached_input_tokens', 'uncached_input_tokens',
                'cache_write_tokens', 'output_tokens', 'reasoning_tokens')
REQUIRED_TOKENS = ('input_tokens', 'cached_input_tokens', 'output_tokens')
TOOL_TYPES = {'command_execution', 'mcp_tool_call', 'web_search', 'file_change',
              'collab_agent_tool_call'}
NON_TOOL_TYPES = {'agent_message', 'reasoning', 'todo_list', 'plan', 'error'}
COUNT_FIELDS = ('tool_calls', 'command_output_bytes', 'failed_commands',
                'duplicate_commands', 'model_round_trips')


def _count(value, label):
    if type(value) is not int or not 0 <= value <= 2**63 - 1:
        raise ValueError(f'{label} must be a nonnegative integer through 2^63-1')
    return value


def _finite_nonnegative(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _usage(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('usage must be an object or null')
    for key in (*TOKEN_FIELDS, 'cache_write_input_tokens', 'reasoning_output_tokens'):
        if value.get(key) is not None:
            _count(value[key], key)
    if ('cache_write_input_tokens' in value and 'cache_write_tokens' in value
            and value['cache_write_input_tokens'] != value['cache_write_tokens']):
        raise ValueError('Conflicting cache-write-token details')
    if any(value.get(key) is None for key in REQUIRED_TOKENS):
        return None
    result = {key: value.get(key) for key in TOKEN_FIELDS}
    result['uncached_input_tokens'] = value['input_tokens'] - value['cached_input_tokens']
    if result['uncached_input_tokens'] < 0:
        raise ValueError('Cached input exceeds total input')
    if (value.get('uncached_input_tokens') is not None
            and value['uncached_input_tokens'] != result['uncached_input_tokens']):
        raise ValueError('Uncached input disagrees with total input minus cached input')
    writes = value.get('cache_write_input_tokens')
    if writes is not None:
        result['cache_write_tokens'] = writes
    reasoning = value.get('reasoning_output_tokens')
    if reasoning is not None:
        if result['reasoning_tokens'] is not None and result['reasoning_tokens'] != reasoning:
            raise ValueError('Conflicting reasoning-token details')
        result['reasoning_tokens'] = reasoning
    if (result['cache_write_tokens'] is not None
            and result['cache_write_tokens'] > result['uncached_input_tokens']):
        raise ValueError('Cache writes overlap cached reads or exceed total input')
    if result['reasoning_tokens'] is not None and result['reasoning_tokens'] > result['output_tokens']:
        raise ValueError('Reasoning tokens exceed total output')
    return result


def _sum_usage(values):
    if not values or any(value is None for value in values):
        return None
    return {key: None if any(value[key] is None for value in values)
            else sum(value[key] for value in values) for key in TOKEN_FIELDS}


def parse_events(events: list[dict]) -> dict:
    """Read observed CLI events without equating completed turns with API trips.

    Multiple terminal turn events require distinct turn IDs: without identity,
    replayed events and independent turns cannot safely be distinguished.
    Tool counts include started tools; output/failure counts are null when a
    command has no complete observation. Non-shell tools are explicitly listed.
    """
    if not isinstance(events, list):
        raise ValueError('events must be a list')
    turns, tools, terminal_ids, unknown = [], {}, set(), set()
    active_turns, started_ids = [], set()
    turn_scope_known = True
    incomplete_tool_identity = False
    for number, event in enumerate(events):
        if not isinstance(event, dict) or not isinstance(event.get('type'), str):
            raise ValueError('Each event requires a string type')
        kind = event['type']
        if kind == 'turn.started':
            turn_id = event.get('turn_id', event.get('id'))
            if turn_id is not None:
                if (not isinstance(turn_id, str) or not turn_id or turn_id in started_ids
                        or turn_id in terminal_ids):
                    raise ValueError('Invalid or duplicate started turn ID')
                started_ids.add(turn_id)
            if active_turns:
                turn_scope_known = False
            active_turns.append(turn_id)
        if kind in {'turn.completed', 'turn.failed'}:
            turn_id = event.get('turn_id', event.get('id'))
            if active_turns:
                started_id = active_turns.pop(0)
                if started_id is not None and turn_id is not None and turn_id != started_id:
                    turn_scope_known = False
                if turn_id is None:
                    turn_id = started_id
            if turn_id is not None:
                if not isinstance(turn_id, str) or not turn_id or turn_id in terminal_ids:
                    raise ValueError('Invalid or duplicate terminal turn ID')
                terminal_ids.add(turn_id)
            turns.append((turn_id, _usage(event.get('usage'))))
        if kind not in {'item.started', 'item.updated', 'item.completed'}:
            continue
        item = event.get('item')
        if not isinstance(item, dict) or not isinstance(item.get('type'), str):
            raise ValueError('Item events require a typed item')
        item_type = item['type']
        if item_type in NON_TOOL_TYPES:
            continue
        if item_type != 'command_execution':
            unknown.add(item_type)
        identifier = item.get('id')
        if identifier is not None and (not isinstance(identifier, str) or not identifier):
            raise ValueError('Tool IDs must be nonempty strings')
        if identifier is None:
            if kind != 'item.completed':
                incomplete_tool_identity = True
                continue
            identifier = ('anonymous', number)
        previous = tools.get(identifier)
        if previous and (previous['complete'] or previous['item']['type'] != item_type):
            raise ValueError('Duplicate completed tool ID or inconsistent tool type')
        tools[identifier] = {'item': {**(previous['item'] if previous else {}), **item},
                             'complete': kind == 'item.completed'}
    usage = _sum_usage([value for _, value in turns])
    if (active_turns or not turn_scope_known or 'collab_agent_tool_call' in unknown
            or (len(turns) > 1 and any(identifier is None for identifier, _ in turns))):
        usage = None
    commands = [tool for tool in tools.values() if tool['item']['type'] == 'command_execution']
    output_bytes, failures, command_text = 0, 0, []
    output_known = failures_known = duplicates_known = not incomplete_tool_identity
    for tool in commands:
        item = tool['item']
        command = item.get('command')
        if command is not None and not isinstance(command, str):
            raise ValueError('Command text must be a string or null')
        if command is None:
            duplicates_known = False
        else:
            command_text.append(command)
        output = item.get('aggregated_output')
        if output is not None and not isinstance(output, str):
            raise ValueError('Command output must be a string or null')
        code = item.get('exit_code')
        if code is not None and type(code) is not int:
            raise ValueError('Command exit code must be an integer or null')
        if tool['complete'] and output is not None:
            output_bytes += len(output.encode('utf-8'))
        else:
            output_known = False
        if tool['complete'] and code is not None:
            failures += code != 0
        else:
            failures_known = False
    tool_count_known = not incomplete_tool_identity and not (unknown - TOOL_TYPES)
    return {'usage': usage, 'usage_complete': usage is not None,
            'tool_calls': len(tools) if tool_count_known else None,
            'command_output_bytes': output_bytes if output_known else None,
            'failed_commands': failures if failures_known else None,
            'duplicate_commands': len(command_text) - len(set(command_text)) if duplicates_known else None,
            'model_round_trips': None,
            'turn_failed': any(event['type'] == 'turn.failed' for event in events),
            'unknown_tools': sorted(unknown)}


def _prices(value):
    if value is None:
        return None
    required = {'provider', 'model', 'effective_date', 'currency', 'rates_per_million'}
    if not isinstance(value, dict) or set(value) not in (required, required | {'cache_write_accounting'}):
        raise ValueError('Price contract requires provider/model/date/currency and four token rates')
    if value['provider'] != 'openai' or not isinstance(value['model'], str) or not value['model'].strip():
        raise ValueError('Only explicit OpenAI model prices are supported')
    if not isinstance(value['effective_date'], str):
        raise ValueError('Price effective_date must be YYYY-MM-DD')
    try:
        if date.fromisoformat(value['effective_date']).isoformat() != value['effective_date']:
            raise ValueError('Noncanonical price date')
    except ValueError as exc:
        raise ValueError('Price effective_date must be YYYY-MM-DD') from exc
    if not isinstance(value['currency'], str) or not re.fullmatch('[A-Z]{3}', value['currency']):
        raise ValueError('Price currency must be three uppercase letters')
    rates = value['rates_per_million']
    if not isinstance(rates, dict) or set(rates) != {'ordinary_input', 'cache_read', 'cache_write', 'output'}:
        raise ValueError('Supply all four disjoint token rates per million')
    if any(not _finite_nonnegative(rate) for rate in rates.values()):
        raise ValueError('Price rates must be finite nonnegative numbers')
    accounting = value.get('cache_write_accounting', 'reported')
    if not isinstance(accounting, str) or accounting not in {'reported', 'included_in_ordinary_input'}:
        raise ValueError('Unknown cache write accounting contract')
    return {**value, 'rates_per_million': dict(rates),
            'cache_write_accounting': value.get('cache_write_accounting', 'reported')}


def _cost(usage, prices):
    if usage is None or prices is None:
        return None
    writes = usage['cache_write_tokens']
    if prices['cache_write_accounting'] == 'included_in_ordinary_input':
        writes = 0  # Explicit contract: no separate cache-write charge.
    if writes is None:
        return None
    quantities = {'ordinary_input': usage['uncached_input_tokens'] - writes,
                  'cache_read': usage['cached_input_tokens'], 'cache_write': writes,
                  'output': usage['output_tokens']}
    total = sum(Decimal(quantities[key]) * Decimal(str(rate))
                for key, rate in prices['rates_per_million'].items()) / Decimal(1_000_000)
    value = float(total)
    if not math.isfinite(value):
        raise ValueError('Calculated cost is not finite')
    return value


def summarize_attempts(records: list[dict], prices: dict | None = None) -> dict:
    """Include every root attempt and explicitly exclusive delegate's usage.

    Root attempts require task_id, arm, attempt_id, success, usage,
    usage_complete and elapsed_seconds. Delegate records inherit task_id/arm;
    nested delegates are rejected. A parent with delegates must declare
    usage_scope='self_only', or the arm's usage/cost stays unknown. Wall time
    sums root attempts only because delegate durations can overlap.
    """
    if not isinstance(records, list):
        raise ValueError('records must be a list')
    prices = _prices(prices)
    arms = {arm: [] for arm in 'ABCD'}
    seen = set()

    def validate(record, parent=None):
        if not isinstance(record, dict):
            raise ValueError('Each attempt must be an object')
        required = {'attempt_id', 'success', 'usage', 'usage_complete', 'elapsed_seconds'}
        if parent is None:
            required |= {'task_id', 'arm'}
        if not required <= set(record):
            raise ValueError('Attempt is missing required observation fields')
        task = record.get('task_id', parent['task_id'] if parent else None)
        arm = record.get('arm', parent['arm'] if parent else None)
        identifier = record['attempt_id']
        if (not isinstance(task, str) or not task or not isinstance(arm, str) or arm not in arms
                or not isinstance(identifier, str) or not identifier or identifier in seen):
            raise ValueError('Invalid task/arm or duplicate attempt ID')
        seen.add(identifier)
        if parent and (task != parent['task_id'] or arm != parent['arm']):
            raise ValueError('Delegate task and arm must match its parent')
        if type(record['success']) is not bool or type(record['usage_complete']) is not bool:
            raise ValueError('Attempt success and usage_complete must be booleans')
        elapsed = record['elapsed_seconds']
        if elapsed is not None and not _finite_nonnegative(elapsed):
            raise ValueError('Elapsed seconds must be finite and nonnegative, or null')
        if record.get('provider', 'openai') != 'openai':
            raise ValueError('Only OpenAI usage accounting is supported')
        for key in ('model', 'model_requested'):
            if key in record and (not isinstance(record[key], str) or not record[key].strip()):
                raise ValueError('Recorded model identity must be a nonempty string')
        for key in COUNT_FIELDS:
            if record.get(key) is not None:
                _count(record[key], key)
        if 'unknown_tools' in record and (not isinstance(record['unknown_tools'], list)
                or any(not isinstance(kind, str) or not kind for kind in record['unknown_tools'])):
            raise ValueError('Unknown tool observations must be a list of nonempty type names')
        usage = _usage(record['usage'])
        if record['usage_complete'] and usage is None:
            raise ValueError('Complete usage requires all three total token counters')
        delegates = record.get('delegates', [])
        if not isinstance(delegates, list) or (parent is not None and delegates):
            raise ValueError('Delegates must be a flat list of observations')
        return {**record, 'task_id': task, 'arm': arm, 'usage': usage, 'delegates': delegates}

    for record in records:
        root = validate(record)
        delegates = [validate(delegate, root) for delegate in root['delegates']]
        arms[root['arm']].append((root, delegates))
    result = {}
    for arm, groups in arms.items():
        roots = [root for root, _ in groups]
        delegates = [delegate for _, children in groups for delegate in children]
        all_records = roots + delegates
        scope_known = all(not children or root.get('usage_scope') == 'self_only' for root, children in groups)
        complete = bool(roots) and scope_known and all(record['usage_complete'] for record in all_records)
        usage = _sum_usage([record['usage'] for record in all_records]) if complete else None
        model_matches = prices is None or all(record.get('model', record.get('model_requested'))
                                              == prices['model'] for record in all_records)
        total_cost = _cost(usage, prices) if model_matches else None
        success = len({root['task_id'] for root in roots if root['success']})
        elapsed = [root['elapsed_seconds'] for root in roots]
        task_counts = Counter(root['task_id'] for root in roots)
        counts = {key: sum(record[key] for record in all_records)
                  if all_records and all(record.get(key) is not None for record in all_records) else None
                  for key in COUNT_FIELDS}
        result[arm] = {'attempts': len(roots), 'all_attempts': len(all_records),
                       'successful_tasks': success, 'failed_attempts': sum(not root['success'] for root in roots),
                       'retry_attempts': sum(count - 1 for count in task_counts.values()),
                       'delegate_attempts': len(delegates),
                       'failed_delegate_attempts': sum(not child['success'] for child in delegates),
                       'usage': usage, 'usage_complete': complete, 'delegate_scope_known': scope_known,
                       **counts,
                       'unknown_tools': sorted({kind for record in all_records for kind in record['unknown_tools']})
                       if all_records and all('unknown_tools' in record for record in all_records) else None,
                       'elapsed_seconds': None if any(value is None for value in elapsed) else sum(elapsed),
                       'total_cost': total_cost,
                       'cost_per_successful_task': total_cost / success if total_cost is not None and success else None}
    return {'arms': result, 'pricing': prices,
            'cost_scope': 'Supplied-rate model estimate across all attempts; not a provider bill or other tool charges.'}
