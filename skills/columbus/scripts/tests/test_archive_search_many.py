"""Batched discovery preserves ranked ambiguity and validates one full archive."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import gzip
import hashlib
import io
import json
import lzma
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from columbus import archive as archive_module
from columbus.archive import archive, search_archive, search_archive_many, source_archive
from columbus.cli import main
from columbus.index import RepositoryIndex, compact
from columbus.presentation import archive_search_many_output, archive_search_text


class ArchiveSearchManyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.consumer = self.root / 'consumer'
        self.consumer.mkdir()
        self.serial = 0

    @staticmethod
    def node(path, name, *, kind='function', language='javascript', qualname=None, **extra):
        data = dict(id=path + ('::module' if kind == 'module' else f'::{name}:{kind}'),
                    path=path, name=name, qualname=qualname or name, kind=kind,
                    language=language, start_line=1, end_line=1, fidelity='heuristic',
                    signature=f'function {name}()')
        data.update(extra)
        return dict(record='node', data=data)

    def records(self):
        return [
            self.node('lib/buildURL.js', 'buildURL', kind='module'),
            self.node('lib/buildURL.js', 'buildURL'),
            self.node('lib/buildURL.js', 'encode'),
            self.node('src/a.py', 'target', language='python', module='one.encoding',
                      fidelity='ast', partial=False),
            self.node('src/b.py', 'target', language='python', module='two.encoding',
                      fidelity='ast', partial=True),
            self.node('tests/other.py', 'target', language='python', module='test.other'),
        ]

    @staticmethod
    def complete(nodes):
        paths = sorted({row['data']['path'] for row in nodes})
        files = [dict(record='file', data=dict(path=path, size=0,
                    hash=hashlib.sha256(path.encode()).hexdigest())) for path in paths]
        records = files + nodes + [dict(record='diagnostic', data=dict(message='fixture'))]
        counts = dict(files=len(files), nodes=len(nodes), scopes=0, edges=0,
                      references=0, imports=0, diagnostics=1)
        return [dict(record='manifest', data=dict(format='columbus-graph', version=1,
                    revision='fixture-revision'))] + records + [dict(record='end', data=counts)]

    def emit(self, rows, codec='gzip'):
        self.serial += 1
        path = self.root / f'archive-{self.serial}.{codec}'
        payload = ''.join(compact(row) + '\n' for row in rows).encode('utf-8')
        path.write_bytes(gzip.compress(payload, mtime=0) if codec == 'gzip' else lzma.compress(payload))
        return path

    def cli(self, artifact, queries, *arguments):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            status = main(['archive-search', *queries, '--input', str(artifact),
                           '--repo', str(self.consumer), *arguments])
        return status, output.getvalue(), error.getvalue()

    def test_batch_matches_independent_searches_in_one_full_scan(self):
        queries = ['target', 'buildURL', 'missing', 'encoding.target', 'one.encoding.target', 'TARGET']
        for codec in ('gzip', 'xz'):
            artifact = self.emit(self.complete(self.records()), codec)
            for filters in ({}, {'path': 'src/*'}, {'language': 'python'},
                            {'path': 'SRC/*', 'language': 'Python'}):
                expected = [search_archive(artifact, query, limit=2, budget_bytes=64000, **filters)
                            for query in queries]
                with patch('columbus.archive._validated_rows', wraps=archive_module._validated_rows) as scans, \
                        patch('columbus.archive._compressed_reader', wraps=archive_module._compressed_reader) as readers, \
                        patch('columbus.archive.search_archive', side_effect=AssertionError('single-query fallback')), \
                        patch('columbus.archive._search_archive', side_effect=AssertionError('repeated scan')):
                    actual = search_archive_many(artifact, queries, limit=2, budget_bytes=64000, **filters)
                self.assertEqual(scans.call_count, 1)
                self.assertEqual(readers.call_count, 1)
                self.assertEqual(actual['format'], 'columbus-archive-search-batch/v1')
                self.assertEqual(actual['results'], [{key: item[key] for key in (
                    'query', 'items', 'matched_nodes', 'truncated')} for item in expected])
                for key in ('revision', 'freshness', 'semantic_complete', 'diagnostic_count', 'source_policy'):
                    self.assertEqual(actual[key], expected[0][key])
                self.assertIn('source not checked', actual['freshness'])
                self.assertFalse(actual['semantic_complete'])
                self.assertEqual(actual.get('path_filter'), filters.get('path'))
                self.assertEqual(actual.get('language_filter'), filters.get('language'))
        self.assertEqual(list(self.consumer.iterdir()), [])

    def test_single_cli_keeps_original_json_text_and_budget_behavior(self):
        artifact = self.emit(self.complete(self.records()))
        for fmt in ('json', 'text'):
            for limit in (1, 50):
                expected = search_archive(artifact, 'target', limit=limit, budget_bytes=2048,
                                          path='src/*', language='python', output_format=fmt)
                encoded = compact(expected) + '\n' if fmt == 'json' else archive_search_text(expected)
                with patch('columbus.archive.search_archive_many', side_effect=AssertionError('single changed')):
                    code, output, error = self.cli(artifact, ['target'], '--format', fmt,
                        '--limit', str(limit), '--budget-bytes', '2048', '--path', 'src/*', '--language', 'python')
                self.assertEqual((code, output, error), (0, encoded, ''))
        self.assertFalse((self.consumer / '.columbus').exists())

    def test_same_name_function_module_stays_ambiguous_even_with_limit_one(self):
        path = 'lib/buildURL.js'
        body = b'function buildURL() {}\n'
        source = self.consumer / path
        source.parent.mkdir()
        source.write_bytes(body)
        rows = self.complete(self.records()[:2])
        rows[1]['data'].update(hash=hashlib.sha256(body).hexdigest(), size=len(body))
        artifact = self.emit(rows)
        complete = search_archive_many(artifact, ['buildURL', 'missing'])
        first, missing = complete['results']
        self.assertEqual({item['kind'] for item in first['items']}, {'function', 'module'})
        self.assertEqual(first['matched_nodes'], 2)
        self.assertFalse(first['truncated'])
        self.assertEqual(missing, dict(query='missing', items=[], matched_nodes=0, truncated=False))
        limited = search_archive_many(artifact, ['buildURL', 'missing'], limit=1)['results'][0]
        self.assertEqual(limited['items'], first['items'][:1])
        self.assertEqual(limited['matched_nodes'], 2)
        self.assertTrue(limited['truncated'])
        with patch('columbus.sync_state.read_stable', side_effect=AssertionError('ambiguous source read')):
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                source_archive(artifact, 'buildURL', self.consumer)
        exact = path + '::buildURL:function'
        self.assertEqual(source_archive(artifact, exact, self.consumer)['target'], exact)

    def test_query_and_option_errors_are_rejected_before_open(self):
        invalid_queries = [[], ['one'], ['same', 'same'], ['x' * 513, 'two'], ['', 'two'],
                           'one two', ['one', None], ['one', True], ['one', []], list(map(str, range(17)))]
        invalid_options = [dict(limit=value) for value in (0, 51, True, 1.5, '5')]
        invalid_options += [dict(budget_bytes=value) for value in (2047, 64001, True, 2048.0)]
        invalid_options += [dict(output_format=value) for value in ('other', [], None, 1)]
        for key in ('path', 'language'):
            invalid_options += [{key: value} for value in ('', True, 1, '\0')]
        with patch('pathlib.Path.open', side_effect=AssertionError('invalid request opened archive')):
            for queries in invalid_queries:
                with self.subTest(queries=queries), self.assertRaises(ValueError):
                    search_archive_many('unused', queries)
            for options in invalid_options:
                with self.subTest(options=options), self.assertRaises(ValueError):
                    search_archive_many('unused', ['one', 'two'], **options)

    def test_literal_case_whitespace_and_maximum_query_count(self):
        artifact = self.emit(self.complete(self.records()))
        queries = ['target', 'TARGET', 'target '] + [f'missing-{i}' for i in range(13)]
        result = search_archive_many(artifact, tuple(queries), limit=1, budget_bytes=64000)
        self.assertEqual([group['query'] for group in result['results']], queries)
        self.assertEqual(result['results'][2]['matched_nodes'], 0)
        for query, group in zip(queries, result['results']):
            single = search_archive(artifact, query, limit=1)
            self.assertEqual(group['items'], single['items'])

    def test_whole_batch_exact_rendered_budget_and_lossless_controls(self):
        controls = '\0\n\x1b\x7f\x80\x85\x9f\u2028\u2029'
        nodes = [self.node(f'lib/한글-{i}.js', f'target_{i}',
                           signature='한글😀' * 50 + controls) for i in range(4)]
        artifact = self.emit(self.complete(nodes))
        queries = ['target', '한글']
        for fmt in ('json', 'text'):
            result = search_archive_many(artifact, queries, budget_bytes=64000, output_format=fmt)
            output = archive_search_many_output(result, fmt)
            size = len(output.encode('utf-8'))
            self.assertGreater(size, 2048)
            self.assertTrue(output.endswith('\n'))
            self.assertFalse(any(ord(char) < 32 or 127 <= ord(char) <= 159 or char in '\u2028\u2029'
                                 for char in output.replace('\n', '')))
            if fmt == 'json':
                self.assertEqual(json.loads(output), result)
            else:
                lines = output.splitlines()
                self.assertEqual(json.loads(lines[1][9:]), {k: v for k, v in result.items() if k != 'results'})
                self.assertEqual([json.loads(line[7:]) for line in lines[2:]], result['results'])
            self.assertEqual(search_archive_many(artifact, queries, budget_bytes=size, output_format=fmt), result)
            with self.assertRaisesRegex(ValueError, 'complete archive-search batch'):
                search_archive_many(artifact, queries, budget_bytes=size - 1, output_format=fmt)
            code, stdout, stderr = self.cli(artifact, queries, '--format', fmt, '--budget-bytes', str(size - 1))
            self.assertEqual((code, stdout), (2, ''))
            self.assertIn('split queries', stderr)

    def test_every_query_can_be_empty_without_hiding_archive_failure(self):
        rows = self.complete(self.records())
        for codec in ('gzip', 'xz'):
            artifact = self.emit(rows, codec)
            result = search_archive_many(artifact, ['none', 'absent'], path='NO/*', language='missing')
            self.assertTrue(all(group['items'] == [] and group['matched_nodes'] == 0
                                and not group['truncated'] for group in result['results']))
            broken = self.emit(rows[:-1], codec)
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                search_archive_many(broken, ['none', 'absent'], path='NO/*', language='missing')

    def test_late_archive_and_compression_errors_never_emit_partial_stdout(self):
        rows = self.complete(self.records())
        for codec in ('gzip', 'xz'):
            wrong_counts = deepcopy(rows)
            wrong_counts[-1]['data']['nodes'] += 1
            bad_rows = [rows[:-1], wrong_counts, rows + [self.records()[0]],
                        rows[:-1] + [dict(record='unknown', data={}), rows[-1]]]
            artifacts = [self.emit(value, codec) for value in bad_rows]
            valid = self.emit(rows, codec)
            truncated = self.root / f'trailer-{codec}'
            truncated.write_bytes(valid.read_bytes()[:-4])
            artifacts.append(truncated)
            for artifact in artifacts:
                with self.subTest(codec=codec, artifact=artifact.name):
                    with self.assertRaises(ValueError):
                        search_archive_many(artifact, ['target', 'buildURL'], limit=1)
                    code, output, error = self.cli(artifact, ['target', 'buildURL'], '--limit', '1')
                    self.assertEqual((code, output), (2, ''))
                    self.assertNotIn('Traceback', error)
        deflate = self.root / 'bad-deflate.gz'
        deflate.write_bytes(bytes.fromhex('1f8b08000000000002ff07') + b'\0' * 8)
        with self.assertRaises(ValueError):
            search_archive_many(deflate, ['target', 'buildURL'])
        self.assertEqual(self.cli(deflate, ['target', 'buildURL'])[:2], (2, ''))

    def test_candidate_retention_is_capped_with_late_best_hits_and_file_rows(self):
        nodes = [self.node(f'lib/{i:03}.js', f'target_{i:03}') for i in reversed(range(90))]
        nodes += [self.node('lib/target.js', 'target')]
        rows = self.complete(nodes)
        # File records are deliberately after nodes; selected hashes must still bind.
        records = rows[1:-1]
        reordered = [rows[0]] + [r for r in records if r['record'] != 'file']
        reordered += [r for r in records if r['record'] == 'file'] + [rows[-1]]
        artifact = self.emit(reordered)
        previous = sys.gettrace()
        observed = []

        def trace(frame, event, arg):
            if frame.f_code is search_archive_many.__code__ and event == 'line':
                selected = frame.f_locals.get('selected')
                if selected is not None:
                    observed.append(max(map(len, selected)))
            return trace

        try:
            sys.settrace(trace)
            result = search_archive_many(artifact, ['target', 'target_'], limit=3, budget_bytes=64000)
        finally:
            sys.settrace(previous)
        self.assertTrue(observed)
        self.assertLessEqual(max(observed), 3)
        for query, group in zip(['target', 'target_'], result['results']):
            expected = search_archive(artifact, query, limit=3, budget_bytes=64000)
            self.assertEqual(group['items'], expected['items'])
            self.assertEqual(group['matched_nodes'], expected['matched_nodes'])
        self.assertEqual(result['results'][0]['items'][0]['name'], 'target')

    def test_malformed_late_matching_candidate_is_checked_after_limit_is_full(self):
        nodes = [self.node('lib/a.js', 'target'), self.node('lib/z.js', 'target_z', signature=None)]
        artifact = self.emit(self.complete(nodes))
        with self.assertRaises(ValueError):
            search_archive(artifact, 'target', limit=1)
        with self.assertRaises(ValueError):
            search_archive_many(artifact, ['target', 'missing'], limit=1)
        self.assertEqual(self.cli(artifact, ['target', 'missing'], '--limit', '1')[:2], (2, ''))

    def test_cli_batch_rejects_index_telemetry_and_pretty_without_constructing_index(self):
        artifact = self.emit(self.complete(self.records()))
        with patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('batch accessed index')):
            for options in (['--db', str(self.root / 'missing.sqlite')], ['--telemetry', ''],
                            ['--telemetry', str(self.root / 'log.jsonl')], ['--pretty']):
                self.assertEqual(self.cli(artifact, ['target', 'buildURL'], *options)[:2], (2, ''))
                output, error = io.StringIO(), io.StringIO()
                with redirect_stdout(output), redirect_stderr(error):
                    code = main([*options, '--repo', str(self.consumer), 'archive-search',
                                 'target', 'buildURL', '--input', str(artifact)])
                self.assertEqual((code, output.getvalue()), (2, ''))
            for fmt in ('json', 'text'):
                code, output, error = self.cli(artifact, ['target', 'missing'], '--format', fmt)
                expected = search_archive_many(artifact, ['target', 'missing'], output_format=fmt)
                self.assertEqual((code, output, error), (0, archive_search_many_output(expected, fmt), ''))
        self.assertEqual(list(self.consumer.iterdir()), [])

    def test_cli_escapes_untrusted_errors_and_rejects_duplicates(self):
        artifact = self.emit(self.complete(self.records()))
        code, output, error = self.cli(artifact, ['target', 'target'])
        self.assertEqual((code, output), (2, ''))
        self.assertIn('exact duplicates', error)
        message = 'bad\n\x00\x1b\x7f\x80\x9f\u2028\u2029path'
        with patch('columbus.archive.search_archive_many', side_effect=ValueError(message)):
            code, output, error = self.cli(artifact, ['target', 'missing'])
        self.assertEqual((code, output), (2, ''))
        self.assertEqual(json.loads('"' + error.removeprefix('columbus: ').removesuffix('\n') + '"'), message)
        self.assertFalse(any(ord(char) < 32 or 127 <= ord(char) <= 159 or char in '\u2028\u2029'
                             for char in error[:-1]))

    def test_exported_gzip_xz_relocated_subprocess_uses_this_engine_without_index(self):
        producer = self.root / 'producer'
        producer.mkdir()
        (producer / 'small.py').write_bytes(b'def first(): pass\ndef second(): pass\n')
        index = RepositoryIndex(producer / '.columbus/index.sqlite')
        index.refresh(producer)
        for codec in ('gzip', 'xz'):
            artifact = self.root / f'exported.{codec}'
            archive(index, artifact, codec)
            environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
            command = [sys.executable, '-B', '-m', 'columbus', '--repo', str(self.consumer),
                       'archive-search', 'first', 'second', 'absent', '--input', str(artifact)]
            completed = subprocess.run(command, cwd=self.consumer, env=environment,
                                       capture_output=True, timeout=15)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            expected = search_archive_many(artifact, ['first', 'second', 'absent'])
            self.assertEqual(completed.stdout, archive_search_many_output(expected).encode('utf-8'))
            self.assertEqual(completed.stderr, b'')
        self.assertEqual(list(self.consumer.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
