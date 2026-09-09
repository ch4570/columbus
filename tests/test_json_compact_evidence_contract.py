"""Actual mixed deliveries keep encoding, source and reviewed utility separate."""
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
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


JSON_TABLE = load('json_contract_json', 'evals/exploration/json_call_table_evidence.py')
TEXT_TABLE = load('json_contract_text', 'evals/exploration/call_table_evidence.py')
SEARCH = load('json_contract_search', 'evals/exploration/search_batch_evidence.py')
OLD = load('json_contract_old', 'evals/exploration/source_call_evidence.py')
FIXTURES = load('json_contract_fixtures', 'tests/test_source_call_evidence.py')


class JsonCompactEvidenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A private fixture class avoids duplicating historical test discovery.
        cls.controls = type('_JsonContractControls', (FIXTURES.SourceCallEvidenceTests,), {})
        cls.controls.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.controls.tearDownClass()

    def setUp(self):
        self.fixture = self.controls()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        source = self.fixture.repo / 'calls.py'
        source.write_bytes(source.read_bytes().replace(
            b'    ping()\n', b'    ping()  # actual:\t literal:\\t\n', 1))
        self.fixture.freeze()

    def event(self, operation, queries, *options, number):
        argv = [*self.fixture.binding['invocation_prefix'], operation, *queries,
                '--input', str(self.fixture.graph), '--repo', str(self.fixture.repo),
                '--budget-bytes', '64000', *options]
        result = subprocess.run(argv, cwd=self.fixture.repo, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
        self.assertEqual(result.stderr, b'')
        self.assertTrue(result.stdout.endswith(b'\n'))
        return dict(type='item.completed', item=dict(id=number, type='command_execution',
                    command=shlex.join(argv), status='completed', exit_code=0,
                    aggregated_output=result.stdout.decode('utf-8')))

    def recognize(self, events, relationships=None):
        return JSON_TABLE.evidence(events, binding=self.fixture.binding,
            relationships=self.fixture.reviewed if relationships is None else relationships)

    def test_actual_mixed_stream_assigns_each_encoding_to_its_own_verifier(self):
        legacy = self.event('archive-source', ['outer'], '--call-sites',
                            '--format', 'json', number='legacy')
        text = self.event('archive-source', ['outer'], '--call-sites', '--call-table',
                          '--format', 'text', number='text-table')
        compact = self.event('archive-source', ['outer'], '--call-sites', '--call-table',
                             '--format', 'json', number='json-table')
        search = self.event('archive-search', ['outer', 'ping'], number='search')
        offered = deepcopy(compact)
        offered['type'] = 'item.started'
        events = [offered, search, legacy, text, compact]
        before, binding = deepcopy(events), deepcopy(self.fixture.binding)
        for verifier, expected in ((OLD, 'legacy'), (TEXT_TABLE, 'text-table'),
                                   (JSON_TABLE, 'json-table')):
            with self.subTest(expected=expected):
                result = verifier.evidence(iter(events), binding=binding,
                                           relationships=self.fixture.reviewed)
                self.assertEqual([r['command_id'] for r in result['source_call_receipts']], [expected])
                self.assertEqual([r['command_id'] for r in result['relationship_receipts']], [expected])
                self.assertTrue(result['relationship_used'])
        discovery = SEARCH.evidence(iter(events), binding=binding)
        self.assertEqual(set(discovery), {'recognizer_version', 'search_batch_receipts'})
        self.assertEqual([r['command_id'] for r in discovery['search_batch_receipts']], ['search'])
        self.assertEqual(events, before)
        self.assertEqual(binding, self.fixture.binding)
        self.assertFalse((self.fixture.repo / '.columbus').exists())

    def test_json_defaults_preserve_exact_source_and_complete_packet_roundtrip(self):
        legacy_event = self.event('archive-source', ['outer'], '--call-sites', number='legacy')
        implicit = self.event('archive-source', ['outer'], '--call-sites', '--call-table', number='implicit')
        explicit = self.event('archive-source', ['outer'], '--call-sites', '--call-table',
                              '--format', 'json', number='explicit')
        self.assertEqual(implicit['item']['aggregated_output'], explicit['item']['aggregated_output'])
        full = json.loads(legacy_event['item']['aggregated_output'])
        compact = json.loads(implicit['item']['aggregated_output'])
        self.assertEqual({k: v for k, v in compact.items() if k != 'call_sites'},
                         {k: v for k, v in full.items() if k != 'call_sites'})
        exact = '\n'.join((self.fixture.repo / 'calls.py').read_text().split('\n')[:8])
        self.assertEqual(compact['sources'][0]['source'], exact)
        self.assertIn('actual:\t literal:\\t', exact)
        calls = compact['call_sites']
        self.assertEqual(calls['format'], 'columbus-call-table-json/v1')
        self.assertEqual(calls['index_scope'], 'this packet')
        nodes = [dict(declaration, path=calls['files'][file_index][0],
                      source_hash=calls['files'][file_index][1])
                 for file_index, declaration in calls['nodes']]
        edges = []
        for source, target, file_index, relationship in calls['edges']:
            self.assertIs(type(source), int)
            self.assertIs(type(target), int)
            self.assertIs(type(file_index), int)
            path, source_hash = calls['files'][file_index]
            self.assertEqual((path, source_hash), (nodes[source]['path'], nodes[source]['source_hash']))
            edges.append(dict(relationship, source=nodes[source]['id'], target=nodes[target]['id'], path=path))
        expanded = {k: v for k, v in calls.items() if k not in {'format', 'index_scope', 'files', 'nodes', 'edges'}}
        compact['call_sites'] = dict(expanded, nodes=nodes, edges=edges)
        self.assertEqual(compact, full)
        self.assertEqual(len(edges), 6)  # Includes the duplicate stored edge.
        receipts = self.recognize([implicit, explicit])['source_call_receipts']
        self.assertEqual([r['command_id'] for r in receipts], ['implicit', 'explicit'])
        self.assertEqual(receipts[0]['output_sha256'], receipts[1]['output_sha256'])
        self.assertNotEqual(receipts[0]['command_sha256'], receipts[1]['command_sha256'])
        self.assertEqual(receipts[0]['output_sha256'], hashlib.sha256(
            implicit['item']['aggregated_output'].encode('utf-8')).hexdigest())

    def test_tab_to_literal_escape_corruption_loses_all_json_delivery_credit(self):
        event = self.event('archive-source', ['outer'], '--call-sites', '--call-table', number='json')
        self.assertTrue(self.recognize([event])['relationship_used'])
        packet = json.loads(event['item']['aggregated_output'])
        original = packet['sources'][0]['source']
        packet['sources'][0]['source'] = original.replace('\t', '\\t', 1)
        self.assertNotEqual(packet['sources'][0]['source'], original)
        event['item']['aggregated_output'] = json.dumps(packet, ensure_ascii=False, separators=(',', ':')) + '\n'
        result = self.recognize([event])
        self.assertFalse(result['json_call_table_used'])
        self.assertFalse(result['relationship_used'])
        self.assertEqual(result['source_call_receipts'], [])
        self.assertEqual(result['relationship_receipts'], [])

    def test_copy_safe_delivery_without_reviewed_edge_is_not_quality_or_utility(self):
        event = self.event('archive-source', ['outer'], '--call-sites', '--call-table', number='json')
        result = self.recognize([event], relationships=[])
        self.assertEqual(result['recognizer_version'], 'json-call-table-evidence-v1')
        self.assertTrue(result['json_call_table_used'])
        self.assertEqual(len(result['source_call_receipts']), 1)
        self.assertFalse(result['relationship_used'])
        self.assertEqual(result['relationship_receipts'], [])
        for unsupported in ('quality_passed', 'cost_passed', 'quotes_used', 'citation_passed'):
            self.assertNotIn(unsupported, result)


if __name__ == '__main__':
    unittest.main()
