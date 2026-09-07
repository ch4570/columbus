import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from columbus.index import RepositoryIndex, byte_size
from columbus.presentation import render
from columbus.receipts import ReceiptFile


class AgentContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'payments.py').write_text('def refund(amount):\n    return amount\n')
        (self.root / 'orders.py').write_text('from payments import refund\ndef cancel():\n    return refund(10)\n')
        (self.root / 'noise.py').write_text('def unrelated():\n' + '    # padding\n' * 2000 + '    return 0\n')
        self.index = RepositoryIndex(self.root / '.columbus/index.sqlite')
        self.index.refresh(self.root)

    def test_bounded_context_distinguishes_semantics_from_output_truncation(self):
        (self.root / 'broken.py').write_text('def broken(:\n')
        (self.root / 'unknown.py').write_text('def unknown(): return missing()\n')
        status = self.index.refresh(self.root)
        for mode in ('snippets', 'signatures'):
            for output_format in ('json', 'text'):
                packet = self.index.context('broken.py::module', mode=mode,
                    output_format=output_format, budget_bytes=2048)
                self.assertTrue(any(i.get('partial') for i in packet['items']))
                self.assertFalse(packet['semantic_complete'])
                self.assertEqual(packet['repository_diagnostic_count'], len(status['diagnostics']))
                self.assertEqual(packet['repository_unresolved_references'], status['unresolved_references'])
                self.assertEqual(packet['partial_nodes'], sum(bool(i.get('partial')) for i in packet['items']))
                rendered = render(packet, output_format)
                self.assertLessEqual(len(rendered.encode()), 2048)
                self.assertIn('repository_diagnostic_count', rendered)
        related = self.index.neighbors('broken.py::module')
        self.assertFalse(related['truncated'])
        self.assertFalse(related['semantic_complete'])
        self.assertEqual(related['repository_diagnostic_count'], len(status['diagnostics']))

    def test_outline_and_signatures_never_read_source(self):
        with patch.object(self.index, '_source', side_effect=AssertionError('source read')):
            outline = self.index.repo_map(budget_bytes=2048)
            packet = self.index.context('refund', mode='signatures', budget_bytes=2048)
        self.assertTrue(outline['items'])
        self.assertIn('refund', json.dumps(outline))
        self.assertTrue(packet['items'])
        self.assertTrue(all('source' not in item for item in packet['items']))
        self.assertLessEqual(byte_size(outline), 2048)
        self.assertEqual(outline['coverage']['files'], 3)
        self.assertEqual(outline['coverage']['symbols'], self.index.status()['symbols'])

    def test_budget_unicode_exclusions_and_accounting(self):
        for mode in ('signatures', 'snippets'):
            packet = self.index.context('refund', budget_tokens=700, mode=mode)
            self.assertLessEqual(packet['estimated_tokens'], 700)
            self.assertEqual(packet['used_bytes'], byte_size(packet))
            self.assertLessEqual(byte_size(packet), 2100)
            self.assertLess(packet['economy']['response_bytes'], packet['economy']['indexed_source_bytes'])
            excluded = [i['id'] for i in packet['items']]
            next_packet = self.index.context('refund', exclude_ids=excluded, mode=mode)
            self.assertFalse(set(excluded) & {i['id'] for i in next_packet['items']})
        with self.assertRaises(ValueError):
            self.index.context('refund', budget_tokens=1)

    def test_no_overlapping_source_ranges_and_stale_source_excluded(self):
        packet = self.index.context('refund')
        covered = set()
        for item in packet['items']:
            for line in range(item['start_line'], item['excerpt_end_line'] + 1):
                location = item['path'], line
                self.assertNotIn(location, covered)
                covered.add(location)
        (self.root / 'payments.py').write_text('def renamed(): return 2\n')
        stale = self.index.context('refund')
        self.assertGreater(stale['stale_candidates'], 0)
        self.assertFalse(any(i['path'] == 'payments.py' for i in stale['items']))

    def test_map_query_and_search_filters(self):
        result = self.index.repo_map('refund', path='payments*', budget_bytes=2048)
        self.assertTrue(result['items'])
        self.assertTrue(all(i['path'] == 'payments.py' for i in result['items']))
        hits = self.index.search('refund', path='orders*', language='python')['hits']
        self.assertTrue(hits)
        self.assertTrue(all(i['path'] == 'orders.py' for i in hits))

    def test_graph_focus_filters_and_file_projection(self):
        graph = self.index.graph(focus='refund', hops=1, kinds=['calls'])
        self.assertIn('cancel', [n['name'] for n in graph['nodes']])
        self.assertTrue(all(e['kind'] == 'calls' for e in graph['edges']))
        graph = self.index.graph(level='file', kinds=['calls'])
        self.assertEqual({n['path'] for n in graph['nodes']}, {'payments.py', 'orders.py', 'noise.py'})
        self.assertTrue(any(e['source'] == 'orders.py::module' and e['target'] == 'payments.py::module' for e in graph['edges']))
        focused = self.index.graph(focus='refund', level='file', kinds=['calls'])
        self.assertEqual(focused['center'], 'payments.py::module')
        self.assertIn(focused['center'], {n['id'] for n in focused['nodes']})
        filtered = self.index.graph(path='payments*')
        self.assertTrue(all(n['path'] == 'payments.py' for n in filtered['nodes']))
        self.assertFalse(filtered['edges'] and any(e['source'] not in {n['id'] for n in filtered['nodes']} for e in filtered['edges']))

