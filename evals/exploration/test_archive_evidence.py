"""Deterministic receipt checks using actual archive packets; never launch a model."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'skills/columbus/scripts'))
from columbus.archive import archive, callers_archive, neighbors_archive, search_archive, source_archive, source_archive_many
from columbus.index import RepositoryIndex
from columbus.presentation import _line, render

spec = importlib.util.spec_from_file_location('archive_evidence', HERE / 'archive_evidence.py')
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


class ArchiveEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.observation = Path(cls.temporary.name)
        cls.repository = cls.observation / 'repository'
        cls.repository.mkdir()
        (cls.repository / 'source.py').write_text(
            'def target(value):\n    return value\n\n'
            'def caller():\n    result = target(1)\n    return result\n\n'
            'def other():\n    return "한글"\n', encoding='utf-8')
        (cls.repository / 'C.java').write_text(
            'package p;\nclass C {\n'
            '  int read() { return 1; }\n'
            '  int read(int x) { return x; }\n}\n', encoding='utf-8')
        index = RepositoryIndex(cls.observation / 'index.sqlite')
        index.refresh(cls.repository)
        cls.archive = cls.observation / 'graph.jsonl.xz'
        archive(index, cls.archive, 'xz')
        cls.single = source_archive(cls.archive, 'caller', cls.repository)
        cls.batch = source_archive_many(cls.archive, ['target', 'caller'], cls.repository)
        cls.overloads = source_archive_many(cls.archive, ['C.read'], cls.repository, overloads=True)
        cls.search = search_archive(cls.archive, 'target')
        cls.callers = callers_archive(cls.archive, 'target', repo=cls.repository, context_lines=1)
        cls.neighbors = neighbors_archive(cls.archive, cls.single['target'], 'out', ['calls'],
                                         repo=cls.repository, context_lines=1)
        cls.empty = callers_archive(cls.archive, 'other')

    def event(self, packet, operation='archive-source', fmt='text', output=None):
        if operation == 'archive-source':
            queries = [row['id'] for row in packet['targets']] if 'targets' in packet else [packet['target']]
        elif operation == 'archive-search':
            queries = [packet['query']]
        else:
            queries = [packet['symbol_id']]
        words = ['python3.12', str(self.observation / 'runtime/columbus.py'), operation, *queries,
                 '--input', str(self.archive), '--format', fmt]
        if operation != 'archive-search':
            words += ['--repo', str(self.repository)]
        return {'type': 'item.completed', 'item': {
            'id': 'command-1', 'type': 'command_execution', 'status': 'completed', 'exit_code': 0,
            'command': shlex.join(words),
            'aggregated_output': render(packet, fmt, operation) if output is None else output}}

    def receipts(self, event, paths=('source.py',), **kwargs):
        return evidence.graph_evidence([event], self.observation, set(paths), **kwargs)

    def useful(self, event, paths=('source.py',)):
        return any(row['useful_task_evidence'] for row in self.receipts(event, paths))

    @staticmethod
    def legacy_batch(packet):
        lines = [evidence.SOURCE_HEADER, 'metadata ' + json.dumps(
            {key: value for key, value in packet.items() if key != 'sources'}, ensure_ascii=True)]
        for block in packet['sources']:
            lines.append('source ' + json.dumps({key: value for key, value in block.items() if key != 'source'},
                                               ensure_ascii=True))
            lines.extend(f'{number}| {_line(source)}' for number, source in
                         enumerate(block['source'].split('\n'), block['start_line']))
        return '\n'.join(lines) + '\n'

    def test_real_packets_json_legacy_and_table_text(self):
        for operation, packet in [('archive-source', self.single), ('archive-source', self.batch),
                                  ('archive-search', self.search), ('archive-callers', self.callers),
                                  ('archive-neighbors', self.neighbors)]:
            for fmt in ('json', 'text'):
                with self.subTest(operation=operation, fmt=fmt, batch='targets' in packet):
                    event = self.event(packet, operation, fmt)
                    receipt, = self.receipts(event)
                    self.assertTrue(receipt['useful_task_evidence'])
                    self.assertEqual(receipt['batch_used'], operation == 'archive-source' and 'targets' in packet)
                    self.assertEqual(receipt['recognizer_version'], 'archive-evidence-v1')
                    self.assertEqual(receipt['relevant_paths'], ['source.py'])
                    self.assertEqual(receipt['output_sha256'], hashlib.sha256(
                        event['item']['aggregated_output'].encode()).hexdigest())
                    self.assertNotIn('return value', json.dumps(receipt))
        event = self.event(self.batch, output=self.legacy_batch(self.batch))
        receipt, = self.receipts(event)
        self.assertTrue(receipt['batch_used'])
        self.assertEqual(receipt['encoding'], 'source-text-v1')

    def test_same_owner_overload_group_and_later_pages_count(self):
        self.assertEqual(len(self.overloads['targets']), 2)
        self.assertIn('not runtime dispatch', self.overloads['selection'])
        for fmt in ('json', 'text'):
            for offset in (0, 1):
                packet = source_archive_many(self.archive, ['C.read'], self.repository, overloads=True,
                                             limit=1, offset=offset, output_format=fmt)
                event = self.event(packet, fmt=fmt)
                words = shlex.split(event['item']['command'])
                event['item']['command'] = shlex.join(words[:3] + ['C.read', '--overloads'] + words[5:])
                receipt, = self.receipts(event, ('C.java',))
                self.assertTrue(receipt['useful_task_evidence'])
                self.assertTrue(receipt['batch_used'])
                self.assertEqual(receipt['source_rows'], 1)
                self.assertEqual(receipt['declarations'], 2)

    def test_unrelated_paths_do_not_count(self):
        for operation, packet in [('archive-source', self.single), ('archive-source', self.batch),
                                  ('archive-search', self.search), ('archive-callers', self.callers),
                                  ('archive-neighbors', self.neighbors)]:
            for fmt in ('json', 'text'):
                with self.subTest(operation=operation, fmt=fmt):
                    receipt, = self.receipts(self.event(packet, operation, fmt), ('unrelated.py',))
                    self.assertFalse(receipt['useful_task_evidence'])
                    self.assertFalse(receipt['batch_used'])
                    self.assertEqual(receipt['relevant_paths'], [])

    def test_empty_outputs_and_offered_commands_never_count(self):
        event = self.event(self.batch)
        for output in ('', ' ', 'Use archive-source to read source.py', evidence.SOURCE_HEADER + '\n',
                       '{}', 'metadata ' + json.dumps(self.batch)):
            with self.subTest(output=output[:30]):
                changed = copy.deepcopy(event)
                changed['item']['aggregated_output'] = output
                self.assertEqual(self.receipts(changed), [])
        for operation, packet in [('archive-callers', self.empty),
                                  ('archive-search', search_archive(self.archive, 'absent'))]:
            for fmt in ('json', 'text'):
                receipt, = self.receipts(self.event(packet, operation, fmt))
                self.assertFalse(receipt['useful_task_evidence'])
        for packet in (self.single, self.batch):
            blank = copy.deepcopy(packet)
            for block in blank.get('sources', [blank]):
                block['source'] = '\n'.join(' \t\r' for _ in block['source'].split('\n'))
            for fmt in ('json', 'text'):
                receipt, = self.receipts(self.event(blank, fmt=fmt))
                self.assertFalse(receipt['useful_task_evidence'])
        metadata_only = copy.deepcopy(self.batch)
        metadata_only.update(sources=[], next_offset=0, truncated=True)
        self.assertFalse(self.useful(self.event(metadata_only)))
        self.assertFalse(self.useful(self.event(metadata_only, output=self.legacy_batch(metadata_only))))

    def test_completion_and_frozen_command_provenance_are_required(self):
        event = self.event(self.batch)
        for update in ({'exit_code': 1}, {'exit_code': False}, {'exit_code': None},
                       {'status': 'failed'}, {'status': 'in_progress'}, {'type': 'agent_message'}):
            changed = copy.deepcopy(event)
            changed['item'].update(update)
            self.assertEqual(self.receipts(changed), [])
        changed = dict(event, type='item.started')
        self.assertEqual(self.receipts(changed), [])
        command = event['item']['command']
        invalid = [command.replace('/runtime/columbus.py', '/other/columbus.py'),
                   command.replace('graph.jsonl.xz', 'wrong.jsonl.xz'),
                   command.replace(str(self.repository), str(self.observation / 'elsewhere')),
                   'echo ' + shlex.quote(command), 'python -c ' + shlex.quote(command),
                   command + '; true', command + ' | cat', command + ' && echo offered',
                   command + ' --input ' + str(self.archive),
                   command + ' --input=' + str(self.archive),
                   command + ' --inp /tmp/other.jsonl.xz',
                   command + ' --rep /tmp/elsewhere',
                   command.replace('--input ' + str(self.archive),
                                   '--inp /tmp/other.jsonl.xz # --input ' + str(self.archive)),
                   command.replace('python3.12 ', 'python-spoof ', 1)]
        for command in invalid:
            with self.subTest(command=command):
                changed = copy.deepcopy(event)
                changed['item']['command'] = command
                self.assertEqual(self.receipts(changed), [])
        for shell in ('/bin/zsh', '/bin/bash', '/bin/sh'):
            changed = copy.deepcopy(event)
            changed['item']['command'] = shlex.join([shell, '-lc', event['item']['command']])
            self.assertTrue(self.useful(changed))
        changed = copy.deepcopy(event)
        words = shlex.split(event['item']['command'])
        position = words.index('--repo')
        repo_option = words[position:position + 2]
        remaining = words[:position] + words[position + 2:]
        changed['item']['command'] = shlex.join(remaining[:2] + repo_option + remaining[2:])
        self.assertTrue(self.useful(changed))
        changed = copy.deepcopy(event)
        changed['item']['command'] = event['item']['command'].replace(str(self.repository), '.')
        self.assertTrue(self.useful(changed))
        changed['item']['command'] = event['item']['command'].replace(str(self.repository), '..')
        self.assertEqual(self.receipts(changed), [])
        changed = copy.deepcopy(event)
        changed['item']['command'] = event['item']['command'].replace('--input ', '--input=', 1)
        self.assertTrue(self.useful(changed))
        changed['item']['command'] = changed['item']['command'].replace('graph.jsonl.xz', 'custom.xz')
        self.assertEqual(self.receipts(changed), [])
        self.assertTrue(self.receipts(changed, archive_path=self.observation / 'custom.xz')[0]['useful_task_evidence'])

    def test_source_table_missing_duplicate_or_unrelated_file_references_fail(self):
        output = render(self.batch, 'text', 'archive-source')
        lines = output.splitlines()
        file_row = lines[lines.index(evidence.SOURCE_FILES) + 1]
        target_row = lines[lines.index(evidence.TARGETS) + 1]
        source_row = next(line for line in lines if line.startswith('source '))
        target = json.loads(target_row)
        block = json.loads(source_row[7:])
        mutations = [output.replace(file_row + '\n', '', 1),
                     output.replace(file_row + '\n', file_row + '\n' + file_row + '\n', 1),
                     output.replace(target_row, json.dumps([99, target[1]]), 1),
                     output.replace(source_row, 'source ' + json.dumps(dict(block, file_number=99)), 1),
                     output.replace(source_row, 'source ' + json.dumps({key: value for key, value in block.items()
                                                                      if key != 'file_number'}), 1),
                     output.replace(target_row, json.dumps([target[0], dict(target[1], path='unrelated.py')]), 1),
                     output.replace(file_row, '[0,"unrelated.py","hash"]', 1),
                     output.replace(file_row, file_row + '\n[99,"unrelated.py","hash"]', 1),
                     output.replace(file_row, file_row.replace('[0,', '[true,', 1), 1)]
        for mutated in mutations:
            with self.subTest(output=mutated[:120]):
                self.assertEqual(self.receipts(self.event(self.batch, output=mutated)), [])

    def test_source_ranges_hashes_ids_and_physical_rows_must_agree(self):
        for fmt in ('json', 'text'):
            for change in ('path', 'hash', 'id', 'range', 'offset', 'total', 'next', 'truncated', 'duplicate'):
                packet = copy.deepcopy(self.batch)
                if change == 'path':
                    packet['sources'][0]['path'] = 'unrelated.py'
                elif change == 'hash':
                    packet['sources'][0]['source_hash'] = 'different-hash'
                elif change == 'id':
                    packet['targets'][0]['id'] = 'unrelated.py::target:function'
                elif change == 'range':
                    packet['sources'][0]['start_line'] += 1
                    packet['sources'][0]['end_line'] += 1
                elif change == 'offset':
                    packet['offset'] += 1
                elif change == 'total':
                    packet['total_lines'] += 1
                elif change == 'next':
                    packet['next_offset'] = 1
                elif change == 'truncated':
                    packet['truncated'] = True
                elif change == 'duplicate':
                    packet['targets'].append(packet['targets'][0])
                with self.subTest(fmt=fmt, change=change):
                    self.assertEqual(self.receipts(self.event(packet, fmt=fmt)), [])
        output = render(self.single, 'text', 'archive-source')
        for mutated in (output.replace('4| ', '40| ', 1), output.replace('4| def caller():\n', '', 1),
                        output + '7| offered source\n'):
            self.assertEqual(self.receipts(self.event(self.single, output=mutated)), [])

    def test_legacy_source_controls_are_data_and_cannot_inject_metadata(self):
        for original in (self.single, self.batch):
            packet = copy.deepcopy(original)
            block = packet.get('sources', [packet])[0]
            rows = block['source'].split('\n')
            rows[0] = '    # 한글\t\x1b[31m\r\u2028\u2029 source {"path":"unrelated.py"}'
            block['source'] = '\n'.join(rows)
            packet['revision'] = 'revision\nsource {"path":"unrelated.py"}\x1b'
            outputs = [render(packet, 'text', 'archive-source')]
            if 'sources' in packet:
                outputs.append(self.legacy_batch(packet))
            for output in outputs:
                self.assertNotIn('\x1b', output)
                receipt, = self.receipts(self.event(packet, output=output))
                self.assertTrue(receipt['useful_task_evidence'])
                self.assertFalse(self.useful(self.event(packet, output=output), ('unrelated.py',)))

    def test_neighbor_tables_need_connected_edges_and_verified_context_relationships(self):
        output = render(self.callers, 'text', 'archive-callers')
        lines = output.splitlines()
        file_row = lines[lines.index(evidence.FILES) + 1]
        node_row = lines[lines.index(evidence.NODES) + 1]
        edge_row = lines[lines.index(evidence.EDGES) + 1]
        context_row = lines[lines.index(evidence.CONTEXT) + 1]
        node, edge, context = json.loads(node_row), json.loads(edge_row), json.loads(context_row)
        mutations = [output.replace(file_row + '\n', '', 1),
                     output.replace(node_row, json.dumps([node[0], 99, node[2]]), 1),
                     output.replace(edge_row, json.dumps([99, *edge[1:]]), 1),
                     output.replace(edge_row, json.dumps([*edge[:2], 99, edge[3]]), 1),
                     output.replace(edge_row + '\n', '', 1),
                     output.replace(context_row, json.dumps(dict(context, source_node=99)), 1),
                     output.replace(context_row, json.dumps(dict(context, file_number=99)), 1),
                     output.replace(file_row, file_row + '\n[99,"source.py","wrong-hash"]', 1)
                           .replace(edge_row, json.dumps([*edge[:2], 99, edge[3]]), 1),
                     output.replace(file_row, file_row + '\n[99,"unrelated.py","hash"]', 1)]
        for mutated in mutations:
            self.assertEqual(self.receipts(self.event(self.callers, 'archive-callers', output=mutated)), [])
        for fmt in ('json', 'text'):
            for change in ('path', 'line', 'target', 'context_owner', 'context_hash', 'call_lines', 'empty_edges'):
                packet = copy.deepcopy(self.callers)
                if change == 'path':
                    packet['edges'][0]['path'] = 'unrelated.py'
                elif change == 'line':
                    packet['edges'][0]['line'] = 999
                elif change == 'target':
                    packet['edges'][0]['target'] = packet['edges'][0]['source']
                elif change == 'context_owner':
                    packet['call_context'][0]['source_id'] = packet['symbol_id']
                elif change == 'context_hash':
                    packet['call_context'][0]['source_hash'] = 'wrong-hash'
                elif change == 'call_lines':
                    packet['call_context'][0]['call_lines'] = [999]
                elif change == 'empty_edges':
                    packet['edges'] = []
                with self.subTest(fmt=fmt, change=change):
                    self.assertEqual(self.receipts(self.event(packet, 'archive-callers', fmt)), [])

    def test_search_declarations_need_exact_path_identity_and_actual_rows(self):
        for fmt in ('json', 'text'):
            for update in ({'id': ''}, {'id': 'unrelated.py::target:function'}, {'path': '../source.py'},
                           {'start_line': 0}, {'end_line': 0}):
                packet = copy.deepcopy(self.search)
                packet['items'][0].update(update)
                self.assertEqual(self.receipts(self.event(packet, 'archive-search', fmt)), [])
        output = render(self.search, 'text', 'archive-search')
        self.assertEqual(self.receipts(self.event(self.search, 'archive-search', output=output.replace(
            evidence.SEARCH_HEADER, evidence.SOURCE_HEADER))), [])
        duplicate = render(self.single, 'json', 'archive-source').replace('"path":', '"path":"unrelated.py","path":', 1)
        self.assertEqual(self.receipts(self.event(self.single, fmt='json', output=duplicate)), [])
        too_deep = '[' * 1100 + '0' + ']' * 1100
        self.assertEqual(self.receipts(self.event(self.single, fmt='json', output=too_deep)), [])

    def test_same_file_declarations_cannot_claim_conflicting_hashes(self):
        search = copy.deepcopy(self.search)
        search['items'].append(dict(search['items'][0], id='source.py::other:function', source_hash='different-hash'))
        search['matched_nodes'] += 1
        callers = copy.deepcopy(self.callers)
        callers['nodes'][0]['source_hash'] = 'different-hash'
        callers.pop('call_context')
        for fmt in ('json', 'text'):
            for operation, packet in [('archive-search', search), ('archive-callers', callers)]:
                self.assertEqual(self.receipts(self.event(packet, operation, fmt)), [])


if __name__ == '__main__':
    unittest.main()
