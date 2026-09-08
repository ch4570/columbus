"""Adapter dispatch only: synthetic frozen bytes and saved controls, no CLI runs."""
from copy import deepcopy
import hashlib
import importlib.util
import json
import lzma
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


COHORT = Path(__file__).resolve().parents[1] / 'evals/source-call-sites-cohort'
SPEC = importlib.util.spec_from_file_location('_source_call_dispatch_tests', COHORT / 'recognize.py')
ADAPTER = importlib.util.module_from_spec(SPEC)
with mock.patch.multiple(subprocess,
        Popen=mock.Mock(side_effect=AssertionError('unexpected process')),
        run=mock.Mock(side_effect=AssertionError('unexpected process')),
        check_output=mock.Mock(side_effect=AssertionError('unexpected process'))):
    SPEC.loader.exec_module(ADAPTER)
SOURCE = ADAPTER.SOURCE_CALLS


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, separators=(',', ':')) + '\n').encode()


def original_adapter(events, observation, relationships):
    """The exact pre-optimization composition, without importing another runtime."""
    old = ADAPTER.LEGACY.evidence(events, observation, relationships)
    combined = SOURCE.evidence(events, binding=ADAPTER.binding(observation), relationships=relationships)
    received = old['relationship_receipts'] + combined['relationship_receipts']
    return {**old, 'recognizer_version': ADAPTER.VERSION,
            'source_calls_used': bool(combined['source_call_receipts']),
            'source_call_receipts': combined['source_call_receipts'],
            'relationship_receipts': received, 'relationship_used': bool(received)}


class DispatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.observation = Path(temporary.name).resolve()
        self.repo, self.runtime = self.observation / 'repository', self.observation / 'runtime'
        self.repo.mkdir()
        (self.runtime / 'columbus').mkdir(parents=True)
        # These are inert inventory bytes, never imported or executed.
        (self.runtime / 'columbus.py').write_bytes(b'# synthetic wrapper\n')
        (self.runtime / 'columbus/source_calls.py').write_bytes(b'# synthetic feature\n')
        raw = b'def outer():\n    inner()\n\ndef inner(): pass\n'
        (self.repo / 'calls.py').write_bytes(raw)
        self.prefix = (sys.executable, '-B', str(self.runtime / 'columbus.py'))
        self.graph = self.observation / 'graph.jsonl.xz'
        self.source, self.target = 'calls.py::outer:function', 'calls.py::inner:function'
        nodes = [dict(id=identity, path='calls.py', name=name, qualname=name,
                      kind='function', language='python', fidelity='ast', partial=False,
                      module='calls', start_line=start, end_line=end)
                 for identity, name, start, end in ((self.source, 'outer', 1, 2),
                                                     (self.target, 'inner', 4, 4))]
        edge = dict(source=self.source, target=self.target, path='calls.py', line=2,
                    kind='calls', confidence='resolved_static', evidence='inner()')
        self.relationships = [{key: edge[key] for key in ('source', 'target', 'path', 'line')}]
        rows = [('manifest', dict(format='columbus-graph', version=1, revision='dispatch-fixture')),
                ('file', dict(path='calls.py', hash=sha(raw), size=len(raw))),
                *[('node', node) for node in nodes], ('edge', edge),
                ('reference', dict(source=self.source, path='calls.py', line=2,
                                   kind='calls', resolved=True, name='inner')),
                ('end', dict(files=1, nodes=2, scopes=0, edges=1, references=1, imports=0, diagnostics=0))]
        self.graph.write_bytes(lzma.compress(b''.join(encoded(dict(record=kind, data=data))
                                                    for kind, data in rows)))
        inventory = {path.relative_to(self.runtime).as_posix(): sha(path.read_bytes())
                     for path in self.runtime.rglob('*') if path.is_file()}
        sources = {'calls.py': sha(raw)}
        (self.observation / 'manifest.json').write_bytes(encoded({'source_manifest': sources}))
        (self.observation / 'engine.json').write_bytes(encoded({'files': inventory, 'archive': {
            'archive_sha256': sha(self.graph.read_bytes()), 'source_manifest': sources,
            'runtime_manifest': inventory, 'revision': 'dispatch-fixture'}}))
        self.binding = ADAPTER.binding(self.observation)
        self.processes = []
        for name in ('Popen', 'run', 'check_output'):
            patcher = mock.patch.object(subprocess, name, side_effect=AssertionError('no actual execution'))
            self.addCleanup(patcher.stop)
            self.processes.append(patcher.start())

    def event(self, arguments=None, *, command=None, output='invalid output'):
        if command is None:
            arguments = arguments or ['archive-source', 'outer', '--call-sites']
            tail = ['--input', str(self.graph)]
            if not any(word == '--repo' or word.startswith('--repo=') for word in arguments):
                tail.extend(['--repo', '.'])
            command = shlex.join([*self.prefix, *arguments, *tail])
        return {'type': 'item.completed', 'item': dict(type='command_execution', id='dispatch-1',
            command=command, status='completed', exit_code=0, aggregated_output=output)}

    def actual_event(self, arguments=None):
        event = self.event(arguments)
        # Existing independent renderer constructs fixture bytes only. No CLI or
        # production runtime is imported; this tests dispatch, not renderer truth.
        snapshot = SOURCE._Snapshot(self.binding)
        invocation = SOURCE._command(event['item'], snapshot)
        _, event['item']['aggregated_output'] = SOURCE._expected(snapshot, invocation)
        return event

    def candidate(self, event):
        return ADAPTER._has_source_call_candidate([event], self.prefix)

    def test_quoted_split_escaped_flags_and_global_repo_are_candidates(self):
        base = shlex.join(self.prefix)
        commands = [base + ' archive-source outer ' + flag for flag in (
            '--call-sites', "'--call-sites'", '"--call-sites"', "--call'-sites'", r'--call\-sites')]
        commands += [base + ' --repo . archive-source outer --call-sites',
                     base + ' --repo=. archive-source outer --call-sites']
        commands += [shlex.join([shell, option, commands[0]])
                     for shell in ('sh', '/bin/bash', '/bin/zsh') for option in ('-c', '-lc')]
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(self.candidate(self.event(command=command)))

    def test_tokens_are_exact_but_screen_is_deliberately_conservative(self):
        base = shlex.join(self.prefix)
        for tail in ('archive-source outer --call-sites=true', 'archive-source outer --call-site',
                     'archive-neighbors outer --call-sites', 'archive-source outer',
                     'archive-source outer --call-sites; echo forged',
                     'archive-source "$expand" --call-sites'):
            with self.subTest(tail=tail):
                self.assertFalse(self.candidate(self.event(command=base + ' ' + tail)))
        # A possible false positive is safe: the full parser still rejects it.
        self.assertTrue(self.candidate(self.event(command=base +
            ' archive-neighbors archive-source --call-sites')))

    def test_wrong_prefix_and_extra_or_nested_shell_wrapping_are_not_candidates(self):
        event = self.event()
        command = event['item']['command']
        candidates = [command.replace(' -B ', ' ', 1), command.replace('columbus.py', 'wrong.py', 1),
                      shlex.join(['sh', '-c', command, 'extra']),
                      shlex.join(['sh', '-c', shlex.join(['bash', '-lc', command])])]
        for command in candidates:
            with self.subTest(command=command):
                self.assertFalse(self.candidate(self.event(command=command)))

    def test_success_id_status_and_integer_zero_are_strict(self):
        original = self.event()
        for key, value in [('type', 'message'), ('id', ''), ('id', None), ('id', 1),
                           ('status', None), ('status', 'failed'), ('exit_code', False),
                           ('exit_code', 1), ('exit_code', 0.0), ('command', None)]:
            event = deepcopy(original)
            event['item'][key] = value
            with self.subTest(key=key, value=value):
                self.assertFalse(self.candidate(event))
        for event in (None, {}, {'type': 'item.started', 'item': original['item']},
                      {'type': 'item.completed', 'item': None}):
            self.assertFalse(self.candidate(event))

    def test_no_candidate_does_not_construct_a_snapshot(self):
        failed = self.event()
        failed['item']['exit_code'] = 1
        for events in ([], [failed], [self.event(['archive-neighbors', 'outer'])],
                       [self.event(['archive-source', 'outer'])]):
            with self.subTest(events=events), mock.patch.object(SOURCE, '_Snapshot',
                    side_effect=AssertionError('irrelevant full snapshot load')):
                result = ADAPTER.evidence(events, self.observation, self.relationships)
                self.assertEqual(result['source_call_receipts'], [])

    def test_candidate_invalid_output_still_runs_full_snapshot_validation(self):
        # A bad output is not a reason to skip input validation.
        self.graph.write_bytes(self.graph.read_bytes() + b'changed frozen archive')
        for output in ('', None, '{}'):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, 'Invalid frozen'):
                ADAPTER.evidence([self.event(output=output)], self.observation, self.relationships)

    def test_candidate_bad_metadata_binding_raises(self):
        with mock.patch.object(ADAPTER, 'binding', return_value={**self.binding, 'archive_sha256': 'bad'}):
            with self.assertRaisesRegex(ValueError, 'Invalid frozen'):
                ADAPTER.evidence([self.event()], self.observation, self.relationships)

    def test_standalone_empty_stream_still_validates_all_inputs(self):
        with self.assertRaisesRegex(ValueError, 'Invalid frozen'):
            SOURCE.evidence([], binding={}, relationships=[])
        (self.repo / 'unexpected.py').write_bytes(b'not frozen')
        with self.assertRaisesRegex(ValueError, 'Invalid frozen'):
            SOURCE.evidence([], binding=self.binding, relationships=self.relationships)

    def test_mixed_streams_keep_all_events_and_full_source_receipts(self):
        actual = self.actual_event()
        failed = self.event()
        failed['item']['exit_code'] = 1
        events = [None, self.event(['archive-neighbors', 'outer']), failed, actual]
        original = original_adapter(events, self.observation, self.relationships)
        with mock.patch.object(SOURCE, 'evidence', wraps=SOURCE.evidence) as full:
            result = ADAPTER.evidence(iter(events), self.observation, self.relationships)
        self.assertEqual(full.call_args.args[0], events)
        self.assertEqual(encoded(result), encoded(original))
        self.assertTrue(result['source_calls_used'])
        self.assertTrue(result['relationship_used'])

    def test_valid_json_text_and_global_options_preserve_receipt_bytes(self):
        for arguments in (['archive-source', 'outer', '--call-sites'],
                          ['archive-source', 'outer', '--call-sites', '--format', 'text'],
                          ['--repo=.', 'archive-source', 'outer', '--call-sites']):
            event = self.actual_event(arguments)
            with self.subTest(arguments=arguments):
                old = original_adapter([event], self.observation, self.relationships)
                new = ADAPTER.evidence([event], self.observation, self.relationships)
                self.assertEqual(encoded(new), encoded(old))

    def test_relocated_saved_java_packet_legacy_receipt_parity(self):
        """Relocate paths, not output bytes; this is not original execution replay.

        Complete frozen source/runtime/archive bytes make the relocated fixture
        valid for strict recognition. No new CLI or original process is executed.
        """
        raw_path = COHORT / 'java/control-raw/000.json'
        relationships_path = COHORT / 'java/relationships.json'
        raw = raw_path.read_bytes()
        self.assertEqual(sha(raw), '5dbe580830181a7ad1ed87cf3a042af923b8e00ba85f71d9c68235f7831c866f')
        row = json.loads(raw)
        frozen = json.loads((COHORT / 'java/freeze.json').read_text())['control']
        observation = self.observation / 'relocated'
        observation.mkdir()
        repository, runtime = observation / 'repository', observation / 'runtime'
        repository.mkdir()
        shutil.copytree(COHORT / 'runtimes/control', runtime)
        graph = observation / 'graph.jsonl.xz'
        shutil.copyfile(COHORT / 'java/graph.jsonl.xz', graph)
        self.assertEqual(sha(graph.read_bytes()), frozen['engine']['archive']['archive_sha256'])
        fixture = COHORT / 'java/source.zip'
        self.assertEqual(sha(fixture.read_bytes()), frozen['manifest']['fixture_sha256'])
        source = json.loads((COHORT / 'sources.json').read_text())['java']
        prefix = source['fixture_prefix']
        with zipfile.ZipFile(fixture) as archive:
            for member in archive.infolist():
                self.assertTrue(member.filename.startswith(prefix))
                if member.is_dir():
                    continue
                relative = member.filename[len(prefix):]
                self.assertIn(relative, frozen['manifest']['source_manifest'])
                target = repository / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))
        for key in ('manifest', 'engine'):
            (observation / (key + '.json')).write_bytes(encoded(frozen[key]))
        relocated = deepcopy(row['event'])
        argv = list(row['argv'])
        self.assertEqual(argv.count('--input'), 1)
        argv[0], argv[2] = sys.executable, str(runtime / 'columbus.py')
        argv[argv.index('--input') + 1] = str(graph)
        relocated['item']['command'] = shlex.join(argv)
        output = relocated['item']['aggregated_output']
        self.assertEqual(output, row['stdout'])
        self.assertEqual(sha(output.encode()), row['stdout_sha256'])
        self.assertEqual(row['stdout_sha256'],
                         '80e077ee385b061052e84265a6eb28b9c844ba9f1b2ec0bf5bd9ce3d7e9822be')
        relationships = json.loads(relationships_path.read_text())
        subset = [relationships[row['relationship_index']]]
        # This saved archive-neighbors event must not load source-call snapshots.
        self.assertEqual(row['kind'], 'relationship')
        # The original adapter fully validates all relocated frozen inputs.
        expected = original_adapter([relocated], observation, subset)
        with mock.patch.object(SOURCE, '_Snapshot', side_effect=AssertionError('irrelevant snapshot')):
            new = ADAPTER.evidence([relocated], observation, subset)
        # Preserve the historical key order as well as every receipt value.
        self.assertEqual(encoded(new), encoded(expected))
        self.assertEqual(len(new['relationship_receipts']), 1)
        self.assertEqual(new['relationship_receipts'][0]['output_sha256'], row['stdout_sha256'])
        self.assertEqual(relocated['item']['aggregated_output'], row['event']['item']['aggregated_output'])
        self.assertEqual(raw_path.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
