"""Append-only post-run evidence capture; no models, process polling or grading.

Capture, only after the owner has checked every original live runner handle:
  python -B evals/source-call-sites-cohort/retain.py --terminal-confirmed --output NEW_DIRECTORY
Use --frozen-repo PATH if the exact pinned checkout is located elsewhere.
Optional --allow-incomplete REASON preserves a failed/stopped partial cohort,
including malformed raw events and every observed extra trial, without claiming
that absent process metadata proves termination. Default capture requires all
18 process/terminal/result records and all three completed runner records.

--semantic-dir ROOT optionally captures ROOT/LANGUAGE/semantic/*.json; missing
reviews are recorded, not filled in. --report PATH includes an explicitly chosen
collector JSON report. Neither option changes grading or requires a passing gate.
--verify DIRECTORY verifies retained files and decompressed events read-only,
without the original /tmp observations, installed dependencies or a model call.

The exact frozen input manifest is copied. Its 449 already committed source ZIP,
graph, runtime, skill, rubric and protocol files are referenced by commit/path/
SHA, not duplicated. This is not a portable model or collector replayer: original
absolute paths are unchanged, no interpreter/dependencies are bundled, and the
manifest digest must be externally anchored for authenticity. Source/runtime
integrity is checked before and after capture; failures preserve partial output.
No output is allowed anywhere inside the frozen checkout. This post-result tool
is not a frozen protocol, control, model dependency, grader or collector.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys


sys.dont_write_bytecode = True
ROOT = Path('/tmp/columbus-call-sites-cohort.Q0BUvh')
HERE = ROOT / 'evals/source-call-sites-cohort'
FROZEN_COMMIT = '28bfa454044f88e2cc0096f509ae316a4676f209'
INPUT_SHA256 = '69f196d7db2fac0248805878f294966774346028dee725f439707702d60c2fa6'
INPUT_COUNT = 449
FROZEN_TREE = 'f928f15d855852b25acd996b899b159e958abf46'
LANGUAGES = ('java', 'kotlin', 'javascript')
ARMS = ('baseline', 'control', 'candidate')
SCHEDULES = {
    'java': [('baseline', 1), ('control', 1), ('candidate', 1),
             ('candidate', 2), ('control', 2), ('baseline', 2)],
    'kotlin': [('control', 1), ('candidate', 1), ('baseline', 1),
               ('baseline', 2), ('candidate', 2), ('control', 2)],
    'javascript': [('candidate', 1), ('baseline', 1), ('control', 1),
                   ('control', 2), ('baseline', 2), ('candidate', 2)],
}
REQUIRED = {'prompt.txt', 'invocation.json', 'process.json', 'terminal.json',
            'events.jsonl', 'stderr.log', 'result.json'}
MAX_FILE = 128 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
SCHEMA = 'columbus.source-call-sites-cohort-retention/v1'


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def inventory_hash(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def relative(name):
    require(isinstance(name, str) and name and not any(c in name for c in ('\\', ':', '\0')),
            'Unsafe relative artifact path')
    path = PurePosixPath(name)
    require(path.parts and not path.is_absolute() and path.as_posix() == name and '..' not in path.parts,
            'Escaped artifact path')
    return name


def unchanged_stats(before, opened, after, finished, *, windows):
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
    # Windows path stat can expose birthtime as ctime while fstat exposes
    # ChangeTime. Compare each API's ctime before/after, never those two meanings.
    return (identity(before) == identity(opened) == identity(after) == identity(finished)
            and before.st_ctime_ns == finished.st_ctime_ns
            and opened.st_ctime_ns == after.st_ctime_ns
            and (windows or before.st_ctime_ns == opened.st_ctime_ns))


def stable(path, root):
    path, root = Path(path).absolute(), Path(root).absolute()
    require(not root.is_symlink(), 'Symlink evidence root')
    require(path.is_relative_to(root) and path.resolve().is_relative_to(root.resolve()), 'Evidence escapes its root')
    for parent in (path, *path.parents):
        if parent == root:
            break
        require(not parent.is_symlink(), 'Symlink in evidence path: ' + str(path))
    before = path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_FILE, 'Non-regular or oversized evidence')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(MAX_FILE + 1)
        after = os.fstat(stream.fileno())
    require(not path.is_symlink() and len(raw) <= MAX_FILE and len(raw) == after.st_size
            and unchanged_stats(before, opened, after, path.stat(), windows=sys.platform == 'win32'),
            'Evidence changed during read: ' + str(path))
    return raw


def members(directory):
    require(not directory.is_symlink(), 'Symlink evidence directory')
    if not directory.exists():
        return []
    require(directory.is_dir(), 'Evidence directory is not a directory')
    result = []
    for path in directory.rglob('*'):
        require(not path.is_symlink(), 'Symlink in evidence inventory')
        require(path.is_dir() or path.is_file(), 'Non-regular evidence entry')
        if path.is_file():
            result.append(path.relative_to(directory).as_posix())
    return sorted(result)


def git_inputs(raw, hashes, sizes):
    """Read pinned Git objects, never a checkout's executable code or hooks."""
    tree = subprocess.check_output(['git', 'rev-parse', FROZEN_COMMIT + '^{tree}'], cwd=ROOT).decode().strip()
    require(tree == FROZEN_TREE, 'Frozen commit tree differs')
    path = 'evals/source-call-sites-cohort/input-hashes.json'
    require(subprocess.check_output(['git', 'show', FROZEN_COMMIT + ':' + path], cwd=ROOT) == raw,
            'Frozen input manifest differs from pinned Git blob')
    for path, expected in hashes.items():
        data = subprocess.check_output(['git', 'show', FROZEN_COMMIT + ':' + relative(path)], cwd=ROOT)
        require(digest(data) == expected and len(data) == sizes[path], 'Frozen Git blob differs: ' + path)


