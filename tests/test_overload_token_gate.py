"""Pure rejection tests for the prospective actual-token acceptance gate."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest import mock


PATH = Path(__file__).resolve().parents[1] / 'evals/overload-token-cohort/collect.py'
SPEC = importlib.util.spec_from_file_location('multilang_token_gate', PATH)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def trial(input_tokens=100, output_tokens=20, cached=0):
    return {'verified': True, 'terminal_passed': True, 'citation_passed': True,
            'semantic_passed': True, 'graph_evidence_used': True,
            'usage': {'input_tokens': input_tokens, 'cached_input_tokens': cached,
                      'uncached_input_tokens': input_tokens - cached, 'output_tokens': output_tokens}}


class OverloadTokenGateTests(unittest.TestCase):
    def test_missing_semantic_clause_cannot_pass_a_review(self):
        review = {'answer_sha256': 'answer', 'rubric_sha256': 'rubric', 'findings': [
            {'id': 'branch', 'passed': True, 'reason': 'reviewed', 'checks': [
                {'criterion_index': 0, 'passed': True, 'reason': 'first clause supported'}]}]}
        criteria = {'branch': ['positive branch', 'negative branch']}
        result = gate.semantic_gate(review, criteria, 'answer', 'rubric')
        self.assertFalse(result['passed'])
        self.assertTrue(result['pending'])
        review['findings'][0]['checks'].append({'criterion_index': 1, 'passed': True, 'reason': 'negative covered'})
        self.assertTrue(gate.semantic_gate(review, criteria, 'answer', 'rubric')['passed'])
        skipped = dict(review, status='skipped')
        self.assertTrue(gate.semantic_gate(skipped, criteria, 'answer', 'rubric')['pending'])
        self.assertFalse(gate.semantic_gate(skipped, criteria, 'answer', 'rubric')['passed'])
        review['findings'][0]['checks'][1]['criterion_index'] = 0
        self.assertFalse(gate.semantic_gate(review, criteria, 'answer', 'rubric')['passed'])

    def test_quality_failure_rejects_lower_usage(self):
        baseline, columbus = trial(), trial(80, 15)
        self.assertTrue(gate.pair_gate(baseline, columbus)['accepted'])
        for condition in ('baseline', 'columbus'):
            for flag in ('semantic_passed', 'citation_passed', 'terminal_passed'):
                pair = {'baseline': copy.deepcopy(baseline), 'columbus': copy.deepcopy(columbus)}
                pair[condition][flag] = False
                self.assertFalse(gate.pair_gate(**pair)['accepted'])

    def test_cached_subset_does_not_reduce_total_input_for_acceptance(self):
        baseline, columbus = trial(100, 20, 10), trial(110, 15, 105)
        self.assertLess(columbus['usage']['uncached_input_tokens'], baseline['usage']['uncached_input_tokens'])
        self.assertFalse(gate.pair_gate(baseline, columbus)['accepted'])
        columbus = trial(90, 20)
        self.assertFalse(gate.pair_gate(baseline, columbus)['accepted'])

    def test_one_failed_or_missing_pair_prevents_cohort_acceptance(self):
        pairs = [{'language': language, 'repeat': repeat, 'accepted': True}
                 for language in gate.LANGUAGES for repeat in (1, 2)]
        self.assertTrue(gate.cohort_gate(pairs))
        self.assertFalse(gate.cohort_gate(pairs[:-1]))
        pairs[3]['accepted'] = False
        self.assertFalse(gate.cohort_gate(pairs))


    def test_answer_schema_rejects_extra_fields_and_boolean_lines(self):
        finding = {'id': 'x', 'path': 'A.java', 'start_line': 1, 'end_line': 2,
                   'quote': 'source', 'explanation': 'behavior'}
        self.assertTrue(gate.answer_schema_valid({'findings': [finding]}))
        for key, value in [('extra', 1), ('start_line', True), ('quote', None)]:
            self.assertFalse(gate.answer_schema_valid({'findings': [{**finding, key: value}]}))
        self.assertFalse(gate.answer_schema_valid({'findings': [finding], 'extra': True}))

    def test_execution_review_binds_events_and_cannot_be_missing(self):
        self.assertTrue(gate.execution_gate(None, 'hash')['pending'])
        review = {'events_sha256': 'hash', 'passed': True, 'reason': 'All commands in scope'}
        self.assertTrue(gate.execution_gate(review, 'hash')['passed'])
        self.assertFalse(gate.execution_gate(review, 'other')['passed'])
        self.assertFalse(gate.execution_gate({**review, 'passed': 1}, 'hash')['passed'])
        self.assertFalse(gate.execution_gate({**review, 'reason': ''}, 'hash')['passed'])
        for key, value in [('pending', True), ('skipped', True), ('status', 'pending'), ('status', 'skipped')]:
            result = gate.execution_gate({**review, key: value}, 'hash')
            self.assertFalse(result['passed'])
            self.assertTrue(result['pending'])

    def test_prompt_reconstruction_matches_actual_frozen_harness_statements(self):
        import ast
        import shlex
        import sys
        harness_path = PATH.parent.parent / 'exploration/observe_saved_callers.py'
        spec = importlib.util.spec_from_file_location('overload_prompt_test_observer', harness_path)
        observer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(observer)
        tree = ast.parse(harness_path.read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'trial')
        start = next(i for i, node in enumerate(function.body)
                     if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'requests'
                                                            for target in node.targets))
        # Execute only the existing prompt construction, never any process/filesystem statement.
        statements = function.body[start:start + 3]
        self.assertIsInstance(statements[-1], ast.If)
        prompt_code = compile(ast.fix_missing_locations(ast.Module(body=statements, type_ignores=[])), str(harness_path), 'exec')
        case = {'question': 'Trace behavior', 'findings': [{'id': 'behavior', 'description': 'Explain branches',
                                                        'path': 'PRIVATE_PATH', 'marker': 'PRIVATE_MARKER'}]}
        output = Path('/tmp/overload-prompt-test')
        for condition in ('baseline', 'columbus'):
            namespace = {'case': case, 'condition': condition, 'output': output,
                         'finding_request': observer.finding_request, 'ENGINE_LAYOUTS': observer.ENGINE_LAYOUTS,
                         'archive_frozen': {'archive': True}, 'sys': sys, 'shlex': shlex}
            exec(prompt_code, namespace)
            prompt = gate.expected_prompt(case, condition, output)
            self.assertEqual(prompt, namespace['prompt'])
            self.assertNotIn('PRIVATE_PATH', prompt)
            self.assertNotIn('PRIVATE_MARKER', prompt)

    def test_inventory_requires_new_recognizer_controls_and_full_sources(self):
        names = gate.required_inputs()
        self.assertIn('evals/exploration/archive_evidence.py', names)
        self.assertIn('evals/exploration/test_archive_evidence.py', names)
        for language in gate.LANGUAGES:
            for name in ('source.zip', 'controls.json', 'mechanism.json', 'SOURCE-REVIEW.md'):
                self.assertIn(f'evals/overload-token-cohort/{language}/{name}', names)

    def test_prelaunch_controls_reject_unsuccessful_placeholders(self):
        case = {'findings': [{'id': 'x'}]}
        control = {'positive': {'passed': True, 'findings': [{'id': 'x', 'passed': True}]},
                   'negative': {'passed': False, 'findings': [{'id': 'x', 'passed': False}]},
                   'control_answer': {'findings': []}}
        observer = mock.Mock()
        observer.grade.return_value = control['positive']
        with mock.patch.object(gate, 'read_json', side_effect=[{'cases': [case]}, control, {'passed': False}]):
            with self.assertRaisesRegex(gate.GateError, 'graph control did not pass'):
                gate.verify_controls('java', observer)
        changed = copy.deepcopy(control)
        changed['negative']['passed'] = True
        with mock.patch.object(gate, 'read_json', side_effect=[{'cases': [case]}, changed]):
            with self.assertRaisesRegex(gate.GateError, 'citation controls did not pass'):
                gate.verify_controls('java', observer)


if __name__ == '__main__':
    unittest.main()
