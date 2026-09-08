"""Independent future receipts: actual source/call delivery, never model use."""
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/columbus/scripts'
SPEC = importlib.util.spec_from_file_location('prospective_source_call_evidence',
                                            ROOT / 'evals/exploration/source_call_evidence.py')
EVIDENCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVIDENCE)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory(root):
    return {path.relative_to(root).as_posix(): sha(path.read_bytes())
            for path in root.rglob('*') if path.is_file()}


class SourceCallEvidenceTests(unittest.TestCase):
    outer = 'calls.py::outer:function'
    inner = 'calls.py::outer.inner:function'
    tail = 'calls.py::tail:function'
    ping = 'other.py::ping:function'

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
    def node(identity, path, name, start, end, **extra):
        return dict(id=identity, path=path, name=name, qualname=name, kind='function',
                    start_line=start, end_line=end, language='python', fidelity='ast',
                    partial=False, module=Path(path).stem, **extra)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / 'repository'
        self.repo.mkdir()
        (self.repo / 'calls.py').write_bytes(
            b'def outer():\n    ping()\n    def inner():\n        ping(); ping()\n'
            b'        inner()\n    missing()\n    inner()\n    return 1\n\ndef tail(): return 2\n')
        (self.repo / 'other.py').write_bytes(b'def ping(): pass\n')
        nodes = [self.node(self.outer, 'calls.py', 'outer', 1, 8),
                 self.node(self.inner, 'calls.py', 'outer.inner', 3, 5),
                 self.node(self.tail, 'calls.py', 'tail', 10, 10),
                 self.node(self.ping, 'other.py', 'ping', 1, 1)]
        edges = [dict(source=owner, target=target, path='calls.py', line=number,
                      kind='calls', confidence='resolved_static', evidence=f'callee:{number}:{column}')
                 for owner, target, number, column in (
                     (self.outer, self.ping, 2, 4), (self.inner, self.ping, 4, 8),
                     (self.inner, self.ping, 4, 16), (self.inner, self.inner, 5, 8),
                     (self.outer, self.inner, 7, 4))]
        self.body = [('node', node) for node in nodes]
        self.body += [('edge', edge) for edge in edges]
        self.body += [('edge', deepcopy(edges[0]))]  # A duplicate stored row is not deduplicated.
        self.body += [('reference', dict(source=edge['source'], path=edge['path'], line=edge['line'],
                        kind='calls', name='callee', resolved=True)) for edge in edges]
        self.body.append(('reference', dict(source=self.outer, path='calls.py', line=6,
                                           kind='calls', name='missing', resolved=False)))
        self.graph = self.base / 'graph.gz'
        self.freeze()
        self.reviewed = [{key: edges[0][key] for key in ('source', 'target', 'path', 'line')}]

    def freeze(self, *, codec='gzip', footer=True, extra=()):
        files = [('file', dict(path=path.name, hash=sha(path.read_bytes()), size=path.stat().st_size))
                 for path in sorted(self.repo.iterdir()) if path.is_file()]
        rows = files + self.body
        names = dict(file='files', node='nodes', edge='edges', reference='references',
                     scope='scopes', diagnostic='diagnostics', **{'import': 'imports'})
        counts = dict.fromkeys(names.values(), 0)
        for kind, _ in rows:
            counts[names[kind]] += 1
        rows = [('manifest', dict(format='columbus-graph', version=1, revision='receipt-fixture'))] + rows
        if footer:
            rows.append(('end', counts))
        rows.extend(extra)
        raw = ''.join(json.dumps(dict(record=kind, data=data), ensure_ascii=False, separators=(',', ':'))
                      + '\n' for kind, data in rows).encode('utf-8')
        if codec == 'gzip':
            self.graph.write_bytes(gzip.compress(raw, mtime=0))
        else:
            import lzma
            self.graph.write_bytes(lzma.compress(raw))
        self.binding = dict(repository=self.repo, archive=self.graph,
                            invocation_prefix=(sys.executable, '-B', str(self.runtime / 'columbus.py')),
                            archive_sha256=sha(self.graph.read_bytes()),
                            runtime_inventory=dict(self.runtime_inventory),
                            source_manifest=inventory(self.repo), revision='receipt-fixture')

    def event(self, queries=('outer',), *, form='json', offset=0, limit=120,
              budget=12000, overloads=False, actual_cli=False):
        from columbus.source_calls import source_calls_archive, source_calls_json, source_calls_text
        arguments = ['archive-source', *queries, '--call-sites', '--input', str(self.graph),
                     '--repo', str(self.repo), '--format', form, '--offset', str(offset),
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
                                          output_format=form, overloads=overloads)
            output = source_calls_text(packet) if form == 'text' else source_calls_json(packet)
        return dict(type='item.completed', item=dict(id='command-1', type='command_execution',
                    command=shlex.join(argv), status='completed', exit_code=0, aggregated_output=output))

    def recognize(self, events, relationships=None):
        return EVIDENCE.evidence(events, binding=self.binding,
                                 relationships=self.reviewed if relationships is None else relationships)

    def rejected(self, event):
        result = self.recognize([event])
        self.assertEqual(result['source_call_receipts'], [])
        self.assertEqual(result['relationship_receipts'], [])
        self.assertIs(result['relationship_used'], False)

    def test_actual_cli_json_text_gzip_xz_and_complete_receipts(self):
        before = inventory(self.runtime)
        for codec in ('gzip', 'xz'):
            self.freeze(codec=codec)
            for form in ('json', 'text'):
                with self.subTest(codec=codec, form=form):
                    event = self.event(form=form, actual_cli=True)
                    result = self.recognize([event])
                    self.assertTrue(result['relationship_used'])
                    receipt = result['source_call_receipts'][0]
                    self.assertEqual(receipt['source_rows'], 8)
                    self.assertEqual(receipt['stored_edges'], 6)
                    self.assertEqual(receipt['endpoint_nodes'], 3)
                    self.assertEqual(receipt['resolved_call_reference_count'], 5)
                    self.assertEqual(receipt['unresolved_call_reference_count'], 1)
                    self.assertEqual(receipt['output_sha256'], sha(event['item']['aggregated_output'].encode()))
                    self.assertNotIn('quotes_used', result)
                    self.assertNotIn('source', receipt)
        self.assertEqual(inventory(self.runtime), before)
        self.assertFalse((self.repo / '.columbus').exists())

    def test_defaults_global_repo_shell_wrapper_and_literal_dollar_query(self):
        event = self.event()
        argv = [*self.binding['invocation_prefix'], '--repo', str(self.repo),
                'archive-source', 'outer', '--call-sites', '--input', str(self.graph)]
        event['item']['command'] = shlex.join(argv)
        self.assertTrue(self.recognize([event])['relationship_used'])
        event['item']['command'] = shlex.join(['/bin/sh', '-c', event['item']['command']])
        self.assertTrue(self.recognize([event])['relationship_used'])
        for kind, node in self.body:
            if kind == 'node' and node['id'] == self.outer:
                node.update(name='outer$literal', qualname='outer$literal')
        self.freeze()
        self.assertTrue(self.recognize([self.event(('outer$literal',))])['relationship_used'])

    def test_full_command_binding_and_noop_negative_mutations_are_rejected(self):
        original = self.event()
        words = shlex.split(original['item']['command'])
        variants = []
        for token, replacement in [(words[0], '/untrusted/python'), (words[2], '/untrusted/columbus.py'),
                                   ('outer', 'tail'), (str(self.graph), str(self.base / 'wrong.gz')),
                                   (str(self.repo), str(self.base)), ('json', 'text')]:
            altered = words.copy()
            altered[altered.index(token)] = replacement
            variants.append(shlex.join(altered))
        for option, value in [('--offset', '1'), ('--limit', '1'), ('--budget-bytes', '2048')]:
            altered = words.copy()
            altered[altered.index(option) + 1] = value
            variants.append(shlex.join(altered))
        variants += [shlex.join([word for word in words if word != '--call-sites']),
                     shlex.join(words + ['--overloads']), shlex.join(words + ['--call-sites']),
                     shlex.join(words + ['--input', str(self.graph)]),
                     shlex.join(words + ['--telemetry', '']), shlex.join(words + ['--db', '']),
                     shlex.join(words + ['--pretty']), shlex.join(words + ['--inp', str(self.graph)]),
                     original['item']['command'] + '; true', original['item']['command'] + ' # hidden',
                     original['item']['command'] + ' > /tmp/out']
        for command in variants:
            with self.subTest(command=command):
                self.assertNotEqual(command, original['item']['command'])
                event = deepcopy(original)
                event['item']['command'] = command
                self.rejected(event)

    def test_failed_offered_missing_status_and_empty_output_never_count(self):
        original = self.event()
        variants = []
        for key, value in [('exit_code', 1), ('exit_code', False), ('status', 'failed'), ('id', None), ('id', ''),
                           ('type', 'agent_message'), ('aggregated_output', '')]:
            event = deepcopy(original)
            event['item'][key] = value
            variants.append(event)
        event = deepcopy(original)
        event['item'].pop('status')
        variants += [event, dict(type='item.started', item=original['item'])]
        for event in variants:
            self.rejected(event)

    def test_batches_aliases_and_pages_cover_union_without_double_counting(self):
        queries = ('tail', 'outer.inner', 'outer', 'calls.outer')
        offset, positions, edge_count = 0, [], 0
        while True:
            event = self.event(queries, limit=2, offset=offset)
            receipt = self.recognize([event])['source_call_receipts'][0]
            self.assertEqual(len(receipt['target_ids']), 3)
            self.assertEqual(receipt['invocation']['offset'], offset)
            positions.extend((block['path'], number) for block in receipt['ranges']
                             for number in range(block['start_line'], block['end_line'] + 1))
            edge_count += receipt['stored_edges']
            offset = receipt['next_offset']
            if offset is None:
                break
        self.assertEqual(positions, [('calls.py', number) for number in [1, 2, 3, 4, 5, 6, 7, 8, 10]])
        self.assertEqual(edge_count, 6)

    def test_packet_tampering_duplicate_calls_and_endpoint_freshness(self):
        original = self.event()
        packet = json.loads(original['item']['aggregated_output'])
        mutations = [
            lambda p: p['call_sites']['edges'].pop(),
            lambda p: p['call_sites']['edges'].append(deepcopy(p['call_sites']['edges'][0])),
            lambda p: p['call_sites']['edges'][0].update(line=3),
            lambda p: p['call_sites']['edges'][2].update(source=self.outer),
            lambda p: p['call_sites']['edges'][0].update(confidence='heuristic'),
            lambda p: p['call_sites']['edges'][0].update(evidence='invented'),
            lambda p: p['call_sites']['nodes'].pop(),
            lambda p: p['call_sites']['nodes'].append(deepcopy(p['call_sites']['nodes'][0])),
            lambda p: p['call_sites']['nodes'][-1].update(source_status='selected_file_hash_verified'),
            lambda p: p['call_sites'].update(unresolved_call_reference_count=0),
            lambda p: p['call_sites'].update(semantic_complete=True),
            lambda p: p['sources'][0].update(source='not the source'),
            lambda p: p['sources'][0].update(start_line=True),
            lambda p: p.update(next_offset=8),
            lambda p: p.update(total_lines=9),
            lambda p: p.update(sources=[]),
        ]
        from columbus.source_calls import source_calls_json
        for mutate in mutations:
            changed = deepcopy(packet)
            mutate(changed)
            self.assertNotEqual(source_calls_json(changed), source_calls_json(packet))
            event = deepcopy(original)
            event['item']['aggregated_output'] = source_calls_json(changed)
            self.rejected(event)
        for suffix in ('\n', 'stderr contamination\n'):
            event = deepcopy(original)
            event['item']['aggregated_output'] += suffix
            self.rejected(event)
        event = deepcopy(original)
        event['item']['aggregated_output'] = original['item']['aggregated_output'].replace(
            '"semantic_complete":false', '"semantic_complete":false,"semantic_complete":false', 1)
        self.rejected(event)

    def test_exact_budget_boundary_and_no_silent_shorter_prefix(self):
        for form in ('json', 'text'):
            large = self.event(form=form, budget=64000)
            size = len(large['item']['aggregated_output'].encode())
            self.assertGreater(size, 2048)
            exact = self.event(form=form, budget=size)
            self.assertTrue(self.recognize([exact])['source_call_receipts'])
            smaller = self.event(form=form, budget=size - 1)
            self.assertTrue(self.recognize([smaller])['source_call_receipts'])
            # A real shorter response cannot be pasted under the larger request.
            smaller['item']['command'] = exact['item']['command']
            self.rejected(smaller)

    def test_zero_edges_unresolved_only_and_unreviewed_relationships_are_separate(self):
        for query, offset in [('tail', 0), ('outer', 5)]:
            result = self.recognize([self.event((query,), offset=offset, limit=1)])
            self.assertEqual(len(result['source_call_receipts']), 1)
            self.assertFalse(result['relationship_used'])
        wrong = deepcopy(self.reviewed)
        wrong[0]['line'] += 10000
        self.assertFalse(self.recognize([self.event()], wrong)['relationship_used'])
        event = self.event()
        event['item']['command'] = event['item']['command'].replace('archive-source', 'archive-quotes', 1)
        self.rejected(event)

    def test_runtime_source_archive_inventory_add_delete_and_byte_tampering(self):
        original = self.event()
        for root, relative in [(self.repo, 'calls.py'), (self.runtime, 'columbus.py')]:
            path = root / relative
            before = path.read_bytes()
            try:
                path.write_bytes(before + b'\n# changed\n')
                with self.assertRaises(ValueError):
                    self.recognize([original])
                path.unlink()
                with self.assertRaises(ValueError):
                    self.recognize([])
            finally:
                path.write_bytes(before)
            extra = root / 'unexpected.txt'
            try:
                extra.write_bytes(b'added')
                with self.assertRaises(ValueError):
                    self.recognize([])
            finally:
                extra.unlink()
        self.graph.write_bytes(self.graph.read_bytes() + b'tamper')
        with self.assertRaises(ValueError):
            self.recognize([])

    def test_invalid_archive_bindings_fail_preflight_even_without_events(self):
        pristine = deepcopy(self.body)
        mutations = [lambda: self.body.append(deepcopy(self.body[0])),
                     lambda: self.body.__setitem__(slice(None), [(kind, data) for kind, data in self.body
                         if not (kind == 'node' and data['id'] == self.ping)]),
                     lambda: self.body[0][1].update(partial=None),
                     lambda: self.body[0][1].update(start_line=True),
                     lambda: self.body[0][1].update(language='java')]
        for mutate in mutations:
            self.body = deepcopy(pristine)
            mutate()
            self.freeze()
            with self.assertRaises(ValueError):
                self.recognize([])
        self.body = pristine
        for options in ({'footer': False}, {'extra': [('node', {})]}):
            self.freeze(**options)
            with self.assertRaises(ValueError):
                self.recognize([])

    def test_missing_partial_unknown_and_text_control_escaping(self):
        controls = '\x01\x7f\x80\x85\u2028\u2029'
        source = (self.repo / 'calls.py').read_bytes().decode()
        source = source.replace('    return 1', '    return 1  # 한글 😀 ' + controls + r' literal\t')
        (self.repo / 'calls.py').write_bytes(source.encode('utf-8'))
        for kind, data in self.body:
            if kind == 'node':
                data.pop('partial')
                data['fidelity'] = 'heuristic'
                if data['id'] == self.ping:
                    data['name'] += controls
            elif kind == 'edge':
                data['evidence'] += controls
        self.freeze()
        for form in ('json', 'text'):
            event = self.event(form=form, budget=64000, actual_cli=True)
            result = self.recognize([event])
            self.assertTrue(result['relationship_used'])
            for control in controls:
                self.assertNotIn(control, event['item']['aggregated_output'])
            changed = deepcopy(event)
            changed['item']['aggregated_output'] = changed['item']['aggregated_output'].replace(r'\u0080', '\x80', 1)
            self.assertNotEqual(changed, event)
            self.rejected(changed)
        event = self.event(form='text', budget=64000)
        lines = event['item']['aggregated_output'].split('\n')
        file_number = next(number for number, line in enumerate(lines) if line.startswith('[0,"calls.py"'))
        lines[file_number] = lines[file_number].replace('[0,', '[9,', 1)
        event['item']['aggregated_output'] = '\n'.join(lines)
        self.rejected(event)

    def test_python_cookie_crlf_blank_and_empty_source(self):
        (self.repo / 'calls.py').write_bytes(b'# coding: latin-1\r\ndef outer():\r\n    return "caf\xe9"\r\n')
        self.body = [('node', self.node(self.outer, 'calls.py', 'outer', 2, 3))]
        self.freeze()
        self.assertEqual(self.recognize([self.event()])['source_call_receipts'][0]['source_rows'], 2)
        self.body[0][1].update(start_line=1, end_line=1)
        (self.repo / 'calls.py').write_bytes(b'\n')
        self.freeze()
        event = self.event()
        result = self.recognize([event])
        self.assertEqual(result['source_call_receipts'][0]['source_rows'], 1)
        self.assertFalse(result['relationship_used'])
        (self.repo / 'calls.py').write_bytes(b'')
        self.freeze()
        self.rejected(event)

    def test_bare_cr_heuristic_rejection_and_python_jvm_exemptions(self):
        event = self.event()
        for kind, data in self.body:
            if kind == 'node':
                data['language'] = 'javascript'
        (self.repo / 'calls.py').write_bytes((self.repo / 'calls.py').read_bytes().replace(b'\n', b'\r'))
        self.freeze()
        self.rejected(event)
        for kind, data in self.body:
            if kind == 'node':
                data['language'] = 'python'
        self.freeze()
        self.assertTrue(self.recognize([self.event()])['relationship_used'])
        for language in ('java', 'kotlin'):
            (self.repo / 'calls.py').write_bytes(b'function outer() {\r return 1;\r}\r')
            self.body = [('node', self.node(self.outer, 'calls.py', 'outer', 1, 1))]
            self.body[0][1]['language'] = language
            self.freeze()
            self.assertEqual(self.recognize([self.event()])['source_call_receipts'][0]['source_rows'], 1)

    def test_overloads_and_different_receivers_are_not_conflated(self):
        path = self.repo / 'Owner.kt'
        path.write_bytes(b'class Owner {\n fun run() { run(1) }\n fun run(x: Int) {}\n}\n')
        nodes = []
        for number, parameters in [(2, []), (3, ['Int'])]:
            node = self.node(f'Owner.kt::Owner.run({",".join(parameters)}):method', 'Owner.kt', 'run', number, number)
            node.update(kind='method', language='kotlin', qualname='Owner.run', parent_id='Owner.kt::Owner:class',
                        receiver_type='', local=False, parameter_types=parameters)
            nodes.append(node)
        self.body = [('node', node) for node in nodes]
        self.body.append(('edge', dict(source=nodes[0]['id'], target=nodes[1]['id'], path='Owner.kt', line=2,
                                       kind='calls', confidence='resolved_static', evidence='run(1)')))
        self.freeze()
        event = self.event(('Owner.run',), overloads=True)
        self.assertEqual(len(self.recognize([event])['source_call_receipts'][0]['target_ids']), 2)
        nodes[1]['receiver_type'] = 'String'
        self.freeze()
        self.rejected(event)

    def test_recognizer_import_and_api_do_not_execute_runtime_or_write(self):
        event = self.event()
        original_open = Path.open
        def read_only_open(path, mode='r', *args, **kwargs):
            self.assertFalse(any(flag in mode for flag in 'wax+'), mode)
            return original_open(path, mode, *args, **kwargs)
        with patch('subprocess.Popen', side_effect=AssertionError('process execution')), \
             patch('os.system', side_effect=AssertionError('shell execution')), \
             patch('socket.socket', side_effect=AssertionError('network access')), \
             patch.object(Path, 'open', read_only_open):
            fresh_spec = importlib.util.spec_from_file_location('source_call_no_effect_import', SPEC.origin)
            fresh = importlib.util.module_from_spec(fresh_spec)
            fresh_spec.loader.exec_module(fresh)
            self.assertTrue(fresh.evidence([event], binding=self.binding, relationships=self.reviewed)['relationship_used'])

    def test_input_change_during_recognition_is_not_swallowed_as_negative_evidence(self):
        event = self.event()
        path = self.repo / 'calls.py'
        before = path.read_bytes()
        render = EVIDENCE._render
        def changing_render(*args):
            result = render(*args)
            path.write_bytes(before + b'\n')
            return result
        with patch.object(EVIDENCE, '_render', side_effect=changing_render):
            with self.assertRaises(ValueError):
                self.recognize([event])

    def test_line_flood_is_order_independent_and_never_skips_the_next_line(self):
        edge = next(data for kind, data in self.body if kind == 'edge' and data['line'] == 4)
        self.body += [('edge', dict(edge, evidence=f'flood-{number}:' + 'x' * 300)) for number in range(35)]
        # Scalar unresolved-reference counts deliberately do not hydrate owners.
        self.body.append(('reference', dict(source='calls.py::unknown_owner:function', path='calls.py',
                                           line=6, kind='calls', name='unknown', resolved=False)))
        self.freeze()
        before = self.event(budget=6000)
        first = self.recognize([before])['source_call_receipts'][0]
        self.assertEqual(first['next_offset'], 3)
        self.body.reverse()
        self.freeze()
        after = self.event(budget=6000)
        self.assertEqual(before['item']['aggregated_output'], after['item']['aggregated_output'])
        self.assertEqual(self.recognize([after])['source_call_receipts'][0]['next_offset'], 3)
        words = shlex.split(after['item']['command'])
        words[words.index('--offset') + 1] = '3'
        after['item']['command'] = shlex.join(words)
        self.rejected(after)
        actual = subprocess.run(words, cwd=self.repo, capture_output=True, check=False)
        self.assertEqual(actual.returncode, 2)
        self.assertEqual(actual.stdout, b'')
        unresolved = self.recognize([self.event(offset=5, limit=1)])['source_call_receipts'][0]
        self.assertEqual(unresolved['unresolved_call_reference_count'], 2)

    def test_spaces_unicode_hash_paths_and_exact_id_actual_cli(self):
        new_path = 'code 한글 #.py'
        (self.repo / 'calls.py').rename(self.repo / new_path)
        for kind, data in self.body:
            for key in ('id', 'source', 'target'):
                if isinstance(data.get(key), str):
                    data[key] = data[key].replace('calls.py::', new_path + '::')
            if data.get('path') == 'calls.py':
                data['path'] = new_path
        for relationship in self.reviewed:
            relationship['path'] = new_path
            relationship['source'] = relationship['source'].replace('calls.py::', new_path + '::')
        self.freeze()
        for form in ('json', 'text'):
            event = self.event((new_path + '::outer:function',), form=form, actual_cli=True)
            self.assertTrue(self.recognize([event])['relationship_used'])

    def test_symlink_and_special_file_inventories_fail_without_opening_them(self):
        link = self.repo / 'linked.py'
        try:
            link.symlink_to(self.repo / 'calls.py')
        except (OSError, NotImplementedError):
            pass  # Windows may deny symlink creation; the special-file mock below is portable.
        else:
            try:
                self.binding['source_manifest']['linked.py'] = sha((self.repo / 'calls.py').read_bytes())
                with self.assertRaises(ValueError):
                    self.recognize([])
            finally:
                link.unlink()
                self.binding['source_manifest'].pop('linked.py')
        special = self.repo / 'fifo-like'
        special.write_bytes(b'not opened')
        special = special.resolve()
        self.binding['source_manifest'] = inventory(self.repo)
        original_stat, original_open = Path.lstat, Path.open
        def fifo_stat(path, *args, **kwargs):
            return SimpleNamespace(st_mode=stat.S_IFIFO) if path == special else original_stat(path, *args, **kwargs)
        def no_special_open(path, *args, **kwargs):
            self.assertNotEqual(path, special)
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'lstat', fifo_stat), patch.object(Path, 'open', no_special_open):
            with self.assertRaises(ValueError):
                self.recognize([])

    def test_corrupt_deflate_and_duplicate_archive_keys_fail_preflight(self):
        payloads = [bytes.fromhex('1f8b08000000000002ff07') + b'\0' * 8,
                    gzip.compress(b'{"record":"manifest","record":"manifest","data":{}}\n', mtime=0)]
        for raw in payloads:
            self.graph.write_bytes(raw)
            self.binding['archive_sha256'] = sha(raw)
            with self.assertRaises(ValueError):
                self.recognize([])

    def test_frozen_control_runtime_without_feature_cannot_get_candidate_credit(self):
        event = self.event()
        path = self.runtime / 'columbus/source_calls.py'
        before = path.read_bytes()
        try:
            path.unlink()
            self.binding['runtime_inventory'].pop('columbus/source_calls.py')
            self.rejected(event)
        finally:
            path.write_bytes(before)

    def test_archive_disappearance_at_postflight_raises_frozen_input_error(self):
        event = self.event()
        render = EVIDENCE._render
        def disappearing_render(*args):
            result = render(*args)
            self.graph.unlink()
            return result
        with patch.object(EVIDENCE, '_render', side_effect=disappearing_render):
            with self.assertRaises(ValueError):
                self.recognize([event])


if __name__ == '__main__':
    unittest.main()
