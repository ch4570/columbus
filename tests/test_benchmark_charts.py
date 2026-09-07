"""Guard the comparison contracts before measured values become published charts."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('plot_benchmarks', ROOT / 'scripts/plot_benchmarks.py')
charts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(charts)


class BenchmarkEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        evidence = ROOT / 'evals/exploration/results/2026-09-07'
        cls.history = json.loads((evidence / 'controlled.json').read_text(encoding='utf-8'))
        cls.delivery = json.loads((evidence / 'delivery.json').read_text(encoding='utf-8'))

    def test_historical_regression_and_failed_citations_are_not_hidden(self):
        series = charts.historical_series(self.history)
        self.assertEqual(len(series), 3)
        eligible = [row for row in series if row['both_citations_passed']]
        self.assertEqual([row['case'] for row in eligible], ['export-safety'])
        self.assertGreater(eligible[0]['change_pct'], 0)
        self.assertEqual(eligible[0]['input_tokens'], [79358, 106334])
        self.assertEqual(sum(not all(row['citation_passed']) for row in series), 2)

    def test_duplicate_trial_cannot_be_silently_selected(self):
        evidence = copy.deepcopy(self.history)
        evidence['trials'].append(evidence['trials'][0])
        with self.assertRaisesRegex(ValueError, 'Expected one measurement'):
            charts.historical_series(evidence)

    def test_pair_cannot_hide_failed_citation(self):
        evidence = copy.deepcopy(self.history)
        evidence['pairs'][1]['quality_gated'] = True
        with self.assertRaisesRegex(ValueError, 'comparability'):
            charts.historical_series(evidence)

    def test_cached_input_is_not_added_to_total(self):
        evidence = copy.deepcopy(self.history)
        trial = evidence['trials'][0]
        trial['usage']['cached_input_tokens'] = trial['usage']['input_tokens'] + 1
        with self.assertRaisesRegex(ValueError, 'Token summary'):
            charts.historical_series(evidence)

    def test_changed_pair_summary_is_rejected(self):
        evidence = copy.deepcopy(self.history)
        evidence['pairs'][0]['measures']['input_tokens']['baseline'] += 1
        with self.assertRaisesRegex(ValueError, 'Token summary'):
            charts.historical_series(evidence)

    def test_delivery_distinguishes_source_from_response(self):
        series = charts.delivery_series(self.delivery)
        self.assertEqual(series['output_totals'], [9633, 4483])
        self.assertEqual(series['source_by_call'][1], [1429, 188, 0])
        self.assertEqual(series['output_by_call'][1][-1], 334)

    def test_truncated_map_cannot_support_same_item_comparison(self):
        evidence = copy.deepcopy(self.delivery)
        evidence['rows'][0]['truncated'] = True
        with self.assertRaisesRegex(ValueError, 'Same-map'):
            charts.delivery_series(evidence)

    def test_missing_receipt_call_is_rejected(self):
        evidence = copy.deepcopy(self.delivery)
        evidence['rows'].pop()
        with self.assertRaisesRegex(ValueError, 'Expected one measurement'):
            charts.delivery_series(evidence)

    def test_negative_and_nonfinite_counts_are_rejected(self):
        for value in (-1, float('nan'), float('inf'), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                charts.number(value, 'observed_bytes')


if __name__ == '__main__':
    unittest.main()
