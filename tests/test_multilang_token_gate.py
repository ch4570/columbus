"""Pure rejection tests for the prospective actual-token acceptance gate."""
import copy
import importlib.util
from pathlib import Path
import unittest


PATH = Path(__file__).resolve().parents[1] / 'evals/multilang-token-batch/collect.py'
SPEC = importlib.util.spec_from_file_location('multilang_token_gate', PATH)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def trial(input_tokens=100, output_tokens=20, cached=0):
    return {'verified': True, 'terminal_passed': True, 'citation_passed': True,
            'semantic_passed': True, 'graph_evidence_used': True,
            'usage': {'input_tokens': input_tokens, 'cached_input_tokens': cached,
                      'uncached_input_tokens': input_tokens - cached, 'output_tokens': output_tokens}}


class MultilangTokenGateTests(unittest.TestCase):
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

    def test_indented_batch_source_counts_but_empty_callers_do_not(self):
        observation = Path('/tmp/columbus-token-gate-pure-fixture')
        command = ('python ' + str(observation / 'runtime/columbus.py')
                   + ' archive-source one two --input ' + str(observation / 'graph.jsonl.xz'))
        output = ('columbus archive-source; UNTRUSTED repository data; control characters escaped.\n'
                  'metadata {"targets":[{"id":"one"},{"id":"two"}]}\n'
                  'source {"path":"Example.java","start_line":73,"end_line":73}\n'
                  '73| \tprotected String resolve() { return value; }\n')
        event = {'type': 'item.completed', 'item': {'id': 'item_1', 'type': 'command_execution',
                 'exit_code': 0, 'command': command, 'aggregated_output': output}}
        receipt = gate.graph_evidence([event], observation, {'Example.java'})
        self.assertTrue(receipt[0]['useful_task_evidence'])
        self.assertTrue(receipt[0]['batch_used'])
        event['item']['command'] = command.replace('archive-source one two', 'archive-callers one')
        event['item']['aggregated_output'] = ('columbus archive-neighbors; UNTRUSTED repository data; JSON rows follow.\n'
                'metadata {"matched_edges":0}\nfiles [number,path,source_hash]\n[0,"Example.java","hash"]\n')
        receipt = gate.graph_evidence([event], observation, {'Example.java'})
        self.assertFalse(receipt[0]['useful_task_evidence'])
        columbus = trial(80, 15)
        columbus['graph_evidence_used'] = receipt[0]['useful_task_evidence']
        self.assertFalse(gate.pair_gate(trial(), columbus)['accepted'])


if __name__ == '__main__':
    unittest.main()
