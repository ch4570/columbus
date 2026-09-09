"""Pure/stubbed prospective protocol tests; no model or upstream commands run."""
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


COHORT = Path(__file__).resolve().parents[1] / 'evals/quotes-three-arm'


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, COHORT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def forbidden(*args, **kwargs):
    raise AssertionError('Unstubbed external execution is forbidden in protocol tests')


with mock.patch.multiple(subprocess, Popen=forbidden, run=forbidden, check_output=forbidden):
    common = load('quotes_protocol_common', 'common.py')
    with mock.patch.dict(sys.modules, {'common': common}):
        prepare = load('quotes_protocol_prepare', 'prepare.py')
        runner = load('quotes_protocol_runner', 'run.py')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, ensure_ascii=False) + '\n').encode('utf-8'))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class QuotesThreeArmProtocolTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='quotes-protocol-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.here = self.root / 'evals/quotes-three-arm'
        self.here.mkdir(parents=True)
        for module in (common, prepare):
            self.patch(module, 'HERE', new=self.here)
            self.patch(module, 'ROOT', new=self.root)
        self.patch(runner, 'HERE', new=self.here)
        self.commands = self.patch(subprocess, 'check_output', side_effect=forbidden)
        self.launches = self.patch(subprocess, 'Popen', side_effect=forbidden)
        self.patch(subprocess, 'run', side_effect=forbidden)
        self.controls = self.patch(runner, 'verify_controls', return_value=None)

    def patch(self, target, name, **kwargs):
        patcher = mock.patch.object(target, name, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def environment(self):
        value = {'observation_root': str(self.root / 'observations'), 'python': sys.version,
                 'python_executable': sys.executable, 'codex_cli': 'codex fixture-version',
                 'packages': [{'name': 'fixture-package', 'version': '1.0'}]}
        write_json(self.here / 'environment.json', value)

        def command(argv, **kwargs):
            self.assertEqual(kwargs, {'text': True})
            if argv == ['codex', '--version']:
                return value['codex_cli'] + '\n'
            self.assertEqual(argv, [sys.executable, '-m', 'pip', 'list', '--format=json'])
            return json.dumps(value['packages'])

        self.commands.side_effect = command
        return value

    def inventory(self):
        for variant in ('control', 'quotes'):
            path = self.here / 'runtimes' / variant / 'columbus.py'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'exported fixture wrapper\n')
        for path in common.required_inputs():
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'frozen fixture input\n')
        hashes = {path.relative_to(self.root).as_posix(): common.sha(path)
                  for path in common.required_inputs()}
        write_json(self.here / 'input-hashes.json', hashes)
        return hashes

    @staticmethod
    def graph_bytes(source_hash):
        counts = dict(files=1, nodes=0, scopes=0, edges=0, references=0, imports=0, diagnostics=0)
        rows = [dict(record='manifest', data=dict(format='columbus-graph', version=1, revision='fixture')),
                dict(record='file', data=dict(path='a.py', hash=source_hash, size=10)),
                dict(record='end', data=counts)]
        return gzip.compress((''.join(json.dumps(row) + '\n' for row in rows)).encode()), counts

    def observations(self, language='java'):
        self.environment()
        case = {'id': 'fixture-case', 'question': 'Explain the fixture behavior.',
                'findings': [dict(id='value', description='Explain the value.', path='a.py',
                                 marker='VALUE = 1', call_lines=[1])]}
        write_json(self.here / language / 'cases.json', {'cases': [case]})
        frozen = {}
        for condition in common.CONDITIONS:
            output = common.observation(language, condition)
            (output / 'repository').mkdir(parents=True)
            (output / 'repository/a.py').write_bytes(b'VALUE = 1\n')
            (output / 'runtime').mkdir()
            (output / 'runtime/columbus.py').write_bytes(b'fixture runtime\n')
            (output / 'cases.json').write_bytes((self.here / language / 'cases.json').read_bytes())
            manifest = {'source_manifest': {'a.py': digest(b'VALUE = 1\n')}, 'arm': condition}
            write_json(output / 'manifest.json', manifest)
            graph, counts = self.graph_bytes(manifest['source_manifest']['a.py'])
            (output / 'graph.jsonl.xz').write_bytes(graph)
            expected = dict(archive_sha256=digest(graph), revision='fixture', counts=counts,
                            source_manifest=manifest['source_manifest'],
                            runtime_manifest=common.PREFLIGHT.file_manifest(output / 'runtime'))
            engine = {'archive': expected}
            write_json(output / 'engine.json', engine)
            frozen[condition] = dict(manifest=manifest, engine=engine,
                manifest_sha256=common.sha(output / 'manifest.json'), engine_sha256=common.sha(output / 'engine.json'))
        write_json(self.here / language / 'freeze.json', frozen)
        return case

    def fake_processes(self, after=None, *, events_raw=None, return_code=0):
        def launch(argv, **kwargs):
            self.assertEqual(argv[:2], ['codex', 'exec'])
            self.assertIn('--ignore-user-config', argv)
            self.assertIn('read-only', argv)
            answer_path = Path(argv[argv.index('--output-last-message') + 1])
            write_json(answer_path, {'findings': [dict(id='value', path='a.py', start_line=1,
                end_line=1, quote='VALUE = 1', explanation='Fixture value is one.')]})
            kwargs['stdout'].write(events_raw if events_raw is not None else json.dumps(
                {'type': 'turn.completed', 'usage':
                 {'input_tokens': 11, 'cached_input_tokens': 2, 'output_tokens': 3}}) + '\n')

            def communicate(text, timeout):
                self.assertEqual(timeout, 1200)
                self.assertIsInstance(text, bytes)
                self.assertIn(b'Explain the fixture behavior.', text)
                self.assertEqual(text, (answer_path.parent / 'prompt.txt').read_bytes())
                if after is not None:
                    after(answer_path.parent)

            return SimpleNamespace(pid=1234, returncode=return_code, communicate=communicate)

        self.launches.side_effect = launch

    def test_imports_never_execute_models_or_subprocesses(self):
        fresh = load('quotes_protocol_import_control', 'common.py')
        with mock.patch.dict(sys.modules, {'common': fresh}):
            load('quotes_protocol_prepare_import_control', 'prepare.py')
            load('quotes_protocol_run_import_control', 'run.py')
        self.commands.assert_not_called()
        self.launches.assert_not_called()

    def test_six_orders_are_all_permutations_with_balanced_positions_and_carryover(self):
        orders = [tuple(order) for language in common.LANGUAGES for order in common.ORDERS[language]]
        self.assertEqual(Counter(orders), Counter(permutations(common.CONDITIONS)))
        for position in range(3):
            self.assertEqual(Counter(order[position] for order in orders), Counter(dict.fromkeys(common.CONDITIONS, 2)))
        self.assertEqual(Counter(pair for order in orders for pair in zip(order, order[1:])),
                         Counter({pair: 2 for pair in permutations(common.CONDITIONS, 2)}))
        for language in common.LANGUAGES:
            self.assertEqual(Counter(common.schedule(language)),
                             Counter((condition, repeat) for condition in common.CONDITIONS for repeat in (1, 2)))

    def test_prompts_allow_efficient_ordinary_json_without_private_oracle_locations(self):
        case = {'question': 'Discover the implementation.', 'findings': [dict(id='mechanism',
            description='Explain the complete mechanism.', path='PRIVATE/PATH.java',
            marker='PRIVATE_LITERAL_MARKER', call_lines=[876543])]}
        for condition in common.CONDITIONS:
            with self.subTest(condition=condition):
                prompt = common.prompt(case, condition, self.root / 'offered')
                self.assertIn('batch multiple searches or source ranges', prompt)
                self.assertIn('standard-library scripts to read source and serialize exact excerpts as JSON', prompt)
                self.assertIn('do not inspect sibling experiments', prompt)
                self.assertIn('Explain the complete mechanism.', prompt)
                for secret in ('PRIVATE/PATH.java', 'PRIVATE_LITERAL_MARKER', '876543', 'criteria.json', 'relationships.json'):
                    self.assertNotIn(secret, prompt)
                if condition == 'baseline':
                    self.assertNotIn(str(self.root / 'offered'), prompt)
                    self.assertIn('Do not use a code-graph tool or saved index', prompt)
                else:
                    self.assertIn(str(self.root / 'offered/runtime/SKILL.md'), prompt)
                    self.assertIn(str(self.root / 'offered/graph.jsonl.xz'), prompt)

    def test_runtime_exports_exact_pinned_git_blobs_not_current_workspace_bytes(self):
        committed = {'skills/columbus/SKILL.md': b'committed skill\n',
                     'skills/columbus/references/archive.md': b'committed archive help\n',
                     'skills/columbus/scripts/columbus.py': b'committed wrapper\n',
                     'skills/columbus/scripts/columbus/__init__.py': b'committed package\n',
                     'skills/columbus/scripts/tests/test_unrelated.py': b'not runtime\n',
                     'skills/columbus/scripts/requirements.txt': b'not an exported runtime input\n'}
        for name in committed:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'uncommitted current bytes must not be used\n')
        expected = {'SKILL.md': committed['skills/columbus/SKILL.md'],
                    'references/archive.md': committed['skills/columbus/references/archive.md'],
                    'columbus.py': committed['skills/columbus/scripts/columbus.py'],
                    'columbus/__init__.py': committed['skills/columbus/scripts/columbus/__init__.py']}
        for variant, commit in common.RUNTIME_COMMITS.items():
            def git(argv, **kwargs):
                self.assertEqual(kwargs.get('cwd'), self.root)
                if argv[:2] == ['git', 'ls-tree']:
                    self.assertEqual(argv, ['git', 'ls-tree', '-r', '--name-only', commit, '--', 'skills/columbus/'])
                    return '\n'.join(committed)
                self.assertEqual(argv[:2], ['git', 'show'])
                revision, path = argv[2].split(':', 1)
                self.assertEqual(revision, commit)
                return committed[path]
            self.commands.side_effect = git
            prepare.export_runtime(variant)
            target = self.here / 'runtimes' / variant
            self.assertEqual({p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob('*') if p.is_file()}, expected)
            before = self.commands.call_count
            with self.assertRaisesRegex(ValueError, 'already exists'):
                prepare.export_runtime(variant)
            self.assertEqual(self.commands.call_count, before)
        self.launches.assert_not_called()

    def test_prepare_refuses_existing_observation_or_environment_before_execution(self):
        target = self.root / 'observation'
        target.mkdir()
        with self.assertRaisesRegex(ValueError, 'Preparation exists'):
            prepare.prepare(target)
        target.rmdir()
        write_json(self.here / 'environment.json', {})
        with self.assertRaisesRegex(ValueError, 'Preparation exists'):
            prepare.prepare(target)
        self.commands.assert_not_called()
        self.launches.assert_not_called()

    def test_fresh_prepare_only_uses_metadata_and_index_export_commands_without_models(self):
        fixture = self.root / 'source.zip'
        fixture.write_bytes(b'stubbed immutable source ZIP\n')
        write_json(self.here / 'sources.json', {'java':
            {'fixture': str(fixture), 'fixture_sha256': common.sha(fixture)}})
        write_json(self.here / 'java/cases.json', {'cases': [{'id': 'fixture-case', 'findings': []}]})
        verifier = self.here.parent / 'archive-exploration/preflight.py'
        verifier.parent.mkdir()
        verifier.write_bytes(b'frozen verifier identity\n')
        self.patch(prepare, 'LANGUAGES', new=('java',))
        self.patch(prepare.platform, 'platform', return_value='fixture-platform')

        def exported(variant):
            payloads = {'columbus.py': b'shared wrapper\n', 'columbus/__init__.py': b'shared analyzer\n',
                        'SKILL.md': variant.encode(), 'references/archive.md': variant.encode(),
                        'columbus/cli.py': variant.encode()}
            if variant == 'quotes':
                payloads['columbus/quotes.py'] = b'new extraction helper\n'
            for name, data in payloads.items():
                path = self.here / 'runtimes' / variant / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)

        def prepared(output, source, cases):
            self.assertEqual(source, fixture)
            (output / 'repository').mkdir(parents=True)
            (output / 'repository/a.py').write_bytes(b'VALUE = 1\n')
            (output / 'cases.json').write_bytes(cases.read_bytes())
            manifest = {'source_manifest': {'a.py': digest(b'VALUE = 1\n')}}
            write_json(output / 'manifest.json', manifest)
            return manifest

        license_bytes = b'stubbed pinned license\n'
        original_sha = prepare.OBSERVE.sha
        self.patch(prepare.OBSERVE, 'sha', side_effect=lambda data:
            '56dfc19e0dc836e30177332f73e8e6fbc297941acf3d906eec6eaaa46c2c452a'
            if data == license_bytes else original_sha(data))
        self.patch(prepare, 'export_runtime', side_effect=exported)
        self.patch(prepare.OBSERVE, 'prepare', side_effect=prepared)

        def command(argv, **kwargs):
            if argv == ['codex', '--version']:
                return 'codex fixture-version\n'
            if argv == [sys.executable, '-m', 'pip', 'list', '--format=json']:
                return '[]'
            if argv[:2] == ['git', 'show']:
                self.assertEqual(argv[2], '4c8c6409a27a62ab163d3b6196ad862b7c835440:LICENSE.txt')
                return license_bytes
            self.assertEqual(argv[:2], [sys.executable, '-B'])
            self.assertEqual(Path(argv[2]).name, 'columbus.py')
            self.assertEqual(Path(argv[2]).parent.name, 'runtime')
            repository = Path(argv[argv.index('--repo') + 1])
            if argv[3] == 'sync':
                (repository / '.columbus').mkdir()
                return json.dumps(dict(files=1, symbols=1, edges=0, indexed_bytes=10, revision='fixture'))
            self.assertEqual(argv[3], 'archive')
            graph, counts = self.graph_bytes(digest(b'VALUE = 1\n'))
            Path(argv[argv.index('--output') + 1]).write_bytes(graph)
            return json.dumps(dict(revision='fixture', **counts))

        self.commands.side_effect = command
        prepare.prepare(self.root / 'fresh-observations')
        frozen = common.read(self.here / 'java/freeze.json')
        self.assertEqual(set(frozen), set(common.CONDITIONS))
        for arm in common.CONDITIONS:
            output = common.observation('java', arm)
            self.assertFalse((output / 'repository/.columbus').exists())
            self.assertFalse((output / 'trials').exists())
            self.assertTrue(common.verify_observation('java', arm)['passed'])
        self.assertEqual({item['engine']['archive']['archive_sha256'] for item in frozen.values()},
                         {common.sha(self.here / 'java/graph.jsonl.xz')})
        self.assertEqual([call.args[0] for call in self.commands.call_args_list if call.args[0][0] == 'codex'],
                         [['codex', '--version']])
        self.launches.assert_not_called()

    def test_citation_control_chooses_reviewed_duplicate_marker_occurrence(self):
        self.observations()
        output = common.observation('java', 'quotes')
        (output / 'repository/a.py').write_bytes(b'anchor()\n# gap\nanchor()\n')
        case = {'id': 'duplicate-marker', 'findings': [dict(id='later', path='a.py', marker='anchor()', call_lines=[3])]}
        write_json(self.here / 'java/cases.json', {'cases': [case]})
        prepare.citation_controls('java')
        control = common.read(self.here / 'java/citation-controls.json')
        self.assertEqual(control['answer']['findings'][0]['start_line'], 3)
        self.assertTrue(control['positive']['passed'])
        self.assertFalse(control['negative']['passed'])
        self.launches.assert_not_called()

    def test_frozen_inventory_rejects_modified_deleted_and_added_runtime_inputs(self):
        hashes = self.inventory()
        self.assertEqual(common.frozen_inputs(), hashes)
        path = self.here / 'runtimes/quotes/columbus.py'
        original = path.read_bytes()
        path.write_bytes(b'changed\n')
        with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
            common.frozen_inputs()
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
            common.frozen_inputs()
        path.write_bytes(original)
        extra = self.here / 'runtimes/quotes/unfrozen.py'
        extra.write_bytes(b'added executable\n')
        with self.assertRaisesRegex(ValueError, 'Incomplete input inventory'):
            common.frozen_inputs()

    def test_frozen_inventory_rejects_omitted_required_path_and_unsafe_path(self):
        hashes = self.inventory()
        removed = next(name for name in hashes if name.endswith('/PLAN.md'))
        incomplete = dict(hashes)
        del incomplete[removed]
        write_json(self.here / 'input-hashes.json', incomplete)
        with self.assertRaisesRegex(ValueError, 'Incomplete input inventory'):
            common.frozen_inputs()
        write_json(self.here / 'input-hashes.json', {**hashes, '../outside.py': '0' * 64})
        with self.assertRaisesRegex(ValueError, 'Unsafe frozen input path'):
            common.frozen_inputs()

    def test_observation_rejects_source_and_runtime_add_delete_or_change(self):
        self.observations()
        self.assertTrue(common.verify_observation('java', 'quotes')['passed'])
        output = common.observation('java', 'quotes')
        for relative in ('repository/a.py', 'runtime/columbus.py'):
            with self.subTest(relative=relative):
                path = output / relative
                original = path.read_bytes()
                path.write_bytes(b'changed bytes\n')
                with self.assertRaisesRegex(ValueError, 'Frozen source or runtime changed'):
                    common.verify_observation('java', 'quotes')
                path.unlink()
                with self.assertRaisesRegex(ValueError, 'Frozen source or runtime changed'):
                    common.verify_observation('java', 'quotes')
                path.write_bytes(original)
                added = path.with_name('unfrozen.py')
                added.write_bytes(b'extra\n')
                with self.assertRaisesRegex(ValueError, 'Frozen source or runtime changed'):
                    common.verify_observation('java', 'quotes')
                added.unlink()
        self.assertTrue(common.verify_observation('java', 'quotes')['passed'])

    def test_environment_rejects_python_cli_and_package_inventory_changes(self):
        environment = self.environment()
        common.verify_environment()
        for field, value in [('python', 'different Python'), ('python_executable', '/different/python'),
                             ('codex_cli', 'different CLI'), ('packages', [])]:
            changed = {**environment, field: value}
            write_json(self.here / 'environment.json', changed)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'changed after freeze'):
                common.verify_environment()
        self.launches.assert_not_called()

    def test_runner_validates_all_arms_and_environment_before_and_after_each_launch(self):
        self.observations()
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
        actual = [Path(call.args[0][call.args[0].index('--output-last-message') + 1]).parent.name
                  for call in self.launches.call_args_list]
        self.assertEqual(actual, [f'fixture-case-{arm}-{repeat}' for arm, repeat in common.schedule('java')])
        for arm, repeat in common.schedule('java'):
            path = common.observation('java', arm) / 'trials' / f'fixture-case-{arm}-{repeat}'
            self.assertEqual(common.read(path / 'terminal.json')['return_code'], 0)
            self.assertTrue(common.read(path / 'result.json')['quality']['passed'])
            case = common.read(self.here / 'java/cases.json')['cases'][0]
            expected_prompt = common.prompt(case, arm, common.observation('java', arm)).encode('utf-8')
            self.assertEqual((path / 'prompt.txt').read_bytes(), expected_prompt)
            self.assertEqual(common.read(path / 'invocation.json')['prompt_bytes'], len(expected_prompt))

    def test_existing_trial_directories_are_never_retried(self):
        self.observations()
        self.inventory()
        output = common.observation('java', 'control')
        trials = output / 'trials'
        trials.mkdir()
        (trials / 'original').write_bytes(b'preserved original evidence\n')
        with self.assertRaisesRegex(ValueError, 'never retry'):
            runner.run('java')
        self.assertEqual((trials / 'original').read_bytes(), b'preserved original evidence\n')
        self.launches.assert_not_called()

    def test_frozen_mutation_after_first_launch_preserves_terminal_and_stops_group(self):
        self.observations()
        self.inventory()
        self.fake_processes(after=lambda _: (self.here / 'PLAN.md').write_bytes(b'mutated during invocation\n'))
        with self.assertRaisesRegex(ValueError, 'Frozen input changed'), redirect_stdout(io.StringIO()):
            runner.run('java')
        self.launches.assert_called_once()
        trial = common.observation('java', 'baseline') / 'trials/fixture-case-baseline-1'
        self.assertEqual(common.read(trial / 'terminal.json')['return_code'], 0)
        self.assertFalse((trial / 'result.json').exists())
        self.assertFalse((common.observation('java', 'control') / 'trials').exists())

    def test_source_addition_during_launch_is_not_saved_as_success_or_followed_by_retry(self):
        self.observations()
        self.inventory()
        source = common.observation('java', 'control') / 'repository/extra.py'
        self.fake_processes(after=lambda _: source.write_bytes(b'unapproved added source\n'))
        with self.assertRaisesRegex(ValueError, 'Frozen source or runtime changed'), redirect_stdout(io.StringIO()):
            runner.run('java')
        self.launches.assert_called_once()
        trial = common.observation('java', 'baseline') / 'trials/fixture-case-baseline-1'
        self.assertTrue((trial / 'terminal.json').is_file())
        self.assertFalse((trial / 'result.json').exists())
        with self.assertRaises(ValueError):
            runner.run('java')
        self.launches.assert_called_once()

    def test_rejected_prelaunch_controls_prevent_any_model_process(self):
        self.observations()
        self.inventory()
        self.controls.side_effect = ValueError('Retained control command does not reproduce')
        with self.assertRaisesRegex(ValueError, 'control command does not reproduce'):
            runner.run('java')
        self.controls.assert_called_once()
        self.launches.assert_not_called()
        self.assertFalse(any((common.observation('java', arm) / 'trials').exists() for arm in common.CONDITIONS))

    def test_malformed_events_preserve_terminal_and_postflight_then_refuse_retry(self):
        self.observations()
        self.inventory()
        self.fake_processes(events_raw='{malformed JSON event}\n')
        frozen = self.patch(runner, 'frozen_inputs', wraps=common.frozen_inputs)
        environment = self.patch(runner, 'verify_environment', wraps=common.verify_environment)
        observations = self.patch(runner, 'verify_observation', wraps=common.verify_observation)
        with self.assertRaises(json.JSONDecodeError), redirect_stdout(io.StringIO()):
            runner.run('java')
        self.assertEqual(frozen.call_count, 3)
        self.assertEqual(environment.call_count, 3)
        self.assertEqual(observations.call_args_list, [mock.call('java', arm) for _ in range(3) for arm in common.CONDITIONS])
        self.launches.assert_called_once()
        trial = common.observation('java', 'baseline') / 'trials/fixture-case-baseline-1'
        self.assertEqual(common.read(trial / 'terminal.json')['return_code'], 0)
        self.assertEqual((trial / 'events.jsonl').read_text(), '{malformed JSON event}\n')
        self.assertFalse((trial / 'result.json').exists())
        with self.assertRaisesRegex(ValueError, 'never retry'):
            runner.run('java')
        self.launches.assert_called_once()

    def test_failed_model_events_retain_every_scheduled_slot_without_extra_retries(self):
        self.observations()
        self.inventory()
        self.fake_processes(events_raw=json.dumps({'type': 'turn.failed', 'error':
                            {'message': 'stubbed model failure'}}) + '\n', return_code=7)
        with redirect_stdout(io.StringIO()):
            runner.run('java')
        self.assertEqual(self.launches.call_count, 6)
        for arm, repeat in common.schedule('java'):
            trial = common.observation('java', arm) / 'trials' / f'fixture-case-{arm}-{repeat}'
            self.assertEqual(common.read(trial / 'terminal.json')['return_code'], 7)
            result = common.read(trial / 'result.json')
            self.assertEqual(result['return_code'], 7)
            self.assertIsNone(result['usage'])
            self.assertTrue(result['turn_failed'])
        with self.assertRaisesRegex(ValueError, 'never retry'):
            runner.run('java')
        self.assertEqual(self.launches.call_count, 6)


if __name__ == '__main__':
    unittest.main()
