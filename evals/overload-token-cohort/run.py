"""Run one predeclared four-execution task group; never resume by retrying a trial."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('saved_observer', HERE.parent / 'exploration/observe_saved_callers.py')
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


def verify_inputs(language=None):
    spec = importlib.util.spec_from_file_location('overload_launch_gate', HERE / 'collect.py')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    gate.frozen_inputs()
    environment = json.loads((HERE / 'environment.json').read_text())
    if subprocess.check_output(['codex', '--version'], text=True).strip() != environment['codex_cli']:
        raise ValueError('Codex CLI changed after freeze')
    if language is not None:
        gate.verify_observation(language, observer)


def run(language):
    verify_inputs(language)
    observation = Path('/tmp') / ('columbus-overload-token-' + language)
    case = json.loads((HERE / language / 'cases.json').read_text())['cases'][0]
    frozen = json.loads((HERE / language / 'freeze.json').read_text())
    if json.loads((observation / 'manifest.json').read_text()) != frozen['manifest']:
        raise ValueError('Frozen source/case manifest changed')
    if json.loads((observation / 'engine.json').read_text()) != frozen['engine']:
        raise ValueError('Frozen engine manifest changed')
    if (observation / 'trials').exists():
        raise ValueError('Trial directory exists; inspect the original live handle or terminal results, never retry')
    observer.dump(observation / 'runner.json', {'pid': os.getpid(), 'language': language})
    for repeat in (1, 2):
        first = ['columbus', 'baseline'] if language == 'kotlin' else ['baseline', 'columbus']
        order = first if repeat == 1 else list(reversed(first))
        for condition in order:
            verify_inputs(language)
            result = observer.trial(observation, case['id'], condition,
                                    model='gpt-5.6-sol', effort='xhigh', repeat=repeat, timeout=1200)
            print(json.dumps({'language': language, 'condition': condition, 'repeat': repeat,
                              'return_code': result['return_code'], 'timed_out': result['timed_out'],
                              'usage': result['usage'], 'citation': result['quality']['passed']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('language', choices=['java', 'kotlin', 'javascript'])
    run(parser.parse_args().language)
