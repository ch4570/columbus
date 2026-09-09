"""Prepare prospective immutable evidence, without launching models or upstream code."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import shlex
import subprocess
import sys
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LANGUAGES = ('java', 'kotlin', 'javascript')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


observer = module('overload_observer', HERE.parent / 'exploration/observe_saved_callers.py')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observation(language):
    return Path('/tmp') / ('columbus-overload-token-' + language)


def download(language):
    pin = json.loads((HERE / 'sources.json').read_text())[language]
    directory = HERE / language
    directory.mkdir(parents=True, exist_ok=True)
    fixture = directory / 'source.zip'
    receipt = directory / 'source.json'
    if fixture.exists() or receipt.exists():
        raise ValueError('Source evidence already exists; do not overwrite')
    request = urllib.request.Request(pin['url'], headers={'User-Agent': 'Columbus-prospective-evaluation'})
    with urllib.request.urlopen(request, timeout=60) as response:
        resolved_url, data = response.geturl(), response.read(20_000_001)
    if len(data) != pin['zip_bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
        raise ValueError('Pinned upstream ZIP does not match')
    fixture.write_bytes(data)
    observer.dump(receipt, {**pin, 'requested_url': pin['url'], 'resolved_url': resolved_url,
                           'snapshot_scope': 'complete superproject archive; not recursive checkout'})
    print(json.dumps({'language': language, 'source_verified': True, 'resolved_url': resolved_url}))


def prepare(language):
    directory, output = HERE / language, observation(language)
    pin = json.loads((HERE / 'sources.json').read_text())[language]
    fixture = directory / 'source.zip'
    if digest(fixture) != pin['sha256']:
        raise ValueError('Source fixture changed')
    observer.prepare(output, fixture, directory / 'cases.json')
    metadata = json.loads((output / 'manifest.json').read_text())
    if len(metadata['source_manifest']) != pin['files']:
        raise ValueError('Unexpected superproject file inventory')
    if digest(output / 'repository' / pin['license']) != pin['license_sha256']:
        raise ValueError('Upstream license changed')
    observer.freeze_archive(output)
    frozen = {name: json.loads((output / (name + '.json')).read_text()) for name in ('manifest', 'engine')}
    frozen.update({name + '_sha256': digest(output / (name + '.json')) for name in ('manifest', 'engine')})
    observer.dump(directory / 'freeze.json', frozen)
    controls(language)
    print(json.dumps({'language': language, 'archive_preflight': True, 'citation_controls': True}), flush=True)


def controls(language):
    directory, output = HERE / language, observation(language)
    # Mechanical positive/negative citation controls are not model answers or semantic proof.
    case = json.loads((directory / 'cases.json').read_text())['cases'][0]
    answer = {'findings': []}
    for finding in case['findings']:
        lines = (output / 'repository' / finding['path']).read_text().splitlines()
        marker_lines = finding['marker'].splitlines()
        starts = [i for i in range(len(lines)) if finding['marker'] in '\n'.join(lines[i:i + len(marker_lines)])]
        if not starts:
            raise ValueError('No physical marker range')
        start = next((i for i in starts if not finding.get('call_lines') or any(
            i + 1 <= line <= i + len(marker_lines) for line in finding['call_lines'])), None)
        if start is None:
            raise ValueError('Marker does not include oracle line')
        answer['findings'].append({'id': finding['id'], 'path': finding['path'], 'start_line': start + 1,
                                  'end_line': start + len(marker_lines), 'quote': '\n'.join(lines[start:start + len(marker_lines)]),
                                  'explanation': 'Mechanical citation control only; not a semantic answer.'})
    positive = observer.grade(answer, case, output / 'repository')
    negative = copy.deepcopy(answer)
    for finding in negative['findings']:
        finding['quote'] = 'deliberately non-source control string'
    rejected = observer.grade(negative, case, output / 'repository')
    if not positive['passed'] or rejected['passed']:
        raise ValueError('Citation controls failed')
    observer.dump(directory / 'controls.json', {'positive': positive, 'negative': rejected, 'control_answer': answer})


def refresh_cases(language):
    """Apply finalized prelaunch peer-review wording; preserve previous catalog hashes."""
    directory, output = HERE / language, observation(language)
    if (HERE / 'input-hashes.json').exists() or any((observation(item) / 'trials').exists() for item in LANGUAGES):
        raise ValueError('Case changes are forbidden after freeze or any trial launch')
    previous = digest(output / 'cases.json')
    controls(language)
    raw = (directory / 'cases.json').read_bytes()
    metadata = json.loads((output / 'manifest.json').read_text())
    if observer.manifest(output / 'repository') != metadata['source_manifest']:
        raise ValueError('Source changed during preparation')
    current = hashlib.sha256(raw).hexdigest()
    (output / 'cases.json').write_bytes(raw)
    metadata['cases_sha256'] = current
    first_order = ['columbus', 'baseline'] if language == 'kotlin' else ['baseline', 'columbus']
    metadata['condition_order'] = {case['id']: first_order for case in json.loads(raw)['cases']}
    observer.dump(output / 'manifest.json', metadata)
    frozen = json.loads((directory / 'freeze.json').read_text())
    frozen['manifest'], frozen['manifest_sha256'] = metadata, digest(output / 'manifest.json')
    observer.dump(directory / 'freeze.json', frozen)
    log = directory / 'preparation-revisions.json'
    revisions = json.loads(log.read_text()) if log.exists() else []
    observer.dump(log, [*revisions, {'previous_cases_sha256': previous, 'finalized_cases_sha256': current,
                                   'stage': 'pre-freeze independent review; no models launched'}])


def verify_runtime_commit(commit):
    """Prove every copied runtime/skill byte is from the same recorded Git commit."""
    first = None
    for language in LANGUAGES:
        frozen = json.loads((HERE / language / 'freeze.json').read_text())
        files = frozen['engine']['files']
        if first is not None and files != first:
            raise ValueError('Languages have different runtime/skill inventories')
        first = files
        for name, expected in files.items():
            source = 'skills/columbus/' + (name if name == 'SKILL.md' or name.startswith('references/') else 'scripts/' + name)
            committed = subprocess.check_output(['git', 'show', commit + ':' + source], cwd=ROOT)
            if hashlib.sha256(committed).hexdigest() != expected or digest(ROOT / source) != expected:
                raise ValueError('Frozen runtime is not the current recorded commit: ' + source)


def freeze():
    target = HERE / 'input-hashes.json'
    if target.exists() or any((observation(language) / 'trials').exists() for language in LANGUAGES):
        raise ValueError('Protocol already frozen or trials exist')
    environment = {'python': sys.version, 'platform': platform.platform(),
                   'codex_cli': subprocess.check_output(['codex', '--version'], text=True).strip(),
                   'runtime_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                   'packages': json.loads(subprocess.check_output([sys.executable, '-m', 'pip', 'list', '--format=json'], text=True))}
    verify_runtime_commit(environment['runtime_commit'])
    observer.dump(HERE / 'environment.json', environment)
    collector = module('prospective_overload_collector', HERE / 'collect.py')
    names = collector.required_inputs()
    names.update(path.relative_to(ROOT).as_posix() for path in (ROOT / 'skills/columbus').rglob('*')
                 if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc')
    for language in LANGUAGES:
        frozen = json.loads((HERE / language / 'freeze.json').read_text())
        if not observer.archive_gate(observation(language), frozen['engine'])['passed']:
            raise ValueError('Archive preflight failed')
        collector.verify_observation(language, observer)
        collector.verify_controls(language, observer)
    observer.dump(target, {name: digest(ROOT / name) for name in sorted(names)})
    collector.frozen_inputs()
    print(json.dumps({'frozen_inputs': len(names), 'manifest_sha256': digest(target)}), flush=True)


def mechanism(language):
    output, directory = observation(language), HERE / language
    target = directory / 'mechanism.json'
    if target.exists() or (HERE / 'input-hashes.json').exists() or (output / 'trials').exists():
        raise ValueError('Do not replace frozen controls or run controls during trials')
    queries = {'java': ['Gson.fromJson'], 'kotlin': ['create'],
               'javascript': ['Axios._request', 'InterceptorManager.use']}[language]
    paths = {finding['path'] for finding in json.loads((directory / 'cases.json').read_text())['cases'][0]['findings']}
    prefix = [sys.executable, str(output / 'runtime/columbus.py')]
    common = ['--input', str(output / 'graph.jsonl.xz'), '--repo', '.']
    ids = []
    for query in queries:
        command = prefix + ['archive-search', query, *common, '--limit', '50']
        if language == 'kotlin':
            command += ['--path', sorted(paths)[0]]
        rows = json.loads(subprocess.check_output(command, cwd=output / 'repository', text=True))['items']
        choices = [row for row in rows if row['path'] in paths]
        if not choices:
            raise ValueError('No task declaration for control')
        ids.append(choices[0]['id'])
    overloads = language != 'javascript'
    if overloads:
        # Use the exact same-owner query derived from actual indexed identity.
        ids = [ids[0].split('::', 1)[1].split(':', 1)[0]]
    arguments = ['archive-source', *ids, *(['--overloads'] if overloads else []), *common,
                 '--limit', '300', '--budget-bytes', '32000']
    recognizer = module('overload_control_recognizer', HERE.parent / 'exploration/archive_evidence.py')
    results = []
    for form in ('json', 'text'):
        command = prefix + [*arguments, '--format', form]
        raw = subprocess.check_output(command, cwd=output / 'repository', text=True)
        event = {'type': 'item.completed', 'item': {'id': 'control-' + form, 'type': 'command_execution',
                 'exit_code': 0, 'command': shlex.join(command), 'aggregated_output': raw}}
        receipts = recognizer.graph_evidence([event], output, paths)
        if not receipts or not receipts[0]['useful_task_evidence'] or not receipts[0]['batch_used']:
            raise ValueError('Representative batch/overload evidence was not recognized')
        results.append({'format': form, 'argv': command, 'output_bytes': len(raw.encode()),
                        'output_sha256': hashlib.sha256(raw.encode()).hexdigest(), 'receipts': receipts})
    frozen = json.loads((output / 'engine.json').read_text())
    if not observer.archive_gate(output, frozen)['passed'] or (output / 'repository/.columbus').exists():
        raise ValueError('Control changed immutable archive/runtime or created consumer SQLite')
    observer.dump(target, {'passed': True, 'queries': queries, 'source_queries': ids, 'overloads': overloads,
                           'recognizer_version': recognizer.RECOGNIZER_VERSION, 'results': results,
                           'no_consumer_sqlite': True})
    print(json.dumps({'language': language, 'mechanism_controls': True}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['download', 'prepare', 'mechanism', 'refresh_cases', 'freeze'])
    parser.add_argument('language', nargs='?', choices=LANGUAGES)
    args = parser.parse_args()
    if args.operation == 'freeze':
        freeze()
    elif args.language is None:
        parser.error('language is required for download/prepare')
    else:
        globals()[args.operation](args.language)
