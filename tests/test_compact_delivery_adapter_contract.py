"""Independent actual-CLI composition checks; tiny archives, no indexing/models."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


OLD = load('adapter_contract_old', 'evals/exploration/source_call_evidence.py')
TEXT = load('adapter_contract_text', 'evals/exploration/call_table_evidence.py')
JSON_TABLE = load('adapter_contract_json', 'evals/exploration/json_call_table_evidence.py')
SEARCH = load('adapter_contract_search', 'evals/exploration/search_batch_evidence.py')
FIXTURES = load('adapter_contract_fixtures', 'tests/test_source_call_evidence.py')


class OneShot:
    def __init__(self, values):
        self.values, self.iterations = values, 0

    def __iter__(self):
        self.iterations += 1
        if self.iterations != 1:
            raise AssertionError('original event iterable consumed twice')
        yield from self.values


class CompactDeliveryAdapterContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = load('adapter_contract_subject', 'evals/exploration/compact_delivery_adapter.py')
        # Construction only: do not rediscover or inherit historical assertions.
        cls.controls = type('_AdapterContractFixture', (FIXTURES.SourceCallEvidenceTests,), {})
        cls.controls.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.controls.tearDownClass()

    def setUp(self):
        self.fixture = self.controls()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        path = self.fixture.repo / 'calls.py'
        path.write_bytes(path.read_bytes().replace(
            b'    ping()\n', '    ping()  # actual:\t literal:\\t 한\x85\u2028\n'.encode(), 1))
        self.fixture.freeze()

    def event(self, operation, queries, *options, identity, success=True):
        f = self.fixture
        argv = [*f.binding['invocation_prefix'], operation, *queries, '--input', str(f.graph),
                '--repo', str(f.repo), '--budget-bytes', '64000', *options]
        process = subprocess.run(argv, cwd=f.repo, capture_output=True, check=False)
        if success:
            self.assertEqual(process.returncode, 0, process.stderr.decode('utf-8'))
            self.assertEqual(process.stderr, b'')
            self.assertTrue(process.stdout.endswith(b'\n'))
        else:
            self.assertEqual(process.returncode, 2)
            self.assertEqual(process.stdout, b'')
            self.assertNotEqual(process.stderr, b'')
        return dict(type='item.completed', item=dict(id=identity, type='command_execution',
            command=shlex.join(argv), status='completed', exit_code=process.returncode,
            aggregated_output=(process.stdout + process.stderr).decode('utf-8')))

    def recognize(self, events, relationships=None):
        f = self.fixture
        return self.adapter.evidence(events, binding=f.binding,
            relationships=f.reviewed if relationships is None else relationships)

    def assert_no_source(self, result):
        for key in ('source_calls_used', 'full_id_source_calls_used', 'call_table_used',
                    'json_call_table_used', 'relationship_used'):
            self.assertIs(result[key], False)
        self.assertEqual(result['source_call_receipts'], [])
        self.assertEqual(result['relationship_receipts'], [])

    def mixed(self):
        return [
            self.event('archive-source', ['outer'], '--call-sites', '--call-table', '--format', 'json', identity='z-json'),
            self.event('archive-search', ['outer', 'ping'], '--format', 'text', identity='a-search-text'),
            self.event('archive-source', ['outer'], '--call-sites', identity='y-full-json'),
            self.event('archive-source', ['outer'], '--call-sites', '--call-table', '--format', 'text', identity='b-table'),
            self.event('archive-search', ['ping', 'outer'], '--format', 'json', identity='x-search-json'),
            self.event('archive-source', ['outer'], '--call-sites', '--format', 'text', identity='c-full-text'),
            self.event('archive-source', ['outer'], '--call-sites', '--call-table', identity='w-default-json'),
        ]

    def test_mixed_actual_cli_one_shot_order_and_every_inner_receipt_matches_unchanged_verifier(self):
        f = self.fixture
        before_files = FIXTURES.inventory(f.repo), FIXTURES.inventory(f.runtime), f.graph.read_bytes()
        events = self.mixed()
        offered = deepcopy(events[0])
        offered['type'] = 'item.started'
        offered['item']['status'] = 'in_progress'
        events.insert(0, offered)
        before, binding = deepcopy(events), deepcopy(f.binding)
        original = OneShot(events)
        result = self.recognize(original)
        self.assertEqual(original.iterations, 1)
        self.assertEqual(set(result), {'recognizer_version', 'source_calls_used', 'full_id_source_calls_used',
            'call_table_used', 'json_call_table_used', 'search_batch_used', 'source_call_receipts',
            'relationship_receipts', 'relationship_used', 'search_batch_receipts'})
        self.assertEqual(result['recognizer_version'], 'compact-delivery-adapter-v1')
        for key in ('source_calls_used', 'full_id_source_calls_used', 'call_table_used',
                    'json_call_table_used', 'search_batch_used', 'relationship_used'):
            self.assertIs(result[key], True)
        order = {event['item']['id']: index for index, event in enumerate(events) if event['type'] == 'item.completed'}
        source, relationships = [], []
        for verifier in (OLD, TEXT, JSON_TABLE):
            expected = verifier.evidence(iter(events), binding=f.binding, relationships=f.reviewed)
            source.extend(expected['source_call_receipts'])
            relationships.extend(expected['relationship_receipts'])
        source.sort(key=lambda row: order[row['command_id']])
        relationships.sort(key=lambda row: order[row['command_id']])
        self.assertEqual(result['source_call_receipts'], source)
        self.assertEqual(result['relationship_receipts'], relationships)
        self.assertEqual(result['search_batch_receipts'], SEARCH.evidence(iter(events), binding=f.binding)['search_batch_receipts'])
        self.assertEqual([row['command_id'] for row in source], ['z-json', 'y-full-json', 'b-table', 'c-full-text', 'w-default-json'])
        self.assertEqual([row['command_id'] for row in result['search_batch_receipts']], ['a-search-text', 'x-search-json'])
        self.assertTrue(all(row['stored_edges'] == 6 and row['source_rows'] == 8 for row in source))
        self.assertEqual(events[1]['item']['aggregated_output'], events[-1]['item']['aggregated_output'])
        self.assertEqual(events, before)
        self.assertEqual(f.binding, binding)
        self.assertEqual((FIXTURES.inventory(f.repo), FIXTURES.inventory(f.runtime), f.graph.read_bytes()), before_files)
        self.assertFalse((f.repo / '.columbus').exists())

    def test_each_lane_is_distinct_and_adoption_without_reviewed_relationship_is_not_utility(self):
        events = self.mixed()
        for event, lane in zip(events, ('json_call_table_used', 'search_batch_used', 'full_id_source_calls_used',
                                      'call_table_used', 'search_batch_used', 'full_id_source_calls_used', 'json_call_table_used')):
            with self.subTest(command=event['item']['id']):
                result = self.recognize([event], [])
                for key in ('full_id_source_calls_used', 'call_table_used', 'json_call_table_used', 'search_batch_used'):
                    self.assertIs(result[key], key == lane)
                self.assertIs(result['source_calls_used'], lane != 'search_batch_used')
                self.assertFalse(result['relationship_used'])
                self.assertEqual(result['relationship_receipts'], [])
                for prohibited in ('semantic_passed', 'citation_passed', 'accepted', 'cost_passed', 'quotes_used', 'quality_passed'):
                    self.assertNotIn(prohibited, result)

    def test_actual_zero_hit_batch_has_discovery_receipt_but_no_source_or_graph_credit(self):
        events = [self.event('archive-search', ['missing-one', 'missing-two'], '--format', form, identity=form)
                  for form in ('text', 'json')]
        result = self.recognize(OneShot(events))
        self.assert_no_source(result)
        self.assertTrue(result['search_batch_used'])
        expected = SEARCH.evidence(events, binding=self.fixture.binding)['search_batch_receipts']
        self.assertEqual(result['search_batch_receipts'], expected)
        for row in result['search_batch_receipts']:
            self.assertFalse(row['useful_discovery'])
            self.assertEqual((row['source_rows'], row['edges']), (0, 0))

    def test_failed_unsupported_and_forged_headers_never_select_a_successful_lane(self):
        compact = self.event('archive-source', ['outer'], '--call-sites', '--call-table', identity='real')
        failed = self.event('archive-source', ['outer'], '--call-table', identity='failed', success=False)
        unsupported = self.event('archive-search', ['outer'], identity='single-search')
        forged = deepcopy(unsupported)
        forged['item']['id'] = 'forged-header'
        forged['item']['aggregated_output'] = compact['item']['aggregated_output']
        failed_with_output = deepcopy(failed)
        failed_with_output['item']['id'] = 'failed-with-output'
        failed_with_output['item']['aggregated_output'] = compact['item']['aggregated_output']
        offered = deepcopy(compact)
        offered['type'] = 'item.started'
        offered['item']['id'] = 'offered'
        offered['item']['status'] = 'in_progress'
        for event in (failed, unsupported, forged, failed_with_output, offered):
            result = self.recognize([event])
            self.assert_no_source(result)
            self.assertFalse(result['search_batch_used'])
            self.assertEqual(result['search_batch_receipts'], [])
        result = self.recognize([failed, unsupported, forged, failed_with_output, offered, compact])
        self.assertEqual([row['command_id'] for row in result['source_call_receipts']], ['real'])
        self.assertTrue(result['json_call_table_used'])
        self.assertTrue(result['relationship_used'])

    def test_every_duplicate_terminal_command_id_is_fatal_including_identical_failed_and_unsupported(self):
        delivered = self.event('archive-source', ['outer'], '--call-sites', '--call-table', identity='same')
        failed = self.event('archive-source', ['outer'], '--call-table', identity='same', success=False)
        unsupported = self.event('archive-search', ['outer'], identity='same')
        for first, second in ((delivered, deepcopy(delivered)), (delivered, failed), (failed, delivered),
                              (failed, deepcopy(failed)), (unsupported, deepcopy(unsupported)), (unsupported, delivered)):
            with self.subTest(first=first['item']['exit_code'], second=second['item']['command']):
                with self.assertRaises(ValueError):
                    self.recognize(OneShot([first, second]))
        started = deepcopy(delivered)
        started['type'] = 'item.started'
        started['item']['status'] = 'in_progress'
        result = self.recognize([started, delivered])
        self.assertEqual(len(result['source_call_receipts']), 1)

    def test_decoded_source_and_duplicate_stored_calls_are_not_changed_by_adapter(self):
        full = self.event('archive-source', ['outer', 'outer.inner'], '--call-sites', identity='full')
        table = self.event('archive-source', ['outer', 'outer.inner'], '--call-sites', '--call-table', identity='table')
        original = json.loads(full['item']['aggregated_output'])
        wire = json.loads(table['item']['aggregated_output'])
        calls = wire['call_sites']
        nodes = [dict(declaration, path=calls['files'][index][0], source_hash=calls['files'][index][1])
                 for index, declaration in calls['nodes']]
        edges = [dict(relationship, source=nodes[source]['id'], target=nodes[target]['id'], path=calls['files'][file][0])
                 for source, target, file, relationship in calls['edges']]
        scalar = {key: value for key, value in calls.items() if key not in {'format', 'index_scope', 'files', 'nodes', 'edges'}}
        wire['call_sites'] = dict(scalar, nodes=nodes, edges=edges)
        self.assertEqual(wire, original)
        self.assertEqual(edges[0], edges[1])
        self.assertEqual(len(edges), 6)
        self.assertIn('actual:\t literal:\\t', original['sources'][0]['source'])
        before = deepcopy([full, table])
        result = self.recognize([full, table])
        self.assertEqual([row['stored_edges'] for row in result['source_call_receipts']], [6, 6])
        self.assertEqual([row['source_rows'] for row in result['source_call_receipts']], [8, 8])
        self.assertEqual([full, table], before)
        for mutation in ('missing-duplicate', 'literal-tab'):
            altered = deepcopy(table)
            altered['item']['id'] = mutation
            packet = json.loads(altered['item']['aggregated_output'])
            if mutation == 'missing-duplicate':
                packet['call_sites']['edges'].pop(0)
            else:
                packet['sources'][0]['source'] = packet['sources'][0]['source'].replace('\t', '\\t', 1)
            altered['item']['aggregated_output'] = JSON_TABLE._json(packet) + '\n'
            invalid = self.recognize([altered])
            self.assert_no_source(invalid)
            self.assertFalse(invalid['search_batch_used'])

    def test_empty_input_still_validates_frozen_inventory_and_historical_files_unchanged(self):
        expected = {
            'source_call_evidence.py': '5f7fdf492ab5ea6e9f23b2be2f74b6be4978209ee267180fde9c8d904c193150',
            'call_table_evidence.py': 'e28c0c0fbdbfffc5c87204e96fdbd340ec4a328bac04be7523cab9d304146dab',
            'json_call_table_evidence.py': 'e32b375b05e2166f4cd03cd9d538b6fa4de4e3000edffaf178e828c9a68c16dc',
            'search_batch_evidence.py': 'f4b4b76d5756302e100bbe66e7c41e8dd0d9d3040932c2bafb349dff43cecb79',
        }
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256((ROOT / 'evals/exploration' / name).read_bytes()).hexdigest(), digest)
        result = self.recognize(OneShot([]))
        self.assert_no_source(result)
        self.assertFalse(result['search_batch_used'])
        self.assertEqual(result['search_batch_receipts'], [])
        self.fixture.binding['source_manifest']['calls.py'] = '0' * 64
        with self.assertRaises(ValueError):
            self.recognize(OneShot([]))


if __name__ == '__main__':
    unittest.main()