def frozen():
    raw = stable(HERE / 'input-hashes.json', ROOT)
    require(digest(raw) == INPUT_SHA256, 'Not the launched frozen input manifest')
    hashes = json.loads(raw)
    require(isinstance(hashes, dict) and len(hashes) == INPUT_COUNT, 'Frozen input count differs')
    sizes = {}
    for name, expected in hashes.items():
        data = stable(ROOT / relative(name), ROOT)
        require(digest(data) == expected, 'Frozen input changed: ' + name)
        sizes[name] = len(data)
    git_inputs(raw, hashes, sizes)
    # Import only after checking all immutable code, including transitive modules.
    key = '_source_call_retention_common_' + digest(str((HERE / 'common.py').resolve()).encode())[:16]
    spec = importlib.util.spec_from_file_location(key, HERE / 'common.py')
    common = importlib.util.module_from_spec(spec)
    sys.modules[key] = common
    spec.loader.exec_module(common)
    require(common.frozen_inputs() == hashes, 'Frozen common verifier disagrees')
    require(tuple(common.LANGUAGES) == LANGUAGES and tuple(common.CONDITIONS) == ARMS,
            'Frozen task or arm inventory differs')
    return common, raw, hashes, sizes


def zip_events(raw):
    stream = io.BytesIO()
    with gzip.GzipFile(filename='', fileobj=stream, mode='wb', mtime=0, compresslevel=9) as zipped:
        zipped.write(raw)
    result = stream.getvalue()
    require(gzip.decompress(result) == raw, 'Event compression changed bytes')
    return result


def date(value):
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None, 'Process timestamp lacks timezone')
    return result


def artifact_hash(raw, name):
    # Collector uses '' for an absent answer, not SHA256(b''). A present empty
    # file still has a real hash; do not collapse these different observations.
    return digest(raw[name]) if name in raw else ''


def review_binding(review, raw, rubric):
    require(isinstance(review, dict)
            and review.get('answer_sha256') == artifact_hash(raw, 'answer.json')
            and review.get('rubric_sha256') == rubric
            and isinstance(review.get('execution_review'), dict)
            and review['execution_review'].get('events_sha256') == artifact_hash(raw, 'events.jsonl'),
            'Semantic review binding differs from captured answer/rubric/events')


