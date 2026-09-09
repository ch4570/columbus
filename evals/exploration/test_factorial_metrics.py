"""Synthetic observations prove cost completeness without calling a model."""
import copy
import unittest

from factorial_metrics import parse_events, summarize_attempts


def usage(input_tokens=100, cached=20, output=10, writes=0, reasoning=None):
    return {'input_tokens': input_tokens, 'cached_input_tokens': cached,
            'uncached_input_tokens': input_tokens - cached, 'cache_write_tokens': writes,
            'output_tokens': output, 'reasoning_tokens': reasoning}


def attempt(identifier='one', task='task-1', arm='A', success=True, tokens=None, **extra):
    return {'attempt_id': identifier, 'task_id': task, 'arm': arm, 'success': success,
            'usage': usage() if tokens is None else tokens, 'usage_complete': True,
            'elapsed_seconds': 1.5, 'provider': 'openai', 'model': 'frozen-model', **extra}


PRICES = {'provider': 'openai', 'model': 'frozen-model', 'effective_date': '2026-09-09', 'currency': 'USD',
          'rates_per_million': {'ordinary_input': 2, 'cache_read': 0.5, 'cache_write': 3, 'output': 8}}


class EventMetricsTests(unittest.TestCase):
    def test_observed_cli_cache_write_input_alias_preserves_reported_zero(self):
        observed = {'input_tokens': 74825, 'cached_input_tokens': 49280,
                    'cache_write_input_tokens': 0, 'output_tokens': 459, 'reasoning_output_tokens': 12}
        parsed = parse_events([{'type': 'turn.completed', 'usage': observed}])
        self.assertTrue(parsed['usage_complete'])
        self.assertEqual(parsed['usage'], usage(74825, 49280, 459, writes=0, reasoning=12))
        matching = parse_events([{'type': 'turn.completed', 'usage': {**observed, 'cache_write_tokens': 0}}])
        self.assertEqual(matching['usage'], parsed['usage'])
        for change in ({'cache_write_tokens': 1}, {'cache_write_tokens': None},
                       {'cache_write_tokens': 0, 'cache_write_input_tokens': None}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'Conflicting cache-write-token details'):
                parse_events([{'type': 'turn.completed', 'usage': {**observed, **change}}])

    def test_cache_write_alias_uses_the_same_counter_and_subset_validation(self):
        raw = usage()
        raw.pop('cache_write_tokens')
        parsed = parse_events([{'type': 'turn.completed', 'usage': {**raw, 'cache_write_input_tokens': 30}}])
        self.assertEqual(parsed['usage']['cache_write_tokens'], 30)
        for invalid in (True, -1, '0', 2**63, 81):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                parse_events([{'type': 'turn.completed', 'usage': {**raw, 'cache_write_input_tokens': invalid}}])

    def test_cache_and_reasoning_are_subsets_and_missing_details_stay_null(self):
        parsed = parse_events([{'type': 'turn.completed', 'usage': {
            'input_tokens': 100, 'cached_input_tokens': 20, 'output_tokens': 10,
            'reasoning_output_tokens': 4}}])
        self.assertEqual(parsed['usage'], usage(writes=None, reasoning=4))
        self.assertTrue(parsed['usage_complete'])
        self.assertIsNone(parsed['model_round_trips'])
        self.assertIsNone(parse_events([])['usage'])
        self.assertFalse(parse_events([{'type': 'turn.failed'}])['usage_complete'])
        self.assertTrue(parse_events([{'type': 'turn.failed'}])['turn_failed'])

    def test_distinct_turns_sum_and_unidentified_or_missing_turns_remain_unknown(self):
        events = [{'type': 'turn.completed', 'turn_id': key, 'usage': usage()} for key in ('t1', 't2')]
        self.assertEqual(parse_events(events)['usage']['input_tokens'], 200)
        self.assertIsNone(parse_events([{k: v for k, v in e.items() if k != 'turn_id'} for e in events])['usage'])
        self.assertIsNone(parse_events(events + [{'type': 'turn.failed', 'turn_id': 't3'}])['usage'])
        with self.assertRaises(ValueError):
            parse_events(events + [events[0]])

    def test_tools_count_once_utf8_bytes_and_exact_duplicate_commands(self):
        command = {'type': 'command_execution', 'id': 'c1', 'command': 'rg needle'}
        events = [{'type': 'item.started', 'item': command},
                  {'type': 'item.completed', 'item': {**command, 'aggregated_output': '환불\n', 'exit_code': 0}},
                  {'type': 'item.completed', 'item': {**command, 'id': 'c2', 'aggregated_output': '', 'exit_code': 1}}]
        parsed = parse_events(events)
        self.assertEqual((parsed['tool_calls'], parsed['command_output_bytes'], parsed['failed_commands'],
                          parsed['duplicate_commands']), (2, 7, 1, 1))
        with self.assertRaises(ValueError):
            parse_events(events + [events[-1]])

    def test_unfinished_or_mismatched_turns_and_unmeasured_delegates_make_usage_incomplete(self):
        completed = {'type': 'turn.completed', 'usage': usage()}
        for suffix in ([{'type': 'turn.started'}],
                       [{'type': 'item.completed', 'item': {'type': 'collab_agent_tool_call', 'id': 'child'}}]):
            result = parse_events([completed, *suffix])
            self.assertFalse(result['usage_complete'])
            self.assertIsNone(result['usage'])
        mismatch = parse_events([{'type': 'turn.started', 'turn_id': 't1'},
                                 {**completed, 'turn_id': 't2'}])
        self.assertFalse(mismatch['usage_complete'])
        matched = parse_events([{'type': 'turn.started', 'turn_id': 't1'}, completed])
        self.assertTrue(matched['usage_complete'])
        with self.assertRaises(ValueError):
            parse_events([{'type': 'turn.started', 'turn_id': 't1'},
                          {'type': 'turn.started', 'turn_id': 't1'}])

    def test_unfinished_or_unreported_commands_do_not_fabricate_zero_counts(self):
        parsed = parse_events([{'type': 'item.started', 'item': {
            'type': 'command_execution', 'id': 'c1', 'command': 'slow'}}])
        self.assertEqual(parsed['tool_calls'], 1)
        self.assertIsNone(parsed['command_output_bytes'])
        self.assertIsNone(parsed['failed_commands'])
        unknown = parse_events([{'type': 'item.completed', 'item': {'type': 'new_tool', 'id': 'x'}}])
        self.assertEqual(unknown['unknown_tools'], ['new_tool'])
        self.assertIsNone(unknown['tool_calls'])
        known = parse_events([{'type': 'item.completed', 'item': {'type': 'mcp_tool_call', 'id': 'm'}}])
        self.assertEqual(known['tool_calls'], 1)
        self.assertEqual(known['unknown_tools'], ['mcp_tool_call'])

    def test_malformed_counts_and_overlapping_subsets_are_rejected(self):
        for key, bad in (('input_tokens', True), ('output_tokens', -1), ('cached_input_tokens', 101),
                         ('cache_write_tokens', 81), ('reasoning_tokens', 11), ('uncached_input_tokens', 79)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                parse_events([{'type': 'turn.completed', 'usage': {**usage(), key: bad}}])
        with self.assertRaises(ValueError):
            parse_events([{'type': 'item.completed', 'item': {
                'type': 'command_execution', 'exit_code': False, 'aggregated_output': ''}}])


class AttemptMetricsTests(unittest.TestCase):
    def test_failed_attempt_and_retry_costs_are_included_per_unique_successful_task(self):
        records = [attempt('failed', success=False), attempt('retry'), attempt('extra-success')]
        original = copy.deepcopy(records)
        summary = summarize_attempts(records, PRICES)['arms']['A']
        self.assertEqual((summary['attempts'], summary['failed_attempts'], summary['retry_attempts'],
                          summary['successful_tasks']), (3, 1, 2, 1))
        self.assertEqual(summary['usage']['input_tokens'], 300)
        self.assertAlmostEqual(summary['total_cost'], 0.00075)
        self.assertEqual(summary['cost_per_successful_task'], summary['total_cost'])
        self.assertEqual(records, original)

    def test_failed_tasks_keep_their_cost_and_zero_success_has_no_unit_cost(self):
        row = summarize_attempts([attempt(success=False)], PRICES)['arms']['A']
        self.assertAlmostEqual(row['total_cost'], 0.00025)
        self.assertIsNone(row['cost_per_successful_task'])
        self.assertIsNone(summarize_attempts([], PRICES)['arms']['A']['total_cost'])

    def test_missing_usage_in_a_timeout_invalidates_full_cost_without_hiding_the_attempt(self):
        failed = attempt('timeout', success=False, usage_complete=False)
        failed['usage'] = None
        row = summarize_attempts([failed, attempt('retry')], PRICES)['arms']['A']
        self.assertEqual((row['attempts'], row['successful_tasks']), (2, 1))
        self.assertFalse(row['usage_complete'])
        self.assertIsNone(row['usage'])
        self.assertIsNone(row['total_cost'])
        self.assertIsNone(row['cost_per_successful_task'])

    def test_cache_writes_and_reasoning_are_not_double_billed(self):
        row = summarize_attempts([attempt(tokens=usage(writes=30, reasoning=4))], PRICES)['arms']['A']
        # 50 ordinary + 20 cached + 30 writes = 100 total input; output stays 10.
        self.assertAlmostEqual(row['total_cost'], (50 * 2 + 20 * .5 + 30 * 3 + 10 * 8) / 1_000_000)
        self.assertEqual(row['usage']['output_tokens'], 10)

    def test_missing_prices_or_unreported_cache_writes_leave_cost_unknown(self):
        self.assertIsNone(summarize_attempts([attempt()])['arms']['A']['total_cost'])
        record = attempt(tokens=usage(writes=None, reasoning=None))
        self.assertIsNone(summarize_attempts([record], PRICES)['arms']['A']['total_cost'])
        declared = {**PRICES, 'cache_write_accounting': 'included_in_ordinary_input'}
        row = summarize_attempts([record], declared)['arms']['A']
        self.assertAlmostEqual(row['total_cost'], 0.00025)
        self.assertIsNone(row['usage']['cache_write_tokens'])
        unidentified = attempt()
        unidentified.pop('model')
        self.assertIsNone(summarize_attempts([unidentified], PRICES)['arms']['A']['total_cost'])

    def test_explicit_self_only_delegates_add_usage_and_failures_without_double_wall_time(self):
        child = attempt('child', success=False, elapsed_seconds=1)
        parent = attempt('parent', usage_scope='self_only', delegates=[child], elapsed_seconds=3)
        row = summarize_attempts([parent], PRICES)['arms']['A']
        self.assertEqual((row['all_attempts'], row['delegate_attempts'], row['failed_delegate_attempts']), (2, 1, 1))
        self.assertEqual(row['usage']['input_tokens'], 200)
        self.assertEqual(row['elapsed_seconds'], 3)
        self.assertAlmostEqual(row['total_cost'], 0.0005)
        parent.pop('usage_scope')
        unknown = summarize_attempts([parent], PRICES)['arms']['A']
        self.assertFalse(unknown['delegate_scope_known'])
        self.assertIsNone(unknown['total_cost'])
        self.assertIsNone(unknown['usage'])

    def test_duplicate_ids_and_nested_or_cross_arm_delegates_are_rejected(self):
        for records in ([attempt(), attempt()],
                        [attempt(delegates=[attempt()])],
                        [attempt(delegates=[attempt('child', arm='B')])],
                        [attempt(delegates=[attempt('child', delegates=[attempt('grandchild')])])]):
            with self.subTest(records=records), self.assertRaises(ValueError):
                summarize_attempts(records)

    def test_optional_counts_are_summed_only_when_every_attempt_reports_them(self):
        counts = {'tool_calls': 2, 'command_output_bytes': 700, 'failed_commands': 1,
                  'duplicate_commands': 1, 'model_round_trips': None, 'unknown_tools': []}
        records = [attempt('first', **counts), attempt('second', **counts)]
        row = summarize_attempts(records)['arms']['A']
        self.assertEqual((row['tool_calls'], row['command_output_bytes'], row['failed_commands']), (4, 1400, 2))
        self.assertIsNone(row['model_round_trips'])
        records[1].pop('command_output_bytes')
        self.assertIsNone(summarize_attempts(records)['arms']['A']['command_output_bytes'])

    def test_price_and_observation_contracts_reject_malformed_data(self):
        for change in ({'provider': 'other'}, {'effective_date': '2026-02-30'}, {'currency': 'usd'},
                       {'model': ''}, {'rates_per_million': {'ordinary_input': 1}},
                       {'cache_write_accounting': []},
                       {'rates_per_million': {**PRICES['rates_per_million'], 'output': float('nan')}},
                       {'rates_per_million': {**PRICES['rates_per_million'], 'output': 10**400}},
                       {'rates_per_million': {**PRICES['rates_per_million'], 'output': True}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                summarize_attempts([attempt()], {**PRICES, **change})
        for change in ({'success': 1}, {'usage_complete': 0}, {'elapsed_seconds': float('inf')},
                       {'elapsed_seconds': 10**400}, {'arm': 'E'}, {'tool_calls': -1},
                       {'provider': 'other'}, {'model': []}, {'unknown_tools': 'not-a-list'}, {'usage': None}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                summarize_attempts([attempt(**change)])
        self.assertIsNone(summarize_attempts([attempt(model='other-model')], PRICES)['arms']['A']['total_cost'])


if __name__ == '__main__':
    unittest.main()
