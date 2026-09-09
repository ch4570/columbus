"""Run one frozen six-execution group once; no resume or selective retry interface."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

_COMMON_PATH = Path(__file__).resolve().with_name('common.py')
_COMMON_KEY = '_source_call_cohort_' + hashlib.sha256(str(_COMMON_PATH).encode()).hexdigest()[:16]
if _COMMON_KEY not in sys.modules:
    _SPEC = importlib.util.spec_from_file_location(_COMMON_KEY, _COMMON_PATH)
    _COMMON = importlib.util.module_from_spec(_SPEC)
    sys.modules[_COMMON_KEY] = _COMMON
    _SPEC.loader.exec_module(_COMMON)
common = sys.modules[_COMMON_KEY]
HERE, LANGUAGES, CONDITIONS = common.HERE, common.LANGUAGES, common.CONDITIONS
OBSERVE, MODEL, EFFORT, TIMEOUT = common.OBSERVE, common.MODEL, common.EFFORT, common.TIMEOUT
argv, frozen_inputs, observation, prompt = common.argv, common.frozen_inputs, common.observation, common.prompt
read, require, save, schedule, sha = common.read, common.require, common.save, common.schedule, common.sha
verify_controls, verify_environment = common.verify_controls, common.verify_environment
verify_observation, disk_guard = common.verify_observation, common.disk_guard


def now():
    return datetime.now(timezone.utc).isoformat()


def evaluation_error(exc):
    # Model-derived error messages may themselves contain unpaired surrogates
    # or very long strings. Raw evidence, not this bounded diagnostic, is primary.
    message = str(exc)[:256].encode('ascii', errors='backslashreplace').decode('ascii')[:1024]
    return {'class': type(exc).__name__, 'message': message}


def trial(language, condition, repeat):
    require(language in LANGUAGES and condition in CONDITIONS and type(repeat) is int and repeat in (1, 2),
            'Unknown scheduled trial')
    frozen_inputs()
    verify_environment()
    before = {arm: verify_observation(language, arm) for arm in CONDITIONS}
    verify_controls(language, before)
    output = observation(language, condition)
    disk_guard(output)
    case = read(HERE / language / 'cases.json')['cases'][0]
    directory = output / 'trials' / f"{case['id']}-{condition}-{repeat}"
    directory.mkdir(parents=True, exist_ok=False)
    text = prompt(case, condition, output)
    with (directory / 'prompt.txt').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)
    command = argv(output, directory)
    save(directory / 'invocation.json', {'argv': command, 'model_requested': MODEL,
        'effort_requested': EFFORT, 'timeout_seconds': TIMEOUT, 'prompt_bytes': len(text.encode('utf-8')),
        'harness_sha256': sha(HERE / 'run.py'), 'common_sha256': sha(HERE / 'common.py'),
        'input_hashes_sha256': sha(HERE / 'input-hashes.json')})
    started = time.monotonic()
    with (directory / 'events.jsonl').open('xb') as stdout, (directory / 'stderr.log').open('xb') as stderr:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                   start_new_session=os.name != 'nt')
        save(directory / 'process.json', {'pid': process.pid, 'started_at': now()})
        timed_out = False
        try:
            process.communicate(text.encode('utf-8'), timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                if os.name != 'nt':
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    if os.name != 'nt':
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                except ProcessLookupError:
                    pass
                process.wait()
    # Preserve real process termination before parsing events or postflight can fail.
    save(directory / 'terminal.json', {'return_code': process.returncode, 'timed_out': timed_out,
        'finished_at': now(), 'elapsed_seconds': time.monotonic() - started})
    after = {arm: verify_observation(language, arm) for arm in CONDITIONS}
    frozen_inputs()
    verify_environment()
    raw = (directory / 'events.jsonl').read_bytes()
    base = {'case': case['id'], 'condition': condition, 'repeat': repeat,
        **read(directory / 'terminal.json'), 'usage': None,
        'preflight': before, 'postflight': after, 'events_sha256': sha(directory / 'events.jsonl')}
    # A harness/input serialization defect is a hard failure, never attributed
    # to model output. Keep this safe base for a model-serialization fallback.
    common.serialize(base)
    result = dict(base)
    # Model output errors invalidate this slot, not the remaining frozen
    # schedule. Input/environment/postflight errors above are never caught here.
    parse_errors = (ValueError, TypeError, AttributeError, KeyError, UnicodeError, RecursionError, OverflowError)
    try:
        events = [json.loads(line) for line in raw.splitlines() if line.strip()]
        result.update(OBSERVE.parse_events(events))
    except parse_errors as exc:
        result['evaluation_error'] = evaluation_error(exc)
    try:
        answer = read(directory / 'answer.json')
    except (FileNotFoundError, *parse_errors) as exc:
        answer = {}
        result.setdefault('evaluation_error', evaluation_error(exc))
    result['answer'] = answer
    try:
        result['quality'] = OBSERVE.grade(answer, case, output / 'repository')
    except parse_errors as exc:
        result.setdefault('evaluation_error', evaluation_error(exc))
        result['quality'] = {'passed': False, 'findings': [], 'note': 'Answer shape could not be graded.'}
    try:
        payload = common.serialize(result)
    except parse_errors as exc:
        # Drop every model-derived field, not only the answer: events can also
        # contain text that parses successfully but cannot be written as UTF-8.
        result = {**base, 'answer': {}, 'evaluation_error': evaluation_error(exc),
            'quality': {'passed': False, 'findings': [],
                        'note': 'Model output could not be serialized; raw answer and events retained.'}}
        payload = common.serialize(result)
    # Filesystem failures remain hard failures. Do not re-serialize one frame
    # deeper in save: that can exceed the recursion limit after validation passed.
    common.save_serialized(directory / 'result.json', payload)
    return result


def run(language):
    require(language in LANGUAGES, 'Unknown language')
    frozen_inputs()
    verify_environment()
    for condition in CONDITIONS:
        verify_observation(language, condition)
        require(not (observation(language, condition) / 'trials').exists(),
                'Existing trial directory: inspect original handle/evidence, never retry')
    group = observation(language, 'baseline').parent
    require(not (group / 'runner.json').exists() and not (group / 'runner-terminal.json').exists(),
            'Existing runner evidence: never resume or retry a scheduled group')
    disk_guard(group)
    save(group / 'runner.json', {'pid': os.getpid(), 'started_at': now(), 'schedule': schedule(language),
                               'input_hashes_sha256': sha(HERE / 'input-hashes.json')})
    for condition, repeat in schedule(language):
        result = trial(language, condition, repeat)
        print(json.dumps({'language': language, 'condition': condition, 'repeat': repeat,
            'return_code': result['return_code'], 'timed_out': result['timed_out'],
            'usage': result.get('usage'), 'citation': result.get('quality', {}).get('passed', False)}), flush=True)
    save(group / 'runner-terminal.json', {'finished_at': now(), 'status': 'all scheduled executions terminated'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('language', choices=LANGUAGES)
    run(parser.parse_args().language)
