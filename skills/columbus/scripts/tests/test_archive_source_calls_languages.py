"""Real multilingual exports retain page-scoped stored calls after relocation."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from columbus.archive import _validated_rows, archive
from columbus.index import RepositoryIndex
from columbus.languages import code_lines, decode_source
from columbus.source_calls import source_calls_archive, source_calls_json, source_calls_text
from columbus.sync_state import read_stable


class ArchiveSourceCallsLanguageTests(unittest.TestCase):
    @staticmethod
    def _edge_multiset(edges):
        return Counter(json.dumps(edge, sort_keys=True, ensure_ascii=False) for edge in edges)

    def _exercise(self, path, language, body, expected_fidelity):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            producer, consumer = workspace / 'producer', workspace / 'relocated'
            producer.mkdir()
            consumer.mkdir()
            (producer / path).write_bytes(body)
            (consumer / path).write_bytes(body)
            index = RepositoryIndex(producer / '.columbus' / 'index.sqlite')
            index.refresh(producer)
            # Exact query IDs come from actual indexed declarations, never a
            # synthetic guess about a language's identity encoding.
            with index._read() as connection:
                indexed = [json.loads(row[0]) for row in connection.execute('SELECT data FROM symbols')]
            chosen = []
            for name in ('tail', 'run'):
                matches = [node for node in indexed if node['path'] == path and node['name'] == name]
                self.assertEqual(len(matches), 1, (language, name, indexed))
                chosen.append(matches[0])
            queries = [node['id'] for node in chosen]
            if language == 'javascript':
                self.assertTrue(all('partial' not in node for node in chosen))
            expected_positions = sorted({(path, number) for node in chosen
                                         for number in range(node['start_line'], node['end_line'] + 1)})
            decoded = code_lines(decode_source(path, body, language=language), language)
            expected_source = [(key, number, decoded[number - 1]) for key, number in expected_positions]
            expected_hash = hashlib.sha256(body).hexdigest()

            for codec in ('gzip', 'xz'):
                artifact = workspace / ('graph.' + codec)
                archive(index, artifact, compression=codec)
                with artifact.open('rb') as stream:
                    records = list(_validated_rows(stream))
                nodes = {data['id']: data for kind, data in records if kind == 'node'}
                hashes = {data['path']: data['hash'] for kind, data in records if kind == 'file'}
                stored = [data for kind, data in records if kind == 'edge' and data['kind'] == 'calls']
                references = [data for kind, data in records
                              if kind == 'reference' and data['kind'] == 'calls']
                expected_edges = [edge for edge in stored
                                  if (edge['path'], edge['line']) in set(expected_positions)]
                self.assertTrue(any(edge['source'] != edge['target'] for edge in expected_edges),
                                (language, 'fixture must exercise a real stored non-self call', stored))
                self.assertEqual(hashes[path], expected_hash)

                # The consumer has only relocated source. Prevent discovery,
                # current language inference, and every SQLite connection while
                # querying; source decoding must use archived language metadata.
                with patch('columbus.discovery.load_config', side_effect=AssertionError('consumer config read')), \
                     patch('columbus.languages.language_for', side_effect=AssertionError('consumer language inference')), \
                     patch('columbus.index.sqlite3.connect', side_effect=AssertionError('consumer index access')):
                    for fmt in ('json', 'text'):
                        with self.subTest(language=language, codec=codec, format=fmt):
                            full = source_calls_archive(artifact, queries, consumer,
                                                        budget_bytes=64000, output_format=fmt)
                            self.assertEqual(self._edge_multiset(full['call_sites']['edges']),
                                             self._edge_multiset(expected_edges))
                            offset, positions, page_edges = 0, [], []
                            for _ in range(len(expected_positions) + 1):
                                with patch('columbus.source_calls.read_stable', wraps=read_stable) as reads:
                                    packet = source_calls_archive(artifact, queries, consumer, limit=2,
                                        offset=offset, budget_bytes=64000, output_format=fmt)
                                self.assertEqual([call.args[1] for call in reads.call_args_list], [path])
                                self.assertEqual([target['id'] for target in packet['targets']], queries)
                                for target in packet['targets']:
                                    self.assertEqual(target['partial'], nodes[target['id']].get('partial'))
                                    if language == 'javascript':
                                        self.assertIsNone(target['partial'])
                                self.assertEqual(packet['total_lines'], len(expected_positions))
                                returned = [(block['path'], number, line) for block in packet['sources']
                                    for number, line in enumerate(block['source'].split('\n'), block['start_line'])]
                                physical = {(key, number) for key, number, _ in returned}
                                self.assertEqual(returned, expected_source[offset:offset + len(returned)])
                                expected_page_edges = [edge for edge in stored
                                                       if (edge['path'], edge['line']) in physical]
                                calls = packet['call_sites']
                                self.assertEqual(self._edge_multiset(calls['edges']),
                                                 self._edge_multiset(expected_page_edges))
                                self.assertEqual(calls['scope'], 'returned_source')
                                self.assertIs(calls['stored_call_sites_complete'], True)
                                self.assertIs(calls['semantic_complete'], False)
                                self.assertIs(packet['semantic_complete'], False)
                                for resolved, counter in ((False, 'unresolved_call_reference_count'),
                                                          (True, 'resolved_call_reference_count')):
                                    self.assertEqual(calls[counter], sum(reference['resolved'] is resolved
                                        and (reference['path'], reference['line']) in physical
                                        for reference in references))
                                expected_endpoints = {edge[key] for edge in expected_page_edges
                                                      for key in ('source', 'target')}
                                self.assertEqual({node['id'] for node in calls['nodes']}, expected_endpoints)
                                for node in calls['nodes']:
                                    archived = nodes[node['id']]
                                    for key in ('path', 'name', 'kind', 'start_line', 'end_line',
                                                'language', 'fidelity'):
                                        self.assertEqual(node[key], archived[key])
                                    self.assertEqual(node['partial'], archived.get('partial'))
                                    if 'partial' in archived:
                                        self.assertIsInstance(node['partial'], bool)
                                    else:
                                        self.assertIsNone(node['partial'])
                                    self.assertEqual(node['language'], language)
                                    self.assertEqual(node['fidelity'], expected_fidelity)
                                    self.assertEqual(node['source_hash'], hashes[node['path']])
                                self.assertEqual(json.loads(source_calls_json(packet)), packet)
                                text = source_calls_text(packet)
                                self.assertEqual([json.loads(line.removeprefix('call_node '))
                                                  for line in text.splitlines() if line.startswith('call_node ')],
                                                 calls['nodes'])
                                self.assertEqual([json.loads(line.removeprefix('call_edge '))
                                                  for line in text.splitlines() if line.startswith('call_edge ')],
                                                 calls['edges'])
                                rendered = text if fmt == 'text' else source_calls_json(packet)
                                self.assertLessEqual(len(rendered.encode('utf-8')), 64000)
                                positions.extend(returned)
                                page_edges.extend(calls['edges'])
                                if packet['next_offset'] is None:
                                    break
                                self.assertEqual(packet['next_offset'], offset + len(returned))
                                offset = packet['next_offset']
                            else:
                                self.fail('Source cursor did not terminate')
                            self.assertEqual(positions, expected_source)
                            self.assertEqual(len(positions), len({row[:2] for row in positions}))
                            self.assertEqual(self._edge_multiset(page_edges), self._edge_multiset(expected_edges))
                self.assertEqual(sorted(item.name for item in consumer.iterdir()), [path])

    def test_java_real_export_pages_match_stored_calls(self):
        source = ('package sample;\nclass Entry {\n'
                  '  static int helper() { return 1; }\n'
                  '  static int run() {\n'
                  '    int first = helper();\n'
                  '    missing();\n'
                  '    return first + helper();\n'
                  '  }\n\n'
                  '  static int tail() {\n'
                  '    return helper();\n'
                  '  }\n}\n')
        self._exercise('Entry.java', 'java', source.replace('\n', '\r\n').encode('utf-8'), 'ast')

    def test_kotlin_real_export_pages_match_stored_calls(self):
        source = ('package sample\nfun helper(): Int = 1\n'
                  'fun run(): Int {\n'
                  '    val first = helper()\n'
                  '    missing()\n'
                  '    return first + helper()\n'
                  '}\n\n'
                  'fun tail(): Int {\n'
                  '    return helper()\n'
                  '}\n')
        self._exercise('entry.kt', 'kotlin', b'\xef\xbb\xbf' + source.encode('utf-8'), 'ast')

    def test_javascript_real_export_pages_match_stored_calls(self):
        source = ('export function helper() { return 1; }\n'
                  'export function run() {\n'
                  '  const first = helper(); // caf\u00e9\n'
                  '  missing();\n'
                  '  return first + helper();\n'
                  '}\n\n'
                  'export function tail() {\n'
                  '  return helper();\n'
                  '}\n')
        self._exercise('entry.js', 'javascript', source.encode('utf-8'), 'heuristic')


if __name__ == '__main__':
    unittest.main()
