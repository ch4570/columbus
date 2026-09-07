"""Observed output budgets, source-span receipts, and private local measurements."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from repoatlas.cli import main
from repoatlas.index import RepositoryIndex, byte_size
from repoatlas.presentation import render
from repoatlas.receipts import ReceiptFile
from repoatlas.telemetry import FIELDS, summarize


class TokenEconomyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'repo with spaces'
        self.root.mkdir()
        (self.root / '정산.py').write_text(
            'class Ledger:\n'
            '    def refund(self, amount):\n'
            '        # QUERY_PRIVATE_MARKER\n'
            '        return amount\n\n'
            'def cancel(ledger):\n'
            '    return ledger.refund(10)\n', encoding='utf-8')
        self.index = RepositoryIndex(self.root / '.repoatlas/index.sqlite')
        self.index.refresh(self.root)
        self.receipt_path = self.root / '.repoatlas/session.json'

    def cli(self, *args):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            status = main(['--repo', str(self.root), '--db', str(self.index.db), *args])
        return status, output.getvalue(), error.getvalue()

    def next_context(self, query='refund', budget=4096, output_format='text', path=None):
        receipt = ReceiptFile(str(self.receipt_path), self.index.status())
        packet = self.index.context(query, budget_bytes=budget, output_format=output_format, receipt=receipt.data, path=path)
        receipt.save(packet)
        return packet

    def test_text_and_json_complete_unicode_output_budgets(self):
        for output_format in ('text', 'json'):
            for budget in (2048, 2100, 4096, 6000):
                for mode in ('map', 'signatures', 'snippets'):
                    with self.subTest(output_format=output_format, budget=budget, mode=mode):
                        kwargs = {'budget_bytes': budget, 'output_format': output_format}
                        packet = (self.index.repo_map(**kwargs) if mode == 'map' else
                                  self.index.context('refund', mode=mode, **kwargs))
                        output = render(packet, output_format)
                        size = len(output.encode('utf-8'))
                        self.assertEqual(packet['used_bytes'], size)
                        self.assertLessEqual(size, budget)
                        self.assertEqual(packet['estimated_tokens'], (size + 2) // 3)
                        self.assertTrue(packet['items'])
                        if output_format == 'text':
                            self.assertIn('UNTRUSTED', output)
                            self.assertIn(packet['revision'], output)
                            self.assertIn('fidelity=ast', output)
                            self.assertIn('정산.py:', output)
                            self.assertIn('truncated=', output)

    def test_text_retains_more_signatures_with_equal_budget(self):
        (self.root / 'many.py').write_text('\n'.join(f'def refund_{n}(x): return x' for n in range(50)))
        self.index.refresh(self.root)
        plain = self.index.repo_map(budget_bytes=2048, output_format='text')
        structured = self.index.repo_map(budget_bytes=2048)
        self.assertGreater(len(plain['items']), len(structured['items']))

    def test_cli_formats_preserve_default_json_and_budget(self):
        for command in (['map'], ['search', 'refund'], ['context', 'refund'],
                        ['symbol', 'refund'], ['neighbors', 'refund'], ['impact', 'refund']):
            status, output, error = self.cli(*command, '--snapshot')
            self.assertEqual(status, 0, error)
            self.assertIsInstance(json.loads(output), dict)
            status, output, error = self.cli(*command, '--format', 'text', '--snapshot')
            self.assertEqual(status, 0, error)
            self.assertIn('UNTRUSTED', output)
            self.assertIn('정산.py', output)
        for command in ('context', 'map'):
            status, output, error = self.cli(command, 'refund', '--format', 'text', '--pretty', '--budget-tokens', '700')
            self.assertEqual(status, 0, error)
            self.assertLessEqual(len(output.encode('utf-8')), 2100)

    def test_receipt_excludes_overlapping_parent_child_spans_across_requests(self):
        all_spans, bodies = {}, []
        for _ in range(8):
            packet = self.next_context(budget=2048)
            for item in packet['items']:
                previous = all_spans.setdefault(item['path'], set())
                current = set(range(item['source_start_offset'], item['source_end_offset']))
                self.assertFalse(previous & current)
                previous.update(current)
                bodies.append(item['source'])
            if not packet['items']:
                break
        else:
            self.fail('Receipt never exhausted a small file')
        self.assertGreater(packet['seen_candidates'], 0)
        self.assertEqual(packet['economy']['source_bytes_returned'], 0)
        self.assertEqual(packet['omitted_candidates'], 0)
        self.assertGreater(packet['receipt']['seen_source_bytes'], 0)
        self.assertIn('return amount', '\n'.join(bodies))

    def test_receipt_continues_beyond_truncated_symbol_and_long_unicode_line(self):
        (self.root / 'long.py').write_text('def very_long():\n' +
            ''.join(f'    # row {n:03d}\n' for n in range(120)) + '    return "THE_END"\n')
        (self.root / 'single.py').write_text('def very_wide(): return "' + '한글' * 1400 + 'TAIL"\n')
        self.index.refresh(self.root)
        for query, path, tail in (('very_long', 'long.py', 'THE_END'), ('very_wide', 'single.py', 'TAIL')):
            self.receipt_path = self.root / '.repoatlas' / (path + '.json')
            seen, source = set(), []
            for _ in range(35):
                packet = self.next_context(query, budget=2048, path=path)
                for item in packet['items']:
                    self.assertEqual(item['path'], path)
                    span = set(range(item['source_start_offset'], item['source_end_offset']))
                    self.assertFalse(seen & span)
                    seen.update(span)
                    source.append(item['source'])
                    if item['source_start_offset'] > 0:
                        self.assertTrue(item['truncated'])
                self.assertLessEqual(len(render(packet, 'text').encode('utf-8')), 2048)
                if not packet['items']:
                    break
            else:
                self.fail('Receipt stalled on truncated source')
            self.assertIn(tail, ''.join(source))

    def test_receipt_hash_invalidates_only_changed_source_and_checks_stale_files(self):
        first = self.next_context()
        before = {item['source_hash'] for item in first['items']}
        source = self.root / '정산.py'
        source.write_text(source.read_text() + '\ndef refund_new(): return "NEW_SOURCE"\n')
        stale = self.next_context()
        self.assertGreater(stale['stale_candidates'], 0)
        self.assertEqual(stale['items'], [])
        self.index.refresh(self.root)
        changed = self.next_context()
        self.assertEqual(changed['receipt']['status'], 'revision_changed_hash_checked')
        self.assertTrue(changed['items'])
        self.assertTrue(all(item['source_hash'] not in before for item in changed['items']))
        self.assertIn('NEW_SOURCE', json.dumps(changed))
        (self.root / 'unrelated.py').write_text('def unrelated(): return 42\n')
        self.index.refresh(self.root)
        unchanged = self.next_context()
        self.assertEqual(unchanged['items'], [])

    def test_receipt_decoder_change_cannot_hide_unread_source_with_unchanged_raw_hash(self):
        # Python's encoding cookie decodes the multibyte prefix as Latin-1.
        # After switching the configured language, UTF-8 decoding moves bar
        # exactly onto the old character range that was emitted for foo.
        prefix = '# coding: latin-1\n# ' + 'é' * 100 + '\n'
        foo = 'def foo():\n    return 111\n'
        old_foo_start = len(prefix.encode('utf-8').decode('latin-1'))
        padding = '#' + 'x' * (old_foo_start - len(prefix + foo) - 2) + '\n'
        content = prefix + foo + padding + 'def bar():\n    return 222\n'
        self.assertEqual(content.index('def bar'), old_foo_start)
        (self.root / 'logic.custom').write_bytes(content.encode('utf-8'))
        config = self.root / '.repoatlas.json'
        config.write_text(json.dumps({'extensions': {'.custom': 'python'}}))
        self.index.refresh(self.root)
        self.next_context('refund')  # An unchanged file should still be reusable.
        receipt = ReceiptFile(str(self.receipt_path), self.index.status())
        original = self.index.context('foo', path='logic.custom', exclude_ids=['logic.custom::module'], receipt=receipt.data)
        self.assertEqual(len(original['items']), 1)
        self.assertEqual(original['items'][0]['source_start_offset'], old_foo_start)
        self.assertIn('return 111', original['items'][0]['source'])
        receipt.save(original)
        old_hash = original['items'][0]['source_hash']

        config.write_text(json.dumps({'extensions': {'.custom': 'custom'}, 'declarations': {'custom': ['def']}}))
        self.index.refresh(self.root)
        receipt = ReceiptFile(str(self.receipt_path), self.index.status())
        current = self.index.context('bar', path='logic.custom', exclude_ids=['logic.custom::module'], receipt=receipt.data)
        self.assertTrue(current['items'], 'Previously unread bar must survive a decoder change')
        self.assertIn('def bar', current['items'][0]['source'])
        self.assertEqual(current['items'][0]['source_hash'], old_hash)
        self.assertNotEqual(current['items'][0]['source_view_hash'], original['items'][0]['source_view_hash'])
        self.assertEqual(current['receipt']['seen_source_bytes'], 0)
        receipt.save(current)
        recorded = json.loads(self.receipt_path.read_text())['files']['logic.custom']
        self.assertEqual(recorded['spans'], [[current['items'][0]['source_start_offset'], current['items'][0]['source_end_offset']]])
        self.assertEqual(self.next_context('refund')['items'], [])

    def test_legacy_receipt_without_decoded_view_hash_retrieves_again_then_upgrades(self):
        self.next_context()
        legacy = json.loads(self.receipt_path.read_text())
        for record in legacy['files'].values():
            record.pop('source_view_hash', None)
        self.receipt_path.write_text(json.dumps(legacy))
        packet = self.next_context()
        self.assertTrue(packet['items'])
        self.assertEqual(packet['receipt']['seen_source_bytes'], 0)
        upgraded = json.loads(self.receipt_path.read_text())
        self.assertTrue(all(len(record['source_view_hash']) == 64 for record in upgraded['files'].values()))

    def test_malformed_foreign_and_symlink_receipts_are_preserved(self):
        for content in ('not json', '{}', '[1,2]', '{"schema":"someone-else"}'):
            self.receipt_path.write_text(content)
            status, output, error = self.cli('context', 'refund', '--receipt', str(self.receipt_path))
            self.assertEqual(status, 2, error)
            self.assertEqual(output, '')
            self.assertEqual(self.receipt_path.read_text(), content)
        self.receipt_path.unlink()
        self.next_context()
        data = json.loads(self.receipt_path.read_text())
        data['repository'] = '0' * 64
        self.receipt_path.write_text(json.dumps(data))
        before = self.receipt_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'another repository'):
            self.next_context()
        self.assertEqual(self.receipt_path.read_bytes(), before)
        self.receipt_path.unlink()
        destination = self.root / 'keep.txt'
        destination.write_text('preserve')
        try:
            self.receipt_path.symlink_to(destination)
        except OSError:
            self.skipTest('Symlinks unavailable on this platform')
        with self.assertRaisesRegex(ValueError, 'non-symlink'):
            ReceiptFile(str(self.receipt_path), self.index.status())
        self.assertEqual(destination.read_text(), 'preserve')

    def test_receipt_does_not_replace_changed_file(self):
        self.next_context()
        receipt = ReceiptFile(str(self.receipt_path), self.index.status())
        packet = self.index.context('refund', receipt=receipt.data)
        self.receipt_path.write_text('concurrent owner data')
        with self.assertRaisesRegex(ValueError, 'changed during retrieval'):
            receipt.save(packet)
        self.assertEqual(self.receipt_path.read_text(), 'concurrent owner data')

    def test_telemetry_records_exact_payload_sizes_and_never_queries_or_source(self):
        log = self.root / '.repoatlas/query.jsonl'
        for command, output_format in (('context', 'text'), ('search', 'json')):
            status, output, error = self.cli(command, 'QUERY_PRIVATE_MARKER', '--format', output_format,
                                             '--telemetry', str(log), '--pretty')
            self.assertEqual(status, 0, error)
            row = json.loads(log.read_text().splitlines()[-1])
            self.assertEqual(set(row), FIELDS)
            self.assertEqual(row['output_bytes'], len(output.encode('utf-8')))
            self.assertEqual(row['estimated_tokens'], (row['output_bytes'] + 2) // 3)
            self.assertGreater(row['returned_items'], 0)
        raw = log.read_text()
        self.assertNotIn('QUERY_PRIVATE_MARKER', raw)
        self.assertNotIn('return amount', raw)
        self.assertNotIn('정산.py', raw)
        self.assertNotIn(str(self.root), raw)
        summary = summarize(str(log))
        self.assertEqual(summary['queries'], 2)
        self.assertEqual(summary['commands'], {'context': 1, 'search': 1})
        self.assertEqual(summary['output_bytes'], sum(json.loads(line)['output_bytes'] for line in raw.splitlines()))
        status, output, error = self.cli('telemetry', str(log))
        self.assertEqual(status, 0, error)
        self.assertIn('not measured model input', output)

    def test_telemetry_rejects_existing_unrelated_file_without_output_or_changes(self):
        log = self.root / '.repoatlas/not-a-log.jsonl'
        for content in ('', 'private data', '{"schema":"other"}\n', '\u0080\n'):
            log.write_text(content)
            status, output, error = self.cli('search', 'refund', '--telemetry', str(log))
            self.assertEqual(status, 2, error)
            self.assertEqual(output, '')
            self.assertEqual(log.read_text(), content)

    def test_json_receipt_budget_includes_receipt_metadata(self):
        packet = self.next_context(budget=2048, output_format='json')
        self.assertTrue(packet['items'])
        self.assertEqual(byte_size(packet), packet['used_bytes'])
        self.assertLessEqual(byte_size(packet), 2048)


if __name__ == '__main__':
    unittest.main()
