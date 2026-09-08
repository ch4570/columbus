"""Pure/stubbed source-call cohort protocol tests; never invoke a model or upstream code."""
from collections import Counter
from contextlib import redirect_stdout
import gzip
import hashlib
import importlib.util
import io
from itertools import permutations
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

COHORT = Path(__file__).resolve().parents[1] / 'evals/source-call-sites-cohort'


def forbidden(*args, **kwargs):
    raise AssertionError('Unstubbed external execution is forbidden in protocol tests')


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, COHORT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


with mock.patch.multiple(subprocess, Popen=forbidden, run=forbidden, check_output=forbidden):
    prepare = load('source_call_protocol_prepare', 'prepare.py')
    common = prepare.common
    runner = load('source_call_protocol_runner', 'run.py')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, ensure_ascii=False) + '\n').encode('utf-8'))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class SourceCallCohortProtocolTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='source-call-protocol-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.here = self.root / 'evals/source-call-sites-cohort'
        self.here.mkdir(parents=True)
        for module in (common, prepare):
            self.patch(module, 'HERE', new=self.here)
            self.patch(module, 'ROOT', new=self.root)
        self.patch(runner, 'HERE', new=self.here)
        self.patch(common, 'SCHEMA', new=self.here.parent / 'exploration/answer.schema.json')
        self.commands = self.patch(subprocess, 'check_output', side_effect=forbidden)
        self.launches = self.patch(subprocess, 'Popen', side_effect=forbidden)
        self.other = self.patch(subprocess, 'run', side_effect=forbidden)
        self.controls = self.patch(runner, 'verify_controls', return_value=None)
        self.codex = self.root / 'saved-codex'
        self.codex.write_bytes(b'fixture CLI executable bytes\n')
        self.patch(common.shutil, 'which', return_value=str(self.codex))
        self.disk = self.patch(common.shutil, 'disk_usage', return_value=SimpleNamespace(free=512 * 1024 * 1024))

    def patch(self, target, name, **kwargs):
        patcher = mock.patch.object(target, name, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def metadata_command(self, argv, **kwargs):
        if argv == [str(self.codex), '--version']:
            return 'codex fixture-version\n'
        self.assertEqual(argv, [sys.executable, '-m', 'pip', 'list', '--format=json'])
        return json.dumps([{'name': 'fixture-package', 'version': '1.0'}])

    def environment(self):
        value = {'observation_root': str(self.root / 'observations'), 'python': sys.version,
            'python_executable': sys.executable, 'codex_cli': 'codex fixture-version',
            'codex_executable': str(self.codex), 'codex_sha256': common.sha(self.codex),
            'packages': [{'name': 'fixture-package', 'version': '1.0'}]}
        write_json(self.here / 'environment.json', value)
        self.commands.side_effect = self.metadata_command
        return value

    def inventory(self):
        for variant in common.RUNTIME_COMMITS:
            path = self.here / 'runtimes' / variant / 'columbus.py'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture wrapper\n')
        for path in common.required_inputs():
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'frozen fixture input\n')
        hashes = {path.relative_to(self.root).as_posix(): common.sha(path) for path in common.required_inputs()}
        write_json(self.here / 'input-hashes.json', hashes)
        return hashes

    @staticmethod
    def graph_bytes():
        counts = dict(files=1, nodes=0, scopes=0, edges=0, references=0, imports=0, diagnostics=0)
        rows = [dict(record='manifest', data=dict(format='columbus-graph', version=1, revision='fixture')),
                dict(record='file', data=dict(path='a.py', hash=digest(b'VALUE = 1\n'), size=10)),
                dict(record='end', data=counts)]
        return gzip.compress((''.join(json.dumps(row) + '\n' for row in rows)).encode()), counts

    def observations(self):
        self.environment()
        case = {'id': 'fixture-case', 'question': 'Explain the fixture behavior.',
                'findings': [dict(id='value', description='Explain the value.', path='a.py',
                                 marker='VALUE = 1', call_lines=[1])]}
        write_json(self.here / 'java/cases.json', {'cases': [case]})
        verifier = self.here.parent / 'archive-exploration/preflight.py'
        verifier.parent.mkdir(parents=True)
        verifier.write_bytes(b'frozen verifier identity\n')
        frozen = {}
        for condition in common.CONDITIONS:
            output = common.observation('java', condition)
            (output / 'repository').mkdir(parents=True)
            (output / 'repository/a.py').write_bytes(b'VALUE = 1\n')
            (output / 'runtime').mkdir()
            (output / 'runtime/columbus.py').write_bytes(b'fixture runtime\n')
            (output / 'cases.json').write_bytes((self.here / 'java/cases.json').read_bytes())
            manifest = {'source_manifest': {'a.py': digest(b'VALUE = 1\n')}, 'arm': condition}
            write_json(output / 'manifest.json', manifest)
            graph, counts = self.graph_bytes()
            (output / 'graph.jsonl.xz').write_bytes(graph)
            expected = dict(archive_sha256=digest(graph), revision='fixture', counts=counts,
                source_manifest=manifest['source_manifest'], runtime_manifest=common.exact_manifest(output / 'runtime'),
                verifier_sha256=common.sha(verifier))
            engine = {'archive': expected}
            write_json(output / 'engine.json', engine)
            frozen[condition] = dict(manifest=manifest, engine=engine,
                manifest_sha256=common.sha(output / 'manifest.json'), engine_sha256=common.sha(output / 'engine.json'))
        write_json(self.here / 'java/freeze.json', frozen)
        return case

    def fake_processes(self, *, after=None, raw=None, return_code=0):
        def launch(argv, **kwargs):
            self.assertEqual(argv[:2], [str(self.codex), 'exec'])
            for argument in ('--ignore-user-config', '--ignore-rules', '--json', '--ephemeral', 'read-only'):
                self.assertIn(argument, argv)
            self.assertEqual(argv[argv.index('--model') + 1], 'gpt-5.6-sol')
            self.assertIn('model_reasoning_effort="xhigh"', argv)
            answer = Path(argv[argv.index('--output-last-message') + 1])
            write_json(answer, {'findings': [dict(id='value', path='a.py', start_line=1,
                end_line=1, quote='VALUE = 1', explanation='Fixture value is one.')]})
            payload = raw(argv) if callable(raw) else raw
            kwargs['stdout'].write(payload if payload is not None else (json.dumps({'type': 'turn.completed',
                'usage': {'input_tokens': 11, 'cached_input_tokens': 2, 'output_tokens': 3}}) + '\n').encode())

            def communicate(text, timeout):
                self.assertEqual(timeout, 1200)
                self.assertEqual(text, (answer.parent / 'prompt.txt').read_bytes())
                if after is not None:
                    after(answer.parent)

            return SimpleNamespace(pid=1234, returncode=return_code, communicate=communicate)
        self.launches.side_effect = launch

    def test_imports_are_model_free_and_ignore_another_cohorts_common(self):
        poison = SimpleNamespace(HERE='wrong cohort', EVIDENCE='wrong evidence')
        with mock.patch.dict(sys.modules, {'common': poison}):
            fresh = load('source_call_isolated_prepare', 'prepare.py')
            self.assertIs(fresh.common, common)
            self.assertIs(load('source_call_isolated_runner', 'run.py').common, common)
            helper = self.root / 'dependency.py'
            helper.write_text('from common import EVIDENCE\nidentity = EVIDENCE\n')
            self.assertIs(common.module('isolation_probe', helper).identity, common.EVIDENCE)
            self.assertIs(sys.modules['common'], poison)
            helper.write_text('from common import EVIDENCE\nraise ValueError("fixture import failure")\n')
            with self.assertRaisesRegex(ValueError, 'fixture import failure'):
                common.module('failed_isolation_probe', helper)
            self.assertIs(sys.modules['common'], poison)
        self.launches.assert_not_called()
        self.commands.assert_not_called()
        self.other.assert_not_called()

    def test_six_orders_balance_all_permutations_positions_and_carryover(self):
        orders = [tuple(order) for language in common.LANGUAGES for order in common.ORDERS[language]]
        self.assertEqual(Counter(orders), Counter(permutations(common.CONDITIONS)))
        for position in range(3):
            self.assertEqual(Counter(order[position] for order in orders), Counter(dict.fromkeys(common.CONDITIONS, 2)))
        self.assertEqual(Counter(pair for order in orders for pair in zip(order, order[1:])),
                         Counter({pair: 2 for pair in permutations(common.CONDITIONS, 2)}))
        for language in common.LANGUAGES:
            self.assertEqual(Counter(common.schedule(language)),
                             Counter((arm, repeat) for arm in common.CONDITIONS for repeat in (1, 2)))

    def test_save_validates_complete_json_and_utf8_before_creating_any_path(self):
        cyclic = []
        cyclic.append(cyclic)
        deep = 0
        for _ in range(sys.getrecursionlimit() + 20):
            deep = [deep]
        for name, value, error in (('surrogate', {'extra': '\ud800'}, UnicodeEncodeError),
                                   ('cycle', cyclic, ValueError), ('deep', deep, RecursionError),
                                   ('nonfinite', float('nan'), ValueError)):
            destination = self.root / name / 'result.json'
            with self.subTest(name=name), self.assertRaises(error):
                common.save(destination, value)
            self.assertFalse(destination.exists())
            self.assertFalse(destination.parent.exists())
        destination = self.root / 'valid.json'
        value = {'unicode': '한글', 'line': 'a\nb'}
        common.save(destination, value)
        self.assertEqual(destination.read_bytes(), common.serialize(value))
        with self.assertRaises(FileExistsError):
            common.save(destination, {'replacement': True})
        self.assertEqual(common.read(destination), value)

    def test_bounded_error_diagnostic_is_ascii_safe(self):
        value = runner.evaluation_error(ValueError('\ud800' * 1000))
        self.assertLessEqual(len(value['message']), 1024)
        self.assertTrue(value['message'].isascii())
        self.assertEqual(value['class'], 'ValueError')
        common.serialize(value)

    def test_prompts_allow_efficient_ordinary_reads_without_private_oracle_hints(self):
        case = {'question': 'Discover the implementation.', 'findings': [dict(id='mechanism',
            description='Explain the complete mechanism.', path='PRIVATE/FILE.java', marker='PRIVATE_MARKER', call_lines=[765432])]}
        for arm in common.CONDITIONS:
            text = common.prompt(case, arm, self.root / 'offered')
            self.assertIn('standard-library scripts to read source and serialize exact excerpts as JSON', text)
            self.assertIn('do not inspect sibling experiments', text)
            self.assertIn('Explain the complete mechanism.', text)
            for secret in ('PRIVATE/FILE.java', 'PRIVATE_MARKER', '765432', 'criteria.json', 'relationships.json'):
                self.assertNotIn(secret, text)
            self.assertEqual(str(self.root / 'offered/runtime/SKILL.md') in text, arm != 'baseline')

    def test_saved_cli_bytes_python_packages_and_disk_are_prelaunch_gates(self):
        environment = self.environment()
        common.verify_environment()
        for key, changed in (('python', 'other'), ('python_executable', '/other/python'),
                             ('codex_cli', 'other version'), ('codex_executable', '/other/codex'),
                             ('codex_sha256', '0' * 64), ('packages', [])):
            write_json(self.here / 'environment.json', {**environment, key: changed})
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'changed after freeze'):
                common.verify_environment()
        write_json(self.here / 'environment.json', environment)
        self.codex.write_bytes(b'changed CLI with same version\n')
        with self.assertRaisesRegex(ValueError, 'executable changed'):
            common.verify_environment()
        self.disk.return_value = SimpleNamespace(free=common.MIN_FREE_BYTES - 1)
        with self.assertRaisesRegex(ValueError, '256 MiB'):
            common.disk_guard(self.root)
        preparation_floor = common.MIN_FREE_BYTES + common.PREPARATION_BYTES
        self.assertEqual(preparation_floor, 384 * 1024 * 1024)
        before = common.exact_manifest(self.root)
        self.disk.return_value = SimpleNamespace(free=preparation_floor - 1)
        with self.assertRaisesRegex(ValueError, '384 MiB'):
            common.disk_guard(self.root / 'not-created', preparing=True)
        self.assertEqual(common.exact_manifest(self.root), before)
        self.disk.return_value = SimpleNamespace(free=preparation_floor)
        common.disk_guard(self.root / 'not-created', preparing=True)
        self.assertEqual(common.exact_manifest(self.root), before)
        self.disk.return_value = SimpleNamespace(free=common.MIN_FREE_BYTES)
        common.disk_guard(self.root)
        self.launches.assert_not_called()

    def test_frozen_inventory_hashes_dependencies_raw_controls_and_hidden_runtime_files(self):
        raw = self.here / 'java/control-raw/000.json'
        write_json(raw, {'stdout': 'retained control bytes'})
        hashes = self.inventory()
        self.assertEqual(common.frozen_inputs(), hashes)
        for suffix in ('evals/exploration/source_call_evidence.py', 'evals/quotes-three-arm/recognize.py',
                       'evals/archive-exploration/preflight.py', 'java/control-raw/000.json'):
            self.assertTrue(any(name.endswith(suffix) for name in hashes), suffix)
        raw.write_bytes(b'changed control\n')
        with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
            common.frozen_inputs()
        raw.write_text(json.dumps({'stdout': 'retained control bytes'}) + '\n')
        added = self.here / 'runtimes/candidate/__pycache__/hidden.pyc'
        added.parent.mkdir()
        added.write_bytes(b'unfrozen hidden executable')
        with self.assertRaisesRegex(ValueError, 'Incomplete input inventory'):
            common.frozen_inputs()

    def test_frozen_inventory_rejects_omitted_unsafe_and_deleted_inputs(self):
        hashes = self.inventory()
        removed = next(name for name in hashes if name.endswith('/PLAN.md'))
        write_json(self.here / 'input-hashes.json', {name: value for name, value in hashes.items() if name != removed})
        with self.assertRaisesRegex(ValueError, 'Incomplete input inventory'):
            common.frozen_inputs()
        write_json(self.here / 'input-hashes.json', {**hashes, '../outside': '0' * 64})
        with self.assertRaisesRegex(ValueError, 'Unsafe frozen input path'):
            common.frozen_inputs()
        write_json(self.here / 'input-hashes.json', hashes)
        (self.root / removed).unlink()
        with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
            common.frozen_inputs()

    def test_observation_exact_inventory_rejects_preflight_excluded_additions(self):
        self.observations()
        output = common.observation('java', 'candidate')
        self.assertTrue(common.verify_observation('java', 'candidate')['passed'])
        for relative in ('repository/.git/unfrozen', 'runtime/__pycache__/unfrozen.pyc'):
            path = output / relative
            path.parent.mkdir(parents=True)
            path.write_bytes(b'hidden addition\n')
            with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, 'Frozen source or runtime changed'):
                common.verify_observation('java', 'candidate')
            path.unlink()
        (output / 'repository/a.py').write_bytes(b'VALUE = 2\n')
        with self.assertRaisesRegex(ValueError, 'Frozen source or runtime changed'):
            common.verify_observation('java', 'candidate')

    def test_runner_checks_all_arms_before_and_after_every_saved_actual_event_stream(self):
        case = self.observations()
        self.inventory()
        self.fake_processes()
        frozen = self.patch(runner, 'frozen_inputs', wraps=common.frozen_inputs)
        environment = self.patch(runner, 'verify_environment', wraps=common.verify_environment)
        observations = self.patch(runner, 'verify_observation', wraps=common.verify_observation)
        with redirect_stdout(io.StringIO()):
            runner.run('java')
        self.assertEqual(self.launches.call_count, 6)
        self.assertEqual(frozen.call_count, 13)
        self.assertEqual(environment.call_count, 13)
        self.assertEqual(self.controls.call_count, 6)
        self.assertEqual(observations.call_args_list, [mock.call('java', arm) for _ in range(13) for arm in common.CONDITIONS])
        for arm, repeat in common.schedule('java'):
            output = common.observation('java', arm)
            trial = output / 'trials' / f'fixture-case-{arm}-{repeat}'
            result = common.read(trial / 'result.json')
            self.assertEqual(result['usage'], dict(input_tokens=11, cached_input_tokens=2,
                                                   output_tokens=3, uncached_input_tokens=9))
            self.assertEqual(result['events_sha256'], common.sha(trial / 'events.jsonl'))
            self.assertEqual(common.read(trial / 'invocation.json')['argv'], common.argv(output, trial))
            self.assertEqual((trial / 'prompt.txt').read_bytes(), common.prompt(case, arm, output).encode())
            self.assertTrue(result['quality']['passed'])

    def test_existing_trial_or_runner_evidence_cannot_resume(self):
        self.observations()
        self.inventory()
        existing = common.observation('java', 'control') / 'trials'
        existing.mkdir()
        with self.assertRaisesRegex(ValueError, 'never retry'):
            runner.run('java')
        existing.rmdir()
        write_json(common.observation('java', 'baseline').parent / 'runner.json', {'original': 'preserved'})
        with self.assertRaisesRegex(ValueError, 'never resume'):
            runner.run('java')
        self.launches.assert_not_called()

    def test_rejected_controls_or_low_disk_prevent_any_model_process(self):
        self.observations()
        self.inventory()
        self.controls.side_effect = ValueError('Retained control does not reproduce')
        with self.assertRaisesRegex(ValueError, 'control does not reproduce'):
            runner.run('java')
        self.launches.assert_not_called()
        self.assertFalse(any((common.observation('java', arm) / 'trials').exists() for arm in common.CONDITIONS))

    def test_integrity_failure_preserves_terminal_and_stops_without_retry(self):
        self.observations()
        self.inventory()
        changed = common.observation('java', 'control') / 'repository/unapproved.py'
        self.fake_processes(after=lambda _: changed.write_bytes(b'new evidence\n'))
        with self.assertRaisesRegex(ValueError, 'Frozen source or runtime changed'), redirect_stdout(io.StringIO()):
            runner.run('java')
        self.launches.assert_called_once()
        trial = common.observation('java', 'baseline') / 'trials/fixture-case-baseline-1'
        self.assertTrue((trial / 'terminal.json').is_file())
        self.assertFalse((trial / 'result.json').exists())

    def test_malformed_events_keep_raw_terminal_postflight_and_all_scheduled_slots(self):
        self.observations()
        self.inventory()
        raw = b'{malformed event}\n'
        self.fake_processes(raw=raw)
        observations = self.patch(runner, 'verify_observation', wraps=common.verify_observation)
        with redirect_stdout(io.StringIO()):
            runner.run('java')
        self.assertEqual(observations.call_count, 39)
        for arm, repeat in common.schedule('java'):
            trial = common.observation('java', arm) / 'trials' / f'fixture-case-{arm}-{repeat}'
            self.assertEqual((trial / 'events.jsonl').read_bytes(), raw)
            self.assertEqual(common.read(trial / 'terminal.json')['return_code'], 0)
            result = common.read(trial / 'result.json')
            self.assertEqual(result['evaluation_error']['class'], 'JSONDecodeError')
            self.assertIsNone(result['usage'])
            self.assertEqual(result['events_sha256'], common.sha(trial / 'events.jsonl'))
            self.assertTrue(result['answer']['findings'])
        with self.assertRaisesRegex(ValueError, 'never retry'):
            runner.run('java')
        self.assertEqual(self.launches.call_count, 6)

    def test_invalid_actual_usage_is_retained_without_fabricated_usage_or_missing_slots(self):
        self.observations()
        self.inventory()
        self.fake_processes(raw=b'{"type":"turn.completed","usage":{"input_tokens":true,"cached_input_tokens":0,"output_tokens":3}}\n')
        with redirect_stdout(io.StringIO()):
            runner.run('java')
        self.assertEqual(self.launches.call_count, 6)
        for arm, repeat in common.schedule('java'):
            trial = common.observation('java', arm) / 'trials' / f'fixture-case-{arm}-{repeat}'
            result = common.read(trial / 'result.json')
            self.assertIsNone(result['usage'])
            self.assertEqual(result['evaluation_error']['class'], 'ValueError')

    def test_first_malformed_slot_does_not_omit_later_valid_actual_events(self):
        self.observations()
        self.inventory()
        first = True

        def raw(argv):
            nonlocal first
            if first:
                first = False
                return b'{malformed first event}\n'
            return None

        self.fake_processes(raw=raw)
        with redirect_stdout(io.StringIO()):
            runner.run('java')
        self.assertEqual(self.launches.call_count, 6)
        for index, (arm, repeat) in enumerate(common.schedule('java')):
            result = common.read(common.observation('java', arm) / 'trials'
                                 / f'fixture-case-{arm}-{repeat}/result.json')
            if index == 0:
                self.assertIn('evaluation_error', result)
                self.assertIsNone(result['usage'])
            else:
                self.assertNotIn('evaluation_error', result)
                self.assertEqual(result['usage']['input_tokens'], 11)

    def assert_first_answer_serialization_failure_continues(self, extra_json, error_class):
        self.observations()
        self.inventory()
        original = None

        def replace_first_answer(directory):
            nonlocal original
            if original is None:
                path = directory / 'answer.json'
                original = path.read_bytes().rstrip()[:-1] + b',"extra":' + extra_json + b'}\n'
                path.write_bytes(original)

        self.fake_processes(after=replace_first_answer)
        with redirect_stdout(io.StringIO()):
            runner.run('java')
        self.assertEqual(self.launches.call_count, 6)
        for index, (arm, repeat) in enumerate(common.schedule('java')):
            trial = common.observation('java', arm) / 'trials' / f'fixture-case-{arm}-{repeat}'
            result = common.read(trial / 'result.json')
            if index == 0:
                self.assertEqual((trial / 'answer.json').read_bytes(), original)
                self.assertEqual(result['evaluation_error']['class'], error_class)
                self.assertEqual(result['answer'], {})
                self.assertFalse(result['quality']['passed'])
                self.assertIn('could not be serialized', result['quality']['note'])
                self.assertIsNone(result['usage'])
                self.assertNotIn('commands', result)
                self.assertEqual(result['events_sha256'], common.sha(trial / 'events.jsonl'))
                self.assertEqual(set(result['preflight']), set(common.CONDITIONS))
                self.assertEqual(set(result['postflight']), set(common.CONDITIONS))
                self.assertEqual(result['return_code'], common.read(trial / 'terminal.json')['return_code'])
            else:
                self.assertNotIn('evaluation_error', result)
                self.assertTrue(result['quality']['passed'])
                self.assertEqual(result['usage']['input_tokens'], 11)

    def test_escaped_lone_surrogate_extra_answer_is_preserved_without_omitting_slots(self):
        self.assert_first_answer_serialization_failure_continues(b'"\\ud800"', 'UnicodeEncodeError')

    def test_deep_json_extra_answer_is_preserved_without_omitting_slots(self):
        # Use the live stack depth, not a fixed 990-level value: unittest and
        # direct discovery add different numbers of frames. JSON decoding fits,
        # but encoding the enclosing result reaches the recursion boundary.
        frame, frames = sys._getframe(), 0
        while frame is not None:
            frames += 1
            frame = frame.f_back
        depth = sys.getrecursionlimit() - frames - 7
        self.assert_first_answer_serialization_failure_continues(b'[' * depth + b'0' + b']' * depth, 'RecursionError')

    def test_answer_permission_error_is_a_hard_failure_not_a_model_error(self):
        self.observations()
        self.inventory()
        self.fake_processes()
        original_read = runner.read

        def denied(path):
            if Path(path).name == 'answer.json':
                raise PermissionError('fixture answer permission denial')
            return original_read(path)

        self.patch(runner, 'read', side_effect=denied)
        with self.assertRaisesRegex(PermissionError, 'answer permission denial'), redirect_stdout(io.StringIO()):
            runner.run('java')
        self.launches.assert_called_once()
        trial = common.observation('java', 'baseline') / 'trials/fixture-case-baseline-1'
        self.assertTrue((trial / 'terminal.json').is_file())
        self.assertFalse((trial / 'result.json').exists())

    def test_result_write_permission_error_is_a_hard_failure_not_a_model_error(self):
        self.observations()
        self.inventory()
        self.fake_processes()
        original_save = common.save_serialized

        def denied(path, value):
            if Path(path).name == 'result.json':
                raise PermissionError('fixture result permission denial')
            return original_save(path, value)

        self.patch(common, 'save_serialized', side_effect=denied)
        with self.assertRaisesRegex(PermissionError, 'result permission denial'), redirect_stdout(io.StringIO()):
            runner.run('java')
        self.launches.assert_called_once()
        trial = common.observation('java', 'baseline') / 'trials/fixture-case-baseline-1'
        self.assertTrue((trial / 'terminal.json').is_file())
        self.assertFalse((trial / 'result.json').exists())

    def test_timeout_records_real_terminal_status_without_extra_launches(self):
        self.observations()
        self.inventory()
        signals = self.patch(runner.os, 'killpg', create=True)
        processes = []

        def launch(argv, **kwargs):
            process = SimpleNamespace(pid=1234, returncode=None, terminate=mock.Mock(), kill=mock.Mock())
            processes.append(process)

            def communicate(text, timeout):
                self.assertEqual(timeout, 1200)
                raise subprocess.TimeoutExpired(argv, timeout)

            def wait(timeout=None):
                if timeout is not None:
                    self.assertEqual(timeout, 10)
                    raise subprocess.TimeoutExpired(argv, timeout)
                process.returncode = -9
                return process.returncode

            process.communicate, process.wait = communicate, wait
            return process

        self.launches.side_effect = launch
        with redirect_stdout(io.StringIO()):
            runner.run('java')
        self.assertEqual(self.launches.call_count, 6)
        if runner.os.name == 'nt':
            for process in processes:
                process.terminate.assert_called_once()
                process.kill.assert_called_once()
        else:
            self.assertEqual(signals.call_count, 12)
        for arm, repeat in common.schedule('java'):
            trial = common.observation('java', arm) / 'trials' / f'fixture-case-{arm}-{repeat}'
            terminal = common.read(trial / 'terminal.json')
            self.assertTrue(terminal['timed_out'])
            self.assertEqual(terminal['return_code'], -9)
            self.assertIsNone(common.read(trial / 'result.json')['usage'])

    def test_terminal_model_failures_retain_every_scheduled_slot_without_retries(self):
        self.observations()
        self.inventory()
        self.fake_processes(raw=b'{"type":"turn.failed","error":{"message":"fixture failure"}}\n', return_code=7)
        with redirect_stdout(io.StringIO()):
            runner.run('java')
        self.assertEqual(self.launches.call_count, 6)
        for arm, repeat in common.schedule('java'):
            trial = common.observation('java', arm) / 'trials' / f'fixture-case-{arm}-{repeat}'
            result = common.read(trial / 'result.json')
            self.assertEqual(result['return_code'], 7)
            self.assertIsNone(result['usage'])
            self.assertTrue(result['turn_failed'])

    def test_prepare_existing_paths_and_copy_destinations_never_overwrite(self):
        target = self.root / 'observations'
        target.mkdir()
        with self.assertRaisesRegex(ValueError, 'Preparation exists'):
            prepare.prepare(target)
        destination = self.root / 'retained'
        destination.write_bytes(b'preserve me')
        with self.assertRaises(FileExistsError):
            prepare.copy_new(self.codex, destination)
        self.assertEqual(destination.read_bytes(), b'preserve me')
        self.commands.assert_not_called()
        self.launches.assert_not_called()

    def preparation_fixture(self):
        fixture = self.root / 'source.zip'
        with zipfile.ZipFile(fixture, 'w') as archive:
            archive.writestr('fixture/a.py', b'VALUE = 1\n')
        source_manifest = {'a.py': digest(b'VALUE = 1\n')}
        source = {'fixture': str(fixture), 'fixture_sha256': common.sha(fixture), 'fixture_prefix': 'fixture/',
            'repository': 'fixture-repository', 'commit': 'fixture-commit', 'source_files': 1, 'source_bytes': 10,
            'corpus_manifest_sha256': digest(json.dumps(source_manifest, sort_keys=True, separators=(',', ':')).encode())}
        sources = {language: source for language in common.LANGUAGES}
        write_json(self.here / 'sources.json', sources)
        for language in common.LANGUAGES:
            write_json(self.here / language / 'source.json', {'repository': source['repository'], 'commit': source['commit'],
                       'sha256': source['fixture_sha256'], 'files': source['source_files']})
            write_json(self.here / language / 'cases.json', {'cases': [{'id': language + '-fixture-case', 'findings':
                [dict(id='value', path='a.py', marker='VALUE = 1')]}]})
        verifier = self.here.parent / 'archive-exploration/preflight.py'
        verifier.parent.mkdir()
        verifier.write_bytes(b'verifier fixture\n')
        self.patch(prepare.platform, 'platform', return_value='fixture-platform')
        graph, counts = self.graph_bytes()
        historical = self.root / 'original-historical-artifacts'
        historical.mkdir()
        graph_path = historical / 'graph.jsonl.xz'
        graph_path.write_bytes(graph)
        (historical / '.git').mkdir()
        (historical / '.git/original').write_bytes(b'preserve original metadata\n')
        receipts = {language: dict(fixture=str(graph_path), fixture_sha256=digest(graph),
            revision='fixture', counts=counts, source_manifest=source_manifest,
            producer_commit='historical-producer-commit',
            index=dict(files=1, symbols=1, edges=0, indexed_bytes=10, revision='fixture'),
            historical_cold_index_seconds=1.25, historical_cold_export_seconds=0.75)
            for language in common.LANGUAGES}
        write_json(self.here / 'graph-bindings.json', receipts)
        phases = []

        def checked(actual_sources, actual_bindings):
            self.assertEqual(actual_sources, sources)
            self.assertEqual(actual_bindings, receipts)
            self.assertFalse((self.root / 'fresh-observations').exists())
            self.assertFalse((self.here / 'environment.json').exists())
            self.assertFalse((self.here / 'runtimes').exists())
            for language in common.LANGUAGES:
                self.assertFalse((self.here / language / 'source.zip').exists())
                self.assertFalse((self.here / language / 'graph-reuse.json').exists())
            self.commands.assert_not_called()
            self.other.assert_not_called()
            phases.append('reuse-check')
            return receipts

        reuse = mock.Mock(side_effect=checked)

        def reuse_module(name, path):
            self.assertEqual((name, Path(path)), ('graph_reuse', self.here / 'reuse.py'))
            return SimpleNamespace(check_bindings=reuse)

        self.patch(common, 'module', side_effect=reuse_module)

        def exported(variant):
            self.assertTrue(reuse.called)
            self.assertEqual(phases[0], 'reuse-check')
            phases.append('export-' + variant)
            payloads = {'columbus.py': b'wrapper\n', 'columbus/__init__.py': b'core\n'}
            payloads.update({name: variant.encode() for name in common.RUNTIME_DELTA if name != 'columbus/source_calls.py'})
            if variant == 'candidate':
                payloads['columbus/source_calls.py'] = b'optional source calls\n'
            for name, data in payloads.items():
                path = self.here / 'runtimes' / variant / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            return {name: digest(data) for name, data in payloads.items()}

        def git_init(argv, **kwargs):
            self.assertEqual(argv[:3], ['git', 'init', '-q'])
            (Path(argv[3]) / '.git').mkdir()
            return SimpleNamespace(returncode=0)

        exports = self.patch(prepare, 'export_runtime', side_effect=exported)
        self.other.side_effect = git_init
        # This strict metadata stub rejects every sync/archive/runtime process.
        self.commands.side_effect = self.metadata_command
        removed = self.patch(prepare, '_remove_generated', wraps=prepare._remove_generated)
        return SimpleNamespace(receipts=receipts, historical=historical, graph=graph, sources=sources,
                               source_manifest=source_manifest, reuse=reuse, exports=exports,
                               removed=removed, phases=phases)

    def test_prepare_stubbed_fresh_source_only_consumers_share_identical_graph(self):
        fixture = self.preparation_fixture()
        original = common.exact_manifest(fixture.historical)
        self.disk.return_value = SimpleNamespace(free=common.MIN_FREE_BYTES + common.PREPARATION_BYTES)
        prepare.prepare(self.root / 'fresh-observations')
        self.assertEqual(fixture.phases, ['reuse-check', 'export-control', 'export-candidate'])
        fixture.reuse.assert_called_once()
        self.assertEqual(common.exact_manifest(fixture.historical), original)
        self.assertEqual(common.read(self.here / 'environment.json')['preparation_mode'], 'historical_graph_reuse')
        for language in common.LANGUAGES:
            frozen = common.read(self.here / language / 'freeze.json')
            self.assertEqual(set(frozen), set(common.CONDITIONS))
            self.assertEqual((self.here / language / 'graph.jsonl.xz').read_bytes(), fixture.graph)
            self.assertEqual(common.read(self.here / language / 'graph-reuse.json'), fixture.receipts[language])
            preparation = common.read(self.here / language / 'preparation.json')
            self.assertEqual(preparation['mode'], 'historical_graph_reuse')
            self.assertIsNone(preparation['new_cold_index_seconds'])
            self.assertIsNone(preparation['new_cold_export_seconds'])
            for arm in common.CONDITIONS:
                output = common.observation(language, arm)
                variant = 'control' if arm == 'control' else 'candidate'
                self.assertEqual(common.exact_manifest(output / 'repository'), fixture.source_manifest)
                self.assertEqual(sorted(path.name for path in (output / 'repository').iterdir()), ['a.py'])
                self.assertEqual(common.exact_manifest(output / 'runtime'),
                                 common.exact_manifest(self.here / 'runtimes' / variant))
                self.assertEqual((output / 'graph.jsonl.xz').read_bytes(), fixture.graph)
                engine = frozen[arm]['engine']
                self.assertEqual(engine['runtime_commit'], common.RUNTIME_COMMITS[variant])
                self.assertEqual(engine['graph_producer_commit'], 'historical-producer-commit')
                self.assertEqual(engine['historical_index'], fixture.receipts[language]['index'])
                self.assertEqual(engine['historical_cold_index_seconds'], 1.25)
                self.assertEqual(engine['historical_cold_export_seconds'], 0.75)
                self.assertIsNone(engine['new_cold_index_seconds'])
                self.assertIsNone(engine['new_cold_export_seconds'])
                self.assertEqual(engine['graph_reuse_receipt_sha256'], common.sha(self.here / language / 'graph-reuse.json'))
                self.assertIsNone(prepare.verify_retained(language, arm))
                self.assertTrue(common.verify_observation(language, arm)['passed'])
        self.assertEqual(fixture.removed.call_count, 9)
        self.assertTrue(all(call.args[1] == '.git' for call in fixture.removed.call_args_list))
        self.assertEqual(self.other.call_count, 9)
        self.assertEqual(self.commands.call_count, 2)  # CLI version and pip metadata only.
        self.launches.assert_not_called()

    def test_retained_runtime_receipt_zip_and_graph_tampering_are_rejected(self):
        self.preparation_fixture()
        prepare.prepare(self.root / 'fresh-observations')
        for variant in common.RUNTIME_COMMITS:
            path = self.here / 'runtimes' / variant / 'columbus.py'
            original = path.read_bytes()
            path.write_bytes(original + b'changed exported runtime\n')
            try:
                with self.subTest(variant=variant), self.assertRaisesRegex(ValueError, 'Retained runtime differs'):
                    prepare.verify_retained('java', variant)
            finally:
                path.write_bytes(original)
        for language in common.LANGUAGES:
            for filename in ('graph-reuse.json', 'source.zip', 'graph.jsonl.xz'):
                path = self.here / language / filename
                original = path.read_bytes()
                if filename == 'graph-reuse.json':
                    receipt = json.loads(original)
                    receipt['producer_commit'] = 'falsely-attributed-producer'
                    write_json(path, receipt)
                else:
                    path.write_bytes(original + b'changed retained bytes')
                try:
                    for arm in common.CONDITIONS:
                        with self.subTest(language=language, arm=arm, artifact=filename), self.assertRaises(ValueError):
                            prepare.verify_retained(language, arm)
                finally:
                    path.write_bytes(original)
                for arm in common.CONDITIONS:
                    self.assertIsNone(prepare.verify_retained(language, arm))
        self.launches.assert_not_called()

    def test_retained_receipt_claims_must_match_prepared_engine_not_only_a_rehashed_receipt(self):
        self.preparation_fixture()
        prepare.prepare(self.root / 'fresh-observations')
        receipt_path = self.here / 'java/graph-reuse.json'
        freeze_path = self.here / 'java/freeze.json'
        receipt_raw, freeze_raw = receipt_path.read_bytes(), freeze_path.read_bytes()
        mismatches = {'producer_commit': 'different-producer', 'fixture_sha256': '0' * 64,
                      'revision': 'different-revision', 'counts': {}, 'source_manifest': {}}
        for field, value in mismatches.items():
            changed = json.loads(receipt_raw)
            changed[field] = value
            write_json(receipt_path, changed)
            frozen = json.loads(freeze_raw)
            frozen['candidate']['engine']['graph_reuse_receipt_sha256'] = common.sha(receipt_path)
            write_json(freeze_path, frozen)
            try:
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'reuse receipt differs'):
                    prepare.verify_retained('java', 'candidate')
            finally:
                receipt_path.write_bytes(receipt_raw)
                freeze_path.write_bytes(freeze_raw)
        frozen = json.loads(freeze_raw)
        frozen['candidate']['engine']['runtime_commit'] = common.RUNTIME_COMMITS['control']
        write_json(freeze_path, frozen)
        try:
            with self.assertRaisesRegex(ValueError, 'Retained runtime differs'):
                prepare.verify_retained('java', 'candidate')
        finally:
            freeze_path.write_bytes(freeze_raw)
        self.assertIsNone(prepare.verify_retained('java', 'candidate'))
        self.launches.assert_not_called()

    def test_invalid_graph_reuse_rejects_before_material_preparation(self):
        fixture = self.preparation_fixture()
        original_inputs = common.exact_manifest(self.here)
        original_history = common.exact_manifest(fixture.historical)
        fixture.reuse.side_effect = ValueError('Historical producer/source binding changed')
        with self.assertRaisesRegex(ValueError, 'producer/source binding changed'):
            prepare.prepare(self.root / 'fresh-observations')
        fixture.reuse.assert_called_once()
        fixture.exports.assert_not_called()
        fixture.removed.assert_not_called()
        self.assertFalse((self.root / 'fresh-observations').exists())
        self.assertEqual(common.exact_manifest(self.here), original_inputs)
        self.assertEqual(common.exact_manifest(fixture.historical), original_history)
        self.commands.assert_not_called()
        self.other.assert_not_called()
        self.launches.assert_not_called()

    def test_preparation_disk_reserve_rejects_before_any_material_output(self):
        fixture = self.preparation_fixture()
        original_inputs = common.exact_manifest(self.here)
        self.disk.return_value = SimpleNamespace(free=common.MIN_FREE_BYTES + common.PREPARATION_BYTES - 1)
        with self.assertRaisesRegex(ValueError, '384 MiB'):
            prepare.prepare(self.root / 'fresh-observations')
        self.assertEqual(common.exact_manifest(self.here), original_inputs)
        self.assertFalse((self.root / 'fresh-observations').exists())
        fixture.reuse.assert_not_called()
        fixture.exports.assert_not_called()
        self.commands.assert_not_called()
        self.other.assert_not_called()
        self.launches.assert_not_called()

    def test_changed_graph_copy_rejects_and_preserves_original_artifact(self):
        fixture = self.preparation_fixture()
        original = common.exact_manifest(fixture.historical)
        copy_new = prepare.copy_new

        def corrupt_copy(source, destination):
            copy_new(source, destination)
            if Path(source) == fixture.historical / 'graph.jsonl.xz':
                with Path(destination).open('ab') as stream:
                    stream.write(b'changed copied graph')

        self.patch(prepare, 'copy_new', side_effect=corrupt_copy)
        with self.assertRaisesRegex(ValueError, 'Historical graph changed during copy'):
            prepare.prepare(self.root / 'fresh-observations')
        self.assertEqual(common.exact_manifest(fixture.historical), original)
        self.assertFalse((self.here / 'java/freeze.json').exists())
        self.assertFalse((self.here / 'java/graph.jsonl.xz').exists())
        self.assertFalse(common.observation('java', 'control').exists())
        self.assertFalse(common.observation('java', 'baseline').exists())
        candidate = common.observation('java', 'candidate')
        self.assertTrue((candidate / 'graph.jsonl.xz').is_file())
        fixture.removed.assert_not_called()
        self.assertEqual(self.commands.call_count, 2)
        self.launches.assert_not_called()

    def test_changed_retained_graph_copy_cannot_become_a_new_frozen_identity(self):
        fixture = self.preparation_fixture()
        original = common.exact_manifest(fixture.historical)
        copy_new = prepare.copy_new

        def corrupt_copy(source, destination):
            copy_new(source, destination)
            if Path(destination) == self.here / 'java/graph.jsonl.xz':
                with Path(destination).open('ab') as stream:
                    stream.write(b'changed retained graph')

        self.patch(prepare, 'copy_new', side_effect=corrupt_copy)
        with self.assertRaises(ValueError):
            prepare.prepare(self.root / 'fresh-observations')
        self.assertEqual(common.exact_manifest(fixture.historical), original)
        self.assertFalse((self.here / 'java/freeze.json').exists())
        self.assertEqual((common.observation('java', 'candidate') / 'graph.jsonl.xz').read_bytes(), fixture.graph)
        self.assertFalse(common.observation('java', 'baseline').exists())
        self.launches.assert_not_called()

    def test_changed_copied_runtime_cannot_be_attributed_to_the_pinned_commit(self):
        fixture = self.preparation_fixture()
        copytree = prepare.shutil.copytree

        def corrupt_copy(source, destination, *args, **kwargs):
            result = copytree(source, destination, *args, **kwargs)
            if Path(destination).name == 'runtime':
                (Path(destination) / 'columbus.py').write_bytes(b'not the pinned wrapper bytes\n')
            return result

        self.patch(prepare.shutil, 'copytree', side_effect=corrupt_copy)
        with self.assertRaises(ValueError):
            prepare.prepare(self.root / 'fresh-observations')
        self.assertEqual((self.here / 'runtimes/candidate/columbus.py').read_bytes(), b'wrapper\n')
        self.assertFalse((self.here / 'java/freeze.json').exists())
        self.assertFalse((common.observation('java', 'candidate') / 'engine.json').exists())
        self.launches.assert_not_called()

    def test_preparation_removal_helper_rejects_non_git_metadata(self):
        output = self.root / 'fresh-observation'
        cache = output / 'repository/.columbus'
        cache.mkdir(parents=True)
        (cache / 'preserve').write_bytes(b'not a generated git directory')
        with self.assertRaisesRegex(ValueError, 'newly generated'):
            prepare._remove_generated(output, '.columbus')
        self.assertEqual((cache / 'preserve').read_bytes(), b'not a generated git directory')
        self.launches.assert_not_called()

    def test_actual_historical_provenance_schemas_bind_without_a_source_zip(self):
        sources = common.read(COHORT / 'sources.json')
        for language in common.LANGUAGES:
            with self.subTest(language=language):
                prepare.check_provenance(sources[language], common.read(COHORT / language / 'source.json'))
        self.launches.assert_not_called()
        self.commands.assert_not_called()

    def test_historical_provenance_alias_conflicts_are_not_silently_preferred(self):
        source = common.read(COHORT / 'sources.json')['kotlin']
        historical = common.read(COHORT / 'kotlin/source.json')
        for key, bad in (('commit', 'other-pin'), ('sha256', '0' * 64), ('files', 1),
                         ('archive_prefix', 'other/'), ('source_bytes', 0), ('corpus_manifest_sha256', '0' * 64)):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'differs or has conflicting aliases'):
                prepare.check_provenance(source, {**historical, key: bad})
        with self.assertRaisesRegex(ValueError, 'Spring license hash'):
            prepare.check_provenance(source, {**historical, 'license':
                {**historical['license'], 'upstream_sha256': '0' * 64}})
        matching_aliases = {**historical, 'commit': historical['source_commit'],
                           'files': historical['source_files'], 'sha256': historical['fixture_sha256']}
        prepare.check_provenance(source, matching_aliases)

    def test_runtime_export_uses_only_pinned_git_blobs(self):
        committed = {'skills/columbus/SKILL.md': b'pinned skill',
            'skills/columbus/references/archive.md': b'pinned help',
            'skills/columbus/scripts/columbus.py': b'pinned wrapper',
            'skills/columbus/scripts/columbus/__init__.py': b'pinned core',
            'skills/columbus/scripts/tests/not_runtime.py': b'not runtime'}
        for variant, commit in common.RUNTIME_COMMITS.items():
            def command(argv, **kwargs):
                self.assertEqual(kwargs['cwd'], self.root)
                if argv[:2] == ['git', 'ls-tree']:
                    self.assertEqual(argv[4], commit)
                    return '\n'.join(committed)
                self.assertEqual(argv[:2], ['git', 'show'])
                revision, name = argv[2].split(':', 1)
                self.assertEqual(revision, commit)
                return committed[name]
            self.commands.side_effect = command
            exported = prepare.export_runtime(variant)
            target = self.here / 'runtimes' / variant
            self.assertEqual((target / 'columbus.py').read_bytes(), b'pinned wrapper')
            self.assertEqual(exported, common.exact_manifest(target))
            self.assertFalse((target / 'tests').exists())
            with self.assertRaisesRegex(ValueError, 'already exists'):
                prepare.export_runtime(variant)
        self.launches.assert_not_called()


if __name__ == '__main__':
    unittest.main()
