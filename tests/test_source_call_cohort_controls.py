"""Model-free control replay and original failed-control retention tests."""
import copy
import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
COHORT = ROOT / 'evals/source-call-sites-cohort'


def forbidden(*args, **kwargs):
    raise AssertionError('No external process is allowed in control replay tests')


with mock.patch.multiple(subprocess, Popen=forbidden, run=forbidden, check_output=forbidden):
    spec = importlib.util.spec_from_file_location('source_calls_control_tests', COHORT / 'controls.py')
    controls = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controls)
common = controls.common


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value) + '\n').encode('utf-8'))


class SourceCallControlTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='source-call-controls-')
        self.addCleanup(temporary.cleanup)
        self.here = Path(temporary.name)
        self.patch(common, 'HERE', new=self.here)
        self.patch(common, 'observation', side_effect=lambda language, arm: self.here / 'observations' / language / arm)
        for name in ('Popen', 'run', 'check_output'):
            self.patch(subprocess, name, side_effect=forbidden)
        self.preflight = {arm: {'passed': True, 'arm': arm} for arm in common.CONDITIONS}
        self.case = {'id': 'case', 'findings': [{'id': 'mechanism', 'description': 'Explain it',
                    'path': 'A.java', 'marker': 'marker'}]}
        self.relationships = [{'source': 'A.java::outer', 'target': 'B.java::helper', 'path': 'A.java', 'line': 1}]
        self.directory = self.here / 'java'
        for arm in common.CONDITIONS:
            source = common.observation('java', arm) / 'repository/A.java'
            source.parent.mkdir(parents=True)
            source.write_bytes(b'marker();\n')
        write(self.directory / 'cases.json', {'cases': [self.case]})
        write(self.directory / 'relationships.json', self.relationships)
        answer = {'findings': [{'id': 'mechanism', 'path': 'A.java', 'start_line': 1,
            'end_line': 1, 'quote': 'marker();', 'explanation': 'A representative mechanism.'}]}
        negative = copy.deepcopy(answer)
        negative['findings'][0]['quote'] = 'not_source'
        repository = common.observation('java', 'candidate') / 'repository'
        self.citation = {'answer': answer, 'negative_answer': negative,
                        'positive': common.OBSERVE.grade(answer, self.case, repository),
                        'negative': common.OBSERVE.grade(negative, self.case, repository)}
        write(self.directory / 'citation-controls.json', self.citation)
        self.recognizer = SimpleNamespace(evidence=self.evidence)

    def patch(self, obj, name, **kwargs):
        patcher = mock.patch.object(obj, name, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def evidence(self, events, output, reviewed):
        item = events[0]['item']
        successful = item['exit_code'] == 0
        text = item['aggregated_output']
        source = successful and 'archive-source' in item['command'] and text in (
            '{"source":"marker();"}', 'source marker();\n')
        quotes = successful and 'archive-quotes' in item['command'] and text == '{"quotes":[{"quote":"marker();"}]}'
        relationship = successful and reviewed == self.relationships and (
            source or 'archive-neighbors' in item['command'] and text == 'reviewed edge\n')
        return {'relationship_used': bool(relationship), 'relationship_receipts': self.relationships if relationship else [],
                'quotes_used': bool(quotes), 'quote_receipts': [{'rows': 1}] if quotes else [],
                'source_calls_used': bool(source), 'source_call_receipts': [{'rows': 1}] if source else []}

    def fixture(self):
        rows = []
        specs = controls.specifications(self.relationships, self.citation)
        write(self.directory / 'control-raw/attempt.json', {'model_started': False, 'harness_pid': 1,
              'started_at': '2026-01-01T00:00:00+00:00', 'specifications': specs})
        for index, spec in enumerate(specs):
            output = common.observation('java', spec['condition'])
            argv = controls.command(output, spec['arguments'])
            body = {'relationship': 'reviewed edge\n', 'quotes': '{"quotes":[{"quote":"marker();"}]}',
                    'source_calls': '{"source":"marker();"}' if spec.get('format') == 'json' else 'source marker();\n',
                    'unavailable': ''}[spec['kind']]
            row = {**spec, 'argv': argv, 'cwd': str(output / 'repository'), 'stdout': body, 'stderr': '',
                   'return_code': 2 if spec['kind'] == 'unavailable' else 0,
                   'stdout_sha256': common.OBSERVE.sha(body.encode()), 'stderr_sha256': common.OBSERVE.sha(b''),
                   'stdout_base64': base64.b64encode(body.encode()).decode('ascii'), 'stderr_base64': '', 'timed_out': False}
            row['event'] = controls.event(argv, row, f'control-{index:03d}')
            write(self.directory / 'control-raw' / f'{index:03d}.json', row)
            row['recognition'] = controls.receipt_checks(row, output, self.relationships, self.recognizer)
            rows.append(row)
        saved = {'passed': True, 'model_started': False, 'preflight': self.preflight, 'postflight': self.preflight, 'rows': rows}
        write(self.directory / 'controls.json', saved)
        return saved

    def verify(self):
        return controls.verify_controls('java', self.case, self.preflight, self.recognizer)

    def test_complete_all_arm_format_controls_replay_without_external_calls(self):
        saved = self.fixture()
        self.assertEqual(len(saved['rows']), 9)
        self.verify()
        quotes = [row for row in saved['rows'] if row['kind'] == 'quotes']
        self.assertEqual({row['condition'] for row in quotes}, {'control', 'candidate'})

    def test_tampered_hash_duplicate_slot_and_missing_raw_receipt_rejected(self):
        original = self.fixture()
        for changed in ('hash', 'duplicate', 'recognition'):
            saved = copy.deepcopy(original)
            if changed == 'hash':
                saved['rows'][0]['stdout_sha256'] = 'forged'
            elif changed == 'duplicate':
                saved['rows'][1] = saved['rows'][0]
            else:
                saved['rows'][0]['recognition']['failed_command_rejected'] = False
            write(self.directory / 'controls.json', saved)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.verify()
        write(self.directory / 'controls.json', original)
        (self.directory / 'control-raw/000.json').unlink()
        with self.assertRaisesRegex(ValueError, 'raw control'):
            self.verify()

    def test_false_citation_and_extra_raw_artifact_rejected(self):
        self.fixture()
        write(self.directory / 'control-raw/extra.json', {})
        with self.assertRaisesRegex(ValueError, 'raw control'):
            self.verify()
        (self.directory / 'control-raw/extra.json').unlink()
        self.citation['positive']['passed'] = False
        write(self.directory / 'citation-controls.json', self.citation)
        with self.assertRaisesRegex(ValueError, 'Citation control'):
            self.verify()

    def test_failed_actual_control_result_is_saved_before_rejection_and_cannot_retry(self):
        self.patch(common, 'verify_observation', side_effect=lambda language, arm: self.preflight[arm])
        self.patch(common, 'module', return_value=self.recognizer)
        with mock.patch.object(subprocess, 'run', return_value=SimpleNamespace(
                returncode=1, stdout=b'', stderr=b'actual control failure')) as invoke:
            with self.assertRaisesRegex(ValueError, 'Positive control command failed'):
                controls.controls('java')
            invoke.assert_called_once()
        raw = common.read(self.directory / 'control-raw/000.json')
        self.assertEqual((raw['return_code'], raw['stderr']), (1, 'actual control failure'))
        self.assertFalse((self.directory / 'controls.json').exists())
        with self.assertRaisesRegex(ValueError, 'already attempted'):
            controls.controls('java')

    def test_timeout_attempt_is_reserved_partial_bytes_retained_and_retry_rejected(self):
        self.patch(common, 'verify_observation', side_effect=lambda language, arm: self.preflight[arm])
        self.patch(common, 'module', return_value=self.recognizer)
        timeout = subprocess.TimeoutExpired(['actual-control'], 120, output=b'partial\xff', stderr=b'timed out')
        with mock.patch.object(subprocess, 'run', side_effect=timeout) as invoke:
            with self.assertRaisesRegex(ValueError, 'original bytes retained'):
                controls.controls('java')
            with self.assertRaisesRegex(ValueError, 'already attempted'):
                controls.controls('java')
            invoke.assert_called_once()
        self.assertTrue((self.directory / 'control-raw/attempt.json').exists())
        raw = common.read(self.directory / 'control-raw/000.json')
        self.assertTrue(raw['timed_out'])
        self.assertIsNone(raw['return_code'])
        self.assertEqual(base64.b64decode(raw['stdout_base64']), b'partial\xff')
        self.assertEqual(raw['execution_error']['class'], 'TimeoutExpired')
        self.assertIn('decode_error', raw)
        self.assertNotIn('event', raw)

    def test_non_utf8_success_and_launch_failure_preserve_raw_attempt(self):
        specs = controls.specifications(self.relationships, self.citation)
        output = common.observation('java', 'candidate')
        for index, behavior in enumerate((SimpleNamespace(returncode=0, stdout=b'\xff', stderr=b''),
                                           FileNotFoundError('missing executable'))):
            with self.subTest(index=index), mock.patch.object(subprocess, 'run',
                    **({'side_effect': behavior} if isinstance(behavior, Exception) else {'return_value': behavior})):
                with self.assertRaisesRegex(ValueError, 'original bytes retained'):
                    controls.capture(specs[0], output, index, self.directory)
            raw = common.read(self.directory / 'control-raw' / f'{index:03d}.json')
            self.assertNotIn('event', raw)
            self.assertIn('decode_error' if index == 0 else 'execution_error', raw)


if __name__ == '__main__':
    unittest.main()
