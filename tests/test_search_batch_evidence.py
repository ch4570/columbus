"""New discovery-only receipts; tiny archives, no indexes or model calls."""
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
import lzma
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
SPEC = importlib.util.spec_from_file_location('prospective_search_batch_evidence',
                                            ROOT / 'evals/exploration/search_batch_evidence.py')
EVIDENCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVIDENCE)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory(root):
    return {path.relative_to(root).as_posix(): sha(path.read_bytes())
            for path in root.rglob('*') if path.is_file()}


class SearchBatchEvidenceTests(unittest.TestCase):
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
    def node(path, identity, name, qualname=None, **extra):
        return dict(id=path + '::' + identity, path=path, name=name,
                    qualname=qualname or name, kind='function', start_line=1, end_line=3,
                    language='java' if path.endswith('.java') else 'python',
                    fidelity='ast', partial=False, module='pkg.' + Path(path).stem,
                    signature='def ' + name + '():', **extra)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / 'repository'
        self.repo.mkdir()
        for name in ('a.py', 'b.py', 'c.java'):
            (self.repo / name).write_bytes(b'// tiny inert source fixture\n' * 8)
        self.nodes = [
            self.node('a.py', 'target:module', 'target'),
            self.node('a.py', 'zTarget:function', 'target', 'Owner.target'),
            self.node('b.py', 'target:function', 'target', 'Owner.target'),
            self.node('c.java', 'Owner.target:method', 'target', 'Owner.target'),
            self.node('b.py', 'Other.Target:function', 'Target', 'nested.Owner.target'),
            self.node('b.py', 'substring:function', 'prefixOwner.targetSuffix'),
            self.node('a.py', 'unicode:function', 'straße', 'nested.Owner.straße'),
            self.node('a.py', 'dollar:function', '$target'),
        ]
        self.nodes[0].update(kind='module', module='target')
        self.nodes[3]['kind'] = 'method'
        self.nodes[4].pop('partial')
        self.nodes[4]['fidelity'] = 'heuristic'
        self.graph = self.base / 'graph.gz'
        self.freeze()

    def freeze(self, *, codec='gzip', footer=True, trailing=(), reverse=False):
        rows = [('file', dict(path=path.name, hash=sha(path.read_bytes()), size=path.stat().st_size))
                for path in sorted(self.repo.iterdir()) if path.is_file()]
        rows += [('node', node) for node in self.nodes]
        rows += [('diagnostic', dict(path='a.py', message='test'))] * 2
        if reverse:
            rows.reverse()
        plurals = dict(file='files', node='nodes', scope='scopes', edge='edges',
                       reference='references', diagnostic='diagnostics', **{'import': 'imports'})
        counts = dict.fromkeys(plurals.values(), 0)
        for kind, _ in rows:
            counts[plurals[kind]] += 1
        rows.insert(0, ('manifest', dict(format='columbus-graph', version=1, revision='search-batch-test')))
        if footer:
            rows.append(('end', counts))
        rows.extend(trailing)
        raw = ''.join(json.dumps(dict(record=kind, data=data), ensure_ascii=False, separators=(',', ':'))
                      + '\n' for kind, data in rows).encode('utf-8')
        self.graph.write_bytes(gzip.compress(raw, mtime=0) if codec == 'gzip' else lzma.compress(raw))
        self.binding = dict(repository=self.repo, archive=self.graph,
                            invocation_prefix=(sys.executable, '-B', str(self.runtime / 'columbus.py')),
                            archive_sha256=sha(self.graph.read_bytes()), revision='search-batch-test',
                            runtime_inventory=dict(self.runtime_inventory), source_manifest=inventory(self.repo))

    def event(self, queries=('target', 'absent'), *, form='json', limit=5, budget=6000,
              path=None, language=None, actual_cli=False):
        # Production imports are test oracles only, never verifier dependencies.
        from columbus.archive import search_archive_many
        from columbus.presentation import archive_search_many_output
        arguments = ['archive-search', *queries, '--input', str(self.graph), '--repo', str(self.repo),
                     '--format', form, '--limit', str(limit), '--budget-bytes', str(budget)]
        if path is not None:
            arguments += ['--path', path]
        if language is not None:
            arguments += ['--language', language]
        argv = [*self.binding['invocation_prefix'], *arguments]
        if actual_cli:
            result = subprocess.run(argv, cwd=self.repo, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
            self.assertEqual(result.stderr, b'')
            output = result.stdout.decode('utf-8')
        else:
            packet = search_archive_many(self.graph, list(queries), limit, budget,
                                         output_format=form, path=path, language=language)
            output = archive_search_many_output(packet, form)
        return dict(type='item.completed', item=dict(id='search-1', type='command_execution',
                    command=shlex.join(argv), status='completed', exit_code=0, aggregated_output=output))

    def recognize(self, events):
        return EVIDENCE.evidence(events, binding=self.binding)

    def receipt(self, event):
        result = self.recognize([event])
        self.assertEqual(set(result), {'recognizer_version', 'search_batch_receipts'})
        self.assertEqual(len(result['search_batch_receipts']), 1)
        return result['search_batch_receipts'][0]

    def rejected(self, event):
        self.assertEqual(self.recognize([event])['search_batch_receipts'], [])

    @staticmethod
    def command_option(event, name, value):
        result = deepcopy(event)
        words = shlex.split(result['item']['command'])
        words[words.index(name) + 1] = str(value)
        result['item']['command'] = shlex.join(words)
        return result

    def test_actual_tiny_cli_json_text_gzip_xz_has_only_discovery_receipts(self):
        before = inventory(self.runtime)
        for codec in ('gzip', 'xz'):
            self.freeze(codec=codec)
            for form in ('json', 'text'):
                with self.subTest(codec=codec, form=form):
                    event = self.event(actual_cli=True, form=form)
                    receipt = self.receipt(event)
                    self.assertTrue(receipt['useful_discovery'])
                    self.assertEqual(receipt['encoding'], 'search-batch-' + form + '-v1')
                    self.assertEqual(receipt['output_sha256'], sha(event['item']['aggregated_output'].encode()))
                    self.assertEqual(receipt['command_sha256'], sha(event['item']['command'].encode()))
                    self.assertEqual(receipt['source_rows'], 0)
                    self.assertEqual(receipt['edges'], 0)
                    self.assertNotIn('relationship_used', receipt)
                    self.assertNotIn('source_call_receipts', receipt)
                    self.assertNotIn('task_relevant', receipt)
        self.assertEqual(inventory(self.runtime), before)
        self.assertFalse((self.repo / '.columbus').exists())

    def test_zero_match_batch_is_valid_adoption_not_useful_discovery(self):
        for form in ('json', 'text'):
            receipt = self.receipt(self.event(('absent', 'also-absent'), form=form))
            self.assertIs(receipt['useful_discovery'], False)
            self.assertEqual(receipt['declaration_occurrences'], 0)
            self.assertEqual(receipt['distinct_declarations'], 0)
            self.assertEqual([group['matched_nodes'] for group in receipt['groups']], [0, 0])

    def test_group_order_overlap_and_counts_do_not_resolve_ambiguity(self):
        event = self.event(('Owner.target', 'target', 'absent'), limit=50, budget=64000)
        receipt = self.receipt(event)
        packet = json.loads(event['item']['aggregated_output'])
        self.assertEqual([group['query'] for group in receipt['groups']], ['Owner.target', 'target', 'absent'])
        self.assertGreater(receipt['declaration_occurrences'], receipt['distinct_declarations'])
        self.assertGreater(receipt['groups'][0]['matched_nodes'], 1)
        self.assertEqual(packet['results'][1]['items'][0]['id'], 'a.py::target:module')
        self.assertEqual(packet['results'][0]['items'][-1]['id'], 'b.py::substring:function')
        self.assertEqual(packet['results'][0]['items'][-2]['id'], 'b.py::Other.Target:function')

    def test_exact_id_canonical_unicode_suffix_and_authoritative_filters(self):
        exact = self.nodes[1]['id']
        for form in ('json', 'text'):
            for path, language in ((None, None), ('b.py', None), (None, 'java'), ('*.py', 'python')):
                event = self.event((exact, 'pkg.a.Owner.target', 'Owner.STRASSE'),
                                   form=form, path=path, language=language)
                receipt = self.receipt(event)
                if path == 'b.py' or language == 'java':
                    self.assertEqual(receipt['groups'][0]['returned_nodes'], 0)
                else:
                    self.assertEqual(receipt['groups'][0]['declaration_ids'], [exact])
                    self.assertEqual(receipt['groups'][2]['declaration_ids'], ['a.py::unicode:function'])
        event = self.event(('target', 'absent'), path='c.java', language='java')
        self.assertEqual(json.loads(event['item']['aggregated_output'])['diagnostic_count'], 2)
        self.receipt(event)

    def test_signature_cap_optional_partial_and_controls_are_exact(self):
        self.nodes[1]['signature'] = '한글 😀\x01\x85\u2028\u2029' * 70
        self.nodes[4].pop('signature')
        self.freeze()
        for form in ('json', 'text'):
            event = self.event(('Owner.target', 'absent'), form=form)
            self.receipt(event)
            output = event['item']['aggregated_output']
            self.assertNotIn('\x01', output)
            self.assertNotIn('\x85', output)
            if form == 'json':
                items = json.loads(output)['results'][0]['items']
                original = next(item for item in items if item['id'] == self.nodes[1]['id'])
                self.assertEqual(len(original['signature']), 240)
                missing = next(item for item in items if item['id'] == self.nodes[4]['id'])
                self.assertEqual(missing['signature'], '')
                self.assertNotIn('partial', missing)

    def test_limits_truncation_and_sixteen_queries_retain_every_group(self):
        queries = ['target'] + ['missing-' + str(i) for i in range(15)]
        receipt = self.receipt(self.event(queries, limit=1))
        self.assertEqual(len(receipt['groups']), 16)
        self.assertEqual(receipt['groups'][0]['returned_nodes'], 1)
        self.assertTrue(receipt['groups'][0]['truncated'])
        self.assertTrue(all(not group['truncated'] for group in receipt['groups'][1:]))
        self.nodes.reverse()
        self.freeze(reverse=True)
        self.assertEqual(self.receipt(self.event(queries, limit=1))['groups'], receipt['groups'])

    def test_shared_exact_budget_never_drops_groups_or_candidates(self):
        for form in ('json', 'text'):
            event = self.event(('Owner.target', 'target'), limit=50, budget=64000, form=form)
            size = len(event['item']['aggregated_output'].encode('utf-8'))
            self.assertGreater(size, 2048)
            self.receipt(self.command_option(event, '--budget-bytes', size))
            self.rejected(self.command_option(event, '--budget-bytes', size - 1))
            packet = json.loads(self.event(('Owner.target', 'target'), limit=50, budget=64000)['item']['aggregated_output'])
            packet['results'][0]['items'].pop()
            packet['results'][0]['truncated'] = True
            changed = self.event(('Owner.target', 'target'), limit=50, budget=64000, form=form)
            from columbus.presentation import archive_search_many_output
            changed['item']['aggregated_output'] = archive_search_many_output(packet, form)
            self.rejected(changed)

    def test_reordered_missing_extra_groups_and_all_metadata_mutations_fail(self):
        from columbus.presentation import archive_search_many_output
        original = self.event(('Owner.target', 'target', 'absent'), budget=64000)
        packet = json.loads(original['item']['aggregated_output'])
        variants = []
        for key, value in [('format', 'wrong'), ('revision', 'wrong'), ('freshness', 'source verified'),
                           ('semantic_complete', True), ('diagnostic_count', 0), ('source_policy', '')]:
            changed = deepcopy(packet)
            changed[key] = value
            variants.append(changed)
        changed = deepcopy(packet)
        changed['results'].reverse()
        variants.append(changed)
        changed = deepcopy(packet)
        changed['results'].pop()
        variants.append(changed)
        changed = deepcopy(packet)
        changed['results'].append(deepcopy(changed['results'][0]))
        variants.append(changed)
        for key, value in [('query', 'wrong'), ('matched_nodes', 999), ('matched_nodes', True), ('truncated', False)]:
            changed = deepcopy(packet)
            changed['results'][1][key] = value
            if changed != packet:
                variants.append(changed)
        for key, value in [('source_hash', 'b' * 64), ('signature', 'wrong'), ('name', 'wrong'),
                           ('start_line', 2), ('partial', True), ('fidelity', 'heuristic')]:
            changed = deepcopy(packet)
            changed['results'][0]['items'][0][key] = value
            variants.append(changed)
        changed = deepcopy(packet)
        changed['results'][0]['items'].reverse()
        variants.append(changed)
        for key, value in [('path_filter', '*.py'), ('language_filter', 'python')]:
            changed = deepcopy(packet)
            changed[key] = value
            variants.append(changed)
        for form in ('json', 'text'):
            for packet in variants:
                with self.subTest(form=form, packet=packet):
                    event = self.command_option(original, '--format', form)
                    event['item']['aggregated_output'] = archive_search_many_output(packet, form)
                    self.rejected(event)

    def test_noncanonical_whitespace_duplicate_keys_controls_and_partial_text_fail(self):
        for form in ('json', 'text'):
            original = self.event(form=form)
            output = original['item']['aggregated_output']
            variants = [output.rstrip('\n'), output + '\n', ' ' + output,
                        output.replace('"query":', '"query":"forged","query":', 1),
                        output.replace('"matched_nodes":', '"matched_nodes":NaN,"unused":', 1)]
            if form == 'text':
                variants += [output.replace('columbus archive-search batch;', 'columbus archive-search;', 1),
                             '\n'.join(output.split('\n')[:-2]) + '\n']
            for value in variants:
                changed = deepcopy(original)
                changed['item']['aggregated_output'] = value
                self.rejected(changed)

    def test_invocation_binding_changes_options_and_unsafe_shells_fail(self):
        original = self.event(('Owner.target', 'absent'))
        words = shlex.split(original['item']['command'])
        variants = []
        for token, value in [(words[0], '/untrusted/python'), (words[2], '/untrusted/columbus.py'),
                             ('Owner.target', 'target'), (str(self.graph), str(self.base / 'wrong.gz')),
                             (str(self.repo), str(self.base)), ('json', 'text')]:
            changed = words.copy()
            changed[changed.index(token)] = value
            variants.append(shlex.join(changed))
        variants += [shlex.join([word for word in words if word != '-B'])]
        for extra in [('--limit', '1'), ('--inp', str(self.graph)), ('--pretty',), ('--offset', '0'),
                      ('--telemetry', ''), ('--path', '*.none'), ('--language', 'javascript')]:
            variants.append(shlex.join(words + list(extra)))
        for shell in ('sh', 'bash', 'zsh', '/untrusted/zsh', '/tmp/bin/bash'):
            variants.append(shlex.join([shell, '-c', original['item']['command']]))
        variants += [original['item']['command'] + ' ; true',
                     shlex.join(['/bin/sh', '-c', shlex.join(['/bin/sh', '-c', original['item']['command']])])]
        for value in variants:
            changed = deepcopy(original)
            changed['item']['command'] = value
            self.rejected(changed)
        for option, value in [('--limit', 1), ('--limit', 0), ('--limit', 51),
                              ('--budget-bytes', 2047), ('--budget-bytes', 64001)]:
            self.rejected(self.command_option(original, option, value))

    def test_literal_queries_default_global_options_equals_and_allowlisted_shells(self):
        original = self.event(('$target', 'absent'))
        argv = [*self.binding['invocation_prefix'], '--repo', str(self.repo), 'archive-search',
                '$target', 'absent', '--input=' + str(self.graph)]
        original['item']['command'] = shlex.join(argv)
        self.receipt(original)
        for shell in sorted(EVIDENCE._SHELLS):
            for flag in ('-c', '-lc'):
                event = deepcopy(original)
                event['item']['command'] = shlex.join([shell, flag, original['item']['command']])
                self.receipt(event)
        changed = deepcopy(original)
        changed['item']['command'] = original['item']['command'].replace("'$target'", '$target')
        self.rejected(changed)

    def test_duplicate_missing_and_oversized_query_lists_fail(self):
        event = self.event()
        words = shlex.split(event['item']['command'])
        start = words.index('archive-search') + 1
        stop = words.index('--input')
        for queries in [('target',), ('target', 'target'), ('x' * 513, 'absent'),
                        tuple('absent-' + str(i) for i in range(17)), ('', 'absent')]:
            changed = deepcopy(event)
            changed['item']['command'] = shlex.join(words[:start] + list(queries) + words[stop:])
            self.rejected(changed)

    def test_failed_offered_nonterminal_and_malformed_event_fields_give_no_receipt(self):
        original = self.event()
        for field, value in [('id', ''), ('id', None), ('type', 'reasoning'), ('status', 'running'),
                             ('exit_code', 1), ('exit_code', False), ('exit_code', '0'), ('aggregated_output', None)]:
            changed = deepcopy(original)
            changed['item'][field] = value
            self.rejected(changed)
        changed = deepcopy(original)
        changed['item'].pop('status')
        self.rejected(changed)
        changed = deepcopy(original)
        changed['type'] = 'item.started'
        self.rejected(changed)
        changed = deepcopy(original)
        changed['item']['extra'] = float('inf')
        self.rejected(changed)
        nested = []
        for _ in range(1200):
            nested = [nested]
        changed = deepcopy(original)
        changed['item']['extra'] = nested
        # Encoder recursion limits differ across Python releases. Deep but
        # serializable extra data is valid; a serialization failure must close.
        try:
            EVIDENCE._compact(changed)
        except (RecursionError, OverflowError):
            self.rejected(changed)
        else:
            self.receipt(changed)
        compact = EVIDENCE._compact
        for error in (RecursionError, OverflowError):
            def failing_event_hash(value):
                if value is original:
                    raise error('synthetic serialization failure')
                return compact(value)
            with patch.object(EVIDENCE, '_compact', side_effect=failing_event_hash):
                self.rejected(original)

    def test_missing_changed_source_runtime_archive_and_binding_fail_even_empty(self):
        for field, value in [('revision', 'wrong'), ('archive_sha256', '0' * 64),
                             ('source_manifest', {}), ('runtime_inventory', {})]:
            original = self.binding
            self.binding = dict(original, **{field: value})
            with self.assertRaises(ValueError):
                self.recognize([])
            self.binding = original
        source = self.repo / 'a.py'
        content = source.read_bytes()
        source.write_bytes(content.replace(b'tiny', b'evil'))
        with self.assertRaises(ValueError):
            self.recognize([])
        source.write_bytes(content)
        extra = self.repo / 'unexpected'
        extra.write_bytes(b'new')
        with self.assertRaises(ValueError):
            self.recognize([])
        extra.unlink()
        runtime = self.runtime / 'columbus.py'
        data = runtime.read_bytes()
        try:
            runtime.write_bytes(data + b'\n')
            with self.assertRaises(ValueError):
                self.recognize([])
        finally:
            runtime.write_bytes(data)
        original = self.binding
        self.binding = deepcopy(original)
        self.binding['runtime_inventory'].pop('columbus.py')
        with self.assertRaises(ValueError):
            self.recognize([])
        self.binding = original

    def test_whole_archive_validation_rejects_missing_late_corrupt_footer(self):
        for codec in ('gzip', 'xz'):
            self.freeze(codec=codec, footer=False)
            with self.assertRaises(ValueError):
                self.recognize([])
            self.freeze(codec=codec, trailing=[('diagnostic', {})])
            with self.assertRaises(ValueError):
                self.recognize([])
            self.freeze(codec=codec)
            self.graph.write_bytes(self.graph.read_bytes()[:-4])
            self.binding['archive_sha256'] = sha(self.graph.read_bytes())
            with self.assertRaises(ValueError):
                self.recognize([])

    def test_post_read_byte_guards_detect_changes_even_if_stamp_check_is_blind(self):
        for target in (self.repo / 'a.py', self.runtime / 'columbus.py', self.graph):
            original = target.read_bytes()
            def changing_events():
                target.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                return
                yield  # Empty stream, mutation happens after initial snapshot.
            try:
                with patch.object(EVIDENCE._Snapshot, 'check', return_value=None), self.assertRaises(ValueError):
                    self.recognize(changing_events())
            finally:
                target.write_bytes(original)

    def test_binding_mutation_during_recognition_fails_and_normal_inputs_are_unchanged(self):
        event = self.event()
        before = deepcopy(self.binding)
        files = inventory(self.repo), inventory(self.runtime), self.graph.read_bytes()
        self.receipt(event)
        self.assertEqual(self.binding, before)
        self.assertEqual((inventory(self.repo), inventory(self.runtime), self.graph.read_bytes()), files)
        def changing_events():
            self.binding['source_manifest']['a.py'] = '0' * 64
            yield event
        with self.assertRaises(ValueError):
            self.recognize(changing_events())

    def test_closing_snapshot_scan_detects_mutation_during_final_hash_reads(self):
        read = EVIDENCE.SAFE._read
        original = self.graph.read_bytes()
        for location in ('source', 'runtime', 'archive'):
            added = (self.repo if location == 'source' else self.runtime) / 'late-added'
            archive_reads = 0
            def changing_read(path):
                nonlocal archive_reads
                result = read(path)
                if path == self.graph:
                    archive_reads += 1
                    if archive_reads == 2:  # Final read, after both inventories.
                        if location == 'archive':
                            self.graph.write_bytes(original + b'x')
                        else:
                            added.write_bytes(b'late addition')
                return result
            try:
                with patch.object(EVIDENCE.SAFE, '_read', side_effect=changing_read), self.assertRaises(ValueError):
                    self.recognize([])
                self.assertEqual(archive_reads, 2)
            finally:
                if location == 'archive':
                    self.graph.write_bytes(original)
                elif added.exists():
                    added.unlink()

    def test_binding_comparison_follows_the_last_snapshot_io(self):
        check = EVIDENCE._Snapshot.check
        checks = 0
        def changing_check(snapshot):
            nonlocal checks
            check(snapshot)
            checks += 1
            if checks == 3:  # Initial check, final pre-scan, final closing scan.
                self.binding['revision'] = 'changed during closing scan'
        with patch.object(EVIDENCE._Snapshot, 'check', new=changing_check), self.assertRaises(ValueError):
            self.recognize([])
        self.assertEqual(checks, 3)

    def test_production_search_and_renderer_are_never_used_by_verifier(self):
        event = self.event()
        with patch('columbus.archive.search_archive_many', side_effect=AssertionError('production oracle')), \
                patch('columbus.presentation.archive_search_many_output', side_effect=AssertionError('production renderer')):
            self.receipt(event)


if __name__ == '__main__':
    unittest.main()
