"""Validate the committed completed capture; no model or original /tmp access."""
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'evals/quotes-three-arm'
spec = importlib.util.spec_from_file_location('completed_quotes_retention', HERE / 'retain.py')
retention = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retention)


class RetainedQuotesCohortTests(unittest.TestCase):
    def test_committed_capture_is_complete_byte_exact_and_failed(self):
        result = retention.verify(HERE / 'retained')
        self.assertEqual(result, {
            'verified': True, 'cohort_complete': True, 'scheduled_trials': 18,
            'files': 198, 'issues': [],
            'retention_sha256': 'd324e0fea704fd00d17fe182adac0c45d5bdaf492ebbafcd6800704604bc9a04',
        })
        raw = (HERE / 'retained/collector-report.json').read_bytes()
        self.assertEqual(retention.digest(raw),
                         '723f580991cb7e4f6419b6b607ea62c2aebe899e347e93f466c350e43f266bda')
        report = json.loads(raw)
        self.assertFalse(report['experiment_accepted'])
        self.assertFalse(report['primary_accepted'])
        self.assertFalse(report['secondary_accepted'])
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['frozen_inputs_verified'], 123)
        self.assertEqual(len(report['trials']), 18)
        self.assertTrue(all(row['verified'] and not row['pending'] for row in report['trials'].values()))


if __name__ == '__main__':
    unittest.main()