def trial_check(raw, case, arm, repeat, output, common, preflight):
    """Return integrity errors without filtering out failed model outcomes."""
    missing = sorted(REQUIRED - set(raw))
    issues = ['Missing artifact: ' + name for name in missing]
    issues.extend('Unexpected artifact: ' + name for name in sorted(set(raw) - REQUIRED - {'answer.json'}))
    details = {'missing_artifacts': missing, 'answer_present': 'answer.json' in raw,
               'process_present': 'process.json' in raw, 'terminal_present': 'terminal.json' in raw,
               'result_present': 'result.json' in raw, 'issues': issues}

    def check(operation):
        try:
            operation()
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError, OverflowError) as error:
            issues.append(str(error))

    def process():
        started = json.loads(raw['process.json'])
        require(type(started.get('pid')) is int and started['pid'] > 0, 'Invalid process PID')
        details['started_at'] = date(started['started_at']).isoformat()
        if 'terminal.json' in raw:
            terminal = json.loads(raw['terminal.json'])
            require(type(terminal.get('return_code')) is int and type(terminal.get('timed_out')) is bool, 'Invalid terminal status')
            elapsed = terminal['elapsed_seconds']
            require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0, 'Invalid elapsed time')
            require(date(terminal['finished_at']) >= date(details['started_at']), 'Finish precedes start')
            details['terminal'] = terminal

    def invocation():
        value = json.loads(raw['invocation.json'])
        trial = output / 'trials' / f"{case['id']}-{arm}-{repeat}"
        expected = {'argv': common.argv(output, trial), 'model_requested': 'gpt-5.6-sol',
                    'effort_requested': 'xhigh', 'timeout_seconds': 1200, 'prompt_bytes': len(raw['prompt.txt']),
                    'harness_sha256': common.sha(HERE / 'run.py'), 'common_sha256': common.sha(HERE / 'common.py'),
                    'input_hashes_sha256': INPUT_SHA256}
        require(all(value.get(key) == wanted for key, wanted in expected.items()), 'Invocation differs from frozen contract')
        require(raw['prompt.txt'] == common.prompt(case, arm, output).encode(), 'Prompt differs from frozen contract')

    def result():
        value = json.loads(raw['result.json'])
        require((value.get('case'), value.get('condition'), value.get('repeat')) == (case['id'], arm, repeat), 'Result identity differs')
        require(value.get('events_sha256') == digest(raw['events.jsonl']), 'Raw event/result hash mismatch')
        require(all(value.get(key) == item for key, item in json.loads(raw['terminal.json']).items()), 'Terminal/result mismatch')
        require(value.get('preflight') == preflight == value.get('postflight'), 'Source/runtime pre/postflight differs')
        # A recorded model parsing/serialization failure is an observed failure,
        # not a reason to discard the raw events or invent replacement metrics.
        model_error = value.get('evaluation_error')
        events, observed = None, None
        try:
            events = [json.loads(line) for line in raw['events.jsonl'].splitlines() if line.strip()]
            require(all(isinstance(event, dict) for event in events), 'Malformed event object')
            observed = common.OBSERVE.parse_events(events)
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError):
            require(isinstance(model_error, dict), 'Unrecorded event parsing failure')
        if model_error is None:
            require(observed is not None and all(value.get(key) == item for key, item in observed.items()),
                    'Event/result metrics differ')
        else:
            require(isinstance(model_error, dict), 'Invalid recorded evaluation error')
            details['evaluation_error'] = model_error
        try:
            answer = json.loads(raw['answer.json'])
        except (KeyError, ValueError, UnicodeError, RecursionError, OverflowError):
            answer = {}
        require(value.get('answer') == answer or (model_error is not None and value.get('answer') == {}),
                'Answer/result mismatch')
        details['return_code'] = value['return_code']
        details['timed_out'] = value['timed_out']
        if observed is not None and model_error is None:
            details['turn_failed'] = observed['turn_failed']
        if events is not None and all(isinstance(event, dict) for event in events):
            details['completed_turns'] = sum(event.get('type') == 'turn.completed' for event in events)

    if 'process.json' in raw:
        check(process)
    if {'invocation.json', 'prompt.txt'} <= set(raw):
        check(invocation)
    if 'result.json' in raw:
        check(result)
    return details


