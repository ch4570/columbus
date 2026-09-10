"""File graph limits apply to useful projected edges, with bounded SQL results."""
from contextlib import closing
import itertools
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from columbus.index import RepositoryIndex


class FileProjectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.index = RepositoryIndex(self.root / '.columbus/index.sqlite')

    def write(self, path, source):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding='utf-8')

    def replace_edges(self, edges):
        with closing(sqlite3.connect(self.index.db)) as conn, conn:
            conn.execute('DELETE FROM edges')
            conn.executemany('INSERT INTO edges VALUES(?,?,?,?,?,?,?)', edges)

    def test_early_containment_cannot_hide_late_cross_file_edges(self):
        self.write('a_many.py', ''.join(f'def f{i:05d}(): pass\n' for i in range(20000)))
        self.write('y_target.py', 'def target():\n    pass\n')
        self.write('z_caller.py', 'from y_target import target\n\ndef run():\n    target()\n')
        self.index.refresh(self.root)

        default = self.index.graph(level='file', limit=3)
        filtered = self.index.graph(level='file', limit=3, kinds=['calls', 'imports', 'inherits'])
        self.assertEqual(3, len(default['nodes']))
        self.assertEqual({'calls', 'imports'}, {e['kind'] for e in default['edges']})
        self.assertEqual(filtered['edges'], default['edges'])
        self.assertFalse(default['truncated'])
        self.assertFalse(filtered['truncated'])
        self.assertEqual({('z_caller.py::module', 'y_target.py::module', 1)},
                         {(e['source'], e['target'], e['count']) for e in default['edges']})

    def test_group_counts_cover_all_raw_edges_without_materializing_them(self):
        self.write('a.py', 'def call(): pass\n')
        self.write('b.py', 'def target(): pass\n')
        self.index.refresh(self.root)
        source, target = 'a.py::call:function', 'b.py::target:function'
        calls = ((source, target, 'calls', 'heuristic', f'call {line}', 'a.py', line)
                 for line in range(25001, 0, -1))
        self.replace_edges(itertools.chain(calls, [
            ('a.py::module', 'b.py::module', 'imports', 'resolved', 'import b', 'a.py', 1),
        ]))

        returned_edges = []

        class CountedConnection(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                cursor = super().execute(sql, parameters)
                columns = {column[0] for column in cursor.description or ()}
                if {'source', 'target', 'kind', 'evidence'} <= columns:
                    row_factory = cursor.row_factory

                    def record(cursor, row):
                        returned_edges.append(None)
                        if len(returned_edges) > 20001:
                            raise AssertionError('Graph materialized more than its edge cap plus sentinel')
                        return row_factory(cursor, row) if row_factory else row

                    cursor.row_factory = record
                return cursor

        connect = sqlite3.connect
        with patch('columbus.index.sqlite3.connect',
                   side_effect=lambda *args, **kwargs: connect(*args, **kwargs, factory=CountedConnection)):
            graph = self.index.graph(level='file')

        self.assertEqual(2, len(graph['edges']))
        calls = next(e for e in graph['edges'] if e['kind'] == 'calls')
        self.assertEqual(25001, calls['count'])
        self.assertEqual((1, 'call 1', 'heuristic'),
                         (calls['line'], calls['evidence'], calls['confidence']))
        self.assertFalse(graph['truncated'])
        self.assertEqual(2, len(returned_edges), 'SQL must return projected rows, not the raw relation set')

        symbols = self.index.graph()
        self.assertEqual(20000, len(symbols['edges']))
        self.assertTrue(symbols['truncated'])
        focused = self.index.graph(focus=source, level='file', kinds=['calls'], direction='out', hops=1)
        self.assertTrue(focused['truncated'])
        self.assertEqual(1000, focused['edges'][0]['count'])

    def test_representative_evidence_is_stable_across_insertion_order(self):
        self.write('a.py', 'def alpha(): pass\ndef zeta(): pass\n')
        self.write('b.py', 'def target(): pass\n')
        self.index.refresh(self.root)
        target = 'b.py::target:function'
        edges = [
            ('a.py::zeta:function', target, 'calls', 'resolved', 'earlier line', 'a.py', 1),
            ('a.py::alpha:function', target, 'calls', 'heuristic', 'z evidence', 'a.py', 4),
            ('a.py::alpha:function', target, 'calls', 'resolved', 'a evidence', 'a.py', 4),
            ('a.py::alpha:function', target, 'calls', 'heuristic', 'later line', 'a.py', 8),
        ]
        results = []
        for order in (edges, list(reversed(edges))):
            self.replace_edges(order)
            graph = self.index.graph(level='file', kinds=['calls'])
            focused = self.index.graph(focus=target, level='file', kinds=['calls'], direction='in', hops=1)
            self.assertEqual(graph['edges'], focused['edges'])
            self.assertEqual(4, graph['edges'][0]['count'])
            self.assertEqual(('a evidence', 4, 'resolved'),
                             tuple(graph['edges'][0][key] for key in ('evidence', 'line', 'confidence')))
            results.append(graph['edges'])
        self.assertEqual(*results)

    def test_actual_projected_overflow_and_exact_cap_are_reported(self):
        paths = [f'f{i:03d}.py' for i in range(143)]
        for path in paths:
            self.write(path, '')
        self.index.refresh(self.root)
        expected = [(a + '::module', b + '::module', 'calls')
                    for a in paths for b in paths if a != b]
        edges = [(a, b, kind, 'heuristic', 'fixture relation', a.split('::')[0], 1)
                 for a, b, kind in expected]
        for size, truncated in ((len(edges), True), (20000, False)):
            with self.subTest(raw_edges=size):
                self.replace_edges(reversed(edges[:size]))
                graph = self.index.graph(level='file', limit=len(paths))
                self.assertEqual(20000, len(graph['edges']))
                self.assertEqual(truncated, graph['truncated'])
                self.assertEqual(expected[:20000],
                                 [(e['source'], e['target'], e['kind']) for e in graph['edges']])
                self.assertTrue(all(e['count'] == 1 for e in graph['edges']))
                self.assertEqual(graph, self.index.graph(level='file', limit=len(paths)))

    def test_focus_filters_and_node_limit_retain_the_selected_scope(self):
        self.write('pkg/a.py', 'def target(): pass\n')
        self.write('pkg/z.py', 'from pkg.a import target\ndef one(): target()\ndef two(): target()\n')
        self.write('unrelated.py', 'def ignored(): pass\n')
        self.write('other.js', 'function ignored() {}\n')
        self.index.refresh(self.root)
        options = {'level': 'file', 'path': 'pkg/*', 'language': 'python', 'kinds': ['calls']}
        graph = self.index.graph(**options)
        focused = self.index.graph(focus='target', direction='in', hops=1, **options)
        self.assertEqual(graph['edges'], focused['edges'])
        self.assertEqual(graph['nodes'], focused['nodes'])
        self.assertEqual(2, graph['edges'][0]['count'])
        self.assertFalse(graph['truncated'])
        self.assertFalse(focused['truncated'])
        self.assertEqual('pkg/a.py::module', focused['center'])

        for focus in (None, 'target'):
            filtered = self.index.graph(focus=focus, **{**options, 'path': 'pkg/a.py'})
            self.assertEqual(['pkg/a.py::module'], [n['id'] for n in filtered['nodes']])
            self.assertEqual([], filtered['edges'])
            empty = self.index.graph(focus=focus, **{**options, 'language': 'ruby'})
            self.assertEqual(([], []), (empty['nodes'], empty['edges']))

        limited = self.index.graph(limit=1, **options)
        self.assertEqual(['pkg/a.py::module'], [n['id'] for n in limited['nodes']])
        self.assertEqual([], limited['edges'])
        self.assertTrue(limited['truncated'])
        focused = self.index.graph(focus='target', direction='in', hops=1, limit=2, **options)
        self.assertTrue(focused['truncated'])
        self.assertEqual(1, focused['edges'][0]['count'])


if __name__ == '__main__':
    unittest.main()
