"""Isolated prelaunch/provenance controls; never execute models or external commands."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


COHORT = Path(__file__).resolve().parents[1] / 'evals/overload-token-cohort'


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, COHORT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load_module('overload_protocol_prepare', 'prepare.py')
runner = load_module('overload_protocol_runner', 'run.py')
collector = load_module('overload_protocol_collector', 'collect.py')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value) + '\n').encode('utf-8'))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class OverloadTokenProtocolTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='overload-protocol-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.here = self.root / 'cohort'
        self.here.mkdir()
        # Any unstubbed subprocess/model path must fail, not launch a real command.
        self.command = self.patch(
            runner.subprocess, 'check_output',
            side_effect=AssertionError('External commands are forbidden in protocol tests'))
        self.patch(runner.observer, 'trial',
                   side_effect=AssertionError('Model calls are forbidden in protocol tests'))

    def patch(self, target, name, **kwargs):
        patcher = mock.patch.object(target, name, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def runtime_inventory(self):
        contents = {
            'SKILL.md': b'fixed skill\n',
            'references/saved-graph.md': b'fixed reference\n',
            'columbus.py': b'fixed entrypoint\n',
            'columbus_engine/presentation.py': b'fixed renderer\n',
        }
        committed = {}
        for name, raw in contents.items():
            relative = 'skills/columbus/' + (
                name if name == 'SKILL.md' or name.startswith('references/') else 'scripts/' + name)
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            committed[relative] = raw
        files = {name: sha(raw) for name, raw in contents.items()}
        for language in prepare.LANGUAGES:
            write_json(self.here / language / 'freeze.json', {'engine': {'files': files}})
        self.patch(prepare, 'HERE', new=self.here)
        self.patch(prepare, 'ROOT', new=self.root)

        def git_show(argv, **kwargs):
            self.assertEqual(argv[:2], ['git', 'show'])
            self.assertEqual(kwargs, {'cwd': self.root})
            commit, relative = argv[2].split(':', 1)
            self.assertEqual(commit, 'recorded-commit')
            return committed[relative]

        self.command.side_effect = git_show
        return files, committed

    def test_runtime_commit_accepts_matching_skill_reference_and_script_bytes(self):
        files, committed = self.runtime_inventory()
        prepare.verify_runtime_commit('recorded-commit')
        self.assertEqual(self.command.call_count, len(files) * len(prepare.LANGUAGES))
        checked = {call.args[0][2].split(':', 1)[1] for call in self.command.call_args_list}
        self.assertEqual(checked, set(committed))

    def test_runtime_commit_rejects_mixed_language_inventories(self):
        files, _ = self.runtime_inventory()
        write_json(self.here / 'kotlin/freeze.json',
                   {'engine': {'files': {**files, 'unexpected.py': sha(b'extra')}}})
        with self.assertRaisesRegex(ValueError, 'different runtime/skill inventories'):
            prepare.verify_runtime_commit('recorded-commit')
        # It rejects the differing catalog before trying to read its extra file.
        self.assertEqual(self.command.call_count, len(files))

    def test_runtime_commit_rejects_bytes_not_in_recorded_commit(self):
        _, committed = self.runtime_inventory()
        relative = 'skills/columbus/scripts/columbus.py'
        committed[relative] = b'different committed entrypoint\n'
        with self.assertRaisesRegex(ValueError, 'current recorded commit.*columbus.py'):
            prepare.verify_runtime_commit('recorded-commit')

    def test_runtime_commit_rejects_dirty_current_bytes(self):
        self.runtime_inventory()
        (self.root / 'skills/columbus/SKILL.md').write_bytes(b'uncommitted skill edit\n')
        with self.assertRaisesRegex(ValueError, 'current recorded commit.*SKILL.md'):
            prepare.verify_runtime_commit('recorded-commit')

    @contextlib.contextmanager
    def runner_fixture(self, language='java'):
        case = {'id': 'fixture-case'}
        manifest, engine = {'source_manifest': {}}, {'files': {}}
        observation = self.root / 'observations' / ('columbus-overload-token-' + language)
        write_json(self.here / language / 'cases.json', {'cases': [case]})
        write_json(self.here / language / 'freeze.json', {'manifest': manifest, 'engine': engine})
        write_json(observation / 'manifest.json', manifest)
        write_json(observation / 'engine.json', engine)
        write_json(self.here / 'environment.json', {'codex_cli': 'codex fixture-version'})
        tracked = self.root / 'runtime.py'
        tracked.write_bytes(b'frozen runtime bytes\n')
        write_json(self.here / 'input-hashes.json', {'runtime.py': sha(tracked.read_bytes())})
        gate = SimpleNamespace(frozen_inputs=mock.Mock(wraps=collector.frozen_inputs),
                               verify_observation=mock.Mock())
        loader = SimpleNamespace(exec_module=mock.Mock())
        result = {'return_code': 0, 'timed_out': False, 'usage': {'input_tokens': 1, 'output_tokens': 1},
                  'quality': {'passed': True}}
        observer = SimpleNamespace(dump=mock.Mock(), trial=mock.Mock(return_value=result))

        def cli_version(argv, **kwargs):
            self.assertEqual(argv, ['codex', '--version'])
            self.assertEqual(kwargs, {'text': True})
            return 'codex fixture-version\n'

        self.command.reset_mock()
        self.command.side_effect = cli_version
        with contextlib.ExitStack() as stack:
            for target, name, value in (
                (runner, 'HERE', self.here), (runner, 'observer', observer),
                (collector, 'HERE', self.here), (collector, 'ROOT', self.root),
            ):
                stack.enter_context(mock.patch.object(target, name, value))
            stack.enter_context(mock.patch.object(collector, 'required_inputs', return_value={'runtime.py'}))
            stack.enter_context(mock.patch.object(runner.importlib.util, 'spec_from_file_location',
                                                 return_value=SimpleNamespace(loader=loader)))
            stack.enter_context(mock.patch.object(runner.importlib.util, 'module_from_spec', return_value=gate))
            stack.enter_context(mock.patch.object(runner, 'Path', side_effect=lambda value: (
                self.root / 'observations' if value == '/tmp' else Path(value))))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            yield gate, observer, tracked, observation

    def test_verify_inputs_rejects_cli_mismatch_before_observation_gate(self):
        with self.runner_fixture() as (gate, observer, _, _):
            self.command.side_effect = None
            self.command.return_value = 'codex different-version\n'
            with self.assertRaisesRegex(ValueError, 'Codex CLI changed after freeze'):
                runner.verify_inputs('java')
            gate.frozen_inputs.assert_called_once_with()
            gate.verify_observation.assert_not_called()
            observer.trial.assert_not_called()

    def test_verify_inputs_accepts_cli_and_checks_requested_observation(self):
        with self.runner_fixture() as (gate, observer, _, _):
            runner.verify_inputs('java')
            gate.frozen_inputs.assert_called_once_with()
            gate.verify_observation.assert_called_once_with('java', observer)
            observer.trial.assert_not_called()

    def test_verify_inputs_stops_before_cli_when_frozen_bytes_changed(self):
        with self.runner_fixture() as (gate, observer, tracked, _):
            tracked.write_bytes(b'changed before launch\n')
            with self.assertRaisesRegex(collector.GateError, 'frozen input changed: runtime.py'):
                runner.verify_inputs('java')
            self.command.assert_not_called()
            gate.verify_observation.assert_not_called()
            observer.trial.assert_not_called()

    def test_runner_rechecks_inputs_immediately_before_every_balanced_launch(self):
        for language in ('java', 'kotlin', 'javascript'):
            with self.subTest(language=language), self.runner_fixture(language) as (gate, observer, _, observation):
                checkpoints = []

                def checked_trial(*args, **kwargs):
                    # One initial validation plus one immediately before each trial.
                    self.assertEqual(gate.frozen_inputs.call_count, len(checkpoints) + 2)
                    self.assertEqual(gate.verify_observation.call_count, len(checkpoints) + 2)
                    checkpoints.append((args[2], kwargs['repeat']))
                    return observer.trial.return_value

                observer.trial.side_effect = checked_trial
                runner.run(language)
                first = ['columbus', 'baseline'] if language == 'kotlin' else ['baseline', 'columbus']
                self.assertEqual(checkpoints, [(first[0], 1), (first[1], 1), (first[1], 2), (first[0], 2)])
                self.assertEqual(gate.frozen_inputs.call_count, 5)
                self.assertEqual(self.command.call_count, 5)
                for call in observer.trial.call_args_list:
                    self.assertEqual(call.args[:2], (observation, 'fixture-case'))
                    self.assertEqual({key: call.kwargs[key] for key in ('model', 'effort', 'timeout')},
                                     {'model': 'gpt-5.6-sol', 'effort': 'xhigh', 'timeout': 1200})

    def test_mutation_after_first_trial_prevents_second_trial(self):
        with self.runner_fixture() as (gate, observer, tracked, _):
            def first_trial(*args, **kwargs):
                tracked.write_bytes(b'mutated after the first trial\n')
                return observer.trial.return_value

            observer.trial.side_effect = first_trial
            with self.assertRaisesRegex(collector.GateError, 'frozen input changed: runtime.py'):
                runner.run('java')
            observer.trial.assert_called_once()
            self.assertEqual(observer.trial.call_args.args[2], 'baseline')
            self.assertEqual(observer.trial.call_args.kwargs['repeat'], 1)
            self.assertEqual(gate.frozen_inputs.call_count, 3)
            self.assertEqual(gate.verify_observation.call_count, 2)

    def order_fixture(self, language='java'):
        observation = self.root / ('order-' + language)
        case = {'id': 'fixture-case'}
        first = ['columbus', 'baseline'] if language == 'kotlin' else ['baseline', 'columbus']
        expected = [(first[0], 1), (first[1], 1), (first[1], 2), (first[0], 2)]
        trials = []
        for index, (condition, repeat) in enumerate(expected):
            trial = observation / 'trials' / f"{case['id']}-{condition}-{repeat}"
            write_json(trial / 'process.json', {'pid': 100 + index,
                                               'started_at': f'2026-01-01T00:00:0{index}+00:00'})
            (trial / 'stderr.log').write_bytes(b'')
            trials.append(trial)
        return observation, case, trials

    def test_order_accepts_both_balanced_arm_orders(self):
        for language in ('java', 'kotlin', 'javascript'):
            with self.subTest(language=language):
                observation, case, _ = self.order_fixture(language)
                collector.verify_order(observation, case, language)

    def test_order_rejects_missing_process_for_terminal_result(self):
        observation, case, trials = self.order_fixture()
        (trials[0] / 'process.json').unlink()
        write_json(trials[0] / 'result.json', {'return_code': 0})
        with self.assertRaisesRegex(collector.GateError, 'terminal result lacks original process record'):
            collector.verify_order(observation, case, 'java')

    def test_order_rejects_missing_raw_stderr(self):
        observation, case, trials = self.order_fixture()
        (trials[0] / 'stderr.log').unlink()
        with self.assertRaisesRegex(collector.GateError, 'raw stderr is missing'):
            collector.verify_order(observation, case, 'java')

    def test_order_rejects_invalid_process_identity(self):
        observation, case, trials = self.order_fixture()
        for pid in (True, 0, -1, '100', None):
            with self.subTest(pid=pid):
                write_json(trials[0] / 'process.json', {'pid': pid, 'started_at': '2026-01-01T00:00:00+00:00'})
                with self.assertRaisesRegex(collector.GateError, 'invalid process identity'):
                    collector.verify_order(observation, case, 'java')

    def test_order_rejects_timezone_free_and_non_increasing_start_times(self):
        observation, case, trials = self.order_fixture()
        for started, message in (
            ('2026-01-01T00:00:00', 'process start time lacks timezone'),
            ('2026-01-01T00:00:01+00:00', 'trial start order differs'),
            ('2026-01-01T00:00:02+00:00', 'trial start order differs'),
        ):
            with self.subTest(started_at=started):
                write_json(trials[0] / 'process.json', {'pid': 100, 'started_at': started})
                with self.assertRaisesRegex(collector.GateError, message):
                    collector.verify_order(observation, case, 'java')


if __name__ == '__main__':
    unittest.main()