def plan(allow_incomplete=None, semantic_dir=None, report=None):
    common, input_raw, hashes, sizes = frozen()
    payloads, entries, origins, roots, directory_inventories = {}, {}, {}, {}, {}
    total = 0

    def capture(path, root):
        nonlocal total
        path = Path(path).absolute()
        raw = stable(path, root)
        key = str(path)
        info = {'bytes': len(raw), 'sha256': digest(raw)}
        require(key not in origins or origins[key] == info, 'Evidence changed across reads')
        if key not in origins:
            total += len(raw)
            require(total <= MAX_TOTAL, 'Capture exceeds bounded memory budget')
        origins[key], roots[key] = info, str(root)
        return raw

    def add(name, raw, source, compression=False):
        relative(name)
        require(name not in payloads and name != 'RETENTION.json', 'Duplicate retained artifact')
        info = {'original_path': str(Path(source).absolute()), 'original_bytes': len(raw), 'original_sha256': digest(raw)}
        if compression:
            raw = zip_events(raw)
            info['encoding'] = 'gzip'
        payloads[name] = raw
        entries[name] = {**info, 'bytes': len(raw), 'sha256': digest(raw)}

    def directory(path):
        current = members(path)
        directories = sorted(item.relative_to(path).as_posix() for item in path.rglob('*') if item.is_dir())
        directory_inventories[str(path)] = {'files': current, 'directories': directories}
        return current

    add('input-hashes.json', capture(HERE / 'input-hashes.json', ROOT), HERE / 'input-hashes.json')
    add('retention-tool.py', capture(Path(__file__), Path(__file__).parent), Path(__file__))
    observations, issues, trials, review_count, missing_reviews = {}, [], {}, 0, []
    group_entries = {}
    for language in LANGUAGES:
        case = common.read(HERE / language / 'cases.json')['cases'][0]
        preflight = {arm: common.verify_observation(language, arm) for arm in ARMS}
        frozen_arm = common.read(HERE / language / 'freeze.json')
        group = common.observation(language, 'baseline').parent
        group_entries[str(group)] = sorted(path.name for path in group.iterdir())
        extras = set(group_entries[str(group)]) - set(ARMS) - {'runner.json', 'runner-terminal.json'}
        for name in sorted(extras):
            issues.append(f'{language}: unexpected group entry {name}')
            path = group / name
            for relative_name in directory(path) if path.is_dir() else ['']:
                original = path / relative_name if relative_name else path
                suffix = name + '/' + relative_name if relative_name else name
                add(f'{language}/unexpected-group/{suffix}', capture(original, group), original)
        group_raw = {}
        for name in ('runner.json', 'runner-terminal.json'):
            path = group / name
            if path.exists():
                group_raw[name] = capture(path, group)
                add(f'{language}/{name}', group_raw[name], path)
            else:
                issues.append(f'{language}: missing {name}; no process status inferred')
        require(common.schedule(language) == SCHEDULES[language], 'Frozen balanced schedule differs')
        observations[language] = {'original_group': str(group), 'preflight': preflight, 'arms': {},
                                  'schedule': common.schedule(language)}
        ordered = []
        for arm in ARMS:
            output = common.observation(language, arm)
            engine = frozen_arm[arm]['engine']
            observations[language]['arms'][arm] = {'original_observation': str(output),
                'frozen_manifest_reference': f'evals/source-call-sites-cohort/{language}/freeze.json',
                'source_inventory_sha256': inventory_hash(frozen_arm[arm]['manifest']['source_manifest']),
                'runtime_inventory_sha256': inventory_hash(engine['files']),
                'archive_sha256': engine['archive']['archive_sha256']}
            for name in ('manifest.json', 'engine.json', 'cases.json'):
                path = output / name
                add(f'{language}/{arm}/{name}', capture(path, output), path)
            base = output / 'trials'
            files = directory(base)
            expected_names = {f"{case['id']}-{arm}-{repeat}" for repeat in (1, 2)}
            actual_names = {item.name for item in base.iterdir()} if base.exists() else set()
            extras = sorted(actual_names - expected_names)
            if extras:
                issues.append(f'{language}/{arm}: unexpected trial entries {extras}')
            raw_trials = {}
            for name in files:
                path = base / name
                raw = capture(path, base)
                top, _, artifact = name.partition('/')
                canonical = top in expected_names and artifact in REQUIRED | {'answer.json'}
                compression = canonical and artifact == 'events.jsonl'
                # Unknown paths have a separate raw namespace. In particular an
                # extra events.jsonl.gz cannot overwrite the compressed original.
                namespace = 'trials' if canonical else 'unexpected'
                target = f'{language}/{arm}/{namespace}/{name}' + ('.gz' if compression else '')
                add(target, raw, path, compression=compression)
                raw_trials.setdefault(top, {})[artifact] = raw
            for repeat in (1, 2):
                name = f"{case['id']}-{arm}-{repeat}"
                row = trial_check(raw_trials.get(name, {}), case, arm, repeat, output, common, preflight)
                row['issues'].extend('Unexpected artifact directory: ' + item for item in
                    directory_inventories[str(base)]['directories'] if item.startswith(name + '/'))
                trials[f'{language}/{arm}/{repeat}'] = row
                issues.extend(f'{language}/{arm}/{repeat}: {item}' for item in row['issues'])
            if semantic_dir is not None:
                folder = Path(semantic_dir).absolute() / language / 'semantic'
                review_files = directory(folder)
                expected = {f"{case['id']}-{condition}-{repeat}.json" for condition in ARMS for repeat in (1, 2)}
                require(set(review_files) <= expected, 'Unexpected semantic review file')
                missing_reviews.extend(f'{language}/semantic/{name}.json' for name in sorted(expected_names)
                                       if name + '.json' not in review_files)
                for name in review_files:
                    if name[:-5] not in expected_names:
                        continue
                    source = folder / name
                    raw = capture(source, folder)
                    review = json.loads(raw)
                    original = raw_trials.get(name[:-5], {})
                    review_binding(review, original, common.sha(HERE / language / 'SOURCE-REVIEW.md'))
                    add(f'{language}/semantic/{name}', raw, source)
                    review_count += 1
        for arm, repeat in common.schedule(language):
            row = trials[f'{language}/{arm}/{repeat}']
            if row.get('started_at') and row.get('terminal'):
                ordered.append((date(row['started_at']), date(row['terminal']['finished_at'])))
        try:
            runner, ended = (json.loads(group_raw[name]) for name in ('runner.json', 'runner-terminal.json'))
            require(isinstance(runner, dict) and isinstance(ended, dict), 'Malformed runner record shape')
            require(type(runner.get('pid')) is int and runner['pid'] > 0, 'Invalid runner PID')
            require(runner.get('schedule') == [list(row) for row in common.schedule(language)]
                    and runner.get('input_hashes_sha256') == INPUT_SHA256, 'Runner schedule/input hash differs')
            require(len(ordered) == 6 and date(runner['started_at']) <= ordered[0][0]
                    and all(left[1] <= right[0] and left[0] < right[0] for left, right in zip(ordered, ordered[1:])),
                    'Incomplete, overlapping or out-of-order original processes')
            require(ended.get('status') == 'all scheduled executions terminated'
                    and date(ended['finished_at']) >= ordered[-1][1], 'Invalid or premature runner completion')
        except (ValueError, KeyError, TypeError, AttributeError, RecursionError, OverflowError) as error:
            issues.append(language + ': ' + str(error))
    if report is not None:
        path = Path(report).absolute()
        raw = capture(path, path.parent)
        value = json.loads(raw)
        require(isinstance(value, dict) and value.get('input_hashes_sha256') == INPUT_SHA256
                and value.get('schema') == 'columbus.source-call-sites-cohort-results/v1'
                and value.get('frozen_inputs_verified') == INPUT_COUNT,
                'Selected report belongs to another/unverified cohort')
        require(isinstance(value.get('trials'), dict) and set(value['trials']) == set(trials),
                'Selected report must include all 18 scheduled slots')
        for slot, row in value.get('trials', {}).items():
            require(slot in trials, 'Selected report contains an unplanned trial')
            require(isinstance(row, dict), 'Malformed selected report trial')
            language, arm, repeat = slot.split('/')
            case_id = common.read(HERE / language / 'cases.json')['cases'][0]['id']
            trial = common.observation(language, arm) / 'trials' / f'{case_id}-{arm}-{repeat}'
            for name, checksum in row.get('artifact_sha256', {}).items():
                original = str((trial / relative(name)).absolute())
                require(original in origins and origins[original]['sha256'] == checksum,
                        'Selected report artifact binding differs from capture')
            if row.get('semantic_review_sha256') is not None:
                require(semantic_dir is not None, 'Selected report references unselected semantic reviews')
                original = str((Path(semantic_dir).absolute() / language / 'semantic'
                                / f'{case_id}-{arm}-{repeat}.json').absolute())
                require(original in origins and origins[original]['sha256'] == row['semantic_review_sha256'],
                        'Selected report semantic review binding differs from capture')
        add('collector-report.json', raw, path)
    require(not issues or (isinstance(allow_incomplete, str) and allow_incomplete.strip()),
            'Complete capture required; preserve failures with explicit --allow-incomplete REASON: ' + '; '.join(issues))

    def unchanged():
        require(frozen()[2] == hashes, 'Frozen inputs changed during retention')
        for language in LANGUAGES:
            require({arm: common.verify_observation(language, arm) for arm in ARMS}
                    == observations[language]['preflight'], 'Observation changed during retention')
        for path, names in group_entries.items():
            require(sorted(item.name for item in Path(path).iterdir()) == names,
                    'Original group entries changed during retention')
        for path, expected in directory_inventories.items():
            current = Path(path)
            require(members(current) == expected['files']
                    and sorted(item.relative_to(current).as_posix() for item in current.rglob('*') if item.is_dir())
                    == expected['directories'], 'Evidence directory inventory changed during retention')
        for path, expected in origins.items():
            raw = stable(path, roots[path])
            require({'bytes': len(raw), 'sha256': digest(raw)} == expected, 'Original evidence changed during retention: ' + path)

    unchanged()
    references = {name: {'sha256': value, 'bytes': sizes[name],
                  'url': 'https://github.com/ch4570/columbus/blob/' + FROZEN_COMMIT + '/' + name}
                  for name, value in hashes.items()}
    manifest = {'schema': SCHEMA, 'captured_at': datetime.now(timezone.utc).isoformat(),
        'frozen_commit': FROZEN_COMMIT, 'frozen_tree': FROZEN_TREE,
        'input_manifest_sha256': digest(input_raw), 'frozen_input_count': len(hashes),
        'frozen_references': references, 'capture_integrity_complete': True, 'cohort_complete': not issues,
        'allow_incomplete_reason': allow_incomplete, 'issues': issues, 'trials': trials, 'scheduled_trial_count': 18,
        'observations': observations, 'semantic_reviews_requested': semantic_dir is not None,
        'semantic_reviews_retained': review_count, 'collector_report_requested': report is not None,
        'semantic_reviews_missing': sorted(missing_reviews),
        'supplemental_evidence_complete': semantic_dir is not None and report is not None and not missing_reviews,
        'original_group_entries': group_entries,
        'original_group_entries_sha256': inventory_hash(group_entries),
        'original_files': origins, 'original_inventory_sha256': inventory_hash(origins),
        'original_directories': directory_inventories,
        'original_directories_sha256': inventory_hash(directory_inventories),
        'files': entries, 'retained_inventory_sha256': inventory_hash(entries),
        'limitations': ['Capture integrity is not model quality, cost acceptance or proof of network/process state.',
            'Owner terminal confirmation is required; no PID polling is performed and absent metadata proves nothing.',
            'All observed trial files are preserved, including extra/failed/incomplete runs when explicitly authorized.',
            'Full immutable source/runtime/protocol files remain at hash-linked commit paths; no portable replayer is supplied.',
            'Only explicitly selected semantic reviews/report are included; missing reviews are not synthesized.',
            'Cohort completeness describes scheduled terminal evidence, never quality or any acceptance verdict.',
            'Absent answer hash is the collector empty string; a present empty answer has SHA256 of zero bytes.',
            'Recorded model parsing/serialization failures remain raw failures; no grades or usage are repaired.',
            'Gzip hashes differ from original JSONL hashes; decompression reproduces exact original bytes.',
            'Unexpected trial artifacts use a separate raw namespace to avoid compressed-name collisions.',
            'Partial capture failures are preserved and rejected by --verify; no overwrite or automatic cleanup occurs.']}
    return payloads, manifest, unchanged


