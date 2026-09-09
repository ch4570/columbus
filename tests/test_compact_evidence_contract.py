"""Future receipts stay separate and do not change historical recognition."""
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import shlex
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TABLE = load('compact_contract_table', ROOT / 'evals/exploration/call_table_evidence.py')
SEARCH = load('compact_contract_search', ROOT / 'evals/exploration/search_batch_evidence.py')
OLD = load('compact_contract_old', ROOT / 'evals/exploration/source_call_evidence.py')
FIXTURES = load('compact_contract_fixtures', ROOT / 'tests/test_source_call_evidence.py')


class CompactEvidenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Keep runtime state private; do not expose another inherited TestCase
        # at module scope and accidentally discover its historical tests twice.
        cls.controls = type('_CompactControls', (FIXTURES.SourceCallEvidenceTests,), {})
        cls.controls.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.controls.tearDownClass()

    def setUp(self):
        self.fixture = self.controls()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def event(self, operation, queries, *options, number='control'):
        argv = [*self.fixture.binding['invocation_prefix'], operation, *queries,
                '--input', str(self.fixture.graph), '--repo', str(self.fixture.repo), *options]
        result = subprocess.run(argv, cwd=self.fixture.repo, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
        self.assertEqual(result.stderr, b'')
        return dict(type='item.completed', item=dict(id=number, type='command_execution',
                    command=shlex.join(argv), status='completed', exit_code=0,
                    aggregated_output=result.stdout.decode('utf-8')))

    def test_actual_mixed_stream_never_promotes_search_to_source_or_relationship(self):
        table = self.event('archive-source', ['outer'], '--call-sites', '--call-table',
                           '--format', 'text', '--budget-bytes', '64000', number='table')
        search = self.event('archive-search', ['outer', 'ping'], '--format', 'text',
                            '--budget-bytes', '64000', number='search')
        offered = deepcopy(table)
        offered['type'] = 'item.started'
        events = [offered, search, table]
        before, binding = deepcopy(events), deepcopy(self.fixture.binding)
        delivered = TABLE.evidence(iter(events), binding=binding, relationships=self.fixture.reviewed)
        discovered = SEARCH.evidence(iter(events), binding=binding)
        historical = OLD.evidence(iter(events), binding=binding, relationships=self.fixture.reviewed)
        self.assertEqual([row['command_id'] for row in delivered['source_call_receipts']], ['table'])
        self.assertEqual([row['command_id'] for row in delivered['relationship_receipts']], ['table'])
        self.assertTrue(delivered['call_table_used'])
        self.assertTrue(delivered['relationship_used'])
        self.assertEqual(set(discovered), {'recognizer_version', 'search_batch_receipts'})
        self.assertEqual([row['command_id'] for row in discovered['search_batch_receipts']], ['search'])
        self.assertEqual(historical['source_call_receipts'], [])
        self.assertEqual(historical['relationship_receipts'], [])
        self.assertEqual(events, before)
        self.assertEqual(binding, self.fixture.binding)
        self.assertFalse((self.fixture.repo / '.columbus').exists())

    def test_table_adoption_without_reviewed_edge_is_not_graph_utility(self):
        event = self.event('archive-source', ['outer'], '--call-sites', '--call-table',
                           '--format', 'text', '--budget-bytes', '64000')
        result = TABLE.evidence([event], binding=self.fixture.binding, relationships=[])
        self.assertTrue(result['call_table_used'])
        self.assertEqual(len(result['source_call_receipts']), 1)
        self.assertEqual(result['relationship_receipts'], [])
        self.assertFalse(result['relationship_used'])
        self.assertNotIn('quality_passed', result)
        self.assertNotIn('cost_passed', result)

    def test_search_json_and_text_bind_distinct_wire_bytes_without_graph_fields(self):
        outputs = []
        for form in ('json', 'text'):
            event = self.event('archive-search', ['missing-one', 'missing-two'], '--format', form)
            result = SEARCH.evidence([event], binding=self.fixture.binding)
            self.assertEqual(set(result), {'recognizer_version', 'search_batch_receipts'})
            self.assertEqual(len(result['search_batch_receipts']), 1)
            receipt = result['search_batch_receipts'][0]
            self.assertFalse(receipt['useful_discovery'])
            self.assertEqual(receipt['source_rows'], 0)
            self.assertEqual(receipt['edges'], 0)
            output = event['item']['aggregated_output'].encode('utf-8')
            self.assertEqual(receipt['output_sha256'], hashlib.sha256(output).hexdigest())
            outputs.append(output)
        self.assertNotEqual(outputs[0], outputs[1])


if __name__ == '__main__':
    unittest.main()
