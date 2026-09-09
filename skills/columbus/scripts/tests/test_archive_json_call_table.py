"""Lossless JSON call tables and format-specific bounded source paging."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from columbus import source_calls as api
from columbus.index import compact
import test_archive_call_table as text_tests


class ArchiveJsonCallTableTests(unittest.TestCase):
    fixture = staticmethod(text_tests.ArchiveCallTableTests.fixture)
    write_archive = staticmethod(text_tests.ArchiveCallTableTests.write_archive)

    @staticmethod
    def query(archive, root, **options):
        return api.source_calls_archive(archive, ['outer'], root, call_table=True, **options)

    @staticmethod
    def decode(output):
        packet = json.loads(output)
        calls = packet['call_sites']
        assert calls['format'] == 'columbus-call-table-json/v1'
        assert calls['index_scope'] == 'this packet'
        files, nodes, edges = calls['files'], [], []
        assert files == [list(pair) for pair in sorted({tuple(pair) for pair in files})]

        def reference(index, values):
            assert type(index) is int and 0 <= index < len(values)
            return values[index]

        for file_number, declaration in calls['nodes']:
            assert not {'path', 'source_hash'} & declaration.keys()
            path, digest = reference(file_number, files)
            nodes.append({**declaration, 'path': path, 'source_hash': digest})
        assert len({node['id'] for node in nodes}) == len(nodes)
        for source, target, file_number, relationship in calls['edges']:
            assert not {'source', 'target', 'path'} & relationship.keys()
            owner, callee = reference(source, nodes), reference(target, nodes)
            path, digest = reference(file_number, files)
            assert (owner['path'], owner['source_hash']) == (path, digest)
            edges.append({**relationship, 'source': owner['id'], 'target': callee['id'], 'path': path})
        packet['call_sites'] = {**{key: value for key, value in calls.items()
                                  if key not in {'format', 'index_scope', 'files', 'nodes', 'edges'}},
                                'nodes': nodes, 'edges': edges}
        return packet

    @staticmethod
    def update_file(root, body, path, content):
        (root / path).write_bytes(content)
        next(row['data'] for row in body if row['record'] == 'file' and row['data']['path'] == path).update(
            hash=hashlib.sha256(content).hexdigest(), size=len(content))

    def test_lossless_source_tabs_literal_escapes_metadata_and_duplicate_edges(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            controls = ''.join(chr(number) for number in (*range(32), *range(127, 160), 0x2028, 0x2029))
            body, _, _ = self.fixture(root, evidence=controls + '\\t\\n한😀', count=3)
            content = 'def outer():\n\tping()  # literal \\t \\n\n    other()\n    return "한\u2028\x85"\n'
            self.update_file(root, body, 'calls.py', content.encode())
            packet = self.query(self.write_archive(root, body), root, budget_bytes=64000)
            packet['call_sites']['extra_metadata'] = {'nested': [1, True, None, 'kept']}
            packet['call_sites']['nodes'][0]['extra_declaration'] = ['kept']
            packet['call_sites']['edges'][0]['extra_relationship'] = {'value': 'kept'}
            before = deepcopy(packet)
            output = api.source_calls_json(packet, call_table=True)
            self.assertEqual(self.decode(output), packet)
            self.assertEqual(packet, before)
            self.assertEqual(json.loads(output)['sources'][0]['source'], content.rstrip('\n'))
            self.assertEqual(len(self.decode(output)['call_sites']['edges']), 3)
            self.assertTrue(any(node['partial'] is None for node in self.decode(output)['call_sites']['nodes']))
            self.assertEqual(output.count('\n'), 1)
            self.assertTrue(output.endswith('\n'))
            self.assertFalse(any(char in output for char in controls if char != '\n'))

    def test_renderer_strict_flags_reserved_collisions_and_malformed_endpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body, _, _ = self.fixture(root)
            packet = self.query(self.write_archive(root, body), root)
            for bad in (None, 0, 1, 'true', [], {}):
                with self.assertRaisesRegex(ValueError, 'boolean'):
                    api.source_calls_json(packet, call_table=bad)
            for key in ('format', 'index_scope', 'files'):
                altered = deepcopy(packet)
                altered['call_sites'][key] = None
                with self.assertRaisesRegex(ValueError, 'Reserved'):
                    api.source_calls_json(altered, call_table=True)
            variants = []
            altered = deepcopy(packet)
            altered['call_sites']['nodes'].append(deepcopy(altered['call_sites']['nodes'][0]))
            variants.append(altered)
            for key, value in (('source', 'missing'), ('target', 'missing'), ('path', 'other.py'), ('source', [])):
                altered = deepcopy(packet)
                altered['call_sites']['edges'][0][key] = value
                variants.append(altered)
            for altered in [*variants, {}, {'call_sites': None}, {'call_sites': {'nodes': {}, 'edges': []}}]:
                with self.assertRaises(ValueError):
                    api.source_calls_json(altered, call_table=True)
            altered = deepcopy(packet)
            altered['call_sites']['untrusted_extra'] = float('nan')
            with self.assertRaises(ValueError):
                api.source_calls_json(altered, call_table=True)

    def test_long_shared_ids_fit_json_but_not_full_id_wire_or_legacy_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body, _, _ = self.fixture(root, id_size=900, count=24)
            archive = self.write_archive(root, body)
            packet = self.query(archive, root, budget_bytes=12000)
            self.assertIsNone(packet['next_offset'])
            self.assertEqual(len(packet['call_sites']['edges']), 24)
            self.assertLessEqual(len(api.source_calls_json(packet, call_table=True).encode()), 12000)
            self.assertEqual(self.decode(api.source_calls_json(packet, call_table=True)), packet)
            for form, render in (('json', api.source_calls_json), ('text', api.source_calls_text)):
                self.assertGreater(len(render(packet).encode()), 12000)
                old = api.source_calls_archive(archive, ['outer'], root, output_format=form, budget_bytes=12000)
                self.assertEqual(old['next_offset'], 1)
                self.assertEqual(old['call_sites']['edges'], [])

    def test_collection_hydration_exact_no_lf_bounds_and_actual_identity_sharing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for recursive, unique in ((True, False), (False, True)):
                body, _, _ = self.fixture(root, id_size=300, count=12, unique=unique, self_call=recursive)
                archive = self.write_archive(root, body)
                original_collect, original_hydrate = api._collect_calls, api._hydrate_table

                def json_bytes(value):
                    return len(compact(value).translate(api._TEXT_ESCAPES).encode())

                def collect(snapshot, bins, budget, **kwargs):
                    self.assertEqual(kwargs['table_format'], 'json')
                    cap = original_collect(snapshot, bins, budget, **kwargs)
                    for item in bins[:cap]:
                        identities = {edge[key] for edge in item['edges'] for key in ('source', 'target')}
                        bound = sum(json_bytes([0, 0, 0, {key: value for key, value in edge.items()
                                                        if key not in {'source', 'target', 'path'}}])
                                    for edge in item['edges']) + sum(json_bytes(identity) for identity in identities)
                        self.assertEqual(item['cost'], bound)
                        for edge in item['edges']:
                            self.assertIs(edge['source'], item['identities'][edge['source']])
                            self.assertIs(edge['target'], item['identities'][edge['target']])
                            self.assertIs(edge['path'], item['path'])
                    return cap

                def hydrate(snapshot, chosen, bins, cap, selected_paths, budget, **kwargs):
                    nodes, cap = original_hydrate(snapshot, chosen, bins, cap, selected_paths, budget, **kwargs)
                    for item in bins[:cap]:
                        needed = {edge[key] for edge in item['edges'] for key in ('source', 'target')}
                        files = {(nodes[identity]['path'], nodes[identity]['source_hash']) for identity in needed}
                        bound = sum(json_bytes([0, 0, 0, {key: value for key, value in edge.items()
                                                         if key not in {'source', 'target', 'path'}}])
                                    for edge in item['edges'])
                        bound += sum(json_bytes([0, {key: value for key, value in nodes[identity].items()
                                                     if key not in {'path', 'source_hash'}}]) for identity in needed)
                        bound += sum(json_bytes(list(pair)) for pair in files)
                        self.assertEqual(item['cost'], bound)
                        self.assertEqual(len(item['call_files']), len(files))
                        for edge in item['edges']:
                            self.assertIs(edge['source'], nodes[edge['source']]['id'])
                            self.assertIs(edge['target'], nodes[edge['target']]['id'])
                    return nodes, cap

                with patch.object(api, '_collect_calls', side_effect=collect), \
                     patch.object(api, '_hydrate_table', side_effect=hydrate):
                    self.query(archive, root, budget_bytes=64000)

    def test_exact_budgets_across_node_and_file_index_widths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for count in (9, 10, 99, 100):
                with self.subTest(maximum_index=count):
                    body, _, targets = self.fixture(root, count=count, unique=True, evidence='한\x85')
                    replacements = {}
                    for number, identity in enumerate(targets):
                        path = f'target{number:03d}.py'
                        content = b'def ping(): pass\n'
                        (root / path).write_bytes(content)
                        replacements[identity] = path + '::ping:function'
                        node = next(row['data'] for row in body if row['record'] == 'node' and row['data']['id'] == identity)
                        node.update(id=replacements[identity], path=path)
                        body.append(dict(record='file', data=dict(path=path, hash=hashlib.sha256(content).hexdigest(),
                                                                 size=len(content))))
                    for row in body:
                        if row['record'] == 'edge':
                            row['data']['target'] = replacements[row['data']['target']]
                    archive = self.write_archive(root, body)
                    packet = self.query(archive, root, offset=1, limit=1, budget_bytes=64000)
                    output = api.source_calls_json(packet, call_table=True)
                    calls = json.loads(output)['call_sites']
                    self.assertEqual(len(calls['files']), count + 1)
                    self.assertEqual(len(calls['nodes']), count + 1)
                    self.assertEqual(calls['nodes'][-1][0], count)
                    size = len(output.encode())
                    self.assertEqual(self.query(archive, root, offset=1, limit=1, budget_bytes=size), packet)
                    with self.assertRaisesRegex(ValueError, 'Budget too small'):
                        self.query(archive, root, offset=1, limit=1, budget_bytes=size - 1)
                    self.assertEqual(self.decode(output), packet)

    def test_floods_order_independence_and_never_skip_unreturnable_line(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for unique, count, evidence in ((False, 12, 'x' * 800), (False, 120, ''), (True, 40, '')):
                body, _, _ = self.fixture(root, count=count, unique=unique, evidence=evidence)
                expected = None
                for codec in ('gzip', 'xz'):
                    for rows in (body, list(reversed(body))):
                        archive = self.write_archive(root, rows, codec=codec)
                        packet = self.query(archive, root, budget_bytes=6000)
                        self.assertEqual(packet['next_offset'], 1)
                        self.assertEqual(packet['call_sites']['edges'], [])
                        self.assertEqual(packet, expected or packet)
                        expected = packet
                        with self.assertRaisesRegex(ValueError, 'Budget too small'):
                            self.query(archive, root, offset=1, budget_bytes=6000)

    def test_later_sorted_endpoints_change_many_earlier_indexes_and_shrink_reindexes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body, owner, targets = self.fixture(root, count=30)
            original_edges = [row['data'] for row in body if row['record'] == 'edge']
            template = next(row['data'] for row in body if row['record'] == 'node' and row['data']['id'] == targets[0])
            for number in range(10):
                # These IDs sort before both original endpoints even though
                # their calls occur on the later physical source line.
                path = f'aa{number}.py'
                content = b'def a(): pass\n'
                (root / path).write_bytes(content)
                body.append(dict(record='file', data=dict(path=path, hash=hashlib.sha256(content).hexdigest(),
                                                         size=len(content))))
                node = {**template, 'id': path + '::a:function', 'path': path, 'name': 'a'}
                body.append(dict(record='node', data=node))
                body.append(dict(record='edge', data={**original_edges[0], 'line': 3, 'target': node['id']}))
            archive = self.write_archive(root, body)
            prefix = self.query(archive, root, limit=3, budget_bytes=64000)
            encoded = json.loads(api.source_calls_json(prefix, call_table=True))['call_sites']
            self.assertEqual(encoded['edges'][0][:3], [10, 11, 10])
            # Whole-prefix overhead, not a per-line flood, forces a suffix
            # removal. Every earlier duplicate must use the recalculated IDs.
            bound = len(api.source_calls_json(prefix, call_table=True).encode()) - 1
            collected_caps = []
            original = api._hydrate_table

            def hydrate(*args, **kwargs):
                nodes, cap = original(*args, **kwargs)
                collected_caps.append(cap)
                return nodes, cap

            with patch.object(api, '_hydrate_table', side_effect=hydrate):
                packet = self.query(archive, root, budget_bytes=bound)
            self.assertEqual(collected_caps, [4])
            self.assertEqual(packet['next_offset'], 2)
            self.assertEqual(packet['call_sites']['edges'], original_edges)
            encoded = json.loads(api.source_calls_json(packet, call_table=True))['call_sites']
            self.assertTrue(all(edge[:3] == [0, 1, 0] for edge in encoded['edges']))
            self.assertEqual(self.decode(api.source_calls_json(packet, call_table=True)), packet)

    def test_overlapping_nested_source_union_and_page_local_reindexing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body, owner, targets = self.fixture(root, count=3, unique=True)
            inner = deepcopy(next(row for row in body if row['record'] == 'node' and row['data']['id'] == owner))
            inner['data'].update(id='calls.py::inner:function', name='inner', start_line=3, end_line=4)
            body.append(inner)
            edges = [row['data'] for row in body if row['record'] == 'edge']
            edges[1].update(source=inner['data']['id'], line=3)
            edges[2].update(source=inner['data']['id'], line=4)
            body.append(dict(record='edge', data=deepcopy(edges[1])))
            archive = self.write_archive(root, body)
            offset, source_lines, delivered = 0, [], []
            while offset is not None:
                packet = api.source_calls_archive(archive, ['outer', 'inner'], root, call_table=True,
                                                  offset=offset, limit=2, budget_bytes=12000)
                output = api.source_calls_json(packet, call_table=True)
                self.assertEqual(self.decode(output), packet)
                self.assertEqual(json.loads(output)['call_sites']['nodes'][0][0], 0)
                source_lines.extend(number for block in packet['sources']
                                    for number in range(block['start_line'], block['end_line'] + 1))
                delivered.extend(packet['call_sites']['edges'])
                offset = packet['next_offset']
            self.assertEqual(source_lines, [1, 2, 3, 4])
            self.assertEqual(delivered, [edges[0], edges[1], edges[1], edges[2]])

    def test_default_json_empty_tables_and_existing_wire_paths_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body, _, _ = self.fixture(root)
            archive = self.write_archive(root, body)
            packet = self.query(archive, root, budget_bytes=64000)
            explicit = self.query(archive, root, output_format='json', budget_bytes=64000)
            self.assertEqual(packet, explicit)
            for form in ('json', 'text'):
                old = api.source_calls_archive(archive, ['outer'], root, output_format=form, budget_bytes=64000)
                false = api.source_calls_archive(archive, ['outer'], root, output_format=form,
                                                 budget_bytes=64000, call_table=False)
                self.assertEqual(packet, old)
                self.assertEqual(old, false)
            self.assertEqual(api.source_calls_json(packet), (compact(packet) + '\n').translate(api._TEXT_ESCAPES))
            self.assertEqual(api.source_calls_json(packet), api.source_calls_json(packet, call_table=False))
            text_packet = self.query(archive, root, output_format='text', budget_bytes=64000)
            self.assertEqual(text_tests.ArchiveCallTableTests.decode_calls(
                api.source_calls_text(text_packet, call_table=True)), packet['call_sites'])
            empty = self.query(archive, root, limit=1)
            calls = json.loads(api.source_calls_json(empty, call_table=True))['call_sites']
            self.assertEqual((calls['files'], calls['nodes'], calls['edges']), ([], [], []))
            self.assertEqual(self.decode(api.source_calls_json(empty, call_table=True)), empty)

    def test_json_overflow_releases_storage_and_keeps_duplicate_ledger(self):
        control = text_tests.ArchiveCallTableTests()
        control.query = self.query
        control.test_collection_interns_values_and_releases_overflow_and_later_bins()
        control.test_hydration_prunes_orphan_descriptors_but_keeps_duplicate_ledger()
        control.test_shared_endpoint_survives_when_only_later_line_overflows()

    def test_json_selected_metadata_capacity_is_not_raw_hydrated_serialization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body, owner, _ = self.fixture(root)
            node = next(row['data'] for row in body if row['record'] == 'node' and row['data']['id'] == owner)
            node.update(name='', qualname='outer')
            node['name'] = 'n' * (63990 - api._bytes(node))
            self.assertEqual(api._bytes(node), 63990)
            hydrated = api._node(node)
            hydrated.update(source_hash='0' * 64, source_status='selected_file_hash_verified')
            self.assertGreater(api._bytes(hydrated), 64000)
            archive = self.write_archive(root, body)
            packet = self.query(archive, root, limit=1, budget_bytes=6000)
            self.assertEqual(packet['call_sites']['nodes'], [])
            output = api.source_calls_json(packet, call_table=True)
            self.assertLessEqual(len(output.encode()), 6000)
            self.assertEqual(self.decode(output), packet)
            with self.assertRaisesRegex(ValueError, 'metadata exceeds bounded'):
                api.source_calls_archive(archive, ['outer'], root, limit=1, budget_bytes=6000)

    def test_json_complete_eof_same_descriptor_and_corruption_precedes_source_reads(self):
        control = text_tests.ArchiveCallTableTests()
        control.query = self.query
        control.test_successful_pages_are_order_independent_and_all_scans_reach_eof()
        control.test_late_footer_errors_and_endpoint_corruption_precede_source_reads()
        control.test_owner_range_and_stale_selected_source_are_not_repaired()

    def test_json_archive_mutation_and_overloads_reuse_portable_controls(self):
        import test_archive_source_calls as legacy

        def query(*args, **kwargs):
            packet = api.source_calls_archive(*args, **kwargs, call_table=True)
            self.assertEqual(self.decode(api.source_calls_json(packet, call_table=True)), packet)
            return packet

        control = legacy.ArchiveSourceCallsTests()
        with patch.object(legacy, 'source_calls_archive', side_effect=query):
            control.test_archive_replacement_between_passes_and_during_source_read_is_rejected()
            control.test_windows_denied_replacement_still_requires_reader_mutation_detection()
            control.test_overload_selection_preserves_edges_and_rejects_receiver_conflicts()
            control.test_stored_language_decodes_nonstandard_extension_and_python_encoding()


if __name__ == '__main__':
    unittest.main()