def verify(output):
    output = Path(output).absolute()
    require(not (output / 'INCOMPLETE.json').exists(), 'Capture failed; partial evidence is preserved')
    raw = stable(output / 'RETENTION.json', output)
    value = json.loads(raw)
    require(value.get('schema') == SCHEMA and value.get('capture_integrity_complete') is True, 'Invalid retention manifest')
    require(value.get('frozen_commit') == FROZEN_COMMIT and value.get('frozen_tree') == FROZEN_TREE
            and value.get('frozen_input_count') == INPUT_COUNT and value.get('input_manifest_sha256') == INPUT_SHA256,
            'Retention is not bound to launched cohort')
    require(isinstance(value.get('issues'), list) and type(value.get('cohort_complete')) is bool
            and value['cohort_complete'] == (not value['issues']), 'Inconsistent cohort completeness claim')
    require(not value['issues'] or (isinstance(value.get('allow_incomplete_reason'), str)
            and value['allow_incomplete_reason'].strip()), 'Incomplete cohort lacks explicit capture reason')
    files, originals = value['files'], value['original_files']
    require(value['retained_inventory_sha256'] == inventory_hash(files)
            and value['original_inventory_sha256'] == inventory_hash(originals)
            and value['original_directories_sha256'] == inventory_hash(value['original_directories'])
            and value['original_group_entries_sha256'] == inventory_hash(value['original_group_entries']),
            'Inventory hash differs')
    require(set(members(output)) == set(files) | {'RETENTION.json'}, 'Missing or extra retained file')
    expected_dirs = {str(parent) for name in files for parent in PurePosixPath(name).parents if str(parent) != '.'}
    require({path.relative_to(output).as_posix() for path in output.rglob('*') if path.is_dir()} == expected_dirs,
            'Missing or extra retained directory')
    contents, total = {}, 0
    for name, expected in files.items():
        stored = stable(output / relative(name), output)
        require(len(stored) == expected['bytes'] and digest(stored) == expected['sha256'], 'Retained file differs: ' + name)
        if expected.get('encoding') == 'gzip':
            with gzip.GzipFile(fileobj=io.BytesIO(stored)) as stream:
                original = stream.read(MAX_FILE + 1)
            require(len(original) <= MAX_FILE, 'Oversized decompressed events')
        else:
            require('encoding' not in expected, 'Unknown retained encoding')
            original = stored
        origin = originals[expected['original_path']]
        require(len(original) == expected['original_bytes'] == origin['bytes']
                and digest(original) == expected['original_sha256'] == origin['sha256'], 'Original-byte binding differs')
        total += len(original)
        require(total <= MAX_TOTAL, 'Retained payload exceeds bounded verification budget')
        contents[name] = original
    hashes = json.loads(stable(output / 'input-hashes.json', output))
    require(digest(stable(output / 'input-hashes.json', output)) == INPUT_SHA256 and len(hashes) == INPUT_COUNT,
            'Retained frozen input manifest differs')
    require({name: row['sha256'] for name, row in value['frozen_references'].items()} == hashes, 'Frozen reference map differs')
    require(all(row['url'] == 'https://github.com/ch4570/columbus/blob/' + FROZEN_COMMIT + '/' + name
                for name, row in value['frozen_references'].items()), 'Frozen reference pin/path differs')
    expected_slots = {f'{language}/{arm}/{repeat}' for language in LANGUAGES for arm in ARMS for repeat in (1, 2)}
    require(set(value['trials']) == expected_slots and value['scheduled_trial_count'] == 18, 'Scheduled trial inventory differs')
    for slot, row in value['trials'].items():
        language, arm, repeat = slot.split('/')
        catalog = json.loads(stable(output / language / arm / 'cases.json', output))
        case_id = catalog['cases'][0]['id']
        prefix = f'{language}/{arm}/trials/{case_id}-{arm}-{repeat}/'
        present = {name[len(prefix):].removesuffix('.gz') if info.get('encoding') == 'gzip' else name[len(prefix):]
                   for name, info in files.items() if name.startswith(prefix)}
        require(row['missing_artifacts'] == sorted(REQUIRED - present)
                and row['answer_present'] == ('answer.json' in present)
                and row['process_present'] == ('process.json' in present)
                and row['terminal_present'] == ('terminal.json' in present)
                and row['result_present'] == ('result.json' in present), 'Trial presence metadata differs from retained files')
        require(not value['cohort_complete'] or (not row['missing_artifacts'] and not row['issues']),
                'Incomplete trial represented as complete cohort')

        def original_json(name):
            data = stable(output / (prefix + name), output)
            parsed = json.loads(data)
            require(isinstance(parsed, dict), 'Malformed retained process/result record')
            return parsed

        if not row['issues']:
            required_summary = {'started_at', 'terminal', 'return_code', 'timed_out'}
            if 'evaluation_error' not in row:
                required_summary |= {'turn_failed', 'completed_turns'}
            require(required_summary <= set(row),
                    'Complete trial lacks derived process summary')
        if 'started_at' in row:
            require(row['started_at'] == date(original_json('process.json')['started_at']).isoformat(),
                    'Trial start summary differs from retained process')
        if 'terminal' in row:
            require(encoded(row['terminal']) == encoded(original_json('terminal.json')),
                    'Trial terminal summary differs from retained terminal')
        for field in ('return_code', 'timed_out', 'turn_failed'):
            if field in row:
                expected = original_json('result.json')[field]
                require(type(row[field]) is type(expected) and row[field] == expected,
                        'Trial result summary differs from retained result: ' + field)
        if 'evaluation_error' in row:
            require(row['evaluation_error'] == original_json('result.json')['evaluation_error'],
                    'Trial evaluation error summary differs from retained result')
        if 'completed_turns' in row:
            with gzip.GzipFile(fileobj=io.BytesIO(stable(output / (prefix + 'events.jsonl.gz'), output))) as stream:
                raw_events = stream.read(MAX_FILE + 1)
            require(len(raw_events) <= MAX_FILE, 'Oversized decompressed events')
            events = [json.loads(line) for line in raw_events.splitlines() if line.strip()]
            require(type(row['completed_turns']) is int and row['completed_turns']
                    == sum(event.get('type') == 'turn.completed' for event in events),
                    'Trial turn summary differs from retained events')
    for language in LANGUAGES:
        schedule = [list(row) for row in SCHEDULES[language]]
        require(value['observations'][language]['schedule'] == schedule, 'Retained balanced schedule differs')
        if value['cohort_complete']:
            runner_name, terminal_name = f'{language}/runner.json', f'{language}/runner-terminal.json'
            require(runner_name in contents and terminal_name in contents, 'Complete cohort lacks runner records')
            runner, terminal = json.loads(contents[runner_name]), json.loads(contents[terminal_name])
            require(isinstance(runner, dict) and isinstance(terminal, dict), 'Malformed retained runner record')
            require(type(runner.get('pid')) is int and runner['pid'] > 0
                    and runner.get('schedule') == schedule and runner.get('input_hashes_sha256') == INPUT_SHA256,
                    'Retained runner schedule/input/PID differs')
            ordered = [value['trials'][f'{language}/{arm}/{repeat}'] for arm, repeat in schedule]
            require(date(runner['started_at']) <= date(ordered[0]['started_at']) and
                    all(date(left['terminal']['finished_at']) <= date(right['started_at'])
                        and date(left['started_at']) < date(right['started_at'])
                        for left, right in zip(ordered, ordered[1:])), 'Retained runner ordering differs')
            require(terminal.get('status') == 'all scheduled executions terminated' and
                    date(terminal['finished_at']) >= date(ordered[-1]['terminal']['finished_at']),
                    'Retained runner finished prematurely')
    reviews = [name for name in files if '/semantic/' in name]
    require(type(value['semantic_reviews_retained']) is int and value['semantic_reviews_retained'] == len(reviews),
            'Semantic review inventory count differs')
    require(not value['semantic_reviews_requested'] or len(reviews) + len(value['semantic_reviews_missing']) == 18,
            'Selected semantic review presence inventory differs')
    expected_reviews = set()
    for language in LANGUAGES:
        case = json.loads(contents[f'{language}/baseline/cases.json'])['cases'][0]['id']
        expected_reviews.update(f'{language}/semantic/{case}-{arm}-{repeat}.json'
                                for arm in ARMS for repeat in (1, 2))
    require(set(reviews) <= expected_reviews and
            (not value['semantic_reviews_requested'] or
             value['semantic_reviews_missing'] == sorted(expected_reviews - set(reviews))),
            'Semantic missing-review names differ')
    require(value.get('supplemental_evidence_complete') is (value['semantic_reviews_requested']
            and value['collector_report_requested'] and not value['semantic_reviews_missing']),
            'Supplemental evidence completeness differs')
    for name in reviews:
        language, _, filename = name.split('/')
        candidates = [slot for slot in expected_slots if slot.startswith(language + '/') and
                      filename[:-5].endswith('-' + slot.split('/')[1] + '-' + slot.split('/')[2])]
        require(len(candidates) == 1, 'Unexpected semantic review name')
        _, arm, repeat = candidates[0].split('/')
        prefix = f'{language}/{arm}/trials/{filename[:-5]}/'
        originals = {key[len(prefix):].removesuffix('.gz') if files[key].get('encoding') == 'gzip'
                     else key[len(prefix):]: raw for key, raw in contents.items() if key.startswith(prefix)}
        rubric_path = f'evals/source-call-sites-cohort/{language}/SOURCE-REVIEW.md'
        review_binding(json.loads(contents[name]), originals, hashes[rubric_path])
    require(value['collector_report_requested'] is ('collector-report.json' in contents),
            'Collector report presence differs')
    if value['collector_report_requested']:
        report = json.loads(contents['collector-report.json'])
        require(report.get('schema') == 'columbus.source-call-sites-cohort-results/v1'
                and report.get('input_hashes_sha256') == INPUT_SHA256
                and report.get('frozen_inputs_verified') == INPUT_COUNT
                and set(report.get('trials', {})) == expected_slots, 'Retained collector report cohort differs')
        for slot, row in report['trials'].items():
            language, arm, repeat = slot.split('/')
            catalog = json.loads(contents[f'{language}/{arm}/cases.json'])
            name = f"{catalog['cases'][0]['id']}-{arm}-{repeat}"
            for artifact, checksum in row.get('artifact_sha256', {}).items():
                artifact = relative(artifact)
                canonical = artifact in REQUIRED | {'answer.json'}
                namespace = 'trials' if canonical else 'unexpected'
                stored = f'{language}/{arm}/{namespace}/{name}/{artifact}'
                if canonical and artifact == 'events.jsonl':
                    stored += '.gz'
                # Never reinterpret an original POSIX/Windows absolute path on
                # the verifier's different host; use portable retained keys.
                require(files.get(stored, {}).get('original_sha256') == checksum,
                        'Retained collector report artifact binding differs')
            if row.get('semantic_review_sha256') is not None:
                selected = f'{language}/semantic/{name}.json'
                require(selected in contents and digest(contents[selected]) == row['semantic_review_sha256'],
                        'Retained collector semantic review binding differs')
    return {'verified': True, 'cohort_complete': value['cohort_complete'], 'scheduled_trials': 18,
            'files': len(files), 'retention_sha256': digest(raw), 'issues': value['issues']}


