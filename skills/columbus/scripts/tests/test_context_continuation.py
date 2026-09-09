"""Receipts continue every lexical page without dropping partial source or scope."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from columbus.cli import main
from columbus.index import RepositoryIndex
from columbus.presentation import render
from columbus.receipts import LEGACY_SCHEMA, SCHEMA, ReceiptFile, validate


class ContextContinuationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.index = RepositoryIndex(self.root / '.columbus/index.sqlite')
        self.receipt = self.root / '.columbus/receipt.json'

    def populate(self, count):
        for number in range(count):
            (self.root / f'entry_{number:03}.py').write_text(f'def target():\n    return {number}\n')
        self.index.refresh(self.root)

    def query(self, *, save=True, **options):
        receipt = ReceiptFile(str(self.receipt), self.index.status())
        packet = self.index.context('target', receipt=receipt.data, **options)
        if save:
            receipt.save(packet)
        return packet

    def exhaust(self, fmt, budget=2048, **options):
        spans, bodies, cursors = {}, {}, []
        for _ in range(500):
            packet = self.query(budget_bytes=budget, output_format=fmt, **options)
            self.assertEqual(packet['used_bytes'], len(render(packet, fmt).encode()))
            self.assertLessEqual(packet['used_bytes'], budget)
            self.assertGreaterEqual(packet['omitted_candidates'], 0)
            for item in packet['items']:
                span = set(range(item['source_start_offset'], item['source_end_offset']))
                self.assertFalse(span & spans.setdefault(item['path'], set()))
                spans[item['path']].update(span)
                bodies.setdefault(item['path'], []).append(item['source'])
            saved = json.loads(self.receipt.read_text())
            cursors.append(tuple(saved['continuations'].values()))
            if not packet['receipt']['has_more']:
                return packet, bodies, cursors
            if not packet['items'] and not packet['stale_candidates']:
                self.assertGreater(len(cursors), 1)
                self.assertNotEqual(cursors[-1], cursors[-2], 'An empty page must advance discovery')
        self.fail('Receipt failed to exhaust bounded fixture')

    def test_more_than_150_matches_are_delivered_without_repeated_source(self):
        self.populate(175)
        for fmt in ('json', 'text'):
            self.receipt = self.root / '.columbus' / (fmt + '.json')
            packet, bodies, cursors = self.exhaust(fmt, budget=6000)
            self.assertEqual(set(bodies), {f'entry_{n:03}.py' for n in range(175)})
            for number in range(175):
                self.assertIn(f'return {number}', ''.join(bodies[f'entry_{number:03}.py']))
            self.assertEqual(packet['omitted_candidates'], 0)
            self.assertTrue(any(cursors))
            self.assertEqual(json.loads(self.receipt.read_text())['schema'], SCHEMA)

    def test_small_json_keeps_source_budget_and_cursor_is_saved_after_delivery(self):
        self.populate(30)
        receipt = ReceiptFile(str(self.receipt), self.index.status())
        original = copy.deepcopy(dict(receipt.data))
        packet = self.index.context('target', budget_bytes=2048, receipt=receipt.data)
        self.assertGreater(len(packet['items']), 0)
        self.assertEqual(dict(receipt.data), original)
        self.assertNotIn('next_cursor', packet['receipt'])
        self.assertNotIn('continuation_scope', packet['receipt'])
        self.assertFalse(self.receipt.exists())
        receipt.save(packet)
        self.assertTrue(json.loads(self.receipt.read_text())['continuations'])
        self.assertLessEqual(len(render(packet).encode()), 2048)

    def test_partial_unicode_and_parent_child_spans_survive_page_transitions(self):
        self.populate(25)
        source = ('class target:\n    def nested(self):\n        return "' + '한글' * 1000 + 'TAIL"\n')
        (self.root / 'entry_000.py').write_text(source, encoding='utf-8')
        self.index.refresh(self.root)
        _, bodies, _ = self.exhaust('text', budget=2048)
        self.assertEqual(len(bodies), 25)
        self.assertIn('TAIL', ''.join(bodies['entry_000.py']))

    def test_scope_and_revision_changes_restart_discovery_preserving_source_hash_checks(self):
        self.populate(35)
        first = self.query(budget_bytes=2048)
        before = json.loads(self.receipt.read_text())
        self.assertTrue(before['continuations'])
        narrowed = self.query(path='entry_03*.py', budget_bytes=6000)
        self.assertTrue(narrowed['items'])
        self.assertTrue(all(item['path'].startswith('entry_03') for item in narrowed['items']))
        self.assertTrue(set(before['continuations']) <= set(json.loads(self.receipt.read_text())['continuations']))
        self.assertEqual(self.query(language='java')['items'], [])
        (self.root / first['items'][0]['path']).write_text('def target():\n    return "CHANGED"\n')
        stale = self.query(budget_bytes=2048)
        self.assertGreater(stale['stale_candidates'], 0)
        self.index.refresh(self.root)
        changed = self.query(budget_bytes=2048)
        self.assertEqual(changed['receipt']['status'], 'revision_changed_hash_checked')
        self.assertIn('CHANGED', json.dumps(changed))

    def test_empty_bounded_scan_advances_to_unread_source(self):
        self.populate(65)
        receipt = ReceiptFile(str(self.receipt), self.index.status())
        receipt.save({'revision': self.index.status()['revision'], 'items': [
            self.index.symbol(f'entry_{n:03}.py::target:function') for n in range(45)]})
        with patch('columbus.retrieval.CONTEXT_PAGE_LIMIT', 2):
            receipt = ReceiptFile(str(self.receipt), self.index.status())
            first = self.index.context('target', receipt=receipt.data, budget_bytes=6000)
            self.assertEqual(first['items'], [])
            self.assertTrue(first['receipt']['has_more'])
            receipt.save(json.loads(json.dumps(first)))
            before = json.loads(self.receipt.read_text())['continuations']
            self.assertTrue(before)
            second = self.query(budget_bytes=6000)
            self.assertTrue(second['items'])
            self.assertTrue(all(int(item['path'][6:9]) >= 45 for item in second['items']))

    def test_changed_packet_is_rejected_and_stale_page_requires_sync(self):
        self.populate(25)
        receipt = ReceiptFile(str(self.receipt), self.index.status())
        packet = self.index.context('target', receipt=receipt.data, budget_bytes=2048)
        changed = copy.deepcopy(packet)
        changed['items'] = []
        with self.assertRaisesRegex(ValueError, 'response changed before receipt save'):
            receipt.save(changed)
        self.assertFalse(self.receipt.exists())
        unrelated = ReceiptFile(str(self.receipt), self.index.status())
        with self.assertRaisesRegex(ValueError, 'belongs to another receipt state'):
            unrelated.save(packet)
        copied = self.index.context('target', receipt=copy.deepcopy(unrelated.data), budget_bytes=2048)
        with self.assertRaisesRegex(ValueError, 'belongs to another receipt state'):
            unrelated.save(copied)
        self.index.context('target', path='entry_000.py', receipt=receipt.data, budget_bytes=2048)
        with self.assertRaisesRegex(ValueError, 'response changed before receipt save'):
            receipt.save(packet)
        self.assertFalse(self.receipt.exists())
        (self.root / 'entry_000.py').write_text('def target(): return "CHANGED"\n')
        first = self.query(budget_bytes=64000)
        self.assertEqual(len(first['items']), 19)
        self.assertEqual(first['stale_candidates'], 1)
        before = self.receipt.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Stale source prevents receipt continuation'):
            self.query(budget_bytes=64000)
        self.assertEqual(self.receipt.read_bytes(), before)
        self.index.refresh(self.root)
        packet, bodies, _ = self.exhaust('json', budget=64000)
        self.assertFalse(packet['receipt']['has_more'])
        self.assertEqual(set(bodies), {'entry_000.py', *(f'entry_{n:03}.py' for n in range(20, 25))})
        self.assertIn('CHANGED', ''.join(bodies['entry_000.py']))

    def test_legacy_upgrade_malformed_state_and_failed_save_preserve_existing_file(self):
        self.populate(30)
        self.query(budget_bytes=2048)
        legacy = json.loads(self.receipt.read_text())
        legacy['schema'] = LEGACY_SCHEMA
        legacy.pop('continuations')
        self.receipt.write_text(json.dumps(legacy))
        self.query(budget_bytes=2048)
        current = json.loads(self.receipt.read_text())
        self.assertEqual(current['schema'], SCHEMA)
        self.assertTrue(current['continuations'])
        for replacement in ([], {'bad': 'x'}, {'a' * 64: ''}, {'a' * 64: 'x' * 32769}):
            malformed = dict(current, continuations=replacement)
            with self.assertRaises(ValueError):
                validate(malformed)
        for schema in ({}, [], True):
            with self.assertRaises(ValueError):
                validate(dict(legacy, schema=schema))
        receipt = ReceiptFile(str(self.receipt), self.index.status())
        packet = self.index.context('target', receipt=receipt.data, budget_bytes=2048)
        self.receipt.write_text('concurrent owner data')
        with self.assertRaisesRegex(ValueError, 'changed during retrieval'):
            receipt.save(packet)
        self.assertEqual(self.receipt.read_text(), 'concurrent owner data')

    def test_exclusions_skip_earlier_search_pages_and_unfit_source_fails_explicitly(self):
        self.populate(205)
        excluded = [f'entry_{n:03}.py::target:function' for n in range(200)]
        result = self.index.context('target', exclude_ids=excluded, budget_bytes=6000)
        self.assertTrue(result['items'])
        self.assertEqual(result['excluded_candidates'], 200)
        name = 'target' + 'x' * 400
        source = self.root / 'large.py'
        source.write_text(f'def {name}(): return 1\n')
        self.index.refresh(self.root)
        receipt = ReceiptFile(str(self.root / '.columbus/new.json'), self.index.status())
        with self.assertRaisesRegex(ValueError, 'Budget too small'):
            self.index.context(f'large.py::{name}:function', budget_bytes=2048, receipt=dict(receipt.data))
        self.assertIsNone(receipt.data.pending)

    def test_cli_session_and_search_cursor_keep_snapshot_scope(self):
        self.populate(30)

        def run(*arguments):
            output, error = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                code = main(['--repo', str(self.root), '--db', str(self.index.db), *arguments])
            return code, output.getvalue(), error.getvalue()

        code, output, error = run('search', 'target', '--limit', '20', '--snapshot')
        self.assertEqual(code, 0, error)
        page = json.loads(output)
        code, output, error = run('search', 'target', '--cursor', page['next_cursor'], '--snapshot')
        self.assertEqual(code, 0, error)
        self.assertFalse({n['id'] for n in page['hits']} & {n['id'] for n in json.loads(output)['hits']})
        self.assertEqual(run('search', 'different', '--cursor', page['next_cursor'], '--snapshot')[0], 2)
        delivered = set()
        for _ in range(30):
            code, output, error = run('explore', 'target', '--session', 'demo', '--budget-bytes', '2048',
                                       '--format', 'json', '--snapshot')
            self.assertEqual(code, 0, error)
            packet = json.loads(output)
            delivered.update(item['path'] for item in packet['items'])
            if not packet['receipt']['has_more']:
                break
        self.assertEqual(len(delivered), 30)


if __name__ == '__main__':
    unittest.main()
