"""Convenient exploration preserves budgets, caller-owned sessions, and read-only stats."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from repoatlas.cli import main
from repoatlas.index import RepositoryIndex


class ExplorationSessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'repository with spaces'
        self.root.mkdir()
        (self.root / 'billing.py').write_text('def refund(amount):\n    return amount\n\n'
                                             'def cancel():\n    return refund(10)\n')

    def call(self, *arguments, root=None):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            status = main(['--repo', str(root or self.root), *arguments])
        return status, output.getvalue(), error.getvalue()

    def test_no_arguments_show_successful_guide_without_an_index(self):
        output = io.StringIO()
        with patch.object(RepositoryIndex, 'refresh', side_effect=AssertionError('unexpected indexing')), \
                patch.object(RepositoryIndex, 'status', side_effect=AssertionError('unexpected index read')), \
                contextlib.redirect_stdout(output):
            self.assertEqual(main([]), 0)
        self.assertIn('repoatlas explore', output.getvalue())
        self.assertIn('repoatlas stats', output.getvalue())
        self.assertLess(len(output.getvalue()), 1000)
        self.assertFalse((self.root / '.repoatlas').exists())

    def test_explore_defaults_to_text_map_or_source_with_2000_estimated_tokens(self):
        with patch.object(RepositoryIndex, '_source', side_effect=AssertionError('map read source')):
            status, outline, error = self.call('explore')
        self.assertEqual(status, 0, error)
        self.assertIn('repoatlas map ', outline)
        self.assertIn('/6000 estimated_tokens=', outline)
        self.assertIn('source_bytes=0', outline)
        status, source, error = self.call('explore', 'refund')
        self.assertEqual(status, 0, error)
        self.assertIn('repoatlas snippets ', source)
        self.assertIn('return amount', source)
        self.assertLessEqual(len(source.encode('utf-8')), 6000)
        self.assertFalse((self.root / '.repoatlas/sessions').exists())

    def test_explore_explicit_budgets_and_filters_override_defaults(self):
        self.call('sync')
        with patch.object(RepositoryIndex, 'refresh', side_effect=AssertionError('snapshot synchronized')):
            for query in ([], ['refund']):
                for flags, expected_bytes, expected_tokens in (
                        ([], 6000, 2000), (['--budget-tokens', '3000'], 9000, 3000),
                        (['--budget-bytes', '2048'], 2048, None),
                        (['--budget-bytes', '2048', '--budget-tokens', '2000'], 2048, 2000)):
                    status, output, error = self.call('explore', *query, '--snapshot', '--format', 'json',
                        '--path', 'billing*', '--language', 'python', *flags)
                    self.assertEqual(status, 0, error)
                    packet = json.loads(output)
                    self.assertEqual(packet['budget_bytes'], expected_bytes)
                    self.assertEqual(packet['budget_tokens'], expected_tokens)
                    self.assertEqual(packet['used_bytes'], len(output.encode('utf-8')))
                    self.assertLessEqual(packet['used_bytes'], expected_bytes)
                    self.assertTrue(packet['items'])
                    self.assertTrue(all(item['path'] == 'billing.py' for item in packet['items']))
            status, output, error = self.call('explore', 'refund', '--snapshot', '--format', 'json', '--language', 'ruby')
            self.assertEqual(status, 0, error)
            self.assertEqual(json.loads(output)['items'], [])

    def test_existing_context_keeps_json_default_and_accepts_the_same_session(self):
        status, first, error = self.call('context', 'refund', '--session', 'checkout-task')
        self.assertEqual(status, 0, error)
        self.assertTrue(json.loads(first)['items'])
        status, second, error = self.call('explore', 'refund', '--session', 'checkout-task', '--format', 'json')
        self.assertEqual(status, 0, error)
        self.assertEqual(json.loads(second)['items'], [])
        self.assertGreater(json.loads(second)['seen_candidates'], 0)

    def test_session_automatically_returns_changed_source_and_updates_its_receipt(self):
        status, output, error = self.call('explore', 'refund', '--session', 'checkout-task', '--format', 'json')
        self.assertEqual(status, 0, error)
        before = json.loads(output)
        source = self.root / 'billing.py'
        source.write_text(source.read_text().replace('return amount', 'return amount + 1'))
        status, output, error = self.call('explore', 'refund', '--session', 'checkout-task', '--format', 'json')
        self.assertEqual(status, 0, error)
        after = json.loads(output)
        self.assertNotEqual(before['revision'], after['revision'])
        self.assertIn('return amount + 1', output)
        self.assertNotEqual(before['items'][0]['source_hash'], after['items'][0]['source_hash'])
        receipt = json.loads((self.root / '.repoatlas/sessions/checkout-task/receipt.json').read_text())
        self.assertEqual(receipt['files']['billing.py']['source_hash'], after['items'][0]['source_hash'])

    def test_session_records_only_delivered_spans_and_exact_response_measurements(self):
        (self.root / 'wide.py').write_text('def wide(): return "' + '한글' * 1200 + 'LAST_PART"\n', encoding='utf-8')
        outputs, spans, bodies = [], set(), []
        for _ in range(30):
            status, output, error = self.call('explore', 'wide', '--session', 'wide-task', '--path', 'wide.py',
                                              '--format', 'json', '--budget-bytes', '2048')
            self.assertEqual(status, 0, error)
            packet = json.loads(output)
            self.assertLessEqual(len(output.encode('utf-8')), 2048)
            outputs.append(output)
            for item in packet['items']:
                current = set(range(item['source_start_offset'], item['source_end_offset']))
                self.assertFalse(current & spans)
                spans.update(current)
                bodies.append(item['source'])
            if not packet['items']:
                self.assertGreater(packet['seen_candidates'], 0)
                break
        else:
            self.fail('Named session stalled before delivering the source remainder')
        self.assertIn('LAST_PART', ''.join(bodies))
        directory = self.root / '.repoatlas/sessions/wide-task'
        self.assertEqual({path.name for path in directory.iterdir()}, {'receipt.json', 'queries.jsonl'})
        rows = [json.loads(line) for line in (directory / 'queries.jsonl').read_text().splitlines()]
        self.assertEqual([row['output_bytes'] for row in rows], [len(output.encode('utf-8')) for output in outputs])
        self.assertEqual([row['command'] for row in rows], ['context'] * len(rows))
        self.assertNotIn('LAST_PART', (directory / 'queries.jsonl').read_text())

    def test_stats_reads_existing_session_without_index_or_filesystem_writes(self):
        status, _, error = self.call('explore', 'refund', '--session', 'checkout-task')
        self.assertEqual(status, 0, error)
        for path in (self.root / '.repoatlas').glob('jvm-v2.sqlite*'):
            path.unlink()
        before = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        with patch.object(RepositoryIndex, 'refresh', side_effect=AssertionError('stats indexed')), \
                patch.object(RepositoryIndex, 'status', side_effect=AssertionError('stats read index')):
            status, output, error = self.call('stats', 'checkout-task')
            self.assertEqual(status, 0, error)
            self.assertIn('1 queries', output)
            status, output, error = self.call('stats', 'checkout-task', '--format', 'json')
            self.assertEqual(status, 0, error)
            self.assertEqual(json.loads(output)['queries'], 1)
        after = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        self.assertEqual(before, after)

    def test_missing_stats_do_not_create_session_or_index(self):
        status, output, error = self.call('stats', 'missing-task')
        self.assertEqual(status, 2, error)
        self.assertEqual(output, '')
        self.assertFalse((self.root / '.repoatlas').exists())

    def test_session_rejects_traversal_invalid_names_and_conflicting_options_before_sync(self):
        with patch.object(RepositoryIndex, 'refresh', side_effect=AssertionError('invalid session indexed')):
            for name in ('', '..', '../outside', 'a/b', 'a\\b', 'a:b', '-leading', '.hidden',
                         'name with spaces', '한글', 'CON', 'LPT1', 'x' * 65):
                for command in (['explore', 'refund', '--session=' + name], ['stats', '--', name]):
                    status, _, error = self.call(*command)
                    self.assertEqual(status, 2, (name, error))
            for command in (['explore', '--session', 'task'],
                            ['explore', 'refund', '--session', 'task', '--mode', 'signatures'],
                            ['context', 'refund', '--session', 'task', '--mode', 'signatures'],
                            ['context', 'refund', '--session', 'task', '--receipt', 'manual.json'],
                            ['explore', 'refund', '--session', 'task', '--telemetry', 'manual.jsonl'],
                            ['explore', 'refund', '--session', 'task', '--db', str(self.root / '.repoatlas/sessions/task/receipt.json')],
                            ['explore', 'refund', '--session', 'task', '--db', str(self.root / '.repoatlas/sessions/task/queries.jsonl')]):
                status, _, error = self.call(*command)
                self.assertEqual(status, 2, error)
        self.assertFalse((self.root / '.repoatlas').exists())

    def test_session_accepts_portable_names_at_both_length_boundaries(self):
        for name in ('a', 'Checkout-task_2', 'x' * 64):
            status, _, error = self.call('explore', 'refund', '--session', name)
            self.assertEqual(status, 0, error)
            self.assertTrue((self.root / '.repoatlas/sessions' / name / 'receipt.json').is_file())

    def test_session_parent_and_file_symlinks_cannot_escape_repository(self):
        outside = Path(self.temporary.name) / 'outside'
        outside.mkdir()
        marker = outside / 'keep.txt'
        marker.write_text('preserve')
        for number, target in enumerate(('.repoatlas', '.repoatlas/sessions', '.repoatlas/sessions/task',
                                          '.repoatlas/sessions/task/receipt.json', '.repoatlas/sessions/task/queries.jsonl')):
            root = Path(self.temporary.name) / f'case-{number}'
            root.mkdir()
            (root / 'source.py').write_text('def refund(): return 1\n')
            link = root / target
            link.parent.mkdir(parents=True, exist_ok=True)
            destination = marker if target.endswith(('.json', '.jsonl')) else outside
            try:
                link.symlink_to(destination, target_is_directory=destination.is_dir())
            except OSError:
                self.skipTest('Symlinks unavailable on this platform')
            for command in (['explore', 'refund', '--session', 'task'], ['stats', 'task']):
                status, output, error = self.call(*command, root=root)
                self.assertEqual(status, 2, error)
                self.assertEqual(output, '')
                self.assertIn('symlink', error)
            self.assertEqual({path.name for path in outside.iterdir()}, {'keep.txt'})
            self.assertEqual(marker.read_text(), 'preserve')

    def test_unrelated_receipt_or_telemetry_is_preserved(self):
        for filename in ('receipt.json', 'queries.jsonl'):
            directory = self.root / '.repoatlas/sessions' / filename.replace('.', '-')
            directory.mkdir(parents=True)
            path = directory / filename
            path.write_text('caller-owned unrelated data')
            status, output, error = self.call('explore', 'refund', '--session', directory.name)
            self.assertEqual(status, 2, error)
            self.assertEqual(output, '')
            self.assertEqual(path.read_text(), 'caller-owned unrelated data')
            self.assertEqual({entry.name for entry in directory.iterdir()}, {filename})

    def test_repository_runner_advertises_new_commands_without_a_runtime(self):
        runner = Path(__file__).resolve().parents[4] / 'run.py'
        if not runner.is_file():
            self.skipTest('The repository runner is available in the distribution source, not an installed skill')
        guide = subprocess.run([sys.executable, str(runner)], cwd=self.root, text=True, capture_output=True)
        self.assertEqual(guide.returncode, 0, guide.stderr)
        self.assertIn('explore checkout --session checkout-task', guide.stdout)
        help_result = subprocess.run([sys.executable, str(runner), '--help'], cwd=self.root, text=True, capture_output=True)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn('stats', help_result.stdout)
        self.assertFalse((self.root / '.repoatlas').exists())


if __name__ == '__main__':
    unittest.main()
