"""Printed numbers must match physical lines before counting a source read."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class NumberedReadsTests(unittest.TestCase):
    def test_sed_then_nl_accepts_both_start_forms_and_rejects_wrong_numbers(self):
        for option in ['-v2', '-v 2']:
            with self.subTest(option=option), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = b'first\nsecond\nthird\n'
                path = root / 'repository/django/example.py'
                path.parent.mkdir(parents=True)
                path.write_bytes(source)
                (root / 'manifest.json').write_text(json.dumps({'source_manifest': {
                    'django/example.py': hashlib.sha256(source).hexdigest()}}))
                for condition, output in [('baseline', '     2\tsecond\n     3\tthird\n'),
                                          ('columbus', '    90\tsecond\n    91\tthird\n')]:
                    trial = root / 'trials' / ('case-' + condition + '-1')
                    trial.mkdir(parents=True)
                    event = {'type': 'item.completed', 'item': {
                        'id': 'read', 'type': 'command_execution', 'exit_code': 0,
                        'command': '/bin/zsh -lc "sed -n 2,3p django/example.py | nl -ba ' + option + '"',
                        'aggregated_output': output}}
                    raw = (json.dumps(event) + '\n').encode()
                    (trial / 'events.jsonl').write_bytes(raw)
                    (trial / 'result.json').write_text(json.dumps({'events_sha256': hashlib.sha256(raw).hexdigest()}))
                destination = root / 'measured.json'
                subprocess.run([sys.executable, str(Path(__file__).with_name('measure.py')),
                                str(root), str(destination), '--case', 'case'], check=True, capture_output=True)
                result = json.loads(destination.read_text())['conditions']
                self.assertEqual(result['baseline']['unique_lines'], 2)
                self.assertEqual(result['baseline']['source_bytes_returned'], len(b'second\nthird\n'))
                self.assertEqual(result['baseline']['unverified_ranges'], [])
                self.assertEqual(result['columbus']['verified_ranges'], 0)
                self.assertEqual(len(result['columbus']['unverified_ranges']), 1)


if __name__ == '__main__':
    unittest.main()
