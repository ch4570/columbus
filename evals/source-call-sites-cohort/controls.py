"""Capture and replay prospective model-free delivery controls without retries."""
from __future__ import annotations

import copy
import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

_COMMON_PATH = Path(__file__).resolve().with_name('common.py')
_COMMON_KEY = '_source_call_cohort_' + hashlib.sha256(str(_COMMON_PATH).encode()).hexdigest()[:16]
if _COMMON_KEY not in sys.modules:
    _SPEC = importlib.util.spec_from_file_location(_COMMON_KEY, _COMMON_PATH)
    _COMMON = importlib.util.module_from_spec(_SPEC)
    sys.modules[_COMMON_KEY] = _COMMON
    _SPEC.loader.exec_module(_COMMON)
common = sys.modules[_COMMON_KEY]


def specifications(relationships, citation):
    rows = []
    for arm in ('control', 'candidate'):
        for index, relationship in enumerate(relationships):
            for form in ('json', 'text'):
                rows.append({'kind': 'relationship', 'condition': arm, 'relationship_index': index,
                    'format': form, 'arguments': ['archive-neighbors', relationship['source'],
                    '--direction', 'out', '--kinds', 'calls', '--context-lines', '2',
                    '--limit', '50', '--budget-bytes', '64000', '--format', form]})
    arguments = ['archive-quotes', '--budget-bytes', '64000']
    ranges = []
    for finding in citation['answer']['findings']:
        value = (finding['path'], str(finding['start_line']), str(finding['end_line']))
        if value not in ranges:
            ranges.append(value)
            arguments.extend(['--range', *value])
    for arm in ('control', 'candidate'):
        rows.append({'kind': 'quotes', 'condition': arm, 'arguments': list(arguments)})
    for index, relationship in enumerate(relationships):
        for form in ('json', 'text'):
            rows.append({'kind': 'source_calls', 'condition': 'candidate', 'relationship_index': index,
                'format': form, 'arguments': ['archive-source', relationship['source'], '--call-sites',
                '--limit', '400', '--budget-bytes', '64000', '--format', form]})
    rows.append({'kind': 'unavailable', 'condition': 'control', 'arguments': [
        'archive-source', relationships[0]['source'], '--call-sites', '--format', 'json']})
    return rows


def command(output, arguments):
    return [sys.executable, '-B', str(output / 'runtime/columbus.py'), *arguments,
            '--input', str(output / 'graph.jsonl.xz'), '--repo', '.']


def event(argv, result, identifier):
    return {'type': 'item.completed', 'item': {'type': 'command_execution', 'id': identifier,
        'command': shlex.join(argv), 'exit_code': result['return_code'], 'status': 'completed',
        'aggregated_output': result['stdout']}}


def capture(spec, output, index, directory):
    """Retain actual bytes even if process launch, timeout or UTF-8 decoding fails."""
    argv = command(output, spec['arguments'])
    row = {**spec, 'argv': argv, 'cwd': str(output / 'repository'), 'timed_out': False}
    failure = None
    try:
        result = subprocess.run(argv, cwd=output / 'repository', capture_output=True, timeout=120)
        stdout, stderr = result.stdout, result.stderr
        row['return_code'] = result.returncode
    except (subprocess.TimeoutExpired, OSError) as error:
        stdout = error.stdout or b'' if isinstance(error, subprocess.TimeoutExpired) else b''
        stderr = error.stderr or b'' if isinstance(error, subprocess.TimeoutExpired) else b''
        row.update(return_code=None, timed_out=isinstance(error, subprocess.TimeoutExpired),
                   execution_error={'class': type(error).__name__, 'message': str(error)})
        failure = error
    row.update(stdout_base64=base64.b64encode(stdout).decode('ascii'),
               stderr_base64=base64.b64encode(stderr).decode('ascii'),
               stdout_sha256=common.OBSERVE.sha(stdout), stderr_sha256=common.OBSERVE.sha(stderr))
    try:
        row.update(stdout=stdout.decode('utf-8'), stderr=stderr.decode('utf-8'))
    except UnicodeError as error:
        row['decode_error'] = {'class': type(error).__name__, 'message': str(error)}
        failure = failure or error
    if failure is None:
        row['event'] = event(argv, row, f'control-{index:03d}')
    common.save(directory / 'control-raw' / f'{index:03d}.json', row)
    if failure is not None:
        raise ValueError('Control attempt failed; original bytes retained, never retry this capture') from failure
    return row


