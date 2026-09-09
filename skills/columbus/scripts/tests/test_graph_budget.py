"""Graph navigation bounds the complete payload, not only the node count."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from columbus.cli import main
from columbus.index import RepositoryIndex, byte_size
from columbus.presentation import render


class GraphBudgetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.index = RepositoryIndex(self.root / '.columbus/index.sqlite')

    def test_one_large_docstring_does_not_enter_default_graph_payload(self):
        (self.root / 'api.py').write_text('def documented():\n    """' + 'x' * 900000 + '"""\n    return 1\n')
        self.index.refresh(self.root)
        packet = self.index.neighbors('documented', direction='in', limit=1, kinds=['calls', 'inherits'])
        self.assertLessEqual(byte_size(packet), 12000)
        self.assertEqual('api.py::documented:function', packet['center'])
        self.assertNotIn('doc', packet['nodes'][0])
        self.assertEqual(900000, packet['omitted_text_bytes'])
        self.assertFalse(packet['traversal_truncated'])
        self.assertTrue(packet['payload_truncated'])

    def test_unicode_graph_preserves_connected_ids_and_reports_each_omission(self):
        source = 'def target(' + ', '.join(f'항목{n}=0' for n in range(120)) + '):\n    """' + '문서' * 800 + '"""\n    return 1\n'
        source += ''.join(f'def caller_{n:02}():\n    return target()\n' for n in range(40))
        (self.root / 'api.py').write_text(source, encoding='utf-8')
        self.index.refresh(self.root)
        complete = self.index.neighbors('target', direction='in', kinds=['calls'], budget_bytes=64000)
        for fmt in ('json', 'text'):
            for budget in (2048, 2100, 6000):
                packet = self.index.neighbors('target', direction='in', kinds=['calls'],
                                              budget_bytes=budget, output_format=fmt)
                size = len(render(packet, fmt).encode('utf-8'))
                self.assertEqual(size, packet['used_bytes'])
                self.assertLessEqual(size, budget)
                self.assertEqual((size + 2) // 3, packet['estimated_tokens'])
                ids = {node['id'] for node in packet['nodes']}
                self.assertIn(packet['center'], ids)
                self.assertTrue(packet['edges'])
                for edge in packet['edges']:
                    self.assertTrue({edge['source'], edge['target']} <= ids)
                    self.assertIn('confidence', edge)
                self.assertEqual(len(complete['edges']) - len(packet['edges']), packet['omitted_edges'])
                self.assertEqual(len(complete['nodes']) - len(packet['nodes']), packet['omitted_nodes'])
                self.assertFalse(packet['traversal_truncated'])
                self.assertTrue(packet['payload_truncated'])
                for node in packet['nodes']:
                    self.assertEqual('ast', node['fidelity'])
                    self.assertIn('partial', node)
                    self.assertLessEqual(len(node['signature'].encode('utf-8')), 240)

    def test_cli_json_text_and_pretty_obey_same_budget(self):
        (self.root / 'api.py').write_text('def target(): pass\ndef caller(): target()\n')
        for command in ('neighbors', 'impact'):
            for fmt in ('json', 'text'):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    status = main([command, 'target', '--repo', str(self.root), '--format', fmt,
                                   '--pretty', '--budget-tokens', '700'])
                self.assertEqual(0, status, err.getvalue())
                self.assertLessEqual(len(out.getvalue().encode('utf-8')), 2100)
                self.assertIn('caller', out.getvalue())

    def test_focused_export_and_context_keep_their_existing_traversal_scope(self):
        source = 'def target(): pass\n' + ''.join(f'def caller_{n:02}(): target()\n' for n in range(45))
        (self.root / 'api.py').write_text(source)
        self.index.refresh(self.root)
        graph = self.index.graph(focus='target', kinds=['calls'], direction='in', limit=100)
        self.assertEqual(45, len(graph['edges']))
        self.assertFalse(graph['truncated'])
        packet = self.index.context('target', budget_bytes=2048)
        self.assertTrue(packet['items'])

    def test_traversal_limits_are_distinct_from_serialization_omissions(self):
        (self.root / 'api.py').write_text('def target(): pass\ndef caller(): target()\n')
        self.index.refresh(self.root)
        packet = self.index.neighbors('target', direction='in', kinds=['calls'], limit=1)
        self.assertTrue(packet['traversal_truncated'])
        self.assertFalse(packet['payload_truncated'])
        self.assertEqual((0, 0), (packet['omitted_nodes'], packet['omitted_edges']))
        for options in ({'budget_bytes': 2047}, {'budget_bytes': 64001}, {'budget_bytes': True},
                        {'budget_tokens': 699}, {'output_format': 'html'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.index.neighbors('target', **options)

    def test_projection_updates_partial_counts_when_input_graph_reports_them(self):
        from columbus.graph_views import bounded_neighbors
        source = 'def target(): pass\n' + ''.join(f'def caller_{n:02}(): target()\n' for n in range(20))
        (self.root / 'api.py').write_text(source)
        self.index.refresh(self.root)
        graph = self.index._neighbors('target', direction='in', kinds=['calls'])
        for node in graph['nodes'][1:]:
            node['partial'] = True
        graph['partial_nodes'] = 20
        packet = bounded_neighbors(graph, 2048, None, 'json')
        self.assertLess(packet['partial_nodes'], 20)
        self.assertEqual(len(packet['nodes']) - 1, packet['partial_nodes'])
        self.assertLessEqual(byte_size(packet), 2048)


if __name__ == '__main__':
    unittest.main()
