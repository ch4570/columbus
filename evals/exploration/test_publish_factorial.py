"""Public artifact checks use sealed synthetic captures, never a model runtime."""
import copy
from hashlib import sha256
import json
from pathlib import Path
import shlex
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

    def test_windows_path_suffixes_are_portable_without_rewriting_command_source(self):
        run = r'C:\Users\private-account\study'
        pilot = run + '-pilot'
        command = run + r'\runtime\columbus.py search "\d+\s" --repo ' + run + r'\repository'
        source = 'print("\\n")'
        payload = {
            'repository': run + r'\repository',
            'nested': [{'source': run + r'\source directory\file.py', 'pilot': pilot + r'\repository'}],
            'commands': [command, {'command': command + ' -c ' + source}],
            'prompt': 'Inspect ' + run + r'\repository with regex \w+',
            'answer': {'quote': run + r'\literal\n', 'explanation': source},
        }
        original = copy.deepcopy(payload)
        rendered = publisher._display_paths(payload, [(run, '$RUN'), (pilot, '$PILOT')])
        self.assertEqual(rendered['repository'], '$RUN/repository')
        self.assertEqual(rendered['nested'], [{'source': '$RUN/source directory/file.py',
                                              'pilot': '$PILOT/repository'}])
        expected_command = command.replace(run, '$RUN')
        self.assertEqual(rendered['commands'], [expected_command, {'command': expected_command + ' -c ' + source}])
        self.assertEqual(rendered['prompt'], r'Inspect $RUN\repository with regex \w+')
        self.assertEqual(rendered['answer'], {'quote': r'$RUN\literal\n', 'explanation': source})
        self.assertEqual(payload, original)

    def test_publisher_reads_utf8_explicitly_independent_of_platform_locale(self):
        pilot = self.pilot()
        write_json(self.output / 'observer-notes.json', {'note': '관찰된 호출만 합산 — 실패 포함'})
        read_text = Path.read_text

        def require_utf8(path, *args, **kwargs):
            self.assertEqual(kwargs.get('encoding'), 'utf-8', str(path))
            return read_text(path, *args, **kwargs)

        with patch.object(Path, 'read_text', require_utf8):
            publisher.publish(self.output, self.destination, pilot=pilot)
        published = json.loads(self.destination.read_text(encoding='utf-8'))
        self.assertEqual(published['observer_notes']['note'], '관찰된 호출만 합산 — 실패 포함')

    def test_restored_invocations_and_old_interpreters_use_captured_path_labels(self):
        for windows in (False, True):
            with self.subTest(windows=windows):
                separator = '\\' if windows else '/'
                account = r'C:\Users\private-account' if windows else '/Users/private-account'
                original = account + separator + 'original-study'
                interpreter = account + separator + ('old-env\\python.exe' if windows else 'old-env/bin/python3')
                record = self.report['attempts'][0]
                record['invocation'] = ['codex', 'exec', '--output-schema', original + separator + 'answer.schema.json',
                                        '-C', original + separator + 'trials' + separator + record['attempt_id'] + separator + 'scratch']
                command = f'"{interpreter}" -c \'print("\\\\n", "\\\\d+")\' {original}{separator}repository'
                record['commands'] = [command, {'command': command}]
                destination = self.destination.with_name(f'restored-{windows}.json')
                publisher.publish(self.output, destination)
                published = json.loads(destination.read_text(encoding='utf-8'))
                invocation = published['attempts'][0]['invocation']
                self.assertEqual(invocation[3], '$RUN/answer.schema.json')
                self.assertEqual(invocation[-1], '$RUN/trials/controlled-A/scratch')
                expected = command.replace(interpreter, '$PYTHON').replace(original, '$RUN')
                self.assertEqual(published['attempts'][0]['commands'], [expected, {'command': expected}])
                self.assertNotIn('private-account', destination.read_text(encoding='utf-8'))
                self.assertEqual(published['attempts'][0]['events_sha256'], record['events_sha256'])

    def test_restored_manifest_paths_and_pilot_origin_are_separately_redacted(self):
        pilot = self.pilot()
        original = '/Users/private-account/original-pilot'
        summary_path = pilot / 'summary.json'
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
        summary['manifest'].update(repository=original + '/repository', python='/Users/private-account/old-env/bin/python',
                                   checkout='/Users/private-account/old-checkout', engine={'python': '3.14.7'})
        summary['attempts'][0]['prompt'] = f'Inspect {original}/repository; preserve regex \\d+'
        directory = pilot / 'trials/pilot-0'
        write_json(directory / 'result.json', summary['attempts'][0])
        self.seal(directory)
        write_json(summary_path, summary)
        publisher.publish(self.output, self.destination, pilot=pilot)
        published = json.loads(self.destination.read_text(encoding='utf-8'))
        metadata = published['instrumentation_pilot']['manifest']
        self.assertEqual(metadata['repository'], '$PILOT/repository')
        self.assertEqual(metadata['python'], '$PYTHON')
        self.assertEqual(metadata['checkout'], '$CHECKOUT')
        self.assertEqual(metadata['engine']['python'], '3.14.7')
        self.assertEqual(published['instrumentation_pilot']['attempts'][0]['prompt'],
                         r'Inspect $PILOT/repository; preserve regex \d+')
        self.assertNotIn('private-account', self.destination.read_text(encoding='utf-8'))

    def test_each_recorded_invocation_location_recovers_the_original_run(self):
        original = '/Users/private-account/original-study'
        for number, (option, suffix) in enumerate([
                ('--output-schema', '/answer.schema.json'),
                ('--output-last-message', '/trials/controlled-A/answer.json'),
                ('-C', '/trials/controlled-A/scratch'),
                ('--add-dir', '/repository/.columbus/sessions')]):
            with self.subTest(option=option):
                self.report['attempts'][0]['invocation'] = ['codex', 'exec', option, original + suffix]
                destination = self.destination.with_name(f'option-{number}.json')
                publisher.publish(self.output, destination)
                published = json.loads(destination.read_text(encoding='utf-8'))
                self.assertEqual(published['attempts'][0]['invocation'][-1], '$RUN' + suffix)

    def test_old_interpreter_inside_shell_wrapper_preserves_command_quoting(self):
        interpreter = '/Users/private-account/old environment/bin/python3.14'
        script = shlex.quote(interpreter) + ' -c ' + shlex.quote('print("\\n", "\\d+")')
        command = '/bin/zsh -lc ' + shlex.quote(script)
        self.report['attempts'][0]['commands'] = [command]
        publisher.publish(self.output, self.destination)
        published = json.loads(self.destination.read_text(encoding='utf-8'))
        self.assertEqual(published['attempts'][0]['commands'], [command.replace(interpreter, '$PYTHON')])
        self.assertNotIn('private-account', self.destination.read_text(encoding='utf-8'))

    def test_old_interpreters_after_shell_operators_and_env_are_redacted(self):
        original = '/Users/private-account/original-study'
        interpreter = '/Users/private-account/old-env/bin/python3'
        execution = interpreter + ' -c ' + shlex.quote('print("\\n", "\\d+")')
        scripts = [f'cd {original}/repository && {execution}',
                   f'cd {original}/repository;{execution}',
                   f'printf text | {execution}',
                   f'false || {execution}',
                   f'LANG=C {execution}',
                   f'/usr/bin/env LANG=C {execution}',
                   f'env -i -u PYTHONPATH LANG=C {execution}']
        self.report['attempts'][0]['invocation'] = ['codex', 'exec', '--output-schema', original + '/answer.schema.json']
        commands = [command for script in scripts for command in (script, '/bin/zsh -lc ' + shlex.quote(script))]
        for number, command in enumerate(commands):
            with self.subTest(command=command):
                self.report['attempts'][0]['commands'] = [command]
                destination = self.destination.with_name(f'compound-{number}.json')
                publisher.publish(self.output, destination)
                published = json.loads(destination.read_text(encoding='utf-8'))
                self.assertEqual(published['attempts'][0]['commands'],
                                 [command.replace(interpreter, '$PYTHON').replace(original, '$RUN')])
                self.assertNotIn('private-account', destination.read_text(encoding='utf-8'))

    def test_python_source_and_quoted_shell_operators_are_not_executable_positions(self):
        source = 'print("; /example/not-an-executable/bin/python3 -c \\\"\\\\n\\\"")'
        commands = ['python3 -c ' + shlex.quote(source),
                    'printf %s ' + shlex.quote('&&') + ' /example/not-an-executable/bin/python3',
                    'printf %s ' + shlex.quote('env /example/not-an-executable/bin/python3')]
        self.report['attempts'][0]['commands'] = commands
        publisher.publish(self.output, self.destination)
        published = json.loads(self.destination.read_text(encoding='utf-8'))
        self.assertEqual(published['attempts'][0]['commands'], commands)

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

    def test_pilot_summary_inventory_cannot_omit_add_or_duplicate_attempts(self):
        pilot = self.pilot(count=2)
        path = pilot / 'summary.json'
        summary = json.loads(path.read_text(encoding='utf-8'))
        records = summary['attempts']
        for name, attempts in [('omitted', records[:1]), ('empty', []),
                               ('extra', records + [{**records[0], 'attempt_id': 'pilot-extra'}]),
                               ('duplicate', records + [records[0]])]:
            with self.subTest(name=name):
                write_json(path, {**summary, 'attempts': attempts})
                destination = self.destination.with_name(name + '.json')
                with self.assertRaisesRegex(ValueError, 'Pilot attempt inventory'):
                    publisher.publish(self.output, destination, pilot=pilot)
                self.assertFalse(destination.exists())

    def test_one_cohort_cannot_be_counted_again_as_its_own_pilot(self):
        cohort = self.pilot(count=2)
        self.report = json.loads((cohort / 'summary.json').read_text(encoding='utf-8'))
        for number, pilot in enumerate((cohort, cohort / '..' / cohort.name)):
            destination = self.destination.with_name(f'own-pilot-{number}.json')
            with self.subTest(pilot=pilot):
                with self.assertRaisesRegex(ValueError, 'distinct cohort'):
                    publisher.publish(cohort, destination, pilot=pilot)
                self.assertFalse(destination.exists())
        self.summarize.assert_not_called()

    def test_unfinished_pilot_start_cannot_disappear_from_stale_summary(self):
        pilot = self.pilot()
        directory = pilot / 'trials/pilot-unfinished'
        directory.mkdir()
        write_json(directory / 'attempt.json', {'attempt_id': 'pilot-unfinished', 'arm': 'D'})
        with self.assertRaisesRegex(ValueError, 'Pilot attempt inventory'):
            publisher.publish(self.output, self.destination, pilot=pilot)
        self.assertFalse(self.destination.exists())

    def test_sealed_pilot_started_identity_must_match_directory_and_result(self):
        pilot = self.pilot()
        directory = pilot / 'trials/pilot-0'
        for changes in ({'attempt_id': 'different-id'}, {'arm': 'D'}, {'invocation': ['different-command']}):
            with self.subTest(changes=changes):
                write_json(directory / 'attempt.json', {'attempt_id': 'pilot-0', 'arm': 'A', **changes})
                self.seal(directory)
                destination = self.destination.with_name(next(iter(changes)) + '.json')
                with self.assertRaisesRegex(ValueError, 'Pilot started attempt'):
                    publisher.publish(self.output, destination, pilot=pilot)
                self.assertFalse(destination.exists())

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
