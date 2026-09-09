"""JSON call tables are explicit, copy-safe and share the actual CLI budget."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from columbus.cli import main
import test_archive_source_calls as fixtures


class JsonCallTableCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name).resolve()
        (self.repo / '.columbus.json').write_bytes(b'{invalid configuration')

    def invoke(self, *options, global_options=(), queries=('outer',), artifact='unopened.xz'):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main([*global_options, 'archive-source', *queries, '--input', str(artifact),
                         '--repo', str(self.repo), *options])
        return code, output.getvalue(), error.getvalue()

    def fixture(self, codec='gzip', *, footer=True):
        fixture = fixtures.ArchiveSourceCallsTests()
        body = fixture._fixture(self.repo)
        body.append(deepcopy(next(row for row in body if row['record'] == 'edge')))
        # Real tab and literal escape characters remain distinguishable after
        # json.loads. This inert comment is data, not executed source.
        path = self.repo / 'calls.py'
        source = path.read_text(encoding='utf-8').split('\n')
        source[1] += '  # actual\ttab literal\\t literal\\n \\ 한글 😀\x01\x7f\x85\u2028\u2029'
        raw = '\n'.join(source).encode('utf-8')
        path.write_bytes(raw)
        for row in body:
            if row['record'] == 'file' and row['data']['path'] == 'calls.py':
                row['data'].update(size=len(raw), hash=hashlib.sha256(raw).hexdigest())
        artifact = fixture._write(self.repo, body, codec=codec, footer=footer)
        return artifact, '\n'.join(source[:8])

    @staticmethod
    def decode(packet):
        packet = deepcopy(packet)
        calls = packet['call_sites']
        assert calls['format'] == 'columbus-call-table-json/v1'
        assert calls['index_scope'] == 'this packet'
        nodes, edges = [], []
        for file_number, declaration in calls['nodes']:
            assert type(file_number) is int and 0 <= file_number < len(calls['files'])
            path, source_hash = calls['files'][file_number]
            nodes.append(dict(declaration, path=path, source_hash=source_hash))
        for source, target, file_number, relationship in calls['edges']:
            assert all(type(number) is int for number in (source, target, file_number))
            assert 0 <= source < len(nodes) and 0 <= target < len(nodes)
            assert 0 <= file_number < len(calls['files'])
            path, source_hash = calls['files'][file_number]
            assert (path, source_hash) == (nodes[source]['path'], nodes[source]['source_hash'])
            edges.append(dict(relationship, source=nodes[source]['id'], target=nodes[target]['id'], path=path))
        packet['call_sites'] = {key: value for key, value in calls.items()
                                if key not in {'format', 'index_scope', 'files', 'nodes', 'edges'}}
        packet['call_sites'].update(nodes=nodes, edges=edges)
        return packet

    def test_default_and_explicit_json_forward_flag_to_fitter_and_serializer(self):
        packet = {'unchanged': 'packet'}
        for form in ((), ('--format', 'json')):
            with self.subTest(form=form), \
                    patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')), \
                    patch('columbus.source_calls.source_calls_archive', return_value=packet) as query, \
                    patch('columbus.source_calls.source_calls_json', return_value='exact json\n') as render, \
                    patch('columbus.source_calls.source_calls_text', side_effect=AssertionError('text rendered')):
                result = self.invoke('--call-sites', '--call-table', *form, '--overloads',
                                     '--offset', '3', '--limit', '8', '--budget-bytes', '9000',
                                     queries=('First', 'Second'))
            self.assertEqual(result, (0, 'exact json\n', ''))
            query.assert_called_once_with('unopened.xz', ['First', 'Second'], self.repo, 8, 9000, 3,
                                          output_format='json', overloads=True, call_table=True)
            render.assert_called_once_with(packet, call_table=True)

    def test_real_json_gzip_xz_default_explicit_full_packet_and_copy_safe_source(self):
        from columbus.source_calls import source_calls_archive, source_calls_json
        for codec in ('gzip', 'xz'):
            artifact, source = self.fixture(codec)
            expected = source_calls_archive(artifact, ['outer'], self.repo, budget_bytes=64000)
            outputs = []
            for form in ((), ('--format', 'json')):
                with self.subTest(codec=codec, form=form), \
                        patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')):
                    code, output, error = self.invoke('--call-sites', '--call-table', *form,
                                                      '--budget-bytes', '64000', artifact=artifact)
                self.assertEqual((code, error), (0, ''))
                self.assertEqual(output, source_calls_json(expected, call_table=True))
                self.assertTrue(output.endswith('\n') and not output.endswith('\n\n'))
                decoded = self.decode(json.loads(output))
                self.assertEqual(decoded, expected)
                self.assertEqual(decoded['sources'][0]['source'], source)
                self.assertIn('actual\ttab literal\\t literal\\n', decoded['sources'][0]['source'])
                self.assertEqual(len(decoded['call_sites']['edges']), 6)
                for character in ('\t', '\x01', '\x7f', '\x85', '\u2028', '\u2029'):
                    self.assertNotIn(character, output)
                outputs.append(output)
            self.assertEqual(outputs[0], outputs[1])
        self.assertFalse((self.repo / '.columbus').exists())

    def test_full_packet_final_lf_exact_budget_and_one_byte_less(self):
        artifact, _ = self.fixture('xz')
        selected = ('--call-sites', '--call-table', '--format', 'json')
        code, full, error = self.invoke(*selected, '--budget-bytes', '64000', artifact=artifact)
        self.assertEqual((code, error), (0, ''))
        size = len(full.encode('utf-8'))
        self.assertGreater(size, 2048)
        exact = self.invoke(*selected, '--budget-bytes', str(size), artifact=artifact)
        smaller = self.invoke(*selected, '--budget-bytes', str(size - 1), artifact=artifact)
        self.assertEqual(exact, (0, full, ''))
        self.assertIn(smaller[0], (0, 2))
        self.assertNotEqual(smaller[1], full)
        self.assertLessEqual(len(smaller[1].encode('utf-8')), size - 1)
        if smaller[0] == 0:
            packet = self.decode(json.loads(smaller[1]))
            self.assertTrue(packet['truncated'])
            self.assertIsNotNone(packet['next_offset'])
        else:
            self.assertEqual(smaller[1], '')

    def test_missing_call_sites_and_pretty_fail_before_filesystem_resolution(self):
        for options in (('--call-table',), ('--call-table', '--format', 'json'),
                        ('--call-table', '--call-sites', '--pretty')):
            with self.subTest(options=options), \
                    patch('columbus.cli.Path.resolve', side_effect=AssertionError('filesystem resolution')), \
                    patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')), \
                    patch('columbus.source_calls.source_calls_archive') as query, \
                    patch('columbus.archive.source_archive_many') as legacy:
                code, output, error = self.invoke(*options)
            self.assertEqual((code, output), (2, ''))
            self.assertIn('--pretty' if '--pretty' in options else '--call-sites', error)
            query.assert_not_called()
            legacy.assert_not_called()

    def test_forbidden_global_and_subcommand_options_fail_before_any_reader(self):
        for extra in (('--db', ''), ('--db', 'existing.sqlite'),
                      ('--telemetry', ''), ('--telemetry', 'events.jsonl'), ('--pretty',)):
            for placement in ('global', 'subcommand'):
                with self.subTest(extra=extra, placement=placement), \
                        patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')), \
                        patch('columbus.cli.Path.resolve', side_effect=AssertionError('filesystem resolution')), \
                        patch('columbus.source_calls.source_calls_archive') as query:
                    selected = ('--call-sites', '--call-table')
                    result = (self.invoke(*selected, global_options=extra) if placement == 'global'
                              else self.invoke(*selected, *extra))
                self.assertEqual(result[:2], (2, ''))
                self.assertIn(extra[0], result[2])
                query.assert_not_called()
        self.assertEqual([path.name for path in self.repo.iterdir()], ['.columbus.json'])

    def test_legacy_text_pretty_keeps_invalid_repository_error_precedence(self):
        self.repo = self.repo / 'does-not-exist'
        with patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')), \
                patch('columbus.source_calls.source_calls_archive') as query:
            result = self.invoke('--call-sites', '--call-table', '--format', 'text', '--pretty')
        self.assertEqual(result, (2, '', 'columbus: --repo must be an existing local repository directory\n'))
        query.assert_not_called()

    def test_query_or_serializer_failure_has_no_partial_stdout(self):
        message = 'bad\x1b[31m\npath\u2028'
        for where in ('query', 'serializer'):
            with self.subTest(where=where), \
                    patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')), \
                    patch('columbus.source_calls.source_calls_archive', return_value={},
                          side_effect=ValueError(message) if where == 'query' else None), \
                    patch('columbus.source_calls.source_calls_json', side_effect=ValueError(message)):
                result = self.invoke('--call-sites', '--call-table')
            self.assertEqual(result, (2, '', 'columbus: ' + json.dumps(message, ensure_ascii=True)[1:-1] + '\n'))

    def test_incomplete_archive_has_no_partial_json_or_index(self):
        for codec in ('gzip', 'xz'):
            artifact, _ = self.fixture(codec, footer=False)
            with patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')):
                result = self.invoke('--call-sites', '--call-table', artifact=artifact)
            self.assertEqual(result[:2], (2, ''))
            self.assertTrue(result[2].startswith('columbus: '))
        self.assertFalse((self.repo / '.columbus').exists())

    def test_unflagged_json_and_existing_text_table_keep_exact_serializer_contracts(self):
        from columbus.source_calls import source_calls_archive, source_calls_json, source_calls_text
        artifact, _ = self.fixture()
        expected = source_calls_archive(artifact, ['outer'], self.repo, budget_bytes=64000)
        for form in ('json', 'text'):
            with patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')):
                result = self.invoke('--call-sites', '--format', form, '--budget-bytes', '64000', artifact=artifact)
            render = source_calls_json if form == 'json' else source_calls_text
            self.assertEqual(result, (0, render(expected), ''))
            if form == 'json':
                self.assertNotIn('format', json.loads(result[1])['call_sites'])
        result = self.invoke('--call-sites', '--call-table', '--format', 'text',
                             '--budget-bytes', '64000', artifact=artifact)
        self.assertEqual(result, (0, source_calls_text(expected, call_table=True), ''))
        self.assertIn('"format":"columbus-call-table/v1"', result[1])


if __name__ == '__main__':
    unittest.main()
