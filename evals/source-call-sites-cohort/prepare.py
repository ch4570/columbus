"""Explicit model-free preparation and prospective freeze; never start a model."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile

_COMMON_PATH = Path(__file__).resolve().with_name('common.py')
_COMMON_KEY = '_source_call_cohort_' + hashlib.sha256(str(_COMMON_PATH).encode()).hexdigest()[:16]
if _COMMON_KEY not in sys.modules:
    _SPEC = importlib.util.spec_from_file_location(_COMMON_KEY, _COMMON_PATH)
    _COMMON = importlib.util.module_from_spec(_SPEC)
    sys.modules[_COMMON_KEY] = _COMMON
    _SPEC.loader.exec_module(_COMMON)
common = sys.modules[_COMMON_KEY]
HERE, ROOT = common.HERE, common.ROOT
LANGUAGES, CONDITIONS, ORDERS = common.LANGUAGES, common.CONDITIONS, common.ORDERS
RUNTIME_COMMITS, RUNTIME_DELTA = common.RUNTIME_COMMITS, common.RUNTIME_DELTA
OBSERVE, PREFLIGHT = common.OBSERVE, common.PREFLIGHT
read, require, save, sha = common.read, common.require, common.save, common.sha
observation, exact_manifest, disk_guard = common.observation, common.exact_manifest, common.disk_guard


def copy_new(source, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Path(source).open('rb') as incoming, destination.open('xb') as outgoing:
        shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)


def export_runtime(variant):
    require(variant in RUNTIME_COMMITS, 'Unknown runtime variant')
    target = HERE / 'runtimes' / variant
    require(not target.exists(), 'Runtime export already exists')
    target.mkdir(parents=True)
    commit, prefix = RUNTIME_COMMITS[variant], 'skills/columbus/'
    names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', commit, '--', prefix],
                                    cwd=ROOT, text=True).splitlines()
    expected = {}
    for name in names:
        require(name.startswith(prefix), 'Unexpected runtime export path')
        suffix = name[len(prefix):]
        if suffix.startswith('scripts/') and suffix.endswith('.py'):
            relative = suffix[len('scripts/'):]
            if relative != 'columbus.py' and not (relative.startswith('columbus/') and relative.count('/') == 1):
                continue
        elif suffix == 'SKILL.md' or suffix.startswith('references/'):
            relative = suffix
        else:
            continue
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts, 'Unsafe runtime export path')
        payload = subprocess.check_output(['git', 'show', commit + ':' + name], cwd=ROOT)
        require(relative not in expected, 'Duplicate runtime export path')
        expected[relative] = hashlib.sha256(payload).hexdigest()
        output = target / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as stream:
            stream.write(payload)
    require((target / 'SKILL.md').is_file() and (target / 'columbus.py').is_file(), 'Incomplete runtime export')
    require(exact_manifest(target) == expected, 'Runtime export differs from pinned Git payloads')
    return expected


def check_provenance(source, historical):
    """Bind known historical schema variants; never silently prefer an alias."""
    require(isinstance(historical, dict), 'Historical source provenance must be an object')

    def bind(record, names, expected, label, *, optional=False):
        present = [name for name in names if name in record]
        require(present or optional, 'Missing historical source provenance ' + label)
        require(all(type(record[name]) is type(expected) and record[name] == expected for name in present),
                'Historical source provenance ' + label + ' differs or has conflicting aliases')

    bind(historical, ('repository',), source['repository'], 'repository')
    bind(historical, ('commit', 'source_commit'), source['commit'], 'commit')
    bind(historical, ('fixture_sha256', 'sha256'), source['fixture_sha256'], 'ZIP hash')
    bind(historical, ('files', 'source_files'), source['source_files'], 'file count')
    bind(historical, ('archive_prefix', 'fixture_prefix'), source['fixture_prefix'], 'prefix', optional=True)
    bind(historical, ('source_bytes',), source['source_bytes'], 'source bytes', optional=True)
    bind(historical, ('corpus_manifest_sha256',), source['corpus_manifest_sha256'], 'file map', optional=True)
    if source['repository'] == 'https://github.com/spring-projects/spring-framework':
        license_data = historical.get('license')
        require(isinstance(license_data, dict), 'Historical Spring license must be an object')
        bind(license_data, ('upstream_sha256', 'sha256'), source['license_sha256'], 'Spring license hash')
    elif 'license_sha256' in historical:
        bind(historical, ('license_sha256',), source['license_sha256'], 'license hash')


def check_sources(sources):
    require(isinstance(sources, dict) and set(sources) == set(LANGUAGES), 'Expected exactly three source bindings')
    for language in LANGUAGES:
        source = sources[language]
        historical = read(HERE / language / 'source.json')
        check_provenance(source, historical)
        if source['repository'] == 'https://github.com/spring-projects/spring-framework':
            require(sha(HERE / 'LICENSE.spring-framework.txt') == source['license_sha256'],
                    'Pinned standalone Spring license differs')
        fixture = Path(source['fixture'])
        require(fixture.is_file() and not fixture.is_symlink() and sha(fixture) == source['fixture_sha256'],
                'Canonical source ZIP changed')
        prefix = source['fixture_prefix']
        require(isinstance(prefix, str) and prefix.endswith('/') and prefix.count('/') == 1
                and prefix[:-1] not in ('', '.', '..'), 'Source ZIP needs one exact top-level prefix')
        with zipfile.ZipFile(fixture) as archive:
            files, source_bytes = {}, 0
            for info in archive.infolist():
                require(info.filename.startswith(prefix), 'Source ZIP prefix differs')
                if info.is_dir():
                    continue
                name = info.filename[len(prefix):]
                require(name and not name.startswith('/') and '\\' not in name and ':' not in name
                        and all(part not in ('', '.', '..') for part in name.split('/'))
                        and not {'.git', '.columbus', '.repoatlas'} & set(name.split('/')),
                        'Unsafe or reserved source ZIP path')
                require(name not in files, 'Duplicate source ZIP paths')
                digest = hashlib.sha256()
                with archive.open(info) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(chunk)
                        source_bytes += len(chunk)
                files[name] = digest.hexdigest()
            require(files and len(files) == source['source_files'], 'Source ZIP inventory count differs')
            require(source_bytes == source['source_bytes'], 'Source ZIP byte count differs')
            encoded = json.dumps(files, sort_keys=True, separators=(',', ':')).encode('utf-8')
            require(hashlib.sha256(encoded).hexdigest() == source['corpus_manifest_sha256'],
                    'Source ZIP complete file map differs')
        case = read(HERE / language / 'cases.json')
        require(isinstance(case, dict) and isinstance(case.get('cases'), list) and len(case['cases']) == 1,
                'One prospective case per language is required')


def _remove_generated(output, name):
    # Only Git metadata created in this fresh OBSERVE.prepare invocation.
    path = output / 'repository' / name
    require(name == '.git' and path.is_dir() and not path.is_symlink(),
            'Expected a newly generated local preparation directory')
    shutil.rmtree(path)


def prepare(observation_root):
    observation_root = Path(observation_root).resolve()
    require(not (HERE / 'environment.json').exists() and not observation_root.exists()
            and not (HERE / 'runtimes').exists(),
            'Preparation exists; preserve inputs and choose a fresh cohort, not an overwrite')
    disk_guard(observation_root, preparing=True)
    sources = read(HERE / 'sources.json')
    check_sources(sources)
    started = OBSERVE.time.monotonic()
    reuse = common.module('graph_reuse', HERE / 'reuse.py')
    reused = reuse.check_bindings(sources, read(HERE / 'graph-bindings.json'))
    reuse_verification_seconds = OBSERVE.time.monotonic() - started
    runtime_manifests = {variant: export_runtime(variant) for variant in RUNTIME_COMMITS}
    control, candidate = (runtime_manifests[variant] for variant in RUNTIME_COMMITS)
    changed = sorted(name for name in set(control) | set(candidate) if control.get(name) != candidate.get(name))
    require(set(changed) == RUNTIME_DELTA, 'Runtime variants differ beyond reviewed source-call-site package delta')
    executable = shutil.which('codex')
    require(executable is not None, 'Codex CLI not found')
    executable = str(Path(executable).resolve())
    environment = {'created_at': datetime.now(timezone.utc).isoformat(),
        'observation_root': str(observation_root), 'python': sys.version, 'python_executable': sys.executable,
        'platform': platform.platform(), 'codex_executable': executable, 'codex_sha256': sha(executable),
        'codex_cli': subprocess.check_output([executable, '--version'], text=True).strip(),
        'runtime_commits': RUNTIME_COMMITS, 'runtime_changed_files': changed,
        'preparation_mode': 'historical_graph_reuse',
        'reuse_verification_seconds': reuse_verification_seconds,
        'prospective_cli_change': '--ignore-rules; do not load user/project execpolicy files',
        'packages': json.loads(subprocess.check_output([sys.executable, '-m', 'pip', 'list', '--format=json'], text=True))}
    save(HERE / 'environment.json', environment)
    for language in LANGUAGES:
        started = OBSERVE.time.monotonic()
        producer = reused[language]
        save(HERE / language / 'graph-reuse.json', producer)
        fixture = Path(sources[language]['fixture'])
        copy_new(fixture, HERE / language / 'source.zip')
        fixture = HERE / language / 'source.zip'
        require(sha(fixture) == sources[language]['fixture_sha256'], 'Retained source ZIP changed during copy')
        candidate = observation(language, 'candidate')
        manifest = OBSERVE.prepare(candidate, fixture, HERE / language / 'cases.json')
        source_map = json.dumps(manifest['source_manifest'], sort_keys=True, separators=(',', ':')).encode('utf-8')
        require(manifest['fixture_sha256'] == sources[language]['fixture_sha256']
                and hashlib.sha256(source_map).hexdigest() == sources[language]['corpus_manifest_sha256']
                and manifest['source_manifest'] == producer['source_manifest'],
                'Extracted source differs from the reviewed complete ZIP')
        shutil.copytree(HERE / 'runtimes/candidate', candidate / 'runtime')
        copy_new(producer['fixture'], candidate / 'graph.jsonl.xz')
        require(sha(candidate / 'graph.jsonl.xz') == producer['fixture_sha256'],
                'Historical graph changed during copy')
        copy_new(candidate / 'graph.jsonl.xz', HERE / language / 'graph.jsonl.xz')
        require(sha(HERE / language / 'graph.jsonl.xz') == producer['fixture_sha256'],
                'Retained historical graph changed during copy')
        _remove_generated(candidate, '.git')
        require(exact_manifest(candidate / 'repository') == manifest['source_manifest'], 'Producer source changed')
        frozen = {}
        for condition in CONDITIONS:
            output = observation(language, condition)
            variant = 'control' if condition == 'control' else 'candidate'
            if condition != 'candidate':
                current = OBSERVE.prepare(output, fixture, HERE / language / 'cases.json')
                require(current['source_manifest'] == manifest['source_manifest'], 'Arm source corpora differ')
                _remove_generated(output, '.git')
                shutil.copytree(HERE / 'runtimes' / variant, output / 'runtime')
                copy_new(candidate / 'graph.jsonl.xz', output / 'graph.jsonl.xz')
            arm_manifest = read(output / 'manifest.json')
            arm_manifest.update({'schema': 'columbus.source-call-sites-cohort-source/v1', 'arm': condition,
                'evidence_mode': 'saved_archive', 'condition_order': ORDERS[language],
                'limitations': ['Reused pinned corpora and development operations, not held-out tasks or repositories.',
                    'Efficient ordinary multi-range/source-to-JSON reads permitted in all arms.',
                    'Byte-identical historical graph reused; producer costs are historical, not newly measured.',
                    'No new index/export or consumer SQLite or Git metadata.',
                    'Aliases are requested settings, not backend attestations.',
                    'Cached input and reasoning output are subsets; no billing inference.']})
            # Replace only the receipt just generated above, before freezing or trials.
            OBSERVE.dump(output / 'manifest.json', arm_manifest)
            require(exact_manifest(output / 'runtime') == runtime_manifests[variant]
                    and exact_manifest(HERE / 'runtimes' / variant) == runtime_manifests[variant],
                    'Consumer runtime differs from pinned Git export')
            engine = {'runtime_commit': RUNTIME_COMMITS[variant], 'files': runtime_manifests[variant],
                'preparation_mode': 'historical_graph_reuse', 'graph_producer_commit': producer['producer_commit'],
                'historical_index': producer['index'],
                'historical_cold_index_seconds': producer['historical_cold_index_seconds'],
                'historical_cold_export_seconds': producer['historical_cold_export_seconds'],
                'new_cold_index_seconds': None, 'new_cold_export_seconds': None,
                'graph_reuse_receipt_sha256': sha(HERE / language / 'graph-reuse.json')}
            engine['archive'] = {'archive_sha256': producer['fixture_sha256'], 'revision': producer['revision'],
                'counts': producer['counts'],
                'source_manifest': manifest['source_manifest'], 'runtime_manifest': engine['files'],
                'verifier_sha256': sha(HERE.parent / 'archive-exploration/preflight.py')}
            require(exact_manifest(output / 'repository') == manifest['source_manifest'], 'Consumer source changed')
            PREFLIGHT.verify(output / 'repository', output / 'runtime', output / 'graph.jsonl.xz', engine['archive'])
            require(exact_manifest(output / 'runtime') == runtime_manifests[variant]
                    and exact_manifest(HERE / 'runtimes' / variant) == runtime_manifests[variant],
                    'Consumer runtime changed during preparation preflight')
            save(output / 'engine.json', engine)
            frozen[condition] = {'manifest': read(output / 'manifest.json'), 'engine': engine,
                'manifest_sha256': sha(output / 'manifest.json'), 'engine_sha256': sha(output / 'engine.json')}
        save(HERE / language / 'freeze.json', frozen)
        save(HERE / language / 'preparation.json', {
            'mode': 'historical_graph_reuse',
            'copy_and_consumer_verification_seconds': OBSERVE.time.monotonic() - started,
            'new_cold_index_seconds': None, 'new_cold_export_seconds': None,
            'note': 'New wall time for source/runtime/graph copies and consumer checks; historical producer times are separate.'})
    disk_guard(observation_root)


def citation_controls(language):
    directory, output = HERE / language, observation(language, 'candidate')
    require(not (directory / 'citation-controls.json').exists(), 'Citation controls already captured')
    case = read(directory / 'cases.json')['cases'][0]
    answer = {'findings': []}
    for finding in case['findings']:
        lines = (output / 'repository' / finding['path']).read_text(encoding='utf-8').splitlines()
        matches = [i for i, line in enumerate(lines, 1) if finding['marker'] in line]
        anchors = finding.get('call_lines') or matches
        candidates = [(min(marker, anchor), max(marker, anchor)) for marker in matches for anchor in anchors
                      if type(anchor) is int and 1 <= anchor <= len(lines) and abs(marker - anchor) < 40]
        require(bool(candidates), 'No bounded marker-plus-reviewed-anchor witness')
        start, end = min(candidates, key=lambda pair: (pair[1] - pair[0], pair[0]))
        answer['findings'].append({'id': finding['id'], 'path': finding['path'], 'start_line': start,
            'end_line': end, 'quote': '\n'.join(lines[start - 1:end]), 'explanation': 'Citation control only, not semantic approval.'})
    positive = OBSERVE.grade(answer, case, output / 'repository')
    negative_answer = copy.deepcopy(answer)
    for finding in negative_answer['findings']:
        finding['quote'] = '__THIS_IS_NOT_A_SOURCE_QUOTE__'
    negative = OBSERVE.grade(negative_answer, case, output / 'repository')
    require(positive['passed'] and not negative['passed'], 'Citation control failed')
    save(directory / 'citation-controls.json', {'answer': answer, 'positive': positive,
        'negative_answer': negative_answer, 'negative': negative})


def verify_retained(language, condition):
    """Keep retained copies tied to the authoritative prepared arm receipts."""
    variant = 'control' if condition == 'control' else 'candidate'
    arm = read(HERE / language / 'freeze.json')[condition]
    engine, manifest = arm['engine'], arm['manifest']
    producer = read(HERE / language / 'graph-reuse.json')
    require(engine['runtime_commit'] == RUNTIME_COMMITS[variant]
            and exact_manifest(HERE / 'runtimes' / variant) == engine['files'],
            'Retained runtime differs from prepared pinned export')
    require(sha(HERE / language / 'graph-reuse.json') == engine['graph_reuse_receipt_sha256']
            and engine['graph_producer_commit'] == producer['producer_commit']
            and engine['archive']['archive_sha256'] == producer['fixture_sha256']
            and engine['archive']['revision'] == producer['revision']
            and engine['archive']['counts'] == producer['counts']
            and engine['archive']['source_manifest'] == producer['source_manifest'],
            'Historical graph reuse receipt differs from prepared engine')
    require(sha(HERE / language / 'graph.jsonl.xz') == engine['archive']['archive_sha256']
            and sha(HERE / language / 'source.zip') == manifest['fixture_sha256'],
            'Retained source or historical graph changed before freeze')


def freeze():
    require(not (HERE / 'input-hashes.json').exists(), 'Already frozen; do not rewrite hashes')
    common.verify_environment()
    disk_guard(observation('java', 'baseline'))
    for language in LANGUAGES:
        for condition in CONDITIONS:
            verify_retained(language, condition)
            common.verify_observation(language, condition)
            require(not (observation(language, condition) / 'trials').exists(), 'Model already started before freeze')
        require(not (observation(language, 'baseline').parent / 'runner.json').exists(), 'Runner already started')
        require(read(HERE / language / 'controls.json')['passed'] is True, 'Prelaunch controls incomplete')
        common.verify_controls(language)
    paths = common.required_inputs()
    require(all(path.is_file() and not path.is_symlink() for path in paths), 'Required input missing')
    save(HERE / 'input-hashes.json', {path.relative_to(ROOT).as_posix(): sha(path) for path in sorted(paths)})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--observation-root', type=Path, required=True)
    sub.add_parser('citation-controls')
    sub.add_parser('freeze')
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.observation_root)
    elif args.command == 'citation-controls':
        for language in LANGUAGES:
            citation_controls(language)
    else:
        freeze()
