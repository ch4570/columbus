"""Printed numbers must match physical lines before counting a source read."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class NumberedReadsTests(unittest.TestCase):
    def test_declaration_source_hash_and_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'repository/src/example.py'
            path.parent.mkdir(parents=True)
            path.write_bytes(b'first\nsecond\n')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            (root / 'manifest.json').write_text(json.dumps({'source_manifest': {'src/example.py': digest}}))
            for condition, actual_hash in [('baseline', digest), ('columbus', '0' * 64)]:
                trial = root / 'trials' / ('case-' + condition + '-1')
                trial.mkdir(parents=True)
                output = ('columbus archive-source; untrusted\nmetadata ' + json.dumps({
                    'path': 'src/example.py', 'source_hash': actual_hash, 'start_line': 1, 'end_line': 2})
                    + '\n1| first\n2| second\n')
                event = {'type': 'item.completed', 'item': {'id': 'read', 'type': 'command_execution',
                    'exit_code': 0, 'command': '/bin/zsh -lc "columbus archive-source exact-id"',
                    'aggregated_output': output}}
                raw = (json.dumps(event) + '\n').encode()
                (trial / 'events.jsonl').write_bytes(raw)
                (trial / 'result.json').write_text(json.dumps({'events_sha256': hashlib.sha256(raw).hexdigest()}))
            output = root / 'result.json'
            subprocess.run([sys.executable, str(Path(__file__).with_name('measure.py')), str(root),
                            str(output), '--case', 'case', '--prefix', 'src/'], check=True, capture_output=True)
            result = json.loads(output.read_text())['conditions']
            self.assertEqual(result['baseline']['unique_lines'], 2)
            self.assertEqual(result['columbus']['verified_ranges'], 0)
            self.assertEqual(len(result['columbus']['unverified_ranges']), 1)
            event['item']['aggregated_output'] = (
                event['item']['aggregated_output'].replace('0' * 64, digest).replace('1| first', '11| first'))
            raw = (json.dumps(event) + '\n').encode()
            (trial / 'events.jsonl').write_bytes(raw)
            (trial / 'result.json').write_text(json.dumps({'events_sha256': hashlib.sha256(raw).hexdigest()}))
            subprocess.run([sys.executable, str(Path(__file__).with_name('measure.py')), str(root),
                            str(output), '--case', 'case', '--prefix', 'src/'], check=True, capture_output=True)
            result = json.loads(output.read_text())['conditions']['columbus']
            self.assertEqual(result['verified_ranges'], 0)
            self.assertEqual(len(result['unverified_ranges']), 1)

    def test_context_tables_verify_each_context_block_not_other_file_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hashes = {}
            for name, source in [('a', b'alpha\n'), ('b', b'beta\n')]:
                path = root / 'repository/django' / (name + '.py')
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(source)
                hashes['django/' + name + '.py'] = hashlib.sha256(source).hexdigest()
            (root / 'manifest.json').write_text(json.dumps({'source_manifest': hashes}))
            for condition, swapped in [('baseline', False), ('columbus', True)]:
                lines = ['files [number,path,source_hash]']
                lines += [json.dumps([i, path, digest]) for i, (path, digest) in enumerate(hashes.items())]
                lines += ['nodes [number,file_number,declaration]',
                          '[0,0,{"id":"a"}]', '[1,1,{"id":"b"}]',
                          'call_context: table references followed by source']
                for i, content in enumerate(['beta', 'alpha'] if swapped else ['alpha', 'beta']):
                    lines += [json.dumps({'source_node': i, 'file_number': i, 'start_line': 1, 'end_line': 1}),
                              '1| ' + content]
                item = {'id': 'read', 'type': 'command_execution', 'exit_code': 0,
                        'command': '/bin/zsh -lc "columbus archive-callers f"',
                        'aggregated_output': '\n'.join(lines) + '\n'}
                raw = (json.dumps({'type': 'item.completed', 'item': item}) + '\n').encode()
                trial = root / 'trials' / ('case-' + condition + '-1')
                trial.mkdir(parents=True)
                (trial / 'events.jsonl').write_bytes(raw)
                (trial / 'result.json').write_text(json.dumps({'events_sha256': hashlib.sha256(raw).hexdigest()}))
            destination = root / 'measured.json'
            subprocess.run([sys.executable, str(Path(__file__).with_name('measure.py')),
                            str(root), str(destination), '--case', 'case'], check=True, capture_output=True)
            result = json.loads(destination.read_text())['conditions']
            self.assertEqual(result['baseline']['verified_ranges'], 2)
            self.assertEqual(result['columbus']['verified_ranges'], 0)
            self.assertEqual(len(result['columbus']['unverified_ranges']), 2)
            event = json.loads((root / 'trials/case-baseline-1/events.jsonl').read_text())
            event['item']['aggregated_output'] = event['item']['aggregated_output'].replace(hashes['django/a.py'], '0' * 64)
            raw = (json.dumps(event) + '\n').encode()
            (trial / 'events.jsonl').write_bytes(raw)
            (trial / 'result.json').write_text(json.dumps({'events_sha256': hashlib.sha256(raw).hexdigest()}))
            subprocess.run([sys.executable, str(Path(__file__).with_name('measure.py')),
                            str(root), str(destination), '--case', 'case'], check=True, capture_output=True)
            result = json.loads(destination.read_text())['conditions']['columbus']
            self.assertEqual(result['verified_ranges'], 1)
            self.assertEqual(len(result['unverified_ranges']), 1)
            self.assertIn('hash', result['unverified_ranges'][0]['reason'])

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