def retain(output, *, terminal_confirmed=False, allow_incomplete=None, semantic_dir=None, report=None):
    require(terminal_confirmed is True, 'Owner confirmation of all original runner handles is required')
    if allow_incomplete is not None:
        require(isinstance(allow_incomplete, str) and allow_incomplete.strip(), '--allow-incomplete requires a nonempty reason')
    output = Path(output).absolute()
    require(not os.path.lexists(output) and output.parent.is_dir(), 'Output must be NEW and its parent must exist')
    require(not output.resolve().is_relative_to(ROOT.resolve()), 'Output would modify the frozen checkout')
    payloads, manifest, unchanged = plan(allow_incomplete, semantic_dir, report)
    for value in manifest['observations'].values():
        require(not output.resolve().is_relative_to(Path(value['original_group']).resolve()), 'Output would alter original observations')
    for path in manifest['original_directories']:
        require(not output.resolve().is_relative_to(Path(path).resolve()), 'Output would alter selected original evidence')
    output.mkdir(exist_ok=False)
    try:
        for name, raw in sorted(payloads.items()):
            path = output / relative(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(raw)
        unchanged()  # After output writes, before claiming capture completion.
        for name, expected in manifest['files'].items():
            raw = stable(output / name, output)
            require(len(raw) == expected['bytes'] and digest(raw) == expected['sha256'], 'Output changed during publication')
        with (output / 'RETENTION.json').open('xb') as stream:
            stream.write(encoded(manifest))
        return {'output': str(output), **verify(output)}
    except BaseException as error:
        try:
            with (output / 'INCOMPLETE.json').open('xb') as stream:
                stream.write(encoded({'capture_integrity_complete': False, 'reason': str(error),
                                      'note': 'Partial files preserved; no overwrite or automatic retry.'}))
        except OSError:
            pass
        print('Incomplete capture preserved at ' + str(output), file=sys.stderr)
        raise


def main():
    global ROOT, HERE
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output', type=Path)
    mode.add_argument('--verify', type=Path)
    parser.add_argument('--terminal-confirmed', action='store_true')
    parser.add_argument('--allow-incomplete', metavar='REASON')
    parser.add_argument('--semantic-dir', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--frozen-repo', type=Path, help='Read-only checkout containing the exact pinned Git objects and inputs')
    args = parser.parse_args()
    require(not args.verify or not (args.terminal_confirmed or args.allow_incomplete or args.semantic_dir
                                   or args.report or args.frozen_repo),
            '--verify cannot be combined with capture options')
    if args.frozen_repo is not None:
        ROOT = args.frozen_repo.absolute()
        HERE = ROOT / 'evals/source-call-sites-cohort'
    result = verify(args.verify) if args.verify else retain(args.output, terminal_confirmed=args.terminal_confirmed,
        allow_incomplete=args.allow_incomplete, semantic_dir=args.semantic_dir, report=args.report)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
