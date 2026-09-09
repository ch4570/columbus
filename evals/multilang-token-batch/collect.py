"""Verify terminal observations against the frozen six-pair gate; never run models."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LANGUAGES = ('java', 'kotlin', 'javascript')
CONDITIONS = ('baseline', 'columbus')
OBSERVATIONS = {language: Path(f'/tmp/columbus-token-{language}-batch') for language in LANGUAGES}


class GateError(ValueError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def require(condition, message):
    if not condition:
        raise GateError(message)


def semantic_gate(review, criteria, answer_sha256, rubric_sha256):
    """Require every frozen clause, with exact IDs/indices and actual booleans."""
    reasons = []
    if not isinstance(review, dict):
        return {'passed': False, 'pending': True, 'reasons': ['semantic review missing']}
    if review.get('skipped') or review.get('pending') or review.get('status') in ('pending', 'skipped'):
        return {'passed': False, 'pending': True, 'reasons': ['semantic review not completed']}
    for field, expected in (('answer_sha256', answer_sha256), ('rubric_sha256', rubric_sha256)):
        if review.get(field) != expected:
            reasons.append(field + ' mismatch')
    findings = review.get('findings')
    if not isinstance(findings, list) or not all(isinstance(item, dict) for item in findings):
        return {'passed': False, 'pending': True, 'reasons': reasons + ['semantic findings missing']}
    ids = [item.get('id') for item in findings]
    if len(ids) != len(criteria) or set(ids) != set(criteria):
        reasons.append('semantic finding IDs missing, duplicate or unexpected')
    pending = False
    for identifier, clauses in criteria.items():
        matches = [item for item in findings if item.get('id') == identifier]
        if len(matches) != 1:
            pending = True
            continue
        finding = matches[0]
        checks = finding.get('checks')
        if not isinstance(checks, list) or not all(isinstance(check, dict) for check in checks):
            reasons.append(identifier + ': clause checks missing')
            pending = True
            continue
        indices = [check.get('criterion_index') for check in checks]
        if (len(indices) != len(clauses) or any(type(index) is not int for index in indices)
                or set(indices) != set(range(len(clauses)))):
            reasons.append(identifier + ': clause indices missing, duplicate or unexpected')
            pending = True
        for item in [finding, *checks]:
            if type(item.get('passed')) is not bool or not isinstance(item.get('reason'), str) or not item['reason'].strip():
                reasons.append(identifier + ': review must state a boolean and reason')
                pending = True
            elif item['passed'] is not True:
                reasons.append(identifier + ': semantic check failed')
    return {'passed': not reasons and not pending, 'pending': pending, 'reasons': reasons}


def pair_gate(baseline, columbus):
    reasons = []
    for condition, trial in (('baseline', baseline), ('columbus', columbus)):
        for flag in ('verified', 'terminal_passed', 'citation_passed', 'semantic_passed'):
            if trial.get(flag) is not True:
                reasons.append(condition + ': ' + flag)
    if columbus.get('graph_evidence_used') is not True:
        reasons.append('columbus: useful graph evidence absent')
    usage = [trial.get('usage') for trial in (baseline, columbus)]
    for key in ('input_tokens', 'output_tokens'):
        if any(not isinstance(item, dict) or type(item.get(key)) is not int or item[key] < 0 for item in usage):
            reasons.append(key + ': usage missing or invalid')
        elif not usage[1][key] < usage[0][key]:
            reasons.append(key + ': Columbus must be strictly lower')
    return {'accepted': not reasons, 'reasons': reasons}


def cohort_gate(pairs):
    expected = {(language, repeat) for language in LANGUAGES for repeat in (1, 2)}
    actual = [(pair.get('language'), pair.get('repeat')) for pair in pairs]
    return (len(actual) == len(expected) and set(actual) == expected
            and all(pair.get('accepted') is True for pair in pairs))


def frozen_inputs():
    path = HERE / 'input-hashes.json'
    require(path.is_file(), 'input-hashes.json is missing; inputs have not been frozen')
    hashes = read_json(path)
    required = {'evals/multilang-token-batch/' + name for name in ('PLAN.md', 'collect.py', 'run.py')}
    required.update(('evals/exploration/observe_saved_callers.py', 'evals/exploration/answer.schema.json',
                     'evals/archive-exploration/preflight.py', 'tests/test_multilang_token_gate.py'))
    for language in LANGUAGES:
        required.update(f'evals/multilang-token-batch/{language}/{name}' for name in
                        ('cases.json', 'criteria.json', 'SOURCE-REVIEW.md', 'source.json', 'freeze.json'))
    require(isinstance(hashes, dict) and required <= set(hashes), 'frozen input inventory lacks required files')
    for name, digest in hashes.items():
        target = ROOT / name
        require(not Path(name).is_absolute() and target.resolve().is_relative_to(ROOT), 'input path escapes repository')
        require(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest), 'invalid frozen input digest')
        require(target.is_file() and sha(target) == digest, 'frozen input changed: ' + name)
    return hashes


def graph_evidence(events, observation, paths):
    """Count recognizable successful frozen-runtime retrieval, never empty callers."""
    receipts = []
    for event in events:
        item = event.get('item', {})
        if event.get('type') != 'item.completed' or item.get('type') != 'command_execution' or item.get('exit_code') != 0:
            continue
        try:
            words = shlex.split(item['command'])
            if len(words) >= 3 and words[1] in ('-lc', '-c'):
                words = shlex.split(words[2])
            position = next(i for i, word in enumerate(words) if Path(word).resolve() == (observation / 'runtime/columbus.py').resolve())
            require(position > 0 and Path(words[position - 1]).name.startswith('python'), 'not frozen Python wrapper')
            operation = words[position + 1]
            require(operation in ('archive-source', 'archive-search', 'archive-callers', 'archive-neighbors'), 'not archive retrieval')
            require(Path(words[words.index('--input') + 1]).resolve() == (observation / 'graph.jsonl.xz').resolve(), 'different archive')
            output = item.get('aggregated_output', '')
            useful, batch = False, False
            if output.lstrip().startswith('{'):
                packet = json.loads(output)
                blocks = packet.get('sources', [packet])
                useful = any(block.get('path') in paths and isinstance(block.get('source'), str)
                             and block['source'].strip() for block in blocks)
                if operation == 'archive-search':
                    useful = any(row.get('path') in paths and row.get('id') for row in packet.get('items', []))
                elif operation in ('archive-callers', 'archive-neighbors'):
                    useful = bool(packet.get('edges')) and any(row.get('path') in paths for row in packet.get('nodes', []))
                batch = operation == 'archive-source' and len(packet.get('targets', [])) > 1
            else:
                lines = output.splitlines()
                require(lines and lines[0].startswith('columbus archive-'), 'not recognizable archive text')
                metadata = next(json.loads(line[9:]) for line in lines if line.startswith('metadata '))
                batch = operation == 'archive-source' and len(metadata.get('targets', [])) > 1
                current_path = metadata.get('path')
                for line in lines:
                    if line.startswith('source '):
                        current_path = json.loads(line[7:]).get('path')
                    elif operation == 'archive-source' and current_path in paths and re.match(r'\d+\| \s*\S', line):
                        useful = True
                    elif operation == 'archive-search' and line.startswith('{'):
                        row = json.loads(line)
                        useful = useful or bool(row.get('id') and row.get('path') in paths)
                if operation in ('archive-callers', 'archive-neighbors') and metadata.get('matched_edges', 0) > 0:
                    useful = any(isinstance(row, list) and len(row) == 3 and row[1] in paths
                                 for row in (json.loads(line) for line in lines if line.startswith('[')))
            receipts.append({'command_id': item.get('id'), 'operation': operation,
                             'useful_task_evidence': bool(useful), 'batch_used': bool(batch and useful),
                             'output_sha256': hashlib.sha256(output.encode()).hexdigest()})
        except (ValueError, KeyError, IndexError, StopIteration, TypeError):
            continue
    return receipts


def collect_trial(observe, observation, language, case, criteria, condition, repeat, archive_gate):
    name = f"{case['id']}-{condition}-{repeat}"
    trial = observation / 'trials' / name
    result_path = trial / 'result.json'
    if not result_path.is_file():
        return {'trial': name, 'verified': False, 'pending': True,
                'reason': 'Terminal result missing; this does not establish that the process is stopped.'}
    result = read_json(result_path)
    require((result.get('case'), result.get('condition'), result.get('repeat')) == (case['id'], condition, repeat), 'trial identity mismatch')
    events_raw = (trial / 'events.jsonl').read_bytes()
    require(hashlib.sha256(events_raw).hexdigest() == result.get('events_sha256'), 'event hash mismatch')
    events = [json.loads(line) for line in events_raw.splitlines() if line.strip()]
    parsed = observe.parse_events(events)
    for key, value in parsed.items():
        require(result.get(key) == value, 'recorded event metric mismatch: ' + key)
    if parsed['usage'] is not None:
        for key, value in parsed['usage'].items():
            require(type(value) is int and value >= 0, 'invalid token usage: ' + key)
        require(parsed['usage'].get('reasoning_output_tokens', 0) <= parsed['usage']['output_tokens'],
                'reasoning subset exceeds output')
    invocation = read_json(trial / 'invocation.json')
    require(invocation.get('harness_sha256') == sha(HERE.parent / 'exploration/observe_saved_callers.py'), 'invocation harness changed')
    require(invocation.get('answer_schema_sha256') == sha(HERE.parent / 'exploration/answer.schema.json'), 'invocation schema changed')
    for key, expected in (('model_requested', 'gpt-5.6-sol'), ('effort_requested', 'xhigh')):
        require(result.get(key) == expected and invocation.get(key) == expected, key + ' differs from protocol')
    require(invocation.get('timeout_seconds') == 1200, 'timeout differs from protocol')
    require(len((trial / 'prompt.txt').read_bytes()) == result.get('prompt_bytes') == invocation.get('prompt_bytes'), 'prompt size mismatch')
    require(result.get('evidence_mode') == 'saved_archive' and result.get('source_unchanged') is True, 'source/evidence condition failed')
    require(result.get('archive_preflight') == archive_gate == result.get('archive_postflight'), 'archive pre/postflight mismatch')
    completed = sum(event.get('type') == 'turn.completed' for event in events)
    allowed_items = {'command_execution', 'agent_message', 'reasoning', 'todo_list'}
    disallowed = [event.get('item', {}).get('type') for event in events if event.get('type') == 'item.completed'
                  and event.get('item', {}).get('type') not in allowed_items]
    terminal = (completed == 1 and result.get('return_code') == 0 and result.get('timed_out') is False
                and parsed['turn_failed'] is False and not parsed['runtime_warnings'] and not disallowed
                and not any(event.get('type') == 'error' for event in events) and parsed['usage'] is not None)
    answer_path = trial / 'answer.json'
    answer = read_json(answer_path) if answer_path.is_file() else {}
    require(answer == result.get('answer'), 'answer file differs from recorded answer')
    messages = [event['item'].get('text', '') for event in events if event.get('type') == 'item.completed'
                and event.get('item', {}).get('type') == 'agent_message']
    if terminal:
        require(messages and json.loads(messages[-1]) == answer, 'terminal answer differs from model event')
    findings = answer.get('findings', [])
    ids = [finding.get('id') for finding in findings if isinstance(finding, dict)]
    expected = [finding['id'] for finding in case['findings']]
    exact_ids = len(findings) == len(ids) == len(expected) and set(ids) == set(expected)
    citation = observe.grade(answer, case, observation / 'repository')
    require(citation == result.get('quality'), 'citation grade differs from recorded result')
    review_path = HERE / language / 'semantic' / (name + '.json')
    review = read_json(review_path) if review_path.is_file() else None
    semantic = semantic_gate(review, criteria, sha(answer_path) if answer_path.is_file() else '',
                             sha(HERE / language / 'SOURCE-REVIEW.md'))
    evidence = graph_evidence(events, observation, {finding['path'] for finding in case['findings']})
    return {'trial': name, 'verified': True, 'pending': semantic['pending'], 'terminal_passed': terminal,
            'completed_turns': completed, 'disallowed_item_types': disallowed,
            'citation_passed': exact_ids and citation['passed'], 'semantic_passed': semantic['passed'],
            'semantic': semantic, 'graph_evidence_used': any(row['useful_task_evidence'] for row in evidence),
            'batch_used': any(row['batch_used'] for row in evidence), 'graph_receipts': evidence,
            'usage': parsed['usage'], 'command_count': parsed['command_count'],
            'command_output_bytes': parsed['command_output_bytes'], 'failed_commands': parsed['failed_commands'],
            'result_sha256': sha(result_path), 'events_sha256': result['events_sha256'],
            'answer_sha256': sha(answer_path) if answer_path.is_file() else None,
            'semantic_review_sha256': sha(review_path) if review_path.is_file() else None,
            'raw_result': result}


def collect():
    hashes = frozen_inputs()
    spec = importlib.util.spec_from_file_location('multilang_frozen_observe', HERE.parent / 'exploration/observe_saved_callers.py')
    observe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(observe)
    trials, pairs, errors = {}, [], []
    for language in LANGUAGES:
        observation = OBSERVATIONS[language]
        try:
            frozen = read_json(HERE / language / 'freeze.json')
            for name in ('manifest', 'engine'):
                require(sha(observation / (name + '.json')) == frozen[name + '_sha256'], 'observation ' + name + ' changed')
            manifest, engine = read_json(observation / 'manifest.json'), read_json(observation / 'engine.json')
            require(observe.manifest(observation / 'repository') == manifest['source_manifest'], 'source manifest changed')
            require(observe.manifest(observation / 'runtime') == engine['files'], 'runtime manifest changed')
            require(sha(observation / 'cases.json') == sha(HERE / language / 'cases.json'), 'frozen catalog changed')
            catalog = observe.case_catalog(observation, manifest)
            require(len(catalog['cases']) == 1, 'expected exactly one task per language')
            case = catalog['cases'][0]
            expected_trials = {f"{case['id']}-{condition}-{repeat}" for condition in CONDITIONS for repeat in (1, 2)}
            actual_trials = {path.name for path in (observation / 'trials').glob('*') if path.is_dir()}
            require(actual_trials <= expected_trials, 'unexpected extra trial directories; selective retries are not allowed')
            criteria = read_json(HERE / language / 'criteria.json')
            require(set(criteria) == {finding['id'] for finding in case['findings']}, 'criteria IDs differ from case')
            require(all(isinstance(clauses, list) and clauses and all(isinstance(clause, str) and clause.strip()
                        for clause in clauses) for clauses in criteria.values()), 'criteria must contain nonempty clauses')
            archive = observe.archive_gate(observation, engine)
            require(archive.get('passed') is True, 'archive gate failed')
            for repeat in (1, 2):
                current = {}
                for condition in CONDITIONS:
                    try:
                        current[condition] = collect_trial(observe, observation, language, case, criteria, condition, repeat, archive)
                    except (OSError, ValueError, KeyError, TypeError) as error:
                        current[condition] = {'verified': False, 'pending': False, 'reason': str(error)}
                    trials[f'{language}/{condition}/{repeat}'] = current[condition]
                pairs.append({'language': language, 'repeat': repeat, **pair_gate(**current)})
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append({'language': language, 'reason': str(error)})
    return {'scope': 'Six predeclared pairs; every pair must preserve full quality and reduce total input and output.',
            'accepted': not errors and cohort_gate(pairs), 'input_hashes_sha256': sha(HERE / 'input-hashes.json'),
            'frozen_inputs_verified': len(hashes), 'errors': errors, 'pairs': pairs, 'trials': trials,
            'note': 'Missing terminal artifacts are not evidence of a stopped process. No models are run or retried.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = collect()
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {'accepted': False, 'errors': [{'reason': str(error)}], 'pairs': [], 'trials': {}}
    (HERE / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    lines = ['# Multilingual actual-token gate', '', 'Accepted: **' + str(result['accepted']).lower() + '**.', '',
             'This is the computed cohort gate, not release authorization or a universal savings claim.', '']
    for pair in result['pairs']:
        lines.append(f"- {pair['language']} repetition {pair['repeat']}: {'pass' if pair['accepted'] else 'fail'}; "
                     + ('all pair requirements passed' if pair['accepted'] else '; '.join(pair['reasons'])))
    for error in result['errors']:
        lines.append('- Verification error: ' + error.get('language', 'cohort') + ': ' + error['reason'])
    lines.extend(['', 'Raw results, usage subsets, clause reviews and graph evidence receipts are retained in results.json.',
                  'Missing terminal results do not establish that an experiment has stopped; this collector never launches or retries one.', ''])
    (HERE / 'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('accepted', 'errors', 'pairs')}))
    return 0 if result['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
