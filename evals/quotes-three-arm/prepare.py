"""Model-free preparation, runtime export, controls and final prospective freeze."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import copy
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from common import (HERE, ROOT, LANGUAGES, CONDITIONS, ORDERS, RUNTIME_COMMITS, OBSERVE, PREFLIGHT,
                    observation, prompt, read, require, required_inputs, save, sha, verify_observation)


def export_runtime(variant):
    target = HERE / 'runtimes' / variant
    require(not target.exists(), 'Runtime export already exists')
    commit = RUNTIME_COMMITS[variant]
    prefix = 'skills/columbus/'
    names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', commit, '--', prefix],
                                    cwd=ROOT, text=True).splitlines()
    for name in names:
        suffix = name[len(prefix):]
        if suffix.startswith('scripts/') and suffix.endswith('.py'):
            relative = suffix[len('scripts/'):]
            if relative != 'columbus.py' and not (relative.startswith('columbus/') and relative.count('/') == 1):
                continue
        elif suffix == 'SKILL.md' or suffix.startswith('references/'):
            relative = suffix
        else:
            continue
        payload = subprocess.check_output(['git', 'show', commit + ':' + name], cwd=ROOT)
        output = target / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as stream:
            stream.write(payload)
    require((target / 'SKILL.md').is_file() and (target / 'columbus.py').is_file(), 'Incomplete runtime export')


def prepare(observation_root):
    require(not (HERE / 'environment.json').exists() and not observation_root.exists(),
            'Preparation exists; preserve inputs and choose a fresh cohort, not an overwrite')
    for variant in RUNTIME_COMMITS:
        export_runtime(variant)
    control = PREFLIGHT.file_manifest(HERE / 'runtimes/control')
    quotes = PREFLIGHT.file_manifest(HERE / 'runtimes/quotes')
    changed = sorted(name for name in set(control) | set(quotes) if control.get(name) != quotes.get(name))
    require(set(changed) == {'SKILL.md', 'references/archive.md', 'columbus/cli.py', 'columbus/quotes.py'},
            'Runtime variants differ beyond reviewed PR17 package delta')
    environment = {'created_at': datetime.now(timezone.utc).isoformat(),
                   'observation_root': str(observation_root.resolve()), 'python': sys.version,
                   'python_executable': sys.executable, 'platform': platform.platform(),
                   'codex_cli': subprocess.check_output(['codex', '--version'], text=True).strip(),
                   'runtime_commits': RUNTIME_COMMITS,
                   'runtime_changed_files': changed,
                   'packages': json.loads(subprocess.check_output([sys.executable, '-m', 'pip', 'list', '--format=json'], text=True))}
    save(HERE / 'environment.json', environment)
    license_bytes = subprocess.check_output(['git', 'show',
        '4c8c6409a27a62ab163d3b6196ad862b7c835440:LICENSE.txt'], cwd='/tmp/columbus-spring-framework')
    require(OBSERVE.sha(license_bytes) == '56dfc19e0dc836e30177332f73e8e6fbc297941acf3d906eec6eaaa46c2c452a',
            'Upstream Spring license changed')
    with (HERE / 'LICENSE.spring-framework.txt').open('xb') as stream:
        stream.write(license_bytes)
    sources = read(HERE / 'sources.json')
    for language in LANGUAGES:
        source = sources[language]
        fixture = Path(source['fixture'])
        require(sha(fixture) == source['fixture_sha256'], 'Canonical source ZIP changed')
        require(not (HERE / language / 'source.zip').exists(), 'Retained ZIP exists')
        shutil.copyfile(fixture, HERE / language / 'source.zip')
        quotes = observation(language, 'quotes')
        manifest = OBSERVE.prepare(quotes, fixture, HERE / language / 'cases.json')
        shutil.copytree(HERE / 'runtimes/quotes', quotes / 'runtime')
        started = OBSERVE.time.monotonic()
        indexed = json.loads(subprocess.check_output([sys.executable, '-B', str(quotes / 'runtime/columbus.py'),
                             'sync', '--repo', str(quotes / 'repository')], text=True))
        index_seconds = OBSERVE.time.monotonic() - started
        require(OBSERVE.index_ready(indexed), 'Empty or failed cold index')
        started = OBSERVE.time.monotonic()
        archive = json.loads(subprocess.check_output([sys.executable, '-B', str(quotes / 'runtime/columbus.py'),
                             'archive', '--snapshot', '--repo', str(quotes / 'repository'),
                             '--output', str(quotes / 'graph.jsonl.xz'), '--compression', 'xz'], text=True))
        archive_seconds = OBSERVE.time.monotonic() - started
        require(not (HERE / language / 'graph.jsonl.xz').exists(), 'Retained graph exists')
        shutil.copyfile(quotes / 'graph.jsonl.xz', HERE / language / 'graph.jsonl.xz')
        # This exact directory was created by the sync immediately above in a fresh observation.
        shutil.rmtree(quotes / 'repository/.columbus')
        frozen = {}
        for condition in CONDITIONS:
            output = observation(language, condition)
            variant = 'control' if condition == 'control' else 'quotes'
            if condition != 'quotes':
                current = OBSERVE.prepare(output, fixture, HERE / language / 'cases.json')
                require(current['source_manifest'] == manifest['source_manifest'], 'Arm source corpora differ')
                shutil.copytree(HERE / 'runtimes' / variant, output / 'runtime')
                shutil.copyfile(quotes / 'graph.jsonl.xz', output / 'graph.jsonl.xz')
            arm_manifest = read(output / 'manifest.json')
            arm_manifest.update({'schema': 'columbus.quotes-three-arm-source/v1', 'arm': condition,
                                 'evidence_mode': 'saved_archive', 'condition_order': ORDERS[language],
                                 'limitations': ['Reused pinned corpus and new operation, not a held-out repository.',
                                     'Efficient ordinary multi-range/source-to-JSON reads permitted in all arms.',
                                     'Saved graph preparation cost is separate; no consumer SQLite.',
                                     'Aliases are requested settings, not backend attestations.',
                                     'Cached input and reasoning output are subsets; no billing inference.']})
            # Replace only the just-generated legacy prepare receipt, before any freeze or model.
            OBSERVE.dump(output / 'manifest.json', arm_manifest)
            engine = {'runtime_commit': RUNTIME_COMMITS[variant], 'files': PREFLIGHT.file_manifest(output / 'runtime'),
                      'index': {key: indexed[key] for key in ('files', 'symbols', 'edges', 'indexed_bytes', 'revision')},
                      'cold_index_seconds': index_seconds, 'cold_export_seconds': archive_seconds}
            engine['archive'] = {'archive_sha256': sha(output / 'graph.jsonl.xz'), 'revision': archive['revision'],
                 'counts': {key: archive[key] for key in ('files', 'nodes', 'scopes', 'edges', 'references', 'imports', 'diagnostics')},
                 'source_manifest': manifest['source_manifest'], 'runtime_manifest': engine['files'],
                 'verifier_sha256': sha(HERE.parent / 'archive-exploration/preflight.py')}
            PREFLIGHT.verify(output / 'repository', output / 'runtime', output / 'graph.jsonl.xz', engine['archive'])
            save(output / 'engine.json', engine)
            frozen[condition] = {'manifest': read(output / 'manifest.json'), 'engine': engine,
                                 'manifest_sha256': sha(output / 'manifest.json'), 'engine_sha256': sha(output / 'engine.json')}
        save(HERE / language / 'freeze.json', frozen)


def citation_controls(language):
    directory = HERE / language
    output = observation(language, 'quotes')
    case = read(directory / 'cases.json')['cases'][0]
    answer = {'findings': []}
    for finding in case['findings']:
        lines = (output / 'repository' / finding['path']).read_text(encoding='utf-8').splitlines()
        matches = [i for i, line in enumerate(lines, 1) if finding['marker'] in line]
        require(bool(matches), 'Missing reviewed citation marker')
        anchors = finding.get('call_lines') or matches
        candidates = [(min(marker, anchor), max(marker, anchor)) for marker in matches for anchor in anchors
                      if type(anchor) is int and 1 <= anchor <= len(lines) and abs(marker - anchor) < 40]
        require(bool(candidates), 'No bounded marker-plus-reviewed-anchor witness')
        start, end = min(candidates, key=lambda pair: (pair[1] - pair[0], pair[0]))
        answer['findings'].append({'id': finding['id'], 'path': finding['path'], 'start_line': start,
                                  'end_line': end, 'quote': '\n'.join(lines[start - 1:end]),
                                  'explanation': 'Citation control only, not semantic approval.'})
    positive = OBSERVE.grade(answer, case, output / 'repository')
    negative_answer = copy.deepcopy(answer)
    for finding in negative_answer['findings']:
        finding['quote'] = '__THIS_IS_NOT_A_SOURCE_QUOTE__'
    negative = OBSERVE.grade(negative_answer, case, output / 'repository')
    require(positive['passed'] and not negative['passed'], 'Citation control failed')
    save(directory / 'citation-controls.json', {'answer': answer, 'positive': positive, 'negative_answer': negative_answer, 'negative': negative})


def freeze():
    require(not (HERE / 'input-hashes.json').exists(), 'Already frozen; do not rewrite hashes')
    from common import verify_controls, verify_environment
    verify_environment()
    for language in LANGUAGES:
        for condition in CONDITIONS:
            verify_observation(language, condition)
            require(not (observation(language, condition) / 'trials').exists(), 'Model already started before freeze')
        controls = read(HERE / language / 'controls.json')
        require(controls['passed'] is True, 'Prelaunch controls incomplete')
        verify_controls(language)
    paths = required_inputs()
    paths.update(HERE / language / 'citation-controls.json' for language in LANGUAGES)
    paths.update(HERE / language / 'relationships.json' for language in LANGUAGES)
    require(all(path.is_file() for path in paths), 'Required input missing')
    save(HERE / 'input-hashes.json', {path.relative_to(ROOT).as_posix(): sha(path) for path in sorted(paths)})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare'); prep.add_argument('--observation-root', type=Path, required=True)
    sub.add_parser('citation-controls'); sub.add_parser('freeze')
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.observation_root)
    elif args.command == 'citation-controls':
        for language in LANGUAGES:
            citation_controls(language)
    else:
        freeze()
