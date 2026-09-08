"""Retain the complete terminal cohort; never launch models or change its grading.

Run only after the owner confirms all three runner processes are terminal:
  .venv/bin/python -B evals/overload-token-cohort/retain.py --terminal-confirmed

The default destination is a NEW retained/ directory next to this script. All
twelve results, their raw-event links, and frozen source/runtime/archive inputs
are validated before any output is created. Failed trials are retained too.
An absent answer from a failed/empty-answer trial is recorded, never fabricated.

This is evidence retention, not a portable trial replayer. Original absolute
paths and process metadata are preserved. The frozen collector still expects
its original observation paths/interpreter; this script neither rewrites those
paths nor re-runs the model. Full source ZIPs and protocol inputs remain in the
surrounding pinned repository, rather than being duplicated in retained/.
The three byte-identical frozen runtime inventories are retained once under
runtime/. Each observation records its original runtime path and references
that shared copy; this storage deduplication does not make replay portable.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys


# The frozen observer dynamically imports its archive verifier during preflight.
# Keep those imports read-only even when the caller omits the recommended -B.
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FROZEN_COMMIT = 'c4ee65c25d40c8085ee659df1da67df651c66b74'
INPUT_MANIFEST_SHA256 = 'f6394e9832690454024cf21728f10cba5933623f12ae3858f52dfb842f49914c'
INPUT_COUNT = 108
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_CAPTURE_BYTES = 512 * 1024 * 1024
MANDATORY_ARTIFACTS = {'events.jsonl', 'invocation.json', 'process.json',
                       'prompt.txt', 'result.json', 'stderr.log'}


class RetentionError(ValueError):
    pass


def require(value, message):
    if not value:
        raise RetentionError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def relative_name(name):
    path = PurePosixPath(name)
    require(isinstance(name, str) and name and not path.is_absolute()
            and path.as_posix() == name and '..' not in path.parts and '\\' not in name,
            'Unsafe retained or manifest path: ' + repr(name))
    return name


def read_stable(path, root):
    """Read one bounded regular file without following an out-of-scope link."""
    path, root = Path(path), Path(root).resolve()
    require(not path.is_symlink() and path.resolve().is_relative_to(root),
            'Symlink or escaped evidence file: ' + str(path))
    before = path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_FILE_BYTES,
            'Non-regular or oversized evidence file: ' + str(path))
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(MAX_FILE_BYTES + 1)
        after = os.fstat(stream.fileno())
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size,
                              value.st_mtime_ns, value.st_ctime_ns)
    require(len(raw) <= MAX_FILE_BYTES and identity(before) == identity(opened)
            == identity(after) == identity(path.stat()) and len(raw) == after.st_size,
            'Evidence changed while reading: ' + str(path))
    return raw


def module(name, path):
    # Importing the already hash-verified graders must not create preflight files.
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        result = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(result)
        return result
    finally:
        sys.dont_write_bytecode = previous


def frozen_modules():
    """Verify pinned code before importing it, then use its existing verifier."""
    raw = read_stable(HERE / 'input-hashes.json', ROOT)
    require(sha(raw) == INPUT_MANIFEST_SHA256, 'Different frozen cohort input manifest')
    hashes = json.loads(raw)
    require(isinstance(hashes, dict) and len(hashes) == INPUT_COUNT,
            'Unexpected frozen input inventory')
    for name, expected in hashes.items():
        relative_name(name)
        require(sha(read_stable(ROOT / name, ROOT)) == expected,
                'Frozen input changed: ' + name)
    collector = module('retained_cohort_collector', HERE / 'collect.py')
    observer = module('retained_saved_observer', HERE.parent / 'exploration/observe_saved_callers.py')
    require(collector.frozen_inputs() == hashes, 'Collector disagrees with pinned frozen inputs')
    return collector, observer


def compressed_events(raw):
    buffer = io.BytesIO()
    with gzip.GzipFile(filename='', mode='wb', fileobj=buffer, mtime=0, compresslevel=9) as stream:
        stream.write(raw)
    compressed = buffer.getvalue()
    require(gzip.decompress(compressed) == raw, 'Gzip did not preserve exact event bytes')
    return compressed


def shared_runtime_inventory(freezes, languages):
    """Reject unequal frozen inventories before capturing any trial payloads."""
    inventory = None
    for language in languages:
        current = freezes[language]['engine']['files']
        require(isinstance(current, dict) and current, 'Empty or invalid frozen runtime inventory')
        for name, digest in current.items():
            relative_name(name)
            require(isinstance(digest, str) and len(digest) == 64
                    and all(character in '0123456789abcdef' for character in digest),
                    'Invalid frozen runtime digest: ' + name)
        if inventory is None:
            inventory = dict(current)
        require(current == inventory, 'Frozen runtime inventories differ: ' + language)
    require(inventory is not None, 'No frozen runtime inventories')
    return inventory


def validate_trial(raw, case_id, condition, repeat, observer, archive_gate):
    """Validate capture consistency, not semantic quality or token acceptance."""
    require(MANDATORY_ARTIFACTS <= raw.keys(), 'Terminal trial artifacts are missing')
    result = json.loads(raw['result.json'])
    require(isinstance(result, dict) and
            (result.get('case'), result.get('condition'), result.get('repeat')) ==
            (case_id, condition, repeat), 'Trial identity differs from fixed cohort')
    require(type(result.get('return_code')) is int and type(result.get('timed_out')) is bool,
            'Result lacks a terminal process outcome')
    require(sha(raw['events.jsonl']) == result.get('events_sha256'),
            'Raw events do not match result events_sha256')
    events = [json.loads(line) for line in raw['events.jsonl'].splitlines() if line.strip()]
    require(all(isinstance(event, dict) for event in events), 'Malformed event records')
    parsed = observer.parse_events(events)
    require(all(result.get(key) == value for key, value in parsed.items()),
            'Result metrics differ from the frozen event parser')
    require(result.get('source_unchanged') is True and result.get('evidence_mode') == 'saved_archive'
            and result.get('archive_preflight') == archive_gate == result.get('archive_postflight'),
            'Result frozen source/archive receipts disagree')
    invocation = json.loads(raw['invocation.json'])
    require(isinstance(invocation, dict) and
            len(raw['prompt.txt']) == invocation.get('prompt_bytes') == result.get('prompt_bytes'),
            'Prompt bytes disagree with invocation/result')
    for field in ('model_requested', 'effort_requested'):
        require(invocation.get(field) == result.get(field), 'Invocation/result setting mismatch: ' + field)
    require(invocation.get('harness_sha256') == sha(read_stable(
        HERE.parent / 'exploration/observe_saved_callers.py', ROOT))
        and invocation.get('answer_schema_sha256') == sha(read_stable(
            HERE.parent / 'exploration/answer.schema.json', ROOT)), 'Invocation frozen code hashes disagree')
    process = json.loads(raw['process.json'])
    require(isinstance(process, dict) and type(process.get('pid')) is int and process['pid'] > 0,
            'Invalid terminal process identity')
    started = datetime.fromisoformat(process['started_at'])
    require(started.tzinfo is not None, 'Process timestamp lacks timezone')
    answer_valid = False
    if 'answer.json' in raw:
        try:
            answer = json.loads(raw['answer.json'])
            answer_valid = True
        except (ValueError, UnicodeError):
            answer = {}  # The frozen harness records {} on answer decoding failure.
        require(answer == result.get('answer'), 'Answer bytes disagree with recorded result')
    else:
        require(result.get('answer') == {}, 'Recorded answer exists but its original artifact is missing')
    return {'result_sha256': sha(raw['result.json']), 'events_sha256': sha(raw['events.jsonl']),
            'condition': condition, 'repeat': repeat, 'return_code': result['return_code'],
            'timed_out': result['timed_out'], 'turn_failed': parsed['turn_failed'],
            'completed_turns': sum(event.get('type') == 'turn.completed' for event in events),
            'answer_present': 'answer.json' in raw, 'answer_json_valid': answer_valid,
            'started_at': started.isoformat(),
            'note': 'Capture integrity only; failed/pending quality and token gates are not filtered out.'}


def capture_plan():
    collector, observer = frozen_modules()
    payloads, entries, origins, observations = {}, {}, {}, {}
    capture_bytes = 0

    def capture(path, root):
        nonlocal capture_bytes
        raw = read_stable(path, root)
        canonical = str(Path(path).resolve())
        digest = sha(raw)
        require(canonical not in origins or origins[canonical] == digest,
                'Evidence changed across reads: ' + canonical)
        if canonical not in origins:
            capture_bytes += len(raw)
            require(capture_bytes <= MAX_CAPTURE_BYTES, 'Evidence exceeds bounded capture memory limit')
        origins[canonical] = digest
        return raw

    def add(name, raw, source, **extra):
        relative_name(name)
        require(name not in payloads and name != 'RETENTION.json', 'Duplicate retained artifact: ' + name)
        payloads[name] = raw
        entries[name] = {'bytes': len(raw), 'sha256': sha(raw), 'original_path': str(source), **extra}

    # Every language and all twelve result files are checked before capture/publication.
    cases = {}
    freezes = {language: collector.verify_observation(language, observer)
               for language in collector.LANGUAGES}
    runtime_files = shared_runtime_inventory(freezes, collector.LANGUAGES)
    runtime_inventory_sha256 = sha(json.dumps(runtime_files, sort_keys=True,
                                              separators=(',', ':')).encode('utf-8'))
    for language in collector.LANGUAGES:
        output = collector.OBSERVATIONS[language]
        catalog = json.loads(capture(HERE / language / 'cases.json', ROOT))
        require(len(catalog['cases']) == 1, 'Expected exactly one case per language')
        case = cases[language] = catalog['cases'][0]
        expected = {f"{case['id']}-{condition}-{repeat}"
                    for condition in collector.CONDITIONS for repeat in (1, 2)}
        actual = {path.name for path in (output / 'trials').iterdir()}
        require(actual == expected, 'Missing or unexpected trial directories for ' + language)
        for name in expected:
            require((output / 'trials' / name / 'result.json').is_file(),
                    'All twelve terminal results are required; missing ' + name)

    # Validate every actual runtime copy, but retain each identical file once.
    # Record all original paths rather than implying the trials used this layout.
    for name, expected_hash in sorted(runtime_files.items()):
        shared_raw = None
        original_paths = {}
        for language in collector.LANGUAGES:
            output = collector.OBSERVATIONS[language]
            path = output / 'runtime' / name
            raw = capture(path, output)
            require(sha(raw) == expected_hash, 'Frozen runtime bytes changed: ' + language + '/' + name)
            require(shared_raw is None or raw == shared_raw, 'Actual runtime bytes differ: ' + name)
            shared_raw = raw
            original_paths[language] = str(path)
        add('runtime/' + name, shared_raw, next(iter(original_paths.values())),
            original_paths=original_paths)

    for language in collector.LANGUAGES:
        output, frozen, case = collector.OBSERVATIONS[language], freezes[language], cases[language]
        archive_gate = observer.archive_gate(output, frozen['engine'])
        details = {'original_observation': str(output), 'case': case['id'], 'trials': {},
                   'runtime': {'original_directory': str(output / 'runtime'),
                               'retained_directory': 'runtime',
                               'inventory_sha256': runtime_inventory_sha256},
                   'source_zip': {'repository_path': f'evals/overload-token-cohort/{language}/source.zip',
                                  'sha256': frozen['manifest']['fixture_sha256']}}
        for name in ('manifest.json', 'engine.json', 'cases.json', 'runner.json', 'graph.jsonl.xz'):
            raw = capture(output / name, output)
            if name == 'graph.jsonl.xz':
                require(sha(raw) == frozen['engine']['archive']['archive_sha256'], 'Archive bytes changed')
            add(f'{language}/{name}', raw, output / name)
        for condition in collector.CONDITIONS:
            for repeat in (1, 2):
                name = f"{case['id']}-{condition}-{repeat}"
                trial = output / 'trials' / name
                require(not trial.is_symlink() and trial.is_dir(), 'Invalid trial directory')
                raw = {}
                for path in sorted(trial.rglob('*')):
                    require(not path.is_symlink(), 'Symlink in trial artifacts: ' + str(path))
                    if path.is_dir():
                        continue
                    relative = path.relative_to(trial).as_posix()
                    raw[relative_name(relative)] = capture(path, output)
                details['trials'][name] = validate_trial(raw, case['id'], condition, repeat, observer, archive_gate)
                for artifact, content in raw.items():
                    target, extra = artifact, {}
                    if artifact == 'events.jsonl':
                        target, extra = artifact + '.gz', {'encoding': 'gzip', 'uncompressed_bytes': len(content),
                                                        'uncompressed_sha256': sha(content)}
                        content = compressed_events(content)
                    add(f'{language}/trials/{name}/{target}', content, trial / artifact, **extra)
        observations[language] = details

    # No reads above wrote output. Recheck all captured inputs and authoritative gates
    # before permitting publication, rather than hashing a moving trial directory.
    for path, expected in origins.items():
        require(sha(read_stable(Path(path), Path(path).parent)) == expected,
                'Evidence changed before publication: ' + path)
    require(collector.frozen_inputs(), 'Frozen input verification failed')
    for language in collector.LANGUAGES:
        collector.verify_observation(language, observer)
    manifest = {'schema': 'columbus.overload-token-retention/v1',
                'created_at': datetime.now(timezone.utc).isoformat(), 'frozen_commit': FROZEN_COMMIT,
                'input_manifest_sha256': INPUT_MANIFEST_SHA256, 'frozen_input_count': INPUT_COUNT,
                'postprocessor_sha256': sha(read_stable(Path(__file__), HERE)), 'python': sys.version,
                'trial_count': sum(len(value['trials']) for value in observations.values()),
                'shared_runtime': {'directory': 'runtime', 'files': runtime_files,
                                   'inventory_sha256': runtime_inventory_sha256},
                'observations': observations, 'files': entries,
                'limitations': [
                    'Post-execution retention only, not model execution, grading, or cohort acceptance.',
                    'Original absolute paths are unchanged; the frozen collector is not redirected to these copies.',
                    'Full source ZIPs and protocol files remain in the surrounding pinned repository.',
                    'Runtime source/skill files are retained; interpreter, installed dependencies and bytecode caches are not.',
                    'Identical runtime/skill inventories are stored once in runtime/; every original runtime path is preserved and no replay path is rewritten.',
                    'Gzip decompression reproduces original event bytes; compressed-stream hashes are recorded separately.',
                    'Failed terminal trials and absent/invalid answer artifacts are reported without replacement.',
                    'A filesystem failure can leave an incomplete destination; no overwrite, automatic cleanup or retry is performed.'
                ]}
    require(manifest['trial_count'] == 12, 'Retention requires all twelve trials')
    return payloads, manifest


def retain(output, *, terminal_confirmed=False):
    require(terminal_confirmed is True, 'Owner confirmation that all runners are terminal is required')
    output = Path(output).expanduser().absolute()
    require(not os.path.lexists(output), 'Refusing to overwrite existing retention destination: ' + str(output))
    require(output.parent.is_dir(), 'Retention destination parent must already exist')
    payloads, manifest = capture_plan()
    require(not any(output.resolve().is_relative_to(Path(value['original_observation']).resolve())
                    for value in manifest['observations'].values()),
            'Retention output must not modify an original observation')
    # Exclusive directory creation is the first write, after the complete preflight.
    output.mkdir(exist_ok=False)
    try:
        for name, raw in sorted(payloads.items()):
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(raw)
            require(sha(read_stable(target, output)) == manifest['files'][name]['sha256'],
                    'Retained output verification failed: ' + name)
        raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        with (output / 'RETENTION.json').open('xb') as stream:
            stream.write(raw)
        require(read_stable(output / 'RETENTION.json', output) == raw,
                'Retention manifest output verification failed')
    except BaseException:
        print('Retention did not complete. Existing partial output was preserved at ' + str(output)
              + '; inspect it, do not overwrite or infer acceptance.', file=sys.stderr)
        raise
    return {'output': str(output), 'trial_count': manifest['trial_count'], 'files': len(payloads),
            'retention_manifest_sha256': sha(raw), 'grading_unchanged': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'retained', help='Fresh destination; never overwritten')
    parser.add_argument('--terminal-confirmed', action='store_true', help='Owner has confirmed all runners are terminal')
    args = parser.parse_args()
    try:
        result = retain(args.output, terminal_confirmed=args.terminal_confirmed)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, 'Retention refused or incomplete: ' + str(error) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
