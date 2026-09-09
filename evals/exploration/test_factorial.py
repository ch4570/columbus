"""Protocol controls without authenticated model calls."""
import json
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import factorial
from factorial_cases import cases
from observe import dump, manifest, sha


class FactorialProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        version = patch.object(factorial, 'codex_version', return_value='fixture-codex')
        version.start()
        self.addCleanup(version.stop)

    def frozen(self):
        (self.root / 'protocol').mkdir()
        for name in factorial.protocol_files():
            shutil.copyfile(factorial.HERE / name, self.root / 'protocol' / name)
        repository = self.root / 'repository'
        repository.mkdir()
        (repository / 'source.py').write_text('def f(): return 1\n')
        (repository / '.columbus').mkdir()
        (repository / '.columbus/index-v1.sqlite').write_bytes(b'frozen test index')
        runtime = self.root / 'runtime'
        runtime.mkdir()
        (runtime / 'columbus.py').write_text('# frozen stub\n')
        dump(self.root / 'cases.json', cases())
        dump(self.root / 'answer.schema.json', factorial.ANSWER_SCHEMA)
        expected = {'protocol': factorial.protocol_files(), 'source_manifest': manifest(repository),
                    'catalog_sha256': sha((self.root / 'cases.json').read_bytes()),
                    'answer_schema_sha256': sha((self.root / 'answer.schema.json').read_bytes()),
                    'engine': {'files': manifest(runtime), 'index_seconds': 1.0},
                    'model': 'explicit-test-model', 'effort': 'high', 'timeout_seconds': 10,
                    'codex_version': 'fixture-codex', 'index_sha256': factorial.index_digest(self.root),
                    'schedule': factorial.schedule(cases(), 2)}
        dump(self.root / 'manifest.json', expected)
        return expected

    def test_four_arms_share_goal_and_only_b_d_share_the_exact_optional_policy(self):
        case = cases()[0]
        prompts = {arm: factorial.prompt_for(self.root, case, arm, 'new-session') for arm in factorial.ARMS}
        for arm, prompt in prompts.items():
            self.assertIn(case['question'], prompt)
            self.assertIn('Efficient rg and bounded source reads', prompt)
            self.assertIn('Do not edit source', prompt)
            self.assertEqual(factorial.WORKFLOW in prompt, arm in ('B', 'D'))
            self.assertEqual('Columbus is also available; using it is optional.' in prompt, arm in ('C', 'D'))
            self.assertNotIn('Start by narrowing', prompt)
            self.assertNotIn('oracle', prompt)
        self.assertEqual(prompts['B'].removesuffix(factorial.WORKFLOW), prompts['A'])
        self.assertEqual(prompts['D'].removesuffix(factorial.WORKFLOW), prompts['C'])

    def test_schedule_has_two_repeats_all_arms_and_changes_order(self):
        result = factorial.schedule(cases(), 2)
        self.assertEqual(len(result), 24)
        self.assertEqual([r['slot'] for r in result], list(range(24)))
        grouped = {}
        for row in result:
            grouped.setdefault(row['task_id'], []).append(row['arm'])
        self.assertTrue(all(set(arms) == set('ABCD') and len(arms) == 4 for arms in grouped.values()))
        first = cases()[0]['id']
        self.assertNotEqual(grouped[first + '-1'], grouped[first + '-2'])

    def test_prepared_manifest_distinguishes_index_availability_from_actual_adoption(self):
        output = self.root / 'fresh-cohort'
        prepared = factorial.prepare(output, model='fixture-model', effort='high', repeats=2, timeout=10)
        self.assertIn('C/D', prepared['index_policy'])
        self.assertIn('optional', prepared['index_policy'])
        self.assertIn('A/B', prepared['index_policy'])
        self.assertIn('observed, not assumed', prepared['index_policy'])

    def test_preflight_detects_source_engine_catalog_schema_and_protocol_changes(self):
        self.frozen()
        self.assertTrue(factorial.preflight(self.root))
        for relative in ('repository/source.py', 'runtime/columbus.py', 'cases.json', 'answer.schema.json',
                         'repository/.columbus/index-v1.sqlite'):
            path = self.root / relative
            before = path.read_bytes()
            path.write_bytes(before + b' ')
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                factorial.preflight(self.root)

    def test_runtime_update_and_pending_index_writes_prevent_next_model_call(self):
        self.frozen()
        with patch.object(factorial, 'codex_version', return_value='changed-codex'):
            with self.assertRaisesRegex(ValueError, 'Codex version changed'):
                factorial.preflight(self.root, check_runtime=True)
        (self.root / 'repository/.columbus/index-v1.sqlite-wal').write_bytes(b'pending writes')
        with self.assertRaisesRegex(ValueError, 'uncheckpointed'):
            factorial.preflight(self.root)
            path.write_bytes(before)
        with patch.object(factorial, 'protocol_files', return_value={}):
            with self.assertRaisesRegex(ValueError, 'protocol changed'):
                factorial.preflight(self.root)

    def test_preparation_never_overwrites_and_requires_repetition(self):
        with patch.object(subprocess, 'run', side_effect=AssertionError('must not launch')):
            with self.assertRaises(ValueError):
                factorial.prepare(self.root, model='m', effort='high', repeats=2, timeout=10)
            with self.assertRaises(ValueError):
                factorial.prepare(self.root / 'new', model='m', effort='high', repeats=1, timeout=10)

    def test_malformed_event_tail_is_retained_as_unknown_not_dropped(self):
        path = self.root / 'events.jsonl'
        path.write_text('{"type":"turn.started"}\n{bad\n[]\n{"incomplete":', encoding='utf-8')
        events, malformed = factorial.read_events(path)
        self.assertEqual(events, [{'type': 'turn.started'}])
        self.assertEqual(malformed, 3)

    def test_failed_launch_is_recorded_and_not_overwritten(self):
        self.frozen()
        with patch.object(subprocess, 'Popen', side_effect=OSError('fixture unavailable')):
            result = factorial.run_slot(self.root, 0)
        self.assertFalse(result['success'])
        self.assertFalse(result['usage_complete'])
        self.assertIn('unavailable', result['launch_error'])
        directory = self.root / 'trials' / result['attempt_id']
        self.assertTrue((directory / 'attempt.json').is_file())
        self.assertTrue((directory / 'result.json').is_file())
        with self.assertRaisesRegex(ValueError, 'Attempt already exists'):
            factorial.run_slot(self.root, 0)
        with patch.object(subprocess, 'Popen', side_effect=OSError('retry unavailable')):
            second = factorial.run_slot(self.root, 0, attempt=2)
        self.assertNotEqual(result['attempt_id'], second['attempt_id'])

    def test_prompt_file_and_stdin_keep_identical_utf8_lf_bytes_on_windows(self):
        self.frozen()
        write_text = Path.write_text

        def windows_write(path, data, *arguments, **options):
            if options.get('newline') != '\n':
                data = data.replace('\n', '\r\n')
            options['newline'] = '\n'
            return write_text(path, data, *arguments, **options)

        with patch.object(Path, 'write_text', windows_write), patch.object(subprocess, 'Popen') as launch:
            launch.return_value.returncode = 0
            result = factorial.run_slot(self.root, 0)
        delivered = launch.return_value.communicate.call_args.args[0]
        self.assertIsInstance(delivered, bytes)
        self.assertNotIn(b'\r\n', delivered)
        saved = (self.root / 'trials' / result['attempt_id'] / 'prompt.txt').read_bytes()
        self.assertEqual(saved, delivered)
        self.assertEqual(sha(saved), result['prompt_sha256'])
        self.assertFalse(launch.call_args.kwargs.get('text', False))

    def test_incomplete_attempt_stays_in_all_attempt_cost_aggregation(self):
        expected = self.frozen()
        scheduled = expected['schedule'][0]
        dump(self.root / 'trials' / 'unfinished' / 'attempt.json', {
            **scheduled, 'attempt_id': 'unfinished', 'model': 'explicit-test-model', 'effort': 'high', 'usage_scope': 'self_only'})
        summary = factorial.summarize(self.root)
        self.assertEqual(len(summary['attempts']), 1)
        self.assertTrue(summary['attempts'][0]['incomplete_attempt'])
        self.assertFalse(any(block['same_quality_comparable'] for block in summary['blocks']))
        self.assertIsNone(summary['totals']['arms']['A']['cost_per_successful_task'])

    def test_summary_rejects_modified_derived_results_and_changed_trial_identity(self):
        self.frozen()
        with patch.object(subprocess, 'Popen', side_effect=OSError('fixture unavailable')):
            result = factorial.run_slot(self.root, 0)
        self.assertEqual(len(factorial.summarize(self.root)['attempts']), 1)
        directory = self.root / 'trials' / result['attempt_id']
        path = directory / 'result.json'
        original = path.read_bytes()
        result['usage'] = {'input_tokens': 0, 'cached_input_tokens': 0, 'output_tokens': 0}
        dump(path, result)
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            factorial.summarize(self.root)
        path.write_bytes(original)
        started = json.loads((directory / 'attempt.json').read_text())
        started['arm'] = 'B'
        dump(directory / 'attempt.json', started)
        with self.assertRaisesRegex(ValueError, 'identity differs'):
            factorial.summarize(self.root)

    def test_evidence_archive_is_reproducible_excludes_scratch_and_preserves_previous_files(self):
        self.frozen()
        dump(self.root / 'summary.json', factorial.summarize(self.root))
        (self.root / 'trials/scratch').mkdir(parents=True)
        (self.root / 'trials/scratch/transient').write_text('not study evidence')
        with tempfile.TemporaryDirectory() as destination:
            first = Path(destination) / 'first.zip'
            second = Path(destination) / 'second.zip'
            a = factorial.pack_evidence(self.root, first)
            b = factorial.pack_evidence(self.root, second)
            self.assertEqual(a['sha256'], b['sha256'])
            with zipfile.ZipFile(first) as archive:
                self.assertIn('manifest.json', archive.namelist())
                self.assertFalse(any('scratch' in name for name in archive.namelist()))
            with self.assertRaisesRegex(ValueError, 'new file outside'):
                factorial.pack_evidence(self.root, first)
            self.assertEqual(sha(first.read_bytes()), a['sha256'])


if __name__ == '__main__':
    unittest.main()
