"""Prospective JSON-table receipts; tiny synthetic archives, no indexing/models."""
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


EVIDENCE = module('prospective_json_call_table_evidence',
                  ROOT / 'evals/exploration/json_call_table_evidence.py')
FIXTURES = module('json_call_table_test_fixtures', ROOT / 'tests/test_source_call_evidence.py')
HISTORICAL_SHA = '5f7fdf492ab5ea6e9f23b2be2f74b6be4978209ee267180fde9c8d904c193150'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class JsonCallTableEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse construction only, not another TestCase's assertions/discovery.
        cls.controls = type('_JsonFixture', (FIXTURES.SourceCallEvidenceTests,), {})
        cls.controls.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.controls.tearDownClass()

    def setUp(self):
        self.fixture = self.controls()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def event(self, queries=('outer',), *, offset=0, limit=120, budget=12000,
              overloads=False, explicit_json=False, actual_cli=False):
        from columbus.source_calls import source_calls_archive, source_calls_json
        f = self.fixture
        args = ['archive-source', *queries, '--call-sites', '--call-table', '--input', str(f.graph),
                '--repo', str(f.repo), '--offset', str(offset), '--limit', str(limit),
                '--budget-bytes', str(budget)]
        if explicit_json:
            args += ['--format', 'json']
        if overloads:
            args.append('--overloads')
        argv = [*f.binding['invocation_prefix'], *args]
        if actual_cli:
            result = subprocess.run(argv, cwd=f.repo, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stderr, b'')
            output = result.stdout.decode('utf-8')
        else:
            packet = source_calls_archive(f.graph, list(queries), f.repo, limit, budget, offset,
                                          output_format='json', overloads=overloads, call_table=True)
            output = source_calls_json(packet, call_table=True)
        return dict(type='item.completed', item=dict(id='command-1', type='command_execution',
                    command=shlex.join(argv), status='completed', exit_code=0, aggregated_output=output))

    def recognize(self, events, relationships=None):
        f = self.fixture
        return EVIDENCE.evidence(events, binding=f.binding,
                                 relationships=f.reviewed if relationships is None else relationships)

    def rejected(self, event):
        self.assertEqual(self.recognize([event]), dict(recognizer_version=EVIDENCE.VERSION,
            json_call_table_used=False, source_call_receipts=[], relationship_receipts=[], relationship_used=False))

    @staticmethod
    def argv(event, change):
        result = deepcopy(event)
        words = shlex.split(result['item']['command'])
        change(words)
        result['item']['command'] = shlex.join(words)
        return result

    @staticmethod
    def output(event, change):
        result = deepcopy(event)
        packet = json.loads(result['item']['aggregated_output'])
        change(packet)
        result['item']['aggregated_output'] = EVIDENCE._json(packet) + '\n'
        assert result != event
        return result

    def test_actual_cli_default_explicit_json_gzip_xz_and_complete_hash_receipts(self):
        f = self.fixture
        before = FIXTURES.inventory(f.runtime), FIXTURES.inventory(f.repo)
        for codec in ('gzip', 'xz'):
            f.freeze(codec=codec)
            default, explicit = (self.event(actual_cli=True, explicit_json=value) for value in (False, True))
            self.assertEqual(default['item']['aggregated_output'], explicit['item']['aggregated_output'])
            for event in (default, explicit):
                result = self.recognize([event])
                self.assertEqual(set(result), {'recognizer_version', 'json_call_table_used',
                    'source_call_receipts', 'relationship_receipts', 'relationship_used'})
                self.assertTrue(result['json_call_table_used'])
                self.assertTrue(result['relationship_used'])
                receipt = result['source_call_receipts'][0]
                self.assertEqual((receipt['source_rows'], receipt['stored_edges'], receipt['endpoint_nodes']), (8, 6, 3))
                self.assertEqual((receipt['resolved_call_reference_count'], receipt['unresolved_call_reference_count']), (5, 1))
                self.assertEqual(receipt['encoding'], 'columbus-call-table-json/v1')
                self.assertEqual(receipt['invocation']['format'], 'json')
                self.assertIs(receipt['invocation']['call_table'], True)
                for key, raw in (('output_sha256', event['item']['aggregated_output'].encode()),
                                 ('command_sha256', event['item']['command'].encode()),
                                 ('event_json_sha256', EVIDENCE.SAFE._compact(event).encode())):
                    self.assertEqual(receipt[key], sha(raw))
                self.assertNotIn('source', receipt)
            self.assertEqual(self.recognize([default])['source_call_receipts'][0]['invocation'],
                             self.recognize([explicit])['source_call_receipts'][0]['invocation'])
        self.assertEqual((FIXTURES.inventory(f.runtime), FIXTURES.inventory(f.repo)), before)
        self.assertFalse((f.repo / '.columbus').exists())

    def test_lossless_source_controls_and_ordered_duplicate_edge_roundtrip(self):
        from columbus.source_calls import source_calls_archive
        f = self.fixture
        path = f.repo / 'calls.py'
        path.write_bytes(path.read_bytes().replace(b'    return 1',
            '    return "\\t\\n\\\\"\t# 한\x7f\x85\u2028\u2029'.encode()))
        controls = ''.join(map(chr, (*range(32), *range(127, 160), 0x2028, 0x2029)))
        for kind, row in f.body:
            if kind == 'edge':
                row['evidence'] += controls + '\\u0085'
            elif kind == 'node' and row['id'] == f.ping:
                row.pop('partial')
        f.freeze()
        event = self.event(budget=64000)
        wire = event['item']['aggregated_output']
        self.assertTrue(self.recognize([event])['relationship_used'])
        self.assertFalse(any(char in wire for char in controls if char != '\n'))
        packet = json.loads(wire)
        table = packet['call_sites']
        nodes = [dict(decl, path=table['files'][index][0], source_hash=table['files'][index][1])
                 for index, decl in table['nodes']]
        edges = [dict(rel, source=nodes[source]['id'], target=nodes[target]['id'], path=table['files'][file][0])
                 for source, target, file, rel in table['edges']]
        decoded = {key: value for key, value in table.items()
                   if key not in {'format', 'index_scope', 'files', 'nodes', 'edges'}}
        decoded.update(nodes=nodes, edges=edges)
        packet['call_sites'] = decoded
        original = source_calls_archive(f.graph, ['outer'], f.repo, budget_bytes=64000,
                                        output_format='json', call_table=True)
        self.assertEqual(packet, original)
        self.assertEqual(edges[0], edges[1])
        self.assertEqual(len(edges), 6)
        self.assertIsNone(next(node for node in nodes if node['id'] == f.ping)['partial'])
        self.assertIn('\t', packet['sources'][0]['source'])
        self.assertIn('\\t', packet['sources'][0]['source'])
        self.rejected(self.output(event, lambda p: p['sources'][0].__setitem__(
            'source', p['sources'][0]['source'].replace('\t', '\\t'))))

    def test_json_table_schema_indexes_hashes_paths_order_and_counts_are_exact(self):
        event = self.event()
        mutations = []
        for value in (True, False, -1, 0.0, '0', None, 999):
            mutations.append(lambda p, v=value: p['call_sites']['edges'][0].__setitem__(0, v))
            mutations.append(lambda p, v=value: p['call_sites']['nodes'][0].__setitem__(0, v))
        for field, value in (('format', 'columbus-call-table/v1'), ('index_scope', 'archive'),
                             ('semantic_complete', True), ('stored_call_sites_complete', False),
                             ('unresolved_call_reference_count', 0)):
            mutations.append(lambda p, k=field, v=value: p['call_sites'].__setitem__(k, v))
        mutations += [lambda p: p['call_sites']['files'][0].__setitem__(0, '../calls.py'),
                      lambda p: p['call_sites']['files'][0].__setitem__(1, '0' * 64),
                      lambda p: p['call_sites']['nodes'][0][1].__setitem__('source_status', 'unverified'),
                      lambda p: p['call_sites']['edges'][0][3].__setitem__('line', 3),
                      lambda p: p['call_sites']['edges'].pop(),
                      lambda p: p['call_sites']['edges'].append(deepcopy(p['call_sites']['edges'][0])),
                      lambda p: p['call_sites']['edges'].reverse(),
                      lambda p: p['call_sites']['nodes'].reverse(),
                      lambda p: p['call_sites']['nodes'].append(deepcopy(p['call_sites']['nodes'][0])),
                      lambda p: p['call_sites']['files'].pop(),
                      lambda p: p.__setitem__('next_offset', 8),
                      lambda p: p.__setitem__('total_lines', 9),
                      lambda p: p['sources'][0].__setitem__('end_line', 7)]
        for index, change in enumerate(mutations):
            with self.subTest(mutation=index):
                self.rejected(self.output(event, change))
        for output in (event['item']['aggregated_output'][:-1], event['item']['aggregated_output'] + '\n',
                       json.dumps(json.loads(event['item']['aggregated_output']), indent=2) + '\n'):
            changed = deepcopy(event)
            changed['item']['aggregated_output'] = output
            self.rejected(changed)

    def test_flags_queries_paths_prefix_and_strict_absolute_wrappers(self):
        event = self.event(('outer', 'tail'), explicit_json=True)
        variants = []
        for flag in ('--call-sites', '--call-table'):
            variants.append(self.argv(event, lambda words, flag=flag: words.remove(flag)))
        for flag, value in (('--format', 'text'), ('--budget-bytes', '2047'), ('--budget-bytes', '64001'),
                            ('--limit', '401'), ('--limit', '0'), ('--offset', '1'),
                            ('--input', str(self.fixture.base / 'wrong.gz')), ('--repo', str(self.fixture.base))):
            variants.append(self.argv(event, lambda w, k=flag, v=value: w.__setitem__(w.index(k) + 1, v)))
        for extra in (['--call-table'], ['--call-table=true'], ['--input', str(self.fixture.graph)],
                      ['--pretty'], ['--db', ''], ['--telemetry', ''], ['--forma', 'json']):
            variants.append(self.argv(event, lambda words, extra=extra: words.extend(extra)))
        for index, value in ((0, '/wrong/python'), (1, '-I'), (2, '/wrong/columbus.py'), (4, 'tail')):
            variants.append(self.argv(event, lambda w, i=index, v=value: w.__setitem__(i, v)))
        variants.append(self.argv(event, lambda w: w.__setitem__(slice(4, 6), ['tail', 'outer'])))
        for variant in variants:
            with self.subTest(command=variant['item']['command']):
                self.rejected(variant)
        plain = self.event()
        plain['item']['command'] = shlex.join([*self.fixture.binding['invocation_prefix'], '--repo',
            str(self.fixture.repo), 'archive-source', 'outer', '--input=' + str(self.fixture.graph),
            '--call-sites', '--call-table'])
        self.assertTrue(self.recognize([plain])['relationship_used'])
        for shell in sorted(EVIDENCE._SHELLS):
            for flag in ('-c', '-lc'):
                wrapped = deepcopy(plain)
                wrapped['item']['command'] = shlex.join([shell, flag, plain['item']['command']])
                self.assertTrue(self.recognize([wrapped])['json_call_table_used'])
        for shell in ('sh', 'bash', 'zsh', '/tmp/sh', '/other/bash'):
            wrapped = deepcopy(plain)
            wrapped['item']['command'] = shlex.join([shell, '-c', plain['item']['command']])
            self.rejected(wrapped)
        for suffix in ('; true', ' # comment', ' | more', ' $(echo x)', ' > file'):
            wrapped = deepcopy(plain)
            wrapped['item']['command'] += suffix
            self.rejected(wrapped)

    def test_exact_json_budget_prefix_no_call_trimming_and_no_skipped_flood_line(self):
        event = self.event(budget=64000)
        size = len(event['item']['aggregated_output'].encode())
        exact = self.event(budget=size)
        self.assertEqual(exact['item']['aggregated_output'], event['item']['aggregated_output'])
        self.assertTrue(self.recognize([exact])['json_call_table_used'])
        self.rejected(self.argv(exact, lambda w: w.__setitem__(w.index('--budget-bytes') + 1, str(size - 1))))
        short = self.event(limit=1)
        self.rejected(self.argv(short, lambda w: w.__setitem__(w.index('--limit') + 1, '120')))
        for kind, row in self.fixture.body:
            if kind == 'edge' and row['line'] == 2:
                row['evidence'] = '한\x85' * 1500
        for reverse in (False, True):
            if reverse:
                self.fixture.body.reverse()
            self.fixture.freeze(codec='xz' if reverse else 'gzip')
            page = self.event(budget=6000)
            receipt = self.recognize([page])['source_call_receipts'][0]
            self.assertEqual((receipt['source_rows'], receipt['next_offset'], receipt['stored_edges']), (1, 1, 0))
            with self.assertRaises(ValueError):
                self.event(offset=1, budget=6000)
            later = self.event(offset=2, limit=1, budget=6000)
            self.rejected(self.argv(later, lambda w: w.__setitem__(w.index('--offset') + 1, '1')))

    def test_json_specific_shared_ids_bound_and_index_decimal_widths(self):
        f = self.fixture
        owner = next(deepcopy(row) for kind, row in f.body if kind == 'node' and row['id'] == f.outer)
        targets = []
        for number in range(100):
            path = f'target{number:03d}한.py'
            (f.repo / path).write_bytes(b'def target(): pass\n')
            targets.append(f.node(path + '::target:function', path, 'target', 1, 1))
        for count in (9, 10, 99, 100):
            f.body = [('node', owner)] + [('node', node) for node in targets[:count]]
            f.body += [('edge', dict(source=f.outer, target=node['id'], path='calls.py', line=2,
                                    kind='calls', confidence='heuristic', evidence='한\x85')) for node in targets[:count]]
            f.freeze()
            event = self.event(budget=64000)
            table = json.loads(event['item']['aggregated_output'])['call_sites']
            self.assertEqual(max(row[1] for row in table['edges']), count)
            self.assertEqual(max(row[0] for row in table['nodes']), count)
            size = len(event['item']['aggregated_output'].encode())
            exact = self.event(budget=size)
            self.assertEqual(exact['item']['aggregated_output'], event['item']['aggregated_output'])
            self.assertTrue(self.recognize([exact], [])['json_call_table_used'])
            self.rejected(self.argv(exact, lambda w: w.__setitem__(w.index('--budget-bytes') + 1, str(size - 1))))

    def test_shared_long_id_edges_do_not_use_full_id_json_bounds(self):
        from columbus.source_calls import source_calls_archive
        f = self.fixture
        replacements = {identity: identity + 'x' * 900 for identity in (f.outer, f.ping)}
        for kind, row in f.body:
            for key in ('id', 'source', 'target'):
                if row.get(key) in replacements:
                    row[key] = replacements[row[key]]
        first = next(row for kind, row in f.body if kind == 'edge')
        f.body = [(kind, row) for kind, row in f.body if kind not in {'edge', 'reference'}]
        f.body += [('edge', deepcopy(first)) for _ in range(24)]
        f.reviewed = [{key: first[key] for key in ('source', 'target', 'path', 'line')}]
        f.freeze()
        result = self.recognize([self.event()])
        self.assertEqual(result['source_call_receipts'][0]['source_rows'], 8)
        self.assertEqual(result['source_call_receipts'][0]['stored_edges'], 24)
        old = source_calls_archive(f.graph, ['outer'], f.repo, output_format='json')
        self.assertEqual(old['next_offset'], 1)

    def test_selected_projection_capacity_is_not_raw_hydrated_node_cap(self):
        f = self.fixture
        owner = next(row for kind, row in f.body if kind == 'node' and row['id'] == f.outer)
        owner['name'] = ''
        owner['name'] = 'n' * (63990 - len(EVIDENCE.SAFE._compact(owner).encode()))
        f.freeze()
        snapshot = EVIDENCE.SAFE._Snapshot(deepcopy(f.binding))
        descriptor = EVIDENCE.SAFE._descriptor(snapshot, f.outer, {'calls.py'})
        self.assertGreater(len(EVIDENCE.SAFE._compact(descriptor).encode()), 64000)
        self.assertTrue(self.recognize([self.event(limit=1, budget=6000)])['json_call_table_used'])

    def test_overlap_paging_aliases_and_empty_calls_are_not_graph_utility(self):
        offset, lines, count = 0, [], 0
        while offset is not None:
            event = self.event(('outer', self.fixture.outer, 'outer.inner', 'tail'), offset=offset, limit=2)
            receipt = self.recognize([event])['source_call_receipts'][0]
            for block in receipt['ranges']:
                lines.extend(range(block['start_line'], block['end_line'] + 1))
            count += receipt['stored_edges']
            offset = receipt['next_offset']
        self.assertEqual(lines, [*range(1, 9), 10])
        self.assertEqual(count, 6)
        for event in (self.event(('tail',)), self.event(offset=5, limit=1), self.event()):
            result = self.recognize([event], [])
            self.assertTrue(result['json_call_table_used'])
            self.assertFalse(result['relationship_used'])
            self.assertEqual(result['relationship_receipts'], [])
        self.assertFalse(self.recognize([])['json_call_table_used'])
        for key, value in (('line', 3), ('source', self.fixture.inner), ('target', self.fixture.inner)):
            self.assertFalse(self.recognize([self.event()], [{**self.fixture.reviewed[0], key: value}])['relationship_used'])
        with self.assertRaises(ValueError):
            self.recognize([self.event()], [{**self.fixture.reviewed[0], 'path': 'other.py'}])

    def test_kotlin_overloads_keep_receiver_identity_and_merged_source_order(self):
        f = self.fixture
        (f.repo / 'Owner.kt').write_bytes(b'class Owner {\n fun run() { run(1) }\n fun run(x: Int) {}\n fun run(x: String) {}\n}\n')
        nodes = []
        for number, parameters in ((2, []), (3, ['Int']), (4, ['String'])):
            node = f.node(f'Owner.kt::Owner.run({",".join(parameters)}):method', 'Owner.kt', 'run', number, number)
            node.update(kind='method', qualname='Owner.run', language='kotlin', parent_id='Owner.kt::Owner:class',
                        receiver_type='', local=False, parameter_types=parameters)
            nodes.append(node)
        edge = dict(source=nodes[0]['id'], target=nodes[1]['id'], path='Owner.kt', line=2,
                    kind='calls', confidence='resolved_static', evidence='callee:2:13-2:16')
        f.body = [('node', node) for node in nodes] + [('edge', edge)]
        f.reviewed = [{key: edge[key] for key in ('source', 'target', 'path', 'line')}]
        f.freeze()
        event = self.event(('Owner.run', nodes[0]['id']), overloads=True)
        receipt = self.recognize([event])['source_call_receipts'][0]
        self.assertEqual(receipt['target_ids'], [node['id'] for node in nodes])
        self.assertEqual(receipt['source_rows'], 3)
        self.rejected(self.argv(event, lambda w: w.remove('--overloads')))
        nodes[-1]['receiver_type'] = 'String'
        f.freeze()
        self.rejected(event)

    def test_physical_source_decoding_cookie_crlf_cr_blank_and_empty(self):
        f = self.fixture
        source = f.repo / 'calls.py'
        original = source.read_bytes()
        for content in (original.replace(b'\n', b'\r\n'), original.replace(b'\n', b'\r')):
            source.write_bytes(content)
            f.freeze()
            self.assertTrue(self.recognize([self.event()])['relationship_used'])
        node = f.node(f.outer, 'calls.py', 'outer', 1, 2)
        f.body = [('node', node)]
        source.write_bytes(b'# coding: latin-1\n# caf\xe9\n')
        f.freeze()
        self.assertTrue(self.recognize([self.event()], [])['json_call_table_used'])
        source.write_bytes(b'\n')
        node['end_line'] = 1
        f.freeze()
        blank = self.event()
        self.assertEqual(self.recognize([blank], [])['source_call_receipts'][0]['source_rows'], 1)
        source.write_bytes(b'')
        f.freeze()
        self.rejected(blank)

    def test_failed_offered_nonterminal_and_unserializable_events(self):
        event = self.event()
        for field, values in (('exit_code', [False, True, '0', 1]), ('status', ['in_progress', None]),
                              ('id', ['', None]), ('aggregated_output', ['', None, '\ud800'])):
            for value in values:
                changed = deepcopy(event)
                changed['item'][field] = value
                self.rejected(changed)
        for kind in ('item.started', 'agent_message', 'turn.completed'):
            changed = deepcopy(event)
            changed['type'] = kind
            self.rejected(changed)
        changed = deepcopy(event)
        changed['extra'] = '\ud800'
        self.rejected(changed)
        nested = []
        for _ in range(max(10000, sys.getrecursionlimit() * 4)):
            nested = [nested]
        changed = deepcopy(event)
        changed['extra'] = nested
        try:
            EVIDENCE.SAFE._compact(changed)
        except (RecursionError, OverflowError):
            self.rejected(changed)
        else:
            self.assertTrue(self.recognize([changed])['json_call_table_used'])
        compact = EVIDENCE.SAFE._compact
        for error in (RecursionError, OverflowError):
            def fail_whole_event(value):
                if value is event:
                    raise error('whole-event serialization failure')
                return compact(value)
            with patch.object(EVIDENCE.SAFE, '_compact', side_effect=fail_whole_event):
                self.rejected(event)

    def test_binding_inputs_are_exact_even_without_events(self):
        f = self.fixture
        for key, value in (('archive_sha256', '0' * 64), ('revision', 'wrong'), ('source_manifest', {}),
                           ('runtime_inventory', {}), ('source_manifest', list(f.binding['source_manifest'].items())),
                           ('runtime_inventory', list(f.binding['runtime_inventory'].items()))):
            binding = deepcopy(f.binding)
            binding[key] = value
            with self.assertRaisesRegex(ValueError, 'frozen'):
                EVIDENCE.evidence([], binding=binding, relationships=f.reviewed)
        for path in (f.repo / 'unexpected.py', f.runtime / 'unexpected.py'):
            try:
                path.write_bytes(b'# extra\n')
                with self.assertRaises(ValueError):
                    self.recognize([])
            finally:
                path.unlink()
        target = f.repo / 'other.py'
        target.unlink()
        with self.assertRaises(ValueError):
            self.recognize([])

    def test_full_archive_eof_and_endpoint_validation_precede_receipts(self):
        f = self.fixture
        body = deepcopy(f.body)
        for codec in ('gzip', 'xz'):
            f.freeze(codec=codec, footer=False)
            with self.assertRaises(ValueError):
                self.recognize([])
            f.freeze(codec=codec, extra=[('diagnostic', {})])
            with self.assertRaises(ValueError):
                self.recognize([])
        for mutation in ('duplicate', 'missing-target', 'owner-line', 'owner-path', 'language', 'partial'):
            f.body = deepcopy(body)
            owner = next(row for kind, row in f.body if kind == 'node' and row['id'] == f.outer)
            edge = next(row for kind, row in f.body if kind == 'edge')
            if mutation == 'duplicate':
                f.body.append(('node', deepcopy(owner)))
            elif mutation == 'missing-target':
                edge['target'] = 'absent'
            elif mutation == 'owner-line':
                edge['line'] = 10
            elif mutation == 'owner-path':
                edge['path'] = 'other.py'
            elif mutation == 'language':
                owner['language'] = 'kotlin'
            else:
                owner['partial'] = None
            f.freeze()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.recognize([])

    def test_final_full_rehash_closes_restored_metadata_blind_spot(self):
        f = self.fixture
        for path in (f.repo / 'calls.py', f.runtime / 'columbus.py', f.graph):
            original, stamp = path.read_bytes(), path.stat()
            def changed():
                path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
                yield from ()
            try:
                with patch.object(EVIDENCE.SAFE, '_stamp', side_effect=lambda s: (s.st_dev, s.st_ino, s.st_size, 0, 0)):
                    with self.assertRaisesRegex(ValueError, 'changed during recognition'):
                        self.recognize(changed())
            finally:
                path.write_bytes(original)
                os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))

    def test_binding_mutations_during_final_read_and_last_check_are_rejected(self):
        f = self.fixture
        binding, read, check = deepcopy(f.binding), EVIDENCE.SAFE._read, EVIDENCE.SAFE._Snapshot.check
        archive_reads = 0
        def changed_read(path):
            nonlocal archive_reads
            result = read(path)
            if path == f.graph:
                archive_reads += 1
                if archive_reads == 2:
                    f.binding['source_manifest']['calls.py'] = '0' * 64
            return result
        with patch.object(EVIDENCE.SAFE, '_read', side_effect=changed_read):
            with self.assertRaisesRegex(ValueError, 'changed during recognition'):
                self.recognize([])
        self.assertEqual(archive_reads, 2)
        f.binding = binding
        checks = 0
        def changed_check(snapshot):
            nonlocal checks
            check(snapshot)
            checks += 1
            # Snapshot construction, final precheck, final closing check.
            if checks == 3:
                f.binding['runtime_inventory']['columbus.py'] = '0' * 64
        with patch.object(EVIDENCE.SAFE._Snapshot, 'check', new=changed_check):
            with self.assertRaisesRegex(ValueError, 'changed during recognition'):
                self.recognize([])
        self.assertEqual(checks, 3)

    def test_event_iterator_failure_still_performs_final_binding_validation(self):
        reads, original = [], EVIDENCE.SAFE._read
        def tracked_read(path):
            reads.append(path)
            return original(path)
        def failed():
            raise RuntimeError('event iterator failed')
            yield
        with patch.object(EVIDENCE.SAFE, '_read', side_effect=tracked_read):
            with self.assertRaisesRegex(RuntimeError, 'event iterator failed'):
                self.recognize(failed())
        self.assertEqual(reads.count(self.fixture.graph), 2)
        def changed_and_failed():
            self.fixture.binding['revision'] = 'mutated'
            raise RuntimeError('event iterator failed')
            yield
        with self.assertRaisesRegex(ValueError, 'changed during recognition'):
            self.recognize(changed_and_failed())

    def test_late_file_additions_after_final_inventory_are_still_rejected(self):
        f = self.fixture
        read = EVIDENCE.SAFE._read
        for path in (f.repo / 'new.py', f.runtime / 'new.py'):
            count = 0
            def added_after_final_read(target):
                nonlocal count
                result = read(target)
                if target == f.graph:
                    count += 1
                    if count == 2:
                        path.write_bytes(b'# added after inventories\n')
                return result
            try:
                with patch.object(EVIDENCE.SAFE, '_read', side_effect=added_after_final_read):
                    with self.assertRaisesRegex(ValueError, 'changed during recognition'):
                        self.recognize([])
                self.assertEqual(count, 2)
            finally:
                if path.exists():
                    path.unlink()

    def test_legacy_text_offers_and_production_oracle_imports_cannot_receive_credit(self):
        f = self.fixture
        event = self.event()
        self.assertEqual(sha((ROOT / 'evals/exploration/source_call_evidence.py').read_bytes()), HISTORICAL_SHA)
        self.assertEqual(EVIDENCE.SAFE.evidence([event], binding=f.binding,
                                               relationships=f.reviewed)['source_call_receipts'], [])
        self.rejected(f.event())
        from columbus.source_calls import source_calls_archive, source_calls_text
        text = self.argv(event, lambda w: w.extend(['--format', 'text']))
        text['item']['aggregated_output'] = source_calls_text(source_calls_archive(
            f.graph, ['outer'], f.repo, output_format='text', call_table=True), call_table=True)
        self.rejected(text)
        offered = deepcopy(event)
        offered['item']['aggregated_output'] = 'Try ' + event['item']['command']
        self.rejected(offered)
        before = FIXTURES.inventory(f.repo), FIXTURES.inventory(f.runtime), f.graph.read_bytes()
        with patch('subprocess.run', side_effect=AssertionError('no subprocess')), \
             patch('subprocess.Popen', side_effect=AssertionError('no subprocess')), \
             patch('columbus.source_calls.source_calls_archive', side_effect=AssertionError('no production selector')), \
             patch('columbus.source_calls.source_calls_json', side_effect=AssertionError('no production renderer')), \
             patch('columbus.source_calls.source_calls_text', side_effect=AssertionError('no text renderer')):
            self.assertTrue(self.recognize([event])['relationship_used'])
        self.assertEqual((FIXTURES.inventory(f.repo), FIXTURES.inventory(f.runtime), f.graph.read_bytes()), before)


if __name__ == '__main__':
    unittest.main()
