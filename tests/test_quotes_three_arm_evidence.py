"""Pure receipt controls: no models, repository execution, or subprocess calls."""
import copy
import gzip
import hashlib
import importlib.util
import json
import lzma
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


COHORT = Path(__file__).resolve().parents[1] / 'evals/quotes-three-arm'


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, COHORT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def forbidden(*args, **kwargs):
    raise AssertionError('External execution forbidden in evidence tests')


with mock.patch.multiple(subprocess, Popen=forbidden, run=forbidden, check_output=forbidden):
    common = load('quotes_evidence_common', 'common.py')
    with mock.patch.dict(sys.modules, {'common': common}):
        recognize = load('quotes_evidence_recognize', 'recognize.py')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def render(packet):
    return json.dumps(packet, ensure_ascii=False, separators=(',', ':')).translate(recognize.ESCAPES) + '\n'


class QuotesThreeArmEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='quotes-evidence-')
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name).resolve()
        self.repo = self.output / 'repository'
        self.repo.mkdir()
        (self.output / 'runtime').mkdir()
        (self.output / 'runtime/columbus.py').write_bytes(b'# frozen tool placeholder, never run\n')
        self.files = {'Caller.java': b'class Caller {\n  void caller() {\n    target();\n  }\n}\n',
                      'Target.java': b'class Target {\n  void target() {}\n}\n'}
        self.languages = {path: ['java'] for path in self.files}
        self.source = 'Caller.java::Caller.caller:method()'
        self.target = 'Target.java::Target.target:method()'
        self.relationship = dict(source=self.source, target=self.target, path='Caller.java', line=3)
        self.freeze()
        self.patches = mock.patch.multiple(subprocess, Popen=forbidden, run=forbidden, check_output=forbidden)
        self.patches.start()
        self.addCleanup(self.patches.stop)

    def freeze(self, compression='xz'):
        manifest = {path: digest(data) for path, data in self.files.items()}
        records = [{'record': 'manifest', 'data': {'format': 'columbus-graph', 'version': 1, 'revision': 'frozen-revision'}}]
        for path, data in self.files.items():
            actual = self.repo / path
            actual.parent.mkdir(parents=True, exist_ok=True)
            actual.write_bytes(data)
            records.append({'record': 'file', 'data': {'path': path, 'hash': manifest[path], 'size': len(data)}})
            for language in self.languages[path]:
                records.append({'record': 'node', 'data': {'path': path, 'language': language}})
        records.append({'record': 'end', 'data': {}})
        raw = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records).encode()
        archive = gzip.compress(raw) if compression == 'gzip' else lzma.compress(raw)
        (self.output / 'graph.jsonl.xz').write_bytes(archive)
        self.manifest = manifest
        self.frozen = {'source_manifest': manifest, 'revision': 'frozen-revision', 'archive_sha256': digest(archive)}
        (self.output / 'manifest.json').write_text(json.dumps({'source_manifest': manifest}))
        (self.output / 'engine.json').write_text(json.dumps({'archive': self.frozen}))

    def command(self, operation, arguments):
        return shlex.join([sys.executable, '-B', str(self.output / 'runtime/columbus.py'), operation,
                           *arguments, '--input', str(self.output / 'graph.jsonl.xz'), '--repo', '.'])

    def event(self, command, output):
        return {'type': 'item.completed', 'item': {'type': 'command_execution', 'id': 'command-1',
                'command': command, 'exit_code': 0, 'status': 'completed', 'aggregated_output': output}}

    def neighbor(self, operation='archive-neighbors', form='json'):
        packet = dict(symbol_id=self.source if operation == 'archive-neighbors' else self.target,
                      direction='out' if operation == 'archive-neighbors' else 'in', kinds=['calls'],
                      revision='frozen-revision', offset=0, matched_edges=1, next_offset=None, truncated=False,
                      nodes=[dict(id=self.source, path='Caller.java', source_hash=self.manifest['Caller.java'],
                                  start_line=2, end_line=4),
                             dict(id=self.target, path='Target.java', source_hash=self.manifest['Target.java'],
                                  start_line=2, end_line=2)],
                      edges=[dict(self.relationship, kind='calls')])
        if form == 'json':
            output = json.dumps(packet)
        else:
            metadata = {key: value for key, value in packet.items() if key not in {'nodes', 'edges'}}
            lines = [common.EVIDENCE.NEIGHBOR_HEADER, 'metadata ' + json.dumps(metadata), common.EVIDENCE.FILES]
            lines.extend(json.dumps([number, path, self.manifest[path]]) for number, path in enumerate(self.files))
            lines.append(common.EVIDENCE.NODES)
            lines.extend(json.dumps([number, number, {key: value for key, value in node.items()
                                                    if key not in {'path', 'source_hash'}}])
                         for number, node in enumerate(packet['nodes']))
            lines.extend([common.EVIDENCE.EDGES, json.dumps([0, 1, 0, {'kind': 'calls', 'line': 3}])])
            output = '\n'.join(lines) + '\n'
        command = self.command(operation, [packet['symbol_id'], '--format', form])
        return self.event(command, output)

    def quote(self, requests=None, budget=64000):
        requests = requests or [('Caller.java', 2, 4)]
        arguments, quotes = ['--budget-bytes', str(budget)], []
        for path, start, end in requests:
            language = self.languages[path][0]
            lines = recognize._lines(self.files[path], language)
            quotes.append(dict(path=path, start_line=start, end_line=end, source_hash=self.manifest[path],
                               language=language, quote='\n'.join(lines[start - 1:end])))
            arguments.extend(['--range', './' + path if path.startswith('-') else path, str(start), str(end)])
        packet = dict(format='columbus-quotes/v1', revision='frozen-revision', freshness=recognize.FRESHNESS,
                      semantic_complete=False, source_policy=recognize.POLICY, quotes=quotes)
        return self.event(self.command('archive-quotes', arguments), render(packet))

    def result(self, events, relationships=None):
        return recognize.evidence(events, self.output, [self.relationship] if relationships is None else relationships)

    def assert_rejected(self, event):
        self.assertEqual(self.result([event]), dict(relationship_used=False, relationship_receipts=[],
                                                   quotes_used=False, quote_receipts=[]))

    def test_actual_relationship_json_text_callers_and_neighbors(self):
        for operation in ('archive-callers', 'archive-neighbors'):
            for form in ('json', 'text'):
                with self.subTest(operation=operation, form=form):
                    event = self.neighbor(operation, form)
                    result = self.result([event])
                    self.assertTrue(result['relationship_used'])
                    self.assertFalse(result['quotes_used'])
                    receipt, = result['relationship_receipts']
                    self.assertEqual(receipt['relationships'], [self.relationship])
                    self.assertEqual(receipt['output_sha256'], digest(event['item']['aggregated_output'].encode()))

    def test_relationship_requires_every_reviewed_field(self):
        for key, value in {'source': self.source + 'other', 'target': self.target + 'other',
                           'path': 'Other.java', 'line': 4}.items():
            changed = dict(self.relationship, **{key: value})
            if key == 'path':
                changed['source'] = 'Other.java::Caller.caller:method()'
            with self.subTest(key=key):
                self.assertFalse(self.result([self.neighbor()], [changed])['relationship_used'])

    def test_all_delivered_declarations_must_match_frozen_hashes(self):
        for index in (0, 1):
            event = self.neighbor()
            packet = json.loads(event['item']['aggregated_output'])
            packet['nodes'][index]['source_hash'] = '0' * 64
            event['item']['aggregated_output'] = json.dumps(packet)
            self.assert_rejected(event)

    def test_neighbor_shape_kind_revision_and_text_reference_rejected(self):
        mutations = [lambda p: p.update(revision='wrong'), lambda p: p.update(truncated=True),
                     lambda p: p['edges'][0].update(line=True), lambda p: p['edges'][0].update(path='Target.java'),
                     lambda p: (p.update(kinds=None), p['edges'][0].update(kind='imports')),
                     lambda p: p['nodes'].append(dict(p['nodes'][0]))]
        for mutate in mutations:
            event = self.neighbor()
            packet = json.loads(event['item']['aggregated_output'])
            mutate(packet)
            event['item']['aggregated_output'] = json.dumps(packet)
            self.assert_rejected(event)
        event = self.neighbor(form='text')
        event['item']['aggregated_output'] = event['item']['aggregated_output'].replace('[0, 1, 0,', '[0, 1, 99,')
        self.assert_rejected(event)

    def test_source_search_and_offered_commands_never_relationship_evidence(self):
        for operation in ('archive-source', 'archive-search'):
            event = self.neighbor()
            event['item']['command'] = event['item']['command'].replace('archive-neighbors', operation)
            self.assert_rejected(event)
        self.assertEqual(self.result([])['relationship_receipts'], [])

    def test_failed_started_boolean_exit_and_noncommand_events_rejected(self):
        for factory in (self.neighbor, self.quote):
            for key, value in [('exit_code', 1), ('exit_code', False), ('status', 'failed'), ('type', 'message')]:
                event = factory()
                event['item'][key] = value
                self.assert_rejected(event)
            event = factory()
            event['type'] = 'item.started'
            self.assert_rejected(event)

    def test_runtime_archive_repo_abbreviations_compounds_and_expansion_rejected(self):
        for factory in (self.neighbor, self.quote):
            for mutate in (lambda c: c.replace(str(self.output / 'runtime/columbus.py'), '/tmp/other/columbus.py'),
                           lambda c: c.replace(str(self.output / 'graph.jsonl.xz'), '/tmp/other.xz'),
                           lambda c: c.replace('--repo .', '--repo ..'),
                           lambda c: c + ' --inp /tmp/other.xz',
                           lambda c: c + ' --input /tmp/other.xz',
                           lambda c: c + ' | head -10', lambda c: c + '; true',
                           lambda c: c.replace('--repo .', '--repo $(pwd)')):
                event = factory()
                event['item']['command'] = mutate(event['item']['command'])
                self.assert_rejected(event)

    def test_supported_shell_wrapper_does_not_lose_positive_receipts(self):
        for factory, key in ((self.neighbor, 'relationship_used'), (self.quote, 'quotes_used')):
            event = factory()
            event['item']['command'] = shlex.join(['/bin/zsh', '-lc', event['item']['command']])
            self.assertTrue(self.result([event])[key])

    def test_quotes_are_separate_and_ordered_including_overlap(self):
        requests = [('Target.java', 1, 2), ('Caller.java', 2, 4), ('Caller.java', 3, 3)]
        event = self.quote(requests)
        result = self.result([self.neighbor(), event])
        self.assertTrue(result['relationship_used'])
        self.assertTrue(result['quotes_used'])
        receipt, = result['quote_receipts']
        self.assertEqual([(r['path'], r['start_line'], r['end_line']) for r in receipt['ranges']], requests)
        self.assertEqual(receipt['source_rows'], 6)
        quote_only = self.result([event], [])
        self.assertTrue(quote_only['quotes_used'])
        self.assertFalse(quote_only['relationship_used'])
        self.assertNotIn('quote', receipt['ranges'][0])

    def test_quote_controls_roundtrip_physical_lines_bom_cr_and_python_encoding(self):
        self.files.update({'-odd\u2028.java': '\ufefffirst\rinside\r\n\tsecond\x7f\x85\u2028\u2029\n\n'.encode(),
                           'configured.custom': b'# coding: latin-1\ncaf\xe9\r\n', 'blank.java': b'\n'})
        self.languages.update({'-odd\u2028.java': ['java'], 'configured.custom': ['python'], 'blank.java': ['java']})
        for compression in ('gzip', 'xz'):
            self.freeze(compression)
            event = self.quote([('-odd\u2028.java', 1, 3), ('configured.custom', 1, 2), ('blank.java', 1, 1)])
            packet = json.loads(event['item']['aggregated_output'])
            self.assertEqual(packet['quotes'][0]['quote'], 'first\rinside\n\tsecond\x7f\x85\u2028\u2029\n')
            self.assertEqual(packet['quotes'][1]['quote'], '# coding: latin-1\ncafé')
            self.assertEqual(packet['quotes'][2]['quote'], '')
            self.assertTrue(self.result([event])['quotes_used'])

    def test_quote_packet_fields_content_order_and_duplicate_json_rejected(self):
        mutations = [lambda p: p.update(revision='wrong'), lambda p: p.update(semantic_complete=True),
                     lambda p: p.update(source_policy='trusted'), lambda p: p.update(extra=True),
                     lambda p: p['quotes'][0].update(quote='not source'),
                     lambda p: p['quotes'][0].update(source_hash='0' * 64),
                     lambda p: p['quotes'][0].update(language='python'),
                     lambda p: p['quotes'][0].update(start_line=True),
                     lambda p: p['quotes'][0].update(end_line=99),
                     lambda p: p['quotes'][0].update(path='../Caller.java'),
                     lambda p: p['quotes'].reverse(), lambda p: p['quotes'].pop()]
        for mutate in mutations:
            event = self.quote([('Caller.java', 2, 4), ('Target.java', 1, 2)])
            packet = json.loads(event['item']['aggregated_output'])
            mutate(packet)
            event['item']['aggregated_output'] = render(packet)
            self.assert_rejected(event)
        for suffix in ('garbage', '\n', '{"format":"columbus-quotes/v1"}'):
            event = self.quote()
            event['item']['aggregated_output'] += suffix
            self.assert_rejected(event)
        event = self.quote()
        event['item']['aggregated_output'] = event['item']['aggregated_output'].replace(
            '"format":', '"format":"duplicate","format":', 1)
        self.assert_rejected(event)

    def test_quote_requested_arguments_bounds_and_duplicates_rejected(self):
        event = self.quote()
        for addition in (' --range Caller.java 2 4', ' --budget-bytes 64000', ' --format text',
                         ' --pretty', ' --db local.sqlite', ' --telemetry receipt', ' --form json'):
            changed = copy.deepcopy(event)
            changed['item']['command'] += addition
            self.assert_rejected(changed)
        for replacement in ('Caller.java 0 4', 'Caller.java 5 4', 'Caller.java 1 401',
                            '././Caller.java 2 4', '/Caller.java 2 4', 'Caller.java true 4'):
            changed = copy.deepcopy(event)
            changed['item']['command'] = changed['item']['command'].replace('Caller.java 2 4', replacement)
            self.assert_rejected(changed)
        changed = self.quote([('Caller.java', 2, 4)] * 17)
        self.assert_rejected(changed)

    def test_quote_exact_render_budget_boundary(self):
        event = self.quote([('Caller.java', 2, 4), ('Target.java', 1, 2)])
        size = len(event['item']['aggregated_output'].encode())
        self.assertGreaterEqual(size, 512)
        event['item']['command'] = event['item']['command'].replace('--budget-bytes 64000', f'--budget-bytes {size}')
        self.assertTrue(self.result([event])['quotes_used'])
        event['item']['command'] = event['item']['command'].replace(f'--budget-bytes {size}', f'--budget-bytes {size - 1}')
        self.assert_rejected(event)

    def test_quote_stale_actual_source_archive_and_symlink_rejected(self):
        event = self.quote()
        (self.repo / 'Caller.java').write_bytes(self.files['Caller.java'].replace(b'target', b'forged'))
        self.assert_rejected(event)
        self.freeze()
        (self.output / 'graph.jsonl.xz').write_bytes(b'not frozen archive')
        self.assert_rejected(event)
        self.freeze()
        original = self.repo / 'Caller.java'
        original.unlink()
        original.symlink_to(self.repo / 'Target.java')
        self.assert_rejected(event)

    def test_missing_conflicting_or_invalid_archived_language_rejected(self):
        event = self.quote()
        for languages in ([], ['java', 'python'], [None], ['Java']):
            self.languages['Caller.java'] = languages
            self.freeze()
            self.assert_rejected(event)

    def test_empty_file_is_not_one_blank_line(self):
        self.files['Empty.java'] = b''
        self.languages['Empty.java'] = ['java']
        self.freeze()
        self.assert_rejected(self.quote([('Empty.java', 1, 1)]))

    def test_malformed_reviews_and_frozen_manifest_fail_as_configuration_errors(self):
        with self.assertRaises(ValueError):
            self.result([], [dict(self.relationship, line=True)])
        (self.output / 'manifest.json').write_text(json.dumps({'source_manifest': {}}))
        with self.assertRaises(ValueError):
            self.result([])


if __name__ == '__main__':
    unittest.main()
