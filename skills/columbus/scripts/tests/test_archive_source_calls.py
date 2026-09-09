"""Returned-source CALL evidence is complete within one shared rendered budget."""
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import json
import lzma
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from columbus.archive import _validated_rows, archive
from columbus.index import RepositoryIndex, compact
from columbus.source_calls import _Snapshot, source_calls_archive, source_calls_json, source_calls_text
from columbus.sync_state import read_stable


class ArchiveSourceCallsTests(unittest.TestCase):
    outer = 'calls.py::outer:function'
    inner = 'calls.py::outer.inner:function'
    tail = 'calls.py::tail:function'
    ping = 'external.py::ping:function'

    @staticmethod
    def _node(node_id, path, name, start, end, **extra):
        return dict(id=node_id, path=path, name=name, qualname=name, kind='function',
                    start_line=start, end_line=end, language='python', fidelity='ast',
                    partial=False, module=Path(path).stem, **extra)

    @staticmethod
    def _rows(packet):
        return [(block['path'], number, line)
                for block in packet['sources']
                for number, line in enumerate(block['source'].split('\n'), block['start_line'])]

    @staticmethod
    def _edges(edges):
        # Stored duplicate edge rows are evidence too; do not reduce to a set.
        return Counter(compact(edge) for edge in edges)

    @staticmethod
    def _render(packet, fmt):
        return source_calls_text(packet) if fmt == 'text' else source_calls_json(packet)

    def _fixture(self, root):
        content = ('def outer():\n'
                   '    ping()\n'
                   '    def inner():\n'
                   '        ping(); ping()\n'
                   '        inner()\n'
                   '    missing()\n'
                   '    inner()\n'
                   '    return 1\n'
                   '\n'
                   'def tail(): return 2\n')
        (root / 'calls.py').write_text(content, encoding='utf-8')
        (root / 'external.py').write_text('def ping(): pass\n', encoding='utf-8')
        files = [dict(path=path, hash=hashlib.sha256((root / path).read_bytes()).hexdigest(),
                      size=(root / path).stat().st_size)
                 for path in ('calls.py', 'external.py')]
        nodes = [self._node(self.outer, 'calls.py', 'outer', 1, 8),
                 self._node(self.inner, 'calls.py', 'outer.inner', 3, 5),
                 self._node(self.tail, 'calls.py', 'tail', 10, 10),
                 self._node(self.ping, 'external.py', 'ping', 1, 1)]
        edges = [dict(source=owner, target=target, path='calls.py', line=line,
                      kind='calls', confidence=confidence, evidence=evidence)
                 for owner, target, line, confidence, evidence in (
                     (self.outer, self.ping, 2, 'resolved_static', 'callee:2:4-2:8'),
                     (self.inner, self.ping, 4, 'heuristic', 'callee:4:8-4:12'),
                     (self.inner, self.ping, 4, 'syntactic', 'callee:4:16-4:20'),
                     (self.inner, self.inner, 5, 'resolved_static', 'callee:5:8-5:13'),
                     (self.outer, self.inner, 7, 'resolved_static', 'callee:7:4-7:9'))]
        references = [dict(source=edge['source'], path=edge['path'], line=edge['line'],
                           kind='calls', name='callee', resolved=True,
                           evidence=edge['evidence']) for edge in edges]
        references += [dict(source=self.outer, path='calls.py', line=6, kind='calls',
                            name='missing', resolved=False, evidence='callee:6:4-6:11')]
        return ([dict(record='file', data=data) for data in files]
                + [dict(record='node', data=data) for data in nodes]
                + [dict(record='edge', data=data) for data in edges]
                + [dict(record='reference', data=data) for data in references])

    @staticmethod
    def _write(root, body, codec='gzip', name='graph', footer=True, extra=()):
        counts = dict(files=0, nodes=0, scopes=0, edges=0, references=0, imports=0,
                      diagnostics=0)
        plural = {'file': 'files', 'node': 'nodes', 'scope': 'scopes', 'edge': 'edges',
                  'reference': 'references', 'import': 'imports', 'diagnostic': 'diagnostics'}
        for row in body:
            counts[plural[row['record']]] += 1
        rows = [dict(record='manifest', data=dict(format='columbus-graph', version=1,
                    revision='source-calls-test', semantic_complete=False,
                    source_bodies_included=False))] + body
        if footer:
            rows.append(dict(record='end', data=counts))
        rows.extend(extra)
        destination = root / (name + '.' + codec)
        opener = gzip.open if codec == 'gzip' else lzma.open
        with opener(destination, 'wt', encoding='utf-8') as stream:
            stream.write(''.join(compact(row) + '\n' for row in rows))
        return destination

    def test_nested_same_line_recursive_and_duplicate_stored_edges_are_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = self._fixture(root)
            duplicate = deepcopy(next(row for row in body if row['record'] == 'edge'))
            body.append(duplicate)
            expected = [row['data'] for row in body if row['record'] == 'edge']
            for codec in ('gzip', 'xz'):
                with self.subTest(codec=codec):
                    artifact = self._write(root, body, codec)
                    packet = source_calls_archive(artifact, ['outer'], root, budget_bytes=64000)
                    calls = packet['call_sites']
                    self.assertEqual(self._edges(calls['edges']), self._edges(expected))
                    self.assertEqual(calls['scope'], 'returned_source')
                    self.assertIs(calls['stored_call_sites_complete'], True)
                    self.assertIs(calls['semantic_complete'], False)
                    self.assertIs(packet['semantic_complete'], False)
                    self.assertEqual(calls['unresolved_call_reference_count'], 1)
                    self.assertEqual(calls['resolved_call_reference_count'], 5)
                    self.assertIn('target_freshness', calls)
                    nodes = {node['id']: node for node in calls['nodes']}
                    self.assertEqual(set(nodes), {self.outer, self.inner, self.ping})
                    self.assertEqual(len(nodes), len(calls['nodes']))
                    for node in nodes.values():
                        original = next(row['data'] for row in body if row['record'] == 'node'
                                        and row['data']['id'] == node['id'])
                        for key in ('path', 'name', 'kind', 'start_line', 'end_line',
                                    'language', 'fidelity', 'partial'):
                            self.assertEqual(node[key], original[key])
                        self.assertEqual(node['source_hash'], hashlib.sha256(
                            (root / node['path']).read_bytes()).hexdigest())
                        self.assertIn('source_status', node)
                    for edge in calls['edges']:
                        self.assertNotIn('source_text', edge)
                        self.assertNotIn('source_body', edge)
                    self.assertNotEqual(nodes[self.outer]['source_status'], nodes[self.ping]['source_status'])

    def test_absent_legacy_partial_metadata_remains_unknown_not_false(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = self._fixture(root)
            for row in body:
                if row['record'] == 'node':
                    row['data'].pop('partial')
                    row['data']['fidelity'] = 'heuristic'
            artifact = self._write(root, body)
            packet = source_calls_archive(artifact, ['outer'], root, budget_bytes=64000)
            for node in packet['targets'] + packet['call_sites']['nodes']:
                self.assertIsNone(node['partial'])
                self.assertEqual(node['fidelity'], 'heuristic')
            self.assertFalse(packet['semantic_complete'])
            self.assertTrue(packet['call_sites']['stored_call_sites_complete'])
            self.assertEqual(len(packet['call_sites']['edges']), 5)

    def test_pages_cover_merged_source_union_once_and_match_exact_physical_sites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = self._fixture(root)
            expected_edges = [row['data'] for row in body if row['record'] == 'edge']
            for codec in ('gzip', 'xz'):
                artifact = self._write(root, body, codec)
                queries = ['tail', 'outer.inner', 'outer', 'calls.outer']
                complete = source_calls_archive(artifact, queries, root, budget_bytes=64000)
                expected_rows = self._rows(complete)
                self.assertEqual(len(complete['targets']), 3)
                self.assertEqual(complete['total_lines'], 9)
                for fmt in ('json', 'text'):
                    recovered, recovered_edges, offset = [], [], 0
                    while True:
                        page = source_calls_archive(artifact, queries, root, limit=2,
                                                    offset=offset, budget_bytes=64000,
                                                    output_format=fmt)
                        rows = self._rows(page)
                        self.assertTrue(1 <= len(rows) <= 2)
                        locations = {(path, line) for path, line, _ in rows}
                        wanted = [edge for edge in expected_edges
                                  if (edge['path'], edge['line']) in locations]
                        self.assertEqual(self._edges(page['call_sites']['edges']), self._edges(wanted))
                        self.assertEqual(page['call_sites']['unresolved_call_reference_count'],
                                         int(('calls.py', 6) in locations))
                        self.assertEqual(page['call_sites']['resolved_call_reference_count'], len(wanted))
                        self.assertLessEqual(len(self._render(page, fmt).encode('utf-8')), 64000)
                        self.assertEqual(page['offset'], offset)
                        recovered.extend(rows)
                        recovered_edges.extend(page['call_sites']['edges'])
                        self.assertEqual(page['total_lines'], len(expected_rows))
                        offset = page['next_offset']
                        if offset is None:
                            break
                        self.assertEqual(offset, len(recovered))
                    self.assertEqual(recovered, expected_rows)
                    self.assertEqual(len({(path, line) for path, line, _ in recovered}), len(recovered))
                    self.assertEqual(self._edges(recovered_edges), self._edges(expected_edges))

    def test_target_only_source_is_not_read_and_selected_file_is_read_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = self._fixture(root)
            artifact = self._write(root, body)
            (root / 'external.py').unlink()
            with patch('columbus.source_calls.read_stable', wraps=read_stable) as reads:
                packet = source_calls_archive(artifact, ['outer', 'outer.inner', 'calls.outer'],
                                              root, budget_bytes=64000)
            self.assertEqual([call.args[1] for call in reads.call_args_list], ['calls.py'])
            self.assertEqual(len(packet['targets']), 2)
            self.assertIn(self.ping, {node['id'] for node in packet['call_sites']['nodes']})

    def test_empty_call_page_and_unresolved_only_page_remain_explicitly_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._write(root, self._fixture(root))
            for query, offset, unresolved in [('tail', 0, 0), ('outer', 5, 1)]:
                packet = source_calls_archive(artifact, [query], root, limit=1, offset=offset)
                self.assertEqual(packet['call_sites']['edges'], [])
                self.assertEqual(packet['call_sites']['nodes'], [])
                self.assertEqual(packet['call_sites']['unresolved_call_reference_count'], unresolved)
                self.assertEqual(packet['call_sites']['resolved_call_reference_count'], 0)
                self.assertFalse(packet['semantic_complete'])
                self.assertTrue(packet['call_sites']['stored_call_sites_complete'])

    def test_shared_utf8_and_text_control_budget_only_shrinks_source_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = self._fixture(root)
            source = (root / 'calls.py').read_text(encoding='utf-8').splitlines()
            source[1] += '  # 한글 😀\x01\x85'
            source[7] += '  # ' + '한글 😀\x1b' * 2000
            (root / 'calls.py').write_text('\n'.join(source) + '\n', encoding='utf-8')
            for row in body:
                if row['record'] == 'file' and row['data']['path'] == 'calls.py':
                    row['data'].update(hash=hashlib.sha256((root / 'calls.py').read_bytes()).hexdigest(),
                                       size=(root / 'calls.py').stat().st_size)
                elif row['record'] == 'edge':
                    row['data']['evidence'] += ' 한글 😀\x01\x85'
            artifact = self._write(root, body)
            for fmt in ('json', 'text'):
                first = source_calls_archive(artifact, ['outer'], root, limit=1,
                                             budget_bytes=64000, output_format=fmt)
                budget = max(2048, len(self._render(first, fmt).encode('utf-8')) + 5000)
                packet = source_calls_archive(artifact, ['outer'], root, limit=8,
                                              budget_bytes=budget, output_format=fmt)
                rendered = self._render(packet, fmt)
                self.assertLessEqual(len(rendered.encode('utf-8')), budget)
                self.assertLess(packet['next_offset'], 8)
                rows = self._rows(packet)
                self.assertEqual([line for _, line, _ in rows], list(range(1, len(rows) + 1)))
                sites = {(path, line) for path, line, _ in rows}
                expected = [row['data'] for row in body if row['record'] == 'edge'
                            and (row['data']['path'], row['data']['line']) in sites]
                self.assertEqual(self._edges(packet['call_sites']['edges']), self._edges(expected))
                self.assertEqual(packet['next_offset'], len(rows))
                if fmt == 'text':
                    self.assertNotIn('\x01', rendered)
                    self.assertNotIn('\x85', rendered)
                    self.assertNotIn('\x1b', rendered)

    def test_one_line_with_all_stored_calls_must_fit_without_edge_truncation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = self._fixture(root)
            template = next(row for row in body if row['record'] == 'edge')
            body += [dict(record='edge', data={**template['data'], 'line': 4,
                        'source': self.inner, 'evidence': str(number) + ':' + 'x' * 300})
                     for number in range(100)]
            for codec in ('gzip', 'xz'):
                artifact = self._write(root, body, codec)
                reverse = self._write(root, list(reversed(body)), codec, 'reverse')
                for fmt in ('json', 'text'):
                    first = source_calls_archive(artifact, ['outer'], root, limit=8,
                                                 budget_bytes=6000, output_format=fmt)
                    self.assertEqual(first['next_offset'], 3)
                    self.assertEqual(self._rows(first)[-1][1], 3)
                    self.assertEqual(source_calls_archive(reverse, ['outer'], root, limit=8,
                                     budget_bytes=6000, output_format=fmt), first)
                    for path in (artifact, reverse):
                        with self.assertRaisesRegex(ValueError, '[Bb]udget|one source line'):
                            source_calls_archive(path, ['outer'], root, offset=3,
                                                 budget_bytes=6000, output_format=fmt)

    def test_oversized_endpoint_metadata_cannot_hide_a_line_or_overflow_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = self._fixture(root)
            for row in body:
                if row['record'] == 'node' and row['data']['id'] == self.ping:
                    row['data']['name'] = 'giant_' + 'x' * 20000
            for rows in (body, list(reversed(body))):
                artifact = self._write(root, rows)
                packet = source_calls_archive(artifact, ['outer'], root, budget_bytes=6000)
                self.assertEqual(packet['next_offset'], 1)
                self.assertEqual(packet['call_sites']['edges'], [])
                self.assertLessEqual(len(self._render(packet, 'json').encode()), 6000)
                with self.assertRaisesRegex(ValueError, '[Bb]udget|one source line'):
                    source_calls_archive(artifact, ['outer'], root, offset=1, budget_bytes=6000)

    def test_late_footer_errors_are_not_hidden_by_limits_or_floods(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = self._fixture(root)
            body.append(dict(record='edge', data=dict(source=self.inner, target=self.ping,
                path='calls.py', line=4, kind='calls', confidence='resolved_static', evidence='x' * 20000)))
            for codec in ('gzip', 'xz'):
                for footer, extra in ((False, ()), (True, (dict(record='node', data={}),))):
                    artifact = self._write(root, body, codec, footer=footer, extra=extra)
                    for offset, limit in ((0, 1), (0, 8), (3, 5)):
                        with patch('columbus.source_calls.read_stable', wraps=read_stable) as reads:
                            with self.assertRaises(ValueError):
                                source_calls_archive(artifact, ['outer'], root, limit=limit,
                                                     offset=offset, budget_bytes=6000)
                            self.assertEqual(reads.call_count, 0)

    def test_relevant_metadata_errors_precede_selected_source_reads(self):
        def change(body, kind, predicate, **updates):
            next(row['data'] for row in body if row['record'] == kind and predicate(row['data'])).update(updates)

        mutations = {
            'duplicate endpoint': lambda body: body.append(deepcopy(next(row for row in body
                if row['record'] == 'node' and row['data']['id'] == self.ping))),
            'missing target endpoint': lambda body: body.__setitem__(slice(None), [row for row in body
                if not (row['record'] == 'node' and row['data']['id'] == self.ping)]),
            'missing nested owner': lambda body: body.__setitem__(slice(None), [row for row in body
                if not (row['record'] == 'node' and row['data']['id'] == self.inner)]),
            'duplicate selected file': lambda body: body.append(deepcopy(next(row for row in body
                if row['record'] == 'file' and row['data']['path'] == 'calls.py'))),
            'missing target file': lambda body: body.__setitem__(slice(None), [row for row in body
                if not (row['record'] == 'file' and row['data']['path'] == 'external.py')]),
            'invalid selected hash': lambda body: change(body, 'file', lambda data: data['path'] == 'calls.py', hash='bad'),
            'invalid target hash': lambda body: change(body, 'file', lambda data: data['path'] == 'external.py', hash='bad'),
            'invalid target size': lambda body: change(body, 'file', lambda data: data['path'] == 'external.py', size=True),
            'conflicting selected file language': lambda body: change(body, 'node', lambda data: data['id'] == self.tail, language='java'),
            'missing target language': lambda body: change(body, 'node', lambda data: data['id'] == self.ping, language=None),
            'invalid endpoint partial flag': lambda body: change(body, 'node', lambda data: data['id'] == self.ping, partial='false'),
            'invalid explicit null partial flag': lambda body: change(body, 'node', lambda data: data['id'] == self.ping, partial=None),
            'invalid nested owner bounds': lambda body: change(body, 'node', lambda data: data['id'] == self.inner, end_line=2),
            'invalid selected bounds': lambda body: change(body, 'node', lambda data: data['id'] == self.outer, start_line=True),
            'owner path mismatch': lambda body: change(body, 'edge', lambda data: data['line'] == 2, source=self.ping),
            'call outside owner bounds': lambda body: change(body, 'edge', lambda data: data['line'] == 2, source=self.inner),
            'boolean call line': lambda body: change(body, 'edge', lambda data: data['line'] == 2, line=True),
            'invalid stored confidence type': lambda body: change(body, 'edge', lambda data: data['line'] == 2, confidence=1.0),
            'invalid resolved flag': lambda body: change(body, 'reference', lambda data: data['line'] == 6, resolved='false'),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pristine = self._fixture(root)
            for label, mutate in mutations.items():
                with self.subTest(label=label):
                    body = deepcopy(pristine)
                    mutate(body)
                    artifact = self._write(root, body)
                    with patch('columbus.source_calls.read_stable', wraps=read_stable) as reads:
                        with self.assertRaises(ValueError):
                            source_calls_archive(artifact, ['outer'], root, budget_bytes=64000)
                        self.assertEqual(reads.call_count, 0)

    def test_stale_selected_source_is_rejected_but_target_only_changes_are_unchecked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._write(root, self._fixture(root))
            (root / 'external.py').write_text('now entirely different\n')
            source_calls_archive(artifact, ['outer'], root, budget_bytes=64000)
            original = (root / 'calls.py').read_bytes()
            (root / 'calls.py').write_bytes(original + b'# changed\n')
            with self.assertRaisesRegex(ValueError, '[Ss]tale|hash|changed'):
                source_calls_archive(artifact, ['outer'], root, budget_bytes=64000)

    @staticmethod
    def _replace_open_archive(replacement, artifact, *, windows):
        """Record the actual mutation; Windows may forbid replacing an open file."""
        try:
            os.replace(replacement, artifact)
        except PermissionError:
            if not windows:
                raise
            # An OS refusal does not exercise the reader's snapshot guard.
            # Make a real, deterministic metadata change without a timing sleep.
            before = artifact.stat()
            changed_mtime = before.st_mtime_ns + 1_000_000_000
            os.utime(artifact, ns=(before.st_atime_ns, changed_mtime))
            if artifact.stat().st_mtime_ns != changed_mtime:
                raise AssertionError('Could not perform the explicit archive mtime mutation')
            return 'mtime-after-windows-replace-denial'
        return 'replacement'

    def _assert_archive_mutation_is_detected(self, *, force_windows_denial=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = self._fixture(root)
            for codec in ('gzip', 'xz'):
                for phase in ('scan', 'source'):
                    with self.subTest(codec=codec, phase=phase, forced_windows_denial=force_windows_denial):
                        artifact = self._write(root, body, codec)
                        before = artifact.stat()
                        replacement = root / 'replacement'
                        replacement.write_bytes(artifact.read_bytes())
                        os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
                        self.assertEqual(replacement.stat().st_size, before.st_size)
                        scans = 0
                        mutation_modes = []

                        def mutate_archive():
                            if force_windows_denial:
                                with patch.object(os, 'replace', side_effect=PermissionError('open archive denied')) as replace:
                                    mode = self._replace_open_archive(replacement, artifact, windows=True)
                                replace.assert_called_once_with(replacement, artifact)
                            else:
                                mode = self._replace_open_archive(replacement, artifact, windows=os.name == 'nt')
                            mutation_modes.append(mode)

                        def replacing_rows(raw):
                            nonlocal scans
                            scans += 1
                            yield from _validated_rows(raw)
                            if scans == 1:
                                mutate_archive()

                        def replacing_read(*args, **kwargs):
                            result = read_stable(*args, **kwargs)
                            mutate_archive()
                            return result

                        target = 'columbus.source_calls.' + ('_validated_rows' if phase == 'scan' else 'read_stable')
                        replacement_call = replacing_rows if phase == 'scan' else replacing_read
                        with patch(target, side_effect=replacement_call):
                            with self.assertRaisesRegex(ValueError, '[Aa]rchive changed|[Aa]rchive.*chang'):
                                source_calls_archive(artifact, ['outer'], root, budget_bytes=64000)
                        self.assertEqual(len(mutation_modes), 1)
                        if force_windows_denial:
                            self.assertEqual(mutation_modes, ['mtime-after-windows-replace-denial'])
                        elif os.name != 'nt':
                            # POSIX continues to exercise actual replacement of
                            # the open archive, never a metadata-only substitute.
                            self.assertEqual(mutation_modes, ['replacement'])
                        else:
                            self.assertIn(mutation_modes[0], ('replacement', 'mtime-after-windows-replace-denial'))

    def test_archive_replacement_between_passes_and_during_source_read_is_rejected(self):
        self._assert_archive_mutation_is_detected()

    def test_windows_denied_replacement_still_requires_reader_mutation_detection(self):
        self._assert_archive_mutation_is_detected(force_windows_denial=True)

    def test_non_windows_replacement_denial_is_not_hidden_by_fallback(self):
        with patch.object(os, 'replace', side_effect=PermissionError('unexpected denial')), \
             patch.object(os, 'utime') as touch:
            with self.assertRaises(PermissionError):
                self._replace_open_archive(Path('replacement'), Path('artifact'), windows=False)
        touch.assert_not_called()

    def test_all_validated_passes_reach_eof_and_record_order_does_not_change_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = self._fixture(root)
            for codec in ('gzip', 'xz'):
                artifact = self._write(root, body, codec)
                unordered = self._write(root, list(reversed(body)), codec, 'unordered')
                starts, ends = [], []

                def observing_rows(raw):
                    starts.append(raw)
                    yield from _validated_rows(raw)
                    ends.append(raw)

                with patch('columbus.source_calls._validated_rows', side_effect=observing_rows):
                    packet = source_calls_archive(artifact, ['outer'], root, limit=2,
                                                  budget_bytes=64000)
                self.assertGreaterEqual(len(starts), 2)
                self.assertEqual(starts, ends)
                self.assertEqual(len({id(raw) for raw in starts}), 1)
                self.assertEqual(source_calls_archive(unordered, ['outer'], root, limit=2,
                                 budget_bytes=64000), packet)

    def test_real_export_supports_relocated_sources_without_index_or_target_bodies(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as moved:
            root, consumer = Path(directory), Path(moved)
            (root / 'calls.py').write_text('def ping(): pass\ndef outer():\n'
                '    def inner():\n        ping(); ping()\n    inner()\n    missing()\n')
            (consumer / 'calls.py').write_bytes((root / 'calls.py').read_bytes())
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            packets = []
            for codec in ('gzip', 'xz'):
                artifact = consumer / ('graph.' + codec)
                archive(index, artifact, codec)
                with patch('columbus.source_calls.read_stable', wraps=read_stable) as reads:
                    packet = source_calls_archive(artifact, ['outer'], consumer, budget_bytes=64000)
                self.assertEqual([call.args[1] for call in reads.call_args_list], ['calls.py'])
                self.assertEqual({edge['line'] for edge in packet['call_sites']['edges']}, {4, 5})
                self.assertTrue(any(edge['source'] != packet['targets'][0]['id']
                                    for edge in packet['call_sites']['edges']))
                self.assertEqual(packet['call_sites']['unresolved_call_reference_count'], 1)
                self.assertFalse((consumer / '.columbus').exists())
                packets.append(packet)
            self.assertEqual(packets[0], packets[1])

    def test_query_aliases_precedence_and_strict_input_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = self._fixture(root)
            artifact = self._write(root, body)
            alias = source_calls_archive(artifact, ['outer', 'calls.outer', self.outer], root,
                                         budget_bytes=64000)
            self.assertEqual(len(alias['targets']), 1)
            for queries in ([], ['outer', 'outer'], ['x' * 2049], list(map(str, range(17))),
                            ['missing'], ['OUTER'], ['uter'], ['alls.outer']):
                with self.subTest(queries=queries):
                    with self.assertRaises(ValueError):
                        source_calls_archive(artifact, queries, root)
            for options in ({'limit': True}, {'limit': 0}, {'limit': 401}, {'offset': True},
                            {'offset': -1}, {'offset': 8}, {'budget_bytes': True},
                            {'budget_bytes': 2047}, {'budget_bytes': 64001},
                            {'output_format': 'yaml'}, {'overloads': 1}):
                with self.subTest(options=options):
                    with self.assertRaises(ValueError):
                        source_calls_archive(artifact, ['outer'], root, **options)
            body.append(dict(record='node', data=self._node('calls.py::other:function',
                             'calls.py', 'outer', 10, 10)))
            ambiguous = self._write(root, body, name='ambiguous')
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                source_calls_archive(ambiguous, ['outer'], root)
            exact = source_calls_archive(ambiguous, [self.outer], root, budget_bytes=64000)
            self.assertEqual(exact['targets'][0]['id'], self.outer)

    def test_overload_selection_preserves_edges_and_rejects_receiver_conflicts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = 'Owner.kt'
            source = ('class Owner {\n fun run() { run(1) }\n fun run(x: Int) {}\n'
                      ' fun run(x: String) {}\n}\n').encode()
            (root / path).write_bytes(source)
            nodes = []
            for line, parameters in ((2, []), (3, ['Int']), (4, ['String'])):
                node = self._node(f'{path}::Owner.run({",".join(parameters)}):method',
                                  path, 'run', line, line)
                node.update(kind='method', qualname='Owner.run', language='kotlin',
                            parent_id=f'{path}::Owner:class', receiver_type='',
                            local=False, parameter_types=parameters)
                nodes.append(node)
            edge = dict(source=nodes[0]['id'], target=nodes[1]['id'], path=path, line=2,
                        kind='calls', confidence='resolved_static', evidence='callee:2:13-2:16')
            body = [dict(record='file', data=dict(path=path, hash=hashlib.sha256(source).hexdigest(),
                                                 size=len(source)))]
            body += [dict(record='node', data=node) for node in nodes]
            body.append(dict(record='edge', data=edge))
            artifact = self._write(root, body)
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                source_calls_archive(artifact, ['Owner.run'], root)
            packet = source_calls_archive(artifact, ['Owner.run', nodes[0]['id']], root,
                                          overloads=True, budget_bytes=64000)
            self.assertEqual([target['id'] for target in packet['targets']],
                             [node['id'] for node in nodes])
            self.assertEqual(packet['total_lines'], 3)
            self.assertEqual(packet['call_sites']['edges'], [edge])
            self.assertIn('selection', packet)
            # Same spelling with a distinct receiver is a different family.
            nodes[-1]['receiver_type'] = 'String'
            artifact = self._write(root, body)
            with patch('columbus.source_calls.read_stable', wraps=read_stable) as reads:
                with self.assertRaisesRegex(ValueError, 'receiver'):
                    source_calls_archive(artifact, ['Owner.run'], root, overloads=True)
                self.assertEqual(reads.call_count, 0)

    def test_overload_and_total_declaration_caps_are_both_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = 'Owner.java'
            source = ('// declaration\n' * 65).encode()
            (root / path).write_bytes(source)
            files = [dict(record='file', data=dict(path=path, hash=hashlib.sha256(source).hexdigest(),
                                                  size=len(source)))]
            nodes = []
            for number in range(65):
                node = self._node(f'{path}::Owner.run(T{number}):method', path, 'run',
                                  number + 1, number + 1)
                node.update(kind='method', qualname='Owner.run', language='java',
                            parent_id=f'{path}::Owner:class', receiver_type='', local=False,
                            parameter_types=[f'T{number}'])
                nodes.append(dict(record='node', data=node))
            artifact = self._write(root, files + nodes[:64])
            packet = source_calls_archive(artifact, ['Owner.run'], root, overloads=True,
                                          budget_bytes=64000)
            self.assertEqual(len(packet['targets']), 64)
            self.assertEqual(packet['total_lines'], 64)
            artifact = self._write(root, files + nodes)
            with patch('columbus.source_calls.read_stable', wraps=read_stable) as reads:
                with self.assertRaises(ValueError):
                    source_calls_archive(artifact, ['Owner.run'], root, overloads=True,
                                         budget_bytes=64000)
                self.assertEqual(reads.call_count, 0)
            for row in nodes[32:]:
                row['data'].update(name='other', qualname='Owner.other')
            artifact = self._write(root, files + nodes)
            with patch('columbus.source_calls.read_stable', wraps=read_stable) as reads:
                with self.assertRaisesRegex(ValueError, '64'):
                    source_calls_archive(artifact, ['Owner.run', 'Owner.other'], root,
                                         overloads=True, budget_bytes=64000)
                self.assertEqual(reads.call_count, 0)

    def test_stored_language_decodes_nonstandard_extension_and_python_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = 'source.opaque'
            source = b'# coding: latin-1\r\ndef cafe():\r\n    return "caf\xe9"\r\n'
            (root / path).write_bytes(source)
            node = self._node(path + '::cafe:function', path, 'cafe', 2, 3)
            body = [dict(record='file', data=dict(path=path, hash=hashlib.sha256(source).hexdigest(),
                                                 size=len(source))), dict(record='node', data=node)]
            artifact = self._write(root, body)
            packet = source_calls_archive(artifact, ['cafe'], root)
            self.assertEqual(self._rows(packet), [(path, 2, 'def cafe():'),
                                                  (path, 3, '    return "café"')])
            self.assertEqual(packet['call_sites']['edges'], [])

    def test_non_call_edges_and_references_do_not_change_call_completeness(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = self._fixture(root)
            artifact = self._write(root, body)
            expected = source_calls_archive(artifact, ['outer'], root, budget_bytes=64000)
            body += [dict(record='edge', data=dict(kind='imports', source=self.outer,
                        target='absent.py::module', path='calls.py', line=2,
                        confidence='syntactic', evidence='not a call')),
                     dict(record='reference', data=dict(kind='reads', source=self.outer,
                        name='missing_variable', path='calls.py', line=6, resolved=False))]
            artifact = self._write(root, body)
            self.assertEqual(source_calls_archive(artifact, ['outer'], root, budget_bytes=64000), expected)

    def test_windows_snapshot_compares_ctime_within_each_api_not_across_apis(self):
        def stamp(ctime):
            return SimpleNamespace(st_dev=7, st_ino=11, st_size=101, st_mtime_ns=123456,
                                   st_ctime_ns=ctime, st_mode=stat.S_IFREG | 0o600)

        path_stamp, fd_stamp = stamp(101), stamp(202)
        source, raw = Mock(), Mock()
        source.stat.return_value = path_stamp
        raw.fileno.return_value = 17
        with patch('columbus.source_calls.WINDOWS', True), \
                patch('columbus.source_calls.os.fstat', return_value=fd_stamp) as fstat:
            snapshot = _Snapshot(source, raw, path_stamp)
            snapshot.check()
            source.stat.return_value = stamp(102)
            with self.assertRaisesRegex(ValueError, '[Aa]rchive changed'):
                snapshot.check()
            source.stat.return_value = path_stamp
            fstat.return_value = stamp(203)
            with self.assertRaisesRegex(ValueError, '[Aa]rchive changed'):
                snapshot.check()
        with patch('columbus.source_calls.WINDOWS', False), \
                patch('columbus.source_calls.os.fstat', return_value=fd_stamp):
            with self.assertRaisesRegex(ValueError, '[Aa]rchive changed'):
                _Snapshot(source, raw, path_stamp)

    def test_later_pass_eof_errors_are_not_hidden_after_a_line_flood(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = self._fixture(root)
            body.append(dict(record='edge', data=dict(source=self.inner, target=self.ping,
                path='calls.py', line=4, kind='calls', confidence='resolved_static', evidence='x' * 20000)))
            artifact = self._write(root, body)
            for fail_on_pass in (2, 3, 4):
                for offset in (0, 3):
                    with self.subTest(fail_on_pass=fail_on_pass, offset=offset):
                        passes = 0

                        def late_failure(raw):
                            nonlocal passes
                            passes += 1
                            yield from _validated_rows(raw)
                            if passes == fail_on_pass:
                                raise ValueError('Incomplete archive: injected late pass footer failure')

                        with patch('columbus.source_calls._validated_rows', side_effect=late_failure), \
                                patch('columbus.source_calls.read_stable', wraps=read_stable) as reads:
                            with self.assertRaisesRegex(ValueError, 'injected late pass footer failure'):
                                source_calls_archive(artifact, ['outer'], root, offset=offset,
                                                     budget_bytes=6000)
                            self.assertEqual(passes, fail_on_pass)
                            self.assertEqual(reads.call_count, 0)

    def test_json_controls_round_trip_and_exact_utf8_budget_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = self._fixture(root)
            controls = ''.join(chr(number) for number in range(0x7f, 0xa0)) + '\u2028\u2029'
            lines = (root / 'calls.py').read_text(encoding='utf-8').split('\n')
            lines[1] += '  # 한글 😀 ' + controls * 8
            (root / 'calls.py').write_text('\n'.join(lines), encoding='utf-8')
            for row in body:
                if row['record'] == 'file' and row['data']['path'] == 'calls.py':
                    row['data'].update(hash=hashlib.sha256((root / 'calls.py').read_bytes()).hexdigest(),
                                       size=(root / 'calls.py').stat().st_size)
                elif row['record'] == 'edge' and row['data']['line'] == 2:
                    row['data']['evidence'] += controls * 8
                elif row['record'] == 'node' and row['data']['id'] == self.ping:
                    row['data']['name'] += controls
            artifact = self._write(root, body)
            packet = source_calls_archive(artifact, ['outer'], root, limit=8, budget_bytes=64000)
            rendered = source_calls_json(packet)
            for control in controls:
                self.assertNotIn(control, rendered)
                self.assertIn(f'\\u{ord(control):04x}', rendered)
            self.assertEqual(json.loads(rendered), packet)
            exact_bytes = len(rendered.encode('utf-8'))
            self.assertGreater(exact_bytes, 2048)
            exact = source_calls_archive(artifact, ['outer'], root, limit=8,
                                         budget_bytes=exact_bytes)
            self.assertEqual(exact, packet)
            below = source_calls_archive(artifact, ['outer'], root, limit=8,
                                         budget_bytes=exact_bytes - 1)
            self.assertLessEqual(len(source_calls_json(below).encode('utf-8')), exact_bytes - 1)
            self.assertLess(len(self._rows(below)), len(self._rows(packet)))
            self.assertEqual(below['next_offset'], len(self._rows(below)))
            locations = {(path, line) for path, line, _ in self._rows(below)}
            wanted = [edge for edge in packet['call_sites']['edges']
                      if (edge['path'], edge['line']) in locations]
            self.assertEqual(self._edges(below['call_sites']['edges']), self._edges(wanted))

            one_line = source_calls_archive(artifact, ['outer'], root, limit=1, offset=1,
                                            budget_bytes=64000)
            one_line_bytes = len(source_calls_json(one_line).encode('utf-8'))
            self.assertGreater(one_line_bytes, 2048)
            self.assertEqual(source_calls_archive(artifact, ['outer'], root, limit=1, offset=1,
                             budget_bytes=one_line_bytes), one_line)
            with self.assertRaisesRegex(ValueError, '[Bb]udget|one source line'):
                source_calls_archive(artifact, ['outer'], root, limit=1, offset=1,
                                     budget_bytes=one_line_bytes - 1)


if __name__ == '__main__':
    unittest.main()
