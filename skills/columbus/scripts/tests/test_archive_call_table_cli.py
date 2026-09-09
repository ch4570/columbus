"""Table selection is explicit, format-bound and read-only before any I/O."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from columbus.cli import main
import test_archive_source_calls as fixtures


class CallTableCliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.repo = Path(directory.name).resolve()
        (self.repo / '.columbus.json').write_bytes(b'{invalid configuration')

    def invoke(self, *options, global_options=(), queries=('First', 'Second'), artifact='unopened.xz'):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main([*global_options, 'archive-source', *queries,
                         '--input', str(artifact), '--repo', str(self.repo), *options])
        return code, output.getvalue(), error.getvalue()

    def test_selected_table_passes_identical_options_to_budgeting_and_renderer(self):
        packet = {'sentinel': 'unchanged'}
        with patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')), \
                patch('columbus.source_calls.source_calls_archive', return_value=packet) as query, \
                patch('columbus.source_calls.source_calls_text', return_value='exact table\n') as render:
            result = self.invoke('--call-table', '--format', 'text', '--call-sites',
                                 '--overloads', '--offset', '3', '--limit', '8', '--budget-bytes', '9000')
        self.assertEqual(result, (0, 'exact table\n', ''))
        query.assert_called_once_with('unopened.xz', ['First', 'Second'], self.repo, 8, 9000, 3,
                                      output_format='text', overloads=True, call_table=True)
        render.assert_called_once_with(packet, call_table=True)
        self.assertEqual([item.name for item in self.repo.iterdir()], ['.columbus.json'])

    def test_requires_source_calls_before_any_reader(self):
        for options in (('--call-table',), ('--call-table', '--format', 'text'),
                        ('--call-table', '--format', 'json')):
            with self.subTest(options=options), \
                    patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')), \
                    patch('columbus.source_calls.source_calls_archive') as query, \
                    patch('columbus.archive.source_archive_many') as legacy:
                code, output, error = self.invoke(*options)
            self.assertEqual((code, output), (2, ''))
            self.assertIn('--call-table requires --call-sites', error)
            query.assert_not_called()
            legacy.assert_not_called()

    def test_unsupported_global_and_subcommand_options_do_not_open_source_or_index(self):
        for extra in (('--db', ''), ('--db', 'existing.sqlite'),
                      ('--telemetry', ''), ('--telemetry', 'events.jsonl'), ('--pretty',)):
            for placement in ('global', 'subcommand'):
                with self.subTest(extra=extra, placement=placement), \
                        patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')), \
                        patch('columbus.source_calls.source_calls_archive') as query:
                    selected = ('--call-sites', '--format', 'text', '--call-table')
                    result = (self.invoke(*selected, global_options=extra) if placement == 'global'
                              else self.invoke(*selected, *extra))
                self.assertEqual(result[:2], (2, ''))
                self.assertIn(extra[0], result[2])
                query.assert_not_called()
        self.assertEqual([item.name for item in self.repo.iterdir()], ['.columbus.json'])

    def test_table_failure_has_no_partial_stdout_and_escapes_untrusted_error(self):
        message = 'bad\x1b[31m\npath\u2028'
        with patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')), \
                patch('columbus.source_calls.source_calls_archive', side_effect=ValueError(message)):
            result = self.invoke('--call-sites', '--call-table', '--format', 'text')
        self.assertEqual(result, (2, '', 'columbus: ' + json.dumps(message, ensure_ascii=True)[1:-1] + '\n'))

    def test_real_archive_table_preserves_duplicate_calls_and_exact_rendered_budget(self):
        from columbus.source_calls import source_calls_archive, source_calls_text

        fixture = fixtures.ArchiveSourceCallsTests()
        body = fixture._fixture(self.repo)
        body.append(next(row for row in body if row['record'] == 'edge'))
        artifact = fixture._write(self.repo, body, codec='xz')
        expected = source_calls_archive(artifact, ['outer'], self.repo, budget_bytes=64000)
        selected = ('--call-sites', '--format', 'text', '--call-table')
        with patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')):
            code, output, error = self.invoke(*selected, '--budget-bytes', '64000',
                                              queries=('outer',), artifact=artifact)
        self.assertEqual((code, error), (0, ''))
        self.assertEqual(output.split('call_sites ', 1)[0],
                         source_calls_text(expected).split('call_sites ', 1)[0])
        files, nodes, edges, section = {}, {}, [], None
        for line in output.split('\n'):
            if line.startswith('call_sites '):
                metadata = json.loads(line.removeprefix('call_sites '))
            elif line.startswith('call_tables '):
                marker = json.loads(line.removeprefix('call_tables '))
            elif line.startswith('call_files '):
                section = 'files'
            elif line.startswith('call_nodes '):
                section = 'nodes'
            elif line.startswith('call_edges '):
                section = 'edges'
            elif section and line.startswith('['):
                row = json.loads(line)
                if section == 'files':
                    self.assertEqual(row[0], len(files))
                    files[row[0]] = row[1:]
                elif section == 'nodes':
                    self.assertEqual(row[0], len(nodes))
                    path, source_hash = files[row[1]]
                    nodes[row[0]] = dict(row[2], path=path, source_hash=source_hash)
                else:
                    path, _ = files[row[2]]
                    edges.append(dict(row[3], source=nodes[row[0]]['id'],
                                      target=nodes[row[1]]['id'], path=path))
        self.assertEqual(marker, {'format': 'columbus-call-table/v1', 'index_scope': 'this packet'})
        self.assertEqual(dict(metadata, nodes=list(nodes.values()), edges=edges), expected['call_sites'])
        self.assertEqual(len(edges), 6)
        size = len(output.encode('utf-8'))
        self.assertGreaterEqual(size, 2048)
        with patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')):
            exact = self.invoke(*selected, '--budget-bytes', str(size), queries=('outer',), artifact=artifact)
            smaller = self.invoke(*selected, '--budget-bytes', str(size - 1), queries=('outer',), artifact=artifact)
        self.assertEqual(exact, (0, output, ''))
        self.assertLessEqual(len(smaller[1].encode('utf-8')), size - 1)
        self.assertNotEqual(smaller[1], output)
        self.assertIn(smaller[0], (0, 2))
        self.assertFalse((self.repo / '.columbus').exists())

    def test_real_incomplete_archive_does_not_emit_partial_table(self):
        fixture = fixtures.ArchiveSourceCallsTests()
        artifact = fixture._write(self.repo, fixture._fixture(self.repo), footer=False)
        with patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')):
            code, output, error = self.invoke('--call-sites', '--call-table', '--format', 'text',
                                              queries=('outer',), artifact=artifact)
        self.assertEqual((code, output), (2, ''))
        self.assertTrue(error.startswith('columbus: '))
        self.assertFalse((self.repo / '.columbus').exists())


if __name__ == '__main__':
    unittest.main()
