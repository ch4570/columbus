"""Model-free collector acceptance, binding and ordering rejection tests."""
from contextlib import redirect_stdout
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


COHORT = Path(__file__).resolve().parents[1] / 'evals/source-call-sites-cohort'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def forbidden(*args, **kwargs):
    raise AssertionError('Collector tests must never start external processes')


with mock.patch.multiple(subprocess, Popen=forbidden, run=forbidden, check_output=forbidden):
    gate = load('source_call_cohort_gate', COHORT / 'collect.py')
    common = gate.common

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + '\n', encoding='utf-8')


def passing(input_tokens=100, output_tokens=20):
    return {'verified': True, 'terminal_passed': True, 'citation_passed': True, 'semantic_passed': True,
            'relationship_used': True, 'quotes_used': False,
            'usage': {'input_tokens': input_tokens, 'cached_input_tokens': 0, 'output_tokens': output_tokens}}


class SourceCallCohortGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='candidate-gate-')
        self.addCleanup(temporary.cleanup)
        self.here = Path(temporary.name)
        self.patch(gate, 'HERE', new=self.here)
        self.patch(common, 'HERE', new=self.here)
        self.patch(common, 'observation', side_effect=lambda language, arm: self.here / 'observations' / language / arm)
        for name in ('Popen', 'run', 'check_output'):
            self.patch(subprocess, name, side_effect=forbidden)
        for name in ('run.py', 'common.py', 'input-hashes.json'):
            (self.here / name).write_text('{}\n')
        self.case = {'id': 'case', 'question': 'Find mechanism', 'findings': [
            {'id': 'mechanism', 'description': 'Explain it', 'path': 'A.java', 'marker': 'marker'}]}
        self.criteria = {'mechanism': ['First clause', 'Second clause']}
        self.preflight = {arm: {'passed': True, 'arm': arm} for arm in gate.CONDITIONS}
        self.recognizer = SimpleNamespace(evidence=lambda *args: {'relationship_used': True,
            'relationship_receipts': [{'reviewed': True}], 'quotes_used': False, 'quote_receipts': []})
        self.clock = datetime(2026, 1, 1, tzinfo=timezone.utc)
        write(self.here / 'environment.json', {'codex_executable': '/frozen/bin/codex'})

    def patch(self, target, name, **kwargs):
        patcher = mock.patch.object(target, name, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def fixture(self, arm='candidate', repeat=1):
        output = common.observation('java', arm)
        (output / 'repository').mkdir(parents=True, exist_ok=True)
        (output / 'repository/A.java').write_text('marker();\n')
        trial = output / 'trials' / f'case-{arm}-{repeat}'
        trial.mkdir(parents=True, exist_ok=True)
        (trial / 'stderr.log').write_bytes(b'')
        prompt = common.prompt(self.case, arm, output)
        (trial / 'prompt.txt').write_bytes(prompt.encode('utf-8'))
        write(trial / 'invocation.json', {'argv': common.argv(output, trial), 'model_requested': 'gpt-5.6-sol',
            'effort_requested': 'xhigh', 'timeout_seconds': 1200, 'prompt_bytes': len(prompt.encode()),
            'harness_sha256': gate.sha(self.here / 'run.py'), 'common_sha256': gate.sha(self.here / 'common.py'),
            'input_hashes_sha256': gate.sha(self.here / 'input-hashes.json')})
        write(trial / 'process.json', {'pid': 123, 'started_at': self.clock.isoformat()})
        write(trial / 'terminal.json', {'return_code': 0, 'timed_out': False, 'elapsed_seconds': 1.0,
              'finished_at': (self.clock + timedelta(seconds=1)).isoformat()})
        answer = {'findings': [{'id': 'mechanism', 'path': 'A.java', 'start_line': 1, 'end_line': 1,
                              'quote': 'marker();', 'explanation': 'Both clauses explained'}]}
        write(trial / 'answer.json', answer)
        events = [{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps(answer)}},
                  {'type': 'turn.completed', 'usage': passing()['usage']}]
        self.write_result(trial, events, arm, repeat)
        write(self.here / 'java/relationships.json', [{'source': 'a', 'target': 'b', 'path': 'A.java', 'line': 1}])
        (self.here / 'java/SOURCE-REVIEW.md').write_text('Frozen review')
        review = {'answer_sha256': gate.sha(trial / 'answer.json'),
                  'rubric_sha256': gate.sha(self.here / 'java/SOURCE-REVIEW.md'), 'findings': [
                    {'id': 'mechanism', 'passed': True, 'reason': 'Both clauses reviewed', 'checks': [
                        {'criterion_index': i, 'passed': True, 'reason': 'Supported'} for i in range(2)]}],
                  'execution_review': {'events_sha256': gate.sha(trial / 'events.jsonl'),
                                       'passed': True, 'reason': 'Every command inspected'}}
        write(self.here / 'java/semantic' / (trial.name + '.json'), review)
        return trial, events

    def write_result(self, trial, events, arm='candidate', repeat=1):
        (trial / 'events.jsonl').write_text(''.join(json.dumps(event) + '\n' for event in events))
        answer = gate.read(trial / 'answer.json')
        write(trial / 'result.json', {'case': 'case', 'condition': arm, 'repeat': repeat,
              **gate.read(trial / 'terminal.json'), **gate.OBSERVE.parse_events(events), 'answer': answer,
              'quality': gate.OBSERVE.grade(answer, self.case, trial.parents[1] / 'repository'),
              'preflight': self.preflight, 'postflight': self.preflight, 'events_sha256': gate.sha(trial / 'events.jsonl')})

    def collected(self, arm='candidate', repeat=1):
        return gate.collect_trial('java', self.case, self.criteria, arm, repeat, self.preflight, self.recognizer)

    def test_primary_requires_both_quality_strict_actual_totals_and_relationship(self):
        baseline, candidate = passing(), passing(90, 19)
        self.assertTrue(gate.pair_gate(baseline, candidate)['accepted'])
        self.assertFalse(candidate['quotes_used'])  # Adoption is optional, not fabricated or required.
        for field in ('verified', 'terminal_passed', 'citation_passed', 'semantic_passed'):
            for left in (True, False):
                pair = [copy.deepcopy(baseline), copy.deepcopy(candidate)]
                pair[0 if left else 1][field] = False
                self.assertFalse(gate.pair_gate(*pair)['accepted'])
        self.assertFalse(gate.pair_gate(baseline, passing(100, 19))['accepted'])
        self.assertFalse(gate.pair_gate(baseline, passing(90, 20))['accepted'])
        candidate['relationship_used'] = False
        candidate['quotes_used'] = True
        self.assertFalse(gate.pair_gate(baseline, candidate)['accepted'])

    def test_secondary_requires_control_quality_and_graph_not_primary_substitution(self):
        control, candidate = passing(), passing(90, 19)
        for flag in ('semantic_passed', 'relationship_used'):
            broken = dict(control, **{flag: False})
            self.assertFalse(gate.pair_gate(broken, candidate, 'control')['accepted'])
        pairs = [{'language': language, 'repeat': repeat, 'accepted': True}
                 for language in gate.LANGUAGES for repeat in (1, 2)]
        self.assertTrue(gate.six_pairs(pairs))
        self.assertFalse(gate.six_pairs(pairs[:-1]))
        self.assertFalse(gate.six_pairs(pairs + [pairs[0]]))
        self.assertFalse(gate.six_pairs([dict(row, accepted=False) if i == 0 else row for i, row in enumerate(pairs)]))

    def test_usage_rejects_bool_negative_invalid_subsets_and_nonintegers(self):
        original = passing()['usage']
        for changed in ({'input_tokens': True}, {'output_tokens': -1}, {'cached_input_tokens': 101},
                        {'reasoning_output_tokens': 21}, {'output_tokens': 2.5}, {'uncached_input_tokens': 99}):
            self.assertFalse(gate.valid_usage({**original, **changed}))
        self.assertFalse(gate.valid_usage(None))
        self.assertFalse(gate.valid_usage({'input_tokens': 1, 'output_tokens': 1}))
        candidate = passing(110, 10)
        candidate['usage']['cached_input_tokens'] = 109
        self.assertFalse(gate.pair_gate(passing(), candidate)['accepted'])

    def test_terminal_trial_recomputes_all_bindings(self):
        trial, _ = self.fixture()
        result = self.collected()
        self.assertTrue(result['verified'])
        self.assertFalse(gate.run_quality(result, True))
        self.assertEqual(result['completed_turns'], 1)
        self.assertEqual(result['artifact_sha256']['events.jsonl'], gate.sha(trial / 'events.jsonl'))
        (trial / 'prompt.txt').write_text('Changed prompt')
        self.assertFalse(self.collected()['verified'])

    def test_fixture_prompt_is_exact_utf8_lf_and_crlf_tampering_is_rejected(self):
        self.case['question'] += ' — café 😀'
        trial, _ = self.fixture()
        expected = common.prompt(self.case, 'candidate', common.observation('java', 'candidate')).encode('utf-8')
        self.assertEqual((trial / 'prompt.txt').read_bytes(), expected)
        self.assertNotIn(b'\r', expected)
        self.assertGreater(expected.count(b'\n'), 0)
        self.assertEqual(gate.read(trial / 'invocation.json')['prompt_bytes'], len(expected))
        self.assertTrue(self.collected()['verified'])
        changed = expected.replace(b'\n', b'\r\n')
        self.assertNotEqual(changed, expected)
        (trial / 'prompt.txt').write_bytes(changed)
        result = self.collected()
        self.assertFalse(result['verified'])
        self.assertEqual(result['reason'], 'Frozen prompt differs')

    def test_raw_event_hash_and_invocation_timeout_cannot_be_rewritten_unnoticed(self):
        trial, _ = self.fixture()
        invocation = gate.read(trial / 'invocation.json')
        write(trial / 'invocation.json', {**invocation, 'timeout_seconds': 999})
        self.assertIn('Invocation', self.collected()['reason'])
        write(trial / 'invocation.json', invocation)
        with (trial / 'events.jsonl').open('a') as stream:
            stream.write('{}\n')
        self.assertIn('events hash', self.collected()['reason'])

    def test_all_completed_turn_usage_validated_and_multiple_turns_fail(self):
        trial, events = self.fixture()
        events.insert(0, {'type': 'turn.completed', 'usage': passing()['usage']})
        self.write_result(trial, events)
        result = self.collected()
        self.assertTrue(result['verified'])
        self.assertFalse(result['terminal_passed'])
        events[0]['usage']['output_tokens'] = True
        self.write_result(trial, events)
        self.assertIn('raw completed-turn usage', self.collected()['reason'])

    def test_unexpected_tool_even_only_started_fails_protocol(self):
        trial, events = self.fixture()
        events.insert(0, {'type': 'item.started', 'item': {'type': 'web_search'}})
        self.write_result(trial, events)
        result = self.collected()
        self.assertFalse(result['terminal_passed'])
        self.assertEqual(result['disallowed_item_types'], ['web_search'])

    def test_deeply_nested_actual_events_and_answer_keep_unverified_terminal_receipts(self):
        for arm, filename in (('baseline', 'events.jsonl'), ('candidate', 'answer.json')):
            with self.subTest(filename=filename):
                trial, _ = self.fixture(arm)
                payload = ('[' * 10000 + '0' + ']' * 10000 + '\n').encode('utf-8')
                (trial / filename).write_bytes(payload)
                if filename == 'events.jsonl':
                    result = gate.read(trial / 'result.json')
                    result['events_sha256'] = gate.sha(trial / filename)
                    write(trial / 'result.json', result)
                observed = self.collected(arm)
                self.assertFalse(observed['verified'])
                self.assertTrue(observed['terminal_evidence_present'])
                self.assertEqual(observed['artifact_sha256'][filename], gate.sha(trial / filename))

    def test_deep_frozen_input_failure_still_reports_all_eighteen_slots(self):
        self.patch(common, 'frozen_inputs', side_effect=RecursionError('deep frozen JSON'))
        with mock.patch.object(sys, 'argv', ['collect.py']), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(gate.main(), 1)
        report = json.loads(output.getvalue())
        self.assertFalse(report['experiment_accepted'])
        self.assertEqual(len(report['trials']), 18)
        self.assertEqual(len(report['primary_pairs']), 6)

    def test_extra_answer_ids_and_missing_semantic_checks_cannot_pass(self):
        trial, events = self.fixture()
        review_path = self.here / 'java/semantic' / (trial.name + '.json')
        review = gate.read(review_path)
        review['findings'][0]['checks'].pop()
        write(review_path, review)
        self.assertFalse(self.collected()['semantic_passed'])
        answer = gate.read(trial / 'answer.json')
        answer['findings'].append({**answer['findings'][0], 'id': 'extra'})
        write(trial / 'answer.json', answer)
        events[0]['item']['text'] = json.dumps(answer)
        self.write_result(trial, events)
        self.assertFalse(self.collected()['citation_passed'])

    def test_missing_terminal_result_retains_hashes_and_does_not_infer_running_or_stopped(self):
        trial, _ = self.fixture()
        (trial / 'result.json').unlink()
        result = self.collected()
        self.assertFalse(result['verified'])
        self.assertTrue(result['terminal_evidence_present'])
        self.assertIn('events.jsonl', result['artifact_sha256'])
        (trial / 'terminal.json').unlink()
        result = self.collected()
        self.assertTrue(result['pending'])
        self.assertFalse(result['terminal_evidence_present'])

    def order_fixture(self):
        group = common.observation('java', 'baseline').parent
        write(group / 'runner.json', {'pid': 1, 'started_at': (self.clock - timedelta(seconds=1)).isoformat(),
            'schedule': common.schedule('java'), 'input_hashes_sha256': gate.sha(self.here / 'input-hashes.json')})
        directories = []
        for index, (arm, repeat) in enumerate(common.schedule('java')):
            trial, _ = self.fixture(arm, repeat)
            start = self.clock + timedelta(seconds=index * 2)
            write(trial / 'process.json', {'pid': index + 10, 'started_at': start.isoformat()})
            write(trial / 'terminal.json', {'return_code': 0, 'timed_out': False, 'elapsed_seconds': 1,
                  'finished_at': (start + timedelta(seconds=1)).isoformat()})
            directories.append(trial)
        write(group / 'runner-terminal.json', {'status': 'all scheduled executions terminated',
              'finished_at': (self.clock + timedelta(seconds=12)).isoformat()})
        return group, directories

    def test_exact_six_order_and_terminal_before_next_start(self):
        _, directories = self.order_fixture()
        self.assertTrue(gate.verify_order('java', self.case)['passed'])
        terminal = gate.read(directories[0] / 'terminal.json')
        write(directories[0] / 'terminal.json', {**terminal,
              'finished_at': (self.clock + timedelta(seconds=3)).isoformat()})
        with self.assertRaisesRegex(ValueError, 'overlap'):
            gate.verify_order('java', self.case)

    def test_extra_trial_rejected_and_missing_control_does_not_fake_complete_group(self):
        group, directories = self.order_fixture()
        extra = directories[0].parent / 'unplanned-retry'
        extra.mkdir()
        with self.assertRaisesRegex(ValueError, 'extra trial'):
            gate.verify_order('java', self.case)
        extra.rmdir()
        control = next(path for path in directories if '-control-' in path.name)
        for path in control.iterdir():
            path.unlink()
        control.rmdir()
        (group / 'runner-terminal.json').unlink()
        result = gate.verify_order('java', self.case)
        self.assertFalse(result['passed'])
        self.assertEqual(result['missing_process_slots'], [['control', 1]])

    def test_main_stdout_is_default_and_explicit_output_cannot_overwrite(self):
        result = {'primary_accepted': True, 'experiment_accepted': True}
        self.patch(gate, 'collect', return_value=result)
        before = sorted(self.here.rglob('*'))
        with mock.patch.object(sys, 'argv', ['collect.py']), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(gate.main(), 0)
        self.assertEqual(json.loads(output.getvalue()), result)
        self.assertEqual(sorted(self.here.rglob('*')), before)
        target = self.here / 'new-report'
        with mock.patch.object(sys, 'argv', ['collect.py', '--output', str(target)]), redirect_stdout(io.StringIO()):
            self.assertEqual(gate.main(), 0)
        self.assertEqual(gate.read(target / 'results.json'), result)
        with mock.patch.object(sys, 'argv', ['collect.py', '--output', str(target)]):
            with self.assertRaisesRegex(ValueError, 'already exists'):
                gate.main()

    def aggregate(self, baseline, control, candidate, order=True):
        for language in gate.LANGUAGES:
            write(self.here / language / 'cases.json', {'cases': [self.case]})
            write(self.here / language / 'criteria.json', self.criteria)
        samples = {'baseline': baseline, 'control': control, 'candidate': candidate}
        with mock.patch.object(common, 'frozen_inputs', return_value={'frozen': 'hash'}), \
             mock.patch.object(common, 'module', return_value=self.recognizer), \
             mock.patch.object(common, 'verify_observation', return_value={'passed': True}), \
             mock.patch.object(gate, 'verify_controls'), \
             mock.patch.object(gate, 'verify_order', return_value={'passed': order}), \
             mock.patch.object(gate, 'collect_trial', side_effect=lambda language, case, criteria, arm, *args: samples[arm]):
            return gate.collect()

    def test_aggregate_keeps_primary_independent_of_control_quality(self):
        result = self.aggregate(passing(), dict(passing(), semantic_passed=False), passing(90, 19))
        self.assertTrue(result['primary_accepted'])
        self.assertFalse(result['experiment_accepted'])
        self.assertFalse(result['secondary_accepted'])
        self.assertEqual(len(result['trials']), 18)
        self.assertEqual(len(result['primary_pairs']), 6)
        self.assertEqual(len(result['secondary_pairs']), 6)
        missing = self.aggregate(passing(), {'verified': False, 'pending': True}, passing(90, 19), order=False)
        self.assertTrue(missing['primary_accepted'])
        self.assertFalse(missing['experiment_accepted'])

    def test_secondary_improvement_never_substitutes_and_regression_is_separate(self):
        result = self.aggregate(passing(100, 20), passing(120, 30), passing(110, 25))
        self.assertTrue(result['secondary_accepted'])
        self.assertFalse(result['primary_accepted'])
        self.assertFalse(result['experiment_accepted'])
        result = self.aggregate(passing(100, 20), passing(80, 10), passing(90, 19))
        self.assertTrue(result['primary_accepted'])
        self.assertTrue(result['experiment_accepted'])
        self.assertFalse(result['secondary_accepted'])


if __name__ == '__main__':
    unittest.main()
