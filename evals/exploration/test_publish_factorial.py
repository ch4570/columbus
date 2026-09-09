"""Public artifact checks use sealed synthetic captures, never a model runtime."""
import copy
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import publish_factorial as publisher


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')


class FactorialPublicationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='columbus-publication-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output = self.root / 'cohort'
        self.output.mkdir()
        self.destination = self.root / 'published' / 'report.json'
        checkout = Path(publisher.__file__).resolve().parents[2]
        self.report = {
            'manifest': {'python': sys.executable, 'resolved_python': str(Path(sys.executable).resolve()),
                         'repository': str(self.output / 'repository'), 'checkout': str(checkout)},
            'attempts': [self.record(f'controlled-{arm}', arm, self.output) for arm in 'ABCD'],
        }
        summarize = patch.object(publisher, 'summarize', side_effect=lambda output: copy.deepcopy(self.report))
        self.summarize = summarize.start()
        self.addCleanup(summarize.stop)
        process = patch('subprocess.Popen', side_effect=AssertionError('Publisher tests must not start a model'))
        process.start()
        self.addCleanup(process.stop)

    def record(self, identifier, arm, directory):
        return {'task_id': 'case-1', 'arm': arm, 'attempt_id': identifier, 'success': False,
                'provider': 'openai', 'model': 'frozen-model', 'elapsed_seconds': 1.25,
                'usage': {'input_tokens': 100, 'cached_input_tokens': 20, 'uncached_input_tokens': 80,
                          'cache_write_tokens': None, 'output_tokens': 10, 'reasoning_tokens': None},
                'usage_complete': True, 'quality': {'passed': False, 'reason': 'missing required finding'},
                'answer': {'findings': [{'id': 'finding', 'quote': 'return 1', 'explanation': 'Incomplete answer'}]},
                'commands': [{'command': f'{sys.executable} {directory}/runtime/columbus.py search needle',
                              'output_sha256': 'a' * 64}],
                'prompt': f'Read bounded source under {directory}/repository', 'events_sha256': 'b' * 64}

    def pilot(self, count=1):
        # The pilot shares the run's string prefix, exercising longest-first labels.
        pilot = self.root / 'cohort-pilot'
        repository = pilot / 'repository'
        repository.mkdir(parents=True)
        (repository / 'source.py').write_text('def needle(): return 1\n', encoding='utf-8')
        records = []
        for number in range(count):
            identifier = f'pilot-{number}'
            directory = pilot / 'trials' / identifier
            directory.mkdir(parents=True)
            record = self.record(identifier, 'AD'[number % 2], pilot)
            events = [
                {'type': 'turn.started'},
                {'type': 'item.completed', 'item': {'type': 'reasoning', 'id': 'private-reasoning',
                                                   'text': 'PRIVATE_REASONING_TRANSCRIPT_SENTINEL'}},
                {'type': 'item.completed', 'item': {'type': 'command_execution', 'id': 'command',
                                                   'command': record['commands'][0]['command'],
                                                   'exit_code': 0, 'aggregated_output': 'source.py\n'}},
                {'type': 'turn.completed', 'usage': {'input_tokens': 100, 'cached_input_tokens': 20,
                                                    'cache_write_input_tokens': 0, 'output_tokens': 10}},
            ]
            raw = ''.join(json.dumps(event, ensure_ascii=False) + '\n' for event in events).encode('utf-8')
            (directory / 'events.jsonl').write_bytes(raw)
            record['events_sha256'] = sha256(raw).hexdigest()
            write_json(directory / 'attempt.json', {'attempt_id': identifier, 'arm': record['arm']})
            write_json(directory / 'result.json', record)
            write_json(directory / 'answer.json', record['answer'])
            (directory / 'prompt.txt').write_text(record['prompt'], encoding='utf-8')
            (directory / 'stderr.log').write_text('PRIVATE_STDERR_SENTINEL', encoding='utf-8')
            self.seal(directory)
            records.append(record)
        write_json(pilot / 'summary.json', {'manifest': {'source_manifest': publisher.manifest(repository)},
                                           'attempts': records})
        return pilot

    @staticmethod
    def seal(directory):
        names = ('attempt.json', 'result.json', 'answer.json', 'events.jsonl', 'prompt.txt', 'stderr.log')
        write_json(directory / 'capture.json', {name: sha256((directory / name).read_bytes()).hexdigest()
                                                for name in names})

    def test_display_labels_remove_local_prefixes_and_keep_original_hashes(self):
        pilot = self.pilot()
        publisher.publish(self.output, self.destination, pilot=pilot)
        published = json.loads(self.destination.read_text(encoding='utf-8'))
        self.assertEqual(published['manifest'], {'python': '$PYTHON', 'resolved_python': '$PYTHON',
                                                 'repository': '$RUN/repository', 'checkout': '$CHECKOUT'})
        controlled = published['attempts'][0]
        self.assertEqual(controlled['commands'][0]['command'], '$PYTHON $RUN/runtime/columbus.py search needle')
        self.assertEqual(controlled['commands'][0]['output_sha256'], 'a' * 64)
        pilot_record = published['instrumentation_pilot']['attempts'][0]
        self.assertEqual(pilot_record['commands'][0]['command'], '$PYTHON $PILOT/runtime/columbus.py search needle')
        rendered = self.destination.read_text(encoding='utf-8')
        for local in (str(self.root), sys.executable, str(Path(publisher.__file__).resolve().parents[2])):
            self.assertNotIn(local, rendered)
        self.summarize.assert_called_once_with(self.output)

    def test_windows_style_interpreter_path_is_a_display_label_too(self):
        interpreter = r'C:\Users\private-account\runtime\python.exe'
        self.report['manifest'] = {'python': interpreter}
        self.report['attempts'] = []
        with patch.object(publisher.sys, 'executable', interpreter):
            publisher.publish(self.output, self.destination)
        self.assertEqual(json.loads(self.destination.read_text())['manifest']['python'], '$PYTHON')

    def test_existing_destination_is_preserved_without_append_or_overwrite(self):
        self.destination.parent.mkdir()
        before = b'previous reviewed artifact\n'
        self.destination.write_bytes(before)
        with self.assertRaises(FileExistsError):
            publisher.publish(self.output, self.destination)
        self.assertEqual(self.destination.read_bytes(), before)

    def test_unused_index_cannot_claim_payback_from_unattributed_wall_time(self):
        self.report['elapsed_amortization'] = {
            'A-C': {'reuse_count_for_elapsed_break_even': 1, 'note': 'raw exploratory formula'},
            'B-D': {'reuse_count_for_elapsed_break_even': 2, 'note': 'raw exploratory formula'}}
        for record in self.report['attempts']:
            record['columbus_commands'] = 1 if record['arm'] == 'D' else 0
        publisher.publish(self.output, self.destination)
        amortization = json.loads(self.destination.read_text())['elapsed_amortization']
        self.assertIsNone(amortization['A-C']['reuse_count_for_elapsed_break_even'])
        self.assertEqual(amortization['A-C']['unattributed_formula_reuse_count'], 1)
        self.assertIn('No Columbus command', amortization['A-C']['note'])
        self.assertEqual(amortization['B-D']['reuse_count_for_elapsed_break_even'], 2)

    def test_all_failed_controlled_and_pilot_attempts_remain_separate_and_complete(self):
        pilot = self.pilot(count=2)
        result = publisher.publish(self.output, self.destination, pilot=pilot)
        published = json.loads(self.destination.read_text())
        self.assertEqual((result['attempts'], result['pilot_attempts']), (4, 2))
        self.assertEqual([row['attempt_id'] for row in published['attempts']],
                         [f'controlled-{arm}' for arm in 'ABCD'])
        self.assertTrue(all(row['success'] is False for row in published['attempts']))
        pilot_report = published['instrumentation_pilot']
        self.assertEqual([row['attempt_id'] for row in pilot_report['attempts']], ['pilot-0', 'pilot-1'])
        for row in pilot_report['attempts']:
            self.assertFalse(row['success'])
            self.assertIsNone(row['usage']['cache_write_tokens'])
            self.assertEqual(row['usage_with_current_aliases']['cache_write_tokens'], 0)
        self.assertEqual(sum(arm['attempts'] for arm in pilot_report['totals']['arms'].values()), 2)
        self.assertTrue(all(arm['successful_tasks'] == 0 and arm['cost_per_successful_task'] is None
                            for arm in pilot_report['totals']['arms'].values()))
        all_calls = published['all_observed_model_calls']
        self.assertEqual((all_calls['attempts'], all_calls['unknown_usage_attempts']), (6, 0))
        self.assertEqual(all_calls['known_reported_usage'],
                         {'input_tokens': 600, 'cached_input_tokens': 120, 'output_tokens': 60})

    def test_unknown_usage_remains_counted_and_partial_totals_are_labelled(self):
        self.report['attempts'][0].update(usage=None, usage_complete=False)
        publisher.publish(self.output, self.destination)
        published = json.loads(self.destination.read_text())
        self.assertEqual(len(published['attempts']), 4)
        self.assertIsNone(published['attempts'][0]['usage'])
        calls = published['all_observed_model_calls']
        self.assertEqual((calls['attempts'], calls['unknown_usage_attempts']), (4, 1))
        self.assertEqual(calls['known_reported_usage']['input_tokens'], 300)
        self.assertIn('partial sums', calls['note'])

    def test_raw_reasoning_and_stderr_stay_private_while_commands_and_answers_remain(self):
        pilot = self.pilot()
        publisher.publish(self.output, self.destination, pilot=pilot)
        raw = self.destination.read_text()
        self.assertNotIn('PRIVATE_REASONING_TRANSCRIPT_SENTINEL', raw)
        self.assertNotIn('PRIVATE_STDERR_SENTINEL', raw)
        self.assertIn('Incomplete answer', raw)
        self.assertIn('columbus.py search needle', raw)
        self.assertEqual({path.name for path in self.destination.parent.iterdir()}, {'report.json'})
        self.assertIn('PRIVATE_REASONING_TRANSCRIPT_SENTINEL',
                      (pilot / 'trials/pilot-0/events.jsonl').read_text())

    def test_every_sealed_capture_file_is_checked_before_creating_public_output(self):
        pilot = self.pilot()
        directory = pilot / 'trials/pilot-0'
        for name in ('attempt.json', 'result.json', 'answer.json', 'events.jsonl', 'prompt.txt', 'stderr.log'):
            path = directory / name
            before = path.read_bytes()
            path.write_bytes(before + b' changed')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Pilot captured evidence changed'):
                publisher.publish(self.output, self.destination, pilot=pilot)
            self.assertFalse(self.destination.exists())
            path.write_bytes(before)

    def test_pilot_source_and_capture_inventory_tampering_are_rejected(self):
        pilot = self.pilot()
        source = pilot / 'repository/source.py'
        before = source.read_bytes()
        source.write_bytes(before + b'# changed\n')
        with self.assertRaisesRegex(ValueError, 'Pilot source snapshot changed'):
            publisher.publish(self.output, self.destination, pilot=pilot)
        source.write_bytes(before)
        capture = pilot / 'trials/pilot-0/capture.json'
        sealed = json.loads(capture.read_text())
        sealed['../outside.txt'] = 'a' * 64
        write_json(capture, sealed)
        with self.assertRaisesRegex(ValueError, 'Invalid pilot capture inventory'):
            publisher.publish(self.output, self.destination, pilot=pilot)
        self.assertFalse(self.destination.exists())

    def test_pilot_summary_cannot_change_captured_usage(self):
        pilot = self.pilot()
        path = pilot / 'summary.json'
        summary = json.loads(path.read_text())
        summary['attempts'][0]['usage']['input_tokens'] += 1
        write_json(path, summary)
        with self.assertRaisesRegex(ValueError, 'Pilot derived measurements differ'):
            publisher.publish(self.output, self.destination, pilot=pilot)
        self.assertFalse(self.destination.exists())

    def test_resealed_derived_usage_still_must_agree_with_raw_event_tokens(self):
        pilot = self.pilot()
        directory = pilot / 'trials/pilot-0'
        captured = json.loads((directory / 'result.json').read_text())
        captured['usage']['input_tokens'] += 1
        captured['usage']['uncached_input_tokens'] += 1
        write_json(directory / 'result.json', captured)
        self.seal(directory)
        summary = json.loads((pilot / 'summary.json').read_text())
        summary['attempts'][0] = captured
        write_json(pilot / 'summary.json', summary)
        with self.assertRaisesRegex(ValueError, 'Pilot token counts disagree with raw events'):
            publisher.publish(self.output, self.destination, pilot=pilot)
        self.assertFalse(self.destination.exists())

    def test_resealed_event_hash_claim_and_unreviewed_success_are_rejected(self):
        pilot = self.pilot()
        directory = pilot / 'trials/pilot-0'
        captured = json.loads((directory / 'result.json').read_text())
        captured['events_sha256'] = 'c' * 64
        write_json(directory / 'result.json', captured)
        self.seal(directory)
        summary = json.loads((pilot / 'summary.json').read_text())
        summary['attempts'][0] = captured
        write_json(pilot / 'summary.json', summary)
        with self.assertRaisesRegex(ValueError, 'Pilot raw event evidence changed'):
            publisher.publish(self.output, self.destination, pilot=pilot)
        captured['events_sha256'] = sha256((directory / 'events.jsonl').read_bytes()).hexdigest()
        write_json(directory / 'result.json', captured)
        self.seal(directory)
        summary['attempts'][0] = {**captured, 'success': True}
        write_json(pilot / 'summary.json', summary)
        with self.assertRaisesRegex(ValueError, 'Pilot success lacks its answer-bound review'):
            publisher.publish(self.output, self.destination, pilot=pilot)
        self.assertFalse(self.destination.exists())


if __name__ == '__main__':
    unittest.main()
