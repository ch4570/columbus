"""Run exactly one frozen six-execution group; no selective retries or resume."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import signal
import subprocess
import time

from common import (HERE, LANGUAGES, CONDITIONS, OBSERVE, argv, frozen_inputs, observation,
                    prompt, read, require, save, schedule, sha, verify_controls, verify_environment, verify_observation)


def now():
    return datetime.now(timezone.utc).isoformat()


def trial(language, condition, repeat):
    frozen_inputs()
    verify_environment()
    before = {arm: verify_observation(language, arm) for arm in CONDITIONS}
    verify_controls(language, before)
    output = observation(language, condition)
    case = read(HERE / language / 'cases.json')['cases'][0]
    directory = output / 'trials' / f"{case['id']}-{condition}-{repeat}"
    directory.mkdir(parents=True, exist_ok=False)
    text = prompt(case, condition, output)
    with (directory / 'prompt.txt').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)
    command = argv(output, directory)
    save(directory / 'invocation.json', {'argv': command, 'model_requested': 'gpt-5.6-sol',
         'effort_requested': 'xhigh', 'timeout_seconds': 1200, 'prompt_bytes': len(text.encode()),
         'harness_sha256': sha(HERE / 'run.py'), 'common_sha256': sha(HERE / 'common.py'),
         'input_hashes_sha256': sha(HERE / 'input-hashes.json')})
    started = time.monotonic()
    with (directory / 'events.jsonl').open('x') as stdout, (directory / 'stderr.log').open('x') as stderr:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                   start_new_session=os.name != 'nt')
        save(directory / 'process.json', {'pid': process.pid, 'started_at': now()})
        timed_out = False
        try:
            process.communicate(text.encode('utf-8'), timeout=1200)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name != 'nt':
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                if os.name != 'nt':
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait()
    # Preserve process termination even if parsing or the postflight subsequently fails.
    save(directory / 'terminal.json', {'return_code': process.returncode, 'timed_out': timed_out,
                                      'finished_at': now(), 'elapsed_seconds': time.monotonic() - started})
    # Run integrity checks even when the following event/usage parser rejects model output.
    after = {arm: verify_observation(language, arm) for arm in CONDITIONS}
    frozen_inputs()
    verify_environment()
    raw = (directory / 'events.jsonl').read_bytes()
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    observed = OBSERVE.parse_events(events)
    try:
        answer = read(directory / 'answer.json')
    except (OSError, ValueError):
        answer = {}
    result = {'case': case['id'], 'condition': condition, 'repeat': repeat,
              **read(directory / 'terminal.json'), **observed, 'answer': answer,
              'quality': OBSERVE.grade(answer, case, output / 'repository'),
              'preflight': before, 'postflight': after, 'events_sha256': sha(directory / 'events.jsonl')}
    save(directory / 'result.json', result)
    return result


def run(language):
    frozen_inputs()
    verify_environment()
    for condition in CONDITIONS:
        verify_observation(language, condition)
        require(not (observation(language, condition) / 'trials').exists(),
                'Existing trial directory: inspect original handle/evidence, never retry')
    group = observation(language, 'baseline').parent
    save(group / 'runner.json', {'pid': os.getpid(), 'started_at': now(), 'schedule': schedule(language),
                               'input_hashes_sha256': sha(HERE / 'input-hashes.json')})
    for condition, repeat in schedule(language):
        result = trial(language, condition, repeat)
        print(json.dumps({'language': language, 'condition': condition, 'repeat': repeat,
                          'return_code': result['return_code'], 'timed_out': result['timed_out'],
                          'usage': result['usage'], 'citation': result['quality']['passed']}), flush=True)
    save(group / 'runner-terminal.json', {'finished_at': now(), 'status': 'all scheduled executions terminated'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('language', choices=LANGUAGES)
    run(parser.parse_args().language)
