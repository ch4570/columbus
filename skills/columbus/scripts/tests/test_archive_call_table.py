"""Lossless page-local call tables with format-aware, bounded collection."""
from copy import deepcopy
import gzip
import hashlib
import json
import lzma
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import weakref

from columbus import source_calls as api
from columbus.index import compact
from columbus.presentation import archive_source_text


class ArchiveCallTableTests(unittest.TestCase):
    @staticmethod
    def fixture(root, *, id_size=0, count=3, unique=False, evidence='ping()', self_call=False):
        contents = {'calls.py': b'def outer():\n    ping()\n    other()\n    return 1\n',
                    'external.py': b'def ping(): pass\n'}
        for path, content in contents.items():
            (root / path).write_bytes(content)
        owner = 'calls.py::outer' + 'x' * id_size + ':function'
        targets = ['external.py::ping' + str(number) + 'y' * id_size + ':function'
                   for number in range(count if unique else 1)]
        nodes = [dict(id=owner, path='calls.py', name='outer', kind='function',
                      start_line=1, end_line=4, language='python', fidelity='ast', partial=False)]
        nodes.extend(dict(id=identity, path='external.py', name='ping' + str(number), kind='function',
                          start_line=1, end_line=1, language='python', fidelity='heuristic')
                     for number, identity in enumerate(targets))
        edges = [dict(source=owner, target=owner if self_call else targets[number if unique else 0],
                      path='calls.py', line=2, kind='calls', confidence='heuristic', evidence=evidence)
                 for number in range(count)]
        files = [dict(path=path, hash=hashlib.sha256(content).hexdigest(), size=len(content))
                 for path, content in contents.items()]
        refs = [dict(source=owner, path='calls.py', line=2, kind='calls', resolved=True)
                for _ in edges]
        refs.append(dict(source=owner, path='calls.py', line=2, kind='calls', resolved=False))
        body = [dict(record=kind, data=data) for kind, values in
                [('file', files), ('node', nodes), ('edge', edges), ('reference', refs)] for data in values]
        return body, owner, targets

    @staticmethod
    def write_archive(root, body, *, codec='gzip', name='graph', footer=True, extra=()):
        counts = dict(files=0, nodes=0, scopes=0, edges=0, references=0, imports=0, diagnostics=0)
        for row in body:
            counts[row['record'] + 's'] += 1
        rows = [dict(record='manifest', data=dict(format='columbus-graph', version=1,
                                                revision='call-table-test'))] + body
        if footer:
            rows.append(dict(record='end', data=counts))
        rows.extend(extra)
        path = root / (name + '.' + codec)
        raw = ''.join(compact(row) + '\n' for row in rows).encode('utf-8')
        path.write_bytes(gzip.compress(raw) if codec == 'gzip' else lzma.compress(raw))
        return path

    @staticmethod
    def query(archive, root, **options):
        return api.source_calls_archive(archive, ['outer'], root, output_format='text',
                                        call_table=True, **options)

    @staticmethod
    def decode_calls(text):
        files, nodes, edges, state, calls = {}, [], [], None, None
        for row in text.splitlines():
            if row.startswith('call_sites '):
                calls = json.loads(row[len('call_sites '):])
            elif row.startswith('call_tables '):
                marker = json.loads(row[len('call_tables '):])
                assert marker == {'format': 'columbus-call-table/v1', 'index_scope': 'this packet'}
            elif row.startswith('call_files '):
                state = 'files'
            elif row.startswith('call_nodes '):
                state = 'nodes'
            elif row.startswith('call_edges '):
                state = 'edges'
            elif state and row.startswith('['):
                values = json.loads(row)
                if state == 'files':
                    number, path, digest = values
                    assert number == len(files)
                    files[number] = path, digest
                elif state == 'nodes':
                    number, file_number, declaration = values
                    assert number == len(nodes)
                    nodes.append({**declaration, 'path': files[file_number][0],
                                  'source_hash': files[file_number][1]})
                else:
                    source, target, file_number, relationship = values
                    assert nodes[source]['path'] == files[file_number][0]
                    assert nodes[source]['source_hash'] == files[file_number][1]
                    edges.append({**relationship, 'source': nodes[source]['id'],
                                  'target': nodes[target]['id'], 'path': files[file_number][0]})
        assert calls is not None
        return {**calls, 'nodes': nodes, 'edges': edges}

    def test_long_shared_ids_fit_table_while_legacy_guard_keeps_its_behavior(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body, _, _ = self.fixture(root, id_size=900, count=24)
            archive = self.write_archive(root, body)
            packet = self.query(archive, root, budget_bytes=12000)
            text = api.source_calls_text(packet, call_table=True)
            self.assertIsNone(packet['next_offset'])
            self.assertEqual(len(packet['call_sites']['edges']), 24)
            self.assertEqual(self.decode_calls(text), packet['call_sites'])
            self.assertLessEqual(len(text.encode()), 12000)
            self.assertGreater(len(api.source_calls_text(packet).encode()), 12000)
            legacy = api.source_calls_archive(archive, ['outer'], root, output_format='text', budget_bytes=12000)
            self.assertEqual(legacy['next_offset'], 1)
            self.assertEqual(legacy['call_sites']['edges'], [])

    def test_shared_file_is_charged_once_and_self_calls_charge_one_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for unique, recursive in ((True, False), (False, True)):
                body, _, _ = self.fixture(root, count=12, unique=unique, self_call=recursive)
                archive = self.write_archive(root, body)
                full = self.query(archive, root, budget_bytes=64000, offset=1, limit=1)
                bound = len(api.source_calls_text(full, call_table=True).encode())
                self.assertGreaterEqual(bound, 2048)
                exact = self.query(archive, root, budget_bytes=bound, offset=1, limit=1)
                self.assertEqual(exact, full)
                self.assertEqual(len(exact['call_sites']['nodes']), 13 if unique else 1)

    def test_duplicate_rows_counts_unknown_partial_and_control_bytes_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = '"quote" \\t\t\x00\x1b\x7f\x85\u2028\u2029 한글 😀'
            body, _, _ = self.fixture(root, count=3, evidence=evidence)
            archive = self.write_archive(root, body)
            packet = self.query(archive, root, budget_bytes=64000)
            original = deepcopy(packet)
            text = api.source_calls_text(packet, call_table=True)
            self.assertEqual(packet, original)
            self.assertEqual(self.decode_calls(text), packet['call_sites'])
            self.assertEqual(len(packet['call_sites']['edges']), 3)
            self.assertEqual(packet['call_sites']['resolved_call_reference_count'], 3)
            self.assertEqual(packet['call_sites']['unresolved_call_reference_count'], 1)
            self.assertTrue(any(node['partial'] is None for node in packet['call_sites']['nodes']))
            self.assertEqual({node['source_status'] for node in packet['call_sites']['nodes']},
                             {'archive_only', 'selected_file_hash_verified'})
            self.assertFalse(packet['call_sites']['semantic_complete'])
            self.assertTrue(text.endswith('\n'))
            self.assertFalse(text.endswith('\n\n'))
            self.assertFalse(any(ord(c) < 32 and c != '\n' or 0x7f <= ord(c) <= 0x9f
                                 or c in '\u2028\u2029' for c in text))

    def test_exact_utf8_budget_and_index_widths_use_final_serialization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for count in (9, 10, 99, 100):
                with self.subTest(count=count):
                    body, _, _ = self.fixture(root, count=count, unique=True, evidence='\x85한글')
                    archive = self.write_archive(root, body)
                    full = self.query(archive, root, budget_bytes=64000, offset=1, limit=1)
                    text = api.source_calls_text(full, call_table=True)
                    bound = len(text.encode())
                    self.assertGreater(bound, 2048)
                    self.assertEqual(self.query(archive, root, budget_bytes=bound, offset=1, limit=1), full)
                    with self.assertRaisesRegex(ValueError, 'Budget too small'):
                        self.query(archive, root, budget_bytes=bound - 1, offset=1, limit=1)
                    self.assertEqual(self.decode_calls(text), full['call_sites'])

    def test_true_line_flood_never_skips_calls_and_order_does_not_change_page(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body, _, _ = self.fixture(root, count=12, evidence='x' * 800)
            for codec in ('gzip', 'xz'):
                for rows in (body, list(reversed(body))):
                    archive = self.write_archive(root, rows, codec=codec)
                    page = self.query(archive, root, budget_bytes=6000)
                    self.assertEqual(page['next_offset'], 1)
                    self.assertEqual(page['sources'][0]['end_line'], 1)
                    self.assertEqual(page['call_sites']['edges'], [])
                    with self.assertRaisesRegex(ValueError, 'Budget too small'):
                        self.query(archive, root, budget_bytes=6000, offset=1)

    def test_successful_pages_are_order_independent_and_all_scans_reach_eof(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body, _, _ = self.fixture(root, count=10, unique=True)
            expected = None
            for codec in ('gzip', 'xz'):
                for rows in (body, list(reversed(body))):
                    archive = self.write_archive(root, rows, codec=codec)
                    starts, ends = [], []
                    original = api._validated_rows
                    def observe(raw):
                        starts.append(raw)
                        yield from original(raw)
                        ends.append(raw)
                    with patch.object(api, '_validated_rows', side_effect=observe):
                        packet = self.query(archive, root, budget_bytes=64000)
                    self.assertGreaterEqual(len(starts), 4)
                    self.assertEqual(starts, ends)
                    self.assertEqual(len({id(raw) for raw in starts}), 1)
                    if expected is None:
                        expected = packet
                    self.assertEqual(packet, expected)

    def test_late_footer_errors_and_endpoint_corruption_precede_source_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body, _, targets = self.fixture(root, count=2)
            target = next(row for row in body if row['record'] == 'node' and row['data']['id'] == targets[0])
            mutations = [body + [deepcopy(target)],
                         [row for row in body if row is not target],
                         body + [deepcopy(next(row for row in body if row['record'] == 'file'))]]
            conflict = deepcopy(body)
            next(row['data'] for row in conflict if row['record'] == 'node'
                 and row['data']['id'] == targets[0])['language'] = 'java'
            other = deepcopy(target)
            other['data']['id'] = 'external.py::language_control:function'
            conflict.append(other)
            mutations.append(conflict)
            for rows in mutations:
                archive = self.write_archive(root, rows)
                with patch.object(api, 'read_stable') as reads:
                    with self.assertRaises(ValueError):
                        self.query(archive, root, budget_bytes=64000)
                    reads.assert_not_called()
            flood, _, _ = self.fixture(root, count=10, evidence='x' * 1000)
            for footer, extra in ((False, ()), (True, (dict(record='node', data={}),))):
                for codec in ('gzip', 'xz'):
                    archive = self.write_archive(root, flood, codec=codec, footer=footer, extra=extra)
                    with patch.object(api, 'read_stable') as reads:
                        with self.assertRaises(ValueError):
                            self.query(archive, root, budget_bytes=6000)
                        reads.assert_not_called()

    def test_collection_interns_values_and_releases_overflow_and_later_bins(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body, _, _ = self.fixture(root, id_size=600, count=12)
            captured = []
            original = api._collect_calls
            def observe(snapshot, bins, budget, **kwargs):
                cap = original(snapshot, bins, budget, **kwargs)
                captured.append(bins)
                for item in bins[:cap]:
                    for edge in item['edges']:
                        self.assertIs(edge['source'], item['identities'][edge['source']])
                        self.assertIs(edge['target'], item['identities'][edge['target']])
                        self.assertIs(edge['path'], item['path'])
                    self.assertLessEqual(item['cost'], budget)
                for item in bins[cap:]:
                    self.assertEqual(item['edges'], [])
                    self.assertEqual(item['identities'], {})
                    self.assertEqual(item['call_files'], set())
                return cap
            with patch.object(api, '_collect_calls', side_effect=observe):
                self.query(self.write_archive(root, body), root, budget_bytes=12000)
                for row in body:
                    if row['record'] == 'edge':
                        row['data']['evidence'] = 'x' * 1000
                self.query(self.write_archive(root, body), root, budget_bytes=6000)
            self.assertEqual(len(captured), 2)

    def test_hydration_prunes_orphan_descriptors_but_keeps_duplicate_ledger(self):
        class TrackedNode(dict):
            pass
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body, _, targets = self.fixture(root, count=2, unique=True)
            target_nodes = [row for row in body if row['record'] == 'node' and row['data']['id'] in targets]
            target_nodes[-1]['data']['name'] = 'huge' + 'z' * 12000
            references = []
            original = api._node
            def tracked(data):
                node = TrackedNode(original(data))
                references.append((node['id'], weakref.ref(node)))
                return node
            with patch.object(api, '_node', side_effect=tracked):
                packet = self.query(self.write_archive(root, body), root, budget_bytes=6000)
            self.assertEqual(packet['next_offset'], 1)
            self.assertTrue(all(ref() is None for identity, ref in references if identity in targets))
            with self.assertRaisesRegex(ValueError, 'Duplicate archived'):
                self.query(self.write_archive(root, body + [deepcopy(target_nodes[0])]), root, budget_bytes=6000)
            self.assertEqual(self.query(self.write_archive(root, list(reversed(body))), root,
                                        budget_bytes=6000), packet)

    def test_shared_endpoint_survives_when_only_later_line_overflows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body, owner, targets = self.fixture(root, id_size=500, count=2)
            edges = [row['data'] for row in body if row['record'] == 'edge']
            edges[1].update(line=3, evidence='x' * 12000)
            packet = self.query(self.write_archive(root, body), root, budget_bytes=6000)
            self.assertEqual(packet['next_offset'], 2)
            self.assertEqual(packet['sources'][0]['end_line'], 2)
            self.assertEqual(packet['call_sites']['edges'], edges[:1])
            self.assertEqual({node['id'] for node in packet['call_sites']['nodes']}, {owner, targets[0]})

    def test_selected_metadata_capacity_is_not_raw_hydrated_dict_serialization(self):
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
            self.assertLessEqual(len(api.source_calls_text(packet, call_table=True).encode()), 6000)
            with self.assertRaisesRegex(ValueError, 'metadata exceeds bounded'):
                api.source_calls_archive(archive, ['outer'], root, limit=1, budget_bytes=6000)

    def test_cursor_pages_cover_source_union_and_preserve_each_page_call_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body, _, _ = self.fixture(root, count=3, unique=True)
            edges = [row['data'] for row in body if row['record'] == 'edge']
            for number, edge in enumerate(edges, 2):
                edge['line'] = number
            archive = self.write_archive(root, body)
            offset, delivered, seen_edges = 0, [], []
            while offset is not None:
                packet = self.query(archive, root, offset=offset, limit=2, budget_bytes=6000)
                text = api.source_calls_text(packet, call_table=True)
                self.assertEqual(self.decode_calls(text), packet['call_sites'])
                delivered.extend((block['path'], line) for block in packet['sources']
                                 for line in range(block['start_line'], block['end_line'] + 1))
                seen_edges.extend(packet['call_sites']['edges'])
                previous, offset = offset, packet['next_offset']
                self.assertTrue(offset is None or offset > previous)
            self.assertEqual(delivered, [('calls.py', line) for line in range(1, 5)])
            self.assertEqual(seen_edges, edges)

    def test_owner_range_and_stale_selected_source_are_not_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body, owner, _ = self.fixture(root)
            nested = deepcopy(next(row for row in body if row['record'] == 'node' and row['data']['id'] == owner))
            nested['data'].update(id='calls.py::nested:function', name='nested', start_line=3, end_line=4)
            body.append(nested)
            next(row['data'] for row in body if row['record'] == 'edge')['source'] = nested['data']['id']
            with patch.object(api, 'read_stable') as reads:
                with self.assertRaisesRegex(ValueError, 'outside its archived source'):
                    self.query(self.write_archive(root, body), root, budget_bytes=64000)
                reads.assert_not_called()
            body, _, _ = self.fixture(root)
            archive = self.write_archive(root, body)
            (root / 'calls.py').write_bytes(b'# changed\n')
            with self.assertRaisesRegex(ValueError, 'Stale source'):
                self.query(archive, root, budget_bytes=64000)

    def test_archive_replacement_and_windows_denied_replace_guard_in_table_mode(self):
        # Reuse the portable real-mutation controls without changing legacy
        # expectations or silently treating an OS-denied replace as a mutation.
        import test_archive_source_calls as legacy

        def query(*args, **kwargs):
            return api.source_calls_archive(*args, **kwargs, output_format='text', call_table=True)

        control = legacy.ArchiveSourceCallsTests()
        with patch.object(legacy, 'source_calls_archive', side_effect=query):
            control.test_archive_replacement_between_passes_and_during_source_read_is_rejected()
            control.test_windows_denied_replacement_still_requires_reader_mutation_detection()

    def test_overload_selection_and_receiver_rejection_in_table_mode(self):
        import test_archive_source_calls as legacy

        def query(*args, **kwargs):
            packet = api.source_calls_archive(*args, **kwargs, output_format='text', call_table=True)
            self.assertEqual(self.decode_calls(api.source_calls_text(packet, call_table=True)),
                             packet['call_sites'])
            return packet

        with patch.object(legacy, 'source_calls_archive', side_effect=query):
            legacy.ArchiveSourceCallsTests().test_overload_selection_preserves_edges_and_rejects_receiver_conflicts()

    def test_renderer_empty_tables_validation_and_legacy_packet_parity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body, _, _ = self.fixture(root)
            archive = self.write_archive(root, body)
            full = self.query(archive, root, budget_bytes=64000)
            for fmt in ('json', 'text'):
                default = api.source_calls_archive(archive, ['outer'], root, output_format=fmt, budget_bytes=64000)
                explicit = api.source_calls_archive(archive, ['outer'], root, output_format=fmt,
                                                    budget_bytes=64000, call_table=False)
                self.assertEqual(default, explicit)
                self.assertEqual(default, full)
            source = {key: value for key, value in full.items() if key != 'call_sites'}
            calls = full['call_sites']
            rows = [archive_source_text(source).rstrip('\n'), 'call_sites ' + compact(
                    {key: value for key, value in calls.items() if key not in {'nodes', 'edges'}})]
            rows += ['call_node ' + compact(node) for node in calls['nodes']]
            rows += ['call_edge ' + compact(edge) for edge in calls['edges']]
            self.assertEqual(api.source_calls_text(full), '\n'.join(rows) + '\n')
            self.assertEqual(api.source_calls_text(full), api.source_calls_text(full, call_table=False))
            empty = self.query(archive, root, limit=1, budget_bytes=64000)
            rendered = api.source_calls_text(empty, call_table=True)
            self.assertEqual(self.decode_calls(rendered), empty['call_sites'])
            self.assertTrue(all(name in rendered for name in ('call_files ', 'call_nodes ', 'call_edges ')))
            broken = deepcopy(full)
            broken['call_sites']['nodes'].append(deepcopy(calls['nodes'][0]))
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                api.source_calls_text(broken, call_table=True)
            for bad in (None, 0, 1, 'true', []):
                with self.assertRaises(ValueError):
                    api.source_calls_text(full, call_table=bad)
                with self.assertRaises(ValueError):
                    api.source_calls_archive(archive, ['outer'], root, call_table=bad)
            with self.assertRaisesRegex(ValueError, 'requires text'):
                api.source_calls_archive(archive, ['outer'], root, call_table=True)


if __name__ == '__main__':
    unittest.main()
