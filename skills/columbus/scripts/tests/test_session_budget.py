"""Named-session limits reject work before retrieval and preserve admitted usage."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from columbus.cli import main
from columbus.index import RepositoryIndex


class SessionBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'repository with spaces'
        self.root.mkdir()
        (self.root / 'billing.py').write_text(
            'def refund(amount):\n    return amount\n', encoding='utf-8')

    def call(self, *arguments, output=None):
        output = io.StringIO() if output is None else output
        error = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            try:
                status = main(['--repo', str(self.root), *arguments])
            except SystemExit as exc:
                status = exc.code
        return status, output.getvalue(), error.getvalue()

    def query(self, *arguments, name='task', query='refund', command='context', output=None):
        return self.call(command, query, '--session', name, *arguments, output=output)

    def directory(self, name='task'):
        return self.root / '.columbus/sessions' / name

    def state(self, name='task'):
        return json.loads((self.directory(name) / 'budget.json').read_text())

    def stats(self, name='task'):
        status, output, error = self.call('stats', name, '--format', 'json')
        self.assertEqual(status, 0, error)
        return json.loads(output)

    def assert_success(self, result):
        status, output, error = result
        self.assertEqual(status, 0, error)
        self.assertTrue(output)
        self.assertEqual(error, '')
        return output

    @contextlib.contextmanager
    def no_retrieval(self):
        with patch.object(RepositoryIndex, 'refresh', side_effect=AssertionError('unexpected sync')), \
                patch.object(RepositoryIndex, '_source', side_effect=AssertionError('unexpected source read')):
            yield

    def assert_rejected(self, result, status=3):
        code, output, error = result
        self.assertEqual(code, status, error)
        self.assertEqual(output, '')
        self.assertTrue(error)
        if status == 3:
            self.assertLessEqual(len(error.encode('utf-8')), 2048)

    def test_query_limit_is_inclusive_and_omitted_flags_reuse_it_before_sync(self):
        for command in ('context', 'explore'):
            with self.subTest(command=command):
                self.assert_success(self.query('--max-queries', '1', name=command, command=command))
                before = self.state(command)
                with self.no_retrieval():
                    self.assert_rejected(self.query(name=command, command=command))
                    self.assert_rejected(self.query('--snapshot', name=command, command=command))
                self.assertEqual(self.state(command), before)
                self.assertEqual(before['queries'], 1)
                self.assertFalse((self.directory(command) / '.budget.lock').exists())

    def test_limits_require_named_snippets_and_positive_integers_before_sync(self):
        invalid = []
        for flag in ('--max-queries', '--max-session-bytes', '--max-no-progress'):
            invalid.append(['context', 'refund', flag, '1'])
            for value in ('0', '-1', '1.5', 'not-a-number'):
                invalid.append(['context', 'refund', '--session', 'task', flag, value])
        invalid.extend([
            ['explore', '--max-queries', '1'],
            ['explore', '--session', 'task', '--max-queries', '1'],
            ['context', 'refund', '--session', 'task', '--mode', 'signatures', '--max-queries', '1'],
            ['context', 'refund', '--session', 'task', '--receipt', 'manual.json', '--max-queries', '1'],
            ['context', 'refund', '--session', 'task', '--telemetry', 'manual.jsonl', '--max-queries', '1'],
        ])
        with self.no_retrieval():
            for arguments in invalid:
                with self.subTest(arguments=arguments):
                    self.assert_rejected(self.call(*arguments), status=2)
        self.assertFalse((self.root / '.columbus').exists())

    def test_byte_limit_too_small_for_admission_never_reads_source(self):
        with self.no_retrieval():
            self.assert_rejected(self.query('--max-session-bytes', '1'))
        state = self.state()
        self.assertEqual((state['queries'], state['output_bytes']), (0, 0))
        self.assertFalse((self.directory() / 'receipt.json').exists())
        self.assertFalse((self.directory() / 'queries.jsonl').exists())
        self.assertFalse((self.directory() / '.budget.lock').exists())

    def test_cumulative_byte_limit_keeps_successful_output_within_remaining_bytes(self):
        first = self.assert_success(self.query('--max-session-bytes', '2048', '--budget-bytes', '2048'))
        self.assertLessEqual(len(first.encode('utf-8')), 2048)
        self.assertEqual(self.state()['output_bytes'], len(first.encode('utf-8')))
        self.assertLess(self.stats()['session_budget']['remaining_bytes'], 2048)
        before = self.state()
        with self.no_retrieval():
            self.assert_rejected(self.query('--budget-bytes', '64000'))
        self.assertEqual(self.state(), before)

    def test_exactly_2048_remaining_bytes_admits_one_more_response(self):
        reference = self.assert_success(self.query('--budget-bytes', '2048', name='reference'))
        limit = len(reference.encode('utf-8')) + 2048
        first = self.assert_success(self.query('--max-session-bytes', str(limit), '--budget-bytes', '2048'))
        self.assertEqual(len(first.encode('utf-8')), len(reference.encode('utf-8')))
        self.assertEqual(self.stats()['session_budget']['remaining_bytes'], 2048)
        second = self.assert_success(self.query('--budget-bytes', '2048'))
        self.assertEqual(json.loads(second)['budget_bytes'], 2048)
        total = len(first.encode('utf-8')) + len(second.encode('utf-8'))
        self.assertEqual(self.state()['output_bytes'], total)
        self.assertLessEqual(total, limit)
        self.assertEqual(self.state()['queries'], 2)
        self.assertLess(self.stats()['session_budget']['remaining_bytes'], 2048)
        with self.no_retrieval():
            self.assert_rejected(self.query())

    def test_unicode_output_and_both_formats_use_exact_utf8_stdout_bytes(self):
        (self.root / 'billing.py').write_text(
            'def refund(amount):\n    return "환불 처리 😀", amount\n', encoding='utf-8')
        outputs = [self.assert_success(self.query(
            '--max-queries', '3', '--max-session-bytes', '40000', '--format', 'text'))]
        outputs.append(self.assert_success(self.query('--format', 'json')))
        self.assertIn('환불 처리 😀', outputs[0])
        self.assertGreater(len(outputs[0].encode('utf-8')), len(outputs[0]))
        summary = self.stats()
        exact_bytes = sum(len(output.encode('utf-8')) for output in outputs)
        self.assertEqual(summary['output_bytes'], exact_bytes)
        self.assertEqual(summary['session_budget']['output_bytes'], exact_bytes)
        self.assertEqual(summary['session_budget']['queries'], 2)
        self.assertEqual(summary['session_budget']['remaining_bytes'], 40000 - exact_bytes)
        self.assertEqual(summary['session_budget']['phase'], 'idle')
        self.assertEqual(summary['session_budget']['reserved_bytes'], 0)

    def test_repeating_identical_policy_is_allowed_but_any_change_is_rejected(self):
        self.assert_success(self.query('--max-queries', '3', '--max-no-progress', '2'))
        policy_path = self.directory() / 'budget-policy.json'
        policy_bytes = policy_path.read_bytes()
        self.assert_success(self.query('--max-queries', '3', '--max-no-progress', '2'))
        before = self.state()
        with self.no_retrieval():
            for flags in (('--max-queries', '4'), ('--max-queries', '2'),
                          ('--max-no-progress', '3'), ('--max-session-bytes', '40000')):
                with self.subTest(flags=flags):
                    self.assert_rejected(self.query(*flags), status=2)
        self.assertEqual(self.state(), before)
        self.assertEqual(policy_path.read_bytes(), policy_bytes)

    def test_exhausted_empty_result_increments_no_progress_and_then_blocks(self):
        self.assert_success(self.query('--max-no-progress', '1'))
        self.assertEqual(self.state()['no_progress'], 0)
        packet = json.loads(self.assert_success(self.query()))
        self.assertEqual(packet['items'], [])
        self.assertFalse(packet['receipt']['has_more'])
        self.assertEqual(self.state()['no_progress'], 1)
        with self.no_retrieval():
            self.assert_rejected(self.query(query='new-entry-point'))

    def test_source_progress_resets_the_consecutive_empty_streak(self):
        self.assert_success(self.query('--max-no-progress', '2', query='missing-symbol'))
        self.assertEqual(self.state()['no_progress'], 1)
        self.assert_success(self.query())
        self.assertEqual(self.state()['no_progress'], 0)
        self.assert_success(self.query(query='missing-symbol'))
        self.assertEqual(self.state()['no_progress'], 1)
        self.assert_success(self.query(query='another-missing-symbol'))
        self.assertEqual(self.state()['no_progress'], 2)
        with self.no_retrieval():
            self.assert_rejected(self.query())

    def test_empty_page_with_an_advancing_cursor_resets_no_progress(self):
        for number in range(65):
            (self.root / f'entry_{number:03}.py').write_text(
                f'def target():\n    return {number}\n', encoding='utf-8')
        for path in ('entry_0[0-3]?.py', 'entry_04[0-4].py'):
            self.assert_success(self.query('--max-no-progress', '2', '--path', path,
                                           '--budget-bytes', '64000', query='target'))
        self.assert_success(self.query(query='missing-symbol'))
        self.assertEqual(self.state()['no_progress'], 1)
        with patch('columbus.retrieval.CONTEXT_PAGE_LIMIT', 2):
            packet = json.loads(self.assert_success(self.query('--budget-bytes', '6000', query='target')))
        self.assertEqual(packet['items'], [])
        self.assertTrue(packet['receipt']['has_more'])
        self.assertEqual(self.state()['no_progress'], 0)
        self.assert_success(self.query(query='missing-symbol'))
        self.assertEqual(self.state()['no_progress'], 1)
        self.assert_success(self.query(query='another-missing-symbol'))
        with self.no_retrieval():
            self.assert_rejected(self.query(query='target'))

    def test_source_revision_changes_preserve_policy_queries_and_output_totals(self):
        first = self.assert_success(self.query('--max-queries', '2'))
        policy = (self.directory() / 'budget-policy.json').read_bytes()
        (self.root / 'billing.py').write_text(
            'def refund(amount):\n    return amount + 1\n', encoding='utf-8')
        second = self.assert_success(self.query())
        self.assertNotEqual(json.loads(first)['revision'], json.loads(second)['revision'])
        self.assertIn('return amount + 1', second)
        self.assertEqual((self.directory() / 'budget-policy.json').read_bytes(), policy)
        self.assertEqual(self.state()['queries'], 2)
        self.assertEqual(self.state()['output_bytes'], len(first.encode()) + len(second.encode()))
        with self.no_retrieval():
            self.assert_rejected(self.query())

    def test_revision_change_alone_does_not_reset_no_progress(self):
        self.assert_success(self.query('--max-no-progress', '2', query='missing-symbol'))
        (self.root / 'billing.py').write_text('def refund(amount): return amount + 2\n', encoding='utf-8')
        self.assert_success(self.query(query='missing-symbol'))
        self.assertEqual(self.state()['no_progress'], 2)
        with self.no_retrieval():
            self.assert_rejected(self.query())

    def test_failed_admitted_sync_consumes_query_and_stats_work_without_telemetry(self):
        with patch.object(RepositoryIndex, 'refresh', side_effect=RuntimeError('fixture sync failure')):
            self.assert_rejected(self.query('--max-queries', '1'), status=2)
        self.assertFalse((self.directory() / 'queries.jsonl').exists())
        self.assertFalse((self.directory() / '.budget.lock').exists())
        before = {path.name: path.read_bytes() for path in self.directory().iterdir()}
        with self.no_retrieval(), patch.object(RepositoryIndex, 'status', side_effect=AssertionError('index read')):
            summary = self.stats()
            self.assert_rejected(self.query())
        self.assertEqual(summary['queries'], 0)
        self.assertEqual(summary['session_budget']['queries'], 1)
        self.assertEqual(summary['session_budget']['output_bytes'], 0)
        self.assertEqual(summary['session_budget']['phase'], 'idle')
        self.assertEqual({path.name: path.read_bytes() for path in self.directory().iterdir()}, before)

    def test_failed_admitted_retrieval_consumes_a_query_and_releases_its_lock(self):
        with patch.object(RepositoryIndex, 'context', side_effect=RuntimeError('fixture retrieval failure')):
            self.assert_rejected(self.query('--max-queries', '2'), status=2)
        self.assertEqual(self.state()['queries'], 1)
        self.assertFalse((self.directory() / '.budget.lock').exists())
        self.assert_success(self.query())
        self.assertEqual(self.state()['queries'], 2)
        with self.no_retrieval():
            self.assert_rejected(self.query())

    def test_interrupted_output_stays_pending_and_future_queries_fail_closed(self):
        class InterruptedOutput(io.StringIO):
            def flush(self):
                raise OSError('fixture output interrupted after write')

        output = InterruptedOutput()
        status, rendered, error = self.query('--max-queries', '3', output=output)
        self.assertEqual(status, 2, error)
        self.assertTrue(rendered)
        before = self.state()
        self.assertEqual(before['phase'], 'pending')
        self.assertEqual(before['queries'], 1)
        self.assertEqual(before['reserved_bytes'], len(rendered.encode('utf-8')))
        self.assertFalse((self.directory() / '.budget.lock').exists())
        with self.no_retrieval():
            self.assert_rejected(self.query(), status=2)
        self.assertEqual(self.state(), before)

    def test_failed_receipt_save_keeps_delivered_response_pending_and_blocks_reuse(self):
        with patch('columbus.receipts.ReceiptFile.save', side_effect=OSError('fixture receipt save failure')):
            status, rendered, error = self.query('--max-queries', '3')
        self.assertEqual(status, 2, error)
        self.assertTrue(rendered)
        before = self.state()
        self.assertEqual(before['phase'], 'pending')
        self.assertEqual(before['queries'], 1)
        self.assertEqual(before['output_bytes'], 0)
        self.assertEqual(before['reserved_bytes'], len(rendered.encode('utf-8')))
        self.assertFalse((self.directory() / 'receipt.json').exists())
        self.assertFalse((self.directory() / '.budget.lock').exists())
        with self.no_retrieval():
            self.assert_rejected(self.query(), status=2)
        self.assertEqual(self.state(), before)

    def test_failed_telemetry_append_keeps_delivered_bytes_charged_and_allows_next_query(self):
        with patch('columbus.telemetry.TelemetryLog.append', side_effect=OSError('fixture telemetry failure')):
            status, first, error = self.query('--max-queries', '2')
        self.assertEqual(status, 2, error)
        self.assertTrue(first)
        before = self.state()
        self.assertEqual(before['phase'], 'idle')
        self.assertEqual(before['queries'], 1)
        self.assertEqual(before['output_bytes'], len(first.encode('utf-8')))
        self.assertEqual(before['reserved_bytes'], 0)
        self.assertTrue((self.directory() / 'receipt.json').exists())
        self.assertFalse((self.directory() / 'queries.jsonl').exists())
        self.assertFalse((self.directory() / '.budget.lock').exists())
        second = self.assert_success(self.query())
        self.assertEqual(json.loads(second)['items'], [])
        summary = self.stats()
        self.assertEqual(summary['queries'], 1)
        self.assertEqual(summary['session_budget']['queries'], 2)
        self.assertEqual(summary['session_budget']['output_bytes'],
                         len(first.encode('utf-8')) + len(second.encode('utf-8')))
        with self.no_retrieval():
            self.assert_rejected(self.query())

    def test_short_stdout_write_keeps_full_reservation_pending(self):
        class ShortOutput(io.StringIO):
            def write(self, value):
                return super().write(value[:max(1, len(value) // 2)])

        status, rendered, error = self.query('--max-queries', '3', output=ShortOutput())
        self.assertEqual(status, 2, error)
        self.assertTrue(rendered)
        before = self.state()
        self.assertEqual(before['phase'], 'pending')
        self.assertEqual(before['queries'], 1)
        self.assertEqual(before['output_bytes'], 0)
        self.assertGreater(before['reserved_bytes'], len(rendered.encode('utf-8')))
        self.assertFalse((self.directory() / 'receipt.json').exists())
        self.assertFalse((self.directory() / '.budget.lock').exists())
        with self.no_retrieval():
            self.assert_rejected(self.query(), status=2)
        self.assertEqual(self.state(), before)

    def test_corrupt_or_missing_budget_files_are_preserved_and_never_reset(self):
        for number, (filename, replacement) in enumerate((
                ('budget.json', b'{'), ('budget-policy.json', b'{}'),
                ('budget.json', None), ('budget-policy.json', None))):
            name = f'damage-{number}'
            with self.subTest(filename=filename, replacement=replacement):
                self.assert_success(self.query('--max-queries', '4', name=name))
                damaged = self.directory(name) / filename
                if replacement is None:
                    damaged.unlink()
                else:
                    damaged.write_bytes(replacement)
                before = {path.name: path.read_bytes() for path in self.directory(name).iterdir()}
                with self.no_retrieval():
                    self.assert_rejected(self.query(name=name), status=2)
                    self.assert_rejected(self.call('stats', name, '--format', 'json'), status=2)
                self.assertEqual({path.name: path.read_bytes() for path in self.directory(name).iterdir()}, before)

    def test_policy_ledger_mismatch_and_invalid_counters_fail_closed(self):
        changes = [('budget-policy.json', 'max_queries', 99),
                   ('budget.json', 'generation', '0' * 32),
                   ('budget.json', 'queries', -1),
                   ('budget.json', 'output_bytes', True),
                   ('budget.json', 'reserved_bytes', 1)]
        for number, (filename, key, value) in enumerate(changes):
            name = f'mismatch-{number}'
            with self.subTest(filename=filename, key=key):
                self.assert_success(self.query('--max-queries', '4', name=name))
                path = self.directory(name) / filename
                content = json.loads(path.read_text())
                content[key] = value
                path.write_text(json.dumps(content))
                before = path.read_bytes()
                with self.no_retrieval():
                    self.assert_rejected(self.query(name=name), status=2)
                self.assertEqual(path.read_bytes(), before)

    def test_receipt_changed_outside_budget_accounting_is_rejected_before_sync(self):
        self.assert_success(self.query('--max-queries', '4'))
        receipt = self.directory() / 'receipt.json'
        receipt.write_bytes(receipt.read_bytes() + b' ')
        before = self.state()
        with self.no_retrieval():
            self.assert_rejected(self.query(), status=2)
        self.assertEqual(self.state(), before)

    def test_revision_counter_must_match_the_saved_receipt_revision(self):
        self.assert_success(self.query('--max-queries', '4'))
        path = self.directory() / 'budget.json'
        content = json.loads(path.read_text())
        content['revision'] = 'tampered-but-well-typed-revision'
        path.write_text(json.dumps(content))
        before = path.read_bytes()
        with self.no_retrieval():
            self.assert_rejected(self.query(), status=2)
            self.assert_rejected(self.call('stats', 'task', '--format', 'json'), status=2)
        self.assertEqual(path.read_bytes(), before)

    def test_existing_lock_is_preserved_and_blocks_budgeted_and_legacy_callers(self):
        self.directory().mkdir(parents=True)
        lock = self.directory() / '.budget.lock'
        lock.write_text('another active caller')
        with self.no_retrieval():
            self.assert_rejected(self.query('--max-queries', '2'), status=2)
            self.assert_rejected(self.query(), status=2)
        self.assertEqual(lock.read_text(), 'another active caller')
        self.assertEqual({path.name for path in self.directory().iterdir()}, {'.budget.lock'})

    def test_in_flight_caller_holds_lock_through_retrieval_and_excludes_a_second_caller(self):
        refresh = RepositoryIndex.refresh
        observed = []

        def while_refreshing(index, *arguments, **options):
            lock = self.directory() / '.budget.lock'
            owner = lock.read_bytes()
            with self.no_retrieval():
                self.assert_rejected(self.query(), status=2)
            self.assertEqual(lock.read_bytes(), owner)
            observed.append(True)
            return refresh(index, *arguments, **options)

        with patch.object(RepositoryIndex, 'refresh', while_refreshing):
            self.assert_success(self.query('--max-queries', '2'))
        self.assertEqual(observed, [True])
        self.assertEqual(self.state()['queries'], 1)
        self.assertFalse((self.directory() / '.budget.lock').exists())

    def test_budget_file_symlinks_are_not_followed_or_overwritten(self):
        outside = Path(self.temporary.name) / 'outside.json'
        outside.write_text('outside data')
        for number, filename in enumerate(('budget.json', 'budget-policy.json', '.budget.lock')):
            name = f'link-{number}'
            directory = self.directory(name)
            directory.mkdir(parents=True)
            link = directory / filename
            try:
                link.symlink_to(outside)
            except OSError:
                self.skipTest('Symlinks unavailable on this platform')
            with self.no_retrieval():
                self.assert_rejected(self.query('--max-queries', '2', name=name), status=2)
            self.assertTrue(link.is_symlink())
            self.assertEqual(outside.read_text(), 'outside data')

    def test_existing_unbudgeted_sessions_keep_their_format_and_cannot_gain_limits(self):
        self.assert_success(self.query())
        self.assert_success(self.query())
        directory = self.directory()
        self.assertEqual({path.name for path in directory.iterdir()}, {'receipt.json', 'queries.jsonl'})
        before = {path.name: path.read_bytes() for path in directory.iterdir()}
        with self.no_retrieval():
            self.assert_rejected(self.query('--max-queries', '5'), status=2)
        self.assertEqual({path.name: path.read_bytes() for path in directory.iterdir()}, before)
        summary = self.stats()
        self.assertEqual(summary['queries'], 2)
        self.assertIsNone(summary.get('session_budget'))

    def test_explicit_database_cannot_alias_any_session_budget_file(self):
        with self.no_retrieval():
            for filename in ('budget.json', 'budget-policy.json', '.budget.lock'):
                with self.subTest(filename=filename):
                    self.assert_rejected(self.query('--max-queries', '2', '--db',
                                                    str(self.directory() / filename)), status=2)
        self.assertFalse((self.root / '.columbus').exists())


if __name__ == '__main__':
    unittest.main()
