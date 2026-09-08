"""Exercise predeclared relationship/quote controls without calling a model."""
from __future__ import annotations

import copy
import json
import shlex
import subprocess
import sys

from common import (HERE, LANGUAGES, CONDITIONS, OBSERVE, observation, read, require, save,
                    verify_observation)
from recognize import evidence


def invoke(output, arguments, identifier):
    command = [sys.executable, '-B', str(output / 'runtime/columbus.py'), *arguments,
               '--input', str(output / 'graph.jsonl.xz'), '--repo', '.']
    result = subprocess.run(command, cwd=output / 'repository', capture_output=True, text=True,
                            encoding='utf-8', timeout=120)
    event = {'type': 'item.completed', 'item': {'type': 'command_execution', 'id': identifier,
             'command': shlex.join(command), 'exit_code': result.returncode, 'status': 'completed',
             'aggregated_output': result.stdout}}
    return {'argv': command, 'stdout': result.stdout, 'stderr': result.stderr, 'return_code': result.returncode,
            'stdout_sha256': OBSERVE.sha(result.stdout.encode()), 'event': event}


def controls(language):
    require(not (HERE / language / 'controls.json').exists(), 'Controls already captured; do not overwrite')
    relationships = read(HERE / language / 'relationships.json')
    require(isinstance(relationships, list) and relationships, 'Reviewed relationships missing')
    before = {arm: verify_observation(language, arm) for arm in CONDITIONS}
    citation = read(HERE / language / 'citation-controls.json')
    case = read(HERE / language / 'cases.json')['cases'][0]
    output = observation(language, 'quotes')
    require(OBSERVE.grade(citation['answer'], case, output / 'repository') == citation['positive'],
            'Citation positive control differs')
    require(OBSERVE.grade(citation['negative_answer'], case, output / 'repository') == citation['negative'],
            'Citation negative control differs')
    require(citation['positive']['passed'] and not citation['negative']['passed'], 'Citation controls failed')
    results = []
    for condition in ('control', 'quotes'):
        output = observation(language, condition)
        for index, relationship in enumerate(relationships):
            for form in ('json', 'text'):
                result = invoke(output, ['archive-neighbors', relationship['source'], '--direction', 'out',
                    '--kinds', 'calls', '--context-lines', '2', '--limit', '50', '--budget-bytes', '64000', '--format', form],
                    f'{condition}-{index}-{form}')
                require(result['return_code'] == 0, 'Relationship control command failed')
                receipt = evidence([result['event']], output, [relationship])
                require(receipt['relationship_used'] is True and receipt['quotes_used'] is False,
                        'Reviewed relationship was not delivered')
                invalid = copy.deepcopy(relationship)
                invalid['line'] = relationship['line'] + 100000
                require(evidence([result['event']], output, [invalid])['relationship_used'] is False,
                        'Wrong relationship line was accepted')
                failed_event = copy.deepcopy(result['event'])
                failed_event['item']['exit_code'] = 1
                rejected = evidence([failed_event], output, [relationship])
                require(not rejected['relationship_used'] and not rejected['quotes_used'], 'Failed command accepted')
                results.append({'condition': condition, 'format': form, 'relationship_index': index,
                                **result, 'recognition': receipt})
    output = observation(language, 'quotes')
    arguments = ['archive-quotes', '--budget-bytes', '64000']
    for finding in citation['answer']['findings']:
        arguments.extend(['--range', finding['path'], str(finding['start_line']), str(finding['end_line'])])
    # Repeated marker lines may be shared by findings; quote command correctly rejects duplicate requests.
    ranges = [tuple(arguments[i + 1:i + 4]) for i, word in enumerate(arguments) if word == '--range']
    require(len(ranges) == len(set(ranges)), 'Control needs distinct representative quote requests')
    quote = invoke(output, arguments, 'quotes-positive')
    require(quote['return_code'] == 0, 'Quote control command failed')
    quote_receipt = evidence([quote['event']], output, relationships)
    require(quote_receipt['quotes_used'] is True and quote_receipt['relationship_used'] is False,
            'Quote adoption is absent or conflated with relationship utility')
    corrupted = copy.deepcopy(quote['event'])
    packet = json.loads(corrupted['item']['aggregated_output'])
    packet['quotes'][0]['quote'] += '__not_source__'
    corrupted['item']['aggregated_output'] = json.dumps(packet)
    rejected = evidence([corrupted], output, relationships)
    require(not rejected['quotes_used'] and not rejected['relationship_used'], 'Corrupt quote accepted')
    unavailable = invoke(observation(language, 'control'), arguments, 'control-no-quotes')
    require(unavailable['return_code'] != 0 and not unavailable['stdout'], 'Control unexpectedly provides quotes')
    after = {arm: verify_observation(language, arm) for arm in CONDITIONS}
    require(before == after, 'Inputs changed during controls')
    save(HERE / language / 'controls.json', {'passed': True, 'model_started': False,
         'preflight': before, 'postflight': after, 'relationships': results,
         'quotes': {**quote, 'recognition': quote_receipt}, 'control_quotes_unavailable': unavailable,
         'negative_wrong_relationship_line_rejected': True, 'negative_failed_command_rejected': True,
         'negative_corrupt_quote_rejected': True, 'quote_only_never_relationship_credit': True})


if __name__ == '__main__':
    for language in LANGUAGES:
        controls(language)