def receipt_checks(row, output, relationships, recognizer):
    """Recompute positive and negative results, never trust captured booleans."""
    actual = row['event']
    recognized = recognizer.evidence([actual], output, relationships)
    kind = row['kind']
    if kind == 'unavailable':
        common.require(row['return_code'] != 0 and not row['stdout'], 'Control unexpectedly supports call-sites')
        common.require(not recognized['relationship_used'] and not recognized['source_calls_used']
                       and not recognized['quotes_used'], 'Failed unavailable command received credit')
        return {'positive': recognized, 'unavailable_rejected': True}
    common.require(row['return_code'] == 0, 'Positive control command failed')
    if kind == 'quotes':
        common.require(recognized['quotes_used'] and not recognized['relationship_used']
                       and not recognized['source_calls_used'], 'Quotes confused with useful calls')
    else:
        common.require(recognized['relationship_used'] and not recognized['quotes_used'],
                       'Reviewed relationship was not delivered')
        common.require(recognized['source_calls_used'] is (kind == 'source_calls'), 'Source/call adoption differs')
    failed = copy.deepcopy(actual)
    failed['item']['exit_code'] = 1
    rejected = recognizer.evidence([failed], output, relationships)
    common.require(not any(rejected[key] for key in ('relationship_used', 'source_calls_used', 'quotes_used')),
                   'Failed command received credit')
    wrong = [{**relationship, 'line': relationship['line'] + 100000} for relationship in relationships]
    wrong_receipt = recognizer.evidence([actual], output, wrong)
    common.require(not wrong_receipt['relationship_used'], 'Wrong reviewed tuple received credit')
    checks = {'positive': recognized, 'failed_command_rejected': True, 'wrong_tuple_rejected': True,
              'unrelated_relationship': wrong_receipt}
    if kind in ('quotes', 'source_calls'):
        corrupt = copy.deepcopy(actual)
        if row.get('format', 'json') == 'json':
            packet = json.loads(corrupt['item']['aggregated_output'])
            if kind == 'quotes':
                packet['quotes'][0]['quote'] += '__not_source__'
            else:
                # An extra packet field is not part of the exact bound format.
                packet['__forged_packet__'] = True
            corrupt['item']['aggregated_output'] = json.dumps(packet)
        else:
            corrupt['item']['aggregated_output'] += '__forged_packet__\n'
        rejected = recognizer.evidence([corrupt], output, relationships)
        common.require(not any(rejected[key] for key in ('relationship_used', 'source_calls_used', 'quotes_used')),
                       'Tampered source packet received credit')
        checks['corrupt_packet_rejected'] = True
    return checks


def citation_checks(language, case):
    citations = common.read(common.HERE / language / 'citation-controls.json')
    for expected, answer, passed in (('positive', 'answer', True), ('negative', 'negative_answer', False)):
        grade = common.OBSERVE.grade(citations[answer], case, common.observation(language, 'candidate') / 'repository')
        common.require(grade == citations[expected] and grade['passed'] is passed, 'Citation control differs')
        ids = {finding['id'] for finding in case['findings']}
        common.require(len(grade['findings']) == len(ids) and {row['id'] for row in grade['findings']} == ids
                       and all(row['passed'] is passed for row in grade['findings']), 'Incomplete citation controls')
    return citations


