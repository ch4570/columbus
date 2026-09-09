"""Future-only call-table receipts, with tiny archives and actual CLI controls."""
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
import lzma
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/columbus/scripts'
SPEC = importlib.util.spec_from_file_location('prospective_call_table_evidence',
                                            ROOT / 'evals/exploration/call_table_evidence.py')
EVIDENCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVIDENCE)
HISTORICAL_SHA = '5f7fdf492ab5ea6e9f23b2be2f74b6be4978209ee267180fde9c8d904c193150'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory(root):
    return {path.relative_to(root).as_posix(): sha(path.read_bytes())
            for path in root.rglob('*') if path.is_file()}


class CallTableEvidenceTests(unittest.TestCase):
    outer = 'calls.py::outer:function'
    inner = 'calls.py::outer.inner:function'
    tail = 'calls.py::tail:function'
    ping = 'a target #한.py::ping:function'

    @classmethod
    def setUpClass(cls):
        cls.runtime_temp = tempfile.TemporaryDirectory()
        cls.runtime = Path(cls.runtime_temp.name) / 'runtime'
        cls.runtime.mkdir()
        shutil.copyfile(SCRIPTS / 'columbus.py', cls.runtime / 'columbus.py')
        (cls.runtime / 'columbus').mkdir()
        for path in (SCRIPTS / 'columbus').glob('*.py'):
            shutil.copyfile(path, cls.runtime / 'columbus' / path.name)
        cls.runtime_inventory = inventory(cls.runtime)

    @classmethod
    def tearDownClass(cls):
        cls.runtime_temp.cleanup()

    @staticmethod
    def node(identity, path, name, start, end):
        return dict(id=identity, path=path, name=name, qualname=name, kind='function',
                    start_line=start, end_line=end, language='python', fidelity='ast',
                    partial=False, module=Path(path).stem)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.repo = self.base / 'repository'
        self.repo.mkdir()
        (self.repo / 'calls.py').write_bytes(
            b'def outer():\n    ping()\n    def inner():\n        ping(); ping()\n'
            b'        inner()\n    missing()\n    inner()\n    return 1\n\ndef tail(): return 2\n')
        (self.repo / 'a target #한.py').write_bytes(b'def ping(): pass\n')
        nodes = [self.node(self.outer, 'calls.py', 'outer', 1, 8),
                 self.node(self.inner, 'calls.py', 'outer.inner', 3, 5),
                 self.node(self.tail, 'calls.py', 'tail', 10, 10),
                 self.node(self.ping, 'a target #한.py', 'ping', 1, 1)]
        edges = [dict(source=owner, target=target, path='calls.py', line=number,
                      kind='calls', confidence='resolved_static', evidence=f'callee:{number}:{column}')
                 for owner, target, number, column in (
                     (self.outer, self.ping, 2, 4), (self.inner, self.ping, 4, 8),
                     (self.inner, self.ping, 4, 16), (self.inner, self.inner, 5, 8),
                     (self.outer, self.inner, 7, 4))]
        self.body = [('node', node) for node in nodes] + [('edge', edge) for edge in edges]
        self.body.append(('edge', deepcopy(edges[0])))
        self.body += [('reference', dict(source=edge['source'], path=edge['path'], line=edge['line'],
                                        kind='calls', resolved=True)) for edge in edges]
        self.body.append(('reference', dict(source=self.outer, path='calls.py', line=6,
                                           kind='calls', resolved=False)))
        self.graph = self.base / 'graph.gz'
        self.reviewed = [{key: edges[0][key] for key in ('source', 'target', 'path', 'line')}]
        self.freeze()

    def freeze(self, *, codec='gzip', footer=True, extra=()):
        rows = [('file', dict(path=path.name, hash=sha(path.read_bytes()), size=path.stat().st_size))
                for path in sorted(self.repo.iterdir()) if path.is_file()] + self.body
        plurals = dict(file='files', node='nodes', edge='edges', reference='references',
                       scope='scopes', diagnostic='diagnostics', **{'import': 'imports'})
        counts = dict.fromkeys(plurals.values(), 0)
        for kind, _ in rows:
            counts[plurals[kind]] += 1
        rows = [('manifest', dict(format='columbus-graph', version=1, revision='table-fixture'))] + rows
        if footer:
            rows.append(('end', counts))
        rows.extend(extra)
        raw = ''.join(json.dumps(dict(record=kind, data=data), ensure_ascii=False, separators=(',', ':'))
                      + '\n' for kind, data in rows).encode('utf-8')
        self.graph.write_bytes(gzip.compress(raw, mtime=0) if codec == 'gzip' else lzma.compress(raw))
        self.binding = dict(repository=self.repo, archive=self.graph,
                            invocation_prefix=(sys.executable, '-B', str(self.runtime / 'columbus.py')),
                            archive_sha256=sha(self.graph.read_bytes()), runtime_inventory=dict(self.runtime_inventory),
                            source_manifest=inventory(self.repo), revision='table-fixture')

    def event(self, queries=('outer',), *, offset=0, limit=120, budget=12000,
              overloads=False, actual_cli=False):
        from columbus.source_calls import source_calls_archive, source_calls_text
        arguments = ['archive-source', *queries, '--call-sites', '--call-table', '--input', str(self.graph),
                     '--repo', str(self.repo), '--format', 'text', '--offset', str(offset),
                     '--limit', str(limit), '--budget-bytes', str(budget)]
        if overloads:
            arguments.append('--overloads')
        argv = [*self.binding['invocation_prefix'], *arguments]
        if actual_cli:
            result = subprocess.run(argv, cwd=self.repo, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
            self.assertEqual(result.stderr, b'')
            output = result.stdout.decode('utf-8')
        else:
            packet = source_calls_archive(self.graph, list(queries), self.repo, limit, budget, offset,
                                          output_format='text', overloads=overloads, call_table=True)
            output = source_calls_text(packet, call_table=True)
        return dict(type='item.completed', item=dict(id='command-1', type='command_execution',
                    command=shlex.join(argv), status='completed', exit_code=0, aggregated_output=output))

    def recognize(self, events, relationships=None):
        return EVIDENCE.evidence(events, binding=self.binding,
                                 relationships=self.reviewed if relationships is None else relationships)

    def rejected(self, event):
        result = self.recognize([event])
        self.assertFalse(result['call_table_used'])
        self.assertFalse(result['relationship_used'])
        self.assertEqual(result['source_call_receipts'], [])
        self.assertEqual(result['relationship_receipts'], [])

    @staticmethod
    def changed_argv(event, operation):
        result = deepcopy(event)
        words = shlex.split(result['item']['command'])
        operation(words)
        result['item']['command'] = shlex.join(words)
        assert result['item']['command'] != event['item']['command']
        return result

    def test_actual_cli_codecs_full_metadata_hashes_and_no_writes(self):
        before = inventory(self.runtime), inventory(self.repo)
        for codec in ('gzip', 'xz'):
            self.freeze(codec=codec)
            event = self.event(actual_cli=True)
            receipt = self.recognize([event])
            self.assertTrue(receipt['call_table_used'])
            self.assertTrue(receipt['relationship_used'])
            source = receipt['source_call_receipts'][0]
            self.assertEqual((source['source_rows'], source['stored_edges'], source['endpoint_nodes']), (8, 6, 3))
            self.assertEqual((source['resolved_call_reference_count'], source['unresolved_call_reference_count']), (5, 1))
            self.assertEqual(source['encoding'], 'columbus-call-table/v1')
            self.assertEqual(source['invocation']['call_table'], True)
            self.assertEqual(source['output_sha256'], sha(event['item']['aggregated_output'].encode()))
            self.assertEqual(source['command_sha256'], sha(event['item']['command'].encode()))
            self.assertEqual(source['event_json_sha256'], sha(EVIDENCE.LEGACY._compact(event).encode()))
            self.assertNotIn('source', source)
            self.assertNotIn('quotes_used', receipt)
        self.assertEqual((inventory(self.runtime), inventory(self.repo)), before)
        self.assertFalse((self.repo / '.columbus').exists())

    def test_explicit_flags_format_options_and_complete_invocation_binding(self):
        event = self.event(('outer', 'tail'))
        variants = []
        for flag in ('--call-table', '--call-sites'):
            variants.append(self.changed_argv(event, lambda words, flag=flag: words.remove(flag)))
        for flag, value in (('--format', 'json'), ('--budget-bytes', 'true'), ('--budget-bytes', '2047'),
                            ('--budget-bytes', '64001'), ('--limit', '0'), ('--limit', '401'),
                            ('--offset', '1'), ('--input', str(self.base / 'other.gz')),
                            ('--repo', str(self.base)), ('--format', 'TEXT')):
            variants.append(self.changed_argv(event, lambda words, flag=flag, value=value:
                                              words.__setitem__(words.index(flag) + 1, value)))
        for extra in (['--call-table'], ['--call-table=true'], ['--call-table', 'false'],
                      ['--pretty'], ['--db', 'ignored'], ['--telemetry', ''], ['--forma', 'text']):
            variants.append(self.changed_argv(event, lambda words, extra=extra: words.extend(extra)))
        for index, value in ((0, '/untrusted/python'), (1, '-I'), (2, '/untrusted/columbus.py'),
                             (4, 'tail')):
            variants.append(self.changed_argv(event, lambda words, index=index, value=value:
                                              words.__setitem__(index, value)))
        variants.append(self.changed_argv(event, lambda words: words.__setitem__(slice(4, 6), ['tail', 'outer'])))
        for variant in variants:
            with self.subTest(command=variant['item']['command']):
                self.rejected(variant)

    def test_quoting_global_repo_and_exact_absolute_shell_allowlist(self):
        event = self.event()
        words = [*self.binding['invocation_prefix'], '--repo', str(self.repo), 'archive-source', 'outer',
                 '--call-sites', '--call-table', '--input=' + str(self.graph), '--format=text']
        event['item']['command'] = shlex.join(words)
        self.assertTrue(self.recognize([event])['relationship_used'])
        for spelling in ("--'call-'table", '--call\\-table'):
            split = deepcopy(event)
            split['item']['command'] = event['item']['command'].replace('--call-table', spelling)
            self.assertTrue(self.recognize([split])['relationship_used'])
        for shell in sorted(EVIDENCE._SHELLS):
            for flag in ('-c', '-lc'):
                wrapped = deepcopy(event)
                wrapped['item']['command'] = shlex.join([shell, flag, event['item']['command']])
                self.assertTrue(self.recognize([wrapped])['relationship_used'])
        for shell in ('sh', 'bash', 'zsh', '/untrusted/zsh', '/tmp/sh'):
            wrapped = deepcopy(event)
            wrapped['item']['command'] = shlex.join([shell, '-c', event['item']['command']])
            self.rejected(wrapped)
        for suffix in ('; echo ignored', ' # comment', ' | more', ' $(echo ignored)'):
            injected = deepcopy(event)
            injected['item']['command'] += suffix
            self.rejected(injected)

    def test_table_rows_indexes_duplicates_and_all_bytes_are_bound(self):
        event = self.event()
        lines = event['item']['aggregated_output'].splitlines()
        edge_start = next(index for index, value in enumerate(lines) if value.startswith('call_edges ')) + 1
        node_start = next(index for index, value in enumerate(lines) if value.startswith('call_nodes ')) + 1
        file_start = next(index for index, value in enumerate(lines) if value.startswith('call_files ')) + 1
        mutations = []
        for index, field, value in ((edge_start, 0, 99), (edge_start, 1, True), (edge_start, 2, 0),
                                     (node_start, 0, 1), (node_start, 1, 999), (file_start, 0, False)):
            changed = list(lines)
            row = json.loads(changed[index])
            row[field] = value
            changed[index] = EVIDENCE.LEGACY._compact(row)
            mutations.append(changed)
        mutations += [lines[:edge_start] + lines[edge_start + 1:], lines + [lines[edge_start]],
                      lines[:node_start] + [lines[node_start]] + lines[node_start:],
                      lines[:file_start] + lines[file_start + 1:]]
        for changed in mutations:
            tampered = deepcopy(event)
            tampered['item']['aggregated_output'] = '\n'.join(changed) + '\n'
            self.assertNotEqual(tampered, event)
            self.rejected(tampered)
        for old, new in (('columbus-call-table/v1', 'columbus-call-table/v2'),
                          ('"stored_call_sites_complete":true', '"stored_call_sites_complete":false'),
                          ('"unresolved_call_reference_count":1', '"unresolved_call_reference_count":0'),
                          ('"source_status":"archive_only"', '"source_status":"selected_file_hash_verified"'),
                          ('"next_offset":null', '"next_offset":8'),
                          ('"semantic_complete":false', '"semantic_complete":true'),
                          ('callee:2:4', 'callee:2:5')):
            tampered = deepcopy(event)
            tampered['item']['aggregated_output'] = event['item']['aggregated_output'].replace(old, new)
            self.assertNotEqual(tampered, event)
            self.rejected(tampered)
        for output in (event['item']['aggregated_output'][:-1], event['item']['aggregated_output'] + '\n',
                       event['item']['aggregated_output'].replace('\n', '\r\n')):
            tampered = deepcopy(event)
            tampered['item']['aggregated_output'] = output
            self.rejected(tampered)

    def test_unknown_partial_control_unicode_and_separate_file_indexes(self):
        controls = ''.join(chr(number) for number in (*range(32), *range(127, 160), 0x2028, 0x2029))
        for kind, row in self.body:
            if kind == 'node' and row['id'] == self.ping:
                row.pop('partial')
                row['name'] += controls
            if kind == 'edge':
                row['evidence'] += controls + '\\u0085'
        self.freeze()
        event = self.event(budget=64000)
        output = event['item']['aggregated_output']
        self.assertTrue(self.recognize([event])['relationship_used'])
        self.assertIn('"partial":null', output)
        self.assertIn('[0,"a target #한.py"', output)
        self.assertIn('[0,"calls.py"', output)  # The source table has an independent zero.
        self.assertFalse(any(char in output for char in controls if char != '\n'))
        tampered = deepcopy(event)
        tampered['item']['aggregated_output'] = output.replace('\\u0085', '\x85', 1)
        self.rejected(tampered)

    def test_long_shared_ids_fit_table_and_preserve_legacy_flood_behavior(self):
        from columbus.source_calls import source_calls_archive
        replacements = {identity: identity + 'x' * 900 for identity in (self.outer, self.ping)}
        for kind, row in self.body:
            for key in ('id', 'source', 'target'):
                if row.get(key) in replacements:
                    row[key] = replacements[row[key]]
        first = next(row for kind, row in self.body if kind == 'edge')
        self.body = [(kind, row) for kind, row in self.body if kind not in {'edge', 'reference'}]
        self.body += [('edge', deepcopy(first)) for _ in range(24)]
        self.reviewed = [{key: first[key] for key in ('source', 'target', 'path', 'line')}]
        self.freeze()
        event = self.event()
        result = self.recognize([event])
        self.assertEqual(result['source_call_receipts'][0]['source_rows'], 8)
        self.assertEqual(result['source_call_receipts'][0]['stored_edges'], 24)
        old = source_calls_archive(self.graph, ['outer'], self.repo, output_format='text')
        self.assertEqual(old['next_offset'], 1)

    def test_selected_projection_capacity_is_not_raw_hydrated_node_cap(self):
        from columbus.source_calls import _node
        owner = next(row for kind, row in self.body if kind == 'node' and row['id'] == self.outer)
        owner['name'] = ''
        owner['name'] = 'n' * (63990 - len(EVIDENCE.LEGACY._compact(owner).encode()))
        hydrated = _node(owner)
        hydrated.update(source_hash='0' * 64, source_status='selected_file_hash_verified')
        self.assertGreater(len(EVIDENCE.LEGACY._compact(hydrated).encode()), 64000)
        self.freeze()
        event = self.event(limit=1, budget=6000)
        self.assertTrue(self.recognize([event])['call_table_used'])

    def test_endpoint_and_file_index_widths_bind_exact_utf8_budget(self):
        owner = next(deepcopy(row) for kind, row in self.body if kind == 'node' and row['id'] == self.outer)
        targets = []
        for number in range(100):
            path = f'target{number:03d}한.py'
            (self.repo / path).write_bytes(b'def target(): pass\n')
            targets.append(self.node(path + '::target:function', path, 'target', 1, 1))
        for count in (9, 10, 99, 100):
            with self.subTest(maximum_index=count):
                self.body = [('node', owner)] + [('node', node) for node in targets[:count]]
                self.body += [('edge', dict(source=self.outer, target=node['id'], path='calls.py',
                                            line=2, kind='calls', confidence='heuristic', evidence='한\x85'))
                              for node in targets[:count]]
                self.freeze()
                event = self.event(budget=64000)
                output = event['item']['aggregated_output']
                size = len(output.encode('utf-8'))
                self.assertLess(size, 64000)
                # Distinct endpoint files ensure both index spaces cross the
                # decimal-width boundaries, not merely the node indexes.
                self.assertIn(f'[{count},"target', output)
                self.assertIn(f'[{count},{count},', output)
                exact = self.event(budget=size)
                self.assertEqual(exact['item']['aggregated_output'], output)
                self.assertTrue(self.recognize([exact], [])['call_table_used'])
                too_small = self.changed_argv(exact, lambda words:
                    words.__setitem__(words.index('--budget-bytes') + 1, str(size - 1)))
                self.rejected(too_small)

    def test_jvm_overloads_and_different_receiver_groups_keep_their_semantics(self):
        source = b'class Owner {\n fun run() { run(1) }\n fun run(x: Int) {}\n fun run(x: String) {}\n}\n'
        (self.repo / 'Owner.kt').write_bytes(source)
        nodes = []
        for number, parameters in ((2, []), (3, ['Int']), (4, ['String'])):
            node = self.node(f'Owner.kt::Owner.run({",".join(parameters)}):method',
                             'Owner.kt', 'run', number, number)
            node.update(kind='method', qualname='Owner.run', language='kotlin', parent_id='Owner.kt::Owner:class',
                        receiver_type='', local=False, parameter_types=parameters)
            nodes.append(node)
        edge = dict(source=nodes[0]['id'], target=nodes[1]['id'], path='Owner.kt', line=2,
                    kind='calls', confidence='resolved_static', evidence='callee:2:13-2:16')
        self.body = [('node', node) for node in nodes] + [('edge', edge)]
        self.reviewed = [{key: edge[key] for key in ('source', 'target', 'path', 'line')}]
        self.freeze()
        event = self.event(('Owner.run', nodes[0]['id']), overloads=True)
        result = self.recognize([event])
        self.assertTrue(result['relationship_used'])
        self.assertEqual(result['source_call_receipts'][0]['target_ids'], [node['id'] for node in nodes])
        self.assertEqual(result['source_call_receipts'][0]['source_rows'], 3)
        self.assertIn('same-owner JVM overload groups; not runtime dispatch', event['item']['aggregated_output'])
        self.rejected(self.changed_argv(event, lambda words: words.remove('--overloads')))
        nodes[-1]['receiver_type'] = 'String'
        self.freeze()
        self.rejected(event)

    def test_physical_source_decode_controls_and_malformed_endpoint_inputs(self):
        source = self.repo / 'calls.py'
        original = source.read_bytes()
        variants = [original.replace(b'\n', b'\r\n'), original.replace(b'\n', b'\r'),
                    original.replace(b'    return 1', b'    return "\\u2028"  # \xe2\x80\xa8\xc2\x85')]
        for content in variants:
            source.write_bytes(content)
            self.freeze()
            self.assertTrue(self.recognize([self.event()])['relationship_used'])
        # Preserve the two physical lines despite a Python encoding cookie.
        source.write_bytes(b'# coding: latin-1\n# caf\xe9\n')
        node = self.node(self.outer, 'calls.py', 'outer', 1, 2)
        self.body = [('node', node)]
        self.freeze()
        self.assertTrue(self.recognize([self.event()], [])['call_table_used'])
        source.write_bytes(b'\n')
        node['end_line'] = 1
        self.freeze()
        blank = self.event()
        self.assertEqual(self.recognize([blank], [])['source_call_receipts'][0]['source_rows'], 1)
        for mutation in ('empty-source', 'null-partial', 'duplicate-node', 'missing-endpoint', 'bad-owner-range'):
            source.write_bytes(b'\n')
            self.body = [('node', deepcopy(node))]
            if mutation == 'empty-source':
                source.write_bytes(b'')
            elif mutation == 'null-partial':
                self.body[0][1]['partial'] = None
            elif mutation == 'duplicate-node':
                self.body.append(('node', deepcopy(node)))
            else:
                self.body.append(('edge', dict(source=self.outer, target=self.outer if mutation == 'bad-owner-range'
                                               else 'calls.py::absent:function', path='calls.py', line=2,
                                               kind='calls', confidence='heuristic', evidence='bad')))
            self.freeze()
            if mutation == 'empty-source':
                with self.assertRaises(ValueError):
                    self.event()
                self.rejected(blank)
            else:
                with self.assertRaises(ValueError):
                    self.recognize([])

    def test_exact_budget_no_shorter_prefix_and_flood_no_skipped_line(self):
        event = self.event(budget=64000)
        size = len(event['item']['aggregated_output'].encode())
        exact = self.event(budget=size)
        self.assertEqual(exact['item']['aggregated_output'], event['item']['aggregated_output'])
        self.assertTrue(self.recognize([exact])['call_table_used'])
        too_small = self.changed_argv(exact, lambda words: words.__setitem__(words.index('--budget-bytes') + 1, str(size - 1)))
        self.rejected(too_small)
        short = self.event(limit=1)
        self.rejected(self.changed_argv(short, lambda words: words.__setitem__(words.index('--limit') + 1, '120')))
        for kind, row in self.body:
            if kind == 'edge' and row['line'] == 2:
                row['evidence'] = 'flood' * 1500
        for reverse in (False, True):
            if reverse:
                self.body.reverse()
            self.freeze(codec='xz' if reverse else 'gzip')
            page = self.event(budget=6000)
            self.assertEqual(self.recognize([page])['source_call_receipts'][0]['next_offset'], 1)
            with self.assertRaises(ValueError):
                self.event(offset=1, budget=6000)
            later = self.event(offset=2, limit=1, budget=6000)
            self.rejected(self.changed_argv(later, lambda words: words.__setitem__(words.index('--offset') + 1, '1')))

    def test_overlap_pages_complete_union_and_zero_calls_not_graph_utility(self):
        offset, ranges, edges = 0, [], 0
        while offset is not None:
            event = self.event(('outer', 'outer.inner', 'tail'), offset=offset, limit=2)
            receipt = self.recognize([event])['source_call_receipts'][0]
            for block in receipt['ranges']:
                ranges.extend(range(block['start_line'], block['end_line'] + 1))
            edges += receipt['stored_edges']
            offset = receipt['next_offset']
        self.assertEqual(ranges, [*range(1, 9), 10])
        self.assertEqual(edges, 6)
        for event in (self.event(('tail',)), self.event(offset=5, limit=1)):
            result = self.recognize([event])
            self.assertTrue(result['call_table_used'])
            self.assertFalse(result['relationship_used'])
            self.assertEqual(result['source_call_receipts'][0]['stored_edges'], 0)
        self.assertFalse(self.recognize([self.event()], [{**self.reviewed[0], 'line': 3}])['relationship_used'])

    def test_failed_offered_boolean_nonterminal_empty_and_unserializable_events(self):
        event = self.event()
        for key, values in (('exit_code', [False, True, '0', 1]), ('status', ['in_progress', None]),
                            ('id', ['', None]), ('aggregated_output', ['', None, '\ud800'])):
            for value in values:
                changed = deepcopy(event)
                changed['item'][key] = value
                self.rejected(changed)
        for kind in ('item.started', 'agent_message', 'turn.completed'):
            changed = deepcopy(event)
            changed['type'] = kind
            self.rejected(changed)
        changed = deepcopy(event)
        nested = []
        # CPython versions differ: C JSON encoding can permit more nesting than
        # the Python recursion limit. This remains a tiny synthetic value.
        for _ in range(max(10000, sys.getrecursionlimit() * 4)):
            nested = [nested]
        changed['extra'] = nested
        try:
            EVIDENCE.LEGACY._compact(changed)
        except (RecursionError, OverflowError):
            self.rejected(changed)
        else:
            # A future/native encoder may support this depth; valid encodable
            # extra event data is not an invented command/packet violation.
            self.assertTrue(self.recognize([changed])['call_table_used'])
        compact = EVIDENCE.LEGACY._compact
        for error in (RecursionError, OverflowError):
            def fail_whole_event(value):
                if value is event:
                    raise error('whole-event serialization failure')
                return compact(value)

            with patch.object(EVIDENCE.LEGACY, '_compact', side_effect=fail_whole_event):
                self.rejected(event)
        changed = deepcopy(event)
        changed['extra'] = '\ud800'
        self.rejected(changed)

    def test_bad_frozen_inputs_are_errors_even_for_empty_events(self):
        before = deepcopy(self.binding)
        self.assertFalse(self.recognize([])['call_table_used'])
        self.assertEqual(self.binding, before)
        for field, value in (('archive_sha256', '0' * 64), ('source_manifest', {}),
                             ('runtime_inventory', {}), ('revision', 'different'),
                             ('source_manifest', list(self.binding['source_manifest'].items())),
                             ('runtime_inventory', list(self.binding['runtime_inventory'].items()))):
            altered = deepcopy(self.binding)
            altered[field] = value
            with self.assertRaisesRegex(ValueError, 'frozen'):
                EVIDENCE.evidence([], binding=altered, relationships=self.reviewed)
        original = self.graph.read_bytes()
        for codec in ('gzip', 'xz'):
            self.freeze(codec=codec, footer=False)
            with self.assertRaises(ValueError):
                self.recognize([])
        self.graph.write_bytes(original)
        self.freeze(extra=[('diagnostic', {})])
        with self.assertRaises(ValueError):
            self.recognize([])

    def test_mutated_binding_object_or_added_deleted_files_never_returns_receipts(self):
        original = deepcopy(self.binding)

        def changed_binding():
            self.binding['revision'] = 'changed during recognition'
            yield from ()

        with self.assertRaisesRegex(ValueError, 'changed during recognition'):
            self.recognize(changed_binding())
        self.binding = original
        extra = self.repo / 'unexpected.py'
        extra.write_bytes(b'# new\n')
        with self.assertRaises(ValueError):
            self.recognize([])
        extra.unlink()
        target = self.repo / 'a target #한.py'
        target.unlink()
        with self.assertRaises(ValueError):
            self.recognize([])

    def test_binding_mutation_during_final_archive_reread_is_rejected(self):
        original = EVIDENCE.LEGACY._read
        archive_reads = 0

        def mutate_during_final_read(path):
            nonlocal archive_reads
            result = original(path)
            if path == self.graph:
                archive_reads += 1
                if archive_reads == 2:
                    self.binding['source_manifest']['calls.py'] = '0' * 64
            return result

        with patch.object(EVIDENCE.LEGACY, '_read', side_effect=mutate_during_final_read):
            with self.assertRaisesRegex(ValueError, 'changed during recognition'):
                self.recognize([])
        self.assertEqual(archive_reads, 2)

    def test_final_rehash_catches_same_size_restored_mtime_for_every_input_class(self):
        for path in (self.repo / 'calls.py', self.runtime / 'columbus.py', self.graph):
            original, stamp = path.read_bytes(), path.stat()
            before_binding = deepcopy(self.binding)

            def changed_after_snapshot():
                path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
                yield from ()

            # Simulate the same-size/restored-mtime Windows birthtime blind spot.
            def metadata_without_change_times(info):
                return (info.st_dev, info.st_ino, info.st_size, 0, 0)

            try:
                with patch.object(EVIDENCE.LEGACY, '_stamp', side_effect=metadata_without_change_times):
                    with self.assertRaisesRegex(ValueError, 'changed during recognition'):
                        self.recognize(changed_after_snapshot())
                self.assertEqual(self.binding, before_binding)
            finally:
                path.write_bytes(original)
                os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))

    def test_import_api_never_execute_production_and_historical_verifier_unchanged(self):
        path = ROOT / 'evals/exploration/source_call_evidence.py'
        self.assertEqual(sha(path.read_bytes()), HISTORICAL_SHA)
        event = self.event()
        self.assertEqual(EVIDENCE.LEGACY.evidence([event], binding=self.binding,
                                                relationships=self.reviewed)['source_call_receipts'], [])
        from columbus.source_calls import source_calls_archive, source_calls_json
        old = deepcopy(event)
        words = shlex.split(old['item']['command'])
        words.remove('--call-table')
        words[words.index('--format') + 1] = 'json'
        old['item']['command'] = shlex.join(words)
        old['item']['aggregated_output'] = source_calls_json(source_calls_archive(self.graph, ['outer'], self.repo))
        self.assertTrue(EVIDENCE.LEGACY.evidence([old], binding=self.binding,
                                               relationships=self.reviewed)['relationship_used'])
        self.rejected(old)
        before = inventory(self.runtime), inventory(self.repo), self.graph.read_bytes()
        with patch('subprocess.run', side_effect=AssertionError('no subprocess')), \
             patch('subprocess.Popen', side_effect=AssertionError('no subprocess')), \
             patch('columbus.source_calls.source_calls_archive', side_effect=AssertionError('no production')), \
             patch('columbus.source_calls.source_calls_text', side_effect=AssertionError('no renderer')):
            self.assertTrue(self.recognize([event])['relationship_used'])
        self.assertEqual((inventory(self.runtime), inventory(self.repo), self.graph.read_bytes()), before)
        self.assertEqual(sha(path.read_bytes()), HISTORICAL_SHA)


if __name__ == '__main__':
    unittest.main()
