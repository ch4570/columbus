"""Read-only verification of all 18 frozen executions; never launch or retry models."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime
import json
import math
from pathlib import Path
import shlex
import sys

import common


HERE = common.HERE
LANGUAGES = common.LANGUAGES
CONDITIONS = common.CONDITIONS
LEGACY = common.LEGACY
OBSERVE = common.OBSERVE
read, require, sha = common.read, common.require, common.sha


def stamp(value):
    require(isinstance(value, str), 'Missing timestamp')
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None, 'Timestamp lacks timezone')
    return result


def valid_usage(value):
    if not isinstance(value, dict) or not {'input_tokens', 'cached_input_tokens', 'output_tokens'} <= set(value):
        return False
    if any(type(number) is not int or number < 0 for number in value.values()):
        return False
    return (value['cached_input_tokens'] <= value['input_tokens']
            and value.get('reasoning_output_tokens', 0) <= value['output_tokens']
            and value.get('uncached_input_tokens', value['input_tokens'] - value['cached_input_tokens'])
            == value['input_tokens'] - value['cached_input_tokens'])


def run_quality(trial, relationship=False):
    flags = ('verified', 'terminal_passed', 'citation_passed', 'semantic_passed')
    reasons = [flag for flag in flags if trial.get(flag) is not True]
    if not valid_usage(trial.get('usage')):
        reasons.append('actual usage missing or invalid')
    if relationship and trial.get('relationship_used') is not True:
        reasons.append('reviewed graph relationship absent')
    return reasons


def pair_gate(left, quotes, left_arm='baseline'):
    require(left_arm in ('baseline', 'control'), 'Unknown pair comparator')
    reasons = [left_arm + ': ' + reason for reason in run_quality(left, left_arm == 'control')]
    reasons += ['quotes: ' + reason for reason in run_quality(quotes, True)]
    deltas = {}
    for key in ('input_tokens', 'output_tokens'):
        if valid_usage(left.get('usage')) and valid_usage(quotes.get('usage')):
            deltas[key] = quotes['usage'][key] - left['usage'][key]
            if deltas[key] >= 0:
                reasons.append(key + ': quotes must be strictly lower')
        else:
            deltas[key] = None
    return {'accepted': not reasons, 'reasons': reasons, 'quotes_minus_' + left_arm: deltas}


def six_pairs(pairs):
    actual = [(item.get('language'), item.get('repeat')) for item in pairs]
    expected = {(language, repeat) for language in LANGUAGES for repeat in (1, 2)}
    return (len(actual) == len(expected) and all(type(repeat) is int for _, repeat in actual)
            and set(actual) == expected and all(item.get('accepted') is True for item in pairs))


def process_record(directory):
    process = read(directory / 'process.json')
    require(type(process.get('pid')) is int and process['pid'] > 0, 'Invalid process identity')
    start = stamp(process.get('started_at'))
    terminal = read(directory / 'terminal.json') if (directory / 'terminal.json').is_file() else None
    if terminal is not None:
        require(type(terminal.get('return_code')) is int and type(terminal.get('timed_out')) is bool,
                'Invalid terminal process status')
        elapsed = terminal.get('elapsed_seconds')
        require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0, 'Invalid elapsed time')
        require(start <= stamp(terminal.get('finished_at')), 'Process finished before it started')
    return start, terminal


def verify_order(language, case):
    """Validate every observed slot; absence is incompleteness, never proof of a stopped process."""
    scheduled = common.schedule(language)
    group = common.observation(language, 'baseline').parent
    runner_path = group / 'runner.json'
    started = None
    if runner_path.is_file():
        runner = read(runner_path)
        require(type(runner.get('pid')) is int and runner['pid'] > 0, 'Invalid runner identity')
        require(runner.get('schedule') == [list(row) for row in scheduled], 'Runner schedule differs')
        require(runner.get('input_hashes_sha256') == sha(HERE / 'input-hashes.json'), 'Runner frozen inventory differs')
        started = stamp(runner.get('started_at'))
    records, missing = [], []
    for arm in CONDITIONS:
        trials = common.observation(language, arm) / 'trials'
        expected = {f"{case['id']}-{arm}-{repeat}" for repeat in (1, 2)}
        for path in trials.iterdir() if trials.exists() else ():
            require(path.name in expected and path.is_dir() and not path.is_symlink(), 'Unexpected extra trial entry')
    for arm, repeat in scheduled:
        trial = common.observation(language, arm) / 'trials' / f"{case['id']}-{arm}-{repeat}"
        if not (trial / 'process.json').is_file():
            require(not (trial / 'result.json').exists() and not (trial / 'terminal.json').exists(),
                    'Terminal evidence lacks original process record')
            missing.append([arm, repeat])
            continue
        require(started is not None, 'Process exists without original runner record')
        start, terminal = process_record(trial)
        require(start >= started, 'Trial started before its runner')
        if records:
            previous_start, previous_terminal = records[-1]
            require(previous_start < start and previous_terminal is not None
                    and stamp(previous_terminal['finished_at']) <= start,
                    'Trial processes overlap or differ from frozen order')
        records.append((start, terminal))
    end_path = group / 'runner-terminal.json'
    complete = len(records) == 6 and all(terminal is not None for _, terminal in records)
    if end_path.is_file():
        end = read(end_path)
        require(complete and end.get('status') == 'all scheduled executions terminated', 'Premature runner completion')
        require(stamp(end.get('finished_at')) >= stamp(records[-1][1]['finished_at']), 'Runner finished before final trial')
    return {'passed': complete and end_path.is_file(), 'missing_process_slots': missing,
            'runner_terminal_present': end_path.is_file(),
            'note': 'An absent terminal record does not establish that a process stopped.'}


def verify_controls(language, case, preflight, recognizer):
    directory = HERE / language
    controls = read(directory / 'controls.json')
    require(controls.get('passed') is True and controls.get('model_started') is False,
            'Relationship/quote prelaunch controls did not pass')
    require(controls.get('preflight') == preflight == controls.get('postflight'), 'Control pre/postflight differs')
    citations = read(directory / 'citation-controls.json')
    for key, answer_key, passed in (('positive', 'answer', True), ('negative', 'negative_answer', False)):
        result = OBSERVE.grade(citations[answer_key], case, common.observation(language, 'quotes') / 'repository')
        require(result == citations[key] and result.get('passed') is passed, 'Citation control does not reproduce')
        expected = {finding['id'] for finding in case['findings']}
        rows = result['findings']
        require(len(rows) == len(expected) and {row['id'] for row in rows} == expected
                and all(row.get('passed') is passed for row in rows), 'Incomplete citation control')
    relationships = read(directory / 'relationships.json')
    require(isinstance(relationships, list) and relationships, 'No reviewed relationships')

    def captured(row, arm, arguments, identifier):
        output = common.observation(language, arm)
        argv = [sys.executable, '-B', str(output / 'runtime/columbus.py'), *arguments,
                '--input', str(output / 'graph.jsonl.xz'), '--repo', '.']
        require(row.get('argv') == argv and isinstance(row.get('stdout'), str)
                and isinstance(row.get('stderr'), str) and type(row.get('return_code')) is int,
                'Control command differs')
        event = {'type': 'item.completed', 'item': {'type': 'command_execution', 'id': identifier,
                 'command': shlex.join(argv), 'exit_code': row['return_code'], 'status': 'completed',
                 'aggregated_output': row['stdout']}}
        require(row.get('event') == event and row.get('stdout_sha256') == OBSERVE.sha(row['stdout'].encode()),
                'Control event/output hash differs')
        return event

    seen = []
    for row in controls['relationships']:
        arm, form, index = row['condition'], row['format'], row['relationship_index']
        require(arm in ('control', 'quotes') and form in ('json', 'text')
                and type(index) is int and 0 <= index < len(relationships), 'Unknown relationship control slot')
        seen.append((arm, form, index))
        relationship = relationships[index]
        arguments = ['archive-neighbors', relationship['source'], '--direction', 'out', '--kinds', 'calls',
                     '--context-lines', '2', '--limit', '50', '--budget-bytes', '64000', '--format', form]
        event = captured(row, arm, arguments, f'{arm}-{index}-{form}')
        output = common.observation(language, arm)
        receipt = recognizer.evidence([event], output, [relationship])
        require(row['return_code'] == 0 and receipt == row['recognition']
                and receipt['relationship_used'] is True and receipt['quotes_used'] is False,
                'Relationship positive control no longer reproduces')
        invalid = {**relationship, 'line': relationship['line'] + 100000}
        require(recognizer.evidence([event], output, [invalid])['relationship_used'] is False,
                'Invalid relationship control accepted')
        failed = copy.deepcopy(event)
        failed['item']['exit_code'] = 1
        rejected = recognizer.evidence([failed], output, [relationship])
        require(not rejected['relationship_used'] and not rejected['quotes_used'], 'Failed command control accepted')
    slots = {(arm, form, index) for arm in ('control', 'quotes') for form in ('json', 'text')
             for index in range(len(relationships))}
    require(len(seen) == len(slots) and set(seen) == slots, 'Missing or duplicate relationship control')
    arguments = ['archive-quotes', '--budget-bytes', '64000']
    for finding in citations['answer']['findings']:
        arguments.extend(['--range', finding['path'], str(finding['start_line']), str(finding['end_line'])])
    quote = controls['quotes']
    event = captured(quote, 'quotes', arguments, 'quotes-positive')
    output = common.observation(language, 'quotes')
    receipt = recognizer.evidence([event], output, relationships)
    require(quote['return_code'] == 0 and receipt == quote['recognition'] and receipt['quotes_used'] is True
            and receipt['relationship_used'] is False, 'Quote positive control no longer reproduces')
    corrupt = copy.deepcopy(event)
    packet = json.loads(corrupt['item']['aggregated_output'])
    packet['quotes'][0]['quote'] += '__not_source__'
    corrupt['item']['aggregated_output'] = json.dumps(packet)
    rejected = recognizer.evidence([corrupt], output, relationships)
    require(not rejected['quotes_used'] and not rejected['relationship_used'], 'Corrupt quote control accepted')
    unavailable = controls['control_quotes_unavailable']
    captured(unavailable, 'control', arguments, 'control-no-quotes')
    require(unavailable['return_code'] != 0 and not unavailable['stdout'], 'Control unexpectedly supports quotes')
    require(all(controls.get(name) is True for name in ('negative_wrong_relationship_line_rejected',
                'negative_failed_command_rejected', 'negative_corrupt_quote_rejected', 'quote_only_never_relationship_credit')),
            'Incomplete negative controls')


def collect_trial(language, case, criteria, arm, repeat, preflight, recognizer):
    output = common.observation(language, arm)
    name = f"{case['id']}-{arm}-{repeat}"
    directory = output / 'trials' / name
    hashes = {path.name: sha(path) for path in directory.iterdir() if path.is_file()} if directory.is_dir() else {}
    summary = {'trial': name, 'language': language, 'condition': arm, 'repeat': repeat, 'artifact_sha256': hashes,
               'verified': False, 'pending': not (directory / 'terminal.json').is_file(),
               'terminal_evidence_present': (directory / 'terminal.json').is_file()}
    try:
        require(all(not path.is_symlink() and path.is_file() for path in directory.iterdir()), 'Unexpected trial artifact type')
        allowed = {'prompt.txt', 'invocation.json', 'process.json', 'terminal.json', 'events.jsonl',
                   'stderr.log', 'answer.json', 'result.json'}
        require(set(hashes) <= allowed, 'Unexpected trial artifact; retain and investigate')
        require('result.json' in hashes, 'Terminal result missing; inspect original process/terminal evidence, never retry')
        require({'prompt.txt', 'invocation.json', 'process.json', 'terminal.json', 'events.jsonl', 'stderr.log'} <= set(hashes),
                'Required raw trial artifact missing')
        start, terminal = process_record(directory)
        result = read(directory / 'result.json')
        require((result.get('case'), result.get('condition'), result.get('repeat')) == (case['id'], arm, repeat), 'Trial identity differs')
        require(all(result.get(key) == value for key, value in terminal.items()), 'Terminal/result process fields differ')
        require(result.get('events_sha256') == hashes['events.jsonl'], 'Raw events hash differs')
        events = [json.loads(line) for line in (directory / 'events.jsonl').read_bytes().splitlines() if line.strip()]
        require(all(isinstance(event, dict) for event in events), 'Malformed event record')
        completions = [event for event in events if event.get('type') == 'turn.completed']
        require(all(valid_usage(event.get('usage')) for event in completions), 'Invalid raw completed-turn usage')
        parsed = OBSERVE.parse_events(events)
        require(all(result.get(key) == value for key, value in parsed.items()), 'Recorded event metrics differ')
        invocation = read(directory / 'invocation.json')
        required = {'argv': common.argv(output, directory), 'model_requested': 'gpt-5.6-sol',
                    'effort_requested': 'xhigh', 'timeout_seconds': 1200,
                    'harness_sha256': sha(HERE / 'run.py'), 'common_sha256': sha(HERE / 'common.py'),
                    'input_hashes_sha256': sha(HERE / 'input-hashes.json')}
        require(all(invocation.get(key) == value for key, value in required.items()), 'Invocation differs from frozen protocol')
        raw_prompt = (directory / 'prompt.txt').read_bytes()
        require(raw_prompt == common.prompt(case, arm, output).encode('utf-8')
                and invocation.get('prompt_bytes') == len(raw_prompt), 'Frozen prompt differs')
        require(result.get('preflight') == preflight == result.get('postflight'), 'All-arm source/runtime/archive checks differ')
        allowed_items = {'command_execution', 'agent_message', 'reasoning', 'todo_list'}
        items = [event.get('item') for event in events if event.get('type') in ('item.started', 'item.updated', 'item.completed')]
        require(all(isinstance(item, dict) for item in items), 'Malformed event item')
        disallowed = sorted({str(item.get('type')) for item in items if item.get('type') not in allowed_items})
        terminal_passed = (len(completions) == 1 and terminal['return_code'] == 0 and terminal['timed_out'] is False
                           and parsed['turn_failed'] is False and not parsed['runtime_warnings'] and not disallowed
                           and not any(event.get('type') == 'error' for event in events) and valid_usage(parsed['usage']))
        answer = read(directory / 'answer.json') if 'answer.json' in hashes else {}
        require(answer == result.get('answer'), 'Raw answer differs from recorded result')
        messages = [event['item'].get('text', '') for event in events if event.get('type') == 'item.completed'
                    and event.get('item', {}).get('type') == 'agent_message']
        if terminal_passed:
            require(messages and json.loads(messages[-1]) == answer, 'Answer differs from final model message')
        schema = LEGACY.answer_schema_valid(answer)
        ids = [finding['id'] for finding in answer['findings']] if schema else []
        expected = {finding['id'] for finding in case['findings']}
        exact_ids = len(ids) == len(expected) and set(ids) == expected
        citation = OBSERVE.grade(answer, case, output / 'repository')
        require(citation == result.get('quality'), 'Recorded citation grade differs')
        review_path = HERE / language / 'semantic' / (name + '.json')
        review = read(review_path) if review_path.is_file() else None
        semantic = LEGACY.semantic_gate(review, criteria, hashes.get('answer.json', ''), sha(HERE / language / 'SOURCE-REVIEW.md'))
        execution = LEGACY.execution_gate(review.get('execution_review') if isinstance(review, dict) else None, hashes['events.jsonl'])
        evidence = recognizer.evidence(events, output, read(HERE / language / 'relationships.json'))
        summary.update({'verified': True, 'pending': semantic['pending'] or execution['pending'],
                        'terminal_passed': terminal_passed and execution['passed'], 'execution_review': execution,
                        'completed_turns': len(completions), 'disallowed_item_types': disallowed,
                        'citation_passed': schema and exact_ids and citation['passed'], 'semantic_passed': semantic['passed'],
                        'semantic': semantic, **evidence, 'usage': parsed['usage'], 'command_count': parsed['command_count'],
                        'command_output_bytes': parsed['command_output_bytes'], 'failed_commands': parsed['failed_commands'],
                        'started_at': start.isoformat(), 'terminal': terminal,
                        'semantic_review_sha256': sha(review_path) if review_path.is_file() else None})
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        summary['reason'] = str(error)
    return summary


def collect():
    frozen = common.frozen_inputs()
    recognizer = common.module('quotes_collector_recognizer', HERE / 'recognize.py')
    trials, errors, orders = {}, [], {}
    for language in LANGUAGES:
        try:
            catalog = read(HERE / language / 'cases.json')
            require(len(catalog['cases']) == 1, 'Expected exactly one task per language')
            case = catalog['cases'][0]
            criteria = read(HERE / language / 'criteria.json')
            require(set(criteria) == {finding['id'] for finding in case['findings']}, 'Criteria IDs differ from task')
            require(all(isinstance(clauses, list) and clauses and all(isinstance(clause, str) and clause.strip()
                        for clause in clauses) for clauses in criteria.values()), 'Empty or malformed semantic clauses')
            preflight = {arm: common.verify_observation(language, arm) for arm in CONDITIONS}
            require(all(value.get('passed') is True for value in preflight.values()), 'Source/runtime/archive check failed')
            verify_controls(language, case, preflight, recognizer)
            try:
                orders[language] = verify_order(language, case)
            except (OSError, ValueError, KeyError, TypeError) as error:
                orders[language] = {'passed': False, 'reason': str(error)}
                errors.append({'language': language, 'reason': str(error)})
            for arm in CONDITIONS:
                for repeat in (1, 2):
                    trials[f'{language}/{arm}/{repeat}'] = collect_trial(language, case, criteria, arm, repeat, preflight, recognizer)
            require(preflight == {arm: common.verify_observation(language, arm) for arm in CONDITIONS}, 'Inputs changed during collection')
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            errors.append({'language': language, 'reason': str(error)})
            for arm in CONDITIONS:
                for repeat in (1, 2):
                    trials.setdefault(f'{language}/{arm}/{repeat}', {'verified': False, 'pending': False, 'reason': str(error)})
    common.frozen_inputs()
    primary, secondary = [], []
    for language in LANGUAGES:
        for repeat in (1, 2):
            quotes = trials[f'{language}/quotes/{repeat}']
            for arm, destination in (('baseline', primary), ('control', secondary)):
                destination.append({'language': language, 'repeat': repeat,
                                    **pair_gate(trials[f'{language}/{arm}/{repeat}'], quotes, arm)})
    all_quality = all(not run_quality(trials[f'{language}/{arm}/{repeat}'], arm != 'baseline')
                      for language in LANGUAGES for arm in CONDITIONS for repeat in (1, 2))
    accepted = not errors and six_pairs(primary)
    return {'schema': 'columbus.quotes-three-arm-results/v1', 'primary_accepted': accepted,
            'secondary_accepted': not errors and six_pairs(secondary),
            'experiment_accepted': accepted and all_quality and all(row['passed'] for row in orders.values())
                                   and len(orders) == len(LANGUAGES),
            'all_18_full_quality_and_utility': all_quality, 'errors': errors, 'orders': orders,
            'primary_pairs': primary, 'secondary_pairs': secondary, 'trials': trials,
            'input_hashes_sha256': sha(HERE / 'input-hashes.json'), 'frozen_inputs_verified': len(frozen),
            'note': 'All 18 scheduled executions are reported. Quote adoption is optional and not graph relationship evidence. '
                    'Serialized bytes are descriptive, not actual tokens. Missing artifacts never authorize retries or prove termination.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Optional NEW directory for results.json; default is stdout only')
    args = parser.parse_args()
    if args.output is not None:
        require(not args.output.exists(), 'Output directory already exists; no evidence is overwritten')
    try:
        result = collect()
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        failed_pairs = [{'language': language, 'repeat': repeat, 'accepted': False,
                         'reasons': ['Frozen cohort verification failed: ' + str(error)]}
                        for language in LANGUAGES for repeat in (1, 2)]
        result = {'primary_accepted': False, 'secondary_accepted': False, 'experiment_accepted': False,
                  'errors': [{'reason': str(error)}], 'primary_pairs': failed_pairs, 'secondary_pairs': failed_pairs,
                  'trials': {f'{language}/{arm}/{repeat}': {'verified': False, 'pending': True,
                             'reason': 'Not verified because frozen cohort validation failed; no process status inferred.'}
                             for language in LANGUAGES for arm in CONDITIONS for repeat in (1, 2)}}
    if args.output is not None:
        args.output.mkdir(parents=True, exist_ok=False)
        common.save(args.output / 'results.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['experiment_accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
