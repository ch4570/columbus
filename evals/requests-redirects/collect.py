"""Collect terminal observations; never launch or retry a model trial."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

parser = argparse.ArgumentParser()
parser.add_argument('observation', type=Path)
args = parser.parse_args()
here = Path(__file__).resolve().parent
root = here.parents[1]
spec = importlib.util.spec_from_file_location(
    'observe', here.parent / 'exploration/observe_saved_callers.py')
observe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observe)
manifest = json.loads((args.observation / 'manifest.json').read_text())
engine = json.loads((args.observation / 'engine.json').read_text())
for name, digest in json.loads((here / 'input-hashes.json').read_text()).items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name
assert observe.manifest(args.observation / 'repository') == manifest['source_manifest']
assert observe.manifest(args.observation / 'runtime') == engine['files']
gate = observe.archive_gate(args.observation, engine)
results, terminal = {}, {}
for condition in ('baseline', 'columbus'):
    trial = args.observation / 'trials' / f'requests-redirects-{condition}-1'
    result = json.loads((trial / 'result.json').read_text())
    events_bytes = (trial / 'events.jsonl').read_bytes()
    assert hashlib.sha256(events_bytes).hexdigest() == result['events_sha256']
    assert result['source_unchanged']
    events = [json.loads(line) for line in events_bytes.splitlines()]
    completed = sum(event.get('type') == 'turn.completed' for event in events)
    terminal[condition] = {'completed_turns': completed,
                           'timed_out': result['timed_out'],
                           'turn_failed': result['turn_failed']}
    if not result['timed_out'] and not result['turn_failed'] and result['return_code'] == 0:
        assert completed == 1 and result['usage'] is not None
    results[condition] = result
    shutil.copytree(trial, root / '.omx/observations/requests-redirects' / trial.name,
                    dirs_exist_ok=True)
(here / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
(here / 'post-run.json').write_text(json.dumps({
    'source_manifest_equal': True, 'runtime_manifest_equal': True,
    'frozen_input_hashes_equal': True, 'archive_postflight': gate,
    'terminal_observations': terminal, 'semantic_review_pending': True,
}, indent=2) + '\n')
print(json.dumps({condition: {key: result[key] for key in
    ('elapsed_seconds', 'return_code', 'timed_out', 'usage', 'quality')}
    for condition, result in results.items()}, indent=2))