def verify_controls(language, case, preflight, recognizer):
    directory = common.HERE / language
    saved = common.read(directory / 'controls.json')
    common.require(saved.get('passed') is True and saved.get('model_started') is False, 'Controls incomplete')
    common.require(saved.get('preflight') == preflight == saved.get('postflight'), 'Control preflight changed')
    citations = citation_checks(language, case)
    relationships = common.read(directory / 'relationships.json')
    common.require(isinstance(relationships, list) and relationships, 'No reviewed relationships')
    specs = specifications(relationships, citations)
    rows = saved['rows']
    common.require(isinstance(rows, list) and len(rows) == len(specs), 'Missing or extra control slots')
    raw_directory = directory / 'control-raw'
    expected_files = {f'{index:03d}.json' for index in range(len(specs))} | {'attempt.json'}
    common.require({path.name for path in raw_directory.iterdir()} == expected_files,
                   'Missing or extra raw control receipts')
    attempt = common.read(raw_directory / 'attempt.json')
    common.require(attempt.get('specifications') == specs and attempt.get('model_started') is False
                   and type(attempt.get('harness_pid')) is int and attempt['harness_pid'] > 0
                   and datetime.fromisoformat(attempt['started_at']).tzinfo is not None,
                   'Invalid original control attempt marker')
    for index, (spec, row) in enumerate(zip(specs, rows)):
        common.require(all(row.get(key) == value for key, value in spec.items()), 'Control specification changed')
        output = common.observation(language, spec['condition'])
        argv = command(output, spec['arguments'])
        common.require(row.get('argv') == argv and row.get('cwd') == str(output / 'repository'), 'Control invocation changed')
        common.require(type(row.get('return_code')) is int and isinstance(row.get('stdout'), str)
                       and isinstance(row.get('stderr'), str) and row.get('timed_out') is False
                       and 'execution_error' not in row and 'decode_error' not in row, 'Malformed raw control output')
        raw_stdout = base64.b64decode(row['stdout_base64'], validate=True)
        raw_stderr = base64.b64decode(row['stderr_base64'], validate=True)
        common.require(raw_stdout == row['stdout'].encode('utf-8') and raw_stderr == row['stderr'].encode('utf-8')
                       and row['stderr_sha256'] == common.OBSERVE.sha(raw_stderr), 'Control raw bytes differ')
        common.require(row.get('event') == event(argv, row, f'control-{index:03d}')
                       and row.get('stdout_sha256') == common.OBSERVE.sha(row['stdout'].encode()), 'Raw control output differs')
        raw = {key: value for key, value in row.items() if key != 'recognition'}
        common.require(common.read(raw_directory / f'{index:03d}.json') == raw, 'Original control receipt differs')
        subset = [relationships[spec['relationship_index']]] if 'relationship_index' in spec else relationships
        common.require(row['recognition'] == receipt_checks(row, output, subset, recognizer), 'Control recognition differs')


def controls(language):
    directory = common.HERE / language
    common.require(not (directory / 'controls.json').exists() and not (directory / 'control-raw').exists(),
                   'Control capture already attempted; preserve it, never overwrite or retry')
    case = common.read(directory / 'cases.json')['cases'][0]
    citations = citation_checks(language, case)
    relationships = common.read(directory / 'relationships.json')
    common.require(isinstance(relationships, list) and relationships, 'Reviewed relationships missing')
    before = {arm: common.verify_observation(language, arm) for arm in common.CONDITIONS}
    recognizer = common.module('capture_recognizer', common.HERE / 'recognize.py')
    specs = specifications(relationships, citations)
    # Reserve the attempt before any process can start, including a launch failure.
    common.save(directory / 'control-raw/attempt.json', {'model_started': False,
        'harness_pid': os.getpid(), 'started_at': datetime.now(timezone.utc).isoformat(), 'specifications': specs})
    rows = []
    for index, spec in enumerate(specs):
        output = common.observation(language, spec['condition'])
        row = capture(spec, output, index, directory)
        subset = [relationships[spec['relationship_index']]] if 'relationship_index' in spec else relationships
        row['recognition'] = receipt_checks(row, output, subset, recognizer)
        rows.append(row)
    after = {arm: common.verify_observation(language, arm) for arm in common.CONDITIONS}
    common.require(before == after, 'Inputs changed during controls')
    common.save(directory / 'controls.json', {'passed': True, 'model_started': False,
                'preflight': before, 'postflight': after, 'rows': rows})
    verify_controls(language, case, after, recognizer)


if __name__ == '__main__':
    for language in common.LANGUAGES:
        controls(language)
