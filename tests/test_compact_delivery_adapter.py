"""Tiny future-only adapter controls; no indexes, models or historical edits."""
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shlex
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ADAPTER = load('compact_adapter_under_test', 'evals/exploration/compact_delivery_adapter.py')
FIXTURES = load('compact_adapter_fixture_builder', 'tests/test_source_call_evidence.py')
LANES = (ADAPTER.FULL_ID, ADAPTER.TEXT_TABLE, ADAPTER.JSON_TABLE, ADAPTER.SEARCH_BATCH)


def empty(verifier):
    result = dict(recognizer_version=verifier.VERSION)
    if verifier is ADAPTER.SEARCH_BATCH:
        result['search_batch_receipts'] = []
    else:
        result.update(source_call_receipts=[], relationship_receipts=[])
    return result


class CompactDeliveryAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Construction only; do not duplicate historical test discovery.
        cls.controls = type('_AdapterFixture', (FIXTURES.SourceCallEvidenceTests,), {})
        cls.controls.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.controls.tearDownClass()

    def setUp(self):
        self.fixture = self.controls()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def event(self, identity='one', *, lane=0):
        # This tests aggregation, not an independent renderer oracle. Actual
        # CLI versus standalone equality is covered by the separate contract suite.
        f, verifier = self.fixture, LANES[lane]
        args = ['archive-source', 'outer', '--call-sites'] if lane < 3 else ['archive-search', 'outer', 'ping']
        if lane in (1, 2):
            args.append('--call-table')
        args += ['--format', 'text' if lane == 1 else 'json', '--input', str(f.graph),
                 '--repo', str(f.repo), '--budget-bytes', '64000']
        event = dict(type='item.completed', item=dict(id=identity, type='command_execution',
            status='completed', exit_code=0, command=shlex.join([*f.binding['invocation_prefix'], *args])))
        snapshot = (verifier._Snapshot(f.binding) if lane == 3 else ADAPTER.FULL_ID._Snapshot(f.binding))
        _, event['item']['aggregated_output'] = verifier._expected(snapshot, verifier._command(event['item'], snapshot))
        return event

    def recognize(self, events):
        return ADAPTER.evidence(events, binding=self.fixture.binding, relationships=self.fixture.reviewed)

    def mute_lanes(self, stack):
        return [stack.enter_context(patch.object(verifier, 'evidence', return_value=empty(verifier)))
                for verifier in LANES]

    def full_result(self, event):
        return ADAPTER.FULL_ID.evidence([event], binding=self.fixture.binding,
                                       relationships=self.fixture.reviewed)

    def test_exact_empty_schema_runs_all_four_verifiers_without_skips(self):
        with ExitStack() as stack:
            calls = [stack.enter_context(patch.object(verifier, 'evidence', wraps=verifier.evidence))
                     for verifier in LANES]
            result = self.recognize(iter(()))
        self.assertEqual(result, dict(recognizer_version='compact-delivery-adapter-v1',
            source_calls_used=False, full_id_source_calls_used=False, call_table_used=False,
            json_call_table_used=False, search_batch_used=False, source_call_receipts=[],
            relationship_receipts=[], relationship_used=False, search_batch_receipts=[]))
        for call in calls:
            call.assert_called_once()
            self.assertEqual(call.call_args.args, ([],))

    def test_all_lists_keep_chronology_and_inner_receipt_bytes(self):
        events = [self.event('search-z', lane=3), self.event('json-y', lane=2),
                  self.event('full-x'), self.event('table-w', lane=1), self.event('full-v')]
        expected = []
        for verifier in LANES:
            kwargs = dict(binding=self.fixture.binding)
            if verifier is not ADAPTER.SEARCH_BATCH:
                kwargs['relationships'] = self.fixture.reviewed
            expected.append(verifier.evidence(events, **kwargs))
        originals = deepcopy((events, self.fixture.binding, self.fixture.reviewed, expected))
        result = self.recognize(iter(events))
        positions = {event['item']['id']: n for n, event in enumerate(events)}
        for key in ('source_call_receipts', 'relationship_receipts', 'search_batch_receipts'):
            rows = sorted([row for lane in expected for row in lane.get(key, [])],
                          key=lambda row: positions[row['command_id']])
            self.assertEqual(result[key], rows)
            self.assertEqual(json.dumps(result[key]), json.dumps(rows))
        self.assertTrue(all(result[key] for key in ('source_calls_used', 'full_id_source_calls_used',
            'call_table_used', 'json_call_table_used', 'search_batch_used', 'relationship_used')))
        self.assertEqual((events, self.fixture.binding, self.fixture.reviewed, expected), originals)

    def test_identical_output_under_distinct_terminal_ids_is_not_deduplicated(self):
        first, second = self.event(), self.event('two')
        result = self.recognize([first, second])
        self.assertEqual([row['command_id'] for row in result['source_call_receipts']], ['one', 'two'])
        self.assertEqual(len(result['relationship_receipts']), 2)
        self.assertEqual(result['source_call_receipts'][0]['output_sha256'],
                         result['source_call_receipts'][1]['output_sha256'])

    def test_all_terminal_duplicates_are_fatal_before_any_lane(self):
        original = self.event()
        mutations = ({}, {'exit_code': 1}, {'exit_code': False}, {'exit_code': None},
                     {'status': 'failed'}, {'status': 'in_progress'}, {'command': 'unsupported'},
                     {'command': None}, {'aggregated_output': ''})
        for mutation in mutations:
            other = deepcopy(original)
            other['item'].update(mutation)
            for events in ([original, other], [other, original]):
                with self.subTest(mutation=mutation), ExitStack() as stack:
                    calls = self.mute_lanes(stack)
                    with self.assertRaisesRegex(ValueError, 'event stream'):
                        self.recognize(events)
                for call in calls:
                    call.assert_not_called()

    def test_nonterminal_to_terminal_and_non_command_id_reuse_are_normal(self):
        terminal = self.event()
        events = [dict(type=kind, item=deepcopy(terminal['item']))
                  for kind in ('item.started', 'item.updated')]
        events += [dict(type='item.completed', item=dict(id='one', type='agent_message')), terminal]
        result = self.recognize(events)
        self.assertEqual(len(result['source_call_receipts']), 1)

    def test_mutable_reused_event_objects_are_snapshotted_at_each_yield(self):
        event = self.event()
        first = deepcopy(event)
        second = deepcopy(first)
        second['item']['id'] = 'two'

        def reused():
            yield event
            event['item']['id'] = 'two'
            yield event
            event['item']['aggregated_output'] = 'changed after both yields'

        result = self.recognize(reused())
        expected = self.recognize([first, second])
        self.assertEqual(result, expected)
        self.assertEqual([row['command_id'] for row in result['source_call_receipts']], ['one', 'two'])

    def test_json_alias_dag_is_allowed_and_copy_preserves_exact_event_hash(self):
        event = self.event()
        shared = ['tab\t', '\\t', {'finite': 0.5, 'integer': 1, 'flag': True, 'empty': None}]
        event['extra'] = [shared, shared]
        result = self.recognize([event])
        self.assertTrue(result['source_calls_used'])
        self.assertEqual(result['source_call_receipts'][0]['event_json_sha256'],
                         ADAPTER.FULL_ID._sha(ADAPTER.FULL_ID._compact(event).encode()))

    def test_malformed_transport_fails_whole_stream_and_still_postflights(self):
        touched = []

        class NotJson:
            def __deepcopy__(self, memo):
                touched.append(True)
                raise AssertionError('must reject before user deepcopy hook')

        cycle = []
        cycle.append(cycle)
        variants = [(1, 2), {1: 'coerced key'}, b'bytes', {1, 2}, float('nan'),
                    float('inf'), float('-inf'), '\ud800', cycle, NotJson()]
        for value in variants:
            event = self.event()
            event['extra'] = value
            with self.subTest(value_type=type(value)), \
                    patch.object(ADAPTER, '_postflight', wraps=ADAPTER._postflight) as final:
                with self.assertRaises(ValueError):
                    self.recognize([self.event('accepted-if-not-malformed'), event])
            final.assert_called_once()
        for value in (None, [], 'not an event object'):
            with self.assertRaises(ValueError):
                self.recognize([value])
        self.assertEqual(touched, [])

    def test_invalid_frozen_inputs_reject_before_iterating_even_empty_stream(self):
        original = deepcopy(self.fixture.binding)
        touched = []

        def events():
            touched.append(True)
            return iter(())

        class Lazy:
            def __iter__(self):
                return events()

        for key in ('archive_sha256', 'revision', 'source_manifest', 'runtime_inventory'):
            self.fixture.binding = deepcopy(original)
            self.fixture.binding[key] = '0' * 64 if key == 'archive_sha256' else '' if key == 'revision' else {}
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'Invalid frozen'):
                self.recognize(Lazy())
        self.fixture.binding = original
        self.assertEqual(touched, [])

    def test_reviewed_relationships_are_frozen_before_iterator_mutation(self):
        original = deepcopy(self.fixture.reviewed)
        for change in ('boolean', 'float', 'list'):
            self.fixture.reviewed = deepcopy(original)

            def events():
                if change == 'list':
                    self.fixture.reviewed.clear()
                else:
                    # The fixture edge is on line 2: use 2.0 for equality bypass.
                    self.fixture.reviewed[0]['line'] = True if change == 'boolean' else 2.0
                return
                yield

            with ExitStack() as stack:
                calls = self.mute_lanes(stack)
                with self.assertRaisesRegex(ValueError, 'Frozen compact-delivery inputs changed'):
                    self.recognize(events())
            for call in calls[:3]:
                self.assertEqual(call.call_args.kwargs['relationships'], original)
        self.fixture.reviewed = original

    def test_binding_is_frozen_before_iterator_mutation(self):
        original = deepcopy(self.fixture.binding)

        def events():
            self.fixture.binding['archive_sha256'] = '0' * 64
            return
            yield

        with ExitStack() as stack:
            calls = self.mute_lanes(stack)
            with self.assertRaisesRegex(ValueError, 'Frozen compact-delivery inputs changed'):
                self.recognize(events())
        for call in calls:
            self.assertEqual(call.call_args.kwargs['binding'], original)

    def test_iterator_exception_runs_final_byte_validation(self):
        path = self.fixture.repo / 'calls.py'

        def events():
            path.write_bytes(path.read_bytes().replace(b'return 1', b'return 9'))
            raise RuntimeError('iterator failed')
            yield

        with patch.object(ADAPTER, '_postflight', wraps=ADAPTER._postflight) as final:
            with self.assertRaisesRegex(ValueError, 'Frozen compact-delivery inputs changed'):
                self.recognize(events())
        final.assert_called_once()

    def test_unchanged_iterator_exception_propagates_after_postflight(self):
        def events():
            raise RuntimeError('original iterator failure')
            yield

        with patch.object(ADAPTER, '_postflight', wraps=ADAPTER._postflight) as final:
            with self.assertRaisesRegex(RuntimeError, 'original iterator failure'):
                self.recognize(events())
        final.assert_called_once()

    def test_each_lane_exception_still_postflights_and_never_returns_partial(self):
        for number in range(4):
            with self.subTest(lane=number), ExitStack() as stack:
                calls = self.mute_lanes(stack)
                calls[number].side_effect = RuntimeError('lane failed')
                final = stack.enter_context(patch.object(ADAPTER, '_postflight', wraps=ADAPTER._postflight))
                with self.assertRaisesRegex(RuntimeError, 'lane failed'):
                    self.recognize([])
                final.assert_called_once()

    def test_late_lane_exception_cannot_bypass_changed_archive_guard(self):
        def fail(*args, **kwargs):
            self.fixture.graph.write_bytes(self.fixture.graph.read_bytes() + b' ')
            raise RuntimeError('last lane failed')

        with ExitStack() as stack:
            calls = self.mute_lanes(stack)
            calls[-1].side_effect = fail
            with self.assertRaisesRegex(ValueError, 'Frozen compact-delivery inputs changed'):
                self.recognize([])

    def test_final_full_hashes_reject_same_size_changes_with_stamp_checks_blinded(self):
        paths = (self.fixture.repo / 'calls.py', self.fixture.runtime / 'columbus.py', self.fixture.graph)
        for path in paths:
            original = path.read_bytes()

            def events():
                path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                return
                yield

            try:
                with self.subTest(path=path.name), ExitStack() as stack:
                    self.mute_lanes(stack)
                    stack.enter_context(patch.object(ADAPTER.FULL_ID._Snapshot, 'check', return_value=None))
                    stack.enter_context(patch.object(ADAPTER.FULL_ID, '_stamp', return_value=(0, 0, len(original), 0, 0)))
                    # Keep archived size validation realistic despite hiding all
                    # timestamp/inode fields; use each file's actual size.
                    ADAPTER.FULL_ID._stamp.side_effect = lambda info: (0, 0, info.st_size, 0, 0)
                    with self.assertRaisesRegex(ValueError, 'Frozen compact-delivery inputs changed'):
                        self.recognize(events())
            finally:
                path.write_bytes(original)

    def test_final_closing_scan_catches_membership_change_during_archive_read(self):
        real_read = ADAPTER.FULL_ID._read
        archive_reads = 0

        def read(path):
            nonlocal archive_reads
            result = real_read(path)
            if path == self.fixture.graph:
                archive_reads += 1
                if archive_reads == 2:
                    (self.fixture.repo / 'late-extra.py').write_bytes(b'')
            return result

        with ExitStack() as stack:
            self.mute_lanes(stack)
            stack.enter_context(patch.object(ADAPTER.FULL_ID, '_read', side_effect=read))
            with self.assertRaisesRegex(ValueError, 'Frozen compact-delivery inputs changed'):
                self.recognize([])
        self.assertEqual(archive_reads, 2)

    def test_exception_paths_rehash_all_three_inputs_despite_hidden_metadata_changes(self):
        paths = (self.fixture.repo / 'calls.py', self.fixture.runtime / 'columbus.py', self.fixture.graph)
        for path in paths:
            original = path.read_bytes()
            for phase in ('iterator', 'last-lane'):
                def mutate_and_fail(*args, **kwargs):
                    path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                    raise RuntimeError('failure must not bypass byte verification')

                def events():
                    mutate_and_fail()
                    yield

                try:
                    with self.subTest(path=path.name, phase=phase), ExitStack() as stack:
                        calls = self.mute_lanes(stack)
                        stack.enter_context(patch.object(ADAPTER.FULL_ID._Snapshot, 'check', return_value=None))
                        stack.enter_context(patch.object(ADAPTER.FULL_ID, '_stamp',
                            side_effect=lambda info: (0, 0, info.st_size, 0, 0)))
                        if phase == 'last-lane':
                            calls[-1].side_effect = mutate_and_fail
                        with self.assertRaisesRegex(ValueError, 'Frozen compact-delivery inputs changed'):
                            self.recognize(events() if phase == 'iterator' else [])
                finally:
                    path.write_bytes(original)

    def test_original_binding_and_relationship_checks_follow_last_io(self):
        real_check = ADAPTER.FULL_ID._Snapshot.check
        original_binding, original_relationships = deepcopy(self.fixture.binding), deepcopy(self.fixture.reviewed)
        for mutate in ('binding', 'relationships'):
            self.fixture.binding, self.fixture.reviewed = deepcopy(original_binding), deepcopy(original_relationships)
            calls = 0

            def check(snapshot):
                nonlocal calls
                real_check(snapshot)
                calls += 1
                if calls == 3:  # Snapshot construction, final opening, final closing scan.
                    if mutate == 'binding':
                        self.fixture.binding['revision'] = 'late revision'
                    else:
                        self.fixture.reviewed[0]['line'] = 2.0

            with self.subTest(mutate=mutate), ExitStack() as stack:
                self.mute_lanes(stack)
                stack.enter_context(patch.object(ADAPTER.FULL_ID._Snapshot, 'check', new=check))
                with self.assertRaisesRegex(ValueError, 'Frozen compact-delivery inputs changed'):
                    self.recognize([])
            self.assertEqual(calls, 3)

    def test_cross_lane_delivery_overlap_is_fatal_not_deduplicated(self):
        event = self.event()
        full = self.full_result(event)
        table = deepcopy(full)
        table['recognizer_version'] = ADAPTER.TEXT_TABLE.VERSION
        for receipt in table['source_call_receipts'] + table['relationship_receipts']:
            receipt.update(recognizer_version=ADAPTER.TEXT_TABLE.VERSION, encoding='columbus-call-table/v1')
        with patch.object(ADAPTER.FULL_ID, 'evidence', return_value=full), \
                patch.object(ADAPTER.TEXT_TABLE, 'evidence', return_value=table):
            with self.assertRaisesRegex(ValueError, 'Overlapping standalone delivery'):
                self.recognize([event])

    def test_orphan_duplicate_and_differently_bound_relationship_receipts_fail(self):
        event = self.event()
        original = self.full_result(event)
        for change in ('orphan', 'duplicate', 'different-output'):
            result = deepcopy(original)
            if change == 'orphan':
                result['source_call_receipts'] = []
            elif change == 'duplicate':
                result['relationship_receipts'] *= 2
            else:
                result['relationship_receipts'][0]['output_sha256'] = '0' * 64
            with self.subTest(change=change), patch.object(ADAPTER.FULL_ID, 'evidence', return_value=result):
                with self.assertRaises(ValueError):
                    self.recognize([event])

    def test_wrong_receipt_event_runtime_and_invocation_provenance_fail(self):
        event = self.event()
        original = self.full_result(event)
        for key in ('event_json_sha256', 'binding_sha256', 'command_sha256', 'output_sha256',
                    'recognizer_version', 'encoding', 'operation', 'delivery_mode', 'command_id'):
            result = deepcopy(original)
            result['source_call_receipts'][0][key] = 'wrong'
            with self.subTest(key=key), patch.object(ADAPTER.FULL_ID, 'evidence', return_value=result):
                with self.assertRaises(ValueError):
                    self.recognize([event])

    def test_merged_receipts_are_detached_without_changing_inner_values_or_order(self):
        event = self.event()
        original = self.full_result(event)
        before = deepcopy(original)
        with patch.object(ADAPTER.FULL_ID, 'evidence', return_value=original):
            result = self.recognize([event])
        for key in ('source_call_receipts', 'relationship_receipts'):
            self.assertEqual(json.dumps(result[key]), json.dumps(before[key]))
            self.assertIsNot(result[key][0], original[key][0])
        original['source_call_receipts'][0]['ranges'][0]['start_line'] = 999
        original['relationship_receipts'][0]['relationships'].clear()
        self.assertEqual(result['source_call_receipts'], before['source_call_receipts'])
        self.assertEqual(result['relationship_receipts'], before['relationship_receipts'])


if __name__ == '__main__':
    unittest.main()