class FullFileRetrievalTests(unittest.TestCase):
    def test_late_file_match_returns_matching_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'long.py').write_text('# filler\n' * 3000 + '# unique_late_behavior\n')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            result = index.context('unique_late_behavior', budget_bytes=2048)
            self.assertTrue(result['items'])
            self.assertIn('unique_late_behavior', result['items'][0]['source'])
            self.assertGreater(result['items'][0]['start_line'], 2900)

    def test_final_metadata_cannot_break_a_valid_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'foo.py').write_text('\n'.join('def refund_%d():\n    return %d\n' % (n, n) for n in range(12)))
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            full = index.context('refund', mode='signatures', budget_bytes=64000)
            for budget in range(max(2048, byte_size(full) - 15), byte_size(full) + 15):
                packet = index.context('refund', mode='signatures', budget_bytes=budget)
                self.assertLessEqual(byte_size(packet), budget)
                self.assertEqual(byte_size(packet), packet['used_bytes'])

    def test_file_projection_includes_each_path_once_even_with_package_modules(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'Foo.pm').write_text('package Foo;\nsub run { return 1; }\n1;\n')
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            graph = index.graph(level='file')
            self.assertEqual([n['id'] for n in graph['nodes']], ['Foo.pm::module'])


class DeclarationExcerptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = ('def outside_before():\n'
                       '    return "needle needle needle needle"\n\n'
                       'def investigate():\n'
                       + ''.join(f'    # prefix {n:03d}\n' for n in range(120))
                       + '    # needle; investigate investigate investigate\n'
                       + ''.join(f'    # suffix {n:03d}\n' for n in range(120))
                       + '    return "COMPLETE_END"\n\n'
                       + 'def outside_after():\n'
                       + '    return "needle needle needle needle"\n')
        (self.root / 'long.py').write_text(self.source)
        (self.root / 'report.py').write_text('class Report:\n'
            + ''.join(f'    row_{n} = {n}\n' for n in range(140))
            + '    late = "class_needle"\n')
        self.index = RepositoryIndex(self.root / '.columbus/index.sqlite')
        self.index.refresh(self.root)

    def source_for(self, symbol_id, query):
        with self.index._read() as conn:
            return self.index._source(conn, self.index._find(conn, symbol_id), 80, query=query)

    def test_long_function_and_class_start_near_query_match(self):
        for symbol, query in (('investigate', 'needle'), ('Report', 'class_needle')):
            with self.subTest(symbol=symbol):
                excerpt = self.source_for(symbol, query)
                self.assertIn(query, excerpt['source'])
                self.assertGreater(excerpt['start_line'], 100)
                self.assertLessEqual(len(excerpt['source'].splitlines()), 80)
                self.assertTrue(excerpt['truncated'])
                self.assertEqual(excerpt['freshness'], 'source_hash_verified')

    def test_exact_name_preserves_header_despite_more_body_occurrences(self):
        for symbol, header in (('investigate', 'def investigate():'), ('Report', 'class Report:')):
            excerpt = self.source_for(symbol, symbol)
            declaration = self.index.symbol(symbol, max_lines=1)
            self.assertEqual(excerpt['start_line'], declaration['start_line'])
            self.assertTrue(excerpt['source'].startswith(header))
            self.assertEqual(excerpt['source_hash'], declaration['source_hash'])
            self.assertEqual(excerpt['source_view_hash'], declaration['source_view_hash'])

    def test_query_excerpt_cannot_select_stronger_matches_in_other_declarations(self):
        excerpt = self.source_for('investigate', 'needle')
        self.assertNotIn('outside_', excerpt['source'])
        self.assertNotIn('needle needle needle needle', excerpt['source'])
        declaration = self.index.symbol('investigate', max_lines=1)
        self.assertGreaterEqual(excerpt['start_line'], declaration['start_line'])
        self.assertLessEqual(excerpt['excerpt_end_line'], declaration['end_line'])
        # No in-scope match keeps the declaration header, even though another
        # function in the same file contains an exact match.
        absent = self.source_for('investigate', 'outside_after')
        self.assertEqual(absent['start_line'], declaration['start_line'])

    def test_context_receipt_exhausts_both_sides_of_query_center_with_no_repetition(self):
        excluded = [node['id'] for node in self.index.graph()['nodes'] if node['name'] != 'investigate']
        for output_format in ('json', 'text'):
            with self.subTest(output_format=output_format):
                receipt_path = self.root / '.columbus' / (output_format + '.json')
                emitted, starts = {}, []
                for _ in range(30):
                    receipt = ReceiptFile(str(receipt_path), self.index.status())
                    packet = self.index.context('needle', path='long.py', budget_bytes=2048,
                        output_format=output_format, exclude_ids=excluded, receipt=receipt.data)
                    self.assertLessEqual(len(render(packet, output_format).encode('utf-8')), 2048)
                    receipt.save(packet)
                    if not packet['items']:
                        self.assertGreater(packet['seen_candidates'], 0)
                        break
                    for item in packet['items']:
                        self.assertEqual(item['name'], 'investigate')
                        starts.append(item['start_line'])
                        if not emitted:
                            self.assertIn('needle', item['source'])
                            self.assertGreater(item['start_line'], 100)
                        for offset, character in enumerate(item['source'], item['source_start_offset']):
                            self.assertNotIn(offset, emitted)
                            emitted[offset] = character
                else:
                    self.fail('Receipt did not exhaust the declaration')
                self.assertTrue(any(start < starts[0] for start in starts))
                self.assertTrue(any(start > starts[0] for start in starts))
                declaration_start = self.source.index('def investigate():')
                declaration_end = self.source.index('\n\ndef outside_after')
                expected = {offset: character for offset, character in enumerate(self.source)
                            if declaration_start <= offset < declaration_end and character != '\n'}
                self.assertEqual({offset: character for offset, character in emitted.items() if character != '\n'}, expected)


class CustomLanguageIndexTests(unittest.TestCase):
    def test_config_change_replaces_facts_and_matches_clean_rebuild(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'logic.custom'
            source.write_text('routine old_action\noperation new_action\n')
            config = root / '.columbus.json'
            config.write_text(json.dumps({'extensions': {'.custom': 'custom'}, 'declarations': {'custom': ['routine']}}))
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            first = index.refresh(root, fast=True)
            self.assertEqual(index.search('old_action')['hits'][0]['name'], 'old_action')
            self.assertEqual(index.symbol('old_action')['language'], 'custom')
            config.write_text(json.dumps({'extensions': {'.custom': 'custom'}, 'declarations': {'custom': ['operation']}}))
            self.assertEqual(index.status(True)['freshness'], 'stale')
            second = index.refresh(root, fast=True)
            self.assertNotEqual(first['revision'], second['revision'])
            self.assertEqual(index.search('new_action')['hits'][0]['name'], 'new_action')
            self.assertFalse(any(n['name'] == 'old_action' for n in index.graph()['nodes']))
            clean = RepositoryIndex(root / '.columbus/rebuilt.sqlite')
            clean.refresh(root)
            self.assertEqual(index.graph(), clean.graph())


if __name__ == '__main__':
    unittest.main()
